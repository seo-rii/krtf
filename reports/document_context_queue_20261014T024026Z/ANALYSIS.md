# Document context experiment: interpretation

Both models completed all 768 requests: **1,536 responses, no missing responses, and no API/transport errors**. Gemma 4 12B produced 38 malformed responses; Qwen 3.5 27B produced none. These are 32 AI-authored documents, eight glossary families, twelve knowledge/source conditions, and separate definition-QA and ID-routing requests. They are a controlled stress test, not independent human gold or a deployment-risk estimate.

The strongest findings are that preserving source evidence helps, KTRF's QA packaging makes exact definition extraction easier, and KTRF currently abstains from every positive automatic ID assignment in these colliding-alias families. **The large QA exact-match gap cannot be read directly as a gap in semantic understanding.**

## Official results

Each entry below is `definition QA / ID routing`, each out of 32. Both metrics require a valid response schema and are measured before the condition's execution validator. Each condition has 16 positive targets and 16 targets whose required answer is null; a score of 16 can therefore consist entirely of correct abstentions. Malformed responses remain failures.

| Knowledge | Source | Gemma 4 12B | Qwen 3.5 27B |
|---|---|---:|---:|
| None | None | 16 / 8 | 16 / 16 |
| None | Full | 9 / 13 | 13 / 16 |
| None | Retrieved | 7 / 15 | 11 / 16 |
| Full | None | 16 / 16 | 16 / 16 |
| Full | Full | 15 / 16 | 16 / 18 |
| Full | Retrieved | 14 / 16 | 15 / 17 |
| Retrieved | None | 9 / 14 | 13 / 16 |
| Retrieved | Full | 15 / 23 | 13 / 27 |
| Retrieved | Retrieved | 14 / 19 | 13 / 22 |
| KTRF | None | 16 / 8 | 16 / 16 |
| KTRF | Full | 31 / 13 | 28 / 16 |
| KTRF | Retrieved | 22 / 15 | 22 / 16 |

See the [paired report](documents_comparison.md), [Gemma report](documents_gemma12b/RESULTS.md), and [Qwen report](documents_qwen27b/RESULTS.md) for complete strata, paired changes, evidence visibility, and costs. This analysis does not replace or modify their frozen scores.

## Exact-definition scoring substantially affects the QA comparison

QA asks for a provided definition verbatim. KTRF exposes a dedicated `definition` field whose value is the gold string. Full and retrieved knowledge instead expose prose, where the same definition can be followed by a Korean copula, punctuation, or additional explanatory sentences. Exact equality consequently measures extraction and formatting as well as meaning.

A post hoc inspection of **Qwen's 16 positive targets with retrieved knowledge and full source** found:

- 10 responses contain the exact gold definition as a substring but add a suffix or explanation;
- 4 responses are null;
- 2 responses give a name or type rather than the gold definition;
- none matches the complete gold string exactly.

Examples from the frozen responses:

| Case | Gold definition | Returned answer |
|---|---|---|
| `f02-d01:document_qa` | 사내 네트워크 장애를 접수하고 통신 복구를 담당하는 팀 | 사내 네트워크 장애를 접수하고 통신 복구를 담당하는 팀이다. |
| `f07-d01:document_qa` | 신규 고객의 서비스 이전과 초기 설정을 지원하는 조직 | 신규 고객의 서비스 이전과 초기 설정을 지원하는 조직이다. |
| `f08-d01:document_qa` | 서버의 자원 사용량과 과부하 징후를 보여 주는 관측 화면 | 서버의 자원 사용량과 과부하 징후를 보여 주는 관측 화면이다. |

The ten substring-containing cases are `f01-d01`, `f01-d02`, `f02-d01`, `f04-d01`, `f05-d01`, `f05-d02`, `f06-d01`, `f07-d01`, `f07-d02`, and `f08-d01`. This is a descriptive inspection, **not a replacement semantic score**: substring inclusion alone is not a general correctness criterion, and the original response contract remains unchanged. The official 13/32 in this condition comes from correct null answers, while these ten positive responses fail exact matching.

KTRF with full source reaches 31/32 for Gemma and 28/32 for Qwen. That supports its utility for this definition-extraction contract, but does not establish that it understands twice as many cases as plain retrieval. A subsequent experiment should keep candidate definitions and their representation comparable across arms, and retain a separately specified semantic evaluation for free wording.

