"""Predeclared fixed-risk threshold validation on independent audit events.

Each group must contain at most one independently sampled event per document.
Do not pass correlated mentions as independent binomial trials. Corrections or
resolver-selected samples are not representative audit samples.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AuditEvent:
    document_id: str
    event_id: str
    group: str  # predeclared channel/ambiguity/domain stratum
    score: float
    incorrect: bool


def binomial_error_ucb(errors: int, commits: int, alpha: float = .05) -> float:
    """One-sided exact Clopper-Pearson bound; no asymptotic approximation."""
    if not (0 <= errors <= commits and 0 < alpha < 1):
        raise ValueError("invalid binomial counts or alpha")
    if commits == 0 or errors == commits:
        return 1.0
    if errors == 0:
        return -math.expm1(math.log(alpha) / commits)
    def cdf(p):
        terms = [math.lgamma(commits + 1) - math.lgamma(k + 1)
                 - math.lgamma(commits - k + 1) + k * math.log(p)
                 + (commits - k) * math.log1p(-p) for k in range(errors + 1)]
        largest = max(terms)
        return math.exp(largest) * sum(math.exp(t - largest) for t in terms)
    low, high = errors / commits, 1.0
    for _ in range(70):
        middle = (low + high) / 2
        if middle == 1.0:
            break
        if cdf(middle) > alpha:
            low = middle
        else:
            high = middle
    return high


def validate_thresholds(tune: list[AuditEvent], test: list[AuditEvent], *,
                        thresholds: list[float], groups: list[str], epsilon: float,
                        alpha: float = .05, minimum_commits: int = 1) -> dict:
    """Tune with simultaneous bounds; validate selected rules on sealed test.

    Returned PASS controls the audited group's error conditional on committing,
    assuming exchangeable independent audit events. It is not E2E coverage.
    Groups and thresholds must be fixed before looking at either partition.
    """
    if not (thresholds and groups and 0 < epsilon < 1 and 0 < alpha < 1 and minimum_commits > 0):
        raise ValueError("invalid predeclared protocol")
    if len(set(thresholds)) != len(thresholds) or len(set(groups)) != len(groups):
        raise ValueError("duplicate hypothesis")
    if any(not math.isfinite(t) or not 0 <= t <= 1 for t in thresholds):
        raise ValueError("threshold must be in [0, 1]")
    for partition in (tune, test):
        seen_events, seen_documents = set(), set()
        for event in partition:
            if event.group not in groups or not math.isfinite(event.score) or not 0 <= event.score <= 1:
                raise ValueError("event outside predeclared protocol")
            if not event.document_id or not event.event_id or not isinstance(event.incorrect, bool):
                raise ValueError("identified audit event and binary correctness required")
            if event.event_id in seen_events or (event.group, event.document_id) in seen_documents:
                raise ValueError("correlated/duplicate audit events require document-cluster inference")
            seen_events.add(event.event_id)
            seen_documents.add((event.group, event.document_id))
    if {e.document_id for e in tune} & {e.document_id for e in test} or {e.event_id for e in tune} & {e.event_id for e in test}:
        raise ValueError("tuning and final validation must be document-disjoint")
    # Split the family-wise budget between independent stages AND tails:
    # PASS uses upper bounds and FAIL uses lower bounds. Both reported
    # decisions must fit inside the declared simultaneous error budget.
    tune_alpha = alpha / (4 * len(groups) * len(thresholds))
    test_alpha = alpha / (4 * len(groups))
    result = {"conditioning": "error_given_commit", "risk_unit": "independent_document_audit_event",
              "epsilon": epsilon, "familywise_alpha": alpha,
              "tune_alpha_per_hypothesis": tune_alpha, "test_alpha_per_group": test_alpha,
              "thresholds": thresholds, "groups": {}}
    def measure(events, threshold, per_alpha):
        selected = [e for e in events if e.score >= threshold]
        errors = sum(e.incorrect for e in selected)
        return {"audit_events": len(events), "commits": len(selected), "errors": errors,
                "commit_rate": len(selected) / len(events) if events else None,
                "error_ucb": binomial_error_ucb(errors, len(selected), per_alpha),
                "error_lcb": 1 - binomial_error_ucb(len(selected) - errors, len(selected), per_alpha)}
    for group in groups:
        tuning = [e for e in tune if e.group == group]
        validation = [e for e in test if e.group == group]
        candidates = [(t, measure(tuning, t, tune_alpha)) for t in thresholds]
        eligible = [(t, m) for t, m in candidates if m["commits"] >= minimum_commits and m["error_ucb"] <= epsilon]
        if not eligible:
            result["groups"][group] = {"status": "FAIL" if all(m["commits"] >= minimum_commits and m["error_lcb"] > epsilon for _, m in candidates) else "INSUFFICIENT_DATA", "selected_threshold": None,
                                       "tuning": [{"threshold": t, **m} for t, m in candidates]}
            continue
        threshold, fit = max(eligible, key=lambda pair: (pair[1]["commits"], pair[0]))
        final = measure(validation, threshold, test_alpha)
        if final["commits"] < minimum_commits:
            status = "INSUFFICIENT_DATA"
        elif final["error_ucb"] <= epsilon:
            status = "PASS"
        elif final["error_lcb"] > epsilon:
            status = "FAIL"
        else:
            status = "INSUFFICIENT_DATA"
        result["groups"][group] = {"status": status, "selected_threshold": threshold,
                                   "tuning_selected": fit, "sealed_test": final}
    return result
