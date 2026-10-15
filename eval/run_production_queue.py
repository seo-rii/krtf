"""Run a frozen production or baseline queue with one owned model runtime at a time."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen


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
    return plan


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


def wait_for_resources(plan, model, update):
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
        wait_for_predecessors(plan, update)
        for index, stage in enumerate(plan["stages"]):
            current = state["stages"][index]
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
                free = wait_for_resources(plan, model, update)
                command = [plan["model_python"], "-m", "vllm.entrypoints.openai.api_server",
                    "--model", str(model_path), "--served-model-name", model["served_name"],
                    "--host", "127.0.0.1", "--port", str(plan["port"]), "--dtype", "bfloat16",
                    "--max-model-len", "8192", "--max-num-seqs", "1",
                    "--gpu-memory-utilization", str(model["gpu_memory_utilization"]),
                    "--enforce-eager", "--generation-config", "vllm", "--language-model-only",
                    "--no-enable-log-requests"]
                server_log = Path(plan["log_dir"]) / (plan["run_id"] + "-" + stage["id"] + "-vllm.log")
                env = {**os.environ, "CUDA_VISIBLE_DEVICES": "0", "HF_HOME": plan["hf_home"],
                       "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                       "VLLM_CACHE_ROOT": str(root / "runtime_cache"), "OMP_NUM_THREADS": "8"}
                with server_log.open("xb") as stream:
                    server = subprocess.Popen(command, cwd=plan["source"], stdout=stream,
                        stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True, env=env)
                current.update(server_pid=server.pid, server_log=str(server_log),
                               checkpoint_revision=model.get("revision", "NOT_VERIFIED"))
                update(phase="MODEL_STARTING")
                endpoint = f"http://127.0.0.1:{plan['port']}/v1"
                deadline = time.monotonic() + 1800
                while True:
                    if server.poll() is not None:
                        raise RuntimeError(f"owned model server exited during startup: {server.returncode}")
                    try:
                        with urlopen(endpoint + "/models", timeout=5) as response:
                            models = json.load(response)
                        if model["served_name"] in {m["id"] for m in models.get("data", [])}:
                            break
                    except (OSError, ValueError):
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError("model startup timeout")
                    time.sleep(5)
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
                current.update(finished_at=now(), server_exit_code=None if server is None else server.returncode)
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
