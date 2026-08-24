"""Snapshot compile/activation/tenant tests (spec §11, §12).

INV-006, INV-007, INV-014, INV-015, REQ-TEN-001/002, REQ-API-002,
REQ-NRM-005 (conformance blocks activation), REQ-LVL-002.
"""

import pytest

from ktrf.errors import KtrfApiError
from ktrf.glossary import GlossaryError, load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import COMPATIBILITY_ID, SnapshotRegistry, compile_snapshot


def _glossary(version="1", surface="한전"):
    return load_glossary({
        "glossary_id": "org-a", "version": version, "schema_version": "3",
        "entities": [{"entity_id": "E1", "canonical": "한국전력공사",
                      "description": "전력 공기업"}],
        "alias_families": [{"family_id": "F1", "representative": surface,
                            "normalization_profile": "korean_org_name"}],
        "alias_bindings": [{"alias_id": "A1", "family_id": "F1",
                            "entity_id": "E1", "surface": surface}],
    })


def test_compile_runs_conformance():
    snap = compile_snapshot(_glossary())
    conf = snap.manifest["conformance"]
    assert conf["failed"] == 0 and conf["total"] > 0
    assert snap.manifest["compatibility_id"] == COMPATIBILITY_ID


def test_strict_validation_blocks_compile():
    bad = load_glossary({
        "glossary_id": "g", "version": "1", "schema_version": "3",
        "entities": [{"entity_id": "E1", "canonical": ""}],
        "alias_families": [],
        "alias_bindings": [],
    })
    with pytest.raises(GlossaryError):
        compile_snapshot(bad)


def test_atomic_activation_keeps_old_on_failure():
    # INV-014: failed compile/activation leaves the active snapshot intact
    reg = SnapshotRegistry()
    v1 = compile_snapshot(_glossary("1"), tenant_id="t1")
    reg.activate(v1)
    with pytest.raises(GlossaryError):
        compile_snapshot(load_glossary({
            "glossary_id": "org-a", "version": "2", "schema_version": "3",
            "entities": [{"entity_id": "E1", "canonical": ""}],  # invalid
            "alias_families": [], "alias_bindings": [],
        }), tenant_id="t1")
    assert reg.get_active("t1") is v1


def test_compatibility_mismatch_refused():
    # INV-015
    reg = SnapshotRegistry()
    snap = compile_snapshot(_glossary(), tenant_id="t1")
    snap.manifest["compatibility_id"] = "ktrf-bundle-v99"
    with pytest.raises(KtrfApiError) as e:
        reg.activate(snap)
    assert e.value.code == "SNAPSHOT_UNAVAILABLE"


def test_version_policy_strict_mismatch():
    # REQ-API-002
    reg = SnapshotRegistry()
    reg.activate(compile_snapshot(_glossary("2026-08-23.1"), tenant_id="t1"))
    with pytest.raises(KtrfApiError) as e:
        reg.resolve_tenant("t1", "org-a", "2026-08-22.4", "strict")
    assert e.value.code == "GLOSSARY_VERSION_MISMATCH"
    assert e.value.details["active_version"] == "2026-08-23.1"
    # latest_active proceeds
    snap = reg.resolve_tenant("t1", "org-a", "2026-08-22.4", "latest_active")
    assert snap.glossary_version == "2026-08-23.1"


def test_forbidden_glossary_outside_tenant_scope():
    # REQ-TEN-001
    reg = SnapshotRegistry()
    reg.activate(compile_snapshot(_glossary(), tenant_id="t1"))
    with pytest.raises(KtrfApiError) as e:
        reg.resolve_tenant("t1", "org-b", None)
    assert e.value.code == "FORBIDDEN_GLOSSARY"


def test_no_active_snapshot():
    reg = SnapshotRegistry()
    with pytest.raises(KtrfApiError) as e:
        reg.get_active("ghost")
    assert e.value.code == "GLOSSARY_NOT_FOUND"


def test_tenant_isolation():
    # INV-007/REQ-TEN-002: tenant B entities never appear for tenant A
    reg = SnapshotRegistry()
    a = compile_snapshot(_glossary(surface="한전"), tenant_id="ta")
    b = load_glossary({
        "glossary_id": "org-b", "version": "1", "schema_version": "3",
        "entities": [{"entity_id": "SECRET_B", "canonical": "비밀조직"}],
        "alias_families": [{"family_id": "F1", "representative": "한전",
                            "normalization_profile": "korean_org_name"}],
        "alias_bindings": [{"alias_id": "A1", "family_id": "F1",
                            "entity_id": "SECRET_B", "surface": "한전"}],
    })
    bs = compile_snapshot(b, tenant_id="tb")
    reg.activate(a)
    reg.activate(bs)
    resp = resolve(reg.get_active("ta"), "한전에서 회의", mode="commit")
    ids = {x.get("entity_id")
           for m in resp["mentions"]
           for x in m.get("prediction_set", {}).get("members", [])}
    ids |= {m.get("resolved_entity", {}).get("entity_id")
            for m in resp["mentions"]}
    assert "SECRET_B" not in ids
    # every response pins exactly one snapshot (INV-006)
    assert resp["snapshot"]["snapshot_id"] == reg.get_active("ta").snapshot_id


def test_conformance_failure_blocks_activation():
    # REQ-NRM-005/REQ-LVL-002: simulate a failing conformance report
    reg = SnapshotRegistry()
    snap = compile_snapshot(_glossary(), tenant_id="t1")
    snap.manifest["conformance"] = {"total": 10, "passed": 9, "failed": 1}
    with pytest.raises(KtrfApiError):
        reg.activate(snap)
