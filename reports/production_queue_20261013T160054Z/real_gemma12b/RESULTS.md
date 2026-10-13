# Production QA and execution evaluation

Run status: **COMPLETE**. 60 target passages and 120 planned separate QA/execution calls.

Gold origin: `AI_AUTHORED_NOT_HUMAN`; human verified: `false`. No deployment-risk guarantee is claimed.

Model: `ktrf-production-gemma4-12b-bf16`. Code revision: `e1a72fb3ac10d8b12914949f8c0947dd506ab6f1`. Request SHA-256: `c87986f95013b25a4be3e197664fc35431aaacfcc1425564fc3f981e5a810515`.

Decoding: `{"chat_template_kwargs": {"enable_thinking": false}, "max_tokens": 128, "seed": 0, "temperature": 0}`. Context budget: `{"max_candidates_per_mention": 6, "max_entities": 12, "max_tokens": 6000}`.

The production path uses actual XML context and the prepared policy, respecting `should_inject`. QA and automation use separate calls and profiles. The 6000-token context allowance is explicitly larger than the 800-token default. QA-generated IDs do not enter execution.

Received 120; missing 0 (including 0 errors and 0 unattempted); malformed 0. COMPLETE describes coverage, not task quality.

## Task outcomes

| Task | Correct / planned | Semantic match | Valid null | Malformed | Missing |
|---|---:|---:|---:|---:|---:|
| document_qa | 56/60 | 56 | 20 | 0 | 0 |
| structured_routing | 57/60 | 57 | 21 | 0 | 0 |

Contextual contrast pairs: both correct **0/0**; complete 0; incomplete 0.

QA exact-definition success includes response-schema compliance. Routing semantic matches require guard approval to count as correct. Malformed and missing outputs cannot earn null credit.

## Strata

| Stratum | Task | Correct / planned | Malformed | Missing |
|---|---|---:|---:|---:|
| real_compositional | document_qa | 5/5 | 0 | 0 |
| real_compositional | structured_routing | 4/5 | 0 | 0 |
| real_link | document_qa | 36/36 | 0 | 0 |
| real_link | structured_routing | 36/36 | 0 | 0 |
| real_nil | document_qa | 14/18 | 0 | 0 |
| real_nil | structured_routing | 16/18 | 0 | 0 |
| real_non_mention | document_qa | 1/1 | 0 | 0 |
| real_non_mention | structured_routing | 1/1 | 0 | 0 |

## Execution boundary and QA schema

| Measure | Count |
|---|---:|
| Wrong routing ID accepted by guard | 2 |
| Wrong routing ID blocked | 1 |
| Semantically correct routing ID blocked | 0 |
| Policy-compliant null on blocked positive gold | 0 |
| Avoidable null on authorized positive gold | 0 |
| QA responses containing forbidden ID fields | 0 |
| QA responses with non-null forbidden IDs | 0 |

Routing semantic-oracle ceiling under the frozen guard: 60/60. This diagnoses authorization limits; it does not establish attainable model performance.

## Cost

| Task | Injected / planned | Latency observations | p50 ms | p95 ms | p99 ms | Prompt tokens | Completion tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| document_qa | 47/60 | 60 | 850.904 | 1049.977 | 1116.371 | 34757 | 888 |
| structured_routing | 42/60 | 60 | 1440.365 | 2385.282 | 2462.823 | 26324 | 2178 |

## Reproduction and limitations

All three artifact hashes, the canonical manifest seal, request/response identities, counts and frozen regrading were verified. No current corpus fixtures are loaded by this report.

Manifest seal: `d18c9b36ae0633351ee6b3b8c458da099790373d34503c5973944607bbabd296`.

Artifacts: [summary](summary.json), [manifest](run_manifest.json), [requests](requests.jsonl), [responses](responses.jsonl), [grades](graded.json).

- Real text, AI-authored gold; not independent human gold or a deployment risk bound.
- Declared lexical/NER stratified sentence sample; not a random deployment audit.
- Source article IDs are unavailable; sentence-level IDs do not establish article-level independence.
- One primary target per selected sentence; not exhaustive end-to-end mention recall.
- Local prior-data hash exclusion does not establish absence from model pretraining.
- Domestic administrative-unit territorial names follow the declared glossary convention; three primary labels required adjudication.
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
