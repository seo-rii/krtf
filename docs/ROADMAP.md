# KTRF Roadmap & Status

**기준일:** 2026-08-25 · **스펙:** PLAN.md v0.3 · 본 문서는 계획/현황 문서이며 규범이 아니다.
수치의 단일 출처는 `reports/`의 생성 리포트다 — 본 문서와 리포트가 어긋나면 리포트가 맞다.

## 문서 지도

| 문서 | 내용 | 성격 |
|---|---|---|
| [PLAN.md](../PLAN.md) | KTRF 기술 스펙 v0.3 (규범) | spec |
| [MODEL_RECOMMEND.md](../MODEL_RECOMMEND.md) | 신경 모델 선정 근거 | 결정 기록 |
| [docs/GPU_PLAN.md](GPU_PLAN.md) | GPU 실행 계획 (G1–G3) | 계획 |
| [PLAN_PI.md](../PLAN_PI.md) | Pi Coding Agent Extension 통합 설계 (pi-ktrf) | 계획 |
| [docs/VARIANTS_PLAN.md](VARIANTS_PLAN.md) | 변형 해석·미등록 약어 로드맵 (M0–M6) | 계획 |
| [docs/traceability.yaml](traceability.yaml) | REQ ↔ 테스트 추적성 (CI 강제) | 계약 |
| [reports/EVALUATION.md](../reports/EVALUATION.md) | 카탈로그 conformance + release gate | 생성 리포트 |
| [reports/BENCHMARKS.md](../reports/BENCHMARKS.md) | 적대적 anti-overfitting 매트릭스 | 생성 리포트 |
| [reports/WILD_CORPUS.md](../reports/WILD_CORPUS.md) | 실 한국어 텍스트(KLUE) 평가 | 생성 리포트 |
| [reports/NEURAL_EVAL.md](../reports/NEURAL_EVAL.md) | Level B gate (UE splits, dense) | 생성 리포트 |
| [reports/GPU_BENCH.md](../reports/GPU_BENCH.md) | GPU vs CPU 인코더 벤치마크 (G1) | 생성 리포트 |
| [reports/LLM_RAG_COMPARE.md](../reports/LLM_RAG_COMPARE.md) | KTRF vs 범용 LLM+RAG (Ollama) | 생성 리포트 |

리포트 재생성: `python -m eval.run_eval` / `run_benchmarks` / `run_wild` / `run_neural_eval`.

## 마일스톤 현황 (스펙 §51)

| 단계 | 내용 | 상태 |
|---|---|---|
| M0 | 스키마·offset 계약·traceability | ✅ 완료 |
| M1 | 심볼릭 코어 (normalization, exact, boundary, FST, fuzzy, snapshot) | ✅ 완료 (Python; Rust 코어는 프로덕션 과제) |
| M2 | compiler·동기 API·오류 스키마·budget·tenant 격리 | ✅ 완료 (library-level, HTTP 계층 없음) |
| M3 | 비동기 API·correction·관측성·메모리 tier | ✅ 완료 |
| M4 | bi-encoder·cross-encoder·fusion·conformal calibration | ✅ 구현 완료 — 단, 대형화된 UE 평가(1,073질의)에서 dense gold-in-set ~90%로 §5.2 목표(95%) 미달 → G2 본 학습이 남은 격차 |
| M5 | benchmark·release gate 자동화 | ✅ 실질 완료 (4계층 평가 + CI hard gates); §53 GPU 열 포함 |
| M6 | Level C proposer(flag)·adaptation 루프 | ◐ adaptation 루프 완료; neural proposer는 학습 데이터 게이트 대기 |

## GPU 단계 현황 (docs/GPU_PLAN.md)

| Phase | 내용 | 상태 |
|---|---|---|
| G1 | GPU 추론 (onnxruntime CUDA EP) | ✅ 실측 완료 — 배치 인코딩 10.7× (RTX 3080, reports/GPU_BENCH.md) |
| G2 | Stage B/C 학습 파이프라인 (torch, KLUE-RoBERTa) | ✅ GPU 전 루프 검증 (train→ONNX→runtime); **본 학습은 라벨 ≥5k 게이트 대기** |
| G3 | 멀티테넌트 adapter GPU 상주 (§32.3) | ✅ residency manager 구현 (`ktrf/adapters.py`) |

## 핵심 실측 (요약)

