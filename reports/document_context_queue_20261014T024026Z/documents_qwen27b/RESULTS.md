# Knowledge and source document context experiment

Status: **COMPLETE**. Model: `ktrf-production-qwen3.5-27b-bf16`. 32 complete authored documents × 12 conditions × 2 tasks; 768 calls planned.

Gold: `AI_AUTHORED_SYNTHETIC`; human verified: `false`. Authored documents and AI gold do not establish deployment risk.

Received 768; missing 0; malformed 0; API/transport errors 0.

Knowledge modes: no knowledge, the full knowledge document, retrieved knowledge passages, and KTRF. Source modes: no surrounding source, the full source document, and retrieved source passages with neighbors. Both axes vary independently; the no/no condition contains only the question and target expression. Every condition uses new inference; no historical C outputs are reused.

The primary metric is a schema-valid exact semantic match **before** each arm's validator. QA and ID routing are reported separately. There is no pooled primary score.

## Semantic outcomes

| Knowledge | Source | Task | Match / planned | Positive null | Correct null | Wrong non-null | Malformed | Missing |
|---|---|---|---:|---:|---:|---:|---:|---:|
| none | none | document_qa | 16/32 | 16 | 16 | 0 | 0 | 0 |
| none | none | structured_routing | 16/32 | 16 | 16 | 0 | 0 | 0 |
| none | full | document_qa | 13/32 | 16 | 13 | 3 | 0 | 0 |
| none | full | structured_routing | 16/32 | 16 | 16 | 0 | 0 | 0 |
| none | retrieved | document_qa | 11/32 | 15 | 10 | 6 | 0 | 0 |
| none | retrieved | structured_routing | 16/32 | 16 | 16 | 0 | 0 | 0 |
| full | none | document_qa | 16/32 | 16 | 16 | 0 | 0 | 0 |
| full | none | structured_routing | 16/32 | 16 | 16 | 0 | 0 | 0 |
| full | full | document_qa | 16/32 | 13 | 16 | 3 | 0 | 0 |
| full | full | structured_routing | 18/32 | 14 | 16 | 0 | 0 | 0 |
| full | retrieved | document_qa | 15/32 | 15 | 15 | 2 | 0 | 0 |
| full | retrieved | structured_routing | 17/32 | 15 | 16 | 0 | 0 | 0 |
| retrieved | none | document_qa | 13/32 | 12 | 13 | 7 | 0 | 0 |
| retrieved | none | structured_routing | 16/32 | 16 | 16 | 0 | 0 | 0 |
| retrieved | full | document_qa | 13/32 | 4 | 13 | 15 | 0 | 0 |
| retrieved | full | structured_routing | 27/32 | 5 | 16 | 0 | 0 | 0 |
| retrieved | retrieved | document_qa | 13/32 | 5 | 13 | 14 | 0 | 0 |
| retrieved | retrieved | structured_routing | 22/32 | 8 | 15 | 2 | 0 | 0 |
| ktrf | none | document_qa | 16/32 | 16 | 16 | 0 | 0 | 0 |
| ktrf | none | structured_routing | 16/32 | 16 | 16 | 0 | 0 | 0 |
| ktrf | full | document_qa | 28/32 | 0 | 12 | 4 | 0 | 0 |
| ktrf | full | structured_routing | 16/32 | 16 | 16 | 0 | 0 | 0 |
| ktrf | retrieved | document_qa | 22/32 | 8 | 14 | 2 | 0 | 0 |
| ktrf | retrieved | structured_routing | 16/32 | 16 | 16 | 0 | 0 | 0 |

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
| none | none_to_full | structured_routing | 32 | 0 | 0 | 0 |
| none | none_to_retrieved | document_qa | 32 | 0 | 3 | 0 |
| none | none_to_retrieved | structured_routing | 32 | 0 | 0 | 0 |
| none | none_to_ktrf | document_qa | 32 | 0 | 0 | 0 |
| none | none_to_ktrf | structured_routing | 32 | 0 | 0 | 0 |
| none | full_to_retrieved | document_qa | 32 | 0 | 3 | 0 |
| none | full_to_retrieved | structured_routing | 32 | 0 | 0 | 0 |
| none | full_to_ktrf | document_qa | 32 | 0 | 0 | 0 |
| none | full_to_ktrf | structured_routing | 32 | 0 | 0 | 0 |
| none | retrieved_to_ktrf | document_qa | 32 | 3 | 0 | 0 |
| none | retrieved_to_ktrf | structured_routing | 32 | 0 | 0 | 0 |
| full | none_to_full | document_qa | 32 | 3 | 0 | 0 |
| full | none_to_full | structured_routing | 32 | 2 | 0 | 0 |
| full | none_to_retrieved | document_qa | 32 | 2 | 2 | 0 |
| full | none_to_retrieved | structured_routing | 32 | 11 | 0 | 0 |
| full | none_to_ktrf | document_qa | 32 | 17 | 2 | 0 |
| full | none_to_ktrf | structured_routing | 32 | 0 | 0 | 0 |
| full | full_to_retrieved | document_qa | 32 | 0 | 3 | 0 |
| full | full_to_retrieved | structured_routing | 32 | 10 | 1 | 0 |
| full | full_to_ktrf | document_qa | 32 | 16 | 4 | 0 |
| full | full_to_ktrf | structured_routing | 32 | 0 | 2 | 0 |
| full | retrieved_to_ktrf | document_qa | 32 | 18 | 3 | 0 |
| full | retrieved_to_ktrf | structured_routing | 32 | 0 | 11 | 0 |
| retrieved | none_to_full | document_qa | 32 | 5 | 1 | 0 |
| retrieved | none_to_full | structured_routing | 32 | 1 | 0 | 0 |
| retrieved | none_to_retrieved | document_qa | 32 | 6 | 4 | 0 |
| retrieved | none_to_retrieved | structured_routing | 32 | 7 | 1 | 0 |
| retrieved | none_to_ktrf | document_qa | 32 | 11 | 0 | 0 |
| retrieved | none_to_ktrf | structured_routing | 32 | 0 | 0 | 0 |
| retrieved | full_to_retrieved | document_qa | 32 | 1 | 3 | 0 |
| retrieved | full_to_retrieved | structured_routing | 32 | 6 | 1 | 0 |
| retrieved | full_to_ktrf | document_qa | 32 | 8 | 1 | 0 |
| retrieved | full_to_ktrf | structured_routing | 32 | 0 | 1 | 0 |
| retrieved | retrieved_to_ktrf | document_qa | 32 | 11 | 2 | 0 |
| retrieved | retrieved_to_ktrf | structured_routing | 32 | 1 | 7 | 0 |

