# Frozen HF QA followup

Experiment: `combined`. Model: `ktrf-fresh-qwen27b-bf16`. Status: `COMPLETE`.

Questions: 36; parent documents: 36. Counts: `{'request_count': 432, 'record_count': 432, 'received_count': 432, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

Question-level averages include all planned requests. Repeats are descriptive and do not increase the independent sample size.

| Context / decoding | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| lexical__json_schema | 36/54 | 42/54 | 0 | 0 | 0 | 53913 |
| lexical_pack__json_schema | 39/54 | 42/54 | 0 | 0 | 0 | 69288 |
| bm25__json_schema | 27/54 | 42/54 | 0 | 0 | 0 | 65106 |
| bm25_pack__json_schema | 30/54 | 42/54 | 0 | 0 | 0 | 81453 |

Matched comparisons and per-question mean changes:

```json
{
  "lexical__json_schema_to_bm25__json_schema": {
    "planned": 108,
    "questions": 36,
    "comparable": 108,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 12,
    "per_question_mean_exact_delta": -0.08333333333333333,
    "question_mean_improved": 1,
    "question_mean_worsened": 4,
    "identical_prompt_pairs": 33,
    "identical_prompt_valid_pairs": 33,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "lexical__json_schema_to_lexical_pack__json_schema": {
    "planned": 108,
    "questions": 36,
    "comparable": 108,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 0,
    "per_question_mean_exact_delta": 0.027777777777777776,
    "question_mean_improved": 1,
    "question_mean_worsened": 0,
    "identical_prompt_pairs": 84,
    "identical_prompt_valid_pairs": 84,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "bm25__json_schema_to_bm25_pack__json_schema": {
    "planned": 108,
    "questions": 36,
    "comparable": 108,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 0,
    "per_question_mean_exact_delta": 0.027777777777777776,
    "question_mean_improved": 1,
    "question_mean_worsened": 0,
    "identical_prompt_pairs": 84,
    "identical_prompt_valid_pairs": 84,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "lexical_pack__json_schema_to_bm25_pack__json_schema": {
    "planned": 108,
    "questions": 36,
    "comparable": 108,
    "incomplete_or_malformed": 0,
    "helpful": 3,
    "harmful": 12,
    "per_question_mean_exact_delta": -0.08333333333333333,
    "question_mean_improved": 1,
    "question_mean_worsened": 4,
    "identical_prompt_pairs": 33,
    "identical_prompt_valid_pairs": 33,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "lexical__json_schema_to_bm25_pack__json_schema": {
    "planned": 108,
    "questions": 36,
    "comparable": 108,
    "incomplete_or_malformed": 0,
    "helpful": 6,
    "harmful": 12,
    "per_question_mean_exact_delta": -0.05555555555555555,
    "question_mean_improved": 2,
    "question_mean_worsened": 4,
    "identical_prompt_pairs": 24,
    "identical_prompt_valid_pairs": 24,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  }
}
```

Repeated identical-prompt agreement:

```json
{
  "lexical__json_schema": {
    "question_groups": 36,
    "fully_valid_groups": 36,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 36,
    "identical_correctness_groups": 36,
    "repeat_count": 3
  },
  "lexical_pack__json_schema": {
    "question_groups": 36,
    "fully_valid_groups": 36,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 36,
    "identical_correctness_groups": 36,
    "repeat_count": 3
  },
  "bm25__json_schema": {
    "question_groups": 36,
    "fully_valid_groups": 36,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 36,
    "identical_correctness_groups": 36,
    "repeat_count": 3
  },
  "bm25_pack__json_schema": {
    "question_groups": 36,
    "fully_valid_groups": 36,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 36,
    "identical_correctness_groups": 36,
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
- This small same-corpus holdout excludes every declared earlier article parent and exact content hash.
- This sample contains 6 SPAN and 12 YES_NO positive articles; efficacy and operational risk are not established.
- Methods were chosen using earlier articles; these selected questions have no earlier generation outputs.
- Near-duplicate articles, other corpora, and model pretraining overlap are not ruled out.
- Three repetitions do not increase the independent question count.
- Sampling uses gold type but neither retrieval success, oracle capacity nor pack injection eligibility.
- All four conditions use strict JSON; pack and no-pack share the exact ranker source windows.
- Search is within a known article, not corpus-level document retrieval.
- Pack and its policy form one intervention; common source caps do not equal actual prompt costs.
