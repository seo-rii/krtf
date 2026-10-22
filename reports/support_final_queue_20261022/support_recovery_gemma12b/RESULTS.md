# Extended frozen experiment

Experiment: `support_recovery`. Model: `ktrf-support-final-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 96; parent documents: 96. Counts: `{'request_count': 192, 'record_count': 192, 'received_count': 192, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

**Evaluation only. Shadow results are EXPERIMENTAL_SIMULATED_APPROVAL, with no execution authority; they are not production approvals.**

| Condition | Decision contract |
|---|---|
| paragraph_all_production | PRODUCTION_GUARD_EVALUATION_ONLY |
| multispan_supported_shadow | EXPERIMENTAL_SIMULATED_APPROVAL |

| Condition | Accepted correct ID | Accepted wrong ID | Rejected wrong ID | Correct abstention | Over-abstention | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| paragraph_all_production | 12 | 0 | 0 | 8 | 0 | 0 | 0 | 0 | 105109 |
| multispan_supported_shadow | 24 | 0 | 1 | 31 | 1 | 0 | 0 | 0 | 128518 |

Production conditions retain the unchanged occurrence authorization guard. Shadow conditions report EXPERIMENTAL_SIMULATED_APPROVAL only and grant no execution authority. Raw model proposals, production guard results and shadow decisions remain separate.

| Condition | Correct ID proposals | Wrong ID proposals | Null proposals |
|---|---:|---:|---:|
| paragraph_all_production | 48 | 0 | 48 |
| multispan_supported_shadow | 47 | 1 | 48 |

Separate guard and simulated-shadow decisions:

| Condition | Production guard correct | Production guard wrong | Simulated shadow correct | Simulated shadow wrong |
|---|---:|---:|---:|---:|
| paragraph_all_production | 35 | 0 | 20 | 0 |
| multispan_supported_shadow | 34 | 1 | 24 | 0 |

Support inventory and validation diagnostics:

```json
{
  "evaluation_population": "FRESH_AI_AUTHORED_CONFIRMATION",
  "support_inventory": {
    "paragraph_all_production": {
      "source_cases": 96,
      "segments": 96,
      "attribute_spans": 151,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 42,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 96
      }
    },
    "multispan_supported_shadow": {
      "source_cases": 96,
      "segments": 279,
      "attribute_spans": 219,
      "source_cases_with_zero_segments": 0,
      "source_cases_with_zero_attributes": 25,
      "ownership_rules": {
        "nearest_named_occurrence_max_four_sentence_units_v1": 96
      }
    }
  },
  "validation_failure_clusters": {
    "paragraph_all_production": {
      "production_guard": {
        "unverified_execution": 13
      },
      "support_gate": {
        "abstention_assertion_inconsistent": 40,
        "unknown_or_stale_attribute_reference": 16,
        "complete_applicability_claims_required": 28,
        "unresolved_candidate_collision": 4,
        "positive_assertion_support_required": 5,
        "full_surface_structural_identity_not_same": 1
      },
      "unknown_attributes": {
        "jurisdiction": 76,
        "temporal_status": 76,
        "referent_kind": 76,
        "scope": 64
      },
      "present_attributes": {
        "jurisdiction": 20,
        "temporal_status": 20,
        "referent_kind": 20,
        "scope": 32
      }
    },
    "multispan_supported_shadow": {
      "production_guard": {
        "unverified_execution": 13
      },
      "support_gate": {
        "evidence_does_not_contain_requested_occurrence": 16,
        "abstention_assertion_inconsistent": 17,
        "attribute_outside_selected_evidence": 6,
        "unknown_or_stale_attribute_reference": 1,
        "full_surface_structural_identity_not_same": 1,
        "positive_assertion_support_required": 1,
        "positive_applicability_support_required": 1
      },
      "unknown_attributes": {
        "jurisdiction": 61,
        "temporal_status": 61,
        "referent_kind": 62,
        "scope": 50
      },
      "present_attributes": {
        "jurisdiction": 35,
        "temporal_status": 35,
        "referent_kind": 34,
        "scope": 46
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
| paragraph_all_production | 5123.681 | 8406.356 | 105109 | 9892 |
| multispan_supported_shadow | 5293.28 | 9860.058 | 128518 | 10702 |

Preparation timings and pipeline diagnostics:

```json
{
  "preparation_timing_ms": {
    "snapshot_compile": {
      "observations": 12,
      "total": 23.85351900011301,
      "min": 1.8580821342766285,
      "max": 2.4131489917635918,
      "p50": 1.944,
      "p95": 2.206,
      "p99": 2.372
    },
    "first_prepare": {
      "observations": 96,
      "total": 1821.502691367641,
      "min": 11.870380025357008,
      "max": 28.84650183841586,
      "p50": 18.913,
      "p95": 24.675,
      "p99": 26.325
    },
    "warm_prepare": {
      "observations": 96,
      "total": 1725.7785126566887,
      "min": 11.369584826752543,
      "max": 27.341709937900305,
      "p50": 17.966,
      "p95": 23.406,
      "p99": 24.915
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
      "paragraph_all_production": {
        "planned": 96,
        "questions": 96,
        "positive_planned": 48,
        "no_answer_planned": 48,
        "correct": 20,
        "correct_rate": 0.20833333333333334,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 96,
        "pack_injected_requests": 66,
        "pack_injected_questions": 66,
        "families": 12,
        "accepted_correct_id": 12,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 0,
        "correct_abstention": 8,
        "over_abstention": 0,
        "rejected_correct_id": 36,
        "attempted_nonnull": 48,
        "guard_valid": 20,
        "semantic_match": 96,
        "accepted_nonnull": 12,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.25,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.16666666666666666,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 48,
        "proposal_wrong_id": 0,
        "proposal_abstention": 48,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 13,
          "evidence_gate_valid": 68
        },
        "evidence_rejection_reasons": {
          "abstention_assertion_inconsistent": 40,
          "unknown_or_stale_attribute_reference": 16,
          "complete_applicability_claims_required": 28,
          "unresolved_candidate_collision": 4,
          "positive_assertion_support_required": 5,
          "full_surface_structural_identity_not_same": 1
        },
        "authorization_mode": "production",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 35,
        "production_guard_accepted_wrong_id": 0,
        "shadow_accepted_correct_id": 20,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 13,
        "support_unknown_attributes": {
          "jurisdiction": 76,
          "temporal_status": 76,
          "referent_kind": 76,
          "scope": 64
        },
        "support_present_attributes": {
          "jurisdiction": 20,
          "temporal_status": 20,
          "referent_kind": 20,
          "scope": 32
        }
      },
      "multispan_supported_shadow": {
        "planned": 96,
        "questions": 96,
        "positive_planned": 48,
        "no_answer_planned": 48,
        "correct": 55,
        "correct_rate": 0.5729166666666666,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 96,
        "pack_injected_requests": 66,
        "pack_injected_questions": 66,
        "families": 12,
        "accepted_correct_id": 24,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 1,
        "correct_abstention": 31,
        "over_abstention": 1,
        "rejected_correct_id": 23,
        "attempted_nonnull": 48,
        "guard_valid": 55,
        "semantic_match": 94,
        "accepted_nonnull": 24,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.5,
        "over_abstention_rate": 0.020833333333333332,
        "correct_abstention_rate": 0.6458333333333334,
        "documents": 96,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 47,
        "proposal_wrong_id": 1,
        "proposal_abstention": 48,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 13,
          "evidence_gate_valid": 41
        },
        "evidence_rejection_reasons": {
          "evidence_does_not_contain_requested_occurrence": 16,
          "abstention_assertion_inconsistent": 17,
          "attribute_outside_selected_evidence": 6,
          "unknown_or_stale_attribute_reference": 1,
          "full_surface_structural_identity_not_same": 1,
          "positive_assertion_support_required": 1,
          "positive_applicability_support_required": 1
        },
        "authorization_mode": "shadow",
        "evaluation_only": true,
        "execution_authority": "none",
        "production_guard_accepted_correct_id": 34,
        "production_guard_accepted_wrong_id": 1,
        "shadow_accepted_correct_id": 24,
        "shadow_accepted_wrong_id": 0,
        "production_base_guard_failures": 13,
        "support_unknown_attributes": {
          "jurisdiction": 61,
          "temporal_status": 61,
          "referent_kind": 62,
          "scope": 50
        },
        "support_present_attributes": {
          "jurisdiction": 35,
          "temporal_status": 35,
          "referent_kind": 34,
          "scope": 46
        }
      }
    }
  }
}
```


Paired comparisons:

```json
{
  "paragraph_all_production_to_multispan_supported_shadow": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 37,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.3645833333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.3854166666666667,
    "harmful_rate_among_comparable": 0.020833333333333332,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.010416666666666666,
    "over_abstention_decrease_rate_among_comparable": 0.0
  }
}
```

Fresh AI-authored confirmation of a method selected on separate reused-source diagnostics. This is not human-verified workplace gold or an operational risk estimate.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `confirmation`. Cases: 96; families: 12.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| paragraph_all_production | 12 | 0 | 8 | 0 | 105109 |
| multispan_supported_shadow | 24 | 0 | 31 | 1 | 128518 |

Split paired comparisons:

```json
{
  "paragraph_all_production_to_multispan_supported_shadow": {
    "planned": 96,
    "questions": 96,
    "comparable": 96,
    "incomplete_or_malformed": 0,
    "helpful": 37,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.3645833333333333,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 12,
    "helpful_rate_among_comparable": 0.3854166666666667,
    "harmful_rate_among_comparable": 0.020833333333333332,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 1,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.010416666666666666,
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
