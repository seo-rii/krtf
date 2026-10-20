"""Production evaluation preserves the actual QA/execution API boundary."""
from copy import deepcopy
import hashlib
import json

import pytest

from eval import production_grounding as suite
from eval import run_product_llm as runner
from eval.synthetic_grounding import _snapshot, _target_span
from eval.synthetic_grounding_v2 import load_balanced_families
from ktrf.context import ContextPolicy, EXECUTION_POLICY, QA_CONTEXT_POLICY, prepare_llm_context


@pytest.fixture(scope="module")
def rows():
    return suite.build_production_requests()


def _output(row, response, **extra):
    return {"case_id": row["case_id"], "condition": row["condition"], "response": response, **extra}


def _routing(row, entity_id):
    return {"selections": [{"surface": row["target_surface"], "entity_id": entity_id}]}


def _envelope(rows, *, real=False):
    return {"protocol": {**suite.PROTOCOL,
        "kind": "production_grounding_real_holdout_v1" if real else suite.PROTOCOL["kind"]},
        "provenance": {"source": "frozen test fixture", "human_verified": False}, "requests": rows}


def test_every_balanced_document_has_separate_production_calls(rows):
    assert len(rows) == 874
    assert len({row["document_id"] for row in rows}) == 437
    assert len({row.get("contrast_pair_id") for row in rows} - {None}) == 37
    assert len({(row["case_id"], row["condition"]) for row in rows}) == len(rows)
    for qa, execution in zip(rows[::2], rows[1::2]):
        assert qa["task"] == "document_qa" and execution["task"] == "structured_routing"
        assert qa["document_id"] == execution["document_id"]
        assert qa["gold"] == execution["gold"]
        assert qa["expected_answer"] == execution["expected_answer"]
        assert qa["pack"]["profile"] == "qa_grounding"
        assert execution["pack"]["profile"] == "automation"
        assert qa["policy_fragment"] == QA_CONTEXT_POLICY
        assert execution["policy_fragment"] == EXECUTION_POLICY
        assert execution["pack"]["ambiguous_mentions"] == []
        assert "expected_answer" not in qa["user"]


def test_uses_actual_prepared_render_policy_and_injection(rows):
    family = load_balanced_families()[0]
    case = family["cases"][0]
    snapshot = _snapshot(family, case["world"])
    for row in (row for row in rows if row["document_id"] == case["case_id"]):
        prepared = prepare_llm_context(snapshot, case["text"], query=case["target_surface"],
            context_policy=ContextPolicy(**row["context_policy"]))
        assert row["pack"] == prepared.context_pack
        assert row["prompt_fragment"] == prepared.prompt_fragment
        assert row["policy_fragment"] == prepared.policy_fragment
        assert row["injected"] == prepared.should_inject
        if prepared.should_inject:
            assert row["user"].startswith(prepared.prompt_fragment + "\n")
            assert row["system"] == suite.BASE_POLICY + "\n" + prepared.policy_fragment
    ungrounded = next(row for row in rows if not row["injected"])
    assert ungrounded["system"] == suite.BASE_POLICY
    assert ungrounded["user"].startswith("문서: ")
    assert ungrounded["prompt_fragment"] not in ungrounded["user"]


def test_source_gold_never_changes_prompt_or_resolver_pack():
    family = load_balanced_families()[0]
    case = next(case for case in family["cases"] if case["gold"]["label"] == "LINK")
    snapshot = _snapshot(family, case["world"])
    common = dict(snapshot=snapshot, document_id=case["case_id"], family_id=family["family_id"],
        domain=family["domain"], stratum=case["stratum"], text=case["text"],
        target_surface=case["target_surface"], target_span=_target_span(case), provenance={"source": "test"})
    positive = suite.build_document_requests(**common, gold=case["gold"], expected_answer="SOURCE_GOLD_SENTINEL")
    negative = suite.build_document_requests(**common, gold={"label": "NIL", "entity_ref": None}, expected_answer=None)
    for a, b in zip(positive, negative):
        assert a["system"] == b["system"] and a["user"] == b["user"] and a["pack"] == b["pack"]
        assert "SOURCE_GOLD_SENTINEL" not in a["system"] + a["user"]


