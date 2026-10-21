"""Run frozen CPU proofs and two serial A100 followup model groups."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
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
from .run_followup_llm import load_request_file
from .run_production_queue import file_hash, save_json, start_model_runtime, stop_owned

KIND = "ktrf_followup_queue_v1"
COMBINED_KIND = "ktrf_combined_queue_v1"
EXTENDED_KIND = "ktrf_extended_queue_v1"
DIAGNOSTIC_KIND = "ktrf_diagnostic_queue_v1"
EVIDENCE_KIND = "ktrf_evidence_control_v1"
EVIDENCE_COUNTS = {"evidence_control": 256}
EVIDENCE_ORDER = [("evidence_control", model) for model in ("gemma12b", "qwen27b")]
CONFIRMATION_KIND = "ktrf_routing_confirmation_v1"
CONFIRMATION_COUNTS = {"routing_confirmation": 1152}
CONFIRMATION_ORDER = [("routing_confirmation", model) for model in ("gemma12b", "qwen27b")]
REVIEW_KIND = "ktrf_review_queue_v1"
REVIEW_COUNTS = {"review_abcd": 1024, "review_policy": 384, "review_budget": 384,
                 "review_nomiracl": 384, "review_routing": 768}
REVIEW_ORDER = [(experiment, model) for model in ("gemma12b", "qwen27b")
                for experiment in REVIEW_COUNTS]
DIAGNOSTIC_COUNTS = {"source_pack_factorial": 768, "fresh_compact": 384, "safety_robustness": 640}
DIAGNOSTIC_ORDER = [(experiment, model) for model in ("gemma12b", "qwen27b")
                    for experiment in DIAGNOSTIC_COUNTS]
EXTENDED_COUNTS = {"transfer": 1024, "budget": 512, "corpus": 512,
                   "pack": 640, "semantic_safety": 96}
EXTENDED_ORDER = [(experiment, model) for model in ("gemma12b", "qwen27b")
                  for experiment in EXTENDED_COUNTS]
ORDER = [(experiment, model) for model in ("gemma12b", "qwen27b")
         for experiment in ("retrieval", "stability")]
COMBINED_ORDER = [("combined", model) for model in ("gemma12b", "qwen27b")]


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_plan(plan):
    if not isinstance(plan, dict) or plan.get("kind") not in {KIND, COMBINED_KIND, EXTENDED_KIND, DIAGNOSTIC_KIND, REVIEW_KIND, CONFIRMATION_KIND, EVIDENCE_KIND}:
        raise ValueError("frozen followup queue required")
    combined = plan["kind"] == COMBINED_KIND
    extended = plan["kind"] in {EXTENDED_KIND, DIAGNOSTIC_KIND, REVIEW_KIND, CONFIRMATION_KIND, EVIDENCE_KIND}
    diagnostic = plan["kind"] == DIAGNOSTIC_KIND
    review = plan["kind"] == REVIEW_KIND
    confirmation = plan["kind"] == CONFIRMATION_KIND
    evidence = plan["kind"] == EVIDENCE_KIND
    sample_design = plan.get("sample_design")
    if "sample_design" in plan:
        if (not combined or not isinstance(sample_design, dict)
                or sample_design.get("kind") != "fresh_document_holdout"):
            raise ValueError("fresh document sample design is supported only for combined queues")
        question_count = sample_design.get("question_count")
        strata = sample_design.get("strata")
        if (type(question_count) is not int or not 0 < question_count <= 128
                or not isinstance(strata, dict) or set(strata) != {"SPAN", "YES_NO", "NO_ANSWER"}
                or any(type(count) is not int or count < 0 for count in strata.values())
                or sum(strata.values()) != question_count
                or strata["SPAN"] + strata["YES_NO"] == 0 or strata["NO_ANSWER"] == 0
                or type(sample_design.get("repeat_count")) is not int
                or sample_design["repeat_count"] != 3
                or sample_design.get("independent_from_prior_declared_articles") is not True):
            raise ValueError("fresh document sample requires bounded questions, positive/negative strata and three repeats")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", plan.get("run_id", "")):
        raise ValueError("invalid run identity")
    if not re.fullmatch(r"[0-9a-f]{40}", plan.get("code_revision", "")):
        raise ValueError("immutable code revision required")
    if not re.fullmatch(r"[0-9a-f]{64}", plan.get("archive_sha256", "")):
        raise ValueError("source archive hash required")
    stages = plan.get("stages", [])
    order = EVIDENCE_ORDER if evidence else CONFIRMATION_ORDER if confirmation else REVIEW_ORDER if review else DIAGNOSTIC_ORDER if diagnostic else EXTENDED_ORDER if extended else COMBINED_ORDER if combined else ORDER
    if [(s.get("experiment"), s.get("model_key")) for s in stages] != order:
        raise ValueError("expected evidence control for Gemma then Qwen" if evidence else
                         "expected fresh routing confirmation for Gemma then Qwen" if confirmation else
                         "expected matched five review experiments for Gemma then Qwen" if review else
                         "expected matched three diagnostics for Gemma then Qwen" if diagnostic else
                         "expected matched five experiments for Gemma then Qwen" if extended else
                         "expected matched combined stages for Gemma then Qwen" if combined else
                         "expected matched retrieval/stability for Gemma then Qwen")
    if len({s.get("id") for s in stages}) != len(order):
        raise ValueError("unique stage IDs required")
    for stage in stages:
        request_count = (EVIDENCE_COUNTS[stage["experiment"]] if evidence else
                         CONFIRMATION_COUNTS[stage["experiment"]] if confirmation else
                         REVIEW_COUNTS[stage["experiment"]] if review else
                         DIAGNOSTIC_COUNTS[stage["experiment"]] if diagnostic else
                         EXTENDED_COUNTS[stage["experiment"]] if extended else
                         sample_design["question_count"] * 12 if sample_design else
                         512 if stage["experiment"] == "retrieval" else 1536)
        if (not re.fullmatch(r"[a-zA-Z0-9_]+", stage.get("id", ""))
                or stage.get("request_count") != request_count):
            raise ValueError("invalid stage identity or predeclared fresh-document matrix" if sample_design else
                             "invalid stage identity or predeclared 128-question matrix")
        for key in ("requests_sha256", "envelope_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", stage.get(key, "")):
                raise ValueError("frozen stage hashes required")
    for experiment in dict.fromkeys(experiment for experiment, _ in order):
        pair = [s for s in stages if s["experiment"] == experiment]
        for key in ("requests_file", "request_count", "requests_sha256", "envelope_sha256"):
            if pair[0][key] != pair[1][key]:
                raise ValueError("both models require identical frozen requests")
    if type(plan.get("port")) is not int or not 1024 <= plan["port"] <= 65535:
        raise ValueError("invalid loopback port")
    if set(plan.get("models", {})) != {"gemma12b", "qwen27b"}:
        raise ValueError("two declared checkpoints required")
    for model in plan["models"].values():
        if not 0 < model["gpu_memory_utilization"] < 1:
            raise ValueError("invalid GPU fraction")
        if not model.get("path") or not model.get("served_name"):
            raise ValueError("local checkpoint and served identity required")
    if not 0 < plan.get("resource_wait_seconds", 0) <= 2 * 86400:
        raise ValueError("bounded resource deadline required")
    if (confirmation or evidence) and plan.get("require_idle_gpu") is not True:
        raise ValueError("confirmation cost measurements require an initially idle GPU")
    expected_proofs = {"unit", "preparation"} if combined or extended else {"unit", "preparation", "blind_document"}
    if set(plan.get("proofs", {})) != expected_proofs:
        raise ValueError("unit and tokenizer preparation proofs required" if combined or extended else
                         "unit, tokenizer preparation and blind-document proofs required")
    for proof in plan["proofs"].values():
        if not proof.get("path") or not re.fullmatch(r"[0-9a-f]{64}", proof.get("sha256", "")):
            raise ValueError("pinned proof file hashes required")
    return plan


def verify_inputs(plan):
    validate_plan(plan)
    if file_hash(plan["source_archive"]) != plan["archive_sha256"]:
        raise ValueError("source archive hash mismatch")
    worker = Path(__file__).resolve()
    if worker != (Path(plan["source"]) / "eval/run_followup_queue.py").resolve():
        raise ValueError("worker must run from the frozen source")
    with tarfile.open(plan["source_archive"], "r:*") as archive:
        member = archive.extractfile("eval/run_followup_queue.py")
        if member is None or member.read() != worker.read_bytes():
            raise ValueError("running worker differs from frozen archive")
        source = Path(plan["source"]).resolve()
        for entry in archive.getmembers():
            if not entry.isfile():
                continue
            target = (source / entry.name).resolve()
            archived = archive.extractfile(entry)
            if (not target.is_relative_to(source) or archived is None or not target.is_file()
                    or target.stat().st_size != entry.size
                    or file_hash(target) != hashlib.sha256(archived.read()).hexdigest()):
                raise ValueError("frozen source file differs from archive")
    proofs = {}
    for name, spec in plan["proofs"].items():
        if file_hash(spec["path"]) != spec["sha256"]:
            raise ValueError("proof file hash mismatch")
        proofs[name] = json.loads(Path(spec["path"]).read_text())
    if (proofs["unit"].get("exit_code") != 0
            or proofs["unit"].get("code_revision") != plan["code_revision"]):
        raise ValueError("successful tests at frozen revision required")
    if plan["kind"] == KIND and proofs["blind_document"].get("exit_code") != 0:
        raise ValueError("completed sealed blind-document CPU evaluation required")
    prepared = proofs["preparation"]
    if prepared.get("code_revision") != plan["code_revision"]:
        raise ValueError("preparation must use frozen code revision")
    sample_design = plan.get("sample_design")
    if sample_design is not None and prepared.get("sample_design") != sample_design:
        raise ValueError("preparation sample design differs from frozen plan")
    for stage in plan["stages"]:
        path = Path(stage["requests_file"])
        if file_hash(path) != stage["envelope_sha256"]:
            raise ValueError("frozen request envelope changed")
        loader = load_request_file
        if plan["kind"] in {EXTENDED_KIND, DIAGNOSTIC_KIND, REVIEW_KIND, CONFIRMATION_KIND, EVIDENCE_KIND}:
            from .run_extended_suite import load_request_file as loader
        rows, protocol, _ = loader(path)
        if (protocol["experiment"] != stage["experiment"] or len(rows) != stage["request_count"]
                or hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest() != stage["requests_sha256"]):
            raise ValueError("request matrix differs from frozen plan")
        # The manifest shape is intentionally explicit and independent of inference outputs.
        preparation = prepared["experiments"][stage["experiment"]]
        if any(preparation.get(key) != stage[key] for key in (
                "request_count", "requests_sha256", "envelope_sha256")):
            raise ValueError("tokenizer preparation must bind the exact frozen corpus")
        if sample_design is not None:
            if protocol.get("sample_design") != sample_design:
                raise ValueError("request protocol sample design differs from frozen plan")
            base = {row["case_id"]: row for row in rows}
            question_count = sample_design["question_count"]
            strata = Counter(row["stratum"] for row in base.values())
            actual_strata = {kind: strata[kind] for kind in ("SPAN", "YES_NO", "NO_ANSWER")}
            if (len(base) != question_count or actual_strata != sample_design["strata"]
                    or preparation.get("question_count") != question_count
                    or preparation.get("strata") != actual_strata):
                raise ValueError("fresh document question count or strata differ from frozen sample")
            parent_ids = {row["parent_document_id"] for row in base.values()}
            document_hashes = {row["document_sha256"] for row in base.values()}
            if (len(parent_ids) != question_count or len(document_hashes) != question_count
                    or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in document_hashes)
                    or preparation.get("parent_articles") != question_count):
                raise ValueError("fresh document sample requires one distinct parent article and content hash per question")
        token = preparation["models"][stage["model_key"]]
        if (token["request_count"] != stage["request_count"] or token["overflow_count"] != 0
                or not 0 < token["max_prompt_tokens"] <= 8192 - (768 if stage["experiment"] in {"routing_confirmation", "evidence_control"} else 384 if stage["experiment"] == "review_routing" else 128)
                or token["path"] != plan["models"][stage["model_key"]]["path"]):
            raise ValueError("actual tokenizer proof differs from frozen requests")
    return proofs


def wait_for_idle_gpu(plan, update):
    """Wait for other compute clients; never stop or modify their processes."""
    deadline = time.monotonic() + plan["resource_wait_seconds"]
    while True:
        output = subprocess.check_output([
            "nvidia-smi", "--id=0", "--query-compute-apps=pid",
            "--format=csv,noheader,nounits"], text=True, timeout=20)
        clients = [int(line.strip()) for line in output.splitlines() if line.strip()]
        if not clients:
            update(phase="GPU_IDLE_VERIFIED", other_gpu_clients=[])
            return
        update(phase="WAITING_FOR_RESOURCE", other_gpu_clients=clients,
               wait_reason="OTHER_GPU_COMPUTE_CLIENTS", last_resource_check=now())
        if time.monotonic() >= deadline:
            raise RuntimeError("GPU compute clients remained active; no other process was modified")
        time.sleep(30)


def run_queue(plan):
    validate_plan(plan)
    status_path = Path(plan["status_path"])
    if status_path.exists():
        raise ValueError("exclusive queue status already exists")
    state = {"kind": plan["kind"], "run_id": plan["run_id"], "pid": os.getpid(),
             "code_revision": plan["code_revision"], "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(),
             "status": "RUNNING", "phase": "PRECHECK", "exit_code": None, "started_at": now(),
             "stages": [{"id": s["id"], "experiment": s["experiment"], "status": "PENDING",
                         "exit_code": None, "request_count": s["request_count"],
                         "benchmark_started": False} for s in plan["stages"]]}

    def update(**values):
        state.update(values)
        state["updated_at"] = now()
        save_json(status_path, state)

    exit_code = 1
    try:
        update()
        verify_inputs(plan)
        update(phase="CPU_PROOFS_VERIFIED")
        for model_key in ("gemma12b", "qwen27b"):
            model = plan["models"][model_key]
            selected = [(index, stage) for index, stage in enumerate(plan["stages"])
                        if stage["model_key"] == model_key]
            runtime = {"model_key": model_key, "served_model": model["served_name"]}
            state.setdefault("runtimes", []).append(runtime)
            server = benchmark = None
            try:
                if plan.get("require_idle_gpu"):
                    wait_for_idle_gpu(plan, update)
                if not (Path(model["path"]) / "config.json").is_file():
                    raise ValueError("local model config unavailable")
                command = [plan["model_python"], "-m", "vllm.entrypoints.openai.api_server",
                    "--model", model["path"], "--served-model-name", model["served_name"],
                    "--host", "127.0.0.1", "--port", str(plan["port"]), "--dtype", "bfloat16",
                    "--max-model-len", "8192", "--max-num-seqs", "1",
                    "--gpu-memory-utilization", str(model["gpu_memory_utilization"]),
                    "--enforce-eager", "--generation-config", "vllm", "--language-model-only",
                    "--no-enable-log-requests"]
                environment = {**os.environ, "CUDA_VISIBLE_DEVICES": "0", "HF_HOME": plan["hf_home"],
                    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "OMP_NUM_THREADS": "8",
                    "VLLM_CACHE_ROOT": str(Path(plan["run_root"]) / "runtime_cache")}
                environment.pop("PYTHONPATH", None)
                # Reuse the bounded, owned-runtime resource race handler; no old plan validation.
                runtime_plan = {**plan, "schema_version": 5}
                update(active_model=model_key, active_stage=selected[0][1]["id"], phase="MODEL_PREPARATION")
                server, free, endpoint = start_model_runtime(runtime_plan, model,
                    {"id": "runtime_" + model_key}, command, environment, runtime, update)
                for index, stage in selected:
                    current = state["stages"][index]
                    out = Path(plan["run_root"]) / "results" / stage["id"]
                    if out.exists():
                        raise ValueError("stage output already exists; no answer reruns allowed")
                    current.update(status="RUNNING", benchmark_started=True, started_at=now())
                    update(active_stage=stage["id"], phase="MODEL_REQUESTS", responses_completed=0)
                    extended = plan["kind"] in {EXTENDED_KIND, DIAGNOSTIC_KIND, REVIEW_KIND, CONFIRMATION_KIND, EVIDENCE_KIND}
                    runner_module = "eval.run_extended_suite" if extended else "eval.run_followup_llm"
                    report_module = "eval.report_extended_suite" if extended else "eval.report_followup_llm"
                    run_command = [plan["python"], "-m", runner_module,
                        "--requests-file", stage["requests_file"], "--endpoint", endpoint,
                        "--model", model["served_name"], "--out-dir", str(out),
                        "--code-revision", plan["code_revision"]]
                    try:
                        benchmark = subprocess.Popen(run_command, cwd=plan["source"],
                            stdin=subprocess.DEVNULL, start_new_session=True, env=environment)
                        while benchmark.poll() is None:
                            responses = out / "responses.jsonl"
                            completed = 0
                            if responses.exists():
                                with responses.open("rb") as stream:
                                    completed = sum(1 for _ in stream)
                            update(responses_completed=completed)
                            time.sleep(15)
                        manifest = json.loads((out / "run_manifest.json").read_text())
                        if any(manifest.get(key) != value for key, value in {
                                "request_corpus_sha256": stage["requests_sha256"],
                                "frozen_request_file_sha256": stage["envelope_sha256"],
                                "request_count": stage["request_count"], "code_revision": plan["code_revision"],
                                "requested_model": model["served_name"], "experiment": stage["experiment"]}.items()):
                            raise ValueError("stage manifest differs from frozen plan")
                        save_json(out / "environment.json", {"model_command": command,
                            "benchmark_command": run_command, "gpu_free_mib_before_start": free,
                            "checkpoint_revision": model.get("revision", "NOT_VERIFIED"),
                            "model_config_sha256": file_hash(Path(model["path"]) / "config.json"),
                            "code_revision": plan["code_revision"], "source_archive_sha256": plan["archive_sha256"],
                            "queue_plan_sha256": state["plan_sha256"]})
                        report = subprocess.run([plan["python"], "-m", report_module,
                            "--run-dir", str(out)], cwd=plan["source"], env=environment)
                        result_code = benchmark.returncode or report.returncode
                        current.update(status="COMPLETE" if result_code == 0 else "FAILED",
                            exit_code=result_code, benchmark_exit_code=benchmark.returncode,
                            report_exit_code=report.returncode, finished_at=now(),
                            **{key: manifest[key] for key in ("received_count", "missing_count", "error_count", "malformed_count")})
                        update(responses_completed=manifest["received_count"])
                    except Exception as error:
                        current.update(status="FAILED", exit_code=1, finished_at=now(), error_type=type(error).__name__)
                    finally:
                        stop_owned(benchmark)
                        benchmark = None
                        update()
            except Exception as error:
                runtime["error_type"] = type(error).__name__
                for index, _ in selected:
                    current = state["stages"][index]
                    if current["status"] in {"PENDING", "RUNNING"}:
                        current.update(status="FAILED", exit_code=1, finished_at=now(), error_type=type(error).__name__)
                update()
            finally:
                update(phase="RUNTIME_CLEANUP")
                stop_owned(benchmark)
                stop_owned(server)
                runtime.update(server_exit_code=None if server is None else server.returncode, finished_at=now())
                update()
        exit_code = int(any(row["exit_code"] != 0 for row in state["stages"]))
    except (Exception, KeyboardInterrupt) as error:
        state["error_type"] = type(error).__name__
    finally:
        update(status="COMPLETE" if exit_code == 0 else "FAILED", phase="FINISHED",
               exit_code=exit_code, finished_at=now())
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    return run_queue(json.loads(args.plan.read_text()))


if __name__ == "__main__":
    raise SystemExit(main())
