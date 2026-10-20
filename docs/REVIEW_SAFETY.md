# Review safety contracts and migration

2026-10-20. These changes address the review of `6164ef6`. They strengthen
provenance and validation contracts; they are not new measurements of deployment
accuracy. The [followup experiment plan](REVIEW_EXPERIMENTS.md) evaluates the new
policies and budget choices separately.

## One source component remains one calibration unit

`cal-3` keeps the transitive event/document/request/correction components used
for splitting through score aggregation, group counts and coverage eligibility.
Shared provenance connects rows even when the first and last rows share no
direct identifier. Components enter deterministic, disjoint fitting and
calibration partitions; input row order does not change the result.

Each component contributes its maximum positive nonconformity to each represented
group and one maximum to the pooled quantile. `group_counts` counts source
components in that group; `partition_manifest.calibration_units` counts distinct
scored components across groups. Repeated verifier weights do not increase
calibration sample size. Thirty documents describing one event are one unit.

The manifest records component IDs, group membership, positive observation counts
and the aggregation rule. A component with several distinct audited mentions
remains ineligible for the current one-audited-mention coverage claim. A future
cluster-aware audit protocol would need its own guarantee and scope. Merely
setting `sample_source="random_audit"` cannot establish representative sampling,
exchangeability or absence of distribution shift.

Historical calibrator dictionaries remain loadable. Without the new component
proof, coverage is false even if an old independence boolean was true. The
resolver additionally checks group support and truncation. Candidate-conditional
set coverage is separate from approved-ID precision and document-level risk.
See [CALIBRATION_SAFETY.md](CALIBRATION_SAFETY.md).

## Complete definitions or explicit omission

The builder preserves the whole selected definition, including trailing
exceptions, scope conditions and prohibitions. If `max_description_chars` or the
field hard cap cannot hold it, the fact/candidate is omitted as a whole and the
omission records its reason and field. This is a conservative omission policy,
not an implemented semantic summarizer.

Token budgeting may remove whole hints, reduce a candidate list while preserving
ambiguity, or remove complete mentions/facts. It does not cut a definition to
80 characters. Budget removals set `budget_truncated=true`, `complete=false`
and add omission records; character-limit omissions also make `complete=false`.
A surviving fact never becomes complete merely because the last reduction step
forgot to record lost information. Consumers should inspect both `coverage` and
`omissions` and use their actual tokenizer through `TokenCounter`.

## Execution binds to a document, snapshot and occurrence

`validate_llm_grounding(..., purpose="execution")` defaults to
`execution_contract="occurrence_v1"`. The automation profile applies execution
validation even when the caller omits `purpose`. A non-null selection must match
one non-degraded resolved fact occurrence on all of:

- `document_hash`: exact UTF-8 document SHA-256 from the context pack.
- `snapshot_id`: `pack["snapshot"]["snapshot_id"]` (the field is nested).
- `mention_id`: the occurrence reference in the fact's `mentions` list.
- `core_span` and `full_span`: exact codepoint `{start, end}` objects copied
  from that occurrence, with the core contained in the full extent.
- `surface` and `entity_id`: the same occurrence and resolved fact.

For example, when a host has already identified the requested mention, the
binding to validate has this shape:

```python
pack = automation.context_pack
requested_mention_id = host_request["mention_id"]
matched = [
    (fact, occurrence)
    for fact in pack["resolved_terms"]
    for occurrence in fact["mentions"]
    if occurrence["mention_id"] == requested_mention_id
]
if len(matched) == 1:
    fact, occurrence = matched[0]
    selection = {
        "surface": occurrence["surface"],
        "document_hash": pack["document_hash"],
        "snapshot_id": pack["snapshot"]["snapshot_id"],
        "mention_id": occurrence["mention_id"],
        "core_span": occurrence["core_span"],
        "full_span": occurrence["full_span"],
        "entity_id": fact["entity_id"],
    }
    check = validate_llm_grounding(
        {"selections": [selection]}, pack, purpose="execution")
```

This shows the binding schema, not an instruction to choose the first fact or
execute an action. The host must authenticate the pack's tenant/snapshot and
check that the requested occurrence is the one its user or workflow authorized.
`mention_id` alone is local to a response and is not globally unique. Raw token
`full_span` may include particles; copy the pack reference rather than replacing
it with a guessed nominal name span. A supplied legacy `span` must agree with
`core_span`.

An unresolved occurrence cannot reuse another occurrence's approved spelling.
Null entity IDs and an empty selections list are abstentions. QA envelopes,
mixed answer/selection outputs, malformed spans and absent binding fields do not
authorize execution. QA and execution remain separate model calls/conversations.
The guard cannot recover provenance after a host copies a QA ID into a new
selection, or correct every meaning the resolver itself resolved incorrectly.

`execution_contract="legacy_surface_v1"` is an explicit compatibility option for
regrading historical raw responses. Any occurrence fields supplied still invoke
the full occurrence check. Historical reports preserve their original contract;
they do not certify the new one. New automation should use `occurrence_v1`.

## Dense artifact identity and old bundles

A dense snapshot manifest now seals `entity_vectors_hash` over the serialized
index content, including vector values, entity row order, dimensions and index
kind. Loading verifies the seal, the expected encoder identity, finite and valid
vector shape, glossary entity order, encoder dimension and required file
presence. Missing vectors cannot silently turn a dense snapshot into a symbolic
one under the same identity. Unexpected vector files also refuse loading.

Old dense bundles without a vector seal are refused. Recompile from a trusted
glossary with the matching encoder and reviewed policy/guard, then save and load
a new bundle. For example:

```python
rebuilt = compile_snapshot(
    trusted_glossary, encoder=matching_encoder,
    policy=reviewed_policy, guard=reviewed_guard)
save_snapshot(rebuilt, "artifacts/rebuilt")
loaded = load_snapshot("artifacts/rebuilt", encoder=matching_encoder)
```

Rebuilding changes snapshot identity; use the normal conformance and activation
checks. Do not add a digest to an untrusted old manifest or manually edit its ID
as a substitute for migration. Symbolic bundles remain supported.

## QA task contracts and resolver guards

| Profile | Answer evidence and abstention |
|---|---|
| `qa_grounding` | Explain a term only when its supplied definition and target-expression context distinguish its meaning. Missing or unresolved meaning can require null. |
| `document_qa` | Answer general source-document questions when the source supports them. An absent term definition does not invalidate an explicit source date or fact; glossary facts alone do not establish an event in the source. |
| `automation` | Select only a validated resolved occurrence. Candidate membership, a fluent explanation and general knowledge grant no execution authority. |

These profiles do not change resolver commit thresholds, structural guards,
core/full-surface meaning or heuristic calibration into probabilities. `fast` is
not a safer commit mode; `aggressive` currently follows `commit`. The new general
QA policy has no measured accuracy advantage yet. The planned comparisons keep
policy, retrieved source and term facts controlled before product-level claims.