- Conformance: 0 실패 (Level A 결정적 보장, release blocker 기준)
- 적대적 매트릭스: hard gate 위반 0 (9 base + 4 dense runs, 200–3000 entities × 3 seeds)
- 실 텍스트(5도메인 114,605문장 — 뉴스·국민청원·판례·위키; 실존 조직 170
  entity): silver gold-in-set **6,916/6,916**, RESOLVED precision 1.0
  (6,126 commits, coverage 88.6%), fake-glossary FP 0 (4.90M chars,
  symbolic/hash/e5 전 구성), tail 분포 커버리지 84.3% (1,969 tails)
- Level B gate (UE 약칭, 실 텍스트 1,073질의): symbolic 79.7% → hash dense
  89.5% → e5 dense 89.8% — 벤치마크 대형화(63→1,073질의)로 §5.2 목표(95%)
  **미달**이 드러남; G2 본 학습(라벨 게이트)이 남은 격차를 메우는 경로
- vs 범용 LLM+RAG (동일 샘플, reports/LLM_RAG_COMPARE.md): silver track에서
  qwen3:8b·gemma4:12b/26b·gpt-oss:20b·qwen3.5:27b recall 0.98–1.0로 근접하나
  grounding 92–98%(환각 존재), latency 116×–570× 열세. **hard track(UE 미등록
  약칭 300질의)**: KTRF 91.7% vs LLM 54.7–66.7% — 병목은 LLM 링크가 아니라
  문장 임베딩 RAG 검색(gold∈후보 ~63%)이며, 심볼릭 mention 탐지 + 조준된
  Pass-2가 격차의 원인
- **Downstream A/B** (reports/AB_GROUNDING.md, qwen3:8b, paired 300사례):
  LLM-only 76.7% → **KTRF context 93.3%** (gold oracle 100%),
  **Gold Benefit Recovery 71.4%** (known 슬라이스 87.0%).
  Helpful flip 67 / Harmful flip 17. 대조군 naive full-glossary는 **68.0%로
  LLM-only보다 낮음**(harmful flip 50) — 관련성 선별 없는 사전 덤프는
  오히려 해롭고, 이득의 출처가 "사전 제공"이 아니라 **KTRF의 선별**임을
  보여준다
- 테스트: 218 (traceability: 56/61 REQ 구현+매핑, 5 deferred 사유 명시)

## 무결성·평가 하드닝 (외부 코드 리뷰 반영)

외부 리뷰가 검증한 결함과 반영 상태. 완료 항목은 `tests/test_integrity_and_gate.py`가 고정한다.

**반영 완료 (2026-08-25):**

- snapshot identity가 **전체 내용**을 커버: glossary 전체 직렬화(설명·프로필·
  경계 정책 포함) + runtime policy + conformance 결과의 SHA-256, 128-bit id,
  conformance 확정 **후** 계산
- artifact loader가 저장 hash 전체 + `snapshot_id`↔manifest 등식을 재검증 —
  `glossary.yaml`/`policy.json`/`manifest.json` 변조는 로드 거부
- encoder/reranker id를 전체 파일(+tokenizer/config) digest로 계산
- conformance 기록 없는 snapshot의 registry activation 차단
- release gate false-pass 제거: golden 위반 1건 = fail, commit 0건 = precision
  N/A + fail(최소 commit 수 강제), Wilson CI 하한 게이트, 리포트 행별 판정을
  실제 조건식으로 계산
- calibration의 Platt 학습/quantile 산출 데이터 분리(split-conformal 전제);
  prediction set truncation 시 `coverage_valid=false` 명시
- runtime options 스키마 검증 (`max_prediction_set` 범위, 미지 옵션 거부,
  일관된 `INVALID_REQUEST` 오류)

**남은 백로그 (우선순위순):**

1. snapshot 중첩 구조의 깊은 불변화 (frozen dataclass / read-only mapping)
2. human-gold 평가셋: 문서 단위 exhaustive annotation, 2인 주석 + adjudication,
   slice당 n≥200 — silver 근사와 분리 보고
3. latency/memory hard gate (p95/p99, 문서 크기·entity 규모별 SLO), 동시성·
   hot-swap·rollback 부하 테스트
4. 평가 데이터/모델 버전 고정 (dataset revision·corpus SHA-256·모델 digest를
   리포트 manifest에 기록), cluster-aware CI (문서/entity 단위 bootstrap)
5. 원격 배포 시 manifest 서명, 1-byte tamper sweep의 hard-gate 편입

