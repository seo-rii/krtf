"""Fresh efficiency workload, sealed inputs, and ownership of GPU resources."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from eval import report_extended_suite  # Import before request-loader fixture patches.
from eval import collect_followup_queue as collector
from eval import run_extended_suite as runner
from eval import run_followup_queue as queue
from eval.hf_qa import canonical
from test_followup_queue import frozen_plan, mock_runtime, rewrite_proof


@pytest.fixture
def efficiency_plan(frozen_plan, monkeypatch, tmp_path):
    plan = deepcopy(frozen_plan)
    plan.update(kind=queue.EFFICIENCY_KIND, run_id="efficiency_queue",
                require_idle_gpu=True, stages=[])
    plan["proofs"].pop("blind_document")
    rows = [{"authored_index": i} for i in range(320)]
    path = tmp_path / "evidence_efficiency.json"
    path.write_bytes(canonical({"authored_experiment": "evidence_efficiency"}))
    spec = {
        "request_count": 320, "envelope_sha256": queue.file_hash(path),
        "requests_sha256": hashlib.sha256(b"".join(canonical(r) for r in rows)).hexdigest(),
        "models": {key: {"path": model["path"], "request_count": 320,
                         "max_prompt_tokens": 7424, "overflow_count": 0}
                   for key, model in plan["models"].items()},
    }
    for experiment, model in queue.EFFICIENCY_ORDER:
        plan["stages"].append({"id": experiment + "_" + model, "experiment": experiment,
            "model_key": model, "requests_file": str(path),
            **{k: spec[k] for k in ("request_count", "requests_sha256", "envelope_sha256")}})
    rewrite_proof(plan, "preparation", lambda p:
                  p.update(experiments={"evidence_efficiency": spec}))
    monkeypatch.setattr(runner, "load_request_file", lambda path:
                        (rows, {"experiment": "evidence_efficiency"}, {"authored": True}))
    return plan


def test_efficiency_matrix_and_768_token_reservation(efficiency_plan):
    assert queue.EFFICIENCY_COUNTS == {"evidence_efficiency": 320}
    assert queue.EFFICIENCY_ORDER == [("evidence_efficiency", "gemma12b"),
                                      ("evidence_efficiency", "qwen27b")]
    assert queue.verify_inputs(efficiency_plan)["unit"]["exit_code"] == 0
    assert sum(s["request_count"] for s in efficiency_plan["stages"]) == 640
    rewrite_proof(efficiency_plan, "preparation", lambda p:
        p["experiments"]["evidence_efficiency"]["models"]["qwen27b"].update(max_prompt_tokens=7425))
    with pytest.raises(ValueError, match="token"):
        queue.verify_inputs(efficiency_plan)


@pytest.mark.parametrize("mutation", [
    lambda p: p.pop("require_idle_gpu"),
    lambda p: p["stages"].reverse(),
    lambda p: p["stages"][0].update(request_count=319),
    lambda p: p["stages"][1].update(requests_sha256="0" * 64),
    lambda p: p["stages"][1].update(requests_file="other-source.json"),
])
def test_efficiency_design_cannot_silently_change(efficiency_plan, mutation):
    mutation(efficiency_plan)
    with pytest.raises(ValueError):
        queue.validate_plan(efficiency_plan)


@pytest.mark.parametrize("mutation", [
    lambda p: p["experiments"]["evidence_efficiency"].update(requests_sha256="0" * 64),
    lambda p: p["experiments"]["evidence_efficiency"]["models"]["gemma12b"].update(overflow_count=1),
    lambda p: p["experiments"]["evidence_efficiency"]["models"]["qwen27b"].update(path="/other-model"),
])
def test_efficiency_token_proof_binds_frozen_input_and_checkpoint(efficiency_plan, mutation):
    rewrite_proof(efficiency_plan, "preparation", mutation)
    with pytest.raises(ValueError):
        queue.verify_inputs(efficiency_plan)


def test_efficiency_envelope_tamper_is_rejected_before_loading(efficiency_plan, monkeypatch):
    Path(efficiency_plan["stages"][0]["requests_file"]).write_text("{}")
    monkeypatch.setattr(runner, "load_request_file", lambda path: pytest.fail("must verify file first"))
    with pytest.raises(ValueError, match="request envelope changed"):
        queue.verify_inputs(efficiency_plan)


def test_efficiency_idle_wait_preserves_foreign_processes(monkeypatch):
    outputs = iter(["123\n456\n", "456\n", ""])
    observations, sleeps = [], []
    monkeypatch.setattr(queue.subprocess, "check_output", lambda *a, **kw: next(outputs))
    monkeypatch.setattr(queue.time, "sleep", sleeps.append)
    monkeypatch.setattr(queue.os, "killpg", lambda *a, **kw: pytest.fail("must not stop foreign work"))
    queue.wait_for_idle_gpu({"resource_wait_seconds": 600}, lambda **kw: observations.append(kw))
    assert sleeps == [30, 30]
    assert observations[0]["other_gpu_clients"] == [123, 456]
    assert observations[-1]["phase"] == "GPU_IDLE_VERIFIED"


def test_efficiency_resource_deadline_never_launches_or_stops_processes(monkeypatch):
    times = iter([0, 2])
    monkeypatch.setattr(queue.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(queue.subprocess, "check_output", lambda *a, **kw: "456\n")
    monkeypatch.setattr(queue.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not launch"))
    monkeypatch.setattr(queue.os, "killpg", lambda *a, **kw: pytest.fail("must not stop foreign work"))
    with pytest.raises(RuntimeError, match="no other process"):
        queue.wait_for_idle_gpu({"resource_wait_seconds": 1}, lambda **kw: None)


def test_efficiency_queue_runs_second_model_after_first_stage_failure(efficiency_plan, monkeypatch):
    calls, stopped, servers = mock_runtime(monkeypatch, efficiency_plan,
        failed_stage=efficiency_plan["stages"][0]["id"])
    waits = []
    monkeypatch.setattr(queue, "wait_for_idle_gpu", lambda *args: waits.append(True))
    assert queue.run_queue(efficiency_plan) == 1
    assert calls == [s["id"] for s in efficiency_plan["stages"]]
    assert len(waits) == len(servers) == 2
    assert all(server in stopped for server in servers)
    state = json.loads(Path(efficiency_plan["status_path"]).read_text())
    assert state["stages"][1]["status"] == "COMPLETE"


def test_efficiency_collector_requires_sealed_raw_regrade(efficiency_plan, monkeypatch, tmp_path):
    def reject_unsealed(root):
        raise ValueError("unsealed efficiency output")
    monkeypatch.setattr(report_extended_suite, "prepare_report", reject_unsealed)
    with pytest.raises(ValueError, match="unsealed efficiency"):
        collector.verify_stage(tmp_path, efficiency_plan["stages"][0], efficiency_plan)


def test_efficiency_runner_preserves_easy_and_checked_selective_schemas(tmp_path, monkeypatch):
    from eval import evidence_efficiency as suite
    from test_evidence_efficiency import prepare, response, source_record

    sources = [source_record(case="easy"), source_record(case="checked", collision=True,
        text="휘온의 관할은 대한민국이며 현재 운영 중인 업무 절차로서 내부 직원에게 적용한다. 담당자는 확인했다.")]
    envelope, _ = prepare(sources)
    by_prompt = {(row["system"], row["user"]): row for row in envelope["requests"]}
    calls = []

    def fake_request(endpoint, *, payload=None, timeout):
        if endpoint.endswith("/models"):
            return {"data": [{"id": "fixture-model"}]}
        row = by_prompt[tuple(message["content"] for message in payload["messages"])]
        assert payload["max_tokens"] == 768
        assert payload["response_format"]["json_schema"]["schema"] == suite.evidence_efficiency_schema(row)
        answer = response(row)
        calls.append((row["case_id"], row["condition"]))
        return {"choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}

    monkeypatch.setattr(runner, "_request_json", fake_request)
    request_path = tmp_path / "requests.json"
    request_path.write_bytes(canonical(envelope))
    output = tmp_path / "output"
    manifest = runner.run_benchmark(requests_file=request_path,
        endpoint="http://127.0.0.1:18118/v1", model="fixture-model",
        out_dir=output, code_revision="f" * 40)
    assert calls == [(row["case_id"], row["condition"]) for row in envelope["requests"]]
    assert manifest["status"] == "COMPLETE"
    schema_key = lambda row: json.dumps([row["case_id"], row["condition"]],
                                       ensure_ascii=False, separators=(",", ":"))
    assert manifest["answer_schema"] == {schema_key(row): suite.evidence_efficiency_schema(row)
                                         for row in envelope["requests"]}
    selective = {row["case_id"]: row for row in envelope["requests"]
                 if row["condition"] == "selective_compact"}
    assert {row["evidence_required"] for row in selective.values()} == {False, True}
    easy = next(row for row in selective.values() if not row["evidence_required"])
    checked = next(row for row in selective.values() if row["evidence_required"])
    required = lambda row: set(suite.evidence_efficiency_schema(row)["properties"]["selections"]["items"]["required"])
    assert required(easy) == {"r", "e"}
    assert required(checked) == {"r", "e", "s", "q", "a"}
    _, rows, records, graded, counts = report_extended_suite.read_run(output)
    assert graded == runner.grade_outputs(rows, records, envelope["protocol"])
    assert counts["malformed_count"] == counts["error_count"] == 0
    assert len(graded["cases"]) == 10
    for case in graded["cases"]:
        assert case["proposal_correct_id"]
        assert case["accepted_correct_id"] is (case["case_id"] == easy["case_id"])
    summary = report_extended_suite.prepare_report(output)
    assert summary["by_variant"]["selective_compact"]["proposal_correct_id"] == 2
    assert summary["by_variant"]["selective_compact"]["accepted_correct_id"] == 1
    assert "Correct ID proposals" in report_extended_suite.render_markdown(summary)
    # Re-sealing a modified manifest cannot erase the easy/checked distinction.
    manifest["answer_schema"][schema_key(easy)] = suite.evidence_efficiency_schema(checked)
    manifest.pop("seal_sha256")
    manifest["seal_sha256"] = hashlib.sha256(canonical(manifest)).hexdigest()
    (output / "run_manifest.json").write_bytes(canonical(manifest))
    with pytest.raises(ValueError, match="manifest disagree"):
        report_extended_suite.read_run(output)
