# HF TyDiQA generation results

Model: `ktrf-hfqa-gemma4-12b-bf16`. Status: `COMPLETE`.

Questions: 128; parent articles: 128. Counts: `{'request_count': 768, 'received_count': 768, 'missing_count': 0, 'malformed_count': 2, 'error_count': 0}`.

These are generation normalized exact match and partial character-F1 diagnostics, not official TyDi byte-span F1.

| Condition | Positive exact | Article no-answer null | Malformed | Missing | Prompt tokens | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| none_knowledge | 18/64 | unjudged | 0 | 0 | 15180 | 1016.007 |
| none_evidence | 0/64 | 64/64 | 0 | 0 | 23372 | 336.673 |
| full | 43/64 | 61/64 | 0 | 0 | 455143 | 1709.449 |
| retrieved | 32/64 | 61/64 | 0 | 0 | 67197 | 903.793 |
| ktrf_expanded | 32/64 | 61/64 | 1 | 0 | 67209 | 900.287 |
| ktrf_pack | 33/64 | 62/64 | 1 | 0 | 87606 | 905.012 |

Matched source-contract changes (incomplete/malformed pairs are separate):

```json
{
  "retrieved_to_full": {
    "comparable": 128,
    "incomplete_or_malformed": 0,
    "helpful": 15,
    "harmful": 4
  },
  "retrieved_to_ktrf_expanded": {
    "comparable": 127,
    "incomplete_or_malformed": 1,
    "helpful": 0,
    "harmful": 0
  },
  "retrieved_to_ktrf_pack": {
    "comparable": 127,
    "incomplete_or_malformed": 1,
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
