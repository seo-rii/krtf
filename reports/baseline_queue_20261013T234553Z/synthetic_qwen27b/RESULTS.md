# Plain glossary retrieval B versus KTRF production C

B status: **COMPLETE**; C reference status: **COMPLETE**. Model: `ktrf-production-qwen3.5-27b-bf16`. 437 target passages; 874 planned B calls.

Gold: `AI_SYNTHETIC`; human verified: `false`. B request SHA-256: `2aed5a236b2da934a094e737179199059fea02533d43479a3c39285b522c12f4`.

Received 874; missing 0; malformed 5; API/transport errors 0.

Primary success is a schema-valid exact semantic match **before** either arm's execution validator. The same frozen documents, gold, requested model and decoding were verified. Prompts, evidence selection and policies differ, so this measures the complete system package. QA and execution remain separate calls.

## Semantic outcomes

| Task | Arm | Semantic match / planned | Wrong non-null | Valid null | Malformed | Missing |
|---|---|---:|---:|---:|---:|---:|
| document_qa | B | 411/437 | 11 | 103 | 1 | 0 |
| document_qa | C | 414/437 | 8 | 111 | 0 | 0 |
| structured_routing | B | 425/437 | 0 | 108 | 4 | 0 |
| structured_routing | C | 335/437 | 0 | 199 | 3 | 0 |

## Paired changes B → C

Helpful means C succeeds where B fails; harmful means B succeeds where C fails. Missing pairs are incomplete; malformed outputs remain failures.

| Task | Comparable | Helpful for C | Harmful for C | Incomplete |
|---|---:|---:|---:|---:|
| document_qa | 437 | 22 | 19 | 0 |
| structured_routing | 437 | 1 | 91 | 0 |

| Stratum | Task | Helpful for C | Harmful for C | Incomplete |
|---|---|---:|---:|---:|
| ambiguous | document_qa | 0 | 0 | 0 |
| ambiguous | structured_routing | 0 | 0 | 0 |
| compound_nonmention | document_qa | 0 | 1 | 0 |
| compound_nonmention | structured_routing | 0 | 0 | 0 |
| contextual_collision | document_qa | 8 | 0 | 0 |
| contextual_collision | structured_routing | 0 | 74 | 0 |
| derived_role | document_qa | 11 | 0 | 0 |
| derived_role | structured_routing | 0 | 0 | 0 |
| exact | document_qa | 0 | 0 | 0 |
| exact | structured_routing | 0 | 0 | 0 |
| glossary_swap | document_qa | 0 | 0 | 0 |
| glossary_swap | structured_routing | 0 | 0 | 0 |
| multi_entity | document_qa | 0 | 0 | 0 |
| multi_entity | structured_routing | 0 | 0 | 0 |
| nil | document_qa | 0 | 3 | 0 |
| nil | structured_routing | 0 | 0 | 0 |
| particle | document_qa | 0 | 0 | 0 |
| particle | structured_routing | 0 | 0 | 0 |
| project_override | document_qa | 0 | 0 | 0 |
| project_override | structured_routing | 0 | 0 | 0 |
| session_override | document_qa | 0 | 0 | 0 |
| session_override | structured_routing | 0 | 0 | 0 |
| typo | document_qa | 3 | 10 | 0 |
| typo | structured_routing | 0 | 14 | 0 |
| unicode_spacing | document_qa | 0 | 5 | 0 |
| unicode_spacing | structured_routing | 1 | 3 | 0 |
| untrusted_override | document_qa | 0 | 0 | 0 |
| untrusted_override | structured_routing | 0 | 0 | 0 |

## Operational execution decisions

B validates the schema and membership in its supplied glossary IDs. C applies its original production guard. B is never passed through C's guard. Acceptance alone does not imply correctness.

| Arm | Accepted correct ID | Accepted wrong ID | Rejected correct ID | Rejected wrong ID | Accepted null |
|---|---:|---:|---:|---:|---:|---:|
| B | 325 | 0 | 0 | 0 | 108 |
| C | 235 | 0 | 0 | 0 | 199 |

## Retrieval and cost

| Task | Arm | Gold retrieved / positive targets | Median candidates | p95 ms | Prompt tokens | Completion tokens |
|---|---|---:|---:|---:|---:|---:|
| document_qa | B | 337/337 | 3.0 | 2631.305 | 324237 | 8136 |
| document_qa | C | 318/337 | 1.0 | 2569.486 | 286575 | 7966 |
| structured_routing | B | 337/337 | 3.0 | 4291.81 | 339969 | 16593 |
| structured_routing | C | 236/337 | 1.0 | 3942.256 | 186159 | 14395 |

## Reproduction and limitations

B manifest seal: `5df1ce309f921de5b17086721692e27c23d31b50877cc428291563942e6f493a`. C manifest seal: `dbe97078322557752c96e642053c577c932607e0cb7e244e82a95429b515bfcb`.

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
