# Extended frozen experiment

Experiment: `evidence_efficiency`. Model: `ktrf-efficiency-qwen27b-bf16`. Status: `COMPLETE`.

Cases: 64; parent documents: 64. Counts: `{'request_count': 320, 'record_count': 320, 'received_count': 320, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Accepted correct ID | Accepted wrong ID | Rejected wrong ID | Correct abstention | Over-abstention | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| plain_matched | 20 | 2 | 0 | 30 | 7 | 0 | 0 | 0 | 42324 |
| evidence_long | 7 | 0 | 0 | 30 | 20 | 0 | 0 | 0 | 79787 |
| evidence_short | 6 | 0 | 4 | 30 | 3 | 0 | 0 | 0 | 65361 |
| evidence_compact | 6 | 0 | 0 | 27 | 3 | 0 | 0 | 0 | 59200 |
| selective_compact | 6 | 0 | 2 | 26 | 2 | 0 | 0 | 0 | 57547 |

Model proposals precede the same production occurrence guard in every arm. Fresh AI-authored family splits are shown separately; no deployment risk is certified. Selective routing is fixed before generation using source and candidate facts, never gold.

| Condition | Correct ID proposals | Wrong ID proposals | Null proposals |
|---|---:|---:|---:|
| plain_matched | 25 | 2 | 37 |
| evidence_long | 12 | 0 | 52 |
| evidence_short | 19 | 0 | 35 |
| evidence_compact | 21 | 0 | 35 |
| selective_compact | 22 | 1 | 33 |

Selective routing paths, including measured tokens and request latency:

```json
{
  "difficulty_gate": {
    "unique_source_cases": 64,
    "easy_cases": 5,
    "reason_counts": {
      "resolver_not_resolved": 18,
      "candidate_count_not_one": 16,
      "quotation_negation_or_context_conflict_cue": 37,
      "no_unique_explicit_four_attribute_support": 58,
      "unique_occurrence_explicit_uncontested_applicability": 5,
      "competing_applicability_values": 3,
      "repeated_or_unmatched_surface": 8
    },
    "uses_gold": false
  },
  "by_evidence_path": {
    "plain_matched": {
      "plain": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 50,
        "correct_rate": 0.78125,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 20,
        "accepted_wrong_id": 2,
        "rejected_wrong_id": 0,
        "correct_abstention": 30,
        "over_abstention": 7,
        "rejected_correct_id": 5,
        "attempted_nonnull": 27,
        "guard_valid": 59,
        "semantic_match": 55,
        "accepted_nonnull": 22,
        "accepted_wrong_id_rate": 0.03125,
        "accepted_wrong_id_rate_among_accepted": 0.09090909090909091,
        "accepted_correct_id_rate": 0.625,
        "over_abstention_rate": 0.21875,
        "correct_abstention_rate": 0.9375,
        "documents": 64,
        "documents_with_wrong_approval": 2,
        "document_wrong_approval_rate": 0.03125,
        "proposal_correct_id": 25,
        "proposal_wrong_id": 2,
        "proposal_abstention": 37,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 5,
          "evidence_gate_valid": 0
        },
        "evidence_rejection_reasons": {},
        "usage": {
          "prompt_tokens": 42324,
          "completion_tokens": 5150,
          "total_tokens": 47474
        },
        "usage_observed_responses": {
          "prompt_tokens": 64,
          "completion_tokens": 64,
          "total_tokens": 64
        },
        "latency_ms": {
          "observations": 64,
          "total": 405443.534,
          "min": 5610.839,
          "max": 7141.995,
          "p50": 6252.233,
          "p95": 7028.837,
          "p99": 7118.185
        },
        "finish_reason_counts": {
          "stop": 64
        },
        "execution_validation_ms": {
          "observations": 64,
          "total": 4.918317,
          "min": 0.062236,
          "max": 0.115195,
          "p50": 0.073,
          "p95": 0.097,
          "p99": 0.114
        }
      }
    },
    "evidence_long": {
      "evidence": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 37,
        "correct_rate": 0.578125,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 7,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 30,
        "over_abstention": 20,
        "rejected_correct_id": 5,
        "attempted_nonnull": 12,
        "guard_valid": 57,
        "semantic_match": 44,
        "accepted_nonnull": 7,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.21875,
        "over_abstention_rate": 0.625,
        "correct_abstention_rate": 0.9375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 12,
        "proposal_wrong_id": 0,
        "proposal_abstention": 52,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 4,
          "evidence_gate_valid": 4
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 2,
          "complete_applicability_claims_required": 2,
          "unknown_or_stale_attribute_reference": 1
        },
        "usage": {
          "prompt_tokens": 79787,
          "completion_tokens": 11934,
          "total_tokens": 91721
        },
        "usage_observed_responses": {
          "prompt_tokens": 64,
          "completion_tokens": 64,
          "total_tokens": 64
        },
        "latency_ms": {
          "observations": 64,
          "total": 936169.718,
          "min": 9615.784,
          "max": 35191.906,
          "p50": 10362.703,
          "p95": 35035.678,
          "p99": 35188.673
        },
        "finish_reason_counts": {
          "stop": 64
        },
        "execution_validation_ms": {
          "observations": 64,
          "total": 6.984385,
          "min": 0.087433,
          "max": 0.317412,
          "p50": 0.093,
          "p95": 0.159,
          "p99": 0.221
        }
      }
    },
    "evidence_short": {
      "evidence": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 36,
        "correct_rate": 0.5625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 6,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 4,
        "correct_abstention": 30,
        "over_abstention": 3,
        "rejected_correct_id": 19,
        "attempted_nonnull": 29,
        "guard_valid": 36,
        "semantic_match": 57,
        "accepted_nonnull": 6,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.1875,
        "over_abstention_rate": 0.09375,
        "correct_abstention_rate": 0.9375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 19,
        "proposal_wrong_id": 0,
        "proposal_abstention": 35,
        "validation_failures": {
          "wire_valid": 10,
          "base_guard_valid": 13,
          "evidence_gate_valid": 25
        },
        "evidence_rejection_reasons": {
          "attribute_from_different_evidence": 4,
          "abstention_assertion_inconsistent": 9,
          "complete_applicability_claims_required": 16,
          "unknown_or_stale_attribute_reference": 7
        },
        "usage": {
          "prompt_tokens": 65361,
          "completion_tokens": 4181,
          "total_tokens": 69542
        },
        "usage_observed_responses": {
          "prompt_tokens": 64,
          "completion_tokens": 64,
          "total_tokens": 64
        },
        "latency_ms": {
          "observations": 64,
          "total": 340327.609,
          "min": 2958.422,
          "max": 9851.399,
          "p50": 4810.182,
          "p95": 9246.624,
          "p99": 9843.625
        },
        "finish_reason_counts": {
          "stop": 64
        },
        "execution_validation_ms": {
          "observations": 64,
          "total": 7.63106,
          "min": 0.087774,
          "max": 0.208529,
          "p50": 0.113,
          "p95": 0.169,
          "p99": 0.189
        }
      }
    },
    "evidence_compact": {
      "evidence": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 33,
        "correct_rate": 0.515625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 6,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 27,
        "over_abstention": 3,
        "rejected_correct_id": 23,
        "attempted_nonnull": 29,
        "guard_valid": 34,
        "semantic_match": 61,
        "accepted_nonnull": 6,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.1875,
        "over_abstention_rate": 0.09375,
        "correct_abstention_rate": 0.84375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 21,
        "proposal_wrong_id": 0,
        "proposal_abstention": 35,
        "validation_failures": {
          "wire_valid": 8,
          "base_guard_valid": 13,
          "evidence_gate_valid": 25
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 7,
          "complete_applicability_claims_required": 18,
          "unknown_or_stale_attribute_reference": 8,
          "positive_assertion_support_required": 1
        },
        "usage": {
          "prompt_tokens": 59200,
          "completion_tokens": 4475,
          "total_tokens": 63675
        },
        "usage_observed_responses": {
          "prompt_tokens": 64,
          "completion_tokens": 64,
          "total_tokens": 64
        },
        "latency_ms": {
          "observations": 64,
          "total": 362609.701,
          "min": 2997.999,
          "max": 10457.939,
          "p50": 5758.532,
          "p95": 9681.231,
          "p99": 10039.834
        },
        "finish_reason_counts": {
          "stop": 64
        },
        "execution_validation_ms": {
          "observations": 64,
          "total": 7.647795,
          "min": 0.086031,
          "max": 0.192369,
          "p50": 0.12,
          "p95": 0.166,
          "p99": 0.185
        }
      }
    },
    "selective_compact": {
      "plain": {
        "planned": 5,
        "questions": 5,
        "positive_planned": 5,
        "no_answer_planned": 0,
        "correct": 5,
        "correct_rate": 1.0,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 5,
        "pack_injected_requests": 5,
        "pack_injected_questions": 5,
        "families": 5,
        "accepted_correct_id": 5,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 0,
        "over_abstention": 0,
        "rejected_correct_id": 0,
        "attempted_nonnull": 5,
        "guard_valid": 5,
        "semantic_match": 5,
        "accepted_nonnull": 5,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 1.0,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": null,
        "documents": 5,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 5,
        "proposal_wrong_id": 0,
        "proposal_abstention": 0,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 0,
          "evidence_gate_valid": 0
        },
        "evidence_rejection_reasons": {},
        "usage": {
          "prompt_tokens": 3263,
          "completion_tokens": 187,
          "total_tokens": 3450
        },
        "usage_observed_responses": {
          "prompt_tokens": 5,
          "completion_tokens": 5,
          "total_tokens": 5
        },
        "latency_ms": {
          "observations": 5,
          "total": 15181.931,
          "min": 2867.04,
          "max": 3190.874,
          "p50": 2993.542,
          "p95": 3181.727,
          "p99": 3189.045
        },
        "finish_reason_counts": {
          "stop": 5
        },
        "execution_validation_ms": {
          "observations": 5,
          "total": 0.601673,
          "min": 0.083787,
          "max": 0.258993,
          "p50": 0.086,
          "p95": 0.225,
          "p99": 0.252
        }
      },
      "evidence": {
        "planned": 59,
        "questions": 59,
        "positive_planned": 27,
        "no_answer_planned": 32,
        "correct": 27,
        "correct_rate": 0.4576271186440678,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 59,
        "pack_injected_requests": 41,
        "pack_injected_questions": 41,
        "families": 8,
        "accepted_correct_id": 1,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 2,
        "correct_abstention": 26,
        "over_abstention": 2,
        "rejected_correct_id": 22,
        "attempted_nonnull": 25,
        "guard_valid": 28,
        "semantic_match": 54,
        "accepted_nonnull": 1,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.037037037037037035,
        "over_abstention_rate": 0.07407407407407407,
        "correct_abstention_rate": 0.8125,
        "documents": 59,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 17,
        "proposal_wrong_id": 1,
        "proposal_abstention": 33,
        "validation_failures": {
          "wire_valid": 8,
          "base_guard_valid": 14,
          "evidence_gate_valid": 25
        },
        "evidence_rejection_reasons": {
          "positive_assertion_support_required": 1,
          "complete_applicability_claims_required": 17,
          "abstention_assertion_inconsistent": 8,
          "unknown_or_stale_attribute_reference": 8
        },
        "usage": {
          "prompt_tokens": 54284,
          "completion_tokens": 3858,
          "total_tokens": 58142
        },
        "usage_observed_responses": {
          "prompt_tokens": 59,
          "completion_tokens": 59,
          "total_tokens": 59
        },
        "latency_ms": {
          "observations": 59,
          "total": 313765.006,
          "min": 2987.111,
          "max": 9861.696,
          "p50": 5329.335,
          "p95": 9313.967,
          "p99": 9813.39
        },
        "finish_reason_counts": {
          "stop": 59
        },
        "execution_validation_ms": {
          "observations": 59,
          "total": 6.792148,
          "min": 0.082504,
          "max": 0.164787,
          "p50": 0.104,
          "p95": 0.156,
          "p99": 0.162
        }
      }
    }
  }
}
```


Raw semantic selection and occurrence-bound approval are separate; synthetic/public proxy samples do not certify deployment risk.

Request wall time includes local parsing and execution validation; preparation costs are measured separately. Snapshot compilation counts only actual compilations, excluding cached zero-cost entries. Shared-host measurements are descriptive, not service-load SLOs.

| Condition | p50 ms | p95 ms | Input tokens | Output tokens |
|---|---:|---:|---:|---:|
| plain_matched | 6252.233 | 7028.837 | 42324 | 5150 |
| evidence_long | 10362.703 | 35035.678 | 79787 | 11934 |
| evidence_short | 4810.182 | 9246.624 | 65361 | 4181 |
| evidence_compact | 5758.532 | 9681.231 | 59200 | 4475 |
| selective_compact | 3856.568 | 9199.47 | 57547 | 4045 |

Preparation timings and pipeline diagnostics:

```json
{
  "preparation_timing_ms": {
    "snapshot_compile": {
      "observations": 8,
      "total": 14.523891266435385,
      "min": 1.7346979584544897,
      "max": 2.164830919355154,
      "p50": 1.768,
      "p95": 2.037,
      "p99": 2.139
    },
    "first_prepare": {
      "observations": 64,
      "total": 975.2796294633299,
      "min": 10.36722189746797,
      "max": 21.49060508236289,
      "p50": 15.262,
      "p95": 18.624,
      "p99": 20.145
    },
    "warm_prepare": {
      "observations": 64,
      "total": 921.1810261476785,
      "min": 9.401730028912425,
      "max": 20.091714104637504,
      "p50": 14.344,
      "p95": 17.654,
      "p99": 19.14
    }
  },
  "pipeline_diagnostics": {
    "confirmation": {
      "targets": 48,
      "positives": 24,
      "exact_core_detected": 48,
      "positive_gold_in_candidates": 24
    },
    "development": {
      "targets": 16,
      "positives": 8,
      "exact_core_detected": 16,
      "positive_gold_in_candidates": 8
    }
  }
}
```

Pre-inference terminology-need strata:

```json
{
  "required": {
    "questions": 64,
    "by_variant": {
      "plain_matched": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 50,
        "correct_rate": 0.78125,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 20,
        "accepted_wrong_id": 2,
        "rejected_wrong_id": 0,
        "correct_abstention": 30,
        "over_abstention": 7,
        "rejected_correct_id": 5,
        "attempted_nonnull": 27,
        "guard_valid": 59,
        "semantic_match": 55,
        "accepted_nonnull": 22,
        "accepted_wrong_id_rate": 0.03125,
        "accepted_wrong_id_rate_among_accepted": 0.09090909090909091,
        "accepted_correct_id_rate": 0.625,
        "over_abstention_rate": 0.21875,
        "correct_abstention_rate": 0.9375,
        "documents": 64,
        "documents_with_wrong_approval": 2,
        "document_wrong_approval_rate": 0.03125,
        "proposal_correct_id": 25,
        "proposal_wrong_id": 2,
        "proposal_abstention": 37,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 5,
          "evidence_gate_valid": 0
        },
        "evidence_rejection_reasons": {}
      },
      "evidence_long": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 37,
        "correct_rate": 0.578125,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 7,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 30,
        "over_abstention": 20,
        "rejected_correct_id": 5,
        "attempted_nonnull": 12,
        "guard_valid": 57,
        "semantic_match": 44,
        "accepted_nonnull": 7,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.21875,
        "over_abstention_rate": 0.625,
        "correct_abstention_rate": 0.9375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 12,
        "proposal_wrong_id": 0,
        "proposal_abstention": 52,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 4,
          "evidence_gate_valid": 4
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 2,
          "complete_applicability_claims_required": 2,
          "unknown_or_stale_attribute_reference": 1
        }
      },
      "evidence_short": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 36,
        "correct_rate": 0.5625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 6,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 4,
        "correct_abstention": 30,
        "over_abstention": 3,
        "rejected_correct_id": 19,
        "attempted_nonnull": 29,
        "guard_valid": 36,
        "semantic_match": 57,
        "accepted_nonnull": 6,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.1875,
        "over_abstention_rate": 0.09375,
        "correct_abstention_rate": 0.9375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 19,
        "proposal_wrong_id": 0,
        "proposal_abstention": 35,
        "validation_failures": {
          "wire_valid": 10,
          "base_guard_valid": 13,
          "evidence_gate_valid": 25
        },
        "evidence_rejection_reasons": {
          "attribute_from_different_evidence": 4,
          "abstention_assertion_inconsistent": 9,
          "complete_applicability_claims_required": 16,
          "unknown_or_stale_attribute_reference": 7
        }
      },
      "evidence_compact": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 33,
        "correct_rate": 0.515625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 6,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 27,
        "over_abstention": 3,
        "rejected_correct_id": 23,
        "attempted_nonnull": 29,
        "guard_valid": 34,
        "semantic_match": 61,
        "accepted_nonnull": 6,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.1875,
        "over_abstention_rate": 0.09375,
        "correct_abstention_rate": 0.84375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 21,
        "proposal_wrong_id": 0,
        "proposal_abstention": 35,
        "validation_failures": {
          "wire_valid": 8,
          "base_guard_valid": 13,
          "evidence_gate_valid": 25
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 7,
          "complete_applicability_claims_required": 18,
          "unknown_or_stale_attribute_reference": 8,
          "positive_assertion_support_required": 1
        }
      },
      "selective_compact": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 32,
        "correct_rate": 0.5,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 6,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 2,
        "correct_abstention": 26,
        "over_abstention": 2,
        "rejected_correct_id": 22,
        "attempted_nonnull": 30,
        "guard_valid": 33,
        "semantic_match": 59,
        "accepted_nonnull": 6,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.1875,
        "over_abstention_rate": 0.0625,
        "correct_abstention_rate": 0.8125,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 22,
        "proposal_wrong_id": 1,
        "proposal_abstention": 33,
        "validation_failures": {
          "wire_valid": 8,
          "base_guard_valid": 14,
          "evidence_gate_valid": 25
        },
        "evidence_rejection_reasons": {
          "positive_assertion_support_required": 1,
          "complete_applicability_claims_required": 17,
          "abstention_assertion_inconsistent": 8,
          "unknown_or_stale_attribute_reference": 8
        }
      }
    }
  }
}
```


Paired comparisons:

```json
{
  "plain_matched_to_evidence_long": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 15,
    "mean_correctness_delta_all_planned": -0.203125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.03125,
    "harmful_rate_among_comparable": 0.234375,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 2,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.03125,
    "over_abstention_increased": 13,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.203125,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "evidence_long_to_evidence_short": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 3,
    "mean_correctness_delta_all_planned": -0.015625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.03125,
    "harmful_rate_among_comparable": 0.046875,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 17,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.265625
  },
  "evidence_short_to_evidence_compact": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 4,
    "mean_correctness_delta_all_planned": -0.046875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.0625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.015625,
    "over_abstention_decrease_rate_among_comparable": 0.015625
  },
  "evidence_compact_to_selective_compact": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.015625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.03125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.015625
  }
}
```

Workload aggregate; exposed diagnostics and fresh families must be assessed separately.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `confirmation`. Cases: 48; families: 6.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| plain_matched | 15 | 1 | 23 | 4 | 31722 |
| evidence_long | 5 | 0 | 22 | 14 | 59559 |
| evidence_short | 5 | 0 | 22 | 1 | 48809 |
| evidence_compact | 4 | 0 | 19 | 2 | 44191 |
| selective_compact | 4 | 0 | 19 | 2 | 43252 |

Split paired comparisons:

```json
{
  "plain_matched_to_evidence_long": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 12,
    "mean_correctness_delta_all_planned": -0.22916666666666666,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.020833333333333332,
    "harmful_rate_among_comparable": 0.25,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.020833333333333332,
    "over_abstention_increased": 10,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.20833333333333334,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "evidence_long_to_evidence_short": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.041666666666666664,
    "harmful_rate_among_comparable": 0.041666666666666664,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 13,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.2708333333333333
  },
  "evidence_short_to_evidence_compact": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 4,
    "mean_correctness_delta_all_planned": -0.08333333333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.08333333333333333,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.020833333333333332,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "evidence_compact_to_selective_compact": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.020833333333333332,
    "harmful_rate_among_comparable": 0.020833333333333332,
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

