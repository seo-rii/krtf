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

import hashlib
import math
import random
import statistics
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
    """One (candidate, label) pair derived from an approved correction.

    ``group`` is the Mondrian *calibration* group (§25.4) — which conformal
    quantile applies to this row. ``groups`` is a different thing entirely:
    the identities this row shares with other rows (which document it came
    from, which entity it is about, which alias family produced it). Two rows
    sharing any of those are not independent draws, and a split that puts them
    on opposite sides is not a split. See :func:`split_examples`.
    """

    ranking_score: float
    group: str
    label: int  # 1 = this candidate was the corrected/true entity
    groups: dict[str, str] = field(default_factory=dict)


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


def platt_marginal(a: float, b: float, ranking_score: float) -> float:
    """The calibrated marginal — the one function, used at fit and inference.

    The conformal quantile is a threshold on ``1 - p``. Computing p at full
    precision while fitting and then clipping and rounding it at inference
    makes those two different thresholds: a score sitting on the boundary is
    inside the set on one side of the system and outside on the other. The
    clip and the round are part of the score function, not presentation, so
    they belong here where both callers get them.
    """
    p = 1.0 / (1.0 + math.exp(-(a * ranking_score + b)))
    return round(min(0.99, max(0.01, p)), 3)


def _conformal_quantile(nonconformity: list[float], alpha: float) -> float:
    """q̂ = ⌈(n+1)(1−α)⌉ / n quantile of the calibration scores (§25.2)."""
    s = sorted(nonconformity)
    n = len(s)
    k = math.ceil((n + 1) * (1 - alpha))
    if k > n:
        return 1.0  # not enough samples to bound below 1
    return s[k - 1]


# ---------------------------------------------------------------------------
# Grouped splitting (§25.2; review P0-3 "데이터 분할")
# ---------------------------------------------------------------------------

#: Dimensions along which two rows are *correlated*: sharing any one of them
#: means the rows are not independent draws, so they have to land in the same
#: fold. A split by row index leaves the same document, the same entity and
#: the same alias family with rows on both sides — which is exactly the leak
#: split conformal exists to rule out.
LINK_DIMS = ("document", "entity", "alias_family")

#: Dimensions that must NOT be used to link rows, even though the review lists
#: them alongside the others. Every row of a tenant shares its tenant id, so
#: linking on `tenant` collapses the whole tenant into one component and no
#: split is possible at all; a coarse time bucket behaves the same way. These
#: are held-out *axes* — fit on some tenants, evaluate on the others — which
#: is a different operation from clustering. :func:`holdout_by` does that one.
HOLDOUT_DIMS = ("tenant", "time_bucket")

#: The four sets the review asks for: ranker training, probability
#: calibration, conformal quantiles, and a locked set touched only at the end.
FOLDS = ("ranker", "platt", "conformal", "test")

DEFAULT_SHARES = {"ranker": 0.4, "platt": 0.2, "conformal": 0.2, "test": 0.2}


class _DisjointSet:
    def __init__(self, n: int):
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)


def cluster_components(examples: list[TrainingExample],
                       link_dims: tuple[str, ...] = LINK_DIMS) -> list[int]:
    """Row index -> component id, a component being rows transitively
    correlated with one another.

    Transitivity is the point. Row A and row B share a document, row B and row
    C share an entity, so A and C are correlated too although they have
    nothing directly in common. Union-find is what makes the split honest;
    checking pairs of rows is not enough.
    """
    ds = _DisjointSet(len(examples))
    first_seen: dict[tuple[str, str], int] = {}
    for i, e in enumerate(examples):
        for dim in link_dims:
            value = (e.groups or {}).get(dim)
            if value is None:
                continue
            ds.union(i, first_seen.setdefault((dim, value), i))
    return [ds.find(i) for i in range(len(examples))]


