# Gemma 미시작 단계 복구와 Qwen 원본 재사용 계획

**새 Gemma 결과는 아직 없다.** 기존 큐의 Qwen 480건은 완료했고 Gemma는 기동 중 실패했다.

- 복구 run: `ktrf-closure-recovery-20261022T233412Z`.
- 추론·채점 코드 `79cb203a83fb10d7bb278558f622d163086bc50f`, 복구 드라이버 `d819eaa95e11363ceceb5f19d117be4e7eb56cd7`.
- 복구 코드 one-server 전체 테스트: **2495 passed**, 11 skipped, exit 0.
- 새 IPC 실제 bind와 원본 계획·상태·게시 종료 증거·Qwen 7개 파일 해시·원본 코드 재채점 검증 통과.
- 새 생성은 **Gemma 480회만** 수행하며, Qwen 480회는 원본 그대로 재사용한다. 완료 시 합계 960개 관측이다.
- Gemma GPU 메모리 예약만 **0.45 → 0.75**로 높인다. 문서·정답·후보·프롬프트·스키마·체크포인트·decoding·판정 정책은 고정한다.
- Qwen의 실행 환경에 새 계획 해시를 덮어쓰지 않는다. 원래 계획과 응답의 해시를 함께 검증해 출처를 보존한다.
- 다른 GPU 작업을 중지하지 않으며, GPU가 빌 때까지 기다린다. 상태·로그는 새 private 실행 경로에 기록한다.
- 원래 2,427개 테스트와 실제 tokenizer 준비 증거는 추론 코드 79cb203에 묶여 있으며, 복구 코드 테스트 증거와 구분한다.

[Qwen 중간 분석](closure_queue_20261023/ANALYSIS.md) · [고정 복구 증빙](CLOSURE_RECOVERY_PLAN_20261023.json) · [원래 실험 계약](../docs/EVIDENCE_CLOSURE.md)

이 자료는 96개 AI 합성 문서·12개 family다. 모든 판정은 실행 권한 없는 shadow이며, 운영 승인 성능이나 실제 업무의 위험 한도를 보장하지 않는다.
