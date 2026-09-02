# KTRF Roadmap & Status

**기준일:** 2026-08-30 · **스펙:** PLAN.md v0.3 · 본 문서는 계획/현황 문서이며 규범이 아니다.
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
| [reports/SEGMENTATION_AB.md](../reports/SEGMENTATION_AB.md) | 공유 segmentation 쌍 표본 A/B (M1) | 생성 리포트 |
| [reports/COMPOSITION_AUDIT.md](../reports/COMPOSITION_AUDIT.md) | core_link/full_surface 표면형 합성 감사 (M2) | 생성 리포트 |
| [reports/VARIANT_MINING.md](../reports/VARIANT_MINING.md) | 미등록 변형 채굴 백로그 (M4) | 생성 리포트 |

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
- Level B gate (UE 약칭, 실 텍스트 **1,116 occurrence**, exact-core span):
  symbolic **85.3%** → hash dense **87.2%** → e5 dense **86.8%**
  (family macro 89.2 / 91.9 / 91.4). §5.2 목표(95%) **미달**.
  세 구성이 M1 이전 대비 **일제히 +6.5%p** 올랐다 — 인코더를 바꾼 게 아니라
  공유 segmentation이 mention 탐지 단계를 고친 결과이고, 이 트랙은 M1의
  자체 A/B가 다루지 않던 표본이다. 채점 코드는 그 사이 바뀌지 않았다.
  dense 증분은 exact-core 기준 **+1.9%p**이며(any-overlap 기준 +3.8%p),
  그 대가로 prediction set이 약 8배 커진다(mean 1.08 → 8.31).
  이 트랙은 라벨된 commit이 0건이라 commit precision을 측정할 수 없다.
- 표면형 합성 (reports/COMPOSITION_AUDIT.md, 실문장 10,000 쌍 비교):
  mention의 **12.4%**(479/3,867)가 core보다 넓은 표면형을 갖는다 — `산업부장관`
  (사람), `우리카드`(다른 회사), `KBS노조`(다른 조직). M2 전에는 응답에 그
  구분이 없었다. 확정 수는 770 → 771로 사실상 그대로인데 commit 보류는
  27 → 763이다: 늘어난 차단은 이미 threshold 아래였던 후보이며, 그래서
  이 규칙은 **오늘 recall을 깎지 않으면서** 확정 여부가 확률 우연에 기대던
  것을 끝낸다
- vs 범용 LLM+RAG (동일 샘플, reports/LLM_RAG_COMPARE.md): silver track에서
  qwen3:8b·gemma4:12b/26b·gpt-oss:20b·qwen3.5:27b recall 0.98–1.0로 근접하나
  grounding 92–98%(환각 존재), latency 116×–570× 열세. **hard track(UE 미등록
  약칭 300질의)**: KTRF 91.7% vs LLM 54.7–66.7% — 병목은 LLM 링크가 아니라
  문장 임베딩 RAG 검색(gold∈후보 ~63%)이며, 심볼릭 mention 탐지 + 조준된
  Pass-2가 격차의 원인
- **Downstream A/B** (reports/AB_GROUNDING.md, 2모델 × paired 450사례,
  strict 채점): **효과가 슬라이스별로 정반대라 전체 평균은 무의미하다.**

  | 슬라이스 | qwen3:8b A→C | gemma4:12b A→C |
  |---|---|---|
  | private_glossary (사내 용어) | **0.00 → 1.00** (harmful 0) | **0.00 → 0.92** (harmful 0) |
  | known_abbrev (공개·등록) | 0.61 → 0.94 | 0.89 → 0.80 |
  | unseen_abbrev (공개·후보만) | 0.79 → 0.95 | 0.85 → **0.34** |

  ① 모델이 알 수 없는 **사내 용어에서 KTRF는 대체 불가능**하다 —
  0% → 92~100%, harmful flip 0. ② 모델이 이미 아는 공개 용어에서는 잘해야
  본전이고, KTRF가 **확정 못 하고 후보만 제시하면 지시 준수형 모델은
  기권**해 크게 손해다(gemma4 harmful 109건 중 106건이 `canonical: null`
  기권, 같은 사례 무맥락 정답률 100%). ③ 대조군 B(검색 덤프)가 known에서
  C보다 높은 것은 B가 "임의 확정 금지" 안전 계약을 지지 않기 때문이다
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