@dataclass
class SplitReport:
    """Where every row went, and whether the split means anything."""

    folds: dict[str, list[int]]
    grouped: bool          # were link groups actually supplied?
    n_rows: int
    n_components: int
    largest_component_share: float
    dims_present: tuple[str, ...]
    # components per fold. A conformal fold of 600 rows drawn from one cluster
    # is one independent observation, not 600, and the quantile it produces is
    # correspondingly weak — a row count alone cannot show that.
    fold_components: dict[str, int] = field(default_factory=dict)

    def rows(self, examples: list[TrainingExample],
             fold: str) -> list[TrainingExample]:
        return [examples[i] for i in self.folds[fold]]

    def to_dict(self) -> dict:
        return {
            "grouped": self.grouped,
            "n_rows": self.n_rows,
            "n_components": self.n_components,
            "largest_component_share": round(self.largest_component_share, 4),
            "dims_present": list(self.dims_present),
            "fold_sizes": {f: len(ix) for f, ix in self.folds.items()},
            "fold_components": dict(self.fold_components),
        }


def _order_key(rows: list[int], comp_id: int) -> tuple:
    """Largest component first, ties broken by a hash so fold membership does
    not track the order the caller happened to build the list in — data
    arriving sorted by document or by date would otherwise drop whole date
    ranges into one fold."""
    digest = hashlib.blake2b(str(comp_id).encode(), digest_size=8).hexdigest()
    return (-len(rows), digest)


def _assign(components: dict[int, list[int]], shares: dict[str, float],
            n_rows: int) -> dict[str, list[int]]:
    """Greedy: each whole component goes to whichever fold is furthest below
    its target, so no component ever straddles a fold boundary."""
    folds: dict[str, list[int]] = {name: [] for name in shares}
    for comp_id, rows in sorted(components.items(),
                                key=lambda kv: _order_key(kv[1], kv[0])):
        name = max(shares,
                   key=lambda f: (shares[f] * n_rows - len(folds[f]), f))
        folds[name].extend(rows)
    for rows in folds.values():
        rows.sort()
    return folds


def split_examples(examples: list[TrainingExample],
                   shares: dict[str, float] | None = None,
                   link_dims: tuple[str, ...] = LINK_DIMS) -> SplitReport:
    """Split into folds without ever cutting a correlated group in half.

    Rows carrying no ``groups`` are each their own component, which reproduces
    a row-level split. That is *reported* (``grouped=False``) rather than
    presented as a group split: the caller supplied nothing to group by, so
    nothing was ruled out.
    """
    shares = dict(shares or DEFAULT_SHARES)
    comp_of = cluster_components(examples, link_dims)
    components: dict[int, list[int]] = {}
    for row, comp in enumerate(comp_of):
        components.setdefault(comp, []).append(row)
    present = tuple(d for d in link_dims
                    if any((e.groups or {}).get(d) is not None
                           for e in examples))
    n = len(examples)
    largest = max((len(r) for r in components.values()), default=0)
    folds = _assign(components, shares, n)
    return SplitReport(
        folds=folds,
        grouped=bool(present),
        n_rows=n,
        n_components=len(components),
        largest_component_share=(largest / n) if n else 0.0,
        dims_present=present,
        fold_components={f: len({comp_of[i] for i in rows})
                         for f, rows in folds.items()},
    )


