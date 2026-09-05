"""What a coverage number has to say before it means anything.

A single marginal coverage figure over correlated rows is the easiest way to
report a system as better calibrated than it is. Three things fix that, and
each is pinned here: conditioning (which slice is failing), cluster resampling
(how many independent observations there really were), and saying out loud
which members of a set the conformal rule actually admitted.
"""

import math

from ktrf.calibration import (
    TunedCalibrator,
    empirical_coverage,
    fit_calibrator,
    TrainingExample,
)
from ktrf.glossary import load_glossary
from ktrf.snapshot import compile_snapshot
from ktrf.resolver import resolve

GLOSSARY = "examples/realorg_glossary.yaml"


def _correction(request_id, gold, members, ctype="WRONG_ENTITY"):
    return {
        "correction_id": f"c-{request_id}-{gold}",
        "correction_type": ctype,
        "corrected": {"entity_id": gold},
        "request_ref": {"request_id": request_id},
        "mention_state": {"prediction_set": {"members": members}},
    }


def _entity(eid, channels=("exact",)):
    return {"kind": "ENTITY", "entity_id": eid,
            "generation_channels": list(channels)}


# ------------------------------------------------------ conditional coverage

def test_a_failing_slice_is_visible_even_when_the_average_looks_fine():
    corrections = []
    # the easy slice: exact matches, always covered
    for i in range(90):
        corrections.append(_correction(
            f"easy-{i}", "E_G", [_entity("E_G", ["exact"])]))
    # the hard slice: fuzzy matches, never covered
    for i in range(10):
        corrections.append(_correction(
            f"hard-{i}", "E_H", [_entity("E_OTHER", ["jamo"])]))
    r = empirical_coverage(corrections, n_boot=200)
    assert r["coverage"] == 0.9              # the average says target met
    by_alias = r["conditional"]["alias_type"]
    assert by_alias["exact"]["coverage"] == 1.0
    # the miss has no gold member, so its alias type is unknown rather than
    # invented — but it is still a slice of its own, not folded into "exact"
    assert set(by_alias) == {"exact", "unknown"}
    assert by_alias["unknown"]["coverage"] == 0.0


def test_entity_frequency_is_a_reported_slice():
    corrections = [_correction(f"d{i}", "E_COMMON", [_entity("E_COMMON")])
                   for i in range(8)]
    corrections.append(_correction("d-rare", "E_RARE", [_entity("E_OTHER")]))
    r = empirical_coverage(corrections, n_boot=200)
    freq = r["conditional"]["entity_frequency"]
    assert freq["6+"]["coverage"] == 1.0
    assert freq["1"]["coverage"] == 0.0


# --------------------------------------------------------- cluster bootstrap

def _row_level_halfwidth(p, n):
    return 1.96 * math.sqrt(p * (1 - p) / n)


def test_clustered_rows_widen_the_interval_they_would_otherwise_shrink():
    # Ten documents, ten mentions each. Whole documents succeed or fail
    # together, so there are ten independent observations, not a hundred.
    corrections = []
    for d in range(10):
        covered = d < 7
        for m in range(10):
            corrections.append(_correction(
                f"doc{d}", "E_G",
                [_entity("E_G" if covered else "E_OTHER")]))
            corrections[-1]["correction_id"] = f"c{d}-{m}"
    r = empirical_coverage(corrections, n_boot=500)
    assert r["labeled"] == 100
    assert r["n_clusters"] == 10
    lo, hi = r["ci95"]
    cluster_halfwidth = (hi - lo) / 2
    assert cluster_halfwidth > _row_level_halfwidth(0.7, 100), (
        "a row-level interval treats ten documents as a hundred draws")


def test_one_cluster_cannot_bound_anything():
    corrections = [_correction("only-doc", "E_G", [_entity("E_G")])
                   for _ in range(20)]
    for i, c in enumerate(corrections):
        c["correction_id"] = f"c{i}"
    assert empirical_coverage(corrections, n_boot=100)["ci95"] is None


# --------------------------------------------------------------- set sizes

def test_set_size_spread_is_reported_not_just_the_mean():
    corrections = [_correction(f"d{i}", "E_G", [_entity("E_G")])
                   for i in range(18)]
    for tag in ("wide-a", "wide-b"):
        corrections.append(_correction(
            tag, "E_G", [_entity(f"E{i}") for i in range(20)]))
    r = empirical_coverage(corrections, n_boot=100)
    # the mean sits at 2.9 and reads as a nearly-singleton set; the median
    # says half the sets are singletons and the p95 says the tail is at 20
    assert r["mean_set_size"] == 2.9
    assert r["median_set_size"] == 1.0
    assert r["p95_set_size"] == 20.0


