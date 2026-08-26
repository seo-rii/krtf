# KTRF — Korean Terminology Resolver Framework

KTRF detects mentions of organization and domain terminology in Korean text
and links them to glossary entities — deterministically where the surface
form is known, statistically where it is not, and conservatively everywhere:
candidates are generated broadly, but a resolver **commit** happens only when
the evidence clears explicit thresholds. Anything less is returned as a
calibrated prediction set, never a guess.

```python
from ktrf import load_glossary, compile_snapshot, resolve

glossary = load_glossary("examples/demo_glossary.yaml")
snapshot = compile_snapshot(glossary)
resp = resolve(snapshot, "한전KDN은 AP 장애 내용을 QMS에 등록했다.", mode="commit")
for m in resp["mentions"]:
    print(m["surface"], m["link_decision"])
```

## Why KTRF

General-purpose NER and embedding retrieval both struggle with Korean
organizational terminology: agglutinative particle chains (`금감원은`,
`한전이`), productive abbreviations (`과기정통부` ← 과학기술정보통신부),
keyboard-layout typos (`gkswjs` ← 한전), homograph collisions (공사 the
corporation vs 공사 construction), and nested names (경기도교육청 ⊃ 경기도).
KTRF models each of these explicitly:

- **Deterministic core** — normalization with full offset provenance
  (byte/codepoint/UTF-16), Aho-Corasick exact matching over normalized
  channels, boundary policies, a particle FST with batchim constraints and
  depth-3 chaining, suffix/prefix catalogs, and a conformance suite that must
  pass 100% for a snapshot to activate.
- **Recovery channels** — jamo-level weighted edit distance, dubeolsik
  keyboard-mapping recovery, document-local alias detection, and
  abbreviation alignment for unseen short forms.
- **Optional neural layer** — bi-encoder dense retrieval (ONNX
  `multilingual-e5-small` reference backend, pure-Python hash-encoder
  fallback), conditional cross-encoder reranking, learned score fusion, and
  group-conditional split conformal prediction sets.
- **Operations** — immutable content-addressed snapshots with atomic
  activation and tamper-refusing artifact bundles, async document jobs,
  a human-in-the-loop correction workflow that feeds calibration, tenant
  isolation, memory tiering, and runtime metrics.

The full technical specification lives in [PLAN.md](PLAN.md); design
decisions for the neural backends are recorded in
[MODEL_RECOMMEND.md](MODEL_RECOMMEND.md).

## Installation

Requires Python 3.11+. The core has a single dependency (PyYAML):

```bash
pip install -e .                # symbolic core
pip install -e .[neural]        # + ONNX bi-encoder/cross-encoder backends
pip install -e .[gpu]           # + CUDA inference (onnxruntime-gpu)
pip install -e .[training]      # + cross-encoder fine-tuning (torch)
```

To enable the dense retrieval reference backend, download
`Xenova/multilingual-e5-small` (ONNX + tokenizer) into
`models/multilingual-e5-small/` and pass an encoder at compile time:

```python
from ktrf import compile_snapshot, load_encoder

snapshot = compile_snapshot(
    glossary, encoder=load_encoder("onnx:models/multilingual-e5-small"))
```

`load_encoder(spec, device="cuda")` selects the CUDA execution provider when
`onnxruntime-gpu` is installed and falls back to CPU otherwise; the
deterministic path always runs on CPU (see
[docs/GPU_PLAN.md](docs/GPU_PLAN.md) for measured GPU throughput).

## Snapshots as artifacts

A compiled snapshot is immutable and content-addressed: its `snapshot_id` is
a 128-bit digest over the complete manifest — full glossary serialization,
runtime policy, morphology catalogs, normalizer version, encoder/reranker
digests, and the conformance record. Any semantically meaningful change
produces a different identity.

```python
from ktrf import save_snapshot, load_snapshot

save_snapshot(snapshot, "artifacts/demo-org")
snapshot = load_snapshot("artifacts/demo-org")
```

Loading recompiles the indexes deterministically from the bundled glossary
and re-verifies every content hash plus the manifest/id equation — a
tampered `glossary.yaml`, `policy.json`, or `manifest.json` refuses to load.
Activation through `SnapshotRegistry` additionally requires a passing
conformance record.

