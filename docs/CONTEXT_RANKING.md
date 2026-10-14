# Candidate and target-context ranking

This experiment asks whether a small pair scorer can distinguish the two
registered meanings of a shared alias using the document that contains it.
It follows the definition-control comparison, where explicit definitions
permitted 15 additional correct execution IDs per model but the 16 original
implicit positive documents still produced no permitted IDs.

The experiment ranks proposals. It does not change the production resolver,
approve an execution ID, fit a calibrator, or turn a relevance logit into an
entity probability.

## Fixed inputs and hypotheses

`eval.context_ranking_corpus.build_cases()` freezes all 64 existing documents
from `document_context` and `context_definitions`. Source text, glossary entries,
authored answers and annotations remain unchanged. Every case has both
registered family entities, including negative cases. Candidate construction
uses the family catalog, rather than production retrieval; the resulting
shortlist is an optimistic controlled input and does not measure retrieval or
mention-detection quality.

The selected occurrence is supplied as a raw document offset. The shared
segmenter derives its core and full-surface interpretation without consulting
the answer. Both entity hypotheses use this same path. The eight role controls
retain `DISTINCT / ROLE_OF` and the existing typed-derivative guard. No score,
including an arbitrarily large one, can remove that guard. These documents have
one matching structural path each; `path_full` tests adding decomposition
features to entity ranking, rather than choosing between competing paths.

Candidate profiles contain the same registered canonical name, all surfaces
and exact short definition in every condition. IDs, gold, rationales and
decisive-evidence annotations do not enter model inputs.

| Variant | Query side of each pair |
|---|---|
| `surface` | Target core alone |
| `local_context` | Unmarked core with a 60-character radius |
| `target_local` | Same window with the selected core marked `[TARGET]` |
| `target_full` | Entire source document with the selected core marked |
| `path_full` | Same entire document plus the typed structural path |

The comparison uses the deterministic lexical scorer and the pinned
KURE-Reranker-nano checkpoint
`f3b3eff2b5251f135b638891ebe7d6c5ae94cc3e`. The latter produces raw scalar
relevance scores. All five variants have the same two candidates and the same
configured token allowance. Actual pair lengths are checked before the first
inference; overflow aborts the run instead of silently dropping document cues.

Batch size is one. Untimed warmup is excluded. Pair latency includes tokenization,
model execution and score transfer; CUDA measurements synchronize before and
after each call. Model loading, snapshot compilation and retrieval are excluded.
The report preserves every candidate score, structural verdict, query/profile
digest, token length, model identity, software version and corpus hash.

## Grading and risk checks

Only the 32 `LINK` documents contribute to exact-span/entity/full-identity
top-one accuracy. The other 32 documents require abstention: eight each of
`AMBIGUOUS`, `NIL`, `COMPOSITIONAL` and `NON_MENTION`. Selecting either candidate
in a genuinely ambiguous document counts as an erroneous proposal. A correct
core candidate in a role expression does not authorize substituting the whole
expression with an organization ID.

The fixed family partition is determined by sorting
SHA-256(`context-ranking-family-v1:` + family ID). Tune families are
`f05, f03, f01, f02`; test families are `f08, f06, f04, f07`. Both document
collections stay in the same family partition. Each side has four families and
32 documents. These data were previously inspected and evaluated, and are
AI-authored synthetic material with `human_verified=false`. This split is a
diagnostic separation, not a sealed independent deployment audit.

The threshold grid is fixed before scores are measured. Scalar minimum scores
are `[-12, -9, -6, -3, 0, 3]`, with margins `[0, 0.25, 0.5, 1, 2]`; lexical
minimum scores are `[0, 0.3, 0.5, 0.7]`, with margins `[0, 0.025, 0.05, 0.1]`.
Every rule also requires a strictly positive margin and a passing structural
guard. Ties abstain. Tune-only exploratory selection cannot consult test scores.
Exploratory rules remain uncertified.

For the conservative risk diagnostic, one family containing any erroneous
proposal is one failed family trial. All documents from both collections stay
inside that trial. This estimates a different quantity from per-commit entity
error and must not be presented as that error rate. Exact one-sided binomial
bounds divide the statistical budget across stages, input variants and rules.
With only four families per side and a five-percent target, even zero observed
errors cannot establish the required bound. Synthetic authorship is a separate
reason to keep `coverage_valid=false` and execution authorization disabled.

The outputs compare overall and family-macro ranking, local versus remote cues,
canonical versus definition declarations, incorrect negative proposals,
structural blocks and batch-one cost. The next adoption decision requires a
separate independent document audit, disjoint calibration and a sufficiently
large fixed-risk validation sample. These results alone do not justify changing
`RESOLVED`, the context-pack execution contract or production thresholds.

## Reproduction

Freeze the cases once and run both backends from the same source revision:

```python
import json
from pathlib import Path
from eval.context_ranking_corpus import build_cases

Path("cases.jsonl").write_text(
    "".join(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n"
            for case in build_cases()), encoding="utf-8")
```

```bash
python -m eval.run_context_ranking --cases cases.jsonl --backend lexical \
  --repeats 3 --out lexical.json
python -m eval.run_context_ranking --cases cases.jsonl --backend scalar \
  --model-dir /models/KURE-Reranker-nano-f3b3eff2b525 \
  --model-id nlpai-lab/KURE-Reranker-nano \
  --model-revision f3b3eff2b5251f135b638891ebe7d6c5ae94cc3e \
  --device cuda --max-length 1024 --repeats 3 --out nano.json
```

No runner downloads weights implicitly. The run manifest records the exact
checkpoint and content digest, source revision, frozen cases and protocol,
hardware, log locations and final exit status.
