# KTRF reused-source support-recovery discovery (evaluation only)

Status: **COMPLETE**, exit code `0`.

Frozen unit tests and actual-tokenizer preparation completed before GPU generation.

| Stage | Status | Received/planned |
|---|---|---:|
| [support_recovery_gemma12b](support_recovery_gemma12b/RESULTS.md) | COMPLETE | 512/512 |
| [support_recovery_qwen27b](support_recovery_qwen27b/RESULTS.md) | COMPLETE | 512/512 |

## Limitations

- All 64 source documents are reused AI-authored diagnostic cases; eight conditions do not constitute eight independent samples.
- Production conditions retain the unchanged occurrence guard; shadow conditions are EXPERIMENTAL_SIMULATED_APPROVAL and grant no execution authority.
- Candidate and source inventories are built without gold; source attribution rules and missing-attribute policies remain experimental rather than semantic guarantees.
- Model proposals, production guard acceptance and simulated shadow acceptance are reported separately for every condition.
- No actual workplace documents or independent human gold have been provided; these results cannot certify deployment error bounds.
- Shared families and paired conditions require clustered interpretation, and shared-host latency is descriptive.
