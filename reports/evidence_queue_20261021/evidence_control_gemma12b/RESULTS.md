# Extended frozen experiment

Experiment: `evidence_control`. Model: `ktrf-evidence-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 64; parent documents: 64. Counts: `{'request_count': 256, 'record_count': 256, 'received_count': 256, 'missing_count': 0, 'error_count': 0, 'malformed_count': 5}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Accepted correct ID | Accepted wrong ID | Rejected wrong ID | Correct abstention | Over-abstention | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| plain_matched | 23 | 4 | 0 | 28 | 0 | 0 | 0 | 0 | 48158 |
| ktrf_matched | 22 | 6 | 0 | 26 | 0 | 0 | 0 | 0 | 50068 |
| ktrf_evidence_ids | 23 | 0 | 1 | 31 | 0 | 0 | 0 | 0 | 94849 |
| ktrf_evidence_offsets | 0 | 0 | 1 | 19 | 0 | 5 | 0 | 0 | 98642 |

Schema-valid model proposals precede the same production occurrence guard in all arms. Retrieved ambiguous candidates are visible for judgment but gain no execution authority. All 64 cases are previously exposed development data; results are adaptive diagnostics.

| Condition | Correct ID proposals | Wrong ID proposals | Null proposals |
|---|---:|---:|---:|
| plain_matched | 32 | 4 | 28 |
| ktrf_matched | 31 | 6 | 26 |
| ktrf_evidence_ids | 32 | 1 | 31 |
| ktrf_evidence_offsets | 27 | 1 | 30 |

Raw semantic selection and occurrence-bound approval are separate; synthetic/public proxy samples do not certify deployment risk.

Request wall time includes local parsing and execution validation; preparation costs are measured separately. Snapshot compilation counts only actual compilations, excluding cached zero-cost entries. Shared-host measurements are descriptive, not service-load SLOs.

| Condition | p50 ms | p95 ms | Input tokens | Output tokens |
|---|---:|---:|---:|---:|
| plain_matched | 4442.743 | 4767.29 | 48158 | 5511 |
| ktrf_matched | 4448.275 | 4755.256 | 50068 | 5506 |
| ktrf_evidence_ids | 15304.529 | 22989.41 | 94849 | 17125 |
| ktrf_evidence_offsets | 12300.819 | 19858.221 | 98642 | 13982 |

Preparation timings and pipeline diagnostics:

```json
{
  "preparation_timing_ms": {
    "snapshot_compile": {
      "observations": 8,
      "total": 15.16193593852222,
      "min": 1.7071559559553862,
      "max": 2.291206968948245,
      "p50": 1.846,
      "p95": 2.178,
      "p99": 2.269
    },
    "first_prepare": {
      "observations": 64,
      "total": 1174.6885234024376,
      "min": 12.230355991050601,
      "max": 26.735908817499876,
      "p50": 17.774,
      "p95": 24.292,
      "p99": 26.126
    },
    "warm_prepare": {
      "observations": 64,
      "total": 1117.9632514249533,
      "min": 11.272188974544406,
      "max": 25.801775977015495,
      "p50": 16.962,
      "p95": 23.249,
      "p99": 24.812
    }
  },
  "pipeline_diagnostics": {
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
    "questions": 64,
    "by_variant": {
      "plain_matched": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 51,
        "correct_rate": 0.796875,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 44,
        "pack_injected_questions": 44,
        "families": 8,
        "accepted_correct_id": 23,
        "accepted_wrong_id": 4,
        "rejected_wrong_id": 0,
        "correct_abstention": 28,
        "over_abstention": 0,
        "rejected_correct_id": 9,
        "attempted_nonnull": 36,
        "guard_valid": 55,
        "semantic_match": 60,
        "accepted_nonnull": 27,
        "accepted_wrong_id_rate": 0.0625,
        "accepted_wrong_id_rate_among_accepted": 0.14814814814814814,
        "accepted_correct_id_rate": 0.71875,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.875,
        "documents": 64,
        "documents_with_wrong_approval": 4,
        "document_wrong_approval_rate": 0.0625,
        "proposal_correct_id": 32,
        "proposal_wrong_id": 4,
        "proposal_abstention": 28,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 0
        },
        "evidence_rejection_reasons": {}
      },
      "ktrf_matched": {
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
        "pack_injected_requests": 44,
        "pack_injected_questions": 44,
        "families": 8,
        "accepted_correct_id": 22,
        "accepted_wrong_id": 6,
        "rejected_wrong_id": 0,
        "correct_abstention": 26,
        "over_abstention": 0,
        "rejected_correct_id": 10,
        "attempted_nonnull": 38,
        "guard_valid": 54,
        "semantic_match": 58,
        "accepted_nonnull": 28,
        "accepted_wrong_id_rate": 0.09375,
        "accepted_wrong_id_rate_among_accepted": 0.21428571428571427,
        "accepted_correct_id_rate": 0.6875,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.8125,
        "documents": 64,
        "documents_with_wrong_approval": 6,
        "document_wrong_approval_rate": 0.09375,
        "proposal_correct_id": 31,
        "proposal_wrong_id": 6,
        "proposal_abstention": 26,
        "validation_failures": {
          "wire_valid": 1,
          "base_guard_valid": 10,
          "evidence_gate_valid": 1
        },
        "evidence_rejection_reasons": {}
      },
      "ktrf_evidence_ids": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 54,
        "correct_rate": 0.84375,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 44,
        "pack_injected_questions": 44,
        "families": 8,
        "accepted_correct_id": 23,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 1,
        "correct_abstention": 31,
        "over_abstention": 0,
        "rejected_correct_id": 9,
        "attempted_nonnull": 33,
        "guard_valid": 54,
        "semantic_match": 63,
        "accepted_nonnull": 23,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": 0.0,
        "accepted_correct_id_rate": 0.71875,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.96875,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 32,
        "proposal_wrong_id": 1,
        "proposal_abstention": 31,
        "validation_failures": {
          "wire_valid": 0,
          "base_guard_valid": 9,
          "evidence_gate_valid": 1
        },
        "evidence_rejection_reasons": {
          "complete_applicability_claims_required": 1
        }
      },
      "ktrf_evidence_offsets": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 19,
        "correct_rate": 0.296875,
        "missing": 0,
        "errors": 0,
        "malformed": 5,
        "valid": 59,
        "pack_injected_requests": 44,
        "pack_injected_questions": 44,
        "families": 8,
        "accepted_correct_id": 0,
        "accepted_wrong_id": 0,
        "rejected_wrong_id": 1,
        "correct_abstention": 19,
        "over_abstention": 0,
        "rejected_correct_id": 27,
        "attempted_nonnull": 33,
        "guard_valid": 19,
        "semantic_match": 58,
        "accepted_nonnull": 0,
        "accepted_wrong_id_rate": 0.0,
        "accepted_wrong_id_rate_among_accepted": null,
        "accepted_correct_id_rate": 0.0,
        "over_abstention_rate": 0.0,
        "correct_abstention_rate": 0.59375,
        "documents": 64,
        "documents_with_wrong_approval": 0,
        "document_wrong_approval_rate": 0.0,
        "proposal_correct_id": 27,
        "proposal_wrong_id": 1,
        "proposal_abstention": 30,
        "validation_failures": {
          "wire_valid": 6,
          "base_guard_valid": 14,
          "evidence_gate_valid": 45
        },
        "evidence_rejection_reasons": {
          "source_quote_mismatch": 27,
          "attribute_source_span_mismatch": 112,
          "evidence_crosses_target_paragraph": 5,
          "evidence_has_other_surface_occurrence": 3,
          "abstention_assertion_inconsistent": 11,
          "evidence_does_not_contain_requested_occurrence": 1
        }
      }
    }
  }
}
```


