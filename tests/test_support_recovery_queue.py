"""Discovery/confirmation partitioning and approval-contract separation."""
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


CONDITIONS = ["paragraph_all_production", "multispan_all_production",
              "multispan_observed_production", "multispan_supported_production",
              "paragraph_all_shadow", "multispan_all_shadow",
              "multispan_observed_shadow", "multispan_supported_shadow"]


@pytest.fixture(params=[False, True], ids=["discovery", "fresh_confirmation"])
def support_plan(request, frozen_plan, monkeypatch, tmp_path):
    confirmation = request.param
    plan = deepcopy(frozen_plan)
    plan.update(kind=queue.SUPPORT_CONFIRMATION_KIND if confirmation else queue.SUPPORT_KIND,
                run_id="support_confirmation" if confirmation else "support_discovery",
                require_idle_gpu=True, stages=[], predecessor={
                    "run_id": "support_discovery" if confirmation else "prior_published_queue",
                    "status_path": str(tmp_path / "predecessor.status.json"),
                    "publication_marker": str(tmp_path / "predecessor-publication.json")})
    plan["proofs"].pop("blind_document")
    count = 192 if confirmation else 512
    rows = [{"authored_index": i} for i in range(count)]
    conditions = [CONDITIONS[0], CONDITIONS[-1]] if confirmation else CONDITIONS
    source = {"source_sha256": "b" * 64, "review_sha256": "c" * 64}
    path = tmp_path / "support_recovery.json"
    path.write_bytes(canonical({"authored_experiment": "support_recovery"}))
    spec = {"request_count": count, "envelope_sha256": queue.file_hash(path),
        "requests_sha256": hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
        "models": {key: {"path": model["path"], "request_count": count,
                         "max_prompt_tokens": 7424, "overflow_count": 0}
                   for key, model in plan["models"].items()}}
    for experiment, model in queue.SUPPORT_ORDER:
        plan["stages"].append({"id": experiment + "_" + model, "experiment": experiment,
            "model_key": model, "requests_file": str(path),
            **{key: spec[key] for key in ("request_count", "requests_sha256", "envelope_sha256")}})
    rewrite_proof(plan, "preparation", lambda proof:
                  proof.update(experiments={"support_recovery": spec}))
    if confirmation:
        selection = {"kind": "ktrf_support_method_selection_v1", "phase": "FINAL_FROZEN",
            "discovery_run_id": plan["predecessor"]["run_id"], "discovery_code_revision": "d" * 40,
            "selected_condition": conditions[1], "baseline_condition": conditions[0],
            "fresh_source_sha256": source["source_sha256"], "fresh_review_sha256": source["review_sha256"],
            "selected_before_confirmation": True, "selection_uses_confirmation_outputs": False,
            "discovery_summary_sha256": {"gemma12b": "e" * 64, "qwen27b": "f" * 64},
            "selection_rule": "minimum_wrong_then_maximum_correct_then_lower_token_cost_v1",
            "evaluation_only": True, "real_execution": False}
        selected = tmp_path / "selection.json"
        selected.write_bytes(canonical(selection))
        plan["selection"] = {"path": str(selected), "sha256": queue.file_hash(selected)}
    monkeypatch.setattr(runner, "load_request_file", lambda path:
                        (rows, {"experiment": "support_recovery", "conditions": conditions}, {"source": source}))
    return plan


def test_support_exact_serial_counts_and_offline_proofs(support_plan):
    confirmation = support_plan["kind"] == queue.SUPPORT_CONFIRMATION_KIND
    assert queue.SUPPORT_COUNTS == {"support_recovery": 512}
    assert queue.SUPPORT_CONFIRMATION_COUNTS == {"support_recovery": 192}
    assert queue.SUPPORT_ORDER == [("support_recovery", "gemma12b"), ("support_recovery", "qwen27b")]
    assert sum(stage["request_count"] for stage in support_plan["stages"]) == (384 if confirmation else 1024)
    assert queue.verify_inputs(support_plan)["unit"]["exit_code"] == 0


