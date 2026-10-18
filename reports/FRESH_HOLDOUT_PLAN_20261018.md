# 미사용 기사 결합 검증 큐 고정 계획

**생성 전 준비 기록**이며 완료 보고서가 아니다. 결과는 검증 후
`reports/fresh_holdout_queue_20261018/`에 게시한다.

- Run: `ktrf-fresh-20261018T134911Z`.
- Source revision: `748e32d4983295ec4a10664e81a2a8c9c497164a`.
- one-server 전체 테스트 **1572개 통과**, skipped 0, exit 0.
- 원본·제외 입력 해시, 실제 두 tokenizer/chat template, 고정 소스 일치 검증 통과.
- 실제 vLLM IPC bind 통과: 78바이트 / 제한 107바이트.
- 기존 표본과 parent·본문 해시가 겹치지 않는 **36질문·36기사**.
- SPAN **6**, YES/NO **12**, 무응답 **18**. 작은 동일 코퍼스 표본이며 새 외부 코퍼스가 아니다.
- lexical/BM25 × pack 유무 × strict JSON × 3반복 × 2모델 = **864회**.
- 실제 pack 주입 문항: lexical **8/36**,
  BM25 **8/36**.
- 최대 prompt tokens: Gemma **1734**, Qwen **1593**.
- 실행 순서: Gemma 432회 → Qwen 432회. GPU 자원 대기·자동 수집·재채점·집계 푸시 포함.

반복을 독립 표본으로 합산하지 않는다. 세부 유형별 성능·원문 근거 보존·기권·
형식 오류·실제 토큰 비용을 분리한다. 이 작은 표본만으로 일반적 효과나 운영 안전성을
확정하지 않으며 다른 작업이나 운영 기본값을 변경하지 않는다.

[실험 계약](../docs/FRESH_HOLDOUT_EXPERIMENT.md) · [고정 계획과 증빙](FRESH_HOLDOUT_PLAN_20261018.json)
