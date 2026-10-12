# Context policy and product utility evaluation

KTRF separates knowledge assistance from authority to execute a linked entity.
`ContextPolicy(answer_policy="knowledge")` permits an explanation using general
knowledge while requiring the host to distinguish it from a verified glossary
link. The default policy preserves existing grounding behavior. The
`automation` profile always uses the execution policy, even if knowledge
assistance was requested.

Before executing a replacement, routing a ticket, or writing a linked field,
call `validate_llm_grounding(output, pack, purpose="execution")`. A non-null ID
must match a non-degraded resolved binding for the exact surface. Candidate
membership, an ID resolved for another surface, and general knowledge grant no
execution authority. A null ID is an abstention and must not trigger an action.
The validator automatically applies this rule to automation packs. Integrations
must independently authenticate the pack's tenant and snapshot and treat these
packs as trusted server-produced data.

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
