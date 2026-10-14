"""Occurrence, candidate and semantic guard contracts of the new challenge."""

from collections import Counter
from copy import deepcopy
import json

import pytest

from eval.context_ranking_challenge import (
    FIXTURE, FAMILIES, LABEL_COUNTS, PARTITION, blind_binding_map,
    blind_projection, build_cases, hypotheses, load_cases, validate_cases,
)
from eval.context_ranking_corpus import FIXTURES as PRIOR_FIXTURES, _digest
from ktrf.rerank import rank_hypotheses


@pytest.fixture(scope="module")
def cases():
    return build_cases()


def test_new_family_document_and_event_inventory(cases):
    assert len(cases) == 384
    assert len({case["document_id"] for case in cases}) == 336
    assert len({case["case_id"] for case in cases}) == 384
    assert {case["family_id"] for case in cases} == set(FAMILIES)
    assert Counter(case["semantic_label"] for case in cases) == LABEL_COUNTS
    assert {case["split"] for case in cases} == {PARTITION}
    assert all(case["human_verified"] is False and case["seen_prior_context"] is False for case in cases)
    assert all("not a sealed real-world audit" in case["evaluation_history"] for case in cases)


def test_catalog_keys_aliases_and_canonicals_disjoint_from_prior_experiment(cases):
    prior_keys, prior_surfaces = set(), set()
    for path in PRIOR_FIXTURES.values():
        for line in path.read_text(encoding="utf-8").splitlines():
            family = json.loads(line)
            for term in family["terms"]:
                prior_keys.add(term["key"])
                prior_surfaces.update(term["surfaces"])
                prior_surfaces.add(term["canonical"])
    for case in cases:
        assert len(case["candidates"]) == 2
        assert [candidate["entity_id"] for candidate in case["candidates"]] == [
            "global:" + term["key"] for term in case["catalog_terms"]]
        for term in case["catalog_terms"]:
            assert term["key"] not in prior_keys
            assert not set(term["surfaces"]) & prior_surfaces
            assert term["canonical"] not in prior_surfaces


def test_original_source_catalog_and_targets_preserved(cases):
    families = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]
    authored = {(document["document_id"], target["target_id"]): (family, document, target)
                for family in families for document in family["documents"] for target in document["targets"]}
    for case in cases:
        family, document, target = authored[(case["document_id"], case["target_id"])]
        assert case["text"] == document["text"] == case["source_text"]
        assert case["catalog_terms"] == family["terms"]
        assert case["world_gold"] == target["gold"]
        assert case["decisive_evidence"] == target["decisive_evidence"]
        assert case["target_surface"] == target["surface"]
        assert case["target_occurrence"] == target["occurrence"]
        start, end = case["target_span"]
        assert case["text"][start:end] == target["surface"]


def test_multitarget_documents_keep_both_offsets_and_one_document_cluster(cases):
    groups = {}
    for case in cases:
        if case["target_group_id"]:
            groups.setdefault(case["target_group_id"], []).append(case)
    assert len(groups) == 48
    for document_id, targets in groups.items():
        assert len(targets) == 2
        assert {target["document_id"] for target in targets} == {document_id}
        assert len({target["document_sha256"] for target in targets}) == 1
        assert len({target["text"] for target in targets}) == 1
        assert {target["target_occurrence"] for target in targets} == {0, 1}
        assert len({tuple(target["target_span"]) for target in targets}) == 2
        assert len({target["expected_entity_id"] for target in targets}) == 2
        assert all(target["semantic_label"] == "LINK" for target in targets)


def test_changed_authored_gold_cannot_change_candidate_inputs_or_occurrence(cases, tmp_path):
    families = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]
    for family in families:
        for document in family["documents"]:
            for target in document["targets"]:
                if target["gold"]["label"] == "LINK":
                    target["gold"]["entity_ref"] = next(
                        "global:" + term["key"] for term in family["terms"]
                        if "global:" + term["key"] != target["gold"]["entity_ref"])
                    target["rationale"] = "Intentionally altered grading metadata for the leakage regression."
    changed_path = tmp_path / "changed-labels.jsonl"
    changed_path.write_text("\n".join(json.dumps(family, ensure_ascii=False) for family in families), encoding="utf-8")
    changed = build_cases(changed_path)
    for before, after in zip(cases, changed):
        for field in ("text", "catalog_terms", "candidates", "candidate_sha256", "catalog_sha256",
                      "document_sha256", "target_span", "core_span", "snapshot_id", "split"):
            assert before[field] == after[field]
        if before["semantic_label"] == "LINK":
            assert before["expected_entity_id"] != after["expected_entity_id"]
    assert blind_projection(cases) == blind_projection(changed)


def test_blind_review_projection_excludes_generator_metadata_and_authored_answers(cases):
    projected = blind_projection(cases)
    binding = blind_binding_map(cases)
    assert len(projected) == len(binding) == 384
    allowed = {"case_id", "document_id", "family_id", "text", "target_surface", "target_occurrence",
               "target_span", "catalog_terms"}
    originals = {case["case_id"]: case for case in cases}
    assert projected == sorted(projected, key=lambda row: row["case_id"])
    for blinded in projected:
        original = originals[binding[blinded["case_id"]]]
        assert set(blinded) == allowed
        assert binding[blinded["case_id"]] == original["case_id"]
        assert blinded["case_id"] != original["case_id"]
        assert blinded["family_id"] != original["family_id"]
        assert blinded["document_id"] != original["document_id"]
        assert blinded["text"] == original["text"]
        assert blinded["catalog_terms"] == original["catalog_terms"]
        assert blinded["target_span"] == original["target_span"]


