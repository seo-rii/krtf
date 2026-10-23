# one-server 백업에서 선별한 공개 재분석 자료

집계 보고서에 없던 **요청별 결과와 비용**을 보존한다. 원문·질문·정답·프롬프트·개별 모델 답변·entity ID는 포함하지 않는다. 원본 자료는 로컬 백업에 유지한다. 새로운 추론이나 성능 실험을 실행한 결과가 아니다.

## 포함 범위와 검증

`manifest_identity.json`을 제공하는 기존 보고서 중 `hf_followup_v1`과 `ktrf_extended_v1` 실행을 선별했다. 각 원본 manifest seal과 네 개 아티팩트의 SHA-256, 요청·응답·채점의 결합 키와 수를 확인했다. 기존 공개 manifest identity, 요청 수, 당시 봉인된 집계 정오 지표와도 대조했다. **점수는 당시 봉인된 채점값**이다. 일부 과거 실행은 현재 grader로 다시 계산하면 달라지므로, 현재 코드의 점수로 덮어쓰거나 새로운 재채점 결과라고 표시하지 않는다. 원래 채점 코드 revision과 아티팩트 해시는 manifest에 남긴다.

총 **48개 실행, 29,664개 요청별 측정**이다. 49개 공개 보고서 참조 중 closure Qwen의 동일 실행 재사용을 한 번만 저장한다. 동일 요청 파일과 동일 응답 파일의 SHA-256 쌍을 기준으로 중복을 제거한다. 이전 형식의 실행과 중복 소스 스냅숏은 이 묶음에 복사하지 않았다.

- [manifest.json](manifest.json): 파일별 해시·행 수·조건별 수, 원본 아티팩트 해시, 코드 revision, 기존 보고서 연결.
- `observations/*.jsonl.gz`: 실행별 요청 단위 지표. 고정 gzip 시간값을 사용해 다시 내보낼 수 있다.
- [model_reproduction.json](model_reproduction.json): Qwen3.5-27B와 KURE-Reranker-nano의 모델 ID·고정 revision·가중치 12개 파일의 크기와 SHA-256.
- [runtime_inventory.json](runtime_inventory.json): 백업 시점 공유 vLLM 환경의 패키지 이름·버전, 공유 모델 파일의 크기·해시. 모든 과거 실험이 이 환경이었다는 검증 기록은 아니다.

## 행의 의미

`case_id_sha256`, `document_id_sha256`, `parent_document_id_sha256`, `family_id_sha256`는 `SHA256(canonical([원래 필드 이름, 원래 값]))`이다. `canonical`은 `eval.hf_qa.canonical`의 정렬된 JSON과 마지막 줄바꿈을 포함한다. 실행별 salt를 쓰지 않으므로 같은 역할의 식별자를 조건·모델·큐 사이에서 결합할 수 있다. 원래 ID의 역할이나 범위는 기존 실험의 정의를 따른다. 문서 내용의 `document_sha256`과 family ID가 모두 있다고 통계적 독립성이 입증되는 것은 아니다.

각 행은 조건·split·repeat, 정오·기권·형식 오류·검증 결과, 입력/출력 토큰과 요청 지연을 제공한다. `usage`는 실행 응답의 관측 비용이다. `prepared_prompt_tokens`는 요청 준비 시 계산한 값으로 정수 또는 모델별 정수 표이며 관측 비용과 구분한다. `prompt_sha256`은 `canonical([system, user])`의 해시이므로 동일 입력 여부를 비교할 수 있다. 검증 위반은 개수만, 서버가 추가한 근거는 `server_added_segment_count`만 보존한다. 자유 텍스트는 내보내지 않는다.

있을 때만 다음 진단을 포함한다.

- `pipeline.exact_core_detected`: 대상 core 위치 일치. 전체 표면형 경계의 정확성을 보장하지 않는다.
- `pipeline.gold_in_candidates`: 후보에 정답이 있는지. `null`을 `false`로 바꾸지 않는다.
- `pipeline.candidate_count`, `resolver_committed`: 후보 수와 resolver 연결 여부. 연결의 의미적 정답 여부와 구분한다.
- `preparation_timing_ms`: `snapshot_compile`, `first_prepare`, `warm_prepare`. 같은 case의 여러 조건·모델에 복사된 준비 측정이므로 요청별로 합산하지 않는다. `first_prepare`는 snapshot compile 이후 측정이며 전체 cold start가 아니다.

누락된 필드는 원본에 자료가 없다는 뜻이다. `null`, `false`, 필드 부재를 같은 값으로 취급하지 않는다. `usage`에 없는 비용은 0이 아니라 미관측이다. `observed=false`인 요청에도 계획된 평가 행은 남기며 오류·누락·malformed를 제외해 분모를 줄이지 않는다.

## 통계와 보장 범위

29,664는 조건·모델·repeat를 포함한 요청별 측정 수이며 독립 질문이나 독립 감사 사건 수가 아니다. 같은 원문을 새 조건에서 실행한 결과는 중복 파일이 아니므로 남아 있다. 비교할 때 기존 보고서의 모집단·소스 이력과 함께 문서/family를 보존한 paired 분석을 사용한다.

`evaluation_split`과 `original_evaluation_split`을 구분한다. `REUSED_SEALED_SOURCE_DIAGNOSTIC`의 기존 confirmation은 새 holdout이 아니다. `source_reused=false`인 `FRESH_AI_AUTHORED_CONFIRMATION`도 사람 gold나 행별 독립 표본을 의미하지 않는다. `human_verified`, `independent_validation`, `evaluation_only`, `authorization_mode`, `execution_authority`를 함께 확인한다. shadow 실험의 승인 결과는 운영 실행 권한을 부여하지 않는다.

QA의 `exact_match`는 기존 추출형 EM이고 `character_f1`은 문자 빈도 overlap이다. 후자를 의미적 정답 보장으로 해석하지 않는다. 이 묶음만으로 원문·답변을 다시 판정할 수는 없으며, 새로운 의미 평가에는 비공개 원본이 필요하다.

## 읽기와 재생성

표준 라이브러리로 바로 읽을 수 있다.

```python
import gzip
import json
from pathlib import Path

root = Path("reports/backup_evidence_20261023")
manifest = json.loads((root / "manifest.json").read_text())
stage = manifest["stages"][0]
with gzip.open(root / stage["file"], "rt", encoding="utf-8") as handle:
    observations = [json.loads(line) for line in handle]
```

원래 로컬 백업에서 새 디렉터리로 다시 내보낸다. 기존 디렉터리는 덮어쓰지 않는다.

```bash
python -m eval.export_backup_evidence \
  --backup /path/to/one-server-20261023T070839Z \
  --output /tmp/krtf-backup-evidence
```

검증 항목: private 필드 배제, 누락/삼값 보존, manifest·아티팩트 변조 거부, 재사용 실행 중복 제거와 각 공개 참조의 검증. 실행·검증 결과는 `validation.json`에 기록한다. 백업·원격 정리 이력은 [완료 기록](../ONE_SERVER_BACKUP_20261023.md)을 따른다.
