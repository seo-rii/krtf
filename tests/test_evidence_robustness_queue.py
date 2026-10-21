"""Reused-source diagnostic matrix, sealed inputs and predecessor ownership."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from eval import report_extended_suite
from eval import collect_followup_queue as collector
from eval import run_extended_suite as runner
from eval import run_followup_queue as queue
from eval.hf_qa import canonical
from test_followup_queue import frozen_plan, mock_runtime, rewrite_proof


@pytest.fixture
def robustness_plan(frozen_plan, monkeypatch, tmp_path):
    plan = deepcopy(frozen_plan)
    plan.update(kind=queue.ROBUSTNESS_KIND, run_id="robustness_queue",
                require_idle_gpu=True, stages=[], predecessor={
                    "run_id": "preceding_efficiency_queue",
                    "status_path": str(tmp_path / "predecessor.status.json"),
                    "publication_marker": str(tmp_path / "predecessor-publication.json")})
    plan["proofs"].pop("blind_document")
    rows = [{"authored_index": i} for i in range(384)]
    path = tmp_path / "evidence_robustness.json"
    path.write_bytes(canonical({"authored_experiment": "evidence_robustness"}))
    spec = {
        "request_count": 384, "envelope_sha256": queue.file_hash(path),
        "requests_sha256": hashlib.sha256(b"".join(canonical(r) for r in rows)).hexdigest(),
        "models": {key: {"path": model["path"], "request_count": 384,
                         "max_prompt_tokens": 7424, "overflow_count": 0}
                   for key, model in plan["models"].items()},
    }
    for experiment, model in queue.ROBUSTNESS_ORDER:
        plan["stages"].append({"id": experiment + "_" + model, "experiment": experiment,
            "model_key": model, "requests_file": str(path),
            **{k: spec[k] for k in ("request_count", "requests_sha256", "envelope_sha256")}})
    rewrite_proof(plan, "preparation", lambda p:
                  p.update(experiments={"evidence_robustness": spec}))
    monkeypatch.setattr(runner, "load_request_file", lambda path:
                        (rows, {"experiment": "evidence_robustness"}, {"authored": True}))
    return plan


def publish_predecessor(plan):
    spec = plan["predecessor"]
    Path(spec["status_path"]).write_bytes(canonical({"run_id": spec["run_id"],
        "status": "COMPLETE", "exit_code": 0}))
    Path(spec["publication_marker"]).write_bytes(canonical({"run_id": spec["run_id"],
        "queue_exit_code": 0, "collector_exit_code": 0, "published": True,
        "collector_commit": "a" * 40}))


def test_robustness_offline_precheck_before_predecessor_publication(robustness_plan):
    assert queue.ROBUSTNESS_COUNTS == {"evidence_robustness": 384}
    assert queue.ROBUSTNESS_ORDER == [("evidence_robustness", "gemma12b"),
                                      ("evidence_robustness", "qwen27b")]
    assert sum(s["request_count"] for s in robustness_plan["stages"]) == 768
    assert queue.verify_inputs(robustness_plan)["unit"]["exit_code"] == 0
    assert not Path(robustness_plan["predecessor"]["publication_marker"]).exists()


@pytest.mark.parametrize("mutation", [
    lambda p: p.pop("require_idle_gpu"),
    lambda p: p["stages"].reverse(),
    lambda p: p["stages"][0].update(request_count=383),
    lambda p: p["stages"][1].update(requests_sha256="0" * 64),
    lambda p: p["stages"][1].update(requests_file="different-source.json"),
    lambda p: p.pop("predecessor"),
    lambda p: p["predecessor"].update(run_id=p["run_id"]),
    lambda p: p["predecessor"].update(status_path="relative.json"),
    lambda p: p["predecessor"].update(publication_marker=None),
    lambda p: p["predecessor"].update(publication_marker=p["predecessor"]["status_path"]),
])
def test_robustness_design_fails_closed(robustness_plan, mutation):
    mutation(robustness_plan)
    with pytest.raises(ValueError):
        queue.validate_plan(robustness_plan)


@pytest.mark.parametrize("mutation", [
    lambda p: p["experiments"]["evidence_robustness"].update(requests_sha256="0" * 64),
    lambda p: p["experiments"]["evidence_robustness"]["models"]["gemma12b"].update(overflow_count=1),
    lambda p: p["experiments"]["evidence_robustness"]["models"]["qwen27b"].update(path="/other-model"),
    lambda p: p["experiments"]["evidence_robustness"]["models"]["qwen27b"].update(max_prompt_tokens=7425),
])
def test_robustness_token_proof_binds_corpus_checkpoint_and_output_reserve(robustness_plan, mutation):
    rewrite_proof(robustness_plan, "preparation", mutation)
    with pytest.raises(ValueError):
        queue.verify_inputs(robustness_plan)


@pytest.mark.parametrize("target,mutation", [
    ("status_path", lambda p: p.update(run_id="wrong_queue")),
    ("status_path", lambda p: p.update(status="RUNNING")),
    ("status_path", lambda p: p.update(exit_code=1)),
    ("status_path", lambda p: p.update(exit_code=False)),
    ("publication_marker", lambda p: p.update(run_id="wrong_queue")),
    ("publication_marker", lambda p: p.update(published=False)),
    ("publication_marker", lambda p: p.update(queue_exit_code=1)),
    ("publication_marker", lambda p: p.update(collector_exit_code=1)),
    ("publication_marker", lambda p: p.update(collector_exit_code=False)),
    ("publication_marker", lambda p: p.update(collector_commit="main")),
])
def test_robustness_rejects_unfinished_or_unpublished_predecessor(robustness_plan, target, mutation):
    publish_predecessor(robustness_plan)
    path = Path(robustness_plan["predecessor"][target])
    value = json.loads(path.read_text())
    mutation(value)
    path.write_bytes(canonical(value))
    with pytest.raises(ValueError, match="publication"):
        queue.verify_predecessor(robustness_plan)


def test_robustness_does_not_start_during_predecessor_between_model_gap(robustness_plan, monkeypatch):
    # An empty GPU is insufficient when an older queue has not published yet.
    calls, _, servers = mock_runtime(monkeypatch, robustness_plan)
    monkeypatch.setattr(queue, "wait_for_idle_gpu", lambda *args: pytest.fail("predecessor must be checked first"))
    assert queue.run_queue(robustness_plan) == 1
    assert calls == servers == []
    status = json.loads(Path(robustness_plan["status_path"]).read_text())
    assert not any(stage["benchmark_started"] for stage in status["stages"])


def test_robustness_rechecks_predecessor_before_second_model(robustness_plan, monkeypatch):
    publish_predecessor(robustness_plan)
    calls, _, servers = mock_runtime(monkeypatch, robustness_plan)
    def idle(*args):
        # Lose the publication attestation after first startup; Qwen cannot start.
        Path(robustness_plan["predecessor"]["publication_marker"]).unlink()
    monkeypatch.setattr(queue, "wait_for_idle_gpu", idle)
    assert queue.run_queue(robustness_plan) == 1
    assert calls == [robustness_plan["stages"][0]["id"]]
    assert len(servers) == 1


def test_robustness_runs_serial_models_after_published_predecessor(robustness_plan, monkeypatch):
    publish_predecessor(robustness_plan)
    calls, stopped, servers = mock_runtime(monkeypatch, robustness_plan)
    waits = []
    monkeypatch.setattr(queue, "wait_for_idle_gpu", lambda *args: waits.append(True))
    assert queue.run_queue(robustness_plan) == 0
    assert calls == [s["id"] for s in robustness_plan["stages"]]
    assert len(waits) == len(servers) == 2
    assert all(server in stopped for server in servers)


def test_robustness_collector_requires_sealed_raw_regrade(robustness_plan, monkeypatch, tmp_path):
    def reject_unsealed(root):
        raise ValueError("unsealed robustness output")
    monkeypatch.setattr(report_extended_suite, "prepare_report", reject_unsealed)
    with pytest.raises(ValueError, match="unsealed robustness"):
        collector.verify_stage(tmp_path, robustness_plan["stages"][0], robustness_plan)


def test_robustness_runner_regrades_format_specific_schemas_and_reused_population(tmp_path, monkeypatch):
    from eval import evidence_robustness as suite
    from test_evidence_efficiency import FixtureTokenizer, provenance, response, source_record

    sources = [source_record(case="resolved"), source_record(case="ambiguous", collision=True,
        text="휘온의 관할은 대한민국이며 현재 운영 중인 업무 절차로서 내부 직원에게 적용한다. 담당자는 확인했다.")]
    models = {name: {"path": "unit-fixture", "revision": "unit"}
              for name in ("gemma12b", "qwen27b")}
    envelope, _ = suite.prepare_evidence_robustness(records=sources,
        models=models, tokenizers={name: FixtureTokenizer() for name in models},
        code_revision="f" * 40,
        source_provenance={**provenance(sources), "evaluation_population": suite.POPULATION})
    by_prompt = {(row["system"], row["user"]): row for row in envelope["requests"]}
    calls = []

    def fake_request(endpoint, *, payload=None, timeout):
        if endpoint.endswith("/models"):
            return {"data": [{"id": "fixture-model"}]}
        row = by_prompt[tuple(message["content"] for message in payload["messages"])]
        assert payload["max_tokens"] == 768
        assert payload["response_format"]["json_schema"]["schema"] == suite.evidence_robustness_schema(row)
        if row["condition"].startswith("bundle_"):
            eid = next(alias for alias, entity in row["reference_registry"]["entities"].items()
                       if entity == "global:control-a")
            bundle = next(alias for alias, bundle in row["bundle_inventory"]["bundles"].items()
                          if bundle["entity_alias"] == eid)
            answer = {"selections": [{"r": row["reference_registry"]["request_ref"],
                                      "e": eid, "s": "SUPPORT", "b": bundle}]}
        else:
            answer = response({**row, "condition": "evidence_compact"})
        calls.append((row["case_id"], row["condition"]))
        return {"choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}

    monkeypatch.setattr(runner, "_request_json", fake_request)
    request_path = tmp_path / "requests.json"
    request_path.write_bytes(canonical(envelope))
    output = tmp_path / "output"
    manifest = runner.run_benchmark(requests_file=request_path,
        endpoint="http://127.0.0.1:18119/v1", model="fixture-model",
        out_dir=output, code_revision="f" * 40)
    assert calls == [(row["case_id"], row["condition"]) for row in envelope["requests"]]
    assert manifest["status"] == "COMPLETE"
    schema_key = lambda row: json.dumps([row["case_id"], row["condition"]],
                                       ensure_ascii=False, separators=(",", ":"))
    assert manifest["answer_schema"] == {schema_key(row): suite.evidence_robustness_schema(row)
                                         for row in envelope["requests"]}
    _, rows, records, graded, counts = report_extended_suite.read_run(output)
    assert graded == runner.grade_outputs(rows, records, envelope["protocol"])
    assert counts["malformed_count"] == counts["error_count"] == 0
    assert len(graded["cases"]) == 12
    for case in graded["cases"]:
        assert case["proposal_correct_id"]
        assert case["accepted_correct_id"] is (case["case_id"] == "resolved")
    summary = report_extended_suite.prepare_report(output)
    assert summary["evaluation_population"] == suite.POPULATION
    assert "Reused-source diagnostic" in summary["aggregate_scope"]
    assert set(summary["by_wire_format"]) == {"compact", "bundle"}
    assert set(summary["by_perturbation"]) == {"control", "reordered", "distractors"}
    assert all(value["questions"] == 2 for value in summary["by_perturbation"].values())
    for condition in suite.CONDITIONS:
        bundle_stats = summary["bundle_inventory"][condition]
        assert bundle_stats["source_cases"] == 2
        assert bundle_stats["total_bundle_references"] == 2
        assert bundle_stats["source_cases_with_zero_bundles"] == 0
        assert bundle_stats["total_combinations"] == bundle_stats["emitted_combinations"] == 2
        assert bundle_stats["omitted_combinations"] == 0
        assert bundle_stats["max_per_entity_segment"] == [8]
    markdown = report_extended_suite.render_markdown(summary)
    assert "Correct ID proposals" in markdown
    assert "REUSED_SEALED_SOURCE_DIAGNOSTIC" in markdown
    assert "neither is a new heldout validation set" in markdown
    # The seal alone does not authorize replacing one transport's schema with another.
    compact = next(row for row in rows if row["condition"] == "compact_control")
    bundle = next(row for row in rows if row["condition"] == "bundle_control")
    manifest["answer_schema"][schema_key(compact)] = suite.evidence_robustness_schema(bundle)
    manifest.pop("seal_sha256")
    manifest["seal_sha256"] = hashlib.sha256(canonical(manifest)).hexdigest()
    (output / "run_manifest.json").write_bytes(canonical(manifest))
    with pytest.raises(ValueError, match="manifest disagree"):
        report_extended_suite.read_run(output)
