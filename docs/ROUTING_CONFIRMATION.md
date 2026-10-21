# 선택적 ID 연결 확인 실험과 무실행 업무 시범 운영

2026-10-20. 이전 리뷰 큐 5,888회는 [완료](../reports/review_queue_20261020/RESULTS.md)했다.
이 문서는 그 결과로 선택한 구성을 고정하고 새 자료에서 재검증하는 후속 계약이다.
합성 GPU 비교 **2,304회는 완료**했고 `ed097a0`까지 재채점·결과 푸시를 마쳤다.
실제 업무 시범 운영은 **`WAITING_FOR_INPUT`**이다. 아래 실험 계약은 생성 전
고정한 설계 기록이며, 완료 수치의 출처는 [결과 보고서](../reports/confirmation_queue_20261020/RESULTS.md)다.

## 완료 결과와 CPU 진단 (2026-10-21)

확인 family 16개·128문서 중 연결 대상은 64개였다. Gemma/Qwen의 KTRF+의미
확인은 전체/간결 출력 모두 정답 승인 42건·오승인 0건이었다. 단순 용어표의 전체
출력은 각각 64/13, 64/6이었다. 실제 제공 후보와 승인 규칙이 다른 제품 비교다.
전체 192건에서 간결한 출력은 KTRF 정답 승인 수를 유지하며 요청 p95를 각각
12.59→6.11초, 14.13→7.18초로 줄였다. 추가 literal 근거 검사 조건의 승인은
두 모델 모두 0건이었다. 이 결과만으로 문맥 판단 능력 자체가 없다고 볼 수 없다.

[기존 응답 CPU 진단](../reports/confirmation_cpu_20261021/ANALYSIS.md)은 원래
봉인·원시 응답 재채점을 검증한 뒤 고유 인용과 속성의 위치만 원문에서 재구성했다.
Qwen 확인 compact 근거의 비기권 45건은 고유 인용이 모두 원문에 있었지만 위치는
모두 틀렸다. 위치를 유일하게 복원한 사후 검사는 정답 승인 41건·오승인 0건이었다.
원래 점수·모델 선택·실행 검증기는 유지하며, 사후 수치를 새 성능 결과로 대체하지 않는다.

KTRF 확인 연결 대상 64개는 전부 검색됐고 정답 사실은 45개에 제공됐다. 나머지
19개는 모호한 후보여서 automation pack에 정의가 없었으며, 올바른 제안 3개도
요청한 발생이 모호해 실행 검증에서 거절됐다. 후보를 보여주는 것과 승인하는 것을
분리한 [근거 ID 진단](EVIDENCE_CONTROL.md)도 기존 개발 자료 64개에서 512회를
완료했다. 서버 ID 조건은 두 모델 모두 32개 정답 제안 중 23개 승인·오승인 0개,
9개는 모호한 발생으로 거절됐다. 요청 p95가 약 23/36초로 커져 비용 개선이 필요하다.
같은 노출 개발 자료를 새로운 독립 확인으로 합산하지 않는다.
[간결한 실행 API](COMPACT_EXECUTION.md)는 별도 운영 연결 인터페이스다.

## 선택한 구성과 비용

이전 96사례에서 Qwen 27B+KTRF+의미 확인은 올바른 ID 36건·잘못된 ID 0건을
승인했고, 단순 용어표+의미 확인은 19건·0건이었다. 연결 대상은 42개였다.
동일 사전 사실을 받은 KTRF 조건은 35건·1건으로 오류가 남았다.
입력 토큰은 109,276 대 64,337로 69.9% 많았다. KTRF 조건의 p95 19.905초는
LLM 생성 요청 왕복 지연이며 resolver나 업무 전체의 지연이 아니다.
일반 QA보다 선택적 ID 연결의 재현성과 비용을 다음 판단 대상으로 삼는다.

## 새 family 검증과 문맥 차단

AI 작성 새 용어집 24 family에 각 8사례, 총 192사례를 준비한다. 8 family·64사례는
개발 자료, 16 family·128사례는 확인 자료다. family와 문서의 원문·정의·정답을
resolver 출력 전에 작성하고 별도 AI 검토와 hash 봉인을 거친다. 기존 fixture의
family·entity·표면형과 겹치는지 검사한다. 합성 자료이며 사람 gold나 실제 업무
모집단으로 표시하지 않는다. 24 family가 네 종류의 시나리오 문체를 공유하므로
새 family를 독립적인 24개 업무 분포나 완전히 새로운 추론 구조로 해석하지 않는다.

