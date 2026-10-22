# Extended frozen experiment

Experiment: `support_recovery`. Model: `ktrf-support-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 64; parent documents: 64. Counts: `{'request_count': 512, 'record_count': 512, 'received_count': 512, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

**Evaluation only. Shadow results are EXPERIMENTAL_SIMULATED_APPROVAL, with no execution authority; they are not production approvals.**

| Condition | Decision contract |
|---|---|
| paragraph_all_production | PRODUCTION_GUARD_EVALUATION_ONLY |
| multispan_all_production | PRODUCTION_GUARD_EVALUATION_ONLY |
| multispan_observed_production | PRODUCTION_GUARD_EVALUATION_ONLY |
| multispan_supported_production | PRODUCTION_GUARD_EVALUATION_ONLY |
| paragraph_all_shadow | EXPERIMENTAL_SIMULATED_APPROVAL |
| multispan_all_shadow | EXPERIMENTAL_SIMULATED_APPROVAL |
| multispan_observed_shadow | EXPERIMENTAL_SIMULATED_APPROVAL |
| multispan_supported_shadow | EXPERIMENTAL_SIMULATED_APPROVAL |

| Condition | Accepted correct ID | Accepted wrong ID | Rejected wrong ID | Correct abstention | Over-abstention | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| paragraph_all_production | 7 | 0 | 2 | 4 | 1 | 0 | 0 | 0 | 68041 |
| multispan_all_production | 7 | 0 | 0 | 6 | 1 | 0 | 0 | 0 | 83538 |
| multispan_observed_production | 13 | 0 | 0 | 9 | 2 | 0 | 0 | 0 | 84238 |
| multispan_supported_production | 16 | 0 | 0 | 22 | 0 | 0 | 0 | 0 | 84429 |
| paragraph_all_shadow | 12 | 0 | 0 | 5 | 1 | 0 | 0 | 0 | 68176 |
| multispan_all_shadow | 8 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 83233 |
| multispan_observed_shadow | 15 | 0 | 0 | 10 | 1 | 0 | 0 | 0 | 84469 |
| multispan_supported_shadow | 19 | 0 | 0 | 23 | 0 | 0 | 0 | 0 | 84268 |

Production conditions retain the unchanged occurrence authorization guard. Shadow conditions report EXPERIMENTAL_SIMULATED_APPROVAL only and grant no execution authority. Raw model proposals, production guard results and shadow decisions remain separate.

| Condition | Correct ID proposals | Wrong ID proposals | Null proposals |
|---|---:|---:|---:|
| paragraph_all_production | 30 | 1 | 32 |
| multispan_all_production | 31 | 0 | 33 |
| multispan_observed_production | 30 | 0 | 34 |
| multispan_supported_production | 32 | 0 | 32 |
| paragraph_all_shadow | 31 | 0 | 33 |
| multispan_all_shadow | 32 | 0 | 32 |
| multispan_observed_shadow | 31 | 0 | 33 |
| multispan_supported_shadow | 32 | 0 | 32 |

Separate guard and simulated-shadow decisions:

| Condition | Production guard correct | Production guard wrong | Simulated shadow correct | Simulated shadow wrong |
|---|---:|---:|---:|---:|
| paragraph_all_production | 21 | 0 | 12 | 0 |
| multispan_all_production | 22 | 0 | 8 | 0 |
| multispan_observed_production | 21 | 0 | 15 | 0 |
| multispan_supported_production | 23 | 0 | 19 | 0 |
| paragraph_all_shadow | 22 | 0 | 12 | 0 |
| multispan_all_shadow | 23 | 0 | 8 | 0 |
| multispan_observed_shadow | 22 | 0 | 15 | 0 |
| multispan_supported_shadow | 23 | 0 | 19 | 0 |

Support inventory and validation diagnostics:

```json
{
  "evaluation_population": "REUSED_SEALED_SOURCE_DIAGNOSTIC",
  "support_inventory": {
    "paragraph_all_production": {
      "source_cases": 64,
      "segments": 64,
      "attribute_spans": 99,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 27,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 64
      }
    },
    "multispan_all_production": {
      "source_cases": 64,
      "segments": 192,
      "attribute_spans": 147,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 13,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 64
      }
    },
    "multispan_observed_production": {
      "source_cases": 64,
      "segments": 192,
      "attribute_spans": 147,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 13,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 64
      }
    },
    "multispan_supported_production": {
      "source_cases": 64,
      "segments": 192,
      "attribute_spans": 147,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 13,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 64
      }
    },
    "paragraph_all_shadow": {
      "source_cases": 64,
      "segments": 64,
      "attribute_spans": 99,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 27,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 64
      }
    },
    "multispan_all_shadow": {
      "source_cases": 64,
      "segments": 192,
      "attribute_spans": 147,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 13,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 64
      }
    },
    "multispan_observed_shadow": {
      "source_cases": 64,
      "segments": 192,
      "attribute_spans": 147,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 13,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 64
      }
    },
    "multispan_supported_shadow": {
      "source_cases": 64,
      "segments": 192,
      "attribute_spans": 147,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 13,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 64
      }
    }
  },
  "validation_failure_clusters": {
    "paragraph_all_production": {
      "production_guard": {
        "unverified_execution": 10
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 28,
        "positive_assertion_support_required": 4,
        "complete_applicability_claims_required": 17,
        "unknown_or_stale_attribute_reference": 8,
        "unresolved_candidate_collision": 2,
        "full_surface_structural_identity_not_same": 2,
        "full_surface_role_or_composition": 1,
        "explicit_applicability_conflict": 1
      },
      "unknown_attributes": {
        "jurisdiction": 50,
        "temporal_status": 47,
        "referent_kind": 47,
        "scope": 44
      },
      "present_attributes": {
        "jurisdiction": 14,
        "temporal_status": 17,
        "referent_kind": 17,
        "scope": 20
      }
    },
    "multispan_all_production": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 27,
        "evidence_does_not_contain_requested_occurrence": 15,
        "positive_assertion_support_required": 4,
        "complete_applicability_claims_required": 7,
        "attribute_outside_selected_evidence": 4,
        "full_surface_structural_identity_not_same": 1,
        "duplicate_source_reference": 1,
        "explicit_applicability_conflict": 1
      },
      "unknown_attributes": {
        "jurisdiction": 40,
        "temporal_status": 40,
        "referent_kind": 40,
        "scope": 33
      },
      "present_attributes": {
        "jurisdiction": 24,
        "temporal_status": 24,
        "referent_kind": 24,
        "scope": 31
      }
    },
    "multispan_observed_production": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 25,
        "evidence_does_not_contain_requested_occurrence": 6,
        "attribute_outside_selected_evidence": 10,
        "full_surface_structural_identity_not_same": 1,
        "positive_assertion_support_required": 1,
        "explicit_applicability_conflict": 1,
        "entity_applicability_mismatch": 1
      },
      "unknown_attributes": {
        "jurisdiction": 43,
        "temporal_status": 42,
        "referent_kind": 43,
        "scope": 35
      },
      "present_attributes": {
        "jurisdiction": 21,
        "temporal_status": 22,
        "referent_kind": 21,
        "scope": 29
      }
    },
    "multispan_supported_production": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "evidence_does_not_contain_requested_occurrence": 6,
        "abstention_assertion_inconsistent": 10,
        "attribute_outside_selected_evidence": 6,
        "full_surface_structural_identity_not_same": 1,
        "explicit_applicability_conflict": 1
      },
      "unknown_attributes": {
        "jurisdiction": 41,
        "temporal_status": 40,
        "referent_kind": 40,
        "scope": 33
      },
      "present_attributes": {
        "jurisdiction": 23,
        "temporal_status": 24,
        "referent_kind": 24,
        "scope": 31
      }
    },
    "paragraph_all_shadow": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 28,
        "positive_assertion_support_required": 4,
        "complete_applicability_claims_required": 17,
        "unknown_or_stale_attribute_reference": 8,
        "unresolved_candidate_collision": 2,
        "full_surface_structural_identity_not_same": 1,
        "explicit_applicability_conflict": 1
      },
      "unknown_attributes": {
        "jurisdiction": 50,
        "temporal_status": 47,
        "referent_kind": 47,
        "scope": 44
      },
      "present_attributes": {
        "jurisdiction": 14,
        "temporal_status": 17,
        "referent_kind": 17,
        "scope": 20
      }
    },
    "multispan_all_shadow": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 27,
        "evidence_does_not_contain_requested_occurrence": 15,
        "positive_assertion_support_required": 4,
        "complete_applicability_claims_required": 8,
        "attribute_outside_selected_evidence": 5,
        "full_surface_structural_identity_not_same": 1,
        "explicit_applicability_conflict": 1
      },
      "unknown_attributes": {
        "jurisdiction": 40,
        "temporal_status": 40,
        "referent_kind": 40,
        "scope": 32
      },
      "present_attributes": {
        "jurisdiction": 24,
        "temporal_status": 24,
        "referent_kind": 24,
        "scope": 32
      }
    },
    "multispan_observed_shadow": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "evidence_does_not_contain_requested_occurrence": 6,
        "abstention_assertion_inconsistent": 23,
        "attribute_outside_selected_evidence": 12,
        "full_surface_structural_identity_not_same": 1,
        "explicit_applicability_conflict": 1,
        "entity_applicability_mismatch": 1
      },
      "unknown_attributes": {
        "jurisdiction": 42,
        "temporal_status": 41,
        "referent_kind": 42,
        "scope": 33
      },
      "present_attributes": {
        "jurisdiction": 22,
        "temporal_status": 23,
        "referent_kind": 22,
        "scope": 31
      }
    },
    "multispan_supported_shadow": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "evidence_does_not_contain_requested_occurrence": 8,
        "attribute_outside_selected_evidence": 6,
        "entity_applicability_mismatch": 1,
        "abstention_assertion_inconsistent": 9,
        "full_surface_structural_identity_not_same": 1,
        "explicit_applicability_conflict": 1
      },
      "unknown_attributes": {
        "jurisdiction": 41,
        "temporal_status": 40,
        "referent_kind": 41,
        "scope": 33
      },
      "present_attributes": {
        "jurisdiction": 23,
        "temporal_status": 24,
        "referent_kind": 23,
        "scope": 31
      }
    }
  }
}
```

Unknown-attribute counts describe absent selected supporting claims. Null proposals leave every attribute UNKNOWN; these counts do not establish that the source lacks the attribute, or that an unstated attribute is false.


Raw semantic selection and occurrence-bound approval are separate; synthetic/public proxy samples do not certify deployment risk.

Request wall time includes local parsing and execution validation; preparation costs are measured separately. Snapshot compilation counts only actual compilations, excluding cached zero-cost entries. Shared-host measurements are descriptive, not service-load SLOs.

| Condition | p50 ms | p95 ms | Input tokens | Output tokens |
|---|---:|---:|---:|---:|
| paragraph_all_production | 4919.615 | 8325.406 | 68041 | 6354 |
| multispan_all_production | 4853.61 | 9968.575 | 83538 | 7349 |
| multispan_observed_production | 4884.39 | 10725.08 | 84238 | 7079 |
| multispan_supported_production | 4906.173 | 10958.574 | 84429 | 7027 |
| paragraph_all_shadow | 4855.87 | 8553.145 | 68176 | 6437 |
| multispan_all_shadow | 4928.719 | 9826.114 | 83233 | 7270 |
| multispan_observed_shadow | 4829.906 | 10986.91 | 84469 | 7160 |
| multispan_supported_shadow | 4951.868 | 10398.543 | 84268 | 6982 |

Preparation timings and pipeline diagnostics:

```json
{
  "preparation_timing_ms": {
    "snapshot_compile": {
      "observations": 8,
      "total": 15.407251194119453,
      "min": 1.8156510777771473,
      "max": 2.2759500425308943,
      "p50": 1.888,
      "p95": 2.163,
      "p99": 2.253
    },
    "first_prepare": {
      "observations": 64,
      "total": 993.2304108515382,
      "min": 10.149924084544182,
      "max": 21.730758948251605,
      "p50": 15.519,
      "p95": 18.881,
      "p99": 20.496
    },
    "warm_prepare": {
      "observations": 64,
      "total": 935.0696329493076,
      "min": 9.722265182062984,
      "max": 20.45822492800653,
      "p50": 14.544,
      "p95": 17.845,
      "p99": 19.454
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
      "paragraph_all_production": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 11,
        "correct_rate": 0.171875,
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
        "correct_abstention": 4,
        "over_abstention": 1,
        "rejected_correct_id": 23,
        "attempted_nonnull": 32,
        "guard_valid": 11,
        "semantic_match": 61,
        "accepted_nonnull": 7,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.21875,
        "over_abstention_rate": 0.03125,
        "correct_abstention_rate": 0.125,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 30,
        "proposal_wrong_id": 1,
        "proposal_abstention": 32,
        "validation_failures": {
          "wire_valid": 1,
          "base_guard_valid": 11,
          "evidence_gate_valid": 48
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 28,
          "positive_assertion_support_required": 4,
          "complete_applicability_claims_required": 17,
          "unknown_or_stale_attribute_reference": 8,
          "unresolved_candidate_collision": 2,
          "full_surface_structural_identity_not_same": 2,
          "full_surface_role_or_composition": 1,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "production",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 21,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 12,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 11,
        "support_unknown_attributes": {
          "jurisdiction": 50,
          "temporal_status": 47,
          "referent_kind": 47,
          "scope": 44
        },
        "support_present_attributes": {
          "jurisdiction": 14,
          "temporal_status": 17,
          "referent_kind": 17,
          "scope": 20
        }
      },
      "multispan_all_production": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 13,
        "correct_rate": 0.203125,
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
        "correct_abstention": 6,
        "over_abstention": 1,
        "rejected_correct_id": 24,
        "attempted_nonnull": 31,
        "guard_valid": 13,
        "semantic_match": 63,
        "accepted_nonnull": 7,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.21875,
        "over_abstention_rate": 0.03125,
        "correct_abstention_rate": 0.1875,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 31,
        "proposal_wrong_id": 0,
        "proposal_abstention": 33,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 50
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 27,
          "evidence_does_not_contain_requested_occurrence": 15,
          "positive_assertion_support_required": 4,
          "complete_applicability_claims_required": 7,
          "attribute_outside_selected_evidence": 4,
          "full_surface_structural_identity_not_same": 1,
          "duplicate_source_reference": 1,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "production",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 22,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 8,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 9,
        "support_unknown_attributes": {
          "jurisdiction": 40,
          "temporal_status": 40,
          "referent_kind": 40,
          "scope": 33
        },
        "support_present_attributes": {
          "jurisdiction": 24,
          "temporal_status": 24,
          "referent_kind": 24,
          "scope": 31
        }
      },
      "multispan_observed_production": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 22,
        "correct_rate": 0.34375,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 13,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 9,
        "over_abstention": 2,
        "rejected_correct_id": 17,
        "attempted_nonnull": 30,
        "guard_valid": 22,
        "semantic_match": 62,
        "accepted_nonnull": 13,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.40625,
        "over_abstention_rate": 0.0625,
        "correct_abstention_rate": 0.28125,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 30,
        "proposal_wrong_id": 0,
        "proposal_abstention": 34,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 40
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 25,
          "evidence_does_not_contain_requested_occurrence": 6,
          "attribute_outside_selected_evidence": 10,
          "full_surface_structural_identity_not_same": 1,
          "positive_assertion_support_required": 1,
          "explicit_applicability_conflict": 1,
          "entity_applicability_mismatch": 1
        },
        "authorization_mode": "production",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 21,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 15,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 9,
        "support_unknown_attributes": {
          "jurisdiction": 43,
          "temporal_status": 42,
          "referent_kind": 43,
          "scope": 35
        },
        "support_present_attributes": {
          "jurisdiction": 21,
          "temporal_status": 22,
          "referent_kind": 21,
          "scope": 29
        }
      },
      "multispan_supported_production": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 38,
        "correct_rate": 0.59375,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 16,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 22,
        "over_abstention": 0,
        "rejected_correct_id": 16,
        "attempted_nonnull": 32,
        "guard_valid": 38,
        "semantic_match": 64,
        "accepted_nonnull": 16,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.5,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.6875,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 32,
        "proposal_wrong_id": 0,
        "proposal_abstention": 32,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 23
        },
        "evidence_rejection_reasons": {
          "evidence_does_not_contain_requested_occurrence": 6,
          "abstention_assertion_inconsistent": 10,
          "attribute_outside_selected_evidence": 6,
          "full_surface_structural_identity_not_same": 1,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "production",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 23,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 19,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 9,
        "support_unknown_attributes": {
          "jurisdiction": 41,
          "temporal_status": 40,
          "referent_kind": 40,
          "scope": 33
        },
        "support_present_attributes": {
          "jurisdiction": 23,
          "temporal_status": 24,
          "referent_kind": 24,
          "scope": 31
        }
      },
      "paragraph_all_shadow": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 17,
        "correct_rate": 0.265625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 12,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 5,
        "over_abstention": 1,
        "rejected_correct_id": 19,
        "attempted_nonnull": 31,
        "guard_valid": 17,
        "semantic_match": 63,
        "accepted_nonnull": 12,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.375,
        "over_abstention_rate": 0.03125,
        "correct_abstention_rate": 0.15625,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 31,
        "proposal_wrong_id": 0,
        "proposal_abstention": 33,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 47
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 28,
          "positive_assertion_support_required": 4,
          "complete_applicability_claims_required": 17,
          "unknown_or_stale_attribute_reference": 8,
          "unresolved_candidate_collision": 2,
          "full_surface_structural_identity_not_same": 1,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 22,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 12,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 9,
        "support_unknown_attributes": {
          "jurisdiction": 50,
          "temporal_status": 47,
          "referent_kind": 47,
          "scope": 44
        },
        "support_present_attributes": {
          "jurisdiction": 14,
          "temporal_status": 17,
          "referent_kind": 17,
          "scope": 20
        }
      },
      "multispan_all_shadow": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 13,
        "correct_rate": 0.203125,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 8,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 5,
        "over_abstention": 0,
        "rejected_correct_id": 24,
        "attempted_nonnull": 32,
        "guard_valid": 13,
        "semantic_match": 64,
        "accepted_nonnull": 8,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.25,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.15625,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 32,
        "proposal_wrong_id": 0,
        "proposal_abstention": 32,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 51
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 27,
          "evidence_does_not_contain_requested_occurrence": 15,
          "positive_assertion_support_required": 4,
          "complete_applicability_claims_required": 8,
          "attribute_outside_selected_evidence": 5,
          "full_surface_structural_identity_not_same": 1,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 23,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 8,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 9,
        "support_unknown_attributes": {
          "jurisdiction": 40,
          "temporal_status": 40,
          "referent_kind": 40,
          "scope": 32
        },
        "support_present_attributes": {
          "jurisdiction": 24,
          "temporal_status": 24,
          "referent_kind": 24,
          "scope": 32
        }
      },
      "multispan_observed_shadow": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 25,
        "correct_rate": 0.390625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 15,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 10,
        "over_abstention": 1,
        "rejected_correct_id": 16,
        "attempted_nonnull": 31,
        "guard_valid": 25,
        "semantic_match": 63,
        "accepted_nonnull": 15,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.46875,
        "over_abstention_rate": 0.03125,
        "correct_abstention_rate": 0.3125,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 31,
        "proposal_wrong_id": 0,
        "proposal_abstention": 33,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 39
        },
        "evidence_rejection_reasons": {
          "evidence_does_not_contain_requested_occurrence": 6,
          "abstention_assertion_inconsistent": 23,
          "attribute_outside_selected_evidence": 12,
          "full_surface_structural_identity_not_same": 1,
          "explicit_applicability_conflict": 1,
          "entity_applicability_mismatch": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 22,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 15,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 9,
        "support_unknown_attributes": {
          "jurisdiction": 42,
          "temporal_status": 41,
          "referent_kind": 42,
          "scope": 33
        },
        "support_present_attributes": {
          "jurisdiction": 22,
          "temporal_status": 23,
          "referent_kind": 22,
          "scope": 31
        }
      },
      "multispan_supported_shadow": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 42,
        "correct_rate": 0.65625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 19,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 23,
        "over_abstention": 0,
        "rejected_correct_id": 13,
        "attempted_nonnull": 32,
        "guard_valid": 42,
        "semantic_match": 64,
        "accepted_nonnull": 19,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.59375,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.71875,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 32,
        "proposal_wrong_id": 0,
        "proposal_abstention": 32,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 22
        },
        "evidence_rejection_reasons": {
          "evidence_does_not_contain_requested_occurrence": 8,
          "attribute_outside_selected_evidence": 6,
          "entity_applicability_mismatch": 1,
          "abstention_assertion_inconsistent": 9,
          "full_surface_structural_identity_not_same": 1,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 23,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 19,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 9,
        "support_unknown_attributes": {
          "jurisdiction": 41,
          "temporal_status": 40,
          "referent_kind": 41,
          "scope": 33
        },
        "support_present_attributes": {
          "jurisdiction": 23,
          "temporal_status": 24,
          "referent_kind": 23,
          "scope": 31
        }
      }
    }
  }
}
```


Paired comparisons:

```json
{
  "paragraph_all_production_to_multispan_all_production": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 7,
    "harmful": 5,
    "mean_correctness_delta_all_planned": 0.03125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.109375,
    "harmful_rate_among_comparable": 0.078125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.015625,
    "over_abstention_decrease_rate_among_comparable": 0.015625
  },
  "paragraph_all_production_to_multispan_observed_production": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 13,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.171875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.203125,
    "harmful_rate_among_comparable": 0.03125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.015625,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_supported_production": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 28,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.421875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.4375,
    "harmful_rate_among_comparable": 0.015625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.015625
  },
  "paragraph_all_production_to_paragraph_all_shadow": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 8,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.09375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.125,
    "harmful_rate_among_comparable": 0.03125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_all_shadow": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 9,
    "harmful": 7,
    "mean_correctness_delta_all_planned": 0.03125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.140625,
    "harmful_rate_among_comparable": 0.109375,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.015625
  },
  "paragraph_all_production_to_multispan_observed_shadow": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 19,
    "harmful": 5,
    "mean_correctness_delta_all_planned": 0.21875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.296875,
    "harmful_rate_among_comparable": 0.078125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_supported_shadow": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 33,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.484375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.515625,
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

Reused-source support-recovery diagnostic; earlier split labels do not identify a new holdout.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `confirmation`. Cases: 48; families: 6.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| paragraph_all_production | 5 | 0 | 3 | 0 | 50688 |
| multispan_all_production | 5 | 0 | 5 | 1 | 63070 |
| multispan_observed_production | 10 | 0 | 6 | 0 | 63502 |
| multispan_supported_production | 12 | 0 | 16 | 0 | 63825 |
| paragraph_all_shadow | 8 | 0 | 5 | 0 | 50872 |
| multispan_all_shadow | 5 | 0 | 4 | 0 | 62798 |
| multispan_observed_shadow | 10 | 0 | 7 | 0 | 63735 |
| multispan_supported_shadow | 12 | 0 | 16 | 0 | 63605 |

Split paired comparisons:

```json
{
  "paragraph_all_production_to_multispan_all_production": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 5,
    "harmful": 3,
    "mean_correctness_delta_all_planned": 0.041666666666666664,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.10416666666666667,
    "harmful_rate_among_comparable": 0.0625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.020833333333333332,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_observed_production": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 10,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.16666666666666666,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.20833333333333334,
    "harmful_rate_among_comparable": 0.041666666666666664,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_supported_production": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 21,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.4166666666666667,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.4375,
    "harmful_rate_among_comparable": 0.020833333333333332,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_paragraph_all_shadow": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.10416666666666667,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.125,
    "harmful_rate_among_comparable": 0.020833333333333332,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_all_shadow": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 5,
    "mean_correctness_delta_all_planned": 0.020833333333333332,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.125,
    "harmful_rate_among_comparable": 0.10416666666666667,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_observed_shadow": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 13,
    "harmful": 4,
    "mean_correctness_delta_all_planned": 0.1875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.2708333333333333,
    "harmful_rate_among_comparable": 0.08333333333333333,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_supported_shadow": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 22,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.4166666666666667,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.4583333333333333,
    "harmful_rate_among_comparable": 0.041666666666666664,
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
| paragraph_all_production | 2 | 0 | 1 | 1 | 17353 |
| multispan_all_production | 2 | 0 | 1 | 0 | 20468 |
| multispan_observed_production | 3 | 0 | 3 | 2 | 20736 |
| multispan_supported_production | 4 | 0 | 6 | 0 | 20604 |
| paragraph_all_shadow | 4 | 0 | 0 | 1 | 17304 |
| multispan_all_shadow | 3 | 0 | 1 | 0 | 20435 |
| multispan_observed_shadow | 5 | 0 | 3 | 1 | 20734 |
| multispan_supported_shadow | 7 | 0 | 7 | 0 | 20663 |

Split paired comparisons:

```json
{
  "paragraph_all_production_to_multispan_all_production": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.125,
    "harmful_rate_among_comparable": 0.125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0625
  },
  "paragraph_all_production_to_multispan_observed_production": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.1875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.1875,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0625,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_supported_production": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 7,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.4375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.4375,
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
  "paragraph_all_production_to_paragraph_all_shadow": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.0625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.125,
    "harmful_rate_among_comparable": 0.0625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_all_shadow": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.0625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.1875,
    "harmful_rate_among_comparable": 0.125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 1,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0625
  },
  "paragraph_all_production_to_multispan_observed_shadow": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.3125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.375,
    "harmful_rate_among_comparable": 0.0625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_supported_shadow": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 11,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.6875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.6875,
    "harmful_rate_among_comparable": 0.0,
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

- All decisions are evaluation-only shadow observations with execution_authority=none; no action is executed.
- Production conditions retain the unchanged production occurrence guard; shadow conditions separately test source support without granting production authorization.
- Source facts and labels are AI authored and independently AI reviewed, not human gold or actual workplace records.
- Missing applicability values remain UNKNOWN and are never inferred to be true.
- Ownership uses known glossary spellings and a bounded nearest-mention discourse rule; it is not semantic entailment.
- All conditions retain complete source text and complete candidate definitions; only evidence policy and experimental judgment differ.
- Candidate retrieval and occurrence binding are produced by the actual resolver; gold is used only for scoring.
- Family clusters are statistical units; reused diagnostic sources are not an independent validation population.
- The paragraph baseline includes the new source-ownership and explicit-conflict checks; it is not numerically interchangeable with the preceding bundle-control baseline.
