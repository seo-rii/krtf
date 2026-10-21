# Extended frozen experiment

Experiment: `evidence_efficiency`. Model: `ktrf-efficiency-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 64; parent documents: 64. Counts: `{'request_count': 320, 'record_count': 320, 'received_count': 320, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Accepted correct ID | Accepted wrong ID | Rejected wrong ID | Correct abstention | Over-abstention | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| plain_matched | 22 | 2 | 0 | 30 | 2 | 0 | 0 | 0 | 45026 |
| evidence_long | 7 | 0 | 2 | 30 | 2 | 0 | 0 | 0 | 84021 |
| evidence_short | 5 | 0 | 7 | 5 | 0 | 0 | 0 | 0 | 69503 |
| evidence_compact | 7 | 0 | 5 | 0 | 1 | 0 | 0 | 0 | 64046 |
| selective_compact | 4 | 0 | 7 | 0 | 0 | 0 | 0 | 0 | 62281 |

Model proposals precede the same production occurrence guard in every arm. Fresh AI-authored family splits are shown separately; no deployment risk is certified. Selective routing is fixed before generation using source and candidate facts, never gold.

| Condition | Correct ID proposals | Wrong ID proposals | Null proposals |
|---|---:|---:|---:|
| plain_matched | 30 | 2 | 32 |
| evidence_long | 30 | 2 | 32 |
| evidence_short | 20 | 0 | 16 |
| evidence_compact | 16 | 1 | 7 |
| selective_compact | 16 | 0 | 8 |

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
        "correct": 52,
        "correct_rate": 0.8125,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 22,
        "accepted_wrong_id": 2,
        "rejected_wrong_id": 0,
        "correct_abstention": 30,
        "over_abstention": 2,
        "rejected_correct_id": 8,
        "attempted_nonnull": 32,
        "guard_valid": 56,
        "semantic_match": 60,
        "accepted_nonnull": 24,
        "accepted_wrong_id_rate": 0.03125,
        "accepted_wrong_id_rate_among_accepted": 0.08333333333333333,
        "accepted_correct_id_rate": 0.6875,
        "over_abstention_rate": 0.0625,
        "correct_abstention_rate": 0.9375,
        "documents": 64,
        "documents_with_wrong_approval": 2,
        "document_wrong_approval_rate": 0.03125,
        "proposal_correct_id": 30,
        "proposal_wrong_id": 2,
        "proposal_abstention": 32,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 8,
          "evidence_gate_valid": 0
        },
        "evidence_rejection_reasons": {},
        "usage": {
          "prompt_tokens": 45026,
          "completion_tokens": 5450,
          "total_tokens": 50476
        },
        "usage_observed_responses": {
          "prompt_tokens": 64,
          "completion_tokens": 64,
          "total_tokens": 64
        },
        "latency_ms": {
          "observations": 64,
          "total": 276873.316,
          "min": 3703.788,
          "max": 5290.468,
          "p50": 4352.382,
          "p95": 4739.263,
          "p99": 4980.974
        },
        "finish_reason_counts": {
          "stop": 64
        },
        "execution_validation_ms": {
          "observations": 64,
          "total": 5.439839,
          "min": 0.059471,
          "max": 0.23034,
          "p50": 0.082,
          "p95": 0.112,
          "p99": 0.176
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
        "rejected_wrong_id": 2,
        "correct_abstention": 30,
        "over_abstention": 2,
        "rejected_correct_id": 23,
        "attempted_nonnull": 32,
        "guard_valid": 39,
        "semantic_match": 60,
        "accepted_nonnull": 7,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.21875,
        "over_abstention_rate": 0.0625,
        "correct_abstention_rate": 0.9375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 30,
        "proposal_wrong_id": 2,
        "proposal_abstention": 32,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 19
        },
        "evidence_rejection_reasons": {
          "complete_applicability_claims_required": 19,
          "unknown_or_stale_attribute_reference": 2
        },
        "usage": {
          "prompt_tokens": 84021,
          "completion_tokens": 13853,
          "total_tokens": 97874
        },
        "usage_observed_responses": {
          "prompt_tokens": 64,
          "completion_tokens": 64,
          "total_tokens": 64
        },
        "latency_ms": {
          "observations": 64,
          "total": 696609.301,
          "min": 4733.588,
          "max": 23309.036,
          "p50": 8313.774,
          "p95": 22938.135,
          "p99": 23234.661
        },
        "finish_reason_counts": {
          "stop": 64
        },
        "execution_validation_ms": {
          "observations": 64,
          "total": 7.895311,
          "min": 0.085229,
          "max": 0.240749,
          "p50": 0.121,
          "p95": 0.184,
          "p99": 0.232
        }
      }
    },
    "evidence_short": {
      "evidence": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 10,
        "correct_rate": 0.15625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 5,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 7,
        "correct_abstention": 5,
        "over_abstention": 0,
        "rejected_correct_id": 22,
        "attempted_nonnull": 34,
        "guard_valid": 10,
        "semantic_match": 57,
        "accepted_nonnull": 5,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.15625,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.15625,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 20,
        "proposal_wrong_id": 0,
        "proposal_abstention": 16,
        "validation_failures": {
          "wire_valid": 28,
          "base_guard_valid": 35,
          "evidence_gate_valid": 47
        },
        "evidence_rejection_reasons": {
          "unknown_or_stale_attribute_reference": 25,
          "attribute_from_different_evidence": 9,
          "abstention_assertion_inconsistent": 17,
          "complete_applicability_claims_required": 16,
          "positive_assertion_support_required": 1
        },
        "usage": {
          "prompt_tokens": 69503,
          "completion_tokens": 5492,
          "total_tokens": 74995
        },
        "usage_observed_responses": {
          "prompt_tokens": 64,
          "completion_tokens": 64,
          "total_tokens": 64
        },
        "latency_ms": {
          "observations": 64,
          "total": 277882.195,
          "min": 2331.178,
          "max": 7254.683,
          "p50": 4113.23,
          "p95": 6812.274,
          "p99": 7244.326
        },
        "finish_reason_counts": {
          "stop": 64
        },
        "execution_validation_ms": {
          "observations": 64,
          "total": 7.881566,
          "min": 0.089437,
          "max": 0.181729,
          "p50": 0.124,
          "p95": 0.156,
          "p99": 0.175
        }
      }
    },
    "evidence_compact": {
      "evidence": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 7,
        "correct_rate": 0.109375,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 7,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 5,
        "correct_abstention": 0,
        "over_abstention": 1,
        "rejected_correct_id": 22,
        "attempted_nonnull": 34,
        "guard_valid": 7,
        "semantic_match": 58,
        "accepted_nonnull": 7,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.21875,
        "over_abstention_rate": 0.03125,
        "correct_abstention_rate": 0.0,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 16,
        "proposal_wrong_id": 1,
        "proposal_abstention": 7,
        "validation_failures": {
          "wire_valid": 40,
          "base_guard_valid": 46,
          "evidence_gate_valid": 52
        },
        "evidence_rejection_reasons": {
          "unknown_or_stale_attribute_reference": 40,
          "abstention_assertion_inconsistent": 22,
          "complete_applicability_claims_required": 19,
          "attribute_from_different_evidence": 4,
          "positive_assertion_support_required": 2
        },
        "usage": {
          "prompt_tokens": 64046,
          "completion_tokens": 6242,
          "total_tokens": 70288
        },
        "usage_observed_responses": {
          "prompt_tokens": 64,
          "completion_tokens": 64,
          "total_tokens": 64
        },
        "latency_ms": {
          "observations": 64,
          "total": 314930.065,
          "min": 3268.201,
          "max": 7258.228,
          "p50": 4619.766,
          "p95": 7080.405,
          "p99": 7214.049
        },
        "finish_reason_counts": {
          "stop": 64
        },
        "execution_validation_ms": {
          "observations": 64,
          "total": 8.105535,
          "min": 0.092623,
          "max": 0.180347,
          "p50": 0.128,
          "p95": 0.16,
          "p99": 0.171
        }
      }
    },
    "selective_compact": {
      "plain": {
        "planned": 5,
        "questions": 5,
        "positive_planned": 5,
        "no_answer_planned": 0,
        "correct": 2,
        "correct_rate": 0.4,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 5,
        "pack_injected_requests": 5,
        "pack_injected_questions": 5,
        "families": 5,
        "accepted_correct_id": 2,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 3,
        "correct_abstention": 0,
        "over_abstention": 0,
        "rejected_correct_id": 0,
        "attempted_nonnull": 5,
        "guard_valid": 2,
        "semantic_match": 2,
        "accepted_nonnull": 2,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.4,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": null,
        "documents": 5,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 2,
        "proposal_wrong_id": 0,
        "proposal_abstention": 0,
        "validation_failures": {
          "wire_valid": 3,
          "base_guard_valid": 3,
          "evidence_gate_valid": 3
        },
        "evidence_rejection_reasons": {},
        "usage": {
          "prompt_tokens": 3544,
          "completion_tokens": 185,
          "total_tokens": 3729
        },
        "usage_observed_responses": {
          "prompt_tokens": 5,
          "completion_tokens": 5,
          "total_tokens": 5
        },
        "latency_ms": {
          "observations": 5,
          "total": 9546.71,
          "min": 1651.005,
          "max": 2330.986,
          "p50": 1701.699,
          "p95": 2303.811,
          "p99": 2325.551
        },
        "finish_reason_counts": {
          "stop": 5
        },
        "execution_validation_ms": {
          "observations": 5,
          "total": 0.409395,
          "min": 0.073618,
          "max": 0.089016,
          "p50": 0.086,
          "p95": 0.088,
          "p99": 0.089
        }
      },
      "evidence": {
        "planned": 59,
        "questions": 59,
        "positive_planned": 27,
        "no_answer_planned": 32,
        "correct": 2,
        "correct_rate": 0.03389830508474576,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 59,
        "pack_injected_requests": 41,
        "pack_injected_questions": 41,
        "families": 8,
        "accepted_correct_id": 2,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 4,
        "correct_abstention": 0,
        "over_abstention": 0,
        "rejected_correct_id": 23,
        "attempted_nonnull": 29,
        "guard_valid": 2,
        "semantic_match": 55,
        "accepted_nonnull": 2,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.07407407407407407,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.0,
        "documents": 59,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 14,
        "proposal_wrong_id": 0,
        "proposal_abstention": 8,
        "validation_failures": {
          "wire_valid": 37,
          "base_guard_valid": 44,
          "evidence_gate_valid": 51
        },
        "evidence_rejection_reasons": {
          "unknown_or_stale_attribute_reference": 37,
          "abstention_assertion_inconsistent": 22,
          "attribute_from_different_evidence": 7,
          "complete_applicability_claims_required": 18
        },
        "usage": {
          "prompt_tokens": 58737,
          "completion_tokens": 5542,
          "total_tokens": 64279
        },
        "usage_observed_responses": {
          "prompt_tokens": 59,
          "completion_tokens": 59,
          "total_tokens": 59
        },
        "latency_ms": {
          "observations": 59,
          "total": 279360.18,
          "min": 3053.246,
          "max": 7239.263,
          "p50": 4398.404,
          "p95": 7135.118,
          "p99": 7193.456
        },
        "finish_reason_counts": {
          "stop": 59
        },
        "execution_validation_ms": {
          "observations": 59,
          "total": 7.534585,
          "min": 0.094897,
          "max": 0.190014,
          "p50": 0.127,
          "p95": 0.177,
          "p99": 0.187
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
| plain_matched | 4352.382 | 4739.263 | 45026 | 5450 |
| evidence_long | 8313.774 | 22938.135 | 84021 | 13853 |
| evidence_short | 4113.23 | 6812.274 | 69503 | 5492 |
| evidence_compact | 4619.766 | 7080.405 | 64046 | 6242 |
| selective_compact | 4377.76 | 7082.77 | 62281 | 5727 |

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
        "correct": 52,
        "correct_rate": 0.8125,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 22,
        "accepted_wrong_id": 2,
        "rejected_wrong_id": 0,
        "correct_abstention": 30,
        "over_abstention": 2,
        "rejected_correct_id": 8,
        "attempted_nonnull": 32,
        "guard_valid": 56,
        "semantic_match": 60,
        "accepted_nonnull": 24,
        "accepted_wrong_id_rate": 0.03125,
        "accepted_wrong_id_rate_among_accepted": 0.08333333333333333,
        "accepted_correct_id_rate": 0.6875,
        "over_abstention_rate": 0.0625,
        "correct_abstention_rate": 0.9375,
        "documents": 64,
        "documents_with_wrong_approval": 2,
        "document_wrong_approval_rate": 0.03125,
        "proposal_correct_id": 30,
        "proposal_wrong_id": 2,
        "proposal_abstention": 32,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 8,
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
        "rejected_wrong_id": 2,
        "correct_abstention": 30,
        "over_abstention": 2,
        "rejected_correct_id": 23,
        "attempted_nonnull": 32,
        "guard_valid": 39,
        "semantic_match": 60,
        "accepted_nonnull": 7,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.21875,
        "over_abstention_rate": 0.0625,
        "correct_abstention_rate": 0.9375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 30,
        "proposal_wrong_id": 2,
        "proposal_abstention": 32,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 19
        },
        "evidence_rejection_reasons": {
          "complete_applicability_claims_required": 19,
          "unknown_or_stale_attribute_reference": 2
        }
      },
      "evidence_short": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 10,
        "correct_rate": 0.15625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 5,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 7,
        "correct_abstention": 5,
        "over_abstention": 0,
        "rejected_correct_id": 22,
        "attempted_nonnull": 34,
        "guard_valid": 10,
        "semantic_match": 57,
        "accepted_nonnull": 5,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.15625,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.15625,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 20,
        "proposal_wrong_id": 0,
        "proposal_abstention": 16,
        "validation_failures": {
          "wire_valid": 28,
          "base_guard_valid": 35,
          "evidence_gate_valid": 47
        },
        "evidence_rejection_reasons": {
          "unknown_or_stale_attribute_reference": 25,
          "attribute_from_different_evidence": 9,
          "abstention_assertion_inconsistent": 17,
          "complete_applicability_claims_required": 16,
          "positive_assertion_support_required": 1
        }
      },
      "evidence_compact": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 7,
        "correct_rate": 0.109375,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 7,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 5,
        "correct_abstention": 0,
        "over_abstention": 1,
        "rejected_correct_id": 22,
        "attempted_nonnull": 34,
        "guard_valid": 7,
        "semantic_match": 58,
        "accepted_nonnull": 7,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.21875,
        "over_abstention_rate": 0.03125,
        "correct_abstention_rate": 0.0,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 16,
        "proposal_wrong_id": 1,
        "proposal_abstention": 7,
        "validation_failures": {
          "wire_valid": 40,
          "base_guard_valid": 46,
          "evidence_gate_valid": 52
        },
        "evidence_rejection_reasons": {
          "unknown_or_stale_attribute_reference": 40,
          "abstention_assertion_inconsistent": 22,
          "complete_applicability_claims_required": 19,
          "attribute_from_different_evidence": 4,
          "positive_assertion_support_required": 2
        }
      },
      "selective_compact": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 4,
        "correct_rate": 0.0625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 4,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 7,
        "correct_abstention": 0,
        "over_abstention": 0,
        "rejected_correct_id": 23,
        "attempted_nonnull": 34,
        "guard_valid": 4,
        "semantic_match": 57,
        "accepted_nonnull": 4,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.125,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.0,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 16,
        "proposal_wrong_id": 0,
        "proposal_abstention": 8,
        "validation_failures": {
          "wire_valid": 40,
          "base_guard_valid": 47,
          "evidence_gate_valid": 54
        },
        "evidence_rejection_reasons": {
          "unknown_or_stale_attribute_reference": 37,
          "abstention_assertion_inconsistent": 22,
          "attribute_from_different_evidence": 7,
          "complete_applicability_claims_required": 18
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
    "helpful": 0,
    "harmful": 15,
    "mean_correctness_delta_all_planned": -0.234375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.234375,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 2,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.03125,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.015625,
    "over_abstention_decrease_rate_among_comparable": 0.015625
  },
  "evidence_long_to_evidence_short": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 27,
    "mean_correctness_delta_all_planned": -0.421875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.421875,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 2,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.03125
  },
  "evidence_short_to_evidence_compact": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 5,
    "mean_correctness_delta_all_planned": -0.046875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.03125,
    "harmful_rate_among_comparable": 0.078125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.015625,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "evidence_compact_to_selective_compact": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 3,
    "mean_correctness_delta_all_planned": -0.046875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.046875,
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
| plain_matched | 17 | 1 | 23 | 0 | 33750 |
| evidence_long | 5 | 0 | 23 | 1 | 62717 |
| evidence_short | 3 | 0 | 5 | 0 | 51906 |
| evidence_compact | 5 | 0 | 0 | 1 | 47810 |
| selective_compact | 3 | 0 | 0 | 0 | 46822 |

