# Expanded synthetic grounding experiment

Run status: **COMPLETE**. 100 AI-authored families, 400 distinct documents, 800 task cases and 4000 planned calls. Gold is AI synthetic and has not been human verified.

Model: `ktrf-synthetic-gemma4-12b-bf16`. Code revision: `370b780e0830acccf9ea670a15c156bd78630997`. Request SHA-256: `37b8ed8537fb955ed40ac1dc64c9d52958441d662d7b671ac3d8ebe7008d57bf`.

Decoding: `{"chat_template_kwargs": {"enable_thinking": false}, "max_tokens": 128, "seed": 0, "temperature": 0}`. The planned output cap is 128 tokens; finish reasons and actual usage below show whether this bound affected outputs.

Received 4000/4000; missing 0, malformed 1, transport/API errors 0. COMPLETE means response coverage, not successful or reliable task performance.

## Controlled 2×2 input comparison

The four cells keep candidate facts, questions, system policy and execution guard fixed. Surface bindings and policy-named fields are the declared factors.

| Condition | Success / planned | Family macro (observed) | Answerable success / observed | Over-abstention | Safe abstention | Malformed | Missing |
|---|---:|---:|---:|---:|---:|---:|---:|
| original | 269/800 | 33.62% | 69/600 | 513 | 200 | 0 | 0 |
| surface_only | 646/800 | 80.75% | 455/600 | 104 | 191 | 0 | 0 |
| schema_only | 264/800 | 33.00% | 64/600 | 511 | 200 | 1 | 0 |
| both | 646/800 | 80.75% | 456/600 | 109 | 190 | 0 | 0 |

Family macro averages observed task success within each family. Missing calls remain failures in the planned denominator and appear separately; family macro is descriptive over observed outputs.

## Full-pack information reference

This condition includes the full production context pack and may add information. It is separate from the isolated 2×2 comparison.

| Condition | Success / planned | Family macro (observed) | Answerable success / observed | Over-abstention | Safe abstention | Malformed | Missing |
|---|---:|---:|---:|---:|---:|---:|---:|
| full_pack | 624/800 | 78.00% | 448/600 | 120 | 176 | 0 | 0 |

## Task outcomes and execution guard

| Condition | QA success / observed | Routing success / observed | Observed / planned | Semantic routing matches | Wrong non-null IDs | Guard rejections | Wrong IDs accepted by guard |
|---|---:|---:|---:|---:|---:|---:|---:|
| original | 131/400 | 138/400 | 800/800 | 142 | 0 | 4 | 0 |
| surface_only | 312/400 | 334/400 | 800/800 | 347 | 2 | 15 | 0 |
| schema_only | 130/400 | 134/400 | 800/800 | 140 | 0 | 6 | 0 |
| both | 312/400 | 334/400 | 800/800 | 344 | 2 | 12 | 0 |
| full_pack | 296/400 | 328/400 | 800/800 | 330 | 8 | 9 | 1 |

A wrong ID is measured against authored semantic gold. A guard rejection can also reject a semantically correct ID that the resolver did not authorize. The accepted-wrong-ID column counts semantic errors that passed the guard; it is not a deployment risk estimate.

## Paired changes versus original

Pairs use the same case ID in each condition. Malformed responses count as failures; missing responses are excluded from pairs and shown explicitly.

| Condition | Pairs | Helpful flips | Harmful flips | Missing pairs |
|---|---:|---:|---:|---:|
| original | 800 | 0 | 0 | 0 |
| surface_only | 800 | 386 | 9 | 0 |
| schema_only | 800 | 11 | 16 | 0 |
| both | 800 | 387 | 10 | 0 |
| full_pack | 800 | 380 | 25 | 0 |

## Per-stratum success

Entries show success / observed. These include both QA and routing tasks for the same documents.

