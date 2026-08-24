# Neural Baseline Model Recommendations for KTRF (English Summary)

**Bottom line:** KoBERT is not recommended. As of 2026 it is regarded as a legacy model; even when an encoder-only model is needed, KoELECTRA, KLUE-RoBERTa, or the recent Korean-tuned ModernBERT are considered the standard choices. It dates from 2019, trails later generations significantly, and its custom tokenizer adds maintenance burden.

Under the KTRF spec, the "neural baseline" splits into three distinct roles (§33, §35), so candidates should be evaluated per role.

## Role 1 — Pretrained encoder for fine-tuning the cross-encoder, termness classifier, and proposer (§35 Stage B/D)

These components are trained in-house with dictionary-conditioned episodes, so what you need is a fine-tunable base encoder, not an off-the-shelf embedding model.

| Candidate | Size | Notes |
|---|---|---|
| **KLUE-RoBERTa base/large** | 110M / 337M | Baseline model of the KLUE benchmark; uses morpheme-based subword tokenization (morpheme pre-tokenization via an analyzer such as Mecab-ko, followed by BPE) to reflect Korean language characteristics. De facto standard for Korean NLU fine-tuning; fits the spec's 100M–350M target exactly |
| KoELECTRA-v3 base | ~110M | Uses the ELECTRA objective (replaced-token detection), which trains more efficiently for the same compute and offers lightweight variants. Strong for classification heads (termness) |
| mDeBERTa-v3-base / XLM-R base | ~280M | Worth A/B testing given KTRF's many Korean–English mixed-alnum aliases (한전KDN, R&D본부) |
| Korean-tuned ModernBERT variants | base-class | 8,192-token context, Pareto improvements in speed and accuracy over BERT, faster and more memory-efficient than DeBERTaV3. However, the original is pretrained on English only, and experiments show that even after Korean fine-tuning it lands slightly below multilingual models, so verify the maturity of any Korean variant before adopting |

**Recommendation:** KLUE-RoBERTa-base as the primary baseline; run comparison experiments against mDeBERTa-v3-base on the mixed-alnum slice.

## Role 2 — Bi-encoder / entity dense retrieval (§35 Stage C, V2 configuration)

| Candidate | Size | Notes |
|---|---|---|
| **KURE-v1** (Korea Univ.) | 568M | Korean-specialized retrieval model fine-tuned from BGE-M3; 1024-dim embeddings, 8,192 sequence length, trained on 2M Korean query–document pairs with 5 hard negatives each, consistently outperforming other multilingual models across benchmarks |
| KoE5 | ~560M | multilingual-e5-large fine-tuned on Korean, released alongside KURE. Note it inherits the 512-token input limit (rarely an issue for KTRF's short descriptions) |
| BGE-M3 (original) | 568M | Its dense+sparse hybrid scored roughly 8.1 points higher Recall@10 than OpenAI's large embedding on a Korean business-document evaluation. A solid choice if you don't need KURE's Korean specialization |
| multilingual-e5-base | 278M | The option that stays within the spec's 100M–350M ceiling. The large-instruct sibling is frequently cited as top-tier for Korean on the MTEB leaderboard |
| Qwen3-Embedding-0.6B | 596M | Supports 100+ languages, 32K context, flexible 32–1024 output dimensions, instruction-aware; MTEB multilingual score 64.33. Slightly ahead of the comparably sized multilingual-e5-large-instruct and above Cohere's commercial multilingual embedding. Its Matryoshka-style adjustable dimension helps control per-tenant vector footprint in the §32 memory formula (entities × dim × dtype) |

**Recommendation:** Evaluate KURE-v1 as the retrieval-quality reference and multilingual-e5-base as the lightweight reference. The 568M-class models exceed the §33 target (100M–350M), but entity vectors are computed at compile time, so the only online cost is query encoding, and fp16 ONNX fits the 8GB-GPU constraint. Do note that 1024-dim vectors need ~2.7× the memory of 384-dim in §32 capacity planning.

## Role 3 — Reranker (comparison baseline before training your own cross-encoder)

BAAI/bge-reranker-v2-m3 is a lightweight 568M multilingual reranker supporting 18+ languages including Korean, and Korean-optimized derivatives such as dragonkue/bge-reranker-v2-m3-ko are available. Since KTRF's sense cross-encoder is trained in-house anyway (§36), use these both as a pre-training baseline and as candidate initialization weights.

## KTRF-Specific Validation Points

1. **Don't trust public benchmarks at face value.** MTEB/AutoRAG-style benchmarks measure document retrieval, whereas KTRF retrieval is short-alias ↔ short-canonical/description matching — a different distribution. Measuring on the spec's `UE-canonical-only` and `UE-derived-abbreviation` splits (§42) plus your own golden set is mandatory; as one practitioner put it, model cards can't decide this for you — there is no substitute for labeling ~100 of your own queries and measuring directly.
2. **Check licenses.** Conditions vary across KLUE-family (CC-BY-SA), Qwen (Apache), BGE/E5 (MIT), and Gemma-family (custom terms) — confirm on each model card before commercial deployment.
3. **Tokenizer behavior on mixed alnum.** Verify how surfaces like `한전KDN` or `5G특화망` tokenize, and how easily a char/Jamo boundary head (§19.3) can be attached.
4. **ONNX exportability** per §34 (all candidates above use standard architectures, so this is generally unproblematic).

**Final recommendation:** Start with **KLUE-RoBERTa-base** as the V3 cross-encoder/termness base, **KURE-v1** for V2 bi-encoder initialization (multilingual-e5-base as the lightweight alternative), and **bge-reranker-v2-m3-ko** as the reranker comparison baseline — and drop KoBERT from consideration.