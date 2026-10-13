# QA and execution policy separation experiment

Run status: **COMPLETE**. 437 AI synthetic documents, 874 task cases and 1748 planned calls. Gold has not been human verified.

Model: `ktrf-synthetic-gemma4-12b-bf16`. Code revision: `0f35b7e7bbdd28d247990602706ecb6f4b7190f3`. Request SHA-256: `6a7d4fea66a3f79ce737099e4519fbc30506b5e6a7c490361f71b8f6ee405bfa`.

Decoding: `{"chat_template_kwargs": {"enable_thinking": false}, "max_tokens": 128, "seed": 0, "temperature": 0}`. Received 1748; missing 0; malformed 0; transport/API errors 0.

The two conditions use the same surface-bound candidate facts and authored answers. `qa_context` permits QA to choose a definition from those candidates using document context. Execution IDs still require the frozen resolver guard. QA answer correctness and any incidental QA entity ID are measured separately. COMPLETE means response coverage, not reliable task performance.

## Primary contextual-collision outcomes

| Condition | QA correct / planned | Null | Malformed | Missing | Both contrast members correct / pairs | Incomplete pairs |
|---|---:|---:|---:|---:|---:|---:|
| strict | 2/74 | 72 | 0 | 0 | 0/37 | 0 |
| qa_context | 54/74 | 20 | 0 | 0 | 20/37 | 0 |

Both members must be correct to pass a contrast pair; selecting a fixed candidate cannot pass both. Incomplete responses remain failures in planned denominators.

## All tasks and routing guard

| Condition | QA correct / planned | Routing correct / planned | Correct routing ID blocked | Wrong routing ID accepted | Policy-compliant null on blocked gold | Avoidable null on authorized gold |
|---|---:|---:|---:|---:|---:|---:|
| strict | 337/437 | 334/437 | 13 | 0 | 87 | 1 |
| qa_context | 397/437 | 331/437 | 31 | 0 | 70 | 4 |

Semantic oracle ceiling with the execution guard: 773/874. Guard acceptance alone is not semantic correctness. A correct but unapproved ID stays blocked.

## Negative QA controls

A non-null answer on negative authored gold is an unsupported answer under this rubric. Rates use all planned negative cases; valid-response denominators are also retained in summary.json.

| Condition | Stratum | Non-null / planned | Valid null | Valid responses |
|---|---|---:|---:|---:|
| strict | ambiguous | 0/25 | 25 | 25 |
| strict | compound_nonmention | 1/16 | 15 | 16 |
| strict | derived_role | 4/37 | 33 | 37 |
| strict | multi_entity | 0/1 | 1 | 1 |
| strict | nil | 0/21 | 21 | 21 |
| qa_context | ambiguous | 0/25 | 25 | 25 |
| qa_context | compound_nonmention | 0/16 | 16 | 16 |
| qa_context | derived_role | 0/37 | 37 | 37 |
| qa_context | multi_entity | 0/1 | 1 | 1 |
| qa_context | nil | 1/21 | 20 | 21 |

## Incidental QA IDs

These IDs do not enter QA answer correctness and carry no execution authority. Well-typed IDs in malformed QA responses are still audited; the malformed response remains a task failure. The guard below is a diagnostic evaluation of the unchanged execution policy.

| Condition | Non-null IDs | Correct but blocked | Wrong and guard-accepted | Wrong and blocked | Correct answer with blocked ID |
|---|---:|---:|---:|---:|---:|
| strict | 252 | 11 | 1 | 5 | 12 |
| qa_context | 279 | 47 | 0 | 0 | 47 |

## Paired changes versus strict

| Task | Comparable | Helpful | Harmful | Incomplete |
|---|---:|---:|---:|---:|
| document_qa | 437 | 65 | 5 | 0 |
| structured_routing | 437 | 0 | 3 | 0 |

Per-stratum changes and both-members-correct pair changes are retained in summary.json.

## Latency and tokens

| Condition | Attempts | p50 ms | p95 ms | p99 ms | Prompt tokens | Completion tokens | Length finishes |
|---|---:|---:|---:|---:|---:|---:|---:|
| strict | 874 | 2,281.109 | 3,041.257 | 3,176.232 | 440526 | 35100 | 0 |
| qa_context | 874 | 2,681.525 | 3,094.217 | 3,205.950 | 634554 | 39975 | 0 |

## Limits and provenance

- AI synthetic documents and gold, correlated families, and one requested model; no deployment risk estimate or independent human-gold claim.
- The intervention permits contextual QA among the same supplied candidates; it does not test unrestricted general-knowledge answers.
- QA exact matching rejects correct paraphrases; no output repair or model-assisted adjudication is performed.
- An answer or incidental QA entity ID never authorizes execution. Routing retains the original execution guard and authored semantic gold.
- Null on guard-blocked positive routing is policy compliant and still a semantic miss; malformed and missing outputs are never safe abstention.
- Paired flips exclude missing outputs and count malformed outputs as failures. Planned denominators and incomplete pairs are reported separately.
- The oracle ceiling supplies authored answers and isolates the execution guard; it does not establish evidence sufficiency or attainable LLM quality.
- Latency includes actual attempts, including failures; shared-host contention can affect it. Missing calls have no imputed latency.
- Model advertisement is preserved; checkpoint weight revision is not established by these artifacts.
- This is a new within-run policy comparison; aggregate differences from earlier v1/v2 runs are not a causal policy effect.

All three artifact hashes, the manifest seal, response identities and counts were verified. The complete recorded model grade was recomputed from frozen requests and responses; current fixtures were not loaded. Source document/candidate hashes and the declared source protocol are retained in summary.json.

Manifest seal: `6a7124bcbb9c0c6b3218e1b6b32db165a87d89404228a4d27923bc6b0197cb0a`.

Artifacts: [summary](summary.json), [manifest](run_manifest.json), [requests](requests.jsonl), [responses](responses.jsonl), [grades](graded.json).
