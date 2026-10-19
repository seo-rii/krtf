# 원문·pack·안전성 진단 큐의 생성 전 고정 기록

**준비 검증 기록이며 GPU 완료 보고서가 아니다.** 결과는 검증 후 `reports/diagnostic_queue_20261020/`에 게시한다.

- Run: `ktrf-diagnostic-20261019T153007Z`.
- Frozen code: `037436c8757af923050dfaba7d76d26859c60a2d`.
- one-server 전체 테스트: **1721 passed**, 0 skipped, exit 0.
- 실제 두 tokenizer, frozen source/input, vLLM IPC bind(78 bytes) 검증 통과.
- Gemma 12B의 세 트랙 → Qwen 27B의 세 트랙, 총 **3,584회**.
- temperature 0, seed 0, thinking off, strict JSON, output 128 tokens, 재시도 없음.

| 트랙 | 모델별 요청 | 질문 | Gemma 최대 입력 tokens | Qwen 최대 입력 tokens |
|---|---:|---:|---:|---:|
| fresh_compact | 384 | 128 | 1991 | 1801 |
| safety_robustness | 640 | 160 | 702 | 654 |
| source_pack_factorial | 768 | 128 | 1879 | 1715 |

QA 원인 진단은 기존128문항, 간결한 pack 검증은 새128문맥을 사용한다. 안전성은 기존96건과 새16 family·64건을 분리한다.
복수 조건이나 동일 family를 독립 표본으로 합산하지 않는다. 자동 수집·원시 응답 재채점·집계 푸시를 연결한다.

[실험 계약](../docs/DIAGNOSTIC_EXPERIMENTS.md) · [고정 계획과 증빙](DIAGNOSTIC_PLAN_20261020.json)
