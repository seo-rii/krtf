# 모드 설명과 평가 결과

2026-10-16. 실행 모드 설명은 `a050ead`의 구현을 기준으로 하며, 이후 runtime의
모드 분기는 바뀌지 않았다. 외부 HF 추가 평가는 `512e9bc`에서 측정했다.

KTRF의 실행 모드, LLM 프로필, 벤치마크의 컨텍스트 조건, 후보 재순위화의
입력 구성을 구분해야 한다. 예를 들어 `commit + qa_grounding`은 현재 API에서
사용할 수 있지만, `nano + scoped_asserted`는 별도 실험 구성이다.

## 1. Resolver 실행 모드

`resolve(..., mode=...)`와 `prepare_llm_context(..., mode=...)`가 받는 값이다.

| 모드 | 현재 구현 | 사용 판단 |
|---|---|---|
| `fast` | 정확한 표기, 공유 형태 분해, 문서 내 정의·별칭 등 결정적 경로를 사용한다. fuzzy·약칭 추론·dense 검색·신경 재순위화·확률 보정을 생략한다. exact 후보를 우선한 후보 집합에서 entity가 하나면 `RESOLVED`, 여러 개면 `AMBIGUOUS`로 반환한다. | 저지연 용어 표시·검색 보조용. 점수와 margin을 검사하는 확정 경로를 거치지 않으므로 더 안전한 모드로 해석하면 안 된다. |
| `commit` | 설정된 exact/fuzzy/약칭/dense 후보 생성, 조건부 재순위화와 점수 계산을 수행한다. 후보 간 margin, 임계값, 의미 guard, 검색 후보 잘림 등을 검사해 확정하거나 보류한다. | 일반 운영의 기본값. 자동 실행에는 별도의 프로필·출력 검증과 업무상 검토가 필요하다. |
| `aggressive` | 현재 `commit`과 같은 분기와 임계값을 사용한다. | 현재 구현에 근거해 더 높은 recall이나 더 낮은 precision을 주장할 수 없다. |

설계 문서의 모드별 목표와 현재 구현을 구분한다. 현재 코드에서 `aggressive`와
`commit` 사이의 판단 차이는 구현되어 있지 않다. 추가 KBMC 평가에서는 512문서의
mention 응답이 두 모드에서 모두 같았다. 정확한 span 회수는 `fast` 782/1,424(54.92%),
`commit/aggressive` 798/1,424(56.04%)였다. 정답 경계에 놓인 확정 출력은 모두
725건이며, entity ID 의미 정확도는 평가하지 않았다.
[외부 HF 보고서](../reports/HF_BENCHMARK.md)에서 사전 범위와 지연 비용을 함께 확인한다.

`commit`을 선택해도 encoder나 reranker가 자동으로 설치·활성화되지는 않는다.
신경 경로는 snapshot에 해당 backend를 설정했을 때 사용한다. fitted calibrator가
없는 점수는 heuristic이며, `RESOLVED`나 기본 설정이 통계적 정확도 보장을 뜻하지
않는다. 보정 상태와 coverage 해석은 [CALIBRATION_SAFETY.md](CALIBRATION_SAFETY.md)를
참조한다. 모든 모드에서 core 연결과 전체 표면형의 의미를 구분해야 한다.

구현: [resolver.py](../ktrf/resolver.py), [snapshot.py](../ktrf/snapshot.py).

## 2. LLM context pack 프로필과 답변 정책

`ContextPolicy(profile=...)`는 resolver 임계값을 바꾸지 않는다. 확정 결과와
후보를 LLM에 어떻게 노출하고 어떤 용도로 쓰게 할지를 정한다.

