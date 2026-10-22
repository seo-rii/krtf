"""Frozen closure matrix, source proofs and shadow-only approval contracts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from eval import collect_followup_queue as collector
from eval import report_extended_suite as reporter
from eval import run_extended_suite as runner
from eval import run_followup_queue as queue
from eval.hf_qa import canonical
from test_followup_queue import frozen_plan, mock_runtime, rewrite_proof
from test_evidence_robustness_queue import publish_predecessor


CONDITIONS = ["manual_legacy", "closure_legacy", "manual_null", "closure_null", "closure_bundle"]


@pytest.fixture
def closure_plan(frozen_plan, monkeypatch, tmp_path):
    plan = deepcopy(frozen_plan)
    plan.update(kind=queue.CLOSURE_KIND, run_id="evidence_closure_queue", require_idle_gpu=True,
                stages=[], predecessor={"run_id": "published_support_confirmation",
                    "status_path": str(tmp_path / "predecessor.status.json"),
                    "publication_marker": str(tmp_path / "predecessor.publication.json")})
    plan["proofs"].pop("blind_document")
    rows = [{"authored_index": index} for index in range(480)]
    path = tmp_path / "evidence_closure.json"
    path.write_bytes(canonical({"authored_experiment": "evidence_closure"}))
    spec = {"request_count": 480, "envelope_sha256": queue.file_hash(path),
        "requests_sha256": hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
        "models": {key: {"path": model["path"], "request_count": 480,
                          "max_prompt_tokens": 7424, "overflow_count": 0}
                   for key, model in plan["models"].items()}}
    for experiment, model in queue.CLOSURE_ORDER:
        plan["stages"].append({"id": experiment + "_" + model, "experiment": experiment,
            "model_key": model, "requests_file": str(path),
            **{key: spec[key] for key in ("request_count", "requests_sha256", "envelope_sha256")}})
    rewrite_proof(plan, "preparation", lambda proof:
                  proof.update(experiments={"evidence_closure": spec}))
    monkeypatch.setattr(runner, "load_request_file", lambda path:
                        (rows, {"experiment": "evidence_closure", "conditions": CONDITIONS},
                         {"source": {"evaluation_population": "FRESH_AI_AUTHORED_CONFIRMATION"}}))
    return plan


def test_closure_exact_960_call_matrix_and_preparation_proofs(closure_plan):
    assert queue.CLOSURE_KIND == "ktrf_evidence_closure_v1"
    assert queue.CLOSURE_COUNTS == {"evidence_closure": 480}
    assert queue.CLOSURE_ORDER == [("evidence_closure", "gemma12b"), ("evidence_closure", "qwen27b")]
    assert sum(stage["request_count"] for stage in closure_plan["stages"]) == 960
    assert queue.verify_inputs(closure_plan)["unit"]["exit_code"] == 0


@pytest.mark.parametrize("mutation", [
    lambda plan: plan.pop("require_idle_gpu"),
    lambda plan: plan["stages"].reverse(),
    lambda plan: plan["stages"][0].update(request_count=479),
    lambda plan: plan["stages"][1].update(requests_sha256="0" * 64),
    lambda plan: plan["stages"][1].update(requests_file="different-source.json"),
    lambda plan: plan.pop("predecessor"),
    lambda plan: plan["predecessor"].update(run_id=plan["run_id"]),
    lambda plan: plan["predecessor"].update(publication_marker="relative.json"),
])
def test_closure_fails_closed_on_matrix_or_dependency_change(closure_plan, mutation):
    mutation(closure_plan)
    with pytest.raises(ValueError):
        queue.validate_plan(closure_plan)


@pytest.mark.parametrize("mutation", [
    lambda proof: proof["experiments"]["evidence_closure"].update(requests_sha256="0" * 64),
    lambda proof: proof["experiments"]["evidence_closure"]["models"]["gemma12b"].update(overflow_count=1),
    lambda proof: proof["experiments"]["evidence_closure"]["models"]["qwen27b"].update(path="/other-model"),
    lambda proof: proof["experiments"]["evidence_closure"]["models"]["qwen27b"].update(max_prompt_tokens=7425),
])
def test_closure_tokenizer_proof_binds_source_model_and_768_output_reserve(closure_plan, mutation):
    rewrite_proof(closure_plan, "preparation", mutation)
    with pytest.raises(ValueError):
        queue.verify_inputs(closure_plan)


def test_closure_checks_publication_before_touching_idle_gpu(closure_plan, monkeypatch):
    calls, _, servers = mock_runtime(monkeypatch, closure_plan)
    monkeypatch.setattr(queue, "wait_for_idle_gpu", lambda *args: pytest.fail("predecessor must be checked first"))
    assert queue.run_queue(closure_plan) == 1
    assert calls == servers == []
    state = json.loads(Path(closure_plan["status_path"]).read_text())
    assert not any(stage["benchmark_started"] for stage in state["stages"])


def test_closure_rechecks_publication_before_qwen(closure_plan, monkeypatch):
    publish_predecessor(closure_plan)
    calls, _, servers = mock_runtime(monkeypatch, closure_plan)
    def remove_publication(*args):
        Path(closure_plan["predecessor"]["publication_marker"]).unlink()
    monkeypatch.setattr(queue, "wait_for_idle_gpu", remove_publication)
    assert queue.run_queue(closure_plan) == 1
    assert calls == [closure_plan["stages"][0]["id"]]
    assert len(servers) == 1


def test_closure_runs_models_serially_and_stops_only_owned_servers(closure_plan, monkeypatch):
    publish_predecessor(closure_plan)
    calls, stopped, servers = mock_runtime(monkeypatch, closure_plan)
    monkeypatch.setattr(queue, "wait_for_idle_gpu", lambda *args: None)
    assert queue.run_queue(closure_plan) == 0
    assert calls == [stage["id"] for stage in closure_plan["stages"]]
    assert len(servers) == 2 and all(server in stopped for server in servers)


def test_closure_collector_rejects_unsealed_model_outputs(closure_plan, monkeypatch, tmp_path):
    def reject_unsealed(root):
        raise ValueError("unsealed closure output")
    monkeypatch.setattr(reporter, "prepare_report", reject_unsealed)
    with pytest.raises(ValueError, match="unsealed closure output"):
        collector.verify_stage(tmp_path, closure_plan["stages"][0], closure_plan)


@pytest.mark.parametrize("count", [2, 4, 6, 8])
def test_closure_protocol_requires_complete_five_condition_factorial(count):
    protocol = {"kind": runner.PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": "evidence_closure",
                "conditions": ["condition_" + str(index) for index in range(count)], "repeat_count": 1,
                "limitations": ["unit fixture"]}
    with pytest.raises(ValueError, match="requires"):
        runner.validate_protocol(protocol)


def test_closure_per_request_schema_sealed_regrading_and_shadow_layers(tmp_path, monkeypatch):
    from eval import evidence_closure as suite
    from test_evidence_efficiency import FixtureTokenizer, provenance, source_record

    sources = [source_record(case="resolved"), source_record(case="ambiguous", collision=True,
                   text="별도 검토 기록: 대한민국에서 현재 운영 중인 업무 절차 휘온은 내부 직원에게 적용한다."),
               source_record(case="nil", expected=None, text="휘온에 대해서는 아직 확인하지 않았다.")]
    for index, source in enumerate(sources):
        source["document_length_band"] = "long" if index == 1 else "short"
    models = {key: {"path": "unit-fixture", "revision": "unit"} for key in ("gemma12b", "qwen27b")}
    envelope, _ = suite.prepare_evidence_closure(records=sources, models=models,
        tokenizers={key: FixtureTokenizer() for key in models}, code_revision="f" * 40,
        source_provenance={**provenance(sources), "evaluation_population": suite.FRESH_POPULATION})
    by_prompt = {(row["system"], row["user"]): row for row in envelope["requests"]}

    def fake_request(endpoint, *, payload=None, timeout):
        if endpoint.endswith("/models"):
            return {"data": [{"id": "fixture-model"}]}
        row = by_prompt[tuple(message["content"] for message in payload["messages"])]
        assert payload["max_tokens"] == 768
        assert payload["response_format"]["json_schema"]["schema"] == suite.evidence_closure_schema(row)
        assert "SECRET_GOLD_NOT_VISIBLE" not in row["user"] + row["system"]
        if row["case_id"] == "nil":
            selection = {"r": row["reference_registry"]["request_ref"], "e": None}
            if not row["discriminated_abstention"]:
                selection.update(s="UNRESOLVED", q=[], a=[])
        else:
            entity = next(alias for alias, eid in row["reference_registry"]["entities"].items()
                          if eid == "global:control-a")
            selection = {"r": row["reference_registry"]["request_ref"], "e": entity, "s": "SUPPORT"}
            if row["condition"] == "closure_bundle":
                selection["b"] = next(alias for alias, bundle in row["bundle_inventory"]["bundles"].items()
                                      if bundle["entity_alias"] == entity)
            else:
                # Omit all source segment references while preserving the literal attribute claims.
                # Server closure can restore these references; manual conditions must remain rejected.
                selection.update(q=[], a=[item["attribute_alias"]
                                           for item in row["support_inventory"]["attributes"]])
        answer = {"selections": [selection]}
        return {"choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}}

    monkeypatch.setattr(runner, "_request_json", fake_request)
    request_file = tmp_path / "requests.json"
    request_file.write_bytes(canonical(envelope))
    output = tmp_path / "output"
    manifest = runner.run_benchmark(requests_file=request_file,
        endpoint="http://127.0.0.1:18120/v1", model="fixture-model", out_dir=output, code_revision="f" * 40)
    assert manifest["status"] == "COMPLETE"
    assert len(manifest["answer_schema"]) == len(envelope["requests"])
    _, rows, records, graded, counts = reporter.read_run(output)
    assert graded == runner.grade_outputs(rows, records, envelope["protocol"])
    assert counts["malformed_count"] == counts["error_count"] == 0
    for case in graded["cases"]:
        assert case["evaluation_only"] and case["execution_authority"] == "none"
        assert case["authorization_mode"] == "shadow"
        if case["case_id"] != "nil":
            assert case["proposal_correct_id"]
            assert case["production_guard_accepted_correct_id"] is (case["case_id"] == "resolved")
            assert case["shadow_accepted_correct_id"] is case["condition"].startswith("closure_")
            assert case["raw_accepted_correct_id"] is (case["condition"] == "closure_bundle")
    summary = reporter.prepare_report(output)
    assert summary["evaluation_population"] == suite.FRESH_POPULATION
    assert set(summary["source_strata"]["document_length_band"]) == {"short", "long"}
    assert summary["source_strata"]["document_length_band"]["long"]["questions"] == 1
    for condition, values in summary["by_variant"].items():
        assert values["production_guard_accepted_correct_id"] == 1
        assert values["shadow_accepted_correct_id"] == (2 if condition.startswith("closure_") else 0)
        assert values["null_wire_errors"] == 0
        assert summary["authorization_by_condition"][condition] == "EXPERIMENTAL_SIMULATED_APPROVAL"
    markdown = reporter.render_markdown(summary)
    assert "EXPERIMENTAL_SIMULATED_APPROVAL" in markdown
    assert "Server closure and null-wire diagnostics" in markdown
    assert "no execution authority" in markdown

    # A sealed grade cannot be silently edited even if the altered tally looks plausible.
    path = output / "graded.json"
    forged = json.loads(path.read_text())
    forged["cases"][0]["accepted_wrong_id"] = not forged["cases"][0]["accepted_wrong_id"]
    path.write_bytes(canonical(forged))
    with pytest.raises(ValueError, match="artifact hash"):
        reporter.read_run(output)


def test_closure_sealed_raw_foreign_references_are_never_repaired(tmp_path, monkeypatch):
    """Wire-valid foreign handles stay rejected after server closure and raw replay."""
    from eval import evidence_closure as suite
    from test_evidence_efficiency import FixtureTokenizer, provenance, source_record

    sources = [source_record()]
    models = {key: {"path": "unit-fixture", "revision": "unit"} for key in ("gemma12b", "qwen27b")}
    envelope, _ = suite.prepare_evidence_closure(records=sources, models=models,
        tokenizers={key: FixtureTokenizer() for key in models}, code_revision="f" * 40,
        source_provenance={**provenance(sources), "evaluation_population": suite.FRESH_POPULATION})
    by_prompt = {(row["system"], row["user"]): row for row in envelope["requests"]}

    def fake_request(endpoint, *, payload=None, timeout):
        if endpoint.endswith("/models"):
            return {"data": [{"id": "fixture-model"}]}
        row = by_prompt[tuple(message["content"] for message in payload["messages"])]
        assert payload["response_format"]["json_schema"]["schema"] == suite.evidence_closure_schema(row)
        entity = next(alias for alias, eid in row["reference_registry"]["entities"].items()
                      if eid == "global:control-a")
        selection = {"r": row["reference_registry"]["request_ref"], "e": entity, "s": "SUPPORT"}
        if row["condition"] == "closure_bundle":
            selection["b"] = "foreign-request:bundle"
        else:
            selection.update(q=["foreign-request:segment"], a=[
                item["attribute_alias"] for item in row["support_inventory"]["attributes"]])
        response = {"selections": [selection]}
        assert suite.evidence_closure_response_error(response, row) is None
        return {"choices": [{"message": {"content": json.dumps(response)}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}}

    monkeypatch.setattr(runner, "_request_json", fake_request)
    request_file = tmp_path / "requests.json"
    request_file.write_bytes(canonical(envelope))
    output = tmp_path / "output"
    manifest = runner.run_benchmark(requests_file=request_file, endpoint="http://127.0.0.1:18120/v1",
        model="fixture-model", out_dir=output, code_revision="f" * 40)
    assert manifest["status"] == "COMPLETE"
    _, _, _, graded, counts = reporter.read_run(output)
    assert counts["malformed_count"] == counts["error_count"] == 0
    assert len(graded["cases"]) == 5
    for case in graded["cases"]:
        bundle_error = case["condition"] == "closure_bundle"
        assert case["proposal_correct_id"] is (not bundle_error)
        assert not case["raw_validation_valid"]
        assert not case["closed_validation_valid"]
        assert not case["accepted_correct_id"] and not case["accepted_wrong_id"]
        # Production linking is an independent diagnostic, not evidence approval.
        # A foreign q must not silently change a valid underlying RESOLVED link.
        assert case["production_guard_accepted_correct_id"] is (not bundle_error)
        assert case["server_added_segments"] == []
        assert case["guard_violations"]
        assert case["execution_authority"] == "none"

    # Re-sealing a manifest does not permit changing the frozen per-request schema.
    path = output / "run_manifest.json"
    forged = json.loads(path.read_text())
    forged["answer_schema"][next(iter(forged["answer_schema"]))] = {"type": "object"}
    forged.pop("seal_sha256")
    forged["seal_sha256"] = hashlib.sha256(canonical(forged)).hexdigest()
    path.write_bytes(canonical(forged))
    with pytest.raises(ValueError, match="frozen envelope and manifest disagree"):
        reporter.read_run(output)
