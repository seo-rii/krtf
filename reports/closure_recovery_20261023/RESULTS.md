# KTRF fresh server evidence closure, null response and bundle confirmation (evaluation only)

Status: **COMPLETE**, exit code `0`.

Frozen unit tests and actual-tokenizer preparation completed before GPU generation.

Recovery: **480 new Gemma requests; 480 reused Qwen requests**. The Qwen stage was not regenerated. Gemma GPU memory utilization changes `0.45 → 0.75`; requests, decoding and inference policy are unchanged.

| Stage | Status | Received/planned |
|---|---|---:|
| [evidence_closure_gemma12b](evidence_closure_gemma12b/RESULTS.md) | COMPLETE | 480/480 |
| [evidence_closure_qwen27b](evidence_closure_qwen27b/RESULTS.md) | COMPLETE | 480/480 |

## Limitations

- Fresh AI-authored and independently AI-reviewed source gold was sealed before resolution and generation; it is not human workplace gold.
- 96 documents share 12 semantic families; 48 short and 48 long documents balance candidate country, referent kind and target side.
- The five paired conditions compare server source-span closure, an explicit null response branch and bundle output; repeated conditions are not independent samples.
- All outcomes are experimental shadow judgments with no execution authority; production occurrence-guard outcomes remain separately reported.
- Server-added segments bind existing source references and do not establish semantic entailment or permit cross-occurrence evidence borrowing.
- No private deployment distribution or independent human annotations have been supplied; shared-host latency is descriptive and no deployment risk is certified.
- Recovery permits new generation only for the previously missing Gemma stage; all 480 Qwen responses are reused byte-for-byte from the pinned original completed stage.
- Gemma GPU memory utilization changes from 0.45 to 0.75 to recover startup capacity; experiment requests, decoding and inference policy remain frozen.
- The original Gemma stage failed before benchmark generation, and the original partial collector completed publication with an expected failed-queue exit status.
