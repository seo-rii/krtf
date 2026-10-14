# Document-context comparison corpus v1

This fixture contains **32 newly authored synthetic business documents** and eight complete synthetic knowledge memos. It supports separate comparisons of source-document context and knowledge-document context. These texts are not real articles, are not expansions of KONEC sentences, and must not be reported as an independent real-world document benchmark.

Every source document has six paragraphs and only 354–402 characters. Every alias is deliberately shared by two registered entities; the corpus contains no easy unambiguous-alias control family. Each family has two registered entities that share a Korean alias, two LINK documents that select different meanings, and two non-LINK controls. Source and knowledge texts were written directly for this fixture, before running either evaluated model and without inspecting resolver output. Annotation origin is `AI_AUTHORED_SYNTHETIC`; no human verification has occurred.

| Property | Count |
| --- | ---: |
| Families / complete knowledge memos | 8 |
| Registered entities | 16 |
| Complete source documents | 32 |
| LINK with decisive evidence in paragraph 5 | 8 |
| LINK with decisive evidence in paragraph 2 | 8 |
| AMBIGUOUS | 4 |
| NIL | 4 |
| COMPOSITIONAL | 4 |
| NON_MENTION | 4 |

Paragraph numbers above are one-based. The first occurrence of every target appears in paragraph 1. Remote LINK documents put distinguishing operational facts in paragraph 5 and keep paragraph 2 generic; local LINK documents put those facts in paragraph 2. Across the eight families, each dictionary ordering position is correct in four remote and four local documents. Both meanings of every alias have one LINK example.

`families.jsonl` contains one complete family per line. Each family carries a knowledge memo, terms with opaque keys, and four source documents. Each complete knowledge memo also has six paragraphs: an introduction, the first definition, two neutral operational notes, the second definition, and closing guidance. Separating the definitions keeps a one-paragraph retrieval neighborhood from automatically supplying both entries. Neutral paragraphs were added before evaluation; source documents and gold labels did not change. Knowledge memos include both compiled entity IDs (`global:e_…`), canonical names, shared aliases, and definitions. Their prose is a complete source document, not an oracle excerpt selected using an evaluated model's answer. All term definitions and IDs remain available in each family's full knowledge condition.

Each document has:

- A stable document ID, a complete title and text, and the designated target surface. `target_occurrence=0` identifies the first exact occurrence in `text`; consumers must preserve its original offsets.
- A world-level gold label and, only for LINK, a compiled entity reference and expected QA definition matching the corresponding term's `short_definition`.
- Exact evidence quotations from source and/or knowledge documents, a source-context stratum, and a rationale. Evidence and rationale are annotation-only material and must never enter a model prompt or retrieval query.

Non-LINK distinctions are intentional. AMBIGUOUS leaves both registered meanings possible even with the complete source. NIL introduces a different, explicitly unregistered named referent. COMPOSITIONAL names a leader as a person rather than the registered organization. NON_MENTION uses the alias as an ordinary noun or as nonreferential typography/input material. All four labels expect abstention under the fixture's whole-surface registered-entity task.

The target-only source condition must omit the title, document text, evidence, rationale, label, and expected answer. Full-source context must preserve the whole original text. Retrieved-source context must use a predeclared lexical selector and paragraph neighborhood without consulting annotations. If the selector finds a different passage than the designated target neighborhood, record that result; do not substitute the gold evidence. Likewise, knowledge retrieval and KRTF must access the same declared family dictionary scope.

This is a controlled, intentionally difficult ambiguity test, not a representative sample of a deployment population. The brief documents and repeated six-paragraph structure do not measure long-document limits. Explicit NIL and nonreferential cues make some controls easier than naturally occurring cases. The family inventory, gold labels, and expected answers are authored by AI; a separate review is recorded in the manifest when completed. Model-family comparisons cannot isolate model size, and no coverage or error-rate guarantee follows from these 32 cases.

The manifest records file hashes, deterministic counts, provenance, and review status. Keep the authored gold fixed across context conditions and model runs, while reporting answerability/evidence visibility separately. A question that is unanswerable from target-only input does not acquire a different underlying entity label.
