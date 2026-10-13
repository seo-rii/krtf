# Context policy and product utility evaluation

KTRF separates explanatory QA from authority to execute a linked entity. The
default `ContextPolicy(profile="qa_grounding", answer_policy="evidence_only")`
uses `QA_CONTEXT_POLICY`: an ambiguous candidate's supplied definition may
explain the entire target expression when the document context uniquely
supports that meaning. It does not permit outside knowledge or guesses, and
requires a null answer if the context cannot distinguish the candidates. A
core term's meaning does not automatically describe a derived role or the
entire compound. This explanation changes neither resolver status nor
execution authority.

`answer_policy="knowledge"` remains an explicit opt-in to explanations using
general knowledge, distinguished from verified glossary links. The
`summarization` and `rag_query_expansion` profiles retain their existing policy
selection. `automation` always uses the unchanged `EXECUTION_POLICY`, even if
knowledge assistance was requested; it receives no contextual QA exception.

QA consumers read only the `answer` field and ignore incidental IDs and
selections. Execution requires a separate automation request and conversation,
without QA output or QA conversation history. Its output schema is
`{"selections": [{"surface": "ABC", "entity_id": "approved-id"}]}`.

Before executing a replacement, routing a ticket, or writing a linked field,
call `validate_llm_grounding(output, pack, purpose="execution")`. A non-null ID
must match a non-degraded resolved binding for the exact surface. Candidate
membership, an ID resolved for another surface, and general knowledge grant no
execution authority. The execution validator rejects raw QA envelopes
(including `answer` alongside selections), top-level `entity_id`, and missing
or non-list selections. An explicit empty selections list or a null selection
ID is an abstention and must not trigger an action. Validate the complete
execution response before extracting any non-null selections; do not repair a
QA response into this schema. The guard cannot identify a QA ID that the host
has manually repackaged as a valid execution selection.

The validator automatically applies the execution contract to automation
packs. Integrations must independently authenticate the pack's tenant and
snapshot and treat these packs as trusted server-produced data.

## Evidence for QA-only adoption

The [recorded QA policy experiment](../reports/qa_policy_20261013T123450Z/RESULTS.md)
used 437 AI-authored synthetic documents and one Gemma4 12B model. Adding a
contextual QA exception improved overall QA from **337/437 to 397/437** and
contextual-collision QA from **2/74 to 54/74**. Routing fell from **334/437 to
331/437** when its shared system prompt also received the exception. Correct
but execution-unapproved IDs emitted incidentally by QA increased from **11 to
47**. These results motivate applying the exception only to QA, retaining the
execution prompt and binding guard, and consuming QA answers without IDs.

The frozen experiment measured its synthetic prompts, not the newly selected
production profile. It did not test unrestricted general knowledge, independent
human gold, or a deployment error bound. The production policy adoption adds
contract tests; these historical scores are not a new production measurement.

## Paired format and policy experiment

From the repository root, generate reproducible requests and local contract
checks:

```sh
python -m eval.product_utility --output /tmp/product-requests.json
```

The matrix has 14 cases and nine conditions per case: one no-context baseline,
and two selectors × two formats × two policies. Each selector's same cards,
statuses, definitions, and IDs are held fixed across all four format/policy
conditions; `candidate_hash` verifies this. The baseline selector is literal
alias retrieval capped at three entities, rather than the dense hybrid RAG used
in older experiments. The KTRF selector uses the resolver context pack, also
capped at three entities. This small fixture may produce identical candidates
for both selectors; it validates the experiment mechanics rather than a
retrieval advantage. Follow-up real-document trials must retain the matrix and
replace the case construction and baseline selector explicitly.

Formats are plain lines and structured JSON. Policies permit general knowledge
or restrict answers to provided evidence. Both policies preserve status
separation and execution restrictions. Estimated prompt tokens are recorded;
they are not measured tokenizer counts. Equal candidate content does not imply
equal token counts. Record model, model revision, decoding configuration, actual
token counts, and latency alongside each response in a sealed run manifest.

Run the generated `system` and `user` fields through one fixed model without
showing it `expected_*` or `pack`. Save one JSONL row per result:

```json
{"case_id":"tenant-a:structured_routing","condition":"ktrf:structured:knowledge","response":{"entity_id":"global:billing"},"latency_ms":12.5}
```

Then grade the recorded outputs:

```sh
python -m eval.product_utility --output /tmp/product-results.json \
  --responses /path/to/recorded-responses.jsonl
```

The grader reports observed counts, task success, harmful/helpful flips on
paired baseline observations, safe abstention, over-abstention, malformed
answers, and scope-switch correctness and previous-meaning retention. Missing
outputs remain missing and do not count as safe abstentions. QA uses strict
matching to the glossary definition; blind adjudication is needed to accept
paraphrases. Structured routing additionally passes the execution gate. Model
outputs are separate from deterministic contract results. No model scores are
emitted unless recorded responses are supplied.

## Counterfactual glossary and task tracks

