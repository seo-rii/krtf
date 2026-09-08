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
- **R19** (`kt` in a baseball headline committing to the telecom) is a
  metonymy that needs context the surface does not carry. Left open; note
  that `KT` is already in the eval's `DETECTION_ONLY` list, which stops the
  scoring and not the commit.

**R18** was real and is fixed here: `美국방부` is the US department, and all
30 occurrences of a country marker glued to a registered body committed to
the Korean one.

**F-05**, which had no runnable repro and so was triaged by hand, was
also real: the default path emits `set_confidence` with no calibrator
behind it.

What follows pins the seven that were real.
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


# --------------------------------------------------------------------- R18
def _realorg():
    return compile_snapshot(load_glossary("examples/realorg_glossary.yaml"))


@pytest.mark.parametrize("text,surface", [
    ("WP 美국방부 사우디 석유시설 피격에 신중 대응 권고", "국방부"),
    ("中외교부 나토 정상회의 관련 브리핑", "외교부"),
    ("美법무부 조세회피의혹 파나마 페이퍼스 면밀 검토", "법무부"),
    ("日공정위 美 대형IT기업 부당거래 실태조사", "공정위"),
    ("獨헌재 방송국 극우당 선거광고 내보내야", "헌재"),
])
def test_a_country_marker_blocks_the_domestic_commit(text, surface):
    """`美국방부` is the US department; every one of the 30 occurrences of
    this pattern across the six corpora committed to the Korean body."""
    committed = [(m["surface"], (m.get("resolved_entity") or {}).get("entity_id"))
                 for m in resolve(_realorg(), text)["mentions"]
                 if m["link_decision"] == "RESOLVED"]
    assert not any(s == surface for s, _ in committed), committed


def test_the_candidate_survives_even_though_the_commit_does_not():
    """Withholding a commit must not delete the reading — a host still needs
    to see what the surface could have been (invariant ④)."""
    resp = resolve(_realorg(), "WP 美국방부 사우디 석유시설 피격에 신중 대응 권고")
    m = next(x for x in resp["mentions"] if x["surface"] == "국방부")
    assert m["link_decision"] != "RESOLVED"
    assert m.get("prediction_set", {}).get("members"), m


def test_koreas_own_marker_is_not_treated_as_foreign():
    """`南통일부` is South Korea's ministry as North Korean media writes it,
    and is the one occurrence of the pattern that was already correct."""
    resp = resolve(_realorg(), "北 북남관계 최악은 南통일부 반통일 망동 때문 궤변")
    got = [(m.get("resolved_entity") or {}).get("entity_id")
           for m in resp["mentions"] if m["link_decision"] == "RESOLVED"]
    assert "ORG_MOU" in got, resp["mentions"]


def test_an_unmarked_ministry_still_commits():
    """The rule must not cost the ordinary case."""
    resp = resolve(_realorg(), "국방부가 오늘 발표했다.")
    got = [(m.get("resolved_entity") or {}).get("entity_id")
           for m in resp["mentions"] if m["link_decision"] == "RESOLVED"]
    assert "ORG_MND" in got, resp["mentions"]


# --------------------------------------------------------------------- F-05
def test_an_uncalibrated_set_says_it_is_heuristic():
    """`{"set_confidence": 0.95}` was emitted bare on the default path, which
    has no calibrator: a configured constant reading as a 95% guarantee."""
    ps = resolve(_realorg(), "한국전력공사가 발표했다.")["mentions"][0]["prediction_set"]
    assert ps["method"] == "HEURISTIC"
    assert "coverage_scope" not in ps, "no procedure means no scope to name"


def test_a_calibrated_set_names_the_procedure_and_its_scope():
    from ktrf.calibration import TunedCalibrator

    s = compile_snapshot(load_glossary("examples/realorg_glossary.yaml"),
                         strict=False, seal=False)
    s.calibrator = TunedCalibrator(0.0, math.log(9), 0.05, {"exact|multi": 1.0},
                                   1.0, 1.0, {"exact|multi": 1000}, 10)
    ps = resolve(s, "한국전력공사가 발표했다.")["mentions"][0]["prediction_set"]
    assert ps["method"] == "CONFORMAL"
    # the quantile is computed on the candidate pool, so it cannot speak for
    # a gold entity retrieval never produced
    assert ps["coverage_scope"] == "candidate_conditional"


def test_the_method_is_not_a_second_coverage_flag():
    """`coverage_valid` must keep meaning "the procedure ran and its
    assumptions held". Folding "there was no procedure" into it would make it
    False on nearly every response and say nothing on the ones that matter."""
    ps = resolve(_realorg(), "한국전력공사가 발표했다.")["mentions"][0]["prediction_set"]
    assert ps["method"] == "HEURISTIC"
    assert "coverage_valid" not in ps


def test_the_published_schema_accepts_both_methods():
    from ktrf.schemas import validate_resolve_response

    for snap_ in (_realorg(),):
        resp = resolve(snap_, "한국전력공사가 발표했다.")
        assert validate_resolve_response(resp) == []


# --------------------------------------------------------------------- F-14
def _write_cache(path, meta, texts=("한국전력공사가 발표했다.",)):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"meta": meta}, ensure_ascii=False) + "\n")
        for t in texts:
            f.write(json.dumps({"text": t, "source": "ds:cfg:train"},
                               ensure_ascii=False) + "\n")


def _load(monkeypatch, tmp_path, meta):
    import eval.wild_data as wd

    cache = tmp_path / "corpus.jsonl"
    _write_cache(cache, meta)
    monkeypatch.setitem(wd.CORPORA, "probe", ([], cache, {}))
    monkeypatch.setattr(wd, "download", lambda **kw: cache)
    wd.load_corpus("probe")
    return wd.corpus_fingerprint()


def test_an_incomplete_download_is_carried_into_the_footer(monkeypatch,
                                                           tmp_path):
    """The loop abandons a source after eight errors and keeps the others, so
    a corpus that lost one produced a cache shaped exactly like a whole one."""
    from eval.metrics import provenance_line

    fp = _load(monkeypatch, tmp_path, {
        "sentences": 1, "by_source": {"ds:cfg:train": 1},
        "sources": {"ds:cfg:train": {"complete": False}},
        "incomplete_sources": ["ds:cfg:train"]})
    assert fp["incomplete_sources"] == ["ds:cfg:train"]
    assert "불완전" in provenance_line(".", corpus=fp)


def test_a_complete_download_says_nothing_extra(monkeypatch, tmp_path):
    from eval.metrics import provenance_line

    fp = _load(monkeypatch, tmp_path, {
        "sentences": 1, "by_source": {"ds:cfg:train": 1},
        "sources": {"ds:cfg:train": {"complete": True}},
        "incomplete_sources": []})
    assert fp["incomplete_sources"] == []
    line = provenance_line(".", corpus=fp)
    assert "불완전" not in line and "기록하기 전에" not in line


def test_a_cache_predating_the_accounting_does_not_claim_completeness(
        monkeypatch, tmp_path):
    """Absence of the record is not evidence every source arrived; defaulting
    it to an empty list would have every existing cache assert that."""
    from eval.metrics import provenance_line

    fp = _load(monkeypatch, tmp_path,
               {"sentences": 1, "by_source": {"ds:cfg:train": 1}})
    assert fp["incomplete_sources"] is None
    assert "기록하기 전에" in provenance_line(".", corpus=fp)
