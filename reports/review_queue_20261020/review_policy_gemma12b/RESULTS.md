# Extended frozen experiment

Experiment: `review_policy`. Model: `ktrf-review-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 64; parent documents: 64. Counts: `{'request_count': 384, 'record_count': 384, 'received_count': 384, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| none_evidence | 24/32 | 18/32 | 0 | 0 | 0 | 43441 |
| none_term | 24/32 | 20/32 | 0 | 0 | 0 | 71345 |
| none_document | 22/32 | 20/32 | 0 | 0 | 0 | 66417 |
| pack_evidence | 24/32 | 19/32 | 0 | 0 | 0 | 47388 |
| pack_term | 24/32 | 20/32 | 0 | 0 | 0 | 75292 |
| pack_document | 22/32 | 20/32 | 0 | 0 | 0 | 70364 |

Normalized answer EM and separate source/terminology-need strata; character overlap is not semantic entailment.

Pre-inference terminology-need strata:

```json
{
  "unannotated": {
    "questions": 64,
    "by_variant": {
      "none_evidence": {
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
        "pack_injected_requests": 0,
        "pack_injected_questions": 0,
        "families": 64,
        "positive_exact": 24,
        "positive_exact_rate": 0.75,
        "positive_character_f1_sum": 26.104594330400783,
        "positive_character_f1_mean": 0.8157685728250245,
        "article_no_answer_null": 18,
        "article_no_answer_null_rate": 0.5625,
        "article_no_answer_nonnull": 14,
        "positive_null": 2,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 24,
        "positive_exact_without_visible_source": 0
      },
      "none_term": {
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
        "pack_injected_requests": 0,
        "pack_injected_questions": 0,
        "families": 64,
        "positive_exact": 24,
        "positive_exact_rate": 0.75,
        "positive_character_f1_sum": 26.417249417249415,
        "positive_character_f1_mean": 0.8255390442890442,
        "article_no_answer_null": 20,
        "article_no_answer_null_rate": 0.625,
        "article_no_answer_nonnull": 12,
        "positive_null": 2,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 24,
        "positive_exact_without_visible_source": 0
      },
      "none_document": {
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
        "pack_injected_requests": 0,
        "pack_injected_questions": 0,
        "families": 64,
        "positive_exact": 22,
        "positive_exact_rate": 0.6875,
        "positive_character_f1_sum": 25.993006993006993,
        "positive_character_f1_mean": 0.8122814685314685,
        "article_no_answer_null": 20,
        "article_no_answer_null_rate": 0.625,
        "article_no_answer_nonnull": 12,
        "positive_null": 2,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 22,
        "positive_exact_without_visible_source": 0
      },
      "pack_evidence": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 43,
        "correct_rate": 0.671875,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 13,
        "pack_injected_questions": 13,
        "families": 64,
        "positive_exact": 24,
        "positive_exact_rate": 0.75,
        "positive_character_f1_sum": 25.437927663734115,
        "positive_character_f1_mean": 0.7949352394916911,
        "article_no_answer_null": 19,
        "article_no_answer_null_rate": 0.59375,
        "article_no_answer_nonnull": 13,
        "positive_null": 3,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 24,
        "positive_exact_without_visible_source": 0
      },
      "pack_term": {
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
        "pack_injected_requests": 13,
        "pack_injected_questions": 13,
        "families": 64,
        "positive_exact": 24,
        "positive_exact_rate": 0.75,
        "positive_character_f1_sum": 25.832215403643975,
        "positive_character_f1_mean": 0.8072567313638742,
        "article_no_answer_null": 20,
        "article_no_answer_null_rate": 0.625,
        "article_no_answer_nonnull": 12,
        "positive_null": 3,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 24,
        "positive_exact_without_visible_source": 0
      },
      "pack_document": {
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
        "pack_injected_requests": 13,
        "pack_injected_questions": 13,
        "families": 64,
        "positive_exact": 22,
        "positive_exact_rate": 0.6875,
        "positive_character_f1_sum": 24.50815850815851,
        "positive_character_f1_mean": 0.7658799533799534,
        "article_no_answer_null": 20,
        "article_no_answer_null_rate": 0.625,
        "article_no_answer_nonnull": 12,
        "positive_null": 3,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 22,
        "positive_exact_without_visible_source": 0
      }
    }
  }
}
```


Paired comparisons:

```json
{
  "none_evidence_to_pack_evidence": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.015625,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.0
  },
  "none_term_to_pack_term": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "none_document_to_pack_document": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.015625
  },
  "none_term_to_none_document": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.03125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.03125
  },
  "pack_term_to_pack_document": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.03125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.03125
  }
}
```

Workload aggregate; exposed diagnostics and fresh families must be assessed separately.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `fresh_public_context`. Cases: 64; families: 64.

| Condition | Positive exact | No-answer null | Prompt tokens |
|---|---:|---:|---:|
| none_evidence | 24/32 | 18/32 | 43441 |
| none_term | 24/32 | 20/32 | 71345 |
| none_document | 22/32 | 20/32 | 66417 |
| pack_evidence | 24/32 | 19/32 | 47388 |
| pack_term | 24/32 | 20/32 | 75292 |
| pack_document | 22/32 | 20/32 | 70364 |

Split paired comparisons:

```json
{
  "none_evidence_to_pack_evidence": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.015625,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.0
  },
  "none_term_to_pack_term": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "none_document_to_pack_document": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.015625
  },
  "none_term_to_none_document": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.03125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.03125
  },
  "pack_term_to_pack_document": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.03125,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.03125
  }
}
```

- Public contexts are stratified, not a sample of actual customer usage; original article independence is unverified.
- Business cases are AI-authored scenarios, not independently collected real workplace documents or human gold.
- All public QA tracks reuse one selected 64-question set; counts across tracks are not independent evidence.
- ABCD is a product comparison with different task policies; the separate policy factorial isolates policy effects.
- Business task policy permits supplied glossary facts only when document meaning and scope support them; public MRC remains source-only.
- Glossary lexical baseline and KTRF receive the same scoped source glossary; retrieved facts may differ.
- Source-first drops entire cards using explicit text redundancy, not learned factual compression or gold-aware retrieval.
- Input caps include full actual chat templates; 128 output tokens are separately reserved within model capacity.
- No retrieval success, pack injection status, generated answer or judge output determines public sampling.
- Character F1 is lexical overlap, not a semantic correctness guarantee; no execution authorization is evaluated here.
