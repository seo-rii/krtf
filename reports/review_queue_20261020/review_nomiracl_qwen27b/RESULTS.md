# Extended frozen experiment

Experiment: `review_nomiracl`. Model: `ktrf-review-qwen27b-bf16`. Status: `COMPLETE`.

Cases: 128; parent documents: 128. Counts: `{'request_count': 384, 'record_count': 384, 'received_count': 384, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

One observation per case and condition. Shared documents, families and conditions do not increase the independent sample size.

| Condition | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| evidence_only | 58/64 | 40/64 | 0 | 0 | 0 | 251141 |
| term_pack | 57/64 | 36/64 | 0 | 0 | 0 | 319143 |
| document_pack | 56/64 | 42/64 | 0 | 0 | 0 | 310055 |

Provided-passage relevance classification: positive_exact means YES on relevant passage sets; no-answer null means abstention on non-relevant sets. Not answer-generation accuracy or entity linking.

Pre-inference terminology-need strata:

```json
{
  "unannotated": {
    "questions": 128,
    "by_variant": {
      "evidence_only": {
        "planned": 128,
        "questions": 128,
        "positive_planned": 64,
        "no_answer_planned": 64,
        "correct": 98,
        "correct_rate": 0.765625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 128,
        "pack_injected_requests": 0,
        "pack_injected_questions": 0,
        "families": 73,
        "positive_exact": 58,
        "positive_exact_rate": 0.90625,
        "positive_character_f1_sum": 58.0,
        "positive_character_f1_mean": 0.90625,
        "article_no_answer_null": 40,
        "article_no_answer_null_rate": 0.625,
        "article_no_answer_nonnull": 24,
        "positive_null": 5,
        "source_positive_visible": 0,
        "source_positive_visibility_unknown": 64,
        "positive_exact_with_visible_source": 0,
        "positive_exact_without_visible_source": 0
      },
      "term_pack": {
        "planned": 128,
        "questions": 128,
        "positive_planned": 64,
        "no_answer_planned": 64,
        "correct": 93,
        "correct_rate": 0.7265625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 128,
        "pack_injected_requests": 35,
        "pack_injected_questions": 35,
        "families": 73,
        "positive_exact": 57,
        "positive_exact_rate": 0.890625,
        "positive_character_f1_sum": 57.0,
        "positive_character_f1_mean": 0.890625,
        "article_no_answer_null": 36,
        "article_no_answer_null_rate": 0.5625,
        "article_no_answer_nonnull": 28,
        "positive_null": 5,
        "source_positive_visible": 0,
        "source_positive_visibility_unknown": 64,
        "positive_exact_with_visible_source": 0,
        "positive_exact_without_visible_source": 0
      },
      "document_pack": {
        "planned": 128,
        "questions": 128,
        "positive_planned": 64,
        "no_answer_planned": 64,
        "correct": 98,
        "correct_rate": 0.765625,
        "missing": 0,
        "errors": 0,
        "malformed": 0,
        "valid": 128,
        "pack_injected_requests": 35,
        "pack_injected_questions": 35,
        "families": 73,
        "positive_exact": 56,
        "positive_exact_rate": 0.875,
        "positive_character_f1_sum": 56.0,
        "positive_character_f1_mean": 0.875,
        "article_no_answer_null": 42,
        "article_no_answer_null_rate": 0.65625,
        "article_no_answer_nonnull": 22,
        "positive_null": 6,
        "source_positive_visible": 0,
        "source_positive_visibility_unknown": 64,
        "positive_exact_with_visible_source": 0,
        "positive_exact_without_visible_source": 0
      }
    }
  }
}
```


Paired comparisons:

```json
{
  "evidence_only_to_term_pack": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 6,
    "mean_correctness_delta_all_planned": -0.0390625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 73,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.046875
  },
  "evidence_only_to_document_pack": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 73,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.015625
  },
  "term_pack_to_document_pack": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.0390625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 73,
    "helpful_rate_among_comparable": 0.046875,
    "harmful_rate_among_comparable": 0.0078125
  }
}
```

Workload aggregate; exposed diagnostics and fresh families must be assessed separately.

Split results are descriptive. Prompt interventions share cases; reused cases are diagnostic, and no new deployment risk bound is inferred.

Evaluation split: `nomiracl_official_test`. Cases: 128; families: 73.

| Condition | Positive exact | No-answer null | Prompt tokens |
|---|---:|---:|---:|
| evidence_only | 58/64 | 40/64 | 251141 |
| term_pack | 57/64 | 36/64 | 319143 |
| document_pack | 56/64 | 42/64 | 310055 |

Split paired comparisons:

```json
{
  "evidence_only_to_term_pack": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 6,
    "mean_correctness_delta_all_planned": -0.0390625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 73,
    "helpful_rate_among_comparable": 0.0078125,
    "harmful_rate_among_comparable": 0.046875
  },
  "evidence_only_to_document_pack": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 2,
    "harmful": 2,
    "mean_correctness_delta_all_planned": 0.0,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 73,
    "helpful_rate_among_comparable": 0.015625,
    "harmful_rate_among_comparable": 0.015625
  },
  "term_pack_to_document_pack": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 1,
    "mean_correctness_delta_all_planned": 0.0390625,
    "identical_prompt_pairs": 0,
    "no_independence_claim_for_repeats": true,
    "families": 73,
    "helpful_rate_among_comparable": 0.046875,
    "harmful_rate_among_comparable": 0.0078125
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
- NoMIRACL tests relevance of the supplied passage set, not answer extraction or corpus-wide NIL.
- All official passages and original qrels order are retained; overflow excludes the complete question.
- Wikipedia may overlap other benchmarks or model pretraining; no independent-corpus claim is made.