def test_contextual_qa_success_cannot_authorize_execution(rows):
    qa = next(row for row in rows if row["task"] == "document_qa" and row["stratum"] == "contextual_collision")
    execution = next(row for row in rows if row["document_id"] == qa["document_id"] and row["task"] == "structured_routing")
    assert qa["pack"]["ambiguous_mentions"]
    assert execution["resolver_authorized_entity_id"] is None
    result = suite.grade_production_outputs([qa, execution], [
        _output(qa, {"answer": qa["expected_answer"]}),
        _output(execution, _routing(execution, execution["expected_entity_id"]))])
    assert result["by_task"]["document_qa"]["correct"] == 1
    assert result["by_task"]["structured_routing"]["semantic_match"] == 1
    assert result["by_task"]["structured_routing"]["correct"] == 0
    assert result["by_task"]["structured_routing"]["denied_nonnull"] == 1


def test_raw_complete_response_reaches_guard_without_projection(rows, monkeypatch):
    execution = next(row for row in rows if row["task"] == "structured_routing" and
        row["expected_entity_id"] is not None and row["resolver_authorized_entity_id"] == row["expected_entity_id"])
    mixed = {**_routing(execution, execution["expected_entity_id"]), "answer": execution["expected_answer"]}
    seen = []
    guard = suite.validate_llm_grounding

    def observe(response, pack, *, purpose, execution_contract):
        seen.append(response)
        return guard(response, pack, purpose=purpose, execution_contract=execution_contract)

    monkeypatch.setattr(suite, "validate_llm_grounding", observe)
    result = suite.grade_production_outputs([execution], [_output(execution, mixed)])
    assert seen == [mixed] and seen[0] is mixed
    assert result["overall"]["correct"] == 0 and result["overall"]["malformed"] == 1
    assert result["cases"][0]["guard_violations"] == [{"kind": "qa_output_not_executable"}]


@pytest.mark.parametrize("response", [{"answer": None, "entity_id": None},
    {"answer": None, "entity_id": "bad"}, {"answer": None, "selections": []}])
def test_qa_incidental_id_fields_fail_answer_only_contract(rows, response):
    qa = next(row for row in rows if row["task"] == "document_qa" and row["expected_answer"] is None)
    result = suite.grade_production_outputs([qa], [_output(qa, response)])["overall"]
    assert result["qa_unexpected_ids"] == result["malformed"] == 1
    assert result["correct"] == result["safe_null"] == 0


def test_missing_malformed_null_and_positive_abstention_are_distinct(rows):
    qa_rows = [row for row in rows if row["task"] == "document_qa" and row["expected_answer"] is not None][:3]
    result = suite.grade_production_outputs(qa_rows, [
        _output(qa_rows[0], {"answer": None}), _output(qa_rows[1], {})])
    assert result["missing_outputs"] == 1
    assert result["overall"]["positive_null"] == 1
    assert result["overall"]["malformed"] == 1
    assert result["overall"]["safe_null"] == 0


@pytest.mark.parametrize("entity_id,expected_count", [(None, 0), ("unapproved", 1)])
def test_qa_incidental_null_selection_is_not_a_nonnull_id(rows, entity_id, expected_count):
    qa = next(row for row in rows if row["task"] == "document_qa")
    response = {"answer": qa["expected_answer"],
                "selections": [{"surface": qa["target_surface"], "entity_id": entity_id}]}
    result = suite.grade_production_outputs([qa], [_output(qa, response)])["overall"]
    assert result["malformed"] == result["qa_unexpected_ids"] == 1
    assert result["qa_unexpected_id_nonnull"] == expected_count


def test_contrast_pair_success_and_cost_use_real_observations(rows):
    pair_id = next(row["contrast_pair_id"] for row in rows if row.get("contrast_pair_id"))
    pair = [row for row in rows if row.get("contrast_pair_id") == pair_id and row["task"] == "document_qa"]
    outputs = [_output(row, {"answer": row["expected_answer"]}, latency_ms=latency,
        usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}) for row, latency in zip(pair, (10, 20))]
    result = suite.grade_production_outputs(pair, outputs)
    assert result["contextual_pairs"]["both_correct"] == result["contextual_pairs"]["complete"] == 1
    assert result["cost"]["document_qa"]["latency_ms"]["p95"] == 20
    assert result["cost"]["overall"]["usage"]["total_tokens"] == 24


