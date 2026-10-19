# Extended frozen experiment

Experiment: `source_pack_factorial`. Model: `ktrf-diagnostic-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 128; parent documents: 128. Counts: `{'request_count': 768, 'record_count': 768, 'received_count': 768, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| full_compact | 39/64 | 43/64 | 0 | 0 | 0 | 139613 |
| full_full | 39/64 | 44/64 | 0 | 0 | 0 | 145904 |
| full_none | 39/64 | 43/64 | 0 | 0 | 0 | 135586 |
| shrunken_compact | 33/64 | 44/64 | 0 | 0 | 0 | 131456 |
| shrunken_full | 33/64 | 44/64 | 0 | 0 | 0 | 137747 |
| shrunken_none | 33/64 | 44/64 | 0 | 0 | 0 | 127429 |

Paired comparisons:

```json
{
  "full_none_to_full_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "full_none_to_full_full": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0078125,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.0
  },
  "shrunken_none_to_shrunken_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "shrunken_none_to_shrunken_full": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "full_full_to_full_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 1,
    "mean_correctness_delta_all_planned": -0.0078125,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0078125
  },
  "shrunken_full_to_shrunken_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "full_none_to_shrunken_none": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 6,
    "mean_correctness_delta_all_planned": -0.0390625,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.046875
  },
  "full_compact_to_shrunken_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 6,
    "mean_correctness_delta_all_planned": -0.0390625,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.046875
  },
  "full_full_to_shrunken_full": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 6,
    "mean_correctness_delta_all_planned": -0.046875,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.046875
  }
}
```

Workload aggregate; exposed diagnostics and fresh families must be assessed separately.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `adaptive_reused`. Cases: 128; families: 128.

| Condition | Positive exact | No-answer null | Prompt tokens |
|---|---:|---:|---:|
| full_compact | 39/64 | 43/64 | 139613 |
| full_full | 39/64 | 44/64 | 145904 |
| full_none | 39/64 | 43/64 | 135586 |
| shrunken_compact | 33/64 | 44/64 | 131456 |
| shrunken_full | 33/64 | 44/64 | 137747 |
| shrunken_none | 33/64 | 44/64 | 127429 |

Split paired comparisons:

```json
{
  "full_none_to_full_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "full_none_to_full_full": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0078125,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.0
  },
  "shrunken_none_to_shrunken_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "shrunken_none_to_shrunken_full": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "full_full_to_full_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 1,
    "mean_correctness_delta_all_planned": -0.0078125,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0078125
  },
  "shrunken_full_to_shrunken_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "full_none_to_shrunken_none": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 6,
    "mean_correctness_delta_all_planned": -0.0390625,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.046875
  },
  "full_compact_to_shrunken_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 6,
    "mean_correctness_delta_all_planned": -0.0390625,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.046875
  },
  "full_full_to_shrunken_full": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 6,
    "mean_correctness_delta_all_planned": -0.046875,
    "identical_prompt_pairs": 99,
    "no_independence_claim_for_repeats": true,
    "families": 128,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.046875
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
- Full source uses prior cap1536_bm25 spans; shrunken source uses prior cap1024_bm25_pack spans without reranking.
- Every factorial arm receives the same evidence plus QA context policy, including no-pack and ungrounded cases.
- All factorial packs are computed from full source; a shrunken-source arm may retain terminology from omitted source.
