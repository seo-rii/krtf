# Routing confirmation CPU diagnosis

**POSTHOC_DIAGNOSTIC — original scores are unchanged.** Both completed runs were verified with
`read_run`: manifest/artifact digests, frozen requests, raw-output reparsing, and sealed regrading.
This reuses the exposed 192 AI-authored documents; it adds no independent validation sample.

## Literal evidence positions

The following table uses the 128-case confirmation split. `Non-null` is a model proposal;
`reconstructed` requires a globally unique verbatim quote in the target paragraph, exactly
the requested surface occurrence, and a unique occurrence of every claimed attribute value
inside that quote. Only numeric positions change. Missing or ambiguous matches reject the repair.
Gold labels are read only after source-only reconstruction for outcome counting.

| Model / evidence wire | Non-null | Unique quote | Original offsets exact | Quote contains target | Reconstructed | Posthoc correct / wrong approvals |
|---|---:|---:|---:|---:|---:|---:|
| gemma12b / full | 45 | 45 | 0 | 45 | 45 | 31 / 0 |
| gemma12b / compact | 45 | 45 | 0 | 44 | 43 | 32 / 0 |
| qwen27b / full | 45 | 45 | 1 | 43 | 42 | 39 / 0 |
| qwen27b / compact | 45 | 45 | 0 | 44 | 44 | 41 / 0 |

The original occurrence guard, request reference, chosen ID, literal values, assessment,
applicability check and direct-negation check are still applied. A source-position repair does
not establish semantic entailment. Repaired outcomes cannot replace the prospective scores
and do not authorize execution. Detailed rejection counts are in `summary.json`.

## Where positive links are lost

Each row contains the same 64 positive targets of the confirmation split. “Offered” concerns
the actual rendered fact inventory; it is not synonymous with the resolver candidate set.

| Model / condition | Detected | Gold retrieved | Gold offered | Correct model ID | Approved correct ID |
|---|---:|---:|---:|---:|---:|
| gemma12b / plain_check_compact | 64 | 64 | 64 | 64 | 64 |
| gemma12b / ktrf_check_compact | 64 | 64 | 45 | 45 | 42 |
| qwen27b / plain_check_compact | 64 | 64 | 64 | 61 | 61 |
| qwen27b / ktrf_check_compact | 64 | 64 | 45 | 45 | 42 |

The KTRF automation pack renders only resolver-resolved terms. A term may also be
visible because another occurrence was resolved; the requested ambiguous occurrence still
fails its own execution guard. Thus merely exposing a correct entity somewhere in the pack
does not grant authority for the target occurrence.

## Guard-policy confounding

The next table keeps each compact response and its original offered facts fixed, then applies
either the plain membership/binding check or the KTRF occurrence guard. It is a CPU counterfactual:
models did not generate again under the alternative rule, and candidate inventories still differ.

| Model / original prompt | Plain guard correct / wrong | KTRF guard correct / wrong |
|---|---:|---:|
| gemma12b / plain_check_compact | 64 / 11 | 42 / 11 |
| gemma12b / ktrf_check_compact | 45 / 0 | 42 / 0 |
| qwen27b / plain_check_compact | 61 / 3 | 39 / 3 |
| qwen27b / ktrf_check_compact | 45 / 0 | 42 / 0 |

A new bounded experiment should hold candidates and execution authorization fixed, have
the model select immutable server-generated evidence IDs, and report candidate ranking separately
from executable approvals. The consumed confirmation cases are now diagnostic material.
Independent deployment-risk claims still require a new audit population.

## Reproduction

Use the private collected run directories from the original experiment:

```bash
python -m eval.confirmation_diagnostics \
  --gemma-run /private/collected/routing_confirmation_gemma12b \
  --qwen-run /private/collected/routing_confirmation_qwen27b \
  --out-dir /new/aggregate-report
```

`summary.json` contains aggregate counts, source seals, and the diagnostic implementation digest.
No source document text, per-case responses, private paths, or new LLM calls are published.
