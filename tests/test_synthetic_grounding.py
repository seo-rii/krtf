"""Independent authored gold, multi-target rendering and execution safety."""
from copy import deepcopy
import json

import pytest

from eval import synthetic_grounding as suite


def family():
    main = {"key": "meter", "canonical": "광원검침실", "surfaces": ["LUX", "검침실"],
            "short_definition": "건물별 조명 전력 사용량을 검침하는 조직", "type": "organization"}
    other = {"key": "return", "canonical": "반송검토실", "surfaces": ["QZ"],
             "short_definition": "반송한 계측기 포장을 확인하는 조직", "type": "organization"}
    collision = {"key": "queue", "canonical": "배치예약실", "surfaces": ["QZ"],
                 "short_definition": "실험실 배치 작업의 순서를 예약하는 조직", "type": "organization"}
    return {"family_id": "test-meter", "domain": "test", "annotation_origin": "AI_SYNTHETIC",
        "human_verified": False, "authored_by": "synthetic-fixture",
        "worlds": {"base": {"mode": "simple", "terms": [main, other]},
                   "collision": {"mode": "simple", "terms": [main, other, collision]}},
        "cases": [
            {"case_id": "test-meter:linked", "world": "base", "text": "LUX가 검침을 마쳤고 반송검토실은 상자를 점검했다.",
             "target_surface": "LUX", "stratum": "multi_entity", "gold": {"label": "LINK", "entity_ref": "global:meter", "full_identity": "SAME"}, "rationale": "registered meter"},
            {"case_id": "test-meter:absent", "world": "base", "text": "별빛접수소가 신규 신청을 받았다.",
             "target_surface": "별빛접수소", "stratum": "nil", "gold": {"label": "NIL", "entity_ref": None, "full_identity": "SAME"}, "rationale": "not in glossary"},
            {"case_id": "test-meter:role", "world": "base", "text": "검침실장이 회의에 참석했다.",
             "target_surface": "검침실장", "stratum": "derived_role", "gold": {"label": "NIL", "entity_ref": None, "full_identity": "DISTINCT", "core_surface": "검침실", "core_entity_ref": "global:meter"}, "rationale": "person differs from organization"},
            {"case_id": "test-meter:collision", "world": "collision", "text": "QZ가 요청을 처리했다는 기록만 남았다.",
             "target_surface": "QZ", "stratum": "ambiguous", "gold": {"label": "AMBIGUOUS", "entity_ref": None, "full_identity": "SAME"}, "rationale": "two unspecified candidates"}]}


def test_independent_gold_not_overwritten_by_missing_resolver_retrieval(monkeypatch):
    class Empty:
        context_pack = {"resolved_terms": [], "ambiguous_mentions": [], "profile": "qa_grounding"}
    monkeypatch.setattr(suite, "prepare_llm_context", lambda *a, **k: Empty())
    rows = suite.build_expanded_requests([family()])
    linked = [r for r in rows if r["document_id"] == "test-meter:linked"]
    assert all(r["expected_entity_id"] == "global:meter" for r in linked)
    assert all(r["resolver_authorized_entity_id"] is None and not r["gold_entity_in_candidates"] for r in linked)


def test_target_surface_guard_and_semantic_gold_are_distinct():
    rows = suite.build_expanded_requests([family()])
    outputs = [{"case_id": "test-meter:linked:structured_routing", "condition": "both", "response": {"entity_id": "global:meter"}},
               {"case_id": "test-meter:role:structured_routing", "condition": "both", "response": {"entity_id": "global:meter"}},
               {"case_id": "test-meter:collision:structured_routing", "condition": "both", "response": {"entity_id": "global:return"}}]
    result = suite.grade_expanded_outputs(rows, outputs)
    assert result["metrics"]["both"]["task_success"] == 1
    score = result["expanded_diagnostics"]["both"]["overall"]
    assert score["wrong_ids"] == score["guard_rejections"] == 2
    assert score["accepted_unauthorized_ids"] == 0