def test_blind_review_can_correct_a_positive_to_nil_without_forcing_designed_totals(cases):
    changed = deepcopy(cases)
    corrected = next(case for case in changed if case["semantic_label"] == "LINK")
    corrected.update(world_gold={"label": "NIL", "entity_ref": None}, semantic_label="NIL",
                     expected_entity_id=None, expected_answer=None, gold=[], ambiguity="nil")
    corrected["rationale"] = "A blind annotation correction may change labels without changing model inputs."
    corrected["authored_annotation_sha256"] = _digest({
        "gold": corrected["world_gold"], "decisive_evidence": corrected["decisive_evidence"],
        "rationale": corrected["rationale"],
    })
    validate_cases(changed)
    assert Counter(case["semantic_label"] for case in changed)["LINK"] == 239
    assert blind_projection(changed) == blind_projection(cases)
    assert [case["candidate_sha256"] for case in changed] == [case["candidate_sha256"] for case in cases]


def test_genuine_ambiguity_and_nil_have_no_positive_ranking_identity(cases):
    negatives = [case for case in cases if case["semantic_label"] != "LINK"]
    assert len(negatives) == 144
    assert all(case["gold"] == [] and case["expected_entity_id"] is None for case in negatives)
    assert all(case["expected_answer"] is None and len(hypotheses(case)) == 2 for case in negatives)


def test_role_paths_preserve_distinct_full_surface_guard_under_arbitrary_scores(cases):
    class AlwaysHigh:
        def score_pairs(self, pairs):
            return [10_000.0 + index for index, _ in enumerate(pairs)]

    roles = [case for case in cases if case["semantic_label"] == "COMPOSITIONAL"]
    assert len(roles) == 24
    for case in roles:
        fixed = hypotheses(case)
        assert len(fixed) == 2 and fixed[0].path == fixed[1].path
        assert all(h.path.full_identity == "DISTINCT" and h.path.relation == "ROLE_OF" for h in fixed)
        assert all(h.path.surface_span == tuple(case["target_span"]) for h in fixed)
        assert all(h.path.core_span == tuple(case["core_span"]) for h in fixed)
        assert all(h.path.core != case["target_surface"] for h in fixed)
        ranked = rank_hypotheses(case["text"], fixed, AlwaysHigh(), "path", radius=len(case["text"]))
        assert all(not row.commit_allowed and "typed_derivative" in row.guard_reasons for row in ranked)


def test_frozen_cases_roundtrip_reconstructs_production_paths(cases, tmp_path):
    frozen = tmp_path / "cases.jsonl"
    frozen.write_text("\n".join(json.dumps(case, ensure_ascii=False) for case in cases), encoding="utf-8")
    loaded = load_cases(frozen)
    assert len(loaded) == 384
    assert [[h.path for h in hypotheses(case)] for case in loaded] == [[h.path for h in hypotheses(case)] for case in cases]
    assert blind_projection(loaded) == blind_projection(cases)


@pytest.mark.parametrize("tamper,pattern", [
    (lambda case: case["candidates"].pop(), "candidate hash"),
    (lambda case: case.update(text=case["text"] + " changed"), "source hash"),
    (lambda case: case.update(split="tune"), "external test"),
    (lambda case: case.update(target_span=[0, 1]), "offset"),
    (lambda case: case.update(target_occurrence=100), "occurrence is absent"),
    (lambda case: case.update(human_verified=True), "authorship"),
    (lambda case: case.update(snapshot_id="other-snapshot"), "snapshot identity"),
    (lambda case: case.update(rationale="Changed after annotation freeze"), "annotation hash"),
])
def test_tampered_identity_inputs_or_annotation_rejected(cases, tamper, pattern):
    changed = deepcopy(cases)
    tamper(changed[0])
    with pytest.raises(ValueError, match=pattern):
        validate_cases(changed)


def test_rehashed_forged_role_path_cannot_remove_production_guard(cases):
    changed = deepcopy(cases)
    case = next(case for case in changed if case["semantic_label"] == "COMPOSITIONAL")
    for candidate in case["candidates"]:
        candidate["path"].update(full_identity="SAME", relation="IDENTITY")
    case["candidate_sha256"] = _digest(case["candidates"])
    with pytest.raises(ValueError, match="actual shared structural path"):
        validate_cases(changed)


def test_rehashed_pruned_candidate_catalog_is_rejected(cases):
    changed = deepcopy(cases)
    changed[0]["candidates"].pop()
    changed[0]["candidate_sha256"] = _digest(changed[0]["candidates"])
    with pytest.raises(ValueError, match="complete catalog"):
        validate_cases(changed)


def test_same_document_cannot_have_conflicting_source_under_two_occurrences(cases):
    changed = deepcopy(cases)
    duplicate = next(case for case in changed if case["target_group_id"])
    sibling = next(case for case in changed if case["document_id"] == duplicate["document_id"]
                   and case["case_id"] != duplicate["case_id"])
    sibling["title"] += " changed"
    with pytest.raises(ValueError, match="share the complete original source"):
        validate_cases(changed)


def test_budget_cannot_prune_the_other_registered_meaning(cases):
    with pytest.raises(ValueError, match="cannot remove"):
        hypotheses(cases[0], budget=1)
    assert len(hypotheses(cases[0], budget=2)) == 2
