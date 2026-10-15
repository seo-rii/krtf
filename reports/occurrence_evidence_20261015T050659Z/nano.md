# Occurrence evidence and assertion-veto diagnostic

Fixed candidates and thresholds; development and new synthetic heldout families are reported separately.
Scores, proposal counts and family bounds confer no production execution authority.

| Cohort | Input | Positive top-1 | Correct proposals | Wrong proposals | Negative errors | Pair p95 ms |
|---|---|---:|---:|---:|---:|---:|
| development | target_full | 138/240 | 43 | 72 | 25 | 28.857 |
| development | target_paragraph | 192/240 | 141 | 25 | 25 | 25.184 |
| development | scoped_evidence | 240/240 | 211 | 26 | 26 | 29.811 |
| development | scoped_asserted | 240/240 | 211 | 0 | 0 | 26.997 |
| heldout | target_full | 61/120 | 4 | 21 | 14 | 32.034 |
| heldout | target_paragraph | 90/120 | 41 | 12 | 12 | 26.062 |
| heldout | scoped_evidence | 109/120 | 48 | 14 | 14 | 14.880 |
| heldout | scoped_asserted | 109/120 | 48 | 2 | 2 | 28.420 |

The scoped inputs are identical with and without the assertion veto; only proposal permission changes.
All source offsets, selected quotes, veto reasons, raw scores, fixed candidates and tokenized input proofs
are retained in JSON. Multiple occurrences share document and family clusters. The alpha allocation covers
four variants, two backends and two cohorts; synthetic sampling does not establish a deployment risk bound.
