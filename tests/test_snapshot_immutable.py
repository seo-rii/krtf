"""Compiled configuration isolation and snapshot state invariance."""
import dataclasses
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml

from ktrf.artifacts import load_snapshot, save_snapshot
from ktrf.calibration import TunedCalibrator
from ktrf.errors import KtrfApiError
from ktrf.fusion import FEATURE_NAMES, FusionModel
from ktrf.glossary import glossary_to_dict, load_glossary
from ktrf.immutable import thaw
from ktrf.resolver import resolve
from ktrf.segmentation import ResolutionGuard, _decompose
from ktrf.snapshot import RuntimePolicy, SnapshotRegistry, compile_snapshot, compute_snapshot_id


def source(entity_id="E1", version="1"):
    return load_glossary({"glossary_id": "immutable", "version": version, "schema_version": "3",
        "entities": [{"entity_id": entity_id, "canonical": "한국전력공사",
                      "grounding": {"disambiguation_hints": ["전력"]},
                      "metadata": {"nested": [{"flag": True}]}}],
        "alias_families": [{"family_id": "F", "representative": "한전",
                            "normalization_profile": "korean_org_name"}],
        "alias_bindings": [{"alias_id": "A", "entity_id": entity_id,
                            "family_id": "F", "surface": "한전",
                            "scope": {"allow": {"domains": ["energy"]}}}]})


def test_source_edits_cannot_change_compiled_semantics():
    g, policy, guard = source(), RuntimePolicy(), ResolutionGuard()
    snap = compile_snapshot(g, policy=policy, guard=guard)
    before = resolve(snap, "한전은 발표했다.")
    identity = snap.snapshot_id
    g.entities[0].canonical = "변경된 이름"
    g.entities[0].metadata["nested"][0]["flag"] = False
    g.alias_bindings[0].surface = "다른표면"
    g.alias_bindings[0].boundary_policy.left = "none"
    policy.resolve_threshold = 0.01
    policy.candidate_budget.max_prediction_set = 1
    guard.rules.clear()
    after = resolve(snap, "한전은 발표했다.")
    assert before == after
    assert snap.snapshot_id == identity == compute_snapshot_id(snap.manifest)
    assert snap.exact_index.glossary is snap.glossary
    assert snap.glossary.entity("E1").canonical == "한국전력공사"
    assert snap.policy.resolve_threshold == 0.70
    assert snap.guard.rules


def test_nested_configuration_mutators_blocked():
    snap = compile_snapshot(source())
    mutations = [
        lambda: setattr(snap, "snapshot_id", "forged"),
        lambda: setattr(snap.policy, "resolve_threshold", 0),
        lambda: setattr(snap.policy.candidate_budget, "max_prediction_set", 1),
        lambda: snap.guard.rules.append("new"),
        lambda: setattr(snap.guard, "derivative_factor", 1),
        lambda: snap.glossary.entities.clear(),
        lambda: setattr(snap.glossary.entity("E1"), "canonical", "changed"),
        lambda: snap.glossary.entity("E1").metadata["nested"][0].update(flag=False),
        lambda: snap.glossary.entity("E1").grounding["disambiguation_hints"].append("hint"),
        lambda: snap.glossary.alias_bindings[0].scope.allow["domains"].append("new"),
        lambda: setattr(snap.glossary.alias_bindings[0].fuzzy_policy, "enabled", False),
        lambda: snap.manifest["conformance"].update(failed=1),
        lambda: snap.diagnostics.append(None),
        lambda: snap.compositions.clear(),
    ]
    for mutation in mutations:
        with pytest.raises((TypeError, dataclasses.FrozenInstanceError)):
            mutation()


def test_calibrator_and_fusion_detached_and_sealed(tmp_path):
    cal = TunedCalibrator(1, 0, .05, {"exact:single": .2}, .2, .3,
                          {"exact:single": 30}, 2,
                          partition_manifest={"fit": ["doc-a"], "calibration": ["doc-b"]})
    fusion = FusionModel([0.] * len(FEATURE_NAMES), 0.)
    snap = dataclasses.replace(compile_snapshot(source()), calibrator=cal, fusion=fusion)
    cal.platt_a = 10
    cal.group_quantiles["exact:single"] = 0
    cal.partition_manifest["fit"].append("doc-b")
    fusion.weights[0] = 99
    assert snap.calibrator.platt_a == 1
    assert snap.calibrator.partition_manifest["fit"] == ["doc-a"]
    assert snap.fusion.weights[0] == 0
    for mutation in [lambda: snap.calibrator.group_quantiles.update(other=.9),
                     lambda: snap.calibrator.partition_manifest["fit"].clear(),
                     lambda: setattr(snap.calibrator, "alpha", .5),
                     lambda: snap.fusion.weights.append(1)]:
        with pytest.raises((TypeError, dataclasses.FrozenInstanceError)):
            mutation()
    restored = load_snapshot(save_snapshot(snap, tmp_path))
    assert restored.calibrator.to_dict() == snap.calibrator.to_dict()
    assert restored.fusion.to_dict() == snap.fusion.to_dict()
    with pytest.raises(TypeError):
        restored.calibrator.group_counts.clear()


