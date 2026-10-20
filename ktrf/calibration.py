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
import hashlib
import json
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
    # Preserve source events; candidate rows and verifier-weight duplicates
    # from one event must never cross a partition boundary.
    event_id: str | None = None
    document_id: str | None = None
    request_id: str | None = None
    mention_id: str | None = None
    correction_id: str | None = None
    sample_source: str = "approved_corrections"


class InsufficientCalibrationData(ValueError):
    calibration_status = "INSUFFICIENT_DATA"


def _sigmoid(value: float) -> float:
    # Stable at extreme scores; exactly the same function at fit and runtime.
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    e = math.exp(value)
    return e / (1.0 + e)


def _partition_source_components(examples: list[TrainingExample]) -> tuple[list, list]:
    """Deterministic, label-independent split of connected source events.

    Shared document/request/correction/event IDs join rows transitively.
    Missing provenance is refused, rather than pretending candidate rows are
    independent observations. IDs must be namespaced by corpus/tenant.
    """
    parents = list(range(len(examples)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    seen = {}
    for i, e in enumerate(examples):
        tokens = [(k, getattr(e, k)) for k in
                  ("event_id", "document_id", "request_id", "correction_id")
                  if getattr(e, k)]
        if not tokens:
            raise InsufficientCalibrationData("insufficient calibration data: source event IDs required")
        if e.mention_id and e.request_id:
            tokens.append(("mention", (e.request_id, e.mention_id)))
        for token in tokens:
            if token in seen:
                parents[root(i)] = root(seen[token])
            else:
                seen[token] = i
    clusters = {}
    for i, e in enumerate(examples):
        clusters.setdefault(root(i), []).append(e)
    def cluster_key(rows):
        ids = sorted({(k, getattr(e, k)) for e in rows for k in
                      ("event_id", "document_id", "request_id", "correction_id")
                      if getattr(e, k)})
        return hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()
    # Stable identities travel with the complete connected component. Sorting
    # rows also makes floating-point fitting independent of caller row order.
    groups = sorted((cluster_key(rows), sorted(rows, key=lambda e: (
        e.group, e.ranking_score, e.label, e.event_id or "",
        e.document_id or "", e.request_id or "", e.mention_id or "",
        e.correction_id or "", e.sample_source))) for rows in clusters.values())
    if len(groups) < 2:
        raise InsufficientCalibrationData("insufficient calibration data: at least two independent source groups required")
    return groups[::2], groups[1::2]


def partition_examples(examples: list[TrainingExample]) -> tuple[list, list]:
    """Split complete source components, retaining the historical row API."""
    fit_components, calibration_components = _partition_source_components(examples)
    return ([e for _, rows in fit_components for e in rows],
            [e for _, rows in calibration_components for e in rows])


def _fit_platt(scores: list[float], labels: list[int],
               iters: int = 200, lr: float = 0.5) -> tuple[float, float]:
    """Fit sigmoid(a*s + b) by gradient descent on log loss (1-D logistic)."""
    a, b = 1.0, 0.0
    n = len(scores)
    for _ in range(iters):
        ga = gb = 0.0
        for s, y in zip(scores, labels):
            p = _sigmoid(a * s + b)
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
    version: str = "cal-3"
    sample_source: str = "approved_corrections"
    partition_manifest: dict = field(default_factory=dict)

    @property
    def coverage_valid(self) -> bool:
        # Fitting on user-reported errors is selection biased. This only
        # declares eligibility for candidate-conditional coverage; callers
        # must additionally validate group support and output truncation.
        proof = self.partition_manifest
        if (self.sample_source != "random_audit"
                or proof.get("schema") != "source_components_v1"
                or proof.get("calibration_unit") != "source_component"
                or proof.get("quantile_score_aggregation") != "maximum_positive_nonconformity"
                or proof.get("coverage_observation_scope") != "one_audited_mention_per_source_component"
                or proof.get("independent_calibration_units") is not True):
            return False
        fit_ids = proof.get("fit_component_ids", [])
        calibration_ids = proof.get("calibration_component_ids", [])
        scored_ids = proof.get("calibration_scored_component_ids", [])
        counts = proof.get("calibration_component_positive_counts", {})
        group_ids = proof.get("group_component_ids", {})
        # Historical artifacts with a true boolean but no component proof are
        # loadable, but cannot inherit a coverage claim. Validate count/proof
        # consistency without re-counting documents from the original rows.
        if (not fit_ids or not scored_ids
                or len(set(fit_ids)) != len(fit_ids)
                or len(set(calibration_ids)) != len(calibration_ids)
                or len(set(scored_ids)) != len(scored_ids)
                or set(fit_ids) & set(calibration_ids)
                or not set(scored_ids) <= set(calibration_ids)
                or set(counts) != set(scored_ids)
                or any(count != 1 for count in counts.values())
                or set(group_ids) != set(self.group_counts)
                or proof.get("calibration_units") != len(scored_ids)):
            return False
        grouped_ids = set()
        for group, ids in group_ids.items():
            if (len(set(ids)) != len(ids) or not set(ids) <= set(scored_ids)
                    or self.group_counts[group] != len(ids)):
                return False
            grouped_ids.update(ids)
        return (grouped_ids == set(scored_ids)
                and 0 < self.alpha < 1
                and len(scored_ids) >= math.ceil(1 / self.alpha) - 1)

    @property
    def set_confidence(self) -> float:
        return round(1.0 - self.alpha, 4)

    def calibrate_marginal(self, ranking_score: float) -> float:
        return _sigmoid(self.platt_a * ranking_score + self.platt_b)

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
            "sample_source": self.sample_source,
            "partition_manifest": self.partition_manifest,
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
            sample_source=d.get("sample_source", "legacy_unknown"),
            partition_manifest=dict(d.get("partition_manifest", {})),
        )


def fit_calibrator(examples: list[TrainingExample], alpha: float = 0.05,
                   n_min: int = 500) -> TunedCalibrator:
    """Fit using disjoint source-event partitions, without data reuse.

    Approved corrections are useful training signals, but are not a random
    deployment audit. Their fitted coverage is explicitly unvalidated.
    """
    if not 0 < alpha < 1 or n_min < 1:
        raise ValueError("alpha must be in (0,1) and n_min must be positive")
    if len(examples) < 10 or not any(e.label for e in examples):
        raise InsufficientCalibrationData("insufficient calibration data: need >=10 examples with positives")
    if any(e.label not in (0, 1) or not math.isfinite(e.ranking_score) for e in examples):
        raise ValueError("calibration scores must be finite and labels binary")
    fit_components, calibration_components = _partition_source_components(examples)
    fit_half = [e for _, rows in fit_components for e in rows]
    conf_half = [e for _, rows in calibration_components for e in rows]
    if {e.label for e in fit_half} != {0, 1} or not any(e.label for e in conf_half):
        raise InsufficientCalibrationData("insufficient calibration data: fitting needs both labels and independent calibration needs positives")
    a, b = _fit_platt([e.ranking_score for e in fit_half],
                      [e.label for e in fit_half])
    # Verifier weights train Platt, but do not manufacture conformal units.
    # The score unit is the SAME transitive source component used for splitting.
    # Multiple positive mentions are conservatively combined by maximum
    # nonconformity. Such clusters remain useful for fitting, but V1 refuses a
    # coverage claim until a cluster-aware audit protocol is supplied.
    by_group: dict[str, list[float]] = {}
    group_component_ids: dict[str, list[str]] = {}
    all_scores = []
    positive_counts = {}
    for component_id, rows in calibration_components:
        unique = {}
        observation_ids = set()
        for e in rows:
            if e.label != 1:
                continue
            observation = ((e.request_id, e.mention_id)
                           if e.request_id and e.mention_id else
                           (e.event_id, e.document_id, e.request_id,
                            e.mention_id, e.correction_id))
            key = (observation, e.group)
            if key in unique and unique[key].ranking_score != e.ranking_score:
                raise InsufficientCalibrationData("conflicting positives for the same source mention")
            unique[key] = e
            observation_ids.add(observation)
        if not unique:
            continue
        positive_counts[component_id] = len(observation_ids)
        component_scores = {}
        for e in unique.values():
            score = 1.0 - _sigmoid(a * e.ranking_score + b)
            component_scores[e.group] = max(score, component_scores.get(e.group, 0.0))
        for group, score in sorted(component_scores.items()):
            by_group.setdefault(group, []).append(score)
            group_component_ids.setdefault(group, []).append(component_id)
        # A source component contributes exactly one pooled observation, even
        # when it contains positives from more than one calibration group.
        all_scores.append(max(component_scores.values()))
    return TunedCalibrator(
        platt_a=a, platt_b=b, alpha=alpha,
        group_quantiles={g: _conformal_quantile(lst, alpha)
                         for g, lst in by_group.items()},
        global_quantile=_conformal_quantile(all_scores, alpha),
        fallback_quantile=_conformal_quantile(all_scores, alpha / 2),
        group_counts={g: len(lst) for g, lst in by_group.items()},
        n_min=n_min,
        sample_source=("random_audit" if all(e.sample_source == "random_audit" for e in conf_half)
                       else "approved_corrections"),
        partition_manifest={
            "schema": "source_components_v1",
            "calibration_unit": "source_component",
            "quantile_score_aggregation": "maximum_positive_nonconformity",
            "coverage_observation_scope": "one_audited_mention_per_source_component",
            "fit_component_ids": [cid for cid, _ in fit_components],
            "calibration_component_ids": [cid for cid, _ in calibration_components],
            "calibration_scored_component_ids": list(positive_counts),
            "calibration_component_positive_counts": positive_counts,
            "group_component_ids": group_component_ids,
            "calibration_units": len(all_scores),
            # Retained for readers of the historical metadata; these IDs and
            # row counts no longer determine independent conformal sample size.
            "fit_event_ids": sorted({e.event_id or e.correction_id or e.request_id or e.document_id for e in fit_half}),
            "calibration_event_ids": sorted({e.event_id or e.correction_id or e.request_id or e.document_id for e in conf_half}),
            "fit_rows": len(fit_half),
            "calibration_rows": len(conf_half),
            "calibration_positives": sum(positive_counts.values()),
            "independent_calibration_units": all(count == 1 for count in positive_counts.values()),
        },
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
    if correction.get("status") != "ACCEPTED":
        return []
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
    ref = correction.get("request_ref") or {}
    namespace = str(correction.get("tenant_id", "default")) + ":"
    def scoped(value):
        return namespace + str(value) if value else None
    # Legacy exports lacking IDs remain usable for extraction; hashing the
    # correction groups identical repeated submissions conservatively.
    correction_id = correction.get("correction_id") or hashlib.sha256(
        json.dumps(correction, sort_keys=True, default=str).encode()).hexdigest()
    out = []
    for m in members:
        group = calibration_group(set(m.get("generation_channels", [])), n_senses)
        out.append(TrainingExample(m["ranking_score"], group,
                                   int(m.get("entity_id") == gold),
                                   event_id=scoped(correction_id),
                                   document_id=scoped(ref.get("document_id")),
                                   request_id=scoped(ref.get("request_id")),
                                   mention_id=ref.get("mention_id"),
                                   correction_id=scoped(correction_id)))
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
