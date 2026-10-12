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
import json
from dataclasses import dataclass
from pathlib import Path

from .segmentation import MatchEvidence, ResolutionGuard, StructuralPath

from .hangul import to_jamo_seq

INPUT_VARIANTS = ("surface", "context", "target", "path")


def rerank_query(text: str, span: tuple[int, int], variant: str = "target",
                 path: StructuralPath | None = None, radius: int = 60) -> str:
    """Build controlled query inputs with raw document offsets.

    ``target`` marks which occurrence is being linked, even if the same
    surface appears twice. ``path`` additionally exposes the supplied
    structural hypothesis, including the full-surface semantic contract.
    These formats are opt-in experiments; changing inputs needs recalibration.
    """
    start, end = span
    if not 0 <= start < end <= len(text):
        raise ValueError("target span must be inside the document")
    if radius < 0:
        raise ValueError("radius must be nonnegative")
    if variant not in INPUT_VARIANTS:
        raise ValueError(f"unknown input variant {variant!r}")
    if path is not None and (path.core_span != span or path.core != text[start:end]):
        raise ValueError("path must describe the target span")
    if variant == "surface":
        return text[start:end]
    left, right = max(0, start - radius), min(len(text), end + radius)
    if variant == "context":
        return text[left:right]
    marked = text[left:start] + "[TARGET]" + text[start:end] + "[/TARGET]" + text[end:right]
    if variant == "target":
        return marked
    if path is None:
        raise ValueError("path input requires a structural hypothesis")
    # Include the contract even for a bare reading; as_dict omits defaults.
    features = {**path.as_dict(), "full_identity": path.full_identity,
                "relation": path.relation, "surface_span": list(path.surface_span)}
    return marked + "\nPATH " + json.dumps(features, ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class LinkingHypothesis:
    """One core/path/entity/full-surface reading; no commit authority."""

    path: StructuralPath
    entity_id: str
    profile: str
    channel: str = "abbrev"
    transform_cost: float = 0.0


@dataclass(frozen=True)
class RankedHypothesis:
    hypothesis: LinkingHypothesis
    score: float  # relevance evidence, never a calibrated probability
    commit_allowed: bool
    guard_reasons: tuple[str, ...]


def rank_hypotheses(text: str, hypotheses: list[LinkingHypothesis], scorer,
                    variant: str = "target", guard: ResolutionGuard | None = None,
                    radius: int = 60) -> list[RankedHypothesis]:
    """Score every supplied hypothesis and retain every existing guard.

    Retrieval/pair budgets must be applied once by the caller, before input
    ablations, so every variant sees identical hypotheses. Ranking cannot
    remove a blocked candidate or promote it to commit authority.
    """
    if not hypotheses:
        return []
    guard = guard or ResolutionGuard()
    pairs = [(rerank_query(text, h.path.core_span, variant, h.path, radius), h.profile)
             for h in hypotheses]
    scores = scorer.score_pairs(pairs)
    if len(scores) != len(hypotheses):
        raise ValueError("reranker must return one score per hypothesis")
    out = []
    for h, score in zip(hypotheses, scores):
        if not math.isfinite(score):
            raise ValueError("reranker scores must be finite")
        verdict = guard.evaluate(MatchEvidence.from_path(
            h.channel, h.path, transform_cost=h.transform_cost))
        out.append(RankedHypothesis(h, float(score), verdict.commit_allowed, verdict.reasons))
    return sorted(out, key=lambda r: (-r.score, r.hypothesis.path.core_span,
                                      r.hypothesis.entity_id, r.hypothesis.path.kind))


def maxsim(query: list[list[float]], document: list[list[float]]) -> float:
    """Sum per-query-token maximum dot products over document tokens.

    Inputs are model-produced, masked token vectors (normally L2-normalized).
    This is candidate reranking, not the single-vector VectorIndex protocol.
    Padding/special-token masks belong to the model adapter.
    """
    if not query or not document:
        raise ValueError("MaxSim requires nonempty token vectors")
    dim = len(query[0])
    if dim == 0 or any(len(v) != dim for v in [*query, *document]):
        raise ValueError("token vectors must share a nonzero dimension")
    if any(not math.isfinite(x) for v in [*query, *document] for x in v):
        raise ValueError("token vectors must be finite")
    return sum(max(sum(a * b for a, b in zip(q, d)) for d in document) for q in query)


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

    def __init__(self, model_dir: str | Path, max_length: int = 192,
                 device: str = "cpu"):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        from .encoders import _providers

        self._np = np
        d = Path(model_dir)
        onnx_file = next(
            (d / n for n in ("model.onnx", "model_quantized.onnx")
             if (d / n).exists()), None)
        if onnx_file is None or not (d / "tokenizer.json").exists():
            raise OSError(f"no ONNX cross-encoder under {d}")
        self._session = ort.InferenceSession(
            str(onnx_file), providers=_providers(ort, device))
        self._tokenizer = Tokenizer.from_file(str(d / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=max_length)
        # content-derived identity (model + tokenizer digest), not just the
        # directory name — a swapped model in a same-named dir must differ
        import hashlib
        h = hashlib.sha256()
        with open(onnx_file, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 22), b""):
                h.update(chunk)
        h.update((d / "tokenizer.json").read_bytes())
        self.reranker_id = f"onnx-xenc:{d.name}:{h.hexdigest()[:32]}"

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
