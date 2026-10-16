# TyDiQA 한국어 LLM 답변 비교

기존 [HF 벤치마크](HF_BENCHMARK.md)는 경계 회수와 정답 근거 보존을 측정했다.
이번 평가는 실제 LLM의 답변을 생성해, 정보량·검색·KTRF 개입을 분리해 비교한다.
실행 전 요청·정답·정규화·채점·표집을 고정한다. 준비 단계의 테스트 성공을 모델
정답률로 보고하지 않는다.

## 비교 조건

| 조건 | 원문·추가 정보 | 답변 정책 |
|---|---|---|
| `none_knowledge` | 질문만 | 자체 지식 허용. 답변 가능한 질문의 정답률을 별도로 측정 |
| `none_evidence` | 질문만 | 제공 원문에만 의존. 원문이 없으므로 기권 정책의 대조군 |
| `full` | 원본 기사 전체 | 원문에 근거하고 답이 없으면 null |
| `retrieved` | 질문으로 고른 lexical 검색 구간 | 위와 같음 |
| `ktrf_expanded` | KTRF가 확정한 canonical 이름으로 질문을 확장한 후 같은 검색 | 위와 같음 |
| `ktrf_pack` | `retrieved`와 같은 원문 구간 + 실제 `qa_grounding` pack·정책 | 원문 해석에 pack을 보조 사용. 원문에 없는 답을 추가하지 않음 |

검색은 기존 HF 평가와 같은 3,000문자·최대 세 구간 예산이다. 선택기에 정답 위치를
넘기지 않는다. `ktrf_pack`은 `should_inject`가 참일 때만 실제 XML과 정책을 넣으며,
생산 API의 context pack 개입을 평가한다. 포맷 효과만 분리하는 실험은 아니다.
`scoped_asserted` 실험은 연결하지 않는다.

질문·원문·정답은 여섯 조건에서 동일하다. 각 호출은 별도 대화이고, 조건 순서는
질문마다 회전시킨다. 두 모델에는 같은 요청 파일을 제공한다. 전송 필드는
`system`, `user`뿐이며 원천 정답·정답 위치·채점 메타데이터는 보내지 않는다.
잘못된 JSON·추가 필드·빈 문자열·API 오류를 고치거나 재시도하지 않는다.

## 원천과 표집

