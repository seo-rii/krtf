"""The quantile and the membership test have to be on the same scale.

The conformal quantile is a threshold on ``1 - p``. The fit computed p as a
raw sigmoid; inference clipped it to [0.01, 0.99] and rounded it to three
places. Those are two different thresholds, so a score sitting on the boundary
was inside the set on one side of the system and outside on the other — and
the side it fell out on was inference, where the coverage claim is made.

The clip and the round are part of the score function, not presentation, so
both callers go through the same one.
"""

import math

import pytest

from ktrf.calibration import (
    TrainingExample,
    TunedCalibrator,
    fit_calibrator,
    fit_with_folds,
    platt_marginal,
)


def _rows(n=60):
    out = []
    for d in range(n):
        out.append(TrainingExample(0.9 - 0.003 * d, "exact|multi", 1,
                                   groups={"document": f"d{d}"}))
        out.append(TrainingExample(0.5 - 0.003 * d, "exact|multi", 0,
                                   groups={"document": f"d{d}"}))
    return out


@pytest.fixture(scope="module")
def fitted():
    return fit_with_folds(_rows(), alpha=0.1, n_min=1)


def test_the_calibrator_uses_the_shared_score_function(fitted):
    cal = fitted.calibrator
    for i in range(200):
        s = -1.0 + 0.01 * i
        assert cal.calibrate_marginal(s) == platt_marginal(
            cal.platt_a, cal.platt_b, s)


def test_no_score_lands_on_different_sides_of_the_quantile(fitted):
    cal = fitted.calibrator
    flips = 0
    for i in range(20000):
        s = -1.0 + 0.0002 * i
        by_fit = (1.0 - platt_marginal(cal.platt_a, cal.platt_b, s)) \
            <= cal.global_quantile
        by_inference = (1.0 - cal.calibrate_marginal(s)) <= cal.global_quantile
        flips += int(by_fit != by_inference)
    assert flips == 0


def test_the_calibration_points_are_admitted_by_the_set_they_defined(fitted):
    # the finite-sample statement: at least ceil((n+1)(1-alpha))/n of the
    # calibration points have nonconformity <= q, so the set built from that
    # q has to admit them. It did not when the two sides rounded differently.
    cal, rep = fitted.calibrator, fitted.split
    positives = [e for e in rep.rows(_rows(), "conformal") if e.label == 1]
    assert positives
    covered = sum(int(cal.in_prediction_set(
        cal.calibrate_marginal(e.ranking_score), e.group)[0])
        for e in positives)
    assert covered / len(positives) >= 0.90


def test_a_raw_sigmoid_is_not_what_the_quantile_is_measured_on(fitted):
    # pins the direction of the fix: the shared function is the clipped and
    # rounded one, not the raw sigmoid. If someone "simplifies" the clip away,
    # inference and the quantile part company again.
    cal = fitted.calibrator
    raw = 1.0 / (1.0 + math.exp(-(cal.platt_a * 0.45 + cal.platt_b)))
    assert platt_marginal(cal.platt_a, cal.platt_b, 0.45) == round(
        min(0.99, max(0.01, raw)), 3)


def test_the_clip_bounds_are_honoured_at_the_extremes():
    assert platt_marginal(50.0, 0.0, 10.0) == 0.99
    assert platt_marginal(50.0, 0.0, -10.0) == 0.01


def test_a_persisted_calibrator_scores_the_same_way_after_a_roundtrip():
    cal = fit_calibrator(_rows(), alpha=0.1, n_min=1)
    back = TunedCalibrator.from_dict(cal.to_dict())
    for i in range(200):
        s = -1.0 + 0.01 * i
        assert back.calibrate_marginal(s) == cal.calibrate_marginal(s)
