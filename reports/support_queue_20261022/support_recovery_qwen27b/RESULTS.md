# Extended frozen experiment

Experiment: `support_recovery`. Model: `ktrf-support-qwen27b-bf16`. Status: `COMPLETE`.

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
| paragraph_all_production | 7 | 0 | 1 | 19 | 0 | 0 | 0 | 0 | 63735 |
| multispan_all_production | 12 | 0 | 1 | 21 | 0 | 0 | 0 | 0 | 78305 |
| multispan_observed_production | 21 | 0 | 1 | 27 | 0 | 0 | 0 | 0 | 79256 |
| multispan_supported_production | 22 | 0 | 0 | 22 | 0 | 0 | 0 | 0 | 79287 |
| paragraph_all_shadow | 12 | 0 | 2 | 19 | 1 | 0 | 0 | 0 | 63924 |
| multispan_all_shadow | 16 | 0 | 0 | 20 | 1 | 0 | 0 | 0 | 78037 |
| multispan_observed_shadow | 27 | 0 | 0 | 28 | 0 | 0 | 0 | 0 | 79399 |
| multispan_supported_shadow | 26 | 0 | 0 | 21 | 0 | 0 | 0 | 0 | 79116 |

Production conditions retain the unchanged occurrence authorization guard. Shadow conditions report EXPERIMENTAL_SIMULATED_APPROVAL only and grant no execution authority. Raw model proposals, production guard results and shadow decisions remain separate.

| Condition | Correct ID proposals | Wrong ID proposals | Null proposals |
|---|---:|---:|---:|
| paragraph_all_production | 32 | 1 | 31 |
| multispan_all_production | 32 | 1 | 29 |
| multispan_observed_production | 32 | 1 | 30 |
| multispan_supported_production | 32 | 0 | 32 |
| paragraph_all_shadow | 30 | 1 | 31 |
| multispan_all_shadow | 31 | 0 | 30 |
| multispan_observed_shadow | 32 | 0 | 31 |
| multispan_supported_shadow | 32 | 0 | 32 |

Separate guard and simulated-shadow decisions:

