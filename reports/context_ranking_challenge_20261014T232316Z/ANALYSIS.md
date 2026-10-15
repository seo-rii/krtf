# Frozen ranking rules on new glossary families

The earlier exploratory thresholds did not transfer safely to this new
synthetic challenge. With marked whole-document context, nano made 43 correct
and 72 erroneous proposals; lexical made 10 correct and six erroneous proposals.
Both thresholds are unsuitable for execution approval on these cases. The
production resolver and its execution guards remain unchanged.

Nano ranked ordinary paraphrases well, but a repeated negated candidate name
or a rejected quotation could receive a high relevance score. Whole-document
target marks also failed to bind the two occurrences in any of the 48
two-target documents correctly. These results qualify the earlier preference
for whole-document input: retaining distant evidence helped, while retaining
unrelated or rejected definitions could dominate target selection.

## Data and completed validation

The fixture contains 24 new glossary families, 336 source documents and 384
target events. Each family supplies two registered team entities with a shared
alias. Term keys, aliases and canonical names do not overlap either previous
context-ranking source collection. There are 240 LINK events and 144 abstention
events: 24 ambiguous, 48 NIL, 48 non-mention and 24 role compositions.

Each source is 252–412 characters long. The 96 nearby and remote paraphrase
events contain neither the exact correct canonical name nor its full registered
definition. They retain some domain words and reusable authoring patterns;
new families and paraphrases do not make this independent deployment data.
Every target is supplied as a raw span and both registered family candidates
are retained. This tests ranking and abstention with a complete catalog
shortlist, rather than production retrieval or mention detection.

Before inference, a separate AI annotator reviewed a source/catalog/target-only
projection of all 384 events. The projection excluded authored gold, rationale,
evidence, titles and strata and used hashed, sorted IDs. All 384 annotations
agreed with the author, with 552 verbatim evidence quotations. Original source
and catalog hashes remained unchanged. These are two related AI annotation
passes with `human_verified=false`, not a human accuracy estimate.

The inference worker completed with exit status 0 on one-server on
2026-10-15 Korean time. Its final source revision is
`2155db117e1df72a13e2d7b4e1ea47b6736ca9ae`.
The full suite passed **1,079 tests in 76.05 seconds**. The worker took
143.09 seconds, including tests, freezing, lexical scoring and nano scoring.

The frozen case SHA-256 is
`ced7b6b15d5580733d947739ea0371f7ebf64874f5a29cbb5ee358ae787c36b0`.
Both backends received identical actual query/profile pairs. Each scored
3,072 measured batch-one pairs plus eight untimed warmup pairs. The total is
6,144 measured pair calls and 3,072 ranked target rows across both backends.
There is one repeat, so determinism is explicitly unverified. All 24 role
events retained their actual `DISTINCT / ROLE_OF` path and failed the structural
guard in every condition for both backends.

## Frozen thresholds and overall results

The lexical rule requires score ≥0.7 and margin ≥0.1. Nano requires a raw
relevance score ≥0 and margin ≥2. Both require a strictly positive margin and
a passing structural guard. These are the previous marked full-document
tune-only exploratory rules. Their original report hashes were checked, and
no threshold was fitted or selected using this challenge. Applying the same
rules to other query formats is an explicit transfer diagnostic.

Positive ranking uses only the 240 LINK events. Proposal errors include both
wrong entity choices on LINK events and any choice on an abstention event.

| Backend | Input | Correct positive top-one | Correct proposals | Wrong proposals | Wrong / all proposals |
|---|---|---:|---:|---:|---:|
| Lexical | Surface only | 120/240 | 0 | 0 | — |
| Lexical | Marked local context | 174/240 | 26 | 28 | 51.85% |
| Lexical | Unmarked whole document | 147/240 | 10 | 6 | 37.50% |
| Lexical | Marked whole document | 146/240 | 10 | 6 | 37.50% |
| Nano | Surface only | 120/240 | 0 | 0 | — |
| Nano | Marked local context | 187/240 | 105 | 35 | 25.00% |
| Nano | Unmarked whole document | 143/240 | 37 | 70 | 65.42% |
| Nano | Marked whole document | 138/240 | 43 | 72 | 62.61% |

