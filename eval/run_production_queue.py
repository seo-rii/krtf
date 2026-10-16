"""Run a frozen production or baseline queue with one owned model runtime at a time."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tarfile
import time
from urllib.request import urlopen


RETRY_FROZEN_FIELDS = (
    "schema_version", "code_revision", "source", "source_archive", "archive_sha256",
    "unit_status", "token_status", "python", "model_python", "hf_home", "models", "stages",
)
_STARTUP_MEMORY_ERROR = re.compile(
    r"ValueError: Free memory on device cuda:0 \([0-9.]+/[0-9.]+ GiB\) on startup "
    r"is less than desired GPU memory utilization \([0-9.]+, [0-9.]+ GiB\)\. "
    r"Decrease GPU memory utilization or reduce GPU memory used by other processes\."
)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode()


def file_hash(path):
    result = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def save_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical(value))
    temporary.chmod(0o600)
    temporary.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def report_module_for_plan(plan):
    """Select a fixed report implementation; baseline never uses the production grader."""
    if plan.get("schema_version") == 1:
        return "eval.report_production_grounding"
    if plan.get("schema_version") == 2:
        return "eval.report_production_baseline"
    if plan.get("schema_version") == 3:
        return "eval.report_document_context"
    if plan.get("schema_version") == 4:
        return "eval.report_definition_control"
    if plan.get("schema_version") == 5:
        return "eval.report_hf_qa"
    raise ValueError("unknown queue schema version")


def validate_plan(plan):
    version = plan.get("schema_version")
    prefix = "baseline" if version == 2 else "production"
    expected = [(prefix + "_synthetic", "gemma12b"),
                (prefix + "_synthetic", "qwen27b"),
                (prefix + "_real", "gemma12b"),
                (prefix + "_real", "qwen27b")]
    if version in (3, 4, 5):
        track = {3: "document_context", 4: "definition_control", 5: "hf_qa"}[version]
        expected = [(track, "gemma12b"), (track, "qwen27b")]
    if version not in (1, 2, 3, 4, 5) or [
            (s["track"], s["model_key"]) for s in plan["stages"]] != expected:
        raise ValueError("expected the four predeclared synthetic/real or two matched document/HF QA model stages")
    if len({s["id"] for s in plan["stages"]}) != len(expected):
        raise ValueError("stage IDs must be unique")
    for stage in plan["stages"]:
        if not stage["id"].replace("_", "").isalnum() or stage["request_count"] < 1:
            raise ValueError("invalid stage identity or request count")
        if len(stage["requests_sha256"]) != 64 or len(stage["envelope_sha256"]) != 64:
            raise ValueError("frozen request and envelope hashes required")
        if version == 2 and stage["request_count"] != (874 if stage["track"] == "baseline_synthetic" else 120):
            raise ValueError("baseline queue requires 874 synthetic and 120 real requests per model")
    tracks = (track,) if version in (3, 4, 5) else (prefix + "_synthetic", prefix + "_real")
    if version in (3, 4, 5) and not plan.get("token_status"):
        raise ValueError("document/HF QA queue requires actual tokenizer preflight")
    for track in tracks:
        stages = [s for s in plan["stages"] if s["track"] == track]
        for field in ("requests_sha256", "envelope_sha256", "request_count"):
            if stages[0][field] != stages[1][field]:
                raise ValueError("both models must receive identical frozen requests")
    if not 1024 <= plan["port"] <= 65535:
        raise ValueError("invalid loopback port")
    for model in plan["models"].values():
        if not 0 < model["gpu_memory_utilization"] < 1:
            raise ValueError("invalid GPU fraction")
        if model.get("repo_id") and len(model.get("revision", "")) != 40:
            raise ValueError("downloaded checkpoint needs an immutable revision")
    if "retry_from" in plan or "orchestrator" in plan:
        if version != 5 or not all(key in plan for key in ("retry_from", "orchestrator")):
            raise ValueError("explicit retry provenance is supported only for HF QA")
        retry = plan["retry_from"]
        if (not isinstance(retry, dict) or set(retry) != {
                "plan_path", "plan_sha256", "status_path", "status_sha256"} or
                any(not isinstance(retry[key], str) or not retry[key]
                    for key in retry) or
                any(not re.fullmatch(r"[0-9a-f]{64}", retry[key])
                    for key in ("plan_sha256", "status_sha256"))):
            raise ValueError("retry requires pinned original plan and terminal status")
        orchestration = plan["orchestrator"]
        if (not isinstance(orchestration, dict) or set(orchestration) != {
                "code_revision", "source", "source_archive", "archive_sha256", "unit_status"} or
                any(not isinstance(value, str) or not value for value in orchestration.values()) or
                not re.fullmatch(r"[0-9a-f]{40}", orchestration["code_revision"]) or
                not re.fullmatch(r"[0-9a-f]{64}", orchestration["archive_sha256"])):
            raise ValueError("retry requires frozen orchestration source and test proof")
    return plan


def validate_retry_origin(plan, original, terminal):
    """Check the only supported retry: no Gemma requests and a completed Qwen run."""
    if any(plan.get(key) != original.get(key) for key in RETRY_FROZEN_FIELDS):
        raise ValueError("retry must preserve every frozen inference input")
    validate_plan(plan)
    validate_plan(original)
    if "retry_from" in original or "orchestrator" in original:
        raise ValueError("retry chains are unsupported")
    retry = plan["retry_from"]
    if (retry["status_path"] != original["status_path"] or
            plan["run_id"] == original["run_id"] or
            Path(plan["run_root"]).resolve() == Path(original["run_root"]).resolve() or
            plan["status_path"] == original["status_path"]):
        raise ValueError("retry must use a new run identity and output root")
    expected = {"run_id": original["run_id"], "code_revision": original["code_revision"],
                "plan_sha256": hashlib.sha256(canonical(original)).hexdigest(),
                "phase": "FINISHED", "status": "FAILED", "exit_code": 1}
    if (any(terminal.get(key) != value for key, value in expected.items()) or
            type(terminal.get("exit_code")) is not int or "error" in terminal):
        raise ValueError("retry origin must be the pinned terminal failed queue")
    results = terminal.get("stages", [])
    if ([row.get("id") for row in results] != [stage["id"] for stage in original["stages"]] or
            any(row.get("request_count") != stage["request_count"]
                for row, stage in zip(results, original["stages"]))):
        raise ValueError("retry origin stage identities differ")
    failed, completed = results
    if (failed.get("status") != "FAILED" or type(failed.get("exit_code")) is not int or
            failed["exit_code"] == 0 or type(failed.get("server_pid")) is not int or
            failed["server_pid"] < 1 or type(failed.get("server_exit_code")) is not int or
            failed["server_exit_code"] == 0 or failed.get("model") != original["models"]["gemma12b"]["served_name"] or
            failed.get("error") != {"type": "RuntimeError", "message":
                f"owned model server exited during startup: {failed.get('server_exit_code')}"} or
            any(key in failed for key in ("benchmark_exit_code", "received_count", "missing_count",
                                          "error_count", "malformed_count"))):
        raise ValueError("only a Gemma failure before benchmark startup can be retried")
    if (completed.get("status") != "COMPLETE" or type(completed.get("exit_code")) is not int or
            completed["exit_code"] != 0 or completed.get("benchmark_exit_code") != 0 or
            completed.get("received_count") != original["stages"][1]["request_count"] or
            completed.get("missing_count") != 0 or completed.get("error_count") != 0 or
            completed.get("model") != original["models"]["qwen27b"]["served_name"]):
        raise ValueError("retry requires the original completed Qwen stage")
    return failed, completed


def prepare_retry(plan):
    """Verify provenance and sealed reusable artifacts before acquiring any GPU."""
    retry = plan["retry_from"]
    if any(file_hash(retry[key + "_path"]) != retry[key + "_sha256"]
           for key in ("plan", "status")):
        raise ValueError("pinned retry origin files changed")
    original = json.loads(Path(retry["plan_path"]).read_text())
    terminal = json.loads(Path(retry["status_path"]).read_text())
    failed, completed = validate_retry_origin(plan, original, terminal)
    failed_out = Path(original["run_root"]) / "results" / original["stages"][0]["id"]
    if failed_out.exists() or failed_out.is_symlink():
        raise ValueError("original Gemma output exists; refusing a benchmark retry")
    if not is_startup_memory_failure(failed["server_log"]):
        raise ValueError("original startup failure is not the known GPU memory race")
    orchestration = plan["orchestrator"]
    if file_hash(orchestration["source_archive"]) != orchestration["archive_sha256"]:
        raise ValueError("orchestration archive hash mismatch")
    proof = json.loads(Path(orchestration["unit_status"]).read_text())
    if proof.get("exit_code") != 0 or proof.get("code_revision") != orchestration["code_revision"]:
        raise ValueError("successful tests at frozen orchestration revision are required")
    module = Path(__file__).resolve()
    if module != (Path(orchestration["source"]) / "eval/run_production_queue.py").resolve():
        raise ValueError("worker is not running from frozen orchestration source")
    with tarfile.open(orchestration["source_archive"], "r:*") as archive:
        member = archive.extractfile("eval/run_production_queue.py")
        if member is None or member.read() != module.read_bytes():
            raise ValueError("running worker differs from orchestration archive")
    stage = original["stages"][1]
    out = Path(original["run_root"]) / "results" / stage["id"]
    manifest = json.loads((out / "run_manifest.json").read_text())
    unsealed = dict(manifest)
    seal = unsealed.pop("seal_sha256", None)
    hashes = {name: file_hash(out / name) for name in ("requests.jsonl", "responses.jsonl", "graded.json")}
    expected = {"code_revision": original["code_revision"], "track": "hf_qa",
                "protocol": "hf_qa_generation_v1", "requested_model": completed["model"],
                "request_count": stage["request_count"], "received_count": stage["request_count"],
                "missing_count": 0, "error_count": 0,
                "request_corpus_sha256": stage["requests_sha256"],
                "frozen_request_file_sha256": stage["envelope_sha256"], "status": "COMPLETE"}
    if (seal != hashlib.sha256(canonical(unsealed)).hexdigest() or
            manifest.get("artifact_sha256") != hashes or hashes["requests.jsonl"] != stage["requests_sha256"] or
            any(manifest.get(key) != value for key, value in expected.items()) or
            any(completed.get(key) != manifest.get(key) for key in
                ("request_count", "received_count", "missing_count", "error_count", "malformed_count"))):
        raise ValueError("original Qwen artifacts or manifest differ from pinned completed run")
    environment = json.loads((out / "environment.json").read_text())
    if any(environment.get(key) != value for key, value in {
            "code_revision": original["code_revision"], "source_archive_sha256": original["archive_sha256"],
            "queue_plan_sha256": hashlib.sha256(canonical(original)).hexdigest()}.items()):
        raise ValueError("original Qwen environment differs from pinned queue")
    return {**completed, "reused_from": {**retry, "run_id": original["run_id"],
            "result_path": str(out), "code_revision": original["code_revision"]}}


def wait_for_predecessors(plan, update):
    """Wait for whole earlier queues, avoiding races during their model changes."""
    deadline = time.monotonic() + plan.get("predecessor_wait_seconds", 6 * 86400)
    for predecessor in plan.get("predecessors", []):
        while True:
            status = json.loads(Path(predecessor["status_path"]).read_text())
            if (status.get("run_id") != predecessor["run_id"] or
                    status.get("code_revision") != predecessor["code_revision"]):
                raise ValueError("predecessor identity changed")
            if status.get("exit_code") is not None:
                if status.get("phase") != "FINISHED" or status.get("status") not in {"COMPLETE", "FAILED"}:
                    raise ValueError("predecessor status is not terminal")
                break
            if time.monotonic() > deadline:
                raise RuntimeError("predecessor queue did not finish within the wait deadline")
            update(phase="WAITING_FOR_PREDECESSOR", predecessor_run_id=predecessor["run_id"])
            time.sleep(60)


def validate_requests(stage):
    if file_hash(stage["requests_file"]) != stage["envelope_sha256"]:
        raise ValueError("frozen request envelope changed")
    envelope = json.loads(Path(stage["requests_file"]).read_text())
    rows = envelope["requests"]
    actual = hashlib.sha256(b"".join(canonical(r) for r in rows)).hexdigest()
    if len(rows) != stage["request_count"] or actual != stage["requests_sha256"]:
        raise ValueError("frozen requests differ from declared count/hash")
    return envelope


def stop_owned(process):
    """Only terminate the process group created by this worker."""
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=45)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=15)


def wait_for_resources(plan, model, update, *, deadline=None):
    if deadline is None:
        deadline = time.monotonic() + plan.get("resource_wait_seconds", 86400)
    while True:
        output = subprocess.check_output([
            "nvidia-smi", "--id=0", "--query-gpu=memory.total,memory.free",
            "--format=csv,noheader,nounits"], text=True, timeout=20)
        total, free = (int(v.strip()) for v in output.strip().split(","))
        required = int(total * model["gpu_memory_utilization"]) + 2048
        available = True
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", plan["port"]))
        except OSError:
            available = False
        update(phase="RESOURCE_CHECK" if free >= required and available else "WAITING_FOR_RESOURCE",
               free_mib=free, required_free_mib=required, port_available=available,
               last_resource_check=now())
        if free >= required and available:
            return free
        if time.monotonic() >= deadline:
            raise RuntimeError("GPU or port remained unavailable; no other process was modified")
        time.sleep(60)


def is_startup_memory_failure(path):
    """Recognize only vLLM's explicit free-memory startup race, from a bounded tail."""
    with Path(path).open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - 256 * 1024))
        return bool(_STARTUP_MEMORY_ERROR.search(stream.read().decode("utf-8", errors="replace")))


