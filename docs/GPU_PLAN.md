# KTRF GPU 실행 계획 (GPU Execution Plan)

**상태:** In progress — G1 구현·실측, G2 파이프라인 스캐폴드+스모크 검증,
G3 residency manager 구현 (2026-08-24; 현황은 docs/ROADMAP.md 참조)
**대상 하드웨어:** NVIDIA RTX 3080 10GB (개발기), 프로덕션은 §5.3의 "8GB GPU" 제약 유지
**관계 문서:** PLAN.md §5.3, §32.3, §33–§36, §41, §48; MODEL_RECOMMEND.md

본 문서는 구현 계획이며 규범(spec)이 아니다. 스펙 본문 편입이 필요하면 v0.4
개정(§0 changelog + §56 결정 등재)으로 처리한다.

---

## 0. 원칙 — GPU가 바꾸지 않는 것

- **Level A 결정적 경로는 영원히 CPU-only다** (§4.7, §5.3). exact/boundary/
  FST/conformance는 GPU와 무관하며, GPU 장애 시에도 Level A는 무영향이다.
- **결정적 모드(deterministic mode)는 CPU 추론을 유지한다.** CUDA 커널의
  비결정성(atomics, cuDNN 알고리즘 선택) 때문에 §34의 "고정 시드·고정 커널"
  요구는 CPU EP에서만 보장한다. GPU는 처리량 최적화 경로다. 재현성 요구
  요청(REQ-GRPH-001 회귀 테스트, conformance)은 CPU로 라우팅한다.
- **per-tenant full fine-tuning은 계속 비목표다** (§6). GPU 학습은 공유 base
  모델(Stage B/C) 1회성 + 경량 adapter(§48.4)에 한정한다.

---

## Phase G1 — GPU 추론 (현행 M4 스택, 코드 변경 최소)

M4의 `OnnxE5Encoder` / `OnnxCrossEncoder`는 provider 파라미터를 받는다
(`device="cuda"` → CUDAExecutionProvider, 실패 시 CPU 자동 fallback — 구현
완료). 남은 작업은 런타임 설치와 실측이다.

1. `pip install onnxruntime-gpu` (CPU 패키지와 교체; CUDA 12.x 런타임 DLL 동봉
   여부는 버전별 확인 — 필요 시 CUDA Toolkit 12.x 설치).
2. 검증: `OnnxE5Encoder(dir, device="cuda")` 로드 후
   `session.get_providers()`에 `CUDAExecutionProvider` 확인.
3. 벤치마크 확장(`eval/benchmark.py`): 인코딩 배치 처리량(문장/s)과 resolve
   p95를 CPU vs GPU로 비교 → §53 벤치마크 문서에 GPU 열 추가.
4. compile-time 벡터 인코딩의 배치화(현행 batch 32 → GPU에서 256).

**예상 효과:** e5-small 기준 인코딩 처리량 ~5–15×. 10만 entity glossary의
compile-time 인코딩이 CPU 수십 분 → GPU 수 분으로 단축 (§5.3 목표 규모).
**완료 기준:** GPU/CPU 결과 코사인 오차 < 1e-3 확인, 벤치마크 수치 발행.
**주의:** fp16 변환 시 `entity_encoder_hash`가 달라지므로 기존 벡터 재사용
금지(§11.3) — 재컴파일 필수.

## Phase G2 — Stage B/C 학습 (torch + CUDA)

MODEL_RECOMMEND.md의 선택을 실행한다: cross-encoder/termness는
**KLUE-RoBERTa-base**에서, bi-encoder는 **multilingual-e5** (또는 KURE-v1
비교군)에서 fine-tune.

**데이터 준비 게이트(선행 조건 — 이것이 진짜 병목이다):**

- Stage B(sense cross-encoder): ACCEPTED corrections 중 sense 라벨
  (`WRONG_ENTITY`/`SHOULD_BE_RESOLVED`) **≥ 5,000건** 또는 동등한 teacher 검증
  라벨(§39, validator 통과분만). 미달 시 학습하지 않는다.
