"""The finetune path must not calibrate a model against its own training data.

Two leaks lived here, both invisible from the outside because both produced a
calibrator that looked well fitted:

1. verifier weighting (REQ-COR-003) is implemented by *repeating* a row, and a
   row-index split dealt the identical copies to opposite sides — the same row
   fitting the probability map and then supplying the quantile meant to test
   it;
2. with ``fit_fusion_model``, fusion was fit on every row and the Platt map
   was then fit on fusion's own outputs for those same rows.

Neither shows up as an error. Both make the reported confidence better than
the system deserves, which is the failure mode worth a test.
"""

from ktrf.artifacts import finetune
from ktrf.calibration import (
    correction_groups,
    derive_training_examples,
    split_examples,
)
from ktrf.corrections import CorrectionStore
from ktrf.glossary import load_glossary
from ktrf.snapshot import compile_snapshot

GLOSSARY = "examples/realorg_glossary.yaml"


def _members(n, gold_at=0, features=False):
    out = []
    for i in range(n):
        m = {"kind": "ENTITY", "entity_id": f"E{i}",
             "ranking_score": 0.9 - 0.1 * i,
             "generation_channels": ["exact"]}
        if features:
            m["features"] = {"exact_score": 0.9 - 0.1 * i, "is_exact": 1.0}
        out.append(m)
    return out


def _correction(request_id, gold, features=False, kind="REVIEWER"):
    return {
        "correction_id": f"c-{request_id}",
        "tenant_id": "t1",
        "request_ref": {"snapshot_id": "s", "request_id": request_id,
                        "mention_id": "m1"},
        "correction_type": "WRONG_ENTITY",
        "corrected": {"entity_id": gold},
        "verifier": {"kind": kind, "principal_ref": "p1"},
        "mention_state": {"surface": f"surface-{request_id}",
                          "prediction_set": {"members": _members(
                              3, features=features)}},
    }


def _fold_of(report, row):
    return next(f for f, rows in report.folds.items() if row in rows)


# ------------------------------------------------------- the weighting leak

def test_repeated_rows_from_one_correction_stay_in_one_fold():
    # This is the weighting path: `pairs * weight`. Before grouping, copy 0
    # and copy 1 of an identical row went to opposite sides of the split.
    correction = _correction("req-1", "E0")
    pairs = derive_training_examples(correction)
    weighted = pairs * 4                       # REQ-COR-003 weight
    report = split_examples(weighted)
    assert len({_fold_of(report, i) for i in range(len(weighted))}) == 1


def test_two_documents_can_still_be_separated():
    # Grouping must not degenerate into "everything in one fold" — otherwise
    # the leak is fixed by having no split at all.
    rows = []
    for d in range(40):
        rows.extend(derive_training_examples(_correction(f"req-{d}", f"E{d}")))
    report = split_examples(rows)
    assert report.n_components >= 40
    assert all(report.folds[f] for f in ("platt", "conformal", "test"))


def test_correction_groups_carry_document_entity_and_alias_family():
    g = correction_groups(_correction("req-9", "E7"))
    assert g["document"] == "req-9"
    assert g["entity"] == "E7"
    assert g["alias_family"] == "surface-req-9"
    # tenant is recorded but is a holdout axis, never a link dimension
    assert g["tenant"] == "t1"


def test_the_same_gold_entity_in_two_documents_is_one_component():
    rows = (derive_training_examples(_correction("req-a", "E_SHARED"))
            + derive_training_examples(_correction("req-b", "E_SHARED")))
    report = split_examples(rows)
    assert report.n_components == 1


# ------------------------------------------------------- the finetune path

def _store_with(n_docs, features=False):
    store = CorrectionStore()
    for d in range(n_docs):
        c = store.submit(
            tenant_id="t1",
            request_ref={"snapshot_id": "s", "request_id": f"req-{d}",
                         "mention_id": "m1"},
            correction_type="WRONG_ENTITY",
            corrected={"entity_id": f"E{d % 3}"},
            verifier={"kind": "REVIEWER", "principal_ref": f"p{d}"},
            mention_state={"surface": f"surface-{d}",
                           "prediction_set": {
                               "members": _members(3, features=features)}},
        )
        store.review("t1", c.correction_id, "ACCEPTED", reviewer="admin-1")
    return store


def test_finetune_records_coverage_measured_on_the_locked_fold():
    snap = compile_snapshot(load_glossary(GLOSSARY), tenant_id="t1")
    tuned = finetune(snap, _store_with(60), alpha=0.1, n_min=1)
    holdout = tuned.manifest["calibration_holdout"]
    assert holdout["n"] > 0, "a locked fold with no positive measures nothing"
    assert 0.0 <= holdout["coverage"] <= 1.0
    assert holdout["target"] == 0.9
    assert holdout["basis"] == "grouped"


