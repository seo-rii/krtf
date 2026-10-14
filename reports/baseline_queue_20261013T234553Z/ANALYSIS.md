# Plain glossary retrieval versus KTRF: interpretation

All four baseline stages completed on 2026-10-14 at 11:49 KST
(02:49 UTC), with queue exit code 0. All 1,988 planned responses were
received; there were no missing responses or API/transport errors. Seven
responses were malformed: one synthetic Gemma response, five synthetic
Qwen responses and one real-sentence Qwen response. Completion does not
mean every answer was correct.

**KTRF did not consistently improve QA accuracy, and its execution policy
withheld many links that the plain retrieval baseline answered correctly.**
It reduced prompt size substantially and reduced some wrong accepted IDs,
but the tradeoff depended on the model. In particular, the synthetic Qwen
baseline made 90 more correct accepted selections with the same observed
count of wrong accepted IDs: zero in both arms. This is a sample result,
not a deployment safety guarantee.

## Matched semantic results

B supplies glossary entries using deterministic character/bigram retrieval.
C is the previously sealed KTRF production run. Within each comparison,
the source documents, gold, requested model and decoding settings match.
The primary metric is a schema-valid exact semantic match before either
arm's execution validator. Null answers receive credit only where the gold
requires abstention; malformed or missing responses never receive null credit.

| Corpus | Model | QA, B → C | ID linking, B → C |
|---|---|---:|---:|
| Synthetic, 437 targets | Gemma4 12B | 406 → 402 | 424 → 335 |
| Synthetic, 437 targets | Qwen3.5 27B | 411 → 414 | 425 → 335 |
| Real sentences, 60 targets | Gemma4 12B | 58 → 56 | 56 → 57 |
| Real sentences, 60 targets | Qwen3.5 27B | 50 → 49 | 58 → 58 |

For synthetic QA, C helped 18 and harmed 22 Gemma cases; it helped 22 and
harmed 19 Qwen cases. These mixed changes should not be described as
uniform improvement. For real-sentence QA, C helped 0 and harmed 2 Gemma
cases; it helped 3 and harmed 4 Qwen cases. All 36 registered positive
targets in the real corpus were answered correctly by both arms and both
models; the differences arose on targets requiring abstention.

The stage reports contain the complete paired changes and per-stratum tables:
[synthetic Gemma](synthetic_gemma12b/RESULTS.md),
[synthetic Qwen](synthetic_qwen27b/RESULTS.md),
[real-sentence Gemma](real_gemma12b/RESULTS.md) and
[real-sentence Qwen](real_qwen27b/RESULTS.md).

## Execution tradeoff

Semantic matching includes correct abstentions. The following table isolates
actual accepted non-null selections. B checks output schema and membership
in the IDs it supplied. C uses its original production guard. B is never
passed through C's guard, and acceptance alone is not evidence of correctness.

| Corpus | Model | Correct IDs accepted, B → C | Wrong IDs accepted, B → C |
|---|---|---:|---:|
| Synthetic | Gemma4 12B | 330 → 236 | 7 → 1 |
| Synthetic | Qwen3.5 27B | 325 → 235 | 0 → 0 |
| Real sentences | Gemma4 12B | 36 → 36 | 4 → 2 |
| Real sentences | Qwen3.5 27B | 36 → 36 | 2 → 2 |

For synthetic Gemma, six fewer wrong accepted IDs accompany 94 fewer
correct accepted IDs. For synthetic Qwen, 90 correct accepted IDs are lost
without an observed reduction in wrong accepted IDs. This makes unnecessary
abstention a concrete improvement target rather than an incidental cost.
Neither model removes the two real-sentence wrong accepted IDs already
identified in the [production analysis](../production_queue_20261013T160054Z/ANALYSIS.md).

