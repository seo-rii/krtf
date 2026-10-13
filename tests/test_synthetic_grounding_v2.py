"""Versioning, contrast balance, opaque IDs and unchanged v1 inputs."""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import pytest

from eval.blind_gold import digest
from eval.report_synthetic_grounding import analyze_frozen_requests
from eval.synthetic_grounding import build_expanded_requests, load_families
from eval import synthetic_grounding_v2 as suite


@pytest.fixture(scope="module")
def source():
    originals = load_families()
    contrasts = [json.loads(line) for p in sorted(suite.CONTRAST_DIR.glob("*.jsonl"))
                 for line in p.read_text().splitlines()]
    return originals, contrasts


@pytest.fixture(scope="module")
def balanced(source):
    families = suite.balance_families(*source)
    return families, suite.build_balanced_requests(families)


def test_v1_source_and_generated_requests_stay_byte_identical(source):
    manifest = json.loads(Path("reports/SYNTHETIC_GROUNDING_CORPUS.json").read_text())
    assert digest(source[0]) == suite.V1_SOURCE_SHA256 == manifest["source_semantic_sha256"]
    encoded = b"".join((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode()
                       for r in build_expanded_requests())
    assert hashlib.sha256(encoded).hexdigest() == manifest["requests_sha256"]


def test_transform_preserves_sources_and_uses_opaque_model_ids(source, balanced):
    before = digest(source)
    transformed = suite.balance_families(*source)
    assert digest(source) == before
    assert digest(transformed) == digest(balanced[0])
    assert len(balanced[1]) == 4370
    for row in balanced[1]:
        for entity_id in re.findall(r"(?:global|project|session):[a-z0-9_.-]+", row["user"]):
            assert re.fullmatch(r"(?:global|project|session):e_[0-9a-f]{24}", entity_id)
        if row["condition"] == "full_pack":
            assert json.loads(row["user"].split("\n", 1)[0]) == {"terminology_context": row["pack"]}


def test_each_collision_pair_has_fixed_cards_and_opposite_gold(balanced):
    pairs = defaultdict(list)
    for row in balanced[1]:
        if row.get("contrast_pair_id") and row["condition"] == "original" and row["task"] == "document_qa":
            pairs[row["contrast_pair_id"]].append(row)
    assert len(pairs) == 37
    for first, second in pairs.values():
        assert first["world"] == second["world"]
        assert first["target_surface"] == second["target_surface"]
        assert first["cards"] == second["cards"]
        assert first["text"] != second["text"]
        assert {first["expected_entity_id"], second["expected_entity_id"]} == {
            card["entity_id"] for card in first["cards"]}
    diagnostics = analyze_frozen_requests(balanced[1])
    shortcuts = diagnostics["contextual_collision_shortcuts"]["rules"]
    assert shortcuts["non_main_suffix"]["support"] == 0
    for name in ("first_candidate", "last_candidate"):
        assert shortcuts[name]["qa_exact_matches"] == shortcuts[name]["semantic_id_matches"] == 37
        assert shortcuts[name]["documents"] == 74
    assert diagnostics["semantic_oracle_ceiling"]["success_ceiling"] == 773


def test_new_contrasts_inherit_v1_family_partitions(balanced):
    manifest = suite.balanced_corpus_manifest(*balanced)
    v1 = json.loads(Path("reports/SYNTHETIC_GROUNDING_CORPUS.json").read_text())
    for case_id, partition in v1["partition_assignments"].items():
        assert manifest["partition_assignments"][case_id] == partition
    for family in balanced[0]:
        assert len({manifest["partition_assignments"][c["case_id"]] for c in family["cases"]}) == 1


def test_v2_runner_selects_versioned_inputs_and_seals_them(tmp_path, monkeypatch, balanced):
    from eval import run_product_llm as runner
    from eval.report_synthetic_grounding import prepare_report

    document = balanced[1][0]["document_id"]
    rows = [row for row in balanced[1] if row["document_id"] == document]
    monkeypatch.setattr(suite, "build_balanced_requests", lambda: rows)
    sent = []

    def fake_api(url, *, payload=None, timeout):
        if url.endswith("/models"):
            return {"data": [{"id": "served"}]}
        sent.append(payload)
        return {"choices": [{"finish_reason": "stop", "message": {
            "content": '{"answer":null,"entity_id":null}'}}]}

    monkeypatch.setattr(runner, "_request_json", fake_api)
    out = tmp_path / "run"
    manifest = runner.run_benchmark(endpoint="http://localhost/v1", model="served",
        out_dir=out, code_revision="frozen-v2-code", track="synthetic_expansion_v2")
    assert manifest["protocol"] == "synthetic_grounding_expansion_v2"
    assert manifest["declared_protocol"] == suite.BALANCED_PROTOCOL
    assert manifest["status"] == "COMPLETE" and len(sent) == len(rows) == 10
    for payload, row in zip(sent, rows):
        assert payload["messages"] == [{"role": "system", "content": row["system"]},
                                       {"role": "user", "content": row["user"]}]
    assert prepare_report(out)["counts"]["request_count"] == 10


@pytest.mark.parametrize("change", ["missing", "duplicate", "same_gold", "other_world", "unverified_origin"])
def test_invalid_contrast_cannot_change_gold_or_pair_membership(source, change):
    originals, contrasts = deepcopy(source)
    item = contrasts[0]
    original = next(c for f in originals for c in f["cases"] if c["case_id"] == item["source_case_id"])
    if change == "missing":
        contrasts.pop()
    elif change == "duplicate":
        contrasts.append(deepcopy(item))
    elif change == "same_gold":
        item["case"]["gold"]["entity_ref"] = original["gold"]["entity_ref"]
    elif change == "other_world":
        item["case"]["world"] = "other"
    else:
        item["annotation_origin"] = "HUMAN"
    with pytest.raises(ValueError):
        suite.balance_families(originals, contrasts)
