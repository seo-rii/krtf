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


# ---------------------------------------------------------------------------
# Evaluation-construction defects found while measuring M1
# ---------------------------------------------------------------------------


def test_fake_glossary_absence_is_checked_in_the_matcher_space():
    """A case-sensitive absence test scores a construction error as an FP.

    The resolver matches through a case-folding normalized channel, so a
    surface like `gb` is reachable in a corpus that only ever writes `GB`.
    Keeping it makes the resolver commit on it, and the fake-glossary suite
    reports a product false positive that the product did not cause.
    """
    from eval.synthetic import absent_bindings_only, build_synthetic_glossary

    g_dict, _ = build_synthetic_glossary(400, seed=5)
    acronym = next(b["surface"] for b in g_dict["alias_bindings"]
                   if b["surface"].isascii() and b["surface"].isalpha())

    # the corpus writes it in the *other* case only
    kept, removed = absent_bindings_only(
        dict(g_dict), [f"오늘 {acronym.lower()} 단위로 저장했다."])
    assert removed >= 1
    assert acronym not in {b["surface"] for b in kept["alias_bindings"]}


def test_absence_filter_keeps_genuinely_absent_surfaces():
    from eval.synthetic import absent_bindings_only, build_synthetic_glossary

    g_dict, _ = build_synthetic_glossary(50, seed=7)
    before = len(g_dict["alias_bindings"])
    kept, removed = absent_bindings_only(dict(g_dict), ["아무 관련 없는 문장."])
    assert removed == 0
    assert len(kept["alias_bindings"]) == before


def test_coverage_verdict_is_three_valued():
    """A point estimate inside the CI is not a pass (VARIANTS_PLAN M0 item 4)."""
    from eval.run_benchmarks import run_calibration_holdout

    res = run_calibration_holdout()["results"]
    for key, v in res.items():
        assert v["verdict"] in ("PASS", "FAIL", "INSUFFICIENT_DATA")
        lo, hi = v["ci95"]
        assert lo <= v["pooled_coverage"] <= hi
        if v["verdict"] == "PASS":
            assert lo >= v["target"]
        elif v["verdict"] == "FAIL":
            assert hi < v["target"]
        else:  # the sample cannot decide, and must not be reported as a pass
            assert lo < v["target"] <= hi
        # pooled over trials, not a single draw that seed noise can swing
        assert v["trials"] >= 4 and v["n_holdout_pooled"] > 1000
