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

리포트 재생성: `python -m eval.run_eval` / `run_benchmarks` / `run_wild` / `run_neural_eval`.

## 마일스톤 현황 (스펙 §51)

| 단계 | 내용 | 상태 |
|---|---|---|
| M0 | 스키마·offset 계약·traceability | ✅ 완료 |
| M1 | 심볼릭 코어 (normalization, exact, boundary, FST, fuzzy, snapshot) | ✅ 완료 (Python; Rust 코어는 프로덕션 과제) |
| M2 | compiler·동기 API·오류 스키마·budget·tenant 격리 | ✅ 완료 (library-level, HTTP 계층 없음) |
| M3 | 비동기 API·correction·관측성·메모리 tier | ✅ 완료 |
| M4 | bi-encoder·cross-encoder·fusion·conformal calibration | ✅ 완료 — Level B gate 통과 (하단) |
| M5 | benchmark·release gate 자동화 | ✅ 실질 완료 (4계층 평가 + CI hard gates); §53 GPU 열 포함 |
| M6 | Level C proposer(flag)·adaptation 루프 | ◐ adaptation 루프 완료; neural proposer는 학습 데이터 게이트 대기 |

## GPU 단계 현황 (docs/GPU_PLAN.md)

| Phase | 내용 | 상태 |
|---|---|---|
| G1 | GPU 추론 (onnxruntime CUDA EP, device 훅) | 진행 — 훅 구현 완료, 런타임 검증/벤치는 본 회차 |
| G2 | Stage B/C 학습 파이프라인 (torch, KLUE-RoBERTa/e5) | 진행 — 스캐폴드 + GPU 스모크 검증; 본 학습은 라벨 ≥5k 게이트 대기 |
| G3 | 멀티테넌트 adapter GPU 상주 (§32.3) | 진행 — residency manager 구현 |

## 핵심 실측 (요약)

- Conformance: 0 실패 (Level A 결정적 보장, release blocker 기준)
- 적대적 매트릭스: hard gate 위반 0 (9 runs, 200–3000 entities × 3 seeds)
- 실 텍스트(KLUE): silver recall 168/168, fake-glossary FP 0, tail 분포 커버리지 78%
- Level B gate (UE 약칭 63질의): symbolic 81.0% → hash dense 96.8% → **e5 dense 98.4%** (§5.2 목표 95% 상회)
- 테스트: 172 (traceability: 56/61 REQ 구현+매핑, 5 deferred 사유 명시)

## 다음 단계 (우선순위)

1. **라벨 축적**: Correction API 운영 → Stage B 학습 게이트(≥5k sense 라벨) 충족이 유일한 실질 병목
2. G2 본 학습: cross-encoder(KLUE-RoBERTa) → NEURAL_EVAL 재실행으로 LexicalCrossEncoder 대비 개선 검증
3. M6: neural mention proposer (Level C, flag 유지)
4. 프로덕션화: Rust core (REQ-MEM-001 mmap artifact), HTTP 계층, §53 기준 하드웨어 SLO 문서
