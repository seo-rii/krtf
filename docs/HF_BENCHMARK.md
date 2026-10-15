# 외부 HF 자료 벤치마크

이 평가는 기존 조직명·합성 업무 문서 평가에 **다른 도메인의 용어 경계**와
**사람이 작성한 공개 질문의 원문 근거**를 추가한다. 자료 검토 및 제외 사유는
[HF_DATASETS.md](HF_DATASETS.md), 실행 결과는
[HF_BENCHMARK.md](../reports/HF_BENCHMARK.md)에 기록한다.

## 측정 범위

| 자료 | 입력과 비교 | 측정하는 것 | 측정하지 않는 것 |
|---|---|---|---|
| KBMC | train-only 용어 사전으로 literal / fast / commit / aggressive 비교 | 외부 span 정답의 exact·overlap 회수, 사전 표현 가능 범위, 후보 수·지연 | entity linking 정확도, 실제 의료 문서 성능, 자동 실행 위험 |
| TyDiQA Korean primary validation | 컨텍스트 없음 / 전체 원문 / lexical 검색 / KTRF로 질문 확장 후 검색 | 선택 문맥에 최소 정답·정답 문단이 보존되는 비율 | 생성형 LLM의 답변 정확도·기권 정확도, 생산 context pack의 추가 효과 |

두 자료의 점수를 합치지 않는다. KBMC는 LLM 생성 후 사람 수정·검토 자료이며,
TyDiQA는 번역 없이 작성한 질문과 원문에 대한 사람 주석이다. 두 경우 모두 KTRF
출력에서 정답을 추출하지 않는다. 기존 silver precision과도 합산하지 않는다.

## 원천 고정과 입력 보존

`eval.hf_sources`의 고정 revision으로 원본 파일·카드를 내려받고 실제 크기와
SHA-256, URL, 수집 시점을 기록한다. TyDiQA 파일은 조사한 LFS SHA-256과도
대조한다. 캐시는 provenance sidecar와 현재 파일 내용이 일치할 때만 재사용한다.
원천과 카드가 이미 고정 revision에 있으므로 rows API의 움직이는 응답을 사용하지
않는다. 다운로드·변환 원문은 gitignored `eval/data/hf_external_v1/`에 둔다.

KBMC는 배포된 형태소 분절 문장을 그대로 쓴다. 문장을 자연 문장처럼 붙이거나
오류 BIO를 수정하지 않는다. 토큰·태그 불일치와 잘못된 continuation은 원천 행 ID와
사유를 제외 ledger에 남긴다. 제외 수를 공개하므로 평가 분모가 원천 전체와 다름을
확인할 수 있다. NER 타입과 span으로 entity ID, NIL 또는 core/full 의미를 만들지 않는다.

TyDiQA는 전체 원문을 유지하며 모든 한국어 질문을 로드한다. UTF-8 byte 위치는
정확한 문자 경계에서만 codepoint 위치로 변환한다. 기본 import는 잘못된 범위에서
중단한다. 이번 러너는 최소 답변 위치에 한해 오류 기록 옵션을 사용한다. 오류가 있는
질문도 표집·전체 질문 분모에 남기고, 최소 정답 보존 지표에서만 측정 불가로 분리한다.
정답 위치를 추정하거나 정상 주석만 선택해 해당 질문을 맞혔다고 세지 않는다.
원천 passage 후보 위치가 잘못되면 검색 입력을 만들 수 없으므로 계속 중단한다.
무응답·yes/no·문단만 있는 답·여러 주석을 유지하고, 비한국어 행 수를 별도 기록한다.
`secondary_task`의 정답 문단을 전체 문서인 것처럼 쓰지 않는다.

## KBMC 분할과 사전

배포 split은 `train` 하나다. 이 안에서 `hf-external-v1-20261016` seed와 원문 내용
SHA-256으로 문서를 나눈다. 해시의 5개 bucket 중 하나를 평가 후보로 두고 나머지로
사전을 만든다. 같은 원문·같은 주석은 한 번만 남긴다. 같은 원문에 다른 주석이 있으면
그 원문의 모든 행을 평가·사전 생성에서 제외하고 그룹 해시·원천 행 ID와 제외 수를
공개한다. 어느 주석이 맞는지 임의로 선택하지 않는다. 낮은 수준의 partition 함수는
여전히 주석 충돌을 거부하므로, 충돌 ledger를 만들지 않고 넘어갈 수 없다.
평가 문서는 resolver 출력이나 용어 포함 여부를 보지 않고 ID 해시 순으로 최대
512개 선택한다. 완전한 빈 주석 문서도 있으면 그대로 포함한다.

사전은 training partition의 `(타입, 표면형)` 빈도순 상위 512개다. 평가 정답으로
사전을 보충하지 않는다. entry ID는 lexical reference 식별자일 뿐 실제 entity
정답이 아니다. 학습·평가 사이 원문 정확 중복은 차단하지만 같은 용어·정의 템플릿은
공유할 수 있다. 이 분할은 family holdout이나 미등록 entity 의미 일반화 시험이 아니다.

분모는 선택 문서의 외부 NER 정답 전체다. 다음을 분리한다.

