"""Candidate/path invariants that matter for the fixed-context experiment."""
from collections import Counter
from copy import deepcopy
import hashlib
import json

import pytest

from eval.context_ranking_corpus import (
    FIXTURES, SPLIT_SEED, TEST_FAMILIES, TUNE_FAMILIES, build_cases,
    family_split, hypotheses, load_cases, validate_cases,
)
from ktrf.rerank import rank_hypotheses


@pytest.fixture(scope="module")
def cases():
    return build_cases()


def test_original_documents_and_complete_catalog_preserved(cases):
    assert len(cases) == 64
    assert Counter(case["semantic_label"] for case in cases) == {
        "LINK": 32, "AMBIGUOUS": 8, "NIL": 8, "COMPOSITIONAL": 8, "NON_MENTION": 8,
    }
    for collection, path in FIXTURES.items():
        families = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        originals = {document["document_id"]: (family, document)
                     for family in families for document in family["documents"]}
        actual = [case for case in cases if case["source_collection"] == collection]
        assert len(actual) == 32
        for case in actual:
            family, document = originals[case["document_id"]]
            assert case["text"] == document["text"]
            assert case["target_surface"] == document["target_surface"]
            assert case["world_gold"] == document["gold"]
            assert case["knowledge_text"] == family["knowledge_document"]["text"]
            assert case["catalog_terms"] == family["terms"]
            assert len(case["candidates"]) == 2
            assert [candidate["entity_id"] for candidate in case["candidates"]] == [
                "global:" + term["key"] for term in family["terms"]]
            assert case["human_verified"] is False
            assert "Previously inspected" in case["evaluation_history"]


def test_family_split_predeclared_and_shared_across_source_collections(cases):
    hash_order = sorted(TUNE_FAMILIES + TEST_FAMILIES,
                        key=lambda family: (hashlib.sha256((SPLIT_SEED + family).encode()).hexdigest(), family))
    assert tuple(hash_order[:4]) == TUNE_FAMILIES
    assert tuple(hash_order[4:]) == TEST_FAMILIES
    assert Counter(case["split"] for case in cases) == {"tune": 32, "test": 32}
    groups = {split: {case["family_id"] for case in cases if case["split"] == split}
              for split in ("tune", "test")}
    assert not groups["tune"] & groups["test"]
    for family in TUNE_FAMILIES + TEST_FAMILIES:
        assert {case["split"] for case in cases if case["family_id"] == family} == {family_split(family)}


def test_gold_changes_cannot_change_candidates_paths_or_partition(cases, tmp_path):
    changed_paths = {}
    for collection, path in FIXTURES.items():
        families = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        for family in families:
            # Swap the authored positive answer. Source, catalog and retrieval
            # inputs stay untouched; this is an oracle-leakage regression.
            for document in family["documents"]:
                if document["gold"]["label"] == "LINK":
                    other = next(term for term in family["terms"]
                                 if "global:" + term["key"] != document["gold"]["entity_ref"])
                    document["gold"]["entity_ref"] = "global:" + other["key"]
                    document["expected_answer"] = other["short_definition"]
                    document["rationale"] = "Deliberately changed grading-only test metadata."
        changed_path = tmp_path / (collection + ".jsonl")
        changed_path.write_text("\n".join(json.dumps(family, ensure_ascii=False) for family in families), encoding="utf-8")
        changed_paths[collection] = changed_path
    changed = build_cases(changed_paths)
    for before, after in zip(cases, changed):
        assert before["candidates"] == after["candidates"]
        assert before["candidate_sha256"] == after["candidate_sha256"]
        assert before["core_span"] == after["core_span"]
        assert before["full_surface_span"] == after["full_surface_span"]
        assert before["split"] == after["split"]
        assert before["text"] == after["text"]
        if before["semantic_label"] == "LINK":
            assert before["expected_entity_id"] != after["expected_entity_id"]


def test_genuine_ambiguity_requires_abstention_instead_of_two_positive_targets(cases):
    ambiguous = [case for case in cases if case["semantic_label"] == "AMBIGUOUS"]
    assert len(ambiguous) == 8
    assert all(case["expected_entity_id"] is None and case["gold"] == [] for case in ambiguous)
    assert all(len(hypotheses(case)) == 2 for case in ambiguous)


def test_actual_typed_role_paths_block_even_arbitrarily_large_scores(cases):
    class AlwaysHigh:
        def score_pairs(self, pairs):
            return [1_000_000.0 + index for index, _ in enumerate(pairs)]

    roles = [case for case in cases if case["semantic_label"] == "COMPOSITIONAL"]
    assert len(roles) == 8
    for case in roles:
        candidate_paths = [h.path for h in hypotheses(case)]
        assert len(candidate_paths) == 2 and candidate_paths[0] == candidate_paths[1]
        for path in candidate_paths:
            assert path.full_identity == "DISTINCT" and path.relation == "ROLE_OF"
            assert path.core_span == tuple(case["core_span"])
            assert path.surface_span == tuple(case["target_span"])
            assert path.core != case["target_surface"]
            assert path.residual
        ranked = rank_hypotheses(case["text"], hypotheses(case), AlwaysHigh(), "path")
        assert all(not row.commit_allowed and "typed_derivative" in row.guard_reasons for row in ranked)


def test_jsonl_roundtrip_uses_frozen_source_and_reconstructs_structural_paths(cases, tmp_path):
    frozen = tmp_path / "frozen.jsonl"
    frozen.write_text("\n".join(json.dumps(case, ensure_ascii=False) for case in cases), encoding="utf-8")
    restored = load_cases(frozen)
    assert len(restored) == 64
    assert [[h.path for h in hypotheses(case)] for case in restored] == [
        [h.path for h in hypotheses(case)] for case in cases]
    for original, loaded in zip(cases, restored):
        assert loaded["document_sha256"] == original["document_sha256"]
        assert loaded["candidate_sha256"] == original["candidate_sha256"]


@pytest.mark.parametrize("tamper,pattern", [
    (lambda case: case["candidates"].pop(), "candidate hash"),
    (lambda case: case.update(text=case["text"] + "x"), "source hash"),
    (lambda case: case.update(split="test" if case["split"] == "tune" else "tune"), "family split"),
    (lambda case: case.update(target_span=[0, 1]), "target offset"),
    (lambda case: case.update(human_verified=True), "authorship"),
])
def test_frozen_identity_and_candidate_tampering_rejected(cases, tamper, pattern):
    changed = deepcopy(cases)
    tamper(changed[0])
    with pytest.raises(ValueError, match=pattern):
        validate_cases(changed)


def test_budget_cannot_prune_fixed_catalog(cases):
    with pytest.raises(ValueError, match="cannot remove"):
        hypotheses(cases[0], budget=1)
    assert len(hypotheses(cases[0], budget=2)) == 2


def test_rehashing_forged_role_path_cannot_bypass_shared_guard(cases):
    changed = deepcopy(cases)
    case = next(row for row in changed if row["semantic_label"] == "COMPOSITIONAL")
    for candidate in case["candidates"]:
        candidate["path"].update(full_identity="SAME", relation="IDENTITY")
    case["candidate_sha256"] = hashlib.sha256(json.dumps(
        case["candidates"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    with pytest.raises(ValueError, match="actual shared structural path"):
        validate_cases(changed)
