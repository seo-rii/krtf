# 추가 다섯 실험 큐의 생성 전 고정 기록

**준비 검증 기록이며 GPU 완료 보고서가 아니다.** 결과는 검증 후 `reports/extended_queue_20261019/`에 게시한다.

- Run: `ktrf-extended-20261019T133422Z`.
- Frozen code: `3351402493263a72c487394405dd048d226601cc`.
- one-server 전체 테스트: **1658 passed**, 0 skipped, exit 0.
- 실제 두 tokenizer, frozen source/input, vLLM IPC bind(78 bytes) 검증 통과.
- Gemma 12B의 다섯 트랙 → Qwen 27B의 다섯 트랙, 총 **5,568회**.
- temperature 0, seed 0, thinking off, strict JSON, output 128 tokens, 재시도 없음.

| 트랙 | 모델별 요청 | 질문 | Gemma 최대 입력 tokens | Qwen 최대 입력 tokens |
|---|---:|---:|---:|---:|
| budget | 512 | 128 | 1536 | 1440 |
| corpus | 512 | 128 | 2776 | 2493 |
| pack | 640 | 128 | 1867 | 1721 |
| semantic_safety | 96 | 96 | 568 | 519 |
| transfer | 1024 | 256 | 1879 | 1715 |

QA는 같은 256문항의 중첩 표본을 사용한다. 안전성은 AI 작성·검토한 24 family, 96문항이다.
복수 조건이나 동일 family를 독립 표본으로 합산하지 않는다. 자동 수집·원시 응답 재채점·집계 푸시를 연결한다.

[실험 계약](../docs/EXTENDED_EXPERIMENTS.md) · [고정 계획과 증빙](EXTENDED_PLAN_20261019.json)