## LLM Grounding — Terminology Context Pack (`ktrf/context.py`)

LLM 앞단 통합 설계 리뷰 반영. **구현 완료 (2026-08-25):** ContextPack schema
v1 (RESOLVED/AMBIGUOUS/document-definition/unknown 4분리, coverage·omission
metadata), `ContextPolicy` (profile 4종·budget·clearance 검증),
entity dedup(`observed_as`), query-aware 결정적 선별(생성형 호출 없음),
hard token budget(고정 축소 순서, 상태 불변 보장), 안전 XML/JSON/text
renderer(제어문자 제거·CDATA 금지), 코드 고정 `TERMINOLOGY_POLICY`,
`prepare_llm_context()` 편의 API, `validate_llm_grounding()` 출력 검증기,
glossary `grounding:` 블록(short_definition·hints·injection_policy·
classification — entities_hash에 포함). 테스트 20종
(`tests/test_context_pack.py`: 분리 불변조건·budget·injection 문자열·
clearance 필터·validator).

**Context-pack 백로그:**

1. **Downstream A/B 평가** — 파일럿 완료 (`eval/run_ab_grounding.py`).

   **A/B가 찾아낸 설계 결함 — context 주입의 억제 비용:**
   초기 계약(pack을 항상 주입)에서 qwen3:8b는 76.7%→93.3%로 개선됐지만
   gemma4:12b는 **89.7%→49.0%로 급락**했다. harmful flip을
   `eval/analyze_flips.py`로 분해한 결과 원인은 하나로 수렴한다 —
   *질문 대상 용어를 담지 못한 pack을 주입하면 모델이 그것을 "그 용어에는
   의미가 없다"는 근거로 읽고, 이미 알던 답을 철회한다.* 미등록 약칭
   12건에서 gemma4는 무맥락 10/12 → 주입 시 1/12였다. 프롬프트 문구로는
   교정되지 않았다("모르는 용어는 네 지식으로 답하라"는 명시 문구 추가 시
   1/12, unknown_mentions 명시까지 더하면 0/12).

   → 라이브러리 계약으로 대응: `coverage.empty`,
   `coverage.query_grounded`, `PreparedContext.should_inject` —
   **pack이 질문 대상을 grounding하지 못하면 주입하지 않는다.**
   (호스트가 gold 없이 판단 가능한 규칙이며, PLAN_PI 의사코드의
   `if (pack.isEmpty) return`을 일반화한 것.) 두 모델 재측정 진행 중.

   나머지 harmful flip: 잘못된 RESOLVED 2건(dense/fuzzy 오연결 —
   계속 감시할 잔여 위험), 후보로만 존재 2건.

   남은 확장: 정식 규모 1,000+ 사례와 문서 단위 cluster bootstrap /
   McNemar, Track 2(문서 QA)·Track 3(요약), counterfactual 오류 주입
   (잘못된 RESOLVED, gold 후보 제거, irrelevant flood)
2. relation 확장(allowlist·depth 1·entity당 2개 상한), semantic relevance
   (기존 encoder 재사용), multi-turn context delta, 2단계 캐시
   (resolve cache + pack cache)
3. resolver 응답에 `resolution_quality` 블록 공식화 (integration layer의
   내부 구현 의존 제거), document-local 정의 원문 span 추출
4. 모델별 TokenCounter 주입 가이드, JSON Schema 파일 발행, prompt-injection
   A/B (raw vs escape vs pack+policy) 자동화

## 변형 해석·미등록 약어 (docs/VARIANTS_PLAN.md, M0–M6)

외부 기술 리뷰를 편입한 별도 로드맵. 핵심 판단은 **SLM 우선이 아니라
측정 신뢰성 복구가 먼저**라는 것이다. M0 평가 코드 결함 수정은 완료했고
(strict 채점, exact-core span, 전 occurrence, family macro, commit ledger,
검색 기반 대조군, raw artifact 보존, provenance manifest — commit
`8d6f427`), human-gold seed와 cluster bootstrap이 남아 있다. 상세와
SLM 진입 게이트는 [VARIANTS_PLAN.md](VARIANTS_PLAN.md) 참조.

주의: 이 수정으로 **기존 리포트 수치는 하향 조정된다**. 이전 값은
관대한 채점(양방향 부분문자열)·any-overlap span·silver-span 한정
precision에 기반했다.

## Pi Extension 통합 (PLAN_PI.md, 6단계)

