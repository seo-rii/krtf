# 한국어 조직 용어 Resolver 프레임워크 기술 스펙

**문서 상태:** Draft
**문서 버전:** 0.3
**작성일:** 2026-08-23
**가칭:** KTRF — Korean Terminology Resolver Framework
**대체 문서:** v0.2 (2026-08-22)

---

## 0. 개정 이력

본 섹션은 changelog 전용이며 규범 효력이 없다. 규범 결정의 유일한 출처는 §56이다.

### v0.3 (2026-08-23)

v0.2 기술 리뷰에서 식별된 스펙 내부 정합성 이슈, 한국어 처리 공백, API·운영 공백을 반영한다.

**정합성·의미론**

1. 문서 규약 신설: 규범 키워드, 요구사항 ID(`REQ-*`), 테스트 추적성 의무를 도입한다(§1). §56을 유일한 규범 결정 목록으로 지정하고 §0은 changelog로 한정한다.
2. Level A의 "결정적 보장"을 지원 변형 카탈로그(§14.7) 기준으로 재정의한다. 카탈로그 내 변형은 conformance 100%(미달 시 release blocker)이고, 99.x% 수치 목표는 실제 corpus 분포에 대한 카탈로그 커버리지 지표로 분리한다(§3.5, §5.2).
3. 모든 품질 지표에 측정 조건(`E2E` / `|mention` / `|candidate`) 표기를 의무화한다(§5.2, §43.1).
4. `link_decision = UNCERTAIN`을 정의하고 mention×link 허용 조합 매트릭스를 추가한다(§7.9, §24.1).
5. `calibrated_probability`를 후보별 marginal 확률로 확정(합산·정규화 금지)하고, set 수준 신뢰도 `set_confidence` 필드를 신설하며, prediction set 산출 방법을 group-conditional split conformal로 명시한다(§7.12, §25).
6. candidate budget의 `max_internal_candidates`를 `max_non_exact_candidates`로 개명하고 exact pool 면제를 불변조건으로 명문화한다(§8 INV-005, §21.3).
7. scope 스키마를 allow/deny 구조로 재정의하고, context trust level별 hard/soft 적용 결정 표를 추가한다(§10.5, §12.4).
8. AliasBinding `normalization_policy`와 AliasFamily `normalization_profile`의 우선순위 규칙을 명시한다(§10.4).
9. 아키텍처를 2-pass conditional retrieval 구조로 수정하고, boundary check와 particle FST의 인터페이스·실행 순서를 정의한다(§9, §15.5, §21.6).

**한국어 처리**

