# Expanded synthetic grounding experiment

Run status: **COMPLETE**. 100 AI-authored families, 437 distinct documents, 874 task cases and 4370 planned calls. Gold is AI synthetic and has not been human verified.

Model: `ktrf-synthetic-gemma4-12b-bf16`. Experiment code revision: `566a90c61f8ecc7789283ee47c74ecec3e578739`. Request SHA-256: `b30cb382e46df3400da839e3584e7e624ad2ea336a012934880e2436e6adcca0`.

Decoding: `{"chat_template_kwargs": {"enable_thinking": false}, "max_tokens": 128, "seed": 0, "temperature": 0}`. The planned output cap is 128 tokens; finish reasons and actual usage below show whether this bound affected outputs.

Received 4370/4370; missing 0, malformed 0, transport/API errors 0. COMPLETE means response coverage, not successful or reliable task performance.

## Controlled 2×2 input comparison

The four cells keep candidate facts, questions, system policy and execution guard fixed. Surface bindings and policy-named fields are the declared factors.

| Condition | Success / planned | Family macro (observed) | Answerable success / observed | Over-abstention | Safe abstention | Malformed | Missing |
|---|---:|---:|---:|---:|---:|---:|---:|
| original | 217/874 | 25.43% | 17/674 | 653 | 200 | 0 | 0 |
| surface_only | 670/874 | 78.70% | 476/674 | 177 | 194 | 0 | 0 |
| schema_only | 224/874 | 26.32% | 24/674 | 646 | 200 | 0 | 0 |
| both | 668/874 | 78.55% | 476/674 | 178 | 192 | 0 | 0 |

Family macro averages observed task success within each family. Missing calls remain failures in the planned denominator and appear separately; family macro is descriptive over observed outputs. The sealed over-abstention count includes every valid null on positive semantic gold; the policy-aware routing breakdown below leaves this original grade unchanged.

## Full-pack information reference

This condition includes the full production context pack and may add information. It is separate from the isolated 2×2 comparison.

| Condition | Success / planned | Family macro (observed) | Answerable success / observed | Over-abstention | Safe abstention | Malformed | Missing |
|---|---:|---:|---:|---:|---:|---:|---:|
| full_pack | 650/874 | 76.40% | 472/674 | 194 | 178 | 0 | 0 |

## Task outcomes and execution guard

| Condition | QA success / observed | Routing success / observed | Observed / planned | Semantic routing matches | Wrong non-null IDs | Guard rejections | Wrong IDs accepted by guard |
|---|---:|---:|---:|---:|---:|---:|---:|
| original | 109/437 | 108/437 | 874/874 | 110 | 0 | 2 | 0 |
| surface_only | 336/437 | 334/437 | 874/874 | 348 | 2 | 16 | 0 |
| schema_only | 115/437 | 109/437 | 874/874 | 111 | 0 | 2 | 0 |
| both | 334/437 | 334/437 | 874/874 | 346 | 2 | 14 | 0 |
| full_pack | 322/437 | 328/437 | 874/874 | 332 | 8 | 11 | 1 |

A wrong ID is measured against authored semantic gold. A guard rejection can also reject a semantically correct ID that the resolver did not authorize. The accepted-wrong-ID column counts semantic errors that passed the guard; it is not a deployment risk estimate.

## Semantic oracle ceiling and policy-aware abstention

This diagnostic supplies the authored correct answer or ID for every frozen request. QA has no execution gate; routing still passes the original execution guard. It uses no model responses and does not revise semantic gold. It isolates the guard ceiling, not whether the prompt contains enough evidence for an LLM to find the answer.

| Task | Oracle successes / planned | Ceiling |
|---|---:|---:|
| document_qa | 437/437 | 100.00% |
| structured_routing | 336/437 | 76.89% |
| all tasks | 773/874 | 88.44% |

Planned family-macro ceiling: 89.47%. Per-condition ceilings over observed outputs are retained separately in `summary.json`, so missing cases do not change a comparison denominator silently.

Positive routing with an unauthorized correct ID cannot succeed under the sealed rubric. A valid null in that case complies with execution policy while remaining a semantic miss. Null on an authorized correct ID is avoidable abstention. Malformed or missing outputs enter neither null count.

| Condition | Positive routing planned | Gold ID blocked by guard | Policy-compliant null on blocked gold | Avoidable null on authorized gold | Observed family-macro ceiling |
|---|---:|---:|---:|---:|---:|
| original | 337 | 101 | 99 | 228 | 89.47% |
| surface_only | 337 | 101 | 86 | 1 | 89.47% |
| schema_only | 337 | 101 | 99 | 227 | 89.47% |
| both | 337 | 101 | 89 | 0 | 89.47% |
| full_pack | 337 | 101 | 97 | 0 | 89.47% |

## Text-blind candidate bias diagnostics

The 74 contextual-collision documents are examined once using original-condition candidate cards, in their presentation order. These fixed rules read neither document text nor model output. QA returns the selected candidate's definition; the raw semantic ID is scored separately from execution authorization. They are corpus baselines, not LLM scores.

`non_main_suffix` chooses the non-`.main` ID only with exactly one `.main` candidate and one other distinct candidate. Otherwise it returns null. `first_candidate` and `last_candidate` expose order shortcuts; repeated IDs use their first card. Support counts documents where the rule makes a non-null selection; accuracy denominators include unsupported cases.

| Rule | Support / documents | QA exact match / cases | Semantic ID match / cases | Guard-accepted semantic matches | Non-null guard rejections |
|---|---:|---:|---:|---:|---:|
| non_main_suffix | 0/74 | 0/74 | 0/74 | 0 | 0 |
| first_candidate | 74/74 | 37/74 | 37/74 | 0 | 74 |
| last_candidate | 74/74 | 37/74 | 37/74 | 0 | 74 |