비교는 다음 세 경로와 두 응답 형식을 교차한 여섯 조건이다.

| 조건 | 경로와 응답 형식 |
|---|---|
| `plain_check_full` | 단순 용어표 + 의미 확인, 전체 occurrence binding |
| `plain_check_compact` | 단순 용어표 + 의미 확인, 간결한 서버 결합 선택 |
| `ktrf_check_full` | 현재 KTRF + 의미 확인, 전체 occurrence binding |
| `ktrf_check_compact` | 현재 KTRF + 의미 확인, 간결한 서버 결합 선택 |
| `ktrf_evidence_full` | KTRF + 원문 근거 일치 검사, 전체 occurrence binding |
| `ktrf_evidence_compact` | KTRF + 원문 근거 일치 검사, 간결한 서버 결합 선택 |

단순 용어표와 KTRF는 같은 원천 용어집을 사용하지만 selector가 고른 후보와
제공 사실은 다를 수 있다. 따라서 이 비교는 제품 경로 비교이며 동일 후보·동일
정보를 통제한 실험이 아니다. 근거 검사 조건은 요청한 발생을 포함하는 원문의
연속 인용과 `jurisdiction`, `temporal_status`, `referent_kind`, `scope`의
명시적 값·위치를 대조한다. 일반적인 의미 함의 판정이나 문맥 안전성 보장이
아니며, 속성이 암시된 정상 사례도 보류할 수 있는 실험적 literal 검사다.

모든 경로는 전체 occurrence binding을 반환하는 형식과 서버가 binding을
보유하고 모델이 간결한 선택을 반환하는 형식을 비교한다. 간결한 출력도
서버 측 요청·문서·snapshot·mention·core/full span에 결합한 뒤 동일한 guard를
통과해야 한다. 모델 선택으로 미확정 후보를 확정하거나 다른 발생의 권한을
빌리는 것은 허용하지 않는다. source text와 사실 의미는 유지하고 정의·예외를
문자 수로 자르지 않는다. 여섯 조건 모두 출력 상한은 동일하게 **768 tokens**다.
전체 원문·제공 사실·지시문·chat template을 실제 tokenizer로 계산하고, 입력과
예약 출력의 합이 **8,192 tokens**를 넘으면 준비 단계에서 실패한다. 초과 원문·
사실을 자동으로 잘라 맞추지 않는다.

Gemma 12B와 Qwen 27B에서 각 192×6, **총 2,304회**를 계획한다. 모델 비교,
개발/확인 split, 조건 반복은 독립 표본 수를 늘리지 않는다. 확인 결과를 본 뒤
threshold·지시문을 바꾸면 해당 자료는 소비된 진단 자료로 전환해야 한다.
최종 실행 manifest가 실제 조건·호출 수·예산·모델 revision을 봉인한다.

보고할 값은 올바른 승인, 잘못된 승인, 보류, 문서당 하나 이상 오승인 여부,
입력·출력 토큰, 생성 요청 지연이다. 준비 비용은 `snapshot_compile`,
`first_prepare`, `warm_prepare`로 분리하고, LLM 요청 왕복 시간과 응답 검증
시간도 따로 기록한다. 각 단계의 분포를 업무 전체 p95로 합산하지 않는다.
의미 정답과 guard 통과를 분리하고,
family paired bootstrap을 함께 제시한다. 합성 오류 0건을 독립 감사 위험
보장이나 무검토 실행 허가로 해석하지 않는다.

## 실제 업무 입력과 blind 주석

실제 업무 문서·용어집은 아직 공급되지 않았다. 이 항목은 GPU 합성 큐와 별도이며
문서가 들어오기 전에는 `WAITING_FOR_INPUT`으로 유지한다. 파일 경로가 제공되면
먼저 원문에서 표본을 정하고 resolver 제안 없이 전체 발생 위치를 주석한다.
주석은 출처가 `AI`인지 `HUMAN`인지 기록하고 독립 검수·이견 조정을 구분한다.
AI 초안만으로 `human_verified=true`를 만들지 않는다.

