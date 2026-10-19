# Extended frozen experiment

Experiment: `fresh_compact`. Model: `ktrf-diagnostic-qwen27b-bf16`. Status: `COMPLETE`.

Cases: 128; parent documents: 128. Counts: `{'request_count': 384, 'record_count': 384, 'received_count': 384, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| compact | 41/64 | 44/64 | 0 | 0 | 0 | 98203 |
| full | 42/64 | 45/64 | 0 | 0 | 0 | 106738 |
| none | 43/64 | 43/64 | 0 | 0 | 0 | 77917 |

Paired comparisons:

```json
{
  "none_to_full": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.0078125,
    "identical_prompt_pairs": 86,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.0078125
  },
  "none_to_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.0078125,
    "identical_prompt_pairs": 86,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.015625
  },
  "full_to_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.015625,
    "identical_prompt_pairs": 86,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.015625
  }
}
```

Workload aggregate; exposed diagnostics and fresh families must be assessed separately.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `fresh_context_holdout`. Cases: 128; families: 128.

| Condition | Positive exact | No-answer null | Prompt tokens |
|---|---:|---:|---:|
| compact | 41/64 | 44/64 | 98203 |
| full | 42/64 | 45/64 | 106738 |
| none | 43/64 | 43/64 | 77917 |

Split paired comparisons:

```json
{
  "none_to_full": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.0078125,
    "identical_prompt_pairs": 86,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.0078125
  },
  "none_to_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.0078125,
    "identical_prompt_pairs": 86,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.015625
  },
  "full_to_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.015625,
    "identical_prompt_pairs": 86,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.015625
  }
}
```

- Follow-on design is adaptive to prior results; the reused factorial sample is not independent confirmation.
- Fresh contexts exclude all prior transfer contexts and supplied corpus exposures using declared exact and near overlap checks.
- Fresh selection precedes retrieval and resolver calls; no retrieval-hit, pack-injection or output filtering is used.
- Context hashes are not verified original article IDs; semantic and model-pretraining overlap remain possible.
- Full and compact packs share essential definitions, observed surfaces, candidates and semantic caveats; metadata verbosity differs.
- Compact omits executable IDs; this diagnostic concerns explanatory QA and grants no execution authority.
- One generation per condition with normalized EM is a diagnostic, not an official KLUE leaderboard score.
- No equal total token cap is claimed: measured full chat templates must fit the 8192 context with 128 output tokens reserved.
- Fresh arms share fixed BM25 source windows; full and compact use the same production QA policy only when should_inject.
- The no-pack fresh arm uses the evidence policy; comparing it to injected arms includes the production policy effect.
