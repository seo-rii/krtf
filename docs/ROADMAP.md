# KTRF Roadmap & Status

**기준일:** 2026-08-24 · **스펙:** PLAN.md v0.3 · 본 문서는 계획/현황 문서이며 규범이 아니다.

## 문서 지도

| 문서 | 내용 | 성격 |
|---|---|---|
| [PLAN.md](../PLAN.md) | KTRF 기술 스펙 v0.3 (규범) | spec |
| [MODEL_RECOMMEND.md](../MODEL_RECOMMEND.md) | 신경 모델 선정 근거 | 결정 기록 |
| [docs/GPU_PLAN.md](GPU_PLAN.md) | GPU 실행 계획 (G1–G3) | 계획 |
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
| M4 | bi-encoder·cross-encoder·fusion·conformal calibration | ✅ 구현 완료 — 단, 대형화된 UE 평가(949질의)에서 dense gold-in-set 91.8%로 §5.2 목표(95%) 미달 → G2 본 학습이 남은 격차 |
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
- 실 텍스트(KLUE 72,935문장, 실존 조직 132 entity): silver gold-in-set **4,711/4,711**,
  RESOLVED precision 1.0 (4,258 commits), fake-glossary FP 0 (2.19M chars,
  symbolic/hash/e5 전 구성), tail 분포 커버리지 82.3% (966 tails)
- Level B gate (UE 약칭, 실 텍스트 949질의): symbolic 80.0% → hash dense 91.8%
  → e5 dense 90.9% — 벤치마크 대형화(63→949질의)로 §5.2 목표(95%) **미달**이
  드러남; G2 본 학습(라벨 게이트)이 남은 격차를 메우는 경로
- vs 범용 LLM+RAG (동일 샘플, reports/LLM_RAG_COMPARE.md): KTRF recall 1.0 /
  fake-FP 0 / 18ms를 qwen3:8b·gemma4:12b·26b·qwen3.5:27b가 recall로는 근접
  (0.98–1.0)하나 grounding 92–98% (환각 존재), fake-FP까지 0인 모델도 latency
  116×–570× 열세
- 테스트: 182 (traceability: 56/61 REQ 구현+매핑, 5 deferred 사유 명시)

## 다음 단계 (우선순위)

1. **Level B 격차 해소**: 949질의 UE 평가에서 dense 91.8% < 목표 95% —
   bi-encoder fine-tune(G2 Stage C) 또는 후보 확장 정책이 필요. 라벨 축적
   (Correction API → ≥5k sense 라벨)이 선행 조건
2. G2 본 학습: cross-encoder(KLUE-RoBERTa) → NEURAL_EVAL 재실행으로 LexicalCrossEncoder 대비 개선 검증
3. M6: neural mention proposer (Level C, flag 유지)
4. 프로덕션화: Rust core (REQ-MEM-001 mmap artifact), HTTP 계층, §53 기준 하드웨어 SLO 문서
