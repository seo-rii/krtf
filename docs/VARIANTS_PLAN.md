# 변형 해석·미등록 약어 로드맵

**기준일:** 2026-08-30 · 본 문서는 계획 문서이며 규범(spec)이 아니다.
근거 수치의 단일 출처는 `reports/`의 생성 리포트다.

외부 기술 리뷰(변형 커버리지·미등록 약어·SLM 도입 조건)를 실행 계획으로
편입한 문서다. 결론부터: **SLM 우선이 아니라 측정 신뢰성 → 공통 분해 →
의미 안전성 → 커버리지 → mining → (그래도 남으면) SLM** 순서다.

## 0. 유지할 것과 바꿀 것

유지: exact·정규화·경계·보수적 commit의 Level A 결정적 계약, CPU-only
배포, offset provenance, 불변 snapshot, 보수적 ContextPack.

바꿀 것: fuzzy와 abbreviation이 exact 경로와 **다른 입력 해석**을 쓰는
구조. 지금 `한국전려`는 fuzzy 후보가 되지만 `한국전려에서도`는 조사까지
붙은 문자열이 fuzzy index에 들어가 실패하기 쉽다. 모델 용량 문제가 아니라
채널 간 분해 불일치 문제다.

## 1. 현재 수치가 말하지 않는 것

| 관측 | 값 | 말할 수 있는 것 | 말할 수 없는 것 |
|---|---:|---|---|
| composed transform | 1,350/1,350 | 정의된 변형·조합 구현이 안정적 | 현실 변형 분포를 설명한다 |
| wild tail coverage | 84.3% | 실문장 tail의 16%가 카탈로그로 설명 안 됨 | 나머지를 suffix로 추가하면 된다 |
| fuzzy recovery | 96.3% | 고립된 near-miss 복구가 강함 | ~~fuzzy+조사·prefix 조합도 강하다~~ → M1에서 측정함: 조합 시 **0.10**이었고, 수정 후 0.69 |
| UE holdout | ~90% | **binding holdout**에서 복구된다 | 신규 formation 일반화가 검증됐다 |
| A/B known | 큰 개선 | 등록 약칭 ContextPack은 유익 | unseen에도 같은 효용이 있다 |
| A/B unseen | 순효과 작음 | 추가 검증 필요 | unseen 개선이 입증됐다 |

특히 UE·A/B의 `unseen`은 **같은 유명 약칭 21종의 binding만 숨긴 것**이다.
alias family·formation·entity가 모두 새로운 경우는 측정하지 않는다.

## 2. 의미 계약 — 변형을 하나의 recall 문제로 합치지 않는다

| 분류 | 예 | core 후보 | 전체를 core와 동일시 |
|---|---|---:|---:|
| 동등 표면형 | `ＡＰ`, `한 전` | 가능 | 가능 |
| 굴절 | `한전에서도` | 가능 | 가능 |
| 제한된 오타 | `한국전려에서도` | 가능 | 조건부 |
| 약어 | `과기정통부` | 가능 | 증거에 따라 |
| base modifier | `전 한전` | 가능 | 조건부 |
| **관련 파생** | `한전노조`, `금감원장` | 가능 | **불가** |
| 의미적 재표현 | `금융당국`→금감원 | 불확실 | 불가 |

추가 불변조건: ① core retention ② **parent full-span overcommit 금지**
③ 등록 relation 우선 ④ candidate/commit 분리 ⑤ 감사 가능한 provenance
⑥ variant profile·confusion table·signature 변경 시 snapshot ID 변경.

## 3. 마일스톤

| 단계 | 내용 | 상태 |
|---|---|---|
| **M0** | 측정 신뢰성 복구 | ◐ 코드 수정 완료, human-gold seed 미착수 |
| M1 | 공유 segmentation + typed path (`StructuralPath`/`MatchEvidence`/`ResolutionGuard`) | ✅ 완료 |
| M2 | 의미 안전성: `core_link`/`full_surface` 분리, typed tail, `COMPOSES_TO` 후보 연결 | 미착수 |
| M3 | 현실 커버리지: wild tail 수동 taxonomy, punctuation class, OCR opt-in, confusion table, abbreviation signature index | 미착수 |
| M4 | 미등록 variant mining + 승인 루프 | 미착수 (PLAN_PI proposal 상태 모델 재사용) |
| M5 | 약어 SLM shadow 실험 | 게이트 대기 |
| M6 | 제한적 새 entity proposal | 미착수 |

### M0 진행 상황 (2026-08-26)

**완료 — 평가 코드 결함 수정** (commit `8d6f427`):

