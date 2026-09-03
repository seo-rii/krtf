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
| wild tail coverage | 84.3% | 실문장 tail의 16%가 카탈로그로 설명 안 됨 | 나머지를 suffix로 추가하면 된다 → M3에서 실행함: 실측 목록을 분류해 **91.1%**. 남은 9%는 대부분 병렬 기관명(`연합뉴스교도통신`)과 잘못된 core 분해(`금융위기`)이지 미분류 suffix가 아니다 |
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
| **M0** | 측정 신뢰성 복구 | ◐ 코드 수정 완료, human-gold **seed 완료**(160행, 1인 주석) |
| M1 | 공유 segmentation + typed path (`StructuralPath`/`MatchEvidence`/`ResolutionGuard`) | ✅ 완료 |
| M2 | 의미 안전성: `core_link`/`full_surface` 분리, typed tail, `COMPOSES_TO` 후보 연결 | ✅ 완료 |
| M3 | 현실 커버리지: wild tail 수동 taxonomy, punctuation class, OCR opt-in, confusion table, abbreviation signature index | ✅ 완료 |
| M4 | 미등록 variant mining + 승인 루프 | ◐ 채굴기·승인 브리지 완료 (`ktrf/mining.py`), 종결어 class 결정은 사람 몫 |
| M5 | 약어 SLM shadow 실험 | 게이트 대기 |
| M6 | 제한적 새 entity proposal | ◐ 문서 내 정의 → 제안 완료 (`extract_new_terms`), 승인·등록 왕복은 남음 |

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
`core_link`/`full_surface` 분리는 M2이며, 아래에서 다룬다.

### M2 의미 안전성 (2026-08-31) — 완료

**문제의 실체.** M1까지 suffix 카탈로그는 **평평한 집합**이었다. `부`,
`본부`, `장`, `노조`가 전부 같은 `SUFFIX` 한 종류였고, 응답은 core span
(`span`)과 원시 토큰 span(`full_span`)만 내보냈다. 그래서 다음 세 문장이
API 상으로 구분되지 않았다.

| 표면형 | 전체가 가리키는 것 | M1 응답 |
|---|---|---|
| `기획재정부` | 같은 기관 | core + full_span |
| `금감원장` | **사람** | core + full_span |
| `한전노조` | **다른 조직** | core + full_span |

> `한국전력공사`처럼 다음절 어미(`공사`·`공단`)로 끝나는 정식 명칭은 아직
> 이 표의 첫 줄에 해당하지 않는다. NAME_PART이 전부 1음절이라 `공사`는
> 카탈로그 밖이고, 따라서 `한국전력` + `공사`는 SAME이 아니라 UNKNOWN으로
> 판정된다 — commit은 막히므로 안전한 방향이지만 관계 라벨은 틀린다.
> 카탈로그 확장은 M3.

`full_span`을 하이라이트하거나 치환하는 소비자는 `금감원장`을 통째로
금융감독원으로 만든다. 이것이 불변조건 ②(parent full-span overcommit
금지)가 금지하는 바로 그 동작인데, M1까지는 **응답에 그것을 말할 자리가
없었다**.

**구현.**

- `SUFFIX_CLASSES` — suffix를 `NAME_PART` / `ORG_UNIT` / `ROLE` /
  `AFFILIATE` / `DERIVED_ORG` / `REFERENTIAL` / `ARTIFACT`로 **타입화**했다.
  `ResidualAnalysis`가 `full_identity`(SAME / DISTINCT / UNKNOWN)와
  `relation`(IDENTITY / PART_OF / ROLE_OF / DERIVED_FROM / AFFILIATE_OF /
  REFERS_TO / ARTIFACT_OF / NAMED_VARIANT)을 계산한다. 판정은 **맨 오른쪽
  DISTINCT part**가 지배한다 — 한 part라도 "core가 아니다"라고 하면 뒤따르는
  part가 그것을 되돌리지 못한다(`본부장`은 본부가 아니라 사람이다). 수식어가
  앞에 붙으면(`서울본부`) head가 `NAME_PART`여도 전체는 DISTINCT다.
- `core_link` / `full_surface` — 응답이 두 개를 **분리해서** 내보낸다.
  `full_surface.span`은 `full_span`과 다르다: 조사는 이름의 일부가 아니므로
  제외한다(`한전노조가` → core (0,2), surface (0,4), token (0,5)).
  core가 곧 전체일 때는 두 키가 **아예 없다** — 구분할 것이 없기 때문이다.
  표면형이 넓어진 이유가 §16.6 prefix 수식어뿐일 때는(`전 한전`) `prefix_kind`
  를 실어 **무엇이 넓혔는지**를 말한다. §2 표가 base modifier를 "조건부"로
  두므로, 그냥 동일하다고 단정하지 않는다. 시간 범위 자체를 모델링하는 것은
  여전히 범위 밖이다.
- `COMPOSES_TO` — `EntityRelation`은 스키마에 있었지만 **resolve 시점에
  아무도 읽지 않았다**(REQ-TAIL-002가 deferred였던 이유). 이제
  `(source_entity, surface_suffix)` 인덱스를 스냅샷이 들고 있고, 선언된
  관계가 있으면 전체 표면형의 답을 **선언에서** 가져온다. 부모 entity는
  어느 쪽이든 전체 span을 갖지 않는다.
- guard 규칙 `unknown_residual_derivative` → `derivative_full_surface`.
  이제 UNKNOWN residual만이 아니라 **타입이 밝혀진 파생**(`typed_derivative`)
  도 Level B commit을 보류한다. `노조`를 카탈로그에 넣는 것이 오히려 규칙을
  느슨하게 만들 뻔했고, 판정 기준을 `residual_kind`에서 `full_identity`로
  옮겨서 막았다.
- ContextPack과 렌더러 — 카드는 occurrence를 `observed_as`로 합치므로
  파생이 사라지던 자리다. `appears_inside`(+`same_entity="false"`)를
  붙여 XML·text 렌더까지 살아남게 했다. LLM이 실제로 보는 경로가 여기다.
- suffix **분류**가 `morphology_rules_hash`에 들어간다. 표면형만이 아니라
  class를 해싱하므로, `노조`를 재분류하면 snapshot ID가 바뀐다(불변조건 ⑥).

**같이 고친 결함.** Pass-2 abbreviation alignment가 guard를 **전혀 거치지
않고** 후보를 추가하고 있었다. `CandidatePool`은 같은 entity에 대해
차단되지 않은 증거가 하나라도 오면 `commit_blocked`를 해제하므로(Level A
에게는 옳은 규칙), 이 채널이 다른 채널의 차단을 조용히 되돌렸다. M1에서도
있던 구멍이며 M2에서 두 번째 사례가 생기면서 드러났다.

**측정.** `python -m eval.run_composition_audit` — 실문장 표본에서 core보다
넓은 표면형의 빈도·종류·차단 사유를 센다. 대조군은 M2 이전 체크아웃(`f121ecf`)
에서 **같은 스크립트**를 돌린 것이다(같은 seed·같은 10,000문장 표본).

| 지표 | M1 | M2 |
|---|---:|---:|
| mention | 3,867 | 3,867 |
| RESOLVED 확정 | 770 | 771 |
| core보다 넓은 표면형 | 0 (표현 불가) | **479** (12.4%) |
| commit 보류된 후보 슬롯 | 27 | 763 |

읽는 법: **탐지도 확정도 움직이지 않았는데 차단만 27 → 763이 됐다.** 늘어난
차단이 확정을 깎지 않았다는 것은 그 후보들이 이미 threshold 아래였다는
뜻이고, 그래서 의미가 있다 — `금감원장`류가 지금까지 확정되지 않은 것은
*확률이 낮아서*였지 규칙 때문이 아니었다. 이제는 calibration이 어떻게
움직여도 막힌다. 실문장 mention의 **12.4%**가 core보다 넓은 표면형을 갖는데,
M1은 그 사실을 응답에 담을 자리가 없었다.

전체는 [reports/COMPOSITION_AUDIT.md](../reports/COMPOSITION_AUDIT.md).

**실텍스트 회귀.** `run_wild`의 silver·fake-glossary 스위트를 두 체크아웃에서
같은 표본(10,000문장)으로 돌린 결과다.

| 지표 | M1 | M2 |
|---|---:|---:|
| silver mention / 탐지 / gold-in-set | 609 / 1.0 / 1.0 | 609 / 1.0 / 1.0 |
| RESOLVED 확정 | 538 | **540** |
| commit precision | 1.0 | 1.0 |
| silver 커버리지 | 0.8834 | **0.8867** |
| ledger silver 밖 확정 | 204 | 204 |
| tail 커버리지 | 0.8400 | **0.8514** |
| fake-glossary FP | 0 | 0 |
| 후보 밀도 /1k chars | 5.114 | 5.114 |
| 지연 p50 / p95 (ms) | 34.57 / 260.8 | 34.94 / 259.6 |

M1은 재현율을 얻는 대신 p95를 1.36배 치렀다. **M2는 측정 가능한 비용이
없다**: 후보 밀도와 지연이 그대로고, 확정이 2건 늘었는데 그 2건이 전부
silver span 위에 떨어졌다(silver 밖 확정은 204로 동일). tail 커버리지
+1.1%p는 `노조`·`노동조합`을 카탈로그에 넣은 직접 효과다.

**감사가 잡아낸 결함.** 첫 실행의 예시에 `KEB하나은행장과`가
`SAME_AS_CORE`로 찍혔다. `장과`가 `장`+`과`로 쪼개지고 head-final 규칙이 맨
오른쪽 `과`(NAME_PART)를 head로 잡았기 때문인데, 중간의 `장`이 이미 사람으로
만든 뒤다. 판정과 관계 라벨 모두를 **"가장 오른쪽 DISTINCT part가
이긴다"**로 고쳤다. 합성 케이스로는 나오지 않았을 종류이며, 실문장 감사를
붙인 값이 여기 있다.

이 수정은 카탈로그가 아니라 **규칙 코드**를 바꾼 것이라 `SUFFIX_CLASSES`
해시로는 잡히지 않는다. `NORMALIZER_VERSION`과 같은 방식으로
`TAIL_GRAMMAR_VERSION`을 만들어 `morphology_rules_hash`에 넣었다.

**남은 것(M2 범위 밖).** suffix 카탈로그 확장 자체는 M3이다. 지금 카탈로그는
기존 항목을 **재분류**했고 `노조`/`노동조합`만 추가했다 — wild tail 16%를
채우는 것은 수동 taxonomy 작업이며 §5("검토 없이 전역 SUFFIXES에 추가")를
따른다. 미등록 파생을 `COMPOSES_TO` 후보로 **자동 제안**하는 것은 M4다.

#### M2 검토 후속 (2026-08-31)

M2를 실텍스트에 돌려 **라벨을 채점**하면서 나온 수정이다. 세는 것과 채점하는
것은 다른 작업이고, 위의 감사는 세기만 했다.

