# KTRF source, compact-pack and safety diagnostics

Status: **COMPLETE**, exit code `0`.

Frozen unit tests and actual-tokenizer preparation completed before GPU generation.

| Stage | Status | Received/planned |
|---|---|---:|
| [source_pack_factorial_gemma12b](source_pack_factorial_gemma12b/RESULTS.md) | COMPLETE | 768/768 |
| [fresh_compact_gemma12b](fresh_compact_gemma12b/RESULTS.md) | COMPLETE | 384/384 |
| [safety_robustness_gemma12b](safety_robustness_gemma12b/RESULTS.md) | COMPLETE | 640/640 |
| [source_pack_factorial_qwen27b](source_pack_factorial_qwen27b/RESULTS.md) | COMPLETE | 768/768 |
| [fresh_compact_qwen27b](fresh_compact_qwen27b/RESULTS.md) | COMPLETE | 384/384 |
| [safety_robustness_qwen27b](safety_robustness_qwen27b/RESULTS.md) | COMPLETE | 640/640 |

## Limitations

- The source/pack factorial reuses previously inspected questions and is an adaptive diagnostic, not independent validation.
- Fresh KLUE contexts exclude prior source contexts and the complete earlier 512-context search corpus; original article identities and pretraining independence remain unverified.
- The factorial fixes policy and pack facts across source amounts; its arms are not a shared-token-cap product comparison.
- Compact packs remove metadata while preserving projected semantic facts and caveats; this is not pure serialization alone.
- Safety results must separate 96 exposed cases from 64 fresh AI-authored cases; shared families and prompt variants are not independent samples.
- Prompt instructions add no execution authority: complete responses still pass the unchanged production guard.
- These tests do not tune deployment thresholds or establish operational error-rate guarantees.
