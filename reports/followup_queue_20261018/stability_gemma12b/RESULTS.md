# Frozen HF QA followup

Experiment: `stability`. Model: `ktrf-followup-gemma12b-bf16`. Status: `COMPLETE`.

Questions: 128; parent documents: 128. Counts: `{'request_count': 1536, 'record_count': 1536, 'received_count': 1536, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

Question-level averages include all planned requests. Repeats are descriptive and do not increase the independent sample size.

| Context / decoding | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| retrieved__free | 96/192 | 183/192 | 0 | 0 | 0 | 201591 |
| retrieved__json_schema | 96/192 | 183/192 | 0 | 0 | 0 | 201591 |
| ktrf_pack__free | 98/192 | 186/192 | 0 | 0 | 0 | 262818 |
| ktrf_pack__json_schema | 99/192 | 186/192 | 0 | 0 | 0 | 262818 |

Matched comparisons and per-question mean changes:

```json
{
  "retrieved__free_to_ktrf_pack__free": {
    "planned": 384,
    "questions": 128,
    "comparable": 384,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 1,
    "per_question_mean_exact_delta": 0.013020833333333334,
    "question_mean_improved": 2,
    "question_mean_worsened": 1,
    "identical_prompt_pairs": 300,
    "identical_prompt_valid_pairs": 300,
    "identical_prompt_answer_disagreements": 1,
    "no_independence_claim_for_repeats": true
  },
  "retrieved__json_schema_to_ktrf_pack__json_schema": {
    "planned": 384,
    "questions": 128,
    "comparable": 384,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 0,
    "per_question_mean_exact_delta": 0.015625,
    "question_mean_improved": 2,
    "question_mean_worsened": 0,
    "identical_prompt_pairs": 300,
    "identical_prompt_valid_pairs": 300,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "retrieved__free_to_retrieved__json_schema": {
    "planned": 384,
    "questions": 128,
    "comparable": 384,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "per_question_mean_exact_delta": 0.0,
    "question_mean_improved": 0,
    "question_mean_worsened": 0,
    "identical_prompt_pairs": 384,
    "identical_prompt_valid_pairs": 384,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "ktrf_pack__free_to_ktrf_pack__json_schema": {
    "planned": 384,
    "questions": 128,
    "comparable": 384,
    "incomplete_or_malformed": 0,
    "helpful": 1,
    "harmful": 0,
    "per_question_mean_exact_delta": 0.0026041666666666665,
    "question_mean_improved": 1,
    "question_mean_worsened": 0,
    "identical_prompt_pairs": 384,
    "identical_prompt_valid_pairs": 384,
    "identical_prompt_answer_disagreements": 1,
    "no_independence_claim_for_repeats": true
  }
}
```

Repeated identical-prompt agreement:

```json
{
  "retrieved__free": {
    "question_groups": 128,
    "fully_valid_groups": 128,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 128,
    "identical_correctness_groups": 128,
    "repeat_count": 3
  },
  "retrieved__json_schema": {
    "question_groups": 128,
    "fully_valid_groups": 128,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 128,
    "identical_correctness_groups": 128,
    "repeat_count": 3
  },
  "ktrf_pack__free": {
    "question_groups": 128,
    "fully_valid_groups": 128,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 127,
    "identical_correctness_groups": 127,
    "repeat_count": 3
  },
  "ktrf_pack__json_schema": {
    "question_groups": 128,
    "fully_valid_groups": 128,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 128,
    "identical_correctness_groups": 128,
    "repeat_count": 3
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
