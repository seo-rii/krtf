# Knowledge documents and source-document context

This experiment crosses two distinct information axes. Every model answers the
same question about the same authored target under all twelve conditions:

| Axis | Conditions |
|---|---|
| Knowledge | no knowledge, complete knowledge document, retrieved knowledge paragraphs, KTRF context pack |
| Source | no source context, complete source document, retrieved source paragraph and its neighbors |

There are 32 complete Korean work documents, grouped in eight glossary families.
Each family has its own complete knowledge document. These are newly AI-authored
originals, not articles reconstructed from the old KONEC sentence fixtures.
Every source document is kept intact, with a stable ID and SHA-256. Gold and
decisive source/knowledge evidence are authored before resolver or model outputs.
The corpus includes distant and nearby clues, competing meanings, genuine
ambiguity, missing glossary entries, derived roles and ordinary-word nonmentions.
All eight shared aliases deliberately collide; source documents are short
six-paragraph memos. This is a context-disambiguation stress test, not a
representative workload or long-context/corpus-wide retrieval benchmark.

Each of 32 targets has separate definition-QA and entity-ID selection calls.
Twelve conditions therefore give 768 calls per model, or **1,536 total** for
Gemma4 12B and Qwen3.5 27B. All cells are new inference; historical production
responses are not relabeled to fit the new questions.

## What remains fixed and what changes

The question identifies the target expression, never the gold or its ID. With
source context absent, only the question and target are shown. Complete source
means the entire authored document. Retrieval uses lexical similarity and a
fixed paragraph-neighbor rule without reading gold evidence. Knowledge retrieval
may inspect only source text visible in that condition; hidden full-source clues
must not influence it. Retrieved offsets, parent IDs and hashes are retained.

Full knowledge is the entire authored glossary knowledge document. Retrieved
knowledge supplies passages from that document. KTRF uses the same glossary
facts with its real QA/automation context profiles and policy. The resolver only
sees the source text available to that condition (or the target alone when
source context is absent), so it cannot recover context hidden from other arms.
KTRF execution guard runs only on KTRF responses. Other arms get schema and
provided-ID membership validation, without being declared resolver-verified.

The exact knowledge evidence and policy change with the chosen arm. This
measures the complete intervention; it does not isolate formatting or a single
resolver component. The primary outcome is the common schema-valid semantic
match before execution validation. Accepted correct/wrong IDs and acceptance
coverage are separate operational outcomes.

No-knowledge rows intentionally test missing information. Private definitions
and opaque IDs cannot be recovered reliably from prior knowledge. No-source rows
can be genuinely ambiguous even when a full knowledge document is available.
Keep these information limitations visible instead of claiming every miss is
model incapability. Report source/definition/ID evidence availability with scores.

## Reproduction and cost

```sh
python -m eval.prepare_document_context --out-dir NEW_DIRECTORY --code-revision SHA
python -m eval.prepare_document_context --check-tokens-plan QUEUE_PLAN
python -m eval.run_production_queue --plan QUEUE_PLAN
```

Before GPU inference, both checkpoints' actual chat templates tokenize every
prompt with thinking disabled. The complete prompt plus 128 output tokens must
fit 8192 tokens. Overflow fails preflight; documents are never silently truncated.
The schema-version-3 queue waits for any declared earlier queue to finish, then
runs one owned model runtime at a time. It never stops another experiment.

Reports verify manifest seals, three artifact hashes, identities, counts and
frozen regrading. Paired comparisons vary one axis while holding the other fixed,
and report beneficial/harmful changes, error types, evidence retrieval, tokens
and latency separately for QA and routing. Model comparison changes family and
size together. Shared-host latency is descriptive, and model-call latency does
not include matched online retrieval/compilation costs. AI synthetic gold is
not independently human verified and does not establish deployment risk.
