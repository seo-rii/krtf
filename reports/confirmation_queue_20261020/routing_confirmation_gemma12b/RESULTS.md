# Extended frozen experiment

Experiment: `routing_confirmation`. Model: `ktrf-confirmation-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 192; parent documents: 192. Counts: `{'request_count': 1152, 'record_count': 1152, 'received_count': 1152, 'missing_count': 0, 'error_count': 0, 'malformed_count': 3}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Accepted correct ID | Accepted wrong ID | Rejected wrong ID | Correct abstention | Over-abstention | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| plain_check_full | 95 | 21 | 2 | 72 | 0 | 0 | 0 | 0 | 137468 |
| plain_check_compact | 95 | 17 | 4 | 74 | 0 | 0 | 0 | 0 | 128126 |
| ktrf_check_full | 65 | 1 | 0 | 94 | 28 | 0 | 0 | 0 | 217493 |
| ktrf_check_compact | 65 | 0 | 0 | 95 | 28 | 0 | 0 | 0 | 208050 |
| ktrf_evidence_full | 0 | 0 | 0 | 64 | 28 | 0 | 0 | 0 | 261653 |
| ktrf_evidence_compact | 0 | 0 | 0 | 43 | 28 | 3 | 0 | 0 | 252277 |

Raw semantic selection and occurrence-bound approval are separate; synthetic/public proxy samples do not certify deployment risk.

Request wall time includes local parsing and execution validation; preparation costs are measured separately. Snapshot compilation counts only actual compilations, excluding cached zero-cost entries. Shared-host measurements are descriptive, not service-load SLOs.