Evaluation split: `development`. Cases: 16; families: 2.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| plain_matched | 5 | 1 | 7 | 3 | 10602 |
| evidence_long | 2 | 0 | 8 | 6 | 20228 |
| evidence_short | 1 | 0 | 8 | 2 | 16552 |
| evidence_compact | 2 | 0 | 8 | 1 | 15009 |
| selective_compact | 2 | 0 | 7 | 0 | 14295 |

Split paired comparisons:

```json
{
  "plain_matched_to_evidence_long": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 3,
    "mean_correctness_delta_all_planned": -0.125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.0625,
    "harmful_rate_among_comparable": 0.1875,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0625,
    "over_abstention_increased": 3,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.1875,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "evidence_long_to_evidence_short": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 1,
    "mean_correctness_delta_all_planned": -0.0625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 4,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.25
  },
  "evidence_short_to_evidence_compact": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.0625,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0625
  },
  "evidence_compact_to_selective_compact": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 1,
    "mean_correctness_delta_all_planned": -0.0625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0625
  }
}
```

- Fresh source documents and glossary facts are AI authored and AI reviewed, not human gold or actual workplace records.
- All arms receive identical actual resolver candidates, complete source text, full candidate definitions and applicability facts.
- The long-ID arm retains the preceding evidence-control instruction and fact representation; short transport changes identifiers and response field names.
- Compact input is a reversible projection of the same complete facts and evidence catalog; no source, definitions, exceptions or applicability facts are clipped.
- Selective routing uses only source text, requested occurrence, actual candidate metadata and resolver observations before model inference; it does not inspect gold or model agreement.
- Easy selective cases omit the experimental evidence check but still use the identical unchanged production occurrence execution guard.
- Evidence checks enforce source literals, occurrence identity and narrow direct-negation vetoes, not semantic entailment or a deployment-risk guarantee.
- Fresh confirmation family clusters are the statistical units; the development split is reported separately and method selection must not reuse confirmation outcomes.
