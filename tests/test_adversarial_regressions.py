"""Regression tests for defects found by the adversarial benchmarks.

These pin the fixes for two bugs that the catalog-derived eval could not
detect (they only appear under adversarial structure):

1. unknown-tail overcommit: Pass-2 abbreviation evidence merged into an
   exact candidate restored its quality prior, letting weak surface paths
   (한전스럽게) commit as RESOLVED;
2. calibration fallback under-coverage: under-sampled conformal groups
   inherited the pooled (majority-distribution) quantile instead of a
   conservative one.

Plus a small always-on adversarial smoke suite (fast subset of
eval/run_benchmarks.py) so hard-gate violations fail CI, not just the
benchmark report.
"""

import random

import pytest

from ktrf.calibration import TrainingExample, fit_calibrator
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

from eval.adversarial import (
    run_boundary_traps,
    run_multisense_discipline,
    run_ooc_tails,
)
from eval.synthetic import build_synthetic_glossary


@pytest.fixture(scope="module")
def synth():
    g, meta = build_synthetic_glossary(150, seed=9)
    snap = compile_snapshot(load_glossary(g), strict=False,
                            run_conformance=False)
    return snap, meta


def test_unknown_tail_never_commits(synth):
    # regression: 공도스럽게-style unknown tails must not RESOLVE, even when
    # Pass-2 abbrev evidence merges into the exact candidate
    snap, meta = synth
    single = [a for a, e in meta.hangul_abbrevs.items() if len(e) == 1][:15]
    assert single
    for abbrev in single:
        text = f"{abbrev}스럽게 굴지 말자."
        resp = resolve(snap, text, mode="commit",
                       options={"return_all_mentions": True})
        for m in resp["mentions"]:
            cp = m["span"]["codepoint"]
            if (cp["start"], cp["end"]) == (0, len(abbrev)):
                assert m["link_decision"] != "RESOLVED", text


def test_clean_exact_still_commits(synth):
    # the overcommit fix must not break commit on clean single-sense surfaces
    snap, meta = synth
    single = [a for a, e in meta.hangul_abbrevs.items() if len(e) == 1][:15]
    committed = 0
    for abbrev in single:
        resp = resolve(snap, f"{abbrev}에서 자료를 보냈다.", mode="commit")
        committed += any(m["link_decision"] == "RESOLVED"
                         for m in resp["mentions"])
    assert committed >= len(single) * 0.8


def test_calibration_fallback_is_conservative():
    # regression: an under-sampled group with a divergent (lower-score)
    # distribution must widen its sets, not inherit the majority quantile
    rng = random.Random(3)
    pool = []
    for _ in range(300):
        pool.append(TrainingExample(1.0 + 0.3 * rng.random(), "exact|multi", 1))
        pool.append(TrainingExample(0.5 + 0.3 * rng.random(), "exact|multi", 0))
    for _ in range(15):
        pool.append(TrainingExample(0.45 + 0.2 * rng.random(), "dense|multi", 1))
        pool.append(TrainingExample(0.25 + 0.2 * rng.random(), "dense|multi", 0))
    cal = fit_calibrator(pool, alpha=0.1, n_min=100)
    q_small, fb = cal.quantile_for("dense|multi")
    assert fb
    # conservative: at least the group's own small-sample quantile
    assert q_small >= cal.group_quantiles["dense|multi"]
    covered = sum(
        cal.in_prediction_set(cal.calibrate_marginal(e.ranking_score),
                              "dense|multi")[0]
        for e in pool if e.group == "dense|multi" and e.label == 1
    )
    assert covered >= 13  # ≥ ~0.9 of 15


def test_adversarial_hard_gates_smoke(synth):
    # fast subset of the benchmark hard gates, run in CI on every change
    snap, meta = synth
    rng = random.Random(77)
    traps = run_boundary_traps(snap, meta, rng, max_aliases=25)
    assert traps.hits == 0, traps.details
    _, overcommit = run_ooc_tails(snap, meta, rng, max_cases=25)
    assert overcommit.hits == 0, overcommit.details
    disc = run_multisense_discipline(snap, meta, rng, max_aliases=25)
    assert disc["arbitrary_commits"] == 0
    assert disc["sense_loss"] == 0
