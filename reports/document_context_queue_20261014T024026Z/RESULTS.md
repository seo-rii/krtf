# Document_context grounding queue

Status: **COMPLETE**. Exit code: `0`.

Each model runs all four knowledge modes and three source-document modes, with separate QA and routing calls. Full documents are preserved; retrieved paragraph windows retain offsets and hashes. No prior inference is reused.

| Stage | Status | Received / planned | Malformed |
|---|---|---:|---:|
| [documents_gemma12b](documents_gemma12b/RESULTS.md) | COMPLETE | 768/768 | 38 |
| [documents_qwen27b](documents_qwen27b/RESULTS.md) | COMPLETE | 768/768 | 0 |

[documents_comparison.md](documents_comparison.md)

- Complete source and knowledge documents are newly AI authored, not reconstructed news articles.
- Twelve matched knowledge/source conditions measure evidence availability as well as pipeline behavior.
- KTRF policies and guard apply only to the KTRF arm; semantic scores precede execution validation.
- Both models run every new condition; no prior production responses are relabeled.
- Model family and size both change; synthetic scores do not establish deployment risk.
