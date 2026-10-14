# Definition controls and executable context evidence: interpretation

Both model stages completed on 2026-10-14 at 14:33 KST (05:33 UTC),
with exit code 0. All **1,536 responses** arrived, with no malformed output,
missing response, or API/transport error. Collection, frozen regrading and
push completed with exit code 0. The inference revision is
`5e420c35ab62755bbfbe783c3fb7634e67015680`.

The experiment has two distinct results. Explicit definition boundaries and
copy instructions make plain glossary QA competitive with KTRF in this sample.
The opt-in contextual rule enables 15 correct executable IDs per model on
new direct-declaration cases, without accepting a wrong ID. It does **not**
resolve the original documents' implicit contextual ambiguity.

## Direct declarations improve; original contextual cases do not

Each collection has 32 documents: 16 registered targets and 16 targets requiring
null. The table isolates accepted non-null IDs; correct abstentions are excluded.
Neutral controls check schema and supplied-ID membership for proposals. KTRF
production controls use the complete-response execution guard. Their accepted
counts therefore describe different operational contracts.

| Condition | Original: Gemma correct / wrong | Original: Qwen correct / wrong | Fresh: Gemma correct / wrong | Fresh: Qwen correct / wrong |
|---|---:|---:|---:|---:|
| All glossary, prose | 13 / 0 | 12 / 0 | 16 / 0 | 16 / 0 |
| All glossary, cards | 11 / 0 | 13 / 2 | 16 / 0 | 16 / 0 |
| Retrieved glossary cards | 13 / 8 | 13 / 5 | 9 / 2 | 9 / 0 |
| KTRF QA cards, neutral proposals | 10 / 1 | 14 / 0 | 16 / 0 | 16 / 0 |
| KTRF production | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| KTRF with contextual definition evidence | 0 / 0 | 0 / 0 | **15 / 0** | **15 / 0** |

The opt-in rule improves 15 routing cases and harms none for each model.
Every newly authorized ID is actually returned correctly by both models;
this is not only a symbolic preflight result. All gains occur in the fresh
direct-definition collection. The 16 negative fresh cases remain unapproved.
The original 16 positive targets remain unapproved because their evidence is
implicit or distant rather than a supported direct naming assertion.

The remaining fresh positive, `cd-f06-d02`, names `사업 기획실`, whose canonical
anchor is below the rule's minimum length. Qwen abstains. Gemma returns the
canonical name in the entity-ID field; this is schema-valid text but not a
supplied or authorized ID, so the guard rejects it. Source and gold were not
changed to hide this limitation.

Gemma also proposes non-ID strings for two original role targets
(`f03-d04`, `f07-d04`) in the contextual production arm; the guard rejects
both. Zero accepted errors does not mean all raw selections were correct.
The feature remains disabled by default, explicitly heuristic, and bounded
to direct assertions and local denial checks. It has no validated deployment
risk guarantee.

## Definition extraction no longer shows a general KTRF advantage

Every new condition receives the same full source and explicit target span.
The prose/card formatting pair supplies identical catalog facts, with exact
definition boundaries and common instructions to copy only the definition.
Scores below include the 32 correct-null opportunities as well as positive
answers, and are measured before any routing validator.

| Condition | Gemma QA / 64 | Qwen QA / 64 | Gemma routing / 64 | Qwen routing / 64 |
|---|---:|---:|---:|---:|
| All glossary, prose | **62** | 60 | **61** | 60 |
| All glossary, cards | 55 | 61 | 59 | 59 |
| Retrieved glossary cards | 39 | 48 | 49 | 51 |
| KTRF QA cards, neutral proposals | 57 | 61 | 57 | **62** |
| KTRF production | **62** | 61 | 30 | 32 |
| KTRF with contextual definition evidence | **62** | 61 | 45 | 47 |

The automatic literal-normalization diagnostic adds no QA matches in this
new run. Gemma has six QA `UNASSESSED` outputs: four retrieved-card answers
give only a canonical name, and the same original target gives a name-only
answer in each production arm. Qwen has none. These cases remain uncredited.

The formatting-only comparison is mixed. Prose to JSON cards hurts seven
Gemma QA cases and helps none; it helps one Qwen QA case and hurts none.
Routing changes by -2 for Gemma and -1 for Qwen. Structured cards do not
uniformly improve results.

For the original 32 documents, prose QA reaches 30/32 for Gemma and 28/32
for Qwen, compared with production QA 30/32 and 29/32. In the earlier
document-context run, whole-knowledge prose scored 15/32 and 16/32 under
the exact contract. The new run changes definition boundaries, instructions,
target-span presentation and runtime timing; that historical improvement is
not an isolated causal estimate of formatting. Within the matched new run,
there is no broad production-KTRF QA advantage over the all-glossary controls.
This complements the [separate historical semantic review](../qa_definition_diagnostic_20261014/ADJUDICATION.md)
without changing the earlier sealed scores.

## Retrieval and cost tradeoffs

Retrieved cards supply the gold ID for only 22/32 positive targets, whereas
all-glossary and neutral KTRF QA cards supply it for 32/32. Definitions also
appear in some sources, but a source definition does not supply its opaque
registry ID. Selecting fewer candidates produces 10 wrong accepted IDs for
Gemma and five for Qwen. Several truly ambiguous original cases become
one-candidate prompts; this encourages an unjustified selection. Two Qwen
all-card errors likewise map role expressions to their organizations.

Cards save about 8% of prompt tokens relative to the matched prose control,
with mixed quality changes. Production QA uses more prompt tokens than either
control in these short documents. Adding contextual authorization increases
routing prompt tokens from 34,729 to 39,688 for Gemma and from 32,057 to
36,665 for Qwen, approximately 14%, because the pack now exposes executable
facts. Routing p95 increases from 1.56 to 2.22 seconds and from 2.00 to 3.46
seconds respectively. Preparation costs are excluded; shared-host timings
are descriptive, not a controlled latency guarantee.

## What remains to validate

The next substantial linking improvement must address the original implicit
context cases, while distinguishing real ambiguity, NIL and role semantics.
The direct-declaration rule is useful within its declared scope but is not a
replacement for that work. Candidate-context ranking and a separately
validated abstention threshold should retain the existing structural and
execution guards. A larger LLM alone cannot use IDs that the resolver has
withheld.

The two collections are short AI-authored synthetic documents using the same
eight glossary families. Their gold has AI review, not independent human
verification. The original collection was previously inspected; the fresh
collection tests deliberately explicit declarations and negative cues.
Report the collections separately, preserve these source/gold limitations,
and do not infer a service error rate or fixed-risk guarantee from zero
observed wrong accepted IDs.

Full frozen outcomes, costs and paired changes are in the
[Gemma report](documents_gemma12b/RESULTS.md),
[Qwen report](documents_qwen27b/RESULTS.md) and
[matched model comparison](documents_comparison.md). The
[queue status](queue_status.json) records exit code 0, and the
[test proof](unit_test_status.json) records successful validation at the
inference revision: 988 tests passed.
