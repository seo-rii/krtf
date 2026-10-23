# Extended frozen experiment

Experiment: `evidence_closure`. Model: `ktrf-closure-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 96; parent documents: 96. Counts: `{'request_count': 480, 'record_count': 480, 'received_count': 480, 'missing_count': 0, 'error_count': 0, 'malformed_count': 44}`.

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
| manual_legacy | 1 | 0 | 7 | 0 | 0 | 0 | 0 | 0 | 373491 |
| closure_legacy | 31 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 375892 |
| manual_null | 0 | 0 | 0 | 48 | 29 | 19 | 0 | 0 | 374286 |
| closure_null | 0 | 0 | 0 | 48 | 28 | 20 | 0 | 0 | 378303 |
| closure_bundle | 0 | 0 | 0 | 48 | 43 | 5 | 0 | 0 | 379498 |

All arms report experimental shadow judgments without execution authority. Model semantic proposals, pre-closure evidence validation, server-closed validation and the unchanged production occurrence-guard result are separate. Server closure only adds source-bound segments for the selected occurrence and attributes; it does not prove semantic entailment.

| Condition | Correct ID proposals | Wrong ID proposals | Null proposals |
|---|---:|---:|---:|
| manual_legacy | 48 | 7 | 41 |
| closure_legacy | 48 | 5 | 43 |
| manual_null | 0 | 0 | 77 |
| closure_null | 0 | 0 | 76 |
| closure_bundle | 0 | 0 | 91 |

Separate guard and simulated-shadow decisions:

| Condition | Production guard correct | Production guard wrong | Simulated shadow correct | Simulated shadow wrong |
|---|---:|---:|---:|---:|
| manual_legacy | 35 | 7 | 1 | 0 |
| closure_legacy | 35 | 5 | 31 | 0 |
| manual_null | 0 | 0 | 0 | 0 |
| closure_null | 0 | 0 | 0 | 0 |
| closure_bundle | 0 | 0 | 0 | 0 |

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
        "unknown_or_stale_evidence_reference": 54,
        "evidence_does_not_contain_requested_occurrence": 54,
        "attribute_outside_selected_evidence": 180,
        "attribute_owned_by_other_or_unresolved_occurrence": 17,
        "entity_applicability_mismatch": 17,
        "abstention_assertion_inconsistent": 41,
        "positive_assertion_support_required": 5,
        "positive_applicability_support_required": 7,
        "unknown_or_stale_attribute_reference": 1,
        "explicit_jurisdiction_conflict": 1,
        "duplicate_source_reference": 3,
        "full_surface_structural_identity_not_same": 1,
        "explicit_separate_identity_context": 2
      },
      "unknown_attributes": {
        "jurisdiction": 60,
        "temporal_status": 60,
        "referent_kind": 51,
        "scope": 48
      },
      "present_attributes": {
        "referent_kind": 45,
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
        "attribute_outside_selected_evidence": 35,
        "attribute_owned_by_other_or_unresolved_occurrence": 16,
        "entity_applicability_mismatch": 16,
        "abstention_assertion_inconsistent": 43,
        "positive_assertion_support_required": 3,
        "evidence_owned_by_other_or_unresolved_occurrence": 4,
        "positive_applicability_support_required": 5,
        "duplicate_source_reference": 3,
        "unknown_or_stale_evidence_reference": 7,
        "evidence_does_not_contain_requested_occurrence": 7,
        "full_surface_structural_identity_not_same": 1,
        "explicit_separate_identity_context": 2
      },
      "unknown_attributes": {
        "jurisdiction": 60,
        "temporal_status": 60,
        "referent_kind": 53,
        "scope": 48
      },
      "present_attributes": {
        "referent_kind": 43,
        "scope": 48,
        "jurisdiction": 36,
        "temporal_status": 36
      }
    },
    "manual_null": {
      "production_guard": {},
      "support_gate": {
        "selection_envelope_required": 19
      },
      "unknown_attributes": {
        "jurisdiction": 96,
        "temporal_status": 96,
        "referent_kind": 96,
        "scope": 96
      },
      "present_attributes": {}
    },
    "closure_null": {
      "production_guard": {},
      "support_gate": {
        "selection_envelope_required": 20
      },
      "unknown_attributes": {
        "jurisdiction": 96,
        "temporal_status": 96,
        "referent_kind": 96,
        "scope": 96
      },
      "present_attributes": {}
    },
    "closure_bundle": {
      "production_guard": {},
      "support_gate": {
        "selection_envelope_required": 5
      },
      "unknown_attributes": {
        "jurisdiction": 96,
        "temporal_status": 96,
        "referent_kind": 96,
        "scope": 96
      },
      "present_attributes": {}
    }
  }
}
```

