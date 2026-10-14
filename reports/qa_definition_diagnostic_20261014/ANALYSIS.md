# Frozen definition-QA diagnostic

The sealed document-context responses show both formatting failures and real candidate-selection failures. A narrow normalization rule adds **six Qwen matches and no Gemma matches**. An AI review of every remaining unassessed answer finds **18 complete correct definitions with extra text**, but also unresolved collisions and wrong candidates. These extra-text cases receive no automatic credit and no replacement semantic score is reported.

The original experiment's requests, responses, scores, and manifests remain unchanged. Both diagnostic runs verified the original artifact seals and regraded the original exact contract before writing these separate reports. Each model has 384 definition-QA requests: 192 positive definitions and 192 required null answers. The original ID-routing results are outside this diagnostic and remain unchanged.

## Bounded automatic normalization

The declared rule accepts only the complete registered definition with whitespace, one Korean copula, and one terminal period changed. It does not credit containment, extra sentences, paraphrases, names alone, missing responses, malformed JSON, or literal `"null"`. The inventory comes from frozen registry facts and candidate packs, not the current fixture or the model's answer. Results that need further semantic review remain `UNASSESSED` and receive no credit.

| Model | Planned QA | Original exact correct | Diagnostic credited | Added normalized matches | Positive definition matches / 192 | Remaining unassessed |
|---|---:|---:|---:|---:|---:|---:|
| Gemma 4 12B | 384 | 184 | 184 | 0 | 30 | 34 |
| Qwen 3.5 27B | 384 | 192 | 198 | 6 | 31 | 23 |

“Diagnostic credited” includes correct null answers. It is a conservative definition-format diagnostic, not a general semantic-accuracy estimate. The six added Qwen matches occur in `full__full` (1), `retrieved__full` (3), `retrieved__none` (1), and `retrieved__retrieved` (1).

| Knowledge / source condition | Gemma original → diagnostic / 32 | Qwen original → diagnostic / 32 |
|---|---:|---:|
| None / none | 16 → 16 | 16 → 16 |
| None / full | 9 → 9 | 13 → 13 |
| None / retrieved | 7 → 7 | 11 → 11 |
| Full / none | 16 → 16 | 16 → 16 |
| Full / full | 15 → 15 | 16 → 17 |
| Full / retrieved | 14 → 14 | 15 → 15 |
| Retrieved / none | 9 → 9 | 13 → 14 |
| Retrieved / full | 15 → 15 | 13 → 16 |
| Retrieved / retrieved | 14 → 14 | 13 → 14 |
| KTRF / none | 16 → 16 | 16 → 16 |
| KTRF / full | 31 → 31 | 28 → 28 |
| KTRF / retrieved | 22 → 22 | 22 → 22 |

The complete machine-readable assessments are in [Gemma diagnostic](gemma12b/diagnostic.json) and [Qwen diagnostic](qwen27b/diagnostic.json); their [Gemma table](gemma12b/RESULTS.md) and [Qwen table](qwen27b/RESULTS.md) preserve the per-condition counts.

## Descriptive review of all 57 unassessed answers

One AI reviewer inspected every answer, its expected definition, and the frozen family knowledge documents. This review is gold-visible, post hoc, and not human-verified. It assigns descriptive categories without changing either exact or normalized credit. [review.json](review.json) preserves all 57 cases, raw answers, rationales, original statuses, source/knowledge evidence visibility, and diagnostic hashes.

| AI review category | Gemma | Qwen | Meaning |
|---|---:|---:|---|
| Same candidate, complete definition plus extra text | 1 | 17 | Complete gold definition plus registry-grounded name, ID, alias, or explanation |
| Same candidate, rewritten definition | 3 | 0 | Correct candidate and relevant tasks, but shortened or rewritten prose |
| Same candidate, name only | 5 | 2 | Correct name without the complete requested definition |
| Partial function or type | 3 | 1 | A narrow task or coarse type without the complete definition |
| Unresolved collision header | 15 | 2 | Family-level alias explanation or both meanings instead of one definition |
| Alias or metadata only | 3 | 0 | Surface string or “registered surface” label without a definition |
| Wrong candidate | 3 | 1 | Another registered meaning, name, or type |
| Malformed response | 1 | 0 | Original JSON/schema failure remains uncredited |
| **Total** | **34** | **23** | **All unassessed cases reviewed; no official new semantic score** |

Examples show why containment alone would be unsafe:

- Qwen `f01-d01`, `retrieved__full`, gives the complete correct console definition plus its correct ID and alias explanation. This looks meaning-preserving, but lies outside the declared normalization rule.
- Qwen `f04-d02`, `retrieved__retrieved`, gives the records-retention policy ID and full policy definition while the target is the development access-key service. A registered definition with extra prose can still select the wrong meaning.
- Gemma `f03-d02`, `retrieved__none`, names the deployment-review committee while the gold target is the data-ethics committee.
- Gemma `f07-d01`, `full__retrieved`, lists both support centers. That preserves the ambiguity rather than returning the required definition.

With retrieved knowledge and full source, Qwen's original 13/32 becomes 16/32 under the bounded rule. Seven of its nine remaining unassessed answers contain the correct complete definition plus registry-grounded prose; two give names only. Gemma stays at 15/32 and has ten unassessed answers of more varied kinds. The earlier QA gap consequently mixes extraction format, candidate selection, and abstention behavior. A name-only answer is weaker than a complete definition, and a same-candidate answer under source-none does not demonstrate justified disambiguation.

This queue excludes answers already classified as wrong, such as positive abstentions and non-null answers where null is required. Qwen's KTRF/full-source errors for `f03-d04` and `f07-d04` still return organization definitions for chair/director expressions. Its `f04-d03` and `f05-d04` answers describe unregistered satellite/artwork names instead of returning null. Those four failures remain unchanged; definition normalization does not excuse a role/entity confusion or a glossary-contract violation.

## Consequence for the next experiment

Keep the exact output-contract score and report the bounded definition diagnostic separately. A complete semantic estimate still requires a declared rubric covering extra claims, contradictions, identity, NIL, and whole-surface meaning, followed by independent adjudication. This single-AI review can guide that rubric but cannot substitute for independent human gold or provide a deployment error guarantee.

The next controlled comparison should expose comparable candidate definitions across knowledge arms and evaluate candidate ID selection separately from free-form prose. Contextual disambiguation can then be assessed for useful accepted IDs while retaining the existing role, NIL, ambiguity, and execution guards. The archived 32 AI-authored documents and their information-removal limitations still apply.

Original experiment code revision: `604666e41c3133ec3032bfd23f69fa4c1bc5d6c9`. Diagnostic version: `qa_definition_normalization_v1`. Both diagnostic commands exited with code 0. Source results: [sealed document-context analysis](../document_context_queue_20261014T024026Z/ANALYSIS.md).