**추가 반영 (2026-08-30) — 리포트 신뢰성:**

M1 작업 중 드러난 세 가지는 resolver가 아니라 **평가 쪽 결함**이었다.

- 리포트가 코드와 조용히 어긋나 있었다. `BENCHMARKS.md`의 conformal
  coverage 0.9532는 **split-conformal 전제를 위반하던 코드**(Platt 학습과
  quantile을 같은 데이터로)가 생성한 값이며, 그 결함을 고친 뒤
  재생성되지 않았다. → 모든 리포트 footer에 측정 commit을 박는
  `provenance_line()` 추가
- 그 coverage 지표는 애초에 **게이트가 아니었다**: 단일 시드 n=171로,
  시드만 바꿔도 0.92~0.97로 움직인다. → 8회 시행 pooling(n=5,518) +
  Wilson CI + **3값 판정**(PASS / FAIL / `INSUFFICIENT_DATA`). 현재
  α=0.05에서 0.9458 [0.9395, 0.9515] → `INSUFFICIENT_DATA` — 목표가
  구간 안에 있으므로 통과로도 위반으로도 적지 않는다
- fake-glossary 부재 필터가 **대소문자 구분 부분문자열** 검사였다. matcher는
  case-fold하므로 corpus에 `GB`만 있어도 `gb`가 "부재"로 남아 실제로
  매칭된다 — 제품 오타가 아닌 **구성 오류가 FP로 집계**되던 것.
  → 정규화 공간에서 검사하도록 수정(`eval/synthetic.py::absent_bindings_only`)

**남은 백로그 (우선순위순):**

0. `WILD_CORPUS.md` 전체 재생성 (114,605문장 ×6 pass ≈ 6시간). 현재는
   20,000문장 표본 쌍 비교(`eval.run_wild_regression`)로 대체했고
   리포트 상단에 경고를 붙였다
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
측정 신뢰성 복구가 먼저**라는 것이다.

**M0 (측정 신뢰성)** — 평가 코드 결함 수정 완료(strict 채점, exact-core
span, 전 occurrence, family macro, commit ledger, 검색 기반 대조군, raw
artifact 보존, provenance manifest — commit `8d6f427`) + eval-only trace
(`return_eval_trace`). human-gold seed와 cluster bootstrap은 남아 있다.

주의: 이 수정으로 **기존 리포트 수치는 하향 조정된다**. 이전 값은
관대한 채점(양방향 부분문자열)·any-overlap span·silver-span 한정
precision에 기반했다.

**M1 (공유 segmentation)** — ✅ 완료. exact 채널만 조사를 분해하고 Level B
채널(jamo·keyboard·abbrev)은 원시 토큰을 인덱스에 넣던 구조를
`ktrf/segmentation.py` 하나로 통합했다. 두 가지가 동시에 고쳐졌다:

1. `한국전려에서도`처럼 **오타+조사** 결합은 mention 자체가 안 나왔다.
   `한국전려`는 되는데 조사가 붙으면 안 되는 것은 모델 용량이 아니라
   채널 간 분해 불일치였다.
2. fuzzy mention span이 분석된 적 없는 조사까지 덮었다 — exact 경로가
   지키는 offset 계약(INV-012) 위반이며, 하이라이트·치환 같은 하위
   소비자가 구분할 수 없는 종류의 결함이다.

