# KTRF five extended experiments

Status: **COMPLETE**, exit code `0`.

Frozen unit tests and actual-tokenizer preparation completed before GPU generation.

| Stage | Status | Received/planned |
|---|---|---:|
| [transfer_gemma12b](transfer_gemma12b/RESULTS.md) | COMPLETE | 1024/1024 |
| [budget_gemma12b](budget_gemma12b/RESULTS.md) | COMPLETE | 512/512 |
| [corpus_gemma12b](corpus_gemma12b/RESULTS.md) | COMPLETE | 512/512 |
| [pack_gemma12b](pack_gemma12b/RESULTS.md) | COMPLETE | 640/640 |
| [semantic_safety_gemma12b](semantic_safety_gemma12b/RESULTS.md) | COMPLETE | 96/96 |
| [transfer_qwen27b](transfer_qwen27b/RESULTS.md) | COMPLETE | 1024/1024 |
| [budget_qwen27b](budget_qwen27b/RESULTS.md) | COMPLETE | 512/512 |
| [corpus_qwen27b](corpus_qwen27b/RESULTS.md) | COMPLETE | 512/512 |
| [pack_qwen27b](pack_qwen27b/RESULTS.md) | COMPLETE | 640/640 |
| [semantic_safety_qwen27b](semantic_safety_qwen27b/RESULTS.md) | COMPLETE | 96/96 |

## Limitations

- The four QA experiments share a frozen KLUE-MRC sample; nested subsets are not independent replications.
- Overlap filtering covers declared sources only and cannot establish absence of model pretraining contamination.
- Corpus retrieval uses a fixed 512-document corpus and positive questions only; article-specific negatives do not establish corpus-wide absence.
- Budget comparisons share total prompt caps, not identical consumed token counts.
- Semantic safety gold is AI authored and reviewed; it is not independently human verified or a deployment error-rate estimate.
- Model family and size change together; shared-host timing is descriptive. No thresholds are tuned on these results.
