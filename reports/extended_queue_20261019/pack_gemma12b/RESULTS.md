# Extended frozen experiment

Experiment: `pack`. Model: `ktrf-extended-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 128; parent documents: 128. Counts: `{'request_count': 640, 'record_count': 640, 'received_count': 640, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| json_conservative | 42/64 | 45/64 | 0 | 0 | 0 | 108604 |
| json_neutral | 43/64 | 45/64 | 0 | 0 | 0 | 97932 |
| none | 44/64 | 44/64 | 0 | 0 | 0 | 88482 |
| text_conservative | 42/64 | 44/64 | 0 | 0 | 0 | 102343 |
| text_neutral | 43/64 | 45/64 | 0 | 0 | 0 | 91671 |

Paired comparisons:

```json
{
  "none_to_text_neutral": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true
  },
  "none_to_json_neutral": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true
  },
  "text_neutral_to_json_neutral": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true
  },
  "text_conservative_to_json_conservative": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0078125,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true
  },
  "text_neutral_to_text_conservative": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.015625,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true
  },
  "json_neutral_to_json_conservative": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 1,
    "mean_correctness_delta_all_planned": -0.0078125,
    "identical_prompt_pairs": 99,
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