- **Exact reference recall:** 정답 span과 정확히 같은 core span을 반환한 비율.
- **Overlap reference recall:** 정답과 겹치는 core span을 반환한 비율. exact로 합치지 않는다.
- **Catalog reference coverage:** 정답 표면형이 사전 정규화 키로 표현 가능한 비율.
  전체 recall의 대체 분모가 아니다.
- **Exact recall within catalog:** 위 표현 가능 reference 안의 exact 회수율.
- **미판정 출력:** reference 밖의 출력과 `RESOLVED` 출력 수를 남기되 entity
  linking precision 또는 false positive로 해석하지 않는다.

타입별 분자·분모, 실패·degraded 수, prediction set 잘림, 후보 수 p95와 전체 호출
지연 p50/p95/p99를 JSON에 보존한다. literal은 등록 문자열의 모든 위치를 찾는
기준선이다. 생산 형태 분해나 의미 판단을 갖춘 대조군이 아니다. 현재 `commit`과
`aggressive`의 실제 mention 응답이 같은지도 문서별로 확인한다.
타입별 수치는 정답 타입으로 나눈 span 회수율이며 예측 타입의 정확도가 아니다.

## TyDiQA 문맥 비교

기존 자료와 원문 해시·사용 가능한 parent ID/URL이 같은 행을 제외한 후, 질문 ID
해시 순으로 최대 256개를 선택한다. 무응답 여부·정답 길이·원문 길이로 필터링하지
않는다. 같은 Wikipedia 기사에서 나온 질문 수와 parent 기사 수를 별도 보고한다.

| 조건 | 선택 규칙 |
|---|---|
| `none` | 원문 구간을 제공하지 않음 |
| `full` | 원본 전체. 길이 예산이 없는 정보 상한 |
| `retrieved` | 질문과 모든 원천 passage 후보를 lexical 비교하여 구간 선택 |
| `ktrf_expanded` | 동일 질문을 기존 realorg glossary와 `commit`으로 해석. 확정된 canonical 이름을 최대 네 개 추가해 같은 검색 수행 |

두 검색 조건은 후보 구간·점수식·3,000문자 예산·구간 최대 세 개를 공유한다.
원천 passage가 길면 1,000문자 창과 100문자 overlap으로 나누고, 선택 구간은 서로
겹치지 않게 한다. 문자 bigram 교집합을 passage 길이로 보정하며 동점은 원문 순이다.
선택기에 정답 위치·정답 문단·정답 문자열을 넘기지 않는다.

KTRF는 **질문만** 읽어 검색어를 보조한다. 원본 전체를 resolver로 스캔하는 비교,
LLM context pack 비교, `scoped_asserted` 실험 또는 신경 reranker 비교가 아니다.
확장할 조직명이 없는 질문에서는 검색 결과가 같을 수 있다. 현재 realorg 사전의
도메인과 공개 QA 질문의 차이가 드러나도록 확장이 일어난 질문 수를 보고한다.

최소 답변이 있는 질문에서 여러 주석 중 하나의 답변 span이 온전히 남으면 최소
정답 보존으로 센다. 정답 passage가 온전히 남는지는 별도 지표다. 두 지표 모두
문자열의 우연한 재등장이 아니라 **원문 offset 포함 관계**로 검사한다.
`NO_ANSWER` 주석만 있는 질문, yes/no 주석, 최소 span이 없는 질문과 혼합 주석 수를
따로 남긴다. 답변 생성기가 없으므로 무응답을 맞혔다고 점수를 주지 않는다.

`none`의 보존율 0과 `full`의 보존율 1은 구성상 상·하한이다. 이것을 LLM 성능
개선으로 읽지 않는다. 두 검색 조건의 helpful/harmful 근거 보존 flip을 짝지어 보고한다.

## 중복·독립성 및 재현

기존 production real holdout, 로컬 blind KONEC/KoNeoBench 자료와 사용 가능한
wild 원문·문장 cache의 내용 해시 및 parent를 검사한다. 검사한 파일의 해시와
없는 cache 경로도 보고한다. 원천 문서 URL을 모두 가진 전역 색인이 아니므로
Wikipedia 기사 겹침이나 near-duplicate가 없다는 보장은 하지 않는다. 여러 질문이나
mention을 독립 표본으로 삼아 위험 신뢰상한을 계산하지 않는다.

```sh
pip install -e '.[dev,benchmark]'
python -m pytest tests/test_hf_sources.py tests/test_hf_benchmark.py
python -m eval.run_hf_benchmark --out-dir eval/out/hf-benchmark
```

출력 디렉터리가 이미 있으면 덮어쓰지 않는다. 첫 resolver 호출 전에 source와
selection/catalog hash, 코드 revision·두 평가 모듈 해시, 고정 비교 조건을 protocol에
기록한다. QA 사전 해시와 평가 코드 범위의 git 상태도 남긴다.
`report.json`은 집계·환경, `ledgers.json`은 문서별 분자·분모·선택 구간을
담는다. 공개 저장소에는 원문 없는 집계 JSON과 분석 문서만 올린다.

보고서 지연은 CPU의 직렬 실행 관측치다. 평가 순서·서버 부하·cache의 영향을
제거한 제어 실험이나 운영 SLO가 아니다. 이 평가에서 정책 임계값을 탐색하거나
확정 규칙을 느슨하게 하지 않는다. `coverage_valid=false`,
`production_authorized=false`를 유지한다.
