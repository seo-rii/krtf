# 근거 연결·기권 분기·긴 문서 후속 큐의 고정 기록

**준비 증빙이며 GPU 완료 보고서가 아니다.** 결과는 검증 후 `reports/closure_queue_20261023/`에 게시한다.

- Run: `ktrf-closure-20261022T150857Z`; frozen code `79cb203a83fb10d7bb278558f622d163086bc50f`.
- one-server 전체 테스트 **2427 passed**, 11 skipped, exit0.
- 실제 두 tokenizer, 봉인된 source/input/schema, vLLM xgrammar 분기 schema 컴파일·IPC bind 검증 통과.
- Gemma12B → Qwen27B, 새96문서 × 5조건, 총 **960회**.
- 국내/해외·절차/시스템·공유약칭 정답A/B 균형, 짧은48문서와 긴48문서.
- temperature0,seed0,thinkingoff,strictJSON,공통 출력 상한768tokens,재시도없음.
- 모든 판정은 실행 권한이 없는 shadow 실험이며 운영 승인 계약은 변경하지 않는다.

| 트랙 | 모델별 요청 | 문서 | Gemma 최대 입력 tokens | Qwen 최대 입력 tokens |
|---|---:|---:|---:|---:|
| evidence_closure | 480 | 96 | 7136 | 6694 |

근거 연결×기권 형식2×2비교와 근거 묶음 비용 비교를 같은 원문·후보·정의·목록에서 수행한다.
기존96문서의 CPU사후진단과 새96문서의 생성 결과를 구분한다. 실제 업무 shadow는 WAITING_FOR_INPUT이다.

[실험 계약](../docs/EVIDENCE_CLOSURE.md) · [CPU 재분석](closure_cpu_20261023/ANALYSIS.md) · [고정 증빙](CLOSURE_PLAN_20261023.json)
