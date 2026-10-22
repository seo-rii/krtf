# 근거 복원·속성 판단·문맥 구분 순차 실험 계획

**생성 전 준비 증빙이며 완료 보고서가 아니다.**

- Run: `ktrf-support-20261022T105826Z`; frozen code `c0f1b063ff9050da331abdb939155def945b2b22`.
- one-server 전체 테스트 **2307 passed**, 11 skipped, exit0.
- 실제 Gemma12B/Qwen27B tokenizer와 두 단계 IPC bind 검사 통과.
- CPU진단 완료: 정상32건의 기존 승인 상한23건, 네 속성 근거 포함 상한7건.
- 기존64문서×8조건×두모델 **1,024회** → 방법선택 → 새96문서×2조건×두모델 **384회**.
- 새96문서·12용어군의 모든8방법 프롬프트·token수를 진단 생성 전에 봉인했다.
- 실제 실행은 없으며 production guard와 shadow 승인 모의 결과를 분리한다.
- temperature0,seed0,thinkingoff,strictJSON,768outputtokens,재시도없음.

[실험 계약](../docs/SUPPORT_RECOVERY.md) · [CPU 결과](support_cpu_20261022/ANALYSIS.md) · [전체 봉인 증빙](SUPPORT_PLAN_20261022.json)
