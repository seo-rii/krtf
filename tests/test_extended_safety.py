"""Source-authored semantic truth remains distinct from production authority."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval import extended_safety as suite
from eval.hf_qa import canonical
from ktrf.context import ContextPolicy, prepare_llm_context, validate_llm_grounding
from ktrf.glossary import load_glossary
from ktrf.registry.simple_schema import compile_simple_terms
from ktrf.snapshot import compile_snapshot


class Tokenizer:
    def __init__(self, length=100):
        self.length, self.calls = length, []

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return list(range(self.length))


MODELS = {key: {"path": "/fixture/" + key} for key in ("gemma12b", "qwen27b")}


@pytest.fixture(scope="module")
def prepared():
    tokenizers = {key: Tokenizer() for key in MODELS}
    envelope, aggregate = suite.prepare_safety(code_revision="fixture-revision",
        tokenizers=tokenizers, models=MODELS)
    return envelope, aggregate, tokenizers


def routing(row, entity_id):
    return {"selections": [{"surface": row["target_surface"], "entity_id": entity_id}]}


def test_authored_family_balance_and_whole_expression_gold():
    data = suite.load_cases()
    assert data["annotation_origin"] == "AI_AUTHORED" and not data["human_verified"]
    assert len(data["families"]) == 24
    for family in data["families"]:
        assert len(family["cases"]) == 4
        assert sum(case["gold"]["label"] == "LINK" for case in family["cases"]) == 2
        for case in family["cases"]:
            start, end = case["target_span"]
            assert case["text"][start:end] == case["target_surface"]
            if case["gold"]["label"] == "COMPOSITIONAL":
                assert case["gold"]["entity_ref"] is None
                assert case["gold"]["core_entity_ref"]
                assert case["gold"]["core_surface"] != case["target_surface"]
                assert case["gold"]["full_identity"] == "DISTINCT"


def test_frozen_protocol_seals_all_cases_and_both_actual_chat_templates(prepared):
    envelope, aggregate, tokenizers = prepared
    rows = envelope["requests"]
    assert envelope["protocol"]["kind"] == "ktrf_extended_v1"
    assert envelope["protocol"]["phase"] == "FINAL_FROZEN"
    assert envelope["protocol"]["conditions"] == ["production"]
    assert envelope["protocol"]["repeat_count"] == 1
    assert not envelope["protocol"]["human_verified"]
    assert not envelope["protocol"]["independent_validation"]
    assert aggregate["request_count"] == aggregate["question_count"] == 96
    assert aggregate["family_count"] == 24
    assert aggregate["positive_questions"] == 48
    assert aggregate["strata"] == {key: 24 for key in suite.STRATA}
    assert aggregate["envelope_sha256"] == hashlib.sha256(canonical(envelope)).hexdigest()
    assert aggregate["requests_sha256"] == hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest()
    authored = {case["case_id"]: case for family in suite.load_cases()["families"] for case in family["cases"]}
    for row in rows:
        assert row["task"] == "structured_routing" and row["repeat_id"] == 0
        assert row["parent_document_id"] == row["document_id"]
        assert row["source_text"] == row["text"]
        assert row["gold"] == authored[row["document_id"]]["gold"]
        assert row["provenance"]["source_case_sha256"] == hashlib.sha256(canonical(authored[row["document_id"]])).hexdigest()
    for tokenizer in tokenizers.values():
        assert len(tokenizer.calls) == 96
        messages, settings = tokenizer.calls[0]
        assert messages == [{"role": "system", "content": rows[0]["system"]},
                            {"role": "user", "content": rows[0]["user"]}]
        assert settings == {"tokenize": True, "add_generation_prompt": True,
                            "enable_thinking": False, "return_dict": False}


def test_authored_routing_retains_real_automation_pack_and_full_prompt(prepared):
    envelope, _, _ = prepared
    family = next(f for f in suite.load_cases()["families"] if f["family_id"] == "role-onbit")
    glossary = load_glossary(compile_simple_terms({"terms": family["terms"]}, scope="global",
        glossary_id="extended-safety:" + family["family_id"]))
    snapshot = compile_snapshot(glossary, run_conformance=False, tenant_id="extended-safety:" + family["family_id"])
    row = next(row for row in envelope["requests"] if row["document_id"] == "role-onbit:1")
    actual = prepare_llm_context(snapshot, row["text"], query=row["target_surface"],
        context_policy=ContextPolicy(**row["context_policy"]))
    assert row["pack"] == actual.context_pack
    assert row["pack"]["profile"] == "automation"
    assert row["prompt_fragment"] == actual.prompt_fragment
    assert row["policy_fragment"] == actual.policy_fragment
    assert row["injected"] == actual.should_inject


def test_complete_mixed_response_reaches_guard_and_cannot_be_repaired(prepared, monkeypatch):
    row = next(row for row in prepared[0]["requests"] if row["document_id"] == "geo-gangwon:1")
    response = {**routing(row, row["expected_entity_id"]), "answer": "incidental QA answer"}
    seen = []
    original = suite.validate_llm_grounding

    def observe(raw, pack, *, purpose):
        seen.append(raw)
        return original(raw, pack, purpose=purpose)

    monkeypatch.setattr(suite, "validate_llm_grounding", observe)
    result = suite.grade_safety(row, response)
    assert seen == [response] and seen[0] is response
    assert result["malformed"] and not result["correct"]
    assert not result["accepted_correct_id"] and not result["accepted_wrong_id"]
    assert result["guard_violations"] == [{"kind": "qa_output_not_executable"}]


def test_known_country_homonym_is_not_relabelled_when_guard_authorizes_wrong_id(prepared):
    row = next(row for row in prepared[0]["requests"] if row["document_id"] == "geo-gangwon:3")
    assert row["gold"]["label"] == "NIL" and row["expected_entity_id"] is None
    response = routing(row, "ORG_GANGWON")
    guard = validate_llm_grounding(response, row["pack"], purpose="execution")
    result = suite.grade_safety(row, response)
    # Allow a future resolver fix; either way an incorrect ID is never success.
    assert result["accepted_wrong_id"] == guard["valid"]
    assert result["rejected_wrong_id"] != guard["valid"]
    assert not result["correct"] and not result["semantic_match"]


def test_role_core_id_cannot_count_as_whole_expression_correct(prepared):
    roles = [row for row in prepared[0]["requests"] if row["gold"]["label"] == "COMPOSITIONAL"]
    assert len(roles) == 12
    for row in roles:
        result = suite.grade_safety(row, routing(row, row["gold"]["core_entity_ref"]))
        assert not result["correct"] and not result["accepted_correct_id"]
        assert result["accepted_wrong_id"] or result["rejected_wrong_id"]
        assert suite.grade_safety(row, routing(row, None))["correct_abstention"]


def test_correct_execution_abstention_and_guard_rejection_are_separate(prepared):
    rows = prepared[0]["requests"]
    positive = next(row for row in rows if row["document_id"] == "geo-gangwon:1")
    success = suite.grade_safety(positive, routing(positive, positive["expected_entity_id"]))
    assert success["accepted_correct_id"] and success["correct"]
    abstain = suite.grade_safety(positive, routing(positive, None))
    assert abstain["over_abstention"] and not abstain["correct"]
    wrong = suite.grade_safety(positive, routing(positive, "invented:entity"))
    assert wrong["rejected_wrong_id"] and not wrong["correct"]
    # A source LINK may still be rejected by the guard; this is not execution success.
    no_authority = deepcopy(positive)
    no_authority["pack"]["resolved_terms"] = []
    denied = suite.grade_safety(no_authority, routing(no_authority, positive["expected_entity_id"]))
    assert denied["semantic_match"] and denied["rejected_correct_id"] and not denied["correct"]


@pytest.mark.parametrize("response", [None, [], {}, {"answer": None}, {"selections": []},
    {"selections": [{"surface": "wrong target", "entity_id": None}]},
    {"selections": [{"surface": "강원도", "entity_id": None}], "extra": True}])
def test_malformed_responses_do_not_become_correct_abstention(prepared, response):
    row = next(row for row in prepared[0]["requests"] if row["document_id"] == "geo-gangwon:3")
    result = suite.grade_safety(row, response)
    assert result["malformed"]
    assert not result["correct"] and not result["correct_abstention"]


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(human_verified=True),
    lambda data: data["families"][0]["cases"][0].update(target_span=[0, 1]),
    lambda data: data["families"][0]["cases"][0]["gold"].update(entity_ref="not:registered"),
    lambda data: data["families"][6]["cases"][2]["gold"].update(full_identity="SAME"),
    lambda data: data["families"][0]["cases"].pop(),
])
def test_invalid_authored_gold_is_rejected_before_resolution(tmp_path, mutation):
    data = suite.load_cases()
    mutation(data)
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        suite.load_cases(path)


def test_source_seal_is_computed_before_any_resolution(monkeypatch):
    source = suite.load_cases()
    seal = hashlib.sha256(canonical(source)).hexdigest()
    observed = []
    original = suite.build_document_requests

    def observe(*args, **kwargs):
        observed.append(kwargs["provenance"]["authored_gold_sha256"])
        return original(*args, **kwargs)

    monkeypatch.setattr(suite, "build_document_requests", observe)
    suite.prepare_safety(code_revision="fixture", models=MODELS,
        tokenizers={key: Tokenizer() for key in MODELS})
    assert observed == [seal] * 96


def test_actual_token_overflow_fails_preparation_without_dropping_cases():
    with pytest.raises(ValueError, match="token capacity"):
        suite.prepare_safety(code_revision="fixture", models=MODELS,
            tokenizers={key: Tokenizer(8065) for key in MODELS})


def test_both_declared_tokenizers_required():
    with pytest.raises(ValueError, match="both matching"):
        suite.prepare_safety(code_revision="fixture", models=MODELS,
            tokenizers={"gemma12b": Tokenizer()})
