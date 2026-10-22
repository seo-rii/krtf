# 근거 연결·기권 형식 실험: Qwen 중간 결과와 Gemma 복구

원래 960회 큐는 Gemma 기동 실패로 **FAILED / exit 1**이다. Qwen 27B는 **480/480회**, API 오류·누락·형식 오류 0으로 완료했다. Gemma는 첫 benchmark 요청 전에 실패했으므로 생성 응답이 없다. 두 모델 완료 보고서와 구분한다.

Gemma 로그에는 `gpu_memory_utilization=0.45`, 모델 적재 22.83 GiB, available KV cache **−13.09 GiB**, `No available memory for the cache blocks`가 기록됐다. 복구 계획은 Gemma의 메모리 예약만 0.75로 높이고 원래 문서·요청·체크포인트·출력 스키마·채점·decoding을 유지한다. Qwen 응답 480개와 원본 실행 환경은 바이트 그대로 검증해 재사용한다.

## 완료된 Qwen 27B

각 조건은 LINK 48문서와 음성 48문서다. 승인 수는 실행 권한이 없는 실험용 shadow 판정이다.

| 조건 | 정상 shadow 연결 | 오승인 | 유효 기권 | p95 지연 |
|---|---:|---:|---:|---:|
| manual_legacy | 45/48 | 0 | 0/48 | 15.11초 |
| closure_legacy | 46/48 | 0 | 27/48 | 15.11초 |
| manual_null | 15/48 | 0 | 46/48 | 16.36초 |
| closure_null | 46/48 | 0 | 47/48 | 15.10초 |
| closure_bundle | 46/48 | 0 | 48/48 | 7.04초 |

`closure_bundle`은 `closure_null`과 같은 정상 연결 46건을 유지하면서 출력 토큰을 8,802→4,583개(47.9% 감소), p95를 15.104→7.037초(53.4% 감소)로 줄였다. 전체 토큰은 361,036→358,435개로 0.72% 줄었고 입력 토큰은 0.46% 늘었다. 긴 문서와 짧은 문서 각각 정상 연결 23/24건, 음성 기권 24/24건이다.

다만 모든 조건의 서버 추가 segment는 0건이고 raw/closed 승인도 같다. 이 자료에서 서버가 실제 참조를 보충해 연결을 회복했다는 효과는 관측되지 않았다. 조건별 정책 문구와 전송 형식이 모델 출력에 미친 차이로 해석한다.

`manual_legacy`의 유효 기권 0건은 모델이 기권을 하지 않았다는 뜻이 아니다. null 제안 47건이 s/q/a 일관성 검사에서 거절됐다. `manual_null`은 올바른 ID를 48건 제안했지만 근거 참조·발생 위치·속성 부모의 선택 오류로 정상 shadow 연결이 15건에 그쳤다. 여러 실패 사유는 중복 집계된다.

최선 조건에서도 정답 연결 2건은 `full_surface_structural_identity_not_same`, `explicit_separate_identity_context`로 각각 거절됐다. 생산 guard의 정상 연결은 모든 조건에서 35/48건이다. `manual_legacy`의 생산 guard 오승인 1건은 strict shadow에서 차단됐으며, shadow 46/48을 생산 승인 성능으로 사용하지 않는다.

이번 자료에서는 대상 96건의 exact-core 탐지와 LINK 48건의 정답 후보 회수가 모두 성공했다. 96개 AI 합성 문서·12개 family와 반복 과제 구조이며 실제 업무 분포·사람 gold·배포 오류 상한을 대표하지 않는다. 공개 하위 집계는 문서 길이와 family를 유지한다. 이전 CPU 사후 재분석과 새 문서 성적은 합산하지 않는다.

[원래 큐 상태](RESULTS.md) · [Qwen 전체 결과](evidence_closure_qwen27b/RESULTS.md) · [고정 실험 계획](../CLOSURE_PLAN_20261023.md)