- **dense 채널이 guard를 거치지 않았다.** Pass-2 abbrev의 구멍은 M2에서
  고쳤지만 같은 블록의 dense는 남아 있었다. dense는 Level B이고 같은 pool로
  합쳐지므로, 차단되지 않은 dense 후보가 tail이 이미 거부한 entity의 차단을
  **푼다**. 같은 입력에서 dense를 끄면 `typed_derivative`, 켜면 `None`이었다.
  `_guard_for`가 `node.path`만 읽던 것도 함께 고쳤다 — exact 채널이 연 노드는
  tail을 proposal에 기록하므로, core를 어느 채널이 찾았는지에 따라 guard가
  적용되거나 안 되는 상태였다.
- **`relation`이 `tail_class`와 모순됐다.** `governing_class`가 `identity`의
  모순은 없앴지만 `relation`의 `SUFFIX_WITH_MODIFIER` 단축 경로가 그것을
  우회해, `한국투자증권`이 `tail_class=AFFILIATE`와 `relation=NAMED_VARIANT`를
  함께 실었다. 실텍스트 기록의 8.2%. modifier는 *이름*이 다르다고 말할 뿐이고
  뒤의 접미사가 여전히 관계를 말한다.
- **`TAIL_CLASSES`가 해시에 없었다.** class→(판정, 관계) 표를 고치면 표면형은
  하나도 안 건드리고 모든 판정이 바뀌는데, 그것이 손으로 올리는 버전 문자열에
  의존했다. **규칙(`governing_class`)은 버전으로, 데이터(표)는 해시로** 나눴다.

**측정.** 6,000문장 동일 표본(seed 20260830), `run_wild`의 silver·fake-glossary
스위트를 두 체크아웃 × 두 구성으로:

| | 수정 전 Level A | 수정 전 dense | 수정 후 Level A | 수정 후 dense |
|---|---:|---:|---:|---:|
| RESOLVED 확정 | 331 | **330** | 331 | **331** |
| commit precision | 1.0 | 1.0 | 1.0 | 1.0 |
| ledger silver 밖 | 117 | 117 | 117 | 117 |
| fake-glossary FP | 0 | 0 | 0 | 0 |
| 후보 밀도 /1k chars | 5.132 | 5.132 | 5.132 | 5.132 |

수정 전에는 dense를 켜면 확정이 하나 **줄었다**. guard를 안 거친 dense 후보가
차단도 감점도 없이 예측집합에서 경쟁해 정답을 AMBIGUOUS로 밀어낸 것이다.
guard를 붙이자 그 후보들이 감점·차단되면서 확정이 Level A와 같아졌다. 1건은
n=6,000에서 노이즈 범위이므로 **재현율이 올랐다고 읽지 않는다** — 읽을 것은
비용이 0이라는 것과, 불변조건 ②가 이제 dense 구성에서도 코드로 성립한다는
것이다. NEURAL_EVAL의 Level B recall(0.853 / 0.8719 / 0.8683)은 불변이다.

### 평가 축 전환 (2026-09-01)

**문제의 실체.** M0~M2의 리포트는 전부 **occurrence를 센다**. 그러면 자주
나오는 용어가 숫자를 정한다. 그런데 KTRF가 답해야 하는 질문은 그것이 아니다
— *등록한 용어 하나를 주었을 때, 실제 텍스트가 그것을 변형시켜도 회수하는가*.
그것은 occurrence당 한 번이 아니라 **용어당 한 번** 묻는 질문이다.

바꾼 것은 지표의 값이 아니라 **세는 단위**다.

| | 이전 | 이후 |
|---|---|---|
| 단위 | mention | **variant family**(등록 entity + 그 표면형 전부) |
| 집계 | micro | **macro** — 천 번 언급되는 부처와 한 번 언급되는 용어가 동일 무게 |
| 음성 집합 | fake glossary(없는 entity) | **confusion glossary**(있는데 1 중성 거리) |
| 정답 출처 | 구현이 읽는 카탈로그 | §2 계약 + **사람이 실문장에 단 라벨** |
| 한 숫자에 섞인 것 | 찾았나 + 확정했나 | **candidate / commit 분리** |

**새 스위트 둘.**

`eval/run_variant_recall.py` — glossary의 각 entity에 대해 표면형을
formation 하나씩 변형해 **실문장 안에** 넣고 회수 여부를 본다. formation은
§2 표의 행에 대응하고, 각 행이 "전체 표면형을 core entity로 확정해도 되는가"를
`SAME`/`CONDITIONAL`/`FORBIDDEN`으로 들고 있다. **이 열은 계획 문서에서 왔지
guard 규칙에서 오지 않았다** — guard에서 가져오면 정의상 통과하는 시험이 된다.
같은 이유로 FORBIDDEN formation이 쓰는 어미는 eval이 소유하며, 실측 tail
census에서 뽑았지 `SUFFIX_CLASSES`에서 뽑지 않았다.

`eval/run_variant_gold.py` — `eval/data/variant_gold.jsonl`의 **사람이 라벨한
160행**에 대고 채점한다. 다른 실텍스트 리포트는 전부 세기만 했다. 이것은
맞는지 본다. 라벨 규칙은 [VARIANT_GOLD_GUIDE](VARIANT_GOLD_GUIDE.md).

**이 축이 처음 보여준 것.**

- **침묵에 값이 붙었다.** 신중한 독자가 이름을 댈 자리 중 리졸버가 실제로
  확정하는 비율이 처음으로 측정됐다. commit precision 1.0은 아무것도 확정하지
  않아도 얻어지므로, 그 짝이 없으면 보수성은 언제나 공짜로 보인다.
- **근거 없는 확정이 2건 잡혔다.** `美국방부`를 대한민국 국방부로,
  `kt`(야구단)를 KT로. silver 스위트는 이것을 볼 수 없다 — silver span 위의
  commit만 채점하므로 span 밖은 *라벨이 없는 것*이지 틀린 것이 아니다.
- **응답의 상당수가 mention이 아닌 것에 관계 라벨을 싣는다.** gold가 "여기엔
  그 entity가 없다"고 한 자리에 `full_surface.identity`가 붙은 경우가 다수였다.
  이것이 M2 검토의 미결 항목 #3이며, 이제 숫자가 있다.
- **`PARTIAL`이라는 별도 범주가 필요했다.** `농협카드`의 `농협`은 농협은행을
  가리키지 않지만 무관한 문자열도 아니다. 이진으로 강제하면 계열사 이름과 순수
  오탐이 한 숫자에 섞인다.

**이 축이 아직 재지 못하는 것.** gold는 리졸버 출력의 층화 표본이므로
**재현율을 재지 못한다** — 리졸버가 한 번도 제안하지 않은 mention은 파일에
없다. 주석자도 1인이고 κ가 없다. SLM Gate A의 증거로 쓸 수 없다.

### M3 현실 커버리지 (2026-09-01) — 완료

**출발점은 세는 것이었다.** silver 표면형 뒤에 실제로 오는 한글 run
**1,970건**을 전수 조사해(리졸버를 돌리지 않고 tail 파서만) 카탈로그가
설명하지 못하는 것을 빈도순으로 뽑았다. M3의 카탈로그 항목은 그 목록에서
왔고, 각 항목 옆에 실측 건수를 주석으로 남겼다.

| | M2 | M3 |
|---|---:|---:|
| suffix 카탈로그 | 44 | **86** |
| 조사 카탈로그 | 59 | **62** |
| 실측 tail 커버리지 | 0.8538 | **0.9112** |

**항목별.** 마일스톤의 다섯 항목(tail taxonomy · punctuation class ·
OCR opt-in · confusion table · abbreviation signature index)을 세부로 풀면
다음과 같다. 앞의 넷은 전부 tail taxonomy 안의 결정이다.

- **wild tail 수동 taxonomy.** 실측 상위 항목을 분류했다 — `법`(26)·`판결`(8)·
  `고시`(5)·`훈령`·`조례`·`규칙`은 ARTIFACT, `이사회`(6)는 ORG_UNIT,
  `교향악단`(6)·`써비스`(6)·`헬스케어`(4)·`케미칼`(4)·`네트웍스`·`투자`는
  AFFILIATE. 실측 없이 넣은 항목은 실측된 항목과 **같은 닫힌 집합의 형제**
  (행정규범 나머지: 시행령·지침·예규)뿐이고, 주석으로 구분해 두었다.
- **다음절 기관 종결어.** `공사`·`공단`을 NAME_PART로 넣었다. M2 문서가
  "`한국전력` + `공사`가 SAME이 아니라 UNKNOWN"이라고 남긴 구멍이 이것이다.
  `공단`은 M2까지 AFFILIATE였는데, 그 분류라면 `국민연금` + `공단`이
  국민연금공단과 **다른 조직**이 된다.
- **문맥 의존 종결어.** `지사`는 core가 `도`로 끝나면 知事(사람), 아니면
  支社(지점)다. 감사가 `제주도지사`를 PART_OF로 찍은 것이 M2에서 이미
  보고됐다. 두 해석 모두 DISTINCT라 **commit 안전성은 어느 쪽이든 같고**,
  갈리는 것은 relation 라벨뿐이라 표 하나로 충분하다.
- **`서` 조사와 그 제약.** 미포함 tail 2위(14건)가 `서`(=에서 축약)였다.
  그냥 넣으면 `서울본부`가 조사로 시작하는 것처럼 보여 `한전서울본부`의 경계가
  SOFT에서 PASS로 풀린다 — **테스트 두 개가 즉시 잡았다**. 뒤에 한글이 더
  오면 조사로 읽지 않는 `TOKEN_FINAL_PARTICLES` 제약을 두어 14건은 얻고
  서울은 잃지 않았다.
- **넣지 않은 것.** `내`(內)는 실측 2건이 있었지만 뺐다. REFERENTIAL은 SAME이라
  **전체 표면형의 확정을 허용**하는데 `서울시내`는 서울시가 아니다 —
  `run_wild`의 DETECTION_ONLY가 이미 그 충돌을 이유로 서울시를 재현율 분모에서
  빼고 있었다. 2건을 얻자고 SAME 쪽으로 갈 근거가 못 된다.
- **punctuation class.** `-`만 무시하던 profile이 `‐`(U+2010)·`–`·`—`·`−`까지
  무시한다. PDF에서 복사한 `S‐Oil`이 빗나가던 자리다. `/`·`&`·`+`·`#`는
  **class를 만들지 않았다** — 이름의 일부일 수 있어서(`KT&G`, `S/W`, `C#`)
  profile이 하나씩 명시적으로 고른다.
- **OCR opt-in.** `ocr_tolerant` profile을 추가하되 **어떤 기본 profile도
  켜지 않는다**. 0/O를 모두에게 접으면 모든 일련번호가 서로의 근접 표면형이
  된다. 입력 provenance가 OCR이라고 말한 경우에만 tenant가 이 profile을
  지목한다.