Gold target positions in the original candidate order (1-based; `absent` means no candidate): `{"1": 37, "2": 37}`. Per-document candidate IDs, target positions, predictions and any v2 contrast-pair metadata are retained in summary.json. V1 authoring IDs leak semantic roles; v2 opaque IDs and paired contexts must be checked with these same diagnostics, without treating synthetic performance as a production risk estimate.

## Paired changes versus original

Pairs use the same case ID in each condition. Malformed responses count as failures; missing responses are excluded from pairs and shown explicitly.

| Condition | Pairs | Helpful flips | Harmful flips | Missing pairs |
|---|---:|---:|---:|---:|
| original | 874 | 0 | 0 | 0 |
| surface_only | 874 | 460 | 7 | 0 |
| schema_only | 874 | 11 | 4 | 0 |
| both | 874 | 460 | 9 | 0 |
| full_pack | 874 | 456 | 23 | 0 |

## Per-stratum success

Entries show success / observed. These include both QA and routing tasks for the same documents.

| Stratum | original | surface_only | schema_only | both | full_pack |
|---|---:|---:|---:|---:|---:|
| ambiguous | 50/50 | 50/50 | 50/50 | 50/50 | 50/50 |
| compound_nonmention | 32/32 | 31/32 | 32/32 | 31/32 | 30/32 |
| contextual_collision | 0/148 | 2/148 | 0/148 | 0/148 | 0/148 |
| derived_role | 74/74 | 69/74 | 74/74 | 67/74 | 55/74 |
| exact | 2/98 | 98/98 | 5/98 | 98/98 | 98/98 |
| glossary_swap | 4/116 | 116/116 | 4/116 | 116/116 | 115/116 |
| multi_entity | 2/90 | 89/90 | 3/90 | 88/90 | 90/90 |
| nil | 42/42 | 42/42 | 42/42 | 42/42 | 41/42 |
| particle | 0/44 | 44/44 | 1/44 | 42/44 | 43/44 |
| project_override | 2/40 | 39/40 | 2/40 | 40/40 | 40/40 |
| session_override | 2/32 | 31/32 | 3/32 | 32/32 | 32/32 |
| typo | 1/44 | 9/44 | 1/44 | 10/44 | 3/44 |
| unicode_spacing | 0/28 | 15/28 | 0/28 | 16/28 | 17/28 |
| untrusted_override | 6/36 | 35/36 | 7/36 | 36/36 | 36/36 |

## Recorded latency and token usage

Latency percentiles use linear interpolation over actual recorded attempts, including failed attempts. There is no imputed latency for missing calls. Shared-host contention can affect these measurements.

| Condition | Attempts | p50 ms | p95 ms | p99 ms | Actual prompt tokens | Actual completion tokens | Completion max | Length finishes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| original | 874 | 850.403 | 874.196 | 2,643.859 | 430432 | 15385 | 80 | 0 |
| surface_only | 874 | 2,276.120 | 3,022.109 | 3,172.791 | 440526 | 35174 | 89 | 0 |
| schema_only | 874 | 849.998 | 874.524 | 3,076.472 | 438980 | 15871 | 94 | 0 |
| both | 874 | 2,290.436 | 3,045.554 | 3,609.597 | 449074 | 35668 | 128 | 0 |
| full_pack | 874 | 2,285.915 | 3,026.805 | 3,167.162 | 793682 | 35271 | 83 | 0 |

Actual usage observation counts, totals and distributions are in `summary.json`; estimated input tokens are reported separately and do not replace API usage.

## Limits and artifact verification

- AI-authored synthetic documents and gold; not independent human gold or deployment traffic.
- Family clusters are correlated; family macro is descriptive, without a risk bound or risk certification.
- The semantic oracle ceiling assumes authored answers are known; it isolates the execution guard and is not an achievable LLM or information-availability guarantee.
- Text-blind candidate baselines are corpus bias diagnostics, not model results; selection rules are fixed without reading document text or model outputs.
- V1 authoring IDs such as .main and .rival can expose answer patterns; candidate order is also measured. These diagnostics do not alter sealed gold or grades.
- Policy-compliant null on guard-blocked positive routing remains a semantic miss in the original grade; it is separated from avoidable null on guard-authorized positives.
- full_pack is a separate information reference beyond the isolated four-condition 2x2.
- QA exact-match grading can reject correct paraphrases; no model-assisted repair or adjudication is performed.
- The output cap is recorded in decoding (planned 128 tokens); length finishes can constrain answers.
- Missing and malformed outputs are failures, never safe abstention; COMPLETE denotes transport coverage, not task success.
- Routing success requires semantic correctness and the original execution guard; guard acceptance alone is not semantic correctness.
- The execution guard is surface-based; explicit occurrence spans in prompts do not make it occurrence-aware.
- Latency includes recorded attempts, including failed attempts; shared-host contention can affect it, and absent outputs have no imputed latency.
- Advertised model identity is recorded; checkpoint weight revision is not established by these artifacts.

All three input artifact SHA-256 values and the canonical manifest seal were verified before this report was generated. This report reads only frozen requests, responses, graded diagnostics and manifest; it does not reload current fixtures.

Manifest seal: `2da5d62effb6ab37911f1eb5bc6a95e6f56e9668a2b88b8765557db289b5d662`.

Artifacts: [summary](summary.json), [sealed manifest](run_manifest.json), [requests](requests.jsonl), [responses](responses.jsonl), [graded diagnostics](graded.json).
