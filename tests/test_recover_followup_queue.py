"""Bounded recovery keeps the completed model sealed and starts only missing Gemma."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace

import pytest

from eval import recover_followup_queue as recovery
from eval.hf_qa import canonical
from test_evidence_closure_queue import closure_plan
from test_followup_queue import frozen_plan, rewrite_proof


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))
    return {"path": str(path), "sha256": recovery.file_hash(path)}


@pytest.fixture
def recovery_case(closure_plan, tmp_path, monkeypatch, request):
    original = deepcopy(closure_plan)
    original.update(run_id=recovery.ORIGINAL_RUN_ID, code_revision=recovery.ORIGINAL_CODE_REVISION,
                    log_dir=str(Path(original["run_root"]) / "logs"),
                    launch_environment={"TMPDIR": str(Path(original["run_root"]) / "tmp"),
                                        "VLLM_RPC_BASE_PATH": "/tmp/old-owned-ipc"})
    original["models"]["gemma12b"]["gpu_memory_utilization"] = .45
    for name in original["proofs"]:
        rewrite_proof(original, name, lambda proof: proof.update(code_revision=original["code_revision"]))
    qwen = original["stages"][1]
    terminal = {"kind": original["kind"], "run_id": original["run_id"],
                "code_revision": original["code_revision"], "pid": 987654,
                "plan_sha256": hashlib.sha256(canonical(original)).hexdigest(),
                "status": "FAILED", "phase": "FINISHED", "exit_code": 1,
                "stages": [{**{key: original["stages"][0][key] for key in ("id", "experiment", "request_count")},
                            "status": "FAILED", "exit_code": 1, "benchmark_started": False},
                           {**{key: qwen[key] for key in ("id", "experiment", "request_count")},
                            "status": "COMPLETE", "exit_code": 0, "benchmark_started": True,
                            "benchmark_exit_code": 0, "report_exit_code": 0,
                            "received_count": 480, "missing_count": 0, "error_count": 0, "malformed_count": 0}]}
    original_pin = write(tmp_path / "original-plan.json", original)
    status_pin = write(tmp_path / "original-status.json", terminal)
    root = tmp_path / "recovery"
    (root / "logs").mkdir(parents=True)
    (root / "tmp").mkdir()
    plan = deepcopy(original)
    plan.update(run_id="closure-missing-gemma-recovery", run_root=str(root),
                log_dir=str(root / "logs"), status_path=str(root / "logs/queue.status.json"),
                log_path=str(root / "logs/queue.log"),
                port=18124, driver_code_revision="b" * 40,
                retry_from={"plan_path": original_pin["path"], "plan_sha256": original_pin["sha256"],
                            "status_path": status_pin["path"], "status_sha256": status_pin["sha256"]})
    plan["models"]["gemma12b"]["gpu_memory_utilization"] = .75
    collector_status = {"run_id": original["run_id"], "pid": 876543,
                        "status": "FAILED", "phase": "FINISHED", "exit_code": 1,
                        "publication_complete": True, "missing_stages": [original["stages"][0]["id"]],
                        "verified_reports": [qwen["id"]], "remote": terminal}
    collector_exit = {"status": "FAILED", "exit_code": 1, "child_pid": collector_status["pid"]}
    out = Path(original["run_root"]) / "results" / qwen["id"]
    out.mkdir(parents=True)
    hashes = {}
    for name in recovery.REUSED_ARTIFACTS:
        (out / name).write_bytes(b"sealed " + name.encode())
        hashes[name] = recovery.file_hash(out / name)
    driver_source = tmp_path / "driver-source"
    worker = driver_source / "eval/recover_followup_queue.py"
    worker.parent.mkdir(parents=True)
    worker.write_bytes(Path(recovery.__file__).read_bytes())
    helper = driver_source / "eval/helper.py"
    helper.write_bytes(b"# frozen helper\n")
    archive = tmp_path / "driver.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(worker, arcname="eval/recover_followup_queue.py")
        stream.add(helper, arcname="eval/helper.py")
    monkeypatch.setattr(recovery, "__file__", str(worker))
    ipc_tmp = tempfile.TemporaryDirectory(prefix="ktrf-recovery-ipc-")
    request.addfinalizer(ipc_tmp.cleanup)
    ipc = Path(ipc_tmp.name)
    ipc.chmod(0o700)
    plan["launch_environment"] = {"TMPDIR": str(root / "tmp"), "VLLM_RPC_BASE_PATH": str(ipc)}
    plan["startup_preflight"] = write(root / "logs/ipc.status.json", {
        "status": "COMPLETE", "exit_code": 0, "code_revision": plan["code_revision"],
        "actual_vllm_address_bound": True, "ipc_dir": str(ipc), "endpoint_bytes": 80})
    spec = {"kind": recovery.KIND, "driver_code_revision": plan["driver_code_revision"],
            "driver_source": str(driver_source), "driver_source_archive": str(archive),
            "driver_archive_sha256": recovery.file_hash(archive),
            "original_collector_status": write(tmp_path / "collector-status.json", collector_status),
            "original_collector_exit": write(tmp_path / "collector-exit.json", collector_exit),
            "reused_stage_artifacts_sha256": hashes, "ipc_dir": str(ipc)}
    frozen_calls = []
    def frozen_call(bound_plan, *, stage=None, out=None):
        frozen_calls.append((deepcopy(bound_plan), stage, out))
        if stage is None:
            return {}
        counts = {"received_count": 480, "missing_count": 0, "error_count": 0, "malformed_count": 0}
        return {"status": "COMPLETE", "counts": counts}, {"sealed": True}, {"original": True}
    monkeypatch.setattr(recovery, "_frozen_call", frozen_call)
    monkeypatch.setattr(recovery, "_assert_dead", lambda pid: None)
    return SimpleNamespace(plan=plan, original=original, terminal=terminal, spec=spec, out=out,
                           collector_status=collector_status, collector_exit=collector_exit,
                           root=root, frozen_calls=frozen_calls)


def test_origin_preserves_exact_frozen_matrix_and_reused_stage(recovery_case):
    case = recovery_case
    context = recovery.validate_recovery_origin(case.plan, case.original, case.terminal)
    assert context["gemma_stage"]["request_count"] == 480
    assert context["qwen_stage"]["request_count"] == 480
    assert context["reused_from"]["result_path"] == str(case.out)
    assert recovery.reused_stage_state(context) == {
        **case.terminal["stages"][1], "reused_from": context["reused_from"],
        "new_model_calls": 0, "reused_model_calls": 480}


@pytest.mark.parametrize("mutation", [
    lambda c: c.plan["stages"][0].update(requests_sha256="1" * 64),
    lambda c: c.plan["models"]["qwen27b"].update(gpu_memory_utilization=.7),
    lambda c: c.plan["models"]["gemma12b"].update(served_name="other-model"),
    lambda c: c.plan["models"]["gemma12b"].update(gpu_memory_utilization=.45),
    lambda c: c.plan.update(code_revision="1" * 40),
    lambda c: c.plan.update(source="/other/source"),
    lambda c: c.plan.update(port=c.original["port"]),
    lambda c: c.plan.update(log_path="/tmp/foreign.log"),
    lambda c: c.plan["launch_environment"].update(TMPDIR="/tmp"),
    lambda c: c.plan["launch_environment"].update(VLLM_RPC_BASE_PATH="/tmp/old-owned-ipc"),
    lambda c: c.plan["startup_preflight"].update(path="/tmp/old-ipc-proof.json"),
    lambda c: c.plan.update(run_root=c.original["run_root"]),
    lambda c: c.terminal["stages"][0].update(benchmark_started=True),
    lambda c: c.terminal["stages"][0].update(received_count=1),
    lambda c: c.terminal["stages"][1].update(received_count=479),
    lambda c: c.terminal["stages"][1].update(status="FAILED", exit_code=1),
    lambda c: c.terminal.update(status="RUNNING", exit_code=None),
])
def test_origin_rejects_changed_experiment_or_any_started_gemma(recovery_case, mutation):
    mutation(recovery_case)
    with pytest.raises(ValueError):
        recovery.validate_recovery_origin(recovery_case.plan, recovery_case.original, recovery_case.terminal)


@pytest.mark.parametrize("mutation", [
    lambda c: c.collector_status.update(publication_complete=False),
    lambda c: c.collector_status.update(missing_stages=[]),
    lambda c: c.collector_status.update(verified_reports=[]),
    lambda c: c.collector_status.update(exit_code=0, status="COMPLETE"),
    lambda c: c.collector_exit.update(child_pid=99),
    lambda c: c.collector_exit.update(exit_code=None, status="RUNNING"),
])
def test_partial_failure_requires_completed_publication_and_matching_collector_exit(recovery_case, mutation):
    case = recovery_case
    mutation(case)
    with pytest.raises(ValueError, match="collected, published and exited"):
        recovery.validate_recovery_publication(case.plan, case.original, case.terminal,
                                              case.collector_status, case.collector_exit)


def test_all_prior_outputs_are_regraded_before_any_new_gpu_activity(recovery_case):
    case = recovery_case
    context = recovery.verify_recovery_inputs(case.plan, case.spec)
    assert context["reused_identity"] == {"sealed": True}
    assert [entry[0] for entry in case.frozen_calls] == [case.original, case.plan, case.original]
    assert case.frozen_calls[-1][1] == case.original["stages"][1]
    assert not (case.root / "results").exists()
    assert not Path(case.plan["status_path"]).exists()


@pytest.mark.parametrize("target", list(recovery.REUSED_ARTIFACTS))
def test_recovery_refuses_every_changed_qwen_artifact(recovery_case, target):
    case = recovery_case
    with (case.out / target).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="artifact changed"):
        recovery.verify_recovery_inputs(case.plan, case.spec)
    assert not Path(case.plan["status_path"]).exists()


@pytest.mark.parametrize("target", ["old-gemma", "new-results", "new-status", "ipc-content", "driver-helper"])
def test_recovery_refuses_partial_old_answers_existing_destination_or_unfrozen_driver(recovery_case, target):
    case = recovery_case
    if target == "old-gemma":
        path = Path(case.original["run_root"]) / "results" / case.original["stages"][0]["id"]
        path.mkdir()
    elif target == "new-results":
        (case.root / "results").mkdir()
    elif target == "new-status":
        Path(case.plan["status_path"]).write_bytes(b"previous status")
    elif target == "ipc-content":
        (Path(case.spec["ipc_dir"]) / "foreign.sock").write_bytes(b"foreign")
    else:
        (Path(case.spec["driver_source"]) / "eval/helper.py").write_bytes(b"mutated helper")
    with pytest.raises(ValueError):
        recovery.verify_recovery_inputs(case.plan, case.spec)
    assert not case.frozen_calls


def test_driver_starts_only_gemma_and_keeps_qwen_bytes_unchanged(recovery_case, monkeypatch):
    case = recovery_case
    initial = {name: (case.out / name).read_bytes() for name in recovery.REUSED_ARTIFACTS}
    started, stopped, calls = [], [], []
    server = SimpleNamespace(returncode=0)
    benchmark = SimpleNamespace(returncode=0, poll=lambda: 0)
    monkeypatch.setattr(recovery, "wait_for_idle_gpu", lambda *args: None)
    def start(plan, model, stage, command, env, runtime, update):
        started.append((model, command, env))
        assert plan["schema_version"] == 4
        assert model == case.plan["models"]["gemma12b"]
        assert command[command.index("--gpu-memory-utilization") + 1] == "0.75"
        assert env["VLLM_RPC_BASE_PATH"] == case.spec["ipc_dir"]
        assert "PYTHONPATH" not in env
        return server, 80000, "http://127.0.0.1:18124/v1"
    monkeypatch.setattr(recovery, "start_model_runtime", start)
    def popen(command, **options):
        calls.append(command)
        assert options["cwd"] == case.original["source"]
        assert command[command.index("--code-revision") + 1] == recovery.ORIGINAL_CODE_REVISION
        assert command[command.index("--model") + 1] == case.plan["models"]["gemma12b"]["served_name"]
        out = Path(command[command.index("--out-dir") + 1])
        stage = case.plan["stages"][0]
        write(out / "run_manifest.json", {"request_corpus_sha256": stage["requests_sha256"],
            "frozen_request_file_sha256": stage["envelope_sha256"], "request_count": 480,
            "code_revision": recovery.ORIGINAL_CODE_REVISION, "experiment": stage["experiment"],
            "requested_model": case.plan["models"]["gemma12b"]["served_name"],
            "received_count": 480, "record_count": 480, "missing_count": 0, "error_count": 0,
            "malformed_count": 0})
        return benchmark
    monkeypatch.setattr(recovery.subprocess, "Popen", popen)
    monkeypatch.setattr(recovery.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(recovery, "stop_owned", lambda process: stopped.append(process))
    assert recovery.run_recovery(case.plan, case.spec, spec_sha256="f" * 64) == 0
    assert len(started) == len(calls) == 1
    assert stopped == [benchmark, server]
    assert {name: (case.out / name).read_bytes() for name in recovery.REUSED_ARTIFACTS} == initial
    assert not (case.root / "results" / case.plan["stages"][1]["id"]).exists()
    state = json.loads(Path(case.plan["status_path"]).read_text())
    assert state["status"] == "COMPLETE" and state["exit_code"] == 0
    assert state["planned_new_model_calls"] == state["new_model_calls"] == 480
    assert state["original_total_model_calls"] == 960 and state["reused_model_calls"] == 480
    assert state["driver_code_revision"] != state["code_revision"]
    assert state["stages"][1]["reused_from"]["result_path"] == str(case.out)
    assert case.frozen_calls[-1][0] == case.plan
    assert case.frozen_calls[-1][1] == case.plan["stages"][0]


def test_resource_wait_cannot_hide_a_changed_completed_stage(recovery_case, monkeypatch):
    case = recovery_case
    def wait(*args):
        (case.out / "responses.jsonl").write_bytes(b"changed while waiting")
    monkeypatch.setattr(recovery, "wait_for_idle_gpu", wait)
    monkeypatch.setattr(recovery, "start_model_runtime", lambda *args: pytest.fail("must not start a model"))
    monkeypatch.setattr(recovery, "stop_owned", lambda process: None)
    assert recovery.run_recovery(case.plan, case.spec, spec_sha256="f" * 64) == 1
    state = json.loads(Path(case.plan["status_path"]).read_text())
    assert state["stages"][0]["benchmark_started"] is False
    assert state["new_model_calls"] == 0
    assert state["stages"][1]["status"] == "COMPLETE"


@pytest.mark.parametrize("field,value", [("actual_vllm_address_bound", False),
                                          ("ipc_dir", "/tmp/other-ipc"),
                                          ("endpoint_bytes", 107),
                                          ("code_revision", "0" * 40)])
def test_ipc_preflight_must_bind_the_new_directory(recovery_case, field, value):
    case = recovery_case
    proof = json.loads(Path(case.plan["startup_preflight"]["path"]).read_text())
    proof[field] = value
    case.plan["startup_preflight"] = write(case.plan["startup_preflight"]["path"], proof)
    with pytest.raises(ValueError, match="actual-bind IPC preflight"):
        recovery.verify_recovery_inputs(case.plan, case.spec)
    assert not case.frozen_calls


def test_original_live_pid_is_checked_without_signalling_or_stopping_it(monkeypatch):
    probes = []
    monkeypatch.setattr(recovery.os, "kill", lambda pid, signal: probes.append((pid, signal)))
    with pytest.raises(ValueError, match="still running"):
        recovery._assert_dead(12345)
    assert probes == [(12345, 0)]


def test_frozen_helper_imports_use_original_source_and_clean_pythonpath(monkeypatch, tmp_path):
    observed = []
    monkeypatch.setenv("PYTHONPATH", "/different/unfrozen/source")
    def run(command, **options):
        observed.append((command, options))
        return SimpleNamespace(stdout='{"frozen":true}')
    monkeypatch.setattr(recovery.subprocess, "run", run)
    plan = {"source": str(tmp_path / "original-source"), "python": "/original/python"}
    assert recovery._frozen_call(plan) == {"frozen": True}
    command, options = observed[0]
    assert command[:2] == ["/original/python", "-c"]
    assert "verify_inputs" in command[2] and "verify_stage" in command[2]
    assert options["cwd"] == plan["source"]
    assert "PYTHONPATH" not in options["env"]
    assert json.loads(options["input"])["plan"] == plan