Paired comparisons:

```json
{
  "plain_matched_to_ktrf_matched": {
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
    "accepted_wrong_id_increased": 2,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.03125,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_matched_to_ktrf_evidence_ids": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.09375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.09375,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 6,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.09375,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_evidence_offsets_to_ktrf_evidence_ids": {
    "planned": 64,
    "questions": 64,
    "comparable": 59,
    "incomplete_or_malformed": 5,
    "helpful": 31,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.546875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.5254237288135594,
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

Workload aggregate; exposed diagnostics and fresh families must be assessed separately.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `development`. Cases: 64; families: 8.

| Condition | Accepted correct ID | Accepted wrong ID | Correct abstention | Over-abstention | Prompt tokens |
|---|---:|---:|---:|---:|---:|
| plain_matched | 23 | 4 | 28 | 0 | 48158 |
| ktrf_matched | 22 | 6 | 26 | 0 | 50068 |
| ktrf_evidence_ids | 23 | 0 | 31 | 0 | 94849 |
| ktrf_evidence_offsets | 0 | 0 | 19 | 0 | 98642 |

Split paired comparisons:

```json
{
  "plain_matched_to_ktrf_matched": {
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
    "accepted_wrong_id_increased": 2,
    "accepted_wrong_id_decreased": 0,
    "accepted_wrong_id_increase_rate_among_comparable": 0.03125,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.0,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_matched_to_ktrf_evidence_ids": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.09375,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.09375,
    "harmful_rate_among_comparable": 0.0,
    "accepted_wrong_id_increased": 0,
    "accepted_wrong_id_decreased": 6,
    "accepted_wrong_id_increase_rate_among_comparable": 0.0,
    "accepted_wrong_id_decrease_rate_among_comparable": 0.09375,
    "over_abstention_increased": 0,
    "over_abstention_decreased": 0,
    "over_abstention_increase_rate_among_comparable": 0.0,
    "over_abstention_decrease_rate_among_comparable": 0.0
  },
  "ktrf_evidence_offsets_to_ktrf_evidence_ids": {
    "planned": 64,
    "questions": 64,
    "comparable": 59,
    "incomplete_or_malformed": 5,
    "helpful": 31,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.546875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 8,
    "helpful_rate_among_comparable": 0.5254237288135594,
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

- Only the previously exposed development split is reused; this is an EXPOSED_DIAGNOSTIC, not a new independent holdout.
- Source documents and glossary facts are AI authored and AI reviewed, not human gold or real workplace records.
- All four arms receive the exact same actual resolver candidates and applicability facts, including ambiguous candidates.
- All arms use the same unchanged production occurrence execution guard; semantic proposals are reported before authorization.
- Evidence IDs and offset arms receive the same source-only quote and attribute inventory; only evidence transport differs.
- Evidence checks enforce literal source consistency, occurrence identity and direct-negation veto, not semantic entailment.
- Whole source documents and glossary definitions remain intact; evidence windows are complete sentence units and never invented from gold.
- Family clusters, not conditions or repeated model calls, are the statistical units; no deployment-risk guarantee is made.
