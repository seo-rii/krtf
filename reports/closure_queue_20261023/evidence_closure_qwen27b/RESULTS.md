# Extended frozen experiment

Experiment: `evidence_closure`. Model: `ktrf-closure-qwen27b-bf16`. Status: `COMPLETE`.

Cases: 96; parent documents: 96. Counts: `{'request_count': 480, 'record_count': 480, 'received_count': 480, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

**Evaluation only. Shadow results are EXPERIMENTAL_SIMULATED_APPROVAL, with no execution authority; they are not production approvals.**

| Condition | Decision contract |
|---|---|
| manual_legacy | EXPERIMENTAL_SIMULATED_APPROVAL |
| closure_legacy | EXPERIMENTAL_SIMULATED_APPROVAL |
| manual_null | EXPERIMENTAL_SIMULATED_APPROVAL |
| closure_null | EXPERIMENTAL_SIMULATED_APPROVAL |
| closure_bundle | EXPERIMENTAL_SIMULATED_APPROVAL |

| Condition | Accepted correct ID | Accepted wrong ID | Rejected wrong ID | Correct abstention | Over-abstention | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| manual_legacy | 45 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 348440 |
| closure_legacy | 46 | 0 | 0 | 27 | 0 | 0 | 0 | 0 | 350811 |
| manual_null | 15 | 0 | 2 | 46 | 0 | 0 | 0 | 0 | 348469 |
| closure_null | 46 | 0 | 0 | 47 | 0 | 0 | 0 | 0 | 352234 |
| closure_bundle | 46 | 0 | 0 | 48 | 0 | 0 | 0 | 0 | 353852 |

All arms report experimental shadow judgments without execution authority. Model semantic proposals, pre-closure evidence validation, server-closed validation and the unchanged production occurrence-guard result are separate. Server closure only adds source-bound segments for the selected occurrence and attributes; it does not prove semantic entailment.

| Condition | Correct ID proposals | Wrong ID proposals | Null proposals |
|---|---:|---:|---:|
| manual_legacy | 48 | 1 | 47 |
| closure_legacy | 48 | 0 | 48 |
| manual_null | 48 | 1 | 46 |
| closure_null | 48 | 0 | 47 |
| closure_bundle | 48 | 0 | 48 |

Separate guard and simulated-shadow decisions:

| Condition | Production guard correct | Production guard wrong | Simulated shadow correct | Simulated shadow wrong |
|---|---:|---:|---:|---:|
| manual_legacy | 35 | 1 | 45 | 0 |
| closure_legacy | 35 | 0 | 46 | 0 |
| manual_null | 35 | 0 | 15 | 0 |
| closure_null | 35 | 0 | 46 | 0 |
| closure_bundle | 35 | 0 | 46 | 0 |

Support inventory and validation diagnostics:

```json
{
  "evaluation_population": "FRESH_AI_AUTHORED_CONFIRMATION",
  "support_inventory": {
    "manual_legacy": {
      "source_cases": 96,
      "segments": 2168,
      "attribute_spans": 264,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 18,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 96
      }
    },
    "closure_legacy": {
      "source_cases": 96,
      "segments": 2168,
      "attribute_spans": 264,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 18,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 96
      }
    },
    "manual_null": {
      "source_cases": 96,
      "segments": 2168,
      "attribute_spans": 264,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 18,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 96
      }
    },
    "closure_null": {
      "source_cases": 96,
      "segments": 2168,
      "attribute_spans": 264,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 18,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 96
      }
    },
    "closure_bundle": {
      "source_cases": 96,
      "segments": 2168,
      "attribute_spans": 264,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 18,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 96
      }
    }
  },
  "validation_failure_clusters": {
    "manual_legacy": {
      "production_guard": {
        "unverified_execution": 13
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 47,
        "positive_assertion_support_required": 2,
        "full_surface_structural_identity_not_same": 1,
        "explicit_separate_identity_context": 1,
        "positive_applicability_support_required": 1,
        "explicit_temporal_or_identity_conflict": 1
      },
      "unknown_attributes": {
        "jurisdiction": 60,
        "temporal_status": 60,
        "referent_kind": 48,
        "scope": 48
      },
      "present_attributes": {
        "referent_kind": 48,
        "scope": 48,
        "jurisdiction": 36,
        "temporal_status": 36
      }
    },
    "closure_legacy": {
      "production_guard": {
        "unverified_execution": 13
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 21,
        "full_surface_structural_identity_not_same": 1,
        "explicit_separate_identity_context": 1
      },
      "unknown_attributes": {
        "jurisdiction": 60,
        "temporal_status": 60,
        "referent_kind": 48,
        "scope": 48
      },
      "present_attributes": {
        "referent_kind": 48,
        "scope": 48,
        "jurisdiction": 36,
        "temporal_status": 36
      }
    },
    "manual_null": {
      "production_guard": {
        "unverified_execution": 14
      },
      "support_gate": {
        "unknown_or_stale_evidence_reference": 34,
        "evidence_does_not_contain_requested_occurrence": 34,
        "attribute_outside_selected_evidence": 120,
        "full_surface_structural_identity_not_same": 2,
        "explicit_separate_identity_context": 1,
        "unknown_or_stale_attribute_reference": 1,
        "positive_applicability_support_required": 1,
        "full_surface_role_or_composition": 1
      },
      "unknown_attributes": {
        "jurisdiction": 60,
        "temporal_status": 60,
        "referent_kind": 48,
        "scope": 48
      },
      "present_attributes": {
        "referent_kind": 48,
        "scope": 48,
        "jurisdiction": 36,
        "temporal_status": 36
      }
    },
    "closure_null": {
      "production_guard": {
        "unverified_execution": 13
      },
      "support_gate": {
        "full_surface_structural_identity_not_same": 1,
        "explicit_separate_identity_context": 1
      },
      "unknown_attributes": {
        "jurisdiction": 60,
        "temporal_status": 60,
        "referent_kind": 48,
        "scope": 48
      },
      "present_attributes": {
        "referent_kind": 48,
        "scope": 48,
        "jurisdiction": 36,
        "temporal_status": 36
      }
    },
    "closure_bundle": {
      "production_guard": {
        "unverified_execution": 13
      },
      "support_gate": {
        "full_surface_structural_identity_not_same": 1,
        "explicit_separate_identity_context": 1
      },
      "unknown_attributes": {
        "jurisdiction": 60,
        "temporal_status": 60,
        "referent_kind": 48,
        "scope": 48
      },
      "present_attributes": {
        "referent_kind": 48,
        "scope": 48,
        "jurisdiction": 36,
        "temporal_status": 36
      }
    }
  }
}
```

Unknown-attribute counts describe absent selected supporting claims. Null proposals leave every attribute UNKNOWN; these counts do not establish that the source lacks the attribute, or that an unstated attribute is false.


Server closure and null-wire diagnostics:

| Condition | Raw correct/wrong | Closed shadow correct/wrong | Raw validation valid | Closed validation valid | Added segments | Cases with additions | Null wire errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| manual_legacy | 45/0 | 45/0 | 45 | 45 | 0 | 0 | 47 |
| closure_legacy | 46/0 | 46/0 | 73 | 73 | 0 | 0 | 21 |
| manual_null | 15/0 | 15/0 | 61 | 61 | 0 | 0 | 0 |
| closure_null | 46/0 | 46/0 | 93 | 93 | 0 | 0 | 0 |
| closure_bundle | 46/0 | 46/0 | 94 | 94 | 0 | 0 | 0 |

Paired source-length, referent-kind, country and target-side strata:

```json
{
  "document_length_band": {
    "long": {
      "questions": 48,
      "families": 12,
      "by_variant": {
        "manual_legacy": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 23,
          "correct_rate": 0.4791666666666667,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 48,
          "pack_injected_questions": 48,
          "families": 12,
          "accepted_correct_id": 23,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 0,
          "over_abstention": 0,
          "rejected_correct_id": 1,
          "attempted_nonnull": 24,
          "guard_valid": 23,
          "semantic_match": 48,
          "accepted_nonnull": 23,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.9583333333333334,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 0.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 0,
          "proposal_abstention": 24,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 6,
            "evidence_gate_valid": 25
          },
          "evidence_rejection_reasons": {
            "abstention_assertion_inconsistent": 24,
            "explicit_separate_identity_context": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 18,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 23,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 6,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 24,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 24,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 23,
          "closed_validation_valid": 23,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 24,
          "raw_guard_failures": 25,
          "raw_accepted_correct_id": 23,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 248935,
            "completion_tokens": 6361,
            "total_tokens": 255296
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 558682.155,
            "min": 7109.353,
            "max": 16599.5,
            "p50": 11441.174,
            "p95": 15642.485,
            "p99": 16314.526
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 85.546489,
            "min": 0.136294,
            "max": 5.025191,
            "p50": 1.545,
            "p95": 3.587,
            "p99": 4.913
          }
        },
        "closure_legacy": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 35,
          "correct_rate": 0.7291666666666666,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 48,
          "pack_injected_questions": 48,
          "families": 12,
          "accepted_correct_id": 23,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 12,
          "over_abstention": 0,
          "rejected_correct_id": 1,
          "attempted_nonnull": 24,
          "guard_valid": 35,
          "semantic_match": 48,
          "accepted_nonnull": 23,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.9583333333333334,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 0.5,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 0,
          "proposal_abstention": 24,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 6,
            "evidence_gate_valid": 13
          },
          "evidence_rejection_reasons": {
            "abstention_assertion_inconsistent": 12,
            "explicit_separate_identity_context": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 18,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 23,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 6,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 24,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 24,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 35,
          "closed_validation_valid": 35,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 12,
          "raw_guard_failures": 13,
          "raw_accepted_correct_id": 23,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 249488,
            "completion_tokens": 5324,
            "total_tokens": 254812
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 477984.583,
            "min": 4098.413,
            "max": 15932.443,
            "p50": 11207.479,
            "p95": 15221.206,
            "p99": 15881.714
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 82.336631,
            "min": 0.134632,
            "max": 3.623804,
            "p50": 1.534,
            "p95": 3.545,
            "p99": 3.608
          }
        },
        "manual_null": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 33,
          "correct_rate": 0.6875,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 48,
          "pack_injected_questions": 48,
          "families": 12,
          "accepted_correct_id": 9,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 24,
          "over_abstention": 0,
          "rejected_correct_id": 15,
          "attempted_nonnull": 24,
          "guard_valid": 33,
          "semantic_match": 48,
          "accepted_nonnull": 9,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.375,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 1.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 0,
          "proposal_abstention": 24,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 6,
            "evidence_gate_valid": 15
          },
          "evidence_rejection_reasons": {
            "unknown_or_stale_evidence_reference": 15,
            "evidence_does_not_contain_requested_occurrence": 15,
            "attribute_outside_selected_evidence": 58,
            "explicit_separate_identity_context": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 18,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 9,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 6,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 24,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 24,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 33,
          "closed_validation_valid": 33,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 15,
          "raw_accepted_correct_id": 9,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 248329,
            "completion_tokens": 4487,
            "total_tokens": 252816
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 413608.293,
            "min": 3162.838,
            "max": 17213.394,
            "p50": 7094.394,
            "p95": 16896.5,
            "p99": 17211.01
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 82.149441,
            "min": 0.132086,
            "max": 3.660283,
            "p50": 1.533,
            "p95": 3.52,
            "p99": 3.623
          }
        },
        "closure_null": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 46,
          "correct_rate": 0.9583333333333334,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 48,
          "pack_injected_questions": 48,
          "families": 12,
          "accepted_correct_id": 23,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 23,
          "over_abstention": 0,
          "rejected_correct_id": 1,
          "attempted_nonnull": 24,
          "guard_valid": 46,
          "semantic_match": 48,
          "accepted_nonnull": 23,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.9583333333333334,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 0.9583333333333334,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 0,
          "proposal_abstention": 23,
          "validation_failures": {
            "wire_valid": 1,
            "base_guard_valid": 7,
            "evidence_gate_valid": 2
          },
          "evidence_rejection_reasons": {
            "explicit_separate_identity_context": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 18,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 23,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 7,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 24,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 24,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 46,
          "closed_validation_valid": 46,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 2,
          "raw_accepted_correct_id": 23,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 250764,
            "completion_tokens": 4372,
            "total_tokens": 255136
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 405544.564,
            "min": 3165.893,
            "max": 15993.339,
            "p50": 6855.559,
            "p95": 15580.942,
            "p99": 15944.145
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 83.069573,
            "min": 0.133379,
            "max": 3.840008,
            "p50": 1.558,
            "p95": 3.515,
            "p99": 3.729
          }
        },
        "closure_bundle": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 47,
          "correct_rate": 0.9791666666666666,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 48,
          "pack_injected_questions": 48,
          "families": 12,
          "accepted_correct_id": 23,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 24,
          "over_abstention": 0,
          "rejected_correct_id": 1,
          "attempted_nonnull": 24,
          "guard_valid": 47,
          "semantic_match": 48,
          "accepted_nonnull": 23,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.9583333333333334,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 1.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 0,
          "proposal_abstention": 24,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 6,
            "evidence_gate_valid": 1
          },
          "evidence_rejection_reasons": {
            "explicit_separate_identity_context": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 18,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 23,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 6,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 24,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 24,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 47,
          "closed_validation_valid": 47,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 1,
          "raw_accepted_correct_id": 23,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 251753,
            "completion_tokens": 2303,
            "total_tokens": 254056
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 246715.154,
            "min": 3160.163,
            "max": 7332.714,
            "p50": 4881.109,
            "p95": 7195.966,
            "p99": 7302.495
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 82.981164,
            "min": 0.13393,
            "max": 3.620629,
            "p50": 1.611,
            "p95": 3.514,
            "p99": 3.618
          }
        }
      }
    },
    "short": {
      "questions": 48,
      "families": 12,
      "by_variant": {
        "manual_legacy": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 22,
          "correct_rate": 0.4583333333333333,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 29,
          "pack_injected_questions": 29,
          "families": 12,
          "accepted_correct_id": 22,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 1,
          "correct_abstention": 0,
          "over_abstention": 0,
          "rejected_correct_id": 2,
          "attempted_nonnull": 25,
          "guard_valid": 22,
          "semantic_match": 47,
          "accepted_nonnull": 22,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.9166666666666666,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 0.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 1,
          "proposal_abstention": 23,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 7,
            "evidence_gate_valid": 26
          },
          "evidence_rejection_reasons": {
            "abstention_assertion_inconsistent": 23,
            "positive_assertion_support_required": 2,
            "full_surface_structural_identity_not_same": 1,
            "positive_applicability_support_required": 1,
            "explicit_temporal_or_identity_conflict": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 17,
          "production_guard_accepted_wrong_id": 1,
          "shadow_accepted_correct_id": 22,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 7,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 24,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 24,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 22,
          "closed_validation_valid": 22,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 23,
          "raw_guard_failures": 26,
          "raw_accepted_correct_id": 22,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 99505,
            "completion_tokens": 6154,
            "total_tokens": 105659
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 500980.295,
            "min": 5716.011,
            "max": 15824.7,
            "p50": 9990.702,
            "p95": 14257.399,
            "p99": 15488.391
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 28.528344,
            "min": 0.132517,
            "max": 1.30717,
            "p50": 0.857,
            "p95": 1.276,
            "p99": 1.3
          }
        },
        "closure_legacy": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 38,
          "correct_rate": 0.7916666666666666,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 29,
          "pack_injected_questions": 29,
          "families": 12,
          "accepted_correct_id": 23,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 15,
          "over_abstention": 0,
          "rejected_correct_id": 1,
          "attempted_nonnull": 24,
          "guard_valid": 38,
          "semantic_match": 48,
          "accepted_nonnull": 23,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.9583333333333334,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 0.625,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 0,
          "proposal_abstention": 24,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 7,
            "evidence_gate_valid": 10
          },
          "evidence_rejection_reasons": {
            "abstention_assertion_inconsistent": 9,
            "full_surface_structural_identity_not_same": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 17,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 23,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 7,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 24,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 24,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 38,
          "closed_validation_valid": 38,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 9,
          "raw_guard_failures": 10,
          "raw_accepted_correct_id": 23,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 101323,
            "completion_tokens": 5205,
            "total_tokens": 106528
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 428585.532,
            "min": 3435.992,
            "max": 15734.199,
            "p50": 10944.565,
            "p95": 14722.531,
            "p99": 15428.414
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 28.678566,
            "min": 0.132027,
            "max": 1.472649,
            "p50": 0.538,
            "p95": 1.29,
            "p99": 1.397
          }
        },
        "manual_null": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 28,
          "correct_rate": 0.5833333333333334,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 29,
          "pack_injected_questions": 29,
          "families": 12,
          "accepted_correct_id": 6,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 2,
          "correct_abstention": 22,
          "over_abstention": 0,
          "rejected_correct_id": 18,
          "attempted_nonnull": 26,
          "guard_valid": 28,
          "semantic_match": 46,
          "accepted_nonnull": 6,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.25,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 0.9166666666666666,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 1,
          "proposal_abstention": 22,
          "validation_failures": {
            "wire_valid": 1,
            "base_guard_valid": 9,
            "evidence_gate_valid": 20
          },
          "evidence_rejection_reasons": {
            "unknown_or_stale_evidence_reference": 19,
            "evidence_does_not_contain_requested_occurrence": 19,
            "attribute_outside_selected_evidence": 62,
            "full_surface_structural_identity_not_same": 2,
            "unknown_or_stale_attribute_reference": 1,
            "positive_applicability_support_required": 1,
            "full_surface_role_or_composition": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 17,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 6,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 9,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 24,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 24,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 28,
          "closed_validation_valid": 28,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 20,
          "raw_accepted_correct_id": 6,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 100140,
            "completion_tokens": 4704,
            "total_tokens": 104844
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 389719.336,
            "min": 2439.713,
            "max": 16748.349,
            "p50": 8674.966,
            "p95": 15549.863,
            "p99": 16519.467
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 28.702908,
            "min": 0.104936,
            "max": 1.377452,
            "p50": 0.8,
            "p95": 1.288,
            "p99": 1.371
          }
        },
        "closure_null": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 47,
          "correct_rate": 0.9791666666666666,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 29,
          "pack_injected_questions": 29,
          "families": 12,
          "accepted_correct_id": 23,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 24,
          "over_abstention": 0,
          "rejected_correct_id": 1,
          "attempted_nonnull": 24,
          "guard_valid": 47,
          "semantic_match": 48,
          "accepted_nonnull": 23,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.9583333333333334,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 1.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 0,
          "proposal_abstention": 24,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 7,
            "evidence_gate_valid": 1
          },
          "evidence_rejection_reasons": {
            "full_surface_structural_identity_not_same": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 17,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 23,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 7,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 24,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 24,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 47,
          "closed_validation_valid": 47,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 1,
          "raw_accepted_correct_id": 23,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 101470,
            "completion_tokens": 4430,
            "total_tokens": 105900
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 368732.913,
            "min": 2414.487,
            "max": 15131.717,
            "p50": 6489.444,
            "p95": 14658.156,
            "p99": 15052.233
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 27.96892,
            "min": 0.130344,
            "max": 1.327758,
            "p50": 0.543,
            "p95": 1.264,
            "p99": 1.307
          }
        },
        "closure_bundle": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 47,
          "correct_rate": 0.9791666666666666,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 29,
          "pack_injected_questions": 29,
          "families": 12,
          "accepted_correct_id": 23,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 24,
          "over_abstention": 0,
          "rejected_correct_id": 1,
          "attempted_nonnull": 24,
          "guard_valid": 47,
          "semantic_match": 48,
          "accepted_nonnull": 23,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.9583333333333334,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 1.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 0,
          "proposal_abstention": 24,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 7,
            "evidence_gate_valid": 1
          },
          "evidence_rejection_reasons": {
            "full_surface_structural_identity_not_same": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 17,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 23,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 7,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 24,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 24,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 47,
          "closed_validation_valid": 47,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 1,
          "raw_accepted_correct_id": 23,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 102099,
            "completion_tokens": 2280,
            "total_tokens": 104379
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 203763.253,
            "min": 2290.826,
            "max": 6536.655,
            "p50": 3664.539,
            "p95": 6302.441,
            "p99": 6535.824
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 28.816195,
            "min": 0.133329,
            "max": 1.362373,
            "p50": 0.541,
            "p95": 1.301,
            "p99": 1.336
          }
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
| manual_legacy | 11008.71 | 15105.843 | 348440 | 12515 |
| closure_legacy | 11135.836 | 15108.572 | 350811 | 10529 |
| manual_null | 8674.966 | 16361.49 | 348469 | 9191 |
| closure_null | 6855.559 | 15104.244 | 352234 | 8802 |
| closure_bundle | 4125.392 | 7037.379 | 353852 | 4583 |

