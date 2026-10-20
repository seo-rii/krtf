# KTRF review-driven QA, relevance and occurrence experiments

Status: **COMPLETE**, exit code `0`.

Frozen unit tests and actual-tokenizer preparation completed before GPU generation.

| Stage | Status | Received/planned |
|---|---|---:|
| [review_abcd_gemma12b](review_abcd_gemma12b/RESULTS.md) | COMPLETE | 1024/1024 |
| [review_policy_gemma12b](review_policy_gemma12b/RESULTS.md) | COMPLETE | 384/384 |
| [review_budget_gemma12b](review_budget_gemma12b/RESULTS.md) | COMPLETE | 384/384 |
| [review_nomiracl_gemma12b](review_nomiracl_gemma12b/RESULTS.md) | COMPLETE | 384/384 |
| [review_routing_gemma12b](review_routing_gemma12b/RESULTS.md) | COMPLETE | 768/768 |
| [review_abcd_qwen27b](review_abcd_qwen27b/RESULTS.md) | COMPLETE | 1024/1024 |
| [review_policy_qwen27b](review_policy_qwen27b/RESULTS.md) | COMPLETE | 384/384 |
| [review_budget_qwen27b](review_budget_qwen27b/RESULTS.md) | COMPLETE | 384/384 |
| [review_nomiracl_qwen27b](review_nomiracl_qwen27b/RESULTS.md) | COMPLETE | 384/384 |
| [review_routing_qwen27b](review_routing_qwen27b/RESULTS.md) | COMPLETE | 768/768 |

## Limitations

- Shared public KLUE contexts across QA/policy/budget/routing tracks and shared authored families are not independent samples.
- Business documents are AI authored; public natural contexts are AI annotated proxies, not private deployment documents or human gold.
- NoMIRACL measures relevance of complete provided passage sets, not answer generation or entity linking; Wikipedia/pretraining overlap remains possible.
- Pipeline selectors differ; matched-facts arms isolate presentation and policy conditionally on the declared common candidate set.
- All new execution calls use strict occurrence-bound identities; historical reanalysis explicitly retains the sealed legacy contract.
- No deployment thresholds are tuned, and synthetic/public proxy observations do not establish operational risk guarantees.