Split paired comparisons:

```json
{
  "plain_matched_to_evidence_long": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 12,
    "mean_correctness_delta_all_planned": -0.25,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.25,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.020833333333333332,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.020833333333333332,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "evidence_long_to_evidence_short": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 20,
    "mean_correctness_delta_all_planned": -0.4166666666666667,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.4166666666666667,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.020833333333333332
  },
  "evidence_short_to_evidence_compact": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 5,
    "mean_correctness_delta_all_planned": -0.0625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.041666666666666664,
    "harmful_rate_among_comparable": 0.10416666666666667,
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
    "helpful": 0,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.041666666666666664,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.041666666666666664,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.020833333333333332
  }
}
```

Evaluation split: `development`. Cases: 16; families: 2.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| plain_matched | 5 | 1 | 7 | 2 | 11276 |
| evidence_long | 2 | 0 | 7 | 1 | 21304 |
| evidence_short | 2 | 0 | 0 | 0 | 17597 |
| evidence_compact | 2 | 0 | 0 | 0 | 16236 |
| selective_compact | 1 | 0 | 0 | 0 | 15459 |

Split paired comparisons:

```json
{
  "plain_matched_to_evidence_long": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 3,
    "mean_correctness_delta_all_planned": -0.1875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.1875,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 1,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0625,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0625
  },
  "evidence_long_to_evidence_short": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 7,
    "mean_correctness_delta_all_planned": -0.4375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.4375,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0625
  },
  "evidence_short_to_evidence_compact": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
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
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
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