def holdout_by(examples: list[TrainingExample], dim: str,
               holdout_values: set[str]) -> tuple[list[TrainingExample],
                                                  list[TrainingExample]]:
    """(fit, holdout) split along whole tenants or time buckets.

    Deliberately separate from :func:`split_examples`. Group splitting answers
    "did a correlated row leak across the split"; this answers "does the fit
    transfer to a tenant, or a period, it never saw" — a generalisation claim
    the other split cannot make.
    """
    fit, held = [], []
    for e in examples:
        (held if (e.groups or {}).get(dim) in holdout_values else fit).append(e)
    return fit, held


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
    # False when the fit had to reuse rows across the Platt/conformal
    # split. The sets are then not disjoint, so `set_confidence` is a
    # nominal level and not a finite-sample guarantee — a consumer has
    # to be able to tell the two apart.
    split_disjoint: bool = True
    # "grouped": correlated rows (same document/entity/alias family) were kept
    # on one side of the split. "row": the split was by row index, which rules
    # out nothing — the same document can sit on both sides, though nothing
    # said it does. "row_fallback": the rows were known to be correlated, the
    # groups were too few to split, and they were split by row anyway — the
    # one case where a leak is not merely unruled-out but demonstrated.
    # Disjointness and groupedness are separate claims and a consumer needs
    # both: a row split can be perfectly disjoint and still leak.
    split_basis: str = "row"
    split_report: dict | None = None

    @property
    def set_confidence(self) -> float:
        return round(1.0 - self.alpha, 4)

    def calibrate_marginal(self, ranking_score: float) -> float:
        return platt_marginal(self.platt_a, self.platt_b, ranking_score)

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
            "split_disjoint": self.split_disjoint,
            "split_basis": self.split_basis,
            "split_report": self.split_report,
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
            split_disjoint=d.get("split_disjoint", True),
            # a calibrator persisted before grouping existed was fit on a row
            # split; reading it back as "grouped" would invent a guarantee
            split_basis=d.get("split_basis", "row"),
            split_report=d.get("split_report"),
        )


def fit_calibrator_from_folds(
    platt_rows: list[TrainingExample],
    conformal_rows: list[TrainingExample],
    alpha: float = 0.05,
    n_min: int = 500,
    split_basis: str = "row",
    split_report: dict | None = None,
) -> TunedCalibrator:
    """Fit from two folds the caller has already separated.

    The split is the caller's, and so is responsibility for it: this function
    reports what it was told (``split_basis``) and whether it had to violate
    it (``split_disjoint``), and never re-splits behind the caller's back.
    """
    everything = list(platt_rows) + list(conformal_rows)
    if len(everything) < 10 or not any(e.label for e in everything):
        raise ValueError(
            "insufficient calibration data: need >=10 examples with >=1 positive"
        )
    split_disjoint = True
    fit_half = list(platt_rows)
    if not any(e.label for e in fit_half) or not any(
            e.label for e in conformal_rows):
        # tiny/degenerate label distribution: fall back to the full set for
        # Platt. That is a real loss of the guarantee rather than a detail —
        # the probability map has now seen the conformal rows — so it is
        # recorded instead of described in a comment.
        fit_half = everything
        split_disjoint = False
    a, b = _fit_platt([e.ranking_score for e in fit_half],
                      [e.label for e in fit_half])

    def marginal(score: float) -> float:
        return platt_marginal(a, b, score)

    positives = [e for e in conformal_rows if e.label == 1]
    if not positives:
        # no positive on the conformal side: the quantiles then come from rows
        # the Platt map was fit on, voiding disjointness the other way round
        positives = [e for e in everything if e.label == 1]
        split_disjoint = False
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
        split_disjoint=split_disjoint,
        split_basis=split_basis,
        split_report=split_report,
    )


def _fit_viable(platt_rows: list[TrainingExample],
                conformal_rows: list[TrainingExample]) -> str | None:
    """Why these two folds cannot support a fit, or None if they can."""
    if len(platt_rows) + len(conformal_rows) < 10:
        return "fewer than 10 rows in the calibration folds"
    if not any(e.label for e in platt_rows):
        return "no positive row in the platt fold"
    if not any(e.label for e in conformal_rows):
        return "no positive row in the conformal fold"
    return None


@dataclass
class FittedSplit:
    """A calibrator, the split behind it, and the rows nothing has touched."""

    calibrator: TunedCalibrator
    split: SplitReport | None
    locked: list[TrainingExample]