def test_finetune_split_is_grouped_and_reported():
    snap = compile_snapshot(load_glossary(GLOSSARY), tenant_id="t1")
    tuned = finetune(snap, _store_with(60), alpha=0.1, n_min=1)
    report = tuned.calibrator.split_report
    assert report["grouped"] is True
    assert "document" in report["dims_present"]
    assert sum(report["fold_sizes"].values()) == report["n_rows"]


def test_the_locked_fold_is_absent_from_the_calibration_folds():
    snap = compile_snapshot(load_glossary(GLOSSARY), tenant_id="t1")
    tuned = finetune(snap, _store_with(60), alpha=0.1, n_min=1)
    sizes = tuned.calibrator.split_report["fold_sizes"]
    assert sizes["test"] > 0
    assert set(sizes) == {"platt", "conformal", "test"}


def test_training_the_ranker_reserves_a_fourth_fold():
    snap = compile_snapshot(load_glossary(GLOSSARY), tenant_id="t1")
    tuned = finetune(snap, _store_with(60, features=True), alpha=0.1, n_min=1,
                     fit_fusion_model=True)
    sizes = tuned.calibrator.split_report["fold_sizes"]
    assert set(sizes) == {"ranker", "platt", "conformal", "test"}
    # the ranker's own rows are not what the probability map is fitted on
    assert sizes["ranker"] > 0 and sizes["platt"] > 0


# ------------------------------------------- when the data cannot be split

def _one_alias_store(n=30):
    """Every correction is about the same alias, so every row is correlated
    with every other one. This is not a contrived fixture — it is what thirty
    corrections about one ambiguous acronym look like."""
    store = CorrectionStore()
    for d in range(n):
        c = store.submit(
            tenant_id="t1",
            request_ref={"snapshot_id": "s", "request_id": f"req-{d}",
                         "mention_id": "m1"},
            correction_type="WRONG_ENTITY",
            corrected={"entity_id": "E0" if d % 2 else "E1"},
            verifier={"kind": "REVIEWER", "principal_ref": f"p{d}"},
            mention_state={"surface": "AP",
                           "prediction_set": {"members": _members(3)}},
        )
        store.review("t1", c.correction_id, "ACCEPTED", reviewer="admin-1")
    return store


def test_a_single_cluster_cannot_be_split_and_the_fit_says_so():
    snap = compile_snapshot(load_glossary(GLOSSARY), tenant_id="t1")
    tuned = finetune(snap, _one_alias_store(), alpha=0.1, n_min=1)
    # the fit still happens — taking the adaptation path away over a guarantee
    # this data never supported would be the worse trade
    assert tuned.calibrator is not None
    # but the guarantee is not claimed
    assert tuned.calibrator.split_basis == "row_fallback"
    report = tuned.calibrator.split_report
    assert report["n_components"] == 1
    assert report["degraded_to"] == "row"
    assert "conformal" in report["reason"] or "10 rows" in report["reason"]


def test_a_fallback_fit_marks_every_prediction_set_it_produces():
    from ktrf.resolver import resolve

    snap = compile_snapshot(load_glossary(GLOSSARY), tenant_id="t1")
    tuned = finetune(snap, _one_alias_store(), alpha=0.1, n_min=1)
    resp = resolve(tuned, "금융감독원이 조사했다", mode="commit")
    sets = [m["prediction_set"] for m in resp["mentions"]
            if "prediction_set" in m]
    assert sets
    for s in sets:
        assert s["coverage_valid"] is False
        assert s["coverage_basis"] == "row_fallback"


def test_a_fallback_fit_locks_nothing_and_reports_no_holdout_coverage():
    # every row was used, so there is no held-out coverage to report. An
    # invented number here would be measured on the fit's own data.
    snap = compile_snapshot(load_glossary(GLOSSARY), tenant_id="t1")
    tuned = finetune(snap, _one_alias_store(), alpha=0.1, n_min=1)
    assert tuned.manifest["calibration_holdout"]["coverage"] is None
    assert tuned.manifest["calibration_holdout"]["n"] == 0


def test_the_conformal_folds_independent_sample_size_is_reported():
    snap = compile_snapshot(load_glossary(GLOSSARY), tenant_id="t1")
    tuned = finetune(snap, _store_with(60), alpha=0.1, n_min=1)
    report = tuned.calibrator.split_report
    # rows are not observations: the quantile rests on this many independent
    # clusters, which is the number that bounds what it can claim
    assert report["fold_components"]["conformal"] >= 1
    assert sum(report["fold_components"].values()) == report["n_components"]