The marked whole-document nano rule selected 43/240 correct positives, or
17.92%, with 47 wrong positive links and 25 wrong negative proposals.
The local nano input selected 105/240 correct positives, or 43.75%, with
10 wrong positive links and 25 wrong negative proposals. Local context was
better on this aggregate, but still produced substantial selection errors.
Zero proposals for surface-only input are abstention, not useful automation.

The previous 32/32 whole-context top-one results used a different, easier
fixture. This new result is a held-out synthetic stress test, not a regression
comparison on unchanged inputs or evidence of a production code failure.
Its important finding is failure of the previously chosen rules to transfer.

## Paraphrases and distant evidence

| Positive stratum | Events | Lexical local top-one | Lexical full top-one | Nano local top-one | Nano full top-one |
|---|---:|---:|---:|---:|---:|
| Nearby paraphrase | 48 | 37 | 40 | 47 | 48 |
| Remote paraphrase | 48 | 24 | 38 | 24 | 47 |
| Negated candidate-name decoy | 48 | 39 | 20 | 48 | 0 |
| Two-target document occurrences | 96 | 74 | 48 | 68 | 43 |

“Full” in this table means marked whole-document input. Nano selected
39 correct proposals on the nearby paraphrases and four on the remote
paraphrases, with no erroneous proposals in those two strata. Thus the model
often found the right distant entity but its old score/margin rule rejected
most of those correct rankings.

In the negated-decoy documents, a later passage repeatedly names the other
registered team while explicitly excluding it from the current request.
Nano local input ranked the affirmed team correctly on 48/48 events and
selected 32 correct proposals. Both full-document formats instead ranked the
excluded team first on 48/48; the frozen rule issued 46 erroneous proposals.
The high score therefore measures candidate relevance rather than reliable
affirmed reference to the selected occurrence.

These paired conditions support a context-selection failure in this fixture:
adding the later negated decoy changed the correct local ranking into an
incorrect full-document ranking. They do not prove how the model internally
represents negation or that all whole-document retrieval must fail.

## Target occurrence binding

There are 48 two-target documents, each with two occurrences of the same alias
referring to different registered teams. Unmarked whole-document inputs are
identical at the two occurrences, including candidate profiles and pair hashes.
Both backends produced identical candidate scores at those positions, so
neither could correctly assign both different entities from those inputs.

| Input | Lexical documents with both targets correct | Nano documents with both targets correct |
|---|---:|---:|
| Surface only | 0/48 | 0/48 |
| Marked local context | 27/48 | 20/48 |
| Unmarked whole document | 0/48 | 0/48 |
| Marked whole document | 0/48 | 0/48 |

Correct top-one rankings do not imply both proposals are accepted. Marked
local nano approved both correct targets in only four documents; lexical
approved both in none under its fixed rule.

Marking the whole document changed nano's selected top entity between positions
in five documents, but still did not correctly link both targets in any one
document. Across all positive events, full-document marking helped two nano
rankings and harmed seven, reducing 143 to 138 correct top-one choices.
Lexical full marking helped none and harmed one, reducing 147 to 146.
Lexical's bigram scorer does not model position, and the pretrained nano scorer
was not trained here to bind the custom target markers. Merely inserting
`[TARGET]` tags did not supply that behavior in this comparison.

## Negative references and structural safety

The quoted-example documents preserve a dictionary-looking assertion inside
an explicitly rejected editorial example. Nano selected the quoted candidate
on 24/24 events with local input and 24/24 with marked whole-document input;
lexical selected it incorrectly on 22/24 locally and 2/24 with marked full input.
The existing morphology guard allows the bare alias; it does not establish
whether an assertion in quotation is a current reference.

The remaining nano marked-full negative error is one never-effective naming
example. Its 25 negative errors are therefore all non-mentions. Nano made no
NIL, true-ambiguity or role proposals under marked-full input. Local input had
the same 25 non-mention errors. The unmarked-full nano input had 22 quoted
non-mention errors and one NIL error.

