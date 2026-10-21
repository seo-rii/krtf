# 리뷰 후속 실험 큐의 생성 전 고정 기록

**준비 검증 기록이며 GPU 완료 보고서가 아니다.** 결과는 검증 후 `reports/evidence_queue_20261021/`에 게시한다.

- Run: `ktrf-evidence-20261021T020906Z`.
- Frozen code: `888f37654be18845d862f4ed642ac31f4b56ae29`.
- one-server 전체 테스트: **2017 passed**, 0 skipped, exit 0.
- 실제 두 tokenizer, frozen source/input, vLLM IPC bind(79 bytes) 검증 통과.
- Gemma 12B → Qwen 27B, 기존 개발 문서 64개 × 4조건, 총 **512회**.
- temperature 0, seed 0, thinking off, strict JSON, all conditions output maximum 768 tokens, 재시도 없음.

| 트랙 | 모델별 요청 | 질문 | Gemma 최대 입력 tokens | Qwen 최대 입력 tokens |
|---|---:|---:|---:|---:|
| evidence_control | 256 | 64 | 1956 | 1873 |

기존 개발 용어군 8개·문서 64개를 사용한 노출 자료 진단이다. 동일 후보·승인 검증기를 유지하며 단순 용어표/KTRF와 근거 ID/문자 위치 반환을 비교한다.
기존 원시 응답의 CPU 진단과 별개인 새 모델 호출이다. 실제 업무 시범 운영은 WAITING_FOR_INPUT이며, 원시 응답 재채점·집계 푸시를 자동 진행한다.

[실험 계약](../docs/EVIDENCE_CONTROL.md) · [고정 계획과 증빙](EVIDENCE_PLAN_20261021.json)
