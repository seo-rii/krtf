# Interpretation of the completed production queue

All four model stages completed on 2026-10-14 at 02:28 KST (2026-10-13
17:28 UTC). All 1,988 planned responses were received; no request was missing
and no transport/API error was recorded. Qwen synthetic execution had three
malformed responses. Completion is distinct from task success.

The two models received identical frozen requests within each corpus, with
separate actual production QA and execution profiles. The comparison is
Gemma4 12B BF16 versus Qwen3.5 27B BF16: model family and size both change.
The original inference revision remains `e1a72fb3ac10d8b12914949f8c0947dd506ab6f1`.

## Results

| Corpus / task | Gemma 12B | Qwen 27B | Difference |
|---|---:|---:|---:|
| Synthetic QA | 402/437 (91.99%) | 414/437 (94.74%) | +12 |
| Synthetic execution | 335/437 (76.66%) | 335/437 (76.66%) | 0 |
| Real-sentence QA | 56/60 (93.33%) | 49/60 (81.67%) | -7 |
| Real-sentence execution | 57/60 (95.00%) | 58/60 (96.67%) | +1 |
| Synthetic contextual QA | 68/74 | 74/74 | +6 |
| Contextual QA pairs, both sides correct | 31/37 | 37/37 | +6 pairs |

On identical synthetic QA cases, Qwen improved 15 and worsened 3; on real QA,
it improved 0 and worsened 7. Synthetic execution had one improvement and one
regression; real execution had one improvement and no regression.

All 36 registered positive targets in the real corpus were correct for both
models and both tasks. The differences came from NIL and compositional targets.
Synthetic derived-role QA correct abstentions increased from 31/37 to 37/37;
all expected answers in that stratum are null. Both models followed
all 58 glossary-swap targets correctly for both tasks.

Synthetic execution is largely limited by resolver authorization: the frozen
guard's semantic-oracle ceiling is 336/437. Both models got 335. The 74 contextual
collision targets and 22 typo targets were never semantically correct execution
selections for either model, mostly because the resolver withheld authorization.
A larger language model alone cannot recover these links under this contract.

QA p95 latency increased from 1.65 to 2.57 seconds on synthetic requests and
from 1.05 to 1.55 seconds on real requests. Execution p95 was 3.29 versus 3.94
seconds on synthetic and 2.39 versus 2.34 seconds on real requests. These are
recorded shared-host latencies, not isolated hardware benchmarks.

## Confirmed semantic execution failures

Both models had **two wrong IDs accepted by the guard** in the real corpus.
They are the same two North Korean place-name cases, not four independent cases:

- `klue-ner-v1_dev_00139-wikitree`: a sentence about Kim's airstrips around
  Pyongyang, Wonsan and South Pyongan contains `강원도` at `[27, 30)`.
- `klue-ner-v1_dev_02242-wikitree`: a sentence about North Korean projectile
  launches contains `강원도` at `[24, 27)`.

In both cases the frozen glossary's `ORG_GANGWON` describes the South Korean
administrative unit. Both independent AI annotators labeled the target NIL.
These are distinct from the three domestic place-name convention cases that
required adjudication. Both models returned `ORG_GANGWON`, which the guard
accepted because the resolver had already committed that surface-to-ID link.
Their QA answers also repeated the South Korean glossary definition.

A read-only resolver reproduction at the frozen inference revision returned
heuristic probabilities 0.92 and 0.9425. A normal South Korean weather example
also received 0.92. Exact single-candidate matches receive a high prior; current
context overlap supplies a positive bonus rather than evidence of contradiction.
Raising the threshold alone therefore also abstains on legitimate matches.

There was no QA-ID leakage or guard bypass. The guard enforced the existing
resolver binding, and the upstream semantic error propagated into an authorized
execution selection. This is an end-to-end safety failure, tracked locally as
`BUG-001`, and it was not eliminated by the 27B model.

Synthetic Gemma also had one wrong accepted ID on
`tech-audit-access:glass-common-noun:structured_routing`: a literal glass door
(`유리문`) was linked to the glossary's inspection device. Qwen returned null for
both QA and execution on this case. Synthetic wrong accepted IDs were 1 versus 0.

## Why real QA declined

Qwen's ten NIL QA failures must not all be labeled hallucinations:

- Four selected a supplied but inappropriate glossary definition: the two
  North Korean place names and two generic/foreign police references. Gemma
  failed on these same four NIL targets.
- Three produced apparent prior-knowledge answers with an empty context pack:
  two IOC references and one university reference. Their factual correctness
  is not established by this exact-definition evaluation.
- One restated the passage's description (`더선` as `영국 매체`).
- Two returned the string `"null"` instead of the JSON null value, on
  `지브리` and `검찰`. This is wrong under the frozen answer contract even though
  the answer field has a valid string type.

Qwen also failed one compositional QA target that Gemma answered correctly.
For the six additional NIL failures, `should_inject` was false, so the production
policy fragment was not inserted; the user request still instructed null when
no supplied definition applied. This observation is not a causal attribution.
A controlled comparison would be needed to isolate the effect of policy
injection, wording, and the output schema. Original grades have not been repaired.

## What the experiment supports

The 27B comparison was useful: it improved contextual QA and derived-role abstention, but
it did not uniformly improve real-task accuracy or solve resolver-authorized
semantic errors. The next priority is contextual rejection of exact homonyms
and ordinary words, with matched legitimate examples to measure the abstention
cost. A second focused comparison should separate empty-pack answer policy from
output-schema compliance while keeping candidate selection and gold fixed.

These results do not establish a reason to replace the current model globally.
Before a production adoption claim, evaluate the intended default context
budget (this run used 6000 estimated tokens, not 800), independent human-reviewed
real documents, and fixed-risk execution performance. The 60-sentence real set
is stratified and AI annotated, with one primary target per sentence; 2/60 is
not an estimate of deployment-wide error and this is not exhaustive recall.

## Artifact verification and collection recovery

See the [queue overview](RESULTS.md), [synthetic paired comparison](synthetic_comparison.md)
and [real paired comparison](real_comparison.md). Stage directories retain sealed
requests, raw responses, grades, model environment and the original summaries.

The original collector exited 1 before pushing any report because Python 3.11
and the remote Python computed two latency totals with different floating-point
last digits. Scores, artifact hashes, individual latencies and percentiles were
identical. Commit `fdb34624c63a3840348269514b2eb0c0fdc58984` uses `math.fsum` only
for production latency totals and retains strict whole-summary comparison.
All twelve task/overall latency totals across the four runs exactly match the
original remote summaries under the corrected method. Nineteen report tests
and the Python 3.11 regression passed. No GPU inference was rerun, and no gold,
raw model output, seal or grading rule was changed.

The failed collector status and partial copy were preserved outside the report
checkout. Recovery revalidates the original manifests and regrades every stage
before publishing its report. Recovery completed with exit code 0 and pushed
all four stage reports and both paired comparisons. Original inference provenance
and report-collection code provenance are intentionally distinct.
