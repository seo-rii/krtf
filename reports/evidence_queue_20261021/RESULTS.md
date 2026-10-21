# KTRF matched candidates and server-bound evidence control

Status: **COMPLETE**, exit code `0`.

Frozen unit tests and actual-tokenizer preparation completed before GPU generation.

| Stage | Status | Received/planned |
|---|---|---:|
| [evidence_control_gemma12b](evidence_control_gemma12b/RESULTS.md) | COMPLETE | 256/256 |
| [evidence_control_qwen27b](evidence_control_qwen27b/RESULTS.md) | COMPLETE | 256/256 |

## Limitations

- All 64 source cases are previously exposed development documents from 8 AI-authored families; this is an adaptive diagnostic, not a new holdout.
- All arms share actual resolver candidates, reference facts, and the unchanged production occurrence authorization guard.
- Ambiguous candidates may be proposed but are never authorized by model or evidence scores alone.
- Evidence IDs bind source spans on the server; they establish literal identity, not semantic entailment.
- Model family and size both change; shared-host latency is descriptive.
- No actual workplace documents or independent human annotations have been supplied.
