# External Hugging Face benchmark

Measured: 2026-10-15T15:37:37.046428+00:00; inference revision: `512e9bc01713d3ee705ef1d026daf025e38ab0f9`.

KBMC measures span-reference recovery with a train-only lexical catalog. TyDiQA measures whether selected source passages retain annotated answers. Neither track measures semantic linking precision, LLM answer accuracy or production risk.

## 결과 해석

2026-10-16 KST 실행에서 KBMC의 `commit/aggressive`는 `fast`보다 정확한 경계를
16건 더 회수했다(+1.12%p). 다만 정답 경계에 놓인 `RESOLVED` 출력 수는 세 모드
모두 725건이다. 추가 후보 회수가 의미상 올바른 entity 확정을 늘렸다는 증거는
아니다. 사전에 표현 가능한 reference 782건은 literal과 세 모드 모두 회수했다.
전체 1,424개 reference 중 나머지에는 미등록 표면형이 포함되므로 전체 회수율과
사전 내 회수율을 구분한다.

`fast`의 관측 p95는 1.62ms, `commit`은 96.08ms였다. 이번 자료에서는 추가 회수에
큰 비용이 따랐다. `aggressive`와 `commit`은 512문서의 mention 응답이 모두 같았으므로,
두 모드 사이의 지연 차이를 다른 알고리즘의 성능 차이로 해석하지 않는다.
이는 신경 backend 없는 직렬 CPU 실행이며, 지연은 순서·부하의 영향을 받는다.

TyDiQA에서는 KTRF를 더해도 최소 정답 보존은 **39/79건으로 동일**했다. 조직명
사전으로 질문을 확장한 경우는 4/256건(1.56%)이고, 선택 구간이 바뀐 것은 2건이다.
정답 근거를 새로 확보하거나 잃은 flip은 모두 0건이다. 현재 사전과 질문 확장 방식이
일반 공개 QA 검색을 개선한다는 증거는 없었다. 검색 두 조건 모두 답변 가능한
79질문 중 40개의 정답 위치를 문맥에서 놓쳤다. LLM의 답변 능력을 높이기 전에
근거 선택의 손실을 별도로 다룰 필요가 있다.

256질문 중 모든 주석이 무응답인 질문은 165개, yes/no 주석이 있는 질문은 11개다.
이 질문들도 목록과 비용 집계에 남아 있다. 무응답을 맞혔다고 점수를 주지 않으며,
최소 정답 위치가 있는 79개만 해당 보존율의 분모가 된다.

## 원천 품질과 검증

- KBMC 6,150행 중 잘못된 BIO 48행과 동일 문장의 상충 주석 25그룹·50행을 제외했다.
  나머지 6,052문서를 training 4,842개와 held-out 후보 1,210개로 나눴고, 그중 512개를
  출력과 무관하게 선택했다. 정답을 임의로 고치거나 충돌한 주석 중 하나를 고르지 않았다.
- TyDiQA validation 18,670행 중 한국어 1,698질문을 모두 로드했다. 최소 정답 byte
  위치가 잘못된 2질문·3주석은 그대로 기록했다. 이 두 질문은 최종 256개 표본에
  포함되지 않아 이번 최소 답변 분모에서 추가로 제외된 질문은 없다.
- 별도 AI 검토자가 원천을 다시 읽어 NER 분모, QA 1,024개 조건 행의 원문 offset
  포함 관계, 문자 예산과 구간 수, 모든 ledger 합계 및 paired flip을 독립 재계산했고
  집계와 일치했다. 이는 새 사람 주석이나 대표 운영 감사가 아니다.
- 고정한 코드의 one-server 전체 회귀 테스트는 **1,197개 통과**, 종료 코드 0이었다.
  벤치마크는 **115.01초**, 종료 코드 0으로 완료했다.

## KBMC boundary reference

512 evaluated documents; 4842 training documents; 512 lexical reference entries.

