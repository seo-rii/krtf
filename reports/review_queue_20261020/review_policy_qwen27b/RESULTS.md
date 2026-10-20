# Extended frozen experiment

Experiment: `review_policy`. Model: `ktrf-review-qwen27b-bf16`. Status: `COMPLETE`.

Cases: 64; parent documents: 64. Counts: `{'request_count': 384, 'record_count': 384, 'received_count': 384, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| none_evidence | 25/32 | 15/32 | 0 | 0 | 0 | 39300 |
| none_term | 25/32 | 18/32 | 0 | 0 | 0 | 65348 |
| none_document | 26/32 | 14/32 | 0 | 0 | 0 | 60804 |
| pack_evidence | 24/32 | 16/32 | 0 | 0 | 0 | 42945 |
| pack_term | 25/32 | 17/32 | 0 | 0 | 0 | 68993 |
| pack_document | 26/32 | 15/32 | 0 | 0 | 0 | 64449 |

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
        "correct": 40,
        "correct_rate": 0.625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 0,
        "pack_injected_questions": 0,
        "families": 64,
        "positive_exact": 25,
        "positive_exact_rate": 0.78125,
        "positive_character_f1_sum": 26.454545454545453,
        "positive_character_f1_mean": 0.8267045454545454,
        "article_no_answer_null": 15,
        "article_no_answer_null_rate": 0.46875,
        "article_no_answer_nonnull": 17,
        "positive_null": 3,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 25,
        "positive_exact_without_visible_source": 0
      },
      "none_term": {
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
        "pack_injected_requests": 0,
        "pack_injected_questions": 0,
        "families": 64,
        "positive_exact": 25,
        "positive_exact_rate": 0.78125,
        "positive_character_f1_sum": 26.454545454545453,
        "positive_character_f1_mean": 0.8267045454545454,
        "article_no_answer_null": 18,
        "article_no_answer_null_rate": 0.5625,
        "article_no_answer_nonnull": 14,
        "positive_null": 3,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 25,
        "positive_exact_without_visible_source": 0
      },
      "none_document": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 40,
        "correct_rate": 0.625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 0,
        "pack_injected_questions": 0,
        "families": 64,
        "positive_exact": 26,
        "positive_exact_rate": 0.8125,
        "positive_character_f1_sum": 26.545454545454547,
        "positive_character_f1_mean": 0.8295454545454546,
        "article_no_answer_null": 14,
        "article_no_answer_null_rate": 0.4375,
        "article_no_answer_nonnull": 18,
        "positive_null": 3,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 26,
        "positive_exact_without_visible_source": 0
      },
      "pack_evidence": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 40,
        "correct_rate": 0.625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 13,
        "pack_injected_questions": 13,
        "families": 64,
        "positive_exact": 24,
        "positive_exact_rate": 0.75,
        "positive_character_f1_sum": 27.03030303030303,
        "positive_character_f1_mean": 0.8446969696969697,
        "article_no_answer_null": 16,
        "article_no_answer_null_rate": 0.5,
        "article_no_answer_nonnull": 16,
        "positive_null": 2,
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
        "correct": 42,
        "correct_rate": 0.65625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 13,
        "pack_injected_questions": 13,
        "families": 64,
        "positive_exact": 25,
        "positive_exact_rate": 0.78125,
        "positive_character_f1_sum": 27.12121212121212,
        "positive_character_f1_mean": 0.8475378787878788,
        "article_no_answer_null": 17,
        "article_no_answer_null_rate": 0.53125,
        "article_no_answer_nonnull": 15,
        "positive_null": 2,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 25,
        "positive_exact_without_visible_source": 0
      },
      "pack_document": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 41,
        "correct_rate": 0.640625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 13,
        "pack_injected_questions": 13,
        "families": 64,
        "positive_exact": 26,
        "positive_exact_rate": 0.8125,
        "positive_character_f1_sum": 27.21212121212121,
        "positive_character_f1_mean": 0.8503787878787878,
        "article_no_answer_null": 15,
        "article_no_answer_null_rate": 0.46875,
        "article_no_answer_nonnull": 17,
        "positive_null": 2,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 26,
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
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.015625
  },
  "none_term_to_pack_term": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.015625,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.03125
  },
  "none_document_to_pack_document": {
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
  "none_term_to_none_document": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 4,
    "mean_correctness_delta_all_planned": -0.046875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.0625
  },
  "pack_term_to_pack_document": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 3,
    "mean_correctness_delta_all_planned": -0.015625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.03125,
    "harmful_rate_among_comparable": 0.046875
  }
}
```

Workload aggregate; exposed diagnostics and fresh families must be assessed separately.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `fresh_public_context`. Cases: 64; families: 64.

| Condition | Positive exact | No-answer null | Prompt tokens |
|---|---:|---:|---:|
| none_evidence | 25/32 | 15/32 | 39300 |
| none_term | 25/32 | 18/32 | 65348 |
| none_document | 26/32 | 14/32 | 60804 |
| pack_evidence | 24/32 | 16/32 | 42945 |
| pack_term | 25/32 | 17/32 | 68993 |
| pack_document | 26/32 | 15/32 | 64449 |

Split paired comparisons:

```json
{
  "none_evidence_to_pack_evidence": {
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
  "none_term_to_pack_term": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 2,
    "mean_correctness_delta_all_planned": -0.015625,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.03125
  },
  "none_document_to_pack_document": {
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
  "none_term_to_none_document": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 4,
    "mean_correctness_delta_all_planned": -0.046875,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.0625
  },
  "pack_term_to_pack_document": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 3,
    "mean_correctness_delta_all_planned": -0.015625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.03125,
    "harmful_rate_among_comparable": 0.046875
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
