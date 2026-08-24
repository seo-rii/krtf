"""Learned score fusion (spec §23, V2 configuration).

The resolver always computes a per-candidate feature vector; without a
fitted model the V1 additive heuristic combines them, and with one a
logistic :class:`FusionModel` (fit from ACCEPTED corrections, like the
calibrator) produces ``ranking_score``. Hard validity conditions (§23.1)
stay outside fusion, and prior-style features are bounded by construction
(§23.3 clipping).
"""

from __future__ import annotations

import math

FEATURE_NAMES = [
    "exact_score",       # best exact/normalized channel score
    "doc_local_score",
    "fuzzy_score",       # best of jamo/keyboard
    "abbrev_score",
    "dense_score",
    "context_overlap",   # bigram context bonus (already clipped)
    "scope_adj",
    "doc_local_boost",
    "xenc",              # conditional cross-encoder score (0.5 = neutral)
    "transform_cost",
    "is_exact",
    "single_sense",      # 1/n_senses among exact candidates
]


def feature_vector(features: dict) -> list[float]:
    return [float(features.get(n, 0.0)) for n in FEATURE_NAMES]


class FusionModel:
    """Logistic fusion over FEATURE_NAMES; a snapshot artifact (§7.11)."""

    def __init__(self, weights: list[float], bias: float,
                 version: str = "fusion-1"):
        assert len(weights) == len(FEATURE_NAMES)
        self.weights = list(weights)
        self.bias = bias
        self.version = version

    def predict(self, features: dict) -> float:
        z = self.bias + sum(w * x for w, x in
                            zip(self.weights, feature_vector(features)))
        return round(1.0 / (1.0 + math.exp(-z)), 4)

    def to_dict(self) -> dict:
        return {"version": self.version, "weights": self.weights,
                "bias": self.bias, "feature_names": FEATURE_NAMES}

    @classmethod
    def from_dict(cls, d: dict) -> "FusionModel":
        if d.get("feature_names") != FEATURE_NAMES:
            # §11.3: ranking feature schema change invalidates the artifact
            raise ValueError("fusion feature schema mismatch")
        return cls(d["weights"], d["bias"], d.get("version", "fusion-1"))


def fit_fusion(rows: list[tuple[dict, int]], iters: int = 300,
               lr: float = 0.3, l2: float = 1e-3) -> FusionModel:
    """Fit logistic fusion from (features, label) rows (ACCEPTED corrections
    only — enforced upstream, INV-018)."""
    if len(rows) < 20 or not any(y for _, y in rows):
        raise ValueError("insufficient fusion training data")
    xs = [feature_vector(f) for f, _ in rows]
    ys = [y for _, y in rows]
    k = len(FEATURE_NAMES)
    w = [0.0] * k
    b = 0.0
    n = len(xs)
    for _ in range(iters):
        gw = [0.0] * k
        gb = 0.0
        for x, y in zip(xs, ys):
            p = 1.0 / (1.0 + math.exp(-(b + sum(wi * xi for wi, xi in zip(w, x)))))
            d = p - y
            for j in range(k):
                gw[j] += d * x[j]
            gb += d
        for j in range(k):
            w[j] -= lr * (gw[j] / n + l2 * w[j])
        b -= lr * gb / n
    return FusionModel(w, b)
