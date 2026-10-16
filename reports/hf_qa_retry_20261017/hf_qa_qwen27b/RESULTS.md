# HF TyDiQA generation results

Model: `ktrf-hfqa-qwen3.5-27b-bf16`. Status: `COMPLETE`.

Questions: 128; parent articles: 128. Counts: `{'request_count': 768, 'received_count': 768, 'missing_count': 0, 'malformed_count': 9, 'error_count': 0}`.

These are generation normalized exact match and partial character-F1 diagnostics, not official TyDi byte-span F1.

| Condition | Positive exact | Article no-answer null | Malformed | Missing | Prompt tokens | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| none_knowledge | 24/64 | unjudged | 2 | 0 | 13975 | 1783.605 |
| none_evidence | 0/64 | 64/64 | 0 | 0 | 21143 | 554.256 |
| full | 45/64 | 56/64 | 3 | 0 | 421603 | 3339.16 |
| retrieved | 31/64 | 63/64 | 0 | 0 | 61963 | 1425.554 |
| ktrf_expanded | 31/64 | 63/64 | 0 | 0 | 61978 | 1425.422 |
| ktrf_pack | 33/64 | 59/64 | 4 | 0 | 81088 | 1423.567 |

Matched source-contract changes (incomplete/malformed pairs are separate):

```json
{
  "retrieved_to_full": {
    "comparable": 125,
    "incomplete_or_malformed": 3,
    "helpful": 16,
    "harmful": 6
  },
  "retrieved_to_ktrf_expanded": {
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 0,
    "harmful": 0
  },
  "retrieved_to_ktrf_pack": {
    "comparable": 124,
    "incomplete_or_malformed": 4,
    "helpful": 2,
    "harmful": 0
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
