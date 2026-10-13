"""Live runner keeps grading data local and distinguishes failures from abstention."""
import hashlib
import json
from urllib.error import URLError

import pytest

from eval import run_product_llm as runner
from eval.product_utility import build_requests


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps(self.value).encode()


def _completion(content):
    return {"model": "served", "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16}}


def test_runner_wire_prompts_malformed_missing_and_sealed_provenance(tmp_path, monkeypatch):
    rows = build_requests()
    rows = [next(row for row in rows if row["case_id"] == "missing:structured_routing"
                 and row["condition"] == condition)
            for condition in ("no_context", "ktrf:plain:knowledge", "ktrf:plain:evidence_only",
                              "ktrf:structured:knowledge", "ktrf:structured:evidence_only")]
    monkeypatch.setattr(runner, "build_requests", lambda: rows)
    sent = []
    answers = iter(['{"entity_id":null,"answer":null}', "not JSON", "[]", URLError("offline"),
                    '```json\n{"entity_id":null}\n```'])

    def fake_urlopen(request, timeout):
        assert timeout == 180
        if request.full_url.endswith("/models"):
            assert request.data is None
            return FakeResponse({"data": [{"id": "served", "root": "frozen-model"}]})
        payload = json.loads(request.data)
        sent.append(payload)
        content = next(answers)
        if isinstance(content, Exception):
            raise content
        return FakeResponse(_completion(content))

    monkeypatch.setattr(runner, "urlopen", fake_urlopen)
    out = tmp_path / "run"
    manifest = runner.run_benchmark(endpoint="http://localhost:18090/v1", model="served",
                                    out_dir=out, code_revision="frozen-sha")
    assert len(sent) == len(rows)
    for payload, row in zip(sent, rows):
        assert payload == {"model": "served", "messages": [
            {"role": "system", "content": row["system"]},
            {"role": "user", "content": row["user"]}], "temperature": 0, "seed": 0,
            "max_tokens": 128, "chat_template_kwargs": {"enable_thinking": False}}
    records = [json.loads(line) for line in (out / "responses.jsonl").read_text().splitlines()]
    assert [r["status"] for r in records] == ["RECEIVED", "MALFORMED", "MALFORMED", "TRANSPORT_ERROR", "RECEIVED"]
    assert records[1]["response"] == records[2]["response"] == {}
    assert records[1]["parse_error"] and records[2]["parse_error"]
    assert "response" not in records[3]
    assert records[0]["raw_text"] == '{"entity_id":null,"answer":null}'
    assert records[4]["raw_text"] == '```json\n{"entity_id":null}\n```'
    assert records[4]["response"] == {"entity_id": None}
    assert records[4]["parse_error"] is None
    assert manifest["status"] == "INCOMPLETE"
    assert manifest["missing_count"] == manifest["error_count"] == 1
    assert manifest["malformed_count"] == 2
    assert manifest["actual_usage"]["total_tokens"] == {"total": 64, "observed_responses": 4}
    graded = json.loads((out / "graded.json").read_text())["model_results"]
    assert graded["missing_outputs"] == 1
    assert graded["metrics"]["no_context"]["safe_abstention"] == 1
    assert graded["metrics"]["ktrf:plain:knowledge"]["malformed"] == 1
    assert graded["metrics"]["ktrf:structured:knowledge"]["observed"] == 0
    for name, digest in manifest["artifact_sha256"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    unsealed = dict(manifest)
    seal = unsealed.pop("seal_sha256")
    assert hashlib.sha256(runner._json_bytes(unsealed)).hexdigest() == seal


@pytest.mark.parametrize("text", ['Here is the result:\n```json\n{"answer":null}\n```',
                                  '```json\n{"answer":null}\n```\nAdditional prose.',
                                  '{"answer":null}\n{"answer":"other"}'])
def test_runner_rejects_prose_and_partial_json_extraction(text):
    with pytest.raises(ValueError):
        runner.parse_model_json(text)


def test_runner_unknown_model_is_missing_not_fake_abstention(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "build_requests", lambda: build_requests()[:1])
    monkeypatch.setattr(runner, "urlopen", lambda request, timeout: FakeResponse({"data": [{"id": "other"}]}))
    manifest = runner.run_benchmark(endpoint="http://localhost/v1", model="served", out_dir=tmp_path / "run",
                                    code_revision="frozen-sha")
    assert manifest["status"] == "INCOMPLETE"
    assert manifest["setup_error"]
    assert manifest["received_count"] == 0
    assert manifest["missing_count"] == 1
    assert (tmp_path / "run" / "responses.jsonl").read_bytes() == b""


def test_contract_track_uses_frozen_prompts_and_diagnostic_grader(tmp_path, monkeypatch):
    from eval.product_contract_probe import CONTRACT_PROTOCOL, build_contract_requests

    rows = build_contract_requests()
    sent = []

    def fake_urlopen(request, timeout):
        if request.full_url.endswith("/models"):
            return FakeResponse({"data": [{"id": "served"}]})
        payload = json.loads(request.data)
        sent.append(payload)
        return FakeResponse(_completion('{"answer":null,"entity_id":null}'))

    monkeypatch.setattr(runner, "urlopen", fake_urlopen)
    out = tmp_path / "contract"
    manifest = runner.run_benchmark(endpoint="http://localhost/v1", model="served",
        out_dir=out, code_revision="frozen-sha", track="contract_probe")
    assert manifest["status"] == "COMPLETE"
    assert manifest["request_count"] == manifest["received_count"] == len(sent) == 56
    assert manifest["protocol"] == "product_contract_probe_v1"
    assert manifest["declared_protocol"] == CONTRACT_PROTOCOL
    for payload, row in zip(sent, rows):
        assert payload["messages"] == [{"role": "system", "content": row["system"]},
                                       {"role": "user", "content": row["user"]}]
        assert set(payload) == {"model", "messages", "temperature", "max_tokens",
                                "seed", "chat_template_kwargs"}
    graded = json.loads((out / "graded.json").read_text())["model_results"]
    assert set(graded["metrics"]) == {"original", "surface_only", "schema_only", "both"}
    assert "contract_diagnostics" in graded and "paired_vs_original" in graded
    assert all(m["safe_abstention"] == 4 and m["over_abstention"] == 10
               for m in graded["metrics"].values())


def test_unknown_track_is_rejected_before_creating_artifacts(tmp_path):
    out = tmp_path / "unknown"
    with pytest.raises(ValueError, match="unknown experiment track"):
        runner.run_benchmark(endpoint="http://localhost/v1", model="served",
                             out_dir=out, code_revision="sha", track="unknown")
    assert not out.exists()


def test_json_object_with_invalid_id_type_is_retained_and_marked_malformed(tmp_path, monkeypatch):
    row = next(r for r in build_requests() if r["case_id"] == "missing:structured_routing"
               and r["condition"] == "no_context")
    monkeypatch.setattr(runner, "build_requests", lambda: [row])
    monkeypatch.setattr(runner, "urlopen", lambda request, timeout: FakeResponse(
        {"data": [{"id": "served"}]} if request.full_url.endswith("/models") else
        _completion('{"entity_id":[]}')))
    manifest = runner.run_benchmark(endpoint="http://localhost/v1", model="served",
        out_dir=tmp_path / "run", code_revision="frozen-sha")
    assert manifest["status"] == "COMPLETE" and manifest["malformed_count"] == 1
    row = json.loads((tmp_path / "run" / "responses.jsonl").read_text())
    assert row["status"] == "MALFORMED" and row["response"] == {"entity_id": []}
    grade = json.loads((tmp_path / "run" / "graded.json").read_text())["model_results"]
    assert grade["metrics"]["no_context"]["malformed"] == 1
    assert grade["metrics"]["no_context"]["safe_abstention"] == 0
