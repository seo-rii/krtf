# Occurrence evidence selection and assertion checks

The frozen selector improved nano's results on the separately authored
held-out synthetic cohort: marked whole-document input produced four correct
and 21 erroneous proposals, while scoped evidence plus assertion checks
produced 48 correct and two erroneous proposals. The two remaining errors
were genuinely ambiguous references. This is useful evidence for occurrence
selection and quotation handling, but does not justify automatic execution.

The previous challenge is now explicitly development data. Its strong
improvement is reported separately from the new 12-family evaluation. The
selector and its thresholds were not changed after reviewing or scoring the
new cohort. The production resolver and execution contract were not modified.

## Frozen implementation and data

The experiment compares four inputs with the same two registered candidates:

| Variant | Source selection | Additional proposal requirement |
|---|---|---|
| `target_full` | Marked whole document | Existing structural guard |
| `target_paragraph` | Whole target paragraph | Existing structural guard |
| `scoped_evidence` | Target paragraph and up to two eligible support paragraphs | Existing structural guard |
| `scoped_asserted` | Identical inputs and scores to `scoped_evidence` | Structural guard and assertion check |

Support selection uses vocabulary from all candidates, rather than selecting
a gold entity. Multiple occurrences stay within the selected paragraph;
a single occurrence may retrieve support inside its section. Complete source
passages, offsets and quotations are retained. The assertion check is a bounded
lexical veto for quoted assertions, target negation, scoped retraction,
unregistered objects and explicit unresolved references. Passing it means
that these vetoes did not fire; it is not semantic entailment.

Lexical score ≥0.7/margin ≥0.1 and nano raw score ≥0/margin ≥2 are unchanged
from the earlier exploratory rules. Both also require a positive margin and
the existing structural guard. No threshold fitting or search took place.

Development contains the consumed challenge's 24 families, 336 documents and
384 events, including 240 LINK events. Held-out evaluation contains 12 new
families, 144 documents and 168 events: 120 LINK and 12 each of quotation
non-mention, role composition, NIL and genuine ambiguity. Catalog keys,
aliases, canonical names and complete source documents are disjoint between
cohorts. The new sources are 226–493 characters long and include 24 positively
asserted quoted names and 24 multi-target documents.

Selector source was frozen in `291e10faf8dc8594696e7d10243f19cd96eb224d`,
SHA-256 `1bdaced2bad896ea61b649b4d464bf643cd03d0396f7e1f541e53635d4aa80f2`,
before the held-out blind annotation review started. A separate AI annotator
received only source, catalog and target positions with hashed IDs. All 168
labels agreed with the author, with 336 verbatim evidence quotations. Source
and selector hashes stayed unchanged. Both cohorts are AI-authored synthetic
data with `human_verified=false`, not a human or deployment-distribution audit.

## Held out results

Positive ranking uses the 120 LINK events. Wrong proposals also count any
selection on the 48 abstention events.

| Backend | Input | Positive top-one | Correct proposals | Wrong proposals |
|---|---|---:|---:|---:|
| Lexical | Whole document | 51/120 | 3 | 9 |
| Lexical | Target paragraph | 78/120 | 10 | 12 |
| Lexical | Scoped evidence | 86/120 | 9 | 11 |
| Lexical | Scoped evidence with assertion check | 86/120 | 9 | 0 |
| Nano | Whole document | 61/120 | 4 | 21 |
| Nano | Target paragraph | 90/120 | 41 | 12 |
| Nano | Scoped evidence | 109/120 | 48 | 14 |
| Nano | Scoped evidence with assertion check | 109/120 | 48 | 2 |

For nano, choosing the target paragraph recovered 41 correct proposals and
eliminated all seven wrong positive links seen with full input. Adding scoped
support improved positive top-one ranking from 90 to 109 and correct proposals
from 41 to 48. It also introduced two ambiguity errors that the paragraph-only
rule had abstained on. Support retrieval therefore has a measurable cost as
well as a recall benefit.

The assertion check removed all 12 quoted-example proposals without removing
any correct proposal in this cohort. Scores and inputs were exactly identical
between the two scoped arms. Lexical's check similarly removed 11 wrong
proposals while retaining nine correct ones. Neither checker vetoed a positive
event in this fixture, including the positively asserted quoted names.

Nano's final correct-proposal recall is 48/120, or 40%. Of its 109 correct
rankings, 61 still fail the old score/margin rule. Its other 11 positive ranking
errors are spread across multi-target occurrences, negated-decoy cases and
paraphrases; the threshold abstained on every one. This is a selective ranking
result, not an end-to-end coverage or accuracy guarantee.

## Target binding and remaining ambiguity

On the 24 held-out two-target documents, nano's full input correctly ranked
both occurrences in one document and approved both in none. Paragraph and
scoped inputs ranked both correctly in 20/24 and approved both correctly in
6/24. Lexical ranked both correctly in 14/24 after paragraph selection but
approved both in none. Selecting the appropriate source passage helped more
than merely marking an occurrence in the full document.

