# 모드 설명과 평가 결과

2026-10-20. 실행 모드의 `fast`/`commit`/`aggressive` 구분은 유지한다.
아래 완료 수치는 각 보고서에 봉인된 측정 revision의 결과다. 오늘 보강한
발생 위치 검증·팩 생략·문서 QA 정책의 효과를 과거 결과에 소급하지 않는다.

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
| `qa_grounding` | 용어 정의·의미 구분 QA용. 제공 문맥이 전체 대상 표현에 대해 한 후보를 유일하게 뒷받침하면 모호한 후보도 설명할 수 있다. 답변이 resolver의 확정 연결로 승격되지는 않는다. | 답변 정확도와 자동 실행 가능한 ID 수를 분리한다. |
| `document_qa` | 일반 문서 QA용. 원문이 날짜·수치·사건 등의 답을 뒷받침하면 용어 정의가 없어도 답하고, 원문에 답이 없으면 기권한다. | 리뷰 후속 비교를 완료했지만 기존 정책·단순 용어표 대비 일관된 품질 우위는 확인되지 않았다. |
| `automation` | 자동 치환·조직 연결·구조화 필드 입력용. 모호한 후보를 제외하고 근거 중심 정책을 강제한다. | 기본 `occurrence_v1`으로 문서 hash·snapshot·mention·core/full span에 묶인 확정 연결을 검증한다. QA 답변·자체 지식·후보 포함 여부만으로 실행 권한을 얻지 못한다. |
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
[PRODUCTION_GROUNDING.md](PRODUCTION_GROUNDING.md)에 있다. 모든 프로필을
독립적으로 비교한 성능 순위는 없다. 현재는 `document_qa`를 포함한 다섯
프로필이며, 보정·발생 위치·벡터 무결성과 마이그레이션은
[리뷰 안전성 계약](REVIEW_SAFETY.md)에 정리했다. `cal-3`의 표본 수는
전이적으로 연결된 source component 수다. 같은 사건의 문서 수를 독립 표본으로
합산하지 않고, 여러 감사 mention을 가진 component에는 coverage를 주장하지 않는다.

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
[최종 12B/27B 생성 결과](../reports/hf_qa_retry_20261017/ANALYSIS.md)는 두 모델
모두 768회씩 완료했다. 답변 가능한 64문항의 정답 일치는 다음과 같다.

| 조건 | Gemma 12B | Qwen 27B |
|---|---:|---:|
| 문맥 없이 자체 지식 | 18/64 (28.1%) | 24/64 (37.5%) |
| 전체 문서 | 43/64 (67.2%) | 45/64 (70.3%) |
| 검색 문맥 | 32/64 (50.0%) | 31/64 (48.4%) |
| KTRF 검색어 확장 | 32/64 (50.0%) | 31/64 (48.4%) |
| 검색 + KTRF pack | 33/64 (51.6%) | 33/64 (51.6%) |

별도 무응답 64문항의 올바른 null은 검색에서 Gemma/Qwen 61/63개, pack에서
62/59개다. Qwen의 pack 추가 정답 2건은 YES/NO이고, 무응답 4건이 형식 오류로
악화됐다. Gemma는 양성 정답과 올바른 null이 각 1개 늘었다. 따라서 KTRF의
일관된 검색 우위나 큰 모델의 일괄 우위를 주장하지 않는다. 검색의 정답 근거
보존은 41/64이며 전체 문서는 64/64다. 토큰 비용·형식 오류·모델 및 표본의 제한은
최종 결과 문서에 함께 기록한다.

추가 [검색·JSON 반복 실험](../reports/followup_queue_20261018/ANALYSIS.md)은 4,096회
완료했다. 새 기사 표본의 양성 48문항에서 BM25는 Gemma 22/48→25/48,
Qwen 25/48→29/48로 정답 일치를 늘렸다. 원문 예산 상한은 같지만 실제 입력
토큰은 약 22% 많았다. 기존 128문항을 3회 반복한 Qwen pack에서는 동일 무응답
4문항의 형식 오류가 매회 발생했고, JSON 스키마 제약으로 총 12건→0건이 됐다.
양성 정답 33/64는 유지됐다. 스키마 pack은 Gemma도 매회 33/64였다.
이는 기존 검색 문맥의 반복 진단이며 독립 질문이 384개로 늘어난 것은 아니다.
BM25와 JSON 제약은 평가 코드의 비교 조건으로, 현재 resolver 모드나 기본 API에
자동 연결되지 않았다. 그 뒤 다음 조합·진단 실험까지 완료했다.