# ------------------------------------------------------- KB_MISSING as label

def test_kb_missing_is_evaluated_rather_than_skipped():
    hit = _correction("d1", None, [{"kind": "KB_MISSING"}],
                      ctype="SHOULD_BE_KB_MISSING")
    miss = _correction("d2", None, [_entity("E_A")],
                       ctype="SHOULD_BE_KB_MISSING")
    r = empirical_coverage([hit, miss], n_boot=100)
    assert r["labeled"] == 2
    assert r["coverage"] == 0.5


# --------------------------------------------------- what the response says

def _snapshot_with(calibrator):
    # seal=False: the calibrator is part of the sealed identity, and this
    # fixture is deliberately building an odd one
    snap = compile_snapshot(load_glossary(GLOSSARY), seal=False)
    snap.calibrator = calibrator
    return snap


def test_a_response_says_which_kind_of_split_backs_its_confidence():
    plain = [TrainingExample(0.9 - 0.01 * i, "exact|multi", int(i % 4 in (0, 1)))
             for i in range(40)]
    snap = _snapshot_with(fit_calibrator(plain, alpha=0.1, n_min=1))
    resp = resolve(snap, "금융감독원이 조사했다", mode="commit")
    sets = [m["prediction_set"] for m in resp["mentions"]
            if "prediction_set" in m]
    assert sets, "no prediction set to inspect"
    assert all(s["coverage_basis"] == "row" for s in sets)


def test_a_member_the_quantile_rejected_is_marked_as_forced():
    # a quantile of 0 admits nothing, so whatever appears in the set is there
    # by the usability contract rather than the conformal one
    strict = TunedCalibrator(
        platt_a=1.0, platt_b=0.0, alpha=0.1,
        group_quantiles={}, global_quantile=0.0, fallback_quantile=0.0,
        group_counts={}, n_min=1)
    resp = resolve(_snapshot_with(strict), "금융감독원이 조사했다", mode="commit")
    forced = [m["prediction_set"].get("forced_top") for m in resp["mentions"]
              if "prediction_set" in m]
    assert forced and all(f is True for f in forced)


# ------------------------------------------- two contracts, told apart

def test_strict_mode_returns_the_set_the_quantile_actually_drew():
    # a quantile of 0 admits nothing. The default contract hands back the top
    # candidate anyway so the caller has something to show; the strict one
    # returns the empty set, which is the honest conformal answer.
    strict = TunedCalibrator(
        platt_a=1.0, platt_b=0.0, alpha=0.1,
        group_quantiles={}, global_quantile=0.0, fallback_quantile=0.0,
        group_counts={}, n_min=1)
    snap = _snapshot_with(strict)
    lenient = resolve(snap, "금융감독원이 조사했다", mode="commit")
    exact = resolve(snap, "금융감독원이 조사했다", mode="commit",
                    options={"strict_conformal_set": True})
    lenient_sets = [m["prediction_set"] for m in lenient["mentions"]
                    if "prediction_set" in m]
    exact_sets = [m["prediction_set"] for m in exact["mentions"]
                  if "prediction_set" in m]
    assert lenient_sets and exact_sets
    assert all(s.get("forced_top") for s in lenient_sets)
    assert all(s.get("forced_top") is None for s in exact_sets)
    assert all(s.get("strict_conformal") for s in exact_sets)
    # the empty set is a real answer: no candidate cleared the bar
    assert all(len(s["members"]) < len(l["members"])
               for s, l in zip(exact_sets, lenient_sets))


def test_a_mention_with_an_empty_strict_set_is_not_reported_as_resolved():
    strict = TunedCalibrator(
        platt_a=1.0, platt_b=0.0, alpha=0.1,
        group_quantiles={}, global_quantile=0.0, fallback_quantile=0.0,
        group_counts={}, n_min=1)
    resp = resolve(_snapshot_with(strict), "금융감독원이 조사했다",
                   mode="commit", options={"strict_conformal_set": True})
    for m in resp["mentions"]:
        if m.get("prediction_set", {}).get("members") == []:
            assert m["link_decision"] != "RESOLVED"


def test_the_default_contract_is_unchanged():
    snap = compile_snapshot(load_glossary(GLOSSARY))
    a = resolve(snap, "금융감독원이 조사했다", mode="commit")
    b = resolve(snap, "금융감독원이 조사했다", mode="commit",
                options={"strict_conformal_set": False})
    assert a["mentions"] == b["mentions"]
