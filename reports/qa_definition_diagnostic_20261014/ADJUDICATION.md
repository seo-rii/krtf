# Post hoc AI semantic adjudication

The separately recorded semantic rubric accepts **21 of the 57 previously unassessed answers** as meaning-preserving definitions after reviewing the entire answer and its frozen evidence. It classifies 11 as partial, 24 as mismatches, and one as invalid. This separates additional grounded wording from wrong candidate selection without changing the sealed experiment or the bounded normalization diagnostic.

This is a **gold-visible, post hoc AI assessment, not a primary score or independent risk certificate**. The primary reviewer had already seen the answers before declaring the rubric. A second AI reviewer, the root agent, separately read all 57 raw answers, gold definitions, and frozen family knowledge documents and agreed with the verdict categories. Both reviewers are AI agents; there is no independent human verification or independent deployment sample. [semantic_rubric.json](semantic_rubric.json) records the declaration timing and complete rubric; [adjudication.json](adjudication.json) preserves every audited answer, decision, rationale, sentence-level supported and contradictory claims, verbatim frozen evidence, parent hashes, offsets, and evidence visibility.

## What the rubric checks

A `MATCH` requires the gold registered referent, a sufficient definition of its core function and kind, grounding for every added factual assertion, and no competing candidate, negation, or whole-surface semantic error. A named team or center can establish its kind when functional prose is also supplied. A registry name alone remains `PARTIAL`, even when the name is descriptive. Partial functions, coarse types, and partial names receive zero added binary credit. Collision explanations, alternative candidates, alias-only answers, and metadata-only answers are `MISMATCH`. Malformed responses remain `INVALID` without recovering an embedded answer. No verdict is awarded by substring containment alone.

For every accepted answer, the added name, ID, alias, or operational details appear in the same frozen registry paragraph as the gold definition. Three Gemma answers rewrite the definition but name the correct team/center and give its relevant operational function. No accepted answer includes an unsupported additional factual claim or a competing candidate. The complete answer and evidence are retained for a second review.

## The reviewed queue and the full QA denominator

| Model | Reviewed queue | MATCH | PARTIAL | MISMATCH | INVALID |
|---|---:|---:|---:|---:|---:|
| Gemma 4 12B | 34 | 4 | 8 | 21 | 1 |
| Qwen 3.5 27B | 23 | 17 | 3 | 3 | 0 |
| Total | 57 | 21 | 11 | 24 | 1 |

The optional full-denominator estimate adds reviewed `MATCH` decisions to the existing bounded diagnostic credit. Existing exact/normalized definition matches and correct nulls remain credited; definite mismatches and positive abstentions are not newly adjudicated. Each model has **384 planned QA answers: 192 positive definitions and 192 null-gold answers**. The denominator is not the 57-case review queue, and it includes the deliberately information-limited conditions.

| Model | Original exact / 384 | Bounded diagnostic / 384 | Added AI matches | Post hoc normalized + AI / 384 | Positive definition matches / 192 | Correct nulls / 192 |
|---|---:|---:|---:|---:|---:|---:|
| Gemma 4 12B | 184 | 184 | 4 | **188 (48.96%)** | 34 | 154 |
| Qwen 3.5 27B | 192 | 198 | 17 | **215 (55.99%)** | 48 | 167 |

These percentages describe this archived synthetic matrix under a post hoc rubric. They do not estimate production precision, validate the existing execution guard, or provide an independent semantic benchmark. All original official scores remain unchanged.

| Knowledge / source | Gemma bounded → post hoc AI / 32 | Qwen bounded → post hoc AI / 32 |
|---|---:|---:|
| None / none | 16 → 16 | 16 → 16 |
| None / full | 9 → 9 | 13 → 13 |
| None / retrieved | 7 → 7 | 11 → 11 |
| Full / none | 16 → 16 | 16 → 16 |
| Full / full | 15 → 15 | 17 → 19 |
| Full / retrieved | 14 → 14 | 15 → 16 |
| Retrieved / none | 9 → 10 | 14 → 14 |
| Retrieved / full | 15 → 18 | 16 → 23 |
| Retrieved / retrieved | 14 → 14 | 14 → 21 |
| KTRF / none | 16 → 16 | 16 → 16 |
| KTRF / full | 31 → 31 | 28 → 28 |
| KTRF / retrieved | 22 → 22 | 22 → 22 |

With retrieved knowledge and full source, Qwen's original 13/32 becomes 16/32 under bounded normalization and 23/32 under this AI content rubric. Its positive definition count becomes 10/16. Gemma becomes 18/32, with six positive definitions out of 16. This confirms that the earlier exact-score gap includes wording differences, while unresolved collisions and incomplete definitions remain material failures. These content decisions do not increase KTRF's accepted routing IDs; routing is a separate task.

## Content match and available disambiguating evidence differ

Of the 21 newly accepted content matches, 19 have both the frozen decisive source cue and the gold knowledge passage visible to the model. Two do not:

- Gemma `f07-d01:document_qa`, `retrieved__none`, names and describes the customer-transition support center, but source-none provides no target-disambiguating source cue.
- Qwen `f03-d01:document_qa`, `retrieved__retrieved`, returns the deployment-review definition and grounded details, but its retrieved source window omits the distant decisive cue.

Those answers match the gold content but do not establish justified resolution from the provided evidence. Their evidence-availability flags are recorded separately, and no availability-adjusted official score is invented. For source-none, an observed gold-content match can be a fortunate selection among colliding meanings.