- A/B 채점이 양방향 부분문자열이라 `현대`가 현대자동차의 정답으로
  처리되던 문제 → strict 채점(정답이 출력에 포함돼야 함) + 사유 기록
- A/B 대조군 B가 entity ID 순 prefix(strawman) → **검색 기반 baseline**
  (dense top-k ∪ literal alias hit, 동일 token budget)
- A/B raw output·context payload·token 수 전량 보존 → 채점 변경 시
  재호출 불필요, harmful flip 감사 가능
- UE 평가가 문장당 첫 alias에서 멈추던 문제 → **모든 occurrence**
  (1,073문장 → 1,116 case)
- UE hit 판정이 any-overlap → **exact-core span 일치**, overlap은 진단용
- UE **family macro** 병기 (occurrence가 family당 5~185로 편중 → micro는
  빈출 약칭이 지배), worst-family 노출
- UE·wild **commit ledger**: gold/silver span 밖 확정도 분모에 집계.
  "silver span 위 commit만 센 precision 1.0"을 시스템 precision으로
  인용하지 않도록 리포트에 명시
- Recall@1/5/10/20/50, prediction-set mean/p95
- McNemar exact p(보조 지표, 군집 미반영 명시), GBR은 oracle gap < 5pp면 N/A
- provenance manifest: git commit, corpus/glossary/prompt/policy 해시, seed

**남음:**

1. human-gold seed set (variant taxonomy 라벨 포함), locked test 봉인
2. alias-family/document cluster bootstrap을 primary 통계로 (현재 Wilson은
   독립 표본 가정)
3. ~~resolver eval-only trace: pre-threshold rank·후보 수·truncation 노출~~
   → 완료 (M1과 함께, `return_eval_trace` 옵션)
4. `INSUFFICIENT_DATA` 표기 규칙 — ◐ 부분 완료. calibration coverage에는
   적용했다(CI 하한≥목표면 PASS, 상한<목표면 FAIL, 사이는
   `INSUFFICIENT_DATA`). formation slice당 최소 200 mention 규칙을 나머지
   리포트에 퍼뜨리는 것은 미완

### M1 공유 segmentation (2026-08-30) — 완료

**문제의 실체.** 변경 전 exact 채널만 `CanonicalStream` → boundary
→ tail parser로 조사·suffix를 분해했고, Level B 채널(jamo·keyboard·
abbrev)은 **원시 토큰 전체**를 인덱스에 넣었다. abbrev에만
별도의 조사 절단 루프가 있었으나 다른 채널은 쓰지 않았다. 결과:

| 입력 | 변경 전 | 변경 후 |
|---|---|---|
| `한국전려` | AMBIGUOUS (ORG_KEPCO 후보) | 동일 |
| `한국전려에서도` | **mention 없음** | AMBIGUOUS, core span (0,4) |
| `국토교퉁부가` (오타) | span이 조사 `가`까지 포함 | core에서 멈춤 |

두 번째는 recall 문제가 아니라 **offset 계약 위반**이다. exact
경로는 core span이 조사를 포함하지 않는다고 보장하는데 fuzzy 경로는
그렇지 않았고, 하위 소비자(하이라이트·치환·ContextPack)는 그 차이를
구분할 수 없었다.

**구현.** `ktrf/segmentation.py` 하나로 통합했다.

- `segment_token(token, span, fst)` → `StructuralPath` 목록.
  BARE·PARTICLE·SUFFIX·SUFFIX_PARTICLE·UNKNOWN_TAIL·LATIN_TAIL로
  **타입화**되며, 하나로 가지치기 하지 않고 전부 돌려준다
  (REQ-TAIL-003). bare 읽기는 항상 최상위이므로 `paths[0]`만 보는
  호출자는 기존 동작을 그대로 유지한다.
- `core_span`은 토큰 상대가 아니라 **문서 절대 좌표**라, Level B
  채널이 exact 경로와 동일한 span 규율을 갖는다 (INV-012).
- `tailparser.analyze_tail`은 `enumerate_tails`의 alias가 되었다 —
  exact 경로와 Level B가 **같은 구현**을 공유한다(복사본 없음).
- `MatchEvidence`: 후보가 어떤 채널·어떤 분해에서 나왔는지를 타입으로
  기록. provenance·explain·eval trace가 같은 레코드를 읽는다.
- `ResolutionGuard`: §2 불변조건을 Level B 증거에만 적용. **Level A는
  거치지 않는다** — 결정적 카탈로그 보장이 Level B 튜닝에
  의존하면 안 되기 때문이다. 후보를 **제거하지 않고** commit만
  보류한다(불변조건 ④ 후보/확정 분리).