Preparation timings and pipeline diagnostics:

```json
{
  "preparation_timing_ms": {
    "snapshot_compile": {
      "observations": 12,
      "total": 23.822252871468663,
      "min": 1.8133139237761497,
      "max": 2.42219096980989,
      "p50": 1.93,
      "p95": 2.323,
      "p99": 2.402
    },
    "first_prepare": {
      "observations": 96,
      "total": 5177.011443767697,
      "min": 23.19051302038133,
      "max": 93.7616981100291,
      "p50": 58.805,
      "p95": 80.374,
      "p99": 86.935
    },
    "warm_prepare": {
      "observations": 96,
      "total": 4914.465619716793,
      "min": 22.26202003657818,
      "max": 82.57175190374255,
      "p50": 56.274,
      "p95": 74.252,
      "p99": 81.049
    }
  },
  "pipeline_diagnostics": {
    "confirmation": {
      "targets": 96,
      "positives": 48,
      "exact_core_detected": 96,
      "positive_gold_in_candidates": 48
    }
  }
}
```

Pre-inference terminology-need strata:

```json
{
  "required": {
    "questions": 96,
    "by_variant": {
      "manual_legacy": {
        "planned": 96,
        "questions": 96,
        "positive_planned": 48,
        "no_answer_planned": 48,
        "correct": 45,
        "correct_rate": 0.46875,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 96,
        "pack_injected_requests": 77,
        "pack_injected_questions": 77,
        "families": 12,
        "accepted_correct_id": 45,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 1,
        "correct_abstention": 0,
        "over_abstention": 0,
        "rejected_correct_id": 3,
        "attempted_nonnull": 49,
        "guard_valid": 45,
        "semantic_match": 95,
        "accepted_nonnull": 45,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.9375,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.0,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 48,
        "proposal_wrong_id": 1,
        "proposal_abstention": 47,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 13,
          "evidence_gate_valid": 51
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 47,
          "positive_assertion_support_required": 2,
          "full_surface_structural_identity_not_same": 1,
          "explicit_separate_identity_context": 1,
          "positive_applicability_support_required": 1,
          "explicit_temporal_or_identity_conflict": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 35,
        "production_guard_accepted_wrong_id": 1,
        "shadow_accepted_correct_id": 45,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 13,
        "support_unknown_attributes": {
          "jurisdiction": 60,
          "temporal_status": 60,
          "referent_kind": 48,
          "scope": 48
        },
        "support_present_attributes": {
          "referent_kind": 48,
          "scope": 48,
          "jurisdiction": 36,
          "temporal_status": 36
        },
        "raw_validation_valid": 45,
        "closed_validation_valid": 45,
        "server_added_segments": 0,
        "cases_with_server_added_segments": 0,
        "null_wire_errors": 47,
        "raw_guard_failures": 51,
        "raw_accepted_correct_id": 45,
        "raw_accepted_wrong_id": 0
      },
      "closure_legacy": {
        "planned": 96,
        "questions": 96,
        "positive_planned": 48,
        "no_answer_planned": 48,
        "correct": 73,
        "correct_rate": 0.7604166666666666,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 96,
        "pack_injected_requests": 77,
        "pack_injected_questions": 77,
        "families": 12,
        "accepted_correct_id": 46,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 27,
        "over_abstention": 0,
        "rejected_correct_id": 2,
        "attempted_nonnull": 48,
        "guard_valid": 73,
        "semantic_match": 96,
        "accepted_nonnull": 46,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.9583333333333334,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.5625,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 48,
        "proposal_wrong_id": 0,
        "proposal_abstention": 48,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 13,
          "evidence_gate_valid": 23
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 21,
          "full_surface_structural_identity_not_same": 1,
          "explicit_separate_identity_context": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 35,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 46,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 13,
        "support_unknown_attributes": {
          "jurisdiction": 60,
          "temporal_status": 60,
          "referent_kind": 48,
          "scope": 48
        },
        "support_present_attributes": {
          "referent_kind": 48,
          "scope": 48,
          "jurisdiction": 36,
          "temporal_status": 36
        },
        "raw_validation_valid": 73,
        "closed_validation_valid": 73,
        "server_added_segments": 0,
        "cases_with_server_added_segments": 0,
        "null_wire_errors": 21,
        "raw_guard_failures": 23,
        "raw_accepted_correct_id": 46,
        "raw_accepted_wrong_id": 0
      },
      "manual_null": {
        "planned": 96,
        "questions": 96,
        "positive_planned": 48,
        "no_answer_planned": 48,
        "correct": 61,
        "correct_rate": 0.6354166666666666,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 96,
        "pack_injected_requests": 77,
        "pack_injected_questions": 77,
        "families": 12,
        "accepted_correct_id": 15,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 2,
        "correct_abstention": 46,
        "over_abstention": 0,
        "rejected_correct_id": 33,
        "attempted_nonnull": 50,
        "guard_valid": 61,
        "semantic_match": 94,
        "accepted_nonnull": 15,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.3125,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.9583333333333334,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 48,
        "proposal_wrong_id": 1,
        "proposal_abstention": 46,
        "validation_failures": {
          "wire_valid": 1,
          "base_guard_valid": 15,
          "evidence_gate_valid": 35
        },
        "evidence_rejection_reasons": {
          "unknown_or_stale_evidence_reference": 34,
          "evidence_does_not_contain_requested_occurrence": 34,
          "attribute_outside_selected_evidence": 120,
          "full_surface_structural_identity_not_same": 2,
          "explicit_separate_identity_context": 1,
          "unknown_or_stale_attribute_reference": 1,
          "positive_applicability_support_required": 1,
          "full_surface_role_or_composition": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 35,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 15,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 15,
        "support_unknown_attributes": {
          "jurisdiction": 60,
          "temporal_status": 60,
          "referent_kind": 48,
          "scope": 48
        },
        "support_present_attributes": {
          "referent_kind": 48,
          "scope": 48,
          "jurisdiction": 36,
          "temporal_status": 36
        },
        "raw_validation_valid": 61,
        "closed_validation_valid": 61,
        "server_added_segments": 0,
        "cases_with_server_added_segments": 0,
        "null_wire_errors": 0,
        "raw_guard_failures": 35,
        "raw_accepted_correct_id": 15,
        "raw_accepted_wrong_id": 0
      },
      "closure_null": {
        "planned": 96,
        "questions": 96,
        "positive_planned": 48,
        "no_answer_planned": 48,
        "correct": 93,
        "correct_rate": 0.96875,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 96,
        "pack_injected_requests": 77,
        "pack_injected_questions": 77,
        "families": 12,
        "accepted_correct_id": 46,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 47,
        "over_abstention": 0,
        "rejected_correct_id": 2,
        "attempted_nonnull": 48,
        "guard_valid": 93,
        "semantic_match": 96,
        "accepted_nonnull": 46,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.9583333333333334,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.9791666666666666,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 48,
        "proposal_wrong_id": 0,
        "proposal_abstention": 47,
        "validation_failures": {
          "wire_valid": 1,
          "base_guard_valid": 14,
          "evidence_gate_valid": 3
        },
        "evidence_rejection_reasons": {
          "full_surface_structural_identity_not_same": 1,
          "explicit_separate_identity_context": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 35,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 46,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 14,
        "support_unknown_attributes": {
          "jurisdiction": 60,
          "temporal_status": 60,
          "referent_kind": 48,
          "scope": 48
        },
        "support_present_attributes": {
          "referent_kind": 48,
          "scope": 48,
          "jurisdiction": 36,
          "temporal_status": 36
        },
        "raw_validation_valid": 93,
        "closed_validation_valid": 93,
        "server_added_segments": 0,
        "cases_with_server_added_segments": 0,
        "null_wire_errors": 0,
        "raw_guard_failures": 3,
        "raw_accepted_correct_id": 46,
        "raw_accepted_wrong_id": 0
      },
      "closure_bundle": {
        "planned": 96,
        "questions": 96,
        "positive_planned": 48,
        "no_answer_planned": 48,
        "correct": 94,
        "correct_rate": 0.9791666666666666,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 96,
        "pack_injected_requests": 77,
        "pack_injected_questions": 77,
        "families": 12,
        "accepted_correct_id": 46,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 48,
        "over_abstention": 0,
        "rejected_correct_id": 2,
        "attempted_nonnull": 48,
        "guard_valid": 94,
        "semantic_match": 96,
        "accepted_nonnull": 46,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.9583333333333334,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 1.0,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 48,
        "proposal_wrong_id": 0,
        "proposal_abstention": 48,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 13,
          "evidence_gate_valid": 2
        },
        "evidence_rejection_reasons": {
          "full_surface_structural_identity_not_same": 1,
          "explicit_separate_identity_context": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 35,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 46,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 13,
        "support_unknown_attributes": {
          "jurisdiction": 60,
          "temporal_status": 60,
          "referent_kind": 48,
          "scope": 48
        },
        "support_present_attributes": {
          "referent_kind": 48,
          "scope": 48,
          "jurisdiction": 36,
          "temporal_status": 36
        },
        "raw_validation_valid": 94,
        "closed_validation_valid": 94,
        "server_added_segments": 0,
        "cases_with_server_added_segments": 0,
        "null_wire_errors": 0,
        "raw_guard_failures": 2,
        "raw_accepted_correct_id": 46,
        "raw_accepted_wrong_id": 0
      }
    }
  }
}
```


