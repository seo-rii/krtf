# one-server KRTF 로컬 백업과 원격 정리

KRTF 전용 원격 자료를 로컬로 백업하고 파일별 SHA-256 검증 후 원격에서 삭제했다.
실험 원시 요청·응답·정답·보고서·실행 코드·가상환경·전용 모델 가중치·로그를 포함한다.

- 로컬 백업: `/home/seorii/backups/krtf/one-server-20261023T070839Z`.
- 일반 파일 115,362개, 심볼릭 링크 4,474개, 69,292,045,229 bytes.
- 삭제한 원격 최상위 항목: 156개. 기록만 남긴 종료 IPC 소켓: 84개.
- 원본 manifest SHA-256: `798e02f03ed9d345d352fcb8109cd38fc0d40afab4eb2c96303b32a2cf8cef43`.
- 원격 전송 전 → 로컬 전송 후 → 삭제 직전 원격의 내용을 모두 해시로 대조했다.
- `krtf-*`와 `ktrf-*` 두 표기를 모두 확인했다. 원격 전용 저장소와 개인 experiments/logs의 해당 항목을 정리했다.
- 공유 vLLM 가상환경·Gemma/Qwen 공유 모델·공용 HF 캐시는 보존했다. 공유 런타임 패키지 버전과 모델 파일 전체 digest를 별도 백업했다.
- 원시 자료·가중치·private manifest는 Git에 올리지 않았다. 이 문서는 집계 완료 기록이다.

상태 파일: `/home/seorii/logs/one-server-20261023T070839Z/backup-cleanup.status.json`. 로그: `/home/seorii/logs/one-server-20261023T070839Z/backup-cleanup.log`. 백업·검증·원격 정리 종료 코드 0.
