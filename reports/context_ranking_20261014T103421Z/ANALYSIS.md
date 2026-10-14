# Candidate and target-context ranking

Whole-document context recovered the correct first-ranked candidate on all
32 positive documents for both the lexical control and KURE-Reranker-nano.
The nano model supplied more correct proposals under a tune-only exploratory
threshold, but this reused synthetic set cannot authorize production execution.
Appending the structural-path JSON did not improve top-one accuracy and reduced
the nano model's exploratory selections.

The run completed successfully on one-server on 2026-10-14, with exit status 0.
The full suite passed **1,037 tests in 74.37 seconds**. The four sequential stages
were unit tests, input/checkpoint freezing, lexical scoring and nano scoring;
the complete worker took 127.76 seconds. Inference source revision is
`8613d34789457e58d4c13409c43d93be8a4c77db`.

## Comparison held constant

All 64 previously evaluated AI-authored documents were retained unchanged:
32 original contextual-confusion documents and 32 explicit-definition controls.
There are 32 unique-link positives and 32 abstention controls: eight each of
true ambiguity, NIL, role composition and non-mention. The glossary supplies
the same two family candidates for every document, including negatives. This
is a controlled complete-catalog shortlist, rather than a production retrieval
or mention-detection evaluation.

Both backends received exactly the same query/profile pairs. Entity IDs, gold,
rationales and decisive-evidence annotations were excluded from those inputs.
The same shared segmentation produced one path per document and both entity
hypotheses used it. Thus the path condition measures adding decomposition
features, not selecting among competing decomposition paths.

The raw corpus SHA-256 is
`ce23c97048227872535bb6c33d74a91463b610cbec8775399c0202fb58c5c9cd`.
The pinned nano revision is `f3b3eff2b5251f135b638891ebe7d6c5ae94cc3e`,
with model-content SHA-256
`139bfeeeb05e6d36886461102645b7e987ff6ac042b935faf45cbde4bf5622f9`.
This content hash matches the earlier nano smoke comparison.

The model checked all 640 unique input pairs before inference. The allowance
was 1,024 tokens; the longest actual pair was 494, with no truncation.
Each backend made 1,920 measured batch-one pair calls across three repeats,
plus ten untimed warmup calls. Repeated scores and rankings were identical.
All eight role expressions retained their `DISTINCT / ROLE_OF` interpretation
and failed the structural guard in all five conditions, for both backends.

## Positive ranking

The denominator is the 32 LINK documents. Negative cases cannot earn a correct
link by choosing either candidate. Because each family has four positives, the
family-macro accuracy equals the pooled accuracy in this particular fixture.

| Query input | Lexical correct top-one | Nano correct top-one | Nano max pair tokens | Nano pair p95 |
|---|---:|---:|---:|---:|
| Core surface only | 16/32 | 16/32 | 42 | 23.60 ms |
| Unmarked local context | 25/32 | 28/32 | 80 | 24.76 ms |
| Marked target, local context | 25/32 | 28/32 | 93 | 24.97 ms |
| Marked target, entire document | 32/32 | 32/32 | 376 | 32.35 ms |
| Entire document plus structural path | 32/32 | 32/32 | 494 | 39.12 ms |

All local-context ranking mistakes occurred in the eight remote-cue documents:
lexical selected the right entity on 1/8 and nano on 4/8. Both methods ranked
all eight nearby-cue documents and all 16 canonical/definition declarations
correctly with local context. Supplying the entire document recovered all eight
remote cases for both methods. This supports preserving the decisive context;
it does not establish a top-one advantage for the neural scorer on full inputs.

Target marks did not improve local top-one accuracy here. There is no unmarked
whole-document condition, and every document has one selected matching path,
so this experiment does not isolate a benefit from target marking or path
selection. The maximum whole-document pair is only 376 tokens: these results
do not establish behavior on large business documents.

## Exploratory selection and abstention

Score and margin grids, family partitions and the structural requirement were
declared before this run's scores. Tune families are `f05, f03, f01, f02`;
test families are `f08, f06, f04, f07`. Each side has 16 positives and 16 negatives.
The exploratory rule maximizes proposals among zero-observed-error tune rules,
with predeclared conservative tie breaking. Test scores never choose the rule.
These are raw relevance thresholds, not calibrated probabilities.