- 카탈로그 생성 데이터 단독 학습 금지 — §40.2의 상한(`deterministic_max:
  0.20`)을 config로 강제한다. 합성 데이터만으로 학습하면 BENCHMARKS.md가
  잡아낸 과적합을 모델 층위에서 재생산한다.
- golden set은 학습에 절대 사용하지 않는다(§45.8) — 게이트 평가 전용.

**작업:**

1. `pip install torch --index-url https://download.pytorch.org/whl/cu124`
   (+transformers). 학습 전용 의존성 — 런타임 배포에는 불포함.
2. `models/training/` 스캐폴드: §36 dictionary-conditioned episode 빌더
   (corrections + mention_state features → candidate-constrained 학습쌍),
   §40 혼합비 config, §42 분할(UA/UE/tenant holdout).
3. Stage B: KLUE-RoBERTa-base cross-encoder, `[context × entity profile]`
   pairwise margin loss (§35.2). VRAM 추정: 110M fp16 + AdamW, batch 32,
   seq 192 ≈ 5–6GB → 3080 10GB 단독 학습 가능. 부족 시 grad accumulation.
4. Stage C: bi-encoder fine-tune — in-batch negatives + Stage B distillation
   (§35.3). e5-small(118M)은 여유; e5-base(278M)는 batch 축소 또는 LoRA.
5. ONNX export → 기존 로더로 무변경 편입:
   `compile_snapshot(g, encoder=load_encoder("onnx:models/<new>"),
   reranker=load_reranker("onnx:models/<xenc>"))`.
6. 활성화 게이트(§48.3, §41): golden 회귀 + conformance 100% + NEURAL_EVAL
   재실행에서 기존 기준선(hash 96.8% / e5 98.4% gold-in-set) 대비 비열화
   확인 후에만 activation. 실패 시 이전 snapshot 유지(INV-014).

**완료 기준:** 학습된 cross-encoder가 LexicalCrossEncoder 기준선 대비
AP-류 다의어 top-1 accuracy(|mention)를 유의하게 개선(§43.8 CI 기준),
UE-canonical-only recall 비열화.

## Phase G3 — 멀티테넌트 GPU 상주 정책 (§32.3)

1. tenant adapter(LoRA)는 기본 CPU 상주, 요청 시 GPU 스왑.
2. 동시 GPU 상주 adapter 상한 + LRU 교체 — `TieredSnapshotStore` 패턴을
   adapter 층에 재사용(refcount 보호 동일 적용).
3. base 모델 1copy 공유, 후보·결과 격리는 기존 §12 계약 그대로.
4. 관측: adapter 스왑 latency, GPU 메모리 수위, tenant별 GPU 점유를
   `RuntimeMetrics`에 추가.

**완료 기준:** 3-tenant 동시 부하에서 cross-tenant 누출 0(기존 security
test 확장) + adapter 스왑 p95 실측 발행.

---

## 실행 순서와 트리거

| Phase | 트리거 | 규모 |
|---|---|---|
| G1 | 즉시 가능 (데이터 불필요) | ~1일 |
| G2 | 라벨 게이트 충족 시 (corrections 축적 후) | 1–2주 + 실험 |
| G3 | 다중 tenant + adapter 도입 시 | G2 이후 |

## 리스크

| 리스크 | 대응 |
|---|---|
| CUDA 비결정성 vs 재현성 계약 | 결정적 모드=CPU 고정; GPU는 처리량 경로로만 |
| 합성 라벨 과적합 (모델 층위) | §40 혼합 상한 강제, BENCHMARKS/WILD 게이트를 학습 후 필수 재실행 |
| fp16/quantization 회귀 | §46.2 quantization regression 지표 + encoder hash 분리 |
| onnxruntime-gpu DLL 지옥 (Windows) | CPU fallback이 항상 동작; CI는 CPU 고정 |
| 10GB VRAM 한계 (KURE-v1 568M 비교 실험) | 추론만 GPU, 학습은 e5-small/base 우선; KURE는 평가 참조군 |
