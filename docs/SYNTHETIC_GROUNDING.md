# Expanded synthetic grounding experiment

This corpus expands the 14-case surface-binding diagnostic to **100 authored
glossary families, 400 distinct Korean documents, 800 task cases and 4,000 model
requests**. Business, technical and public-service scenarios contribute 34, 33
and 33 families respectively. Each family contains four manually authored
documents and at least two glossary worlds; the corpus has 310 worlds.

The [source fixtures](../eval/fixtures/grounding_expansion/) preserve each
document, exact target surface and occurrence, source-world definition,
semantic gold and rationale. Three AI authors wrote the scenarios, and other AI
contexts reviewed their labels without resolver or model outputs. Every record
declares `AI_SYNTHETIC` and `human_verified: false`. These are deliberately
constructed challenges, rather than random deployment documents or independent
human annotations. Increasing the case count does not establish population
precision, conformal coverage or a production error bound.

## Corpus and independent gold

All 400 document text hashes differ. The
[corpus manifest](../reports/SYNTHETIC_GROUNDING_CORPUS.json) freezes the semantic
source hash, generated request hash, label counts and family-connected split.
Entity keys include their source family, preventing a constant `global:main`
answer from becoming a shortcut across unrelated dictionaries.
This does not remove role suffixes such as `.main` and `.rival`: the review
below documents a remaining text-blind shortcut in this v1 corpus.

| Whole-target gold | Documents |
|---|---:|
| LINK | 300 |
| NIL: target entity absent from the authored glossary | 66 |
| AMBIGUOUS: available context does not select one entity | 25 |
| NON_MENTION: ordinary expression rather than glossary referent | 9 |

The target is the **entire requested expression**. An institution head or
unregistered derived product does not inherit the institution's entity ID.
Where relevant, gold records the distinct core separately. Contextual
collisions can be LINK when authored context determines the referent, even if
the resolver keeps both candidates. Gold is never rewritten to agree with
resolver retrieval or authorization.

The 14 strata include exact names, particles, multiple entities, typos, genuine
ambiguity, contextual collisions, glossary swaps, approved project/session
overrides, untrusted overrides, derived roles, ordinary-word collisions,
unregistered targets, and Unicode/spacing variations. Glossary-swap scenarios
extend semantic coverage; their texts are not all identical across worlds, so
they are not all strict counterfactual pairs. The earlier 14-case track retains
its identical-text glossary-swap checks.

Family and shared alias connections stay in one partition: 264 train, 64
validation and 72 test documents. This run scores **all partitions
descriptively**; it does not select thresholds or claim a sealed risk test.
These assignments are retained for later development without splitting sibling
worlds between fit and evaluation.

## Input intervention

Each document supplies a definition QA task and a structured entity routing
task. The question names the whole target and its half-open Python codepoint
span. The four diagnostic cells keep document, question, candidate facts,
resolution statuses, system policy and execution guard fixed:

| Condition | Explicit surface binding | Policy-named fields |
|---|---|---|
| original | absent | absent |
| surface_only | present | absent |
| schema_only | absent | present |
| both | present | present |

Bindings are copied from actual resolver mentions, including distractor
surfaces. The schema factor groups the same cards under `resolved_terms` and
`ambiguous_mentions`; ambiguous candidates keep their status. The fifth
condition, `full_pack`, supplies the actual production context pack as a
**separate reference**. It includes additional information, so its difference
from a minimal card is not attributed solely to either matrix factor.

Requests rotate condition order within each task and use fresh system/user
conversations. Only the two prompt strings reach the endpoint. Gold labels,
expected answers and grader metadata remain outside model messages. The
predeclared settings are temperature 0, seed 0, thinking disabled and 128 output
tokens. Input character-token estimates peak at 1,337 for this corpus; actual
model token counts and completion truncation are recorded by the live runner.

## Scoring and resolver baseline

QA matches the authored definition exactly; a valid paraphrase can therefore
be a strict-match failure. Missing responses, malformed fields, transport
failures and valid null abstentions remain distinct. Routing succeeds only
when the ID is semantically correct **and** passes the existing execution
validator. Raw semantic matches, wrong IDs, guard rejections and wrong IDs
accepted by the guard are reported separately. No downstream action is run.

Before LLM calls, the actual resolver supplies the gold entity among the exact
target's candidates for **281/300** LINK documents and correctly authorizes
**236/300**. These counts expose retrieval and authorization limits; the LLM
cannot create execution authority for the remaining cases. Three negative-gold
documents also receive a non-null target authorization: the ordinary
expressions `나루채`, `풀숨` and `유리문` share registered surfaces. Their negative
gold remains intact, so the expanded evaluation can measure these harmful
links. Surface-wide authorization is distinct from interpreting a particular
occurrence's referent. This experiment reports that limitation without changing
the production resolver or validator.

Results include per-task, per-stratum and family macro success, paired helpful
and harmful changes, safe/over-abstention, actual tokens and p50/p95/p99 request
latency. Family clustering is preserved; no row-independent confidence bound
or retrieval-selector advantage is inferred from this synthetic matrix.

