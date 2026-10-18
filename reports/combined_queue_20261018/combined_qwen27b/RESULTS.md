# Frozen HF QA followup

Experiment: `combined`. Model: `ktrf-combined-qwen27b-bf16`. Status: `COMPLETE`.

Questions: 128; parent documents: 128. Counts: `{'request_count': 1536, 'record_count': 1536, 'received_count': 1536, 'missing_count': 0, 'error_count': 0, 'malformed_count': 0}`.

Question-level averages include all planned requests. Repeats are descriptive and do not increase the independent sample size.

| Context / decoding | Positive exact | No-answer null | Malformed | API errors | Missing | Prompt tokens |
|---|---:|---:|---:|---:|---:|---:|
| lexical__json_schema | 75/144 | 219/240 | 0 | 0 | 0 | 198372 |
| lexical_pack__json_schema | 72/144 | 219/240 | 0 | 0 | 0 | 226680 |
| bm25__json_schema | 87/144 | 219/240 | 0 | 0 | 0 | 242982 |
| bm25_pack__json_schema | 87/144 | 219/240 | 0 | 0 | 0 | 272547 |

Matched comparisons and per-question mean changes:

```json
{
  "lexical__json_schema_to_bm25__json_schema": {
    "planned": 384,
    "questions": 128,
    "comparable": 384,
    "incomplete_or_malformed": 0,
    "helpful": 24,
    "harmful": 12,
    "per_question_mean_exact_delta": 0.03125,
    "question_mean_improved": 8,
    "question_mean_worsened": 4,
    "identical_prompt_pairs": 111,
    "identical_prompt_valid_pairs": 111,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "lexical__json_schema_to_lexical_pack__json_schema": {
    "planned": 384,
    "questions": 128,
    "comparable": 384,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 3,
    "per_question_mean_exact_delta": -0.0078125,
    "question_mean_improved": 0,
    "question_mean_worsened": 1,
    "identical_prompt_pairs": 345,
    "identical_prompt_valid_pairs": 345,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "bm25__json_schema_to_bm25_pack__json_schema": {
    "planned": 384,
    "questions": 128,
    "comparable": 384,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0,
    "per_question_mean_exact_delta": 0.0,
    "question_mean_improved": 0,
    "question_mean_worsened": 0,
    "identical_prompt_pairs": 342,
    "identical_prompt_valid_pairs": 342,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "lexical_pack__json_schema_to_bm25_pack__json_schema": {
    "planned": 384,
    "questions": 128,
    "comparable": 384,
    "incomplete_or_malformed": 0,
    "helpful": 27,
    "harmful": 12,
    "per_question_mean_exact_delta": 0.0390625,
    "question_mean_improved": 9,
    "question_mean_worsened": 4,
    "identical_prompt_pairs": 111,
    "identical_prompt_valid_pairs": 111,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  },
  "lexical__json_schema_to_bm25_pack__json_schema": {
    "planned": 384,
    "questions": 128,
    "comparable": 384,
    "incomplete_or_malformed": 0,
    "helpful": 24,
    "harmful": 12,
    "per_question_mean_exact_delta": 0.03125,
    "question_mean_improved": 8,
    "question_mean_worsened": 4,
    "identical_prompt_pairs": 99,
    "identical_prompt_valid_pairs": 99,
    "identical_prompt_answer_disagreements": 0,
    "no_independence_claim_for_repeats": true
  }
}
```

Repeated identical-prompt agreement:

```json
{
  "lexical__json_schema": {
    "question_groups": 128,
    "fully_valid_groups": 128,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 128,
    "identical_correctness_groups": 128,
    "repeat_count": 3
  },
  "lexical_pack__json_schema": {
    "question_groups": 128,
    "fully_valid_groups": 128,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 128,
    "identical_correctness_groups": 128,
    "repeat_count": 3
  },
  "bm25__json_schema": {
    "question_groups": 128,
    "fully_valid_groups": 128,
    "incomplete_or_malformed_groups": 0,
    "identical_normalized_answer_groups": 128,
    "identical_correctness_groups": 128,
    "repeat_count": 3
  },
  "bm25_pack__json_schema": {
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
- This is an adaptive followup on previously inspected retrieval questions, not independent validation.
- All 128 prior questions and exact lexical/BM25 source offsets are retained without output-based filtering.
- All four conditions use strict JSON schema; this run does not isolate the decoding effect.
- Three repetitions measure stability and do not increase the independent sample size.
- Pack and no-pack retain identical ranker source windows; actual prompt lengths differ.
- Packs are recomputed from each ranker's question and selected source only; gold and oracle are never pack inputs.
- Search selects passages inside the known article, not documents from a corpus.
- The common source-token cap is not equal actual token consumption or total prompt cost.