| Backend/input | Tune-selected minimum score / margin | Tune correct / wrong proposals | Test correct / wrong proposals | Test positive recall |
|---|---|---:|---:|---:|
| Lexical, entire document | 0.7 / 0.1 | 8 / 0 | 6 / 0 | 37.50% |
| Nano, entire document | 0 / 2 | 14 / 0 | 13 / 0 | 81.25% |
| Lexical, entire document plus path | 0.5 / 0.1 | 7 / 0 | 6 / 0 | 37.50% |
| Nano, entire document plus path | 0 / 2 | 12 / 0 | 11 / 0 | 68.75% |

No error-free positive-proposal rule existed on the declared grid for either
backend's surface or local-context conditions. This refers to the grid and
corpus used, rather than proving that every other threshold must fail.

The nano whole-document rule accepted 11/16 original implicit positives and
16/16 explicit controls across both partitions. In the test partition it
accepted five of eight implicit positives and all eight explicit positives.
Its five rejected positives across both partitions were `f01-d01`, `f03-d01`,
`f04-d02`, `f06-d02` and `f08-d02`, all remote-cue documents. They were ranked
correctly but did not meet the score/margin rule.

Across the 64 documents, this rule rejected all eight ambiguous, eight NIL and
eight non-mention cases; the structural guard blocked all eight role cases.
However, merely selecting the highest-scoring structurally allowed candidate
would select all 24 non-role negatives incorrectly in either whole-document
backend. High ranking accuracy alone therefore supplies no abstention contract.

The path JSON preserved the same correct winner but reduced separation:
nano's test selections fell from 13 to 11 and its pair p95 increased from
32.35 to 39.12 ms. Keeping the typed guard outside the scorer does not require
inserting that JSON into the scorer's query. The present evidence favors the
simpler marked whole-document input for the next independent comparison.

## Risk gate and cost

There are four entity families per partition. The conservative diagnostic
treats a family with any wrong proposal as one failed trial, combining both
document collections inside that family. Its quantity is family-any-error
conditional on having a proposal, not per-commit entity error. The alpha budget
accounts for both stages, all five variants and every declared threshold rule.

No rule passed the statistical threshold-selection gate. For the whole-document
exploratory rules, the test family-any-error upper bound is **0.9321** for lexical
and **0.8864** for nano, despite observing no errors. At the nano protocol's
allocated alpha, 170 zero-error independent proposed families would be needed
to meet the five-percent numerical bound. Artificially generating that many
families would not make them representative independent deployment audits.
Every result remains `INSUFFICIENT_DATA`, `coverage_valid=false` and
`production_authorized=false`.

Nano ran in FP32 using SDPA on an A100 80 GB with batch size one, Transformers
5.17.0 and PyTorch 2.13.0 (CUDA 13.0); TF32 was disabled. The process's peak allocated
CUDA memory was about 614 MiB. Pair p95 includes tokenization, model execution
and CPU transfer, and excludes loading, retrieval, compilation of snapshots and
LLM generation. Lexical whole-document p95 was 0.82 ms. Shared-server load and
the different CPU/GPU implementations prevent interpreting these figures as an
isolated end-to-end speed comparison.

The next adoption check should compare lexical and nano whole-context rules on
new, independently sampled document gold, preserve existing semantic and
execution guards, and validate thresholds on separate events. This run supports
further testing of neural selective ranking, without enabling it to issue
production IDs. It also provides no reason to increase the LLM size for the
candidate-ranking subtask.

## Artifacts

- [Frozen cases](cases.jsonl), [predeclared protocols](protocols.json),
  [checkpoint identity](checkpoint.json).
- [Lexical raw report](lexical.json), [nano raw report](nano.json): all candidate
  scores, paths, guards, actual inputs, token proof, thresholds and repeat checks.
- [Worker status and exit codes](run_status.json), [run manifest](run_manifest.json),
  [output hashes](output_manifest.json), [collection verification](verification.json).
- [Executed worker](run_worker.py), [input freezer](freeze_inputs.py),
  [completed unit-test log excerpt](unit_log_tail.txt).
- [Protocol and reproduction](../../docs/CONTEXT_RANKING.md).

Persistent worker PID: `319830` (completed).
Main log: `/home/one/logs/ktrf-context-ranking-20261014T103421Z.log`.
Final status: `/home/one/logs/ktrf-context-ranking-20261014T103421Z.status.json`.
Individual stage log paths and commands are preserved in the status artifact.