def fit_with_folds(examples: list[TrainingExample], alpha: float = 0.05,
                   n_min: int = 500,
                   shares: dict[str, float] | None = None) -> FittedSplit:
    """Split as well as the data allows, fit, and say which it was.

    Group splitting can fail on real data, and the failure is not rare: thirty
    corrections about a single alias are one correlated cluster, and a cluster
    cannot be split. When that happens the choice is between refusing to fit
    at all and fitting on a split that is known to leak. Refusing would take a
    working adaptation path away over a guarantee it never actually had, so
    this fits — and records ``split_basis="row_fallback"``, which every
    prediction set then reports as ``coverage_valid=False``. The fit stays
    useful; the guarantee stops being claimed.
    """
    shares = dict(shares or {"platt": 0.5, "conformal": 0.5})
    if not any(e.groups for e in examples):
        # Nothing to group by: the row split is all there is, and it is not
        # evidence of a leak — just an absence of evidence either way. It uses
        # every row, including the ones a fold named "test" would hold, so
        # nothing is locked and none is claimed to be: a held-out coverage
        # measured on rows the fit saw is the number this whole change exists
        # to stop reporting.
        return FittedSplit(
            calibrator=fit_calibrator_from_folds(
                examples[0::2], examples[1::2], alpha=alpha, n_min=n_min,
                split_basis="row"),
            split=None,
            locked=[],
        )
    report = split_examples(examples, shares=shares)
    platt = report.rows(examples, "platt")
    conformal = report.rows(examples, "conformal")
    reason = _fit_viable(platt, conformal)
    if reason is None:
        return FittedSplit(
            calibrator=fit_calibrator_from_folds(
                platt, conformal, alpha=alpha, n_min=n_min,
                # rows can carry only tenant or time, which are holdout axes
                # and link nothing: the split then separates rows without
                # separating groups, and calling it "grouped" would claim a
                # guarantee the identities never supported
                split_basis="grouped" if report.grouped else "row",
                split_report=report.to_dict()),
            split=report,
            locked=(report.rows(examples, "test")
                    if "test" in shares and report.grouped else []),
        )
    degraded = report.to_dict()
    degraded["degraded_to"] = "row"
    degraded["reason"] = reason
    return FittedSplit(
        calibrator=fit_calibrator_from_folds(
            examples[0::2], examples[1::2], alpha=alpha, n_min=n_min,
            split_basis="row_fallback", split_report=degraded),
        split=report,
        locked=[],   # a fallback fit used every row; nothing is locked
    )


def fit_calibrator(examples: list[TrainingExample], alpha: float = 0.05,
                   n_min: int = 500) -> TunedCalibrator:
    """Fit marginal calibration + group-conditional conformal quantiles.

    ``examples`` must come only from ACCEPTED corrections (INV-018 — the
    correction store enforces this on export).

    Split-conformal validity requires that the data fitting the probability
    map (Platt) and the data supplying the conformal quantiles are DISJOINT —
    reusing one set for both voids the finite-sample coverage guarantee. It
    also requires the two sides to be *independent*, which disjointness alone
    does not give you: the same document, entity or alias family on both sides
    leaks even though no row is shared.

    So when the examples carry ``groups``, the split is by connected component
    over those identities (:func:`split_examples`). When they do not, it falls
    back to row index — even rows fit Platt, odd rows supply the quantiles.
    When they do but the groups are too coarse to split, it falls back too and
    says so. Nothing here is asserted; all three outcomes are reported through
    ``split_basis``.

    A degenerate label distribution forces rows to be reused across the split.
    That is not a detail to absorb silently either: the result carries
    ``split_disjoint=False``, and every prediction set built from it reports
    ``coverage_valid=False``, so a nominal confidence level is never presented
    as a finite-sample guarantee.

    The four-way split the review asks for (ranker / probability calibration /
    conformal quantile / locked evaluation) is dataset preparation rather than
    a fitting concern: call :func:`fit_with_folds` with four shares, so the
    locked fold is never touched by a fit.
    """
    if len(examples) < 10 or not any(e.label for e in examples):
        raise ValueError(
            "insufficient calibration data: need >=10 examples with >=1 positive"
        )
    return fit_with_folds(examples, alpha=alpha, n_min=n_min).calibrator


# ---------------------------------------------------------------------------
# Training-pair extraction and online coverage (§25.5, REQ-CAL-004)
# ---------------------------------------------------------------------------

_GOLD_BEARING = {"WRONG_ENTITY", "SHOULD_BE_RESOLVED"}