## Source changes at fixed knowledge

Helpful means the current condition succeeds where baseline fails; harmful means the reverse. Missing pairs are incomplete; malformed responses remain failures.

| Fixed mode | Change | Task | Comparable | Helpful | Harmful | Incomplete |
|---|---|---|---:|---:|---:|---:|
| none | none_to_full | document_qa | 32 | 0 | 3 | 0 |
| none | none_to_full | structured_routing | 32 | 0 | 0 | 0 |
| none | none_to_retrieved | document_qa | 32 | 1 | 6 | 0 |
| none | none_to_retrieved | structured_routing | 32 | 0 | 0 | 0 |
| none | full_to_retrieved | document_qa | 32 | 1 | 3 | 0 |
| none | full_to_retrieved | structured_routing | 32 | 0 | 0 | 0 |
| full | none_to_full | document_qa | 32 | 0 | 0 | 0 |
| full | none_to_full | structured_routing | 32 | 2 | 0 | 0 |
| full | none_to_retrieved | document_qa | 32 | 0 | 1 | 0 |
| full | none_to_retrieved | structured_routing | 32 | 1 | 0 | 0 |
| full | full_to_retrieved | document_qa | 32 | 0 | 1 | 0 |
| full | full_to_retrieved | structured_routing | 32 | 1 | 2 | 0 |
| retrieved | none_to_full | document_qa | 32 | 3 | 3 | 0 |
| retrieved | none_to_full | structured_routing | 32 | 11 | 0 | 0 |
| retrieved | none_to_retrieved | document_qa | 32 | 3 | 3 | 0 |
| retrieved | none_to_retrieved | structured_routing | 32 | 7 | 1 | 0 |
| retrieved | full_to_retrieved | document_qa | 32 | 1 | 1 | 0 |
| retrieved | full_to_retrieved | structured_routing | 32 | 0 | 5 | 0 |
| ktrf | none_to_full | document_qa | 32 | 16 | 4 | 0 |
| ktrf | none_to_full | structured_routing | 32 | 0 | 0 | 0 |
| ktrf | none_to_retrieved | document_qa | 32 | 8 | 2 | 0 |
| ktrf | none_to_retrieved | structured_routing | 32 | 0 | 0 | 0 |
| ktrf | full_to_retrieved | document_qa | 32 | 2 | 8 | 0 |
| ktrf | full_to_retrieved | structured_routing | 32 | 0 | 0 | 0 |

## Operational execution acceptance

