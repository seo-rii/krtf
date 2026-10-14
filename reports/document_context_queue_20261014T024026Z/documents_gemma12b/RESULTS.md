# Knowledge and source document context experiment

Status: **COMPLETE**. Model: `ktrf-production-gemma4-12b-bf16`. 32 complete authored documents × 12 conditions × 2 tasks; 768 calls planned.

Gold: `AI_AUTHORED_SYNTHETIC`; human verified: `false`. Authored documents and AI gold do not establish deployment risk.

Received 768; missing 0; malformed 38; API/transport errors 0.

Knowledge modes: no knowledge, the full knowledge document, retrieved knowledge passages, and KTRF. Source modes: no surrounding source, the full source document, and retrieved source passages with neighbors. Both axes vary independently; the no/no condition contains only the question and target expression. Every condition uses new inference; no historical C outputs are reused.

The primary metric is a schema-valid exact semantic match **before** each arm's validator. QA and ID routing are reported separately. There is no pooled primary score.

## Semantic outcomes

| Knowledge | Source | Task | Match / planned | Positive null | Correct null | Wrong non-null | Malformed | Missing |
|---|---|---|---:|---:|---:|---:|---:|---:|
| none | none | document_qa | 16/32 | 16 | 16 | 0 | 0 | 0 |
| none | none | structured_routing | 8/32 | 5 | 8 | 0 | 19 | 0 |
| none | full | document_qa | 9/32 | 14 | 7 | 9 | 0 | 0 |
| none | full | structured_routing | 13/32 | 16 | 13 | 3 | 0 | 0 |
| none | retrieved | document_qa | 7/32 | 16 | 7 | 9 | 0 | 0 |
| none | retrieved | structured_routing | 15/32 | 16 | 15 | 1 | 0 | 0 |
| full | none | document_qa | 16/32 | 16 | 16 | 0 | 0 | 0 |
| full | none | structured_routing | 16/32 | 16 | 16 | 0 | 0 | 0 |
| full | full | document_qa | 15/32 | 11 | 15 | 6 | 0 | 0 |
| full | full | structured_routing | 16/32 | 16 | 16 | 0 | 0 | 0 |
| full | retrieved | document_qa | 14/32 | 15 | 14 | 2 | 1 | 0 |
| full | retrieved | structured_routing | 16/32 | 16 | 16 | 0 | 0 | 0 |
| retrieved | none | document_qa | 9/32 | 5 | 8 | 18 | 0 | 0 |
| retrieved | none | structured_routing | 14/32 | 12 | 12 | 6 | 0 | 0 |
| retrieved | full | document_qa | 15/32 | 3 | 12 | 14 | 0 | 0 |
| retrieved | full | structured_routing | 23/32 | 7 | 15 | 2 | 0 | 0 |
| retrieved | retrieved | document_qa | 14/32 | 4 | 11 | 14 | 0 | 0 |
| retrieved | retrieved | structured_routing | 19/32 | 11 | 15 | 2 | 0 | 0 |
| ktrf | none | document_qa | 16/32 | 16 | 16 | 0 | 0 | 0 |
| ktrf | none | structured_routing | 8/32 | 6 | 8 | 0 | 18 | 0 |
| ktrf | full | document_qa | 31/32 | 1 | 16 | 0 | 0 | 0 |
| ktrf | full | structured_routing | 13/32 | 16 | 13 | 3 | 0 | 0 |
| ktrf | retrieved | document_qa | 22/32 | 10 | 16 | 0 | 0 | 0 |
| ktrf | retrieved | structured_routing | 15/32 | 16 | 15 | 1 | 0 | 0 |

## Provided evidence

Source presence includes decision cues for null-gold targets. Definition and entity-ID recall use positive gold only. Visibility does not imply the model used the evidence correctly.

