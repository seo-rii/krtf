# 근거 묶음·순서·방해 문맥 후속 큐의 고정 기록

**준비 검증 기록이며 GPU 완료 보고서가 아니다.** 결과는 검증 후 `reports/robustness_queue_20261022/`에 게시한다.

- Run: `ktrf-robustness-20261021T152702Z`.
- Frozen code: `82d798cd3f6089616f6610a42ac9afe65e9fdd1d`.
- one-server 전체 테스트: **2189 passed**, 0 skipped, exit 0.
- 실제 두 tokenizer, 봉인된 source/input/schema, vLLM IPC bind(79 bytes) 검증 통과.
- Gemma 12B → Qwen 27B, 재사용 AI 문서 64개 × 6조건, 총 **768회**.
- temperature 0, seed 0, thinking off, strict JSON, 공통 출력 상한 768 tokens, 재시도 없음.
- 선행 `ktrf-efficiency-20261021T145325Z`의 두 모델·재채점·결과 게시 성공을 모두 확인한 뒤 실행한다.

| 트랙 | 모델별 요청 | 질문 | Gemma 최대 입력 tokens | Qwen 최대 입력 tokens |
|---|---:|---:|---:|---:|
| evidence_robustness | 384 | 64 | 1896 | 1783 |

개별 근거 참조와 근거 묶음을 원래 순서·뒤집은 순서·별도 방해 문맥에서 비교한다.
선행 응답·점수를 읽지 않고 방법을 고정했어도 문서는 재사용하므로 새 독립 확인으로 세지 않는다. 실제 업무 shadow는 WAITING_FOR_INPUT이다.

[실험 계약](../docs/EVIDENCE_ROBUSTNESS.md) · [고정 계획과 증빙](ROBUSTNESS_PLAN_20261022.json)