## All 57 case decisions

The index matches the existing descriptive review queue. Full answers and exact supporting passages are in [adjudication.json](adjudication.json). Every listed decision is AI-authored and human-unverified.

| Model | Review index | Case | Condition | Decision |
|---|---:|---|---|---|
| Gemma | 1 | f01-d02 | retrieved__retrieved | PARTIAL |
| Gemma | 2 | f02-d01 | retrieved__none | MISMATCH |
| Gemma | 3 | f02-d01 | retrieved__full | MATCH |
| Gemma | 4 | f02-d02 | retrieved__none | MISMATCH |
| Gemma | 5 | f02-d02 | full__full | MISMATCH |
| Gemma | 6 | f02-d02 | retrieved__full | MISMATCH |
| Gemma | 7 | f02-d02 | retrieved__retrieved | MISMATCH |
| Gemma | 8 | f03-d01 | retrieved__none | PARTIAL |
| Gemma | 9 | f03-d01 | retrieved__full | MISMATCH |
| Gemma | 10 | f03-d01 | retrieved__retrieved | PARTIAL |
| Gemma | 11 | f03-d02 | retrieved__none | MISMATCH |
| Gemma | 12 | f03-d02 | retrieved__retrieved | PARTIAL |
| Gemma | 13 | f04-d01 | retrieved__none | MISMATCH |
| Gemma | 14 | f04-d02 | retrieved__none | MISMATCH |
| Gemma | 15 | f04-d02 | full__full | PARTIAL |
| Gemma | 16 | f05-d01 | retrieved__full | MATCH |
| Gemma | 17 | f06-d01 | retrieved__full | MISMATCH |
| Gemma | 18 | f06-d01 | retrieved__retrieved | MISMATCH |
| Gemma | 19 | f06-d02 | retrieved__none | MISMATCH |
| Gemma | 20 | f06-d02 | full__full | MISMATCH |
| Gemma | 21 | f06-d02 | retrieved__full | MISMATCH |
| Gemma | 22 | f06-d02 | retrieved__retrieved | MISMATCH |
| Gemma | 23 | f07-d01 | retrieved__none | MATCH |
| Gemma | 24 | f07-d01 | full__full | MISMATCH |
| Gemma | 25 | f07-d01 | retrieved__full | PARTIAL |
| Gemma | 26 | f07-d01 | full__retrieved | MISMATCH |
| Gemma | 27 | f07-d01 | retrieved__retrieved | MISMATCH |
| Gemma | 28 | f07-d02 | retrieved__none | MISMATCH |
| Gemma | 29 | f07-d02 | full__full | MISMATCH |
| Gemma | 30 | f07-d02 | retrieved__full | MATCH |
| Gemma | 31 | f07-d03 | full__retrieved | INVALID |
| Gemma | 32 | f08-d01 | retrieved__full | PARTIAL |
| Gemma | 33 | f08-d01 | retrieved__retrieved | PARTIAL |
| Gemma | 34 | f08-d02 | retrieved__full | MISMATCH |
| Qwen | 1 | f01-d01 | full__full | MATCH |
| Qwen | 2 | f01-d01 | retrieved__full | MATCH |
| Qwen | 3 | f01-d02 | retrieved__full | MATCH |
| Qwen | 4 | f01-d02 | retrieved__retrieved | MATCH |
| Qwen | 5 | f02-d01 | retrieved__retrieved | MATCH |
| Qwen | 6 | f02-d02 | full__full | MATCH |
| Qwen | 7 | f03-d01 | retrieved__full | PARTIAL |
| Qwen | 8 | f03-d01 | retrieved__retrieved | MATCH |
| Qwen | 9 | f03-d02 | retrieved__retrieved | PARTIAL |
| Qwen | 10 | f04-d01 | retrieved__none | MISMATCH |
| Qwen | 11 | f04-d01 | retrieved__full | MATCH |
| Qwen | 12 | f04-d01 | retrieved__retrieved | MATCH |
| Qwen | 13 | f04-d02 | retrieved__none | MISMATCH |
| Qwen | 14 | f04-d02 | retrieved__retrieved | MISMATCH |
| Qwen | 15 | f05-d01 | retrieved__full | MATCH |
| Qwen | 16 | f05-d02 | retrieved__full | MATCH |
| Qwen | 17 | f05-d02 | retrieved__retrieved | MATCH |
| Qwen | 18 | f06-d01 | retrieved__full | MATCH |
| Qwen | 19 | f06-d01 | full__retrieved | MATCH |
| Qwen | 20 | f06-d01 | retrieved__retrieved | MATCH |
| Qwen | 21 | f07-d02 | retrieved__full | MATCH |
| Qwen | 22 | f07-d02 | retrieved__retrieved | MATCH |
| Qwen | 23 | f08-d02 | retrieved__full | PARTIAL |

The wrong-candidate cases remain mismatches even when their descriptions are valid facts about another registered entry. The malformed Gemma case includes fenced, truncated JSON and two competing definitions; its raw text is retained for audit and receives no recovered-answer credit. The prior role/organization and NIL errors lie outside this 57-case queue and remain unchanged in the complete diagnostics.

Before using a semantic rubric as a prospective primary metric, define it before inference, arrange independent adjudication, and preserve both answer-content and evidence-availability results. This AI assessment is useful for distinguishing the observed formatting cost from candidate selection failures; it does not supply those independent validation conditions.
