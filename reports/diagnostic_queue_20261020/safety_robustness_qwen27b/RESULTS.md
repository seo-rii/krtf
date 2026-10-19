# Extended frozen experiment

Experiment: `safety_robustness`. Model: `ktrf-diagnostic-qwen27b-bf16`. Status: `COMPLETE`.

Cases: 160; parent documents: 160. Counts: `{'request_count': 640, 'record_count': 640, 'received_count': 640, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Accepted correct ID | Accepted wrong ID | Rejected wrong ID | Correct abstention | Over-abstention | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pack_first_baseline | 77 | 1 | 0 | 79 | 3 | 0 | 0 | 0 | 71020 |
| pack_last_baseline | 77 | 0 | 0 | 80 | 3 | 0 | 0 | 0 | 71020 |
| pack_first_semantic_check | 77 | 0 | 0 | 80 | 3 | 0 | 0 | 0 | 88940 |
| pack_last_semantic_check | 77 | 1 | 0 | 79 | 3 | 0 | 0 | 0 | 88940 |

Paired comparisons:

```json
{
  "pack_first_baseline_to_pack_last_baseline": {
    "planned": 160,
    "questions": 160,
    "comparable": 160,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.00625,
    "identical_prompt_pairs": 27,
    "no_independence_claim_for_repeats": true,
    "families": 40,
    "helpful_rate_among_comparable": 0.00625,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.00625,
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
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.00625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 40,
    "helpful_rate_among_comparable": 0.00625,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.00625,
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
    "helpful": 0,
    "harmful": 1,
    "mean_correctness_delta_all_planned": -0.00625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 40,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.00625,
    "accepted_wrong_id_increased": 1,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.00625,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
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
    "helpful": 0,
    "harmful": 1,
    "mean_correctness_delta_all_planned": -0.00625,
    "identical_prompt_pairs": 27,
    "no_independence_claim_for_repeats": true,
    "families": 40,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.00625,
    "accepted_wrong_id_increased": 1,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.00625,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
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
| pack_first_baseline | 46 | 0 | 48 | 2 | 41705 |
| pack_last_baseline | 46 | 0 | 48 | 2 | 41705 |
| pack_first_semantic_check | 46 | 0 | 48 | 2 | 52457 |
| pack_last_semantic_check | 46 | 1 | 47 | 2 | 52457 |

Split paired comparisons:

```json
{
  "pack_first_baseline_to_pack_last_baseline": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 17,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
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
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
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
    "helpful": 0,
    "harmful": 1,
    "mean_correctness_delta_all_planned": -0.010416666666666666,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.010416666666666666,
    "accepted_wrong_id_increased": 1,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.010416666666666666,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
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
    "helpful": 0,
    "harmful": 1,
    "mean_correctness_delta_all_planned": -0.010416666666666666,
    "identical_prompt_pairs": 17,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.010416666666666666,
    "accepted_wrong_id_increased": 1,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.010416666666666666,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
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
| pack_first_baseline | 31 | 1 | 31 | 1 | 29315 |
| pack_last_baseline | 31 | 0 | 32 | 1 | 29315 |
| pack_first_semantic_check | 31 | 0 | 32 | 1 | 36483 |
| pack_last_semantic_check | 31 | 0 | 32 | 1 | 36483 |

Split paired comparisons:

```json
{
  "pack_first_baseline_to_pack_last_baseline": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.015625,
    "identical_prompt_pairs": 10,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.015625,
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
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.015625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.015625,
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
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
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
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 10,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
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
