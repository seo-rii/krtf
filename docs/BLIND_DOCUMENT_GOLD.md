# 독립 문서 gold와 고정 위험 평가

이 파이프라인은 평가 자료를 준비하고 검증한다. 새 사람 주석이나 성능 개선을
주장하지 않는다. 기존 `variant_gold.jsonl`은 출력 기반 표본이므로 여기의 독립
문서 gold로 변환하지 않는다.

## 문서 수집과 출처

`python -m eval.wild_data`는 기존 sentence cache를 다시 수집하면서
`eval/data/wild_documents.jsonl`에 원문 전체를 보존한다. 문장에는 원천 row ID,
parent document ID, 원문/문장 SHA-256, 원문 내 codepoint span, 수집 시점,
데이터셋 revision을 기록한다. 같은 원문은 내용 해시로 묶인다. 전체 문서는
출력 mention이나 등록 alias로 필터링하지 않고 수집한다.

revision은 수집 시 Hugging Face Hub에서 조회한 revision이다. rows API의
응답을 그 revision에 고정한 다운로드라는 보장은 없으며, 실제 평가 입력은
저장한 내용 해시로 식별한다. 조회 전후 revision이 달라지거나 확인할 수 없게 되면 수집을 거부한다. 최초 조회에 실패하면 revision은 null이며 blind
준비 명령은 이를 거부한다. 이전 text/source-only cache에서 문서 ID를 추정해
만들지 않는다. source별 라이선스는 `wild_data.py`와 sentence cache meta를
확인하고 재배포 조건을 검토한다. 이 작업은 원문을 git에 추가하지 않는다.

## 출력 없이 주석하기

1. 실제 사용 분포에서 문서를 뽑는다. resolver 결과와 무관하게 표집한다.
   원천 데이터셋의 연속 앞부분만 수집한 기본 wild corpus는 서비스의 무작위
   감사 표본을 대신하지 않는다.
2. 두 사람이 같은 동결 glossary를 보면서 문서 전체를 독립적으로 읽는다.
   검색되지 않은 mention도 모두 적는다. 빈 문서도 `complete=true`로 제출한다.
3. glossary의 entity family 또는 별도 독립 family 목록을 각 문서의 `family_ids`에
   부착한다. 가족이 이어진 문서는 같은 partition에 남는다. KLUE/KONEC 중복도
   같은 parent ID나 내용 해시로 묶는다. 가족이 없으면 document split만 보장한다.
4. protocol에 채널·모호성·도메인 strata, threshold 목록, 위험 한도, 주석 지침,
   표집 방식, 모델·정책·입력 길이·예산을 사전 선언하고 manifest를 봉인한다.
   큰 connected family로 partition이 비면 데이터 부족으로 보고한다.

```sh
python -m eval.blind_gold prepare \
  --documents eval/data/wild_documents.jsonl --count 200 --seed blind-v1 \
  --glossary examples/realorg_glossary.yaml --code-revision "$(git rev-parse HEAD)" \
  --protocol /path/to/predeclared-protocol.json --out /path/to/new-blind-batch
```

명령은 resolver 출력이 없는 두 주석 packet, 선택 원문, manifest를 생성한다.
표집은 seed와 document ID의 해시 순서이며, split도 입력 순서에 불변이다.
출력 폴더가 이미 있으면 덮어쓰지 않는다. 봉인은 변경 탐지용 SHA-256이다.
기술적으로 test 열람을 막지는 않으므로 test packet은 평가 담당자가 별도 보관한다.

주석 packet의 `annotator`에는 실제 주석자 ID를 적고, 전체 문서 검토 뒤
`complete=true`로 바꾼다. `mentions`의 예시는 **형식 설명**이며 정답 데이터가 아니다.

```json
{"span":[0,3], "surface":"금감원", "label":"LINK", "entity_id":"ORG_FSS",
 "should_commit":true, "full_span":[0,4], "full_identity":"DISTINCT",
 "family_ids":["financial-regulator"]}
```

