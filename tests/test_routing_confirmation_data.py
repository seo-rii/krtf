"""Source/gold exclusion, occurrence identity and independent review checks."""
from collections import Counter
import hashlib
import importlib.util
import json

import pytest

from eval import routing_confirmation_data as data


def artifact():
    return json.loads(data.CASES_FILE.read_text())


def test_predeclared_split_and_annotation_origin():
    rows = data.load_routing_confirmation_records(require_review=False)
    assert len(rows) == 192
    assert Counter(r["evaluation_split"] for r in rows) == {
        "development": 64, "confirmation": 128,
    }
    assert Counter(r["gold"]["label"] for r in rows) == {
        "LINK": 96, "NIL": 54, "COMPOSITIONAL": 12, "NON_MENTION": 6, "AMBIGUOUS": 24,
    }
    assert all(r["human_verified"] is False for r in rows)
    assert all(r["source_provenance"]["authored_before_resolver"] for r in rows)
    assert len({r["document_sha256"] for r in rows}) == 192
    dev = data.load_routing_confirmation_records("development", require_review=False)
    confirm = data.load_routing_confirmation_records("confirmation", require_review=False)
    assert {r["family_id"] for r in dev}.isdisjoint(r["family_id"] for r in confirm)
    assert {r["family_id"] for r in dev} == data.DEVELOPMENT_FAMILIES
    assert {r["family_id"] for r in confirm} == data.CONFIRMATION_FAMILIES
    with pytest.raises(ValueError, match="split"):
        data.load_routing_confirmation_records("test")


def test_collision_controls_preserve_unique_surfaces_and_entity_level_constraints():
    rows = data.load_routing_confirmation_records(require_review=False)
    for family in data.ALL_FAMILIES:
        group = [r for r in rows if r["family_id"] == family]
        terms = group[0]["terms"]
        shared = set(terms[0]["surfaces"]) & set(terms[1]["surfaces"])
        assert len(shared) == 1
        assert sum(r["target_surface"] in shared for r in group) == 2
        assert sum(r["gold"]["label"] == "LINK" for r in group) == 4
        assert all(r["entity_constraints"] == group[0]["entity_constraints"] for r in group)
        assert all("applicability" not in term for term in terms)
        for r in group:
            if r["expected_entity_id"] is None:
                continue
            constraints = r["entity_constraints"][r["expected_entity_id"]]
            # This is an explicit, disclosed source design: the literal
            # consistency gate has all required positive evidence available.
            assert all(v in r["text"] for values in constraints.values() for v in values)
    rows[0]["entity_constraints"].clear()
    assert rows[1]["entity_constraints"]  # per-record isolation, no mutable leak


def test_repeated_targets_refer_to_selected_occurrence_not_first_surface():
    rows = data.load_routing_confirmation_records(require_review=False)
    repeated = [r for r in rows if r["stratum"].startswith("repeated_")
                or r["stratum"] == "exception_distinct_permission"]
    assert len(repeated) == 30
    for row in repeated:
        surface = row["target_surface"]
        assert row["text"].count(surface) >= 2
        assert row["target_full_span"]["start"] > row["text"].index(surface)
        assert row["expected_entity_id"] is None
    for row in rows:
        core, full = row["target_core_span"], row["target_full_span"]
        assert row["text"][full["start"]:full["end"]] == row["target_surface"]
        assert full["start"] <= core["start"] < core["end"] <= full["end"]
        if row["gold"]["label"] == "COMPOSITIONAL":
            assert core["end"] < full["end"]


def test_prior_source_names_and_families_are_excluded():
    source = artifact()
    proof = json.loads(data.EXCLUSION_FILE.read_text())
    new_names = {
        v for f in source["families"] for t in f["terms"]
        for v in [t["canonical"], *t["surfaces"]]
    }
    assert not new_names & set(proof["prior_business_names"])
    assert not data.ALL_FAMILIES & set(proof["prior_business_family_ids"])
    root = data.CASES_FILE.parents[3]
    for old in proof["tracked_json_yaml_source_files"]:
        path = root / old["path"]
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == old["sha256"]
        assert not any(name in raw.decode() for name in new_names)