def test_untrusted_wrong_id_accepted_by_guard_is_still_failure(rows):
    row = next(row for row in rows if row["task"] == "structured_routing" and
        row["expected_entity_id"] is None and row["resolver_authorized_entity_id"] is not None)
    result = suite.grade_production_outputs([row], [_output(row, _routing(row, row["resolver_authorized_entity_id"]))])
    assert result["overall"]["accepted_wrong_id"] == 1
    assert result["overall"]["correct"] == 0


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.append(deepcopy(rows[0])),
    lambda rows: rows[0].update(target_span=[0, 1]),
    lambda rows: rows[0].update(system="replacement policy"),
    lambda rows: rows[0].update(expected_entity_id="missing-id"),
    lambda rows: rows[0].pop("provenance"),
])
def test_frozen_file_rejected_before_artifacts_or_network(rows, mutation, tmp_path, monkeypatch):
    frozen = deepcopy(rows[:2])
    mutation(frozen)
    path = tmp_path / "requests.json"
    path.write_text(json.dumps(_envelope(frozen)))
    monkeypatch.setattr(runner, "_request_json", lambda *a, **kw: pytest.fail("must validate before HTTP"))
    with pytest.raises(ValueError):
        runner.run_benchmark(endpoint="http://localhost/v1", model="served", out_dir=tmp_path / "run",
            code_revision="sha", track="production_synthetic", requests_file=path)
    assert not (tmp_path / "run").exists()


def test_frozen_regrading_does_not_depend_on_current_policy_wording(rows, monkeypatch):
    row = deepcopy(rows[0])
    monkeypatch.setattr(suite, "QA_CONTEXT_POLICY", "new policy")
    with pytest.raises(ValueError, match="policy"):
        suite.validate_production_requests([row])
    result = suite.grade_production_outputs([row], [_output(row, {"answer": row["expected_answer"]})])
    assert result["overall"]["correct"] == 1


def test_real_frozen_runner_sends_only_prompts_and_seals_raw_responses(rows, tmp_path, monkeypatch):
    rows = rows[:2]
    envelope = _envelope(rows, real=True)
    envelope["protocol"]["limitations"] = ["real AI gold is not independently human verified"]
    frozen = tmp_path / "frozen.json"
    frozen.write_text(json.dumps(envelope))
    sent = []
    responses = iter([{"answer": rows[0]["expected_answer"]}, _routing(rows[1], rows[1]["expected_entity_id"])])

    def fake_request(url, *, payload=None, timeout):
        if url.endswith("/models"):
            return {"data": [{"id": "served"}]}
        sent.append(payload)
        return {"choices": [{"message": {"content": json.dumps(next(responses))}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}}

    monkeypatch.setattr(runner, "_request_json", fake_request)
    out = tmp_path / "run"
    manifest = runner.run_benchmark(endpoint="http://localhost/v1", model="served", out_dir=out,
        code_revision="sha", track="production_real", requests_file=frozen)
    assert manifest["status"] == "COMPLETE"
    assert manifest["request_provenance"] == envelope["provenance"]
    assert manifest["protocol"] == "production_grounding_real_holdout_v1"
    assert manifest["frozen_request_file_sha256"] == hashlib.sha256(frozen.read_bytes()).hexdigest()
    assert manifest["malformed_count"] == 0
    for payload, row in zip(sent, rows):
        assert payload["messages"] == [{"role": "system", "content": row["system"]},
                                       {"role": "user", "content": row["user"]}]
        assert all(field not in payload for field in ("gold", "expected_answer", "expected_entity_id", "pack"))
    graded = json.loads((out / "graded.json").read_text())["model_results"]
    assert graded["limitations"] == envelope["protocol"]["limitations"]
    for name, sha in manifest["artifact_sha256"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == sha


def test_real_track_requires_frozen_file(tmp_path):
    with pytest.raises(ValueError, match="requires a frozen"):
        runner.run_benchmark(endpoint="http://localhost/v1", model="served", out_dir=tmp_path / "run",
            code_revision="sha", track="production_real")
    assert not (tmp_path / "run").exists()
