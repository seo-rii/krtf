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
| Snapshot save/load (artifact bundle + hash verification) | §11, §47.3 | `ktrf/artifacts.py` |
| Correction workflow (approval, tenant isolation, caps) | §30 | `ktrf/corrections.py` |
| Tenant calibrator: Platt + group-conditional conformal | §25, §48.3 | `ktrf/calibration.py` |
| Evaluation harness (deterministic datagen + metrics) | §37, §43–44 | `eval/` |

## Deliberate deviations from the production spec

- **Language:** Python instead of Rust runtime core (§34). This is a reference
  implementation; the module boundaries mirror the recommended monorepo layout.
- **Artifacts:** snapshots are immutable in-memory objects with a hashed
  manifest, not mmap `.bin` bundles (§11.1/REQ-MEM-001 deferred to Rust core).
- **No HTTP layer:** the sync Resolve API, glossary compile/activation,
  correction workflow and finetuning are exposed as library calls with the
  spec's request/response/error schemas; the async job API (§28) and memory
  tiers (§32) are M3+ scope and not implemented.
- **Calibration:** zero-training tenants start on the heuristic "global
  conservative calibrator" (§48.1). `finetune()` upgrades a tenant to a fitted
  calibrator — Platt-scaled marginals plus group-conditional split conformal
  prediction sets with n_min fallback (§25.2) — from ACCEPTED corrections.
  Neural stages (bi-/cross-encoder, §33 V2+) remain out of scope.

## Usage

```python
from ktrf import load_glossary, compile_snapshot, resolve

glossary = load_glossary("examples/demo_glossary.yaml")
snapshot = compile_snapshot(glossary)
resp = resolve(snapshot, "한전KDN은 AP 장애 내용을 QMS에 등록했다.", mode="commit")
for m in resp["mentions"]:
    print(m["surface"], m["link_decision"])
```

### Save / load snapshots (§11 artifact bundle)

```python
from ktrf import save_snapshot, load_snapshot

save_snapshot(snapshot, "artifacts/demo-org")   # manifest + glossary + policy (+ calibrator)
snapshot = load_snapshot("artifacts/demo-org")  # deterministic recompile + hash verification
```

Loading recompiles indexes from `glossary.yaml` and verifies the recomputed
content hashes against the stored manifest — tampered or incompatible bundles
refuse to load (§47.3, INV-015).

### Finetuning (§48.3 adaptation loop)

V1 finetuning fits a **tenant calibrator** (Platt-scaled marginals +
group-conditional split conformal prediction sets, §25.2) from approved
corrections. The glossary and indexes are never modified; only the calibrator
artifact changes, and the result is a *new* snapshot to activate explicitly.

```python
from ktrf import CorrectionStore, finetune

store = CorrectionStore()
c = store.submit(
    tenant_id="default",
    request_ref={"snapshot_id": resp["snapshot"]["snapshot_id"],
                 "request_id": "req-1", "mention_id": "m2"},
    correction_type="WRONG_ENTITY",
    corrected={"entity_id": "WORKFLOW_APPROVAL_PROCESS"},
    verifier={"kind": "REVIEWER", "principal_ref": "rev-1"},
    mention_state=resp["mentions"][1],   # spans/scores — no raw text (§30.2)
)
store.review("default", c.correction_id, "ACCEPTED", reviewer="admin")

tuned = finetune(snapshot, store, alpha=0.05,
                 golden_check=lambda s: my_golden_regression(s))  # §48.3 gate
```

Only `ACCEPTED` corrections feed fitting (INV-018), verifier kinds are
weighted and per-principal capped against poisoning (REQ-COR-003), and a
failing golden regression refuses the finetune. The tuned snapshot round-trips
through `save_snapshot`/`load_snapshot` with its own `calibrator_hash`.

## Tests & evaluation

```bash
python -m pytest                 # 144 unit/property/conformance/traceability tests
python -m eval.run_eval          # eval corpus + golden set + release gate -> EVALUATION.md
python -m eval.run_benchmarks    # adversarial anti-overfitting suite -> BENCHMARKS.md
python -m eval.run_wild          # real Korean text (HuggingFace KLUE) -> WILD_CORPUS.md
python -m eval.benchmark         # latency-only scale benchmark
```

Current results ([EVALUATION.md](EVALUATION.md)): conformance **0 failures /
544 fixtures** (and 0/74,450 on a 500-entity synthetic glossary), Level A
core-span recall (E2E) 213/213, golden-set recall 19/19 with 0 violations,
RESOLVED precision (|commit) 1.0, release gate **PASS**. fast mode resolves in
&lt;1ms; commit mode p95 ≈ 54ms at 2,000 entities (Python reference — the
production Rust core in §34 is the optimization target).

Because the catalog-derived eval cannot detect overfitting (it shares the
§14.7/§16 catalogs with the implementation), [BENCHMARKS.md](BENCHMARKS.md)
runs independently generated adversarial suites at 200/1000/3000 entities ×
3 seeds: synthetic glossaries with natural abbreviation collisions and
near-miss siblings, boundary-trap corpora (대한전선-style embeddings), stacked
transform compositions, out-of-catalog tails, term-free negative corpora,
1-jamo distractor typos, unicode fuzzing and pathological inputs, plus
fit/holdout calibration coverage. Hard gates (boundary violations, sense
loss, arbitrary commits, crashes, offset failures) must be 0 at every scale;
a fast subset runs in CI (`tests/test_adversarial_regressions.py`). This
suite caught two real bugs on first run — unknown-tail overcommit and
non-conservative calibration fallback — both now fixed and pinned by
regression tests.

[WILD_CORPUS.md](WILD_CORPUS.md) evaluates against **real Korean text**:
~5,200 news sentences from HuggingFace KLUE (CC BY-SA 4.0, fetched by
`eval/wild_data.py` — the repo ships the downloader, not the data) with a
46-entity real-organization glossary (`examples/realorg_glossary.yaml`).
Suites: silver-labeled recall on unambiguous org surfaces (168/168
gold-in-set, RESOLVED precision 1.0), real-distribution particle/suffix
coverage — the §5.2 metric, measurable only on real text — and a
fake-glossary suite where any commit on real text is a false positive by
construction (0 commits). The tail-coverage signal drove a §16 catalog
extension exactly as §3.5 prescribes (role suffixes 장/장관/원장, corporate
suffixes 그룹/증권, contracted particles 엔/에선), lifting real-tail coverage
from 29% to 78% with the remainder being genuine non-organizational tails.

The traceability matrix (`docs/traceability.yaml`, enforced by
`tests/test_traceability.py`) maps all 61 spec REQ IDs: 54 implemented+tested,
7 explicitly deferred with milestone reasons (async API → M3, neural
stages/termness → M4, mmap artifacts and memory tiers → Rust core).
