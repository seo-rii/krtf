# Fixed-candidate target/context ranking

Raw relevance scores and ranking proposals do not authorize production execution.

Backend: `lexical`; model: `lexical-xenc-v1`.
Corpus SHA-256: `ce23c97048227872535bb6c33d74a91463b610cbec8775399c0202fb58c5c9cd`.
Risk protocol SHA-256: `79503e84461a1d9b445d1a50b54620a14cfd49b45b89359deae3edfd8358be7d`.

| Input | Positive top-1 | Candidate recall | Pair p95 ms | Max pair tokens |
|---|---:|---:|---:|---:|
| surface | 16/32 | 1.000 | 0.095 | None |
| local_context | 25/32 | 1.000 | 0.175 | None |
| target_local | 25/32 | 1.000 | 0.184 | None |
| target_full | 32/32 | 1.000 | 0.818 | None |
| path_full | 32/32 | 1.000 | 0.919 | None |

The corpus contains AI-authored synthetic documents, shares eight entity families,
and does not provide independent human or deployment-distribution risk validation.
The JSON report preserves every candidate score, structural guard, input pair,
and family-level proposal-risk result. Coverage validity remains false.