def test_five_conditions_keep_facts_and_questions_fixed():
    rows = suite.build_expanded_requests([family()])
    assert len(rows) == 40
    assert len({(r["case_id"], r["condition"]) for r in rows}) == 40
    assert set(r["condition"] for r in rows) == set(suite.CONDITIONS)
    for case in {r["case_id"] for r in rows}:
        group = [r for r in rows if r["case_id"] == case]
        assert len({r["candidate_hash"] for r in group}) == len({r["binding_hash"] for r in group}) == 1
        assert len({r["system"] for r in group}) == 1
        assert len({r["user"].split("\n", 1)[1] for r in group}) == 1
        for row in group:
            data = json.loads(row["user"].split("\n", 1)[0])
            assert "expected_entity_id" not in data and "gold" not in data
            if row["condition"] == "full_pack":
                assert data == {"terminology_context": row["pack"]}
            else:
                cards = (data["terminology_data"] if "terminology_data" in data else
                         data["resolved_terms"] + [c for m in data["ambiguous_mentions"] for c in m["candidates"]])
                assert [{k: v for k, v in c.items() if k != "surface"} for c in cards] == row["cards"]


def test_gold_and_card_aliases_do_not_leak_other_target_authority():
    rows = suite.build_expanded_requests([family()])
    row = next(r for r in rows if r["case_id"] == "test-meter:linked:document_qa" and r["condition"] == "both")
    assert row["target_surface"] == "LUX"
    data = json.loads(row["user"].split("\n", 1)[0])
    assert any(c["surface"] == "반송검토실" for c in data["resolved_terms"])
    assert row["expected_answer"] == family()["worlds"]["base"]["terms"][0]["short_definition"]


@pytest.mark.parametrize("change", ["duplicate", "missing_target", "false_origin", "wrong_link", "whole_role_link"])
def test_invalid_authored_gold_is_rejected(change):
    f = family()
    if change == "duplicate":
        f["cases"][1]["case_id"] = f["cases"][0]["case_id"]
    elif change == "missing_target":
        f["cases"][0]["target_surface"] = "absent"
    elif change == "false_origin":
        f["human_verified"] = True
    elif change == "wrong_link":
        f["cases"][0]["gold"]["entity_ref"] = "global:absent"
    else:
        f["cases"][2]["gold"].update(label="LINK", entity_ref="global:meter")
    with pytest.raises(ValueError):
        suite.validate_families([f])


def test_family_and_alias_groups_never_split_across_partitions():
    first, second = family(), family()
    second["family_id"] = "test-other"
    for c in second["cases"]:
        c["case_id"] = c["case_id"].replace("test-meter:", "test-other:")
        c["text"] += " 추가 출처."
    rows = suite.build_expanded_requests([first, second])
    manifest = suite.corpus_manifest([first, second], rows)
    assert manifest["documents"] == manifest["unique_document_hashes"] == 8
    assert len(set(manifest["partition_assignments"].values())) == 1
    assert manifest["model_requests"] == 80
    assert manifest["resolver_pipeline"]["gold_LINK_documents"] == 2


def test_missing_and_malformed_are_not_reported_as_safe_abstention():
    rows = suite.build_expanded_requests([family()])
    result = suite.grade_expanded_outputs(rows, [{"case_id": "test-meter:absent:document_qa", "condition": "both", "response": {}}])
    assert result["missing_outputs"] == 39
    assert result["expanded_diagnostics"]["both"]["overall"]["safe_abstention"] == 0
    assert result["expanded_diagnostics"]["both"]["overall"]["malformed"] == 1


@pytest.mark.parametrize("value", [[], {}, 23, True, "", "   "])
def test_invalid_id_field_types_are_malformed_and_cannot_crash_scoring(value):
    rows = suite.build_expanded_requests([family()])
    result = suite.grade_expanded_outputs(rows, [{"case_id": "test-meter:absent:structured_routing",
        "condition": "both", "response": {"entity_id": value}}])
    metric = result["metrics"]["both"]
    assert metric["malformed"] == 1 and metric["safe_abstention"] == metric["task_success"] == 0
    assert result["expanded_diagnostics"]["both"]["overall"]["malformed"] == 1