| 완료 실험 | 호출 수 | 범위와 한계 |
|---|---:|---|
| [BM25 × pack × JSON schema](../reports/combined_queue_20261018/RESULTS.md) | 3,072 | 기존 질문 재사용·반복을 포함한 조합 진단이다. |
| [새 TyDiQA 기사 비교](../reports/fresh_holdout_queue_20261018/RESULTS.md) | 864 | 사전 선언 기사 ID·내용 hash를 제외한 같은 코퍼스의 새 기사다. |
| [다섯 확장 실험](../reports/extended_queue_20261019/RESULTS.md) | 5,568 | KLUE 이전, 전체 입력 예산, 512문맥 검색, pack 형식·정책, 의미 안전성이다. |
| [원문·compact·안전성 진단](../reports/diagnostic_queue_20261020/RESULTS.md) | 3,584 | 기존 원문량 factorial과 새 문맥·합성 family를 나누어 보고한다. |
| [리뷰 후속 QA·예산·NoMIRACL·발생 위치 실행](../reports/review_queue_20261020/RESULTS.md) | 5,888 | AI 업무와 공개 자료이며 실제 사내 업무 분포·사람 gold가 아니다. |
| [새 family·간결한 출력·근거 검사](../reports/confirmation_queue_20261020/RESULTS.md) | 2,304 | 24개 AI family의 개발/확인 분할이며 운영 감사가 아니다. |
| [동일 후보·검증기와 서버 근거 ID](../reports/evidence_queue_20261021/RESULTS.md) | 512 | 노출 개발 자료 64개·8개 family를 재사용한 진단이다. |

호출 수는 독립 질문 수가 아니다. 반복·조건 비교를 표본 수로 합산하지 않는다.
일반 한국어 QA에서 pack의 일관된 이득은 아직 없으며, 1,024토큰 예산에서는
원문 정답 근거 보존이 61/64→52/64로 감소했다. 이후 정책을 고정한 원문량
진단도 같은 실패 구조를 뒷받침했지만, 기존 문항을 재사용한 원인 분석이다.

새 compact 평가 128문항 가운데 실제 주입은 42문항이었다. 이 42문항의
정답·올바른 기권 합계는 Gemma `none/full/compact=30/32/30`, Qwen
`30/31/29`였다. 동일 프롬프트인 나머지 86문항의 출력 정오는 각 모델에서
그대로였다. full pack 증가량의 family paired bootstrap 95% 구간은 Gemma
0~11.90%p, Qwen -4.76~11.90%p로 0을 포함한다. 사후 subgroup 진단을 새
독립 성능 검증으로 취급하지 않는다.
[봉인 결과 CPU 재분석](../reports/review_cpu_20261020/ANALYSIS.md).

`document_qa` 정책, 원문 우선 예산 배분, 단순 용어표와 KTRF 비교를
[리뷰 후속 실험](REVIEW_EXPERIMENTS.md)에서 완료했다. 원문 고정 AI 업무 QA
64문항의 정답·올바른 기권 합계는 다음과 같았다.

| 구성 | Gemma 12B | Qwen 27B |
|---|---:|---:|
| 원문만 | 41 | 43 |
| 단순 용어표 | 59 | 60 |
| 현재 KTRF | 56 | 59 |
| 문서 QA·원문 보존 KTRF | 57 | 59 |

용어 정보의 가치는 확인했지만 KTRF의 추가 우위는 확인하지 못했다. 일반 공개
QA와 NoMIRACL 근거 존재 판단에서도 pack의 일관된 이득은 없었다.

발생 위치 실행 96사례(연결 대상 42개)에서 Qwen의 의미 확인 지시 적용 결과는
단순 용어표가 올바른 승인 19건·잘못된 승인 0건, KTRF 실제 pipeline이 36건·0건,
동일 사실의 KTRF 통제가 35건·1건이었다. 실제 pipeline은 입력 토큰을 69.9%
더 사용했고 생성 요청 왕복 p95는 약 19.9초였다. 이 시간에는 resolver·검색·
사람 검토가 포함되지 않는다. [실행 결과](../reports/review_queue_20261020/review_routing_qwen27b/RESULTS.md).
현재 선택적 ID 연결의 유망한 구성이며, 운영 안전성이 검증된 설정은 아니다.
[새 family 확인 실험](ROUTING_CONFIRMATION.md) 2,304회도 완료했다. 확인 자료
128건 중 연결 대상 64개에 대한 정답 승인/오승인은 다음과 같다.

| 구성 | Gemma 12B | Qwen 27B |
|---|---:|---:|
| 단순 용어표 + 의미 확인, 전체 출력 | 64 / 13 | 64 / 6 |
| KTRF + 의미 확인, 전체 출력 | 42 / 0 | 42 / 0 |
| KTRF + 의미 확인, 간결한 출력 | 42 / 0 | 42 / 0 |
| KTRF + 추가 근거 검사, 전체/간결 출력 | 0 / 0 | 0 / 0 |

전체 192건에서 간결한 출력은 KTRF 정답 승인 수 65건을 유지하며 요청 p95를
Gemma 12.59→6.11초, Qwen 14.13→7.18초로 줄였다. 출력 형식의 개선이지
새 resolver 모드가 아니다. [간결한 실행 API](COMPACT_EXECUTION.md)는 서버가
보관한 요청·발생 위치를 복원하고 기존 검증기로 검사한다.

