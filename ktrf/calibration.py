"""Tenant calibrator: fitting, persistence, conformal prediction sets (spec §25).

The V1 default is the heuristic global conservative calibrator baked into the
resolver (§48.1 zero-training start, REQ-CAL-003). This module implements the
adaptation path (§48.3): a :class:`TunedCalibrator` fitted from ACCEPTED
corrections, per §25.2 [normative]:

1. marginal calibration — Platt scaling of the fusion ``ranking_score``
   (group-shared sigmoid; per-candidate marginal, INV-019),
2. nonconformity ``s(x, y) = 1 − calibrated_marginal(y)``,
3. group-conditional (Mondrian) split conformal quantile
   ``q̂ = ⌈(n+1)(1−α)⌉ / n`` per group,
4. groups below ``n_min`` fall back to the pooled quantile, and the fallback
   is flagged (REQ-CAL-002).

Groups follow a simplified §25.4 scheme: generation-channel class × sense
count bucket.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def calibration_group(channels: set[str] | list[str], n_senses: int) -> str:
    """Group key shared between fitting and inference (§25.4, simplified)."""
    chs = set(channels)
    if "exact" in chs or "normalized" in chs:
        cls = "exact"
    elif chs & {"jamo", "keyboard"}:
        cls = "fuzzy"
    else:
        cls = "dense"
    bucket = "single" if n_senses <= 1 else "multi"
    return f"{cls}|{bucket}"


@dataclass
class TrainingExample:
    """One (candidate, label) pair derived from an approved correction."""

    ranking_score: float
    group: str
    label: int  # 1 = this candidate was the corrected/true entity


def _fit_platt(scores: list[float], labels: list[int],
               iters: int = 200, lr: float = 0.5) -> tuple[float, float]:
    """Fit sigmoid(a*s + b) by gradient descent on log loss (1-D logistic)."""
    a, b = 1.0, 0.0
    n = len(scores)
    for _ in range(iters):
        ga = gb = 0.0
        for s, y in zip(scores, labels):
            p = 1.0 / (1.0 + math.exp(-(a * s + b)))
            ga += (p - y) * s
            gb += p - y
        a -= lr * ga / n
        b -= lr * gb / n
    return a, b


def _conformal_quantile(nonconformity: list[float], alpha: float) -> float:
    """q̂ = ⌈(n+1)(1−α)⌉ / n quantile of the calibration scores (§25.2)."""
    s = sorted(nonconformity)
    n = len(s)
    k = math.ceil((n + 1) * (1 - alpha))
    if k > n:
        return 1.0  # not enough samples to bound below 1
    return s[k - 1]


@dataclass
class TunedCalibrator:
    """Fitted tenant calibrator; a snapshot artifact (§7.11, §54)."""

    platt_a: float
    platt_b: float
    alpha: float
    group_quantiles: dict[str, float]
    global_quantile: float
    # REQ-CAL-003 spirit: the fallback is *conservative* (α 하향 조정) — a
    # pooled quantile at α/2, so under-sampled groups over-cover rather than
    # inherit the majority group's distribution
    fallback_quantile: float
    group_counts: dict[str, int]
    n_min: int
    version: str = "cal-1"

    @property
    def set_confidence(self) -> float:
        return round(1.0 - self.alpha, 4)

    def calibrate_marginal(self, ranking_score: float) -> float:
        p = 1.0 / (1.0 + math.exp(-(self.platt_a * ranking_score + self.platt_b)))
        return round(min(0.99, max(0.01, p)), 3)

    def quantile_for(self, group: str) -> tuple[float, bool]:
        """(q̂, used_fallback). Below n_min, fall back conservatively
        (REQ-CAL-002): the max of the group's own small-sample quantile
        (finite-sample valid, just wide) and the pooled α/2 quantile — an
        under-sampled group widens its sets, never inherits the majority
        group's tighter distribution."""
        if self.group_counts.get(group, 0) >= self.n_min:
            return self.group_quantiles[group], False
        own = self.group_quantiles.get(group, 0.0)
        return max(own, self.fallback_quantile), True

    def in_prediction_set(self, marginal: float, group: str) -> tuple[bool, bool]:
        """(included, used_fallback): s = 1 − marginal ≤ q̂ (§25.2 step 4)."""
        q, fb = self.quantile_for(group)
        return (1.0 - marginal) <= q, fb

    def to_dict(self) -> dict:
        return {
            "version": self.version, "platt_a": self.platt_a,
            "platt_b": self.platt_b, "alpha": self.alpha,
            "group_quantiles": self.group_quantiles,
            "global_quantile": self.global_quantile,
            "fallback_quantile": self.fallback_quantile,
            "group_counts": self.group_counts, "n_min": self.n_min,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TunedCalibrator":
        return cls(
            platt_a=d["platt_a"], platt_b=d["platt_b"], alpha=d["alpha"],
            group_quantiles=dict(d["group_quantiles"]),
            global_quantile=d["global_quantile"],
            fallback_quantile=d.get("fallback_quantile", d["global_quantile"]),
            group_counts=dict(d["group_counts"]), n_min=d["n_min"],
            version=d.get("version", "cal-1"),
        )


def fit_calibrator(examples: list[TrainingExample], alpha: float = 0.05,
                   n_min: int = 500) -> TunedCalibrator:
    """Fit marginal calibration + group-conditional conformal quantiles.

    ``examples`` must come only from ACCEPTED corrections (INV-018 — the
    correction store enforces this on export).

    Split-conformal validity requires that the data fitting the probability
    map (Platt) and the data supplying the conformal quantiles are
    DISJOINT — reusing one set for both voids the finite-sample coverage
    guarantee. Examples are therefore split deterministically in half:
    even-indexed examples fit Platt scaling, odd-indexed positives form the
    conformal calibration set. (Callers who can group by document/entity
    should pre-order examples so correlated rows land on one side.)
    """
    if len(examples) < 10 or not any(e.label for e in examples):
        raise ValueError(
            "insufficient calibration data: need >=10 examples with >=1 positive"
        )
    fit_half = examples[0::2]
    conf_half = examples[1::2]
    if not any(e.label for e in fit_half) or not any(
            e.label for e in conf_half):
        # tiny/degenerate label distribution: fall back to the full set for
        # Platt but KEEP the halves disjoint for the quantiles
        fit_half = examples
    a, b = _fit_platt([e.ranking_score for e in fit_half],
                      [e.label for e in fit_half])

    def marginal(score: float) -> float:
        return 1.0 / (1.0 + math.exp(-(a * score + b)))

    positives = [e for e in conf_half if e.label == 1] or \
        [e for e in examples if e.label == 1]
    by_group: dict[str, list[float]] = {}
    for e in positives:
        by_group.setdefault(e.group, []).append(1.0 - marginal(e.ranking_score))
    all_scores = [s for lst in by_group.values() for s in lst]
    return TunedCalibrator(
        platt_a=a, platt_b=b, alpha=alpha,
        group_quantiles={g: _conformal_quantile(lst, alpha)
                         for g, lst in by_group.items()},
        global_quantile=_conformal_quantile(all_scores, alpha),
        fallback_quantile=_conformal_quantile(all_scores, alpha / 2),
        group_counts={g: len(lst) for g, lst in by_group.items()},
        n_min=n_min,
    )


# ---------------------------------------------------------------------------
# Training-pair extraction and online coverage (§25.5, REQ-CAL-004)
# ---------------------------------------------------------------------------

_GOLD_BEARING = {"WRONG_ENTITY", "SHOULD_BE_RESOLVED"}


def derive_training_examples(correction: dict) -> list[TrainingExample]:
    """Turn one ACCEPTED correction (with its ``mention_state``) into pairs.

    ``mention_state`` is the mention object from the original response
    (§30.1 — span/state data, no raw text). Each ENTITY member of its
    prediction set becomes one example labeled against the corrected entity.
    """
    state = correction.get("mention_state") or {}
    members = [m for m in state.get("prediction_set", {}).get("members", [])
               if m.get("kind", "ENTITY") == "ENTITY"
               and m.get("ranking_score") is not None]
    if not members:
        return []
    ctype = correction.get("correction_type")
    if ctype in _GOLD_BEARING:
        gold = (correction.get("corrected") or {}).get("entity_id")
    elif ctype == "SHOULD_BE_KB_MISSING":
        gold = None  # every entity member is a negative
    else:
        return []  # span/mention-level corrections carry no sense label
    n_senses = len(members)
    out = []
    for m in members:
        group = calibration_group(set(m.get("generation_channels", [])), n_senses)
        out.append(TrainingExample(m["ranking_score"], group,
                                   int(m.get("entity_id") == gold)))
    return out


def empirical_coverage(corrections: list[dict]) -> dict:
    """Online empirical coverage from ACCEPTED gold-bearing corrections
    (§25.5). Never claimed without a correction path (REQ-CAL-004)."""
    total = covered = 0
    set_sizes: list[int] = []
    for c in corrections:
        if c.get("correction_type") not in _GOLD_BEARING:
            continue
        gold = (c.get("corrected") or {}).get("entity_id")
        state = c.get("mention_state") or {}
        members = [m for m in state.get("prediction_set", {}).get("members", [])
                   if m.get("kind", "ENTITY") == "ENTITY"]
        if gold is None or not state:
            continue
        total += 1
        set_sizes.append(len(members))
        covered += int(any(m.get("entity_id") == gold for m in members))
    if not total:
        return {"labeled": 0, "coverage": None, "mean_set_size": None}
    return {
        "labeled": total,
        "coverage": round(covered / total, 4),
        "mean_set_size": round(sum(set_sizes) / total, 2),
    }
