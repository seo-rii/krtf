# Fixed-candidate target/context ranking

Raw relevance scores and ranking proposals do not authorize production execution.

Backend: `scalar`; model: `nlpai-lab/KURE-Reranker-nano`.
Corpus SHA-256: `ce23c97048227872535bb6c33d74a91463b610cbec8775399c0202fb58c5c9cd`.
Risk protocol SHA-256: `cc5ae54bbff67c880e68d6d6d02cfa2f3c1416a6adf90c4944e6a9b4c99b8130`.

| Input | Positive top-1 | Candidate recall | Pair p95 ms | Max pair tokens |
|---|---:|---:|---:|---:|
| surface | 16/32 | 1.000 | 23.596 | 42 |
| local_context | 28/32 | 1.000 | 24.762 | 80 |
| target_local | 28/32 | 1.000 | 24.973 | 93 |
| target_full | 32/32 | 1.000 | 32.347 | 376 |
| path_full | 32/32 | 1.000 | 39.118 | 494 |

The corpus contains AI-authored synthetic documents, shares eight entity families,
and does not provide independent human or deployment-distribution risk validation.
The JSON report preserves every candidate score, structural guard, input pair,
and family-level proposal-risk result. Coverage validity remains false.