| 프로필 | 목적과 현재 동작 | 평가에서 확인할 점 |
|---|---|---|
| `qa_grounding` | 용어 설명·문서 QA용. 제공 문맥이 전체 대상 표현에 대해 한 후보를 유일하게 뒷받침하면 모호한 후보도 설명할 수 있다. 답변이 resolver의 확정 연결로 승격되지는 않는다. | 답변 정확도와 자동 실행 가능한 ID 수를 분리한다. |
| `automation` | 자동 치환·조직 연결·구조화 필드 입력용. 모호한 후보를 제외하고 근거 중심 정책을 강제한다. | 정확한 전체 표면형에 대응하는 확정 연결을 출력 검증기로 검사한다. QA 답변·자체 지식·후보 포함 여부만으로 실행 권한을 얻지 못한다. |
| `summarization` | 요약에서 용어 의미를 보조하기 위한 프로필. 현재 공통 pack 생성 로직과 일반 용어 정책을 사용한다. | 별도 요약 알고리즘이나 독립적인 요약 품질 개선이 입증된 것은 아니다. |
| `rag_query_expansion` | 검색어 확장에 사용할 용어 정보를 제공하기 위한 프로필. 현재 공통 pack 생성 로직과 일반 용어 정책을 사용한다. | 별도의 검색 확장 엔진이나 독립적인 검색 성능 향상이 구현·검증된 것으로 해석하지 않는다. |

`answer_policy="evidence_only"`가 기본값이다. 제공 근거로 판단하며, 기본 QA는
외부 지식으로 후보를 고르지 않는다. `answer_policy="knowledge"`는 사람에게
설명할 때 일반 지식 사용을 명시적으로 허용한다. 이 경우에도 설명을 검증된 연결로
표시하거나 실행 권한으로 사용해서는 안 된다. `automation`은 설정과 관계없이
`evidence_only`로 동작한다.

QA와 자동 실행은 별도 LLM 호출·대화로 분리하고, 자동 실행 응답 전체에
`validate_llm_grounding(..., purpose="execution")`을 적용한다. 검증기는 resolver가
이미 잘못 확정한 의미까지 모두 교정하지는 않는다. 실제 문장 평가에서 잘못된
ID 두 건이 실행 검증을 통과했으므로, 무검토 자동 실행의 안전성을 주장하지 않는다.
근거: [production 분석](../reports/production_queue_20261013T160054Z/ANALYSIS.md),
[일반 검색과의 비교](../reports/baseline_queue_20261013T234553Z/ANALYSIS.md).

구현: [context.py](../ktrf/context.py). QA/automation 측정 계약은
[PRODUCTION_GROUNDING.md](PRODUCTION_GROUNDING.md)에 있다. 네 프로필 전체를
독립적으로 비교한 성능 순위는 없다.

## 3. 컨텍스트 없음·전체 문서·검색·KTRF 비교

문서 컨텍스트 벤치마크는 다음 두 축을 교차한 **12개 조건**이다.

| 축 | 조건 | 실제 제공 자료 |
|---|---|---|
| 지식 자료 | `None` | 용어 정의·사전 지식 자료를 제공하지 않는다. |
| 지식 자료 | `Full` | 해당 family의 지식 문서 전체를 제공한다. |
| 지식 자료 | `Retrieved` | 지식 문서에서 lexical 검색으로 고른 문단을 제공한다. |
| 지식 자료 | `KTRF` | 같은 사전 사실로 만든 실제 QA/automation context pack과 정책을 제공한다. |
| 원본 문서 | `None` | 질문과 대상 표현만 제공한다. |
| 원본 문서 | `Full` | 판단 대상이 들어 있는 원본 문서 전체를 제공한다. |
| 원본 문서 | `Retrieved` | 대상 관련 문단과 인접 문단을 선택해 제공한다. |

따라서 `KTRF + Full`은 KTRF 용어 pack과 원본 문서 전체를 함께 주는 조건이다.
`Full + Full`은 지식 문서 전체와 원본 문서 전체를 주는 조건이다. 사내 정의와
불투명 ID를 모르는 `None + None`은 정보가 없는 하한 조건이며, 같은 정보를 가진
검색 대조군과 동등한 기준선은 아니다.

이 평가는 알려진 원본 문서 안에서 문단을 선택한다. 전체 문서 집합에서 정답
문서를 찾아오는 검색 성능은 측정하지 않는다. 32개 AI 작성 문서에 대한 결과이며,
정의 QA의 완전 일치 채점에는 의미 이해 외에 정의의 표시 형식과 추출 난이도도
영향을 준다. 실제 QA 성능이 일반 검색보다 일관되게 좋다는 결론은 나오지 않았다.