[고정 HF TyDiQA primary validation](https://huggingface.co/datasets/google-research-datasets/tydiqa/blob/da78f23f9119363459acbaf46bf89426ff26c259/README.md)의
한국어 1,698질문을 읽는다. 앞선 HF 평가의 256질문과 같은 원천이므로 새 독립
코퍼스처럼 합산하지 않는다. 원문 해시와 사용 가능한 기존 parent/URL 중복 검사도
수행하되, 모델 사전학습·Wikipedia 기사 중복이 없다고 주장하지 않는다.

한국어 행에는 주석이 세 개 있다. 유효한 최소 span 또는 YES/NO 주석이 두 개 이상이면
답변 가능 후보로 둔다. 최소 답변 위치 오류가 있는 질문, SPAN/YESNO 혼합,
문단만 정답인 경우와 투표가 부족한 경우는 각각 원천 제외 사유로 남긴다.
음성은 세 주석 모두 `NO_ANSWER`인 질문을 쓴다. 한 명만 답을 찾은 논쟁적인 사례를
기권 정답으로 강제하지 않는다.

목표 표본은 **SPAN 56개·YES/NO 8개·무응답 64개**, 총 128질문이다. 코드에 고정한
seed의 ID 해시 순으로 각 목표의 세 배인 screening pool을 먼저 뽑는다. 이 pool의
모든 조건을 두 checkpoint의 실제 tokenizer/chat template으로 검사한다. prompt와
128개 출력 토큰을 합쳐 8,192토큰에 들어가는 질문만 공통 후보가 된다.
원문을 자르지 않는다. 부족하면 `INSUFFICIENT_DATA`로 중단한다.

공통 후보에서 같은 seed 순으로 목표 수를 선택하며, 기사 parent당 질문은 하나만
남긴다. source 제외·pool 규모·모델별 overflow·공통 fit·최종 strata와 기사 수를
모두 기록한다. pool 밖 긴 문서까지 모델 용량을 검사했다고 주장하지 않는다.
균형 표본의 전체 정확도를 원천 분포나 운영 정확도로 일반화하지 않는다.

## 채점

[공식 TyDiQA primary scorer](https://github.com/google-research-datasets/tydiqa/blob/43cde6d598c1cf88c1a8b9ed32e89263ffb5e03b/tydi_eval.py)는
byte span을 평가한다. 이번 생성 문자열 점수는 **KTRF 프로젝트의 진단 지표**이며
공식 TyDi 점수가 아니다.

- 주 지표는 유효한 원천 답변 중 하나와의 normalized exact match다. NFC·casefold·
  공백 정리만 적용하며 소수점·구두점은 지우지 않는다. YES/NO 별칭은 해당 타입에서만 허용한다.
- 답변 가능 64개와 원문 무응답 64개를 분리한다. 자체 지식 조건의 원문 무응답은
  판단하지 않는다. 해당 기사에 없다는 주석이 세상에 답이 없다는 뜻은 아니기 때문이다.
- 문자 F1은 부분 일치 진단이다. 문자 순서를 반영하지 않아 EM과 동등한 정확도로 해석하지 않는다.
- 정답을 말했더라도 선택한 원문에 정답 근거가 없는 경우를 별도 집계한다.
  모델 자체 지식으로 맞힌 답과 근거 보존을 혼동하지 않는다.
- 원문 무응답의 null, 과잉 응답, 답변 가능 질문의 과잉 기권, malformed·누락을 따로 센다.
  실패를 올바른 null로 보상하지 않는다.
- `retrieved` 대비 `full`, `ktrf_expanded`, `ktrf_pack`의 helpful/harmful flip을
  같은 질문에서 계산한다. 오류·malformed 쌍은 불완전 비교로 남긴다.

## 실행·공개

Gemma4 12B와 Qwen3.5 27B를 one-server에서 한 번에 하나씩 실행한다. family와
크기가 함께 바뀌므로 크기만의 효과로 해석하지 않는다. 온도 0, seed 0, thinking off,
출력 128토큰, batch 1이다. 실제 checkpoint 설정 hash와 확인 가능한 revision을
기록하며, Gemma의 upstream identity가 확인되지 않은 경우 이를 숨기지 않는다.

schema 5 queue는 고정 코드의 테스트 성공과 두 tokenizer의 실제 길이 증빙을 요구한다.
GPU·port가 바쁘면 기다리고 다른 작업은 종료하지 않는다. 큐가 만든 서버 프로세스만
정리한다. 실행 상태와 로그는 사용자 전용 경로에 보존한다.

수집기는 완료 후 원문·프롬프트·응답을 gitignored private 경로로 가져와 artifact hash,
manifest seal, 환경, 요청 identity와 채점을 다시 검증한다. 공개 파일은 집계와
manifest·실행 증빙뿐이다. raw 원문·개별 답변·로그 원문은 커밋하지 않는다.
검증된 결과만 현재 `main`이 `origin/main`과 같을 때 자동으로 커밋·푸시한다.
다른 작업으로 branch나 동기화 상태가 바뀌면 결과를 로컬에 남기고 수집을 실패 처리한다.

```sh
python -m eval.prepare_hf_qa --out-dir eval/out/hf-qa-pool --code-revision COMMIT
# one-server에서 두 실제 tokenizer로 pool을 검사하고 최종 요청을 동결한다.
python -m eval.prepare_hf_qa --pool-file POOL_JSON --models-file MODELS_JSON \
  --out-dir NEW_REQUEST_DIRECTORY --code-revision COMMIT
python -m eval.prepare_hf_qa --check-tokens-plan QUEUE_PLAN
python -m eval.run_production_queue --plan QUEUE_PLAN
python -m eval.collect_hf_qa_queue --config LOCAL_COLLECTOR_CONFIG
```

실험 상태는 queue status가 terminal인지로 확인한다. 한 모델이 추론 전에 실패하면
실패 증빙과 출력 디렉터리 부재를 확인한 뒤, 완료 모델의 집계를 별도로 검증해
게시한다. 누락된 모델은 0점으로 취급하지 않으며 두 모델 비교를 생성하지 않는다.
같은 고정 추론 입력을 유지한 재실행은 원본 계획·종료 상태 해시와 완료 모델의
봉인된 산출물을 확인해 실패 모델만 다시 실행한다. 새 실행기 코드와 테스트 증빙은
추론 코드 revision과 별도로 기록한다. 이 평가는 entity ID 자동 실행이나 운영 위험
보장을 부여하지 않는다.

[Qwen의 검증된 결과와 제한](../reports/hf_qa_queue_20261016/ANALYSIS.md)을 먼저
보고하며, 두 모델의 최종 집계가 검증되면 같은 질문의 모델 비교를 게시한다.
