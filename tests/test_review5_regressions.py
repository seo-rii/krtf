"""REVIEW 2026-09-08 — the findings that reproduced against HEAD.

The package shipped runnable reproductions, which is what made this triage
cheap: 15 of its 28 checks failed here against 22 on the archive it reviewed
(again `origin/main`, 413 tests). Seven of the fifteen turned out not to be
defects, and each was verified rather than waved away:

- **R01** (a display limit promoting a commit) and **R04** (a bundle missing
  a declared artifact) fail only because their setup rebinds an attribute on
  a *sealed* snapshot. Rebuilt with `seal=False`, `max_prediction_set=1`
  leaves the decision AMBIGUOUS with the set flagged truncated, and deleting
  either `calibrator.json` or `entity-vectors.json` is refused.
- **R12** (two workers skipping a chunk) — both chunks are claimed, resolved
  and stored; the loss is the §20.3 overlap merge collapsing two mentions the
  test's stub left at identical coordinates, because its span dict is not a
  span record and so is never globalised. With real span records the same
  race yields both mentions, at 0-1 and 8-9.
- **C02** (their control) fails on `Path.read_text()` without an encoding —
  cp949 against a UTF-8 Korean glossary. Tampering with the glossary is
  refused (`entities_hash mismatch`).
- **R17** the package itself files as a policy proposal, not a defect.
- **R18/R19** are the two known false commits from `VARIANT_GOLD.md`; they
  are resolution quality, not a contract, and are not addressed here.

What follows pins the five that were real.
"""

import json
import math
import tempfile
from pathlib import Path

import pytest

from ktrf import compile_snapshot, load_glossary, resolve
from ktrf.artifacts import load_snapshot, save_snapshot
from ktrf.calibration import (TrainingExample, fit_calibrator,
                              fit_calibrator_from_folds)
from ktrf.errors import KtrfApiError
from ktrf.jobs import ResolveJobManager


@pytest.fixture
def snap():
    return compile_snapshot(load_glossary("examples/demo_glossary.yaml"))


def _surrogate() -> str:
    """Exactly how one arrives from a JSON request body."""
    return json.loads('"\\ud800"')


# --------------------------------------------------------------------- R16
def test_an_unencodable_string_is_a_typed_error_not_a_crash(snap):
    with pytest.raises(KtrfApiError) as e:
        resolve(snap, _surrogate())
    assert e.value.to_dict()["error"]["code"] == "INVALID_UTF8"


def test_the_async_entry_point_types_it_too(snap):
    """The review only exercised `resolve`; `submit` had the same hole."""
    with pytest.raises(KtrfApiError) as e:
        ResolveJobManager().submit(snap, _surrogate())
    assert e.value.to_dict()["error"]["code"] == "INVALID_UTF8"


# --------------------------------------------------------------------- R05
@pytest.mark.parametrize("key", ["normalization_profiles_hash",
                                 "fuzzy_confusion_hash",
                                 "abbrev_signature_hash"])
def test_every_recorded_runtime_hash_is_verified(snap, tmp_path, monkeypatch,
                                                 key):
    """A hash written into the manifest and never read back is a comment.

    These three describe the normalization profiles, the fuzzy confusion
    table and the abbreviation signature set — change any of them and the
    same `snapshot_id` resolves differently.
    """
    import ktrf.artifacts as artifacts

    save_snapshot(snap, tmp_path)
    real = artifacts.compile_snapshot

    def drifted(*a, **kw):
        out = real(*a, **kw)
        out.manifest[key] = "sha256:a-different-runtime"
        return out

    monkeypatch.setattr(artifacts, "compile_snapshot", drifted)
    with pytest.raises(KtrfApiError) as e:
        artifacts.load_snapshot(tmp_path)
    assert key in str(e.value)


def test_an_untouched_bundle_still_loads(snap, tmp_path):
    """The verification must not refuse a bundle that is simply correct."""
    save_snapshot(snap, tmp_path)
    restored = load_snapshot(tmp_path)
    assert resolve(snap, "한전") == resolve(restored, "한전")


# --------------------------------------------------------------------- R13
def test_an_unexpected_worker_fault_makes_the_job_terminal(snap, monkeypatch):
    """It used to propagate with the job left RUNNING, so a polling host
    waited forever on work nothing was doing."""
    import ktrf.jobs as jobs

    def boom(*a, **kw):
        raise RuntimeError("simulated encoder fault")

    monkeypatch.setattr(jobs, "resolve", boom)
    mgr = ResolveJobManager()
    job = mgr.submit(snap, "한전")["job_id"]
    with pytest.raises(RuntimeError):
        mgr.process(job)          # still propagates; it is not anticipated
    status = mgr.status(job)
    assert status["status"] == "FAILED", status
    assert status.get("error", {}).get("code") == "INTERNAL"


