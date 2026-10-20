"""Regression tests for the artifact-integrity and release-gate defects
found in external review: content-blind hashes, tamper-accepting loader,
vacuous gate passes, unvalidated runtime options.
"""

import dataclasses
import json

import pytest

from ktrf.artifacts import load_snapshot, save_snapshot
from ktrf.errors import KtrfApiError
from ktrf.encoders import HashEncoder
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import (RuntimePolicy, SnapshotRegistry, compile_snapshot,
                           compute_snapshot_id, _hash)

from eval.metrics import Metric
from eval.run_eval import compute_gate


def _glossary(description="네트워크 장비"):
    return load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [
            {"entity_id": "E1", "canonical": "Access Point",
             "description": description, "domain_ids": ["NET"]}],
        "alias_families": [
            {"family_id": "F", "representative": "AP",
             "normalization_profile": "latin_acronym"}],
        "alias_bindings": [
            {"alias_id": "A1", "family_id": "F", "entity_id": "E1",
             "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary"}}],
    })


# ---------------------------------------------------------------- identity

def test_snapshot_id_covers_description():
    a = compile_snapshot(_glossary(), run_conformance=False)
    b = compile_snapshot(_glossary("변경된 설명"), run_conformance=False)
    assert a.snapshot_id != b.snapshot_id
    assert a.manifest["entities_hash"] != b.manifest["entities_hash"]


def test_snapshot_id_covers_runtime_policy():
    a = compile_snapshot(_glossary(), run_conformance=False)
    b = compile_snapshot(_glossary(), run_conformance=False,
                         policy=RuntimePolicy(resolve_threshold=0.5))
    assert a.snapshot_id != b.snapshot_id
    assert a.manifest["policy_hash"] != b.manifest["policy_hash"]


def test_snapshot_id_is_128_bit():
    snap = compile_snapshot(_glossary(), run_conformance=False)
    assert len(snap.snapshot_id.removeprefix("snap-")) == 32


def test_snapshot_id_includes_conformance_record():
    unverified = compile_snapshot(_glossary(), run_conformance=False)
    verified = compile_snapshot(_glossary(), run_conformance=True)
    assert unverified.snapshot_id != verified.snapshot_id


# ------------------------------------------------------------------ tamper

def test_loader_rejects_policy_tamper(tmp_path):
    snap = compile_snapshot(_glossary(), run_conformance=False)
    save_snapshot(snap, tmp_path)
    p = json.loads((tmp_path / "policy.json").read_text(encoding="utf-8"))
    p["resolve_threshold"] = 0.01
    (tmp_path / "policy.json").write_text(json.dumps(p), encoding="utf-8")
    with pytest.raises(KtrfApiError) as e:
        load_snapshot(tmp_path)
    assert "policy_hash" in str(e.value)


def test_loader_rejects_glossary_description_tamper(tmp_path):
    snap = compile_snapshot(_glossary(), run_conformance=False)
    save_snapshot(snap, tmp_path)
    y = (tmp_path / "glossary.yaml").read_text(encoding="utf-8")
    (tmp_path / "glossary.yaml").write_text(
        y.replace("네트워크 장비", "조작된 설명"), encoding="utf-8")
    with pytest.raises(KtrfApiError) as e:
        load_snapshot(tmp_path)
    assert "entities_hash" in str(e.value)


