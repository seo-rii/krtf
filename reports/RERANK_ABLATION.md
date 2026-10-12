# Fixed-candidate rerank input smoke experiment

Measured on 2026-10-13 with the zero-dependency `lexical-xenc-v1` scorer, CPU,
Python 3.14.7. The 12 cases are constructed review examples, with nine uniquely
resolvable cases, two genuinely ambiguous cases and one NIL case. They are not
blind document gold and cannot establish deployment quality or fixed-risk gains.

```bash
python -m eval.run_rerank_ablation --out eval/out/rerank_ablation.json \
  --pairs-out eval/out/confusion_pairs.jsonl
```

Case SHA-256: `d59adf9c8bc5d94289112e3aaf1baa5dbc54bf2afebace9eb66b5ae982d65e93`.

Each variant received the same two hypotheses per case (budget cap eight),
context radius 60, one untimed warmup case and three measured repeats. Each pair
was scored serially at batch one: 72 measured calls per format. No model downloads,
neural inference, calibration or automatic commits were performed.

| Input | Exact link top-one, uniquely resolvable | Family macro | Fixed-candidate recall | Candidates/case | Batch-one pair p95 |
|---|---|---|---|---|---|
| surface | 7/9 | 0.8333 | 1.0000 | 2.0 | 0.050 ms |
| context | 8/9 | 0.9167 | 1.0000 | 2.0 | 0.107 ms |
| target | 8/9 | 0.9167 | 1.0000 | 2.0 | 0.123 ms |
| path | 8/9 | 0.9167 | 1.0000 | 2.0 | 0.211 ms |

Context recovers one constructed shared-alias case compared with surface-only
input. Target marking and path information do not improve this lexical baseline
further. Both occurrences in the multi-target sentence still receive the same
lexical winner, leaving the billing occurrence wrong. This is the failure the
neural comparison must measure, not evidence that adding markers alone solves it.

The family macro groups constructed confusion categories, not independent real
entity families. NIL and genuine ambiguity are excluded from top-one accuracy
and remain explicit in diagnostics. No top-one choice is issued as a commit.
The typed derivative guard is separately verified under a deliberately dominant
model score. Candidate-budget reduction is tested to expose recall loss.

These tiny latency measurements describe scorer plumbing only. They are noisy,
exclude retrieval and do not predict neural batch-one latency. Pinned KURE-Reranker-nano and KURE-v2 CPU comparisons are recorded separately
when completed. ONNX parity and independent quality/risk comparisons remain
pending; these constructed cases cannot establish deployment improvements.
See [the protocol](../docs/RERANK_EXPERIMENTS.md) for the executable neural adapters
and the disjoint calibration/threshold/test acceptance gate.

Machine-readable lexical measurements: [rerank_lexical_smoke.json](rerank_lexical_smoke.json).
