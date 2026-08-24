"""Save/load/finetune interface tests (spec §11, §25, §30, §47.3, §48.3).

REQ-COR-001..004 (correction workflow), REQ-CAL-002/003 (conformal fallback,
conservative zero-training start), INV-014/015/018.
"""

import json

import pytest

from ktrf.artifacts import finetune, load_snapshot, save_snapshot
from ktrf.calibration import (
    TrainingExample,
    calibration_group,
    derive_training_examples,
    empirical_coverage,
    fit_calibrator,
)
from ktrf.corrections import CorrectionError, CorrectionStore
from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot


@pytest.fixture(scope="module")
def snap():
    return compile_snapshot(load_glossary("examples/demo_glossary.yaml"),
                            tenant_id="t1")


# ---------------------------------------------------------------------------
# save / load (§11, §47.3)
# ---------------------------------------------------------------------------


def test_save_load_roundtrip(snap, tmp_path):
    bundle = save_snapshot(snap, tmp_path / "bundle")
    assert (bundle / "manifest.json").exists()
    assert (bundle / "glossary.yaml").exists()
    loaded = load_snapshot(bundle)
    assert loaded.snapshot_id == snap.snapshot_id
    assert loaded.tenant_id == "t1"
    text = "한전KDN은 AP 장애 내용을 QMS에 등록했다."
    assert resolve(loaded, text, mode="commit") == resolve(snap, text, mode="commit")


def test_load_refuses_tampered_glossary(snap, tmp_path):
    # §47.3/INV-015: content-hash mismatch blocks loading
    bundle = save_snapshot(snap, tmp_path / "bundle")
    g = (bundle / "glossary.yaml").read_text(encoding="utf-8")
    (bundle / "glossary.yaml").write_text(
        g.replace("ORG_KEPCO", "ORG_EVIL"), encoding="utf-8")
    with pytest.raises(KtrfApiError) as e:
        load_snapshot(bundle)
    assert e.value.code == "SNAPSHOT_UNAVAILABLE"
    assert "entities_hash" in e.value.message


def test_load_refuses_tampered_calibrator(snap, tmp_path):
    tuned = _finetuned(snap)
    bundle = save_snapshot(tuned, tmp_path / "bundle")
    cal = json.loads((bundle / "calibrator.json").read_text(encoding="utf-8"))
    cal["platt_a"] = 99.0
    (bundle / "calibrator.json").write_text(json.dumps(cal), encoding="utf-8")
    with pytest.raises(KtrfApiError):
        load_snapshot(bundle)


def test_load_missing_bundle(tmp_path):
    with pytest.raises(KtrfApiError) as e:
        load_snapshot(tmp_path / "nope")
    assert e.value.code == "SNAPSHOT_UNAVAILABLE"


# ---------------------------------------------------------------------------
# correction workflow (§30)
# ---------------------------------------------------------------------------


def _submit_one(store, tenant="t1", entity="NETWORK_ACCESS_POINT",
                mention_state=None, verifier=None):
    return store.submit(
        tenant_id=tenant,
        request_ref={"snapshot_id": "snap-x", "request_id": "req-1",
                     "mention_id": "m1"},
        correction_type="WRONG_ENTITY",
        corrected={"entity_id": entity},
        verifier=verifier or {"kind": "REVIEWER", "principal_ref": "rev-1"},
        mention_state=mention_state,
    )


def test_correction_workflow_states():
    store = CorrectionStore()
    c = _submit_one(store)
    assert c.status == "SUBMITTED"
    store.review("t1", c.correction_id, "ACCEPTED", reviewer="admin-1")
    assert store.get("t1", c.correction_id).status == "ACCEPTED"
    with pytest.raises(CorrectionError):
        store.review("t1", c.correction_id, "REJECTED", reviewer="admin-1")


def test_accepted_only_export():
    # INV-018/REQ-COR-001: SUBMITTED and REJECTED never export
    store = CorrectionStore()
    a = _submit_one(store)
    b = _submit_one(store)
    _submit_one(store)  # stays SUBMITTED
    store.review("t1", a.correction_id, "ACCEPTED", reviewer="r")
    store.review("t1", b.correction_id, "REJECTED", reviewer="r")
    exported = store.export_accepted("t1")
    assert [c["correction_id"] for c in exported] == [a.correction_id]


def test_correction_tenant_isolation():
    # REQ-COR-004
    store = CorrectionStore()
    c = _submit_one(store, tenant="t1")
    with pytest.raises(CorrectionError):
        store.get("t2", c.correction_id)
    assert store.list("t2") == []


