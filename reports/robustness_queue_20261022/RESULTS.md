# KTRF reused-source evidence robustness and bundle cost diagnostics

Status: **COMPLETE**, exit code `0`.

Frozen unit tests and actual-tokenizer preparation completed before GPU generation.

| Stage | Status | Received/planned |
|---|---|---:|
| [evidence_robustness_gemma12b](evidence_robustness_gemma12b/RESULTS.md) | COMPLETE | 384/384 |
| [evidence_robustness_qwen27b](evidence_robustness_qwen27b/RESULTS.md) | COMPLETE | 384/384 |

## Limitations

- All source documents and original development/confirmation families are reused from the evidence-efficiency experiment; no fresh holdout or independent replication claim.
- This adaptive diagnostic compares evidence representation, candidate/catalog ordering and unrelated evidence distractors on the same 64 AI-authored cases.
- Bundles bind the same four server-known attribute spans; they do not establish semantic entailment or grant execution authority.
- Every arm retains actual resolver candidates and the unchanged production occurrence guard.
- Family and document paired analyses remain descriptive; repeated conditions do not increase the independent sample size.
- No private workplace documents or independent human annotations have been supplied; shared-host costs do not establish deployment guarantees.
