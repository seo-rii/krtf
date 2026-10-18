# KTRF fresh-document combined BM25, pack and JSON queue

Status: **COMPLETE**, exit code `0`.

Frozen unit tests and actual-tokenizer preparation completed before GPU generation.

| Stage | Status | Received/planned |
|---|---|---:|
| [fresh_gemma12b](fresh_gemma12b/RESULTS.md) | COMPLETE | 432/432 |
| [fresh_qwen27b](fresh_qwen27b/RESULTS.md) | COMPLETE | 432/432 |

## Limitations

- Fresh article split excludes declared prior articles by identity and content hash; this is a same-corpus holdout, not external independent validation.
- Exact article exclusion does not establish absence of near-duplicate documents or pretrained-model contamination.
- Earlier results informed the methods; this sample was frozen before its generation outputs.
- Repeats are descriptive measurements and do not increase the number of independent questions.
- Search is within known source articles; corpus-level document retrieval is not evaluated.
- The KTRF pack and its policy form one intervention; pack source matches each retrieval arm.
- Common source-token caps do not imply equal actual prompt-token cost.
- Model family and size change together; timing on a shared host is descriptive.
