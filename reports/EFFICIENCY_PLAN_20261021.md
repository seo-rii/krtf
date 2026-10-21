# 리뷰 후속 실험 큐의 생성 전 고정 기록

**준비 검증 기록이며 GPU 완료 보고서가 아니다.** 결과는 검증 후 `reports/efficiency_queue_20261021/`에 게시한다.

- Run: `ktrf-efficiency-20261021T145325Z`.
- Frozen code: `7aedeaa2ae26ef8ecfac39dcba1a04f4f973b295`.
- one-server 전체 테스트: **2096 passed**, 0 skipped, exit 0.
- 실제 두 tokenizer, frozen source/input, vLLM IPC bind(79 bytes) 검증 통과.
- Gemma 12B → Qwen 27B, 새 AI 문서 64개 × 5조건, 총 **640회**.
- temperature 0, seed 0, thinking off, strict JSON, all conditions output maximum 768 tokens, 재시도 없음.

| 트랙 | 모델별 요청 | 질문 | Gemma 최대 입력 tokens | Qwen 최대 입력 tokens |
|---|---:|---:|---:|---:|
| evidence_efficiency | 320 | 64 | 1983 | 1899 |

새 용어군 8개·문서 64개를 개발 2개/확인 6개 용어군으로 나눈다. 긴 참조·짧은 참조·중복 없는 입력·선택적 근거 검사를 같은 후보와 승인 검증기로 비교한다.
이전 노출 자료에서 방법을 선택한 뒤 새 AI 소스를 작성·검토해 고정한 모델 비교다. 실제 업무 시범 운영은 WAITING_FOR_INPUT이며, 원시 응답 재채점·집계 푸시를 자동 진행한다.

[실험 계약](../docs/EVIDENCE_EFFICIENCY.md) · [고정 계획과 증빙](EFFICIENCY_PLAN_20261021.json)
