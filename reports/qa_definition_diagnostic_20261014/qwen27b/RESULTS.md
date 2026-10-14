# Frozen QA definition diagnostic

Model: `ktrf-production-qwen3.5-27b-bf16`.

Original exact scores and sealed artifacts remain unchanged. This diagnostic credits only the complete definition with whitespace, one Korean copula, and one terminal period changed. Additional claims and paraphrases receive no automatic credit.

| Condition | Planned | Strict exact correct | Diagnostic credited | Added matches | Unassessed |
|---|---:|---:|---:|---:|---:|
| full__full | 32 | 16 | 17 | 1 | 2 |
| full__none | 32 | 16 | 16 | 0 | 0 |
| full__retrieved | 32 | 15 | 15 | 0 | 1 |
| ktrf__full | 32 | 28 | 28 | 0 | 0 |
| ktrf__none | 32 | 16 | 16 | 0 | 0 |
| ktrf__retrieved | 32 | 22 | 22 | 0 | 0 |
| none__full | 32 | 13 | 13 | 0 | 0 |
| none__none | 32 | 16 | 16 | 0 | 0 |
| none__retrieved | 32 | 11 | 11 | 0 | 0 |
| retrieved__full | 32 | 13 | 16 | 3 | 9 |
| retrieved__none | 32 | 13 | 14 | 1 | 2 |
| retrieved__retrieved | 32 | 13 | 14 | 1 | 9 |

Unassessed items remain failures until reviewed. Their complete raw answers, expected definitions and reasons are preserved in `diagnostic.json` under `review_queue`.

Limitations:

- This bounded deterministic normalization is not a general semantic accuracy estimate.
- Paraphrases, additional assertions, contradictions and multiple candidate definitions need independent review.
- Missing or malformed responses are unassessed failures, never correct abstentions.
- Original AI-authored synthetic gold and information-removal limitations still apply.
