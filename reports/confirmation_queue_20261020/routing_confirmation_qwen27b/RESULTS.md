# Extended frozen experiment

Experiment: `routing_confirmation`. Model: `ktrf-confirmation-qwen27b-bf16`. Status: `COMPLETE`.

Cases: 192; parent documents: 192. Counts: `{'request_count': 1152, 'record_count': 1152, 'received_count': 1152, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Accepted correct ID | Accepted wrong ID | Rejected wrong ID | Correct abstention | Over-abstention | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| plain_check_full | 96 | 11 | 0 | 85 | 0 | 0 | 0 | 0 | 129388 |
| plain_check_compact | 93 | 5 | 0 | 91 | 3 | 0 | 0 | 0 | 121552 |
| ktrf_check_full | 65 | 0 | 0 | 96 | 28 | 0 | 0 | 0 | 204448 |
| ktrf_check_compact | 65 | 0 | 0 | 96 | 28 | 0 | 0 | 0 | 196522 |
| ktrf_evidence_full | 0 | 0 | 0 | 92 | 28 | 0 | 0 | 0 | 245152 |
| ktrf_evidence_compact | 0 | 0 | 0 | 94 | 28 | 0 | 0 | 0 | 237274 |

Raw semantic selection and occurrence-bound approval are separate; synthetic/public proxy samples do not certify deployment risk.

Request wall time includes local parsing and execution validation; preparation costs are measured separately. Snapshot compilation counts only actual compilations, excluding cached zero-cost entries. Shared-host measurements are descriptive, not service-load SLOs.

| Condition | p50 ms | p95 ms | Input tokens | Output tokens |
|---|---:|---:|---:|---:|
| plain_check_full | 13246.779 | 13969.957 | 129388 | 32408 |
| plain_check_compact | 6454.497 | 7122.98 | 121552 | 15651 |
| ktrf_check_full | 13054.362 | 14127.426 | 204448 | 32018 |
| ktrf_check_compact | 6372.768 | 7176.675 | 196522 | 15261 |
| ktrf_evidence_full | 14882.73 | 28414.9 | 245152 | 47589 |
| ktrf_evidence_compact | 8202.431 | 21323.49 | 237274 | 31327 |

Preparation timings and pipeline diagnostics:

```json
{
  "preparation_timing_ms": {
    "snapshot_compile": {
      "observations": 24,
      "total": 44.14441157132387,
      "min": 1.766077009961009,
      "max": 2.235082909464836,
      "p50": 1.816,
      "p95": 1.887,
      "p99": 2.156
    },
    "first_prepare": {
      "observations": 192,
      "total": 3487.936132121831,
      "min": 9.771812940016389,
      "max": 28.027572901919484,
      "p50": 17.761,
      "p95": 25.049,
      "p99": 27.516
    },
    "warm_prepare": {
      "observations": 192,
      "total": 3318.1756138801575,
      "min": 9.183703921735287,
      "max": 27.13779197074473,
      "p50": 16.871,
      "p95": 24.103,
      "p99": 26.692
    }
  },
  "pipeline_diagnostics": {
    "confirmation": {
      "targets": 128,
      "positives": 64,
      "exact_core_detected": 128,
      "positive_gold_in_candidates": 64
    },
    "development": {
      "targets": 64,
      "positives": 32,
      "exact_core_detected": 64,
      "positive_gold_in_candidates": 32
    }
  }
}
```

Pre-inference terminology-need strata:

```json
{
  "required": {
    "questions": 192,
    "by_variant": {
      "plain_check_full": {
        "planned": 192,
        "questions": 192,
        "positive_planned": 96,
        "no_answer_planned": 96,
        "correct": 181,
        "correct_rate": 0.9427083333333334,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 192,
        "pack_injected_requests": 192,
        "pack_injected_questions": 192,
        "families": 24,
        "accepted_correct_id": 96,
        "accepted_wrong_id": 11,
        "rejected_wrong_id": 0,
        "correct_abstention": 85,
        "over_abstention": 0,
        "rejected_correct_id": 0,
        "attempted_nonnull": 107,
        "guard_valid": 192,
        "semantic_match": 181,
        "accepted_nonnull": 107,
        "accepted_wrong_id_rate": 0.057291666666666664,
        "accepted_wrong_id_rate_among_accepted": 0.102803738317757,
        "accepted_correct_id_rate": 1.0,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.8854166666666666,
        "documents": 192,
        "documents_with_wrong_approval": 11,
        "document_wrong_approval_rate": 0.057291666666666664,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 0,
          "evidence_gate_valid": 0
        },
        "evidence_rejection_reasons": {}
      },
      "plain_check_compact": {
        "planned": 192,
        "questions": 192,
        "positive_planned": 96,
        "no_answer_planned": 96,
        "correct": 184,
        "correct_rate": 0.9583333333333334,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 192,
        "pack_injected_requests": 192,
        "pack_injected_questions": 192,
        "families": 24,
        "accepted_correct_id": 93,
        "accepted_wrong_id": 5,
        "rejected_wrong_id": 0,
        "correct_abstention": 91,
        "over_abstention": 3,
        "rejected_correct_id": 0,
        "attempted_nonnull": 98,
        "guard_valid": 192,
        "semantic_match": 184,
        "accepted_nonnull": 98,
        "accepted_wrong_id_rate": 0.026041666666666668,
        "accepted_wrong_id_rate_among_accepted": 0.05102040816326531,
        "accepted_correct_id_rate": 0.96875,
        "over_abstention_rate": 0.03125,
        "correct_abstention_rate": 0.9479166666666666,
        "documents": 192,
        "documents_with_wrong_approval": 5,
        "document_wrong_approval_rate": 0.026041666666666668,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 0,
          "evidence_gate_valid": 0
        },
        "evidence_rejection_reasons": {}
      },
      "ktrf_check_full": {
        "planned": 192,
        "questions": 192,
        "positive_planned": 96,
        "no_answer_planned": 96,
        "correct": 161,
        "correct_rate": 0.8385416666666666,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 192,
        "pack_injected_requests": 134,
        "pack_injected_questions": 134,
        "families": 24,
        "accepted_correct_id": 65,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 96,
        "over_abstention": 28,
        "rejected_correct_id": 3,
        "attempted_nonnull": 68,
        "guard_valid": 189,
        "semantic_match": 164,
        "accepted_nonnull": 65,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.6770833333333334,
        "over_abstention_rate": 0.2916666666666667,
        "correct_abstention_rate": 1.0,
        "documents": 192,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 3,
          "evidence_gate_valid": 0
        },
        "evidence_rejection_reasons": {}
      },
      "ktrf_check_compact": {
        "planned": 192,
        "questions": 192,
        "positive_planned": 96,
        "no_answer_planned": 96,
        "correct": 161,
        "correct_rate": 0.8385416666666666,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 192,
        "pack_injected_requests": 134,
        "pack_injected_questions": 134,
        "families": 24,
        "accepted_correct_id": 65,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 96,
        "over_abstention": 28,
        "rejected_correct_id": 3,
        "attempted_nonnull": 68,
        "guard_valid": 189,
        "semantic_match": 164,
        "accepted_nonnull": 65,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.6770833333333334,
        "over_abstention_rate": 0.2916666666666667,
        "correct_abstention_rate": 1.0,
        "documents": 192,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 3,
          "evidence_gate_valid": 0
        },
        "evidence_rejection_reasons": {}
      },
      "ktrf_evidence_full": {
        "planned": 192,
        "questions": 192,
        "positive_planned": 96,
        "no_answer_planned": 96,
        "correct": 92,
        "correct_rate": 0.4791666666666667,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 192,
        "pack_injected_requests": 134,
        "pack_injected_questions": 134,
        "families": 24,
        "accepted_correct_id": 0,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 92,
        "over_abstention": 28,
        "rejected_correct_id": 68,
        "attempted_nonnull": 68,
        "guard_valid": 119,
        "semantic_match": 164,
        "accepted_nonnull": 0,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": null,
        "accepted_correct_id_rate": 0.0,
        "over_abstention_rate": 0.2916666666666667,
        "correct_abstention_rate": 0.9583333333333334,
        "documents": 192,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 3,
          "evidence_gate_valid": 73
        },
        "evidence_rejection_reasons": {
          "source_quote_mismatch": 67,
          "attribute_source_span_mismatch": 259,
          "abstention_assertion_inconsistent": 5,
          "evidence_does_not_contain_requested_occurrence": 8,
          "evidence_has_other_surface_occurrence": 8
        }
      },
      "ktrf_evidence_compact": {
        "planned": 192,
        "questions": 192,
        "positive_planned": 96,
        "no_answer_planned": 96,
        "correct": 94,
        "correct_rate": 0.4895833333333333,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 192,
        "pack_injected_requests": 134,
        "pack_injected_questions": 134,
        "families": 24,
        "accepted_correct_id": 0,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 94,
        "over_abstention": 28,
        "rejected_correct_id": 68,
        "attempted_nonnull": 68,
        "guard_valid": 117,
        "semantic_match": 164,
        "accepted_nonnull": 0,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": null,
        "accepted_correct_id_rate": 0.0,
        "over_abstention_rate": 0.2916666666666667,
        "correct_abstention_rate": 0.9791666666666666,
        "documents": 192,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 3,
          "evidence_gate_valid": 75
        },
        "evidence_rejection_reasons": {
          "source_quote_mismatch": 68,
          "attribute_source_span_mismatch": 255,
          "abstention_assertion_inconsistent": 7,
          "evidence_does_not_contain_requested_occurrence": 2,
          "evidence_has_other_surface_occurrence": 2
        }
      }
    }
  }
}
```


Paired comparisons:

```json
{
  "plain_check_full_to_ktrf_check_full": {
    "planned": 192,
    "questions": 192,
    "comparable": 192,
    "incomplete_or_malformed": 0,
    "helpful": 11,
    "harmful": 31,
    "mean_correctness_delta_all_planned": -0.10416666666666667,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.057291666666666664,
    "harmful_rate_among_comparable": 0.16145833333333334,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 11,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.057291666666666664,
    "over_abstention_increased": 28,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.14583333333333334,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_check_full_to_ktrf_evidence_full": {
    "planned": 192,
    "questions": 192,
    "comparable": 192,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 69,
    "mean_correctness_delta_all_planned": -0.359375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.359375,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "plain_check_compact_to_ktrf_check_compact": {
    "planned": 192,
    "questions": 192,
    "comparable": 192,
    "incomplete_or_malformed": 0,
    "helpful": 8,
    "harmful": 31,
    "mean_correctness_delta_all_planned": -0.11979166666666667,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.041666666666666664,
    "harmful_rate_among_comparable": 0.16145833333333334,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 5,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.026041666666666668,
    "over_abstention_increased": 28,
    "over_abstention_decreased": 3,
    "over_abstention_increase_rate_among_comparable": 0.14583333333333334,
    "over_abstention_decrease_rate_among_comparable": 0.015625
  },
  "ktrf_check_compact_to_ktrf_evidence_compact": {
    "planned": 192,
    "questions": 192,
    "comparable": 192,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 67,
    "mean_correctness_delta_all_planned": -0.3489583333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.3489583333333333,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "plain_check_full_to_plain_check_compact": {
    "planned": 192,
    "questions": 192,
    "comparable": 192,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 3,
    "mean_correctness_delta_all_planned": 0.015625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.03125,
    "harmful_rate_among_comparable": 0.015625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 6,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.03125,
    "over_abstention_increased": 3,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.015625,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_check_full_to_ktrf_check_compact": {
    "planned": 192,
    "questions": 192,
    "comparable": 192,
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
  "ktrf_evidence_full_to_ktrf_evidence_compact": {
    "planned": 192,
    "questions": 192,
    "comparable": 192,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.010416666666666666,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.005208333333333333,
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

Workload aggregate; exposed diagnostics and fresh families must be assessed separately.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `confirmation`. Cases: 128; families: 16.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| plain_check_full | 64 | 6 | 58 | 0 | 86154 |
| plain_check_compact | 61 | 3 | 61 | 3 | 81004 |
| ktrf_check_full | 42 | 0 | 64 | 19 | 136008 |
| ktrf_check_compact | 42 | 0 | 64 | 19 | 130772 |
| ktrf_evidence_full | 0 | 0 | 62 | 19 | 163144 |
| ktrf_evidence_compact | 0 | 0 | 62 | 19 | 157956 |

Split paired comparisons:

```json
{
  "plain_check_full_to_ktrf_check_full": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 22,
    "mean_correctness_delta_all_planned": -0.125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.046875,
    "harmful_rate_among_comparable": 0.171875,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 6,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.046875,
    "over_abstention_increased": 19,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.1484375,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_check_full_to_ktrf_evidence_full": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 44,
    "mean_correctness_delta_all_planned": -0.34375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.34375,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "plain_check_compact_to_ktrf_check_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 22,
    "mean_correctness_delta_all_planned": -0.125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.046875,
    "harmful_rate_among_comparable": 0.171875,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 3,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0234375,
    "over_abstention_increased": 19,
    "over_abstention_decreased": 3,
    "over_abstention_increase_rate_among_comparable": 0.1484375,
    "over_abstention_decrease_rate_among_comparable": 0.0234375
  },
  "ktrf_check_compact_to_ktrf_evidence_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 44,
    "mean_correctness_delta_all_planned": -0.34375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.34375,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "plain_check_full_to_plain_check_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 3,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.0234375,
    "harmful_rate_among_comparable": 0.0234375,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 3,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0234375,
    "over_abstention_increased": 3,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0234375,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_check_full_to_ktrf_check_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
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
  "ktrf_evidence_full_to_ktrf_evidence_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.0078125,
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

Evaluation split: `development`. Cases: 64; families: 8.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| plain_check_full | 32 | 5 | 27 | 0 | 43234 |
| plain_check_compact | 32 | 2 | 30 | 0 | 40548 |
| ktrf_check_full | 23 | 0 | 32 | 9 | 68440 |
| ktrf_check_compact | 23 | 0 | 32 | 9 | 65750 |
| ktrf_evidence_full | 0 | 0 | 30 | 9 | 82008 |
| ktrf_evidence_compact | 0 | 0 | 32 | 9 | 79318 |

Split paired comparisons:

```json
{
  "plain_check_full_to_ktrf_check_full": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 5,
    "harmful": 9,
    "mean_correctness_delta_all_planned": -0.0625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.078125,
    "harmful_rate_among_comparable": 0.140625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 5,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.078125,
    "over_abstention_increased": 9,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.140625,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_check_full_to_ktrf_evidence_full": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 25,
    "mean_correctness_delta_all_planned": -0.390625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.390625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "plain_check_compact_to_ktrf_check_compact": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 9,
    "mean_correctness_delta_all_planned": -0.109375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.03125,
    "harmful_rate_among_comparable": 0.140625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 2,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.03125,
    "over_abstention_increased": 9,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.140625,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_check_compact_to_ktrf_evidence_compact": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 23,
    "mean_correctness_delta_all_planned": -0.359375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.359375,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "plain_check_full_to_plain_check_compact": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.046875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.046875,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 3,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.046875,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_check_full_to_ktrf_check_compact": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
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
  "ktrf_evidence_full_to_ktrf_evidence_compact": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.03125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.03125,
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

- Fresh documents and glossary worlds are AI authored and AI reviewed, not human gold or actual workplace records.
- Pipeline selectors expose their own retrieved facts; plain versus KTRF is a product comparison, not a matched-information formatting test.
- Applicability metadata is supplied identically to all arms and is source-authored entity metadata, never case gold.
- The experimental evidence gate checks literal source and occurrence consistency, not general semantic entailment or a deployment-risk guarantee.
- Compact responses are expanded only through an immutable per-request binding; production occurrence authorization remains required.
- All sources and facts remain complete; overlong prompts fail preparation instead of being clipped.
- Fresh family clusters, not repeated arms or model calls, are the statistical units.