| Condition | p50 ms | p95 ms | Input tokens | Output tokens |
|---|---:|---:|---:|---:|
| plain_check_full | 8852.322 | 11363.537 | 137468 | 34095 |
| plain_check_compact | 4423.047 | 5442.893 | 128126 | 16491 |
| ktrf_check_full | 10285.563 | 12592.489 | 217493 | 39473 |
| ktrf_check_compact | 4688.473 | 6107.201 | 208050 | 17749 |
| ktrf_evidence_full | 14213.928 | 26176.172 | 261653 | 61609 |
| ktrf_evidence_compact | 9315.727 | 21101.122 | 252277 | 45270 |

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
        "correct": 167,
        "correct_rate": 0.8697916666666666,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 192,
        "pack_injected_requests": 192,
        "pack_injected_questions": 192,
        "families": 24,
        "accepted_correct_id": 95,
        "accepted_wrong_id": 21,
        "rejected_wrong_id": 2,
        "correct_abstention": 72,
        "over_abstention": 0,
        "rejected_correct_id": 1,
        "attempted_nonnull": 119,
        "guard_valid": 188,
        "semantic_match": 169,
        "accepted_nonnull": 116,
        "accepted_wrong_id_rate": 0.109375,
        "accepted_wrong_id_rate_among_accepted": 0.1810344827586207,
        "accepted_correct_id_rate": 0.9895833333333334,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.75,
        "documents": 192,
        "documents_with_wrong_approval": 21,
        "document_wrong_approval_rate": 0.109375,
        "validation_failures": {
          "wire_valid": 4,
          "base_guard_valid": 4,
          "evidence_gate_valid": 4
        },
        "evidence_rejection_reasons": {}
      },
      "plain_check_compact": {
        "planned": 192,
        "questions": 192,
        "positive_planned": 96,
        "no_answer_planned": 96,
        "correct": 169,
        "correct_rate": 0.8802083333333334,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 192,
        "pack_injected_requests": 192,
        "pack_injected_questions": 192,
        "families": 24,
        "accepted_correct_id": 95,
        "accepted_wrong_id": 17,
        "rejected_wrong_id": 4,
        "correct_abstention": 74,
        "over_abstention": 0,
        "rejected_correct_id": 1,
        "attempted_nonnull": 117,
        "guard_valid": 186,
        "semantic_match": 171,
        "accepted_nonnull": 112,
        "accepted_wrong_id_rate": 0.08854166666666667,
        "accepted_wrong_id_rate_among_accepted": 0.15178571428571427,
        "accepted_correct_id_rate": 0.9895833333333334,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.7708333333333334,
        "documents": 192,
        "documents_with_wrong_approval": 17,
        "document_wrong_approval_rate": 0.08854166666666667,
        "validation_failures": {
          "wire_valid": 2,
          "base_guard_valid": 6,
          "evidence_gate_valid": 2
        },
        "evidence_rejection_reasons": {}
      },
      "ktrf_check_full": {
        "planned": 192,
        "questions": 192,
        "positive_planned": 96,
        "no_answer_planned": 96,
        "correct": 159,
        "correct_rate": 0.828125,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 192,
        "pack_injected_requests": 134,
        "pack_injected_questions": 134,
        "families": 24,
        "accepted_correct_id": 65,
        "accepted_wrong_id": 1,
        "rejected_wrong_id": 0,
        "correct_abstention": 94,
        "over_abstention": 28,
        "rejected_correct_id": 3,
        "attempted_nonnull": 69,
        "guard_valid": 188,
        "semantic_match": 163,
        "accepted_nonnull": 66,
        "accepted_wrong_id_rate": 0.005208333333333333,
        "accepted_wrong_id_rate_among_accepted": 0.015151515151515152,
        "accepted_correct_id_rate": 0.6770833333333334,
        "over_abstention_rate": 0.2916666666666667,
        "correct_abstention_rate": 0.9791666666666666,
        "documents": 192,
        "documents_with_wrong_approval": 1,
        "document_wrong_approval_rate": 0.005208333333333333,
        "validation_failures": {
          "wire_valid": 1,
          "base_guard_valid": 4,
          "evidence_gate_valid": 1
        },
        "evidence_rejection_reasons": {}
      },
      "ktrf_check_compact": {
        "planned": 192,
        "questions": 192,
        "positive_planned": 96,
        "no_answer_planned": 96,
        "correct": 160,
        "correct_rate": 0.8333333333333334,
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
        "correct_abstention": 95,
        "over_abstention": 28,
        "rejected_correct_id": 3,
        "attempted_nonnull": 68,
        "guard_valid": 187,
        "semantic_match": 164,
        "accepted_nonnull": 65,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.6770833333333334,
        "over_abstention_rate": 0.2916666666666667,
        "correct_abstention_rate": 0.9895833333333334,
        "documents": 192,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "validation_failures": {
          "wire_valid": 2,
          "base_guard_valid": 5,
          "evidence_gate_valid": 2
        },
        "evidence_rejection_reasons": {}
      },
      "ktrf_evidence_full": {
        "planned": 192,
        "questions": 192,
        "positive_planned": 96,
        "no_answer_planned": 96,
        "correct": 64,
        "correct_rate": 0.3333333333333333,
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
        "correct_abstention": 64,
        "over_abstention": 28,
        "rejected_correct_id": 68,
        "attempted_nonnull": 68,
        "guard_valid": 92,
        "semantic_match": 164,
        "accepted_nonnull": 0,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": null,
        "accepted_correct_id_rate": 0.0,
        "over_abstention_rate": 0.2916666666666667,
        "correct_abstention_rate": 0.6666666666666666,
        "documents": 192,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "validation_failures": {
          "wire_valid": 1,
          "base_guard_valid": 4,
          "evidence_gate_valid": 100
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 31,
          "source_quote_mismatch": 67,
          "attribute_source_span_mismatch": 264,
          "evidence_does_not_contain_requested_occurrence": 12,
          "evidence_crosses_target_paragraph": 24,
          "evidence_has_other_surface_occurrence": 13,
          "claimed_value_directly_negated": 6,
          "entity_applicability_mismatch": 52
        }
      },
      "ktrf_evidence_compact": {
        "planned": 192,
        "questions": 192,
        "positive_planned": 96,
        "no_answer_planned": 96,
        "correct": 43,
        "correct_rate": 0.22395833333333334,
        "missing": 0,
        "errors": 0,
        "malformed": 3,
        "valid": 189,
        "pack_injected_requests": 134,
        "pack_injected_questions": 134,
        "families": 24,
        "accepted_correct_id": 0,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 43,
        "over_abstention": 28,
        "rejected_correct_id": 68,
        "attempted_nonnull": 68,
        "guard_valid": 65,
        "semantic_match": 161,
        "accepted_nonnull": 0,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": null,
        "accepted_correct_id_rate": 0.0,
        "over_abstention_rate": 0.2916666666666667,
        "correct_abstention_rate": 0.4479166666666667,
        "documents": 192,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "validation_failures": {
          "wire_valid": 30,
          "base_guard_valid": 32,
          "evidence_gate_valid": 127
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 31,
          "source_quote_mismatch": 65,
          "evidence_does_not_contain_requested_occurrence": 12,
          "evidence_has_other_surface_occurrence": 12,
          "attribute_source_span_mismatch": 258,
          "evidence_crosses_target_paragraph": 22,
          "claimed_value_directly_negated": 2,
          "entity_applicability_mismatch": 33
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
    "helpful": 23,
    "harmful": 31,
    "mean_correctness_delta_all_planned": -0.041666666666666664,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.11979166666666667,
    "harmful_rate_among_comparable": 0.16145833333333334,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 20,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.10416666666666667,
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
    "helpful": 2,
    "harmful": 97,
    "mean_correctness_delta_all_planned": -0.4947916666666667,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.010416666666666666,
    "harmful_rate_among_comparable": 0.5052083333333334,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.005208333333333333,
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
    "helpful": 23,
    "harmful": 32,
    "mean_correctness_delta_all_planned": -0.046875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.11979166666666667,
    "harmful_rate_among_comparable": 0.16666666666666666,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 17,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.08854166666666667,
    "over_abstention_increased": 28,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.14583333333333334,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_check_compact_to_ktrf_evidence_compact": {
    "planned": 192,
    "questions": 192,
    "comparable": 189,
    "incomplete_or_malformed": 3,
    "helpful": 1,
    "harmful": 115,
    "mean_correctness_delta_all_planned": -0.609375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.005291005291005291,
    "harmful_rate_among_comparable": 0.6084656084656085,
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
    "helpful": 8,
    "harmful": 6,
    "mean_correctness_delta_all_planned": 0.010416666666666666,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.041666666666666664,
    "harmful_rate_among_comparable": 0.03125,
    "accepted_wrong_id_increased": 3,
    "accepted_wrong_id_decreased": 7,
    "accepted_wrong_id_increase_rate_among_comparable": 0.015625,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.036458333333333336,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_check_full_to_ktrf_check_compact": {
    "planned": 192,
    "questions": 192,
    "comparable": 192,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.005208333333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.010416666666666666,
    "harmful_rate_among_comparable": 0.005208333333333333,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.005208333333333333,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_evidence_full_to_ktrf_evidence_compact": {
    "planned": 192,
    "questions": 192,
    "comparable": 189,
    "incomplete_or_malformed": 3,
    "helpful": 4,
    "harmful": 24,
    "mean_correctness_delta_all_planned": -0.109375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 24,
    "helpful_rate_among_comparable": 0.021164021164021163,
    "harmful_rate_among_comparable": 0.12698412698412698,
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
| plain_check_full | 64 | 13 | 48 | 0 | 91529 |
| plain_check_compact | 64 | 11 | 48 | 0 | 85381 |
| ktrf_check_full | 42 | 0 | 63 | 19 | 144667 |
| ktrf_check_compact | 42 | 0 | 63 | 19 | 138426 |
| ktrf_evidence_full | 0 | 0 | 42 | 19 | 174107 |
| ktrf_evidence_compact | 0 | 0 | 27 | 19 | 167915 |

Split paired comparisons:

```json
{
  "plain_check_full_to_ktrf_check_full": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 16,
    "harmful": 23,
    "mean_correctness_delta_all_planned": -0.0546875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.125,
    "harmful_rate_among_comparable": 0.1796875,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 13,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.1015625,
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
    "helpful": 1,
    "harmful": 64,
    "mean_correctness_delta_all_planned": -0.4921875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.5,
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
    "helpful": 16,
    "harmful": 23,
    "mean_correctness_delta_all_planned": -0.0546875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.125,
    "harmful_rate_among_comparable": 0.1796875,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 11,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0859375,
    "over_abstention_increased": 19,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.1484375,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_check_compact_to_ktrf_evidence_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 125,
    "incomplete_or_malformed": 3,
    "helpful": 1,
    "harmful": 76,
    "mean_correctness_delta_all_planned": -0.609375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.008,
    "harmful_rate_among_comparable": 0.608,
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
    "helpful": 5,
    "harmful": 5,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.0390625,
    "harmful_rate_among_comparable": 0.0390625,
    "accepted_wrong_id_increased": 3,
    "accepted_wrong_id_decreased": 5,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0234375,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0390625,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_check_full_to_ktrf_check_compact": {
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
  },
  "ktrf_evidence_full_to_ktrf_evidence_compact": {
    "planned": 128,
    "questions": 128,
    "comparable": 125,
    "incomplete_or_malformed": 3,
    "helpful": 2,
    "harmful": 16,
    "mean_correctness_delta_all_planned": -0.1171875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 16,
    "helpful_rate_among_comparable": 0.016,
    "harmful_rate_among_comparable": 0.128,
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
| plain_check_full | 31 | 8 | 24 | 0 | 45939 |
| plain_check_compact | 31 | 6 | 26 | 0 | 42745 |
| ktrf_check_full | 23 | 1 | 31 | 9 | 72826 |
| ktrf_check_compact | 23 | 0 | 32 | 9 | 69624 |
| ktrf_evidence_full | 0 | 0 | 22 | 9 | 87546 |
| ktrf_evidence_compact | 0 | 0 | 16 | 9 | 84362 |

Split paired comparisons:

```json
{
  "plain_check_full_to_ktrf_check_full": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 7,
    "harmful": 8,
    "mean_correctness_delta_all_planned": -0.015625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.109375,
    "harmful_rate_among_comparable": 0.125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 7,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.109375,
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
    "helpful": 1,
    "harmful": 33,
    "mean_correctness_delta_all_planned": -0.5,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.515625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.015625,
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
    "helpful": 7,
    "harmful": 9,
    "mean_correctness_delta_all_planned": -0.03125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.109375,
    "harmful_rate_among_comparable": 0.140625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 6,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.09375,
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
    "harmful": 39,
    "mean_correctness_delta_all_planned": -0.609375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.609375,
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
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.03125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.046875,
    "harmful_rate_among_comparable": 0.015625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 2,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.03125,
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
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.015625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
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
  "ktrf_evidence_full_to_ktrf_evidence_compact": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 8,
    "mean_correctness_delta_all_planned": -0.09375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.03125,
    "harmful_rate_among_comparable": 0.125,
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