- **confusion table.** 평음·격음·경음(`ㄱㅋㄲ`)과 모음 합류(`ㅐㅔ`)를 타입화한
  비용 표를 두고 `_subst_cost`가 최소 규칙으로 읽는다. 비용은 아직 **counted
  correction이 아니라 음운론에서** 왔다 — REVIEW_3 §4.6이 요구하는 "승인된
  교정에서 compile"은 M4의 승인 루프가 있어야 가능하다. class에 이름을 붙인
  것이 나중에 그 치환을 가능하게 한다. 합성 모음(`ㅚ`)은 표에 넣지 않았다:
  `to_jamo_seq`가 먼저 분해하므로 **한 번도 읽히지 않을 항목**이 되고,
  테스트가 그것을 막는다.
- **abbreviation signature index.** 토큰마다 전 entity를 순회하던 것을 첫 글자
  버킷으로 줄였고(175 entry / 79 버킷 / 최대 20), 정렬 대상을 canonical에서
  **등록된 name binding 전체**로 넓혔으며, 혼합 문자(`SK하닉`)를 지원한다.
  약어 후보의 commit 권한은 그대로 없다 — Level B이고 guard를 거친다.

**측정 — 새 축으로 M3를 재평가한 결과.** 두 체크아웃(`67fd422` = M2, 현재)에서
**같은 eval 하네스**를 같은 seed·같은 표본으로 돌린 쌍 비교다.

*변형 회수* (`run_variant_recall`, 170 family × 15 formation = 3,053 case,
host 6,000문장):

| 지표 | 조건 | M2 | M3 |
|---|---|---:|---:|
| variant-family macro recall | `\|candidate` | 0.9392 | 0.9392 |
| ├ Level A formation | `\|candidate` | 0.9868 | 0.9868 |
| └ Level B formation | `\|candidate` | 0.7532 | 0.7532 |
| commit macro (§2 SAME) | `\|commit` | 0.9865 | 0.9865 |
| core span 오분해율 | `\|mention` | 0.0052 | 0.0059 |
| 잘못된 entity 확정 | `\|commit` | 0 | 0 |
| **불변조건 ② 위반** | `\|commit` | **0** | **0** |
| **넓은 표면형 `UNKNOWN` 판정** | — | **639 / 1,070** | **352 / 1,070** |

읽는 법: **재현율도 확정도 계약도 움직이지 않았고, 이름을 못 붙이던 표면형만
287건 줄었다.** 카탈로그 작업이 해야 할 일이 정확히 그것이다 — 계약을 느슨하게
하지 않고 라벨을 채우는 것. formation별로는 `artifact` 214→30,
`org_unit` 135→32이고, `derivative_*` 세 행은 **하나도 움직이지 않았다**:
그 행이 쓰는 어미는 eval이 카탈로그 밖에서 고른 것이라 계약만 시험한다.
span 오분해율의 +0.0007(3,053건 중 16→18)은 카탈로그가 넓어져 후보가 늘어난
값이며, 아래 실텍스트 지표들과 같은 방향이다.

*Confusion 대조군* (같은 6,000문장, decoy 110개 = 근접 표면형 60·약칭 충돌
25·접두 확장 25):

| | 값 |
|---|---:|
| decoy가 후보로 올라온 mention | 193 |
| **decoy 확정(FP)** | **0** |
| silver 확정: decoy 없음 → 있음 | 301 → **259** |
| 약칭 충돌 mention / 두 뜻 모두 후보 | 93 / **93** |
| **충돌인데도 확정** | **0** |

`silver 확정` 줄이 새 정보다. **1 중성 거리의 형제를 110개 등록하면 확정이
42건 사라진다**(−14%). fake glossary 스위트에는 이 축이 아예 없다 —
형태소를 공유하지 않는 이름은 진짜 답과 경쟁하지 않으므로 잴 것이 없다.
아래 두 줄은 반대로 완전한 성적이다: 한 약칭에 뜻이 둘 생기면 93건 **전부**
두 뜻을 후보에 담고 **한 건도 확정하지 않는다**(불변조건 ④). decoy 확정도
0이다 — 근접 표면형이 후보로는 193번 올라왔는데(시험이 살아 있다는 증거)
확정으로는 한 번도 넘어가지 않았다.

*실문장 gold* (`run_variant_gold`, 사람이 라벨한 160행):

| 지표 | 조건 | M2 | M3 |
|---|---|---:|---:|
| 응답에 실린 mention | — | 160 | 159 |
| mention precision | `\|mention` | 0.3688 | 0.3711 |
| 단어를 자른 span | `\|mention` | 0.0875 (14) | 0.0818 (13) |
| gold entity가 후보에 | `\|candidate` | 1.0 | 1.0 |
| commit precision | `\|commit` | 0.931 (27/29) | 0.9333 (28/30) |
| **확정해야 할 때 확정** | `\|commit` | 0.4821 | **0.50** |
| **`identity` 정확도** | — | 0.7857 | **0.8214** |
| **`relation` 정확도** | — | 0.7778 | **0.8148** |
| **근거 없는 확정** | `\|commit` | **2** | **2** |

여기서 움직인 것은 **라벨**이다(identity +3.6%p, relation +3.7%p). precision과
span은 사실상 제자리이며, 그것이 맞다 — M3는 분해 규칙이 아니라 카탈로그를
바꿨다.

*표면형 합성 감사* (`run_composition_audit`, 실문장 10,000):

| 지표 | M2 | M3 |
|---|---:|---:|
| mention | 3,867 | **4,140** |
| RESOLVED 확정 | 771 | **775** |
| core보다 넓은 표면형 | 479 | 544 |
| 그중 `UNKNOWN` | 102 | **91** |
| commit 보류(typed) | 742 | 896 |

*미등록 약어* (`run_neural_eval`, 실문장 1,116 query, held-out 약칭 21종):

| 구성 | exact-core recall | family macro |
|---|---:|---:|
| symbolic | 0.853 → **0.8611** | 0.8916 → **0.8982** |
| hash | 0.8719 → **0.8799** | 0.9187 → **0.9253** |
| e5 | 0.8683 → **0.8763** | 0.9135 → **0.9201** |

세 구성이 같은 방향으로 같은 크기만큼 움직였다. 원인은 정렬 대상을 canonical
에서 **등록된 name binding 전체**로 넓힌 것과 기관 유형 종결 signature다.


*실측 tail 커버리지* (silver 표면형 뒤 한글 run 1,970건 전수):
**0.8538 → 0.9112**.

*실텍스트 회귀* (`run_wild_regression --single`, 20,000문장 동일 표본,
두 체크아웃):

| 지표 | M2 | M3 |
|---|---:|---:|
| silver mention / 탐지 / gold-in-set | 1,176 / 1.0 / 1.0 | 1,176 / 1.0 / 1.0 |
| RESOLVED 확정 | 1,047 | **1,051** |
| commit precision | 1.0 | 1.0 |
| ledger silver 밖 | 468 | 469 |
| **tail coverage** | 0.8634 | **0.9273** |
| **fake-glossary FP** | **0** | **0** |
| 후보 밀도 /1k chars | 5.044 | **5.459** |
| 지연 p50 / p95 (ms) | 50.4 / 359.8 | 50.6 / 366.1 |

M1은 재현율을 얻는 대신 p95를 1.36배 치렀고, M2는 비용이 0이었다.
**M3의 비용은 후보 8% 증가**다 — 카탈로그가 넓어지면 설명되는 tail이 늘고
그만큼 후보가 는다. 그 대가로 tail coverage가 +6.4%p, 확정이 4건 늘었고
구조적 오탐은 0에서 움직이지 않았다. (지연 두 값은 두 arm 모두 다른 작업과
CPU를 나눠 쓴 상태에서 잰 것이라 절대값을 인용하지 말 것 — 읽을 수 있는
것은 두 arm이 서로 같다는 사실뿐이다.)

*Level A 결정적 보장* (`run_eval`): conformance fixture가 568 → **632**로
늘었다 — 넓어진 구두점 class가 변형을 더 만들기 때문이고, `punct_variant`
슬라이스가 8 → **48**이 되었다. **전부 통과했고** Level A core-span recall은
분모가 213 → 253으로 커진 채 1.0을 유지한다. 커버리지를 넓히면서 결정적
보장을 느슨하게 하지 않았다는 뜻이다.

**읽는 법.** M3는 **후보를 넓히고 라벨을 채웠다.** 실문장 10,000개에서
mention이 3,867 → 4,140으로 늘고, 그중 이름을 못 붙이던 넓은 표면형은
102 → 91로 줄었으며, 확정이 4건 늘었다. 합성 스위트에서는 넓은 표면형의
`UNKNOWN`이 639 → 352로 줄었고, 미등록 약어 재현율이 세 구성 모두 약
+0.8%p 올랐다. **그러는 동안 불변조건 ② 위반, 잘못된 entity 확정,
fake-glossary FP는 모두 0에서 움직이지 않았다.**

넓힌 대가는 후보가 늘어난 것이고(합성 span 오분해율 0.0052 → 0.0059, 3,053건
중 16 → 18), 그 이상은 아니다. gold의 precision과 span은 사실상 제자리다 —
M3가 바꾼 것은 분해 규칙이 아니라 카탈로그이므로 그것이 맞는 결과다.

**남은 가장 큰 숫자는 M3가 건드리지 않았다** — 다음 절에서 다룬다. gold에서
확정해야 할 자리의 **절반이 확정되지 않았고**(0.50), 미확정 28건은 전부 span을
정확히 맞힌 mention이었다. 내역은 이렇다:

| 유형 | 건수 | 예 |
|---|---:|---|
| `ROLE_OF` | 13 | `금감원`장, `서울시`장, `대법원`장 |
| `IDENTITY` | 6 | `전북도`청, `경북도`청 — **전체가 곧 그 기관** |
| 병렬 기관명 | 8 | `KBS`한전, `SKT`코트라, `연합뉴스`타스통신 |
| `ARTIFACT_OF` | 1 | `서울특별시`건축조례… |

원인은 guard가 아니라 **calibration**이고, 정확히 재현된다:

```
금감원 규탄 기자회견        -> 금감원 0.943  RESOLVED
윤석헌 금감원장 …           -> 금감원 0.645  AMBIGUOUS   (resolve_threshold 0.70)
경북도청 신도시 …           -> 경북도 0.532  AMBIGUOUS
```

같은 core, 같은 채널, 같은 entity인데 **뒤에 표면형이 넓어졌다는 이유만으로
확률이 threshold 아래로 내려간다**. 넓은 표면형이 DISTINCT라는 판정은 이미
따로 실려 있으므로 core의 확률까지 깎을 이유가 없다 — 두 번 벌하는 셈이다.
임계값이나 사후확률을 건드리는 일이라 M3 범위 밖이며, 근거 없는 확정 2건
(`美국방부`→국방부, `kt`(야구단)→KT)과 함께 다음 단계의 입력으로 남긴다.