Paired comparisons:

```json
{
  "manual_legacy_to_closure_legacy": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 28,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.2916666666666667,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.2916666666666667,
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
  "manual_legacy_to_manual_null": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 47,
    "harmful": 31,
    "mean_correctness_delta_all_planned": 0.16666666666666666,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.4895833333333333,
    "harmful_rate_among_comparable": 0.3229166666666667,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "manual_null_to_closure_null": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 33,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.3333333333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.34375,
    "harmful_rate_among_comparable": 0.010416666666666666,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "closure_legacy_to_closure_null": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 21,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.20833333333333334,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.21875,
    "harmful_rate_among_comparable": 0.010416666666666666,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "closure_null_to_closure_bundle": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.010416666666666666,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.010416666666666666,
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

Fresh AI-authored server-closure confirmation on 96 documents from 12 semantic families, balanced between short and long sources. This is not human workplace gold or a deployment risk estimate.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `confirmation`. Cases: 96; families: 12.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| manual_legacy | 45 | 0 | 0 | 0 | 348440 |
| closure_legacy | 46 | 0 | 27 | 0 | 350811 |
| manual_null | 15 | 0 | 46 | 0 | 348469 |
| closure_null | 46 | 0 | 47 | 0 | 352234 |
| closure_bundle | 46 | 0 | 48 | 0 | 353852 |

Split paired comparisons:

```json
{
  "manual_legacy_to_closure_legacy": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 28,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.2916666666666667,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.2916666666666667,
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
  "manual_legacy_to_manual_null": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 47,
    "harmful": 31,
    "mean_correctness_delta_all_planned": 0.16666666666666666,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.4895833333333333,
    "harmful_rate_among_comparable": 0.3229166666666667,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "manual_null_to_closure_null": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 33,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.3333333333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.34375,
    "harmful_rate_among_comparable": 0.010416666666666666,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "closure_legacy_to_closure_null": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 21,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.20833333333333334,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.21875,
    "harmful_rate_among_comparable": 0.010416666666666666,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "closure_null_to_closure_bundle": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.010416666666666666,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.010416666666666666,
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

- All decisions are evaluation-only shadow observations with execution_authority=none; no action is executed.
- The supported-shadow source ownership, positive-support, explicit-conflict and occurrence checks are unchanged across all five arms.
- Server closure adds only the exact requested target sentence and parents of model-selected attribute anchors; it never supplies an entity, assessment or attribute claim.
- Unknown, stale, duplicate or other-occurrence references are not repaired, and original selected evidence is never removed to conceal contradictions.
- A discriminated null wire accepts only request reference and e=null; link branches require SUPPORT and still undergo the complete unchanged gate.
- Source-only bundles enumerate individual compatible owned attributes and a bounded combined set, not semantic entailment or authorization.
- Every arm receives the same full document, complete definitions, ownership inventory and bundle catalog; policies and response transport are the manipulated factors.
- Missing applicability values remain UNKNOWN; the server does not infer missing facts or create new support.
- Sources and annotations are AI authored and independently AI reviewed, not human gold or actual workplace records.
- Document and family provenance is retained; model calls and paired conditions are not independent documents.
