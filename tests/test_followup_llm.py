"""Frozen followup matrices, payload isolation, failures and sealed regrading."""
import copy
import hashlib
import json
from urllib.error import HTTPError

import pytest

from eval import run_followup_llm as runner
from eval.hf_qa import EVIDENCE_POLICY, canonical
from eval.report_followup_llm import prepare_report, render_markdown


def envelope(experiment="stability", negative=False):
    source, question = "가상기관의 표식은 푸른색이다.", "가상기관의 표식은?"
    rows = []
    for context, mode, repeat in sorted(runner._matrix(experiment)):
        rows.append({"case_id": "authored-private-case", "condition": f"{context}__{mode}__r{repeat}",
            "experiment": experiment, "context_condition": context, "decoding_mode": mode,
            "repeat_id": repeat, "task": "document_qa", "stratum": "NO_ANSWER" if negative else "SPAN",
            "positive_gold": not negative, "expected_answers": [] if negative else ["푸른색"],
            "source_gold_visible": None if negative else True, "parent_document_id": "authored-private-parent",
            "document_sha256": hashlib.sha256(source.encode()).hexdigest(), "source_text": source,
            "question": question, "source_spans": [[0, len(source)]], "pack_injected": False,
            "system": EVIDENCE_POLICY, "user": "질문: " + question + "\n\n<source>\n" + source + "\n</source>"})
    return {"protocol": {"kind": runner.PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": experiment,
        "limitations": ["Authored diagnostic; repeats are not independent samples."]},
        "provenance": {"authored": True}, "requests": rows}


