"""Bound follow-on workload and preserve the fresh/exposed evidence boundary."""
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
def review_plan(frozen_plan, monkeypatch, tmp_path):
    plan = copy.deepcopy(frozen_plan)
    plan.update(kind=queue.REVIEW_KIND, run_id="review_queue", stages=[])
    plan["proofs"].pop("blind_document")
    rows, experiments = {}, {}
    for name, count in queue.REVIEW_COUNTS.items():
        rows[name] = [{"authored_index": i} for i in range(count)]
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical({"authored_experiment": name}))
        experiments[name] = {"request_count": count, "envelope_sha256": queue.file_hash(path),
            "requests_sha256": hashlib.sha256(b"".join(canonical(r) for r in rows[name])).hexdigest(),
            "models": {key: {"path": model["path"], "request_count": count,
                              "max_prompt_tokens": 7808 if name == "review_routing" else 8064,
                              "overflow_count": 0}
                       for key, model in plan["models"].items()}}
    for name, model in queue.REVIEW_ORDER:
        plan["stages"].append({"id": name + "_" + model, "experiment": name, "model_key": model,
            "requests_file": str(tmp_path / (name + ".json")),
            **{k: experiments[name][k] for k in ("request_count", "requests_sha256", "envelope_sha256")}})
    rewrite_proof(plan, "preparation", lambda proof: proof.update(experiments=experiments))
    monkeypatch.setattr(runner, "load_request_file", lambda path: (
        rows[Path(path).stem], {"experiment": Path(path).stem}, {"authored": True}))
    return plan


def test_diagnostic_proofs_bind_all_three_inputs(review_plan):
    assert queue.verify_inputs(review_plan)["unit"]["exit_code"] == 0
    assert sum(s["request_count"] for s in review_plan["stages"]) == 5888
    rewrite_proof(review_plan, "preparation", lambda proof:
                  proof["experiments"]["review_policy"].update(requests_sha256="0" * 64))
    with pytest.raises(ValueError, match="exact frozen corpus"):
        queue.verify_inputs(review_plan)


@pytest.mark.parametrize("mutate", [lambda p: p["stages"].reverse(),
    lambda p: p["stages"].pop(), lambda p: p["stages"][0].update(request_count=1023),
    lambda p: p["stages"][5].update(envelope_sha256="0" * 64)])
def test_diagnostic_matrix_cannot_silently_drift(review_plan, mutate):
    mutate(review_plan)
    with pytest.raises(ValueError):
        queue.validate_plan(review_plan)


def test_queue_keeps_later_diagnostics_after_independent_stage_failure(review_plan, monkeypatch):
    calls, stopped, servers = mock_runtime(monkeypatch, review_plan,
                                          failed_stage=review_plan["stages"][0]["id"])
    original = queue.subprocess.Popen
    modules = []
    def popen(command, **kwargs):
        modules.append(command[command.index("-m") + 1])
        return original(command, **kwargs)
    monkeypatch.setattr(queue.subprocess, "Popen", popen)
    assert queue.run_queue(review_plan) == 1
    assert calls == [s["id"] for s in review_plan["stages"]]
    assert modules == ["eval.run_extended_suite"] * 10
    assert len(servers) == 2 and all(server in stopped for server in servers)


def summaries_for(plan):
    summaries = {}
    for stage in plan["stages"]:
        rates = {"malformed": 0, "accepted_wrong_id_rate": .25 if stage["model_key"] == "gemma12b" else 0}
        splits = {"authored_business": {"questions": 64, "families": 16, "by_variant": {"baseline": rates}},
                  "natural_public": {"questions": 32, "families": 32, "by_variant": {"baseline": {
                      "malformed": 0, "accepted_wrong_id_rate": 0}}}}
        summaries[stage["id"]] = {"request_corpus_sha256": stage["requests_sha256"],
            "code_revision": "same", "decoding": {}, "model": stage["model_key"], "questions": 96,
            "by_variant": {"baseline": rates}, "by_evaluation_split": splits}
    return summaries


def test_model_comparison_never_substitutes_pooled_safety_for_fresh(review_plan):
    result = collector.compare_models(summaries_for(review_plan), review_plan)["review_routing"]
    splits = result["by_evaluation_split"]
    assert splits["authored_business"]["by_variant"]["baseline"]["accepted_wrong_id_rate_delta"] == -.25
    assert splits["natural_public"]["by_variant"]["baseline"]["accepted_wrong_id_rate_delta"] == 0
    assert splits["natural_public"]["questions"] == 32
    assert "workload aggregate only" in result["aggregate_scope"]


def test_model_comparison_rejects_split_relabeling(review_plan):
    summaries = summaries_for(review_plan)
    summaries["review_routing_qwen27b"]["by_evaluation_split"]["natural_public"]["questions"] = 160
    with pytest.raises(ValueError, match="evaluation splits differ"):
        collector.compare_models(summaries, review_plan)
