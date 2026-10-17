# Frozen HF QA followup

Experiment: `retrieval`. Model: `ktrf-followup-gemma12b-bf16`. Status: `COMPLETE`.

Questions: 128; parent documents: 128. Counts: `{'request_count': 512, 'record_count': 512, 'received_count': 512, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

Question-level averages include all planned requests. Repeats are descriptive and do not increase the independent sample size.

| Context / decoding | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| lexical__free | 22/48 | 73/80 | 0 | 0 | 0 | 71685 |
| bm25__free | 25/48 | 73/80 | 0 | 0 | 0 | 87624 |
| adjacent__free | 19/48 | 71/80 | 0 | 0 | 0 | 74553 |
| oracle__free | 35/48 | 72/80 | 0 | 0 | 0 | 65230 |

Matched comparisons and per-question mean changes:

```json
{
  "lexical__free_to_bm25__free": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 5,
    "harmful": 2,
    "per_question_mean_exact_delta": 0.0234375,
    "question_mean_improved": 5,
    "question_mean_worsened": 2,
    "identical_prompt_pairs": 37,
    "identical_prompt_valid_pairs": 37,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "lexical__free_to_adjacent__free": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 8,
    "per_question_mean_exact_delta": -0.0390625,
    "question_mean_improved": 3,
    "question_mean_worsened": 8,
    "identical_prompt_pairs": 14,
    "identical_prompt_valid_pairs": 14,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "lexical__free_to_oracle__free": {
    "planned": 128,
    "questions": 128,
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 13,
    "harmful": 1,
    "per_question_mean_exact_delta": 0.09375,
    "question_mean_improved": 13,
    "question_mean_worsened": 1,
    "identical_prompt_pairs": 80,
    "identical_prompt_valid_pairs": 80,
    "identical_prompt_answer_disagreements": 1,
    "no_independence_claim_for_repeats": true
  }
}
```

Repeated identical-prompt agreement:

```json
{
  "lexical__free": {
    "question_groups": 128,
    "fully_valid_groups": 128,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 128,
    "identical_correctness_groups": 128,
    "repeat_count": 1
  },
  "bm25__free": {
    "question_groups": 128,
    "fully_valid_groups": 128,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 128,
    "identical_correctness_groups": 128,
    "repeat_count": 1
  },
  "adjacent__free": {
    "question_groups": 128,
    "fully_valid_groups": 128,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 128,
    "identical_correctness_groups": 128,
    "repeat_count": 1
  },
  "oracle__free": {
    "question_groups": 128,
    "fully_valid_groups": 128,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 128,
    "identical_correctness_groups": 128,
    "repeat_count": 1
  }
}
```

- Generation normalized EM and character F1 are project diagnostics, not official TyDi byte-span F1.
- Capacity-feasible stratified questions are not representative of the full Korean validation distribution.
- No-answer is article-specific; closed-book knowledge has a positive-only primary outcome.
- Unanimous NO_ANSWER and two-vote minimal-positive questions are selected; disputed and malformed gold stay in the inventory.
- All source text and individual responses remain private; only aggregate reports are published.
- Existing Wikipedia/model-pretraining overlap and repeated content cannot be ruled out.
- Model family and size both change; shared-host timing is descriptive.
- KTRF pack is a full intervention including its policy, not an isolated formatting effect.
- No execution IDs or deployment risk are evaluated.
- Oracle supplies gold-annotated source passages and is diagnostic only, never deployable.
- Retrieval sampling excludes all declared prior article parents and content hashes; near duplicates are not detected.
- Retrieval sample is conditional on a complete original oracle passage fitting both tokenizers and the character budget.
- Stability reuses the original questions and exact prompts; repeats are not independent validation samples.
- The initial retrieval target was amended before generation due to distinct-article scarcity; positive and negative denominators differ.
- Retrieval has a common source-token cap; stability intentionally preserves the older source lengths unchanged.
- Deterministic decoding can still vary with inference scheduling and hardware; repeats diagnose this variation.