KTRF를 Pi Coding Agent의 terminology grounding 레이어로 배포하는 계획.
원칙: **LLM은 제안자, KTRF 정책 엔진은 검증자, 영속 등록은 승인 정책이
결정** — LLM 추론만으로 영구 사전을 수정하지 않는다. 첫 구현은 Python
심볼릭 코어를 CPU-only stdio sidecar로 쓰고 TypeScript 재작성은 하지 않는다.

| 단계 | 내용 | 상태 |
|---|---|---|
| 1. KTRF 기반 정비 | snapshot digest·ContextPack·safe renderer / layered glossary compiler·Simple Terminology Schema·explain API·stdio runtime | ✅ **완료** (아래 상세) |
| 2. 수동 Pi Extension | Pi Package 스캐폴드, sidecar bridge, `/terms` 명령어, 계층 사전(global/project/session), project trust | 미착수 (별도 TS 패키지) |
| 3. 자동 context injection | lifecycle hook (`before_agent_start`/`tool_result`/`context`), dedup, adaptive budget | 미착수 |
| 4. LLM-assisted learning | `ktrf_propose_term`, proposal queue, `/terms review`, provisional term | 미착수 |
| 5. 제한적 자동 등록 | 명시적 정의 session 자동 등록, 반복 evidence 기반 project 승격, shadow compile + conformance gate | 미착수 |
| 6. 평가·배포 | Pi lifecycle E2E, scope/보안 테스트, A/B 평가, npm 배포 | 미착수 |

**1단계 구현 완료 (2026-08-26)** — KTRF 저장소 쪽 Pi 연동 기반:

- `ktrf/registry/simple_schema.py` — Simple Terminology Schema
  (`terms.yaml`) → glossary 컴파일. id·alias family·normalization profile
  (표면형에서 추론)·boundary policy·grounding·provenance 자동 생성,
  미지 키는 조용히 무시하지 않고 거부
- `ktrf/registry/layers.py` — 5계층(base→global→project→session→document)
  병합. 상위 scope가 이기되 하위 의미는 `shadows` provenance로 보존하고,
  `override: true` 없는 shadowing은 conflict로 보고. untrusted scope는
  로드 자체를 건너뜀(project trust 계약). `compile_layered_snapshot()`은
  manifest 추가 후 snapshot_id를 재계산해 무결성 등식 유지
- `ktrf/registry/proposals.py` — OBSERVED→PROPOSED→VALIDATED→
  PROVISIONAL/ACTIVE 상태 모델, `TermAdmissionPolicy`, 결정적 검증
  (evidence에 surface 실존, alias 충돌, 중복 entity, instructional·민감정보
  거부, 길이·제어문자), session 명시적 정의만 자동 활성화, project는 신뢰·
  증거·세션 수 전부 충족 시에만, **global 자동 등록은 정책상 불가**,
  provisional TTL, per-session 제출 상한, audit log
- `ktrf/explain.py` — `explain_resolution()` (채널·scope·후보·**미확정
  사유**: threshold 미달/margin 부족/degraded 구분), `lookup_surface()`
- `ktrf/integrations/pi_stdio.py` — JSONL JSON-RPC sidecar (13 method).
  stdout은 프로토콜 전용·로그는 stderr, malformed 라인 격리, 요청 크기
  상한, 모든 핸들러 오류를 error 응답으로 변환하는 fail-open 계약,
  프로토콜 스트림 UTF-8 강제(호스트 로케일 무관)
- ContextPack이 `source_scope`·`shadowed_entities`를 노출 — 모델이 어느
  scope의 의미인지, 무엇을 가리고 있는지 알 수 있음
- 테스트 36종(`tests/test_registry_and_sidecar.py`), 실제 서브프로세스
  왕복 테스트 포함 (총 254)

## 다음 단계 (우선순위)

1. **Level B 격차 해소**: 949질의 UE 평가에서 dense 91.8% < 목표 95% —
   bi-encoder fine-tune(G2 Stage C) 또는 후보 확장 정책이 필요. 라벨 축적
   (Correction API → ≥5k sense 라벨)이 선행 조건
2. G2 본 학습: cross-encoder(KLUE-RoBERTa) → NEURAL_EVAL 재실행으로 LexicalCrossEncoder 대비 개선 검증
3. M6: neural mention proposer (Level C, flag 유지)
4. 프로덕션화: Rust core (REQ-MEM-001 mmap artifact), HTTP 계층, §53 기준 하드웨어 SLO 문서
