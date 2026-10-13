# Production QA and execution evaluation

Run status: **COMPLETE**. 437 target passages and 874 planned separate QA/execution calls.

Gold origin: `AI_SYNTHETIC`; human verified: `false`. No deployment-risk guarantee is claimed.

Model: `ktrf-production-qwen3.5-27b-bf16`. Code revision: `e1a72fb3ac10d8b12914949f8c0947dd506ab6f1`. Request SHA-256: `68dad08832023697d702bfb6405f2f3634ef1d67cb791784b869c1cd7783bed9`.

Decoding: `{"chat_template_kwargs": {"enable_thinking": false}, "max_tokens": 128, "seed": 0, "temperature": 0}`. Context budget: `{"max_candidates_per_mention": 6, "max_entities": 12, "max_tokens": 6000}`.

The production path uses actual XML context and the prepared policy, respecting `should_inject`. QA and automation use separate calls and profiles. The 6000-token context allowance is explicitly larger than the 800-token default. QA-generated IDs do not enter execution.

Received 874; missing 0 (including 0 errors and 0 unattempted); malformed 3. COMPLETE describes coverage, not task quality.

## Task outcomes

| Task | Correct / planned | Semantic match | Valid null | Malformed | Missing |
|---|---:|---:|---:|---:|---:|
| document_qa | 414/437 | 414 | 111 | 0 | 0 |
| structured_routing | 335/437 | 335 | 199 | 3 | 0 |

Contextual contrast pairs: both correct **37/37**; complete 37; incomplete 0.

QA exact-definition success includes response-schema compliance. Routing semantic matches require guard approval to count as correct. Malformed and missing outputs cannot earn null credit.

## Strata

| Stratum | Task | Correct / planned | Malformed | Missing |
|---|---|---:|---:|---:|
| ambiguous | document_qa | 25/25 | 0 | 0 |
| ambiguous | structured_routing | 25/25 | 0 | 0 |
| compound_nonmention | document_qa | 15/16 | 0 | 0 |
| compound_nonmention | structured_routing | 16/16 | 0 | 0 |
| contextual_collision | document_qa | 74/74 | 0 | 0 |
| contextual_collision | structured_routing | 0/74 | 0 | 0 |
| derived_role | document_qa | 37/37 | 0 | 0 |
| derived_role | structured_routing | 37/37 | 0 | 0 |
| exact | document_qa | 49/49 | 0 | 0 |
| exact | structured_routing | 49/49 | 0 | 0 |
| glossary_swap | document_qa | 58/58 | 0 | 0 |
| glossary_swap | structured_routing | 58/58 | 0 | 0 |
| multi_entity | document_qa | 45/45 | 0 | 0 |
| multi_entity | structured_routing | 45/45 | 0 | 0 |
| nil | document_qa | 18/21 | 0 | 0 |
| nil | structured_routing | 21/21 | 0 | 0 |
| particle | document_qa | 22/22 | 0 | 0 |
| particle | structured_routing | 22/22 | 0 | 0 |
| project_override | document_qa | 20/20 | 0 | 0 |
| project_override | structured_routing | 20/20 | 0 | 0 |
| session_override | document_qa | 16/16 | 0 | 0 |
| session_override | structured_routing | 16/16 | 0 | 0 |
| typo | document_qa | 8/22 | 0 | 0 |
| typo | structured_routing | 0/22 | 0 | 0 |
| unicode_spacing | document_qa | 9/14 | 0 | 0 |
| unicode_spacing | structured_routing | 8/14 | 3 | 0 |
| untrusted_override | document_qa | 18/18 | 0 | 0 |
| untrusted_override | structured_routing | 18/18 | 0 | 0 |

## Execution boundary and QA schema

| Measure | Count |
|---|---:|
| Wrong routing ID accepted by guard | 0 |
| Wrong routing ID blocked | 0 |
| Semantically correct routing ID blocked | 0 |
| Policy-compliant null on blocked positive gold | 99 |
| Avoidable null on authorized positive gold | 0 |
| QA responses containing forbidden ID fields | 0 |
| QA responses with non-null forbidden IDs | 0 |

Routing semantic-oracle ceiling under the frozen guard: 336/437. This diagnoses authorization limits; it does not establish attainable model performance.

## Cost

| Task | Injected / planned | Latency observations | p50 ms | p95 ms | p99 ms | Prompt tokens | Completion tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| document_qa | 399/437 | 437 | 1797.943 | 2569.486 | 2931.477 | 286575 | 7966 |
| structured_routing | 277/437 | 437 | 3154.176 | 3942.256 | 4296.014 | 186159 | 14395 |

## Reproduction and limitations

All three artifact hashes, the canonical manifest seal, request/response identities, counts and frozen regrading were verified. No current corpus fixtures are loaded by this report.

Manifest seal: `dbe97078322557752c96e642053c577c932607e0cb7e244e82a95429b515bfcb`.

Artifacts: [summary](summary.json), [manifest](run_manifest.json), [requests](requests.jsonl), [responses](responses.jsonl), [grades](graded.json).

- Previously evaluated AI synthetic cases are diagnostic controls, not unseen deployment risk data.
- QA exact-definition matching does not credit paraphrases.
- The explicit 6000-token context allowance is not the production default 800-token budget.
- Model-family comparisons do not isolate parameter-count effects.
- Gold origin and verification are copied from the sealed protocol; real documents do not imply human-verified entity-linking gold.
- This run does not establish deployment risk or an independent human-gold guarantee.
- QA explanations never authorize execution. QA IDs violate the response contract and are counted separately.
- Execution receives its own automation context; the complete response reaches the guard without ID projection or repair.
- Null on guard-blocked positive gold can obey the policy while remaining a semantic miss.
- Missing counts include transport/API failures and unattempted requests; malformed received responses are separate and never safe abstentions.
- COMPLETE means response coverage, including malformed responses, not reliable task performance.
- Latency includes recorded attempts, including failures; shared-host contention and serving configurations affect timing.
- Advertised model identities are recorded; the report alone does not establish checkpoint weight revision.
