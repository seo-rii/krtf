"""A conformal guarantee that quietly stops holding (§25.2, REQ-CAL-003).

`fit_calibrator` splits examples so the Platt map and the conformal
quantiles come from disjoint rows — but both fallbacks for a degenerate
label distribution put the rows back together, and the calibrator went on
reporting `set_confidence = 1 - alpha` as though nothing had changed.
"""

import pytest

from ktrf.calibration import (TrainingExample, TunedCalibrator,
                              fit_calibrator, fit_calibrator_from_folds)


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


def _leaked():
    """A fold split the caller got wrong: no positive on the conformal side.

    `fit_calibrator` no longer produces this from label/parity-correlated
    input — it stratifies — so the leak is reached the way it can still
    happen, through the fold API, whose contract puts the split in the
    caller's hands and only promises to *report* a violation.
    """
    fit = [_ex(0.9, 1) for _ in range(10)] + [_ex(0.1, 0) for _ in range(10)]
    conformal = [_ex(0.1, 0) for _ in range(20)]
    return fit_calibrator_from_folds(fit, conformal, alpha=0.1, n_min=1)


def test_positives_only_on_the_fit_side_voids_disjointness():
    assert not _leaked().split_disjoint


def test_a_label_pattern_lined_up_with_row_parity_no_longer_leaks():
    """The fix. Every positive on an even index used to put them all on one
    side of the split; an export ordered by correction kind or by time does
    exactly that without anyone contriving it."""
    examples = [_ex(0.9 if i % 2 == 0 else 0.1, 1 if i % 2 == 0 else 0)
                for i in range(40)]
    cal = fit_calibrator(examples, alpha=0.1, n_min=1)
    assert cal.split_disjoint, "stratified halves should both hold positives"


def test_the_flag_survives_serialisation():
    cal = _leaked()
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
    leaked = _leaked()
    assert not leaked.split_disjoint
    snap.calibrator = leaked

    resp = resolve(snap, "한국전력공사가 발표했다", mode="commit")
    sets = [m["prediction_set"] for m in resp["mentions"]
            if m.get("prediction_set")]
    assert sets, "no prediction set produced"
    assert all(ps.get("coverage_valid") is False for ps in sets), sets
