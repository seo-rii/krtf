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

*실텍스트 회귀* (`run_wild_regression --single`, 20,000문장) — **재측정
대기**. 첫 측정은 아래 "측정이 잡아낸 결함 (1)"의 index 버그가 있는 코드에서
나왔고, 그 수정이 후보 생성을 바꾸므로 그 표는 이 커밋의 수치가 아니다.
같은 스크립트를 두 체크아웃에서 다시 돌려 채운다.

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

**남은 가장 큰 숫자는 M3가 건드리지 않았다.** gold에서 확정해야 할 자리의
**절반이 여전히 확정되지 않는다**(0.50). 미확정 28건은 전부 span을 정확히
맞힌 mention이고, 내역은 이렇다:

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