## Adaptation without retraining

Approved corrections fit a per-tenant calibrator (Platt-scaled marginals +
group-conditional split conformal sets, with fit and quantile data kept
disjoint) and optionally a learned fusion model:

```python
from ktrf import CorrectionStore, finetune

store = CorrectionStore()
c = store.submit(tenant_id="default", request_ref={...},
                 correction_type="WRONG_ENTITY",
                 corrected={"entity_id": "WORKFLOW_APPROVAL_PROCESS"},
                 verifier={"kind": "REVIEWER", "principal_ref": "rev-1"},
                 mention_state=resp["mentions"][1])
store.review("default", c.correction_id, "ACCEPTED", reviewer="admin")

tuned = finetune(snapshot, store, alpha=0.05, golden_check=my_regression)
```

Only `ACCEPTED` corrections feed fitting, verifier kinds are weighted and
per-principal capped against poisoning, and a failing golden-set regression
refuses the finetune. The result is a *new* snapshot; the input is never
mutated.

## LLM grounding (terminology context packs)

To put KTRF in front of an LLM, don't render resolver output straight into a
prompt — build a **context pack**, a structured intermediate representation
with strict status separation:

```python
from ktrf import prepare_llm_context, ContextPolicy, validate_llm_grounding

prepared = prepare_llm_context(
    snapshot, document, query="금감원의 PF 점검 결과는?",
    context_policy=ContextPolicy(profile="qa_grounding", max_tokens=800))

prompt = prepared.policy_fragment + "\n" + prepared.prompt_fragment
# ... call your LLM, then gate structured output before automation:
check = validate_llm_grounding(llm_output, prepared.context_pack)
```

The builder keeps RESOLVED facts, AMBIGUOUS candidate sets,
document-asserted definitions, and unknown mentions structurally separate
(a candidate is never rendered as a fact), deduplicates entities across
mentions (`observed_as` + occurrence count), selects query-relevant entities
with a deterministic heuristic (no LLM calls inside the layer), enforces a
hard token budget with a fixed reduction order and honest
`coverage`/`omissions` metadata, strips control characters and escapes
everything at render time, and ships a fixed `terminology_policy` fragment
from code so glossary content can never rewrite the rules. Glossary entities
can carry an optional `grounding:` block (`short_definition`,
`disambiguation_hints`, `injection_policy`, `classification`) for
prompt-ready definitions and clearance filtering.

## Agent integration (layered terminology + sidecar)

For editor/agent hosts, terminology usually arrives in scopes — a company
base glossary, the user's own terms, a repository's `terms.yaml`, and terms
defined only in this session or document. `ktrf.registry` compiles them
together:

```python
from ktrf import TermLayer, compile_layered_snapshot

snapshot, report = compile_layered_snapshot([
    TermLayer("global", global_terms_doc),
    TermLayer("project", project_terms_doc),   # from .../terms.yaml
])
report.shadowed     # surfaces where a narrower scope outranks a wider one
report.conflicts    # shadowing that did not declare `override: true`
```

Authors write the compact Simple Terminology Schema, not the full glossary
format — the compiler derives ids, alias families, normalization profiles,
and boundary policies:

```yaml
schema_version: 1
terms:
  - key: advanced-billing-console
    canonical: Advanced Billing Console
    surfaces: [ABC, 빌링 콘솔]
    short_definition: 사내 과금 정책과 청구 상태를 관리하는 운영 콘솔
    override: true          # required to shadow a wider-scope meaning
```

New terms discovered mid-conversation go through a proposal lifecycle
(`ktrf.registry.proposals`) rather than straight into a dictionary: a model
may *propose*, deterministic validation checks it (surface actually present
in cited evidence, no alias collision, no instructional or sensitive
content), and an admission policy decides. Session-scoped explicit user
definitions can auto-activate; project scope requires trust plus repeated
evidence; **global scope always requires human approval**.

