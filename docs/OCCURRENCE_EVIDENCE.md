# Occurrence specific evidence comparison

This experiment separates selecting relevant source passages from checking
whether a statement is affirmed. It follows the new-family challenge where
whole-document nano input made 43 correct and 72 incorrect proposals under the
previously selected score/margin rule. That challenge is now development data.
A separate 12-family synthetic cohort evaluates the frozen implementation.

The new module does not choose entity IDs or participate in the production
resolver. It selects source passages and supplies a bounded heuristic assertion
check. Candidate ranking, the existing structural guard and diagnostic proposal
thresholds remain separate. Coverage validity and execution authorization stay
false.

## Controlled inputs

| Variant | Source passages | Additional proposal check |
|---|---|---|
| `target_full` | Entire document with the selected occurrence marked | Existing structural guard |
| `target_paragraph` | Whole paragraph containing the selected occurrence | Existing structural guard |
| `scoped_evidence` | Target paragraph and up to two eligible supporting paragraphs | Existing structural guard |
| `scoped_asserted` | Exactly the same input pairs as `scoped_evidence` | Structural guard and assertion check |

All variants retain both registered family candidates. Entity profiles contain
the same canonical name, aliases and short definition. Gold, annotation evidence,
rationales and stratum names never enter model inputs. The two scoped variants
use identical queries so their proposal difference measures the extra assertion
check rather than a changed scoring prompt.

The selector preserves raw source spans and quotations. It marks only the
designated core occurrence and joins complete passages in original source order.
For repeated aliases, scope stays at the selected occurrence's paragraph.
For a single occurrence inside an explicitly delimited section, eligible support
paragraphs are ranked by maximum lexical overlap with any registered candidate.
This uses catalog vocabulary without first selecting a winner. Complete passages
containing rejected assertions or negated requests cannot serve as support.

The assertion check rejects whole quoted claims, explicit target negation,
scoped retraction, declared unresolved reference and explicit unregistered
objects. Quoting a name alone does not reject an assertion outside the quotes.
An unrelated negated candidate name does not itself negate the target request.
These are bounded lexical rules: a passing result means that the implemented
vetoes did not fire, not that semantic entailment has been proved. Full-surface
role expressions still require the existing typed structural guard.

The selected source budget is 1,024 characters including markers and separators.
Overflow abstains instead of cutting a passage. The scalar pair allowance is
1,024 tokens; actual pair overflow aborts inference without truncation. The
report records passage offsets, reasons, rendered inputs, assertion verdicts
and all candidate scores so the selection can be reviewed independently.

## Development and held out cohorts

Development contains the consumed 24-family challenge: 336 documents and
384 target occurrences. Results on it describe development behavior and cannot
be reported as untouched evaluation.

The new held-out fixture contains 12 additional families, 144 documents and
168 target occurrences. Its intended design has 120 registered links and
48 abstention events: 12 each of rejected quotation, role composition, NIL and
genuine ambiguity. It includes nearby and remote paraphrases, two targets with
different meanings in the same document, affirmed requests beside negated
candidate names and positively asserted quoted names.

The selector developer does not inspect this new fixture. The selector source
is committed and hashed before the source-only blind annotation review starts.
Another AI annotator receives the catalog, source and target positions without
authored gold, rationales, titles or strata. Any disagreement is adjudicated
before scores exist; neither labels nor rules are adjusted using held-out model
results. The manifest records the selector freeze, original and final fixture
hashes and annotation artifacts.

Both cohorts are AI-authored synthetic documents. New families and separate AI
annotation do not constitute representative service documents or human gold.
The report keeps cohort results separate and checks family, catalog and source
identity overlap. Supplied spans and complete two-candidate catalogs exclude
mention detection and production candidate retrieval from this experiment.

## Fixed rules and grading

The earlier lexical threshold remains score ≥0.7 and margin ≥0.1. Nano remains
raw score ≥0 and margin ≥2. Both also require a strictly positive margin and a
passing structural guard. The asserted variant additionally requires its
assertion check. There is no threshold search, fitted probability or expansion
of execution authority.

Primary diagnostics are correct and erroneous proposals, positive exact-link
top-one accuracy and the number of multi-target documents where both targets
are correct. The report separates positive mistakes from NIL, ambiguity,
non-mention and full-surface errors, and reports correct positives rejected by
the added gate. Every original hypothesis remains in the scored candidate set.

All targets and documents from one family remain in one risk cluster. The
descriptive exact bound concerns a family with any erroneous proposal,
conditional on having a proposal. Alpha 0.003125 allocates 0.05 across four
variants, two backends and two cohorts. This quantity differs from per-proposal
error, and the synthetic data do not satisfy deployment sampling assumptions.
No numerical bound enables production execution.

Nano uses checkpoint `f3b3eff2b5251f135b638891ebe7d6c5ae94cc3e`, with the
earlier content digest checked. Both scorers process the same prepared inputs.
Each backend makes 4,416 measured batch-one pair calls over the two cohorts,
four variants and two candidates, plus warmup. One repeat does not verify
determinism. Pair timing includes tokenization, execution and score transfer;
selection cost is reported separately where measured. Loading, retrieval,
snapshot compilation and LLM generation are excluded.

## Reproduction

The CLI loads the consumed development fixture and the reviewed held-out fixture,
checks their hashes and requires the frozen selector's identity:

```bash
python -m eval.run_occurrence_evidence --backend lexical \
  --out /tmp/evidence-lexical.json
python -m eval.run_occurrence_evidence --backend scalar \
  --model-dir /models/KURE-Reranker-nano-f3b3eff2b525 \
  --model-id nlpai-lab/KURE-Reranker-nano \
  --model-revision f3b3eff2b5251f135b638891ebe7d6c5ae94cc3e \
  --device cuda --max-length 1024 --out /tmp/evidence-nano.json
```

The protocol, annotation manifest, prepared input proof, source revision,
checkpoint content hash and final exit status accompany the result artifacts.