입력은 UTF-8 JSONL이다. 필수 필드는 `document_id`, `family_id`, `text`다.
가능하면 원천 `source_row_id`, `parent_document_id`, `event_id`,
`source_revision`, `source_uri`, `collected_at`을 함께 제공한다. `partition`은
`audit`(기본), `development`, `confirmation` 중 하나다. 마지막 값은 합성 확인
자료를 실제 독립 감사로 부르지 않고 보존할 때 쓴다. 동일 family·event·부모 문서를 전이적으로
묶으며 연결된 자료가 양 partition에 걸치면 거부한다. 중복 ID·동일 원문·불일치
hash도 거부한다. 연결 성분을 보존하는 것은 통계적 독립성을 입증하지 않는다.
`source_origin`은 `AI_AUTHORED`, `PUBLIC_SOURCE`, `USER_PROVIDED_UNVERIFIED` 중
하나이며 기본값은 마지막 값이다. 합성 CPU 사전 점검은 반드시 `AI_AUTHORED`로
표시하고 실제 업무 시범 운영 상태를 `NOT_ACTUAL_BUSINESS_INPUT`으로 기록한다.

아래는 형식만 보여 주는 합성 예시다.

```json
{"document_id":"synthetic-demo-1","family_id":"synthetic-demo","text":"한전KDN은 계획을 발표했다.","source_row_id":"example:1","source_revision":"example-v1","partition":"audit","source_origin":"AI_AUTHORED"}
```

```bash
python -m eval.shadow_routing \
  --documents /private/ktrf/documents.jsonl \
  --glossary /private/ktrf/glossary.yaml \
  --out-dir /private/ktrf/shadow-packet
```

`glossary.yaml`은 KTRF glossary 형식이다. 명령은 기본적으로 resolver를 호출하지
않는다. 원본 `source.jsonl`, `glossary.yaml`, `blind_annotation.json`,
`shadow_requests.jsonl`, 집계 전용 `summary.json`, 각 파일 hash를 담은
`manifest.json`을 생성한다.
주석 packet은 원문·출처·빈 주석 목록을 담으며 resolver 결과나 입력에 붙어 있던
제안 ID·정답을 가져오지 않는다. 원본 전체는 별도 파일로 보존한다. 기본 제한은
200문서이며 `--max-documents`로 최대 1,000문서까지 허용한다. 문서는 자동
절단하지 않으며 동기 resolver 입력 한도를 넘으면 명시적으로 실패한다.

출력 디렉터리는 새로 만들어야 하며 0700, 파일은 0600이다. 원문과 개별 응답은
비공개로 보관한다. 이 도구는 업로드·외부 모델 호출·업무 시스템 변경을 수행하지
않는다. 공급된 출처 정보는 그대로 보존하지만 진위를 인증하지는 않는다.

## 로컬 resolver 비용과 사람 작업 시간

원문 주석 packet을 만든 뒤 제안과 resolver 비용을 별도로 확인할 수 있다.

```bash
python -m eval.shadow_routing \
  --documents /private/ktrf/documents.jsonl \
  --glossary /private/ktrf/glossary.yaml \
  --out-dir /private/ktrf/shadow-replay \
  --replay --repeats 3
```

`--replay`도 업무 실행은 하지 않는다. 모든 출력은 `SHADOW_PROPOSAL_ONLY`,
`execution_enabled=false`, `action_performed=false`다. `shadow_proposals.jsonl`은
문서 hash·source component·snapshot과 resolver 응답을 보존한다. 의미 정답은
자동으로 채우지 않으며 blind packet은 제안 생성 전 상태를 유지한다.

`resolver_latency.json`은 snapshot을 한 번 만든 뒤 문서별 첫 호출과 반복 호출의
시간, 반복 p50/p95/p99를 기록한다. CPU 심볼릭 `resolve()` 시간만 포함하며
snapshot 컴파일·모델 생성·네트워크·사람 검토는 제외한다. 반복은 1~20회로
제한하고 독립 표본으로 계산하지 않는다. `human_review_time_ms`는 `null`이다.
실제 업무 시범 운영에서는 별도 검토 시작·종료·수정·보류 기록이 있어야 사람
작업 시간 절감과 최종 업무 성공을 평가할 수 있다.

공개 가능한 `summary.json`은 원문·개별 document ID·개별 시간·기계 경로를
제외하고 자료 수·연결 성분 수·출처 분류·작업 상태·지연 분포만 포함한다.
합성 입력에서는 `real_business_pilot_status=NOT_ACTUAL_BUSINESS_INPUT`과
`actual_business_data_verified=false`를 유지한다.
