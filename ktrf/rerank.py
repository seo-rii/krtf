"""Conditional cross-encoder reranking (spec §22.3-22.4, V3 quality stage).

The production cross-encoder is trained in-house from KLUE-RoBERTa-base with
dictionary-conditioned episodes (§35 Stage B, §36; MODEL_RECOMMEND.md Role 1)
— that training needs tenant data, so this module ships:

- :class:`LexicalCrossEncoder` — the deterministic pre-training baseline
  (character/jamo-bigram compatibility between mention context and entity
  profile); zero-dependency default;
- :class:`OnnxCrossEncoder` — loads any fine-tuned pair-scoring ONNX model
  (e.g. a trained KLUE-RoBERTa or bge-reranker-v2-m3-ko export) when one is
  available.

Execution is conditional (§22.4): only mentions with ≥2 senses and a thin
margin are reranked, under the ``max_cross_encoder_pairs`` budget (§31.1).
Scores are evidence for fusion — they never delete candidates (INV-010).
"""

from __future__ import annotations

import math
from pathlib import Path

from .hangul import to_jamo_seq


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else set()


def _f1(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    p, r = inter / len(b), inter / len(a)
    return 2 * p * r / (p + r)


class LexicalCrossEncoder:
    """Char+jamo bigram compatibility scorer (pre-training stand-in)."""

    reranker_id = "lexical-xenc-v1"

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        out = []
        for context, profile in pairs:
            c, p = context.lower(), profile.lower()
            char_f1 = _f1(_bigrams(c), _bigrams(p))
            jamo_f1 = _f1(_bigrams(to_jamo_seq(c)), _bigrams(to_jamo_seq(p)))
            raw = 0.5 * char_f1 + 0.5 * jamo_f1
            # squash into (0,1) centered near typical overlap levels
            out.append(round(1.0 / (1.0 + math.exp(-(8.0 * raw - 1.2))), 4))
        return out


class OnnxCrossEncoder:
    """Fine-tuned pair scorer via ONNX Runtime (sequence-pair, 1 logit)."""

    def __init__(self, model_dir: str | Path, max_length: int = 192):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._np = np
        d = Path(model_dir)
        onnx_file = next(
            (d / n for n in ("model.onnx", "model_quantized.onnx")
             if (d / n).exists()), None)
        if onnx_file is None or not (d / "tokenizer.json").exists():
            raise OSError(f"no ONNX cross-encoder under {d}")
        self._session = ort.InferenceSession(
            str(onnx_file), providers=["CPUExecutionProvider"])
        self._tokenizer = Tokenizer.from_file(str(d / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=max_length)
        self.reranker_id = f"onnx-xenc:{d.name}"

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        np = self._np
        enc = [self._tokenizer.encode(a, b) for a, b in pairs]
        maxlen = max(len(e.ids) for e in enc)
        ids = np.zeros((len(enc), maxlen), dtype=np.int64)
        mask = np.zeros((len(enc), maxlen), dtype=np.int64)
        types = np.zeros((len(enc), maxlen), dtype=np.int64)
        for i, e in enumerate(enc):
            ids[i, :len(e.ids)] = e.ids
            mask[i, :len(e.ids)] = e.attention_mask
            types[i, :len(e.type_ids)] = e.type_ids
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in {i.name for i in self._session.get_inputs()}:
            feeds["token_type_ids"] = types
        logits = self._session.run(None, feeds)[0]
        scores = 1.0 / (1.0 + np.exp(-logits[:, 0]))
        return [round(float(s), 4) for s in scores]


def load_reranker(spec: str | None):
    if spec is None:
        return None
    if spec == "lexical":
        return LexicalCrossEncoder()
    if spec.startswith("onnx:"):
        return OnnxCrossEncoder(spec.split(":", 1)[1])
    raise ValueError(f"unknown reranker spec {spec!r}")
