"""New source/gold identity, family independence and pre-inference review seals."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path

import pytest

from eval import evidence_efficiency_data as data


def artifact():
    return json.loads(data.CASES_FILE.read_text())


def test_new_predeclared_families_and_source_authorship():
    rows = data.load_evidence_efficiency_records(require_review=False)
    assert len(rows) == 64
    assert Counter(r["evaluation_split"] for r in rows) == {
        "development": 16, "confirmation": 48,
    }
    assert Counter(r["gold"]["label"] for r in rows) == {
        "LINK": 32, "NIL": 20, "COMPOSITIONAL": 2,
        "NON_MENTION": 2, "AMBIGUOUS": 8,
    }
    assert Counter(r["scenario_style"] for r in rows) == {
        "work_ledger": 16, "support_dialogue": 16,
        "change_log": 16, "handover_memo": 16,
    }
    assert all(r["annotation_origin"] == "AI_AUTHORED" for r in rows)
    assert all(r["human_verified"] is False for r in rows)
    assert all(r["source_provenance"]["authored_before_resolver"] for r in rows)
    assert all(r["source_provenance"]["authored_before_generation"] for r in rows)
    dev = data.load_evidence_efficiency_records("development", require_review=False)
    confirm = data.load_evidence_efficiency_records("confirmation", require_review=False)
    assert {r["family_id"] for r in dev} == data.DEVELOPMENT_FAMILIES
    assert {r["family_id"] for r in confirm} == data.CONFIRMATION_FAMILIES
    for key in ("family_id", "event_id", "document_id", "parent_document_id", "document_sha256"):
        assert {r[key] for r in dev}.isdisjoint(r[key] for r in confirm)


def test_same_surface_rivals_and_missing_literal_evidence_are_preserved():
    rows = data.load_evidence_efficiency_records(require_review=False)
    for fid in data.ALL_FAMILIES:
        group = [r for r in rows if r["family_id"] == fid]
        assert sum(r["gold"]["label"] == "LINK" for r in group) == 4
        terms = group[0]["terms"]
        shared = set(terms[0]["surfaces"]) & set(terms[1]["surfaces"])
        assert len(shared) == 1
        assert sum(r["target_surface"] in shared for r in group) == 2
        implicit = [r for r in group if r["evidence_design"] == "IMPLICIT_ATTRIBUTE_POSITIVE"]
        assert len(implicit) == 1
        row = implicit[0]
        assert row["gold"]["label"] == "LINK"
        attrs = row["entity_constraints"][row["expected_entity_id"]]
        assert all(v not in row["text"] for k in ("jurisdiction", "temporal_status") for v in attrs[k])
        cross = [r for r in group if r["evidence_design"] == "CROSS_SENTENCE_ATTRIBUTES"]
        assert len(cross) == 1
        attrs = cross[0]["entity_constraints"][cross[0]["expected_entity_id"]]
        assert all(v in cross[0]["text"] for values in attrs.values() for v in values)
        assert all("applicability" not in term for term in terms)
        assert all(r["entity_constraints"] == group[0]["entity_constraints"] for r in group)
    rows[0]["entity_constraints"].clear()
    assert rows[1]["entity_constraints"]


def test_selected_occurrences_and_compositional_full_spans():
    rows = data.load_evidence_efficiency_records(require_review=False)
    repeated = [r for r in rows if r["stratum"].startswith("repeated_")]
    assert len(repeated) == 8
    for row in repeated:
        assert row["text"].count(row["target_surface"]) >= 2
        assert row["target_full_span"]["start"] > row["text"].index(row["target_surface"])
        assert row["expected_entity_id"] is None
    for row in rows:
        core, full = row["target_core_span"], row["target_full_span"]
        assert row["text"][full["start"]:full["end"]] == row["target_surface"]
        assert full["start"] <= core["start"] < core["end"] <= full["end"]
        if row["gold"]["label"] == "COMPOSITIONAL":
            assert core["end"] < full["end"]
            assert row["target_surface"].endswith("담당자")


def test_exclusion_audit_covers_prior_tracked_source_and_new_names():
    source = artifact()
    proof = json.loads(data.EXCLUSION_FILE.read_text())
    names = {v for f in source["families"] for t in f["terms"]
             for v in [t["canonical"], *t["surfaces"]]}
    assert len(names) == 40
    assert set(proof["new_lexical_names"]) == names
    assert proof["new_name_string_overlap_count"] == 0
    assert proof["collisions"] == []
    root = data.CASES_FILE.parents[3]
    paths = {item["path"] for item in proof["tracked_json_yaml_source_files"]}
    assert "eval/fixtures/routing_confirmation/source_gold.json" in paths
    assert "eval/data/review_business_cases.json" in paths
    for item in proof["tracked_json_yaml_source_files"]:
        raw = (root / item["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        assert not any(name in raw.decode() for name in names)


@pytest.mark.parametrize("field", ["event_id", "document_id", "parent_document_id"])
def test_source_clusters_cannot_leak_across_family_split(field):
    source = artifact()
    source["families"][1]["cases"][0][field] = source["families"][0]["cases"][0][field]
    with pytest.raises(ValueError, match="identities"):
        data.validate_source_artifact(source)


@pytest.mark.parametrize("mutation", ["text", "span", "gold", "family_split", "implicit"])
def test_substantive_source_mutation_is_rejected(mutation):
    source = artifact()
    row = source["families"][0]["cases"][0]
    if mutation == "text":
        row["text"] += "changed"
    elif mutation == "span":
        row["target_full_span"]["start"] += 1
    elif mutation == "gold":
        row["expected_entity_id"] = "global:ee26-family-02-a"
        row["gold"]["entity_ref"] = row["expected_entity_id"]
    elif mutation == "family_split":
        source["families"][0]["evaluation_split"] = "confirmation"
    else:
        row = source["families"][0]["cases"][3]
        row["text"] += " 대한민국 현행"
        row["document_sha256"] = hashlib.sha256(row["text"].encode()).hexdigest()
    with pytest.raises(ValueError):
        data.validate_source_artifact(source)


def test_source_byte_seal_and_review_required_by_default(tmp_path):
    rows = data.load_evidence_efficiency_records()
    assert len(rows) == 64
    assert all(r["source_provenance"]["independent_ai_reviewed"] for r in rows)
    assert data.file_sha256(data.REVIEW_FILE) == data.REVIEW_SHA256
    changed = tmp_path / "changed.json"
    changed.write_bytes(data.CASES_FILE.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="source/gold seal"):
        data.load_evidence_efficiency_records(path=changed, require_review=False)
    with pytest.raises(ValueError, match="review is required"):
        data.load_evidence_efficiency_records(review_path=tmp_path / "missing.json")
    with pytest.raises(ValueError, match="split"):
        data.load_evidence_efficiency_records("test")


@pytest.mark.parametrize("mutation", ["author", "case_coverage", "after_resolver", "after_generation", "human", "disagreement"])
def test_even_resealed_review_must_meet_complete_independent_preinference_contract(tmp_path, monkeypatch, mutation):
    source = artifact()
    review = dict(
        schema_version=1, status="APPROVED", source_sha256=data.SOURCE_SHA256,
        reviewer="independent-test-reviewer",
        reviewed_case_ids=sorted(r["case_id"] for f in source["families"] for r in f["cases"]),
        reviewed_before_resolver=True, reviewed_before_generation=True,
        human_verified=False, unresolved_disagreements=0,
    )
    if mutation == "author":
        review["reviewer"] = source["authored_by"]
    elif mutation == "case_coverage":
        review["reviewed_case_ids"].pop()
    elif mutation == "after_resolver":
        review["reviewed_before_resolver"] = False
    elif mutation == "after_generation":
        review["reviewed_before_generation"] = False
    elif mutation == "human":
        review["human_verified"] = True
    else:
        review["unresolved_disagreements"] = 1
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review))
    monkeypatch.setattr(data, "REVIEW_SHA256", data.file_sha256(path))
    with pytest.raises(ValueError, match="complete pre-inference"):
        data.load_evidence_efficiency_records(review_path=path)


def test_sealed_review_enables_only_source_loading(tmp_path, monkeypatch):
    source = artifact()
    review = dict(
        schema_version=1, status="APPROVED", source_sha256=data.SOURCE_SHA256,
        reviewer="independent-test-reviewer",
        reviewed_case_ids=sorted(r["case_id"] for f in source["families"] for r in f["cases"]),
        reviewed_before_resolver=True, reviewed_before_generation=True,
        human_verified=False, unresolved_disagreements=0,
    )
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review))
    monkeypatch.setattr(data, "REVIEW_SHA256", data.file_sha256(path))
    rows = data.load_evidence_efficiency_records(review_path=path)
    assert len(rows) == 64
    assert all(r["source_provenance"]["independent_ai_reviewed"] for r in rows)
    assert all(r["source_provenance"]["review_sha256"] == data.file_sha256(path) for r in rows)
    parsed = ast.parse(Path(data.__file__).read_text())
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            assert all(n.name.split(".")[0] not in {"ktrf", "eval", "torch", "transformers"} for n in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module.split(".")[0] not in {"ktrf", "eval", "torch", "transformers"}