| Condition | Production guard correct | Production guard wrong | Simulated shadow correct | Simulated shadow wrong |
|---|---:|---:|---:|---:|
| paragraph_all_production | 23 | 1 | 12 | 0 |
| multispan_all_production | 23 | 1 | 15 | 0 |
| multispan_observed_production | 23 | 0 | 26 | 0 |
| multispan_supported_production | 23 | 0 | 26 | 0 |
| paragraph_all_shadow | 22 | 1 | 12 | 0 |
| multispan_all_shadow | 22 | 0 | 16 | 0 |
| multispan_observed_shadow | 23 | 0 | 27 | 0 |
| multispan_supported_shadow | 23 | 0 | 26 | 0 |

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
        "unverified_execution": 9
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 12,
        "positive_assertion_support_required": 11,
        "complete_applicability_claims_required": 19,
        "unknown_or_stale_attribute_reference": 9,
        "unresolved_candidate_collision": 2,
        "full_surface_structural_identity_not_same": 1,
        "explicit_applicability_conflict": 1
      },
      "unknown_attributes": {
        "jurisdiction": 50,
        "temporal_status": 46,
        "referent_kind": 46,
        "scope": 43
      },
      "present_attributes": {
        "jurisdiction": 14,
        "temporal_status": 18,
        "referent_kind": 18,
        "scope": 21
      }
    },
    "multispan_all_production": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "evidence_does_not_contain_requested_occurrence": 9,
        "positive_assertion_support_required": 9,
        "complete_applicability_claims_required": 10,
        "abstention_assertion_inconsistent": 8,
        "full_surface_structural_identity_not_same": 1,
        "attribute_outside_selected_evidence": 1,
        "explicit_applicability_conflict": 1,
        "unknown_or_stale_attribute_reference": 1
      },
      "unknown_attributes": {
        "jurisdiction": 41,
        "temporal_status": 40,
        "referent_kind": 40,
        "scope": 32
      },
      "present_attributes": {
        "jurisdiction": 23,
        "temporal_status": 24,
        "referent_kind": 24,
        "scope": 32
      }
    },
    "multispan_observed_production": {
      "production_guard": {
        "unverified_execution": 10
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 3,
        "positive_assertion_support_required": 1,
        "explicit_separate_identity_context": 1,
        "full_surface_structural_identity_not_same": 2,
        "evidence_does_not_contain_requested_occurrence": 3,
        "attribute_outside_selected_evidence": 3,
        "explicit_applicability_conflict": 1
      },
      "unknown_attributes": {
        "jurisdiction": 42,
        "temporal_status": 40,
        "referent_kind": 40,
        "scope": 34
      },
      "present_attributes": {
        "jurisdiction": 22,
        "temporal_status": 24,
        "referent_kind": 24,
        "scope": 30
      }
    },
    "multispan_supported_production": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 10,
        "evidence_does_not_contain_requested_occurrence": 5,
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
    "paragraph_all_shadow": {
      "production_guard": {
        "unverified_execution": 8
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 11,
        "positive_assertion_support_required": 11,
        "complete_applicability_claims_required": 17,
        "explicit_temporal_or_identity_conflict": 1,
        "unknown_or_stale_attribute_reference": 8,
        "full_surface_structural_identity_not_same": 1,
        "explicit_applicability_conflict": 1,
        "unresolved_candidate_collision": 1
      },
      "unknown_attributes": {
        "jurisdiction": 50,
        "temporal_status": 46,
        "referent_kind": 46,
        "scope": 44
      },
      "present_attributes": {
        "jurisdiction": 14,
        "temporal_status": 18,
        "referent_kind": 18,
        "scope": 20
      }
    },
    "multispan_all_shadow": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "evidence_does_not_contain_requested_occurrence": 7,
        "abstention_assertion_inconsistent": 10,
        "positive_assertion_support_required": 7,
        "complete_applicability_claims_required": 7,
        "full_surface_structural_identity_not_same": 1,
        "attribute_outside_selected_evidence": 1,
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
    "multispan_observed_shadow": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 3,
        "evidence_does_not_contain_requested_occurrence": 3,
        "full_surface_structural_identity_not_same": 1,
        "attribute_outside_selected_evidence": 2,
        "explicit_applicability_conflict": 1
      },
      "unknown_attributes": {
        "jurisdiction": 42,
        "temporal_status": 40,
        "referent_kind": 40,
        "scope": 34
      },
      "present_attributes": {
        "jurisdiction": 22,
        "temporal_status": 24,
        "referent_kind": 24,
        "scope": 30
      }
    },
    "multispan_supported_shadow": {
      "production_guard": {
        "unverified_execution": 9
      },
      "support_gate": {
        "evidence_does_not_contain_requested_occurrence": 4,
        "abstention_assertion_inconsistent": 11,
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
    }
  }
}
```

Unknown-attribute counts describe absent selected supporting claims. Null proposals leave every attribute UNKNOWN; these counts do not establish that the source lacks the attribute, or that an unstated attribute is false.


Raw semantic selection and occurrence-bound approval are separate; synthetic/public proxy samples do not certify deployment risk.

Request wall time includes local parsing and execution validation; preparation costs are measured separately. Snapshot compilation counts only actual compilations, excluding cached zero-cost entries. Shared-host measurements are descriptive, not service-load SLOs.

| Condition | p50 ms | p95 ms | Input tokens | Output tokens |
|---|---:|---:|---:|---:|
| paragraph_all_production | 6670.362 | 11699.349 | 63735 | 5385 |
| multispan_all_production | 7424.665 | 14527.514 | 78305 | 6308 |
| multispan_observed_production | 6899.798 | 15099.21 | 79256 | 6077 |
| multispan_supported_production | 7043.28 | 15240.581 | 79287 | 6340 |
| paragraph_all_shadow | 6511.355 | 12039.621 | 63924 | 5314 |
| multispan_all_shadow | 6991.582 | 14489.967 | 78037 | 6205 |
| multispan_observed_shadow | 7684.512 | 15017.521 | 79399 | 6089 |
| multispan_supported_shadow | 6536.465 | 15189.223 | 79116 | 6317 |

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
        "correct": 26,
        "correct_rate": 0.40625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 7,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 1,
        "correct_abstention": 19,
        "over_abstention": 0,
        "rejected_correct_id": 25,
        "attempted_nonnull": 33,
        "guard_valid": 26,
        "semantic_match": 63,
        "accepted_nonnull": 7,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.21875,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.59375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 32,
        "proposal_wrong_id": 1,
        "proposal_abstention": 31,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 33
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 12,
          "positive_assertion_support_required": 11,
          "complete_applicability_claims_required": 19,
          "unknown_or_stale_attribute_reference": 9,
          "unresolved_candidate_collision": 2,
          "full_surface_structural_identity_not_same": 1,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "production",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 23,
        "production_guard_accepted_wrong_id": 1,
        "shadow_accepted_correct_id": 12,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 9,
        "support_unknown_attributes": {
          "jurisdiction": 50,
          "temporal_status": 46,
          "referent_kind": 46,
          "scope": 43
        },
        "support_present_attributes": {
          "jurisdiction": 14,
          "temporal_status": 18,
          "referent_kind": 18,
          "scope": 21
        }
      },
      "multispan_all_production": {
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
        "accepted_correct_id": 12,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 1,
        "correct_abstention": 21,
        "over_abstention": 0,
        "rejected_correct_id": 20,
        "attempted_nonnull": 33,
        "guard_valid": 33,
        "semantic_match": 63,
        "accepted_nonnull": 12,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.375,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.65625,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 32,
        "proposal_wrong_id": 1,
        "proposal_abstention": 29,
        "validation_failures": {
          "wire_valid": 2,
          "base_guard_valid": 11,
          "evidence_gate_valid": 28
        },
        "evidence_rejection_reasons": {
          "evidence_does_not_contain_requested_occurrence": 9,
          "positive_assertion_support_required": 9,
          "complete_applicability_claims_required": 10,
          "abstention_assertion_inconsistent": 8,
          "full_surface_structural_identity_not_same": 1,
          "attribute_outside_selected_evidence": 1,
          "explicit_applicability_conflict": 1,
          "unknown_or_stale_attribute_reference": 1
        },
        "authorization_mode": "production",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 23,
        "production_guard_accepted_wrong_id": 1,
        "shadow_accepted_correct_id": 15,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 11,
        "support_unknown_attributes": {
          "jurisdiction": 41,
          "temporal_status": 40,
          "referent_kind": 40,
          "scope": 32
        },
        "support_present_attributes": {
          "jurisdiction": 23,
          "temporal_status": 24,
          "referent_kind": 24,
          "scope": 32
        }
      },
      "multispan_observed_production": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 48,
        "correct_rate": 0.75,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 21,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 1,
        "correct_abstention": 27,
        "over_abstention": 0,
        "rejected_correct_id": 11,
        "attempted_nonnull": 33,
        "guard_valid": 48,
        "semantic_match": 63,
        "accepted_nonnull": 21,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.65625,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.84375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 32,
        "proposal_wrong_id": 1,
        "proposal_abstention": 30,
        "validation_failures": {
          "wire_valid": 1,
          "base_guard_valid": 11,
          "evidence_gate_valid": 11
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 3,
          "positive_assertion_support_required": 1,
          "explicit_separate_identity_context": 1,
          "full_surface_structural_identity_not_same": 2,
          "evidence_does_not_contain_requested_occurrence": 3,
          "attribute_outside_selected_evidence": 3,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "production",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 23,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 26,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 11,
        "support_unknown_attributes": {
          "jurisdiction": 42,
          "temporal_status": 40,
          "referent_kind": 40,
          "scope": 34
        },
        "support_present_attributes": {
          "jurisdiction": 22,
          "temporal_status": 24,
          "referent_kind": 24,
          "scope": 30
        }
      },
      "multispan_supported_production": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 44,
        "correct_rate": 0.6875,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 22,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 22,
        "over_abstention": 0,
        "rejected_correct_id": 10,
        "attempted_nonnull": 32,
        "guard_valid": 44,
        "semantic_match": 64,
        "accepted_nonnull": 22,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.6875,
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
          "evidence_gate_valid": 16
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 10,
          "evidence_does_not_contain_requested_occurrence": 5,
          "full_surface_structural_identity_not_same": 1,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "production",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 23,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 26,
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
      "paragraph_all_shadow": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 31,
        "correct_rate": 0.484375,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 12,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 2,
        "correct_abstention": 19,
        "over_abstention": 1,
        "rejected_correct_id": 18,
        "attempted_nonnull": 32,
        "guard_valid": 32,
        "semantic_match": 61,
        "accepted_nonnull": 12,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.375,
        "over_abstention_rate": 0.03125,
        "correct_abstention_rate": 0.59375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 30,
        "proposal_wrong_id": 1,
        "proposal_abstention": 31,
        "validation_failures": {
          "wire_valid": 2,
          "base_guard_valid": 10,
          "evidence_gate_valid": 32
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 11,
          "positive_assertion_support_required": 11,
          "complete_applicability_claims_required": 17,
          "explicit_temporal_or_identity_conflict": 1,
          "unknown_or_stale_attribute_reference": 8,
          "full_surface_structural_identity_not_same": 1,
          "explicit_applicability_conflict": 1,
          "unresolved_candidate_collision": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 22,
        "production_guard_accepted_wrong_id": 1,
        "shadow_accepted_correct_id": 12,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 10,
        "support_unknown_attributes": {
          "jurisdiction": 50,
          "temporal_status": 46,
          "referent_kind": 46,
          "scope": 44
        },
        "support_present_attributes": {
          "jurisdiction": 14,
          "temporal_status": 18,
          "referent_kind": 18,
          "scope": 20
        }
      },
      "multispan_all_shadow": {
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
        "accepted_correct_id": 16,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 20,
        "over_abstention": 1,
        "rejected_correct_id": 15,
        "attempted_nonnull": 31,
        "guard_valid": 36,
        "semantic_match": 63,
        "accepted_nonnull": 16,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.5,
        "over_abstention_rate": 0.03125,
        "correct_abstention_rate": 0.625,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 31,
        "proposal_wrong_id": 0,
        "proposal_abstention": 30,
        "validation_failures": {
          "wire_valid": 3,
          "base_guard_valid": 12,
          "evidence_gate_valid": 28
        },
        "evidence_rejection_reasons": {
          "evidence_does_not_contain_requested_occurrence": 7,
          "abstention_assertion_inconsistent": 10,
          "positive_assertion_support_required": 7,
          "complete_applicability_claims_required": 7,
          "full_surface_structural_identity_not_same": 1,
          "attribute_outside_selected_evidence": 1,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 22,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 16,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 12,
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
      "multispan_observed_shadow": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 55,
        "correct_rate": 0.859375,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 27,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 28,
        "over_abstention": 0,
        "rejected_correct_id": 5,
        "attempted_nonnull": 32,
        "guard_valid": 55,
        "semantic_match": 64,
        "accepted_nonnull": 27,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.84375,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.875,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 32,
        "proposal_wrong_id": 0,
        "proposal_abstention": 31,
        "validation_failures": {
          "wire_valid": 1,
          "base_guard_valid": 10,
          "evidence_gate_valid": 9
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 3,
          "evidence_does_not_contain_requested_occurrence": 3,
          "full_surface_structural_identity_not_same": 1,
          "attribute_outside_selected_evidence": 2,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 23,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 27,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 10,
        "support_unknown_attributes": {
          "jurisdiction": 42,
          "temporal_status": 40,
          "referent_kind": 40,
          "scope": 34
        },
        "support_present_attributes": {
          "jurisdiction": 22,
          "temporal_status": 24,
          "referent_kind": 24,
          "scope": 30
        }
      },
      "multispan_supported_shadow": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 47,
        "correct_rate": 0.734375,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 46,
        "pack_injected_questions": 46,
        "families": 8,
        "accepted_correct_id": 26,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 21,
        "over_abstention": 0,
        "rejected_correct_id": 6,
        "attempted_nonnull": 32,
        "guard_valid": 47,
        "semantic_match": 64,
        "accepted_nonnull": 26,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.8125,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.65625,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 32,
        "proposal_wrong_id": 0,
        "proposal_abstention": 32,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 17
        },
        "evidence_rejection_reasons": {
          "evidence_does_not_contain_requested_occurrence": 4,
          "abstention_assertion_inconsistent": 11,
          "full_surface_structural_identity_not_same": 1,
          "explicit_applicability_conflict": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 23,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 26,
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
    "helpful": 15,
    "harmful": 8,
    "mean_correctness_delta_all_planned": 0.109375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.234375,
    "harmful_rate_among_comparable": 0.125,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_observed_production": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 24,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.34375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.375,
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
  "paragraph_all_production_to_multispan_supported_production": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 21,
    "harmful": 3,
    "mean_correctness_delta_all_planned": 0.28125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.328125,
    "harmful_rate_among_comparable": 0.046875,
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
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.078125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.09375,
    "harmful_rate_among_comparable": 0.015625,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.015625,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_all_shadow": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 15,
    "harmful": 5,
    "mean_correctness_delta_all_planned": 0.15625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.234375,
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
  "paragraph_all_production_to_multispan_observed_shadow": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 29,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.453125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.453125,
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
  "paragraph_all_production_to_multispan_supported_shadow": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 24,
    "harmful": 3,
    "mean_correctness_delta_all_planned": 0.328125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.375,
    "harmful_rate_among_comparable": 0.046875,
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

Reused-source support-recovery diagnostic; earlier split labels do not identify a new holdout.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `confirmation`. Cases: 48; families: 6.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| paragraph_all_production | 5 | 0 | 14 | 0 | 47480 |
| multispan_all_production | 8 | 0 | 15 | 0 | 59124 |
| multispan_observed_production | 16 | 0 | 19 | 0 | 59768 |
| multispan_supported_production | 16 | 0 | 15 | 0 | 59961 |
| paragraph_all_shadow | 8 | 0 | 13 | 1 | 47712 |
| multispan_all_shadow | 10 | 0 | 16 | 1 | 58890 |
| multispan_observed_shadow | 20 | 0 | 21 | 0 | 59908 |
| multispan_supported_shadow | 18 | 0 | 16 | 0 | 59718 |

Split paired comparisons:

```json
{
  "paragraph_all_production_to_multispan_all_production": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 11,
    "harmful": 7,
    "mean_correctness_delta_all_planned": 0.08333333333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.22916666666666666,
    "harmful_rate_among_comparable": 0.14583333333333334,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_observed_production": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 18,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.3333333333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.375,
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
    "helpful": 15,
    "harmful": 3,
    "mean_correctness_delta_all_planned": 0.25,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.3125,
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
  "paragraph_all_production_to_paragraph_all_shadow": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.041666666666666664,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.0625,
    "harmful_rate_among_comparable": 0.020833333333333332,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.020833333333333332,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_all_shadow": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 10,
    "harmful": 3,
    "mean_correctness_delta_all_planned": 0.14583333333333334,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.20833333333333334,
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
  "paragraph_all_production_to_multispan_observed_shadow": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 22,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.4583333333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.4583333333333333,
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
  "paragraph_all_production_to_multispan_supported_shadow": {
    "planned": 48,
    "questions": 48,
    "comparable": 48,
    "incomplete_or_malformed": 0,
    "helpful": 17,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.3125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 6,
    "helpful_rate_among_comparable": 0.3541666666666667,
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
| paragraph_all_production | 2 | 0 | 5 | 0 | 16255 |
| multispan_all_production | 4 | 0 | 6 | 0 | 19181 |
| multispan_observed_production | 5 | 0 | 8 | 0 | 19488 |
| multispan_supported_production | 6 | 0 | 7 | 0 | 19326 |
| paragraph_all_shadow | 4 | 0 | 6 | 0 | 16212 |
| multispan_all_shadow | 6 | 0 | 4 | 0 | 19147 |
| multispan_observed_shadow | 7 | 0 | 7 | 0 | 19491 |
| multispan_supported_shadow | 8 | 0 | 5 | 0 | 19398 |

Split paired comparisons:

```json
{
  "paragraph_all_production_to_multispan_all_production": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 4,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.1875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.25,
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
  "paragraph_all_production_to_multispan_observed_production": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.375,
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
  "paragraph_all_production_to_multispan_supported_production": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.375,
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
  "paragraph_all_production_to_paragraph_all_shadow": {
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
    "helpful": 5,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.1875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.3125,
    "harmful_rate_among_comparable": 0.125,
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
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "paragraph_all_production_to_multispan_supported_shadow": {
    "planned": 16,
    "questions": 16,
    "comparable": 16,
    "incomplete_or_malformed": 0,
    "helpful": 7,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 2,
    "helpful_rate_among_comparable": 0.4375,
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

- All decisions are evaluation-only shadow observations with execution_authority=none; no action is executed.
- Production conditions retain the unchanged production occurrence guard; shadow conditions separately test source support without granting production authorization.
- Source facts and labels are AI authored and independently AI reviewed, not human gold or actual workplace records.
- Missing applicability values remain UNKNOWN and are never inferred to be true.
- Ownership uses known glossary spellings and a bounded nearest-mention discourse rule; it is not semantic entailment.
- All conditions retain complete source text and complete candidate definitions; only evidence policy and experimental judgment differ.
- Candidate retrieval and occurrence binding are produced by the actual resolver; gold is used only for scoring.
- Family clusters are statistical units; reused diagnostic sources are not an independent validation population.
- The paragraph baseline includes the new source-ownership and explicit-conflict checks; it is not numerically interchangeable with the preceding bundle-control baseline.
