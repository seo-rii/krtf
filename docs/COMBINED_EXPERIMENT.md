# BM25·KTRF pack·JSON 결합 비교

앞선 [4,096회 결과](../reports/followup_queue_20261018/ANALYSIS.md)에서 BM25 검색과
JSON 스키마 강제 생성이 각각 도움이 됐다. 그 이득을 더해 결합 성능을 추정하지 않고,
다음 네 조건을 같은 질문에서 직접 비교한다. 운영 기본값은 이 실험으로 변경하지 않는다.

| 조건 | 원문 선택 | 용어 pack | 생성 |
|---|---|---|---|
| `lexical` | 기존 lexical | 없음 | JSON Schema |
| `lexical_pack` | 같은 lexical 구간 | 해당 질문·구간에서 구성 | JSON Schema |
| `bm25` | 기존 BM25 | 없음 | JSON Schema |
| `bm25_pack` | 같은 BM25 구간 | 해당 질문·구간에서 구성 | JSON Schema |

## 고정 표본과 비용

앞선 검색 실험의 128문항·128기사를 **전부 재사용**한다. SPAN 40개·YES/NO 8개·
무응답 80개이며 기사·문항·정답·검색 구간을 바꾸거나 결과에 따라 제외하지 않는다.
이미 관찰한 결과가 방법 선택에 영향을 준 후속 실험이므로 새 독립 검증셋으로 부르지 않는다.
Oracle 구간과 정답 주석은 pack 생성이나 모델 입력에 전달하지 않는다.

각 조건을 같은 두 모델 Gemma 12B·Qwen 27B에서 3회씩 실행한다.
128문항 × 4조건 × 3회 × 2모델 = **3,072회**다. 반복은 새로운 독립 문항이 아니다.
질문별로 조건 순서를 회전하며 같은 조건의 prompt는 반복과 모델 사이에서 동일하다.

원문은 앞선 두 실제 tokenizer의 1,536토큰·3,000문자·3구간 상한을 그대로 따른다.
Pack은 기존 `commit`, `qa_grounding`, pack 예산 800과 `should_inject`를 사용한다.
BM25용 pack은 질문과 BM25 선택 원문으로 다시 만들며 lexical용 pack을 재사용하지 않는다.
주입하지 않는 pack 조건은 대응하는 일반 조건과 정확히 같은 prompt다.
공통 상한이 실제 입력 비용까지 같다는 뜻은 아니므로 token usage를 별도로 보고한다.

## 생성·평가 계약

온도 0·seed 0·thinking off·출력 128토큰·batch 1을 유지한다. 답변은 `answer` 하나만
갖는 JSON 객체이며 값은 문자열 또는 null이다. 스키마 미지원·HTTP 실패는 오류로
기록하고 자유 생성으로 대체하거나 답변을 재시도·수정하지 않는다.

양성 48개 정답 일치와 SPAN/YESNO, 무응답 80개 올바른 null, 형식 오류·누락·API 오류,
gold 위치가 남은 정답, 실제 prompt/output token, 지연, 반복 일치율을 보고한다.
주입 문항 수와 동일 prompt 쌍의 답변 불일치도 남긴다. 다섯 비교를 사전에 고정한다.

1. lexical → BM25: 검색 차이.
2. lexical → lexical pack: 기존 검색에서 pack 효과.
3. BM25 → BM25 pack: 개선 검색에서 pack 효과.
4. lexical pack → BM25 pack: pack이 있는 경우 검색 차이.
5. lexical → BM25 pack: 두 기능을 함께 적용한 결과.

모든 조건이 스키마를 쓰므로 이번 실행만으로 디코딩 방식의 효과를 분리하지 않는다.
Pack은 포맷과 용어 정책을 함께 바꾼 개입이다. 알려진 기사 안의 구간 선택 평가이며,
문서 집합 검색·운영 위험 보장·모델 크기만의 인과 효과를 측정하지 않는다.

## 큐와 자동 수집

새 소스 archive와 revision을 고정하고 전체 테스트·실제 두 chat template의 용량을
검증한 뒤 Gemma 1,536회 → Qwen 1,536회를 직렬 실행한다. GPU 메모리와 전용
loopback port가 부족하면 제한된 시간 동안 기다리며 다른 작업을 종료하지 않는다.

별도 수집기는 원본 요청·응답·정답·코드·실행 환경 해시와 manifest seal을 확인하고
같은 코드로 재채점한 뒤 집계만 커밋·푸시한다. 원문과 개별 답변은 ignored private
storage에 보관한다. 실행 상태·로그·고정 계획은 launch record에 기록한다.

구현: [준비](../eval/prepare_combined_followup.py), [생성](../eval/run_followup_llm.py),
[큐](../eval/run_followup_queue.py), [수집](../eval/collect_followup_queue.py).