| Knowledge | Source | Task | Source cue / annotated | Definition / positive | ID / positive |
|---|---|---|---:|---:|---:|
| none | none | document_qa | 0/32 | 0/16 | 0/16 |
| none | none | structured_routing | 0/32 | 0/16 | 0/16 |
| none | full | document_qa | 32/32 | 4/16 | 0/16 |
| none | full | structured_routing | 32/32 | 4/16 | 0/16 |
| none | retrieved | document_qa | 16/32 | 1/16 | 0/16 |
| none | retrieved | structured_routing | 16/32 | 1/16 | 0/16 |
| full | none | document_qa | 0/32 | 16/16 | 16/16 |
| full | none | structured_routing | 0/32 | 16/16 | 16/16 |
| full | full | document_qa | 32/32 | 16/16 | 16/16 |
| full | full | structured_routing | 32/32 | 16/16 | 16/16 |
| full | retrieved | document_qa | 16/32 | 16/16 | 16/16 |
| full | retrieved | structured_routing | 16/32 | 16/16 | 16/16 |
| retrieved | none | document_qa | 0/32 | 8/16 | 8/16 |
| retrieved | none | structured_routing | 0/32 | 8/16 | 8/16 |
| retrieved | full | document_qa | 32/32 | 14/16 | 13/16 |
| retrieved | full | structured_routing | 32/32 | 14/16 | 13/16 |
| retrieved | retrieved | document_qa | 16/32 | 12/16 | 12/16 |
| retrieved | retrieved | structured_routing | 16/32 | 12/16 | 12/16 |
| ktrf | none | document_qa | 0/32 | 16/16 | 16/16 |
| ktrf | none | structured_routing | 0/32 | 0/16 | 0/16 |
| ktrf | full | document_qa | 32/32 | 16/16 | 16/16 |
| ktrf | full | structured_routing | 32/32 | 4/16 | 0/16 |
| ktrf | retrieved | document_qa | 16/32 | 16/16 | 16/16 |
| ktrf | retrieved | structured_routing | 16/32 | 1/16 | 0/16 |

## Knowledge changes at fixed source

Helpful means the current condition succeeds where baseline fails; harmful means the reverse. Missing pairs are incomplete; malformed responses remain failures.

| Fixed mode | Change | Task | Comparable | Helpful | Harmful | Incomplete |
|---|---|---|---:|---:|---:|---:|
| none | none_to_full | document_qa | 32 | 0 | 0 | 0 |
| none | none_to_full | structured_routing | 32 | 8 | 0 | 0 |
| none | none_to_retrieved | document_qa | 32 | 1 | 8 | 0 |
| none | none_to_retrieved | structured_routing | 32 | 8 | 2 | 0 |
| none | none_to_ktrf | document_qa | 32 | 0 | 0 | 0 |
| none | none_to_ktrf | structured_routing | 32 | 0 | 0 | 0 |
| none | full_to_retrieved | document_qa | 32 | 1 | 8 | 0 |
| none | full_to_retrieved | structured_routing | 32 | 2 | 4 | 0 |
| none | full_to_ktrf | document_qa | 32 | 0 | 0 | 0 |
| none | full_to_ktrf | structured_routing | 32 | 0 | 8 | 0 |
| none | retrieved_to_ktrf | document_qa | 32 | 8 | 1 | 0 |
| none | retrieved_to_ktrf | structured_routing | 32 | 2 | 8 | 0 |
| full | none_to_full | document_qa | 32 | 9 | 3 | 0 |
| full | none_to_full | structured_routing | 32 | 3 | 0 | 0 |
| full | none_to_retrieved | document_qa | 32 | 10 | 4 | 0 |
| full | none_to_retrieved | structured_routing | 32 | 11 | 1 | 0 |
| full | none_to_ktrf | document_qa | 32 | 22 | 0 | 0 |
| full | none_to_ktrf | structured_routing | 32 | 0 | 0 | 0 |
| full | full_to_retrieved | document_qa | 32 | 3 | 3 | 0 |
| full | full_to_retrieved | structured_routing | 32 | 8 | 1 | 0 |
| full | full_to_ktrf | document_qa | 32 | 16 | 0 | 0 |
| full | full_to_ktrf | structured_routing | 32 | 0 | 3 | 0 |
| full | retrieved_to_ktrf | document_qa | 32 | 16 | 0 | 0 |
| full | retrieved_to_ktrf | structured_routing | 32 | 1 | 11 | 0 |
| retrieved | none_to_full | document_qa | 32 | 8 | 1 | 0 |
| retrieved | none_to_full | structured_routing | 32 | 1 | 0 | 0 |
| retrieved | none_to_retrieved | document_qa | 32 | 10 | 3 | 0 |
| retrieved | none_to_retrieved | structured_routing | 32 | 5 | 1 | 0 |
| retrieved | none_to_ktrf | document_qa | 32 | 15 | 0 | 0 |
| retrieved | none_to_ktrf | structured_routing | 32 | 0 | 0 | 0 |
| retrieved | full_to_retrieved | document_qa | 32 | 3 | 3 | 0 |
| retrieved | full_to_retrieved | structured_routing | 32 | 4 | 1 | 0 |
| retrieved | full_to_ktrf | document_qa | 32 | 8 | 0 | 0 |
| retrieved | full_to_ktrf | structured_routing | 32 | 0 | 1 | 0 |
| retrieved | retrieved_to_ktrf | document_qa | 32 | 9 | 1 | 0 |
| retrieved | retrieved_to_ktrf | structured_routing | 32 | 1 | 5 | 0 |

## Source changes at fixed knowledge