def test_source_builder_reproduces_frozen_review_artifact():
    path = data.FIXTURE_DIR / "author_source.py"
    spec = importlib.util.spec_from_file_location("routing_source_authorship", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.make_source() == artifact()
    assert data.file_sha256(data.CASES_FILE) == data.SOURCE_SHA256


@pytest.mark.parametrize("mutate, message", [
    (lambda a: a["families"][0].update(evaluation_split="confirmation"), "split"),
    (lambda a: a["families"][0]["cases"][0].update(document_sha256="0" * 64), "content hash"),
    (lambda a: a["families"][0]["cases"][0]["target_full_span"].update(start=0), "spans"),
    (lambda a: a["families"][0]["cases"][0].update(expected_entity_id="global:other-family"), "gold entity"),
    (lambda a: a["families"][0]["terms"][0]["applicability"].update(scope=["invented"]), "definition"),
    (lambda a: a["families"][0]["terms"][1].update(key=a["families"][0]["terms"][0]["key"]), "identity"),
    (lambda a: a["families"][0]["cases"][0]["gold"].update(label="NIL"), "gold entity"),
    (lambda a: a["families"][0]["cases"][0]["qa"].update(answers=["unrelated"]), "QA identity"),
    (lambda a: a.update(human_verified=True), "AI annotation"),
])
def test_structural_tampering_is_rejected_independently_of_byte_hash(mutate, message):
    source = artifact()
    mutate(source)
    with pytest.raises(ValueError, match=message):
        data.validate_source_artifact(source)


def test_cross_family_candidate_reference_is_rejected_even_if_gold_fields_agree():
    source = artifact()
    row = source["families"][0]["cases"][0]
    row["expected_entity_id"] = "global:" + source["families"][1]["terms"][0]["key"]
    row["gold"]["entity_ref"] = row["expected_entity_id"]
    with pytest.raises(ValueError, match="same source glossary family"):
        data.validate_source_artifact(source)


def test_mutated_document_cannot_reuse_old_text_digest(tmp_path):
    source = artifact()
    source["families"][0]["cases"][0]["text"] += "변경"
    target = tmp_path / "source.json"
    target.write_text(json.dumps(source, ensure_ascii=False))
    with pytest.raises(ValueError, match="immutable source/gold seal"):
        data.load_routing_confirmation_records(path=target, require_review=False)


def test_review_cannot_be_bypassed_by_missing_or_self_authored_seal(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "REVIEW_SHA256", None)
    with pytest.raises(ValueError, match="review is required before inference"):
        data.load_routing_confirmation_records()
    rows = data.load_routing_confirmation_records(require_review=False)
    review = {
        "schema_version": 1,
        "status": "APPROVED",
        "source_sha256": data.SOURCE_SHA256,
        "reviewer": artifact()["authored_by"],
        "reviewed_case_ids": sorted(r["case_id"] for r in rows),
        "reviewed_before_resolver": True,
        "reviewed_before_generation": True,
        "human_verified": False,
        "unresolved_disagreements": 0,
    }
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review))
    monkeypatch.setattr(data, "REVIEW_SHA256", data.file_sha256(path))
    with pytest.raises(ValueError, match="independent complete"):
        data.load_routing_confirmation_records(review_path=path)
    review["reviewer"] = "independent-test-reviewer"
    review["reviewed_case_ids"].pop()
    path.write_text(json.dumps(review))
    monkeypatch.setattr(data, "REVIEW_SHA256", data.file_sha256(path))
    with pytest.raises(ValueError, match="independent complete"):
        data.load_routing_confirmation_records(review_path=path)


def test_approved_review_covers_exact_source_before_any_inference(tmp_path, monkeypatch):
    rows = data.load_routing_confirmation_records(require_review=False)
    review = {
        "schema_version": 1,
        "status": "APPROVED",
        "source_sha256": data.SOURCE_SHA256,
        "reviewer": "independent-test-reviewer",
        "reviewed_case_ids": sorted(r["case_id"] for r in rows),
        "reviewed_before_resolver": True,
        "reviewed_before_generation": True,
        "human_verified": False,
        "unresolved_disagreements": 0,
    }
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review))
    monkeypatch.setattr(data, "REVIEW_SHA256", data.file_sha256(path))
    reviewed = data.load_routing_confirmation_records(review_path=path)
    assert len(reviewed) == 192
    assert all(r["source_provenance"]["independent_ai_reviewed"] for r in reviewed)
    review["reviewed_before_resolver"] = False
    path.write_text(json.dumps(review))
    monkeypatch.setattr(data, "REVIEW_SHA256", data.file_sha256(path))
    with pytest.raises(ValueError, match="pre-inference"):
        data.load_routing_confirmation_records(review_path=path)