**측정이 잡아낸 결함 (1) — signature가 필요조건이 아니었다.** abbreviation
signature index의 첫 설계는 "약어는 이름의 첫 음절을 유지한다"였고, 그래서
target의 **첫 글자**로 버킷을 만들었다. 한국어에서는 틀린 전제다:
`고용노동부`→`노동부`, `보건복지부`→`복지부`처럼 앞 형태소를 통째로 버리는
약어가 흔하다. 그 둘이 정렬 대상에서 아예 사라졌고, **미등록 약어 트랙에서
exact-core recall이 0.853→0.818(symbolic), 0.872→0.839(hash),
0.868→0.838(e5)로 떨어졌다**. 다른 어떤 스위트도 이것을 보지 못했다 —
그 트랙만 held-out 약어를 묻기 때문이다.

고친 뒤 21개 held-out 약어의 정렬 결과가 M2와 **완전히 일치**한다. 올바른
필요조건은 "token의 첫 글자가 이름 **안에** 있다"이고, 부분열 정렬이 이미
요구하는 조건이라 재현율을 하나도 잃지 않으면서 버킷이 남는다. *가끔만* 참인
signature는 성능 최적화의 탈을 쓴 재현율 버그다.

**측정이 잡아낸 결함 (2).** abbreviation 정렬을 문자 체계 무관으로 바꾸자 두 글자
라틴 토큰이 더 긴 약어의 부분열로 붙었다 — `KB S`(띄어쓴 `KBS`)에서 `KB`만의
mention이 올바른 span과 경쟁했다. **새 스위트의 `spaced` formation에서
`core span 오분해율`이 0.0052→0.0072로 뛴 것이 유일한 신호였고**, 고친 뒤
0.0052로 정확히 돌아왔다. REVIEW_3 §4.6("짧은 라틴 약어에는 generic fuzzy를
거의 허용하지 않는다")이 이미 답을 갖고 있었다.

**첫 측정은 아무것도 보지 못했다.** 이 스위트의 첫 쌍 비교는 **바이트 단위로
동일**했다. 스위트가 쓰는 파생 어미를 전부 카탈로그 **밖에서** 고른 탓에
카탈로그 작업을 볼 수 없었던 것이다. eval이 소유하는 목록은 구현이 아는 것과
모르는 것에 **양다리를 걸쳐야** 하고, 테스트가 두 쪽 다 비지 않았음을
확인한다. 그러지 않으면 "변화 없음"은 반증 불가능한 진술이 된다.

전체는 [reports/VARIANT_RECALL.md](../reports/VARIANT_RECALL.md),
[reports/VARIANT_GOLD.md](../reports/VARIANT_GOLD.md),
[reports/COMPOSITION_AUDIT.md](../reports/COMPOSITION_AUDIT.md).

**남은 것(M3 범위 밖).** 혼합 문자(`SK하닉`) 정렬은 aligner에는 있으나
tokenizer가 문자 체계 경계에서 자르므로 **end-to-end로 닿지 않는다** —
문자 run을 한 토큰으로 잇는 것은 모든 채널의 경계 정책을 바꾸는 일이라
별도 과제다. confusion 비용도 아직 승인된 교정에서 compile한 것이 아니라
음운론에서 왔다(M4의 승인 루프가 선행 조건). 미등록 파생의 자동 제안은
그대로 M4다.

### 침묵의 값 — 설명된 tail이 core의 확정을 깎지 않는다 (2026-09-01)

**문제의 실체.** M3 gold가 처음 매긴 값이 "확정해야 할 자리 중 실제 확정
비율 0.50"이었고, 미확정 28건은 전부 **span을 정확히 맞힌** mention이었다.
원인은 guard가 아니라 점수였고, 정확히 재현된다:

```
금감원 규탄 기자회견        -> 금감원 0.943  RESOLVED
윤석헌 금감원장 …           -> 금감원 0.645  AMBIGUOUS   (resolve_threshold 0.70)
```

같은 entity, 같은 채널, 같은 span인데 **뒤에 표면형이 넓어졌다는 이유만으로**
threshold 아래로 내려간다. `tailparser`가 곱하던 두 값 때문이다:

```python
boundary_factor = 1.0 if boundary.status == "PASS" else 0.6
score = (1 - transform_cost) * best.score * boundary_factor
```

`best.score`는 이미 tail을 얼마나 설명했는지의 값이다(§16.5:
카탈로그 suffix로 완전 분해 0.9, 수식어 뒤 0.75, UNKNOWN 0.3). SOFT 경계는
"core 뒤로 한글이 이어지는데 이게 이 이름의 일부인가"라는 **질문**이고,
`best`가 바로 그 **답**이다. 답을 받아 든 뒤에 다시 0.6을 곱하는 것은
같은 의심을 두 번 청구하는 것이다.

**고친 것.** 잔여부가 **카탈로그 suffix로 완전히 분해되면**(`SUFFIX`) SOFT
경계의 추가 감점을 없앴다. 설명되지 않은 잔여부는 두 감점을 모두 유지한다
— 0.3 × 0.6은 어떤 threshold에도 닿지 않으며, 그것이 의도된 이중 신호다.

**`SUFFIX_WITH_MODIFIER`는 제외했다.** 처음엔 포함했는데, 그 종류는
"설명됨"처럼 읽히지만 아니다: `classify_suffix`는 카탈로그가 **모르는** 조각에
MODIFIER를 돌려주므로 `민공원`이 민(모름) + 원(NAME_PART)으로 분해되어 깨끗한
tail처럼 보인다. 그대로 두었더니 `부산시민공원` 안의 `부산시`가 확정됐다 —
**사람이 라벨한 gold만이** 부산시민공원이 공원이라는 것을 안다.

**측정** (M3 = `8e8d336` 대비, 같은 표본·같은 seed):

| 지표 | 조건 | M3 | +calibration |
|---|---|---:|---:|
| **확정해야 할 때 확정** (gold) | `\|commit` | 0.4821 (27/56) | **0.7143 (40/56)** |
| commit precision (gold) | `\|commit` | 0.9333 | **0.9524 (40/42)** |
| **근거 없는 확정** (gold) | `\|commit` | **2** | **2** |
| mention precision / span 오분해 (gold) | `\|mention` | 0.3711 / 0.0818 | 0.3711 / 0.0818 |
| RESOLVED 확정 (실문장 10,000) | — | 775 | **827** |
| variant-family macro recall | `\|candidate` | 0.9392 | 0.9392 |
| **불변조건 ② 위반 / 잘못된 entity 확정** | `\|commit` | **0 / 0** | **0 / 0** |

*실텍스트 회귀* (20,000문장 동일 표본):

| 지표 | M3 | +calibration |
|---|---:|---:|
| silver mention / 탐지 / gold-in-set | 1,176 / 1.0 / 1.0 | 1,176 / 1.0 / 1.0 |
| **RESOLVED 확정** | 1,051 | **1,141** |
| **commit precision** | **1.0** | **1.0** |
| silver 커버리지 | 0.8937 | **0.9702** |
| ledger silver 밖 | 469 | 482 |
| tail coverage | 0.9273 | 0.9273 |
| **fake-glossary FP** | **0** | **0** |
| 후보 밀도 /1k chars | 5.459 | 5.459 |

**후보를 하나도 더 만들지 않고**(밀도 동일) silver span 위 확정이 90건 늘었으며
precision은 1.0 그대로고 구조적 오탐도 0이다. 이것이 "이미 찾아 놓고 말하지
않던 것"이라는 말의 증거다. (지연은 두 arm이 다른 장비 부하에서 측정되어
인용하지 않는다.)

FORBIDDEN formation의 **core 확정률**(재현율이 아니라 보수성)이 크게 오른다 —
`artifact` 0.0097 → 0.8604, `org_unit` 0.0812 → 0.8571, `derivative_org`
0.0097 → 0.3312. 이것은 §2가 허용하는 방향이다: 그 표는 관련 파생에 대해
core 후보를 "가능", 전체 동일시를 "불가"로 둔다. **위반 열은 모든 formation
에서 0에서 움직이지 않았다** — 넓은 표면형은 여전히 부모 entity를 갖지
못한다.

**읽는 법.** 이 변경은 재현율을 새로 얻은 것이 아니라 **이미 찾아 놓고 말하지
않던 것을 말하게 한 것**이다. candidate 층 지표는 하나도 움직이지 않았고
(`macro recall` 0.9392 그대로), 움직인 것은 commit 층뿐이다. 그리고 precision이
같이 올랐다 — 되찾은 12건이 전부 gold가 확정하라고 한 자리였기 때문이다.

### 문자 체계가 바뀌는 자리는 이름의 끝이 아니다 (2026-09-01)

**문제의 실체.** M3에서 abbreviation aligner를 문자 체계 무관으로 만들었지만
`resolve`로는 닿지 않았다. 토큰 정규식이 문자 체계가 바뀌는 자리마다 끊기
때문이다:

```python
_TOKEN_RE = re.compile(r"[가-힣ㄱ-ㅣ]+|[A-Za-z][A-Za-z0-9]*|[0-9]+")
```

`SK하닉`은 `SK`와 `하닉`으로 갈려 aligner에 도착했고 둘 다 아무것도 맞히지
못했다. **모듈에 있는 기능이 파이프라인에 있는 기능은 아니다** — aligner
단위 테스트는 통과하고 있었고, 그 사실이 오히려 착시를 만들었다.

한국 기관명은 이름 한가운데서 문자 체계를 바꾼다(`SK하이닉스`, `LG유플러스`,
`한전KDN`). 그러므로 문자 체계 전환은 이름의 경계가 아니다.

**고친 것.** `_abbrev_tokens`가 문자 체계 run **에 더해** 한글과 ASCII를
섞은 run을 함께 내놓는다. 범위는 **abbreviation 채널 하나**다:

- 부분열 정렬은 글자가 어느 알파벳 소속인지 묻지 않으므로 그대로 옳다.
- fuzzy 채널의 편집 비용은 문자 체계별로 정의돼 있고(자모 거리, 두벌식 인접),
  섞인 run이 거기서 얼마여야 하는지는 **별개의 질문**이다. 그래서 fuzzy는
  문자 체계 run을 그대로 쓴다.

**"에 더해"가 핵심이다.** 섞인 run만 내놓으면, 어떤 단어에 라틴 문자 하나가
붙는 순간 그 안의 한글 alias가 조회 대상에서 사라진다. 두 벌 다 내놓고
겹치는 span은 node가 알아서 합친다.

`_TOKEN_RE`는 Level B 두 채널만 쓴다. exact 채널은 Aho-Corasick 인덱스를
쓰므로 이 변경에 닿지 않는다 — 결정적 보장은 건드리지 않았다.

**측정.** `SK하닉`·`LG유플`이 이제 mention을 만든다(AMBIGUOUS — Level B
약어는 §2가 "증거에 따라"라고 두었고 확정 권한이 없다). **실문장 gold는 이
변경을 보지 못한다**: 160행에 혼합 문자 약어가 한 건도 없고, 그래서 모든
수치가 소수점까지 동일하다. 이 스위트가 그것을 볼 수 없다는 사실을 숨기지
않는 편이 낫다 — 볼 수 있는 것은 회귀뿐이고, 회귀는 없었다.

