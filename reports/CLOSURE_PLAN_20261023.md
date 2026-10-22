# 근거 연결·기권 분기·긴 문서 후속 큐의 고정 기록

**준비 증빙이며 GPU 완료 보고서가 아니다.** 결과는 검증 후 `reports/closure_queue_20261023/`에 게시한다.

- Run: `ktrf-closure-20261022T150857Z`; frozen code `79cb203a83fb10d7bb278558f622d163086bc50f`.
- one-server 전체 테스트 **2427 passed**, 11 skipped, exit0.
- 실제 두 tokenizer, 봉인된 source/input/schema, vLLM xgrammar 분기 schema 컴파일·IPC bind 검증 통과.
- Gemma 12B → Qwen 27B, 새 96문서 × 5조건, 총 **960회**.
- 사전 A/B 역할별 국내/해외·절차/시스템 각 6:6, 공유 약칭 LINK의 정답 A/B 6:6. 짧은 문서 48개와 긴 문서 48개.
- temperature 0, seed 0, thinking off, strict JSON, 공통 출력 상한 768 tokens, 응답 재시도 없음.
- 모든 판정은 실행 권한이 없는 shadow 실험이며 운영 승인 계약은 변경하지 않는다.

| 트랙 | 모델별 요청 | 문서 | Gemma 최대 입력 tokens | Qwen 최대 입력 tokens |
|---|---:|---:|---:|---:|
| evidence_closure | 480 | 96 | 7136 | 6694 |

근거 연결 × 기권 형식의 2×2 비교와 근거 묶음 비용 비교를 같은 원문·후보·정의·목록에서 수행한다.
기존 96문서의 CPU 사후 진단과 새 96문서의 생성 결과를 구분한다. 실제 업무 shadow는 WAITING_FOR_INPUT이다.

주요 하위 집계는 문서 길이와 family를 보존한다. 고유 명칭의 explicit/implicit LINK는 A, 문단 간 LINK는 B를 주로 가리키는 상관이 남아 있다. 전체 정답 역할 분포와 각 세부 유형의 균형은 [source 검토](../eval/fixtures/evidence_closure/REVIEW.md)에서 구분한다.

[실험 계약](../docs/EVIDENCE_CLOSURE.md) · [CPU 재분석](closure_cpu_20261023/ANALYSIS.md) · [고정 증빙](CLOSURE_PLAN_20261023.json)
