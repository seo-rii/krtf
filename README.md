# KTRF — Korean Terminology Resolver Framework

Reference implementation (Python) of the **V1 symbolic core** described in
[PLAN.md](PLAN.md) (spec v0.3). V1 corresponds to spec §33/§55: a zero-GPU,
deterministic resolver covering all of **Level A** (closed-world surface
resolution) plus the fuzzy / keyboard / document-local / abbreviation-alignment
channels, with heuristic fusion and fast/aggressive/commit execution modes.

## What is implemented (V1 scope)

| Area | Spec | Module |
|---|---|---|
| Offset contract (byte/codepoint/UTF-16) | §13 | `ktrf/offsets.py` |
| Hangul jamo decompose/compose, dubeolsik keyboard | §17.2, §17.4 | `ktrf/hangul.py` |
| Canonical normalization stream + MappedUnit provenance | §14 | `ktrf/normalization.py` |
| Glossary schema, strict validation, content lint | §10, §47.7 | `ktrf/glossary.py` |
| Particle FST (조사 catalog + chaining), suffix/prefix catalogs | §16 | `ktrf/morphology.py` |
| Exact alias matcher + boundary policies | §15 | `ktrf/matcher.py` |
| Prefix/core/residual/particle tail parser | §16 | `ktrf/tailparser.py` |
| Jamo/keyboard fuzzy recovery | §17 | `ktrf/fuzzy.py` |
| Document-local alias | §18 | `ktrf/doclocal.py` |
| Abbreviation alignment (Pass 2) | §21.7 | `ktrf/abbrev.py` |
| Candidate union + budgets (exact pool exempt) | §21, §31 | `ktrf/candidates.py` |
| Mention graph, primary selection, modes, resolve pipeline | §20, §26, §27 | `ktrf/resolver.py` |
| Immutable snapshot + atomic activation | §11 | `ktrf/snapshot.py` |
| Conformance fixture generation + suite | §14.8 | `ktrf/conformance.py` |
| Error schema | §27.6 | `ktrf/errors.py` |
| REQ traceability matrix + CI check | §1.2, 부록 D | `docs/traceability.yaml`, `tests/test_traceability.py` |
| Evaluation harness (deterministic datagen + metrics) | §37, §43–44 | `eval/` |

## Deliberate deviations from the production spec

- **Language:** Python instead of Rust runtime core (§34). This is a reference
  implementation; the module boundaries mirror the recommended monorepo layout.
- **Artifacts:** snapshots are immutable in-memory objects with a hashed
  manifest, not mmap `.bin` bundles (§11.1/REQ-MEM-001 deferred to Rust core).
- **No HTTP layer:** the sync Resolve API is exposed as a library call with the
  spec's request/response/error schema; async job API (§28), correction API
  (§30) and memory tiers (§32) are M3+ scope and not implemented.
- **Calibration:** V1 ships the "global conservative calibrator" placeholder
  (§48.1): heuristic probabilities capped conservatively; group-conditional
  conformal calibration is M4 (V2) scope.

## Usage

```python
from ktrf import load_glossary, compile_snapshot, resolve

glossary = load_glossary("examples/demo_glossary.yaml")
snapshot = compile_snapshot(glossary)
resp = resolve(snapshot, "한전KDN은 AP 장애 내용을 QMS에 등록했다.", mode="commit")
for m in resp["mentions"]:
    print(m["surface"], m["link_decision"])
```

## Tests & evaluation

```bash
python -m pytest                 # unit/property/conformance/traceability tests
python -m eval.run_eval          # generates eval data, runs metrics, writes eval/out/
```