**스위트가 볼 수 있게 만들었다.** 그래서 `mixed_abbrev` formation을 추가했다 —
문자 체계를 섞은 등록 표면형의 라턴 부분을 유지하고 한글 head를 두 음절로
줄인다(`SK하이닉스` → `SK하이`). realorg glossary에서 적용 가능한 것은 6 family다
— 이름 중간에서 문자 체계를 바꾸는 기관명 자체가 소수라, 나머지 family에는 이
셀이 없다(0점이 아니라 분모에서 빠진다).

| 지표 | 조건 | 이전 | 이후 |
|---|---|---:|---:|
| `mixed_abbrev` candidate macro (n=6) | `\|candidate` | **0.0** | **1.0** |
| `mixed_abbrev` span 정확 | `\|mention` | 0.0 | 1.0 |
| `mixed_abbrev` commit macro | `\|commit` | 0.0 | 0.0 |
| variant-family macro recall | `\|candidate` | 0.932 | **0.9397** |
| Level B formation macro | `\|candidate` | 0.7296 | **0.7626** |
| core span 오분해율 | `\|mention` | 0.0075 | 0.0072 |
| **불변조건 ② 위반 / 잘못된 entity 확정** | `\|commit` | **0 / 0** | **0 / 0** |

n=6은 비율로 읽기에 너무 작다. 여기서 읽을 것은 정도가 아니라 **종류**다:
이전에는 하나도 닿지 못했고 지금은 전부 닿는다. commit macro가 0인 것도 결함이
아니다 — 약어는 Level B이고 §2가 확정 권한을 주지 않는다.

*실텍스트 회귀* (20,000문장): silver mention / 탐지 / 확정 / precision /
tail coverage / fake-glossary FP / **후보 밀도(5.459)** 전부 소수점까지 동일하다.
비용이 0이다 — 실문장에서 문자 체계를 섞은 run 자체가 드물기 때문이고, 그것이
이 변경이 오랫동안 눈에 띄지 않았던 이유이기도 하다.

**같은 전제가 한 층 위에 또 있다 (미해결).** 고치는 도중 발견한 것:
`한전KDN`은 `한전`만 확정하고 **넓은 표면형을 아예 싣지 않는다**. matcher가
한글→라틴 전환을 깨끗한 토큰 경계로 판정해 라틴 run이 잔여부로 분석되지조차
않기 때문이다. 소비자 입장에서는 `농협카드`보다 나쁘다 — 경고할 자리가
`full_surface`에 있는데 그 필드가 아예 없다.

