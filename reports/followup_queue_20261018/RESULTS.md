# KTRF followup queue

Status: **COMPLETE**, exit code `0`.

CPU preparation and AI blind-document evaluation completed before GPU generation.

| Stage | Status | Received/planned |
|---|---|---:|
| [retrieval_gemma12b](retrieval_gemma12b/RESULTS.md) | COMPLETE | 512/512 |
| [stability_gemma12b](stability_gemma12b/RESULTS.md) | COMPLETE | 1536/1536 |
| [retrieval_qwen27b](retrieval_qwen27b/RESULTS.md) | COMPLETE | 512/512 |
| [stability_qwen27b](stability_qwen27b/RESULTS.md) | COMPLETE | 1536/1536 |

## Limitations

- Blind document gold is AI authored and adjudicated; no human verification or deployment guarantee.
- Oracle uses gold and is diagnostic only.
- Stability uses previously inspected questions; repeats are not independent samples.
- Model family and size change together; timing on a shared host is descriptive.
