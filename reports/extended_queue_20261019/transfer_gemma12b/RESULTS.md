# Extended frozen experiment

Experiment: `transfer`. Model: `ktrf-extended-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 256; parent documents: 256. Counts: `{'request_count': 1024, 'record_count': 1024, 'received_count': 1024, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| bm25 | 89/128 | 85/128 | 0 | 0 | 0 | 176385 |
| bm25_pack | 86/128 | 86/128 | 0 | 0 | 0 | 219344 |
| lexical | 89/128 | 88/128 | 0 | 0 | 0 | 170114 |
| lexical_pack | 86/128 | 89/128 | 0 | 0 | 0 | 212110 |

Paired comparisons:

```json
{
  "lexical_to_lexical_pack": {
    "planned": 256,
    "questions": 256,
    "comparable": 256,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 3,
    "mean_correctness_delta_all_planned": -0.0078125,
    "identical_prompt_pairs": 197,
    "no_independence_claim_for_repeats": true
  },
  "bm25_to_bm25_pack": {
    "planned": 256,
    "questions": 256,
    "comparable": 256,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 3,
    "mean_correctness_delta_all_planned": -0.0078125,
    "identical_prompt_pairs": 197,
    "no_independence_claim_for_repeats": true
  },
  "lexical_to_bm25": {
    "planned": 256,
    "questions": 256,
    "comparable": 256,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 6,
    "mean_correctness_delta_all_planned": -0.01171875,
    "identical_prompt_pairs": 237,
    "no_independence_claim_for_repeats": true
  },
  "lexical_pack_to_bm25_pack": {
    "planned": 256,
    "questions": 256,
    "comparable": 256,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 6,
    "mean_correctness_delta_all_planned": -0.01171875,
    "identical_prompt_pairs": 237,
    "no_independence_claim_for_repeats": true
  }
}
```

- Stratified contexts do not represent the original KLUE MRC question distribution.
- Absent original article IDs use context hashes; parent contexts are not verified independent original articles.
- Declared prior exact, normalized, sentence and 5-gram overlap is excluded; semantic and pretraining overlap remain possible.
- All tracks reuse nested subsets of one frozen sample and are not independent replication datasets.
- Corpus retrieval uses positive questions only because impossible labels apply only to the original source context.
- The bounded 512-context corpus deliberately contains every positive anchor; it is not open-web retrieval.
- Equal prompt caps measure complete actual chat templates; consumption may differ and no padding is added.
- Budget prefixes are source-only deterministic choices, not gold-centered windows or an optimal knapsack solution.
- Format comparison renders the same minimal fact cards; full production metadata is deliberately absent from both formats.
- Neutral and conservative policies both remain evidence-only; no arm grants execution authority.
- No output-based, retrieval-hit-based or pack-injection-based sample filtering is performed.
- All conditions use JSON Schema and one generation; normalized EM is a diagnostic, not an official leaderboard score.