## Reproduce

Use an existing compatible OpenAI-style endpoint. The output directory must be
new; raw prompts, raw completions, grades and the sealed run manifest are kept.

```sh
python -m eval.run_product_llm --track synthetic_expansion \
  --endpoint http://127.0.0.1:18103/v1 --model krtf-synthetic-gemma4-12b-bf16 \
  --out-dir /path/to/new-run --code-revision COMMIT_SHA \
  --max-tokens 128 --timeout 180
python -m eval.report_synthetic_grounding --run-dir /path/to/new-run
```

The report generator verifies frozen artifact hashes and the manifest seal,
then writes `summary.json` and `RESULTS.md` from those artifacts. An incomplete
run retains expected denominators and missing counts; observed-only family
macro values must not be read as complete-corpus success. The previous one-server
endpoint on port 18090 was unavailable during preflight. The expanded run uses
an experiment-owned loopback vLLM process with the same cached checkpoint,
an 8,192-token context and a 0.45 GPU memory allocation limit. Its lifecycle and
configuration are recorded separately from other server jobs; it exits after
the experiment. This is a new runtime, so absolute latency is not directly
comparable with the earlier shared-service runs. The serving model ID and
config hashes do not verify the full checkpoint weight revision. A second model, blind real-document gold
and representative random audits remain separate experiments.

## Review addendum for the frozen v1 run

The running v1 experiment retains its original source, requests and grades.
Request-only diagnostics found that selecting the unique candidate whose ID
does not end in `.main` answers **35/37 contextual-collision documents (94.6%)**
correctly for exact-definition QA and raw semantic routing. It reads neither
the document nor model outputs. First- and last-candidate baselines score
14/37 and 23/37 respectively. All those contextual IDs remain execution-blocked.
Consequently this stratum's semantic score alone cannot establish contextual
reasoning by the model.

A perfect semantic oracle reaches QA **400/400**, routing **336/400**, and
overall **736/800 (92%)** in each v1 condition. The 64 remaining routing cases
have a known glossary answer but no execution authorization. This is a guard
ceiling, assuming the answer is known, rather than a claim that the model has
enough supplied information to attain it. The supplemental report separates
nulls required by that guard from avoidable nulls on authorized positive cases,
without changing the original semantic gold or overall grade.

After a run completes, create an additional report without overwriting its
original `summary.json`, `RESULTS.md`, grades or sealed artifacts:

```sh
python -m eval.report_synthetic_grounding --run-dir /path/to/completed-v1-run \
  --supplement --analysis-revision ANALYSIS_COMMIT_SHA
```

This writes `reviewed_summary.json` and `REVIEWED_RESULTS.md`. The original
experiment revision and the supplemental reporting revision remain distinct.

## Balanced v2 corpus

V2 preserves all 400 original documents and adds **37 independently authored
contrasts**. Another AI context reviewed every contrast against its source
dictionary, without resolver or live-model outputs. Each of the 37 contextual
collision families now has two same-world documents: one for each candidate.
There are **437 documents, 874 task cases and 4,370 requests**, including
74 contextual-collision documents. Gold remains AI synthetic and unverified by
humans. The added texts and rationales live in
[the contrast fixtures](../eval/fixtures/grounding_expansion_v2/); the
[v2 manifest](../reports/SYNTHETIC_GROUNDING_V2_CORPUS.json) records source
lineage, pair counts, assignments and request hash.

Every authored entity key is replaced deterministically with an opaque hash
key; scope prefixes remain because approval scope is part of the contract.
The four minimal-card conditions sort by status, opaque ID and binding surface,
independently of document text and gold. This gives each pair exactly the same
two candidate cards in the same order. The first and last positions are each
correct **37/74 (50%)** of the time; the `.main`-suffix rule has zero applicable
cases. The `full_pack` reference retains actual production ordering and scores,
so it can contain resolver ranking information in addition to the minimal cards.

Original family partitions are retained; each new contrast inherits its source
partition. No sibling pair crosses a partition, and none of the original 400
documents moves between train, validation and test. All partitions remain
descriptive evaluation material, not a sealed risk test. Existing v1 fixture
bytes and generated request hash are covered by a regression check.

The extra 37 positive routing cases are also guard-blocked. V2's semantic
oracle ceiling is **773/874 (88.44%)**: QA 437/437 and routing 336/437. A lower
aggregate ceiling here reflects the changed task mix, not a resolver regression.
Dataset size, opaque IDs and minimal-card ordering all changed, so v1-versus-v2
model scores would not isolate a single intervention. These baseline diagnostics
are local deterministic checks; a v2 model score requires a separate live run:

```sh
python -m eval.run_product_llm --track synthetic_expansion_v2 \
  --endpoint EXISTING_ENDPOINT --model MODEL_ID \
  --out-dir /path/to/new-v2-run --code-revision V2_COMMIT_SHA
```
