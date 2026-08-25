"""Regression tests for the artifact-integrity and release-gate defects
found in external review: content-blind hashes, tamper-accepting loader,
vacuous gate passes, unvalidated runtime options.
"""

import dataclasses
import json

import pytest

from ktrf.artifacts import load_snapshot, save_snapshot
from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import (RuntimePolicy, SnapshotRegistry, compile_snapshot,
                           compute_snapshot_id)

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