| Mode | Exact reference hits | Overlap hits | Catalog coverage | Exact recall within catalog | Failures | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| literal | 782/1424 (54.92%) | 1047 | 54.92% | 100.00% | 0 | 0.17 |
| fast | 782/1424 (54.92%) | 1027 | 54.92% | 100.00% | 0 | 1.62 |
| commit | 798/1424 (56.04%) | 1108 | 54.92% | 100.00% | 0 | 96.08 |
| aggressive | 798/1424 (56.04%) | 1108 | 54.92% | 100.00% | 0 | 134.23 |

Commit/aggressive mention-response differences: 0 over 512 successful matched documents.

KBMC source sentences are LLM-generated and human-reviewed, with morpheme spacing preserved. Reference IDs denote type/surface entries, not real-world entities. Off-reference resolver output remains unjudged; no false-link precision is inferred. The split groups exact duplicate text, but allows terms/templates across partitions. It is not a family holdout or representative clinical-document test.

## TyDiQA Korean evidence retention

256 questions from 191 parent articles. All selected no-answer and yes/no questions remain in the ledger.

| Context | Minimal answer retained | Entire annotated passage retained | Mean characters | Failures | p95 ms |
|---|---:|---:|---:|---:|---:|
| none | 0/79 (0.00%) | 0/91 | 0.0 | 0 | 0.00 |
| full | 79/79 (100.00%) | 91/91 | 12696.1 | 0 | 0.00 |
| retrieved | 39/79 (49.37%) | 50/91 | 548.1 | 0 | 18.57 |
| ktrf_expanded | 39/79 (49.37%) | 50/91 | 548.1 | 0 | 94.31 |

`full` is an unbudgeted information ceiling, not an equal-cost baseline. `retrieved` and `ktrf_expanded` share the candidate passages, 3,000-character allowance and three-passage cap; the latter adds up to four resolved canonical names from the question. It does not inject a production context pack or use the experimental assertion checker.

Selected questions with invalid source minimal-answer offsets: 0. These stay in the question ledger but are unevaluable for minimal-answer retention; their positions are not guessed or corrected.

Paired changes: `{"different_source_selection": 2, "harmful_answer_preservation_flips": 0, "helpful_answer_preservation_flips": 0}`.

No-context retention is zero by construction, and full-source retention is a ceiling by construction. Neither is an LLM accuracy measurement. Null/yes-no annotations are not counted as correct abstentions without an answer generator. Multiple questions from one article are correlated. Exact content and available parent IDs are checked against available prior fixtures; missing caches, Wikipedia source overlap and near-duplicates limit independence claims.

## Reproduction and provenance

Install `.[dev,benchmark]`, then run:

```sh
python -m eval.run_hf_benchmark --out-dir eval/out/hf-benchmark
```

See [protocol](../docs/HF_BENCHMARK.md), [dataset inventory](../docs/HF_DATASETS.md), [mode guide](../docs/MODE_EVALUATION.md) and [aggregate JSON](HF_BENCHMARK.json). The JSON records source revisions/hashes, sample and catalog hashes, counts, per-type statistics and observed runtime. Raw source text and individual ledgers are not redistributed.

`coverage_valid=false`; `production_authorized=false`. Fixed lexical scoring and shared-host timings do not establish an operational risk or latency guarantee.

Run logs and status files:

- Benchmark: `/home/seorii/logs/ktrf-hf-benchmark-20261015T153542Z.log`,
  `/home/seorii/logs/ktrf-hf-benchmark-20261015T153542Z.status.json` (exit 0).
- one-server tests: `/home/one/logs/ktrf-hf-512e9bc-tests.log`,
  `/home/one/logs/ktrf-hf-512e9bc-tests.status.json` (exit 0).
- Source acquisition: `/home/seorii/logs/ktrf-hf-acquisition-20261015T152438Z.log`,
  `/home/seorii/logs/ktrf-hf-acquisition-20261015T152438Z.status.json` (exit 0).

An earlier source preflight stopped before any resolver call when identical KBMC
texts had conflicting labels. The quarantine rule and regression checks were
committed before the successful scoring run; no thresholds were changed after
observing performance.
