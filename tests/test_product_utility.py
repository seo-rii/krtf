"""Product safety and paired intervention evaluation regressions."""
import pytest
from eval.product_utility import build_requests, grade_outputs, local_swap_checks, swap_worlds
from ktrf.context import (ContextPolicy, EXECUTION_POLICY, prepare_llm_context,
                          validate_llm_grounding)


def test_counterfactual_glossary_scope_restoration():
    checks = local_swap_checks()
    assert checks["passed"]
    assert len(checks["checks"]) == 8
    assert checks["checks"][0]["snapshot_id"] == checks["checks"][-1]["snapshot_id"]
    assert checks["checks"][0]["snapshot_id"] != checks["checks"][1]["snapshot_id"]


def test_execution_rejects_candidate_and_unbound_surface():
    worlds = {name: snap for name, snap, _ in swap_worlds()}
    ambiguous = prepare_llm_context(worlds["ambiguous"], "ABC", query="ABC?").context_pack
    selection = {"selections": [{"surface": "ABC", "entity_id": "project:billing"}]}
    candidate = ambiguous["ambiguous_mentions"][0]["candidates"][0]["entity_id"]
    selection["selections"][0]["entity_id"] = candidate
    assert validate_llm_grounding(selection, ambiguous)["valid"]
    assert not validate_llm_grounding(selection, ambiguous, purpose="execution")["valid"]
    resolved = prepare_llm_context(worlds["tenant-a"], "ABC", query="ABC?").context_pack
    for surface, eid, valid in [("ABC", "global:billing", True),
                                ("unmentioned", "global:billing", False),
                                ("ABC", "global:access", False),
                                ("ABC", None, True)]:
        result = validate_llm_grounding({"selections": [{"surface": surface, "entity_id": eid}]},
                                        resolved, purpose="execution")
        assert result["valid"] is valid
    resolved["resolved_terms"][0]["resolution"]["degraded"] = True
    assert not validate_llm_grounding({"selections": [{"surface": "ABC", "entity_id": "global:billing"}]},
                                      resolved, purpose="execution")["valid"]
    assert not validate_llm_grounding({"selections": [{}]}, resolved,
                                      purpose="execution")["valid"]


def test_automation_enforces_execution_even_default_validator():
    _, snap, _ = swap_worlds()[0]
    prepared = prepare_llm_context(snap, "ABC", context_policy=ContextPolicy(profile="automation"))
    assert prepared.policy_fragment == EXECUTION_POLICY
    result = validate_llm_grounding({"selections": [{"surface": "unbound", "entity_id": "global:billing"}]}, prepared.context_pack)
    assert not result["valid"]


def test_factorial_holds_candidates_fixed_and_no_fake_model_results():
    rows = build_requests()
    assert len(rows) == 126
    for case in {r["case_id"] for r in rows}:
        for selector in ("ktrf", "lexical"):
            subset = [r for r in rows if r["case_id"] == case and r.get("selector") == selector]
            assert len(subset) == 4
            assert len({r["candidate_hash"] for r in subset}) == 1
            assert all(r["cards"] == subset[0]["cards"] for r in subset)
    result = grade_outputs(rows, [])
    assert result["missing_outputs"] == 126
    assert all(m["observed"] == m["safe_abstention"] == 0 for m in result["metrics"].values())


def test_paired_harmful_flips_null_and_malformed_distinct():
    rows = build_requests()
    condition = "ktrf:structured:knowledge"
    outputs = [
        {"case_id": "tenant-a:structured_routing", "condition": "no_context", "response": {"entity_id": "global:billing"}},
        {"case_id": "tenant-a:structured_routing", "condition": condition, "response": {"entity_id": None}},
        {"case_id": "missing:structured_routing", "condition": condition, "response": {"entity_id": None}},
        {"case_id": "ambiguous:structured_routing", "condition": condition, "response": {}},
    ]
    metrics = grade_outputs(rows, outputs)["metrics"][condition]
    assert metrics["harmful_flip"] == metrics["safe_abstention"] == metrics["over_abstention"] == metrics["malformed"] == 1
    assert metrics["task_success"] == 1
    with pytest.raises(ValueError):
        grade_outputs(rows, outputs + outputs[:1])


def test_glossary_swap_measures_retained_old_meaning():
    rows = build_requests()
    condition = "ktrf:plain:evidence_only"
    outputs = [{"case_id": f"{world}:structured_routing", "condition": condition,
                "response": {"entity_id": "global:billing"}}
               for world in ("tenant-a", "tenant-b")]
    metrics = grade_outputs(rows, outputs)["metrics"][condition]
    assert metrics["glossary_swap_pairs"] == metrics["previous_meaning_retained"] == 1
    assert metrics["correct_meaning_switch"] == 0


def test_knowledge_answer_policy_does_not_grant_execution():
    from ktrf.context import KNOWLEDGE_ASSISTANCE_POLICY
    _, snap, _ = swap_worlds()[0]
    p = prepare_llm_context(snap, "ABC", context_policy=ContextPolicy(answer_policy="knowledge"))
    assert p.policy_fragment == KNOWLEDGE_ASSISTANCE_POLICY
    assert p.context_pack["answer_policy"] == "knowledge"
    p = prepare_llm_context(snap, "ABC", context_policy=ContextPolicy(profile="automation", answer_policy="knowledge"))
    assert p.policy_fragment == EXECUTION_POLICY
    assert p.context_pack["answer_policy"] == "evidence_only"


def test_context_never_turns_heuristic_candidates_into_coverage_claim():
    worlds = {name: snap for name, snap, _ in swap_worlds()}
    pack = prepare_llm_context(worlds['ambiguous'], 'ABC', query='ABC?').context_pack
    candidate_set = pack['ambiguous_mentions'][0]
    assert candidate_set['calibration_status'] == 'HEURISTIC'
    assert candidate_set['coverage_scope'] == 'candidate_conditional'
    assert candidate_set['set_confidence'] is None
    assert not candidate_set['coverage_valid']
    assert not candidate_set['set_valid']


def test_context_unknown_is_retrieval_uncertainty_not_verified_glossary_absence():
    from ktrf.context import build_context_pack
    _, snap, _ = swap_worlds()[0]
    response = {'mentions': [{'mention_id': 'm1', 'surface': 'XYZ',
                             'link_decision': 'KB_MISSING',
                             'span': {'codepoint': {'start': 0, 'end': 3}}}]}
    pack = build_context_pack(snap, response, policy=ContextPolicy(include_unknown_mentions=True))
    unknown = pack['unknown_mentions'][0]
    assert unknown['reason'] == 'NO_COMPATIBLE_RETRIEVED_CANDIDATE'
    assert not unknown['kb_absence_verified']
