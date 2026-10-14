# Explicit context-definition diagnostic corpus v1

This fixture adds **32 newly authored complete synthetic Korean business documents** to the definition-control diagnostic. It reuses the eight approved glossary families, their 16 opaque entity IDs, and every complete knowledge memo from `../document_context/families.jsonl` without changing any term or knowledge field. The source texts are new; they are not reconstructed articles or extensions of previously evaluated source texts.

Each family contains two positive documents that select different meanings of its shared alias, plus two hard negative documents. Every source has six paragraphs, 599–658 Unicode characters, and exactly one occurrence of its designated target. Eight positives directly declare the alias's registered canonical name; eight directly declare its registered definition. These are actual assertions in their source documents, rather than reported alternatives or quoted examples.

| Gold label or positive stratum | Documents |
| --- | ---: |
| LINK: direct canonical declaration | 8 |
| LINK: direct definition declaration | 8 |
| NON_MENTION: rejected quoted assertion | 4 |
| NIL: newly named unregistered physical object | 4 |
| AMBIGUOUS: competing registered meanings without decisive evidence | 4 |
| COMPOSITIONAL: whole alias-plus-장 expression naming a person or role | 4 |
| Total source documents | 32 |

The negative examples preserve distinctions needed by a resolver. A quoted sentence containing a registered name is an explicitly rejected test string in NON_MENTION examples; its predicate is not an endorsed naming assertion. NIL examples use the shared alias to name a new physical object and explicitly distinguish it from both registered meanings. AMBIGUOUS examples state that the author has not yet selected either registered destination. COMPOSITIONAL examples refer to a responsibility-bearing person rather than the registered organization; the whole role expression expects null even if its core organization is recognizable. Role controls use the team, committee, department, and support-center families.

`families.jsonl` has one family per line and uses the existing document-context family schema. Stable document IDs begin with `cd-`; the prefix carries no grading semantics. `target_occurrence=0` designates the unique source occurrence. LINK `expected_answer` values exactly match the selected term's `short_definition`; other labels have a null entity reference and null expected answer. Exact decisive evidence and the authored rationale are grading metadata and must not enter retrieval queries or model prompts.

The sources and labels were authored before any evaluated-model inference for this fixture, without inspecting resolver outputs or model answers. Provenance is `AI_AUTHORED_SYNTHETIC`, with `human_verified=false`. The manifest records the original glossary-fixture hash, this fixture's hash, document hashes, deterministic counts, and a separate review status. The root agent reviews the new text and gold before inference; that AI review does not establish human verification.

These examples are a controlled diagnostic of explicit declarations, quoting, and whole-expression semantics. They do not constitute an independent deployment-risk validation set: the glossary families and alias collisions have been used in prior experiments. Brief documents and repeated workflow or closure prose do not test long-document limits. Several negative scope cues are deliberately explicit. Operational bodies are authored around the selected work, while some workflow and closure wording is shared. No statistical coverage guarantee follows from this corpus.

Keep the source text, target occurrence, glossary, and authored gold fixed across all six definition-control arms and both models. Report candidate visibility, raw QA or routing correctness, and actual execution authorization separately. Reaching a correct answer from a declaration does not permit a model to override a resolver guard.

Independent semantic review of all 32 documents by the root and context-review AI agents passed. No human verification occurred. The source/gold were preserved when symbolic preflight exposed unsupported declaration styles; coverage limitations belong to the recognizer, not a relabeling of these cases.