def correction_groups(correction: dict) -> dict[str, str]:
    """The identities a correction shares with other corrections (§25.2).

    Every row derived from one correction is correlated with every other row
    derived from it — same mention, same context, same gold — so they all
    carry the same identities and land in the same fold. Beyond that:

    * ``document`` — the request the mention came from. One request is one
      document, so two mentions of the same document stay together.
    * ``entity`` — the corrected (gold) entity. The same entity recurring
      across documents is the correlation that most directly inflates
      measured coverage: get it right once and you get it right everywhere.
    * ``alias_family`` — the normalised surface. Morphological variants of
      one alias are near-duplicates as far as the ranker is concerned.
    * ``tenant`` / ``time_bucket`` — recorded but NOT linked (see
      :data:`HOLDOUT_DIMS`); they are for :func:`holdout_by`.
    """
    ref = correction.get("request_ref") or {}
    state = correction.get("mention_state") or {}
    groups: dict[str, str] = {}
    if ref.get("request_id"):
        groups["document"] = str(ref["request_id"])
    gold = (correction.get("corrected") or {}).get("entity_id")
    if gold:
        groups["entity"] = str(gold)
    family = state.get("normalized_surface") or state.get("surface")
    if family:
        groups["alias_family"] = str(family)
    if correction.get("tenant_id"):
        groups["tenant"] = str(correction["tenant_id"])
    bucket = (correction.get("review") or {}).get("decided_at") or \
        correction.get("created_at")
    if bucket:
        groups["time_bucket"] = str(bucket)[:10]  # day granularity
    return groups