Helpful means the current condition succeeds where baseline fails; harmful means the reverse. Missing pairs are incomplete; malformed responses remain failures.

| Fixed mode | Change | Task | Comparable | Helpful | Harmful | Incomplete |
|---|---|---|---:|---:|---:|---:|
| none | none_to_full | document_qa | 32 | 2 | 9 | 0 |
| none | none_to_full | structured_routing | 32 | 8 | 3 | 0 |
| none | none_to_retrieved | document_qa | 32 | 0 | 9 | 0 |
| none | none_to_retrieved | structured_routing | 32 | 8 | 1 | 0 |
| none | full_to_retrieved | document_qa | 32 | 1 | 3 | 0 |
| none | full_to_retrieved | structured_routing | 32 | 2 | 0 | 0 |
| full | none_to_full | document_qa | 32 | 0 | 1 | 0 |
| full | none_to_full | structured_routing | 32 | 0 | 0 | 0 |
| full | none_to_retrieved | document_qa | 32 | 0 | 2 | 0 |
| full | none_to_retrieved | structured_routing | 32 | 0 | 0 | 0 |
| full | full_to_retrieved | document_qa | 32 | 0 | 1 | 0 |
| full | full_to_retrieved | structured_routing | 32 | 0 | 0 | 0 |
| retrieved | none_to_full | document_qa | 32 | 7 | 1 | 0 |
| retrieved | none_to_full | structured_routing | 32 | 9 | 0 | 0 |
| retrieved | none_to_retrieved | document_qa | 32 | 6 | 1 | 0 |
| retrieved | none_to_retrieved | structured_routing | 32 | 5 | 0 | 0 |
| retrieved | full_to_retrieved | document_qa | 32 | 1 | 2 | 0 |
| retrieved | full_to_retrieved | structured_routing | 32 | 0 | 4 | 0 |
| ktrf | none_to_full | document_qa | 32 | 15 | 0 | 0 |
| ktrf | none_to_full | structured_routing | 32 | 8 | 3 | 0 |
| ktrf | none_to_retrieved | document_qa | 32 | 6 | 0 | 0 |
| ktrf | none_to_retrieved | structured_routing | 32 | 8 | 1 | 0 |
| ktrf | full_to_retrieved | document_qa | 32 | 0 | 9 | 0 |
| ktrf | full_to_retrieved | structured_routing | 32 | 2 | 0 | 0 |

## Operational execution acceptance

KTRF applies its complete-response guard. Other modes check the schema and membership among IDs actually provided in evidence. Acceptance is not semantic correctness, and these validators are not interchangeable.

| Knowledge | Source | Accepted correct ID | Accepted wrong ID | Rejected correct ID | Rejected wrong ID | Accepted null |
|---|---|---:|---:|---:|---:|---:|
| none | none | 0 | 0 | 0 | 0 | 13 |
| none | full | 0 | 0 | 0 | 3 | 29 |
| none | retrieved | 0 | 0 | 0 | 1 | 31 |
| full | none | 0 | 0 | 0 | 0 | 32 |
| full | full | 0 | 0 | 0 | 0 | 32 |
| full | retrieved | 0 | 0 | 0 | 0 | 32 |
| retrieved | none | 2 | 6 | 0 | 0 | 24 |
| retrieved | full | 8 | 2 | 0 | 0 | 22 |
| retrieved | retrieved | 4 | 2 | 0 | 0 | 26 |
| ktrf | none | 0 | 0 | 0 | 0 | 14 |
| ktrf | full | 0 | 0 | 0 | 3 | 29 |
| ktrf | retrieved | 0 | 0 | 0 | 1 | 31 |

## Cost

Latency includes failed attempts. Usage counts only reported observations.

