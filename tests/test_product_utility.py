"""Product safety and paired intervention evaluation regressions."""
import pytest
from eval.product_utility import build_requests, grade_outputs, local_swap_checks, swap_worlds
from ktrf.context import (ContextPolicy, EXECUTION_POLICY,
                          KNOWLEDGE_ASSISTANCE_POLICY, QA_CONTEXT_POLICY,
                          TERMINOLOGY_POLICY, prepare_llm_context,
                          validate_llm_grounding)


def _execution_selection(pack, surface, entity_id):
    """Copy the authoritative occurrence identity rather than inventing one."""
    mention = next((m for c in pack["resolved_terms"] for m in c["mentions"]
                    if m["surface"] == surface), {})
    return {"surface": surface, "entity_id": entity_id,
            "document_hash": pack["document_hash"],
            "snapshot_id": pack["snapshot"]["snapshot_id"],
            **{key: mention.get(key) for key in
               ("mention_id", "core_span", "full_span")}}


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
        result = validate_llm_grounding({"selections": [
            _execution_selection(resolved, surface, eid)]},
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


@pytest.mark.parametrize("profile,answer_policy,expected_policy", [
    ("qa_grounding", "evidence_only", QA_CONTEXT_POLICY),
    ("qa_grounding", "knowledge", KNOWLEDGE_ASSISTANCE_POLICY),
    ("summarization", "evidence_only", TERMINOLOGY_POLICY),
    ("rag_query_expansion", "evidence_only", TERMINOLOGY_POLICY),
    ("automation", "evidence_only", EXECUTION_POLICY),
    ("automation", "knowledge", EXECUTION_POLICY),
])
def test_contextual_explanation_policy_is_limited_to_qa(
        profile, answer_policy, expected_policy):
    _, snap, _ = swap_worlds()[0]
    prepared = prepare_llm_context(
        snap, "ABC", context_policy=ContextPolicy(
            profile=profile, answer_policy=answer_policy))
    assert prepared.policy_fragment == expected_policy
    assert prepared.context_pack["answer_policy"] == (
        "evidence_only" if profile == "automation" else answer_policy)


def test_contextual_qa_keeps_candidate_links_unverified():
    worlds = {name: snap for name, snap, _ in swap_worlds()}
    prepared = prepare_llm_context(
        worlds["ambiguous"], "ABC의 과금 정책과 청구 상태를 확인해.",
        query="ABC는 무엇인가?")
    assert prepared.policy_fragment == QA_CONTEXT_POLICY
    assert prepared.should_inject
    assert not prepared.resolves_query
    pack = prepared.context_pack
    assert not pack["resolved_terms"]
    candidates = pack["ambiguous_mentions"][0]["candidates"]
    assert len(candidates) >= 2
    for candidate in candidates:
        output = {"selections": [{"surface": "ABC",
                                  "entity_id": candidate["entity_id"]}]}
        assert validate_llm_grounding(output, pack)["valid"]
        result = validate_llm_grounding(output, pack, purpose="execution")
        assert not result["valid"]
        assert "unverified_execution" in {
            violation["kind"] for violation in result["violations"]}
    assert not pack["resolved_terms"]


@pytest.fixture(scope="module")
def resolved_qa_pack():
    _, snap, _ = swap_worlds()[0]
    return prepare_llm_context(snap, "ABC", query="ABC?").context_pack


@pytest.mark.parametrize("automation_default", [False, True])
@pytest.mark.parametrize("output", [
    {"answer": "사내 과금 콘솔"},
    {"answer": None, "entity_id": None},
    {"answer": "사내 과금 콘솔", "entity_id": "global:billing"},
    {"answer": "사내 과금 콘솔", "selections": [
        {"surface": "ABC", "entity_id": "global:billing"}]},
])
def test_qa_answers_cannot_be_executed_even_with_a_verified_id(
        resolved_qa_pack, automation_default, output):
    pack = {**resolved_qa_pack,
            "profile": "automation" if automation_default else "qa_grounding"}
    kwargs = {} if automation_default else {"purpose": "execution"}
    result = validate_llm_grounding(output, pack, **kwargs)
    assert result == {"valid": False, "violations": [
        {"kind": "qa_output_not_executable"}]}


@pytest.mark.parametrize("output", [
    None, [], "ABC", 1, {},
    {"selections": None},
    {"selections": {"surface": "ABC", "entity_id": "global:billing"}},
    {"selections": (), "entity_id": None},
    {"selections": [], "entity_id": "global:billing"},
])
def test_execution_requires_an_explicit_selection_list(resolved_qa_pack, output):
    result = validate_llm_grounding(output, resolved_qa_pack, purpose="execution")
    assert result == {"valid": False,
                      "violations": [{"kind": "malformed_output"}]}


@pytest.mark.parametrize("selection", [
    None, [], {},
    {"surface": "ABC", "entity_id": []},
    {"surface": "ABC", "entity_id": {}},
    {"surface": "ABC", "entity_id": True},
    {"surface": "ABC", "entity_id": ""},
    {"surface": "ABC", "entity_id": " "},
    {"surface": [], "entity_id": "global:billing"},
    {"surface": {}, "entity_id": "global:billing"},
    {"surface": None, "entity_id": "global:billing"},
    {"surface": True, "entity_id": "global:billing"},
    {"surface": "", "entity_id": "global:billing"},
    {"surface": " ", "entity_id": "global:billing"},
    {"entity_id": "global:billing"},
])
def test_execution_rejects_malformed_selections_without_crashing(
        resolved_qa_pack, selection):
    result = validate_llm_grounding(
        {"selections": [selection]}, resolved_qa_pack, purpose="execution")
    assert result == {"valid": False,
                      "violations": [{"kind": "malformed_selection"}]}


@pytest.mark.parametrize("selections", [
    [], [{"entity_id": None}], [{"surface": "ABC", "entity_id": None}],
    [{"surface": "ABC", "entity_id": "global:billing"}],
])
def test_execution_retains_explicit_abstention_and_verified_selection(
        resolved_qa_pack, selections):
    selections = [(_execution_selection(resolved_qa_pack, sel["surface"],
                                       sel["entity_id"])
                   if sel.get("entity_id") is not None else sel)
                  for sel in selections]
    result = validate_llm_grounding(
        {"selections": selections}, resolved_qa_pack, purpose="execution")
    assert result == {"valid": True, "violations": []}


def test_grounding_validation_does_not_require_an_execution_envelope(resolved_qa_pack):
    assert validate_llm_grounding({}, resolved_qa_pack)["valid"]
    assert validate_llm_grounding(
        {"answer": "참고 설명", "entity_id": "global:billing"},
        resolved_qa_pack)["valid"]


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
