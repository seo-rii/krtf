"""Prospective workload, source seals, output budgets and resource ownership."""
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
def evidence_plan(frozen_plan, monkeypatch, tmp_path):
    plan = deepcopy(frozen_plan)
    plan.update(kind=queue.EVIDENCE_KIND, run_id="evidence_queue",
                require_idle_gpu=True, stages=[])
    plan["proofs"].pop("blind_document")
    rows = [{"authored_index": i} for i in range(256)]
    path = tmp_path / "evidence_control.json"
    path.write_bytes(canonical({"authored_experiment": "evidence_control"}))
    spec = {
        "request_count": 256, "envelope_sha256": queue.file_hash(path),
        "requests_sha256": hashlib.sha256(b"".join(canonical(r) for r in rows)).hexdigest(),
        "models": {key: {"path": model["path"], "request_count": 256,
                         "max_prompt_tokens": 7424, "overflow_count": 0}
                   for key, model in plan["models"].items()},
    }
    for experiment, model in queue.EVIDENCE_ORDER:
        plan["stages"].append({"id": experiment + "_" + model, "experiment": experiment,
            "model_key": model, "requests_file": str(path),
            **{k: spec[k] for k in ("request_count", "requests_sha256", "envelope_sha256")}})
    rewrite_proof(plan, "preparation", lambda p:
                  p.update(experiments={"evidence_control": spec}))
    monkeypatch.setattr(runner, "load_request_file", lambda path:
                        (rows, {"experiment": "evidence_control"}, {"authored": True}))
    return plan


def test_evidence_seals_and_768_token_output_reservation(evidence_plan):
    assert queue.verify_inputs(evidence_plan)["unit"]["exit_code"] == 0
    assert sum(s["request_count"] for s in evidence_plan["stages"]) == 512
    rewrite_proof(evidence_plan, "preparation", lambda p:
        p["experiments"]["evidence_control"]["models"]["qwen27b"].update(max_prompt_tokens=7425))
    with pytest.raises(ValueError, match="token"):
        queue.verify_inputs(evidence_plan)


@pytest.mark.parametrize("mutation", [
    lambda p: p.pop("require_idle_gpu"),
    lambda p: p["stages"].reverse(),
    lambda p: p["stages"][0].update(request_count=255),
    lambda p: p["stages"][1].update(requests_sha256="0" * 64),
])
def test_evidence_design_cannot_silently_change(evidence_plan, mutation):
    mutation(evidence_plan)
    with pytest.raises(ValueError):
        queue.validate_plan(evidence_plan)


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


def test_evidence_queue_runs_both_models_after_one_stage_fails(evidence_plan, monkeypatch):
    calls, stopped, servers = mock_runtime(monkeypatch, evidence_plan,
        failed_stage=evidence_plan["stages"][0]["id"])
    waits = []
    monkeypatch.setattr(queue, "wait_for_idle_gpu", lambda *args: waits.append(True))
    assert queue.run_queue(evidence_plan) == 1
    assert calls == [s["id"] for s in evidence_plan["stages"]]
    assert len(waits) == len(servers) == 2
    assert all(server in stopped for server in servers)
    state = json.loads(Path(evidence_plan["status_path"]).read_text())
    assert state["stages"][1]["status"] == "COMPLETE"


def test_evidence_collector_reparses_raw_responses(evidence_plan, monkeypatch, tmp_path):
    from eval import report_extended_suite
    def reject_unsealed(root):
        raise ValueError("unsealed evidence output")
    monkeypatch.setattr(report_extended_suite, "prepare_report", reject_unsealed)
    with pytest.raises(ValueError, match="unsealed evidence"):
        collector.verify_stage(tmp_path, evidence_plan["stages"][0], evidence_plan)


