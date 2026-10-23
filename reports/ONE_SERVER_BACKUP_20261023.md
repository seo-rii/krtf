# one-server KRTF 핵심 자료 백업과 원격 정리

원격 전용 자료의 전체 검증 백업·정리를 완료한 뒤, 사용자 요청에 따라 로컬 백업을 의미 있는 실험 자료 중심으로 축소했다. 현재 보존 위치는 `data/`이며 기존 전체 복사본 `remote/`는 제거했다.

- 백업: `/home/seorii/backups/krtf/one-server-20261023T070839Z`.
- 보존 파일 24,676개, 링크 14개.
- 디렉터리·검증 metadata를 포함한 실제 백업 사용량: **약 2.40 GiB**.
- 보존 내용의 논리적 크기: **10.28 GiB**. 동일 내용 중복 저장을 줄인 파일 크기: **2.25 GiB**.
- 보존: 원시 입력·요청·응답, 원문·주석·정답, 프롬프트, 채점 결과, 보고서·로그, 전체 소스 스냅숏·아카이브, 재현 설정.
- 보존: 모델 repository/revision/파일 SHA-256, tokenizer/config/template/index, 설치 패키지 dist-info와 pyvenv.cfg.
- 재생성 가능한 가중치·설치 파일·테스트 임시 자료·캐시 **54.25 GiB**를 제외했다. 공개 가중치 12개는 고정 revision과 다운로드 ETag/SHA-256 일치를 확인했다.
- 동일 SHA-256·크기·권한의 파일을 hard link로 묶었으며, 원래 경로별 metadata는 manifest에 유지한다.
- 선별 자료의 모든 파일과 링크를 검증하고 디스크에 반영한 뒤 기존 전체 복사본을 지웠다. 제거 후에도 다시 검증했다.

현재 manifest SHA-256: `564ba5ade30d9f7f72b1550cf82dd923b4eebe155f7f23852442f1246fd60d5d`. 현재 검증 기록은 `metadata/retained-verification.json`이다. 최초 전체 snapshot의 manifest와 원격 삭제 증빙은 감사 기록으로 보존한다. 전체 파일이 현재 남아 있다는 뜻은 아니다.

## 원격 정리 기록

- one-server의 KRTF 전용 최상위 항목 156개를 삭제했고 남은 대상이 없음을 확인했다. `krtf-*`와 `ktrf-*`를 모두 포함한다.
- 공유 모델·vLLM 가상환경·공용 HF 캐시는 보존했다. 이번 로컬 선별 작업은 원격을 추가로 변경하지 않았다.
- 원시 자료·가중치·private manifest는 Git에 올리지 않는다.

원격 백업·삭제 로그: `/home/seorii/logs/one-server-20261023T070839Z/backup-cleanup.log`.
로컬 선별 로그·상태: `/home/seorii/logs/one-server-20261023T070839Z/curation.log`, `curation.status.json`. 두 작업 모두 종료 코드 0.