def execute(tmp_path, monkeypatch, *, data=None, completion=None):
    data = data or envelope()
    frozen = tmp_path / "frozen.json"
    frozen.write_bytes(canonical(data))
    payloads = []
    def fake_api(url, *, payload=None, timeout):
        if url.endswith("/models"):
            return {"data": [{"id": "authored-model"}]}
        payloads.append(payload)
        if completion:
            return completion(payload, len(payloads))
        return {"choices": [{"message": {"content": '{"answer":"푸른색"}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 13, "completion_tokens": 6, "total_tokens": 19}}
    monkeypatch.setattr(runner, "_request_json", fake_api)
    result = tmp_path / "result"
    manifest = runner.run_benchmark(requests_file=frozen, endpoint="http://localhost:1234/v1",
        model="authored-model", out_dir=result, code_revision="authored-revision")
    return data, result, manifest, payloads


@pytest.mark.parametrize("experiment,count", [("retrieval", 4), ("stability", 12)])
def test_payload_isolation_and_fixed_decoding(tmp_path, monkeypatch, experiment, count):
    data, result, manifest, payloads = execute(tmp_path, monkeypatch, data=envelope(experiment))
    assert manifest["status"] == "COMPLETE"
    assert manifest["request_count"] == len(payloads) == count
    for payload, row in zip(payloads, data["requests"]):
        expected = {"model", "messages", *runner.DECODING}
        if row["decoding_mode"] == "json_schema":
            expected.add("response_format")
            assert payload["response_format"] == {"type": "json_schema", "json_schema": {
                "name": "qa_answer", "strict": True, "schema": runner.ANSWER_SCHEMA}}
        assert set(payload) == expected
        assert payload["messages"] == [{"role": "system", "content": row["system"]},
                                        {"role": "user", "content": row["user"]}]
        assert all(payload[key] == value for key, value in runner.DECODING.items())
        assert "authored-private-case" not in json.dumps(payload)
    report = prepare_report(result)
    serialized = json.dumps(report, ensure_ascii=False)
    for private in ("authored-private-case", "authored-private-parent", "푸른색", '"source_text":', '"expected_answers":'):
        assert private not in serialized
    assert report["questions"] == 1
    assert all(v["positive_exact_rate"] == 1 for v in report["by_variant"].values())
    assert "not increase" in render_markdown(report)


@pytest.mark.parametrize("mutation,message", [
    (lambda e: e["protocol"].update(phase="SCREENING_POOL"), "FINAL_FROZEN"),
    (lambda e: e["requests"].pop(), "matrix"),
    (lambda e: e["requests"].append(copy.deepcopy(e["requests"][0])), "duplicate"),
    (lambda e: e["requests"][0].update(user="gold: 푸른색"), "prompt differs"),
    (lambda e: e["requests"][0].update(system="gold: 푸른색"), "prompt differs"),
    (lambda e: e["requests"][0].update(source_text="changed"), "document hash"),
    (lambda e: e["requests"][0].update(expected_answers=["다른색"]), "disagree"),
    (lambda e: e["requests"][0].update(repeat_id=True), "unknown context"),
    (lambda e: e["requests"][0].update(source_gold_visible=None), "visibility"),
    (lambda e: e["requests"][0].update(condition="anything"), "condition must"),
])
def test_preflight_rejects_before_server_or_artifacts(tmp_path, monkeypatch, mutation, message):
    data = envelope()
    mutation(data)
    frozen = tmp_path / "frozen.json"
    frozen.write_bytes(canonical(data))
    monkeypatch.setattr(runner, "_request_json", lambda *a, **k: pytest.fail("must validate before network"))
    with pytest.raises(ValueError, match=message):
        runner.run_benchmark(requests_file=frozen, endpoint="http://localhost:1234/v1",
            model="authored-model", out_dir=tmp_path / "result", code_revision="revision")
    assert not (tmp_path / "result").exists()


def test_stability_repeat_must_keep_identical_prompt(tmp_path):
    data = envelope()
    row = data["requests"][0]
    row["source_spans"] = []
    row["source_gold_visible"] = False
    row["user"] = "질문: " + row["question"] + "\n\n<source>\n\n</source>"
    with pytest.raises(ValueError, match="identical prompts"):
        runner.validate_requests(data["requests"])


@pytest.mark.parametrize("content", ['{"answer":null,"extra":1}', '{"answer":""}', '{"answer":"  "}',
                                     'null', 'prose {"answer":null}', '{"answer": false}'])
def test_malformed_never_receives_no_answer_credit(tmp_path, monkeypatch, content):
    def completion(payload, index):
        return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
    _, result, manifest, _ = execute(tmp_path, monkeypatch, data=envelope(negative=True), completion=completion)
    assert manifest["malformed_count"] == 12
    report = prepare_report(result)
    assert all(v["article_no_answer_null"] == 0 and v["malformed"] == 3 for v in report["by_variant"].values())
    assert all(v["comparable"] == 0 for v in report["paired"].values())


def test_schema_unsupported_remains_failed_without_fallback(tmp_path, monkeypatch):
    def completion(payload, index):
        if "response_format" in payload:
            raise HTTPError("http://localhost/", 400, "schema unavailable", None, None)
        return {"choices": [{"message": {"content": '{"answer":"푸른색"}'}, "finish_reason": "stop"}]}
    _, result, manifest, payloads = execute(tmp_path, monkeypatch, completion=completion)
    assert len(payloads) == 12
    assert manifest["status"] == "INCOMPLETE"
    assert manifest["error_count"] == 6
    assert manifest["missing_count"] == manifest["malformed_count"] == 0
    report = prepare_report(result)
    for variant in ("retrieved__json_schema", "ktrf_pack__json_schema"):
        assert report["by_variant"][variant]["errors"] == 3
        assert report["by_variant"][variant]["positive_exact"] == 0


def test_setup_failure_sealed_and_regradeable(tmp_path, monkeypatch):
    data = envelope()
    frozen = tmp_path / "frozen.json"
    frozen.write_bytes(canonical(data))
    monkeypatch.setattr(runner, "_request_json", lambda *a, **k: {"data": [{"id": "wrong-model"}]})
    result = tmp_path / "result"
    manifest = runner.run_benchmark(requests_file=frozen, endpoint="http://localhost/v1", model="wanted",
        out_dir=result, code_revision="revision")
    assert manifest["status"] == "INCOMPLETE" and manifest["missing_count"] == 12
    report = prepare_report(result)
    assert report["setup_failed"] is True
    assert report["counts"]["record_count"] == 0


def test_question_level_means_and_repeat_agreement():
    rows = envelope()["requests"]
    outputs = [{"case_id": r["case_id"], "condition": r["condition"], "status": "RECEIVED",
        "response": {"answer": "푸른색" if r["repeat_id"] < 2 else "붉은색"}} for r in rows]
    graded = runner.grade_outputs(rows, outputs)
    for values in graded["by_variant"].values():
        assert values["positive_exact"] == 2
        assert values["questions"] == 1
        assert values["positive_exact_rate"] == 2 / 3
    for values in graded["repeat_agreement"].values():
        assert values["fully_valid_groups"] == 1
        assert values["identical_normalized_answer_groups"] == 0
        assert values["identical_correctness_groups"] == 0
    assert all(v["per_question_mean_exact_delta"] == 0 for v in graded["paired"].values())


def reseal(result, mutate):
    manifest = json.loads((result / "run_manifest.json").read_text())
    mutate(result, manifest)
    manifest["artifact_sha256"] = {name: hashlib.sha256((result / name).read_bytes()).hexdigest() for name in runner.ARTIFACTS}
    manifest.pop("seal_sha256")
    manifest["seal_sha256"] = hashlib.sha256(canonical(manifest)).hexdigest()
    (result / "run_manifest.json").write_bytes(canonical(manifest))


def test_report_rejects_artifact_tampering(tmp_path, monkeypatch):
    _, result, _, _ = execute(tmp_path, monkeypatch)
    with (result / "responses.jsonl").open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="artifact hash"):
        prepare_report(result)


def test_report_regrades_instead_of_trusting_sealed_aggregate(tmp_path, monkeypatch):
    _, result, _, _ = execute(tmp_path, monkeypatch)
    def mutate(path, manifest):
        grades = json.loads((path / "graded.json").read_text())
        grades["by_variant"]["ktrf_pack__free"]["positive_exact"] = 99
        (path / "graded.json").write_bytes(canonical(grades))
    reseal(result, mutate)
    with pytest.raises(ValueError, match="grades differ"):
        prepare_report(result)


def test_report_checks_raw_text_against_recorded_prediction(tmp_path, monkeypatch):
    _, result, _, _ = execute(tmp_path, monkeypatch)
    def mutate(path, manifest):
        records = [json.loads(line) for line in (path / "responses.jsonl").read_text().splitlines()]
        records[0]["response"] = {"answer": "forged answer"}
        (path / "responses.jsonl").write_bytes(b"".join(canonical(r) for r in records))
    reseal(result, mutate)
    with pytest.raises(ValueError, match="parsed response differs"):
        prepare_report(result)


def test_gold_variants_do_not_leak_through_payload_schema(tmp_path, monkeypatch):
    data = envelope()
    for row in data["requests"]:
        row["expected_answers"] = ["held-private-gold"]
        row["annotation_secret"] = "held-private-annotation"
    _, _, _, payloads = execute(tmp_path, monkeypatch, data=data)
    serialized = json.dumps(payloads)
    assert "held-private-gold" not in serialized
    assert "held-private-annotation" not in serialized


def test_unexpected_api_finish_reason_is_not_published_verbatim(tmp_path, monkeypatch):
    def completion(payload, index):
        return {"choices": [{"message": {"content": '{"answer":"푸른색"}'},
                             "finish_reason": "private untrusted source field"}]}
    _, result, _, _ = execute(tmp_path, monkeypatch, completion=completion)
    report = prepare_report(result)
    assert "private untrusted source field" not in json.dumps(report)
    assert all(v["finish_reason_counts"] == {"other": 3} for v in report["by_variant"].values())
