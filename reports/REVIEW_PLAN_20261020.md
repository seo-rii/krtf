# 리뷰 후속 실험 큐의 생성 전 고정 기록

**준비 검증 기록이며 GPU 완료 보고서가 아니다.** 결과는 검증 후 `reports/review_queue_20261020/`에 게시한다.

- Run: `ktrf-review-20261020T003946Z`.
- Frozen code: `5648fa0a36feb44a27b1148cd356d896f37d7385`.
- one-server 전체 테스트: **1846 passed**, 0 skipped, exit 0.
- 실제 두 tokenizer, frozen source/input, vLLM IPC bind(78 bytes) 검증 통과.
- Gemma 12B의 다섯 트랙 → Qwen 27B의 다섯 트랙, 총 **5,888회**.
- temperature 0, seed 0, thinking off, strict JSON, QA output 128 / occurrence routing output 384 tokens, 재시도 없음.

| 트랙 | 모델별 요청 | 질문 | Gemma 최대 입력 tokens | Qwen 최대 입력 tokens |
|---|---:|---:|---:|---:|
| review_abcd | 1024 | 128 | 1928 | 1789 |
| review_budget | 384 | 64 | 1536 | 1436 |
| review_nomiracl | 384 | 128 | 4251 | 3857 |
| review_policy | 384 | 64 | 1928 | 1789 |
| review_routing | 768 | 96 | 2635 | 2423 |

새 공개64문맥과 가상 업무64문서로 QA를 비교하고, 실행은 업무64+공개32표적을 분리한다. NoMIRACL 한국어128건은 근거 존재 여부를 판별한다.
실제 resolver 후보의 lexical/nano 비교616표적을 완료했고 nano 집계를 함께 게시한다. 복수 조건이나 family를 독립 표본으로 합산하지 않는다. 자동 수집·원시 응답 재채점·집계 푸시를 연결한다.

[실험 계약](../docs/REVIEW_EXPERIMENTS.md) · [고정 계획과 증빙](REVIEW_PLAN_20261020.json)