def test_correction_validation():
    store = CorrectionStore()
    with pytest.raises(CorrectionError):
        store.submit("t1", {}, "BOGUS_TYPE")
    with pytest.raises(CorrectionError):
        store.submit("t1", {}, "MISSED_MENTION", corrected={})  # span required
    with pytest.raises(CorrectionError):
        store.submit("t1", {}, "WRONG_ENTITY", corrected={})  # entity required


def test_evidence_text_requires_double_opt_in():
    # §30.2: raw text stored only with opt-in AND tenant policy
    plain = CorrectionStore(allow_evidence_text=False)
    c = plain.submit("t1", {}, "FALSE_MENTION", evidence_text="비밀 문장",
                     evidence_text_opt_in=True)
    assert c.evidence_text is None
    allowed = CorrectionStore(allow_evidence_text=True)
    c = allowed.submit("t1", {}, "FALSE_MENTION", evidence_text="문장",
                       evidence_text_opt_in=True)
    assert c.evidence_text == "문장"
    c = allowed.submit("t1", {}, "FALSE_MENTION", evidence_text="문장",
                       evidence_text_opt_in=False)
    assert c.evidence_text is None


def test_per_principal_export_cap():
    # REQ-COR-003: one USER principal cannot dominate the label pool
    store = CorrectionStore()
    for _ in range(60):
        c = _submit_one(store, verifier={"kind": "USER", "principal_ref": "u1"})
        store.review("t1", c.correction_id, "ACCEPTED", reviewer="r")
    exported = store.export_accepted("t1")
    assert len(exported) == 50  # DEFAULT_PER_PRINCIPAL_CAP["USER"]
    assert all(e["weight"] == 1 for e in exported)


# ---------------------------------------------------------------------------
# calibration fitting (§25)
# ---------------------------------------------------------------------------


def _synthetic_examples(n=400, group="exact|multi"):
    # correct candidates get higher scores; separable but noisy
    out = []
    for i in range(n):
        pos_score = 0.9 + 0.2 * ((i % 10) / 10)
        neg_score = 0.4 + 0.2 * ((i % 7) / 7)
        out.append(TrainingExample(pos_score, group, 1))
        out.append(TrainingExample(neg_score, group, 0))
    return out


def test_fit_calibrator_monotonic_and_bounded():
    cal = fit_calibrator(_synthetic_examples(), alpha=0.05, n_min=100)
    lo, hi = cal.calibrate_marginal(0.3), cal.calibrate_marginal(1.1)
    assert lo < hi
    assert 0.0 < lo and hi < 1.0
    assert cal.set_confidence == 0.95


def test_conformal_group_fallback_flagged():
    # REQ-CAL-002: small group -> pooled quantile + fallback flag
    examples = _synthetic_examples(400, "exact|multi") + \
        _synthetic_examples(5, "dense|multi")
    cal = fit_calibrator(examples, alpha=0.05, n_min=100)
    _, fb_big = cal.quantile_for("exact|multi")
    _, fb_small = cal.quantile_for("dense|multi")
    assert not fb_big and fb_small


def test_conformal_coverage_on_holdout():
    # empirical check: ≥ ~1-α of held-out positives fall inside the set
    fit = _synthetic_examples(300)
    cal = fit_calibrator(fit, alpha=0.1, n_min=100)
    holdout = [e for e in _synthetic_examples(97) if e.label == 1]
    covered = sum(
        cal.in_prediction_set(cal.calibrate_marginal(e.ranking_score),
                              e.group)[0]
        for e in holdout
    )
    assert covered / len(holdout) >= 0.85


def test_fit_requires_data():
    with pytest.raises(ValueError):
        fit_calibrator([])
    with pytest.raises(ValueError):
        fit_calibrator([TrainingExample(0.5, "exact|multi", 0)] * 20)


def test_derive_training_examples_from_correction():
    correction = {
        "correction_type": "WRONG_ENTITY",
        "corrected": {"entity_id": "E_B"},
        "mention_state": {
            "prediction_set": {"members": [
                {"kind": "ENTITY", "entity_id": "E_A", "ranking_score": 1.0,
                 "generation_channels": ["exact"]},
                {"kind": "ENTITY", "entity_id": "E_B", "ranking_score": 0.9,
                 "generation_channels": ["exact"]},
                {"kind": "KB_MISSING"},
            ]},
        },
    }
    pairs = derive_training_examples(correction)
    assert len(pairs) == 2
    labels = {(p.label, round(p.ranking_score, 1)) for p in pairs}
    assert labels == {(0, 1.0), (1, 0.9)}
    assert all(p.group == calibration_group({"exact"}, 2) for p in pairs)


