# Input-contract diagnostic — 2026-10-13

The explicit `ABC → candidate` surface binding repaired the observed over-abstention in this small controlled experiment. Renaming/partitioning policy fields alone did not improve the result.

Tested commit: `e929e3af046f78e10d74ec9bf1c8582b11794ab0`. Existing one-server `mil-gemma4-12b-bf16` service; fixed temperature 0, seed 0, disabled thinking and 128-token output cap. All 56 requests completed without transport or parsing errors. Full core suite: **551 passed in 13.58s**. Process exit 0 was verified.

## Four-condition result

| Condition | Overall /14 | Answerable QA /5 | Valid routing /5 | Over-abstention /10 | Safe abstention /4 | Scope switches /3 |
|---|---:|---:|---:|---:|---:|---:|
| original | 5 | 0 | 1 | 9 | 4 | 0 |
| surface_only | 14 | 5 | 5 | 0 | 4 | 3 |
| schema_only | 5 | 0 | 1 | 9 | 4 | 0 |
| both | 14 | 5 | 5 | 0 | 4 | 3 |

Surface-present conditions improve the same nine previously failing cases with zero harmful changes. Definitions, entity IDs, statuses, candidate order, questions, system policy and the original execution guard are fixed. Ambiguous/NIL cases remain four safe abstentions in every condition. Every emitted non-null ID, including ancillary QA IDs, matches the original resolved binding; no wrong or guard-accepted unauthorized IDs were observed.

The original 14 structured/evidence-only prompts byte-match the prior run. This fresh control reproduces its 5/14 task score. The two-factor comparison separates missing surface bindings from the earlier hypothesis about policy field names: surface alone is sufficient here; field names alone are insufficient. Adding the fields after surface produces no further score change in this sample. This supports input binding loss as the cause of these fixture failures, without asserting a universal model behavior.

No hidden correct QA paraphrases were rejected by exact matching. All finish reasons are stop; the largest completion is 36 tokens, below the 128-token cap. Actual prompt/completion totals are 18,556/1,184 tokens.

## Protocol and scope

The [protocol](CONTRACT_PROBE_PROTOCOL.json) was frozen before inference. The model receives only system/user strings. Surface comes from the original pack, not expected labels. Minimal structured cards stay identical except for the two declared factors. Condition order is rotated separately within QA and routing; all requests are stateless. Original missing-card cases naturally have no surface intervention.

The input is a policy-named minimal representation, retaining definition/status card keys. It is not a full production pack trial. Fourteen correlated synthetic cases, one model and one observation per cell do not certify deployment error or retrieval superiority. Existing model config hashes match the prior run, but the checkpoint revision/weight content is not verified. Latency is measured on a shared API/GPU.

## Reproduction and artifacts

```sh
python -m eval.run_product_llm --track contract_probe \
  --endpoint http://127.0.0.1:18090/v1 \
  --model mil-gemma4-12b-bf16 \
  --out-dir /path/to/new-exclusive-contract-run \
  --code-revision e929e3af046f78e10d74ec9bf1c8582b11794ab0 \
  --max-tokens 128 --timeout 180
```

[Detailed result](CONTRACT_PROBE_RESULTS.json), [sealed manifest](contract_probe_20261013/run_manifest.json), [requests](contract_probe_20261013/requests.jsonl), [raw responses](contract_probe_20261013/responses.jsonl), [graded diagnostics](contract_probe_20261013/graded.json). Input/source hashes, all artifact hashes, manifest seal, offline regrading and all 56 raw outputs were independently checked.

Remote log: `/home/one/logs/krtf-contract-probe-20261013T021940Z.log`. Status: `/home/one/logs/krtf-contract-probe-20261013T021940Z.status.json` (exit 0). Local copies: `/home/seorii/logs/krtf-contract-probe-20261013T021940Z.log` and `/home/seorii/logs/krtf-contract-probe-20261013T021940Z.status.json`.