The final nano mistakes are `ev06-d12::ev06-d12-t01` and
`ev07-d12::ev07-d12-t01`. Their source explicitly states that the recipient
field contains only the shared alias, the request body is empty, and there is
no attachment or previous conversation to identify the intended team. The
scoped query retains both currently valid teams. The lexical uncertainty
patterns do not recognize this wording, so the veto allows it; nano's raw
score and margin then select one candidate. The sources and annotations were
not changed to accommodate these mistakes.

The held-out set has now been consumed. Adding these exact phrases to the
veto and reporting the same set as a fresh safety test would be invalid.
A later development step should require adequate affirmative evidence and
handle unresolved reference more generally, then use a new evaluation set.

## Development results and external limitations

| Backend | Input | Correct proposals | Wrong proposals |
|---|---|---:|---:|
| Lexical | Whole document | 10 | 6 |
| Lexical | Target paragraph | 56 | 30 |
| Lexical | Scoped evidence | 58 | 24 |
| Lexical | Scoped with assertion check | 58 | 0 |
| Nano | Whole document | 43 | 72 |
| Nano | Target paragraph | 141 | 25 |
| Nano | Scoped evidence | 211 | 26 |
| Nano | Scoped with assertion check | 211 | 0 |

The development full-input controls reproduce every original candidate score,
winner and proposal decision exactly. This makes the source-selection
comparison interpretable against the earlier failure. Development nano reaches
240/240 positive top-one, while the new cohort reaches 109/120; these denominators
must not be pooled into an independent validation claim.

Independent source-only review also produced two false-veto probes outside the
measured cohorts. In one, an affirmed request followed by a denial concerning
another team is rejected. In the other, the later retraction of an explicitly
unrelated meeting-record explanation vetoes the earlier request. These show
that zero positive vetoes in the measured fixture does not establish a general
absence of over-abstention. Exact inputs and actual results are preserved in
[scope_limitations.json](scope_limitations.json); no model scores were used
for those review probes. The frozen selector was not changed in response.

All 36 measured role events keep `DISTINCT / ROLE_OF` and remain structurally
blocked for every backend/input. No score or assertion check can lift that
guard. The module remains experimental and is not called by the production
resolver.

## Risk and cost

All targets and documents from a family stay in one cluster. The descriptive
family-any-error upper bound allocates alpha 0.003125 across four variants,
two scorers and two cohorts. It concerns any wrong proposal in a proposed
family, not error per proposal. Synthetic templates and related AI annotations
do not satisfy independent deployment sampling assumptions.

Final held-out nano has errors in two of 11 proposed families, with upper bound
0.6309. Lexical has no observed errors but only three proposed families, with
upper bound 0.8538. Even development nano's zero-error bound is 0.2136 over
24 proposed families. No arm establishes the five-percent diagnostic target;
`coverage_valid=false` and `production_authorized=false` remain in every report.

Nano used FP32/SDPA on an A100 80 GB, PyTorch 2.13.0 with CUDA 13.0,
Transformers 5.17.0, and TF32 disabled. Every actual pair was checked before
warmup or inference: 4,416 pair inputs per backend, containing 2,616 distinct
query/profile contents. Maximum nano length was 325 tokens within the frozen
1,024-token allowance, with truncation disabled. Each backend made 4,416 measured
batch-one calls plus eight untimed warmup calls. One repeat leaves determinism
unverified.

On held-out data, scoped selection p95 was 0.59 ms per occurrence in the nano
process, measured separately from pair scoring. Pair p95 was 32.03 ms for full
input, 26.06 ms for the target paragraph, 14.88 ms for scoped evidence and
28.42 ms for the same scoped inputs with the later assertion arm. The identical
scoped pairs have identical scores but different measured latency, illustrating
the shared server and order effects. These measurements do not establish an
isolated speedup. Selection is cached once per mode/event; loading, snapshot
compilation, production retrieval and downstream LLM work are excluded.

The sequential worker exited with code 0 in 189.30 seconds. The full suite
passed **1,158 tests in 78.14 seconds**. Inference revision is
`eda4afd218c5c766a787dda903dbd7c02f5c5d10`.

## Artifacts

- [Protocol](protocol.json), [development cases](development_cases.jsonl),
  [held-out cases](heldout_cases.jsonl), [implementation notes](../../docs/OCCURRENCE_EVIDENCE.md).
- [Blind annotations](blind_review.jsonl), [annotation manifest](annotation_manifest.json),
  [annotation checks](annotation_verification.json), [scope counterexamples](scope_limitations.json).
- [Lexical scores and inputs](lexical.json), [nano scores and inputs](nano.json),
  [recomputed metrics](metrics_verification.json), [collection verification](verification.json).
- [Source and runtime manifest](run_manifest.json), [artifact hashes](output_manifest.json),
  [exit status](run_status.json), [completed test excerpt](validation_log_tail.txt).

Worker PID `360722` has completed. Exit code: `0`.
Log: `/home/one/logs/ktrf-occurrence-evidence-20261015T050659Z.log`.
Status: `/home/one/logs/ktrf-occurrence-evidence-20261015T050659Z.status.json`.
