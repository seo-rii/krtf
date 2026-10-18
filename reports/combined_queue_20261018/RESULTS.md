# KTRF combined BM25, pack and JSON queue

Status: **COMPLETE**, exit code `0`.

Frozen unit tests and actual-tokenizer preparation completed before GPU generation.

| Stage | Status | Received/planned |
|---|---|---:|
| [combined_gemma12b](combined_gemma12b/RESULTS.md) | COMPLETE | 1536/1536 |
| [combined_qwen27b](combined_qwen27b/RESULTS.md) | COMPLETE | 1536/1536 |

## Limitations

- Previously inspected frozen retrieval questions are reused for this adaptive combined followup; no independent holdout claim.
- Repeats are descriptive measurements and do not increase the number of independent questions.
- Search is within known source articles; corpus-level document retrieval is not evaluated.
- The KTRF pack and its policy form one intervention; pack source matches each retrieval arm.
- Common source-token caps do not imply equal actual prompt-token cost.
- Model family and size change together; timing on a shared host is descriptive.
