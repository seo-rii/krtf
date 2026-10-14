# New family target context ranking

This comparison tests whether the earlier exploratory ranking rules transfer
to newly authored Korean glossary families, especially when a document contains
two occurrences of the same alias with different referents. Lexical and nano
scorers receive fixed complete candidate pairs. Production execution remains
unchanged.

The preceding comparison ranked all 32 positive documents correctly with
whole-document context for both scorers. Its marked whole-document exploratory
rules selected 14 correct lexical proposals and 27 correct nano proposals
across 64 documents, with no observed errors. Those rules were not statistically
certified. The new experiment keeps them fixed instead of choosing thresholds
using the new answers or scores.

## Documents and target occurrences

The deterministic authoring fixture contains 24 new families, 336 documents and
384 target events. Each family registers two distinct teams with one shared
alias. Family IDs, term keys, aliases and canonical names do not overlap the
two prior context-ranking source collections. The domains and descriptions
cover different business functions, while the source prose shares reusable
authoring patterns.

Each family contains 14 documents and 16 targets:

| Condition | Targets per family | Intended interpretation |
|---|---:|---|
| Nearby paraphrases | 2 | One registered team |
| Remote paraphrases | 2 | One registered team |
| Same alias in two sections, both section orders | 4 | Two different teams within each document |
| Affirmed paraphrase with a negated canonical decoy | 2 | Affirmed team |
| Insufficient context for two legitimate meanings | 1 | Ambiguous |
| Name of an unregistered object | 1 | NIL |
| Rejected quoted editorial example | 1 | Non-mention |
| Alias with a role suffix | 1 | Distinct full-surface referent |
| Naming example that never took effect | 1 | Non-mention |
| Unregistered referent beside an unrelated registered definition | 1 | NIL |

The initial authoring design has 240 LINK and 144 abstention events. Independent
AI review may correct that grading without changing model inputs. The builder
validates the full document and target inventory without forcing reviewed labels
to match the designed positive count. The 96 nearby/remote paraphrase events
copy neither the correct canonical name nor its entire registered definition.
Documents are 252–412 characters long; this is a short-document stress test.

The selected occurrence is supplied as a raw source span. The same production
segmenter derives the core and nominal full-surface interpretation without
reading gold. Every event retains both registered family candidates, including
abstention events. All role targets preserve `DISTINCT / ROLE_OF` and the
typed-derivative guard. A high relevance score cannot approve those full
surfaces for substitution with a team ID.

## Review before inference

The author's fixture is hashed before a second AI annotator receives source
text, the two catalog entries and the target occurrence. The review projection
omits authored gold, titles, strata, evidence and rationales. Hashing and sorting
its IDs hides the generator's family and document ordering; a separate binding
map joins the results afterward.

The second annotator labels every event and supplies verbatim evidence and a
rationale. Disagreements are adjudicated before any model scores are produced.
The manifest preserves the original and final source hashes, projection and
review hashes, agreement counts and any adjudication. CLI inference requires
completed review and the matching final fixture identity.

These are newly authored synthetic documents with AI annotations and
`human_verified=false`. Source families are held out from the previous
comparison, but templated authoring and related annotations do not constitute
an independent deployment audit or human gold.

## Fixed comparison

| Query variant | Query side |
|---|---|
| `surface` | Core surface alone |
| `target_local` | Selected core marked within a 60-character radius |
| `context_full` | Entire document without a target mark |
| `target_full` | Entire document with the selected core marked |

The entity side is unchanged: canonical name, all aliases and short definition.
Gold, annotation evidence, rationales and entity IDs never enter scorer inputs.
The same two hypotheses and existing structural verdicts remain in every arm.

The lexical rule requires score ≥0.7 and margin ≥0.1. The nano rule requires raw
score ≥0 and margin ≥2. Both additionally require a strictly positive margin
and a passing structural guard. These are the earlier marked full-document
tune-only rules, with their report hashes checked. Applying them to other input
formats is an explicit transfer diagnostic, not calibration for those formats.
The new corpus supplies no threshold search or fitted probabilities.

Nano uses the pinned checkpoint
`f3b3eff2b5251f135b638891ebe7d6c5ae94cc3e` and the previously measured model
content digest. The combined pair allowance is 1,024 tokens. Every actual pair
is tokenized before warmup or inference, with truncation disabled; overflow
aborts the entire comparison. Each backend makes 3,072 measured batch-one pair
calls across four variants and one repeat, plus untimed warmup. A single repeat
does not verify determinism.

## Measures and interpretation

The report separates positive exact-span/entity/full-identity ranking, selected
correct and erroneous proposals, negative labels, strata, domains and families.
Two targets from one document are also graded together. For the 48 two-target
documents, an unmarked whole-document query gives exactly the same query/profile
pairs at both positions. Deterministic scoring cannot select two different
entities from those identical inputs. The report checks actual input and score
identity and compares both-target success with marked inputs.

All targets from a family stay inside one risk cluster. A family with any
erroneous proposal contributes one failed family, conditional on that family
having a proposal. The descriptive exact upper bound uses alpha 0.00625,
allocating 0.05 across four query variants and two scorers. The quantity differs
from per-proposal entity error, and the synthetic sampling does not satisfy
population risk assumptions. Coverage validity and production authorization
remain false regardless of observed error counts.

Pair latency includes tokenization, model execution and CPU score transfer;
CUDA calls synchronize around measurement. Loading, retrieval, snapshot
compilation and LLM generation are excluded. The manifest records actual dtype,
GPU, package versions, token lengths, source and input hashes, completed tests
and exit codes. The complete catalog shortlist and supplied spans do not test
production candidate retrieval or mention detection.

The adoption question is whether marked context improves difficult target
selection while frozen rules abstain on non-mentions, NIL and true ambiguity.
Any failures motivate a new development set and a later untouched evaluation,
rather than adjusting the thresholds on this test.

## Reproduction

From the repository root, with the adjudicated fixture and local model present:

```bash
python -m eval.run_context_ranking_challenge --backend lexical \
  --out /tmp/challenge-lexical.json
python -m eval.run_context_ranking_challenge --backend scalar \
  --model-dir /models/KURE-Reranker-nano-f3b3eff2b525 \
  --model-id nlpai-lab/KURE-Reranker-nano \
  --model-revision f3b3eff2b5251f135b638891ebe7d6c5ae94cc3e \
  --device cuda --max-length 1024 --repeats 1 \
  --out /tmp/challenge-nano.json
```

`--cases` accepts the frozen case export, and `--source-revision` records its
inference revision. The CLI checks the protocol, earlier rules, adjudicated
fixture, frozen cases and model identity before producing scores.
