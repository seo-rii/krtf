"""A snapshot owns its content, and a bundle is replaced or it is not.

Three ways the identity stopped identifying anything:

* the snapshot held the caller's glossary, so editing that object afterwards
  changed what an already-compiled snapshot answered while `snapshot_id`,
  computed once at compile, went on describing the glossary as it was;
* a save wrote straight into the destination, so a failure partway through a
  re-save left the new glossary beside the old manifest — a bundle matching
  neither, and the previous good one destroyed by the attempt to replace it;
* optional artifacts were verified only `if the file exists`, so deleting a
  file the manifest declared removed the check along with its subject.
"""

import json
from pathlib import Path

import pytest

from ktrf.artifacts import _hash, load_snapshot, save_snapshot
from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

GLOSSARY = "examples/realorg_glossary.yaml"


def _small_glossary():
    return load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [
            {"entity_id": "E_ONE", "canonical": "한국전력공사",
             "description": "전력 공기업"},
        ],
        "alias_families": [
            {"family_id": "F", "representative": "한전",
             "normalization_profile": "korean_org_name"},
        ],
        "alias_bindings": [
            {"alias_id": "A", "family_id": "F", "entity_id": "E_ONE",
             "surface": "한전"},
        ],
    })


# --------------------------------------------------------------- ownership

def test_editing_the_glossary_after_compile_does_not_reach_the_snapshot():
    g = _small_glossary()
    snap = compile_snapshot(g)
    before = [m.get("resolved_entity", {}).get("canonical")
              for m in resolve(snap, "한전 관련 회의", mode="commit")["mentions"]]
    g.entities[0].canonical = "MUTATED_AFTER_COMPILE"
    after = [m.get("resolved_entity", {}).get("canonical")
             for m in resolve(snap, "한전 관련 회의", mode="commit")["mentions"]]
    assert before == after
    assert "MUTATED_AFTER_COMPILE" not in str(after)


def test_appending_a_binding_after_compile_does_not_reach_the_snapshot():
    g = _small_glossary()
    snap = compile_snapshot(g)
    g.alias_bindings.append(type(g.alias_bindings[0])(
        **{**vars(g.alias_bindings[0]), "alias_id": "A2", "surface": "한국전력"}))
    resp = resolve(snap, "한국전력 관련 회의", mode="commit")
    assert all(m["link_decision"] != "RESOLVED" for m in resp["mentions"])


def test_two_snapshots_from_one_glossary_do_not_share_state():
    g = _small_glossary()
    a = compile_snapshot(g)
    b = compile_snapshot(g)
    a.glossary.entities[0].canonical = "ONLY_A"
    assert b.glossary.entities[0].canonical != "ONLY_A"


# ------------------------------------------------------------- atomic save

def test_an_interrupted_resave_leaves_the_previous_bundle_intact(tmp_path):
    first = compile_snapshot(_small_glossary())
    g2 = _small_glossary()
    g2.entities[0].canonical = "COMPLETELY DIFFERENT"
    second = compile_snapshot(g2)
    assert first.snapshot_id != second.snapshot_id

    out = tmp_path / "bundle"
    save_snapshot(first, out)
    assert load_snapshot(out).snapshot_id == first.snapshot_id

    real_write = Path.write_text
    fired = {"n": 0}

    def flaky(self, data, *a, **kw):
        if self.name == "policy.json":
            fired["n"] += 1
            raise OSError("injected write failure")
        return real_write(self, data, *a, **kw)

    Path.write_text = flaky
    try:
        with pytest.raises(OSError):
            save_snapshot(second, out)
    finally:
        Path.write_text = real_write

    assert fired["n"] == 1, "the failure has to actually happen"
    # the old bundle is still there, still loads, still itself
    assert load_snapshot(out).snapshot_id == first.snapshot_id


def test_a_failed_first_save_leaves_no_half_bundle(tmp_path):
    out = tmp_path / "bundle"
    real_write = Path.write_text

    def flaky(self, data, *a, **kw):
        if self.name == "policy.json":
            raise OSError("injected write failure")
        return real_write(self, data, *a, **kw)

    Path.write_text = flaky
    try:
        with pytest.raises(OSError):
            save_snapshot(compile_snapshot(_small_glossary()), out)
    finally:
        Path.write_text = real_write
    assert not out.exists(), "a bundle that was never finished must not appear"


def test_staging_directories_do_not_survive_a_successful_save(tmp_path):
    save_snapshot(compile_snapshot(_small_glossary()), tmp_path / "bundle")
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "bundle"]
    assert leftovers == []


def test_a_resave_drops_an_artifact_the_new_snapshot_does_not_have(tmp_path):
    from ktrf.encoders import HashEncoder

    out = tmp_path / "bundle"
    save_snapshot(compile_snapshot(_small_glossary(), encoder=HashEncoder()),
                  out)
    assert (out / "entity-vectors.json").exists()
    save_snapshot(compile_snapshot(_small_glossary()), out)
    assert not (out / "entity-vectors.json").exists()


# ----------------------------------------------- declared but not delivered

@pytest.mark.parametrize("filename,key", [
    ("calibrator.json", "calibrator_hash"),
    ("guard.json", "segmentation_guard_hash"),
])
def test_a_declared_artifact_that_is_missing_is_refused(tmp_path, filename,
                                                        key):
    from ktrf.calibration import TrainingExample, fit_calibrator

    snap = compile_snapshot(_small_glossary(), seal=False)
    snap.calibrator = fit_calibrator(
        [TrainingExample(0.5 + 0.02 * i, "exact|multi", int(i % 4 in (0, 1)))
         for i in range(40)], alpha=0.1, n_min=1)
    out = tmp_path / "bundle"
    save_snapshot(snap, out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get(key) is not None, f"{key} should be declared"
    (out / filename).unlink()
    with pytest.raises(KtrfApiError) as e:
        load_snapshot(out)
    assert e.value.to_dict()["error"]["code"] == "SNAPSHOT_UNAVAILABLE"
    assert key in str(e.value)


def test_a_bundle_declaring_nothing_optional_still_loads(tmp_path):
    out = tmp_path / "bundle"
    save_snapshot(compile_snapshot(_small_glossary()), out)
    assert not (out / "calibrator.json").exists()
    assert load_snapshot(out) is not None


def test_a_tampered_calibrator_is_still_refused(tmp_path):
    from ktrf.calibration import TrainingExample, fit_calibrator

    snap = compile_snapshot(_small_glossary(), seal=False)
    snap.calibrator = fit_calibrator(
        [TrainingExample(0.5 + 0.02 * i, "exact|multi", int(i % 4 in (0, 1)))
         for i in range(40)], alpha=0.1, n_min=1)
    out = tmp_path / "bundle"
    save_snapshot(snap, out)
    doc = json.loads((out / "calibrator.json").read_text(encoding="utf-8"))
    doc["alpha"] = 0.5
    (out / "calibrator.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(KtrfApiError):
        load_snapshot(out)