`StructuralPath`(타입화된 분해) / `MatchEvidence`(후보의 출처) /
`ResolutionGuard`(§2 불변조건, **Level B 전용**)로 구성된다. guard는
후보를 제거하지 않고 commit만 보류하며, 설정은 snapshot ID에 반영된다.
수치는 [SEGMENTATION_AB.md](../reports/SEGMENTATION_AB.md).

**M2 (의미 안전성)** — ✅ 완료. M1까지 suffix 카탈로그는 평평한 집합이라
`부`·`본부`·`장`·`노조`가 전부 같은 종류였고, 응답은 core span과 원시 토큰
span만 내보냈다. 그래서 **`금감원장`(사람)과 `한국전력공사`(같은 기관)가
API 상 구분되지 않았고**, `full_span`을 하이라이트·치환하는 소비자는
불변조건 ②가 금지하는 overcommit을 그대로 했다.

M2는 suffix를 `NAME_PART`/`ORG_UNIT`/`ROLE`/`AFFILIATE`/`DERIVED_ORG`/
`REFERENTIAL`/`ARTIFACT`로 타입화하고, 응답에 `core_link`(core가 가리키는
것)와 `full_surface`(전체가 가리키는 것, 조사 제외)를 **분리해서** 실었다.
스키마에만 있고 resolve 시점에 아무도 읽지 않던 `COMPOSES_TO` 관계를
연결해 `한전`+`노조` → 전국전력노동조합처럼 **선언된 파생을 이름으로**
돌려준다(REQ-TAIL-002가 deferred에서 implemented로 이동). ContextPack과
XML/text 렌더러까지 이어져 LLM이 실제로 보는 경로에서도 파생이 사라지지
않는다. 수치는 [COMPOSITION_AUDIT.md](../reports/COMPOSITION_AUDIT.md).

작업 중 별도 결함도 드러났다: Pass-2 abbreviation alignment가 guard를 전혀
거치지 않고 후보를 추가하고 있었고, `CandidatePool`이 차단되지 않은 증거로
`commit_blocked`를 해제하기 때문에 **다른 채널의 차단을 조용히 되돌리고**
있었다. M1부터 있던 구멍이다.

**M4 (미등록 변형 채굴)** — ◐ 채굴기와 승인 브리지 완료. resolver가 이미
`full_surface`로 "가지지 못한 이름이 여기 있다"고 말하고 있으므로 새 분석이
아니라 **그 진술의 집계**다(`ktrf/mining.py`, 공개 응답 필드만 읽는다).

설계 전에 20,000문장을 세었고 census가 계획을 고쳤다: 자리 354개 중 263개가
1회성이고, 상위 자리는 `대한`+`민국`(147회)처럼 **이름이 아니었다**. 후보 층의
반복은 증거가 못 된다 — 흔한 것은 이름이 아니라 단어여서 우연히 겹친 접두가
진짜만큼 안정적으로 반복된다. 그래서 발견을 둘로 나눴다:

- **종결어 공백**(여러 entity 뒤에 반복) — 강한 증거. `교육청`이 12개 entity
  뒤에 있었고 카탈로그에 없다. M3까지 손으로 하던 taxonomy가 측정값이 된다.
- **이름 공백**(한 entity 뒤에서만 반복) — 약한 증거라 **exact 채널이 찾은
  core 뒤에서만** 채굴한다. 20,000문장에서 4건이고 전부 진짜 이름이다.

승인은 PLAN_PI의 상태 모델을 그대로 쓴다. `origin`이 `deterministic_detector`라
**어느 scope에서도 자동 활성화되지 않고**, `canonical`은 기본값 없는 인자라
채굴기가 지어낼 수 없다. 등록은 `COMPOSES_TO`까지 함께 하므로 불변조건 ③이
그 표면형에 이름을 주고, 다음 채굴에서 백로그가 **줄어드는 것**이 루프가
닫혔다는 증거다. 수치는 [VARIANT_MINING.md](../reports/VARIANT_MINING.md).

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
