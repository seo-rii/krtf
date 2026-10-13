"""Input-contract factorial integrity and execution-gate diagnostics."""
from collections import Counter
from copy import deepcopy
import json

import pytest

import eval.product_contract_probe as probe
from eval.product_utility import build_requests


def _rendered_cards(row):
    data = row["rendered_data"]
    if "terminology_data" in data:
        return data["terminology_data"]
    return data["resolved_terms"] + [card for mention in data["ambiguous_mentions"]
                                     for card in mention["candidates"]]


def _correct_outputs(rows):
    return [{"case_id": r["case_id"], "condition": r["condition"],
             "response": {"answer": r["expected_answer"], "entity_id": r["expected_entity_id"]}}
            for r in rows]


def test_original_input_bytes_and_local_metadata_are_unchanged():
    baseline = {r["case_id"]: r for r in build_requests()
                if r["condition"] == probe.ORIGINAL_CONDITION}
    for row in probe.build_contract_requests():
        original = baseline[row["case_id"]]
        assert row["system"] == original["system"]
        assert row["cards"] == original["cards"]
        assert row["pack"] == original["pack"]
        assert row["candidate_hash"] == original["candidate_hash"]
        if row["condition"] == "original":
            assert row["user"].encode() == original["user"].encode()
            assert row["estimated_input_tokens"] == original["estimated_input_tokens"]
        assert row["user"].split("\n", 1)[1] == original["user"].split("\n", 1)[1]
        assert json.loads(row["user"].split("\n", 1)[0]) == row["rendered_data"]


def test_all_candidate_facts_and_surface_factor_are_fixed_across_schemas():
    rows = probe.build_contract_requests()
    for case in {r["case_id"] for r in rows}:
        variants = [r for r in rows if r["case_id"] == case]
        assert len({r["candidate_hash"] for r in variants}) == 1
        assert len({r["alias_binding_hash"] for r in variants}) == 1
        for row in variants:
            cards = _rendered_cards(row)
            facts = [{key: value for key, value in card.items() if key != "surface"} for card in cards]
            assert facts == row["cards"]
            assert all(("surface" in card) == row["factors"]["surface_binding"] for card in cards)
            assert all(card.get("surface", "ABC") == "ABC" for card in cards)
        for conditions in (("original", "schema_only"), ("surface_only", "both")):
            assert _rendered_cards(next(r for r in variants if r["condition"] == conditions[0])) == _rendered_cards(next(r for r in variants if r["condition"] == conditions[1]))


def test_surface_is_read_from_pack_binding_not_ground_truth(monkeypatch):
    originals = build_requests()
    target = next(r for r in originals if r["condition"] == probe.ORIGINAL_CONDITION
                  and r["case_id"] == "tenant-a:document_qa")
    original_candidate_hash = target["candidate_hash"]
    target["pack"]["resolved_terms"][0]["mentions"][0]["surface"] = "pack-only-marker"
    target["expected_entity_id"] = "not-a-pack-binding"
    target["expected_answer"] = "not-a-surface"
    monkeypatch.setattr(probe, "build_requests", lambda: deepcopy(originals))
    rows = [r for r in probe.build_contract_requests() if r["case_id"] == target["case_id"]]
    assert all(r["candidate_hash"] == original_candidate_hash for r in rows)
    assert all(_rendered_cards(r)[0]["surface"] == "pack-only-marker"
               for r in rows if r["factors"]["surface_binding"])


def test_ambiguous_and_missing_cards_never_become_resolved():
    for row in probe.build_contract_requests():
        if row["world"] not in ("ambiguous", "missing"):
            continue
        assert not any(c["status"] == "RESOLVED" for c in _rendered_cards(row))
        if row["factors"]["policy_named_fields"]:
            assert row["rendered_data"]["resolved_terms"] == []
            assert all(set(a) == {"candidates"} for a in row["rendered_data"]["ambiguous_mentions"])
        if row["world"] == "missing":
            assert _rendered_cards(row) == []