span은 원문 Python codepoint 기준 half-open이다. `full_span`은 core를 포함한다.
`label`은 LINK / NIL / AMBIGUOUS / NON_MENTION이고, NIL은 동결된 사전에
대상이 없는 경우다. 검색 누락은 LINK의 recall 실패이며 NIL로 바꾸지 않는다.
전체 표면형은 SAME / DISTINCT / JUXTAPOSED로 분리한다. 모호한 mention은
별도로 남기고, only LINK에 대해 독자가 확정할 수 있을 때 `should_commit=true`다.
`family_ids`는 family macro 집계 기준이며 누락 시 entity ID로 집계한다.

```sh
python -m eval.blind_gold adjudicate \
  --first /path/to/annotator-a.jsonl --second /path/to/annotator-b.jsonl \
  --decisions /path/to/disputed-decisions.jsonl --out /path/to/gold.jsonl
```

이견 문서에는 전체 최종 주석 packet과 `adjudication_note`가 필요하다. 독립 주석
해시와 이견 여부를 보존한다. 두 동일 ID로 주석한 결과는 거부한다. 독립 작성
절차의 실제 준수와 주석자 간 agreement 측정은 사람이 확보해야 한다.

## 봉인 test 평가

prediction JSONL은 문서마다 `document_id`, `document_sha256`, 그리고 resolver의
`mentions` 배열을 가진다. 전혀 찾지 못한 문서도 빈 배열로 기록한다.

```sh
python -m eval.blind_gold score \
  --documents /path/to/new-blind-batch/documents.jsonl \
  --manifest /path/to/new-blind-batch/manifest.json \
  --gold /path/to/sealed-test-gold.jsonl --predictions /path/to/test-predictions.jsonl \
  --out /path/to/new-report.json
```

gold와 prediction은 봉인 test partition을 빠짐없이 포함해야 한다. 원문·출처·
family 변경, 누락 문서, 중복 span, 독립 주석 없는 gold를 거부한다. 보고서는
manifest, gold, prediction 해시와 문서별 분자/분모를 남긴다. 같은 실험의 실행
환경·snapshot/policy/calibrator/model 해시와 command도 protocol에 기록한다.

후보 exact-link recall은 resolver가 제안하지 않은 LINK를 분모에 포함한다.
정확 확정과 미확정 비용, NIL 오확정, 출력 외 추가 오확정, core/full-surface
오류, family macro recall을 따로 기록한다. 상관된 문서 내 mention의 합계는
점 추정이며 오류 보장이 아니다. 보고서의 `risk_status=UNVALIDATED`를 없애고
확정 오류를 보장하려면 독립 감사 평가가 필요하다. 문서 bootstrap에는 반환된
`document_counts`를 재표집하며 mention을 독립 재표집하지 않는다.

## 고정 위험 threshold 선택

`eval.fixed_risk.validate_thresholds`는 independent tune/test 문서 감사 사건과
사전 선언한 threshold·group 목록을 받는다. 각 group에서 문서당 무작위 감사
사건 하나만 사용하며, 여러 correlated mention을 binomial 표본으로 넣으면
거부한다. 그룹은 channel/ambiguity/domain을 사전에 조합한 층이다.

- tuning에서 exact one-sided Clopper–Pearson UCB와 모든 threshold×group에
  대한 Bonferroni 보정을 적용하고, 통과한 규칙 중 확정 수가 가장 큰 것을 택한다.
- 독립 test에서 선택한 규칙만 검증한다. 그룹 수에 대한 보정을 적용하고,
  두 단계에 전체 alpha의 절반씩 배정하고, 각 단계에서 상·하한 두 꼬리에 다시 나눈다. 실패한 test를 보고 threshold를 다시
  고르지 않는다. 재탐색에는 새로운 봉인 test가 필요하다.
- group별 확정률, 오류 수, 오류 UCB, 선택 threshold를 구분해 반환한다.
  빈/작은 표본이나 UCB가 위험 한도를 넘는 경우 `INSUFFICIENT_DATA`다.

이 보장은 대표성 있는 독립·교환 가능한 감사 사건이라는 가정 아래의
`error_given_commit`이다. 후보 조건부 coverage나 end-to-end 검색 recall 보장과
다르다. 승인 correction과 출력 기반 strata는 대표 감사 표본으로 취급하지 않는다.
threshold 선택은 semantic guard를 통과한 사건에만 적용한다. threshold가 높아도
금감원장 전체를 기관으로 확정하는 guard 위반을 허용하지 않는다.

## 외부 자료의 경계

