# 리뷰 후속 실험 큐의 생성 전 고정 기록

**준비 검증 기록이며 GPU 완료 보고서가 아니다.** 결과는 검증 후 `reports/confirmation_queue_20261020/`에 게시한다.

- Run: `ktrf-confirmation-20261020T105734Z`.
- Frozen code: `a16fd42c5736415083d3a09d1e7e49c8e748fb2c`.
- one-server 전체 테스트: **1928 passed**, 0 skipped, exit 0.
- 실제 두 tokenizer, frozen source/input, vLLM IPC bind(79 bytes) 검증 통과.
- Gemma 12B → Qwen 27B, 새 문서 192개 × 6조건, 총 **2,304회**.
- temperature 0, seed 0, thinking off, strict JSON, all conditions output maximum 768 tokens, 재시도 없음.

| 트랙 | 모델별 요청 | 질문 | Gemma 최대 입력 tokens | Qwen 최대 입력 tokens |
|---|---:|---:|---:|---:|
| routing_confirmation | 1152 | 192 | 1554 | 1448 |

새 용어군 24개·문서 192개를 개발용 8개와 확인용 16개 용어군으로 나누고, 단순 용어표/KTRF/근거 대조 × 전체/간결 출력을 비교한다.
합성 자료의 무실행 재생과 CPU 지연 측정을 완료했다. 실제 업무 시범 운영은 WAITING_FOR_INPUT이다. 자동 수집·원시 응답 재채점·집계 푸시를 연결한다.

[실험 계약](../docs/ROUTING_CONFIRMATION.md) · [고정 계획과 증빙](CONFIRMATION_PLAN_20261020.json)
