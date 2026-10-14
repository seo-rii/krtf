# Baseline grounding queue

Status: **COMPLETE**. Exit code: `0`.

All stages run frozen baseline B with separate stateless QA and execution requests. The KTRF execution guard is not applied to baseline B. Each stage compares against referenced sealed production C outputs; C GPU inference is not rerun.

| Stage | Status | Received / planned | Malformed |
|---|---|---:|---:|
| [synthetic_gemma12b](synthetic_gemma12b/RESULTS.md) | COMPLETE | 874/874 | 1 |
| [synthetic_qwen27b](synthetic_qwen27b/RESULTS.md) | COMPLETE | 874/874 | 5 |
| [real_gemma12b](real_gemma12b/RESULTS.md) | COMPLETE | 120/120 | 0 |
| [real_qwen27b](real_qwen27b/RESULTS.md) | COMPLETE | 120/120 | 1 |

[synthetic_comparison.md](synthetic_comparison.md)
[real_comparison.md](real_comparison.md)

- Real-document gold is AI annotated, not human verified.
- Synthetic and stratified real-sentence scores are separate; no deployment risk bound.
- Gemma12B versus Qwen27B changes model family as well as size.
- Failures and missing runs remain failures, never inferred successes.
- Baseline B uses its own retrieval and execution contract; the KTRF execution guard is not applied.
- Each baseline stage compares with referenced sealed production C outputs; C GPU inference is not rerun.
