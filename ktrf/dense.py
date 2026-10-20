"""Entity dense retrieval: flat inner-product index (spec §22.3, §11.2).

Vectors are computed at compile time from entity profiles (canonical +
description + domains) and searched at Pass 2 (§21.6). ``index_type`` is
``flat_ip`` per the manifest example; numpy accelerates search when present,
with a pure-Python fallback so the artifact stays loadable anywhere.
"""

from __future__ import annotations

import math
from numbers import Real
import struct

from .glossary import Entity

try:
    import numpy as _np
except ImportError:  # pure-Python fallback
    _np = None


def entity_profile_text(e: Entity) -> str:
    """§22.3 entity profile: canonical / description / domains."""
    parts = [e.canonical]
    if e.description:
        parts.append(e.description)
    if e.domain_ids:
        parts.append(" ".join(e.domain_ids))
    return ". ".join(parts)


class VectorIndex:
    FORMAT_VERSION = "flat-ip-f32-v1"

    def __init__(self, entity_ids: list[str], vectors: list[list[float]]):
        if len(entity_ids) != len(vectors):
            raise ValueError("vector entity count does not match row count")
        if any(not isinstance(eid, str) or not eid for eid in entity_ids):
            raise ValueError("vector entity IDs must be nonempty strings")
        if len(set(entity_ids)) != len(entity_ids):
            raise ValueError("vector entity IDs must be unique")
        self.entity_ids = list(entity_ids)
        self.dim = len(vectors[0]) if vectors else 0
        if vectors and not self.dim:
            raise ValueError("nonempty vector index requires a positive dimension")
        if any(len(v) != self.dim for v in vectors):
            raise ValueError("vector rows must have one consistent dimension")
        # The digest and the persisted payload use the exact values searched by
        # numpy. Quantize here even without numpy so fallback roundtrips have
        # the same content identity; reject float32 overflow as well as NaN/inf.
        rows = [[self._float32(value) for value in row] for row in vectors]
        self._matrix = _np.array(rows, dtype=_np.float32) if _np is not None else rows

    @staticmethod
    def _float32(value) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError("vectors must contain finite real numbers")
        try:
            rounded = struct.unpack("!f", struct.pack("!f", value))[0]
        except (OverflowError, struct.error) as exc:
            raise ValueError("vector value is outside the finite float32 range") from exc
        if not math.isfinite(rounded):
            raise ValueError("vectors must contain finite float32 values")
        return rounded

    def search(self, query: list[float], top_k: int = 10) -> list[tuple[str, float]]:
        if len(query) != self.dim:
            raise ValueError(f"query dimension {len(query)} does not match index {self.dim}")
        q_values = [self._float32(value) for value in query]
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
            raise ValueError("top_k must be a nonnegative integer")
        if not self.entity_ids:
            return []
        if _np is not None:
            q = _np.asarray(q_values, dtype=_np.float32)
            sims = self._matrix @ q
            idx = sims.argsort()[::-1][:top_k]
            return [(self.entity_ids[i], float(sims[i])) for i in idx]
        scored = [
            (eid, sum(a * b for a, b in zip(vec, q_values, strict=True)))
            for eid, vec in zip(self.entity_ids, self._matrix, strict=True)
        ]
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]

    def to_dict(self) -> dict:
        matrix = (self._matrix.tolist() if _np is not None
                  else [list(row) for row in self._matrix])
        return {"entity_ids": list(self.entity_ids), "vectors": matrix,
                "index_type": "flat_ip", "dim": self.dim,
                "format_version": self.FORMAT_VERSION}

    @classmethod
    def from_dict(cls, d: dict) -> "VectorIndex":
        if d.get("format_version") != cls.FORMAT_VERSION:
            raise ValueError("unsupported vector format; recompile and save the dense snapshot")
        if d.get("index_type") != "flat_ip":
            raise ValueError("unsupported vector index_type")
        if type(d.get("dim")) is not int or d["dim"] < 0:
            raise ValueError("vector dimension must be a nonnegative integer")
        if not isinstance(d.get("entity_ids"), list) or not isinstance(d.get("vectors"), list):
            raise ValueError("vector entity_ids and vectors must be lists")
        if any(not isinstance(row, list) for row in d["vectors"]):
            raise ValueError("vector rows must be lists")
        index = cls(d["entity_ids"], d["vectors"])
        if index.dim != d["dim"]:
            raise ValueError("vector dimension metadata does not match rows")
        return index


class DenseArtifacts:
    """Compiled dense-retrieval bundle attached to a snapshot (§7.11)."""

    def __init__(self, encoder, index: VectorIndex):
        if (index.entity_ids and getattr(encoder, "dim", index.dim) != index.dim):
            raise ValueError("vector dimension does not match the encoder")
        self.encoder = encoder
        self.index = index

    @property
    def encoder_id(self) -> str:
        return self.encoder.encoder_id

    @classmethod
    def build(cls, glossary, encoder) -> "DenseArtifacts":
        texts = [entity_profile_text(e) for e in glossary.entities]
        vectors = encoder.encode_passages(texts)
        ids = [e.entity_id for e in glossary.entities]
        return cls(encoder, VectorIndex(ids, vectors))