@pytest.mark.parametrize("mutation", [
    lambda plan: plan.pop("require_idle_gpu"),
    lambda plan: plan.pop("predecessor"),
    lambda plan: plan["stages"].reverse(),
    lambda plan: plan["stages"][0].update(request_count=193),
    lambda plan: plan["stages"][1].update(requests_sha256="0" * 64),
])
def test_support_matrix_fails_closed(support_plan, mutation):
    mutation(support_plan)
    with pytest.raises(ValueError):
        queue.validate_plan(support_plan)


def test_support_does_not_start_before_predecessor_publication(support_plan, monkeypatch):
    calls, _, servers = mock_runtime(monkeypatch, support_plan)
    monkeypatch.setattr(queue, "wait_for_idle_gpu", lambda *args: pytest.fail("predecessor must be checked first"))
    assert queue.run_queue(support_plan) == 1
    assert calls == servers == []


def test_support_runs_models_serially_after_published_predecessor(support_plan, monkeypatch):
    publish_predecessor(support_plan)
    calls, stopped, servers = mock_runtime(monkeypatch, support_plan)
    monkeypatch.setattr(queue, "wait_for_idle_gpu", lambda *args: None)
    assert queue.run_queue(support_plan) == 0
    assert calls == [stage["id"] for stage in support_plan["stages"]]
    assert len(servers) == 2 and all(server in stopped for server in servers)


@pytest.mark.parametrize("mutate", [
    lambda selection: selection.update(selected_condition="paragraph_all_production"),
    lambda selection: selection.update(selected_condition="unregistered_method"),
    lambda selection: selection.update(selected_condition=[]),
    lambda selection: selection.update(discovery_run_id="different_discovery"),
    lambda selection: selection.update(fresh_source_sha256="0" * 64),
    lambda selection: selection.update(fresh_review_sha256="0" * 64),
    lambda selection: selection.update(selected_before_confirmation=False),
    lambda selection: selection.update(selection_uses_confirmation_outputs=True),
    lambda selection: selection.update(real_execution=True),
    lambda selection: selection.update(discovery_summary_sha256={"gemma12b": "e" * 64}),
])
def test_fresh_selection_has_no_confirmation_oracle_leak(support_plan, mutate):
    if support_plan["kind"] != queue.SUPPORT_CONFIRMATION_KIND:
        pytest.skip("selection applies only to fresh confirmation")
    spec = support_plan["selection"]
    path = Path(spec["path"])
    value = json.loads(path.read_text())
    mutate(value)
    path.write_bytes(canonical(value))
    spec["sha256"] = queue.file_hash(path)
    with pytest.raises(ValueError):
        queue.verify_inputs(support_plan)


def test_fresh_selection_content_tampering_rejected(support_plan):
    if support_plan["kind"] != queue.SUPPORT_CONFIRMATION_KIND:
        pytest.skip("selection applies only to fresh confirmation")
    Path(support_plan["selection"]["path"]).write_bytes(b"{}")
    with pytest.raises(ValueError, match="selection proof hash"):
        queue.verify_inputs(support_plan)


def test_support_collector_requires_sealed_raw_regrade(support_plan, monkeypatch, tmp_path):
    def reject_unsealed(root):
        raise ValueError("unsealed support output")
    monkeypatch.setattr(reporter, "prepare_report", reject_unsealed)
    with pytest.raises(ValueError, match="unsealed support output"):
        collector.verify_stage(tmp_path, support_plan["stages"][0], support_plan)


@pytest.mark.parametrize("count", [1, 3, 6, 7, 9])
def test_support_protocol_rejects_non_discovery_confirmation_counts(count):
    protocol = {"kind": runner.PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": "support_recovery",
                "conditions": ["condition_" + str(i) for i in range(count)], "repeat_count": 1,
                "limitations": ["unit fixture"]}
    with pytest.raises(ValueError, match="requires"):
        runner.validate_protocol(protocol)


def test_support_metrics_refuse_production_shadow_pooling():
    from test_evidence_efficiency import provenance, source_record
    from eval.evidence_efficiency import prepare_evidence_efficiency
    from test_evidence_efficiency import FixtureTokenizer
    records = [source_record()]
    models = {key: {"path": "unit", "revision": "unit"} for key in ("gemma12b", "qwen27b")}
    envelope, _ = prepare_evidence_efficiency(records=records, models=models,
        tokenizers={key: FixtureTokenizer() for key in models}, code_revision="a" * 40,
        source_provenance=provenance(records))
    graded = runner.grade_outputs(envelope["requests"], [], envelope["protocol"])
    first = graded["cases"][0]
    production = {**first, "authorization_mode": "production"}
    shadow = {**first, "authorization_mode": "shadow"}
    with pytest.raises(ValueError, match="must not be pooled"):
        runner._metrics([production, shadow], True)


