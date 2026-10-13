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
