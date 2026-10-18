# BM25·KTRF pack·JSON 결합 큐 고정 계획

**생성 전 준비 기록**이며 완료 보고서가 아니다. 실행 결과는 별도의
`reports/combined_queue_20261018/`에 검증 후 게시한다.

- Run: `ktrf-combined-20261018T035715Z`.
- Source revision: `a634e0a742e171368d589a4f9454d4489c559a78`.
- one-server 전체 테스트: **1525개 통과**,
  skipped 0, exit code 0.
- 실제 Gemma/Qwen chat template 용량·원문 1,536토큰 상한 및 frozen input 검증 통과.
- 재사용 표본 128문항·128기사: SPAN 40, YES/NO 8, 무응답 80.
- lexical/BM25 × pack 유무 × JSON Schema × 3회 × 두 모델 = **3,072회**.
- Pack 실제 주입 문항: lexical **13/128**,
  BM25 **14/128**.
- 최대 prompt token: Gemma **1952**,
  Qwen **1815**; 출력 128토큰 예약.
- 실행 순서: Gemma 1,536회 → Qwen 1,536회. 자원 부족 시 대기하며 다른 작업을 종료하지 않는다.
- 완료 후 원본 seal·해시 검증 → 같은 코드로 재채점 → 집계만 자동 커밋·푸시한다.

이전 결과를 확인한 표본의 후속 비교이며 새 독립 검증셋이 아니다. 세 반복을
독립 표본으로 합산하지 않는다. 같은 검색 조건의 pack 유무는 동일 원문을 쓴다.
원문 상한이 실제 token 비용까지 같다는 뜻은 아니며 사용량을 따로 보고한다.
이번 실행의 네 조건이 모두 스키마를 사용하므로 스키마 자체의 효과를 분리하지 않는다.

[실험 계약](../docs/COMBINED_EXPERIMENT.md) · [고정 계획·CPU 증빙](COMBINED_PLAN_20261018.json)