Lexical marked-full negative errors were two rejected quotations and one NIL.
Its other three errors were incorrect positive links. All 24 compositional
role expressions were blocked by the existing typed guard in every arm.
These are experimental proposals; no resolver status or execution binding was
promoted by the scorer.

## Risk diagnostics and measured cost

Targets from the same source document and all documents from one family remain
inside one family cluster. The descriptive exact bound concerns a family having
any wrong proposal, conditional on having a proposal. It differs from error
per approved entity and does not provide a service-level risk guarantee.
Alpha 0.00625 allocates 0.05 across the four input formats and two backends.

Nano had at least one wrong proposal in all 24 proposed families under local,
unmarked-full and marked-full input; its family-any-error upper bound is 1.0.
Lexical marked-full made an error in four of eight proposed families, with an
upper bound of 0.8938. Shared synthetic templates and AI annotations do not
satisfy independent deployment-sampling assumptions. All arms retain
`coverage_valid=false`, `production_authorized=false` and an uncertified
external-test status. No fixed-risk gain is established.

Nano ran in FP32 with SDPA on an A100 80 GB using PyTorch 2.13.0 and CUDA 13.0,
Transformers 5.17.0, and TF32 disabled. Peak process allocation was about
606 MiB. All 3,072 nano pair inputs were checked before the first inference.
They contain 2,208 distinct query/profile contents; some controls intentionally
repeat the same contents for different target events.
The maximum pair was 268 tokens against the frozen 1,024-token allowance;
truncation was disabled and no overflow occurred.

| Input | Nano pair p95 | Maximum nano pair tokens | Lexical pair p95 |
|---|---:|---:|---:|
| Surface only | 24.75 ms | 47 | 0.10 ms |
| Marked local context | 16.90 ms | 127 | 0.23 ms |
| Unmarked whole document | 24.82 ms | 255 | 0.51 ms |
| Marked whole document | 23.43 ms | 268 | 0.52 ms |

Timing includes tokenization, model execution and score transfer, with CUDA
synchronization. It excludes model loading, candidate retrieval, snapshot
compilation and downstream LLM work. The server is shared and each condition
was measured once; the order-dependent latency pattern is not an isolated
performance comparison.

## Next development decision

The current nano relevance rule should not be connected to automatic execution.
The productive next development target is occurrence-specific evidence
selection together with checking whether the supporting statement is affirmed,
current and outside rejected quotations. Nearby contextual evidence and remote
evidence need separate handling: always shortening the window would lose the
remote paraphrases, while always taking the whole document exposed the decoys.

Any development using these failures should treat this challenge as a consumed
test, create a distinct development partition and evaluate the resulting rules
on another untouched document/family set. The 72 marked-full nano errors cannot
be repaired by retuning on this same evaluation and then reporting its score
as held-out safety. Larger models or relaxing existing structural guards have
no support from this result.

## Artifacts

- [Source protocol](../../docs/CONTEXT_RANKING_CHALLENGE.md),
  [frozen comparison configuration](protocol.json), [frozen cases](cases.jsonl).
- [Blind AI review](blind_review.jsonl), [annotation manifest](annotation_manifest.json),
  [annotation adjudication](annotation_adjudication.json),
  [independent annotation checks](annotation_verification.json).
- [Lexical scores and inputs](lexical.json), [nano scores and inputs](nano.json),
  [raw metric recomputation](metrics_verification.json).
- [Output hashes](output_manifest.json), [collection checks](verification.json),
  [run metadata](run_manifest.json), [exit status](run_status.json),
  [completed test log excerpt](validation_log_tail.txt).
- [Executed worker](run_worker.py), [input freezer](freeze_inputs.py).

Worker PID `342964` has completed. Final exit code is `0`.
Main log: `/home/one/logs/ktrf-ranking-challenge-20261014T232316Z.log`.
Status file: `/home/one/logs/ktrf-ranking-challenge-20261014T232316Z.status.json`.
Stage commands and private log paths are preserved in the status artifact.
