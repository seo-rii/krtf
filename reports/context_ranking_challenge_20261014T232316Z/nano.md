# New-family target/context ranking challenge

AI-authored out-of-sample synthetic evaluation; no threshold refitting or production authorization.

Backend: `scalar`; frozen minimum score `0.0` and minimum margin `2.0` (strictly positive margin and existing structural guard required).
Corpus SHA-256: `ced7b6b15d5580733d947739ea0371f7ebf64874f5a29cbb5ee358ae787c36b0`.
Frozen protocol SHA-256: `c2ebfc1ebebe087ef8b777d0231c70889535077b5e6cba53357227a1ead58041`.

| Input | Positive top-1 | Correct proposals | Wrong proposals | Negative errors | Pair p95 ms |
|---|---:|---:|---:|---:|---:|
| surface | 120/240 | 0 | 0 | 0 | 24.753 |
| target_local | 187/240 | 105 | 35 | 25 | 16.898 |
| context_full | 143/240 | 37 | 70 | 23 | 24.817 |
| target_full | 138/240 | 43 | 72 | 25 | 23.428 |

Multiple target cases from one document are not independent samples. Risk diagnostics
aggregate every document and target within its entity family; the alpha budget covers
four input variants and two scoring backends. Synthetic authoring does not satisfy
independent deployment-sampling assumptions, even if a numerical bound is small.
The JSON retains all scores, guards, actual input pairs, token counts and target-pair controls.
