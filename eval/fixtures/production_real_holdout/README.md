# 실제 문장 holdout: production-grounding v1

이 자료는 KONEC의 실제 문장 60개와 고정된 KTRF 조직 사전으로 만든 소규모
제품 경로 평가 자료다. 원문은 합성하지 않았다. 연결·의미 주석은
**AI_AUTHORED_NOT_HUMAN**이며 사람 gold로 해석하면 안 된다.

## 원천과 고정

- 원천: [Korean Named Entity Corpus (KONEC)](https://github.com/korean-named-entity/konec)
- 파일: [`konec/konec-dev.tsv`, revision `b6c98a457f9b13379a815bb153ae94dee2872cd4`](https://github.com/korean-named-entity/konec/blob/b6c98a457f9b13379a815bb153ae94dee2872cd4/konec/konec-dev.tsv)
- 원천 SHA-256: `5345b4a62802307c71070c0666a04b454525dd1d13035b3853d883c62d4a7195`
- 저작자 표시: KONEC 구축자 및 upstream KLUE 데이터 기여자. KONEC 참고문헌은
  정유남·송영숙·유현조(2023), 「한국어 중첩 개체명의 말뭉치 구축 연구」다.
- 원문과 원천 NER 주석은 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)이다.
  이 디렉터리의 파생 연결 주석에도 같은 라이선스를 적용한다.
- `glossary.yaml`은 `examples/realorg_glossary.yaml`의 변경 없는 복사본이다.
  정의·alias·entity ID를 평가 문장을 보고 수정하지 않았다.

`documents.jsonl`은 원천의 문장 전체, NER span/type, 정규화한 원천 문장 ID,
revision, 파일·문장 hash, 수집 시점을 보존한다. 원천 주석에서 text와 ID를
구분하는 탭 이후 내용은 ID에 포함하지 않았다. 문장 본문은 바꾸지 않았다.
KONEC은 KLUE 원문을 재주석한 자료이므로 두 코퍼스를 독립 검증으로 합산하지 않는다.

## 문장 선택

seed는 `ktrf-production-real-holdout-v1-20261014`이다. 이전 로컬 주석·평가
자료·실험 요청·보고서 83개 JSON/JSONL 파일에서 문장 hash와 ID를 모아 중복
20문장을 먼저 제외했다. 검사 파일 목록과 hash는 `selection_manifest.json`에 있다.

남은 원문에서 사전 canonical/alias의 문자열을 포함한 390문장과, 해당 문자열은
없지만 원천 `OGG_*` 조직 주석이 있는 1,083문장을 별도 층으로 만들었다.
각 층에서 `SHA256(seed + NUL + document_id)` 순으로 각각 48개와 12개를
골랐다. resolver의 발견·확정 여부, 모델 답변, 연결 gold는 선택에 쓰지 않았다.
지명, 상위 기관과 다른 하부 기관, 일반 단어와 겹친 문자열도 원래 뽑힌 문장에
그대로 남겨 두었다.

이것은 **어휘·NER 층화 문장 표본**이다. 전체 문서의 무작위 감사 표본이나 실제
서비스 분포를 대표하지 않는다. 원 기사 ID가 없으므로 원 기사 단위 독립성도
주장하지 않는다. 같은 entity/family가 이전 실험에 등장했을 수 있다. 검사 가능한
로컬 자료와의 문장 중복을 배제했으며, 모델 사전학습 및 확보하지 못한 과거
wild corpus와의 비중복은 증명하지 않는다.

## 질문 대상과 AI 주석

각 문장에 실제 나타난 대상 하나를 `target_packets.jsonl`에 먼저 고정했다.
어휘 층은 가장 긴 사전 문자열을 우선하고 동률이면 문자열 순, 같은 문자열이면
첫 출현을 택했다. 다른 뜻을 이루는 연속된 전체 표현이 명확하면 기관명 일부를
대신 물어보지 않고 `법무부장관`, `금융위기`, `KBS2`처럼 전체 표현을 대상으로
삼았다. 원천 조직 대조 층은 첫 `OGG_*` span을 사용했다.

`annotations.ai.jsonl`은 각 문장 전체를 읽은 첫 AI 주석이다. 60개의 주요 질문
대상 이외에도 원천 `OGG_*` span과 모든 사전 표면형 출현을 검토한 138개의
주석을 담는다. 사전에 없는 사람·제품·날짜 등을 모두 연결 주석한 것은 아니므로
exhaustive entity-linking gold라고 주장하지 않는다. resolver 출력은 보지 않았다.

다른 AI 주석자는 원문·사전·정답 없는 target packet만 보고 독립적으로
`annotations.review.jsonl`을 작성했다. 불일치는 모델 실행 전에 조정했다.
평가 입력은 조정된 최종 primary target만 사용하며, 보조 주석은 주 지표에
합산하지 않는다. 두 AI의 일치는 사람 두 명의 합의나 독립적인 인간 검증을
대체하지 않는다.

이 실험에서 고정 사전의 국내 `LOCAL` 광역자치단체 항목은 그 행정구역의
지리적 용례도 포함한다. 사전 description에 기관·청사만을 가리킨다는 제한이
없으므로 `ORG_`라는 ID 접두어만으로 별도의 조직 전용 의미를 강제하지 않는다.
이에 따라 날씨의 강원도·제주도, 주소의 광주광역시를 연결한다. 북한의 강원도는
같은 이름의 다른 행정구역이므로 연결하지 않는다. 이 규약은 이 고정 사전을
사용하는 pilot의 범위 선택이며, 모든 조직·영토 이름의 동일성을 주장하는 것은
아니다. 원래 두 AI 주석은 변경하지 않고 조정 결과를 별도 파일에 보존한다.

`LINK`의 답은 고정 사전의 description 원문이며, 나머지 label의 QA 답과 실행
ID는 null이다. `COMPOSITIONAL`에서 의미가 확인된 내부 기관은 core ID에 따로
기록하며 전체 표현의 실행 ID로 승격하지 않는다. 지리적 행정구역, 기관 이름의
장소 환유, 방송사와 채널 등은 주석자 사이의 경계 판단을 명시적으로 조정할
대상이다.

실제 실행은 production QA와 automation context pack을 각각 만들고 동일한
60문장·120과제를 12B와 27B에 제공한다. 최종 파일 hash와 주석 상태는
`manifest.json`에서 확인한다. 이 작은 자료의 정확도를 모집단 오류 한도의
보장이나 conformal coverage로 해석하지 않는다.
