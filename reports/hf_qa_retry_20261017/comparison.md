# HF QA model comparison

Baseline: `ktrf-hfqa-gemma4-12b-bf16`; current: `ktrf-hfqa-qwen3.5-27b-bf16`.

Same frozen questions, conditions and decoding; model family and size both change.

| Condition | Comparable | Current helpful | Current harmful |
|---|---:|---:|---:|
| none_knowledge | 64/64 | 8 | 2 |
| none_evidence | 128/128 | 0 | 0 |
| full | 125/128 | 8 | 8 |
| retrieved | 128/128 | 6 | 5 |
| ktrf_expanded | 127/128 | 6 | 5 |
| ktrf_pack | 123/128 | 4 | 3 |

- Generation normalized EM and character F1 are project diagnostics, not official TyDi byte-span F1.
- Capacity-feasible stratified questions are not representative of the full Korean validation distribution.
- No-answer is article-specific; closed-book knowledge has a positive-only primary outcome.
- Unanimous NO_ANSWER and two-vote minimal-positive questions are selected; disputed and malformed gold stay in the inventory.
- All source text and individual responses remain private; only aggregate reports are published.
- Existing Wikipedia/model-pretraining overlap and repeated content cannot be ruled out.
- Model family and size both change; shared-host timing is descriptive.
- KTRF pack is a full intervention including its policy, not an isolated formatting effect.
- No execution IDs or deployment risk are evaluated.