def derive_training_examples(correction: dict) -> list[TrainingExample]:
    """Turn one ACCEPTED correction (with its ``mention_state``) into pairs.

    ``mention_state`` is the mention object from the original response
    (§30.1 — span/state data, no raw text). Each ENTITY member of its
    prediction set becomes one example labeled against the corrected entity.

    Every row carries the correction's group identities, so the rows of one
    correction cannot be split across folds. That matters more than it looks:
    verifier weighting (REQ-COR-003) is implemented by *repeating* rows, and
    under a row-index split the identical copies landed on both sides — the
    same row fitting the probability map and supplying the quantile that is
    supposed to test it.
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
    groups = correction_groups(correction)
    out = []
    for m in members:
        group = calibration_group(set(m.get("generation_channels", [])), n_senses)
        out.append(TrainingExample(m["ranking_score"], group,
                                   int(m.get("entity_id") == gold),
                                   groups=dict(groups)))
    return out


def _percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile; no interpolation, so p95 of 20 observations is
    an observation and not a number that never occurred."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(1, math.ceil(q * len(ordered)))
    return ordered[min(k, len(ordered)) - 1]


def _cluster_bootstrap_ci(units: list[tuple[str, int]], n_boot: int = 1000,
                          seed: int = 20260905) -> tuple[float, float] | None:
    """Percentile CI resampling whole clusters, not rows.

    Rows from one document are not independent, so a row-level interval is
    narrower than the data supports — it treats five mentions of one document
    as five observations. Resampling documents keeps the interval honest about
    how many independent things were actually seen.
    """
    by_cluster: dict[str, list[int]] = {}
    for key, covered in units:
        by_cluster.setdefault(key, []).append(covered)
    keys = list(by_cluster)
    if len(keys) < 2:
        return None  # one cluster cannot bound anything
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_boot):
        flat: list[int] = []
        for _ in keys:
            flat.extend(by_cluster[keys[rng.randrange(len(keys))]])
        if flat:
            means.append(sum(flat) / len(flat))
    if not means:
        return None
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[min(len(means) - 1, int(0.975 * len(means)))]
    return lo, hi


def _alias_type(member: dict) -> str:
    """Coarse alias type from the channels that produced the gold member."""
    chs = set(member.get("generation_channels", []))
    if chs & {"exact", "normalized"}:
        return "exact"
    if chs & {"jamo", "keyboard"}:
        return "fuzzy"
    if "abbrev" in chs:
        return "abbrev"
    if "dense" in chs:
        return "dense"
    return "unknown"


def _frequency_bucket(n: int) -> str:
    if n <= 1:
        return "1"
    if n <= 5:
        return "2-5"
    return "6+"


def empirical_coverage(corrections: list[dict], n_boot: int = 1000) -> dict:
    """Online empirical coverage from ACCEPTED labeled corrections (§25.5).
    Never claimed without a correction path (REQ-CAL-004).

    Marginal coverage alone hides the failure that matters: a set that covers
    90% overall can be covering 99% of the easy exact-match slice and 60% of
    the rare entities, and the average reads fine. So this reports coverage
    conditioned on the calibration group, on how often the entity was seen,
    and on alias type — and a cluster bootstrap interval, because mentions
    from one document are not independent observations.

    KB_MISSING is evaluated as a label rather than skipped: a correction
    saying "this should have been KB_MISSING" is covered when the prediction
    set contained a KB_MISSING member, exactly as an entity label is covered
    when the set contained that entity.
    """
    labeled: list[dict] = []
    entity_counts: dict[str, int] = {}
    for c in corrections:
        ctype = c.get("correction_type")
        state = c.get("mention_state") or {}
        if not state or ctype not in _GOLD_BEARING | {"SHOULD_BE_KB_MISSING"}:
            continue
        members = state.get("prediction_set", {}).get("members", [])
        if ctype == "SHOULD_BE_KB_MISSING":
            gold = None
            covered = any(m.get("kind") == "KB_MISSING" for m in members)
            gold_member: dict = {}
        else:
            gold = (c.get("corrected") or {}).get("entity_id")
            if gold is None:
                continue
            entity_members = [m for m in members
                              if m.get("kind", "ENTITY") == "ENTITY"]
            gold_member = next(
                (m for m in entity_members if m.get("entity_id") == gold), {})
            covered = bool(gold_member)
            entity_counts[gold] = entity_counts.get(gold, 0) + 1
        cluster = str((c.get("request_ref") or {}).get("request_id")
                      or c.get("correction_id") or id(c))
        labeled.append({
            "covered": int(covered), "set_size": len(members),
            "cluster": cluster, "gold": gold,
            "group": calibration_group(
                set(gold_member.get("generation_channels", [])), len(members)),
            "alias_type": _alias_type(gold_member),
        })
    if not labeled:
        return {"labeled": 0, "coverage": None, "mean_set_size": None,
                "median_set_size": None, "p95_set_size": None,
                "ci95": None, "n_clusters": 0, "conditional": {}}

    sizes = [r["set_size"] for r in labeled]
    total = len(labeled)
    covered = sum(r["covered"] for r in labeled)

    def slice_coverage(key: str) -> dict:
        buckets: dict[str, list[int]] = {}
        for r in labeled:
            buckets.setdefault(str(r[key]), []).append(r["covered"])
        return {k: {"n": len(v), "coverage": round(sum(v) / len(v), 4)}
                for k, v in sorted(buckets.items())}

    freq: dict[str, list[int]] = {}
    for r in labeled:
        bucket = _frequency_bucket(entity_counts.get(r["gold"], 0))
        freq.setdefault(bucket, []).append(r["covered"])
    ci = _cluster_bootstrap_ci([(r["cluster"], r["covered"]) for r in labeled],
                               n_boot=n_boot)
    return {
        "labeled": total,
        "coverage": round(covered / total, 4),
        "mean_set_size": round(sum(sizes) / total, 2),
        "median_set_size": round(statistics.median(sizes), 2),
        "p95_set_size": _percentile([float(x) for x in sizes], 0.95),
        "ci95": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
        "n_clusters": len({r["cluster"] for r in labeled}),
        "conditional": {
            "group": slice_coverage("group"),
            "alias_type": slice_coverage("alias_type"),
            "entity_frequency": {
                k: {"n": len(v), "coverage": round(sum(v) / len(v), 4)}
                for k, v in sorted(freq.items())},
        },
    }
