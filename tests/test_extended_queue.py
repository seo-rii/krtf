"""The five-track queue binds inputs and preserves missing denominators."""
import copy
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
def extended_plan(frozen_plan, monkeypatch, tmp_path):
    plan = copy.deepcopy(frozen_plan)
    plan.update(kind=queue.EXTENDED_KIND, run_id="authored_extended_queue", stages=[])
    plan["proofs"].pop("blind_document")
    rows, experiments = {}, {}
    for experiment, count in queue.EXTENDED_COUNTS.items():
        rows[experiment] = [{"authored_index": i} for i in range(count)]
        path = tmp_path / (experiment + ".json")
        path.write_bytes(canonical({"authored_experiment": experiment}))
        experiments[experiment] = {
            "request_count": count, "envelope_sha256": queue.file_hash(path),
            "requests_sha256": hashlib.sha256(b"".join(canonical(r) for r in rows[experiment])).hexdigest(),
            "models": {key: {"path": model["path"], "request_count": count,
                              "max_prompt_tokens": 8064, "overflow_count": 0}
                       for key, model in plan["models"].items()}}
    for experiment, model in queue.EXTENDED_ORDER:
        spec = experiments[experiment]
        plan["stages"].append({"id": experiment + "_" + model, "experiment": experiment,
            "model_key": model, "requests_file": str(tmp_path / (experiment + ".json")),
            **{k: spec[k] for k in ("request_count", "requests_sha256", "envelope_sha256")}})
    rewrite_proof(plan, "preparation", lambda proof: proof.update(experiments=experiments))
    monkeypatch.setattr(runner, "load_request_file", lambda path: (
        rows[Path(path).stem], {"experiment": Path(path).stem}, {"authored": True}))
    return plan


def test_all_five_inputs_are_bound_before_inference(extended_plan):
    assert queue.verify_inputs(extended_plan)["unit"]["exit_code"] == 0
    assert sum(s["request_count"] for s in extended_plan["stages"]) == 5568
    rewrite_proof(extended_plan, "preparation", lambda proof:
                  proof["experiments"]["semantic_safety"].update(requests_sha256="0" * 64))
    with pytest.raises(ValueError, match="exact frozen corpus"):
        queue.verify_inputs(extended_plan)


@pytest.mark.parametrize("mutate", [
    lambda p: p["stages"].reverse(),
    lambda p: p["stages"].pop(),
    lambda p: p["stages"][0].update(request_count=1023),
    lambda p: p["stages"][5].update(requests_sha256="0" * 64),
    lambda p: p.update(sample_design={"kind": "fresh_document_holdout"}),
])
def test_extended_matrix_drift_fails_closed(extended_plan, mutate):
    mutate(extended_plan)
    with pytest.raises(ValueError):
        queue.validate_plan(extended_plan)


def test_serial_stages_dispatch_new_runner_and_keep_later_work(extended_plan, monkeypatch):
    failed = extended_plan["stages"][1]["id"]
    calls, stopped, servers = mock_runtime(monkeypatch, extended_plan, failed_stage=failed)
    original = queue.subprocess.Popen
    modules = []

    def popen(command, **kwargs):
        modules.append(command[command.index("-m") + 1])
        return original(command, **kwargs)

    monkeypatch.setattr(queue.subprocess, "Popen", popen)
    assert queue.run_queue(extended_plan) == 1
    assert calls == [s["id"] for s in extended_plan["stages"]]
    assert modules == ["eval.run_extended_suite"] * 10
    assert len(servers) == 2 and all(server in stopped for server in servers)
    state = json.loads(Path(extended_plan["status_path"]).read_text())
    assert sum(s["status"] == "COMPLETE" for s in state["stages"]) == 9


def test_comparison_does_not_invent_null_rates_for_positive_only_corpus(extended_plan):
    summaries = {}
    for stage in extended_plan["stages"]:
        summaries[stage["id"]] = {
            "request_corpus_sha256": stage["requests_sha256"], "code_revision": "same", "decoding": {},
            "model": stage["model_key"], "questions": 128,
            "by_variant": {"authored": {"positive_exact_rate": 0.5,
                "article_no_answer_null_rate": None, "malformed": 0,
                "correct_rate": 0.75, "accepted_wrong_id_rate": 0.125}}}
    compared = collector.compare_models(summaries, extended_plan)
    corpus = compared["corpus"]["by_variant"]["authored"]
    assert corpus["positive_exact_rate_delta"] == 0
    assert corpus["no_answer_null_rate_delta"] is None
    assert compared["semantic_safety"]["by_variant"]["authored"]["accepted_wrong_id_rate_delta"] == 0


def test_extended_collection_uses_raw_extended_regrader(extended_plan, monkeypatch, tmp_path):
    from eval import report_extended_suite as report
    stage = extended_plan["stages"][0]
    seen = []

    def reject_unsealed(root):
        seen.append(root)
        raise ValueError("unsealed extended output")

    monkeypatch.setattr(report, "prepare_report", reject_unsealed)
    with pytest.raises(ValueError, match="unsealed extended"):
        collector.verify_stage(tmp_path, stage, extended_plan)
    assert seen == [tmp_path]
