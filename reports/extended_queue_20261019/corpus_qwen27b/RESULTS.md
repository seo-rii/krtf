# Extended frozen experiment

Experiment: `corpus`. Model: `ktrf-extended-qwen27b-bf16`. Status: `COMPLETE`.

Cases: 128; parent documents: 128. Counts: `{'request_count': 512, 'record_count': 512, 'received_count': 512, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| bm25 | 88/128 | 0/0 | 0 | 0 | 0 | 184852 |
| bm25_pack | 87/128 | 0/0 | 0 | 0 | 0 | 213677 |
| lexical | 84/128 | 0/0 | 0 | 0 | 0 | 178297 |
| lexical_pack | 86/128 | 0/0 | 0 | 0 | 0 | 210569 |

Paired comparisons:

```json
{
  "lexical_to_lexical_pack": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.015625,
    "identical_prompt_pairs": 86,
    "no_independence_claim_for_repeats": true
  },
  "bm25_to_bm25_pack": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.0078125,
    "identical_prompt_pairs": 91,
    "no_independence_claim_for_repeats": true
  },
  "lexical_to_bm25": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 7,
    "harmful": 3,
    "mean_correctness_delta_all_planned": 0.03125,
    "identical_prompt_pairs": 6,
    "no_independence_claim_for_repeats": true
  },
  "lexical_pack_to_bm25_pack": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 5,
    "mean_correctness_delta_all_planned": 0.0078125,
    "identical_prompt_pairs": 6,
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