설계: [DOCUMENT_CONTEXT.md](DOCUMENT_CONTEXT.md).
결과: [문서 컨텍스트 분석](../reports/document_context_queue_20261014T024026Z/ANALYSIS.md).
후속 형식 통제 설계: [DEFINITION_CONTROL.md](DEFINITION_CONTROL.md).

추가 외부 자료 비교는 [HF_BENCHMARK.md](HF_BENCHMARK.md)에 있다. KBMC에서는
외부 경계 정답을 대상으로 literal/fast/commit/aggressive를 비교하고, TyDiQA에서는
전체 원문과 검색 구간에 정답 근거가 남는지 검사한다. 후자의 `ktrf_expanded`는
질문의 확정 용어로 검색어를 보조하는 조건이며, 위 production context pack 조건과
다르다. LLM 답변 정확도를 새로 측정한 것으로 합산하지 않는다.
TyDiQA 256질문의 최소 정답 위치 보존은 일반 검색과 KTRF 확장 검색 모두
39/79(49.37%)였다. 확장은 4질문에서만 일어났고 정답 근거 보존 개선은 없었다.
전체 원문의 79/79는 구성상 정보 상한이며 LLM 정답률이 아니다.
실제 답변 정답률의 후속 비교는 [HF_LLM_QA.md](HF_LLM_QA.md)에서 여섯 조건을
정의한다. 자체 지식 조건과 근거 전용 조건을 구분하고, 두 모델의 전체 원문 토큰
용량을 확인한 동일 질문으로 생성 결과를 비교한다.
[Qwen 27B 생성 결과](../reports/hf_qa_queue_20261016/ANALYSIS.md)는 답변 가능한
64문항에서 전체 문서 45/64(70.31%), 검색 31/64(48.44%), KTRF pack 33/64(51.56%),
자체 지식 24/64(37.50%)다. Pack 개선 2건은 모두 YES/NO이고 SPAN은 같았다.
Pack은 검색 대비 무응답 형식 오류도 4건 늘었다. 따라서 이 결과만으로 KTRF가
일반 검색보다 우수하다고 결론내리지 않는다. Gemma는 첫 큐의 서버 시작 단계에서
실패했으므로 이 Qwen 보고서에는 12B/27B 비교가 없다. 별도 재실행 계획과 실제
상태 경로는 위 결과 문서에 기록한다.

## 4. 최근 후보 재순위화 실험의 입력 구성

다음 값은 운영 API의 `mode`나 LLM 프로필이 아니다. 이미 주어진 대상 위치와
두 후보를 비교할 때 어떤 원문을 점수 계산기에 주고, 어떤 추가 검사를 하는지
정하는 실험 variant이다.

| 구성 | 점수 계산에 주는 원문 | 제안 채택 조건 |
|---|---|---|
| `target_full` | 선택한 대상 위치를 표시한 원본 문서 전체 | 기존 점수·margin 규칙과 구조적 guard |
| `target_paragraph` | 대상이 있는 문단 전체 | 위와 같음 |
| `scoped_evidence` | 대상 문단과 선택 가능한 관련 보조 문단 최대 두 개 | 위와 같음 |
| `scoped_asserted` | `scoped_evidence`와 동일한 입력·동일한 점수 | 위 조건에 인용된 주장·부정·철회·명시적 모호성·미등록 대상 등을 검사하는 assertion veto 추가 |

관련 보조 문단은 모든 후보의 어휘를 기준으로 선택한다. 해당 section에서 같은
별칭이 인용 밖에 여러 번 등장하면 선택한 발생 위치의 문단 안으로 범위를
제한한다. 원문과 offset을 보존한다.
`scoped_asserted`의 검사는 제한된 어휘 규칙이다. 통과가 의미적 참임을 증명하지
않고, 관련 없는 부정·철회 때문에 올바른 연결을 보류하는 반례도 있다.

각 입력에 두 점수 계산기를 조합했다. `lexical`은 문자·자모 유사도 기반의
결정적 기준선이고, `nano`는 KURE-Reranker-nano의 문맥–entity 설명 쌍 점수다.
nano의 raw score를 확률로 해석하지 않는다. 이 둘은 답변을 생성하는 12B/27B LLM의
선택과도 별개다.

### 별도 작성한 held-out 합성 평가 결과

