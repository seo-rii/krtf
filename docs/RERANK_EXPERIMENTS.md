# Target and structural-path reranking experiments

The next comparison holds retrieval candidates fixed and changes how the target
is presented to one scorer. This isolates target confusion from encoder size.
The runner is an experimental shortlist scorer; it issues no automatic commits.

## Inputs and hypotheses

The ranking unit is `(core span, StructuralPath, entity ID, full_identity)`.
`ktrf.rerank.LinkingHypothesis` keeps these together. `rank_hypotheses` scores all
supplied hypotheses and evaluates the existing `ResolutionGuard` independently
of the score. A high relevance score cannot lift `typed_derivative` or an unknown
residual block. Ranking retains blocked hypotheses for diagnostic inspection.

Production snapshots expose `RuntimePolicy(rerank_input="context")`; the default
keeps the previous context-only input. `surface`, `target` and `path` are opt-in
choices. Exact proposals supply their typed tail/prefix to the path query; Level B
proposals retain their accepted `StructuralPath`. Abbreviation proposal scanning
now collects every path within `max_segmentation_paths`, instead of stopping at
the first successful decomposition. Dense query and rerank pair budgets still
apply. Recalibrate before adopting a changed format for commit decisions.

| Input variant | Query provided to the same scorer | Entity side |
|---|---|---|
| `surface` | Raw target surface | Canonical, description, domain |
| `context` | Surrounding window | Same profile |
| `target` | Window with the selected occurrence marked `[TARGET]…[/TARGET]` | Same profile |
| `path` | Marked window plus typed decomposition, raw span and full-surface identity/relation | Same profile |

The target mark uses raw document offsets, so repeated surfaces refer to the
selected occurrence. `path` includes identity/relation even when their values are
defaults. Altering the input format changes the evidence distribution and needs
independent calibration before using it to make production decisions.

## Reproducible local runs

Run from the repository root:

```bash
python -m eval.run_rerank_ablation --out eval/out/rerank_ablation.json
python -m eval.run_rerank_ablation --cases /data/blind_rerank_test.jsonl \
  --backend onnx --model-dir /models/export --max-length 192 --budget 8 \
  --out eval/out/rerank_onnx.json
python -m eval.run_rerank_ablation --backend scalar --model-dir /models/KURE-Reranker-nano \
  --max-length 192 --budget 8 --out eval/out/rerank_scalar.json
python -m eval.run_rerank_ablation --backend maxsim --model-dir /models/KURE-v2 \
  --max-length 192 --budget 8 --out eval/out/rerank_maxsim.json
```

Neural runs require local weights. The scalar adapter requires PyTorch and
Transformers; the MaxSim adapter additionally requires PyLate. Local-only model
loading avoids implicit downloads. Neural adapter integration is unverified
until the actual checkpoint, dependencies and hardware are available. ONNX
requires the existing sequence-pair, one-logit export contract. KURE-v2 requires
masked per-token representations and MaxSim; its vectors do not fit `VectorIndex`.

Shortlists are selected in input order once, before any ablation. Every variant
uses the same candidate budget and context radius. The three neural adapters use
the same configured combined token allowance; MaxSim divides it evenly between
query and document while cross-encoders share the total cap across the pair. The
manifest records both MaxSim caps. Report actual token counts when comparing
architectures. Changing the query cap also changes KURE-v2 query expansion;
retain a model-native-length control in a later model comparison. The lexical
baseline has no tokenizer and is not a neural latency comparison.

Timing uses serial batch-one pair calls, including tokenization, model execution
and CPU score transfer. Each format has one untimed warmup case. Retrieval,
snapshot compilation and model loading are excluded. The JSON records p50/p95/p99,
pair counts, model-content hash, case hash, installed package versions, device,
length cap, radius and repeats. Profile encoding is repeated in MaxSim timing;
a later cached-profile experiment must report this changed condition separately.

## Data and hard negatives

Each JSONL case contains `case_id`, `document_id`, `family_id`, `source`, `text`,
`ambiguity`, `gold` and an ordered `candidates` list. `gold` gives entity ID, exact
core span and full identity; each candidate gives entity ID/profile and the
structural path fields. The example schema is
[rerank_confusion.jsonl](../eval/data/rerank_confusion.jsonl).

The included 12 constructed cases cover shared aliases, multiple targets in one
sentence, one-vowel names, parent versus subsidiary, organization versus leader,
ordinary-word overlap and competing decompositions. Cases are labeled
`resolvable`, `ambiguous` or `nil`. Truly ambiguous cases have multiple acceptable
gold hypotheses; NIL cases have none. Top-one exact-link metrics exclude both
categories instead of inventing a uniquely correct sense. They remain in per-case
diagnostics and later risk evaluation.

Export pairs for later training, preserving document/family/source grouping:

```bash
python -m eval.run_rerank_ablation --cases /data/annotated_cases.jsonl \
  --pairs-out eval/out/confusion_pairs.jsonl --pairs-variant path
```

Gold hypotheses receive positive labels; other *actual confusing candidates*
receive negative labels. Ambiguous cases keep all acceptable senses positive.
Split documents and entity families before training; never split candidate rows
from one mention. Keep fit, calibration, threshold-selection and sealed test
events disjoint. Synthetic cases may test plumbing but cannot serve as independent
calibration or deployment-risk evidence.

## Evaluation gate

The runner reports exact-span/entity/full-identity top-one accuracy, family macro
accuracy, fixed-shortlist recall, candidate count, truncation and guard reasons.
Scalar logits, MaxSim and lexical scores are relevance evidence, not probabilities.
The report explicitly carries `coverage_valid=false` and
`calibration_status=INSUFFICIENT_DATA`: no conformal or commit-precision guarantee
has been fitted by this experiment.

For adoption, evaluate independent document gold with the same retrieved
candidates, candidate budget, input cap and latency envelope. Calibrate each input
format on disjoint events, select thresholds on separate validation events, then
report sealed-test commit rates at the same one-sided error upper bound. Count
retrieval misses, NIL overcommits, true-ambiguity overcommits and full-surface
identity errors; expose insufficient strata rather than granting confidence.
Report exact/fuzzy/abbreviation/dense, ambiguity and domain strata. A top-one gain
in this runner alone does not establish safer or more frequent automatic commits.

Do not add a larger encoder or a new multi-vector retrieval backend before this
controlled shortlist test shows a useful gain. ONNX export parity and batch-one
hardware latency are separate acceptance checks, not assumptions from model cards.