Unknown-attribute counts describe absent selected supporting claims. Null proposals leave every attribute UNKNOWN; these counts do not establish that the source lacks the attribute, or that an unstated attribute is false.


Server closure and null-wire diagnostics:

| Condition | Raw correct/wrong | Closed shadow correct/wrong | Raw validation valid | Closed validation valid | Added segments | Cases with additions | Null wire errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| manual_legacy | 1/0 | 1/0 | 1 | 1 | 0 | 0 | 41 |
| closure_legacy | 31/0 | 31/0 | 31 | 31 | 0 | 0 | 43 |
| manual_null | 0/0 | 0/0 | 77 | 77 | 0 | 0 | 0 |
| closure_null | 0/0 | 0/0 | 76 | 76 | 0 | 0 | 0 |
| closure_bundle | 0/0 | 0/0 | 91 | 91 | 0 | 0 | 0 |

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
          "correct": 0,
          "correct_rate": 0.0,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 48,
          "pack_injected_questions": 48,
          "families": 12,
          "accepted_correct_id": 0,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 7,
          "correct_abstention": 0,
          "over_abstention": 0,
          "rejected_correct_id": 24,
          "attempted_nonnull": 31,
          "guard_valid": 0,
          "semantic_match": 41,
          "accepted_nonnull": 0,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": null,
          "accepted_correct_id_rate": 0.0,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 0.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 7,
          "proposal_abstention": 17,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 6,
            "evidence_gate_valid": 48
          },
          "evidence_rejection_reasons": {
            "unknown_or_stale_evidence_reference": 31,
            "evidence_does_not_contain_requested_occurrence": 31,
            "attribute_outside_selected_evidence": 98,
            "attribute_owned_by_other_or_unresolved_occurrence": 17,
            "entity_applicability_mismatch": 17,
            "abstention_assertion_inconsistent": 17,
            "positive_assertion_support_required": 5,
            "positive_applicability_support_required": 7,
            "unknown_or_stale_attribute_reference": 1,
            "explicit_jurisdiction_conflict": 1,
            "duplicate_source_reference": 3,
            "explicit_separate_identity_context": 2
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 18,
          "production_guard_accepted_wrong_id": 7,
          "shadow_accepted_correct_id": 0,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 6,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 27,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 21,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 0,
          "closed_validation_valid": 0,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 17,
          "raw_guard_failures": 48,
          "raw_accepted_correct_id": 0,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 267440,
            "completion_tokens": 8286,
            "total_tokens": 275726
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 443555.952,
            "min": 5573.112,
            "max": 12499.769,
            "p50": 9935.151,
            "p95": 11783.536,
            "p99": 12191.168
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 105.265822,
            "min": 0.134482,
            "max": 4.758725,
            "p50": 3.071,
            "p95": 3.603,
            "p99": 4.335
          }
        },
        "closure_legacy": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 9,
          "correct_rate": 0.1875,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 48,
          "pack_injected_questions": 48,
          "families": 12,
          "accepted_correct_id": 9,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 5,
          "correct_abstention": 0,
          "over_abstention": 0,
          "rejected_correct_id": 15,
          "attempted_nonnull": 29,
          "guard_valid": 9,
          "semantic_match": 43,
          "accepted_nonnull": 9,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.375,
          "over_abstention_rate": 0.0,
          "correct_abstention_rate": 0.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 24,
          "proposal_wrong_id": 5,
          "proposal_abstention": 19,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 6,
            "evidence_gate_valid": 39
          },
          "evidence_rejection_reasons": {
            "attribute_outside_selected_evidence": 35,
            "attribute_owned_by_other_or_unresolved_occurrence": 16,
            "entity_applicability_mismatch": 16,
            "abstention_assertion_inconsistent": 19,
            "positive_assertion_support_required": 3,
            "evidence_owned_by_other_or_unresolved_occurrence": 4,
            "positive_applicability_support_required": 5,
            "unknown_or_stale_evidence_reference": 7,
            "evidence_does_not_contain_requested_occurrence": 7,
            "duplicate_source_reference": 2,
            "explicit_separate_identity_context": 2
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 18,
          "production_guard_accepted_wrong_id": 5,
          "shadow_accepted_correct_id": 9,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 6,
          "support_unknown_attributes": {
            "jurisdiction": 30,
            "temporal_status": 30,
            "referent_kind": 29,
            "scope": 24
          },
          "support_present_attributes": {
            "referent_kind": 19,
            "scope": 24,
            "jurisdiction": 18,
            "temporal_status": 18
          },
          "raw_validation_valid": 9,
          "closed_validation_valid": 9,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 19,
          "raw_guard_failures": 39,
          "raw_accepted_correct_id": 9,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 267728,
            "completion_tokens": 7625,
            "total_tokens": 275353
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 408890.2,
            "min": 5103.613,
            "max": 11504.045,
            "p50": 8728.6,
            "p95": 11189.209,
            "p99": 11503.287
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 97.088567,
            "min": 0.142045,
            "max": 3.792049,
            "p50": 2.998,
            "p95": 3.56,
            "p99": 3.711
          }
        },
        "manual_null": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 24,
          "correct_rate": 0.5,
          "missing": 0,
          "errors": 0,
          "malformed": 4,
          "valid": 44,
          "pack_injected_requests": 48,
          "pack_injected_questions": 48,
          "families": 12,
          "accepted_correct_id": 0,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 24,
          "over_abstention": 20,
          "rejected_correct_id": 0,
          "attempted_nonnull": 0,
          "guard_valid": 44,
          "semantic_match": 24,
          "accepted_nonnull": 0,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": null,
          "accepted_correct_id_rate": 0.0,
          "over_abstention_rate": 0.8333333333333334,
          "correct_abstention_rate": 1.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 0,
          "proposal_wrong_id": 0,
          "proposal_abstention": 44,
          "validation_failures": {
            "wire_valid": 4,
            "base_guard_valid": 4,
            "evidence_gate_valid": 4
          },
          "evidence_rejection_reasons": {
            "selection_envelope_required": 4
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 0,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 0,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 4,
          "support_unknown_attributes": {
            "jurisdiction": 48,
            "temporal_status": 48,
            "referent_kind": 48,
            "scope": 48
          },
          "support_present_attributes": {},
          "raw_validation_valid": 44,
          "closed_validation_valid": 44,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 4,
          "raw_accepted_correct_id": 0,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 267148,
            "completion_tokens": 4579,
            "total_tokens": 271727
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 257451.513,
            "min": 1902.418,
            "max": 38498.331,
            "p50": 2330.349,
            "p95": 38397.799,
            "p99": 38455.647
          },
          "finish_reason_counts": {
            "stop": 44,
            "length": 4
          },
          "execution_validation_ms": {
            "observations": 44,
            "total": 6.508663,
            "min": 0.116718,
            "max": 0.345625,
            "p50": 0.141,
            "p95": 0.174,
            "p99": 0.274
          }
        },
        "closure_null": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 24,
          "correct_rate": 0.5,
          "missing": 0,
          "errors": 0,
          "malformed": 3,
          "valid": 45,
          "pack_injected_requests": 48,
          "pack_injected_questions": 48,
          "families": 12,
          "accepted_correct_id": 0,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 24,
          "over_abstention": 21,
          "rejected_correct_id": 0,
          "attempted_nonnull": 0,
          "guard_valid": 45,
          "semantic_match": 24,
          "accepted_nonnull": 0,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": null,
          "accepted_correct_id_rate": 0.0,
          "over_abstention_rate": 0.875,
          "correct_abstention_rate": 1.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 0,
          "proposal_wrong_id": 0,
          "proposal_abstention": 45,
          "validation_failures": {
            "wire_valid": 3,
            "base_guard_valid": 3,
            "evidence_gate_valid": 3
          },
          "evidence_rejection_reasons": {
            "selection_envelope_required": 3
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 0,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 0,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 3,
          "support_unknown_attributes": {
            "jurisdiction": 48,
            "temporal_status": 48,
            "referent_kind": 48,
            "scope": 48
          },
          "support_present_attributes": {},
          "raw_validation_valid": 45,
          "closed_validation_valid": 45,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 3,
          "raw_accepted_correct_id": 0,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 269689,
            "completion_tokens": 3802,
            "total_tokens": 273491
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 220257.701,
            "min": 1871.072,
            "max": 38838.058,
            "p50": 2350.486,
            "p95": 25970.807,
            "p99": 38658.922
          },
          "finish_reason_counts": {
            "stop": 45,
            "length": 3
          },
          "execution_validation_ms": {
            "observations": 45,
            "total": 6.730989,
            "min": 0.13399,
            "max": 0.216304,
            "p50": 0.142,
            "p95": 0.177,
            "p99": 0.2
          }
        },
        "closure_bundle": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 24,
          "correct_rate": 0.5,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 48,
          "pack_injected_questions": 48,
          "families": 12,
          "accepted_correct_id": 0,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 24,
          "over_abstention": 24,
          "rejected_correct_id": 0,
          "attempted_nonnull": 0,
          "guard_valid": 48,
          "semantic_match": 24,
          "accepted_nonnull": 0,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": null,
          "accepted_correct_id_rate": 0.0,
          "over_abstention_rate": 1.0,
          "correct_abstention_rate": 1.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 0,
          "proposal_wrong_id": 0,
          "proposal_abstention": 48,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 0,
            "evidence_gate_valid": 0
          },
          "evidence_rejection_reasons": {},
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 0,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 0,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 0,
          "support_unknown_attributes": {
            "jurisdiction": 48,
            "temporal_status": 48,
            "referent_kind": 48,
            "scope": 48
          },
          "support_present_attributes": {},
          "raw_validation_valid": 48,
          "closed_validation_valid": 48,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 0,
          "raw_accepted_correct_id": 0,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 270497,
            "completion_tokens": 1531,
            "total_tokens": 272028
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 108482.735,
            "min": 1938.56,
            "max": 3136.364,
            "p50": 2241.52,
            "p95": 2498.343,
            "p99": 3010.906
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 7.15188,
            "min": 0.126516,
            "max": 0.198391,
            "p50": 0.141,
            "p95": 0.184,
            "p99": 0.193
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
          "correct": 1,
          "correct_rate": 0.020833333333333332,
          "missing": 0,
          "errors": 0,
          "malformed": 0,
          "valid": 48,
          "pack_injected_requests": 29,
          "pack_injected_questions": 29,
          "families": 12,
          "accepted_correct_id": 1,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 0,
          "over_abstention": 0,
          "rejected_correct_id": 23,
          "attempted_nonnull": 24,
          "guard_valid": 1,
          "semantic_match": 48,
          "accepted_nonnull": 1,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": 0.0,
          "accepted_correct_id_rate": 0.041666666666666664,
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
            "base_guard_valid": 7,
            "evidence_gate_valid": 47
          },
          "evidence_rejection_reasons": {
            "unknown_or_stale_evidence_reference": 23,
            "evidence_does_not_contain_requested_occurrence": 23,
            "attribute_outside_selected_evidence": 82,
            "abstention_assertion_inconsistent": 24,
            "full_surface_structural_identity_not_same": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 17,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 1,
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
          "raw_validation_valid": 1,
          "closed_validation_valid": 1,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 24,
          "raw_guard_failures": 47,
          "raw_accepted_correct_id": 1,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 106051,
            "completion_tokens": 7475,
            "total_tokens": 113526
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 378794.431,
            "min": 4320.398,
            "max": 11727.146,
            "p50": 8098.508,
            "p95": 10817.87,
            "p99": 11431.959
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 28.056331,
            "min": 0.131005,
            "max": 1.398911,
            "p50": 0.548,
            "p95": 1.284,
            "p99": 1.382
          }
        },
        "closure_legacy": {
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
          "rejected_wrong_id": 0,
          "correct_abstention": 0,
          "over_abstention": 0,
          "rejected_correct_id": 2,
          "attempted_nonnull": 24,
          "guard_valid": 22,
          "semantic_match": 48,
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
          "proposal_wrong_id": 0,
          "proposal_abstention": 24,
          "validation_failures": {
            "wire_valid": 0,
            "base_guard_valid": 7,
            "evidence_gate_valid": 26
          },
          "evidence_rejection_reasons": {
            "abstention_assertion_inconsistent": 24,
            "duplicate_source_reference": 1,
            "full_surface_structural_identity_not_same": 1
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 17,
          "production_guard_accepted_wrong_id": 0,
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
          "null_wire_errors": 24,
          "raw_guard_failures": 26,
          "raw_accepted_correct_id": 22,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 108164,
            "completion_tokens": 6742,
            "total_tokens": 114906
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 342528.143,
            "min": 3274.793,
            "max": 10924.341,
            "p50": 7267.077,
            "p95": 10188.82,
            "p99": 10751.932
          },
          "finish_reason_counts": {
            "stop": 48
          },
          "execution_validation_ms": {
            "observations": 48,
            "total": 28.311907,
            "min": 0.131456,
            "max": 1.292683,
            "p50": 0.532,
            "p95": 1.27,
            "p99": 1.29
          }
        },
        "manual_null": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 24,
          "correct_rate": 0.5,
          "missing": 0,
          "errors": 0,
          "malformed": 15,
          "valid": 33,
          "pack_injected_requests": 29,
          "pack_injected_questions": 29,
          "families": 12,
          "accepted_correct_id": 0,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 24,
          "over_abstention": 9,
          "rejected_correct_id": 0,
          "attempted_nonnull": 0,
          "guard_valid": 33,
          "semantic_match": 24,
          "accepted_nonnull": 0,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": null,
          "accepted_correct_id_rate": 0.0,
          "over_abstention_rate": 0.375,
          "correct_abstention_rate": 1.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 0,
          "proposal_wrong_id": 0,
          "proposal_abstention": 33,
          "validation_failures": {
            "wire_valid": 15,
            "base_guard_valid": 15,
            "evidence_gate_valid": 15
          },
          "evidence_rejection_reasons": {
            "selection_envelope_required": 15
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 0,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 0,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 15,
          "support_unknown_attributes": {
            "jurisdiction": 48,
            "temporal_status": 48,
            "referent_kind": 48,
            "scope": 48
          },
          "support_present_attributes": {},
          "raw_validation_valid": 33,
          "closed_validation_valid": 33,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 15,
          "raw_accepted_correct_id": 0,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 107138,
            "completion_tokens": 12569,
            "total_tokens": 119707
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 627313.871,
            "min": 1460.646,
            "max": 38476.023,
            "p50": 1754.253,
            "p95": 38337.875,
            "p99": 38454.603
          },
          "finish_reason_counts": {
            "stop": 33,
            "length": 15
          },
          "execution_validation_ms": {
            "observations": 33,
            "total": 4.579902,
            "min": 0.114414,
            "max": 0.181559,
            "p50": 0.133,
            "p95": 0.165,
            "p99": 0.177
          }
        },
        "closure_null": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 24,
          "correct_rate": 0.5,
          "missing": 0,
          "errors": 0,
          "malformed": 17,
          "valid": 31,
          "pack_injected_requests": 29,
          "pack_injected_questions": 29,
          "families": 12,
          "accepted_correct_id": 0,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 24,
          "over_abstention": 7,
          "rejected_correct_id": 0,
          "attempted_nonnull": 0,
          "guard_valid": 31,
          "semantic_match": 24,
          "accepted_nonnull": 0,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": null,
          "accepted_correct_id_rate": 0.0,
          "over_abstention_rate": 0.2916666666666667,
          "correct_abstention_rate": 1.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 0,
          "proposal_wrong_id": 0,
          "proposal_abstention": 31,
          "validation_failures": {
            "wire_valid": 17,
            "base_guard_valid": 17,
            "evidence_gate_valid": 17
          },
          "evidence_rejection_reasons": {
            "selection_envelope_required": 17
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 0,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 0,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 17,
          "support_unknown_attributes": {
            "jurisdiction": 48,
            "temporal_status": 48,
            "referent_kind": 48,
            "scope": 48
          },
          "support_present_attributes": {},
          "raw_validation_valid": 31,
          "closed_validation_valid": 31,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 17,
          "raw_accepted_correct_id": 0,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 108614,
            "completion_tokens": 14017,
            "total_tokens": 122631
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 698565.713,
            "min": 1465.959,
            "max": 38375.962,
            "p50": 1760.26,
            "p95": 38203.372,
            "p99": 38330.099
          },
          "finish_reason_counts": {
            "stop": 31,
            "length": 17
          },
          "execution_validation_ms": {
            "observations": 31,
            "total": 4.5047,
            "min": 0.125805,
            "max": 0.216043,
            "p50": 0.14,
            "p95": 0.177,
            "p99": 0.208
          }
        },
        "closure_bundle": {
          "planned": 48,
          "questions": 48,
          "positive_planned": 24,
          "no_answer_planned": 24,
          "correct": 24,
          "correct_rate": 0.5,
          "missing": 0,
          "errors": 0,
          "malformed": 5,
          "valid": 43,
          "pack_injected_requests": 29,
          "pack_injected_questions": 29,
          "families": 12,
          "accepted_correct_id": 0,
          "accepted_wrong_id": 0,
          "rejected_wrong_id": 0,
          "correct_abstention": 24,
          "over_abstention": 19,
          "rejected_correct_id": 0,
          "attempted_nonnull": 0,
          "guard_valid": 43,
          "semantic_match": 24,
          "accepted_nonnull": 0,
          "accepted_wrong_id_rate": 0.0,
          "accepted_wrong_id_rate_among_accepted": null,
          "accepted_correct_id_rate": 0.0,
          "over_abstention_rate": 0.7916666666666666,
          "correct_abstention_rate": 1.0,
          "documents": 48,
          "documents_with_wrong_approval": 0,
          "document_wrong_approval_rate": 0.0,
          "proposal_correct_id": 0,
          "proposal_wrong_id": 0,
          "proposal_abstention": 43,
          "validation_failures": {
            "wire_valid": 5,
            "base_guard_valid": 5,
            "evidence_gate_valid": 5
          },
          "evidence_rejection_reasons": {
            "selection_envelope_required": 5
          },
          "authorization_mode": "shadow",
          "evaluation_only": true,
          "execution_authority": "none",
          "production_guard_accepted_correct_id": 0,
          "production_guard_accepted_wrong_id": 0,
          "shadow_accepted_correct_id": 0,
          "shadow_accepted_wrong_id": 0,
          "production_base_guard_failures": 5,
          "support_unknown_attributes": {
            "jurisdiction": 48,
            "temporal_status": 48,
            "referent_kind": 48,
            "scope": 48
          },
          "support_present_attributes": {},
          "raw_validation_valid": 43,
          "closed_validation_valid": 43,
          "server_added_segments": 0,
          "cases_with_server_added_segments": 0,
          "null_wire_errors": 0,
          "raw_guard_failures": 5,
          "raw_accepted_correct_id": 0,
          "raw_accepted_wrong_id": 0,
          "usage": {
            "prompt_tokens": 109001,
            "completion_tokens": 5124,
            "total_tokens": 114125
          },
          "usage_observed_responses": {
            "prompt_tokens": 48,
            "completion_tokens": 48,
            "total_tokens": 48
          },
          "latency_ms": {
            "observations": 48,
            "total": 261019.736,
            "min": 1340.972,
            "max": 38334.346,
            "p50": 1647.6,
            "p95": 37781.54,
            "p99": 38188.559
          },
          "finish_reason_counts": {
            "stop": 43,
            "length": 5
          },
          "execution_validation_ms": {
            "observations": 43,
            "total": 6.223899,
            "min": 0.129382,
            "max": 0.195024,
            "p50": 0.14,
            "p95": 0.169,
            "p99": 0.185
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
| manual_legacy | 9296.077 | 11661.511 | 373491 | 15761 |
| closure_legacy | 8128.552 | 10967.707 | 375892 | 14367 |
| manual_null | 2160.311 | 38391.164 | 374286 | 17148 |
| closure_null | 2193.194 | 38229.288 | 378303 | 17819 |
| closure_bundle | 2068.584 | 11756.971 | 379498 | 6655 |

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
        "correct": 1,
        "correct_rate": 0.010416666666666666,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 96,
        "pack_injected_requests": 77,
        "pack_injected_questions": 77,
        "families": 12,
        "accepted_correct_id": 1,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 7,
        "correct_abstention": 0,
        "over_abstention": 0,
        "rejected_correct_id": 47,
        "attempted_nonnull": 55,
        "guard_valid": 1,
        "semantic_match": 89,
        "accepted_nonnull": 1,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.020833333333333332,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.0,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 48,
        "proposal_wrong_id": 7,
        "proposal_abstention": 41,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 13,
          "evidence_gate_valid": 95
        },
        "evidence_rejection_reasons": {
          "unknown_or_stale_evidence_reference": 54,
          "evidence_does_not_contain_requested_occurrence": 54,
          "attribute_outside_selected_evidence": 180,
          "attribute_owned_by_other_or_unresolved_occurrence": 17,
          "entity_applicability_mismatch": 17,
          "abstention_assertion_inconsistent": 41,
          "positive_assertion_support_required": 5,
          "positive_applicability_support_required": 7,
          "unknown_or_stale_attribute_reference": 1,
          "explicit_jurisdiction_conflict": 1,
          "duplicate_source_reference": 3,
          "full_surface_structural_identity_not_same": 1,
          "explicit_separate_identity_context": 2
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 35,
        "production_guard_accepted_wrong_id": 7,
        "shadow_accepted_correct_id": 1,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 13,
        "support_unknown_attributes": {
          "jurisdiction": 60,
          "temporal_status": 60,
          "referent_kind": 51,
          "scope": 48
        },
        "support_present_attributes": {
          "referent_kind": 45,
          "scope": 48,
          "jurisdiction": 36,
          "temporal_status": 36
        },
        "raw_validation_valid": 1,
        "closed_validation_valid": 1,
        "server_added_segments": 0,
        "cases_with_server_added_segments": 0,
        "null_wire_errors": 41,
        "raw_guard_failures": 95,
        "raw_accepted_correct_id": 1,
        "raw_accepted_wrong_id": 0
      },
      "closure_legacy": {
        "planned": 96,
        "questions": 96,
        "positive_planned": 48,
        "no_answer_planned": 48,
        "correct": 31,
        "correct_rate": 0.3229166666666667,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 96,
        "pack_injected_requests": 77,
        "pack_injected_questions": 77,
        "families": 12,
        "accepted_correct_id": 31,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 5,
        "correct_abstention": 0,
        "over_abstention": 0,
        "rejected_correct_id": 17,
        "attempted_nonnull": 53,
        "guard_valid": 31,
        "semantic_match": 91,
        "accepted_nonnull": 31,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.6458333333333334,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.0,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 48,
        "proposal_wrong_id": 5,
        "proposal_abstention": 43,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 13,
          "evidence_gate_valid": 65
        },
        "evidence_rejection_reasons": {
          "attribute_outside_selected_evidence": 35,
          "attribute_owned_by_other_or_unresolved_occurrence": 16,
          "entity_applicability_mismatch": 16,
          "abstention_assertion_inconsistent": 43,
          "positive_assertion_support_required": 3,
          "evidence_owned_by_other_or_unresolved_occurrence": 4,
          "positive_applicability_support_required": 5,
          "duplicate_source_reference": 3,
          "unknown_or_stale_evidence_reference": 7,
          "evidence_does_not_contain_requested_occurrence": 7,
          "full_surface_structural_identity_not_same": 1,
          "explicit_separate_identity_context": 2
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 35,
        "production_guard_accepted_wrong_id": 5,
        "shadow_accepted_correct_id": 31,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 13,
        "support_unknown_attributes": {
          "jurisdiction": 60,
          "temporal_status": 60,
          "referent_kind": 53,
          "scope": 48
        },
        "support_present_attributes": {
          "referent_kind": 43,
          "scope": 48,
          "jurisdiction": 36,
          "temporal_status": 36
        },
        "raw_validation_valid": 31,
        "closed_validation_valid": 31,
        "server_added_segments": 0,
        "cases_with_server_added_segments": 0,
        "null_wire_errors": 43,
        "raw_guard_failures": 65,
        "raw_accepted_correct_id": 31,
        "raw_accepted_wrong_id": 0
      },
      "manual_null": {
        "planned": 96,
        "questions": 96,
        "positive_planned": 48,
        "no_answer_planned": 48,
        "correct": 48,
        "correct_rate": 0.5,
        "missing": 0,
        "errors": 0,
        "malformed": 19,
        "valid": 77,
        "pack_injected_requests": 77,
        "pack_injected_questions": 77,
        "families": 12,
        "accepted_correct_id": 0,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 48,
        "over_abstention": 29,
        "rejected_correct_id": 0,
        "attempted_nonnull": 0,
        "guard_valid": 77,
        "semantic_match": 48,
        "accepted_nonnull": 0,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": null,
        "accepted_correct_id_rate": 0.0,
        "over_abstention_rate": 0.6041666666666666,
        "correct_abstention_rate": 1.0,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 0,
        "proposal_wrong_id": 0,
        "proposal_abstention": 77,
        "validation_failures": {
          "wire_valid": 19,
          "base_guard_valid": 19,
          "evidence_gate_valid": 19
        },
        "evidence_rejection_reasons": {
          "selection_envelope_required": 19
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 0,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 0,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 19,
        "support_unknown_attributes": {
          "jurisdiction": 96,
          "temporal_status": 96,
          "referent_kind": 96,
          "scope": 96
        },
        "support_present_attributes": {},
        "raw_validation_valid": 77,
        "closed_validation_valid": 77,
        "server_added_segments": 0,
        "cases_with_server_added_segments": 0,
        "null_wire_errors": 0,
        "raw_guard_failures": 19,
        "raw_accepted_correct_id": 0,
        "raw_accepted_wrong_id": 0
      },
      "closure_null": {
        "planned": 96,
        "questions": 96,
        "positive_planned": 48,
        "no_answer_planned": 48,
        "correct": 48,
        "correct_rate": 0.5,
        "missing": 0,
        "errors": 0,
        "malformed": 20,
        "valid": 76,
        "pack_injected_requests": 77,
        "pack_injected_questions": 77,
        "families": 12,
        "accepted_correct_id": 0,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 48,
        "over_abstention": 28,
        "rejected_correct_id": 0,
        "attempted_nonnull": 0,
        "guard_valid": 76,
        "semantic_match": 48,
        "accepted_nonnull": 0,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": null,
        "accepted_correct_id_rate": 0.0,
        "over_abstention_rate": 0.5833333333333334,
        "correct_abstention_rate": 1.0,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 0,
        "proposal_wrong_id": 0,
        "proposal_abstention": 76,
        "validation_failures": {
          "wire_valid": 20,
          "base_guard_valid": 20,
          "evidence_gate_valid": 20
        },
        "evidence_rejection_reasons": {
          "selection_envelope_required": 20
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 0,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 0,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 20,
        "support_unknown_attributes": {
          "jurisdiction": 96,
          "temporal_status": 96,
          "referent_kind": 96,
          "scope": 96
        },
        "support_present_attributes": {},
        "raw_validation_valid": 76,
        "closed_validation_valid": 76,
        "server_added_segments": 0,
        "cases_with_server_added_segments": 0,
        "null_wire_errors": 0,
        "raw_guard_failures": 20,
        "raw_accepted_correct_id": 0,
        "raw_accepted_wrong_id": 0
      },
      "closure_bundle": {
        "planned": 96,
        "questions": 96,
        "positive_planned": 48,
        "no_answer_planned": 48,
        "correct": 48,
        "correct_rate": 0.5,
        "missing": 0,
        "errors": 0,
        "malformed": 5,
        "valid": 91,
        "pack_injected_requests": 77,
        "pack_injected_questions": 77,
        "families": 12,
        "accepted_correct_id": 0,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 48,
        "over_abstention": 43,
        "rejected_correct_id": 0,
        "attempted_nonnull": 0,
        "guard_valid": 91,
        "semantic_match": 48,
        "accepted_nonnull": 0,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": null,
        "accepted_correct_id_rate": 0.0,
        "over_abstention_rate": 0.8958333333333334,
        "correct_abstention_rate": 1.0,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 0,
        "proposal_wrong_id": 0,
        "proposal_abstention": 91,
        "validation_failures": {
          "wire_valid": 5,
          "base_guard_valid": 5,
          "evidence_gate_valid": 5
        },
        "evidence_rejection_reasons": {
          "selection_envelope_required": 5
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 0,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 0,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 5,
        "support_unknown_attributes": {
          "jurisdiction": 96,
          "temporal_status": 96,
          "referent_kind": 96,
          "scope": 96
        },
        "support_present_attributes": {},
        "raw_validation_valid": 91,
        "closed_validation_valid": 91,
        "server_added_segments": 0,
        "cases_with_server_added_segments": 0,
        "null_wire_errors": 0,
        "raw_guard_failures": 5,
        "raw_accepted_correct_id": 0,
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
    "helpful": 30,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.3125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.3125,
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
    "comparable": 77,
    "incomplete_or_malformed": 19,
    "helpful": 48,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.4895833333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.6233766233766234,
    "harmful_rate_among_comparable": 0.012987012987012988,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 29,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.37662337662337664,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "manual_null_to_closure_null": {
    "planned": 96,
    "questions": 96,
    "comparable": 69,
    "incomplete_or_malformed": 27,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
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
  "closure_legacy_to_closure_null": {
    "planned": 96,
    "questions": 96,
    "comparable": 76,
    "incomplete_or_malformed": 20,
    "helpful": 48,
    "harmful": 16,
    "mean_correctness_delta_all_planned": 0.17708333333333334,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.631578947368421,
    "harmful_rate_among_comparable": 0.21052631578947367,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 28,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.3684210526315789,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "closure_null_to_closure_bundle": {
    "planned": 96,
    "questions": 96,
    "comparable": 75,
    "incomplete_or_malformed": 21,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
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

Fresh AI-authored server-closure confirmation on 96 documents from 12 semantic families, balanced between short and long sources. This is not human workplace gold or a deployment risk estimate.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `confirmation`. Cases: 96; families: 12.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| manual_legacy | 1 | 0 | 0 | 0 | 373491 |
| closure_legacy | 31 | 0 | 0 | 0 | 375892 |
| manual_null | 0 | 0 | 48 | 29 | 374286 |
| closure_null | 0 | 0 | 48 | 28 | 378303 |
| closure_bundle | 0 | 0 | 48 | 43 | 379498 |

Split paired comparisons:

```json
{
  "manual_legacy_to_closure_legacy": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 30,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.3125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.3125,
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
    "comparable": 77,
    "incomplete_or_malformed": 19,
    "helpful": 48,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.4895833333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.6233766233766234,
    "harmful_rate_among_comparable": 0.012987012987012988,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 29,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.37662337662337664,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "manual_null_to_closure_null": {
    "planned": 96,
    "questions": 96,
    "comparable": 69,
    "incomplete_or_malformed": 27,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
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
  "closure_legacy_to_closure_null": {
    "planned": 96,
    "questions": 96,
    "comparable": 76,
    "incomplete_or_malformed": 20,
    "helpful": 48,
    "harmful": 16,
    "mean_correctness_delta_all_planned": 0.17708333333333334,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.631578947368421,
    "harmful_rate_among_comparable": 0.21052631578947367,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 28,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.3684210526315789,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "closure_null_to_closure_bundle": {
    "planned": 96,
    "questions": 96,
    "comparable": 75,
    "incomplete_or_malformed": 21,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
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
