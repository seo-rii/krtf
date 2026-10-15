# Hugging Face 평가 자료 검토

확인일: 2026-10-16. 기존 KLUE/KONEC, KoNeoBench, KorQuAD 1.0 원문과
AI 작성 문서 평가를 보완할 자료를 조사했다. 아래 revision은 조사 당시 HF API에서
확인한 값이며, 평가 manifest에는 실제 다운로드 파일의 SHA-256도 기록한다.
데이터셋 설명의 규모와 이번 실행에서 사용한 행 수는 구분한다.

## 반영 대상과 측정 범위

| 자료 | 선택 이유 | 실제 필드 | 이번 평가의 범위 |
|---|---|---|---|
| SungJoo/KBMC | 의료 용어라는 다른 도메인과 인간이 검토한 주석 | 대문자 `Sentence`, `Tags`; 태그는 `Disease-B`, `Body-I`, `Treatment-B`, `O` 등 | 배포된 분절 문장 안의 reference span 회수. 실제 의료 문서 검증으로 해석하지 않음 |
| Google TyDiQA primary validation의 한국어 행 | 실제 질문과 전체 원문, 정답 위치 및 무응답 주석 | `question_text`, `document_plaintext`, `document_title`, `document_url`, `language`, `passage_answer_candidates`, `annotations` | 제공한 문맥에 정답·근거 위치가 남는지 평가. LLM 답변 정확도나 entity linking 정확도가 아님 |

KBMC는 entity ID 정답이 없다. 주석된 표면형으로 평가용 사전을 만들더라도
이를 독립 entity linking gold라고 부르지 않는다. 같은 행의 정답을 보고 그 행만의
사전을 만들지 않으며, 분할과 표면형 중복 처리 방법은 평가 프로토콜에 기록한다.
서로 다른 자료의 점수를 하나의 운영 오류율로 합산하지 않는다.

## 고정 원천과 라이선스

### Naver NER 변환본: 확인 후 기본 대상에서 제외