def start_model_runtime(plan, model, stage, command, env, current, update):
    """Retry at most three owned startups, never an already-started benchmark."""
    resource_deadline = time.monotonic() + plan.get("resource_wait_seconds", 86400)
    max_attempts = 3 if plan.get("schema_version") == 5 else 1
    endpoint = f"http://127.0.0.1:{plan['port']}/v1"
    attempts = current.setdefault("startup_attempts", [])
    for attempt in range(1, max_attempts + 1):
        free = wait_for_resources(plan, model, update, deadline=resource_deadline)
        suffix = "" if attempt == 1 else "-attempt" + str(attempt)
        server_log = Path(plan["log_dir"]) / (
            plan["run_id"] + "-" + stage["id"] + suffix + "-vllm.log")
        server = None
        observation = {"attempt": attempt, "server_log": str(server_log), "started_at": now()}
        attempts.append(observation)
        try:
            with server_log.open("xb") as stream:
                server = subprocess.Popen(command, cwd=plan["source"], stdout=stream,
                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True, env=env)
            current.update(server_pid=server.pid, server_log=str(server_log),
                           checkpoint_revision=model.get("revision", "NOT_VERIFIED"))
            observation["server_pid"] = server.pid
            update(phase="MODEL_STARTING", startup_attempt=attempt)
            startup_deadline = min(resource_deadline, time.monotonic() + 1800)
            while True:
                if server.poll() is not None:
                    raise RuntimeError(f"owned model server exited during startup: {server.returncode}")
                try:
                    with urlopen(endpoint + "/models", timeout=5) as response:
                        models = json.load(response)
                    if model["served_name"] in {m["id"] for m in models.get("data", [])}:
                        observation.update(status="READY", ready_at=now())
                        return server, free, endpoint
                except (OSError, ValueError):
                    pass
                if time.monotonic() > startup_deadline:
                    raise RuntimeError("model startup timeout")
                time.sleep(5)
        except BaseException as error:
            exited = server is not None and server.poll() is not None
            retryable = (exited and isinstance(error, RuntimeError) and
                         is_startup_memory_failure(server_log))
            stop_owned(server)
            current["server_exit_code"] = None if server is None else server.returncode
            observation.update(status="FAILED", finished_at=now(),
                               server_exit_code=None if server is None else server.returncode,
                               retryable_memory_race=retryable)
            if not retryable or attempt == max_attempts or time.monotonic() >= resource_deadline:
                raise
            update(phase="RETRYING_STARTUP_MEMORY_RACE", startup_attempt=attempt)
    raise AssertionError("startup attempts exhausted without a terminal outcome")


