# Extended frozen experiment

Experiment: `review_budget`. Model: `ktrf-review-gemma12b-bf16`. Status: `COMPLETE`.

Cases: 64; parent documents: 64. Counts: `{'request_count': 384, 'record_count': 384, 'received_count': 384, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| cap1024_search | 20/32 | 18/32 | 0 | 0 | 0 | 62856 |
| cap1024_current | 20/32 | 20/32 | 0 | 0 | 0 | 63370 |
| cap1024_sourcefirst | 20/32 | 18/32 | 0 | 0 | 0 | 63099 |
| cap1536_search | 21/32 | 18/32 | 0 | 0 | 0 | 66417 |
| cap1536_current | 21/32 | 19/32 | 0 | 0 | 0 | 69748 |
| cap1536_sourcefirst | 22/32 | 19/32 | 0 | 0 | 0 | 69541 |

Normalized answer EM and separate source/terminology-need strata; character overlap is not semantic entailment.

Pre-inference terminology-need strata:

```json
{
  "unannotated": {
    "questions": 64,
    "by_variant": {
      "cap1024_search": {
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
        "pack_injected_requests": 0,
        "pack_injected_questions": 0,
        "families": 64,
        "positive_exact": 20,
        "positive_exact_rate": 0.625,
        "positive_character_f1_sum": 24.31193085352678,
        "positive_character_f1_mean": 0.7597478391727118,
        "article_no_answer_null": 18,
        "article_no_answer_null_rate": 0.5625,
        "article_no_answer_nonnull": 14,
        "positive_null": 4,
        "source_positive_visible": 26,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 20,
        "positive_exact_without_visible_source": 0
      },
      "cap1024_current": {
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
        "positive_exact": 20,
        "positive_exact_rate": 0.625,
        "positive_character_f1_sum": 23.40283994443587,
        "positive_character_f1_mean": 0.7313387482636209,
        "article_no_answer_null": 20,
        "article_no_answer_null_rate": 0.625,
        "article_no_answer_nonnull": 12,
        "positive_null": 5,
        "source_positive_visible": 25,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 20,
        "positive_exact_without_visible_source": 0
      },
      "cap1024_sourcefirst": {
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
        "pack_injected_requests": 2,
        "pack_injected_questions": 2,
        "families": 64,
        "positive_exact": 20,
        "positive_exact_rate": 0.625,
        "positive_character_f1_sum": 24.31193085352678,
        "positive_character_f1_mean": 0.7597478391727118,
        "article_no_answer_null": 18,
        "article_no_answer_null_rate": 0.5625,
        "article_no_answer_nonnull": 14,
        "positive_null": 4,
        "source_positive_visible": 26,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 20,
        "positive_exact_without_visible_source": 0
      },
      "cap1536_search": {
        "planned": 64,
        "questions": 64,
        "positive_planned": 32,
        "no_answer_planned": 32,
        "correct": 39,
        "correct_rate": 0.609375,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 64,
        "pack_injected_requests": 0,
        "pack_injected_questions": 0,
        "families": 64,
        "positive_exact": 21,
        "positive_exact_rate": 0.65625,
        "positive_character_f1_sum": 25.165548736977307,
        "positive_character_f1_mean": 0.7864233980305408,
        "article_no_answer_null": 18,
        "article_no_answer_null_rate": 0.5625,
        "article_no_answer_nonnull": 14,
        "positive_null": 2,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 21,
        "positive_exact_without_visible_source": 0
      },
      "cap1536_current": {
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
        "positive_exact": 21,
        "positive_exact_rate": 0.65625,
        "positive_character_f1_sum": 24.498882070310643,
        "positive_character_f1_mean": 0.7655900646972076,
        "article_no_answer_null": 19,
        "article_no_answer_null_rate": 0.59375,
        "article_no_answer_nonnull": 13,
        "positive_null": 3,
        "source_positive_visible": 27,
        "source_positive_visibility_unknown": 0,
        "positive_exact_with_visible_source": 21,
        "positive_exact_without_visible_source": 0
      },
      "cap1536_sourcefirst": {
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
        "positive_exact": 22,
        "positive_exact_rate": 0.6875,
        "positive_character_f1_sum": 25.40797297940155,
        "positive_character_f1_mean": 0.7939991556062984,
        "article_no_answer_null": 19,
        "article_no_answer_null_rate": 0.59375,
        "article_no_answer_nonnull": 13,
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
  "cap1024_search_to_cap1024_current": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.03125,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.046875,
    "harmful_rate_among_comparable": 0.015625
  },
  "cap1024_search_to_cap1024_sourcefirst": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 62,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "cap1536_search_to_cap1536_current": {
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
  "cap1536_search_to_cap1536_sourcefirst": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.03125,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.03125,
    "harmful_rate_among_comparable": 0.0
  },
  "cap1024_current_to_cap1024_sourcefirst": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 3,
    "mean_correctness_delta_all_planned": -0.03125,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.046875
  },
  "cap1536_current_to_cap1536_sourcefirst": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.015625,
    "identical_prompt_pairs": 61,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.0
  }
}
```

Workload aggregate; exposed diagnostics and fresh families must be assessed separately.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `fresh_public_context`. Cases: 64; families: 64.

| Condition | Positive exact | No-answer null | Prompt tokens |
|---|---:|---:|---:|
| cap1024_search | 20/32 | 18/32 | 62856 |
| cap1024_current | 20/32 | 20/32 | 63370 |
| cap1024_sourcefirst | 20/32 | 18/32 | 63099 |
| cap1536_search | 21/32 | 18/32 | 66417 |
| cap1536_current | 21/32 | 19/32 | 69748 |
| cap1536_sourcefirst | 22/32 | 19/32 | 69541 |

Split paired comparisons:

```json
{
  "cap1024_search_to_cap1024_current": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.03125,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.046875,
    "harmful_rate_among_comparable": 0.015625
  },
  "cap1024_search_to_cap1024_sourcefirst": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 62,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.0,
    "harmful_rate_among_comparable": 0.0
  },
  "cap1536_search_to_cap1536_current": {
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
  "cap1536_search_to_cap1536_sourcefirst": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.03125,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.03125,
    "harmful_rate_among_comparable": 0.0
  },
  "cap1024_current_to_cap1024_sourcefirst": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 3,
    "mean_correctness_delta_all_planned": -0.03125,
    "identical_prompt_pairs": 51,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.046875
  },
  "cap1536_current_to_cap1536_sourcefirst": {
    "planned": 64,
    "questions": 64,
    "comparable": 64,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "mean_correctness_delta_all_planned": 0.015625,
    "identical_prompt_pairs": 61,
    "no_independence_claim_for_repeats": true,
    "families": 64,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.0
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