- HF: [HERIUN/kor-ner-spacy-data](https://huggingface.co/datasets/HERIUN/kor-ner-spacy-data).
- Revision: `3427cb52e81bba251311cec48710b47f891073f2`.
- [고정 카드](https://huggingface.co/datasets/HERIUN/kor-ner-spacy-data/blob/3427cb52e81bba251311cec48710b47f891073f2/README.md),
  [고정 JSONL](https://huggingface.co/datasets/HERIUN/kor-ner-spacy-data/resolve/3427cb52e81bba251311cec48710b47f891073f2/data/naver_ner_dataset.jsonl).

이 HF 저장소는 여러 자료를 모은 변환본이다. 이번 검토 대상은
`data/naver_ner_dataset.jsonl`이며, AI Hub·KMOU 파일까지 같은 원천으로 취급하지 않는다.
필드는 `text`, `entities: [[start, end, label], ...]`이고 문자 위치는 Python slice와
같은 시작 포함·끝 제외다.

HF 카드는 CC BY 4.0을 표시한다. 그러나
[원본 Naver 참가 동의서](https://github.com/naver/nlp-challenge/blob/a51654472e0da75cd37c6e73ffe583db78e68323/AGREEMENT.md)는
자료의 권리 귀속과 대회 목적 외 사용·보관·배포 제한을 명시한다. 따라서 변환자의
카드만으로 원본의 이용 조건이 해소되었다고 판단할 수 없다. 이번 벤치마크의 기본
다운로드·실행 대상에서 제외하고, 발견한 표기 차이와 제외 사유를 남긴다.

### KBMC

- HF: [SungJoo/KBMC](https://huggingface.co/datasets/SungJoo/KBMC).
- Revision: `9cd99c088d3192577f9355b4832b96c3087996e8`.
- [고정 카드](https://huggingface.co/datasets/SungJoo/KBMC/blob/9cd99c088d3192577f9355b4832b96c3087996e8/README.md),
  [고정 TSV](https://huggingface.co/datasets/SungJoo/KBMC/resolve/9cd99c088d3192577f9355b4832b96c3087996e8/KBMC.tsv).
- 카드 라이선스: Apache 2.0. 배포 split 이름은 `train`이며 독립 공식 test로 바꾸어 부르지 않는다.

[원 논문](https://aclanthology.org/2024.lrec-main.868/)에 따르면 문장은
KOSTOM 의료 용어를 바탕으로 `gpt-3.5-turbo`가 생성했다. 사전으로 먼저 태깅한 뒤
네 사람이 수정하고 별도 검토자가 검토했다. 따라서 인간 검토를 거친 **합성 문장**이다.
논문이 사용하는 Naver 결합 학습 자료와 HF의 KBMC 단독 TSV도 구분한다.

`Sentence`는 이미 형태소 단위로 띄어 쓴 문자열이다. 이를 임의로 붙여 원래 자연 문장을
복원했다고 주장하지 않는다. 배포 문자열을 그대로 평가 입력으로 쓰고 토큰 위치를
그 문자열의 문자 위치로 변환하며, 토큰·태그 수가 맞지 않는 행은 조용히 고치지 않는다.

### TyDiQA

- HF: [google-research-datasets/tydiqa](https://huggingface.co/datasets/google-research-datasets/tydiqa).
- Revision: `da78f23f9119363459acbaf46bf89426ff26c259`.
- [고정 카드](https://huggingface.co/datasets/google-research-datasets/tydiqa/blob/da78f23f9119363459acbaf46bf89426ff26c259/README.md),
  [고정 primary validation Parquet](https://huggingface.co/datasets/google-research-datasets/tydiqa/resolve/da78f23f9119363459acbaf46bf89426ff26c259/primary_task/validation-00000-of-00001.parquet).
- 카드 라이선스: Apache 2.0. 원문은 Wikipedia에서 왔으므로 원문 출처도 보존한다.

[공식 설명](https://github.com/google-research-datasets/tydiqa)은 번역 없이 각 언어로
작성한 질문과 사람이 주석한 정답을 제공한다. `primary_task`는 전체 원문과 무응답을
포함한다. `secondary_task`는 이미 정답이 있다고 보장된 문단만 제공하고 무응답을 제외하므로
전체 문서·무응답 조건의 대체재로 쓰지 않는다.

Primary의 위치는 UTF-8 **byte** 기준이다. `minimal_answers_start_byte/end_byte`와
`passage_answer_candidates.plaintext_start_byte/end_byte`를 문자 위치처럼 자르면 안 된다.
`annotations`에는 passage index, 최소 답변 위치, `yes_no_answer`가 있으며 `-1`을
빈 문자열 정답으로 바꾸지 않는다. 여러 주석, yes/no, 무응답은 각각 보존한다.

원천 페이지와 문서가 기존 KorQuAD·Wikipedia·KONEC 계열과 겹칠 수 있다. 신규 행이라는
이유만으로 원천 독립성을 단정하지 않고 URL·제목·내용 해시로 중복을 확인한다.
같은 페이지의 여러 질문은 문서 단위로 묶고, 긴 문서와 무응답을 편의상 제외하지 않는다.

## 이번 통합에서 제외한 후보

| 후보 | 확인 결과와 제외 이유 |
|---|---|
| [coref-data/korean_ecmt_raw](https://huggingface.co/datasets/coref-data/korean_ecmt_raw) | 카드에는 entity linking 원천이 설명되지만 HF 실제 행은 `doc_id`, `sentences`의 lemma/POS/NER/coreference 정보, `coref_chains`다. 원문 문자열·문자 offset·KB ID가 없어 lemma를 이어 붙여 linking gold로 사용할 수 없다. 원본 자료를 별도 확인해야 한다. 카드 라이선스는 CC BY-NC-SA 4.0 |
| [apple/mkqa](https://huggingface.co/datasets/apple/mkqa) | 한국어 질문과 `answers.ko`의 정답·별칭·entity ID는 유용하나 전체 문서와 span이 없다. HF는 로딩 스크립트를 제공하며 viewer만으로 원문 문맥을 확보할 수 없다. 카드 라이선스는 CC BY 3.0 |
| [unimelb-nlp/wikiann](https://huggingface.co/datasets/unimelb-nlp/wikiann) | 한국어 `tokens`, BIO `ner_tags`, `langs`, `spans`는 있지만 자동 구축한 Wikipedia 기반 silver다. 원문 offset·entity ID를 갖춘 독립 인간 gold가 아니며 카드 라이선스도 `unknown` |
| [Raoyuan/MAKIEval](https://huggingface.co/datasets/Raoyuan/MAKIEval) | `generated_text`와 JSON 문자열 `entities`에 QID가 있으나 LLM 생성 텍스트·자동 연결 자료다. 실제 독립 문서 gold와 구분해야 한다. 카드 라이선스는 CC BY 4.0 |
| [KorQuAD/squad_kor_v2](https://huggingface.co/datasets/KorQuAD/squad_kor_v2) | 전체 HTML과 답변 위치는 유용하다. 다만 기존 KorQuAD와 원천이 겹치고, 카드 머리말의 CC BY-ND 4.0과 본문의 CC BY-ND 2.0 KR 표기가 달라 이번 우선 통합에서 제외 |

## 저장·공개 원칙

원본 다운로드와 변환한 평가 행은 실행용 별도 디렉터리에 둔다. 제3자 원문, 모델 입력에
포함된 원문, 사례별 원문 인용은 저장소에 커밋하지 않는다. 공개 보고서는 자료 revision,
파일 해시, 실제 평가 수, 제외 사유, 집계 지표와 평가 코드를 제공한다. 자료 탐색 결과와
실제 벤치마크 결과를 구분하며, 실행 전 이 문서만으로 점수나 실행 행 수를 선언하지 않는다.