이것은 Level A 경계 정책이고 conformance fixture가 뒤에 붙어 있어 자체
측정 주기가 필요하다. **이번 변경에 끼워 넣지 않았다**: 같은 전제("문자 체계
전환 = 경계")가 틀렸다는 것만 여기 적어 둔다.

### 응답 계약 — 모르는 것을 관계로 말하지 않는다 (2026-09-01)

**먼저 잰 것.** M2 검토 미결 #3은 "entity가 확정되지 않은 mention에
`core_link`/`full_surface`가 붙는다(기록의 56%)"였다. 고치기 전에 **어느
결정 층에 실리는지**부터 셌다:

| gold 판정 | `KB_MISSING` | `AMBIGUOUS` | `RESOLVED` |
|---|---:|---:|---:|
| `refers=NO` | 38 | 14 | **0** |
| `refers=PARTIAL` | 9 | 14 | **0** |
| `refers=YES` | 3 | 14 | 16 |

**gold가 "여기엔 그 entity가 없다"고 한 75건 중 확정된 것은 하나도 없다.**
층 분리는 이미 `link_decision`으로 성립하고 있었고, ContextPack도 KB_MISSING
mention을 아예 싣지 않는다. AMBIGUOUS는 `ambiguous_mentions`로 따로 나가며
거기 붙는 `appears_inside`는 `same_entity="false"` — **안전한 방향**의 경고다.

그러므로 이것은 정확성 결함이 아니라 **가독성** 문제였다. 스키마를 다시 짤
일이 아니었고, 실제로 고칠 것은 따로 있었다.

**진짜 결함: 모르는 조각이 특정 관계를 주장했다.** `classify_suffix`는 카탈로그가
모르는 조각에 `MODIFIER`를 돌려주고, `TAIL_CLASSES[MODIFIER]`가
`(DISTINCT, NAMED_VARIANT)`였다. 그래서 `대한`|`민`국, `산림`|`당`국처럼
**아무것도 모르는** 자리가 "전체는 core의 다른 이름"이라는 **발견**을 내놓았다.
gold에서 `NAMED_VARIANT`가 붙은 15건은 **전부** mention이 아닌 자리였다.

두 주장이 엉켜 있었다:

- **전체가 core가 아니다** — 모르는 조각도 이것은 확실히 정한다(`서울부`는 `부`가
  아니다). `DISTINCT`는 유지한다.
- **어떻게 관계되는가** — 모르는 조각은 이것을 정하지 못한다. 주장을 멈춘다.

`MODIFIER`를 `UNKNOWN_PART`로 바꾸고 `(DISTINCT, "UNKNOWN")`에 매핑했다.
이름도 바꾼 이유는, `MODIFIER`가 §16.6의 **등록된 수식어**(전/현/구/신)와 같은
말이라 읽는 사람을 오도했기 때문이다. 실제로는 `SUFFIX_CLASSES` 어느 항목도
그 class를 갖지 않는다 — 오직 fallback이었다. (이 혼동은 앞선 calibration
작업에서 `민공원`을 "설명된 tail"로 착각하게 만든 것과 같은 뿌리다.)

**측정** (`5203ac5` 대비, 같은 표본):

| 지표 | 조건 | 이전 | 이후 |
|---|---|---:|---:|
| **mention이 아닌 곳에 관계를 단언** | `\|mention` | 0.68 (51/75) | **0.48 (36/75)** |
| 실문장 10,000의 `NAMED_VARIANT` 주장 | — | 178 | **0** |
| `relation` 정확도 (gold) | — | 0.8148 | 0.8148 |
| `identity` 정확도 (gold) | — | 0.8214 | 0.8214 |
| 확정해야 할 때 확정 / commit precision | `\|commit` | 0.7143 / 0.9524 | 0.7143 / 0.9524 |
| variant-family macro recall | `\|candidate` | 0.9397 | 0.9397 |
| **불변조건 ② 위반 / 잘못된 entity 확정** | `\|commit` | **0 / 0** | **0 / 0** |

**아무것도 움직이지 않았다는 것이 요점이다.** 실문장 10,000에서 mention(4,140),
확정(827), 넓은 표면형(544), `identity` 분포(431/91/22), **commit 보류
사유(886/31)까지 전부 소수점 없이 동일**하다. guard는 `full_identity`를 읽지
`relation`을 읽지 않으므로 안전성 경로는 애초에 닿지 않는다 — 사라진 것은
근거 없는 관계 이름 **178건**뿐이다.

**새 지표를 하나 추가했다.** `overclaimed_relations` — gold가 mention이 아니라고
한 자리에 응답이 특정 관계를 실은 비율. 이것이 없었다면 이 변경은 모든
리포트에서 "아무 변화 없음"으로 보였을 것이다. 남은 0.48은 `ROLE_OF`(12) ·
`IDENTITY`(11) · `AFFILIATE_OF`(9)처럼 **형태론적으로는 맞지만 core 자체가
잘못 제안된** 경우이고, 그것은 라벨이 아니라 후보 생성의 문제다.

### 붙어 있는 라틴 run은 경계가 아니라 잔여부다 (2026-09-01)

**문제의 실체.** `한전KDN`은 `한전`만 확정하고 **넓은 표면형을 아예 싣지
않았다**. `_is_token_boundary`가 문자 체계 전환을 깨끗한 경계로 판정하고,
tail 파서는 오른쪽이 한글일 때만(또는 `latin_morph` profile에서 복수형일 때만)
잔여부를 분석하기 때문이다. 그래서 다음 세 문장이 응답에서 구분되지 않았다:

| 표면형 | 전체가 가리키는 것 | 이전 응답 |
|---|---|---|
| `한전이` | 한국전력공사 | core + 조사 |
| `한전노조가` | **다른 조직** | core + `full_surface`(DISTINCT) |
| `한전KDN이` | **다른 회사** | core만. **`full_surface` 없음** |

세 번째가 `농협카드`보다 나쁘다. 거기엔 경고를 실을 필드라도 있는데, 여기엔
그 필드 자체가 없어서 core span을 하이라이트하거나 치환하는 소비자에게 **그
span이 더 긴 이름의 일부라는 사실을 전할 방법이 없었다.**

**방향은 한쪽뿐이었다.** 라틴 core 뒤에 한글이 오는 경우(`KT노조`, `KBS노조`,
`SKT지사`)는 이미 정상이었다 — tail 파서의 첫 분기가 boundary 판정과 무관하게
한글 run을 분석하기 때문이다. 잘못은 경계 규칙이 아니라 **tail 파서가 라틴
run을 쳐다보지 않는 것**에 있었고, 그래서 Level A 경계 정책을 건드리지 않고
고칠 수 있었다.

**고친 것.** 어떤 형태론 규칙으로도 설명되지 않는 **붙어 있는 라틴 run**을
UNKNOWN 잔여부로 읽는다. 설명되지 않은 한글 조각이 받는 것과 같은 답이고,
같은 경로로 도달한다. 결과: `한전KDN` → `full_surface=한전KDN`,
`identity=UNKNOWN`, core 확정 보류.

**세 가지를 좁혔다:**

- **다른 등록 표면형으로 시작하는 run은 잔여부가 아니다.** 한국어 헤드라인은
  두 기관 사이의 구두점을 자주 생략한다(`산업부KOTRA`, `삼성전자SKT`,
  `과기정통부GSMA`). 첫 판은 그것까지 설명 안 되는 잔여부로 읽어 **양쪽 확정을
  모두 취소**했다. matcher가 이미 두 번째 표면형을 찾아 놓았으므로 파서는 묻기만
  하면 됐다 — `eval/run_wild.py`가 M0부터 tail 통계에서 이 경우를 같은 규칙으로
  빼 왔다. **평가는 알고 있었고 리졸버만 몰랐다.**

- **조사는 이름의 일부가 아니다.** `_right_run`은 공백까지 걸어가므로 첫 판은
  `한전KDN이`를 이름으로 보고했다. 라틴 run이 끝나는 자리에서 잘라내고 뒤의
  한글은 조사 연쇄로 파싱한다 — M2가 정한 규칙이 이 경로에도 적용된다.
- **숫자는 이름 조각이 아니다.** 이 분기가 존재하는 이유인 이름들은 전부
  **글자**를 붙인다(KDN, ICT, GRS, E&C). 한국어 이름에 붙은 순수 숫자 run은
  띄어쓰기를 잃은 수량이고(`과학기술정보통신부2024년`), 첫 판은 그것까지
  잔여부로 읽어 부처가 받아야 할 확정을 보류했다. 글자가 하나라도 있어야 한다.

**스위트가 볼 수 있게 만들었다.** `latin_suffix` formation을 추가했다 —
한글 표면형에 계열사가 붙이는 라턴 run을 달아 만든다(KDN·ICT·GRS·DS·
CNS). 계약은 FORBIDDEN이다 — `한전KDN`은 다른 회사라 부모가 전체 표면형을
가져가면 안 된다.

| 지표 | 조건 | 이전 | 이후 |
|---|---|---:|---:|
| `latin_suffix` 넘은 표면형을 **보고함** (n=214) | `\|mention` | **0** | **214** |
| 그중 `identity=UNKNOWN` | `\|mention` | 0 | 214 |
| `latin_suffix` core 확정률 | `\|commit` | **1.0** | **0.0** |
| `latin_suffix` candidate macro | `\|candidate` | 1.0 | 1.0 |
| variant-family macro recall | `\|candidate` | 0.9444 | 0.9444 |
| core span 오분해율 | `\|mention` | 0.0046 | 0.0046 |
| **불변조건 ② 위반 / 잘못된 entity 확정** | `\|commit` | **0 / 0** | **0 / 0** |

첫 줄이 구먹의 크기다: **214건 전부 응답이 아무 말도 하지 않던 자리**였고,
그러면서 core는 전부 확정했다(1.0). 지금은 전부 넘은 표면형을 실고 확정을
보류한다. candidate 층은 그대로다 — core를 못 찾게 된 것이 아니라 말하게 된 것이다.

*실문장* (감사 10,000 / 회귀 20,000):

| 지표 | 이전 | 이후 |
|---|---:|---:|
| mention (10k) | 4,140 | 4,140 |
| RESOLVED 확정 (10k) | 827 | **824** |
| core보다 넘은 표면형 (10k) | 544 | **547** |
| 그중 `UNKNOWN` (10k) | 91 | **94** |
| silver 확정 (20k) | 1,141 | **1,138** |
| **commit precision (20k)** | **1.0** | **1.0** |
| **fake-glossary FP / 후보 밀도** | **0 / 5.459** | **0 / 5.459** |

실문장에서 이 분기가 건드리는 것은 20,000문장에 3건이다. 모두 `네이버TV`류의
서브브랜드고, 이전에는 그 자리에서 **아무 경고 없이 부분 이름을 확정**했다.
구두점을 생략한 병렬 기관명(`산업부KOTRA`, `삼성전자SKT`)은 위의 첫 번째
규칙이 되돌려 두 확정을 모두 살렸다 — 중간 단계에서 5건을 잃었다가 2건을
되찾았고, 그 2건이 병렬이었다.

*실문장 gold*는 이 변경을 보지 못한다 — 160행의 병렬 기관명은 전부
한글+한글(`KBS한전`, `연합뉴스타스통신`)이라 다른 분기를 타기 때문이다. 모든
수치가 그대로고, 그것이 맞는 결과다.

**같이 발견했지만 고치지 않은 것.** `AP통신이`가 `full_surface=AP통신이`로
보고된다 — 조사가 이름 안에 들어간다. 이것은 이 변경 **이전부터** 있던 것이고
경로도 다르다(라틴 core + 한글 run, tail 파서 첫 분기). 원인은
`enumerate_tails`의 정렬이 점수 동률일 때 **조사가 적은 쪽**을 앞에 두는 것이라,
`통신이`(UNKNOWN, 조사 0)가 `통신`+`이`(UNKNOWN, 조사 1)를 이긴다. UNKNOWN
잔여부에서는 어느 쪽인지 파서가 알 수 없으므로 동률 규칙 자체를 바꿔야 하고,
그것은 모든 UNKNOWN 잔여부의 span을 바꾸는 별도 변경이다.

### 조사는 이름의 끝이 아니다 — 동점을 가르는 규칙 (2026-09-02)

**문제의 실체.** `AP통신이`가 `full_surface=AP통신이`로 보고됐다. 조사가 이름
안에 들어간다. §16이 정한 것과 정반대이고(`surface_span`의 docstring이 그
말을 그대로 하고 있다), 이 span을 하이라이트하거나 치환하는 소비자는 문장에
없는 이름을 받는다.

**원인은 점수가 아니라 동점 규칙이었다.** `enumerate_tails`는 같은 문자열의
모든 읽기를 만들고 `(-score, len(particles))`로 정렬한다. `통신이`(UNKNOWN,
조사 0)와 `통신`+`이`(UNKNOWN, 조사 1)는 **점수가 정확히 같고**, 둘째 키가
조사가 **적은** 쪽을 앞에 둔다. 카탈로그가 잔여부를 설명하지 못할 때마다
조사가 이름 안으로 들어갔다.

**동점은 span만 가른다 — 증명 가능하게.** `_RESIDUAL_BASE`(4값) × 문법성
계수(1.0/0.7)의 곱 8개가 **전부 다르다**. 그래서 동점은 곧 같은
`residual_kind`·같은 문법성이고, identity·relation·commit 보류는 모두 그
둘에서 나온다. 동점 순서를 바꾸는 것은 **보고하는 이름의 끝**만 움직이고 다른
어떤 것도 움직일 수 없다. 표가 나중에 충돌을 얻으면 이 논증이 조용히 무너지므로
테스트로 고정했다.

**고친 것.** 동점일 때는 **조사를 떼는 읽기**가 이긴다 — 단, 이름의 끝음절이
될 수 없는 조사일 때만(`SPLITTABLE_PARTICLES`, 62개 중 32개).

**허용 목록인 이유는 오류가 대칭이 아니기 때문이다.** 전체 코퍼스
114,605문장에서 동점을 그냥 뒤집어 봤다: 110건이 바뀌고 그중 **8건이 이름을
반토막** 냈다 — `카카오게임`→`카카오게`, `코레일공항철도`→`코레일공항철`,
`카카오브레인`→`카카오브레`, `서울시메트로`→`서울시메트`, `행자부유엔`→`행자부유`.
`임`·`인`·`도`·`로`·`엔`은 조사이면서 흔한 이름 끝음절이다. 위쪽 주석이 한 음절
조사가 명사의 **첫** 음절과 겹친다고 이미 말하는데(`도`시, `과`학), **끝**
음절과도 똑같이 겹친다는 것은 적혀 있지 않았다.

조사를 이름에 남기면 진짜 이름의 superstring을 보고한다(`카카오톡에`). 이름
음절을 조사로 떼면 **아무것도 철자하지 않는 span**을 보고하고 그 음절은 mention
밖으로 나간다. 그래서 목록에 없는 조사는 붙은 채로 둔다. 같은 코퍼스에서 허용
목록으로 다시 재면 92건이 바뀌고, **이름을 자른 것은 0건**이다(남은 2건은
`복지부동하는`·`YTN스타라는`으로, 둘 다 이 변경 이전에도 잘못 잡힌 mention이라
어느 읽기든 쓰레기다).

**`과`는 덤으로 따라왔다.** SUFFIX_CLASSES와 PARTICLES가 공유하는 **유일한**
항목이라, 완전히 설명된 잔여부끼리 동점을 만들 수 있는 유일한 끝이기도 하다.
`서울시장과`·`공정거래법과`·`KEB하나은행장과`는 `장`+`과(부서)`로 읽혀 접속의
`과`를 이름 안에 넣고 있었다. `과`가 부서로 정당한 자리는 `총무과`처럼 카탈로그에
없는 이름 뒤이고 그것은 SUFFIX_WITH_MODIFIER(0.75)라 애초에 동점이 아니다.
동점이 되는 것은 **다른 종결어 바로 뒤**뿐이고, 거기에 부서는 없다.

**스위트가 볼 수 있게 만들었다.** `derivative_particle` formation은 이미 이
모양을 만들고 있었는데(`대변인`·`고문`·`출입기자단`은 일부러 카탈로그 밖이다)
채점표에 **이름의 끝을 맞게 보고했는가**를 묻는 칸이 없었다. `VariantCase`에
`name`(token − 조사)을 붙이고 `name_span_exact`를 추가했다. 감사 쪽에는 실문장
지표를 붙였다 — `full_surface`가 **카탈로그 조사 전체** 중 하나로 끝나는 건수.
분리하기로 한 조사만 세면 정의상 0이라 아무것도 재지 못한다.

*변형 스위트* (170 family × 17 formation = 3,273 case):

| 지표 | 조건 | 이전 | 이후 |
|---|---|---:|---:|
| `derivative_particle` **이름 끝을 맞게 보고** (n=214) | `\|mention` | **0.4673** | **0.9393** |
| variant-family macro recall | `\|candidate` | 0.9444 | 0.9444 |
| ├ Level A / Level B macro | `\|candidate` | 0.9869 / 0.7710 | 0.9869 / 0.7710 |
| commit macro (SAME 계열) | `\|commit` | 0.9865 | 0.9865 |
| core span 오분해율 | `\|mention` | 0.0046 | 0.0046 |
| FORBIDDEN 넓은 표면형 / 그중 UNKNOWN | `\|mention` | 1,284 / 562 | 1,284 / 562 |
| **불변조건 ② 위반 / 잘못된 entity 확정 / decoy 확정** | `\|commit` | **0 / 0 / 0** | **0 / 0 / 0** |

남은 11건은 둘로 갈린다. **8건은 `로`** — 일부러 뺀 조사다(`서울시메트로`,
`종로`). **3건은 `대변인과`·`고문과`** 로, 아래 미해결 항목이다. 첫 줄 말고는
아무것도 움직이지 않았다는 것이 이 변경의 성질이다.

*실문장 감사* (10,000문장):

| 지표 | 이전 | 이후 |
|---|---:|---:|
| mention | 4,140 | 4,140 |
| RESOLVED 확정 | 824 | 824 |
| core보다 넓은 표면형 | 547 | 547 |
| identity·tail_class·relation 분포 | — | **전부 동일** |
| commit 보류 사유 분포 | — | **전부 동일** |
| **이름 안에 조사가 들어간 것** | **25** | **12** |

남은 12건: `과` 9(그중 `통계학과`·`여성학과`는 실제로 학과라 맞는 보고다),
`서` 1(`정보부서`), `부터` 1(`중기부터` — 잔여부는 `터`이고 지표가 문자열로만
걸린 것), `으로` 1(`KBS클래식FM으로` — 잔여부 안에 라틴이 섞여 동점 자체가
만들어지지 않는 별개 경로).

*gold 160행*은 요약 지표가 **바이트 단위로 동일**하다. 이 모양의 행이 없다 —
`latin_suffix` 때와 같은 이유이고, 그래서 스위트 쪽에 칸을 만든 것이다.

*실문장 회귀* (20,000문장, 짝지어 측정): **모든 지표가 동일하다** — silver 확정
1,138, commit precision 1.0, coverage 0.9677, ledger 1,617/479, tail coverage
0.9273, fake-glossary FP 0, 후보 밀도 5.459. 위의 증명이 예측한 그대로다.
확정을 만드는 어떤 값도 동점 순서에 닿지 않는다.


**같이 발견했지만 고치지 않은 것.** `대변인과`·`고문과`는 그대로 남는다.
SUFFIX_WITH_MODIFIER(0.75)가 UNKNOWN+조사(0.3)를 **점수로** 이기므로 동점이
아니고, 이 규칙이 닿지 않는다. 그리고 여기서는 애매함이 진짜다 —
`총무과`·`예산과`와 형태가 완전히 같고(4음절 이하 미등록 chunk + `과`), 그 둘은
흡수하는 쪽이 **맞다**. 형태론만으로 가를 수 있는 자리가 아니다. 실문장 잔여
`과` 10건이 이 모양이다.

### 미등록 변형 채굴 — 응답이 이미 말하고 있던 백로그 (2026-09-02) — M4 1/2

**M4가 물은 것.** 미등록 파생을 자동으로 제안하고 승인 루프에 태우는 것.
설계 전에 백로그를 먼저 셌고, 그 census가 계획을 바꿨다.

**신호는 이미 응답 안에 있다.** `full_surface`에 `SAME_AS_CORE`가 아닌
`identity`가 실려 있다는 것은 resolver가 **자기가 가지지 못한 더 긴 이름이
여기 있다**고 말하는 것이다. 새 분석이 필요 없고, 공개 응답 필드만 읽으면
된다 — 그래서 채굴기는 이 모듈보다 오래된 빌드의 출력에도 돈다.

**census가 계획을 고쳤다.** 20,000문장에서 넓은 표면형 1,147건, 서로 다른
자리 354개. 그런데 **263개(74%)가 1회성**이고, 상위 자리를 읽어 보면 태반이
이름이 아니었다:

| 자리 | 관측 | 실체 |
|---|---:|---|
| `대한` + `민국` | 147 | 대한민국. `대한`은 대한항공의 등록 표면형이 아니다 |
| `해수` + `욕장` | 9 | 해수욕장. 약어 채널이 해양수산부의 부분수열로 닿았다 |
| `소프트` + `웨어` | 4 | 소프트웨어 |
| `카카오` + `톡` | 10 | **진짜 이름** |

셋 다 확정되지 않았다(`KB_MISSING`/`AMBIGUOUS`) — guard는 제 일을 했다. 문제는
**후보 층의 반복이 증거가 되지 못한다**는 것이다. 흔한 것은 이름이 아니라
**단어**여서, 우연히 겹친 접두는 진짜만큼 안정적으로 반복된다.

**그래서 발견을 둘로 나눴고, 둘은 증거의 세기가 다르다.**

- **종결어 공백** — 여러 entity 뒤에 반복되는 잔여부. 우연이라면 서로 무관한
  이름들에서 같은 끝이 반복되어야 하므로 **entity 수가 곧 증거**다. M4가
  요청한 것이 아닌데도 **둘 중 강한 쪽**이다. M3까지 손으로 하던 taxonomy
  작업이 여기서는 측정값이 된다.
- **이름 공백** — 한 entity 뒤에서만 반복되는 잔여부. M4가 노린 것이고 약한
  쪽이다. **exact 채널이 찾은 core 뒤에서만** 채굴한다 — 등록된 표면형이지
  부분수열이 아니라는 뜻이고, `카카오`+`톡`과 `해수`+`욕장`을 가르는 것이
  정확히 그 차이다.

**측정** (20,000문장, `eval/run_variant_mining`):

| 단계 | 건수 |
|---|---:|
| mention | 8,479 |
| core보다 넓은 표면형 | 1,147 |
| 서로 다른 (entity, 잔여부) 자리 | 354 |
| 그중 1회성 | 263 |
| 여러 entity에 붙는 잔여부 | 19 (그중 카탈로그에 이미 있는 것 12) |
| **종결어 공백** | **7** |
| **이름 공백** | **4** |

자리 354개에서 발견 11건. 이름 공백 4건은 `카카오톡`·`카카오게임즈`·
`대법원판결`·`현대차증권`으로 **전부 진짜 이름**이고, census가 보여 준
`해수욕장`·`공소사실`·`소프트웨어`·`대선결과`는 exact 게이트가 전부 걸러냈다.
종결어 공백 7건 중 `교육청`(entity 12개)·`고법`·`지부`·`공무원`·`뉴스`가
카탈로그 후보이고, `고`는 조각이다.

전체는 [reports/VARIANT_MINING.md](../reports/VARIANT_MINING.md).

**승인 루프는 PLAN_PI의 상태 모델을 그대로 쓴다.** `NameGap.to_proposal()`이
`TermProposalStore.submit()`의 인자를 만들고, `origin`은
`deterministic_detector`다 — 정책이 explicit으로 치지 않으므로 **어느 scope에서도
자동 활성화되지 않는다**. 증거는 LLM 제안보다 강하다: `surface_present`가
주장이 아니라 코퍼스를 읽은 결과이고, 어느 문서에서 봤는지가 붙는다.

`canonical`과 `short_definition`은 기본값 없는 키워드 인자이고 공백이면
거절한다. **채굴기는 이름이 있다는 것만 알고 그것이 무엇인지는 모른다** —
둘 중 하나를 지어내는 것이 이 루프가 막으려는 바로 그 일이다.

**등록은 관계까지 같이 한다.** 파생을 독립 entity로만 등록하면 채굴기가
확인한 유일한 사실 — 이 표면형이 사전이 가진 core로 시작한다는 것 — 을
버리게 된다. `to_composition()`이 잔여부를 `surface_suffix`로 하는
`COMPOSES_TO`를 만들고, 그러면 불변조건 ③이 그 표면형에 **이름을 준다**.
다음 채굴에서 같은 자리가 백로그가 아니라 `already_named`로 세어지는 것이
루프가 닫혔다는 증거이고, 테스트가 그 왕복을 통째로 돈다.

**하지 않은 것.** 종결어 공백에는 `to_proposal`이 **없다**. §5가 검토 없는
전역 `SUFFIXES` 추가를 금지하고, 잘못된 class는 대칭이 아니다 —
`NAME_PART`/`REFERENTIAL`은 전체 표면형의 확정을 **허용**한다. 그래서 그 표는
검토 대상 목록이지 패치가 아니고, 테스트가 채굴 전후로 `SUFFIX_CLASSES`가
바이트 단위로 같은지 확인한다.

### 문서가 준 이름 — 조건이 목적과 반대로 걸려 있었다 (2026-09-03) — M6 1/2

**M6가 물은 것.** 제한적으로 새 entity를 제안하는 것. 시작하기 전에 §18
문서 내 정의 경로가 실텍스트에서 무엇을 하는지 재 봤고, 답은 **거의 아무것도
하지 않는다**였다.

**측정이 먼저 찾은 것은 결함이었다.** `ktrf/doclocal.py`는 스펙 §18이고
REQ-LOC-001/002이며 resolver에 `+0.20` 점수 보정까지 걸려 있다. 그런데
114,605문장에서 정의 패턴 **2,346건이 일치하는 동안 별칭은 6건** 나왔다.
원인은 커버리지가 아니라 조건의 방향이다:

```python
entity_ids = self._resolve_long_form(long_form)
if not entity_ids:
    ...
    else:
        continue        # 문서가 이름을 말해줬는데 버린다
```

`extract()`는 **긴 이름이 이미 등록돼 있어야** 별칭을 만든다. 그런데 문서가
`X(Y)`를 쓰는 이유는 정확히 독자가 **가지고 있지 않은** 이름을 소개하기
위해서다. 조건이 목적과 반대로 걸려 있으므로 이 모듈은 **아무것도 더해주지
않는 경우에만** 발동할 수 있다. 20,000문장 표본에서는 0건이었다.

**계약이 고정한 것은 하지 말아야 할 일뿐이었다.** REQ-LOC-001/002를 거는
테스트는 두 개이고 둘 다 "전역 사전을 덮어쓰지 않는다"를 검사한다 — 아무 일도
하지 않는 모듈이 완벽하게 통과하는 성질이다. 합성 픽스처에서는 통과하고
실텍스트에서는 침묵하는 종류의 결함이며, ROADMAP이 이미 "평가 쪽 결함"으로
기록한 부류다.

**그 6건을 하나씩 읽은 것이 두 번째 결함을 찾았다.** 총계만 봤으면 놓쳤을
것이다 — 6건 중 **3건이 틀렸고**, 틀린 쪽은 한 갈래에 몰려 있었다:

| 갈래 | 짝 | 판정 |
|---|---|---|
| forward | `한국철도공사(코레일)` | ✓ |
| forward | `한수원(한국수력원자력)` | ✓ |
| forward | `서울특별시(사실상), 세종특별자치시(행정)` | ✗ 수도 표기의 한정어 |
| reversed | `노선영(강원도청)` | ✗ 선수(소속팀) |
| reversed | `현대캐피탈(현대자동차그룹)` | ✗ 자회사(모기업) |
| reversed | `저는 공공기관(한국토지주택공사)` | ✗ |

reversed 갈래(`Y(X)` — 괄호 안이 긴 이름)의 유일한 증거는
`len(short) > len(long_form)`였다. **더 길다는 것은 증거가 아니다.** 세 번
발동해 세 번 틀렸고, 셋 다 서로 다른 한국어 동격 관습이다. 각각이 이름이
아닌 표면형을 entity에 묶고 점수 보정까지 얹었다.

**한글 약칭은 근거를 보여야 한다.** `reversed_pair_defines()`는
`AbbrevAligner`가 요구하는 것과 같은 부분수열 정렬을 요구한다 — 세 오탐이
모두 걸리고 `한전(한국전력공사)`은 통과한다. 라틴 두문자는 예외인데, `KIST`는
`한국과학기술연구원`의 로마자화에서 만들어진 것이고 이 라이브러리는 그것을
계산할 방법이 없다. 그 문서화된 형식에서는 관습 자체가 증거다.

`세종특별자치시(행정)`은 **고치지 않았다.** `코레일`(만들어진 이름)과
`행정`(보통명사)을 가르려면 보통명사 목록이 필요하고, 이 라이브러리는 그것을
가지고 있지 않다. 114,605문장에 1건이며 리포트가 그대로 싣는다.

**그리고 버려지던 정의는 이제 제안이 된다.** 등록된 entity가 없으면 묶을 곳도
없으므로 resolver는 관여하지 않는다 — `extract_new_terms()`가
`NewTermDefinition`으로 보고하고 `ktrf.registry.proposals`로 간다. 기존 수치가
움직이지 않는 이유가 이것이다.

**M4와 다른 점 하나.** 잔여부 채굴은 이름이 **있다**는 것만 알아서 canonical을
사람이 채워야 했다. 정의 패턴은 문서가 **canonical을 직접 말한 것**이고, 그것이
정의를 정의이게 하는 성질이다. 다만 문서는 그것이 **무엇인지**는 말하지 않으므로
`short_definition`은 여전히 사람 몫이고 `to_proposal`이 지어내기를 거부한다.

**게이트는 셋이고, 넷째부터는 일부러 얹지 않았다.** 전 코퍼스에서 후보 규칙을
먼저 재고 골랐다:

- **약어는 건너뛴다.** `초등학교`는 `서원초등학교`의 부분수열이지만 줄인 것이
  아니라 이름을 자른 것이다. `변제`←`대물변제`, `선물`←`선물옵션`도 같다.
  연속된 구간은 절단이고, 이름을 가로질러 음절을 고르는 것이 약어다. (18건 제거)
- **정렬이 이름의 시작을 말한다.** `X(Y)`는 괄호 앞의 절을 통째로 잡는다 —
  `위한 중앙재난안전대책본부`, `탈당하여 후보 단일화 추진 협의회`. 첫 정렬
  문자가 약어가 주장하는 첫 문자이므로 그 왼쪽은 이름이 아니라 문장이다.
  **M4에서 잔여부가 이름의 끝을 말한 것의 거울상이다.**
- **끝나는 자리도 말한다.** 마지막 정렬 문자 뒤에 어절이 남으면 정렬이 이름을
  덮은 게 아니라 문장을 가로지른 것이다 —
  `미국`이 `미사일에 대한 국제사회와 트럼프대통령과 트럼프행정부`를 "줄인" 경우. (6건 제거)

후보 규칙 세 개를 더 재봤고 **셋 다 진짜 이름을 죽였다**: 마지막 문자 일치는
`추경`←`추가경정예산`을, 정렬 밀도는 `개특법`을, 이름 내부 조사 금지는
법령명 전체를 죽인다(`~에 관한 특별조치법`은 조사를 품은 진짜 이름이다).
21행을 손으로 다듬는 것은 그 21행에 대한 과적합이므로 거기서 멈췄다.

**측정** (114,605문장 전체, `eval/run_doclocal_audit`):

| 단계 | 건수 |
|---|---:|
| 정의 패턴 일치 | 2,346 |
| 긴 이름이 이미 등록된 entity | 31 |
| → 문서 내 별칭 (해석에 영향) | 6 → **3** |
| → 미등록 이름 정의 (제안 큐) | **18** (서로 다른 15) |

거부 사유: `not_a_subsequence` 1,912 · `too_short_to_abbreviate` 360 ·
`contiguous_substring` 18 · `name_does_not_end_there` 6 ·
`bare_type_terminal` 1.

**찾은 것 중 사람이 읽어 진짜인 것**: `추경`←추가경정예산,
`중대본`←중앙재난안전대책본부, `국공노`←국가공무원노동조합,
`교총`←교원단체총연합회, `개특법`←개발제한구역…특별조치법, `비대위`←비상대책위,
`후단협`←후보 단일화 추진 협의회, `활보`←활동보조인,
`PPR`←Portland Pattern Repository, `CSE`←Computer Science and Engineering,
`SAC`←Stand Alone Complex. 15건 중 11건이며, 나머지 4건
(`셀레노효소`·`혈색소`·`근해자망`·`자금조달계획서`)은 오탐이다. gold가 없으므로
리포트는 정밀도를 **주장하지 않고** 목록을 그대로 싣는다 — 검토 큐이지 사전
패치가 아니다.

**이하 패턴의 60%는 잘린 단어였다.** `_PAT_IHA`가 두 음절을 어디서나 잡아서
`용이하게`·`맞이하게`·`같이하여`가 정의로 읽혔다 — 긴 이름이 `용`에서 끝나고
별칭이 `게`가 된다. 그 패턴이 실텍스트에서 발동한 58건 중 35건이 이것이었다.
이제 `이하`는 자기 어절을 열어야 한다.

**하지 않은 것.** 미등록 이름에 대한 **문서 범위 synthetic entity**는 만들지
않았다. 그것을 만들면 응답 스키마·candidates·snapshot이 전부 따라 움직이고,
resolver 변경은 회귀 위험을 지는 반면 제안 경로는 지지 않는다. `국공노`가
문서 안에서 해석되려면 그 entity가 실제로 승인·등록돼야 하고, 그 왕복이
M6의 나머지 절반이다.

### 규칙이 자기 코퍼스 밖에서도 버티는가 (2026-09-03) — held-out

M6의 정렬 게이트 세 개는 **21~26행을 눈으로 읽고** 골랐다. 그것은 과적합의
전형적인 모양이므로, 그 규칙을 한 번도 통과시켜 본 적 없는 코퍼스가 필요했다.

**기존 코퍼스는 건드리지 않았다.** 거기에 도메인을 더하면 공개된 모든 수치가
변경과 무관한 이유로 움직인다. 대신 별도 코퍼스 두 개를 받았다:

| 코퍼스 | 구성 | 문장 |
|---|---|---:|
| `wild` | 뉴스 헤드라인·청원·판례·백과 (기존) | 114,605 |
| `holdout` | **뉴스 본문**(Apache-2.0) + **비격식 댓글**(CC BY-SA 4.0) | 29,735 |
| `holdout2` | 같은 뉴스 소스의 **겹치지 않는 기사** | 18,000 |

앞의 다섯 도메인에 없던 것을 골랐다 — 기존 뉴스는 연합뉴스 **헤드라인**(한 문장)
이고, 비격식 텍스트는 아예 없었다. LLM이 생성한 코퍼스는 검토했지만 뺐다:
합성 산문은 사람이 실제로 어떻게 쓰는지에 대한 규칙을 반증할 수 없다.

**정밀도는 개발 코퍼스 밖에서 더 좋았다.**

| 코퍼스 | 발견 | 사람이 읽어 진짜 |
|---|---:|---|
| `wild` (규칙을 고른 곳) | 15 | 11 (73%) |
| `holdout` | 6 | **6 (100%)** |
| `holdout2` | 8 | **8 (100%)** |

`중진공`←중소벤처기업진흥공단, `배민`←배달의민족, `콘진원`←콘텐츠진흥원,
`전지협`←전국지역아동센터협의회, `주정심`←주거정책심의위원회,
`NFT`←Non Fungible Token. 게이트 세 개 전부 held-out에서도 발동한다 —
개발 코퍼스에서만 의미 있던 죽은 규칙이 아니다.

`wild`의 정밀도가 더 낮은 이유도 드러났다: 패턴 일치율이 2.0% 대 0.28%로
훨씬 높은데, 그 대부분이 **판례의 괄호 관습**(`원고(반소피고)`)이다. 개발
코퍼스가 유난히 적대적이었던 것이지 규칙이 거기 맞춰진 것이 아니었다.

**held-out이 찾은 것은 정밀도가 아니라 recall 결함이었다.** 거부된 짝을
읽어 보니 `name_does_not_end_there`로 걸린 3건이 **전부 진짜**였다:

```
한국콘텐츠진흥원 원장 조현래  ->  한콘진
코리아스타트업포럼 의장 박재욱 ->  코스포
기술보증기금 이사장 김종호    ->  기보
```

한국 보도자료는 기관을 `기관명(직책 이름, 이하 약칭)`으로 소개한다. 괄호를
제거한 코퍼스에서는 `기관명 직책 이름`이 마커 앞에 남고, 정렬 뒤로 어절이
따라오므로 게이트가 잘라냈다. 그런데 이 모양은 게이트가 막으려던 것과 다르다 —
`미국`이 문장을 가로지른 경우는 정렬이 **여러 어절에 흩어져** 있고, 이쪽은
**한 어절 안에** 있다. 그래서 규칙을 좁혔다: 뒤에 어절이 남더라도 **정렬이 한
어절 안에 있으면** 이름은 그 어절에서 끝난다.

**그 수정은 held-out을 소비한다.** 세 행을 읽고 규칙을 고쳤으므로 그 코퍼스는
더 이상 held-out이 아니다. 그래서 두 가지로 확인했다:

- **개발 코퍼스에서 아무것도 바뀌지 않는다** — 15건 그대로, 추가도 손실도 0.
- **읽은 적 없는 기사(`holdout2`)에서 8건 전부 진짜**이고, 그중 `중진공`·
  `콘진원`·`전지협`이 바로 이 보도자료 모양이다.

`기보`는 여전히 놓친다. 부분수열 정렬이 **가장 왼쪽**부터 맞추므로
`기술가치금액`의 `기`에 먼저 걸려 여러 어절에 흩어진 정렬이 된다. 오른쪽부터
맞추는 변형은 만들지 않았다 — 한 행을 위해 정렬 방향을 바꾸는 것이 바로 이
절이 경계하는 일이다.

**채굴기(M4)도 같은 코퍼스에 돌렸고, 결과가 다르다.** held-out 20,000문장에서
이름 공백 **26건**(wild는 4건). 뉴스 본문이 헤드라인보다 조직 언급이 훨씬
조밀하므로 수 자체는 놀랍지 않지만, **구성이 다르다**:

- 진짜 미등록 조직명 19건 — `카카오모빌리티`·`카카오게임즈`·`네이버웹툰`·
  `포스코홀딩스`·`KT클라우드`·`셀트리온헬스케어`·`카카오뱅크` 등.
- **이름이 아닌 것 6건** — `경기도지사`·`금융위원장`·`공정위원장`(ROLE),
  `현대차지부`·`카카오지회`(ORG_UNIT), `카카오노조`(DERIVED_ORG). 이들의 잔여부는
  entity 하나 뒤에서만 반복돼 종결어 공백 문턱(entity ≥3)에 못 미쳐 **이름 공백
  쪽으로 떨어진다**. 설계상 검토 큐이므로 결함은 아니지만, wild에서 "4건 전부
  진짜"였던 것이 조직 밀도가 높은 코퍼스에서는 **19/26**이 된다.
- **조사가 이름 안에 들어간 것 1건** — `네이버웹툰과`.

마지막 것은 리포트에 적어둔 `대변인과`/`고문과` 유예 사례가 held-out에서 다시
나온 것이고, 확인해 보니 유예 당시 기록보다 나쁘다:

```
네이버웹툰이 공개했다      → full_surface '네이버웹툰'    (조사 이 분해됨)
네이버웹툰과 카카오가 …    → full_surface '네이버웹툰과'  identity DISTINCT_FROM_CORE
```

`과`는 조사이면서 동시에 종결어(총무`과`)라 "웹툰+과(부서)" 읽기가
"웹툰과=UNKNOWN+조사"보다 점수가 높고, 그래서 **동점이 생기지 않아** 조사 분해
규칙이 닿지 못한다. 결과는 span이 조금 넓은 정도가 아니라 **존재하지 않는 부서를
별개 조직으로 주장**하는 것이다. 20,000문장에서 4회 발동했다.

고치는 방향은 있다 — UNKNOWN_PART 뒤에 종결어가 붙은 읽기가
`SUFFIX_WITH_MODIFIER`(0.75)의 확신을 빌려 쓰는 것이 문제이고, 이는
`MODIFIER`가 "모르는 것"의 이름이었던 과거 결함과 같은 모양이다. 다만 점수표
변경은 blast radius가 넓어 쌍 측정이 필요하므로 별도 작업으로 남긴다.

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
