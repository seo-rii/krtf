"""Entity dense retrieval: flat inner-product index (spec §22.3, §11.2).

Vectors are computed at compile time from entity profiles (canonical +
description + domains) and searched at Pass 2 (§21.6). ``index_type`` is
``flat_ip`` per the manifest example; numpy accelerates search when present,
with a pure-Python fallback so the artifact stays loadable anywhere.
"""

from __future__ import annotations

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
    def __init__(self, entity_ids: list[str], vectors: list[list[float]]):
        assert len(entity_ids) == len(vectors)
        self.entity_ids = list(entity_ids)
        self.dim = len(vectors[0]) if vectors else 0
        self._matrix = _np.array(vectors, dtype=_np.float32) if _np is not None \
            else [list(v) for v in vectors]

    def search(self, query: list[float], top_k: int = 10) -> list[tuple[str, float]]:
        if not self.entity_ids:
            return []
        if _np is not None:
            q = _np.asarray(query, dtype=_np.float32)
            sims = self._matrix @ q
            idx = sims.argsort()[::-1][:top_k]
            return [(self.entity_ids[i], float(sims[i])) for i in idx]
        scored = [
            (eid, sum(a * b for a, b in zip(vec, query)))
            for eid, vec in zip(self.entity_ids, self._matrix)
        ]
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]

    def to_dict(self) -> dict:
        matrix = (self._matrix.tolist() if _np is not None else self._matrix)
        return {"entity_ids": self.entity_ids, "vectors": matrix,
                "index_type": "flat_ip", "dim": self.dim}

    @classmethod
    def from_dict(cls, d: dict) -> "VectorIndex":
        return cls(d["entity_ids"], d["vectors"])


class DenseArtifacts:
    """Compiled dense-retrieval bundle attached to a snapshot (§7.11)."""

    def __init__(self, encoder, index: VectorIndex):
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