12개 신규 family, 144개 문서, 168개 대상 중 정답 연결 대상은 120개이고,
나머지 48개는 보류해야 하는 사례다. 오답 제안에는 이 48개에서 잘못 선택한
경우도 포함한다. '제안'은 실험의 점수·guard 규칙을 통과한 선택이며 운영
resolver의 `RESOLVED` 또는 실행 승인을 뜻하지 않는다.

| 점수 계산기 | 구성 | 연결 대상의 정답 1위 | 정답 제안 | 오답 제안 |
|---|---|---:|---:|---:|
| lexical | `target_full` | 51/120 | 3 | 9 |
| lexical | `target_paragraph` | 78/120 | 10 | 12 |
| lexical | `scoped_evidence` | 86/120 | 9 | 11 |
| lexical | `scoped_asserted` | 86/120 | 9 | 0 |
| nano | `target_full` | 61/120 | 4 | 21 |
| nano | `target_paragraph` | 90/120 | 41 | 12 |
| nano | `scoped_evidence` | 109/120 | 48 | 14 |
| nano | `scoped_asserted` | 109/120 | 48 | 2 |

이 실험에서 가장 유용한 균형은 **nano + `scoped_asserted`**였다. 정답 제안은
120개 중 48개(40%), 채택한 50개 중 정답은 48개(관측 정밀도 96%)였다.
96%는 전체 문서·서비스의 정확도가 아니다. lexical + `scoped_asserted`는 관측
오답이 0개지만 정답 제안도 9/120(7.5%)에 그쳤다.

이 평가는 대상 위치와 두 등록 후보가 미리 주어지고, LINK 정답은 후보에 포함되어
있어 mention 탐지와 운영 검색 누락을 측정하지 않는다. AI 작성·별도 AI 주석 검토 자료로, 사람 검증
gold나 운영 분포 감사가 아니다. 평가 후 이 집합은 이미 확인한 데이터이며, 규칙을
수정한 뒤 같은 집합을 새로운 독립 안전성 검증으로 사용할 수 없다.

두 nano 오답은 실제 모호성이 남은 사례다. 관측 오답 수나 96%만으로 허용 위험
한도를 충족했다고 볼 수 없고, 보고서의 위험 검사도 통과하지 못했다.
`coverage_valid=false`, `production_authorized=false`이며 **운영 resolver에는
아직 연결되지 않았다.** `resolve(mode="scoped_asserted")`는 유효한 호출이 아니다.

설계·구현: [OCCURRENCE_EVIDENCE.md](OCCURRENCE_EVIDENCE.md),
[occurrence_evidence.py](../ktrf/occurrence_evidence.py).
결과·잔여 오류·비용·한계:
[held-out 분석](../reports/occurrence_evidence_20261015T050659Z/ANALYSIS.md).

위 순위는 제안 품질에 대한 판단이다. 공유 서버에서 같은 scoped 입력의 측정
시간도 실행 순서에 따라 달랐으므로, 이를 안정적인 지연 순위나 운영 전체 처리
속도의 비교로 해석하지 않는다. 모델 로딩·운영 검색·후속 LLM 호출 비용도 별도다.

## 5. 현재 사용 구성

문서 QA·용어 설명은 `commit + qa_grounding`을 기본으로 시작한다.

```python
from ktrf import ContextPolicy, compile_snapshot, load_glossary, prepare_llm_context

snapshot = compile_snapshot(load_glossary("examples/demo_glossary.yaml"))
prepared = prepare_llm_context(
    snapshot,
    "한전KDN은 AP 장애 내용을 QMS에 등록했다.",
    query="이 문서에서 한전KDN은 무엇을 뜻하나?",
    mode="commit",
    context_policy=ContextPolicy(
        profile="qa_grounding", answer_policy="evidence_only"),
)
```

자동 입력·치환은 `commit + automation`과 별도 실행 응답 검증, 사람 확인을
조합한다. 낮은 지연이 중요한 용어 표시·검색 보조에는 `fast`를 고려할 수 있다.
nano + `scoped_asserted`는 사람이 검토할 후보를 개선하는 후속 통합 실험 대상으로
해석하며, 현재 운영 설정으로 제공된다고 안내하지 않는다.
