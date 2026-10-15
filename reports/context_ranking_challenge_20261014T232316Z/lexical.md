# New-family target/context ranking challenge

AI-authored out-of-sample synthetic evaluation; no threshold refitting or production authorization.

Backend: `lexical`; frozen minimum score `0.7` and minimum margin `0.1` (strictly positive margin and existing structural guard required).
Corpus SHA-256: `ced7b6b15d5580733d947739ea0371f7ebf64874f5a29cbb5ee358ae787c36b0`.
Frozen protocol SHA-256: `15102388dca767d312a727b46bc13dde1e45a74e8fd8f7aff6fa6eba27fc4ec5`.

| Input | Positive top-1 | Correct proposals | Wrong proposals | Negative errors | Pair p95 ms |
|---|---:|---:|---:|---:|---:|
| surface | 120/240 | 0 | 0 | 0 | 0.095 |
| target_local | 174/240 | 26 | 28 | 25 | 0.232 |
| context_full | 147/240 | 10 | 6 | 3 | 0.513 |
| target_full | 146/240 | 10 | 6 | 3 | 0.524 |

Multiple target cases from one document are not independent samples. Risk diagnostics
aggregate every document and target within its entity family; the alpha budget covers
four input variants and two scoring backends. Synthetic authoring does not satisfy
independent deployment-sampling assumptions, even if a numerical bound is small.
The JSON retains all scores, guards, actual input pairs, token counts and target-pair controls.