@pytest.mark.parametrize("conditions", [CONDITIONS, [CONDITIONS[0], CONDITIONS[-1]]],
                         ids=["discovery_matrix", "selected_confirmation_pair"])
def test_support_runner_and_report_preserve_authorization_layers(tmp_path, monkeypatch, conditions):
    from eval import support_recovery as suite
    from test_evidence_efficiency import FixtureTokenizer, provenance, source_record
    sources = [source_record(case="resolved"), source_record(case="ambiguous", collision=True,
        text="휘온의 관할은 대한민국이며 현재 운영 중인 업무 절차로서 내부 직원에게 적용한다. 담당자는 확인했다.")]
    models = {key: {"path": "unit-fixture", "revision": "unit"}
              for key in ("gemma12b", "qwen27b")}
    population = suite.POPULATION if len(conditions) == 8 else suite.FRESH_POPULATION
    envelope, _ = suite.prepare_support_recovery(records=sources, models=models,
        tokenizers={key: FixtureTokenizer() for key in models}, code_revision="f" * 40,
        source_provenance={**provenance(sources), "evaluation_population": population},
        conditions=conditions)
    by_prompt = {(row["system"], row["user"]): row for row in envelope["requests"]}

    def fake_request(endpoint, *, payload=None, timeout):
        if endpoint.endswith("/models"):
            return {"data": [{"id": "fixture-model"}]}
        row = by_prompt[tuple(message["content"] for message in payload["messages"])]
        assert payload["max_tokens"] == 768
        assert payload["response_format"]["json_schema"]["schema"] == suite.support_recovery_schema(row)
        assert "SECRET_GOLD_NOT_VISIBLE" not in row["user"] + row["system"]
        selected = next(alias for alias, entity in row["reference_registry"]["entities"].items()
                        if entity == "global:control-a")
        answer = {"selections": [{"r": row["reference_registry"]["request_ref"], "e": selected,
            "s": "SUPPORT", "q": [item["segment_alias"] for item in row["support_inventory"]["segments"]],
            "a": [item["attribute_alias"] for item in row["support_inventory"]["attributes"]]}]}
        return {"choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)},
                              "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}

    monkeypatch.setattr(runner, "_request_json", fake_request)
    path = tmp_path / "requests.json"
    path.write_bytes(canonical(envelope))
    output = tmp_path / "output"
    manifest = runner.run_benchmark(requests_file=path,
        endpoint="http://127.0.0.1:18120/v1", model="fixture-model", out_dir=output, code_revision="f" * 40)
    assert manifest["status"] == "COMPLETE"
    assert len(manifest["answer_schema"]) == len(envelope["requests"])
    _, rows, records, graded, counts = reporter.read_run(output)
    assert graded == runner.grade_outputs(rows, records, envelope["protocol"])
    assert counts["malformed_count"] == counts["error_count"] == 0
    for case in graded["cases"]:
        assert case["proposal_correct_id"]
        assert case["production_guard_accepted_correct_id"] is (case["case_id"] == "resolved")
        assert case["shadow_accepted_correct_id"]
        assert case["accepted_correct_id"] is (case["case_id"] == "resolved" or case["authorization_mode"] == "shadow")
        assert case["execution_authority"] == "none" and case["evaluation_only"]
    summary = reporter.prepare_report(output)
    assert summary["evaluation_population"] == population
    assert set(summary["authorization_by_condition"]) == set(conditions)
    for condition, values in summary["by_variant"].items():
        assert values["production_guard_accepted_correct_id"] == 1
        assert values["shadow_accepted_correct_id"] == 2
        assert summary["support_inventory"][condition]["source_cases"] == 2
    markdown = reporter.render_markdown(summary)
    assert "EXPERIMENTAL_SIMULATED_APPROVAL" in markdown
    assert "no execution authority" in markdown
    assert "Support inventory and validation diagnostics" in markdown