10. 조사 카탈로그를 확장(도, 만, 조차, 마저, 처럼, 보다, 한테, 께서 등)하고 조사 연쇄를 FST 합성으로 처리한다 — 결합형 열거를 금지한다(§16.2).
11. 조사·기관 suffix 동형 충돌(과, 부/부터, 도) 시 복수 분석 보존 규칙을 추가한다(§16.5).
12. 좌측 수식(prefix modifier: 구·신·전·현 등) 파서를 추가한다(§16.6).
13. Latin alias 형태 변형(복수형 s/es, 소유격 's) residual과 boundary 예외 규칙을 추가한다(§16.7).
14. 호환 자모 연쇄 입력의 합성 규칙과 zero-width 문자 처리를 변형 카탈로그에 편입한다(§14.7).
15. fuzzy 비용 규칙의 최소 비용 단일 적용 원칙을 명시한다(§17.2).

**API·운영**

16. 동기 API 입력 상한을 64KB로 축소하고 비동기 Document Resolve API를 신설한다(§27.2, §28).
17. 표준 오류 스키마·코드와 `expected_version` 불일치 동작(`version_policy`)을 정의한다(§27.6, §27.7).
18. Correction API를 신설한다 — tenant calibration, adaptation, 온라인 coverage 모니터링, golden set 축적의 라벨 공급 경로를 계약으로 확정한다(§30).
19. `fast` 실행 모드를 추가한다: RAG query expansion용 저지연 결정적 경로(§26.1).
20. Snapshot 메모리 tier(hot/warm/cold), eviction, adapter GPU 상주 정책과 warm-up API를 정의한다(§32).
21. glossary description 경유 prompt injection 위협 모델과 terminology injection 이스케이프 의무를 추가한다(§47.7, §49.2).
22. Golden set 구축 절차와 annotator 간 일치도(IAA) 기준을 추가한다(§48.6).
23. 마일스톤 개략 공수 추정(참고치)과 Open Questions 섹션을 신설한다(§51, §57).
24. 신규 위험을 등재한다: 조사 연쇄 과생성, correction 오염, cold tenant latency(§52.13–52.15).

### v0.2 (2026-08-22)

문제 범위 3단계 분리(Level A/B/C), mention/link 2축 상태 모델, Entity/AliasFamily/AliasBinding 스키마, UTF-8 byte 내부 offset 기준, budget·degraded 계약, immutable snapshot과 atomic activation, conditional dense retrieval, unseen 평가 세분화 등. 상세는 v0.2 문서 §0을 참조한다.

---

## 1. 문서 규약과 규범 표기

### 1.1 규범 키워드

본 문서에서 다음 표현은 RFC 2119 규범 키워드에 대응한다.

| 표현 | 대응 | 의미 |
|---|---|---|
| ~해야 한다 / ~하여야 한다 | MUST | 절대 요구사항 |
| ~해서는 안 된다 / ~하지 않는다(금지 문맥) | MUST NOT | 절대 금지 |
| ~권장한다 | SHOULD | 정당한 사유 없이 벗어나지 않음 |
| ~권장하지 않는다 | SHOULD NOT | 정당한 사유 없이 하지 않음 |
| ~할 수 있다 | MAY | 선택 사항 |

### 1.2 요구사항 ID

- 검증 가능한 핵심 요구사항에는 `REQ-<영역>-<번호>` ID를 부여한다.
- 영역 코드: `LVL`(보장 수준), `INV`(불변조건), `OFF`(offset), `NRM`(normalization), `BND`(boundary), `TAIL`(tail/prefix), `FUZ`(fuzzy), `LOC`(document-local), `CAND`(candidate), `TRM`(termness), `CAL`(calibration), `API`(API), `COR`(correction), `BUD`(budget), `MEM`(memory), `TEN`(tenant), `SEC`(보안), `EVAL`(평가), `OPS`(운영).
- 모든 REQ ID는 최소 1개의 자동화 테스트에 매핑되어야 한다. 매핑은 부록 D 형식의 추적성 매트릭스(`docs/traceability.yaml`)로 관리하며, 매핑 없는 REQ가 존재하면 CI가 실패해야 한다. (REQ-EVAL-003)

### 1.3 규범/정보 구분

- §8(시스템 불변조건), §56(규범 결정 사항), REQ ID가 부여된 문장, `[normative]` 표시가 있는 표·목록은 규범이다.
- 코드 블록, 수치 예시, YAML config 예시는 별도 표시가 없으면 informative다.
- §4(핵심 설계 원칙)의 산문은 rationale이며, 동일 내용의 규범 효력은 §8과 §56이 가진다.
- v0.2에서 §0·§3·§52에 삼중 중복되던 결정 사항은 v0.3에서 §56 단일 출처로 통합한다.

---

## 2. 개요

KTRF는 특정 조직에서 사용하는 약어, 기관명, 시스템명, 제품명, 부서명, 업무 용어를 문장과 문서에서 탐지하고 조직의 용어 사전(glossary)에 등록된 표준 Entity로 연결하는 경량 Resolver 프레임워크다.

시스템이 다루는 주요 문제는 다음과 같다.

- 한 문장 또는 문서에 여러 용어가 등장하는 경우
- 서로 겹치거나 중첩된 용어
- 동일 alias가 여러 Entity를 의미하는 경우
- 조사, 어미, 직책, 기관종별, 부가 명사가 붙는 한국어 형태 변형
- 구·신·전·현 같은 좌측 수식(prefix modifier)이 붙는 경우
- 띄어쓰기, 하이픈, 대소문자, 전각·반각, Unicode 차이
- 자모 오타, 두벌식 키보드 오타, 영문 입력 모드 오타
- Latin alias의 복수형·소유격 등 형태 변형
- 문서 안에서 새로 정의되는 임시 alias
- glossary에는 Entity가 있지만 해당 표면형 alias가 등록되어 있지 않은 경우
- glossary 자체에 정답 Entity가 없는 경우
- 새로운 조직의 glossary를 모델 재학습 없이 즉시 적용하는 경우

KTRF의 최우선 목표는 **정답 Entity가 후속 단계에서 사용할 수 있는 후보 집합에서 사라지는 일을 최소화하는 것**이다. 후보 생성 단계의 false positive는 일정 수준 허용하되, 비용과 후보 폭발을 통제하는 명시적 budget을 둔다.

하나의 의미로 안전하게 확정하기 어려운 경우에는 임의로 top-1을 강제하지 않고 후보 집합 또는 KB-missing 상태를 보존한다.

---

## 3. 문제 범위와 보장 수준

### 3.1 Level A — Closed-World Surface Resolution

다음 경우를 zero-training 모드에서 결정적으로 지원한다.

- glossary에 등록된 exact alias
- §14.7 지원 변형 카탈로그에 명시된 Unicode/case/spacing/punctuation 변형
- §16.2 조사 카탈로그와 연쇄 규칙으로 설명되는 조사·어미 부착
- glossary의 suffix/extension 정책으로 설명되는 후속 표현
- §16.6 prefix 카탈로그에 명시된 좌측 수식
- 동일 alias에 연결된 모든 등록 sense 보존

예:

```text
사전: 한전 → ORG_KEPCO
입력: 한전에서도
결과: ORG_KEPCO가 후보 집합에 반드시 포함
```

Level A는 KTRF의 필수 제품 계약이다.

- Level A의 결정적 보장 범위는 §14.7 변형 카탈로그와 §16의 조사·suffix·prefix 카탈로그에 **명시된 변형에 한정**된다. (REQ-LVL-001)
- 카탈로그 내 변형에 대한 conformance fixture(§14.8)는 100% 통과해야 하며, 실패 1건은 release blocker다. (REQ-LVL-002)

### 3.2 Level B — Open-Surface Entity Linking

Entity는 glossary에 존재하지만 입력 표면형이 등록 alias가 아닌 경우다.

```text
glossary:
  canonical: 과학기술정보통신부

input:
  과기정통부
```

다음 수단을 사용할 수 있다.

- abbreviation alignment
- Jamo/keyboard fuzzy recovery
- alias-family surface model
- canonical/description dense retrieval
- contextual cross-encoder

Level B는 통계적 성능으로 평가하며 deterministic guarantee를 제공하지 않는다.

### 3.3 Level C — Open-World Term Detection

표면형이 사전에 없고, 해당 문자열이 조직 용어인지 자체를 판단해야 하는 경우다.

```text
문서: 액포 장애 건 확인 부탁드립니다.
```

`액포`가 다음 중 무엇인지 먼저 판단해야 한다.

- 등록 Entity의 미등록 alias
- glossary에 없는 조직 용어
- 일반 단어 또는 우연한 문자열

Level C는 별도 neural mention proposer와 termness classifier를 사용하는 실험적 기능으로 취급한다. 초기 기본 런타임에서는 feature flag로 비활성화할 수 있어야 한다.

### 3.4 KB-Missing

정답 개념 자체가 현재 tenant glossary에 없는 경우다.

```text
mention_decision = TERM
link_decision = KB_MISSING
```

이는 일반 단어를 뜻하는 `NON_TERM`과 구분한다.

### 3.5 결정적 보장과 통계 목표의 관계

v0.2에서 "결정적 지원"과 "99.x% 목표"가 병기되어 해석 충돌이 있었다. v0.3에서 두 개념을 다음과 같이 분리한다.

1. **결정적 보장(conformance):** 카탈로그에 명시된 변형은 항상 성공해야 한다. 측정 단위는 비율이 아니라 실패 건수이며, 목표는 0건이다. conformance fixture는 glossary와 카탈로그로부터 결정적으로 생성된다(§14.8).
2. **분포 커버리지(통계 목표):** §5.2의 99.x% 수치는 실제 corpus에서 발생하는 표현 중 카탈로그가 설명하는 비율을 측정한다. 미달의 원인은 규칙 실패가 아니라 카탈로그 미포함 표현(미등록 조사, 신조 표현, 예상 밖 변형)의 자연 발생이다.
3. 분포 커버리지 미달은 카탈로그·규칙 확장의 우선순위 신호로 사용하고, conformance 실패는 구현 결함으로 취급한다. 두 지표를 하나의 수치로 합산 보고해서는 안 된다. (REQ-LVL-003)

---
## 4. 핵심 설계 원칙

본 섹션은 rationale(informative)이며 규범 효력은 §8, §56에 있다.

### 4.1 canonical 문자열을 생성하지 않는다

모델은 표준명을 자유 생성하지 않는다. glossary에 등록된 Entity ID를 선택하고, canonical name, description, type, relation의 source of truth는 항상 활성화된 glossary snapshot이다.

```text
잘못된 방향: 한전 → "한국전력공사" 생성
올바른 방향: 한전 → ORG_KEPCO, ORG_KEPCO → 한국전력공사
```

### 4.2 문장당 단일 라벨이 아니라 mention 집합을 예측한다

```text
입력: 한전KDN은 AP 장애 내용을 QMS에 등록했다.

한전KDN → ORG_KEPCO_KDN
AP      → NETWORK_ACCESS_POINT 또는 다른 AP sense 집합
QMS     → SYSTEM_QUALITY_MANAGEMENT
```

각 mention은 독립된 후보 집합과 link decision을 가진다.

### 4.3 Surface Resolution과 Sense Resolution을 분리한다

`AP`라는 표면형을 찾는 문제와 문맥에서 `AP`의 의미를 선택하는 문제를 분리한다.

```text
Surface resolver
AP / A.P. / ＡＰ / ap / AP에서
    ↓
ALIAS_FAMILY_AP

Sense resolver
ALIAS_FAMILY_AP
    ├─ NETWORK_ACCESS_POINT
    ├─ FINANCE_ACCOUNTS_PAYABLE
    └─ WORKFLOW_APPROVAL_PROCESS
```

표기 복구 모델이 조직의 고정 Entity ID를 외우도록 만들지 않는다.

### 4.4 후보를 조기에 제거하지 않되 무제한 유지하지 않는다

미탐은 `mention_miss`, `candidate_miss`, `budget_miss`, `ranking_miss`, `commit_miss`로 구분한다. 후보 생성은 여러 채널의 합집합으로 구성하되, 각 stage는 명시적 budget을 가지며 잘림이 발생하면 응답과 trace에 기록한다.

### 4.5 새 조직은 glossary compile만으로 Level A를 즉시 사용할 수 있어야 한다

새 tenant는 모델 재학습 없이 exact/normalized match, morphology/tail/prefix parsing, alias ambiguity 보존, 기본 global sense resolver, 기본 conservative calibration을 사용할 수 있어야 한다. Level B/C 성능은 glossary의 description과 조직별 문맥 데이터의 품질에 따라 달라진다.

### 4.6 검색은 공격적으로, 확정은 보수적으로 수행한다

RAG/query expansion에는 높은 recall을 우선한 `fast`/`aggressive` 결과를, 최종 답변·canonical 표시·자동화에는 높은 precision의 `commit` 결과를 제공한다. 확정 단계에서 충분한 근거가 없으면 AMBIGUOUS 또는 KB_MISSING을 유지한다.

### 4.7 symbolic matcher는 neural model 이후에도 제거하지 않는다

Exact alias와 deterministic transformation은 재현성과 회귀 보장을 위해 항상 독립 경로로 유지한다.

### 4.8 모든 결과는 snapshot과 provenance에 고정된다

각 요청(동기·비동기 공통)은 처리 시작 시 하나의 immutable runtime snapshot을 pin한다. 하나의 요청 안에서 glossary, vector index, normalizer, calibrator 버전이 섞여서는 안 된다.

---

## 5. 목표

### 5.1 기능 목표

- 복수 mention 탐지, overlapping/nested span 지원
- 동일 alias 다의성 해소
- 조사, 어미, 기관 suffix, residual, prefix modifier 처리
- 한국어·영어·숫자 혼합 alias 및 Latin 형태 변형
- Unicode, case, spacing, punctuation 변형 (카탈로그 기반)
- Jamo 및 keyboard 오타 복구
- 문서 내부 임시 alias
- Level A zero-training 동작
- Level B unseen-surface retrieval, 선택적 Level C unknown mention 탐지
- immutable glossary hot reload, tenant별 완전한 candidate 격리
- 온라인 생성형 LLM 호출 없이 동작
- fast / aggressive / commit 실행 모드 제공
- 동기·비동기(장문) API 제공
- 원문 offset과 normalization provenance 보존
- correction 수집과 승인 기반 adaptation 경로

### 5.2 품질 목표

모든 지표는 측정 조건을 명시해야 한다(§43.1). 표기: `E2E`(원문 입력 기준 전체 파이프라인), `|mention`(gold core span이 proposal된 mention 조건부), `|candidate`(gold Entity가 후보 집합에 포함된 조건부), `|commit`(해당 상태로 commit된 것 중).

초기 수치는 조직별 golden set으로 보정하되 release gate는 단일 점 추정치만 사용하지 않는다.

| 지표 | 조건 | 초기 목표 |
|---|---|---:|
| Level A conformance (카탈로그 내 변형) | fixture | 100% (미달 = release blocker) |
| Level A core-span recall | E2E | 99.5% 이상 |
| Candidate Recall@50 | \|mention | 99.7% 이상 |
| E2E gold-in-candidates (파생 참고치) | E2E | 99.2% 이상 |
| All-mentions sentence recall | E2E | 98.0% 이상 |
| `RESOLVED` precision | \|commit | 98.0% 이상 |
| `RESOLVED` coverage | E2E | 제품별 최소값 별도 정의 |
| 조사·어미 카탈로그 분포 커버리지 | E2E | 99.0% 이상 |
| 1자모 오타 candidate recall | \|mention | 98.0% 이상 |
| 영문 입력 모드 오타 candidate recall | \|mention | 95.0% 이상 |
| `UE-canonical-only` Candidate Recall@50 | \|mention | 95.0% 이상을 목표로 실험 |
| Prediction-set empirical coverage | \|commit | 설정 목표(1-α)와 오차 범위 내 |

각 핵심 지표는 가능한 경우 Wilson 95% confidence interval 또는 bootstrap interval을 함께 보고한다.

다음 지표는 반드시 쌍으로 평가한다.

```text
RESOLVED precision + RESOLVED coverage
Prediction-set coverage + prediction-set size
Mention recall + proposal budget
Candidate recall + candidate count/cross-encoder pair count
```

### 5.3 성능 목표

- 온라인 생성형 LLM 호출 없음
- glossary 100,000 Entity 이상 지원
- exact matcher는 입력 길이에 준선형으로 동작
- CPU-only deterministic mode 제공
- 8GB 이하 GPU에서도 기본 neural runtime 구성 가능
- cross-encoder는 조건부 실행
- 장문 문서는 비동기 API의 chunk 처리
- runtime budget 초과 시 OOM 대신 degraded 결과 반환
- fast 모드는 결정적 경로만으로 저지연 동작

구체적인 latency SLO는 기준 하드웨어별 benchmark 문서에서 정의한다(§53, OQ-002).

---

## 6. 비목표

초기 버전의 비목표는 다음과 같다.

- glossary에 없는 표준 명칭을 생성형 모델로 만들어 확정
- 범용 한국어 NER 대체
- 조직과 무관한 일반 고유명사 전체 인식
- 모든 unknown surface를 반드시 기존 Entity로 연결
- 모든 candidate를 하나의 Entity로 강제 연결
- 형태소 분석기 하나의 결과에 의존
- Resolver 결과를 검증 없이 원문 canonical로 직접 치환
- tenant별 full model fine-tuning을 필수 온보딩 절차로 사용
- 초기 버전에서 end-to-end neural resolver 하나로 모든 기능 통합
- correction의 무검증 자동 반영

---

## 7. 주요 용어와 상태 모델

### 7.1 Entity

조직 glossary에서 관리되는 표준 개념이다.

```text
entity_id: ORG_KEPCO
canonical: 한국전력공사
```

### 7.2 Alias

Entity를 지칭할 수 있는 원문 표면 문자열이다. 예: 한국전력, 한전, KEPCO.

### 7.3 Alias Family

표기만 다르고 같은 기본 표면형으로 취급할 수 있는 alias 집합이다. 예: AP, A.P., ＡＰ, ap.

Alias family는 Entity sense와 분리한다. 하나의 family가 여러 Entity에 연결될 수 있다. Family의 변형 집합은 목록 열거가 아니라 `representative + normalization profile`에서 유도된다(§10.3).

### 7.4 Alias Binding

특정 alias family와 특정 Entity의 연결 관계다. Alias별 boundary, normalization, fuzzy, scope, provenance 정책은 AliasBinding에 둔다.

### 7.5 Mention

입력 문서에서 조직 용어일 가능성이 있는 실제 문자 구간이다. Mention은 최소 다음 span을 구분할 수 있다.

- `core_span`: Entity surface의 핵심 영역
- `full_span`: prefix/particle/residual까지 포함한 분석 영역
- `matched_segments`: 공백·구두점 완화로 분리된 원문 구간 목록

### 7.6 Prefix / Residual

- `prefix`: core 앞의 좌측 수식(구, 전, 현 등). core span에 포함하지 않는다(§16.6).
- `residual`: 기본 Entity에 포함되지 않는 후속 표현.

```text
전 한전서울본부에서도

prefix:   전 (TEMPORAL)
core:     한전
residual: 서울본부
particle: 에서도
```

### 7.7 Entity Extension

기본 Entity와 suffix가 결합되어 glossary의 별도 Entity가 되는 경우다(예: 서울대 + 병원 → 서울대학교병원). 자유 heuristic으로 확정하지 않고 `EntityRelation` 또는 명시적 alias binding을 우선한다.

### 7.8 Mention Decision

span 자체가 조직 용어인지에 대한 판단이다.

```text
TERM
NON_TERM
UNCERTAIN
```

### 7.9 Link Decision

TERM 또는 UNCERTAIN mention을 현재 glossary에 연결하는 결과다.

- `RESOLVED`: 단일 Entity가 commit 조건(§25.6)을 충족한다.
- `AMBIGUOUS`: termness는 신뢰되나 prediction set에 2개 이상의 후보(Entity 또는 KB_MISSING)가 남는다. "정답이 이 set 안에 있다"는 calibrated 주장(set_confidence)을 동반한다.
- `KB_MISSING`: term일 확률이 높으나 현재 glossary의 어떤 Entity와도 충분한 호환 근거가 없다.
- `UNCERTAIN`: prediction set 수준의 보장 자체를 주장할 수 없는 상태. 발생 조건: (a) mention_decision이 UNCERTAIN이어서 termness가 불확실, (b) 해당 calibration 그룹의 표본 부족으로 coverage 보장 불가(§25.4), (c) degraded 처리로 후보 생성이 불완전(§27.8). AMBIGUOUS와의 차이는 set-level 보장 주장의 유무다.

허용되는 상태 조합은 §24.1의 매트릭스를 따른다. mention_decision이 UNCERTAIN인 mention은 RESOLVED로 commit해서는 안 된다. (REQ-TRM-001)

### 7.10 Prediction Set

하나의 mention에 대해 commit 시점에도 남겨 둘 Entity 및 KB-missing 후보 집합이다. 산출 방법은 §25를 따른다.

### 7.11 Runtime Snapshot

한 요청에서 사용하는 다음 artifact의 immutable 조합이다.

```text
glossary / exact·fuzzy index / normalization rules / morphology rules
entity vectors / model bundle / calibrator / adapter / runtime policy
```

### 7.12 확률 의미론 [normative]

API가 노출하는 점수·확률 필드는 다음 의미를 가진다.

- `ranking_score`: 후보 간 순위 비교용 비정규 점수. 확률로 해석해서는 안 된다.
- `calibrated_probability`: **후보별 marginal 확률**. 해당 후보가 정답일 calibrated 추정 P(정답=후보 | mention, context)이며, prediction set 내에서 정규화된 posterior가 아니다. 후보 간 합이 1을 초과하거나 미달할 수 있고, 클라이언트는 이 값을 합산·정규화해서 사용해서는 안 된다. (REQ-CAL-001)
- `KB_MISSING` 후보의 `calibrated_probability`: 정답 Entity가 현재 glossary에 존재하지 않을 calibrated 추정 P(KB-missing | mention, context).
- `set_confidence`: prediction set 수준의 목표 신뢰도(1-α). "정답이 이 set에 포함될 확률이 목표상 1-α 이상"이라는 conformal 주장이며(§25.3), 후보별 marginal과는 별개 개념이다.

---

## 8. 시스템 불변조건

구현체는 다음 invariant를 지켜야 한다. 각 항목은 규범이며 부록 D의 추적성 매트릭스에 매핑된다.

| ID | 불변조건 |
|---|---|
| INV-001 | canonical 문자열은 활성 glossary snapshot에서만 읽는다. |
| INV-002 | `text[codepoint_start:codepoint_end]`는 응답 `surface`와 일치해야 한다. |
| INV-003 | 내부 UTF-8 byte span도 같은 원문 구간을 가리켜야 한다. |
| INV-004 | exact alias에 연결된 모든 sense는 내부 exact candidate pool에 들어간다. |
| INV-005 | 어떤 budget 값(`max_non_exact_candidates` 포함)도 exact pool을 자르는 데 사용해서는 안 된다. exact pool이 안전 한계를 넘는 경우는 §21.5의 절차만 허용된다. |
| INV-006 | 한 요청은 하나의 `snapshot_id`만 사용한다. |
| INV-007 | 다른 tenant의 Entity는 candidate pool, trace, cache에서 노출되어서는 안 된다. |
| INV-008 | document-local alias는 문서/session scope를 벗어나 저장되지 않는다. |
| INV-009 | document-local alias는 global alias candidate를 제거하지 못한다. |
| INV-010 | fuzzy/neural 결과가 exact result를 overwrite하지 않는다. |
| INV-011 | score와 probability를 동일한 필드로 취급하지 않는다. |
| INV-012 | normalization은 원문을 파괴하지 않으며 모든 match는 원문으로 역매핑 가능해야 한다. |
| INV-013 | truncation, timeout, budget exhaustion은 `degraded=true`로 노출한다. |
| INV-014 | compile 실패나 activation 실패 시 이전 snapshot을 그대로 유지한다. |
| INV-015 | 모델/벡터/normalizer/calibrator compatibility mismatch가 있으면 activation을 거부한다. |
| INV-016 | mention_decision이 UNCERTAIN인 mention은 link_decision RESOLVED로 commit되지 않는다. |
| INV-017 | 비동기 job의 모든 chunk는 시작 시 pin된 동일 snapshot을 사용한다. |
| INV-018 | correction 데이터는 승인(ACCEPTED) 전에 glossary, 모델, calibrator, golden set에 반영되지 않는다. |
| INV-019 | `calibrated_probability`는 후보별 marginal로 계산·문서화되며 prediction set 내 정규화를 하지 않는다. |

---
## 9. 전체 아키텍처

v0.2 대비 두 가지가 수정되었다: (1) conditional retrieval을 명시적 2-pass 구조로 표현, (2) boundary check와 particle FST의 공유 관계 명시.

```text
Authenticated Request
        │
        ▼
Tenant/Glossary Authorization
        │
        ▼
Immutable Snapshot Pin
        │
        ▼
Safe Canonical Normalization
+ raw offset provenance
        │
        ├──────────────────────────┐
        ▼                          ▼
Exact Alias Match           Surface Window Extraction
+ boundary check                   │
   │        ▲                      ├─ spacing/punctuation channel
   │        │                      ├─ Jamo fuzzy
   │   Particle/Tail FST           ├─ keyboard recovery
   │   (read-only 공유,            └─ neural proposal (optional)
   │    prefix-accept 질의)               │
   └───────────────┬──────────────────────┘
                   ▼
     Prefix / Core / Residual / Particle Parser
                   ▼
            Mention Proposal Graph
                   ▼
     Candidate Union — Pass 1
     (exact ∪ normalized ∪ morphology
      ∪ jamo ∪ keyboard ∪ doc-local)
                   ▼
       Preliminary Ranking + Fusion
                   │
        confidence 충분? ──────── 예 ──────┐
                   │                       │
                  아니오                    │
                   ▼                       │
     Conditional Retrieval (1회 한정)      │
     (dense ∪ abbreviation alignment)     │
                   ▼                       │
     Candidate Union — Pass 2             │
     (Pass 1 후보 보존 + 추가)             │
                   ▼                       │
        Final Ranking + Fusion ◄──────────┘
                   ▼
          Termness / KB-Missing
                   ▼
       Calibration + Prediction Set
                   ▼
      Mention Graph Primary Selection
                   ▼
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼
  Fast View   Aggressive View  Commit View
```

핵심 원칙:

- deterministic path는 항상 독립적으로 동작하고 neural module은 recall 또는 sense resolution을 보완한다.
- Pass 2(conditional retrieval)는 요청당 최대 1회 실행하며(§21.6), Pass 1의 후보 — 특히 exact 후보 — 를 제거하거나 대체해서는 안 된다. (REQ-CAND-004)
- Particle/Tail FST는 snapshot artifact의 read-only 공유 컴포넌트다. boundary check는 FST에 접두 수락(prefix-accept) 질의만 수행하고, 완전한 분해는 이후 parser 단계가 수행한다. 컴포넌트 간 순환 의존은 없으며 데이터 의존만 존재한다(§15.5).
- `fast` 모드는 Pass 1의 결정적 채널까지만 실행하고 ranking/calibration을 생략한다(§26.1).

---

## 10. Glossary 스키마

### 10.1 최상위 구조

```yaml
glossary_id: organization-a
version: 2026-08-23.1
schema_version: "3"

entities: []
alias_families: []
alias_bindings: []
entity_relations: []
normalization_profiles: []
policies: {}
```

`schema_version: "2"`(v0.2) glossary는 §10.5의 scope 호환 규칙에 따라 읽을 수 있으나, compiler는 마이그레이션 경고를 출력해야 한다.

### 10.2 Entity

```yaml
entities:
  - entity_id: NETWORK_ACCESS_POINT
    canonical: Access Point
    language: en
    type_ids: [NETWORK_DEVICE]
    domain_ids: [NETWORK, INFRASTRUCTURE]
    description: 무선 단말을 유선 네트워크에 연결하는 네트워크 장비
    examples:
      - 무선 AP 장애를 확인한다.
    valid_from: null
    valid_to: null
    metadata: {}
    provenance:
      source: admin
      source_version: "2026-08-23"
```

최소 필수 필드는 `entity_id`, `canonical`이다. 다의어 resolution을 사용하려면 `description`, `type_ids`, `domain_ids`, `examples` 중 하나 이상의 구분 신호를 권장한다.

description·examples는 downstream LLM 프롬프트에 주입될 수 있으므로 §47.7의 content lint 대상이다.

### 10.3 Alias Family

```yaml
alias_families:
  - family_id: FAMILY_AP
    representative: AP
    normalization_profile: latin_acronym
```

Family의 표면 변형 집합은 `representative`에 `normalization_profile`을 적용해 유도한다. 변형 문자열을 열거하지 않는다.

### 10.4 Alias Binding

```yaml
alias_bindings:
  - alias_id: AP_NETWORK
    family_id: FAMILY_AP
    entity_id: NETWORK_ACCESS_POINT
    surface: AP
    kind: abbreviation

    boundary_policy:
      left: latin_token_boundary
      right: particle_or_token_boundary
      allow_inside_latin_run: false

    normalization_policy:            # family profile의 필드 단위 override
      case_sensitive: false

    fuzzy_policy:
      enabled: false
      keyboard_recovery: true
      max_edit_cost: 0.0

    scope:
      allow:
        departments: [network]
        projects: []
      deny:
        departments: []
        projects: []

    provenance:
      source: glossary
```

**Normalization 우선순위 [normative]:** 적용 순서는 `AliasBinding.normalization_policy` > `AliasFamily.normalization_profile` > tenant 기본 profile > 시스템 기본 profile이다. Binding의 policy는 profile 전체를 대체하지 않고 명시된 필드만 override한다. (REQ-NRM-001)

AliasBinding은 surface, family_id, entity_id, kind, boundary policy, normalization policy(override), fuzzy policy, scope, valid_from/valid_to(선택), provenance를 1급 필드로 가진다.

### 10.5 Scope 모델 [normative]

```yaml
scope:
  allow:
    departments: []     # 비어 있으면 전 범위 허용
    projects: []
  deny:
    departments: []
    projects: []
```

- `allow`가 비어 있으면 전 범위 허용을 의미한다.
- `allow` 불일치는 어떤 context trust level에서도 hard filter가 아니며 soft feature(`scope_match`)로만 반영한다. 사전 오류나 조직 개편 시 recall 붕괴를 막기 위함이다. (REQ-TEN-003)
- `deny` 일치는 §12.4의 결정 표에 따라, 서버가 검증한 신뢰 수준(SERVER_VERIFIED, AUTH_CLAIM)의 context에서만 hard filter로 적용한다. 그 외 신뢰 수준에서는 soft 감점으로만 반영한다. (REQ-TEN-004)
- 요청에 해당 context 필드가 없으면 allow/deny 판정 자체를 하지 않는다(중립).
- v0.2 호환: 구형 `scope: {departments: [...], projects: [...]}`는 `scope.allow.*`로 해석한다.

### 10.6 짧은 alias 기본 fuzzy 정책

| 정규화 후 길이 | 기본 정책 |
|---:|---|
| 1 | 일반 edit fuzzy 비활성화 |
| 2 | 일반 edit 비활성화, width/case/명시적 keyboard 복구만 허용 |
| 3~4 | 매우 낮은 edit cost만 허용 |
| 5 이상 | 길이 정규화 weighted edit 사용 가능 |

Tenant 또는 AliasBinding이 명시적으로 override할 수 있다.

### 10.7 Entity Relation

```yaml
entity_relations:
  - relation_id: REL_SNU_HOSPITAL_PARENT
    source_entity_id: ORG_SNU_HOSPITAL
    relation_type: SUBSIDIARY_OR_UNIT_OF
    target_entity_id: ORG_SNU

  - relation_id: REL_SNU_COMPOSE_HOSPITAL
    source_entity_id: ORG_SNU
    relation_type: COMPOSES_TO
    surface_suffix: 병원
    target_entity_id: ORG_SNU_HOSPITAL
```

### 10.8 Strict Validation

Compiler의 strict mode는 다음을 오류 또는 강한 경고로 처리한다.

- 중복 Entity ID
- 존재하지 않는 Entity를 참조하는 AliasBinding
- 동일 normalized alias에 다수 sense가 있으나 구분 정보가 전혀 없음
- 지나치게 많은 sense를 가진 짧은 alias
- boundary policy가 없는 위험한 1~2자 Latin alias
- invalid relation cycle 또는 dangling reference
- canonical 빈 문자열
- Unicode normalization 후 alias collision
- 동일 alias binding의 상충하는 유효기간
- allow와 deny에 동일 값이 중복 등재된 scope
- description/examples의 content lint 경고(§47.7)

---

## 11. Glossary Compiler와 Artifact Bundle

### 11.1 Compiler 출력

```text
compiled-glossary/
├── manifest.json
├── entities.bin
├── alias-families.bin
├── alias-bindings.bin
├── exact-index.bin
├── fuzzy-index.bin
├── entity-relations.bin
├── morphology-rules.bin        # particle/suffix/prefix FST 포함
├── normalization-rules.bin
├── entity-vectors.bin          # optional
├── conformance-fixtures.bin    # §14.8 자동 생성 fixture
└── diagnostics.json
```

모든 `.bin` artifact는 mmap 친화적 포맷이어야 한다 — 로드 시 전체 역직렬화 없이 페이지 단위 접근이 가능해야 하며, 이는 §32의 tier 상주 정책의 전제다. (REQ-MEM-001)

### 11.2 Manifest

```json
{
  "schema_version": "3",
  "glossary_id": "organization-a",
  "glossary_version": "2026-08-23.1",
  "compatibility_id": "ktrf-bundle-v3",

  "normalizer_hash": "sha256:...",
  "morphology_rules_hash": "sha256:...",
  "surface_error_model_hash": "sha256:...",

  "entity_encoder_hash": "sha256:...",
  "context_encoder_hash": "sha256:...",
  "cross_encoder_hash": "sha256:...",
  "calibrator_hash": "sha256:...",

  "vector_dimension": 384,
  "vector_dtype": "float16",
  "index_type": "flat_ip",

  "entities_hash": "sha256:...",
  "aliases_hash": "sha256:...",
  "conformance_fixtures_hash": "sha256:...",
  "artifact_hashes": {}
}
```

Entity vector가 없는 Level A-only bundle에서는 encoder/vector 관련 필드를 null로 둘 수 있다.

### 11.3 Compatibility Contract

다음 변경은 기존 vector/index/calibrator를 자동 재사용해서는 안 된다.

- entity encoder 변경
- vector dimension 변경
- similarity metric 변경
- canonical normalization 변경
- alias family normalization 변경
- ranking feature schema 변경
- candidate generator 동작 변경
- calibrator 입력 score 정의 변경
- 조사·suffix·prefix 카탈로그(morphology rules) 변경 시 conformance fixture 재생성

Activation 시 `compatibility_id`와 각 hash를 검증한다.

### 11.4 Atomic Activation

```text
1. 새 bundle을 별도 위치에 완전히 빌드
2. checksum/schema/compatibility 검증
3. conformance fixture 실행 (100% 통과 필수)
4. index와 model artifact 사전 load 검증
5. immutable SnapshotHandle 생성
6. tenant registry의 active pointer를 atomic swap
7. 새 요청부터 새 snapshot pin
8. 기존 요청은 이전 snapshot 계속 사용
9. 이전 snapshot refcount가 0이면 회수
```

Activation 실패 시 현재 active snapshot은 변경되지 않는다.

---

## 12. Tenant 격리와 인증

### 12.1 Tenant 결정

Tenant는 클라이언트가 자유롭게 전달하는 `glossary_id`로 결정하지 않는다.

```text
인증 토큰 / mTLS / trusted gateway
        ↓
resolved tenant_id
        ↓
허용된 glossary_id/version 확인
```

요청에 `glossary_id`가 있더라도 인증된 tenant scope 안에서만 선택할 수 있다. (REQ-TEN-001)

### 12.2 Tenant별 분리 대상

glossary artifact, exact/fuzzy index, entity vector index, calibrator, 조직 adapter, document-local cache namespace, runtime statistics, correction data와 correction queue, audit log scope.

공유 base model을 사용하더라도 다른 tenant Entity가 candidate로 유입되어서는 안 된다. (REQ-TEN-002)

### 12.3 Cache Key

캐시 키에는 최소 다음이 포함되어야 한다.

```text
tenant_id
glossary_version
model_bundle_version
normalization_version
context_policy_version
request mode
```

Tenant ID가 누락된 global candidate cache는 금지한다.

### 12.4 Context Trust와 Scope 적용 [normative]

`department`, `project`, `role` 같은 context metadata는 다음 신뢰 수준을 구분한다.

```text
SERVER_VERIFIED
AUTH_CLAIM
APPLICATION_VERIFIED
USER_PROVIDED
UNTRUSTED_DOCUMENT
```

Scope(§10.5)와 trust level의 결합은 다음 표를 따른다.

| context trust | allow 불일치 | deny 일치 |
|---|---|---|
| SERVER_VERIFIED | soft 감점 (후보 제거 금지) | **hard 제거** |
| AUTH_CLAIM | soft 감점 | **hard 제거** |
| APPLICATION_VERIFIED | soft 감점 | soft 강한 감점 (제거 금지) |
| USER_PROVIDED | soft 감점 | soft 감점 |
| UNTRUSTED_DOCUMENT | 무시 또는 미세 감점 | 무시 |

- hard 제거는 §23.1 validity filter 단계에서 수행하고 trace에 사유를 기록한다.
- 서버가 검증하지 않은 metadata만으로 global candidate를 hard-filter해서는 안 된다는 v0.2 원칙은 유지되며, 위 표는 그 원칙의 구체화다.

---

## 13. 문자열, Unicode, Offset 계약

### 13.1 내부 기준

내부 canonical span 식별자는 UTF-8 byte offset의 반개구간 `[start, end)`을 사용한다. (REQ-OFF-001)

이유: Rust/C++ runtime core에서 안정적으로 사용 가능하고, raw byte provenance 보존이 쉬우며, combining sequence와 UTF-16 surrogate pair의 혼동을 피할 수 있다.

### 13.2 API Offset

API는 기본적으로 byte / codepoint / utf16 세 좌표를 함께 반환한다.

기준 예 (`한전 AP 점검`):

```json
{
  "surface": "AP",
  "span": {
    "byte":      {"start": 7, "end": 9},
    "codepoint": {"start": 3, "end": 5},
    "utf16":     {"start": 3, "end": 5}
  }
}
```

- `byte`: UTF-8 byte offset (한글 1음절 = 3 byte)
- `codepoint`: Unicode scalar 인덱스
- `utf16`: UTF-16 code unit 인덱스. BMP 문자만 있으면 codepoint와 같고, 보충 평면 문자(emoji 등)가 앞에 있으면 달라진다.

### 13.3 Offset Invariant

모든 API fixture와 teacher data에 다음 검증을 수행한다. (REQ-OFF-002)

```python
assert text[codepoint_start:codepoint_end] == surface
```

위 예시는 명세를 설명하기 위한 코드이며 실행 결과가 아니다. 별도로 byte/UTF-16 변환 round-trip도 검증한다. (REQ-OFF-003)

### 13.4 기준 예제

입력:

```text
한전KDN은 AP 장애 내용을 QMS에 등록했다.
```

Unicode code point 기준:

```text
한전KDN  [0, 5)
AP       [7, 9)
QMS      [17, 20)
```

UTF-8 byte 기준:

```text
한전KDN  [0, 9)
AP       [13, 15)
QMS      [33, 36)
```

### 13.5 Matched Segments

공백이나 punctuation tolerant match는 raw cover span만으로는 정보 손실이 생길 수 있다.

```json
{
  "raw_cover_span": {
    "codepoint": {"start": 10, "end": 18}
  },
  "matched_segments": [
    {"start": 10, "end": 12},
    {"start": 13, "end": 18}
  ]
}
```

### 13.6 Malformed 입력

API boundary에 malformed UTF-8이 들어오면 수리를 시도하지 않고 `INVALID_UTF8` 오류(§27.6)를 반환한다. 자동 수리는 offset 계약을 침식하므로 금지한다. (REQ-OFF-004)

---
## 14. Normalization과 Provenance

### 14.1 기본 원칙

원문을 하나의 공격적인 normalized string으로 덮어쓰지 않는다. 다음 두 층을 분리한다.

1. 안전한 canonical stream
2. 목적별 tolerant search channel

### 14.2 Canonical Stream

기본 canonical stream은 보수적으로 구성한다.

```text
raw
→ Unicode validation
→ NFC
→ allowlist 기반 width folding
→ 호환 자모 연쇄의 조건부 음절 합성 (T-08)
→ allowlist 기반 zero-width 문자 제거 (gap provenance 기록)
→ alias policy에 따른 Latin case handling
```

전체 문자열에 무조건적인 NFKC를 적용하지 않는다. compatibility folding은 KTRF가 허용한 문자 범위와 profile로 제한한다.

### 14.3 독립 Search Channel

다음 변형은 데카르트 곱으로 모든 문자열을 materialize하지 않는다.

```text
canonical exact channel
spacing-tolerant channel
punctuation-tolerant channel
Jamo channel
keyboard channel
```

필요한 matcher가 자신의 channel representation을 사용한다.

### 14.4 MappedUnit

정규화 결과 각 unit은 raw provenance를 가져야 한다.

```text
MappedUnit {
    normalized_symbol
    raw_start_byte
    raw_end_byte
    transform_id        # §14.7 카탈로그의 T-ID
    transform_cost
}
```

삭제된 공백, punctuation, zero-width 문자 역시 gap metadata로 추적할 수 있어야 한다.

### 14.5 금지 사항

- normalization 결과만 저장하고 raw text를 버리지 않는다.
- 모든 가능한 spacing/punctuation/Jamo 조합을 문자열 배열로 생성하지 않는다.
- normalization cost가 높은 경로를 exact match와 같은 신뢰도로 처리하지 않는다.

### 14.6 기본 Normalization Profile [normative]

다음 5종은 시스템 기본 profile이며 정의는 규범이다. tenant는 추가 profile을 정의할 수 있으나 기본 profile의 의미를 변경해서는 안 된다. (REQ-NRM-002)

```yaml
normalization_profiles:
  - id: latin_acronym          # AP, QMS, KEPCO
    nfc: true
    width_fold: ascii_compat
    case_fold: ascii
    ignore_punctuation: [".", "-"]
    spacing_mode: strict
    latin_morph: false

  - id: latin_word             # Kubernetes, Salesforce
    nfc: true
    width_fold: ascii_compat
    case_fold: ascii
    ignore_punctuation: ["-"]
    spacing_mode: strict
    latin_morph: true          # 복수형/소유격 tail 허용 (§16.7)

  - id: korean_org_name        # 한국전력공사, 서울대학교병원
    nfc: true
    width_fold: ascii_compat
    case_fold: none
    ignore_punctuation: ["-", "·"]
    spacing_mode: tolerant
    latin_morph: false

  - id: korean_term            # 결재선, 품의서
    nfc: true
    width_fold: ascii_compat
    case_fold: none
    ignore_punctuation: []
    spacing_mode: strict
    latin_morph: false

  - id: mixed_alnum            # 한전KDN, 5G특화망, R&D본부
    nfc: true
    width_fold: ascii_compat
    case_fold: ascii
    ignore_punctuation: ["-", "&", "/"]
    spacing_mode: tolerant
    latin_morph: false
```

### 14.7 지원 변형 카탈로그 [normative]

Level A 결정적 보장(§3.1)의 실체는 아래 변형 클래스 목록이다. 각 변형에는 transform ID를 부여하며, MappedUnit과 conformance fixture가 이 ID를 참조한다.

| ID | 변형 클래스 | 조건 |
|---|---|---|
| T-01 | NFC 정규화 | 항상 |
| T-02 | 전각·반각 변환 | ascii_compat allowlist 범위 |
| T-03 | Latin 대소문자 | profile `case_fold` |
| T-04 | 구두점 삽입·삭제 | profile `ignore_punctuation` 목록 내 |
| T-05 | 공백 삽입·삭제 | profile `spacing_mode: tolerant` |
| T-06 | 조사 부착 | §16.2 조사 카탈로그 + 연쇄 규칙 |
| T-07 | 기관 suffix / extension | §16.3 suffix 카탈로그 + EntityRelation |
| T-08 | 호환 자모 연쇄 음절 합성 | U+3131–U+318E 연쇄가 완전한 음절로 합성 가능한 경우. 합성 후 provenance 기록. 합성 불가 잔여 자모는 canonical stream에 보존하고 Jamo channel에서만 처리 |
| T-09 | zero-width 문자 제거 | allowlist(ZWSP, ZWNJ, ZWJ, BOM) 내. gap provenance 기록 |
| T-10 | prefix modifier 분리 | §16.6 prefix 카탈로그 |
| T-11 | Latin 형태 tail 분리 | profile `latin_morph: true`, §16.7 |

카탈로그 밖의 변형(자모 오타, 키보드 오타, 미등록 조사, 임의 약어)은 Level A 보장 대상이 아니며 fuzzy/dense 등 통계 경로(Level B)로 처리한다. (REQ-NRM-003)

### 14.8 Conformance Fixture Suite [normative]

- Compiler는 활성 glossary의 모든 AliasBinding에 대해, 해당 binding의 profile·boundary·카탈로그가 허용하는 변형을 결정적으로 생성한 fixture(`conformance-fixtures.bin`)를 출력해야 한다. (REQ-NRM-004)
- Fixture의 각 항목은 (입력 문자열, 기대 raw span, 기대 entity_id 포함 여부)로 구성된다.
- CI와 activation 절차(§11.4)에서 fixture는 100% 통과해야 하며, 실패는 release/activation blocker다. (REQ-NRM-005)
- 조합 폭발 통제: fixture 생성은 변형 클래스당 대표 표본 + 무작위 시드 고정 샘플로 제한할 수 있되, 조사 카탈로그의 단일 조사 전수와 연쇄 depth 2 대표 조합은 반드시 포함한다. (REQ-NRM-006)

---

## 15. Exact Alias Matcher와 경계 정책

### 15.1 Exact Index

Trie 또는 Aho-Corasick 계열을 사용한다.

요구사항: 여러 alias 동시 검색, overlapping match 유지, canonical channel과 허용된 normalized channel 검색, raw offset 복구, match된 AliasBinding 목록 반환.

### 15.2 경계 정책의 필요성

단순 substring match는 다음 오류를 만든다.

```text
AP 장애     → AP match
AP에서      → AP match
SAP 시스템  → 보통 AP 내부 match 금지
CAPEX       → 보통 AP 내부 match 금지

한전에서    → 한전 match
한전KDN     → 한전 / 한전KDN 중첩 가능
대한전선    → 내부 "한전"을 독립 match하면 안 됨
```

### 15.3 Boundary Policy

지원 가능한 기본 boundary type:

```text
ANY
UNICODE_WORD_BOUNDARY
LATIN_TOKEN_BOUNDARY
HANGUL_TOKEN_BOUNDARY
PARTICLE_OR_TOKEN_BOUNDARY
CUSTOM_FST
```

각 match는 left/right boundary 검사를 통과한 뒤 proposal이 된다. (REQ-BND-001)

### 15.4 Exact Sense 보존

한 exact surface가 여러 Entity에 연결되면 모든 binding을 내부 candidate pool에 추가한다. 인기도, domain prior, 과거 top-1만으로 exact sense를 제거하지 않는다. (INV-004)

### 15.5 Boundary와 Tail Parser의 인터페이스 [normative]

v0.2에서 `PARTICLE_OR_TOKEN_BOUNDARY` 판정이 particle 지식을 필요로 하여 boundary check와 tail parser 사이에 순서 모호성이 있었다. v0.3은 다음과 같이 확정한다.

- `PARTICLE_OR_TOKEN_BOUNDARY`의 우측 판정 = (다음 위치가 token boundary) OR (particle FST가 후속 문자열의 접두를 수락). (REQ-BND-002)
- 실행 순서: (1) exact matcher가 core 후보 span 생성 → (2) boundary checker가 좌우 문자 검사와 particle FST의 prefix-accept 질의로 통과 판정 → (3) 통과한 proposal에 대해 tail/prefix parser가 완전한 분해(prefix/residual/particle) 수행.
- FST는 `morphology-rules.bin`의 read-only 공유 컴포넌트이며, boundary 단계는 수락 여부만 질의하고 분해 결과를 생성하지 않는다. (REQ-BND-003)

---

## 16. Tail/Prefix Parser: 조사, 어미, Residual, Extension, 좌측 수식

### 16.1 기본 동작

Exact/fuzzy core match의 좌우 문자열을 다음 타입으로 분석한다.

```text
좌측: PREFIX_MODIFIER
우측: ENTITY_EXTENSION / RELATIONAL_SUFFIX / ROLE_SUFFIX / LOCATION_SUFFIX
      / DOCUMENT_MODIFIER / SYSTEM_MODIFIER / PARTICLE
      / LATIN_PLURAL / LATIN_POSSESSIVE / UNKNOWN
```

예:

```text
전 한전서울본부에서도

prefix:   전 (TEMPORAL)
core:     한전
residual: 서울본부
particle: 에서도 (에서 + 도)
```

### 16.2 조사 카탈로그와 연쇄 규칙 [normative]

**단일 조사 카탈로그 (초기):**

```text
격·보조:  은/는  이/가  을/를  과/와  의
          도  만  뿐  밖에  조차  마저  마다  대로  만큼
          처럼  보다  같이  부터  까지
부사격:   에  에서  에게  에게서  한테  한테서  께  께서
          (으)로  (으)로서  (으)로써  (이)랑  하고
          (이)나  (이)든  (이)라도  (이)야
계사·종결(초기): 이다  인  이라  이면  였다  임  이며  이고
```

**받침 allomorph 쌍:** 은/는, 이/가, 을/를, 과/와, 으로/로(ㄹ받침은 로), 으로서/로서, 으로써/로써, 이나/나, 이든/든, 이라도/라도, 이랑/랑, 이야/야.

**연쇄 규칙:**

- 조사 결합형(에서+도, 까지+는, 만+이라도, 과+의, 에+는, 부터+는 등)은 목록으로 열거하지 않고 FST 합성으로 처리해야 한다. (REQ-TAIL-001)
- 연쇄 depth는 기본 최대 3으로 제한한다(과생성 통제, §52.13). 한계값은 config이며 실측으로 조정한다(OQ-001).
- 받침과 맞지 않는 비문법적 조합은 후보 생성 단계에서 hard reject하지 않고 낮은 confidence로 유지할 수 있다.

v0.2 대비: `도`, `만` 등 최고빈도 단일 조사가 카탈로그에 추가되었고, `에서도` 같은 결합형은 열거 항목에서 제거되어 합성으로 이동했다.

### 16.3 기관 및 역할 suffix 카탈로그 (초기)

```text
부  처  청  원  국  실  과  팀
본부  지사  센터  사무국
연구원  연구소  위원회
병원  대학  재단  협회  공단
담당자  직원  측  규정  시스템
```

### 16.4 Extension 확정 정책

`서울대 + 병원 → 서울대학교병원` 같은 결합은 다음 우선순위를 따른다.

1. full surface exact alias가 존재하면 해당 binding 사용
2. `COMPOSES_TO` relation이 있으면 relation candidate 추가
3. heuristic extension은 별도 candidate로만 생성
4. heuristic만으로 base Entity를 다른 Entity로 확정하지 않음 (REQ-TAIL-002)

### 16.5 조사·Suffix 동형 충돌 [normative]

단일 음절 suffix와 조사(또는 조사의 접두)가 표면상 충돌하는 경우가 있다.

```text
과:   한전과 계약했다      → [한전] + [과=조사]        (일반적)
      네트워크과에서       → [네트워크과=부서] + [에서]  (가능)
부:   기획부터 검토했다    → [기획] + [부터=조사]       (일반적)
      기획부에서           → [기획부=부서] + [에서]     (가능)
도:   한전도 참여했다      → [한전] + [도=조사]         (일반적)
      경기도               → 지명 suffix 가능
```

규칙:

- 충돌이 발생하면 파서는 조사 분석과 suffix/extension 분석을 **모두 별도 proposal로 보존해야 한다**. 파서 단계에서 hard 선택을 하지 않고 ranking에 위임한다. (REQ-TAIL-003)
- 단, 한쪽 분석의 잔여 문자열이 UNKNOWN이 되는 경우(예: `기획부터`를 [기획부]+[터]로 본 경우) 해당 분석은 낮은 confidence로만 보존한다.
- UNKNOWN tail이 존재해도 core alias candidate를 제거하지 않는다.

### 16.6 Prefix Modifier [normative]

**Prefix 카탈로그 (초기):**

```text
시제:  구  신  전  현  舊  新  前  現
명명:  가칭  약칭  이른바
```

규칙:

- prefix는 core span에 포함하지 않고 mention의 `prefix` 필드로 분리 반환한다. 유형(TEMPORAL, NAMING)을 함께 표기한다. (REQ-TAIL-004)
- 공백 유무(`구 한국전력` / `구한국전력`) 모두 지원하되 provenance에 기록한다.
- prefix가 붙어도 core alias candidate를 제거하지 않는다. (REQ-TAIL-005)
- prefix의 시제 해석(예: `전 한전 사장`이 현재 조직을 지칭하는지)은 resolver가 확정하지 않고 downstream 정책에 위임한다(OQ-009).
- 단, prefix를 포함한 전체 표면이 별도 exact alias로 등록되어 있으면(예: `구 한국전력`이 별도 Entity) exact binding이 우선한다.

### 16.7 Latin 형태 변형 tail [normative]

profile `latin_morph: true`인 binding에 대해 다음 tail을 지원한다.

```text
LATIN_PLURAL:      s, es          예: APs, servers
LATIN_POSSESSIVE:  's, ’s         예: AP's
```

- boundary 상호작용: `allow_inside_latin_run: false`인 binding은 기본적으로 `APs`의 `AP`를 latin run 내부로 보고 거부한다. `latin_morph: true`이면 s/es/'s tail은 boundary 예외로 등록되어 core match + LATIN_PLURAL/POSSESSIVE residual로 분석된다. (REQ-TAIL-006)
- 기본값은 profile에 따른다(§14.6): `latin_acronym`은 false, `latin_word`는 true. 기본값의 적정성은 OQ-006으로 관리한다.

---

## 17. Fuzzy Surface Recovery

### 17.1 목표

Fuzzy matcher는 typo recovery를 담당한다. 임의의 짧은 문자열을 모든 alias와 edit-distance 비교하지 않는다. Fuzzy는 Level B(통계) 경로이며 카탈로그 보장 대상이 아니다.

### 17.2 Jamo Representation과 비용 규칙

한글 음절을 초성·중성·종성으로 분해하고 weighted edit cost를 계산한다.

초기 비용 예시 (normative constant가 아니라 초기 config):

| 변형 | 비용 |
|---|---:|
| 공백 삽입·삭제 | 0.05 |
| 하이픈·점 삽입·삭제 | 0.05 |
| 허용된 전각·반각 변환 | 0.00 |
| 인접 키 치환 | 0.20 |
| 종성 삽입·삭제 | 0.25 |
| 자모 순서 전환 | 0.30 |
| 초성 또는 중성 치환 (일반) | 0.70 |
| 음절 전체 치환 | 1.00 |

**최소 비용 단일 적용 원칙 [normative]:** 하나의 원자 변형이 복수 비용 규칙에 해당하면(예: 초성의 인접 키 치환은 "인접 키 치환"이자 "초성 치환"), 가장 저렴한 — 즉 가장 구체적인 — 규칙 하나만 적용한다. 비용을 중복 합산해서는 안 된다. (REQ-FUZ-001)

### 17.3 Two-Stage Retrieval

전체 alias에 expensive distance를 계산하지 않는다.

```text
character/Jamo n-gram inverted index
        ↓
top-M alias family shortlist
        ↓
weighted Damerau-Levenshtein verification
```

### 17.4 Keyboard Channel

두벌식 key sequence를 별도 representation으로 사용한다.

```text
한전 → gkswjs
```

처리 대상: 영문 입력 모드(한글을 영문 자판으로 입력), 인접 키, 키 누락, 키 중복, 두 키 순서 변경, 한글·영문 혼합. 역방향(Latin alias를 한글 모드로 입력, 예: `qms` → `ㅂㅡㄴ` 계열)도 keyboard channel에서 처리할 수 있다. 세벌식 지원 여부는 OQ-008로 관리한다.

### 17.5 Fuzzy Safety

- 1~2자 alias 일반 edit fuzzy 기본 비활성화 (REQ-FUZ-002)
- high-collision alias는 더 높은 context requirement 적용
- fuzzy result는 exact result를 제거하지 않음 (INV-010)
- fuzzy proposal 수는 request budget을 사용
- threshold는 alias 길이와 script type에 따라 분리 가능

---

## 18. Document-Local Alias

### 18.1 정의 패턴

다음과 같은 문서 내부 정의를 탐지한다.

```text
한국과학기술연구원(KIST)
한국과학기술연구원, 이하 KIST
KIST(한국과학기술연구원)
한국과학기술연구원(이하 "연구원")
```

### 18.2 Scope

Document-local alias는 `document`(기본), `conversation/session`, `explicit application scope` 중 하나에만 존재한다.

### 18.3 Poisoning 방지

문서가 `한국전력공사(이하 AP)`를 선언하더라도 global glossary의 기존 `AP` binding을 삭제하거나 overwrite하지 않는다. (INV-009, REQ-LOC-001)

대신: local candidate 강한 boost 가능, source definition span 보존, `trust_level` 기록, global candidates 유지, untrusted document에서는 commit threshold 강화 가능.

### 18.4 저장 금지

문서 안에서 발견한 alias를 관리자 승인 없이 tenant global glossary로 승격하지 않는다. (INV-008, REQ-LOC-002) 승격 제안은 §30의 correction/제안 큐를 통해서만 이루어진다.

---

## 19. Neural Mention Proposer

### 19.1 역할

Neural proposer는 Level C open-world mention detection을 담당한다. 초기 기본 모드에서는 선택적이다.

```json
{ "detect_unregistered_mentions": false }
```

### 19.2 요구사항

- 여러 mention 동시 탐지, overlapping/nested span
- 높은 recall 운영점
- raw text만으로 동작 가능, 형태소 분석기는 optional feature
- tokenizer token 내부 boundary 표현 가능

### 19.3 Character Boundary Head

단순 subword token start/end classifier만으로는 token 내부 문자 경계를 표현할 수 없다.

권장 구조:

```text
Transformer contextual token features
        ↓
character/Jamo position projection
        ↓
char-level start/end/span head
```

대안: 별도 lightweight character encoder, byte/character encoder.

### 19.4 Neural Proposal Budget

```text
max_neural_spans_per_chunk
max_neural_spans_per_1k_chars
min_span_score
max_span_length
```

Neural-only proposal은 trace에서 별도로 식별한다.

---

## 20. Mention Graph와 중첩 처리

### 20.1 Proposal 보존

```text
입력: 서울대병원AI센터에서

가능한 proposal:
서울대 / 서울대병원 / 서울대병원AI센터 / 병원 / AI센터
```

Proposal 단계에서는 일반 NMS를 사용하지 않는다.

### 20.2 Mention Graph

```text
MentionNode
- prefix / core_span / full_span / matched_segments
- candidates / proposal sources

MentionEdge
- CONTAINS / OVERLAPS / COMPOSES / EXTENDS / SAME_ENTITY
```

### 20.3 중복 병합

동일 raw core span, 동일 entity candidate, 호환되는 normalization provenance가 모두 같으면 동일 node로 병합할 수 있다. 서로 다른 span을 longest-match 규칙 하나로 제거하지 않는다.

### 20.4 Primary Mention Selection [normative]

Downstream 기본 출력에는 `primary_mentions`를 제공한다. 선택 우선순위:

1. glossary에 명시된 full composite exact alias
2. 높은 신뢰도의 전체 exact binding
3. base Entity + 검증된 extension relation
4. 독립 Entity로 강하게 판별된 nested mention
5. 일반 role/suffix로 보이는 내부 문자열은 기본 primary에서 제외

**결정성 요구:** 동일 snapshot과 동일 입력에 대해 primary 선택 결과는 결정적이어야 한다. 동순위 tie는 (긴 core span 우선 → 시작 offset 오름차순 → alias_id 사전순)으로 해소한다. (REQ-GRPH-001)

모든 proposal이 필요한 디버그/검색 사용자는 `all_mentions`를 요청할 수 있다.

---
## 21. Candidate Generator

### 21.1 채널 합집합

```text
exact alias
normalized/tolerant alias
morphology 기반 core (tail/prefix 분해)
document-local alias
Jamo fuzzy
keyboard fuzzy
abbreviation alignment      (조건부, Pass 2)
dense retrieval             (조건부, Pass 2)
relation expansion
```

### 21.2 후보 metadata

각 후보는 최소 다음을 유지한다.

```text
entity_id
alias_id / family_id
generation_channels
channel_scores
surface_transform_cost
boundary_valid
scope_match
provenance
retrieval_pass            # 1 | 2
```

### 21.3 Candidate Budget

```yaml
candidate_budget:
  max_exact_senses: 4096            # exact pool 안전 한계 (초과 시 §21.5)
  max_non_exact_candidates: 256     # exact pool을 제외한 내부 후보 상한
  max_rerank_candidates: 64
  max_final_candidates: 32
  max_prediction_set: 10
```

`max_non_exact_candidates`(v0.2의 `max_internal_candidates`에서 개명)는 exact pool에 적용되지 않는다. 내부 후보 총량은 `exact pool + non-exact pool`이다. budget 처리기는 exact pool을 잘라서는 안 된다. (INV-005, REQ-CAND-001)

### 21.4 Exact Sense 보존과 Budget 충돌

Exact alias sense는 `max_non_exact_candidates`와 무관하게 내부 후보에 모두 포함된다. `AMBIGUOUS` 응답의 클라이언트 노출 개수만 `max_prediction_set` 등으로 제한할 수 있다. (REQ-CAND-002)

### 21.5 Exact Pool 안전 한계 초과 절차 [normative]

한 surface의 exact sense 수가 `max_exact_senses`를 넘는 경우는 사전 품질 문제로 취급하며, 다음 절차만 허용된다. (REQ-CAND-003)

1. compile strict mode에서 오류로 검출하고 activation을 거부한다(권장 기본).
2. 운영상 불가피하게 활성화된 경우, 해당 surface의 요청은 hard-fail하지 않고 `AMBIGUOUS` + `degraded=true`로 응답하며 scope/context 조건 제공을 안내한다.
3. rerank는 batch로 분할 수행할 수 있으나 sense를 임의로 버릴 수 없다.

### 21.6 Conditional Retrieval — 2-Pass 실행 [normative]

- **Pass 1:** exact, normalized, morphology, fuzzy, doc-local 채널 실행 후 preliminary ranking/fusion.
- **Trigger 판정:** 다음 중 하나이면 Pass 2를 실행한다 — (a) Pass 1 후보 없음, (b) Pass 1 최대 calibrated marginal < `tau_dense`, (c) 평가/디버그 경로에서 강제 실행 옵션.
- **Pass 2:** dense retrieval과 abbreviation alignment를 실행하여 후보 합집합에 추가하고 final ranking/fusion을 수행한다.
- Pass 2는 요청당 최대 1회 실행한다(루프 금지). Pass 1 후보를 제거·대체해서는 안 되며, trace에 각 후보의 `retrieval_pass`를 기록한다. (REQ-CAND-004)
- `fast` 모드에서는 Pass 2를 실행하지 않는다. (REQ-CAND-005)

### 21.7 Abbreviation Alignment

`과기정통부 → 과학기술정보통신부` 같은 subsequence 정렬은 별도 후보 채널로 유지한다. 한국어 특성 반영: 어절 첫 음절 조합, 부분 음절 조합, 한자어 축약, 영문 두문자.

---

## 22. Contextual Sense Resolution

### 22.1 문제

동일 surface의 후보 sense 중 문맥에 맞는 의미를 선택한다.

```text
AP 결재 부탁드립니다     → WORKFLOW_APPROVAL_PROCESS 우세
무선 AP 장애 발생        → NETWORK_ACCESS_POINT 우세
AP 전표 처리             → FINANCE_ACCOUNTS_PAYABLE 우세
```

### 22.2 입력 신호

mention 좌우 문맥 window, Entity canonical/description/type/domain/examples, 같은 문서 내 다른 confirmed mentions, document metadata(신뢰 수준 반영), alias-level prior. Entity ID 자체를 임베딩 테이블로 암기하는 방식은 zero-training 조직 확장성을 깨므로 사용하지 않는다.

### 22.3 모델 구성

- **Bi-encoder:** context vector와 entity profile vector의 유사도. 후보 pruning과 dense retrieval 공용. entity vector는 compile time 계산.
- **Cross-encoder:** `[context with mention] × [entity profile]` 쌍 입력. 상위 후보에만 조건부 실행.

V1은 bi-encoder 없이 exact/fuzzy/문맥 keyword 기반으로도 배포 가능하다.

### 22.4 실행 조건 (초기)

```text
후보 sense가 2개 이상
top-1 margin이 임계값 미만
termness가 불확실
KB-missing 경계 판정
```

---

## 23. Score Fusion

### 23.1 원칙

여러 채널 점수를 단일 fusion score로 결합하되, 다음은 hard validity 조건으로 유지한다.

```text
boundary 위반
tenant 불일치
비활성 snapshot 참조
scope deny (단, §12.4 결정 표의 신뢰 수준 조건 충족 시에만)
```

### 23.2 Fusion 입력 예

```text
exact_channel_score
surface_transform_cost
morphology_parse_score
context_similarity
cross_encoder_score
alias_prior            # 상한 clipping 적용
doc_local_bonus
scope_match            # soft
retrieval_pass 표시
```

### 23.3 Prior 통제

echo-chamber 방지를 위해 prior 성분에는 상한(clipping)을 적용하고, self-training 데이터에서 prior가 재강화되는 경로를 모니터링한다(§41).

---

## 24. Termness와 KB-Missing 판정

### 24.1 상태 조합 매트릭스 [normative]

| mention_decision | 허용되는 link_decision |
|---|---|
| TERM | RESOLVED, AMBIGUOUS, KB_MISSING, UNCERTAIN |
| UNCERTAIN | AMBIGUOUS, KB_MISSING, UNCERTAIN (RESOLVED 금지 — INV-016) |
| NON_TERM | 없음 (link 단계 미수행) |

### 24.2 Termness 신호

surface가 glossary alias와 일치하는가, 문맥이 조직 용어 사용 패턴인가(결재, 장애, 시스템, 부서, 공문 등), document-local 정의 존재 여부, 일반 명사 사전과의 충돌, subword 희귀도.

### 24.3 KB-Missing 판정

`TERM/UNCERTAIN`이면서 어떤 후보도 문맥 호환 임계값을 넘지 못하면 `KB_MISSING` 후보를 prediction set에 포함한다. KB_MISSING의 calibrated_probability 의미는 §7.12를 따른다.

### 24.4 신조어 vs 일반어

`액포`류 판정을 위해 termness classifier는 desk-context feature와 negative corpus(일반 텍스트) 학습을 병행한다. 확신이 없으면 `UNCERTAIN`으로 남기고 RESOLVED를 강제하지 않는다. (REQ-TRM-002)

---

## 25. Calibration과 Prediction Set

### 25.1 목표

`calibrated_probability`(후보별 marginal)와 prediction set(집합 수준 보장)을 제공한다. 두 산출물의 의미 구분은 §7.12를 따른다.

### 25.2 기본 절차 [normative]

1. **Marginal calibration:** fusion score를 입력으로 그룹별 temperature scaling / Platt / isotonic 중 하나(config)로 후보별 marginal을 보정한다.
2. **Nonconformity score:** `s(x, y) = 1 − calibrated_marginal(y)`를 기본으로 한다.
3. **Group-conditional (Mondrian) split conformal:** 그룹별 held-out calibration set에서 분위수 `q̂ = ⌈(n+1)(1−α)⌉ / n`을 계산한다.
4. **Prediction set 구성:** `{y : s(x, y) ≤ q̂}`에 KB_MISSING 후보 조건(§24.3)을 결합한다.
5. **표본 부족 fallback:** 그룹 calibration 표본이 `n_min`(기본 500) 미만이면 상위 그룹 quantile로 fallback하고, fallback 사실을 trace에 기록한다. (REQ-CAL-002)

### 25.3 보장의 성격

- Exchangeability 가정 하에 marginal coverage(정답이 set에 포함될 확률 ≥ 1−α)를 목표로 하며, 그룹 조건부 구성으로 그룹별 편차를 줄인다.
- 응답의 `set_confidence`는 목표 1−α를 노출한다. distribution shift 하에서는 이 값이 자동으로 보장되지 않으므로 empirical coverage를 온라인 모니터링한다(§25.5).

### 25.4 Calibration 그룹 (초기)

```text
alias 길이 구간 × script type(한글/Latin/혼합)
× sense 수 구간 × generation channel(exact/fuzzy/dense)
× (tenant | global)
```

그룹 세분성과 표본 확보의 트레이드오프는 OQ-003으로 관리한다. Zero-training tenant는 global conservative calibrator(α 하향 조정)로 시작한다. (REQ-CAL-003)

### 25.5 온라인 Empirical Coverage 모니터링

- 라벨 소스는 §30 Correction API의 ACCEPTED 데이터와 주기적 human audit 표본이다. correction 경로 없이 온라인 coverage를 주장해서는 안 된다. (REQ-CAL-004)
- 지표: empirical coverage, mean/p95 prediction set size, 그룹별 coverage 편차.
- coverage가 목표 대비 유의하게 미달하면 α 재조정 또는 calibrator 재생성을 트리거한다(§54).

### 25.6 Commit 조건

`RESOLVED` commit은 최소 다음을 동시에 요구한다.

```text
top-1 calibrated marginal ≥ resolve_threshold
prediction set이 {top-1} 단독이거나 top-2 margin ≥ margin_threshold
mention_decision = TERM
degraded = false 인 채널 근거 존재
```

임계값은 mode(§26)와 tenant 정책에 따른다.

---

## 26. 실행 Mode: Fast, Aggressive, Commit

### 26.1 Mode 정의

| mode | 실행 채널 | neural | calibration | 용도 |
|---|---|---|---|---|
| `fast` | exact + normalized + morphology (+ doc-local 선택) | 없음 | 없음 | RAG query expansion, 자동완성, 저지연 태깅 |
| `aggressive` | 전 채널 + 조건부 Pass 2 | 조건부 | 선택 | 검색 recall 극대화, 진단 |
| `commit` | 전 채널 + 조건부 Pass 2, 보수 threshold | 조건부 | 필수 | 최종 답변, canonical 표시, 자동화 트리거 |

`fast` 규칙 [normative]:

- 온라인 신경망 호출과 Pass 2를 포함해서는 안 된다. (REQ-API-001)
- calibrated_probability를 제공하지 않는다. 단일 sense exact는 `RESOLVED`, 다의 exact는 ranking 없이 전체 sense를 나열한 `AMBIGUOUS`로 반환한다.
- 목표 latency는 기준 하드웨어 벤치마크로 확정한다(OQ-002).

### 26.2 View

동일 mode 결과 안에서 `aggressive_view`(후보 폭 넓게)와 `commit_view`(커밋 가능한 결정만)를 함께 반환할 수 있다. RAG 검색 인덱스 확장에는 fast/aggressive를, 사용자 표시·자동화에는 commit을 사용한다.

---
## 27. Resolve API

### 27.1 요청

```json
POST /v1/resolve
{
  "tenant_context": {
    "glossary_id": "organization-a",
    "expected_version": "2026-08-23.1",
    "version_policy": "strict"
  },
  "mode": "commit",
  "text": "한전KDN은 AP 장애 내용을 QMS에 등록했다.",
  "context": {
    "department": {"value": "network", "trust": "AUTH_CLAIM"}
  },
  "options": {
    "return_all_mentions": false,
    "return_trace": false,
    "detect_unregistered_mentions": false,
    "max_prediction_set": 5
  }
}
```

- `version_policy`: `strict`(기본) — `expected_version`이 현재 active와 다르면 409 오류. `latest_active` — 현재 active snapshot으로 진행하고 응답에 실제 사용 버전을 명시. (REQ-API-002)
- `mode`: `fast | aggressive | commit`.

### 27.2 입력 한도 [normative]

- 동기 API 입력 상한 기본값: `sync_max_input_bytes = 65536`(64KB). 초과 시 413 `INPUT_TOO_LARGE`와 함께 비동기 API(§28) 사용을 안내한다. (REQ-API-003)
- v0.2의 "동기 1MB"는 폐기한다. 장문 처리 경로는 §28이다.

### 27.3 응답 예

```json
{
  "snapshot": {
    "glossary_id": "organization-a",
    "glossary_version": "2026-08-23.1",
    "snapshot_id": "snap-3f8c",
    "model_bundle_version": "mb-1.4.0"
  },
  "mode": "commit",
  "degraded": false,
  "mentions": [
    {
      "mention_id": "m1",
      "surface": "한전KDN",
      "span": {
        "byte": {"start": 0, "end": 9},
        "codepoint": {"start": 0, "end": 5},
        "utf16": {"start": 0, "end": 5}
      },
      "mention_decision": "TERM",
      "link_decision": "RESOLVED",
      "resolved_entity": {
        "entity_id": "ORG_KEPCO_KDN",
        "canonical": "한전KDN",
        "calibrated_probability": 0.99
      },
      "prediction_set": {
        "set_confidence": 0.95,
        "members": [
          {"kind": "ENTITY", "entity_id": "ORG_KEPCO_KDN", "calibrated_probability": 0.99}
        ]
      }
    },
    {
      "mention_id": "m2",
      "surface": "AP",
      "span": {
        "byte": {"start": 13, "end": 15},
        "codepoint": {"start": 7, "end": 9},
        "utf16": {"start": 7, "end": 9}
      },
      "mention_decision": "TERM",
      "link_decision": "AMBIGUOUS",
      "prediction_set": {
        "set_confidence": 0.95,
        "members": [
          {"kind": "ENTITY", "entity_id": "NETWORK_ACCESS_POINT",
           "calibrated_probability": 0.86},
          {"kind": "ENTITY", "entity_id": "WORKFLOW_APPROVAL_PROCESS",
           "calibrated_probability": 0.21},
          {"kind": "KB_MISSING", "calibrated_probability": 0.04}
        ]
      }
    }
  ]
}
```

`calibrated_probability`는 후보별 marginal이므로 합이 1이 아닐 수 있다(§7.12). 위 예의 0.86 + 0.21 + 0.04 = 1.11은 정상이다.

### 27.4 Trace 옵션

`return_trace: true`일 때 채널별 근거, budget 사용량, boundary 판정, `retrieval_pass`, drop 사유, fallback 여부를 반환한다.

### 27.5 재현성 필드

응답에는 항상 snapshot 식별 정보(glossary_version, snapshot_id, model_bundle_version)를 포함한다.

### 27.6 오류 스키마 [normative]

```json
{
  "error": {
    "code": "GLOSSARY_VERSION_MISMATCH",
    "message": "expected 2026-08-22.4 but active is 2026-08-23.1",
    "retryable": false,
    "details": {"active_version": "2026-08-23.1"}
  }
}
```

| HTTP | code | 의미 | retryable |
|---:|---|---|---|
| 400 | `INVALID_REQUEST` | 스키마 위반 | no |
| 400 | `INVALID_UTF8` | malformed 입력(§13.6). 수리하지 않음 | no |
| 401 | `UNAUTHENTICATED` | 인증 실패 | no |
| 403 | `FORBIDDEN_GLOSSARY` | tenant scope 밖 glossary | no |
| 404 | `GLOSSARY_NOT_FOUND` | 존재하지 않는 glossary | no |
| 409 | `GLOSSARY_VERSION_MISMATCH` | strict policy에서 버전 불일치 | no |
| 413 | `INPUT_TOO_LARGE` | 동기 상한 초과. details에 비동기 안내 | no |
| 429 | `RATE_LIMITED` | Retry-After 헤더 포함 | yes |
| 500 | `INTERNAL` | 내부 오류 | yes |
| 503 | `SNAPSHOT_UNAVAILABLE` | activation 중/로드 실패 | yes |

(REQ-API-004)

### 27.7 Degraded와 오류의 구분

budget/timeout/truncation은 오류가 아니라 200 + `degraded: true`로 반환한다(INV-013). 오류 코드는 요청 자체를 처리할 수 없는 경우에만 사용한다.

### 27.8 Degraded 시 상태 하향

degraded 처리로 후보 생성이 불완전한 mention은 `RESOLVED`로 commit하지 않고 `UNCERTAIN` 또는 `AMBIGUOUS`로 하향한다. (REQ-API-005)

---

## 28. 비동기 Document Resolve API

### 28.1 Job 생성

```json
POST /v1/resolve-jobs
{
  "tenant_context": {"glossary_id": "organization-a", "version_policy": "latest_active"},
  "mode": "commit",
  "input": {"inline_text": "...", "or_object_ref": null},
  "options": {"chunking": "auto", "callback_url": null}
}

202 Accepted
{"job_id": "job-9d2a", "status": "QUEUED"}
```

- 입력 상한 기본값: `async_max_input_bytes = 10485760`(10MB).
- Job 시작 시 snapshot을 1회 pin하며, 모든 chunk는 동일 snapshot으로 처리한다. (INV-017, REQ-API-006)

### 28.2 상태 조회와 결과

```text
GET /v1/resolve-jobs/{job_id}
→ {status: QUEUED|RUNNING|SUCCEEDED|FAILED|CANCELLED,
   snapshot: {...}, progress: {chunks_done, chunks_total}}

GET /v1/resolve-jobs/{job_id}/results?page_token=...
→ mention 결과 페이지네이션 (chunk 경계와 원문 전역 offset 포함)

DELETE /v1/resolve-jobs/{job_id}   # 취소
```

### 28.3 Chunk와 Offset

- chunk 분할은 문장/문단 경계를 우선하며, 응답 offset은 항상 원문 전역 기준으로 환산해 반환한다.
- chunk 경계에 걸친 mention은 overlap window로 복구하고 중복 병합한다(§20.3).

### 28.4 운영 정책

- job 결과 보존 기한, 우선순위 큐, tenant별 동시 job 수는 tenant 정책이다.
- `callback_url` webhook은 선택 기능이며 서명 헤더를 포함해야 한다.

---

## 29. Glossary Management API

```text
POST   /v1/glossaries/{id}/versions           # 새 버전 업로드
POST   /v1/glossaries/{id}/versions/{v}/compile
GET    /v1/glossaries/{id}/versions/{v}/diagnostics
POST   /v1/glossaries/{id}/versions/{v}/activate   # atomic (§11.4)
POST   /v1/glossaries/{id}/versions/{v}/rollback
GET    /v1/glossaries/{id}/active
POST   /v1/glossaries/{id}/warm               # §32.4 사전 예열
```

- compile은 비동기이며 diagnostics(경고·오류·conformance 결과)를 반환한다.
- activate는 conformance 100%와 compatibility 검증을 통과해야만 성공한다.
- 모든 관리 API 호출은 audit log 대상이다(§46.4).

---

## 30. Correction API

Calibration 재생성(§25.5), tenant adaptation(§48), golden set 축적(§48.6), glossary 개선 제안의 라벨 공급 경로다. v0.2에서 언급만 되고 계약이 없던 부분을 확정한다.

### 30.1 제출

```json
POST /v1/corrections
{
  "request_ref": {
    "snapshot_id": "snap-3f8c",
    "request_id": "req-7b1e",
    "mention_id": "m2"
  },
  "correction_type": "WRONG_ENTITY",
  "corrected": {
    "entity_id": "FINANCE_ACCOUNTS_PAYABLE",
    "span": null
  },
  "verifier": {"kind": "REVIEWER", "principal_ref": "opaque-id"},
  "evidence_text_opt_in": false,
  "comment": "재무 문서 맥락"
}
```

`correction_type` [normative]:

```text
WRONG_ENTITY            # 다른 Entity가 정답
WRONG_SPAN              # span 경계 오류
MISSED_MENTION          # 탐지 누락 (corrected.span 필수)
FALSE_MENTION           # 용어가 아님 (NON_TERM)
SHOULD_BE_KB_MISSING    # 어떤 Entity도 정답 아님
SHOULD_BE_RESOLVED      # AMBIGUOUS/UNCERTAIN였으나 확정 가능했음
```

### 30.2 개인정보

- 기본값은 원문 미저장이다: `request_id` 참조, span, alias family, 상태 정보만 저장한다.
- `evidence_text_opt_in: true`이고 tenant 정책이 허용할 때만 mention 주변 window를 저장한다(§46.3, §47).

### 30.3 승인 워크플로 [normative]

```text
SUBMITTED → REVIEWED → ACCEPTED | REJECTED
```

- ACCEPTED 상태의 correction만 calibrator 재생성, adaptation 학습, 온라인 coverage 라벨, golden set 후보로 사용할 수 있다. (INV-018, REQ-COR-001)
- correction은 glossary를 자동 수정하지 않는다. alias 추가·수정 제안은 별도 제안 큐에 적재되고 관리자 승인을 거친다. (REQ-COR-002)
- verifier 종류(USER/REVIEWER/ADMIN)별 가중치와 출처별 수량 상한을 두어 오염을 완화한다(§52.14). (REQ-COR-003)
- correction 데이터와 큐는 tenant별로 격리된다. (REQ-COR-004)

### 30.4 조회

```text
GET /v1/corrections?status=SUBMITTED&page_token=...   # 관리자 검토 큐
GET /v1/corrections/{id}
POST /v1/corrections/{id}/review {decision: ACCEPTED|REJECTED, reason}
```

---

## 31. Runtime Budget과 Resource Policy

### 31.1 Budget Config 예

```yaml
runtime_budget:
  sync_max_input_bytes: 65536
  async_max_input_bytes: 10485760
  max_chunk_bytes: 8192
  max_total_mention_proposals: 512
  max_non_exact_candidates: 256
  max_cross_encoder_pairs: 256
  max_dense_queries_per_request: 16
  request_timeout_ms: 1500
```

`request_timeout_ms`는 동기 API 기준이며, 비동기 job은 별도 job timeout을 사용한다.

### 31.2 초과 시 동작

deterministic 결과 우선 반환, optional stage 순차 생략, `degraded: true`와 생략 stage 노출, 프로세스 kill 대신 graceful partial result. (REQ-BUD-001)

### 31.3 우선순위

절대 유지: exact alias match, mention offset 정합성, tenant 격리, snapshot 일관성.

먼저 생략: cross-encoder 재순위(전체) → dense retrieval(Pass 2) → fuzzy 후보 폭 → neural proposer. 이 우선순위는 **non-exact 채널 간의 순위**이며 exact pool에는 적용되지 않는다(INV-005). (REQ-BUD-002)

---

## 32. Snapshot 메모리와 Tenant 상주 정책

v0.2에서 미정이던 다중 tenant 메모리 관리를 정의한다.

### 32.1 Tier 모델 [normative]

| tier | 상주 내용 | 진입 조건 |
|---|---|---|
| hot | exact/fuzzy index + entity vectors + calibrator (+ adapter) 전체 상주 | 최근 활동 상위 tenant, 또는 pinned |
| warm | exact index만 상주, vectors/adapter는 mmap lazy-load | 최근 활동 있으나 hot 초과분 |
| cold | 디스크(mmap 파일)만, 요청 시 로드 | 비활동 tenant |

- eviction은 LRU 기반이되, 활성 요청이 참조 중인 snapshot은 refcount로 보호되어 evict되지 않는다. (REQ-MEM-002)
- tier 전환과 cold-start latency는 tenant별 지표로 관측한다(§46).
- cold tenant의 첫 요청 latency 목표(SLA)는 OQ-004로 관리한다.

### 32.2 Footprint 산정 (informative)

```text
vectors ≈ entities × dim × dtype_bytes
예: 100,000 × 384 × 2B(fp16) ≈ 77 MB

per-tenant hot footprint ≈ exact index + fuzzy n-gram index
                          + vectors + calibrator + (adapter)
```

capacity planning은 위 공식과 실측 index 크기로 수행한다.

### 32.3 Adapter GPU 정책

- tenant adapter(LoRA 등)는 기본 CPU 상주로 두고, 요청 시 GPU 스왑 또는 사전 병합 캐시를 사용한다.
- 동시 GPU 상주 adapter 수에 상한을 두고 LRU로 교체한다. base model은 tenant 간 공유하되 후보·결과 격리는 §12를 따른다.

### 32.4 Warm-up

`POST /v1/glossaries/{id}/warm`(§29)으로 예상 트래픽 전에 hot tier 승격을 요청할 수 있다. 승격 실패는 오류가 아니라 best-effort로 처리한다.

---

## 33. 모델 구성과 도입 순서

| 구성 | 내용 | 비고 |
|---|---|---|
| V1 | symbolic only: exact + normalization + morphology + fuzzy + doc-local | zero-GPU, Level A 전체 |
| V2 | V1 + bi-encoder retrieval + 기본 calibrator | Level B 개시 |
| V3 | V2 + cross-encoder + termness classifier | commit 품질 강화 |
| V4 | V3 + neural mention proposer (Level C, flag) | 실험 |

모델 크기 지향점: bi-encoder/cross-encoder 100M~350M급 다국어 encoder에서 시작하고, 온라인 생성형 LLM은 사용하지 않는다.

---

## 34. 권장 구현 기술

- **Runtime core:** Rust — exact/fuzzy index, normalization, FST, offset, snapshot 관리. C ABI 또는 gRPC로 노출.
- **Neural serving:** PyTorch 학습 → ONNX Runtime(CPU) / TensorRT(GPU) 추론. 결정적 모드에서는 고정 시드·고정 커널.
- **API layer:** 언어 무관(초기 구현 Python FastAPI 또는 Rust axum), OpenAPI 스키마 산출.
- **저장:** artifact는 파일 기반 mmap(§11.1), 메타데이터는 RDB, correction/job 큐는 내구성 큐.
- 형태소 분석기는 optional feature 소스로만 사용하고 단일 의존을 피한다.

---
## 35. 학습 목표와 단계적 Training

처음부터 모든 loss를 하나의 shared model로 동시에 학습하는 것을 요구하지 않는다. 각 하위 문제를 독립 baseline으로 검증한 뒤, 공유 encoder 또는 multi-task 구조가 실제 이득이 있을 때만 결합한다.

### 35.1 Stage A — Surface Robustness

- 목표: spacing/punctuation 변형, Jamo typo, keyboard typo, boundary extension, alias family similarity.
- 데이터: deterministic 변형, 실제 correction log(§30 ACCEPTED), 수동 확인 typo pair.
- 가능 loss: `L_surface_contrastive`, `L_edit_cost`, `L_boundary`.
- Symbolic matcher가 충분한 영역은 neural surface model을 필수로 두지 않는다.

### 35.2 Stage B — Sense Cross-Encoder

- 목표: 같은 surface의 여러 의미 판별, rare sense 보존, context/candidate compatibility 학습.
- 데이터: 수동 검증 문맥, candidate-constrained teacher annotation, same-surface hard negative, partial sense label.
- 가능 loss: `L_entity_ranking`, `L_pairwise_margin`, `L_nil_or_kb_missing`.

### 35.3 Stage C — Bi-Encoder

- 목표: Entity retrieval, unseen entity, unlisted alias, canonical/description 기반 연결.
- 학습: cross-encoder distillation, in-batch negatives, same-domain hard negatives, lexically similar Entity.

### 35.4 Stage D — Unknown Mention Proposer

- 목표: 사전에 잡히지 않는 span 탐지, NON_TERM/TERM 구분.
- 데이터: partially annotated corpus, PU learning, neural-only mention 검증, KB-missing term 예, false-positive heavy negatives.

### 35.5 Stage E — Document Context

- 목표: 앞뒤 문장, 문서 내 정의, 제목/섹션, mention 간 evidence 활용.
- 문서 전체를 하나의 sense로 강제하지 않는다. 같은 문서에서도 동일 alias가 다른 sense를 가질 수 있다.

---

## 36. Dictionary-Conditioned 학습

### 36.1 핵심 원칙

모델은 고정 Entity class head를 외우는 대신, 현재 제공된 glossary entry와 mention context의 호환성을 학습한다.

### 36.2 Temporary Glossary Episode

각 training episode에서 임시 glossary 후보를 구성한다.

```text
E1: alias=AP,  description=무선 단말을 연결하는 네트워크 장비
E2: alias=AP,  description=매입채무와 지급을 처리하는 회계 업무
E3: alias=QMS, description=품질 관리 시스템
E4: alias=한전, description=한국전력공사

입력: 한전 담당자가 AP 장애 내용을 QMS에 등록했다.
정답: 한전→E4, AP→E1, QMS→E3
```

다음 episode는 다른 Entity ID와 다른 glossary를 사용한다.

### 36.3 Candidate 구성

정답 Entity, 동일 alias의 다른 sense, 이름이 비슷한 Entity, 동일 type/domain, 실제 문서 공기 Entity, Jamo/keyboard 근접 Entity, 현재 model hard negative, KB_MISSING pseudo candidate.

### 36.4 Glossary Dropout

alias masking, mention masking, description dropout을 실험적으로 사용해 단일 feature 의존을 방지한다. 비율은 실험 config다.

---

## 37. Deterministic 데이터 생성

### 37.1 조사·어미 (v0.3 확장)

카탈로그(§16.2) 전수와 연쇄 대표 조합을 생성한다.

```text
한전은 / 한전이 / 한전을 / 한전에서 / 한전으로 / 한전과의 / 한전이라면 / 한전임
한전도 / 한전만 / 한전조차 / 한전마저 / 한전처럼 / 한전보다      # v0.3 추가
한전에서도 / 한전까지는 / 한전만이라도 / 한전으로부터            # 연쇄 (FST 합성)
```

### 37.2 부가 표현

```text
한전측 / 한전직원 / 한전담당자 / 한전본부 / 한전서울본부
한전AI센터 / 한전규정 / 한전시스템
```

생성 데이터는 base Entity와 residual/particle label을 분리해 저장한다.

### 37.3 Prefix 변형 (v0.3 신규)

```text
구 한전 / 구한전 / 전 한전 사장 / 현 한전 / 신한전   # prefix label 분리 저장
```

### 37.4 공백·구두점

```text
한 전 / 한-전 / 한전 KDN / 한전-KDN / 한전/KDN
```

### 37.5 Jamo/Keyboard

종성 누락·추가, 초·중성 인접 키, key omission/duplication/transposition, 영문 입력 모드(gkswjs), 혼합 입력.

### 37.6 Latin 형태 변형 (v0.3 신규)

```text
APs / AP's / servers   # latin_morph 대상 binding에 한정
```

### 37.7 Multi-Mention / Nested

```text
한전은 QMS를 통해 AP 교체 요청을 접수했다.
서울대병원AI센터에서 / 과기정통부AI전략팀은
```

### 37.8 Negative

alias가 더 긴 Latin word 내부에 포함, 짧은 대문자 일반 표현, 비슷한 일반 명사, fuzzy 거리가 작지만 무관한 문자열, 기관 suffix만 있는 일반 문장.

---

## 38. Distant Supervision과 Partial Label

### 38.1 Mention Label

glossary match된 surface는 mention positive로 사용할 수 있다. 탐지되지 않은 문자열은 자동 negative가 아니라 `UNLABELED`다.

### 38.2 Ambiguous Sense

다의 alias의 exact match 사실만으로 특정 sense를 positive로 만들지 않는다.

```json
{
  "mention_label": "POSITIVE",
  "allowed_entity_ids": ["NETWORK_ACCESS_POINT", "FINANCE_ACCOUNTS_PAYABLE",
                          "WORKFLOW_APPROVAL_PROCESS"],
  "sense_label": "UNLABELED"
}
```

### 38.3 PU Learning

사전 불완전성으로 unmatched term을 negative로 오인하는 문제와 open-world proposer 학습에 사용한다. PU learning이 ambiguous sense를 자동 정답으로 바꾸는 방법은 아니다.

### 38.4 Hard Negative

수동 검증, teacher 검증, high-score false positive log, 일반어 dictionary/corpus, cross-tenant Entity를 제외한 same-domain distractor에서 수집한다.

---

## 39. LLM-as-a-Teacher

LLM teacher는 온라인 resolver가 아니라 오프라인 annotation/data-generation 도구다.

### 39.1 역할

Annotator(후보 중 Entity 또는 KB_MISSING 선택), Recall Critic(누락 검토), Counterfactual Generator(같은 alias를 다른 sense 문맥으로 변경), Hard-Negative Selector, Adjudicator(복수 annotation 충돌 조정).

### 39.2 Candidate-Constrained 입력

teacher에는 allowed_entities allowlist와 `allow_kb_missing`을 제공하며 자유 생성 Entity를 금지한다.

### 39.3 Teacher Validator

다음 검사를 모두 통과한 데이터만 학습에 사용한다: `text[start:end] == surface`, Entity ID allowlist, KB_MISSING schema 유효성, 존재하지 않는 Entity 생성 금지, raw span 범위, 중첩 annotation 규칙, 동일 span의 모순된 확정 label 금지, canonical 변조 금지, definition relation consistency.

불확실한 annotation은 AMBIGUOUS / KB_MISSING / REVIEW_REQUIRED로 유지하고 강제로 하나의 sense로 만들지 않는다.

### 39.4 보안

외부 teacher 사용은 기본 비활성화한다. 활성화 시 PII redaction, tenant data egress policy, audit log, provider policy, retention policy를 요구한다.

---

## 40. 데이터 혼합과 Sampling

### 40.1 Normative 비율 금지

혼합 비율은 스펙의 고정 요구사항이 아니라 실험 config다. 실제 corpus 분포, rare sense frequency, false-positive profile, glossary completeness, teacher 품질, domain shift를 기준으로 결정한다.

### 40.2 Source별 최대 비중 (예시)

```yaml
data_mix:
  real_verified: 0.35
  teacher_real_docs: 0.25
  deterministic_max: 0.20
  counterfactual_max: 0.10
  free_synthetic_max: 0.05
  negative_min: 0.05
```

### 40.3 Ablation

baseline / +deterministic / +teacher / +PU / +counterfactual / +self-training으로 source별 가치를 평가하고, 주요 slice 순이익이 없는 source는 제거할 수 있어야 한다.

### 40.4 Sense-Balanced Sampling

mini-batch는 rare sense를 oversample할 수 있다. 단, calibration용 validation/test는 실제 분포를 보존한다.

### 40.5 Same-Surface Hard Negative

랜덤 negative보다 동일 surface의 다른 sense를 우선한다.

---

## 41. Self-Training

```text
base model → pseudo label → rule/teacher/human 검증 → accepted pseudo data → optional retraining
```

안전장치: sense별 pseudo-label 상한, majority sense 증가율 감시, exact/context disagreement 별도 queue, prediction-set이 넓은 샘플은 단일 pseudo-label 금지, model 자체 출력만으로 재귀 학습 금지, 새 adapter는 golden set 회귀 통과 후 활성화. Self-training은 zero-training 제품의 필수 조건이 아니며 후기 adaptation 단계에서 사용한다.

---

## 42. 데이터 분할

Random sentence split 하나만 사용하지 않는다.

| split | 내용 |
|---|---|
| Seen-Entity Context | 학습에서 본 Entity의 새 문맥 |
| UA — Unseen Alias | Entity는 봤으나 test surface는 미등장 |
| UE-Listed-Alias | Entity 학습 제외, test glossary에 정답 alias 명시. compiler/zero-training exact 경로 검증용 (dense zero-shot으로 해석 금지) |
| UE-Canonical-Only | Entity 학습 제외, canonical/description만 제공. dense retrieval 평가 |
| UE-Derived-Abbreviation | canonical에서 유도 가능한 미등록 약어 (과학기술정보통신부→과기정통부) |
| US-New-Sense | 기존 alias family에 새 sense 추가, description만 제공 |
| KB-Missing | 정답 Entity를 test glossary에서 제거. TERM+KB_MISSING vs NON_TERM 구분 측정 |
| Transformation Holdout | 특정 오류 유형을 학습에서 제외 (예: train Jamo, test 영문 입력 모드) |
| Domain Holdout / Time Split / Tenant Holdout | 부서·시간·tenant 전체 제외. tenant holdout이 진정한 zero-training onboarding 평가 |

---
## 43. 평가 지표

### 43.1 Conditioning 표기 [normative]

모든 지표 보고는 측정 조건을 명시해야 한다. (REQ-EVAL-001)

```text
E2E         원문 입력 기준 전체 파이프라인
|mention    gold core span이 proposal된 mention 조건부
|candidate  gold Entity가 후보 집합에 포함된 조건부
|commit     해당 상태로 commit된 것 중
```

예: "Candidate Recall@50 (|mention) 99.7%"와 "E2E gold-in-candidates 99.2%"는 서로 다른 지표다. 조건 없는 수치 보고는 금지한다.

### 43.2 Mention 지표 (E2E)

exact core-span P/R, exact full-span P/R, constrained containment recall, nested/overlapping recall, all-mentions sentence/document recall, false positives per 1k chars, proposals per 1k chars.

### 43.3 Constrained Containment

gold span이 긴 proposal 안에 들어가기만 하면 성공으로 계산하지 않는다. 성공 조건: (1) gold core span 포함, (2) 추가 영역이 허용된 prefix/residual/particle/extension으로 분석, (3) expansion ratio 제한 이내, (4) 해당 proposal의 candidate set에 정답 Entity 포함. Unrestricted containment는 진단 지표로만 둔다.

### 43.4 Candidate 지표 (|mention)

Candidate Recall@1/5/20/50, candidate count 통계, source별 정답 기여, exact miss 후 fallback recovery, cross-encoder pair 수, budget/truncation miss rate, Pass 2 실행률과 Pass 2 기여율.

### 43.5 Linking 지표

Top-1 accuracy(|candidate 또는 |mention 명시), MRR, RESOLVED precision(|commit), RESOLVED coverage(E2E), selective accuracy, risk-coverage curve, prediction-set empirical coverage와 mean/p95 size, KB_MISSING P/R, NON_TERM P/R, TERM recall.

### 43.6 End-to-End 조합 지표

correct mention + gold candidate retained / + correct top-1 / + gold in prediction set / all mentions in sentence covered.

### 43.7 Slice

필수 slice는 v0.2 목록을 유지하고 다음을 추가한다: 조사 연쇄 부착, prefix modifier 부착, 조사·suffix 동형 충돌, Latin morph tail, fast 모드 결과.

### 43.8 Confidence Interval

핵심 release gate는 point estimate + 95% CI + failure count + slice별 최소 표본 수를 함께 사용한다. 전체 평균만으로 release를 승인하지 않는다. (REQ-EVAL-002)

---

## 44. Release Gate 예시

실제 수치는 서비스별로 조정한다.

```yaml
release_gate:
  conformance:
    catalog_fixture_pass_rate: 1.0          # 미달 = blocker (REQ-LVL-002)

  level_a:
    core_span_recall_min_e2e: 0.995
    candidate_recall_at_50_min_given_mention: 0.997
    max_proposals_per_1k_chars_p95: 256

  commit:
    resolved_precision_min: 0.98
    resolved_coverage_min: 0.60             # 제품 profile별 별도 관리

  prediction_set:
    empirical_coverage_min: 0.995
    mean_size_max: 3.0
    p95_size_max: 8

  safety:
    cross_tenant_leak_count: 0
    offset_invariant_failures: 0
    snapshot_mixing_failures: 0
    unmapped_req_ids: 0                     # REQ-EVAL-003
```

---

## 45. 테스트 전략

### 45.1 Unit Test

Unicode normalization, byte/codepoint/UTF-16 offset mapping, Aho-Corasick exact match, boundary policy, particle/prefix FST, residual parser, extension relation, Jamo 분해, keyboard 변환, weighted edit distance, fuzzy shortlist, glossary validation, manifest compatibility, tenant authorization, cache namespace, API/오류 스키마 serialization, score/calibration 스키마.

### 45.2 Property-Based Test

glossary 전체에 대해 지원 변형을 자동 생성한다.

```python
for binding in glossary.alias_bindings:
    for variant in generate_supported_variants(binding):   # 카탈로그 기반
        result = resolver.resolve(variant.text)
        assert binding.entity_id in result.internal_candidate_entity_ids
        assert result.raw_span == variant.expected_raw_span
```

위 코드는 구조 설명용 예시다. 추가 property: normalization round-trip 복원 가능, exact candidate는 fallback candidate 때문에 사라지지 않음, 동일 snapshot 결정적 입력 재현성, tenant 변경 시 namespace 완전 분리.

### 45.3 Conformance Suite 실행 (v0.3 신규)

§14.8 fixture를 CI와 activation에서 실행한다. 실패 1건 = blocker. (REQ-NRM-005)

### 45.4 Metamorphic Test

- Candidate-generation invariant: 허용 조사(연쇄 포함) 추가, 허용 spacing/punctuation 변형, 지원 범위 keyboard typo, prefix 부착, 무관 문장 추가 후에도 gold candidate가 사라지지 않는다.
- Ranking expectation: document-local 정의 시 해당 sense score 상승 방향, domain evidence 추가 시 ranking 개선 가능.
- Commit behavior: 추가 문맥에 따라 commit이 바뀔 수 있으므로 "무관 문장 추가 시 top-1 불변" 같은 강한 invariant는 두지 않는다.

### 45.5 Unicode/Offset Fuzzing

NFC/NFD 혼합, 호환 자모, combining mark, zero-width, emoji, 보충 평면 문자, variation selector, 전각 Latin, malformed UTF-8(→ INVALID_UTF8 확인), 긴 combining sequence. raw byte ↔ codepoint ↔ UTF-16 ↔ substring 왕복 검증.

### 45.6 Candidate Explosion / Concurrency / Security / Artifact Test

v0.2 §41.5~41.8을 유지하고 다음을 추가한다: 조사 연쇄 pathological 입력(`한전에서부터까지도...`)의 depth cap 검증, 비동기 job 중 activation 발생 시 snapshot 고정(INV-017), correction API 권한·tenant 격리, warm/evict 경합.

### 45.7 요구사항 추적성 검증 (v0.3 신규)

CI는 `docs/traceability.yaml`을 읽어 모든 REQ-* ID가 최소 1개 테스트에 매핑되어 있는지 검사한다. 매핑 누락 또는 존재하지 않는 테스트 참조는 CI 실패다. (REQ-EVAL-003)

### 45.8 Golden Set

tenant별 수동 검증 세트를 유지하고 training/self-training에 사용하지 않는다. 구축 절차는 §48.6.

---

## 46. 관측성

### 46.1 Runtime Metric

v0.2 지표를 유지하고 다음을 추가한다: mode별(fast/aggressive/commit) 요청 비율과 latency, Pass 2 실행률, 비동기 job 큐 길이·처리 시간, tenant tier 분포와 cold-start latency(§32), correction 제출·승인율, empirical coverage 대비 목표 편차.

### 46.2 Offline Quality Metric

candidate source별 gold 기여, majority-sense bias, rare-sense recall, Level A/B/C, unseen split별 성능, KB-missing vs NON_TERM confusion, calibration drift, glossary update regression, quantization regression, conformance 실패 이력.

### 46.3 Trace와 Logging Privacy

- 권한 있는 debug mode에서 mention별 proposal source, normalization path, matched segments, boundary 결과, parse 결과, candidate source, feature/score, calibrated probability, prediction-set 사유, budget truncation, snapshot version, retrieval_pass를 기록할 수 있다.
- "어떤 문맥이 기여했는가"는 attention 기반 사실 설명으로 제공하지 않고 검증 가능한 provenance만 제공한다.
- 원문 전체 로깅은 기본 비활성화한다. 기본 로그: hash된 request ID, span 길이, alias family ID, Entity ID, score/budget/latency, snapshot. 원문·context 저장은 tenant opt-in 정책이 필요하다(§30.2 연계).

### 46.4 Audit

glossary 관리, correction 검토, warm/evict, teacher 사용은 audit log 대상이다.

---

## 47. 보안과 개인정보

### 47.1 Trust Boundary

```text
Client → authentication → API Gateway → trusted tenant identity
→ Resolver Runtime → authorized snapshot only → Tenant Artifact Store
```

ML model은 authorization enforcement를 담당하지 않는다.

### 47.2 Tenant Isolation

candidate index, vector index, cache, calibration, document-local alias, correction queue, debug output 어디에도 타 tenant 데이터가 섞이지 않는다.

### 47.3 Glossary Supply Chain

compiled artifact에 checksum, schema version, publisher/tenant metadata, optional signature, compatibility 검증을 적용한다. 검증 실패 artifact는 activation 금지.

### 47.4 Model Supply Chain

model bundle 해시 고정, 서명 검증(선택), 학습 데이터 provenance 기록.

### 47.5 Alias Poisoning

문서 내부 정의가 global glossary를 수정할 수 없고(INV-008/009), correction도 자동 반영되지 않는다(INV-018). glossary 편집은 권한·감사 대상이다.

### 47.6 개인정보

입력 문서는 처리 목적 외 저장하지 않는 것을 기본으로 한다. correction의 원문 저장은 opt-in(§30.2). 관련 법규(PIPA 등) 준수는 배포 조직 정책과 연계한다.

### 47.7 Glossary Content Injection (v0.3 신규)

- **위협:** Entity `description`/`canonical`/`examples`는 §49.2를 통해 downstream LLM 프롬프트에 주입된다. glossary 편집 권한자(또는 승인 우회 경로)가 description에 지시문을 삽입하면 프롬프트 주입 벡터가 된다.
- **대응:**
  1. compiler content lint: 지시문 패턴, 제어 문자, 태그 문자, 과도한 길이를 경고/오류 처리(§10.8).
  2. terminology injection 시 구조적 이스케이프 의무: 속성값·본문의 XML/구분자 이스케이프, description 길이 상한(권장 500자), CDATA 사용 금지. raw 문자열 그대로 삽입해서는 안 된다. (REQ-SEC-001)
  3. downstream 통합 가이드: resolved_terms 블록은 데이터로 취급한다는 정책 문구를 프롬프트에 포함할 것을 권장한다.
  4. glossary 편집 이력 audit와 권한 최소화.

---

## 48. Zero-Training과 조직 온보딩

### 48.1 Zero-Training 정의

새 tenant는 재학습 없이 glossary compile만으로 Level A 전체와 global 기본 모델·conservative calibration을 사용한다.

### 48.2 온보딩 절차

```text
glossary 작성 → validate → compile → diagnostics 검토
→ conformance 통과 → activate → (선택) warm → 운영
```

### 48.3 품질 개선 루프

운영 중 correction(§30) 축적 → 승인 → tenant calibrator 재생성 → (선택) adapter 학습 → golden set 회귀 통과 후 활성화.

### 48.4 Adapter 정책

tenant adapter는 base model을 변경하지 않는 부가 구성(LoRA 등)으로 두고, compatibility manifest에 기록한다.

### 48.5 Glossary 작성 가이드 요점

다의 alias에는 구분 신호(description/type/domain/examples) 필수 권장, 짧은 alias boundary policy 명시, scope는 allow/deny 의미(§10.5)에 따라 최소한으로.

### 48.6 Golden Set 구축과 IAA (v0.3 신규)

- 규모: critical slice당 최소 표본 n≥200에서 시작해 §43.8 CI 요구를 만족하도록 확장한다.
- 절차: 이중 annotation → adjudication. teacher는 사전 후보 제시에만 사용하고 최종 gold는 인간 adjudication을 거친다.
- IAA 기준: mention core-span F1과 sense 선택 Cohen's κ를 측정하고, sense κ ≥ 0.75를 권장 기준으로 한다. 미달 slice는 annotation guide를 개정하고 재작업한다.
- gold가 단일 sense로 강제되지 않는 경우 AMBIGUOUS gold(허용 sense 집합)를 허용한다.
- golden set은 학습·self-training에 사용하지 않는다.

---

## 49. RAG와 LLM 챗봇 통합

### 49.1 위치

Resolver는 LLM 앞단의 terminology grounding 계층이다. 검색 인덱싱·질의 확장에는 fast/aggressive, 답변 표시·자동화에는 commit을 사용한다.

### 49.2 Terminology Injection (이스케이프 적용)

```xml
<resolved_terms snapshot="organization-a:2026-08-23.1">
  <term surface="AP" entity_id="NETWORK_ACCESS_POINT"
        canonical="Access Point" probability="0.96"
        description="무선 단말을 유선 네트워크에 연결하는 네트워크 장비" />
</resolved_terms>
```

- 모든 속성값과 본문은 XML 이스케이프를 거쳐야 하며(REQ-SEC-001), description은 길이 상한을 적용해 잘라 넣는다.
- 이 블록은 downstream LLM에 "데이터"로 제공되며 지시문으로 해석되지 않도록 프롬프트 정책을 함께 배포할 것을 권장한다.
- AMBIGUOUS mention은 prediction set 전체(또는 상위 k)를 넣고 단일 canonical로 강제하지 않는다.

### 49.3 원문 치환 금지

Resolver는 원문을 canonical로 자동 치환하지 않는다. 치환은 downstream이 commit 결과와 정책을 확인한 후 수행한다.

---

## 50. 저장소 구조 (권장 monorepo)

```text
ktrf/
├── core-rs/            # Rust runtime core (offset, index, FST, snapshot)
├── compiler/           # glossary compiler + conformance fixture 생성
├── service/            # API layer (sync/async/mgmt/correction)
├── models/             # 학습 파이프라인, teacher, calibration
├── eval/               # 지표, slice, golden set 도구, benchmark
├── docs/
│   ├── spec/           # 본 문서
│   └── traceability.yaml
└── ops/                # 배포, 관측, capacity
```

---

## 51. 구현 단계

### 51.1 마일스톤

| 단계 | 내용 | 완료 기준 요점 |
|---|---|---|
| M0 | 스키마·offset 계약·annotation guide·traceability 골격 | offset fixture, REQ 목록 확정 |
| M1 | Rust core: normalization, exact index, boundary, tail/prefix FST, fuzzy, snapshot | conformance suite 100%, Level A gate |
| M2 | compiler·동기 API·오류 스키마·budget·tenant 격리 | §27 계약 전체, security test |
| M3 | 비동기 API·correction API·관측성·메모리 tier | §28/§30/§32 계약, concurrency test |
| M4 | V2 신경 구성: bi-encoder, cross-encoder, fusion, calibration | Level B gate, conformal coverage |
| M5 | fast 모드 최적화·benchmark·release gate 자동화 | §53 benchmark 문서, gate CI |
| M6 | Level C proposer(flag)·adaptation 루프 | tenant holdout 평가 |

### 51.2 개략 공수 추정 (informative)

아래는 계획 수립용 참고치이며 normative가 아니다. 전제: Rust 엔지니어 2, ML 엔지니어 2, 데이터/annotation 리드 1(겸임 PM). 불확실성 ±50%.

```text
M0: 3–5주    M1: 10–14주   M2: 8–12주 (M1과 부분 병행 가능)
M3: 6–10주   M4: 10–14주 (연구 불확실성 최대)
M5: 5–8주    M6: 5–8주
```

순차 진행 시 총 12–17개월 규모이며, M2의 데이터 준비를 M1과 병행하면 단축할 수 있다. M1 종료 시점에 재추정할 것을 권장한다.

---

## 52. 주요 위험과 대응

| # | 위험 | 대응 |
|---|---|---|
| 52.1 | 짧은 alias 후보 폭발 | 길이별 fuzzy 정책, boundary 강화, budget |
| 52.2 | majority sense collapse | sense-balanced sampling, prior clipping, rare-sense slice gate |
| 52.3 | distant supervision 오라벨 | partial label, sense UNLABELED, teacher validator |
| 52.4 | normalization 폭발 | channel 분리, materialize 금지 |
| 52.5 | teacher 오염/환각 | allowlist, validator, 승인 워크플로 |
| 52.6 | metric gaming | 쌍 지표, conditioning 표기, slice gate |
| 52.7 | glossary 품질 편차 | strict validation, diagnostics, 작성 가이드 |
| 52.8 | snapshot 혼합 | pin, atomic activation, concurrency test |
| 52.9 | tenant 격리 실패 | cache key 계약, security test, audit |
| 52.10 | calibration drift | invalidating change 목록, empirical coverage 모니터링 |
| 52.11 | 장문/폭주 입력 자원 고갈 | budget, degraded, 비동기 강제 |
| 52.12 | self-training 편향 증폭 | §41 안전장치 |
| 52.13 | **조사 연쇄 과생성** (v0.3) | FST depth cap(기본 3), explosion test, 실측 조정(OQ-001) |
| 52.14 | **correction 오염** (v0.3) | 승인 워크플로, verifier 등급·수량 상한, tenant 격리(§30.3) |
| 52.15 | **cold tenant latency 스파이크** (v0.3) | tier 정책, warm-up API, cold-start SLA 관측(§32, OQ-004) |
| 52.16 | glossary content injection | §47.7 lint + 이스케이프 의무 |

---

## 53. 성능 Benchmark 계획

기준 하드웨어(예: 16 vCPU CPU-only / 단일 24GB GPU)별로 다음을 측정해 별도 문서로 발행한다: fast/aggressive/commit p50/p95/p99 latency, 처리량, glossary 크기별(10k/100k/500k) 메모리·latency 곡선, cold-start 시간, 비동기 처리율, Pass 2 실행 비용. 이 문서가 §5.3의 SLO 수치와 OQ-002/004/005의 해소 근거가 된다.

---

## 54. 운영과 버전 관리

- 버전 축: glossary_version, model_bundle_version, normalizer/morphology version, calibrator version, schema_version. 응답에 항상 노출.
- Calibrator 재검증 트리거: 다의어 sense 추가/삭제, alias collision 구조 변화, description 변경, candidate/ranking/normalizer/embedding/fuzzy 변경 (v0.2 목록 유지).
- 재생성 절차: correction 라벨 축적 → offline 재계산 → shadow 평가 → activation.
- Rollback: 이전 검증 snapshot으로 atomic 전환. calibrator/adapter도 snapshot 단위로 함께 되돌린다.
- 운영 runbook: conformance 실패, coverage 미달, cold-start 급증, correction 큐 적체 각각의 대응 절차를 문서화한다.

---

## 55. 최종 권장 온라인 구성

| 단계 | 구성 |
|---|---|
| V1 | Rust symbolic core + fast/aggressive/commit(휴리스틱 fusion) — zero-GPU |
| V2 | + bi-encoder retrieval + learned fusion + group-conditional conformal calibration |
| V3 | + cross-encoder + termness classifier |
| V4 | + neural mention proposer (feature flag) + document context |

각 단계는 이전 단계의 결정적 경로를 제거하지 않는다.

---
## 56. 규범 결정 사항

본 목록이 KTRF의 유일한 규범 결정 목록이다. 본문과 불일치가 발견되면 본 목록이 우선하며, 불일치는 결함으로 등록한다. 1~45는 v0.2 결정의 carry(문구 정비 포함), 46~60은 v0.3 신규다.

1. canonical 문자열은 생성하지 않고 glossary Entity ID 선택으로만 결정한다.
2. 문장당 단일 라벨이 아니라 mention 집합을 예측하며 overlapping/nested를 지원한다.
3. Surface resolution과 sense resolution을 분리하고 모델이 고정 Entity ID를 암기하지 않게 한다.
4. Alias 변형은 열거하지 않고 representative + normalization profile에서 유도한다.
5. 상태는 `mention_decision × link_decision` 2축으로 표현한다.
6. 내부 span 기준은 UTF-8 byte 반개구간 `[start, end)`다.
7. API는 byte/codepoint/UTF-16 offset을 함께 제공한다.
8. `text[codepoint_start:codepoint_end] == surface` invariant를 모든 fixture에서 검증한다.
9. exact alias에 연결된 모든 sense는 내부 후보 pool에 보존한다.
10. 어떤 budget도 exact pool을 자르는 데 사용할 수 없다.
11. 한 요청(비동기 job 포함)은 하나의 immutable snapshot만 사용한다.
12. glossary activation은 atomic이며 실패 시 이전 snapshot을 유지한다.
13. compatibility mismatch가 있으면 activation을 거부한다.
14. tenant는 인증 컨텍스트로 결정하고 cross-tenant 데이터 노출을 금지한다.
15. cache key에는 tenant와 버전 축이 필수다.
16. 서버가 검증하지 않은 metadata만으로 candidate를 hard-filter하지 않는다.
17. document-local alias는 scope 밖에 저장되지 않고 global binding을 overwrite하지 못한다.
18. fuzzy/neural 결과는 exact 결과를 overwrite하지 않는다.
19. `ranking_score`와 확률 필드를 분리하고 calibrator 미통과 값을 확률로 노출하지 않는다.
20. 1~2자 alias의 일반 edit fuzzy는 기본 비활성화한다.
21. normalization은 원문을 파괴하지 않으며 전역 NFKC를 금지하고 channel을 분리한다.
22. 변형 조합의 데카르트 materialize를 금지한다.
23. 조사·어미는 FST 기반 tail parsing으로 처리한다.
24. extension 확정 우선순위는 full exact alias > COMPOSES_TO relation > heuristic candidate다.
25. proposal 단계에서 일반 NMS를 금지하고 mention graph로 보존한다.
26. primary mention 선택은 §20.4의 우선순위와 tie-break 규칙을 따른다.
27. dense retrieval은 trigger 조건에서만 조건부 실행한다.
28. cross-encoder는 조건부 실행한다.
29. popularity prior는 clipping하며 후보 삭제 조건이 아니다.
30. `KB_MISSING`과 `NON_TERM`을 구분한다.
31. commit은 calibrated threshold와 prediction set 규칙을 따른다.
32. 검색용(고recall)과 확정용(고precision) 결과를 분리 제공한다.
33. Resolver는 원문을 canonical로 자동 치환하지 않는다.
34. 온라인 경로에서 생성형 LLM을 호출하지 않으며 teacher는 오프라인 전용이다.
35. teacher 데이터는 candidate-constrained 입력과 validator 통과분만 사용한다.
36. distant supervision에서 unmatched는 UNLABELED, 다의 alias의 sense는 UNLABELED로 둔다.
37. 데이터 혼합 비율은 normative가 아니며 실험 config다.
38. calibration용 평가 세트는 실제 분포를 보존한다.
39. self-training은 §41 안전장치 하에서만 수행하고 golden set을 학습에 사용하지 않는다.
40. 평가는 UA/UE-listed/UE-canonical-only/UE-derived-abbrev/US-new-sense/KB-missing/시간/tenant holdout 분할을 사용한다.
41. release gate는 confidence interval, failure count, slice별 최소 표본을 포함한다.
42. budget/timeout 초과는 오류가 아니라 `degraded=true`로 노출한다.
43. 클라이언트 요청 옵션으로 내부 안전 한계를 확장할 수 없다.
44. 원문 전체 로깅은 기본 비활성화한다.
45. 모든 결과는 snapshot 버전 정보와 함께 반환한다.

**v0.3 신규**

46. `calibrated_probability`는 후보별 marginal이며 prediction set 내 정규화 posterior가 아니다. 클라이언트 합산 사용을 금지한다.
47. prediction set은 group-conditional split conformal로 구성하고 `set_confidence`(1−α)를 응답에 노출한다. 그룹 표본 부족 시 상위 그룹으로 fallback한다.
48. `link_decision = UNCERTAIN`은 set-level 보장을 주장하지 않는 상태이며, mention_decision UNCERTAIN은 RESOLVED로 commit되지 않는다.
49. scope `deny`는 SERVER_VERIFIED/AUTH_CLAIM context에서만 hard filter이고, `allow` 불일치는 항상 soft다. context 부재 시 중립이다.
50. 기본 normalization profile(§14.6)과 지원 변형 카탈로그(§14.7)는 normative이며, 카탈로그 내 변형의 conformance 실패는 release/activation blocker다.
51. `max_non_exact_candidates`(구 max_internal_candidates)는 exact pool에 적용되지 않으며, exact 초과는 §21.5 절차만 허용된다.
52. 조사 결합형은 열거하지 않고 개별 조사 + 연쇄 규칙의 FST 합성으로 처리하며 depth 상한을 둔다.
53. 조사·suffix 동형 충돌 시 두 분석을 모두 proposal로 보존하고 선택은 ranking에 위임한다.
54. prefix modifier는 core span에 포함하지 않고 별도 필드로 반환하며 core candidate를 제거하지 않는다.
55. 동기 API 입력 상한은 64KB(기본)로 낮게 유지하고 장문은 비동기 job API로 처리한다. malformed UTF-8은 수리하지 않고 INVALID_UTF8을 반환한다.
56. correction은 승인 전 어떤 산출물에도 반영되지 않으며 glossary를 자동 수정하지 않는다.
57. terminology injection 페이로드는 구조적으로 이스케이프해야 하며 raw 삽입을 금지한다.
58. 모든 REQ ID는 테스트에 매핑되어야 하며 매핑 누락은 CI 실패다.
59. 모든 품질 지표는 conditioning(E2E/|mention/|candidate/|commit)을 명시한다.
60. snapshot artifact는 mmap 친화 포맷으로 배포하고 tenant tier(hot/warm/cold) 상주 정책과 refcount 보호 eviction을 적용한다.

---

## 57. Open Questions

미해결 항목을 명시적으로 관리한다. 각 항목은 해소 조건과 함께 추적한다.

| ID | 질문 | 해소 조건 |
|---|---|---|
| OQ-001 | 조사 연쇄 FST depth 상한(기본 3)과 과생성 통제 수치의 적정값 | 실 corpus 연쇄 분포 측정 + explosion test |
| OQ-002 | fast 모드 p99 latency 목표 수치 | 기준 하드웨어 benchmark(§53) |
| OQ-003 | conformal calibration 그룹 세분성 vs 표본 확보 트레이드오프 | 그룹별 coverage 편차 실측 |
| OQ-004 | cold tenant 첫 요청 latency SLA | tier 구현 후 실측 |
| OQ-005 | 동기 입력 상한 64KB의 적정성 | 실제 요청 크기 분포 |
| OQ-006 | `latin_morph` profile 기본값(acronym에서 off가 맞는가) | APs류 오탐/미탐 실측 |
| OQ-007 | correction 자동 수용 조건 도입 여부(현재 전량 수동 승인) | 오염율·검토 부하 데이터 축적 후 재검토 |
| OQ-008 | 세벌식 키보드 채널 지원 여부 | 사용자 분포 조사 |
| OQ-009 | prefix modifier(전/구)의 entity 시제 해석 downstream 계약 | downstream 제품 요구 정의 |
| OQ-010 | vector index의 multi-node 전환 임계점 | glossary 규모·QPS 성장 관측 |

---

## 부록 A. 예제 Glossary (schema_version 3)

```yaml
glossary_id: demo-org
version: 2026-08-23.1
schema_version: "3"

normalization_profiles: []        # 시스템 기본 5종 사용 (§14.6)

entities:
  - entity_id: ORG_KEPCO
    canonical: 한국전력공사
    description: 대한민국의 전력 공기업
  - entity_id: NETWORK_ACCESS_POINT
    canonical: Access Point
    description: 무선 단말을 유선 네트워크에 연결하는 네트워크 장비
    domain_ids: [NETWORK]
  - entity_id: WORKFLOW_APPROVAL_PROCESS
    canonical: Approval Process
    description: 결재 승인 업무 절차
    domain_ids: [WORKFLOW]
  - entity_id: SYSTEM_QUALITY_MANAGEMENT
    canonical: Quality Management System
    description: 품질 관리 시스템
    domain_ids: [QUALITY]

alias_families:
  - family_id: FAMILY_KEPCO_KR
    representative: 한전
    normalization_profile: korean_org_name
  - family_id: FAMILY_AP
    representative: AP
    normalization_profile: latin_acronym
  - family_id: FAMILY_QMS
    representative: QMS
    normalization_profile: latin_acronym

alias_bindings:
  - alias_id: KEPCO_KR
    family_id: FAMILY_KEPCO_KR
    entity_id: ORG_KEPCO
    surface: 한전
    kind: abbreviation
    boundary_policy: {left: hangul_token_boundary, right: particle_or_token_boundary}

  - alias_id: AP_NETWORK
    family_id: FAMILY_AP
    entity_id: NETWORK_ACCESS_POINT
    surface: AP
    kind: abbreviation
    boundary_policy: {left: latin_token_boundary, right: particle_or_token_boundary,
                      allow_inside_latin_run: false}
    scope:
      allow: {departments: [network]}
      deny: {}

  - alias_id: AP_APPROVAL
    family_id: FAMILY_AP
    entity_id: WORKFLOW_APPROVAL_PROCESS
    surface: AP
    kind: abbreviation
    boundary_policy: {left: latin_token_boundary, right: particle_or_token_boundary,
                      allow_inside_latin_run: false}

  - alias_id: QMS_SYSTEM
    family_id: FAMILY_QMS
    entity_id: SYSTEM_QUALITY_MANAGEMENT
    surface: QMS
    kind: abbreviation
    boundary_policy: {left: latin_token_boundary, right: particle_or_token_boundary}
```

---

## 부록 B. Annotation 예

각 예의 offset은 codepoint 기준이며 `text[start:end] == surface`를 만족한다.

**B.1 exact + 조사**

```json
{"text": "QMS에 결과를 등록했다.",
 "mentions": [{"surface": "QMS", "core_span": {"codepoint": {"start": 0, "end": 3}},
   "particle": "에", "mention_decision": "TERM", "link_decision": "RESOLVED",
   "entity_id": "SYSTEM_QUALITY_MANAGEMENT"}]}
```

**B.2 다의어 AMBIGUOUS**

```json
{"text": "AP 처리가 지연되고 있습니다.",
 "mentions": [{"surface": "AP", "core_span": {"codepoint": {"start": 0, "end": 2}},
   "mention_decision": "TERM", "link_decision": "AMBIGUOUS",
   "prediction_set": ["NETWORK_ACCESS_POINT", "WORKFLOW_APPROVAL_PROCESS"]}]}
```

**B.3 KB-Missing 후보**

```json
{"text": "액포 장애 건 확인 부탁드립니다.",
 "mentions": [{"surface": "액포", "core_span": {"codepoint": {"start": 0, "end": 2}},
   "mention_decision": "UNCERTAIN", "link_decision": "KB_MISSING"}]}
```

**B.4 소문자 변형**

```json
{"text": "ap라는 약어가 무슨 뜻인가요?",
 "mentions": [{"surface": "ap", "core_span": {"codepoint": {"start": 0, "end": 2}},
   "mention_decision": "TERM", "link_decision": "AMBIGUOUS"}]}
```

---

## 부록 C. 구현 우선순위 요약

1. offset 계약과 conformance fixture 파이프라인 (모든 것의 기반)
2. exact index + boundary + tail/prefix FST (Level A의 몸통)
3. snapshot/tenant/budget 계약 (운영 안전)
4. 동기 API + 오류 스키마 → 비동기 API → correction API (피드백 루프 확보)
5. fuzzy/keyboard 채널
6. bi-encoder retrieval + conformal calibration (Level B)
7. cross-encoder, termness (commit 품질)
8. Level C proposer (flag)

---

## 부록 D. 요구사항-테스트 추적성 매트릭스

전체 매트릭스는 `docs/traceability.yaml`로 관리하며 CI가 검증한다(REQ-EVAL-003). 형식과 예시:

```yaml
# docs/traceability.yaml
- req: REQ-LVL-002
  tests: [compiler/tests/conformance_suite.rs]
- req: REQ-INV-005          # exact pool budget 면제
  tests: [core-rs/tests/property/exact_sense_preservation.rs,
          core-rs/tests/unit/candidate_pool.rs]
- req: REQ-OFF-001
  tests: [core-rs/tests/unit/offset_mapping.rs, core-rs/tests/fuzz/unicode_offsets.rs]
- req: REQ-NRM-001          # normalization 우선순위
  tests: [compiler/tests/unit/profile_precedence.rs]
- req: REQ-BND-002          # boundary FST prefix-accept
  tests: [core-rs/tests/unit/boundary_particle_fst.rs]
- req: REQ-TAIL-003         # 동형 충돌 복수 분석 보존
  tests: [core-rs/tests/unit/particle_suffix_collision.rs]
- req: REQ-CAND-004         # Pass 2 단일 실행·보존
  tests: [service/tests/integration/two_pass_retrieval.rs]
- req: REQ-CAL-001          # marginal 의미론
  tests: [models/tests/calibration_semantics.py]
- req: REQ-API-006          # 비동기 동일 snapshot
  tests: [service/tests/concurrency/async_snapshot_pin.rs]
- req: REQ-COR-001          # 승인 전 미반영
  tests: [service/tests/integration/correction_workflow.rs]
- req: REQ-SEC-001          # injection 이스케이프
  tests: [service/tests/security/terminology_injection_escape.rs]
```

규칙: (1) 모든 REQ는 1개 이상 테스트에 매핑, (2) 존재하지 않는 테스트 경로 참조는 실패, (3) REQ 삭제는 §0 changelog에 기록.

---

*문서 끝 — KTRF 기술 스펙 v0.3*
