# 추가 다섯 실험의 고정 계약

기존 TyDiQA 결과를 본 뒤 설계한 후속 실험이다. 결과를 보기 전에 질문,
정답, 조건, 입력 순서, 코드 revision과 실제 tokenizer 검증을 고정한다.
새 데이터에서 방법의 재현성을 확인하되, 배포 오류율이나 독립된 사람 평가로
해석하지 않는다. 운영 기본값과 확정 임계값은 변경하지 않는다.

| 순서 | 트랙 | 모델별 요청 | 비교 |
|---|---|---:|---|
| 1 | `transfer` | 1,024 | KLUE-MRC 256문항 × lexical/BM25 × KTRF pack 유무 |
| 2 | `budget` | 512 | 128문항 × 전체 prompt 상한 1,024/1,536 tokens × BM25 pack 유무 |
| 3 | `corpus` | 512 | 정답 존재 128문항 × 512문서 검색 lexical/BM25 × pack 유무 |
| 4 | `pack` | 640 | 128문항 × 없음/평문 중립/JSON 중립/평문 보수/JSON 보수 |
| 5 | `semantic_safety` | 96 | 동명이의·기관/역할·과거/현재·모호성/비언급의 실행 ID 검증 |

Gemma 12B의 다섯 트랙 다음에 Qwen 27B의 다섯 트랙을 직렬 실행한다.
총 **5,568회**, 조건별 반복은 1회다. 두 모델에는 동일한 봉인 요청을 사용한다.
단순 크기 비교가 아니라 모델 계열과 크기가 함께 변하는 비교다.

## 자료와 표본

[KLUE 공식 HF 자료](https://huggingface.co/datasets/klue/klue/blob/349481ec73fff722f88e0453ca05c77a447d967c/README.md)의
`mrc/validation-00000-of-00001.parquet`를 revision
`349481ec73fff722f88e0453ca05c77a447d967c`에 고정한다. 카드의 라이선스는
CC BY-SA 4.0이다. 원문과 개별 모델 답변은 비공개 실행 디렉터리에 보관하고
공개 보고서에는 해시·설정·집계만 포함한다.

원본 5,841문항 중 SPAN 4,008건, NO_ANSWER 1,833건이다. 정답 offset은
원문 codepoint로 검증한다. `is_impossible`에 딸린 plausible answer를
정답으로 쓰지 않는다. 원문 기사 ID가 없는 자료이므로 context hash를
parent identity로 보존하고, 원래 기사의 독립성이 확인됐다고 주장하지 않는다.

기존 TyDiQA 한국어 전체 원문, KLUE-NER validation 전체 5,000문장,
기존 KONEC·KoNeoBench blind 문서를 제외 입력으로 봉인한다. NER의
`<surface:TYPE>` 표기는 원문 문자 토큰과 대조한 뒤 제거한다.
정규화 exact·문장 포함·문자 5-gram 포함률 기준으로 겹치는 문맥을 제외한다.
이는 선언된 입력에 대한 필터이며 의미적 중복이나 모델 사전학습 오염을
완전히 배제하지 않는다.

문맥이 중복되지 않는 SPAN 128건과 NO_ANSWER 128건을 먼저 선택한다.
`budget`과 `pack`은 여기서 각 64건씩 뽑은 동일 128문항을 사용한다.
검색 성공이나 pack 주입 여부를 보고 표본을 바꾸지 않는다. 네 QA 트랙의
점수를 독립된 표본처럼 합산하지 않는다.

## 비교에서 고정하는 것

- `transfer`: 알고 있는 원문 안에서 최대 3개 window, 3,000자,
  두 tokenizer 각각 source 1,536 tokens 상한을 적용한다.
  같은 ranker의 pack 유무 조건은 원문 window가 같다.
- `budget`: system, 질문, 검색 근거, pack, 정책, 실제 chat template까지
  합친 전체 입력 상한을 맞춘다. pack이 차지하는 만큼 원문량이 줄 수 있다.
  상한이 같다는 뜻이며 사용 토큰이 완전히 같다는 뜻은 아니다. padding은 없다.
- `corpus`: 질문만으로 고정된 512개 문맥을 검색한다. 검색 함수에 정답이나
  정답 문서 ID를 넘기지 않는다. 모든 positive anchor는 코퍼스에 포함한다.
  원문의 NO_ANSWER가 코퍼스 전체 무응답을 뜻하지 않으므로 이 트랙에서는
  무응답 성능을 계산하지 않는다. 열린 웹 전체를 검색하는 실험도 아니다.
- `pack`: 같은 BM25 근거와 같은 최소 fact card를 평문/JSON으로 표현한다.
  full production JSON의 부가 metadata 차이는 제거한다. 중립·보수 정책
  모두 근거 안에서 답하게 하며, 보수 조건만 KTRF 안전 정책을 더한다.
  `should_inject=false`이면 pack이나 그 정책을 강제로 넣지 않는다.
- `semantic_safety`: 24 family ×4문항, 각 family LINK 2건과 비LINK 2건.
  AI가 작성하고 별도 AI가 정답을 검토한 진단 자료다. 실제 production
  automation context와 execution guard에 모델의 전체 parsed response를
  통과시킨다. guard 통과 여부와 의미적 정답 여부를 별도로 채점한다.
  오류를 없애기 위한 gold 변경이나 실패 사례 제외는 하지 않는다.

## 채점과 실행 계약

temperature 0, seed 0, thinking off, 출력 최대 128 tokens, strict JSON
Schema를 공통으로 적용한다. 요청을 재시도하거나 답변을 보정하지 않는다.
문서 QA는 normalized exact match·문자 F1, positive/negative 분모,
근거 내 정답 보존, 유익한 전환·해로운 전환을 분리한다. 실행 안전성은
올바른 ID 허용·잘못된 ID 허용·잘못된 ID 차단·올바른 기권·과잉 기권을
분리한다. 형식 오류와 API 오류, 누락, 실제 토큰, 지연도 함께 기록한다.

신뢰구간이 필요한 후속 해석에서는 동일 문맥과 합성 family의 의존성을
보존해야 한다. 96개 합성 문항을 96개 독립 원천으로 취급하지 않는다.
이 실험으로 임계값을 고르거나 배포 위험 보장을 산출하지 않는다.

전체 테스트, 실제 두 tokenizer 준비, vLLM IPC bind, 봉인 소스/입력 검증 후
GPU 큐를 시작한다. 완료 후 원시 출력을 다시 파싱·재채점하고 원격 집계와
일치할 때만 집계 보고서를 커밋·푸시한다. 하나의 독립 트랙에서 실행 오류가
나더라도 다음 트랙은 수행하고, 실패 상태를 성공으로 바꾸지 않는다.
