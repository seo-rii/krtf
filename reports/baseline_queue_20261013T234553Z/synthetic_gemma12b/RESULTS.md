# Plain glossary retrieval B versus KTRF production C

B status: **COMPLETE**; C reference status: **COMPLETE**. Model: `ktrf-production-gemma4-12b-bf16`. 437 target passages; 874 planned B calls.

Gold: `AI_SYNTHETIC`; human verified: `false`. B request SHA-256: `2aed5a236b2da934a094e737179199059fea02533d43479a3c39285b522c12f4`.

Received 874; missing 0; malformed 1; API/transport errors 0.

Primary success is a schema-valid exact semantic match **before** either arm's execution validator. The same frozen documents, gold, requested model and decoding were verified. Prompts, evidence selection and policies differ, so this measures the complete system package. QA and execution remain separate calls.

## Semantic outcomes

| Task | Arm | Semantic match / planned | Wrong non-null | Valid null | Malformed | Missing |
|---|---|---:|---:|---:|---:|---:|
| document_qa | B | 406/437 | 17 | 102 | 0 | 0 |
| document_qa | C | 402/437 | 14 | 112 | 0 | 0 |
| structured_routing | B | 424/437 | 7 | 99 | 1 | 0 |
| structured_routing | C | 335/437 | 2 | 199 | 0 | 0 |

## Paired changes B → C

Helpful means C succeeds where B fails; harmful means B succeeds where C fails. Missing pairs are incomplete; malformed outputs remain failures.

| Task | Comparable | Helpful for C | Harmful for C | Incomplete |
|---|---:|---:|---:|---:|
| document_qa | 437 | 18 | 22 | 0 |
| structured_routing | 437 | 7 | 96 | 0 |

| Stratum | Task | Helpful for C | Harmful for C | Incomplete |
|---|---|---:|---:|---:|
| ambiguous | document_qa | 2 | 0 | 0 |
| ambiguous | structured_routing | 2 | 0 | 0 |
| compound_nonmention | document_qa | 1 | 1 | 0 |
| compound_nonmention | structured_routing | 1 | 1 | 0 |
| contextual_collision | document_qa | 10 | 3 | 0 |
| contextual_collision | structured_routing | 0 | 71 | 0 |
| derived_role | document_qa | 3 | 0 | 0 |
| derived_role | structured_routing | 3 | 0 | 0 |
| exact | document_qa | 0 | 0 | 0 |
| exact | structured_routing | 0 | 0 | 0 |
| glossary_swap | document_qa | 0 | 0 | 0 |
| glossary_swap | structured_routing | 0 | 0 | 0 |
| multi_entity | document_qa | 0 | 0 | 0 |
| multi_entity | structured_routing | 0 | 0 | 0 |
| nil | document_qa | 0 | 2 | 0 |
| nil | structured_routing | 0 | 0 | 0 |
| particle | document_qa | 0 | 0 | 0 |
| particle | structured_routing | 0 | 0 | 0 |
| project_override | document_qa | 0 | 0 | 0 |
| project_override | structured_routing | 0 | 0 | 0 |
| session_override | document_qa | 0 | 0 | 0 |
| session_override | structured_routing | 0 | 0 | 0 |
| typo | document_qa | 2 | 10 | 0 |
| typo | structured_routing | 0 | 19 | 0 |
| unicode_spacing | document_qa | 0 | 6 | 0 |
| unicode_spacing | structured_routing | 1 | 5 | 0 |
| untrusted_override | document_qa | 0 | 0 | 0 |
| untrusted_override | structured_routing | 0 | 0 | 0 |

## Operational execution decisions

B validates the schema and membership in its supplied glossary IDs. C applies its original production guard. B is never passed through C's guard. Acceptance alone does not imply correctness.

| Arm | Accepted correct ID | Accepted wrong ID | Rejected correct ID | Rejected wrong ID | Accepted null |
|---|---:|---:|---:|---:|---:|---:|
| B | 330 | 7 | 0 | 0 | 99 |
| C | 236 | 1 | 0 | 1 | 199 |

## Retrieval and cost

| Task | Arm | Gold retrieved / positive targets | Median candidates | p95 ms | Prompt tokens | Completion tokens |
|---|---|---:|---:|---:|---:|---:|
| document_qa | B | 337/337 | 3.0 | 1459.694 | 342969 | 9133 |
| document_qa | C | 318/337 | 1.0 | 1653.941 | 307765 | 10725 |
| structured_routing | B | 337/337 | 3.0 | 2455.579 | 359575 | 19656 |
| structured_routing | C | 236/337 | 1.0 | 3293.341 | 201427 | 21963 |

## Reproduction and limitations

B manifest seal: `54d8641749381e81647ab01fad2b2b0b1a1bcb43b518e7fb998d60f1ccfacd81`. C manifest seal: `7e8e4d3452a44b78bea951bf6a7e1565325e79f00417d42cc5bb37bef89f4d3f`.

Both arms' sealed artifacts and frozen grading were verified. The matching C source manifest, case set, per-request hash, documents, gold, model and decoding were checked before comparison.

Artifacts: [summary](summary.json), [manifest](run_manifest.json), [requests](requests.jsonl), [responses](responses.jsonl), [grades](graded.json).

- Post-hoc diagnostic comparison on previously inspected KTRF outputs; not a new sealed risk test.
- Gold and source documents are unchanged; reference model responses do not select or rank baseline cards.
- This compares complete systems, including retrieval, prompts and execution policy; it does not isolate one component.
- The baseline uses deterministic character/bigram retrieval, not a trained dense RAG system.
- Without-glossary LLM-only is omitted: exact private definitions and opaque IDs would make it an information floor.
- Baseline acceptance checks response schema and supplied ID membership only; it is not verified entity linking.
- QA exact-definition matching does not credit paraphrases.
- Synthetic and AI-annotated real cases are not independent human gold or deployment risk estimates.
- The allowance is 6000 estimated context tokens and 12 entries; actual model tokens are reported separately.
- Frozen request preparation costs, including glossary compilation and retrieval, are excluded from model-call latency.
- The primary semantic metric is schema-valid exact matching before validator decisions; malformed and missing outputs never earn null credit.
- B/C share documents, gold, model and decoding, but differ in retrieval, prompt/policy packaging and execution validation. This is a system-package comparison, not an isolated resolver or formatting effect.
- B uses only its supplied-ID membership validator; it is never evaluated through C's execution guard. Validator acceptance and semantic correctness are reported separately.
- C is a previously sealed run, not a concurrent randomized control; timing can differ because of host contention and runtime state.
- LLM-only A is not a new primary condition: dictionary-free models cannot fairly recover opaque glossary IDs. Historical A results do not isolate the value of KTRF.
- Candidate recall has arm-specific evidence scope: B supplied IDs versus C exact-target-bound cards; candidate-set size and cost must accompany it.
- Gold is AI authored; no independent human-gold or deployment-risk guarantee is claimed.
- Latency totals use math.fsum; failures retain recorded latency, and absent calls receive no imputed latency.
- COMPLETE describes response coverage, including malformed responses, not task quality.
