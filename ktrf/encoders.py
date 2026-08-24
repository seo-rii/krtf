"""Bi-encoder backends for entity dense retrieval (spec §22.3, §33 V2).

Two implementations behind one interface:

- :class:`HashEncoder` — deterministic jamo/char n-gram hashing projection.
  Pure Python, always available; a *lexical* dense baseline used in CI and
  as the zero-dependency default. It retrieves surface-similar canonicals
  (한전공사 ↔ 한국전력공사) but has no semantic power.
- :class:`OnnxE5Encoder` — multilingual-e5 via ONNX Runtime (§34), the
  MODEL_RECOMMEND.md Role-2 lightweight reference. Uses the mandatory
  ``query:`` / ``passage:`` input prefixes, mean pooling, L2 norm.

The ``encoder_id`` feeds ``entity_encoder_hash`` in the manifest so the
compatibility contract (§11.3, INV-015) refuses to reuse vectors across
encoder changes.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

from .hangul import to_jamo_seq


def _providers(ort, device: str) -> list[str]:
    """GPU throughput path with CPU fallback (docs/GPU_PLAN.md Phase G1).

    Deterministic mode stays on CPU (§34 고정 커널); "cuda" requests the
    CUDA EP when the installed onnxruntime build offers it and silently
    falls back otherwise, so bundles stay loadable on any machine.
    """
    if device == "cuda" and "CUDAExecutionProvider" in ort.get_available_providers():
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


class HashEncoder:
    """Jamo n-gram feature hashing with L2 normalization (lexical baseline)."""

    # observed similarity band for score normalization in fusion
    sim_range = (0.15, 0.75)

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.encoder_id = f"hash-jamo-ngram-v1-d{dim}"

    def _vector(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        jamo = to_jamo_seq(text.lower())
        for n in (2, 3, 4):
            for i in range(len(jamo) - n + 1):
                gram = jamo[i:i + n]
                h = int.from_bytes(
                    hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest(),
                    "little")
                v[h % self.dim] += 1.0 / n
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def encode_query(self, text: str) -> list[float]:
        return self._vector(text)


class OnnxE5Encoder:
    """multilingual-e5 (small/base) through ONNX Runtime.

    Expects a model directory containing ``model.onnx`` (or a quantized
    variant) and ``tokenizer.json``. Raises ImportError/OSError when the
    stack or files are unavailable — callers fall back to HashEncoder.
    """

    sim_range = (0.72, 0.92)  # e5 cosine band on this task family

    def __init__(self, model_dir: str | Path, max_length: int = 128,
                 device: str = "cpu"):
        import numpy as np  # noqa: F401 (hard dependency of this backend)
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._np = np
        d = Path(model_dir)
        onnx_file = next(
            (d / n for n in ("model.onnx", "model_quantized.onnx",
                             "model_int8.onnx") if (d / n).exists()), None)
        if onnx_file is None or not (d / "tokenizer.json").exists():
            raise OSError(f"no ONNX model/tokenizer under {d}")
        self._session = ort.InferenceSession(
            str(onnx_file), providers=_providers(ort, device))
        self.device = ("cuda" if "CUDAExecutionProvider"
                       in self._session.get_providers() else "cpu")
        self._tokenizer = Tokenizer.from_file(str(d / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=max_length)
        self.max_length = max_length
        with open(onnx_file, "rb") as f:
            head = f.read(1 << 20)
        self.encoder_id = (f"e5-onnx:{d.name}:"
                           + hashlib.sha256(head).hexdigest()[:12])
        self.dim = int(self._embed(["query: probe"]).shape[1])

    def _embed(self, texts: list[str]):
        np = self._np
        enc = self._tokenizer.encode_batch(texts)
        maxlen = max(len(e.ids) for e in enc)
        ids = np.zeros((len(enc), maxlen), dtype=np.int64)
        mask = np.zeros((len(enc), maxlen), dtype=np.int64)
        for i, e in enumerate(enc):
            ids[i, :len(e.ids)] = e.ids
            mask[i, :len(e.ids)] = e.attention_mask
        feeds = {"input_ids": ids, "attention_mask": mask}
        input_names = {i.name for i in self._session.get_inputs()}
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        out = self._session.run(None, feeds)[0]  # (B, T, H) last hidden state
        m = mask[:, :, None].astype(out.dtype)
        pooled = (out * m).sum(axis=1) / m.sum(axis=1).clip(min=1e-9)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
        return pooled / norms

    def encode_passages(self, texts: list[str],
                        batch_size: int = 32) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = ["passage: " + t for t in texts[i:i + batch_size]]
            out.extend(self._embed(batch).tolist())
        return out

    def encode_query(self, text: str) -> list[float]:
        return self._embed(["query: " + text])[0].tolist()


def load_encoder(spec: str | None, device: str = "cpu"):
    """Resolve an encoder spec: None -> None (Level A-only), "hash" ->
    HashEncoder, "hash:<dim>" -> sized HashEncoder, "onnx:<dir>" -> e5.
    ``device="cuda"`` selects the GPU execution provider when available
    (docs/GPU_PLAN.md Phase G1); the encoder_id — and therefore vector
    compatibility (§11.3) — is device-independent."""
    if spec is None:
        return None
    if spec == "hash":
        return HashEncoder()
    if spec.startswith("hash:"):
        return HashEncoder(dim=int(spec.split(":", 1)[1]))
    if spec.startswith("onnx:"):
        return OnnxE5Encoder(spec.split(":", 1)[1], device=device)
    raise ValueError(f"unknown encoder spec {spec!r}")
