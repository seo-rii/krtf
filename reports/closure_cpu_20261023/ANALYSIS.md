# 근거 연결·기권 형식 CPU 재분석

기존96문서의 봉인된 원시 응답을 검증한 후, 같은 응답에 결정적 변환을 적용한 사후 진단이다.
새 생성 결과나 운영 승인이 아니며, 아래 회복 수가 새 실험에서 재현된다고 가정하지 않는다.

| 모델 | 변환 | 정상 shadow 판정 | 잘못된 shadow 판정 | 정상 기권 | 추가 연결 회복 |
|---|---|---:|---:|---:|---:|
| gemma12b | original | 24/48 | 0 | 31 | 0 |
| gemma12b | server_closure | 45/48 | 0 | 31 | 21 |
| gemma12b | null_projection | 24/48 | 0 | 47 | 0 |
| gemma12b | closure_and_null | 45/48 | 0 | 47 | 21 |
| qwen27b | original | 31/48 | 0 | 35 | 0 |
| qwen27b | server_closure | 47/48 | 0 | 35 | 16 |
| qwen27b | null_projection | 31/48 | 0 | 46 | 0 |
| qwen27b | closure_and_null | 47/48 | 0 | 46 | 16 |

원시 응답과 기존 성적은 변경하지 않는다. 비어 있지 않은 잘못된 근거 참조를 삭제해
오류를 숨기거나, 사전 속성을 원문 근거로 추가하거나, 잘못된 entity를 교체하지 않는다.