def run_queue(plan):
    validate_plan(plan)
    root = Path(plan["run_root"])
    status_path = Path(plan["status_path"])
    if status_path.exists():
        raise ValueError("exclusive queue status already exists; refusing a duplicate launch")
    state = {"run_id": plan["run_id"], "pid": os.getpid(), "status": "RUNNING",
             "phase": "PRECHECK", "exit_code": None, "started_at": now(),
             "code_revision": plan["code_revision"], "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(),
             "stages": [{"id": s["id"], "status": "PENDING", "exit_code": None,
                         "request_count": s["request_count"]} for s in plan["stages"]]}
    def update(**values):
        state.update(values)
        state["updated_at"] = now()
        save_json(status_path, state)
    exit_code = 1
    try:
        update()
        if file_hash(plan["source_archive"]) != plan["archive_sha256"]:
            raise ValueError("source archive hash mismatch")
        proof = json.loads(Path(plan["unit_status"]).read_text())
        if proof.get("exit_code") != 0 or proof.get("code_revision") != plan["code_revision"]:
            raise ValueError("successful tests at the frozen revision are required")
        for stage in plan["stages"]:
            validate_requests(stage)
        if plan.get("schema_version") in (3, 4, 5):
            token_proof = json.loads(Path(plan["token_status"]).read_text())
            if token_proof.get("exit_code") != 0 or token_proof.get("code_revision") != plan["code_revision"]:
                raise ValueError("successful tokenizer preflight at the frozen revision is required")
            for stage in plan["stages"]:
                observed = token_proof.get("models", {}).get(stage["model_key"], {})
                if (observed.get("requests_sha256") != stage["requests_sha256"] or
                        observed.get("request_count") != stage["request_count"] or
                        observed.get("model_path") != plan["models"][stage["model_key"]]["path"] or
                        type(observed.get("max_prompt_tokens")) is not int or
                        not 0 < observed["max_prompt_tokens"] <= 8192 - 128):
                    raise ValueError("tokenizer preflight differs from frozen requests or context capacity")
        reused = prepare_retry(plan) if "retry_from" in plan else None
        if reused is not None:
            state["orchestrator_revision"] = plan["orchestrator"]["code_revision"]
            state["retry_from"] = plan["retry_from"]
        wait_for_predecessors(plan, update)
        for index, stage in enumerate(plan["stages"]):
            current = state["stages"][index]
            if reused is not None and index == 1:
                current.update(reused)
                update(active_stage=stage["id"], phase="REUSING_VERIFIED_STAGE",
                       responses_completed=current["received_count"])
                continue
            model = plan["models"][stage["model_key"]]
            out = root / "results" / stage["id"]
            server = benchmark = None
            current.update(status="RUNNING", started_at=now(), model=model["served_name"])
            update(active_stage=stage["id"], phase="MODEL_PREPARATION", responses_completed=0)
            try:
                if out.exists():
                    raise ValueError("stage output already exists; refusing to overwrite")
                model_path = Path(model["path"])
                if model.get("repo_id"):
                    download = [plan["model_python"], "-c",
                        "from huggingface_hub import snapshot_download; "
                        "snapshot_download(repo_id=" + repr(model["repo_id"]) +
                        ", revision=" + repr(model["revision"]) +
                        ", local_dir=" + repr(str(model_path)) +
                        ", max_workers=4, allow_patterns=['*.json','*.safetensors','*.model','*.txt','*.tiktoken','*.jinja'])"]
                    update(phase="DOWNLOADING_PINNED_MODEL", checkpoint_revision=model["revision"])
                    subprocess.run(download, check=True, timeout=4 * 3600,
                                   env={**os.environ, "HF_HOME": plan["hf_home"], "HF_HUB_DISABLE_PROGRESS_BARS": "1"})
                if not (model_path / "config.json").is_file():
                    raise ValueError("model config is unavailable")
                command = [plan["model_python"], "-m", "vllm.entrypoints.openai.api_server",
                    "--model", str(model_path), "--served-model-name", model["served_name"],
                    "--host", "127.0.0.1", "--port", str(plan["port"]), "--dtype", "bfloat16",
                    "--max-model-len", "8192", "--max-num-seqs", "1",
                    "--gpu-memory-utilization", str(model["gpu_memory_utilization"]),
                    "--enforce-eager", "--generation-config", "vllm", "--language-model-only",
                    "--no-enable-log-requests"]
                env = {**os.environ, "CUDA_VISIBLE_DEVICES": "0", "HF_HOME": plan["hf_home"],
                       "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                       "VLLM_CACHE_ROOT": str(root / "runtime_cache"), "OMP_NUM_THREADS": "8"}
                server, free, endpoint = start_model_runtime(
                    plan, model, stage, command, env, current, update)
                update(phase="MODEL_REQUESTS")
                run_command = [plan["python"], "-m", "eval.run_product_llm", "--track", stage["track"],
                    "--requests-file", stage["requests_file"], "--endpoint", endpoint,
                    "--model", model["served_name"], "--out-dir", str(out),
                    "--code-revision", plan["code_revision"], "--max-tokens", "128", "--timeout", "180"]
                benchmark = subprocess.Popen(run_command, cwd=plan["source"], start_new_session=True)
                while benchmark.poll() is None:
                    responses = out / "responses.jsonl"
                    completed = 0
                    if responses.exists():
                        with responses.open("rb") as stream:
                            completed = sum(1 for line in stream if line.endswith(b"\n"))
                    update(responses_completed=completed)
                    time.sleep(15)
                current["benchmark_exit_code"] = benchmark.returncode
                environment = {"model_command": command, "benchmark_command": run_command,
                    "checkpoint_repo": model.get("repo_id"),
                    "checkpoint_revision": model.get("revision", "NOT_VERIFIED"),
                    "config_sha256": {name: file_hash(model_path / name) for name in
                        ("config.json", "tokenizer_config.json", "generation_config.json", "model.safetensors.index.json")
                        if (model_path / name).is_file()},
                    "gpu_free_mib_before_start": free, "queue_plan_sha256": state["plan_sha256"],
                    "code_revision": plan["code_revision"], "source_archive_sha256": plan["archive_sha256"]}
                save_json(out / "environment.json", environment)
                manifest = json.loads((out / "run_manifest.json").read_text())
                for field, expected in (("request_corpus_sha256", stage["requests_sha256"]),
                                        ("request_count", stage["request_count"]),
                                        ("code_revision", plan["code_revision"]),
                                        ("track", stage["track"]), ("requested_model", model["served_name"])):
                    if manifest.get(field) != expected:
                        raise ValueError("run manifest differs from plan: " + field)
                update(phase="REPORTING", responses_completed=manifest["received_count"])
                report = subprocess.run([plan["python"], "-m", report_module_for_plan(plan),
                    "--run-dir", str(out)], cwd=plan["source"])
                current.update(exit_code=benchmark.returncode or report.returncode,
                    received_count=manifest["received_count"], malformed_count=manifest["malformed_count"],
                    missing_count=manifest["missing_count"], error_count=manifest["error_count"],
                    status="COMPLETE" if benchmark.returncode == report.returncode == 0 else "FAILED")
            except Exception as error:
                current.update(status="FAILED", exit_code=1,
                               error={"type": type(error).__name__, "message": str(error)})
                print(json.dumps({"stage": stage["id"], "error": current["error"]}), flush=True)
            finally:
                update(phase="RUNTIME_CLEANUP")
                try:
                    stop_owned(benchmark)
                finally:
                    stop_owned(server)
                if current["status"] == "RUNNING":
                    current.update(status="FAILED", exit_code=130, error={"type": "Interrupted", "message": "queue interrupted"})
                current.update(finished_at=now(), server_exit_code=(current.get("server_exit_code")
                               if server is None else server.returncode))
                update()
        exit_code = int(any(s["exit_code"] != 0 for s in state["stages"]))
    except (Exception, KeyboardInterrupt) as error:
        state["error"] = {"type": type(error).__name__, "message": str(error)}
        print(json.dumps(state["error"]), flush=True)
    finally:
        update(status="COMPLETE" if exit_code == 0 else "FAILED", phase="FINISHED",
               exit_code=exit_code, finished_at=now())
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    def interrupted(signum, frame):
        raise KeyboardInterrupt("queue received termination signal")
    signal.signal(signal.SIGTERM, interrupted)
    return run_queue(json.loads(args.plan.read_text()))


if __name__ == "__main__":
    raise SystemExit(main())