| 규칙 | 효과 | 근거 |
|---|---|---|
| `short_core` | commit 차단 | 식별력 없는 core (불변조건 ①) |
| `unknown_residual_derivative` | commit 차단 + 0.60 | `한전노조`류 관련 파생 (②) |
| `ungrammatical_particle` | 0.80 | 받침 제약 위반은 soft 신호 (§16.2) |
| `inferred_tail` | 0.92 | 관측한 tail이 아니라 추론한 tail |

- guard 설정은 `segmentation_guard_hash`로 manifest에 들어가 **snapshot ID를
  바꿔 다른 아티팩트가 된다** (불변조건 ⑥).
- `RuntimePolicy.max_segmentation_paths` — 토큰당 분해 예산. **1이면 M1
  이전 동작**과 정확히 같으므로 A/B 대조군이 된다.
- `resolve(..., options={"return_eval_trace": True})` — threshold 이전
  순위·후보 수·truncation 노출 (M0 잔여 항목 3). 진단 전용이며
  어떤 결정에도 입력되지 않는다.

**측정.** `python -m eval.run_segmentation_ab` — 동일 표본을 `paths=1`(변경
전)과 `paths=4`로 두 번 돌려 쌍으로 비교한다. formation당 400건,
실문장 6,000개.

| formation | core recall | 정확 span | RESOLVED |
|---|---|---|---|
| `particle` | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 |
| `suffix_particle` | 1.00 → 1.00 | 1.00 → 1.00 | 0.03 → 0.03 |
| `typo` | 0.68 → 0.69 | 0.66 → 0.66 | 0.00 → 0.00 |
| **`typo_particle`** | **0.10 → 0.69** | **0.00 → 0.63** | 0.00 → 0.00 |

구조적 FP(fake glossary) 0 → 0, 지연 p95 1.36배. `particle` 계열이
양쪽 1.00인 것은 **Level A를 건드리지 않았다는 증거**고, RESOLVED가
양쪽 0.00인 것은 **확정 기준을 느슨하게 하지 않았다는 증거**다.
전체는 [reports/SEGMENTATION_AB.md](../reports/SEGMENTATION_AB.md).

실텍스트 회귀는 `python -m eval.run_wild_regression`(20,000문장 표본 쌍
비교). `WILD_CORPUS.md` 전체 재생성은 6시간이라 별도 과제로 남겨둔다.

**남은 것(M1 범위 밖).** typed tail 문법과 `COMPOSES_TO` 후보 연결,
`core_link`/`full_surface` 분리는 M2이다. 현재는 UNKNOWN residual을
commit 차단으로만 다루며, `한전노조` 같은 파생을 별도 관계로
모델링하지는 않는다.

## 4. SLM 진입 조건 (요약)

SLM은 resolver 대체재가 아니라 **candidate-only proposer**다. 본 학습 전
세 게이트를 모두 충족해야 한다.

- **Gate A 평가 준비**: locked human-gold, distinct abbreviation family
  ≥200, slice당 ≥200 mention, 2인 주석 κ≥0.75, 5-way 분할(train/dev/
  prob-calib/conformal-calib/locked test)
- **Gate B 비모델 한계 확인**: rule+typed variant+mining 후에도
  unseen-family macro가 목표 미달이고, 잔여 miss의 30% 이상이 glossary에
  entity가 있는 **systematic formation**
- **Gate C 데이터**: accepted contextual positive ≥5,000, distinct
  abbreviation–entity pair ≥1,000, formation별 ≥100, 합성 데이터 ≤25%

비교 기준은 SLM-only가 아니라 **최선의 비모델 hybrid 대비 증분**이며,
승격에는 cluster bootstrap CI 하한 > 0, priority slice non-inferiority,
FP/1k chars 비열화, latency p95 +10% 이내, Level A conformance 0 실패가
모두 필요하다.

## 5. 하지 않을 것

- wild tail 목록을 검토 없이 전역 `SUFFIXES`에 추가
- 모든 transform의 자유 조합 허용
- 관련 파생 표현(`한전노조`)을 parent entity로 full-span 확정
- 범용 dense retrieval 결과를 약어 SLM 검증으로 간주
- 단일 occurrence나 LLM 상식만으로 entity/alias 영구 등록
- prediction set 50의 any-overlap micro recall을 모델 선택 주 지표로 사용
- silver-span 내부 commit만 센 precision을 시스템 precision으로 홍보
