# Definition_control grounding queue

Status: **COMPLETE**. Exit code: `0`.

Each model runs all six matched source/definition controls with separate QA and routing calls. Definition boundaries and source/gold are fixed. Heuristic authorization is disabled by default.

| Stage | Status | Received / planned | Malformed |
|---|---|---:|---:|
| [documents_gemma12b](documents_gemma12b/RESULTS.md) | COMPLETE | 768/768 | 0 |
| [documents_qwen27b](documents_qwen27b/RESULTS.md) | COMPLETE | 768/768 | 0 |

[documents_comparison.md](documents_comparison.md)

- Six matched definition-format/candidate/authorization controls on short AI-authored documents.
- Exact QA, literal-normalized diagnostics and unassessed review cases are distinct.
- Context definition authorization is an opt-in experimental heuristic, not a risk certificate.
- Both models infer all new arms; historical outputs are not relabeled.
- System contracts differ between proposal and executable arms; no deployment risk guarantee.