def test_evidence_runner_schemas_raw_regrading_and_proposal_counts(tmp_path, monkeypatch):
    from eval import evidence_control as suite
    from eval import report_extended_suite as reporter
    from test_evidence_control import prepare, response
    envelope, _ = prepare()
    by_prompt = {(row['system'], row['user']): row for row in envelope['requests']}
    calls = []

    def fake_request(endpoint, *, payload=None, timeout):
        if endpoint.endswith('/models'):
            return {'data': [{'id': 'fixture-model'}]}
        row = by_prompt[tuple(message['content'] for message in payload['messages'])]
        assert payload['max_tokens'] == 768
        assert payload['response_format']['json_schema']['schema'] == suite.evidence_control_schema(row)
        answer = response(row)
        if row['condition'] == 'ktrf_evidence_offsets':
            answer['selections'][0]['assertion']['evidence']['end'] -= 1
        calls.append(row['condition'])
        return {'choices': [{'message': {'content': json.dumps(answer, ensure_ascii=False)},
                             'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}}

    monkeypatch.setattr(runner, '_request_json', fake_request)
    request_path = tmp_path / 'requests.json'
    request_path.write_bytes(canonical(envelope))
    output = tmp_path / 'output'
    manifest = runner.run_benchmark(requests_file=request_path,
        endpoint='http://127.0.0.1:18117/v1', model='fixture-model',
        out_dir=output, code_revision='f' * 40)
    assert calls == [row['condition'] for row in envelope['requests']]
    assert manifest['status'] == 'COMPLETE'
    assert manifest['answer_schema'] == {row['condition']: suite.evidence_control_schema(row)
                                         for row in envelope['requests']}
    _, rows, records, graded, counts = reporter.read_run(output)
    assert graded == runner.grade_outputs(rows, records, envelope['protocol'])
    assert counts['malformed_count'] == counts['error_count'] == 0
    summary = reporter.prepare_report(output)
    offsets = summary['by_variant']['ktrf_evidence_offsets']
    ids = summary['by_variant']['ktrf_evidence_ids']
    assert offsets['proposal_correct_id'] == ids['proposal_correct_id'] == 1
    assert offsets['accepted_correct_id'] == 0
    assert ids['accepted_correct_id'] == 1
    assert summary['pipeline_diagnostics']['development']['positive_gold_in_candidates'] == 1
    assert 'Correct ID proposals' in reporter.render_markdown(summary)
    # An updated artifact seal cannot change the per-condition schema contract.
    manifest['answer_schema']['ktrf_evidence_ids'] = suite.evidence_control_schema('plain_matched')
    manifest.pop('seal_sha256')
    manifest['seal_sha256'] = hashlib.sha256(canonical(manifest)).hexdigest()
    (output / 'run_manifest.json').write_bytes(canonical(manifest))
    with pytest.raises(ValueError, match='manifest disagree'):
        reporter.read_run(output)


def test_evidence_wrapper_freezes_only_exposed_development(tmp_path, monkeypatch):
    from eval import prepare_evidence_control as wrapper
    from eval.routing_confirmation_data import SOURCE_SHA256, REVIEW_SHA256
    from test_evidence_control import FixtureTokenizer
    selected = {'source_sha256': SOURCE_SHA256, 'review_sha256': REVIEW_SHA256,
        'models': {key: {'path': 'fixture:' + key} for key in ('gemma12b', 'qwen27b')}}
    monkeypatch.setattr(wrapper, 'load_tokenizers',
                        lambda models: {key: FixtureTokenizer() for key in models})
    root = tmp_path / 'prepared'
    manifest = wrapper.prepare(selected, root, code_revision='f' * 40)
    rows, protocol, provenance = runner.load_request_file(root / 'evidence_control.json')
    assert len(rows) == 256 and manifest['total_planned_model_calls'] == 512
    assert {row['evaluation_split'] for row in rows} == {'development'}
    assert len({row['family_id'] for row in rows}) == 8
    assert provenance['source']['evaluation_population'] == 'EXPOSED_DIAGNOSTIC'
    assert provenance['source']['original_review_applies_to_source_labels_only']
    assert provenance['source']['independent_ai_review']['cases_reviewed'] == 64
    assert provenance['source']['independent_ai_review']['original_cases_reviewed'] == 192
    assert manifest['posthoc_method_selection_not_independent_confirmation']
    assert json.loads((root / 'manifest.json').read_text()) == manifest


@pytest.mark.parametrize('field', ['source_sha256', 'review_sha256'])
def test_evidence_wrapper_rejects_changed_seals_before_loading(tmp_path, monkeypatch, field):
    from eval import prepare_evidence_control as wrapper
    from eval.routing_confirmation_data import SOURCE_SHA256, REVIEW_SHA256
    selected = {'source_sha256': SOURCE_SHA256, 'review_sha256': REVIEW_SHA256,
        'models': {key: {'path': 'fixture:' + key} for key in ('gemma12b', 'qwen27b')}}
    selected[field] = '0' * 64
    monkeypatch.setattr(wrapper, 'load_routing_confirmation_records',
                        lambda *args: pytest.fail('changed seals must fail before loading'))
    with pytest.raises(ValueError, match='source gold or independent review changed'):
        wrapper.prepare(selected, tmp_path / 'absent', code_revision='f' * 40)