[기존 응답 CPU 진단](../reports/confirmation_cpu_20261021/ANALYSIS.md)에서 Qwen의
확인 자료 근거 compact 조건은 고유 인용 45건 모두 원문에 있지만 원래 위치는
모두 틀렸다. gold를 보지 않고 유일한 원문 위치만 복원한 사후 검사는 41건 정답·
0건 오승인이었다. 원래 완료 점수는 수정하지 않는다. 같은 KTRF 확인 자료의
정상 연결 64개는 전부 후보로 검색됐지만 정답 사실 제공은 45개, 승인은 42개다.
19개 미제공과 3개 정답 거절은 모두 모호한 발생에서 나왔다.

기존 비교는 단순 용어표와 KTRF의 후보·승인 규칙이 다르다. 그 영향을 분리하는
[동일 후보·검증기와 근거 ID 비교](EVIDENCE_CONTROL.md)도 노출된 개발 자료
64건에서 512회를 완료했다. 연결 대상 32개 중 서버 근거 ID 조건은 두 모델 모두
정답 32개를 제안했고 23개 승인·오승인 0개였다. 나머지 정답 9개는 모호한 발생이라
기존 guard가 거절했다. 단순 용어표의 정답 승인/오승인은 Gemma 23/4, Qwen 23/1,
구조화 조건은 22/6, 23/2였다. 형식만 구조화하는 것으로는 이득이 없었다.
문자 위치를 직접 쓰는 조건은 두 모델 모두 정답 승인 0개로 위치 실패가 반복됐다.

서버 근거 ID는 비용이 컸다. 단순 용어표 대비 요청 p95는 Gemma 4.77→22.99초,
Qwen 7.09→35.75초로 늘었다. 위치 복원의 효과와 근거 목록·긴 참조의 비용을 함께
봐야 하며, 이미 노출된 개발 family 8개를 새 독립 확인 결과로 합산하지 않는다.
[완료 집계](../reports/evidence_queue_20261021/RESULTS.md).

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

용어 설명은 `commit + qa_grounding`, 원문 날짜·수치 등의 일반 문서 QA는
`commit + document_qa`를 과제에 맞게 선택한다. 프로필 선택 자체가 성능 우위를
보장하지는 않는다.

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


### 실제 resolver 후보를 사용한 CPU 통합 진단 (2026-10-20)

위 고정 두 후보 실험에 이어, family의 등록 용어집 전체를 만든 뒤 문서별로
실제 `resolve()`를 한 번 호출했다. 생성된 후보 중 최대 8개만 동일하게
유지하고 `target_full`, `scoped_evidence`, `scoped_asserted`를 비교했다.
정답 후보를 추가하거나 기존 gold shortlist로 대체하지 않았다.

| 노출된 합성 자료 | LINK 대상 | full 정답/오답 제안 | scoped 정답/오답 제안 | asserted 정답/오답 제안 |
|---|---:|---:|---:|---:|
| 개발 24 family·336문서·384대상 | 240 | 10 / 6 | 58 / 23 | 58 / 0 |
| 기존 heldout 12 family·144문서·168대상 | 120 | 3 / 6 | 8 / 10 | 8 / 0 |

lexical 기준선의 결과다. 운영 확정은 두 자료 모두 0건이며, 실험 제안은 실행
승인이 아니다. 등록 alias를 중심으로 작성된 기존 자료라 gold 후보 회수율 1.0을
일반 검색 성능으로 해석할 수 없다. 기존 heldout도 이미 평가·분석된 노출 자료다.
정확한 core와 nominal full span을 따로 비교하며, 원시 토큰 `full_span`에 포함된
조사는 명칭 경계로 채점하지 않는다.
[CPU 통합 결과와 제한](../reports/review_cpu_20261020/ANALYSIS.md).

실제 후보를 고정한 nano 비교도 총 616대상에서 완료했다.

| 자료 | LINK 대상 | lexical asserted 정답/오답 제안 | nano asserted 정답/오답 제안 |
|---|---:|---:|---:|
| 노출된 개발 384대상 | 240 | 58 / 0 | 211 / 0 |
| 노출된 heldout 168대상 | 120 | 8 / 0 | 34 / 2 |
| 새 AI 업무 64대상 | 32 | 21 / 22 | 23 / 21 |

새 업무 자료의 기본 resolver 확정은 올바른 28건·잘못된 25건이었다. 이 표는
후속 LLM 의미 검사나 최종 실행 승인 결과가 아닌 후보 통합 진단이다. 이전
고정 두 후보 평가의 성능을 운영 경로로 옮긴 보장으로 사용할 수 없으며,
새 업무 자료도 실제 사내 문서나 사람 gold가 아니다.
[봉인 nano 집계](../reports/review_cpu_20261020/nano.json).
