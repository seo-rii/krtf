# one-server KTRF validation — 2026-10-13

Tested commit: `bfce711f4538464f8bd8dd932a0b7aea6c8a82ae`. Python 3.12.3 on one-server. Full core suite: **541 passed in 13.26s**. The detached process exited with code 0; its exit was verified.

The existing A100 service `mil-gemma4-12b-bf16` received 126 serial requests. All returned valid JSON; all finish reasons were `stop` and the largest completion was 43 tokens against the 128-token cap. Prompt/completion totals were 33,880/2,583 tokens. No service, GPU allocation policy or model weights were changed.

## Model outcomes

| Condition | Success /14 | Answerable QA /5 | Answerable routing /5 | Over-abstention | Meaning switches /3 |
|---|---:|---:|---:|---:|---:|
| no_context | 2 | 0 | 0 | 5 | 0 |
| ktrf:plain:evidence_only | 5 | 0 | 1 | 8 | 0 |
| ktrf:plain:knowledge | 5 | 0 | 1 | 8 | 0 |
| ktrf:structured:evidence_only | 5 | 0 | 1 | 9 | 0 |
| ktrf:structured:knowledge | 5 | 0 | 1 | 9 | 0 |
| lexical:plain:evidence_only | 5 | 0 | 1 | 8 | 0 |
| lexical:plain:knowledge | 5 | 0 | 1 | 8 | 0 |
| lexical:structured:evidence_only | 5 | 0 | 1 | 9 | 0 |
| lexical:structured:knowledge | 5 | 0 | 1 | 9 | 0 |

Each contextual 5/14 consists of four safe abstentions on ambiguous/missing cases and one correct project-routing ID. All five answerable QA cases return null. Plain session routing emits `session` in place of `session:session`; the execution validator rejects it. Structured session routing returns null. Raw review found no correct QA paraphrase hidden by strict matching.

KTRF and literal alias retrieval supply exactly the same cards and prompts in all 56 paired observations and produce identical parsed outputs. This is a format/policy smoke experiment and does not compare distinct selectors or establish an advantage over general RAG. Policy changes do not improve the measured outcomes.

## Interpretation and scope

The policy requires `resolved_terms` and an exact surface binding, but rendered inputs provide either plain cards or `terminology_data` with `entity_id/canonical/definition/status` only. Neither format supplies `resolved_terms` or the `ABC` surface mapping that is present in the full local pack. This mismatch is directly observable. Its causal contribution to over-abstention remains a hypothesis requiring a separate corrected-stimulus comparison; the current results should not be treated as scores for complete production context packs.

The shared GPU can add queueing to latency. Checkpoint revision/weight content was not independently verified; recorded config hashes identify metadata only. This run does not certify deployment risk, perform CUDA reranker/ONNX parity checks, or measure human correction time.

## Reproduction and artifacts

Run `python -m pytest -q` in the isolated checkout. The model experiment is:

```sh
python -m eval.run_product_llm \
  --endpoint http://127.0.0.1:18090/v1 \
  --model mil-gemma4-12b-bf16 \
  --out-dir /path/to/new-exclusive-run \
  --code-revision bfce711f4538464f8bd8dd932a0b7aea6c8a82ae \
  --max-tokens 128 --timeout 180
```

The runner forwards only system/user strings, uses temperature 0, seed 0 and disabled thinking, accepts bare JSON or one JSON code fence uniformly, and performs no retries or answer repair.

[Structured validation](ONE_SERVER_VALIDATION.json), [sealed run manifest](one_server_20261013/run_manifest.json), [requests](one_server_20261013/requests.jsonl), [raw responses](one_server_20261013/responses.jsonl), [graded results](one_server_20261013/graded.json). All artifact hashes and exact offline regrading were verified.

Remote log: `/home/one/logs/krtf-one-server-20261013T003732Z-validation.log`. Exit status: `/home/one/logs/krtf-one-server-20261013T003732Z-validation.status.json` (exit 0). Local copies: `/home/seorii/logs/krtf-one-server-20261013T003732Z-validation.log` and `/home/seorii/logs/krtf-one-server-20261013T003732Z-validation.status.json`.
