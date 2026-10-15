# Occurrence evidence and assertion-veto diagnostic

Fixed candidates and thresholds; development and new synthetic heldout families are reported separately.
Scores, proposal counts and family bounds confer no production execution authority.

| Cohort | Input | Positive top-1 | Correct proposals | Wrong proposals | Negative errors | Pair p95 ms |
|---|---|---:|---:|---:|---:|---:|
| development | target_full | 146/240 | 10 | 6 | 3 | 0.525 |
| development | target_paragraph | 183/240 | 56 | 30 | 24 | 0.248 |
| development | scoped_evidence | 216/240 | 58 | 24 | 24 | 0.380 |
| development | scoped_asserted | 216/240 | 58 | 0 | 0 | 0.379 |
| heldout | target_full | 51/120 | 3 | 9 | 3 | 0.635 |
| heldout | target_paragraph | 78/120 | 10 | 12 | 11 | 0.283 |
| heldout | scoped_evidence | 86/120 | 9 | 11 | 11 | 0.439 |
| heldout | scoped_asserted | 86/120 | 9 | 0 | 0 | 0.438 |

The scoped inputs are identical with and without the assertion veto; only proposal permission changes.
All source offsets, selected quotes, veto reasons, raw scores, fixed candidates and tokenized input proofs
are retained in JSON. Multiple occurrences share document and family clusters. The alpha allocation covers
four variants, two backends and two cohorts; synthetic sampling does not establish a deployment risk bound.