def test_a_cancelled_job_is_not_overwritten_as_failed(snap, monkeypatch):
    import ktrf.jobs as jobs

    mgr = ResolveJobManager()
    job = mgr.submit(snap, "한전")["job_id"]

    def cancel_then_fine(*a, **kw):
        mgr.cancel(job)
        return {"degraded": False, "mentions": []}

    monkeypatch.setattr(jobs, "resolve", cancel_then_fine)
    mgr.process(job)
    assert mgr.status(job)["status"] == "CANCELLED"


# --------------------------------------------------------------------- R07
def test_labels_lined_up_with_row_parity_no_longer_void_the_split():
    """The ungrouped split was raw row parity, so any label pattern
    correlated with row index put every positive on one side and the Platt
    map was refit on all rows. An export ordered by correction kind or by
    time does that without anyone contriving it."""
    examples = [TrainingExample(ranking_score=0.9 if i % 2 == 0 else 0.1,
                                label=1 if i % 2 == 0 else 0, group="g")
                for i in range(40)]
    cal = fit_calibrator(examples, alpha=0.1, n_min=1)
    assert cal.split_disjoint


def test_the_halves_are_still_disjoint_after_stratifying():
    fit = [TrainingExample(ranking_score=0.9, label=1, group="g")
           for _ in range(10)]
    conformal = [TrainingExample(ranking_score=0.1, label=0, group="g")
                 for _ in range(20)]
    # a caller-supplied fold with no positive on the conformal side must
    # still be reported, not silently repaired
    assert not fit_calibrator_from_folds(fit, conformal, alpha=0.1,
                                         n_min=1).split_disjoint


# --------------------------------------------------------------------- E01
def test_a_mention_that_was_never_emitted_gets_no_identity_credit(monkeypatch):
    from eval import run_variant_gold as vg

    row = {"id": "synthetic", "text": "SKT서 발표했다", "span": [0, 3],
           "stratum": "synthetic",
           "gold": {"span_ok": True, "refers": "YES", "entity": "ORG_SKT",
                    "should_commit": True, "full_identity": "SAME",
                    "relation": "IDENTITY"}}
    monkeypatch.setattr(vg, "resolve", lambda *a, **kw: {"mentions": []})
    graded = vg.grade([row], None)[0]
    assert graded["emitted"] is False
    assert graded["identity_correct"] is False


def test_an_emitted_mention_that_stays_silent_still_counts_as_same(monkeypatch):
    """The licence being narrowed, not removed: `SAME` and saying nothing
    are the same answer for a mention that exists."""
    from eval import run_variant_gold as vg

    row = {"id": "synthetic", "text": "SKT서 발표했다", "span": [0, 3],
           "stratum": "synthetic",
           "gold": {"span_ok": True, "refers": "YES", "entity": "ORG_SKT",
                    "should_commit": True, "full_identity": "SAME",
                    "relation": "IDENTITY"}}
    mention = {"span": {"codepoint": {"start": 0, "end": 3}},
               "link_decision": "RESOLVED",
               "resolved_entity": {"entity_id": "ORG_SKT"}}
    monkeypatch.setattr(vg, "resolve",
                        lambda *a, **kw: {"mentions": [mention]})
    assert vg.grade([row], None)[0]["identity_correct"] is True


# ------------------------------------------------- the verified non-defects
def test_a_display_limit_still_does_not_promote_a_commit():
    """R01, rebuilt without rebinding a sealed snapshot."""
    from ktrf.calibration import TunedCalibrator

    s = compile_snapshot(load_glossary("examples/demo_glossary.yaml"),
                         seal=False)
    s.calibrator = TunedCalibrator(0.0, math.log(9), 0.05,
                                   {"exact|multi": 1.0}, 1.0, 1.0,
                                   {"exact|multi": 1000}, 10)
    wide = resolve(s, "AP", options={"max_prediction_set": 50})["mentions"][0]
    cut = resolve(s, "AP", options={"max_prediction_set": 1})["mentions"][0]
    assert wide["link_decision"] == "AMBIGUOUS"
    assert cut["link_decision"] == "AMBIGUOUS"
    assert cut["prediction_set"]["truncated"] is True


def test_tampering_with_the_stored_glossary_is_refused(snap):
    """C02, with the encoding their harness omitted."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        save_snapshot(snap, out)
        p = out / "glossary.yaml"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace("description:", "description: changed ", 1),
                     encoding="utf-8")
        with pytest.raises(KtrfApiError):
            load_snapshot(out)
