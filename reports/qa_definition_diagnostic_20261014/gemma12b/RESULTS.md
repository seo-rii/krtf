# Frozen QA definition diagnostic

Model: `ktrf-production-gemma4-12b-bf16`.

Original exact scores and sealed artifacts remain unchanged. This diagnostic credits only the complete definition with whitespace, one Korean copula, and one terminal period changed. Additional claims and paraphrases receive no automatic credit.

| Condition | Planned | Strict exact correct | Diagnostic credited | Added matches | Unassessed |
|---|---:|---:|---:|---:|---:|
| full__full | 32 | 15 | 15 | 0 | 5 |
| full__none | 32 | 16 | 16 | 0 | 0 |
| full__retrieved | 32 | 14 | 14 | 0 | 2 |
| ktrf__full | 32 | 31 | 31 | 0 | 0 |
| ktrf__none | 32 | 16 | 16 | 0 | 0 |
| ktrf__retrieved | 32 | 22 | 22 | 0 | 0 |
| none__full | 32 | 9 | 9 | 0 | 0 |
| none__none | 32 | 16 | 16 | 0 | 0 |
| none__retrieved | 32 | 7 | 7 | 0 | 0 |
| retrieved__full | 32 | 15 | 15 | 0 | 10 |
| retrieved__none | 32 | 9 | 9 | 0 | 9 |
| retrieved__retrieved | 32 | 14 | 14 | 0 | 8 |

Unassessed items remain failures until reviewed. Their complete raw answers, expected definitions and reasons are preserved in `diagnostic.json` under `review_queue`.

Limitations:

- This bounded deterministic normalization is not a general semantic accuracy estimate.
- Paraphrases, additional assertions, contradictions and multiple candidate definitions need independent review.
- Missing or malformed responses are unassessed failures, never correct abstentions.
- Original AI-authored synthetic gold and information-removal limitations still apply.
