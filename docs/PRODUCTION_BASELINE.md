# Paired KTRF versus no-resolver glossary baseline

The production queue in `reports/production_queue_20261013T160054Z` compared
two models with KTRF enabled. It cannot establish KTRF's incremental benefit.
The older `reports/AB_GROUNDING.md` includes LLM-only and retrieval controls,
but uses different tasks and data and cannot replace a control for this queue.

## Primary comparison

For each of the same 437 synthetic and 60 real sentences, compare:

- **B: plain glossary + LLM.** Retrieve from the same active glossary using
  deterministic lexical matching on the target and sentence. Supply entity
  IDs, names, aliases, full definitions and scope information. Do not use KTRF
  resolution status, scores, decomposition, context packs or execution guard.
- **C: production KTRF + LLM.** Reuse the sealed responses from the completed
  production queue, including its actual prepared policy and execution guard.

Both conditions use the same source text, target span, semantic gold, model,
decoding and response JSON shape. QA asks for the supplied glossary definition.
B execution asks for the glossary ID supported by the sentence; it does not
require a resolver-approved binding that a no-resolver pipeline cannot have.
C retains its production execution instructions. This estimates the complete
pipeline intervention, including selection, rendering, policy and validation;
it does not isolate a single component or a prompt-only effect.

B has the same 6000 estimated-token context allowance and up to 12 entities.
Selection never reads gold, expected answers or C's retrieved candidates.
Candidate recall, selected entity count and actual prompt-token cost are
reported. Deterministic lexical retrieval is a named baseline, not a claim
about the best possible dense or learned retrieval system.

An LLM-only condition without the glossary is not the primary control for this
task: private definitions and opaque entity IDs are unavailable to it. Removing
the glossary would combine the benefit of providing information with the benefit
of KTRF. Report this information asymmetry explicitly whenever that condition
is included, and separate public-knowledge QA from private-definition/ID tasks.

## Requested document-context comparison

The requested next matrix is: no additional context, the complete source
document, a retrieved passage with its neighboring context, and KTRF context.
The definition of source document must be fixed before preparing this matrix:
a knowledge document containing definitions and the original article containing
the target measure different interventions. The existing real fixture contains
sentences, not recoverable complete source articles; sentence-only evidence must
not be described as a whole-article benchmark.

Keep the question and target text fixed across conditions. No additional
context still includes the question. Record document IDs, revisions, hashes,
chunk offsets and the neighbor-window rule. A complete-document condition must
actually include the complete document; an over-limit document is an explicit
ineligible case rather than a silently truncated full-context result. Report
retrieval recall, evidence availability, answer changes, token use and latency.
Changing the QA rubric requires a new protocol and matched KTRF requests; the
existing exact-definition C responses cannot silently become a new QA baseline.

The currently implemented plain-glossary control is one component of this
comparison. It does not yet represent all requested document-context conditions.

## Outcomes and validation

The common primary outcome is the raw semantic task match, with identical
schema checks, before either condition's execution validation. Report QA and
execution separately, with helpful/harmful paired flips, wrong non-null answers,
positive-target abstention, malformed output, missing responses and strata.

Operational metrics are separate: B accepts only a well-formed response and a
null or provided glossary ID; C applies its actual execution guard. Report
accepted correct IDs, accepted wrong IDs and acceptance coverage for each.
Never apply the KTRF guard to B and label that result no-KTRF performance.
Wrong accepted IDs must not be hidden by a combined QA/execution average.

Stored latency and token observations measure the LLM calls. They do not include
a matched end-to-end timing experiment for both selectors. The same checkpoints
and serving settings are reused, but the B and C runs occur at different times
on a shared GPU host. Serving contention can affect latency.

This is a post-hoc diagnostic comparison on already examined cases. Gold and
original C responses remain unchanged. Real text has independent AI annotation
and adjudication, not independent human verification or random deployment
sampling. The explicit context allowance differs from the 800-token default.

## Execution and reproduction

Freeze the B requests and the immutable reference seals before new inference:

```sh
python -m eval.prepare_baseline_queue --out-dir /path/to/new/requests \
  --code-revision COMMIT_SHA
```

A schema-version-2 queue runs synthetic Gemma12B (874 calls), synthetic Qwen27B
(874), real Gemma12B (120), then real Qwen27B (120). Only B requires new calls:
**1,988 total**. Model identity and decoding must match the relevant C run.

```sh
python -m eval.run_production_queue --plan /path/to/baseline-plan.json
python -m eval.collect_production_queue --config /path/to/collector-config.json
```

Each report verifies the new manifest and artifact hashes, regrades frozen B
outputs, verifies the matching sealed C report and checks source/gold/decoding
identity before paired comparison. The collector requires exact equality of
remote and local reports. Original production reports are never overwritten.
Failure, missing output and malformed JSON remain visible without repair.