def test_runtime_caches_and_serialization_remain_usable(tmp_path):
    snap = compile_snapshot(source())
    snap.runtime.caches[(snap.snapshot_id, "query")] = "cached"
    assert snap.runtime.caches[(snap.snapshot_id, "query")] == "cached"
    _decompose.cache_clear()
    cold = resolve(snap, "한전은 발표했다.")
    warm = resolve(snap, "한전은 발표했다.")
    assert cold == warm
    assert _decompose.cache_info().hits > 0
    yaml.safe_dump(thaw(glossary_to_dict(snap.glossary)))
    assert dataclasses.asdict(snap.policy)["candidate_budget"]["max_prediction_set"] == 10
    loaded = load_snapshot(save_snapshot(snap, tmp_path))
    assert loaded.snapshot_id == snap.snapshot_id
    assert resolve(loaded, "한전은 발표했다.") == warm
    assert not loaded.runtime.caches


def test_activation_and_concurrent_responses_pin_one_snapshot():
    old = compile_snapshot(source("E1", "1"))
    new = compile_snapshot(source("E2", "2"))
    registry = SnapshotRegistry()
    registry.activate(old)
    baseline = resolve(old, "한전은 발표했다.")
    registry.activate(new)
    assert resolve(old, "한전은 발표했다.") == baseline
    expected = {old.snapshot_id: "E1", new.snapshot_id: "E2"}

    def flip(i):
        registry.activate(old if i % 2 else new)

    def query(i):
        return resolve(registry.get_active("default"), "한전은 발표했다.")

    with ThreadPoolExecutor(max_workers=4) as executor:
        flips, queries = [], []
        for i in range(30):
            flips.append(executor.submit(flip, i))
            queries.append(executor.submit(query, i))
        results = [future.result() for future in queries]
        for future in flips:
            future.result()
    for response in results:
        eid = expected[response["snapshot"]["snapshot_id"]]
        ids = {m["resolved_entity"]["entity_id"] for m in response["mentions"] if m.get("resolved_entity")}
        assert ids == {eid}


def test_candidate_insertion_order_has_same_tie_decision():
    g = source()
    second = dataclasses.replace(g.entities[0], entity_id="E2")
    g.entities.append(second)
    g.alias_bindings.append(dataclasses.replace(g.alias_bindings[0], alias_id="B", entity_id="E2"))
    first = compile_snapshot(g, run_conformance=False)
    g.entities.reverse()
    g.alias_bindings.reverse()
    second = compile_snapshot(g, run_conformance=False)
    a, b = resolve(first, "한전"), resolve(second, "한전")
    for response in (a, b):
        response.pop("snapshot")
    assert a == b


def test_legacy_semantics_manifest_rejected(tmp_path):
    import json
    snap = compile_snapshot(source())
    save_snapshot(snap, tmp_path)
    path = tmp_path / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.pop("resolver_semantics_version")
    manifest["snapshot_id"] = compute_snapshot_id(manifest)
    path.write_text(json.dumps(manifest))
    with pytest.raises(KtrfApiError, match="resolver_semantics_version"):
        load_snapshot(tmp_path)


def test_rerank_input_is_validated_and_in_identity():
    a = compile_snapshot(source(), policy=RuntimePolicy(rerank_input="context"))
    b = compile_snapshot(source(), policy=RuntimePolicy(rerank_input="target"))
    assert a.snapshot_id != b.snapshot_id
    with pytest.raises(ValueError):
        RuntimePolicy(rerank_input="unsupported")


def test_custom_guard_roundtrip_and_tampering(tmp_path):
    import json
    guard = ResolutionGuard(derivative_factor=.35, rules=["short_core"])
    snap = compile_snapshot(source(), guard=guard)
    save_snapshot(snap, tmp_path)
    loaded = load_snapshot(tmp_path)
    assert dataclasses.asdict(loaded.guard) == dataclasses.asdict(snap.guard)
    assert loaded.snapshot_id == snap.snapshot_id
    assert resolve(loaded, "한전장은 발표했다.") == resolve(snap, "한전장은 발표했다.")
    path = tmp_path / "guard.json"
    data = json.loads(path.read_text())
    data["derivative_factor"] = .9
    path.write_text(json.dumps(data))
    with pytest.raises(KtrfApiError, match="segmentation_guard_hash"):
        load_snapshot(tmp_path)