`python -m ktrf.integrations.pi_stdio` runs the whole thing as a
line-delimited JSON-RPC sidecar (resolve, context packs, lookup, explain,
proposals) with a fail-open contract: protocol JSON on stdout, diagnostics
on stderr, malformed input isolated, and every handler error returned as a
response so a host that loses terminology never loses the user's request.
`ktrf.explain_resolution()` reports why a mention resolved — or which
threshold it failed to clear.

## Evaluation

KTRF is evaluated in layers, each targeting a failure mode the previous
layer cannot see. All reports are regenerated from code — the files under
[reports/](reports/) are the source of truth for current numbers:

| Layer | What it measures | Report |
|---|---|---|
| `python -m eval.run_eval` | deterministic conformance, golden set, release gate (CI-lower-bound gated) | [EVALUATION.md](reports/EVALUATION.md) |
| `python -m eval.run_benchmarks` | adversarial anti-overfitting matrix: collisions, boundary traps, out-of-catalog tails, negative corpora, unicode fuzzing — hard gates must be 0 at every scale | [BENCHMARKS.md](reports/BENCHMARKS.md) |
| `python -m eval.run_wild` | real multi-domain Korean text (news, petitions, court decisions, encyclopedia) with a real-organization glossary: silver recall, real particle-distribution coverage, fake-glossary false positives | [WILD_CORPUS.md](reports/WILD_CORPUS.md) |
| `python -m eval.run_neural_eval` | unseen-abbreviation generalization: held-out short forms queried through real sentences, symbolic vs dense configs | [NEURAL_EVAL.md](reports/NEURAL_EVAL.md) |
| `python -m eval.run_llm_rag` | baseline comparison against open-weight LLMs with retrieval-augmented prompting (recall, grounding, hallucination, speed) | [LLM_RAG_COMPARE.md](reports/LLM_RAG_COMPARE.md) |
| `python -m eval.run_ab_grounding` | downstream A/B: does KTRF context actually improve LLM answers? four paired conditions, Helpful/Harmful Flips, Gold Benefit Recovery | [AB_GROUNDING.md](reports/AB_GROUNDING.md) |

Highlights from the current reports: zero conformance failures and zero
adversarial hard-gate violations at every tested scale; across 114k
sentences of real Korean text spanning news, government petitions, court
decisions and encyclopedia prose, silver recall and commit precision hold
at 1.0 with zero fake-glossary commits in every encoder configuration; on
the unseen-abbreviation track the dense channel recovers ~90% of held-out
short forms where sentence-level RAG retrieval caps general LLMs near 60%;
and in the downstream A/B, terminology context lifts an 8B model from 77%
to 93% on term-interpretation questions (**71% Gold Benefit Recovery**)
while a naive glossary dump at the same token budget *lowers* accuracy to
68% — the gain comes from selection, not from having a glossary. See the
reports for exact numbers, sample sizes, and confidence intervals, and
[docs/ROADMAP.md](docs/ROADMAP.md) for known gaps (the §5.2 95% unseen-
surface target is currently **not met** at scale; closing it is the top
roadmap item).

Real-text corpora are fetched by `eval/wild_data.py` from public HuggingFace
datasets (KLUE, 국민청원 petitions, 판례 court decisions, KorQuAD,
Wikipedia, KoBEST) — the repository ships the downloader, not the text; each
source carries its own license.

## Testing & requirements traceability

```bash
python -m pytest
```

The test suite covers unit/property tests, conformance, adversarial
regressions, artifact tamper refusal, and release-gate edge cases. Every
requirement ID in the specification is mapped to tests (or an explicit
deferral with reasons) in [docs/traceability.yaml](docs/traceability.yaml),
enforced by `tests/test_traceability.py`.

## Scope and limitations

This is a **Python reference implementation**. It favors clarity and
verifiability over throughput; the production design (Rust core, mmap
artifact bundles, HTTP service layer) is specified in PLAN.md §34 but not
implemented here. Known limitations are tracked honestly in
[docs/ROADMAP.md](docs/ROADMAP.md) — including current statistical limits of
the evaluation (silver labels are rule-derived approximations, not human
gold; sample sizes gate how tight the CI floors can be) and deferred
operational hardening (latency SLO gates, deep snapshot immutability,
concurrency load tests).
