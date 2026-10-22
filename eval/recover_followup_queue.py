"""Recover only the never-started Gemma stage of the frozen closure experiment.

The completed Qwen output remains in its original directory and is regraded with
its original source/plan. This driver never repairs, reissues, or copies answers.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tarfile
import time

from .hf_qa import canonical
from .run_followup_llm import ARTIFACTS
from .run_followup_queue import CLOSURE_KIND, now, validate_plan, wait_for_idle_gpu
from .run_production_queue import file_hash, save_json, start_model_runtime, stop_owned

KIND = "ktrf_closure_missing_stage_recovery_v1"
ORIGINAL_RUN_ID = "ktrf-closure-20261022T150857Z"
ORIGINAL_CODE_REVISION = "79cb203a83fb10d7bb278558f622d163086bc50f"
REUSED_ARTIFACTS = (*ARTIFACTS, "run_manifest.json", "environment.json", "summary.json")
RETRY_FIELDS = {"plan_path", "plan_sha256", "status_path", "status_sha256"}
SPEC_FIELDS = {"kind", "driver_code_revision", "driver_source", "driver_source_archive",
               "driver_archive_sha256", "original_collector_status", "original_collector_exit",
               "reused_stage_artifacts_sha256", "ipc_dir"}


def _digest(value, size=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % size, value) is not None


def _absolute(value):
    return isinstance(value, str) and Path(value).is_absolute()


def validate_recovery_spec(spec, plan):
    if (not isinstance(spec, dict) or set(spec) != SPEC_FIELDS or spec.get("kind") != KIND
            or not _digest(spec.get("driver_code_revision"), 40)
            or spec["driver_code_revision"] != plan.get("driver_code_revision")
            or not _digest(spec.get("driver_archive_sha256"))
            or any(not _absolute(spec.get(key)) for key in (
                "driver_source", "driver_source_archive", "ipc_dir"))):
        raise ValueError("pinned closure recovery driver and owned IPC required")
    for key in ("original_collector_status", "original_collector_exit"):
        proof = spec.get(key)
        if (not isinstance(proof, dict) or set(proof) != {"path", "sha256"}
                or not _absolute(proof.get("path")) or not _digest(proof.get("sha256"))):
            raise ValueError("pinned original collector publication and exit proofs required")
    hashes = spec.get("reused_stage_artifacts_sha256")
    if (not isinstance(hashes, dict) or set(hashes) != set(REUSED_ARTIFACTS)
            or any(not _digest(value) for value in hashes.values())):
        raise ValueError("every reused private artifact must be pinned")
    if plan.get("launch_environment") != {"TMPDIR": str(Path(plan["run_root"]) / "tmp"),
                                           "VLLM_RPC_BASE_PATH": spec["ipc_dir"]}:
        raise ValueError("recovery launch environment must use its new private temporary and IPC paths")
    return spec


def validate_recovery_origin(plan, original, terminal):
    """Pure, shared fail-closed contract for this single missing-stage recovery."""
    validate_plan(original)
    validate_plan(plan)
    retry = plan.get("retry_from")
    if (plan.get("kind") != CLOSURE_KIND or original.get("kind") != CLOSURE_KIND
            or original.get("run_id") != ORIGINAL_RUN_ID
            or original.get("code_revision") != ORIGINAL_CODE_REVISION
            or plan["run_id"] == original["run_id"]
            or not _digest(plan.get("driver_code_revision"), 40)
            or not isinstance(retry, dict) or set(retry) != RETRY_FIELDS
            or not _absolute(retry.get("plan_path")) or not _absolute(retry.get("status_path"))
            or not _digest(retry.get("plan_sha256")) or not _digest(retry.get("status_sha256"))):
        raise ValueError("explicit original frozen closure recovery pins required")
    operational = {"run_id", "run_root", "status_path", "log_dir", "log_path", "port", "models",
                   "retry_from", "driver_code_revision", "launch_environment", "startup_preflight"}
    if ({key: value for key, value in original.items() if key not in operational}
            != {key: value for key, value in plan.items() if key not in operational}):
        raise ValueError("recovery must retain original requests, source, proofs and protocol")
    for key in ("run_root", "status_path", "log_dir"):
        if not _absolute(plan.get(key)) or plan[key] == original.get(key):
            raise ValueError("new exclusive recovery paths required")
    new_root, old_root = Path(plan["run_root"]).resolve(), Path(original["run_root"]).resolve()
    if new_root.is_relative_to(old_root) or old_root.is_relative_to(new_root):
        raise ValueError("recovery and original run directories must be separate")
    # These are remote paths when called by the local collector; do not resolve
    # the server's /home/one/logs symlinks using the collector host filesystem.
    logs = Path(plan["log_dir"])
    permitted_logs = {Path(plan["run_root"]) / "logs",
                      Path(original["log_dir"]).parent / plan["run_id"]}
    if (logs not in permitted_logs
            or Path(plan["status_path"]) != logs / "queue.status.json"
            or Path(plan.get("log_path", "")) != logs / "queue.log"
            or plan["port"] == original["port"]):
        raise ValueError("new owned status, logs and loopback port required")
    launch = plan.get("launch_environment")
    preflight = plan.get("startup_preflight")
    if (not isinstance(launch, dict) or set(launch) != {"TMPDIR", "VLLM_RPC_BASE_PATH"}
            or launch["TMPDIR"] != str(Path(plan["run_root"]) / "tmp")
            or not _absolute(launch["VLLM_RPC_BASE_PATH"])
            or launch["VLLM_RPC_BASE_PATH"] == original.get("launch_environment", {}).get("VLLM_RPC_BASE_PATH")
            or not isinstance(preflight, dict) or set(preflight) != {"path", "sha256"}
            or preflight.get("path") != str(logs / "ipc.status.json")
            or not _digest(preflight.get("sha256"))):
        raise ValueError("new private launch paths and pinned IPC preflight required")
    for model_key in ("gemma12b", "qwen27b"):
        old, new = original["models"][model_key], plan["models"][model_key]
        if model_key == "qwen27b":
            if new != old:
                raise ValueError("reused Qwen configuration must remain unchanged")
        elif (set(new) != set(old)
                or {k: v for k, v in new.items() if k != "gpu_memory_utilization"}
                   != {k: v for k, v in old.items() if k != "gpu_memory_utilization"}
                or new["gpu_memory_utilization"] <= old["gpu_memory_utilization"]):
            raise ValueError("only an increased Gemma memory budget is permitted")
    expected = {"kind": original["kind"], "run_id": original["run_id"],
                "code_revision": original["code_revision"], "status": "FAILED", "phase": "FINISHED",
                "plan_sha256": hashlib.sha256(canonical(original)).hexdigest()}
    if (not isinstance(terminal, dict) or any(terminal.get(k) != v for k, v in expected.items())
            or type(terminal.get("exit_code")) is not int or terminal["exit_code"] != 1
            or not isinstance(terminal.get("stages"), list) or len(terminal["stages"]) != 2):
        raise ValueError("original failed queue must be terminal at its pinned plan")
    gemma, qwen = original["stages"]
    first, second = terminal["stages"]
    for stage, result in zip((gemma, qwen), (first, second), strict=True):
        if any(result.get(key) != stage[key] for key in ("id", "experiment", "request_count")):
            raise ValueError("original stage identities differ")
    if (first.get("status") != "FAILED" or first.get("benchmark_started") is not False
            or type(first.get("exit_code")) is not int or first["exit_code"] != 1
            or any(first.get(key, 0) != 0 for key in (
                "received_count", "missing_count", "error_count", "malformed_count"))):
        raise ValueError("Gemma recovery is allowed only when its benchmark never started")
    if (second.get("status") != "COMPLETE" or second.get("benchmark_started") is not True
            or any(type(second.get(key)) is not int or second[key] != 0 for key in (
                "exit_code", "benchmark_exit_code", "report_exit_code", "missing_count", "error_count"))
            or second.get("received_count") != qwen["request_count"]):
        raise ValueError("only a complete Qwen stage may be reused")
    reused_from = {"run_id": original["run_id"],
                   "result_path": str(Path(original["run_root"]) / "results" / qwen["id"]), **retry}
    return {"gemma_stage": gemma, "qwen_stage": qwen,
            "qwen_terminal": deepcopy(second), "reused_from": reused_from}


def validate_recovery_publication(plan, original, terminal, collector_status, collector_exit):
    context = validate_recovery_origin(plan, original, terminal)
    if (not isinstance(collector_status, dict) or not isinstance(collector_exit, dict)
            or collector_status.get("run_id") != original["run_id"]
            or collector_status.get("status") != "FAILED" or collector_status.get("phase") != "FINISHED"
            or type(collector_status.get("exit_code")) is not int or collector_status["exit_code"] != 1
            or collector_status.get("publication_complete") is not True
            or collector_status.get("missing_stages") != [context["gemma_stage"]["id"]]
            or collector_status.get("verified_reports") != [context["qwen_stage"]["id"]]
            or collector_status.get("remote") != terminal
            or collector_exit.get("status") != "FAILED"
            or type(collector_exit.get("exit_code")) is not int or collector_exit["exit_code"] != 1
            or type(collector_status.get("pid")) is not int or collector_status["pid"] <= 1
            or collector_exit.get("child_pid") != collector_status["pid"]):
        raise ValueError("original partial failure must be fully collected, published and exited")
    return context


def reused_stage_state(context):
    return {**deepcopy(context["qwen_terminal"]), "reused_from": deepcopy(context["reused_from"]),
            "new_model_calls": 0, "reused_model_calls": context["qwen_stage"]["request_count"]}


def _pinned_json(spec):
    if file_hash(spec["path"]) != spec["sha256"]:
        raise ValueError("recovery provenance file hash mismatch")
    return json.loads(Path(spec["path"]).read_text())


def _verify_driver(spec):
    root = Path(spec["driver_source"]).resolve(strict=True)
    worker = Path(__file__).resolve()
    if (worker != root / "eval/recover_followup_queue.py"
            or file_hash(spec["driver_source_archive"]) != spec["driver_archive_sha256"]):
        raise ValueError("recovery must execute its pinned driver archive")
    found_worker = False
    with tarfile.open(spec["driver_source_archive"], "r:*") as archive:
        for entry in archive.getmembers():
            if not entry.isfile():
                continue
            target = (root / entry.name).resolve()
            archived = archive.extractfile(entry)
            if (not target.is_relative_to(root) or archived is None or not target.is_file()
                    or target.stat().st_size != entry.size
                    or file_hash(target) != hashlib.sha256(archived.read()).hexdigest()):
                raise ValueError("recovery driver dependency differs from pinned archive")
            found_worker |= target == worker
    if not found_worker:
        raise ValueError("recovery driver is absent from pinned archive")


def _frozen_call(plan, *, stage=None, out=None):
    """Import the original helpers from the original frozen source, never this checkout."""
    script = (
        "import json,sys; from eval.run_followup_queue import verify_inputs,verify_predecessor; "
        "from eval.collect_followup_queue import verify_stage; p=json.load(sys.stdin); "
        "result=(verify_inputs(p['plan']),verify_predecessor(p['plan'])) if p['stage'] is None else "
        "verify_stage(p['out'],p['stage'],p['plan']); "
        "sys.stdout.write(json.dumps(result,ensure_ascii=False,sort_keys=True))"
    )
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    env.pop("PYTHONPATH", None)
    result = subprocess.run([plan["python"], "-c", script], cwd=plan["source"], env=env,
                            input=json.dumps({"plan": plan, "stage": stage, "out": str(out) if out else None}),
                            text=True, stdout=subprocess.PIPE, check=True, timeout=600)
    return json.loads(result.stdout)


def _assert_dead(pid):
    if type(pid) is not int or pid <= 1:
        raise ValueError("original queue process identity unavailable")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    except PermissionError:
        pass
    raise ValueError("original queue or owned runtime is still running")


def verify_recovery_inputs(plan, spec):
    validate_recovery_spec(spec, plan)
    retry = plan["retry_from"]
    original = _pinned_json({"path": retry["plan_path"], "sha256": retry["plan_sha256"]})
    terminal = _pinned_json({"path": retry["status_path"], "sha256": retry["status_sha256"]})
    collector_status = _pinned_json(spec["original_collector_status"])
    collector_exit = _pinned_json(spec["original_collector_exit"])
    context = validate_recovery_publication(plan, original, terminal, collector_status, collector_exit)
    _verify_driver(spec)
    _assert_dead(terminal.get("pid"))
    for runtime in terminal.get("runtimes", []):
        if "server_pid" in runtime:
            _assert_dead(runtime["server_pid"])
    old_missing = Path(original["run_root"]) / "results" / context["gemma_stage"]["id"]
    if os.path.lexists(old_missing):
        raise ValueError("original Gemma output exists; partial answers must never be rerun")
    root = Path(plan["run_root"])
    if os.path.lexists(root / "results") or os.path.lexists(plan["status_path"]):
        raise ValueError("exclusive recovery destination already exists")
    ipc = Path(spec["ipc_dir"])
    if (not ipc.is_dir() or ipc.is_symlink() or ipc.stat().st_uid != os.getuid()
            or ipc.stat().st_mode & 0o077 or any(ipc.iterdir())
            or ipc.resolve() in {Path(os.environ.get(key, "/")).resolve()
                                 for key in ("HOME", "TMPDIR")}
            or len(os.fsencode(str(ipc / ("x" * 40)))) >= 107):
        raise ValueError("new empty private owned IPC directory required")
    preflight = _pinned_json(plan["startup_preflight"])
    if (preflight.get("status") != "COMPLETE" or preflight.get("exit_code") != 0
            or preflight.get("code_revision") != plan["code_revision"]
            or preflight.get("actual_vllm_address_bound") is not True
            or preflight.get("ipc_dir") != spec["ipc_dir"]
            or type(preflight.get("endpoint_bytes")) is not int
            or not 0 < preflight["endpoint_bytes"] < 107):
        raise ValueError("successful actual-bind IPC preflight required for the new owned directory")
    _frozen_call(original)
    _frozen_call(plan)
    out = Path(context["reused_from"]["result_path"])
    if out.is_symlink() or not out.is_dir():
        raise ValueError("original Qwen result directory must retain its owned location")
    for name, expected in spec["reused_stage_artifacts_sha256"].items():
        target = out / name
        if target.is_symlink() or not target.is_file() or file_hash(target) != expected:
            raise ValueError("reused Qwen private artifact changed")
    summary, identity, environment = _frozen_call(original, stage=context["qwen_stage"], out=out)
    if (summary.get("status") != "COMPLETE"
            or any(summary["counts"].get(key) != context["qwen_terminal"].get(key)
                   for key in ("received_count", "missing_count", "error_count", "malformed_count"))):
        raise ValueError("reused Qwen terminal counts differ from sealed regrading")
    context.update(original_plan=original, original_status=terminal,
                   reused_identity=identity, reused_environment=environment)
    return context


def run_recovery(plan, spec, *, spec_sha256):
    """Make at most 480 new requests; Qwen never acquires another model runtime."""
    if not _digest(spec_sha256):
        raise ValueError("recovery spec hash required")
    # Every dependency, prior output and destination is checked before a status or GPU is touched.
    context = verify_recovery_inputs(plan, spec)
    root, status_path = Path(plan["run_root"]), Path(plan["status_path"])
    stage = context["gemma_stage"]
    model = plan["models"]["gemma12b"]
    state = {"kind": plan["kind"], "run_id": plan["run_id"], "pid": os.getpid(),
             "code_revision": plan["code_revision"], "driver_code_revision": spec["driver_code_revision"],
             "driver_archive_sha256": spec["driver_archive_sha256"], "recovery_spec_sha256": spec_sha256,
             "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(), "retry_from": plan["retry_from"],
             "status": "RUNNING", "phase": "PRECHECK", "exit_code": None, "started_at": now(),
             "original_total_model_calls": 960, "planned_new_model_calls": 480,
             "new_model_calls": 0, "reused_model_calls": 480,
             "stages": [{"id": stage["id"], "experiment": stage["experiment"], "status": "PENDING",
                         "exit_code": None, "request_count": stage["request_count"], "benchmark_started": False,
                         "new_model_calls": 0}, reused_stage_state(context)]}
    def update(**values):
        state.update(values)
        state["updated_at"] = now()
        save_json(status_path, state)
    server = benchmark = None
    exit_code = 1
    current = state["stages"][0]
    runtime = {"model_key": "gemma12b", "served_model": model["served_name"]}
    state["runtimes"] = [runtime]
    try:
        update(phase="PRIOR_QWEN_VERIFIED")
        wait_for_idle_gpu(plan, update)
        # Recheck immutable provenance and all prior artifacts after a possibly long resource wait.
        for key, expected in (("plan_path", plan["retry_from"]["plan_sha256"]),
                              ("status_path", plan["retry_from"]["status_sha256"])):
            if file_hash(plan["retry_from"][key]) != expected:
                raise ValueError("original provenance changed during GPU wait")
        for name, expected in spec["reused_stage_artifacts_sha256"].items():
            if file_hash(Path(context["reused_from"]["result_path"]) / name) != expected:
                raise ValueError("reused Qwen artifact changed during GPU wait")
        _frozen_call(plan)
        if not (Path(model["path"]) / "config.json").is_file():
            raise ValueError("local Gemma model config unavailable")
        command = [plan["model_python"], "-m", "vllm.entrypoints.openai.api_server",
                   "--model", model["path"], "--served-model-name", model["served_name"],
                   "--host", "127.0.0.1", "--port", str(plan["port"]), "--dtype", "bfloat16",
                   "--max-model-len", "8192", "--max-num-seqs", "1",
                   "--gpu-memory-utilization", str(model["gpu_memory_utilization"]),
                   "--enforce-eager", "--generation-config", "vllm", "--language-model-only",
                   "--no-enable-log-requests"]
        environment = {**os.environ, "CUDA_VISIBLE_DEVICES": "0", "HF_HOME": plan["hf_home"],
                       "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "OMP_NUM_THREADS": "8",
                       "VLLM_CACHE_ROOT": str(root / "runtime_cache"),
                       "TMPDIR": str(root / "tmp"), "VLLM_RPC_BASE_PATH": spec["ipc_dir"]}
        environment.pop("PYTHONPATH", None)
        update(active_model="gemma12b", active_stage=stage["id"], phase="MODEL_PREPARATION")
        # schema_version 4 disables generic startup retries for this bounded recovery.
        server, free, endpoint = start_model_runtime({**plan, "schema_version": 4}, model,
            {"id": "runtime_gemma12b"}, command, environment, runtime, update)
        out = root / "results" / stage["id"]
        if os.path.lexists(out):
            raise ValueError("recovery stage output already exists; refusing answer reruns")
        current.update(status="RUNNING", benchmark_started=True, started_at=now())
        update(phase="MODEL_REQUESTS", responses_completed=0)
        run_command = [plan["python"], "-m", "eval.run_extended_suite", "--requests-file", stage["requests_file"],
                       "--endpoint", endpoint, "--model", model["served_name"], "--out-dir", str(out),
                       "--code-revision", plan["code_revision"]]
        benchmark = subprocess.Popen(run_command, cwd=plan["source"], stdin=subprocess.DEVNULL,
                                     start_new_session=True, env=environment)
        while benchmark.poll() is None:
            responses = out / "responses.jsonl"
            completed = len(responses.read_bytes().splitlines()) if responses.is_file() else 0
            current["new_model_calls"] = completed
            update(responses_completed=completed, new_model_calls=completed)
            time.sleep(15)
        manifest = json.loads((out / "run_manifest.json").read_text())
        expected = {"request_corpus_sha256": stage["requests_sha256"],
                    "frozen_request_file_sha256": stage["envelope_sha256"],
                    "request_count": 480, "code_revision": plan["code_revision"],
                    "requested_model": model["served_name"], "experiment": stage["experiment"]}
        if any(manifest.get(key) != value for key, value in expected.items()):
            raise ValueError("Gemma manifest differs from the original frozen experiment")
        if type(manifest.get("record_count")) is not int or not 0 <= manifest["record_count"] <= 480:
            raise ValueError("Gemma call count exceeds the bounded missing stage")
        save_json(out / "environment.json", {"model_command": command, "benchmark_command": run_command,
            "gpu_free_mib_before_start": free, "checkpoint_revision": model.get("revision", "NOT_VERIFIED"),
            "model_config_sha256": file_hash(Path(model["path"]) / "config.json"),
            "code_revision": plan["code_revision"], "source_archive_sha256": plan["archive_sha256"],
            "queue_plan_sha256": state["plan_sha256"], "driver_code_revision": spec["driver_code_revision"],
            "recovery_spec_sha256": spec_sha256, "recovery_from_run_id": context["original_plan"]["run_id"]})
        report = subprocess.run([plan["python"], "-m", "eval.report_extended_suite", "--run-dir", str(out)],
                                cwd=plan["source"], env=environment)
        result_code = benchmark.returncode or report.returncode
        current.update(status="COMPLETE" if result_code == 0 else "FAILED", exit_code=result_code,
                       benchmark_exit_code=benchmark.returncode, report_exit_code=report.returncode,
                       finished_at=now(), new_model_calls=manifest["record_count"],
                       **{key: manifest[key] for key in ("received_count", "missing_count", "error_count", "malformed_count")})
        update(responses_completed=manifest["received_count"], new_model_calls=manifest["record_count"])
        if result_code == 0:
            _frozen_call(plan, stage=stage, out=out)
        exit_code = int(result_code != 0)
    except (Exception, KeyboardInterrupt) as error:
        state["error_type"] = type(error).__name__
        current.update(status="FAILED", exit_code=1, finished_at=now(), error_type=type(error).__name__)
    finally:
        update(phase="RUNTIME_CLEANUP")
        stop_owned(benchmark)
        stop_owned(server)
        runtime.update(server_exit_code=None if server is None else server.returncode, finished_at=now())
        update(status="COMPLETE" if exit_code == 0 else "FAILED", phase="FINISHED",
               exit_code=exit_code, finished_at=now())
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--recovery-spec", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    return run_recovery(json.loads(args.plan.read_text()), json.loads(args.recovery_spec.read_text()),
                        spec_sha256=file_hash(args.recovery_spec))


if __name__ == "__main__":
    raise SystemExit(main())