KoNeoBench는 형태 형성 일반화의 보조 자료다. 별도 glossary/entity ID 주석,
formation/family split 및 라이선스 확인 없이는 linking gold가 아니다.
KLUE-NER와 KONEC은 원천 문장이 겹치므로 독립 두 코퍼스처럼 합산하지 않는다.
span/type 정답을 재사용하더라도 entity와 core/full 의미는 별도 주석해야 한다.
실제 데이터 도입 전 이 조건을 충족해야 하며, 이 파이프라인은 외부 NER 라벨을
자동 linking 정답으로 변환하지 않는다.

### 확인한 원천 형식과 실제 준비 smoke

[공식 KONEC 설명](https://github.com/korean-named-entity/konec)은 KLUE의 sentence ID를
유지하는 character BIO TSV 형식을 명시한다. `eval.external_gold`는 원천 ID를
공유 parent로 묶고, character span/type을 가져오며 entity ID를 만들지 않는다.
`##` header의 인라인 표기 대신 BIO character 행으로 원문을 복원한다. 문장의
공백 character도 유지하며 잘못된 BIO continuation을 거부한다.

```sh
python -m eval.external_gold --source konec --input /path/to/konec-dev.tsv \
  --revision PINNED_GIT_SHA --collected-at ISO_UTC_TIME --out /path/to/new-documents.jsonl
```

[KoNeoBench 논문](https://arxiv.org/abs/2609.19916)과
[공식 저장소](https://github.com/bcmilab/ko-neobench)의 Task-2 CSV를 확인했다.
`--source koneobench`는 축약/혼성 행만 가져와 구성요소를 family key로 남긴다.
MASK 용례는 제공된 headword로 복원하고 변환을 기록한다. 이미 unmasked인
용례는 원문대로 보존한다. 이 용례는 실제 독립 업무 문서 gold가 아닌 보조
형성 시험이다. entity ID, NIL 여부, core/full 관계의 주석을 자동 생성하지 않는다.

```sh
python -m eval.external_gold --source koneobench \
  --input '/path/to/Task2_Source Word Identification.csv' \
  --revision PINNED_GIT_SHA --collected-at ISO_UTC_TIME --out /path/to/new-formation-documents.jsonl
```

`reports/EVALUATION_FOUNDATIONS.json`에는 pinned 공식 source로 실행한 import →
prepare smoke의 원천 hash, revision, 행 수, partition 수, 봉인 해시만 기록한다.
원문, 사람 정답, 성능 점수는 포함하지 않는다. fixture 테스트는 별도로
prepare → adjudicate → score와 미검색 mention 집계까지 검증한다.

확정 위험 검증에서 test 오류의 lower bound가 위험 한도보다 높으면 `FAIL`이다.
UCB가 한도를 넘지만 lower bound로 실패를 확정할 수 없는 경우와 표본이 부족한
경우는 `INSUFFICIENT_DATA`로 남긴다. 점 추정만 보고 안전/실패를 확정하지 않는다.

현재 pinned KONEC TSV의 BIO token 행이 없는 header 5개는 원문 없는 source
record로 제외한다. 제외한 원천 sentence ID는 `import_exclusions`와 준비 smoke
보고서에 남긴다. 다른 정상 문장 5,000개는 독립 span/type annotation을 보존한다.

준비한 20문서씩의 두 주석 packet은 로컬의 `eval/data/blind_review_20261013/konec/`와
`eval/data/blind_review_20261013/koneobench/`에 있다. 이 디렉터리는 gitignored이며
공식 원문이나 주석 packet을 원격으로 배포하지 않는다. 봉인된 glossary는 준비 시
`examples/realorg_glossary.yaml`이다. 아직 complete=false이며 실제 사람의 독립
주석과 실사용 용어 glossary 설계는 남아 있다. 보조 형성 시험에는 목적에 맞는
glossary/protocol을 먼저 정하고 새 batch를 준비한다. 이 smoke packet 자체는
실사용 무작위 감사 표본이 아니다.

`source_file_sha256`는 UTF-8-sig로 읽은 텍스트를 UTF-8로 다시 인코딩한 hash다.
BOM이나 원천 파일 바이트까지 검증하려면 다운로드 원본의 hash도 별도로 보존한다.