def test_loader_rejects_manifest_id_tamper(tmp_path):
    snap = compile_snapshot(_glossary(), run_conformance=False)
    save_snapshot(snap, tmp_path)
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    m["snapshot_id"] = "snap-" + "0" * 32
    (tmp_path / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(KtrfApiError) as e:
        load_snapshot(tmp_path)
    assert "snapshot_id" in str(e.value)


def test_saved_id_matches_manifest_content(tmp_path):
    snap = compile_snapshot(_glossary(), run_conformance=False)
    save_snapshot(snap, tmp_path)
    m = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert m["snapshot_id"] == compute_snapshot_id(m)
    load_snapshot(tmp_path)  # round-trips cleanly


def _dense_snapshot(vectors=None):
    glossary = load_glossary({
        "glossary_id": "dense-seal", "version": "1", "schema_version": "3",
        "entities": [
            {"entity_id": "POWER", "canonical": "전력 기관"},
            {"entity_id": "FINANCE", "canonical": "금융 기관"},
        ],
    })

    class FixedEncoder(HashEncoder):
        def __init__(self):
            super().__init__(dim=2)

        def encode_passages(self, texts):
            return vectors or [[0.1, 1.0 / 3.0], [0.9, -0.2]]

    return compile_snapshot(glossary, encoder=FixedEncoder(), run_conformance=False)


def _rewrite_vector_payload(bundle, mutate, reseal=False):
    vector_path = bundle / "entity-vectors.json"
    payload = json.loads(vector_path.read_text(encoding="utf-8"))
    mutate(payload)
    vector_path.write_text(json.dumps(payload), encoding="utf-8")
    if reseal:
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entity_vectors_hash"] = _hash(payload)
        manifest["snapshot_id"] = compute_snapshot_id(manifest)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_dense_compile_identity_covers_vector_content_and_roundtrips_float32(tmp_path):
    snapshot = _dense_snapshot()
    changed = _dense_snapshot([[0.1, 1.0 / 3.0], [0.8, -0.2]])
    assert snapshot.dense.encoder_id == changed.dense.encoder_id
    assert snapshot.snapshot_id != changed.snapshot_id
    assert snapshot.manifest["entity_vectors_hash"] != changed.manifest["entity_vectors_hash"]
    bundle = save_snapshot(snapshot, tmp_path / "first")
    loaded = load_snapshot(bundle, encoder=HashEncoder(dim=2))
    assert loaded.snapshot_id == snapshot.snapshot_id
    assert loaded.dense.index.to_dict() == snapshot.dense.index.to_dict()
    assert loaded.dense.index.search([1.0, 0.0]) == snapshot.dense.index.search([1.0, 0.0])
    second = save_snapshot(loaded, tmp_path / "second")
    assert (bundle / "entity-vectors.json").read_bytes() == (second / "entity-vectors.json").read_bytes()


def test_symbolic_manifest_keeps_previous_dense_null_contract():
    snapshot = compile_snapshot(_glossary(), run_conformance=False)
    assert "entity_vectors_hash" not in snapshot.manifest


@pytest.mark.parametrize("tamper", [
    lambda p: p["vectors"].reverse(),
    lambda p: p["entity_ids"].reverse(),
    lambda p: p["vectors"][0].__setitem__(0, 0.5),
])
def test_loader_refuses_vector_tamper_with_unchanged_snapshot_id(tmp_path, tamper):
    snapshot = _dense_snapshot()
    bundle = save_snapshot(snapshot, tmp_path)
    before = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    _rewrite_vector_payload(bundle, tamper)
    assert json.loads((bundle / "manifest.json").read_text(encoding="utf-8")) == before
    with pytest.raises(KtrfApiError, match="entity_vectors_hash mismatch"):
        load_snapshot(bundle, encoder=HashEncoder(dim=2))


@pytest.mark.parametrize("tamper,reason", [
    (lambda p: p["entity_ids"].reverse(), "row order"),
    (lambda p: p["entity_ids"].__setitem__(0, "MISSING"), "row order"),
    (lambda p: p["entity_ids"].__setitem__(0, "FINANCE"), "unique"),
    (lambda p: p["vectors"].pop(), "count"),
    (lambda p: p["vectors"][0].pop(), "dimension"),
    (lambda p: p["vectors"][0].__setitem__(0, float("nan")), "finite"),
    (lambda p: p.__setitem__("dim", 3), "dimension"),
    (lambda p: p.__setitem__("index_type", "cosine"), "index_type"),
])
def test_loader_validates_vector_structure_even_with_matching_digest(tmp_path, tamper, reason):
    bundle = save_snapshot(_dense_snapshot(), tmp_path)
    _rewrite_vector_payload(bundle, tamper, reseal=True)
    with pytest.raises(KtrfApiError, match=reason):
        load_snapshot(bundle, encoder=HashEncoder(dim=2))


def test_loader_refuses_missing_required_vector_file(tmp_path):
    bundle = save_snapshot(_dense_snapshot(), tmp_path)
    (bundle / "entity-vectors.json").unlink()
    with pytest.raises(KtrfApiError, match="missing required entity-vectors"):
        load_snapshot(bundle, encoder=HashEncoder(dim=2))


@pytest.mark.parametrize("field,value", [("vector_dimension", 3),
                                        ("index_type", "cosine")])
def test_loader_rejects_inconsistent_dense_manifest_metadata(tmp_path, field, value):
    bundle = save_snapshot(_dense_snapshot(), tmp_path)
    path = bundle / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest[field] = value
    manifest["snapshot_id"] = compute_snapshot_id(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(KtrfApiError, match="do not match the manifest"):
        load_snapshot(bundle, encoder=HashEncoder(dim=2))


def test_old_dense_bundle_requires_trusted_recompile(tmp_path):
    bundle = save_snapshot(_dense_snapshot(), tmp_path)
    path = bundle / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    del manifest["entity_vectors_hash"]
    manifest["snapshot_id"] = compute_snapshot_id(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(KtrfApiError, match="recompile from the trusted glossary"):
        load_snapshot(bundle, encoder=HashEncoder(dim=2))


def test_loader_refuses_unexpected_vectors_in_symbolic_bundle(tmp_path):
    save_snapshot(compile_snapshot(_glossary(), run_conformance=False), tmp_path)
    (tmp_path / "entity-vectors.json").write_text("{}", encoding="utf-8")
    with pytest.raises(KtrfApiError, match="unexpected entity-vectors"):
        load_snapshot(tmp_path)


def test_resaving_symbolic_bundle_removes_only_stale_vector_file(tmp_path):
    save_snapshot(_dense_snapshot(), tmp_path)
    symbolic = compile_snapshot(_glossary(), run_conformance=False)
    save_snapshot(symbolic, tmp_path)
    assert not (tmp_path / "entity-vectors.json").exists()
    assert load_snapshot(tmp_path).snapshot_id == symbolic.snapshot_id


# -------------------------------------------------------------- activation

def test_activation_requires_conformance_record():
    reg = SnapshotRegistry()
    unverified = compile_snapshot(_glossary(), run_conformance=False)
    with pytest.raises(KtrfApiError):
        reg.activate(unverified)
    reg.activate(unverified, allow_unverified=True)  # explicit opt-out only
    reg.activate(compile_snapshot(_glossary(), run_conformance=True))


# ------------------------------------------------------------ release gate

def _gate(**overrides):
    n = 800  # large enough that Wilson lower bounds clear the CI floors
    kw = dict(
        conformance_failures=0, golden_violations=0,
        recall_metric=Metric("r", "E2E", n, n),
        in_set_metric=Metric("s", "|mention", n, n),
        resolved_correct=600, resolved_total=600,
        forbidden_entity_hits=0, offset_invariant_failures=0,
    )
    kw.update(overrides)
    return compute_gate(**kw)


def test_gate_passes_on_clean_run():
    assert _gate()["pass"] is True


def test_gate_fails_on_single_golden_violation():
    g = _gate(golden_violations=1)
    assert g["pass"] is False
    assert g["checks"]["golden_violations"] is False


def test_gate_fails_with_zero_commits():
    g = _gate(resolved_correct=0, resolved_total=0)
    assert g["pass"] is False
    assert g["values"]["resolved_precision_commit"] is None  # not 1.0


def test_gate_fails_below_min_commits():
    g = _gate(resolved_correct=5, resolved_total=5)
    assert g["checks"]["resolved_precision"] is False


def test_gate_fails_when_ci_lower_bound_is_weak():
    # 11/11 = 100% point estimate but Wilson lower bound ~0.74
    g = _gate(recall_metric=Metric("r", "E2E", 11, 11))
    assert g["checks"]["level_a_core_span_recall"] is False


def test_gate_rows_reflect_actual_checks():
    g = _gate(golden_violations=2)
    assert g["checks"]["golden_violations"] is False
    assert g["checks"]["conformance_failures"] is True


# --------------------------------------------------------- option schema

def test_options_validation():
    snap = compile_snapshot(_glossary(), run_conformance=False)
    for bad in [{"max_prediction_set": -1},
                {"max_prediction_set": 0},
                {"max_prediction_set": 10 ** 9},
                {"max_prediction_set": "50"},
                {"max_prediction_set": True},
                {"unknown_option": 1},
                {"return_all_mentions": "yes"}]:
        with pytest.raises(KtrfApiError) as e:
            resolve(snap, "AP 설정", options=bad)
        assert e.value.code == "INVALID_REQUEST"
    resolve(snap, "AP 설정", options={"max_prediction_set": 50,
                                     "return_all_mentions": True})
