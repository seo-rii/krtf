# Sequential production grounding evaluation

Four stages run in order: Gemma4 12B BF16 on the 437 balanced synthetic
sentences (874 QA/execution calls), Qwen3.5-27B BF16 on the same frozen
requests, then Gemma12B and Qwen27B on the fresh real-sentence holdout.

The real corpus, source hashes, selection protocol, AI annotation and review
are retained in `eval/fixtures/production_real_holdout/`. This stratified
sentence evaluation has one primary target per sentence. It does not measure
exhaustive mention recall or establish a deployment error bound. AI annotation
is distinct from human verification. Selection and gold are frozen before
model outputs are available.

## Production contract and measurements

Each target has two separate stateless calls. QA uses `qa_grounding` and its
contextual explanation policy; automation uses the unchanged execution policy.
The actual production XML and policy fragments are injected only when
`PreparedContext.should_inject` permits it. QA output is exactly an `answer`
field. Execution output is exactly one `selections` item with the requested
surface and an ID or null. The complete execution response enters the guard;
QA IDs never enter execution selections or conversation history.

Both models receive identical requests for each corpus: temperature 0, seed 0,
thinking disabled and 128 output tokens. The context allowance is explicitly
6000 estimated tokens, 12 entities and 6 candidates per mention, matching the
prior synthetic allowance. This tests the production API at that configuration,
not its default 800-token allowance. Serialization, profiles, task schemas and
injection differ from older probes, so aggregate changes against older runs
are not a causal policy estimate.

Reports separate semantic correctness, guard acceptance, safe and
policy-required abstention, avoidable abstention, malformed output and missing
responses. They retain task/stratum results, both-correct scores for all 37
contextual contrast pairs, unexpected QA IDs, wrong accepted execution IDs,
actual tokens and latency percentiles. Exact-definition QA matching does not
credit paraphrases or apply answer repair. Paired 12B/27B comparisons require
identical request hashes, protocols and decoding. The comparison changes model
family as well as size.

## Reproduction

Freeze requests before live inference:

```sh
python -m eval.prepare_production_queue \
  --out-dir /path/to/new/frozen-requests --code-revision COMMIT_SHA
```

The queue plan records envelope and request hashes, source archive hash,
successful tests at that revision, runtime paths, ordered stages and checkpoint
identity. Downloaded Qwen weights use an immutable Hugging Face revision.
An existing Gemma checkpoint without established upstream identity is reported
as `NOT_VERIFIED`; a served name alone is not checkpoint verification.

```sh
python -m eval.run_production_queue --plan /path/to/queue-plan.json
python -m eval.collect_production_queue --config /path/to/collector-config.json
```

Run both in persistent background sessions with private logs and status files.
The worker uses an owned loopback vLLM server and serial requests, releasing
its runtime between stages. It waits for GPU/port availability instead of
stopping other jobs (24-hour resource deadline per stage). Model download has
a four-hour deadline. A failed stage remains failed and subsequent stages are
attempted. Precision, checkpoint, prompts and gold never silently change.
Malformed output and transport errors remain recorded without retries.

The collector waits for terminal completion, retrieves artifacts and bounded
log excerpts, verifies seals and recomputes grades from frozen requests and
responses. Each stage report is a separate commit; paired comparisons and the
overview form another commit. Only this queue's paths are staged. Collection
refuses to commit/push if the active branch changed or main is not synchronized
with origin/main, preserving independently created local commits. Remote
results survive local collection failure.

Terminal status means processes finished; each stage's status and report state
whether a comparison completed. Worker status contains progress and exit codes;
collector status separately records collection errors and pushed commits.
