"""Evaluation metric contract tests (spec §43). REQ-EVAL-001/002, REQ-LVL-003."""

import pytest

from eval.metrics import EvalReport, wilson_interval


def test_metrics_require_conditioning():
    # REQ-EVAL-001: unconditioned metric reporting is forbidden
    r = EvalReport()
    with pytest.raises(ValueError):
        r.add_metric("recall", "overall", 9, 10)
    m = r.add_metric("recall", "E2E", 9, 10)
    assert m.conditioning == "E2E"
    assert m.to_dict()["conditioning"] == "E2E"


def test_conformance_and_coverage_not_merged():
    # REQ-LVL-003/§3.5: conformance is a failure count, never a coverage %
    r = EvalReport()
    with pytest.raises(ValueError):
        r.add_metric("conformance_rate", "E2E", 100, 100)
    r.set_conformance(total=100, failed=0)
    d = r.to_dict()
    assert d["conformance"]["failure_count"] == 0
    assert all("conformance" not in m["name"] for m in d["metrics"])


def test_wilson_interval():
    # REQ-EVAL-002: CIs accompany point estimates
    lo, hi = wilson_interval(95, 100)
    assert lo < 0.95 < hi
    assert 0.88 < lo < 0.92
    assert wilson_interval(0, 0) == (0.0, 1.0)
    lo, hi = wilson_interval(10, 10)
    assert hi == 1.0 and lo < 1.0


def test_report_includes_ci():
    r = EvalReport()
    m = r.add_metric("recall", "E2E", 99, 100)
    d = m.to_dict()
    assert "ci95" in d and d["ci95"][0] < d["value"] <= d["ci95"][1]