The largest synthetic execution regressions are contextual collisions:
B succeeds and C fails on 71 Gemma cases and 74 Qwen cases. Typo cases add
19 and 14 regressions respectively. B supplies the gold ID for all 337
positive synthetic targets; C's exact-target-bound execution cards contain
it for 236/337. C's QA cards contain it for 318/337. Both arms cover all
36/36 positive real targets. These figures have different evidence scopes
(B's supplied entries versus C's target-bound cards), but they show where
information and authorization become unavailable to the language model.

The next resolver experiment should recover context-resolvable collision
and typo links while retaining the semantic guards, then compare accepted
correct IDs at a predeclared error limit. A larger model alone cannot restore
execution authorization that the resolver has withheld. The observed zero
errors for Qwen B is insufficient to certify such a limit.

## Evidence size and cost

Median supplied candidate counts are 3 for B versus 1 for C on synthetic
targets, and 12 versus 1 on real targets. Total prompt tokens below combine
the separate QA and execution calls within each corpus/model.

| Corpus | Model | Prompt tokens, B → C | Reduction |
|---|---|---:|---:|
| Synthetic | Gemma4 12B | 702,544 → 509,192 | 27.52% |
| Synthetic | Qwen3.5 27B | 664,206 → 472,734 | 28.83% |
| Real sentences | Gemma4 12B | 160,464 → 61,081 | 61.93% |
| Real sentences | Qwen3.5 27B | 152,268 → 56,505 | 62.89% |

Prompt savings do not consistently translate into lower measured latency.
For example, synthetic Gemma execution p95 increases from 2.46 to 3.29
seconds, whereas synthetic Qwen execution p95 decreases from 4.29 to 3.94
seconds. On real targets, Gemma execution p95 increases from 1.63 to 2.39
seconds and Qwen decreases from 2.42 to 2.34 seconds. These are recorded
model-call latencies on a shared server. Frozen request preparation,
including glossary compilation and retrieval, is excluded. Total latency
uses `math.fsum`; no missing calls receive imputed latency.

## Scope of the conclusion

- B and C are matched by document, gold, model and decoding, but differ in
  retrieval, prompt packaging, policy and execution validation. This measures
  the complete systems, not the isolated causal effect of the resolver.
- C is a historical sealed run, not a concurrent randomized control.
  Shared-host load and runtime state can differ, so latency differences are
  descriptive rather than controlled hardware comparisons.
- B is lexical glossary retrieval, not a trained dense RAG baseline. Its
  allowance is 12 entries and 6,000 estimated context tokens; actual model
  tokens are reported separately.
- QA requires exact glossary definitions and does not credit paraphrases.
  Dictionary-free models cannot fairly recover private opaque IDs, so this
  experiment does not use LLM-only answers as its primary control.
- Synthetic targets and AI-annotated real sentences are not independent
  human gold. The real set is stratified, has one primary target per sentence
  and does not measure exhaustive document recall. Its error counts must not
  be extrapolated to a deployment-wide rate.
- The baseline was designed after inspecting the earlier KTRF run. It is a
  diagnostic matched comparison, not a fresh sealed risk test. No raw output,
  gold or grading rule was changed to improve the comparison.

The completed [document-context matrix](../document_context_queue_20261014T024026Z/ANALYSIS.md)
examines evidence availability and context boundaries on a separate authored
corpus. Neither result establishes a general task-accuracy advantage over
plain glossary retrieval. Its demonstrated advantages here
are smaller prompts and, in some settings, fewer accepted semantic errors;
the large avoidable execution abstention cost remains to be addressed.

## Provenance

Baseline inference revision: `6a44829a73a6efcca4a1afed07c8c4504d2cbc6a`.
Historical C inference revision: `e1a72fb3ac10d8b12914949f8c0947dd506ab6f1`.
The reports verify both arms' sealed artifacts, frozen grading, matching
source manifests, case identities, per-request hashes, model and decoding.
Stage `summary.json` files preserve the paired outcomes, candidate recall,
operational acceptance and cost tables behind this interpretation.
