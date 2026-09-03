"""A conformal guarantee that quietly stops holding (§25.2, REQ-CAL-003).

`fit_calibrator` splits examples so the Platt map and the conformal
quantiles come from disjoint rows — but both fallbacks for a degenerate
label distribution put the rows back together, and the calibrator went on
reporting `set_confidence = 1 - alpha` as though nothing had changed.
"""

import pytest

from ktrf.calibration import TrainingExample, TunedCalibrator, fit_calibrator


def _ex(score, label, group="g", idx=0):
    return TrainingExample(ranking_score=score, label=label, group=group)


def _both_sides():
    """Positives on even and odd indices alike, so each half of the split
    has some — the case where the guarantee actually holds."""
    return [_ex(0.9 if i % 4 in (0, 1) else 0.1, 1 if i % 4 in (0, 1) else 0)
            for i in range(40)]


def test_a_clean_split_keeps_the_guarantee():
    cal = fit_calibrator(_both_sides(), alpha=0.1, n_min=1)
    assert cal.split_disjoint


def test_positives_only_on_the_fit_side_voids_disjointness():
    """Every positive lands on the even side, so the conformal half has none
    and the quantiles must be taken from rows the Platt map already saw."""
    examples = []
    for i in range(40):
        on_fit_side = i % 2 == 0
        examples.append(_ex(0.9 if on_fit_side else 0.1,
                            1 if on_fit_side else 0))
    cal = fit_calibrator(examples, alpha=0.1, n_min=1)
    assert not cal.split_disjoint


def test_the_flag_survives_serialisation():
    examples = [_ex(0.9 if i % 2 == 0 else 0.1, 1 if i % 2 == 0 else 0)
                for i in range(40)]
    cal = fit_calibrator(examples, alpha=0.1, n_min=1)
    assert not cal.split_disjoint
    assert not TunedCalibrator.from_dict(cal.to_dict()).split_disjoint


def test_an_old_calibrator_without_the_flag_loads_as_disjoint():
    d = fit_calibrator(_both_sides(), alpha=0.1, n_min=1).to_dict()
    d.pop("split_disjoint")
    assert TunedCalibrator.from_dict(d).split_disjoint


def test_a_leaked_calibrator_marks_its_prediction_sets_invalid():
    """The point of the flag: it has to reach the response, not just sit on
    the artifact."""
    from ktrf.glossary import load_glossary
    from ktrf.resolver import resolve
    from ktrf.snapshot import compile_snapshot

    # seal=False: attaching an artifact to a sealed snapshot is refused,
    # which is the point of the seal — this test is about the flag, not that
    snap = compile_snapshot(load_glossary("examples/realorg_glossary.yaml"),
                            seal=False)
    examples = [_ex(0.9 if i % 2 == 0 else 0.1, 1 if i % 2 == 0 else 0)
                for i in range(40)]
    leaked = fit_calibrator(examples, alpha=0.1, n_min=1)
    assert not leaked.split_disjoint
    snap.calibrator = leaked

    resp = resolve(snap, "한국전력공사가 발표했다", mode="commit")
    sets = [m["prediction_set"] for m in resp["mentions"]
            if m.get("prediction_set")]
    assert sets, "no prediction set produced"
    assert all(ps.get("coverage_valid") is False for ps in sets), sets
