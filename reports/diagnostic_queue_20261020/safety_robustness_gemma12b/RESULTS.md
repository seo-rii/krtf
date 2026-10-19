# Extended frozen experiment

Experiment: `safety_robustness`. Model: `ktrf-diagnostic-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 160; parent documents: 160. Counts: `{'request_count': 640, 'record_count': 640, 'received_count': 640, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Accepted correct ID | Accepted wrong ID | Rejected wrong ID | Correct abstention | Over-abstention | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pack_first_baseline | 77 | 21 | 8 | 51 | 3 | 0 | 0 | 0 | 76812 |
| pack_last_baseline | 77 | 13 | 0 | 67 | 3 | 0 | 0 | 0 | 76812 |
| pack_first_semantic_check | 77 | 4 | 0 | 76 | 3 | 0 | 0 | 0 | 96652 |
| pack_last_semantic_check | 75 | 1 | 2 | 79 | 3 | 0 | 0 | 0 | 96652 |

Paired comparisons:

```json
{
  "pack_first_baseline_to_pack_last_baseline": {
    "planned": 160,
    "questions": 160,
    "comparable": 160,
    "incomplete_or_malformed": 0,
    "helpful": 19,
    "harmful": 3,
    "mean_correctness_delta_all_planned": 0.1,
    "identical_prompt_pairs": 27,
    "no_independence_claim_for_repeats": true,
    "families": 40,
    "helpful_rate_among_comparable": 0.11875,
    "harmful_rate_among_comparable": 0.01875,
    "accepted_wrong_id_increased": 3,
    "accepted_wrong_id_decreased": 11,
    "accepted_wrong_id_increase_rate_among_comparable": 0.01875,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.06875,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "pack_first_baseline_to_pack_first_semantic_check": {
    "planned": 160,
    "questions": 160,
    "comparable": 160,
    "incomplete_or_malformed": 0,
    "helpful": 25,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.15625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 40,
    "helpful_rate_among_comparable": 0.15625,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 17,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.10625,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "pack_last_baseline_to_pack_last_semantic_check": {
    "planned": 160,
    "questions": 160,
    "comparable": 160,
    "incomplete_or_malformed": 0,
    "helpful": 12,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.0625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 40,
    "helpful_rate_among_comparable": 0.075,
    "harmful_rate_among_comparable": 0.0125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 12,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.075,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "pack_first_semantic_check_to_pack_last_semantic_check": {
    "planned": 160,
    "questions": 160,
    "comparable": 160,
    "incomplete_or_malformed": 0,
    "helpful": 4,
    "harmful": 3,
    "mean_correctness_delta_all_planned": 0.00625,
    "identical_prompt_pairs": 27,
    "no_independence_claim_for_repeats": true,
    "families": 40,
    "helpful_rate_among_comparable": 0.025,
    "harmful_rate_among_comparable": 0.01875,
    "accepted_wrong_id_increased": 1,
    "accepted_wrong_id_decreased": 4,
    "accepted_wrong_id_increase_rate_among_comparable": 0.00625,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.025,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  }
}
```

Workload aggregate; exposed diagnostics and fresh families must be assessed separately.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `exposed_diagnostic`. Cases: 96; families: 24.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| pack_first_baseline | 46 | 10 | 34 | 2 | 45258 |
| pack_last_baseline | 46 | 6 | 42 | 2 | 45258 |
| pack_first_semantic_check | 46 | 3 | 45 | 2 | 57162 |
| pack_last_semantic_check | 46 | 1 | 47 | 2 | 57162 |

Split paired comparisons:

```json
{
  "pack_first_baseline_to_pack_last_baseline": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 10,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.08333333333333333,
    "identical_prompt_pairs": 17,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.10416666666666667,
    "harmful_rate_among_comparable": 0.020833333333333332,
    "accepted_wrong_id_increased": 2,
    "accepted_wrong_id_decreased": 6,
    "accepted_wrong_id_increase_rate_among_comparable": 0.020833333333333332,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0625,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "pack_first_baseline_to_pack_first_semantic_check": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 11,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.11458333333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.11458333333333333,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 7,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.07291666666666667,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "pack_last_baseline_to_pack_last_semantic_check": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 5,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.052083333333333336,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.052083333333333336,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 5,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.052083333333333336,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "pack_first_semantic_check_to_pack_last_semantic_check": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.020833333333333332,
    "identical_prompt_pairs": 17,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.03125,
    "harmful_rate_among_comparable": 0.010416666666666666,
    "accepted_wrong_id_increased": 1,
    "accepted_wrong_id_decreased": 3,
    "accepted_wrong_id_increase_rate_among_comparable": 0.010416666666666666,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.03125,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  }
}
```

Evaluation split: `fresh_family`. Cases: 64; families: 16.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| pack_first_baseline | 31 | 11 | 17 | 1 | 31554 |
| pack_last_baseline | 31 | 7 | 25 | 1 | 31554 |
| pack_first_semantic_check | 31 | 1 | 31 | 1 | 39490 |
| pack_last_semantic_check | 29 | 0 | 32 | 1 | 39490 |

Split paired comparisons:

```json
{
  "pack_first_baseline_to_pack_last_baseline": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 9,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.125,
    "identical_prompt_pairs": 10,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.140625,
    "harmful_rate_among_comparable": 0.015625,
    "accepted_wrong_id_increased": 1,
    "accepted_wrong_id_decreased": 5,
    "accepted_wrong_id_increase_rate_among_comparable": 0.015625,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.078125,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "pack_first_baseline_to_pack_first_semantic_check": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 14,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.21875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.21875,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 10,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.15625,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "pack_last_baseline_to_pack_last_semantic_check": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 7,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.078125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.109375,
    "harmful_rate_among_comparable": 0.03125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 7,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.109375,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "pack_first_semantic_check_to_pack_last_semantic_check": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.015625,
    "identical_prompt_pairs": 10,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.03125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.015625,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  }
}
```

- AI-authored diagnostic families, not a random deployment sample or human-verified gold.
- All places, countries, organizations and histories are fictional.
- The 64 fresh cases share 16 families and closely related templates; freshness is entity-family separation, not independent natural-language distribution.
- Previously evaluated 96 cases are exposed diagnostics and reported separately from 64 fresh-family cases.
- All 160 cases are retained regardless of resolver or previous model outcomes; no selection by failures.
- Pack placement moves only the same XML block before or after the identical user task; the production system policy is unchanged.
- Semantic-check wording is identical for every case and condition that enables it; no gold or case rationale reaches the prompt.
- The exposed split preserves its previous sealed packs; fresh packs use the current frozen revision.
- No production resolver or execution-guard policy changes are evaluated.
- The 6000-token evaluation pack allowance differs from the default 800-token product allowance.