KTRF applies its complete-response guard. Other modes check the schema and membership among IDs actually provided in evidence. Acceptance is not semantic correctness, and these validators are not interchangeable.

| Knowledge | Source | Accepted correct ID | Accepted wrong ID | Rejected correct ID | Rejected wrong ID | Accepted null |
|---|---|---:|---:|---:|---:|---:|
| none | none | 0 | 0 | 0 | 0 | 32 |
| none | full | 0 | 0 | 0 | 0 | 32 |
| none | retrieved | 0 | 0 | 0 | 0 | 32 |
| full | none | 0 | 0 | 0 | 0 | 32 |
| full | full | 2 | 0 | 0 | 0 | 30 |
| full | retrieved | 1 | 0 | 0 | 0 | 31 |
| retrieved | none | 0 | 0 | 0 | 0 | 32 |
| retrieved | full | 11 | 0 | 0 | 0 | 21 |
| retrieved | retrieved | 7 | 2 | 0 | 0 | 23 |
| ktrf | none | 0 | 0 | 0 | 0 | 32 |
| ktrf | full | 0 | 0 | 0 | 0 | 32 |
| ktrf | retrieved | 0 | 0 | 0 | 0 | 32 |

## Cost

Latency includes failed attempts. Usage counts only reported observations.

| Knowledge | Source | Task | Latency observations | Total ms | p95 ms | Prompt tokens | Completion tokens | Usage observations |
|---|---|---|---:|---:|---:|---:|---:|---:|
| none | none | document_qa | 32 | 20775.319 | 729.446 | 5599 | 192 | 32 |
| none | none | structured_routing | 32 | 54213.735 | 1885.774 | 6495 | 611 | 32 |
| none | full | document_qa | 32 | 24899.253 | 1477.591 | 11498 | 223 | 32 |
| none | full | structured_routing | 32 | 56599.200 | 2026.926 | 12394 | 611 | 32 |
| none | retrieved | document_qa | 32 | 26310.444 | 1665.428 | 7776 | 263 | 32 |
| none | retrieved | structured_routing | 32 | 54705.945 | 1886.557 | 8672 | 611 | 32 |
| full | none | document_qa | 32 | 24665.515 | 935.273 | 15119 | 192 | 32 |
| full | none | structured_routing | 32 | 57743.196 | 2036.006 | 16015 | 611 | 32 |
| full | full | document_qa | 32 | 37440.482 | 2975.235 | 21018 | 326 | 32 |
| full | full | structured_routing | 32 | 64464.000 | 2840.38 | 21914 | 649 | 32 |
| full | retrieved | document_qa | 32 | 31551.910 | 2097.478 | 17296 | 268 | 32 |
| full | retrieved | structured_routing | 32 | 60054.320 | 2031.702 | 18192 | 628 | 32 |
| retrieved | none | document_qa | 32 | 36998.106 | 3501.159 | 9078 | 381 | 32 |
| retrieved | none | structured_routing | 32 | 55465.762 | 1936.937 | 9974 | 611 | 32 |
| retrieved | full | document_qa | 32 | 64373.405 | 5634.849 | 15364 | 700 | 32 |
| retrieved | full | structured_routing | 32 | 72373.493 | 3248.39 | 16260 | 797 | 32 |
| retrieved | retrieved | document_qa | 32 | 61943.084 | 4872.308 | 11680 | 692 | 32 |
| retrieved | retrieved | structured_routing | 32 | 68196.792 | 3106.723 | 12576 | 762 | 32 |
| ktrf | none | document_qa | 32 | 27943.749 | 992.904 | 22501 | 192 | 32 |
| ktrf | none | structured_routing | 32 | 53613.640 | 1868.934 | 6495 | 611 | 32 |
| ktrf | full | document_qa | 32 | 54825.942 | 2485.945 | 28736 | 456 | 32 |
| ktrf | full | structured_routing | 32 | 56659.139 | 1948.671 | 12394 | 611 | 32 |
| ktrf | retrieved | document_qa | 32 | 39449.405 | 2002.225 | 25014 | 321 | 32 |
| ktrf | retrieved | structured_routing | 32 | 54823.102 | 1937.194 | 8672 | 611 | 32 |

Per-stratum results and helpful/harmful case IDs are available in `summary.json`.

## Reproducibility and limits

Code revision: `604666e41c3133ec3032bfd23f69fa4c1bc5d6c9`. Request SHA-256: `33cdb7b94492e9cc5d24caef4a29c12cce12a94f2633ebb2e5b479cda241b9da`. Manifest seal: `a1cf200af0c7cf85fd8bf56b695ffb1559564c7016fe3a2899a4ab2d9eb133f6`.

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