Identical text and questions use `ABC` for a billing console in tenant A and an
access-approval procedure in tenant B. Separate snapshots, approved project and
session overrides, an untrusted session, genuine ambiguity, and an empty
glossary exercise scope behavior. Returning to tenant A verifies that another
world has not mutated its meaning. An undeclared override is rejected using
`strict_conflicts=True`; the harness does not approve or publish glossary data.
Each world supplies document QA and structured routing cases.

Separate snapshots test local isolation. They do not establish HTTP tenant
authentication or session cache isolation. Synthetic cases do not certify a
production error bound, and human correction time remains a separate trial.

## Local validation result

The reproducible local run passed all eight snapshot/scope checks and rejected
an undeclared override. It generated 126 requests. Focused context and product
tests passed (33 tests). The configured default Ollama endpoint,
`localhost:11434`, refused the read-only model-list connection, so no LLM
factorial run or human trial is represented by this result. The machine-readable
summary is in `reports/PRODUCT_UTILITY.json`.

## one-server run, 2026-10-13

The full core suite passed on Python 3.12.3: **541 tests in 13.26 seconds**.
The existing A100/vLLM service `mil-gemma4-12b-bf16` completed all 126 live
requests with no transport or JSON errors. The runner forwards only each
request's system/user prompts and records actual tokens, raw responses, fixed
decoding settings and a sealed manifest:

```sh
python -m eval.run_product_llm \
  --endpoint http://127.0.0.1:18090/v1 --model mil-gemma4-12b-bf16 \
  --out-dir /path/to/new-exclusive-run --code-revision COMMIT_SHA \
  --max-tokens 128 --timeout 180
```

Every contextual condition scored 5/14; the no-context baseline scored 2/14.
Four contextual successes are safe abstentions, and the remaining success is a
project routing ID. All five answerable QA cases per condition returned null.
KTRF and lexical retrieval produced identical cards, prompts and responses in
all 56 paired requests, so this sample cannot measure a selector advantage.

The rendered cards omit the `resolved_terms` field and the `ABC` surface binding
required by the system policy. This is an observed mismatch between stimulus
and policy. Its contribution to over-abstention needs a controlled follow-up;
these scores do not measure a complete production context pack. No corrected
stimulus or policy was substituted during the run. Detailed outcomes and
provenance are in [the remote report](../reports/ONE_SERVER_VALIDATION.md) and
[the recorded run](../reports/one_server_20261013/run_manifest.json).

## Controlled input-contract diagnostic

`--track contract_probe` uses the same 14 cases, KTRF candidates, structured
format and evidence-only policy. It creates four conditions per case:
`original`, `surface_only`, `schema_only`, and `both`. Surface bindings come
from the original resolver pack. The schema factor places the unchanged cards
under the policy-named `resolved_terms` and `ambiguous_mentions` fields. It keeps
definitions, entity IDs, resolution status, candidate order, questions, system
policy and execution guards fixed. Ambiguous candidates remain ambiguous.

This minimal policy-field representation retains the `definition` card key and
does not reproduce all production pack fields. It isolates two input-contract
factors. Missing cases contain no cards, so their surface factor is inert.
Condition order rotates independently within QA and routing; each model call
is a fresh system/user conversation. The protocol and source/input hashes are
frozen in [the declared protocol](../reports/CONTRACT_PROBE_PROTOCOL.json).

```sh
python -m eval.run_product_llm --track contract_probe \
  --endpoint http://127.0.0.1:18090/v1 --model mil-gemma4-12b-bf16 \
  --out-dir /path/to/new-exclusive-contract-run --code-revision COMMIT_SHA \
  --max-tokens 128 --timeout 180
```

Diagnostics separate answerable QA, valid-ID routing, over-abstention, safe
abstention, raw ID mistakes and gate rejection. `accepted_unauthorized_ids`
counts wrong IDs the unchanged validator would permit; no actual downstream
actions are performed. Each condition is also paired with the same case's
`original` result. These descriptive counts do not certify population risk.

### Recorded diagnostic result

On 2026-10-13 the same served model completed all 56 requests. The full core
suite passed 551 tests in 13.58 seconds. Original prompts reproduced the prior
5/14 task score. The outcome was:

| Condition | Task success /14 | Answerable QA /5 | Valid routing /5 | Over-abstention /10 |
|---|---:|---:|---:|---:|
| original | 5 | 0 | 1 | 9 |
| surface_only | 14 | 5 | 5 | 0 |
| schema_only | 5 | 0 | 1 | 9 |
| both | 14 | 5 | 5 | 0 |

Both surface-present conditions repaired the same nine cases with no harmful
changes. All four uncertain cases safely abstained in every condition; all
three scope-switch pairs succeeded when surface bindings were present. No
incorrect or guard-accepted unauthorized IDs were observed. Policy field
renaming alone had no measured benefit. This supports missing surface binding
as the source of these fixture failures. It does not establish that a literal
`resolved_terms` key is necessary for the tested model.

The [result report](../reports/CONTRACT_PROBE_RESULTS.md) links the original
requests, raw responses, paired diagnostics and sealed manifest. A complete
production-pack trial, another model and independent documents remain separate
validation steps.