def test_coverage_and_rotating_condition_order_are_balanced_and_stateless():
    rows = probe.build_contract_requests()
    assert rows == probe.build_contract_requests()
    assert len(rows) == probe.CONTRACT_PROTOCOL["request_count"] == 56
    assert Counter(r["condition"] for r in rows) == {c: 14 for c in probe.CONDITIONS}
    assert len({(r["case_id"], r["condition"]) for r in rows}) == 56
    for index in range(14):
        group = rows[index * 4:index * 4 + 4]
        assert len({r["case_id"] for r in group}) == 1
        offset = (index // 2) % 4
        assert [r["condition"] for r in group] == list(probe.CONDITIONS[offset:] + probe.CONDITIONS[:offset])
        assert [r["condition_position"] for r in group] == [0, 1, 2, 3]
    for task in ("document_qa", "structured_routing"):
        for position in range(4):
            frequencies = Counter(r["condition"] for r in rows
                                  if r["condition_position"] == position and r["task"] == task)
            assert set(frequencies.values()) == {1, 2}
    first, second = rows[:2]
    first["pack"]["resolved_terms"].clear()
    assert second["pack"]["resolved_terms"]


def test_grade_reports_answerable_tasks_abstentions_swaps_and_paired_changes():
    rows = probe.build_contract_requests()
    outputs = _correct_outputs(rows)
    next(o for o in outputs if o["case_id"] == "tenant-a:document_qa" and o["condition"] == "original")["response"]["answer"] = None
    next(o for o in outputs if o["case_id"] == "tenant-b:document_qa" and o["condition"] == "both")["response"]["answer"] = None
    grade = probe.grade_contract_outputs(rows, outputs)
    assert grade["kind"] == "recorded_model_outputs"
    assert grade["missing_outputs"] == 0
    original = grade["contract_diagnostics"]["original"]
    assert original["answerable_qa"] == {"success": 4, "observed": 5, "expected": 5}
    assert original["routing_valid_ids"] == {"success": 5, "observed": 5, "expected": 5}
    assert original["over_abstention"] == {"count": 1, "expected_answerable": 10}
    assert original["safe_abstention"] == {"count": 4, "expected_unanswerable": 4}
    both = grade["paired_vs_original"]["both"]
    assert both["paired_cases"] == 14
    assert both["beneficial_changes"] == both["harmful_changes"] == 1
    assert both["beneficial_case_ids"] == ["tenant-a:document_qa"]
    assert both["harmful_case_ids"] == ["tenant-b:document_qa"]
    assert grade["metrics"]["both"]["correct_meaning_switch"] == 3


def test_wrong_short_id_and_ambiguous_candidate_are_guard_rejected():
    rows = probe.build_contract_requests()
    ambiguous = next(r for r in rows if r["case_id"] == "ambiguous:structured_routing")
    candidate = ambiguous["cards"][0]["entity_id"]
    outputs = [{"case_id": "tenant-a:structured_routing", "condition": "both",
                "response": {"entity_id": "billing"}},
               {"case_id": "ambiguous:structured_routing", "condition": "both",
                "response": {"entity_id": candidate}}]
    grade = probe.grade_contract_outputs(rows, outputs)
    diagnostic = grade["contract_diagnostics"]["both"]
    assert diagnostic["wrong_raw_ids"] == diagnostic["execution_guard_rejections"] == 2
    assert diagnostic["accepted_unauthorized_ids"] == 0
    assert diagnostic["routing_valid_ids"]["success"] == 0
    assert diagnostic["safe_abstention"]["count"] == 0
    assert grade["metrics"]["both"]["task_success"] == 0


def test_missing_and_malformed_responses_are_not_safe_abstentions():
    rows = probe.build_contract_requests()
    outputs = [{"case_id": "missing:document_qa", "condition": "original",
                "response": {"answer": None}},
               {"case_id": "ambiguous:structured_routing", "condition": "original",
                "response": {}}]
    grade = probe.grade_contract_outputs(rows, outputs)
    assert grade["missing_outputs"] == 54
    original = grade["contract_diagnostics"]["original"]
    assert original["missing"] == 12
    assert original["malformed"] == 1
    assert original["safe_abstention"]["count"] == 1
    assert grade["contract_diagnostics"]["both"]["safe_abstention"]["count"] == 0
    assert grade["paired_vs_original"]["both"]["paired_cases"] == 0
    with pytest.raises(ValueError, match="duplicate"):
        probe.grade_contract_outputs(rows, outputs + outputs[:1])
