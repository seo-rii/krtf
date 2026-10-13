# Production grounding queue

Status: **COMPLETE**. Exit code: `0`.

All stages use separate stateless QA and automation requests with the actual production profiles.

| Stage | Status | Received / planned | Malformed |
|---|---|---:|---:|
| [synthetic_gemma12b](synthetic_gemma12b/RESULTS.md) | COMPLETE | 874/874 | 0 |
| [synthetic_qwen27b](synthetic_qwen27b/RESULTS.md) | COMPLETE | 874/874 | 3 |
| [real_gemma12b](real_gemma12b/RESULTS.md) | COMPLETE | 120/120 | 0 |
| [real_qwen27b](real_qwen27b/RESULTS.md) | COMPLETE | 120/120 | 0 |

[synthetic_comparison.md](synthetic_comparison.md)
[real_comparison.md](real_comparison.md)

- Real-document gold is AI annotated, not human verified.
- Synthetic and stratified real-sentence scores are separate; no deployment risk bound.
- Gemma12B versus Qwen27B changes model family as well as size.
- Failures and missing runs remain failures, never inferred successes.