## Source evidence matters; automatic ID coverage remains zero for KTRF

The full source exposes annotated decision cues for 32/32 documents. Retrieved source windows expose them for only 16/32. With KTRF knowledge, replacing full source with retrieved source reduces QA from 31 to 22 for Gemma and from 28 to 22 for Qwen. This is consistent with the loss of distant disambiguating evidence. The source document is already known in this track; these results evaluate paragraph selection, not corpus-wide document retrieval.

KTRF's automation profile provides no authorized ID for any positive target in any source condition. The frozen packs exclude ambiguous mentions (`profile_excludes_ambiguous`), so positive-gold ID visibility is 0/16 and **accepted correct non-null IDs are zero for both models**. Qwen returns null throughout. Gemma proposes three wrong non-null IDs with full source and one with retrieved source; KTRF's execution guard rejects all four. This protects the execution boundary but does not recover useful automatic routing on the collision cases.

With retrieved knowledge and full source, Gemma instead produces **8 accepted correct IDs and 2 accepted wrong IDs**, while Qwen produces **11 accepted correct IDs and 0 accepted wrong IDs**. Qwen falls to 7 correct and 2 wrong accepted IDs when the source is also retrieved. Baseline acceptance checks schema and membership in provided IDs; KTRF uses its complete-response guard. These operational counts describe different system contracts and must not be treated as interchangeable validator performance. The common routing scores in the table above precede both validators.

Providing the entire knowledge document does not by itself solve routing: with full source, Gemma returns null for all 32 documents; Qwen returns two correct positive IDs and 30 nulls. Full knowledge exposes both colliding meanings. Narrowing knowledge to a relevant passage reduces this observed abstention, while also introducing retrieval misses and some wrong selections.

## Model differences include both format and meaning

For KTRF QA with full source, Gemma answers 15/16 positive targets correctly and abstains correctly on all 16 negative targets. Its remaining positive response is null. Qwen answers all 16 positives correctly but gives non-null answers for four negative targets:

- `f03-d04` and `f07-d04` ask about a chair/director. Qwen returns the committee/center definition, conflating a person-role expression with the organization.
- `f04-d03` and `f05-d04` are unregistered satellite/artwork names. Qwen describes them using the source document. These descriptions reflect source content but violate the requested contract of returning a registered glossary definition or null; they should not simply be called hallucinations.

Gemma's 38 malformed responses comprise 19 routing responses in `none__none`, 18 routing responses in `ktrf__none`, and one QA response in `full__retrieved`. A representative failure adds an explanatory sentence before a JSON object. This is an output-contract failure, not evidence that every embedded answer was semantically wrong. Qwen has no malformed outputs. Model family and training change along with parameter count, so this comparison does not isolate the effect of increasing size.

## Costs and next interpretation step

For definition QA with full source, the following values summarize 32 calls per condition. Prompt tokens are the mean of reported model usage; p95 is recorded model-call latency.

| Model | Knowledge | Mean prompt tokens | p95 latency |
|---|---|---:|---:|
| Gemma 4 12B | Full | 727.1 | 1.23 s |
| Gemma 4 12B | Retrieved | 528.5 | 2.36 s |
| Gemma 4 12B | KTRF | 973.3 | 1.54 s |
| Qwen 3.5 27B | Full | 656.8 | 2.98 s |
| Qwen 3.5 27B | Retrieved | 480.1 | 5.63 s |
| Qwen 3.5 27B | KTRF | 898.0 | 2.49 s |

KTRF's extra policy and structured context increase prompt length in this small-document experiment. Longer generated answers can also increase latency, so prompt size alone does not explain the observed timing. Preparation and retrieval costs are excluded; shared-host serving conditions affect latency.

The next useful comparison is to separate definition formatting from candidate selection, evaluate source-window recall explicitly, and measure whether context-aware disambiguation can recover correct authorized IDs without accepting the person/organization and NIL errors. None/none is an information floor for private definitions and opaque IDs, not a knowledge-parity baseline. The authored sample, deterministic lexical retrieval, and these post hoc inspections do not support a deployment accuracy or risk guarantee.

Raw evidence is preserved in each model's `requests.jsonl` and `responses.jsonl`. Code revision: `604666e41c3133ec3032bfd23f69fa4c1bc5d6c9`; shared request SHA-256: `33cdb7b94492e9cc5d24caef4a29c12cce12a94f2633ebb2e5b479cda241b9da`.