| Stratum | original | surface_only | schema_only | both | full_pack |
|---|---:|---:|---:|---:|---:|
| ambiguous | 50/50 | 50/50 | 50/50 | 50/50 | 50/50 |
| compound_nonmention | 32/32 | 31/32 | 32/32 | 31/32 | 30/32 |
| contextual_collision | 0/74 | 1/74 | 0/74 | 1/74 | 1/74 |
| derived_role | 74/74 | 66/74 | 74/74 | 65/74 | 53/74 |
| exact | 15/98 | 96/98 | 12/98 | 94/98 | 95/98 |
| glossary_swap | 13/116 | 110/116 | 12/116 | 111/116 | 103/116 |
| multi_entity | 11/90 | 83/90 | 10/90 | 84/90 | 82/90 |
| nil | 42/42 | 42/42 | 42/42 | 42/42 | 41/42 |
| particle | 7/44 | 43/44 | 8/44 | 44/44 | 42/44 |
| project_override | 7/40 | 37/40 | 6/40 | 38/40 | 40/40 |
| session_override | 4/32 | 28/32 | 4/32 | 29/32 | 30/32 |
| typo | 2/44 | 10/44 | 2/44 | 8/44 | 4/44 |
| unicode_spacing | 0/28 | 15/28 | 1/28 | 16/28 | 17/28 |
| untrusted_override | 12/36 | 34/36 | 11/36 | 33/36 | 36/36 |

## Recorded latency and token usage

Latency percentiles use linear interpolation over actual recorded attempts, including failed attempts. There is no imputed latency for missing calls. Shared-host contention can affect these measurements.

| Condition | Attempts | p50 ms | p95 ms | p99 ms | Actual prompt tokens | Actual completion tokens | Completion max | Length finishes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| original | 800 | 870.697 | 1,775.228 | 2,413.708 | 372130 | 15965 | 106 | 0 |
| surface_only | 800 | 1,633.147 | 2,396.500 | 3,003.845 | 381092 | 25962 | 84 | 0 |
| schema_only | 800 | 870.140 | 2,050.421 | 3,282.688 | 379790 | 16518 | 128 | 1 |
| both | 800 | 1,637.400 | 2,451.985 | 3,363.345 | 388752 | 26459 | 128 | 0 |
| full_pack | 800 | 1,648.805 | 2,427.391 | 2,580.093 | 705858 | 25814 | 72 | 0 |

Actual usage observation counts, totals and distributions are in `summary.json`; estimated input tokens are reported separately and do not replace API usage.

## Limits and artifact verification

- AI-authored synthetic documents and gold; not independent human gold or deployment traffic.
- Family clusters are correlated; family macro is descriptive, without a risk bound or risk certification.
- full_pack is a separate information reference beyond the isolated four-condition 2x2.
- QA exact-match grading can reject correct paraphrases; no model-assisted repair or adjudication is performed.
- The output cap is recorded in decoding (planned 128 tokens); length finishes can constrain answers.
- Missing and malformed outputs are failures, never safe abstention; COMPLETE denotes transport coverage, not task success.
- Routing success requires semantic correctness and the original execution guard; guard acceptance alone is not semantic correctness.
- The execution guard is surface-based; explicit occurrence spans in prompts do not make it occurrence-aware.
- Latency includes recorded attempts, including failed attempts; shared-host contention can affect it, and absent outputs have no imputed latency.
- Advertised model identity is recorded; checkpoint weight revision is not established by these artifacts.

All three input artifact SHA-256 values and the canonical manifest seal were verified before this report was generated. This report reads only frozen requests, responses, graded diagnostics and manifest; it does not reload current fixtures.

Manifest seal: `8a2b1417658cd2b162e515389919f1f1b296af60b74c6d7c2619e2ce1ccc9473`.

Artifacts: [summary](summary.json), [sealed manifest](run_manifest.json), [requests](requests.jsonl), [responses](responses.jsonl), [graded diagnostics](graded.json).
