# Plain glossary retrieval B versus KTRF production C

B status: **COMPLETE**; C reference status: **COMPLETE**. Model: `ktrf-production-qwen3.5-27b-bf16`. 60 target passages; 120 planned B calls.

Gold: `AI_AUTHORED_NOT_HUMAN`; human verified: `false`. B request SHA-256: `03209237c1f46b246afc488eb04e15167d30770f4465c93087fcc4f48492c39a`.

Received 120; missing 0; malformed 1; API/transport errors 0.

Primary success is a schema-valid exact semantic match **before** either arm's execution validator. The same frozen documents, gold, requested model and decoding were verified. Prompts, evidence selection and policies differ, so this measures the complete system package. QA and execution remain separate calls.

## Semantic outcomes

| Task | Arm | Semantic match / planned | Wrong non-null | Valid null | Malformed | Missing |
|---|---|---:|---:|---:|---:|---:|
| document_qa | B | 50/60 | 9 | 14 | 1 | 0 |
| document_qa | C | 49/60 | 11 | 13 | 0 | 0 |
| structured_routing | B | 58/60 | 2 | 22 | 0 | 0 |
| structured_routing | C | 58/60 | 2 | 22 | 0 | 0 |

## Paired changes B → C

Helpful means C succeeds where B fails; harmful means B succeeds where C fails. Missing pairs are incomplete; malformed outputs remain failures.

| Task | Comparable | Helpful for C | Harmful for C | Incomplete |
|---|---:|---:|---:|---:|
| document_qa | 60 | 3 | 4 | 0 |
| structured_routing | 60 | 0 | 0 | 0 |

| Stratum | Task | Helpful for C | Harmful for C | Incomplete |
|---|---|---:|---:|---:|
| real_compositional | document_qa | 3 | 0 | 0 |
| real_compositional | structured_routing | 0 | 0 | 0 |
| real_link | document_qa | 0 | 0 | 0 |
| real_link | structured_routing | 0 | 0 | 0 |
| real_nil | document_qa | 0 | 4 | 0 |
| real_nil | structured_routing | 0 | 0 | 0 |
| real_non_mention | document_qa | 0 | 0 | 0 |
| real_non_mention | structured_routing | 0 | 0 | 0 |

## Operational execution decisions

B validates the schema and membership in its supplied glossary IDs. C applies its original production guard. B is never passed through C's guard. Acceptance alone does not imply correctness.

| Arm | Accepted correct ID | Accepted wrong ID | Rejected correct ID | Rejected wrong ID | Accepted null |
|---|---:|---:|---:|---:|---:|---:|
| B | 36 | 2 | 0 | 0 | 22 |
| C | 36 | 2 | 0 | 0 | 22 |

## Retrieval and cost

| Task | Arm | Gold retrieved / positive targets | Median candidates | p95 ms | Prompt tokens | Completion tokens |
|---|---|---:|---:|---:|---:|---:|
| document_qa | B | 36/36 | 12.0 | 2054.594 | 75054 | 657 |
| document_qa | C | 36/36 | 1.0 | 1547.716 | 32259 | 659 |
| structured_routing | B | 36/36 | 12.0 | 2422.715 | 77214 | 1332 |
| structured_routing | C | 36/36 | 1.0 | 2339.897 | 24246 | 1332 |

## Paired B-model comparison

`ktrf-production-gemma4-12b-bf16` → `ktrf-production-qwen3.5-27b-bf16` on identical B requests and source references. This changes model family as well as size.

| Task | Helpful | Harmful | Incomplete |
|---|---:|---:|---:|
| document_qa | 0 | 8 | 0 |
| structured_routing | 2 | 0 | 0 |

## Reproduction and limitations

B manifest seal: `9cd06351ddb756aeefae5c48d470f56f8e077da5322d6923e353d4d8091a31a3`. C manifest seal: `f4efa4b83b697610adc7972a9ec8be39f8ff2021516cefcbd64b8571bfa0c2e8`.

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
