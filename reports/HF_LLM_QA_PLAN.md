# HF LLM QA frozen plan

**Frozen before inference.** This records preparation; queue status and collected reports establish completion. No model accuracy is claimed here.

Run: `ktrf-hf-qa-20261016T065054KST`. Inference revision: `cfdd5c583d82f900c321f9621474b4fb297ceed7`.

128 questions from 128 distinct parent articles: 56 span answers, 8 YES/NO and 64 unanimous article-no-answer cases. Six conditions produce 768 requests per model, 1,536 in total.

Gemma4 12B runs before Qwen3.5 27B. The queue waits for GPU/port availability and never stops another job.

| Preparation | Verified outcome |
|---|---|
| Candidate pool | 384 questions |
| Common context fit | 256 questions |
| Final selected | 128 questions / 128 parent articles |
| Prior evidence sample overlap | 19 questions |
| one-server tests | 1,310 passed, exit 0 |
| gemma12b actual template | max 8063 + 128 output ≤ 8,192; overflow 0 |
| qwen27b actual template | max 7597 + 128 output ≤ 8,192; overflow 0 |

No original article is truncated. Over-capacity screening cases are recorded rather than repaired. This is a capacity-feasible balanced sample, not a representative score for all 1,698 Korean questions.

[Protocol](../docs/HF_LLM_QA.md) · [Frozen plan and proofs](HF_LLM_QA_PLAN.json)

Generation normalized EM and partial character F1 are project diagnostics, not official TyDi byte-span F1. Closed-book no-answer cases are unjudged; factual positive accuracy and source-grounded outcomes remain separate.

Verified results will be collected under `reports/hf_qa_queue_20261016/`. Raw prompts, articles and model responses remain private. The collector regrades both runs before publishing aggregate reports and pushing them on synchronized main.

Queue log: `/home/one/logs/ktrf-hf-qa-20261016T065054KST.log`.
Queue status: `/home/one/logs/ktrf-hf-qa-20261016T065054KST.status.json`.
