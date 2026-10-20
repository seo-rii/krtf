"""Prospective workload, source seals, output budgets and resource ownership."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from eval import collect_followup_queue as collector
from eval import run_extended_suite as runner
from eval import run_followup_queue as queue
from eval.hf_qa import canonical
from test_followup_queue import frozen_plan, mock_runtime, rewrite_proof


@pytest.fixture
def confirmation_plan(frozen_plan, monkeypatch, tmp_path):
    plan = deepcopy(frozen_plan)
    plan.update(kind=queue.CONFIRMATION_KIND, run_id="confirmation_queue",
                require_idle_gpu=True, stages=[])
    plan["proofs"].pop("blind_document")
    rows = [{"authored_index": i} for i in range(1152)]
    path = tmp_path / "routing_confirmation.json"
    path.write_bytes(canonical({"authored_experiment": "routing_confirmation"}))
    spec = {
        "request_count": 1152, "envelope_sha256": queue.file_hash(path),
        "requests_sha256": hashlib.sha256(b"".join(canonical(r) for r in rows)).hexdigest(),
        "models": {key: {"path": model["path"], "request_count": 1152,
                         "max_prompt_tokens": 7424, "overflow_count": 0}
                   for key, model in plan["models"].items()},
    }
    for experiment, model in queue.CONFIRMATION_ORDER:
        plan["stages"].append({"id": experiment + "_" + model, "experiment": experiment,
            "model_key": model, "requests_file": str(path),
            **{k: spec[k] for k in ("request_count", "requests_sha256", "envelope_sha256")}})
    rewrite_proof(plan, "preparation", lambda p:
                  p.update(experiments={"routing_confirmation": spec}))
    monkeypatch.setattr(runner, "load_request_file", lambda path:
                        (rows, {"experiment": "routing_confirmation"}, {"authored": True}))
    return plan


def test_confirmation_seals_and_768_token_output_reservation(confirmation_plan):
    assert queue.verify_inputs(confirmation_plan)["unit"]["exit_code"] == 0
    assert sum(s["request_count"] for s in confirmation_plan["stages"]) == 2304
    rewrite_proof(confirmation_plan, "preparation", lambda p:
        p["experiments"]["routing_confirmation"]["models"]["qwen27b"].update(max_prompt_tokens=7425))
    with pytest.raises(ValueError, match="token"):
        queue.verify_inputs(confirmation_plan)


@pytest.mark.parametrize("mutation", [
    lambda p: p.pop("require_idle_gpu"),
    lambda p: p["stages"].reverse(),
    lambda p: p["stages"][0].update(request_count=768),
    lambda p: p["stages"][1].update(requests_sha256="0" * 64),
])
def test_confirmation_design_cannot_silently_change(confirmation_plan, mutation):
    mutation(confirmation_plan)
    with pytest.raises(ValueError):
        queue.validate_plan(confirmation_plan)


def test_idle_wait_preserves_foreign_processes(monkeypatch):
    outputs = iter(["123\n456\n", "456\n", ""])
    observations, sleeps = [], []
    monkeypatch.setattr(queue.subprocess, "check_output", lambda *a, **kw: next(outputs))
    monkeypatch.setattr(queue.time, "sleep", sleeps.append)
    queue.wait_for_idle_gpu({"resource_wait_seconds": 600}, lambda **kw: observations.append(kw))
    assert sleeps == [30, 30]
    assert observations[0]["other_gpu_clients"] == [123, 456]
    assert observations[-1]["phase"] == "GPU_IDLE_VERIFIED"


def test_idle_wait_deadline_does_not_start_or_stop_any_process(monkeypatch):
    times = iter([0, 2])
    monkeypatch.setattr(queue.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(queue.subprocess, "check_output", lambda *a, **kw: "456\n")
    monkeypatch.setattr(queue.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not launch"))
    monkeypatch.setattr(queue.os, "killpg", lambda *a, **kw: pytest.fail("must not stop foreign work"))
    with pytest.raises(RuntimeError, match="no other process"):
        queue.wait_for_idle_gpu({"resource_wait_seconds": 1}, lambda **kw: None)


def test_confirmation_queue_runs_both_models_after_one_stage_fails(confirmation_plan, monkeypatch):
    calls, stopped, servers = mock_runtime(monkeypatch, confirmation_plan,
        failed_stage=confirmation_plan["stages"][0]["id"])
    waits = []
    monkeypatch.setattr(queue, "wait_for_idle_gpu", lambda *args: waits.append(True))
    assert queue.run_queue(confirmation_plan) == 1
    assert calls == [s["id"] for s in confirmation_plan["stages"]]
    assert len(waits) == len(servers) == 2
    assert all(server in stopped for server in servers)
    state = json.loads(Path(confirmation_plan["status_path"]).read_text())
    assert state["stages"][1]["status"] == "COMPLETE"


def test_confirmation_collector_reparses_raw_responses(confirmation_plan, monkeypatch, tmp_path):
    from eval import report_extended_suite
    def reject_unsealed(root):
        raise ValueError("unsealed confirmation output")
    monkeypatch.setattr(report_extended_suite, "prepare_report", reject_unsealed)
    with pytest.raises(ValueError, match="unsealed confirmation"):
        collector.verify_stage(tmp_path, confirmation_plan["stages"][0], confirmation_plan)