def test_empirical_coverage():
    # REQ-CAL-004: coverage only from labeled corrections
    good = {
        "correction_type": "WRONG_ENTITY", "corrected": {"entity_id": "E_B"},
        "mention_state": {"prediction_set": {"members": [
            {"kind": "ENTITY", "entity_id": "E_A"},
            {"kind": "ENTITY", "entity_id": "E_B"},
        ]}},
    }
    miss = {
        "correction_type": "WRONG_ENTITY", "corrected": {"entity_id": "E_Z"},
        "mention_state": {"prediction_set": {"members": [
            {"kind": "ENTITY", "entity_id": "E_A"},
        ]}},
    }
    r = empirical_coverage([good, miss, {"correction_type": "FALSE_MENTION"}])
    assert r == {"labeled": 2, "coverage": 0.5, "mean_set_size": 1.5}
    assert empirical_coverage([])["coverage"] is None


# ---------------------------------------------------------------------------
# end-to-end finetune (§48.3)
# ---------------------------------------------------------------------------


def _finetuned(snap, n_min=50):
    """Resolve → correct → approve → finetune, on the demo glossary."""
    store = CorrectionStore()
    texts = ["무선 AP 장애가 발생했다.", "AP 결재 부탁드립니다.",
             "AP 전표 처리 부탁드립니다.", "AP 상태를 점검했다."]
    gold = ["NETWORK_ACCESS_POINT", "WORKFLOW_APPROVAL_PROCESS",
            "WORKFLOW_APPROVAL_PROCESS", "NETWORK_ACCESS_POINT"]
    for i, (text, g) in enumerate(zip(texts * 5, gold * 5)):
        resp = resolve(snap, text, mode="commit")
        mention = next(m for m in resp["mentions"] if m["surface"] == "AP")
        c = store.submit(
            tenant_id=snap.tenant_id,
            request_ref={"snapshot_id": resp["snapshot"]["snapshot_id"],
                         "request_id": f"req-{i}", "mention_id":
                             mention["mention_id"]},
            correction_type="WRONG_ENTITY",
            corrected={"entity_id": g},
            verifier={"kind": "REVIEWER", "principal_ref": f"rev-{i % 3}"},
            mention_state=mention,
        )
        store.review(snap.tenant_id, c.correction_id, "ACCEPTED", reviewer="adm")
    return finetune(snap, store, alpha=0.1, n_min=n_min)


def test_finetune_produces_new_snapshot(snap):
    tuned = _finetuned(snap)
    assert tuned.snapshot_id != snap.snapshot_id
    assert tuned.calibrator is not None
    assert snap.calibrator is None  # input never mutated
    assert tuned.manifest["calibrator_hash"] is not None
    assert snap.manifest.get("calibrator_hash") is None
    # glossary untouched (REQ-COR-002)
    assert tuned.glossary is snap.glossary


def test_finetuned_resolver_uses_calibrator(snap):
    tuned = _finetuned(snap)
    resp = resolve(tuned, "AP 확인 요청", mode="commit")
    m = next(x for x in resp["mentions"] if x["surface"] == "AP")
    assert m["prediction_set"]["set_confidence"] == tuned.calibrator.set_confidence
    for member in m["prediction_set"]["members"]:
        if member.get("kind", "ENTITY") == "ENTITY":
            expected = tuned.calibrator.calibrate_marginal(
                member["ranking_score"])
            assert member["calibrated_probability"] == expected


def test_finetune_golden_gate_refusal(snap):
    store = CorrectionStore()
    resp = resolve(snap, "무선 AP 장애가 발생했다.", mode="commit")
    mention = next(m for m in resp["mentions"] if m["surface"] == "AP")
    for i in range(12):
        c = store.submit(
            tenant_id=snap.tenant_id,
            request_ref={"snapshot_id": "s", "request_id": f"r{i}",
                         "mention_id": "m1"},
            correction_type="WRONG_ENTITY",
            corrected={"entity_id": "NETWORK_ACCESS_POINT"},
            verifier={"kind": "ADMIN", "principal_ref": "a"},
            mention_state=mention,
        )
        store.review(snap.tenant_id, c.correction_id, "ACCEPTED", reviewer="r")
    with pytest.raises(KtrfApiError) as e:
        finetune(snap, store, golden_check=lambda s: False)
    assert "golden" in e.value.message


def test_finetuned_roundtrip_through_bundle(snap, tmp_path):
    tuned = _finetuned(snap)
    bundle = save_snapshot(tuned, tmp_path / "tuned")
    loaded = load_snapshot(bundle)
    assert loaded.calibrator is not None
    text = "AP 확인 요청"
    assert resolve(loaded, text, mode="commit") == resolve(tuned, text, mode="commit")
