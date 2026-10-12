# KURE candidate reranking: constructed CPU smoke comparison

Both checkpoints were evaluated on the same 12 constructed confusion cases and fixed shortlists.
Nine cases have a unique gold hypothesis; two are genuinely ambiguous and one is NIL.
This is an adapter/input smoke test, not independent document gold or a fixed-risk commit evaluation.

| Model | Input | Unique-gold exact link top-one | Family macro | Batch-one pair p50 | Pair p95 |
|---|---|---|---|---|---|
| KURE-Reranker-nano | surface | 3/9 | 0.3333 | 4597.6 ms | 6959.5 ms |
| KURE-Reranker-nano | context | 6/9 | 0.6667 | 261.1 ms | 4794.6 ms |
| KURE-Reranker-nano | target | 4/9 | 0.4167 | 203.2 ms | 496.0 ms |
| KURE-Reranker-nano | path | 3/9 | 0.3333 | 331.4 ms | 568.1 ms |
| KURE-v2 | surface | 6/9 | 0.6667 | 1315.8 ms | 4647.9 ms |
| KURE-v2 | context | 8/9 | 0.9167 | 2124.5 ms | 10363.3 ms |
| KURE-v2 | target | 8/9 | 0.9167 | 10637.9 ms | 17893.2 ms |
| KURE-v2 | path | 8/9 | 0.9167 | 10613.1 ms | 16321.5 ms |

The lexical control measured 7/9 with surface input and 8/9 with context, target and path input.
Compare only these constructed cases; no larger-model improvement or safe commit-rate gain is established.
True ambiguity and NIL are excluded from the top-one denominator but remain in raw diagnostics.
Ranking scores never issue commits and cannot lift the typed-derivative guard.

The common runtime is CPU with OMP/MKL thread caps of four, input allowance 192 tokens,
candidate budget eight (two supplied hypotheses per case), radius 60 and one measured repeat.
KURE-v2 uses query/document caps of 96 each; this changes its native 64-token query expansion.
Actual token usage differs by format. One repeat does not test determinism.
Pair timing includes tokenization, inference, CPU transfer and reference Python MaxSim for v2;
model loading, retrieval and compilation are excluded, although first-seen-shape work after warmup
can still affect the tiny p95 sample. MaxSim profile encoding is repeated rather than cached.

Data SHA-256: `d59adf9c8bc5d94289112e3aaf1baa5dbc54bf2afebace9eb66b5ae982d65e93`.

Runtime packages: `{"onnxruntime": null, "pylate": "1.6.0", "tokenizers": "0.22.2", "torch": "2.11.0", "transformers": "5.3.0"}`.

| Model | Pinned revision | Process peak RSS | Measured at UTC |
|---|---|---|---|
| nlpai-lab/KURE-Reranker-nano | `f3b3eff2b5251f135b638891ebe7d6c5ae94cc3e` | 1276.0 MiB | 2026-10-12T15:32:01.483334+00:00 |
| nlpai-lab/KURE-v2 | `3431f86d399d666083890dbb882aced6708873bc` | 1085.6 MiB | 2026-10-12T15:43:23.356194+00:00 |

Raw reports retain model-content digests, individual cases, scores, guard reasons and timing counts:
[nano](rerank_nano_smoke.json), [v2](rerank_kure_v2_smoke.json).

The preliminary nano run used a different dependency environment and was superseded by this common-runtime rerun.
Its metrics are not pooled into this comparison. Runtime/export parity still needs validation before deployment.
No ONNX export or production multi-vector index was built. Independent human document annotations,
disjoint calibration, risk-controlled threshold validation and larger latency samples remain necessary.

Comparison process verified exit status 0.
Process log: `/home/seorii/logs/krtf-kure-comparison-20261013-002836.log`.
Exit-status file: `/home/seorii/logs/krtf-kure-comparison-20261013-002836.status`.