| Knowledge | Source | Task | Latency observations | Total ms | p95 ms | Prompt tokens | Completion tokens | Usage observations |
|---|---|---|---:|---:|---:|---:|---:|---:|
| none | none | document_qa | 32 | 18210.842 | 590.459 | 6088 | 352 | 32 |
| none | none | structured_routing | 32 | 66057.782 | 2761.702 | 7080 | 1386 | 32 |
| none | full | document_qa | 32 | 20025.220 | 1215.582 | 12620 | 390 | 32 |
| none | full | structured_routing | 32 | 38984.353 | 1585.667 | 13612 | 802 | 32 |
| none | retrieved | document_qa | 32 | 16991.140 | 1139.944 | 8467 | 330 | 32 |
| none | retrieved | structured_routing | 32 | 38013.941 | 1258.859 | 9459 | 781 | 32 |
| full | none | document_qa | 32 | 18065.503 | 598.079 | 16736 | 347 | 32 |
| full | none | structured_routing | 32 | 37726.124 | 1254.68 | 17728 | 776 | 32 |
| full | full | document_qa | 32 | 22349.213 | 1234.071 | 23268 | 414 | 32 |
| full | full | structured_routing | 32 | 38670.943 | 1280.223 | 24260 | 794 | 32 |
| full | retrieved | document_qa | 32 | 26055.171 | 1197.042 | 19115 | 495 | 32 |
| full | retrieved | structured_routing | 32 | 37749.503 | 1256.747 | 20107 | 776 | 32 |
| retrieved | none | document_qa | 32 | 31285.307 | 1493.267 | 9966 | 634 | 32 |
| retrieved | none | structured_routing | 32 | 45447.231 | 2145.295 | 10958 | 940 | 32 |
| retrieved | full | document_qa | 32 | 31093.886 | 2364.939 | 16913 | 632 | 32 |
| retrieved | full | structured_routing | 32 | 47094.403 | 2128.904 | 17905 | 974 | 32 |
| retrieved | retrieved | document_qa | 32 | 27072.985 | 1376.591 | 12815 | 545 | 32 |
| retrieved | retrieved | structured_routing | 32 | 43367.334 | 2123.718 | 13807 | 896 | 32 |
| ktrf | none | document_qa | 32 | 10793.584 | 351.075 | 24240 | 192 | 32 |
| ktrf | none | structured_routing | 32 | 64597.266 | 2769.722 | 7080 | 1352 | 32 |
| ktrf | full | document_qa | 32 | 28741.713 | 1542.872 | 31147 | 530 | 32 |
| ktrf | full | structured_routing | 32 | 38956.848 | 1585.894 | 13612 | 802 | 32 |
| ktrf | retrieved | document_qa | 32 | 18383.120 | 1348.168 | 26994 | 344 | 32 |
| ktrf | retrieved | structured_routing | 32 | 38251.536 | 1271.976 | 9459 | 781 | 32 |

Per-stratum results and helpful/harmful case IDs are available in `summary.json`.

## Reproducibility and limits

Code revision: `604666e41c3133ec3032bfd23f69fa4c1bc5d6c9`. Request SHA-256: `33cdb7b94492e9cc5d24caef4a29c12cce12a94f2633ebb2e5b479cda241b9da`. Manifest seal: `b196ed8ee220badb0bd5443c3aa69234a7c4c273729c8c253cafa391820d1ab4`.

Decoding: `{"chat_template_kwargs": {"enable_thinking": false}, "max_tokens": 128, "seed": 0, "temperature": 0}`.

- AI-authored synthetic full documents and annotations; not human gold or deployment risk estimates.
- No-context conditions are information floors for private definitions and opaque IDs, not fair knowledge-parity baselines.
- World gold stays fixed when context is removed; missing evidence can make a question unanswerable.
- QA uses exact source definitions and does not credit paraphrases.
- KTRF adds production policy and execution authorization; these are full-system comparisons, not one-component effects.
- Lexical paragraph retrieval is a deterministic control, not a trained RAG retrieval benchmark.
- Full documents are never silently truncated; model-token capacity must be checked before inference.
- Source retrieval only uses the target; knowledge retrieval uses the target and visible source, never hidden source or labels.
- Model-family comparisons do not isolate parameter count. Preparation and retrieval costs are excluded from model-call latency.
- These complete source and knowledge documents are authored originals, not reconstructed news articles. Their AI-authored gold is not independent human gold or evidence of deployment risk.
- No pooled factorial success score is a primary result. Each source mode, knowledge mode and task is reported separately.
- All twelve conditions are newly inferred on identical documents and gold for this model. Prior production C responses are not used as controls.
- The none/none condition sees only the question and target expression. Recovering an opaque glossary ID without evidence is not a fair test of general knowledge; report QA and ID visibility alongside execution.
- KTRF includes its retrieval, context packaging, policy and guard. Compared with full or retrieved knowledge, this measures a system intervention, not an isolated resolver effect.
- KTRF's guard and baseline supplied-ID membership validation differ. Their operational acceptance is separate from common semantic accuracy; malformed/missing responses never earn null credit.
- Full means the entire frozen document; search uses only its retrieved chunks and neighbors. Evidence presence/recall is a property of provided inputs, not a model score.
- The target and relevant source document are known in this track. Source chunk retrieval is not an evaluation of corpus-wide document discovery.
- QA exact-definition matching can mark synonymous free wording incorrect; the fixed response contract is common across conditions.
- Latency uses math.fsum across recorded attempts, including failures. Missing attempts receive no imputed latency. Shared-host and serving differences affect latency.
- COMPLETE measures response coverage, including malformed outputs, rather than task quality. No confidence or risk-control guarantee follows from this authored sample.
