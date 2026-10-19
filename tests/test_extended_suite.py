"""Frozen extended matrices, local payload isolation, guard identity and regrading."""
from copy import deepcopy
import hashlib
import json
from urllib.error import HTTPError

import pytest

from eval import run_extended_suite as runner
from eval.hf_qa import EVIDENCE_POLICY, canonical
from eval.report_extended_suite import prepare_report, render_markdown


def envelope(*, negative=False, experiment="transfer"):
    source = "가상기관의 표식은 푸른색이다."
    rows = [{"case_id": "private-case", "condition": condition, "repeat_id": 0,
        "task": "document_qa", "stratum": "NO_ANSWER" if negative else "SPAN",
        "positive_gold": not negative, "expected_answers": [] if negative else ["푸른색"],
        "parent_document_id": "private-parent", "source_text": source,
        "document_sha256": hashlib.sha256(source.encode()).hexdigest(), "question": "표식은?",
        "source_gold_visible": None if negative else True, "pack_injected": False,
        "system": EVIDENCE_POLICY, "user": "질문: 표식은?\n\n" + source}
        for condition in ("lexical", "bm25")]
    return {"protocol": {"kind": runner.PROTOCOL_ID, "phase": "FINAL_FROZEN",
        "experiment": experiment, "conditions": ["lexical", "bm25"], "repeat_count": 1,
        "limitations": ["Authored diagnostic; shared documents are not independent samples."]},
        "provenance": {"code_revision": "authored-revision", "source": "authored"}, "requests": rows}


def execute(tmp_path, monkeypatch, *, data=None, completion=None):
    data = data or envelope()
    frozen = tmp_path / "frozen.json"
    frozen.write_bytes(canonical(data))
    payloads = []

    def api(url, *, payload=None, timeout):
        if url.endswith("/models"):
            return {"data": [{"id": "authored-model"}]}
        payloads.append(payload)
        if completion is not None:
            return completion(payload, len(payloads))
        return {"choices": [{"message": {"content": '{"answer":"푸른색"}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16}}

    monkeypatch.setattr(runner, "_request_json", api)
    result = tmp_path / "result"
    manifest = runner.run_benchmark(requests_file=frozen, endpoint="http://127.0.0.1:1234/v1",
        model="authored-model", out_dir=result, code_revision="authored-revision")
    return data, result, manifest, payloads


@pytest.mark.parametrize("experiment", ["transfer", "budget", "corpus", "pack"])
def test_payload_schema_isolation_and_aggregate_only_report(tmp_path, monkeypatch, experiment):
    data = envelope(experiment=experiment)
    for row in data["requests"]:
        row["private_annotation"] = "never-sent-private-annotation"
    data, result, manifest, payloads = execute(tmp_path, monkeypatch, data=data)
    assert manifest["status"] == "COMPLETE" and manifest["request_count"] == len(payloads) == 2
    for row, payload in zip(data["requests"], payloads):
        assert set(payload) == {"model", "messages", "response_format", *runner.DECODING}
        assert payload["messages"] == [{"role": "system", "content": row["system"]},
                                        {"role": "user", "content": row["user"]}]
        assert payload["response_format"] == {"type": "json_schema", "json_schema": {
            "name": "qa_answer", "strict": True, "schema": runner.ANSWER_SCHEMA}}
        assert all(payload[key] == value for key, value in runner.DECODING.items())
        assert "never-sent-private-annotation" not in json.dumps(payload)
    summary = prepare_report(result)
    serialized = json.dumps(summary, ensure_ascii=False)
    for private in ("private-case", "private-parent", "푸른색", '"source_text":', '"expected_answers":'):
        assert private not in serialized
    assert summary["questions"] == summary["parent_documents"] == 1
    assert all(value["positive_exact_rate"] == 1 for value in summary["by_variant"].values())
    assert all(value["article_no_answer_null_rate"] is None for value in summary["by_variant"].values())
    assert all(value["usage"]["prompt_tokens"] == 11 for value in summary["by_variant"].values())
    assert "do not increase" in render_markdown(summary)


@pytest.mark.parametrize("mutation,message", [
    (lambda e: e["protocol"].update(phase="PREPARATION"), "FINAL_FROZEN"),
    (lambda e: e["protocol"].update(repeat_count=True), "repeat_count"),
    (lambda e: e["protocol"].update(conditions=["lexical", "lexical"]), "condition"),
    (lambda e: e["protocol"].update(comparisons=[["lexical", "unknown"]]), "comparisons"),
    (lambda e: e["protocol"].update(limitations=[]), "limitations"),
    (lambda e: e["requests"].pop(), "matrix"),
    (lambda e: e["requests"].append(deepcopy(e["requests"][0])), "duplicate"),
    (lambda e: e["requests"][0].update(source_text="changed"), "document hash"),
    (lambda e: e["requests"][0].update(expected_answers=["different"]), "disagree"),
    (lambda e: e["requests"][0].update(repeat_id=True), "repeat_id"),
    (lambda e: e["requests"][0].update(pack_injected="true"), "injection"),
    (lambda e: e["requests"][0].update(source_gold_visible="true"), "visibility"),
    (lambda e: e["requests"][0].update(task="other"), "tasks"),
    (lambda e: e["requests"][0].update(task="structured_routing"), "tasks"),
    (lambda e: e["provenance"].pop("code_revision"), "provenance"),
])
def test_invalid_freeze_rejected_before_artifacts_or_network(tmp_path, monkeypatch, mutation, message):
    data = envelope()
    mutation(data)
    frozen = tmp_path / "frozen.json"
    frozen.write_bytes(canonical(data))
    monkeypatch.setattr(runner, "_request_json", lambda *a, **k: pytest.fail("network must not be reached"))
    with pytest.raises(ValueError, match=message):
        runner.run_benchmark(requests_file=frozen, endpoint="http://localhost/v1", model="model",
            out_dir=tmp_path / "result", code_revision="revision")
    assert not (tmp_path / "result").exists()


def test_corpus_prompt_can_contain_multiple_documents(tmp_path, monkeypatch):
    data = envelope(experiment="corpus")
    data["requests"][1]["user"] += "\n다른 검색 문서의 내용."
    _, result, _, _ = execute(tmp_path, monkeypatch, data=data)
    assert prepare_report(result)["paired"]["lexical_to_bm25"]["identical_prompt_pairs"] == 0


@pytest.mark.parametrize("endpoint", ["http://example.com/v1", "http://10.0.0.1/v1", "http://localhost@evil.test/v1",
                                     "http://localhost/v1?secret=x", "http://localhost:bad/v1"])
def test_private_data_only_sent_to_loopback(tmp_path, monkeypatch, endpoint):
    frozen = tmp_path / "frozen.json"
    frozen.write_bytes(canonical(envelope()))
    monkeypatch.setattr(runner, "_request_json", lambda *a, **k: pytest.fail("network must not be reached"))
    with pytest.raises(ValueError, match="loopback"):
        runner.run_benchmark(requests_file=frozen, endpoint=endpoint, model="model",
            out_dir=tmp_path / "result", code_revision="revision")
    assert not (tmp_path / "result").exists()


@pytest.mark.parametrize("content", ['{"answer":null,"extra":1}', '{"answer":""}', '{"answer":"  "}',
                                     'null', 'prose {"answer":null}', '{"answer":false}'])
def test_malformed_never_receives_no_answer_credit(tmp_path, monkeypatch, content):
    def completion(payload, index):
        return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
    _, result, manifest, _ = execute(tmp_path, monkeypatch, data=envelope(negative=True), completion=completion)
    assert manifest["malformed_count"] == 2
    summary = prepare_report(result)
    assert all(value["article_no_answer_null"] == 0 and value["malformed"] == 1
               for value in summary["by_variant"].values())
    assert summary["paired"]["lexical_to_bm25"]["comparable"] == 0


def test_schema_failure_kept_without_retries_or_null_credit(tmp_path, monkeypatch):
    def completion(payload, index):
        raise HTTPError("http://localhost/", 400, "unsupported schema", None, None)
    _, result, manifest, payloads = execute(tmp_path, monkeypatch, data=envelope(negative=True), completion=completion)
    assert len(payloads) == 2 and manifest["status"] == "INCOMPLETE" and manifest["error_count"] == 2
    assert all(value["article_no_answer_null"] == 0 for value in prepare_report(result)["by_variant"].values())


def test_setup_failure_missing_is_not_abstention(tmp_path, monkeypatch):
    frozen = tmp_path / "frozen.json"
    frozen.write_bytes(canonical(envelope(negative=True)))
    monkeypatch.setattr(runner, "_request_json", lambda *a, **k: {"data": []})
    result = tmp_path / "result"
    manifest = runner.run_benchmark(requests_file=frozen, endpoint="http://localhost/v1", model="model",
        out_dir=result, code_revision="revision")
    assert manifest["status"] == "INCOMPLETE" and manifest["missing_count"] == 2
    summary = prepare_report(result)
    assert summary["setup_failed"] and summary["counts"]["record_count"] == 0
    assert all(value["article_no_answer_null"] == 0 for value in summary["by_variant"].values())


def test_declared_paired_comparisons_count_helpful_and_harmful():
    data = envelope()
    second = deepcopy(data["requests"])
    for row in second:
        row["case_id"] = "another-private-case"
    data["requests"].extend(second)
    data["protocol"]["comparisons"] = [["bm25", "lexical"]]
    outputs = [{"case_id": row["case_id"], "condition": row["condition"], "status": "RECEIVED",
        "response": {"answer": "푸른색" if (row["condition"] == "lexical") == (row["case_id"] == "private-case") else "wrong"}}
        for row in data["requests"]]
    paired = runner.grade_outputs(data["requests"], outputs, data["protocol"])["paired"]
    assert set(paired) == {"bm25_to_lexical"}
    assert paired["bm25_to_lexical"]["helpful"] == paired["bm25_to_lexical"]["harmful"] == 1


def reseal(result, mutate):
    manifest = json.loads((result / "run_manifest.json").read_text())
    mutate(result, manifest)
    manifest["artifact_sha256"] = {name: hashlib.sha256((result / name).read_bytes()).hexdigest() for name in runner.ARTIFACTS}
    manifest.pop("seal_sha256")
    manifest["seal_sha256"] = hashlib.sha256(canonical(manifest)).hexdigest()
    (result / "run_manifest.json").write_bytes(canonical(manifest))


def test_unsealed_artifact_tampering_rejected(tmp_path, monkeypatch):
    _, result, _, _ = execute(tmp_path, monkeypatch)
    with (result / "responses.jsonl").open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="artifact hash"):
        prepare_report(result)


def test_sealed_aggregate_recomputed_from_responses(tmp_path, monkeypatch):
    _, result, _, _ = execute(tmp_path, monkeypatch)

    def mutate(path, manifest):
        grades = json.loads((path / "graded.json").read_text())
        grades["by_variant"]["lexical"]["positive_exact"] = 99
        (path / "graded.json").write_bytes(canonical(grades))

    reseal(result, mutate)
    with pytest.raises(ValueError, match="grades differ"):
        prepare_report(result)


@pytest.mark.parametrize("field,value,message", [("response", {"answer": "forged"}, "parsed response differs"),
    ("raw_text", '{"answer":"forged"}', "raw model content"),
    ("usage", {"prompt_tokens": 1000}, "raw usage"), ("finish_reason", "forged", "finish reason")])
def test_reparse_raw_and_metadata_after_resealing(tmp_path, monkeypatch, field, value, message):
    _, result, _, _ = execute(tmp_path, monkeypatch)

    def mutate(path, manifest):
        records = [json.loads(line) for line in (path / "responses.jsonl").read_text().splitlines()]
        records[0][field] = value
        (path / "responses.jsonl").write_bytes(b"".join(canonical(record) for record in records))

    reseal(result, mutate)
    with pytest.raises(ValueError, match=message):
        prepare_report(result)


def test_unknown_api_finish_reason_is_not_published(tmp_path, monkeypatch):
    def completion(payload, index):
        return {"choices": [{"message": {"content": '{"answer":"푸른색"}'},
                             "finish_reason": "private untrusted finish reason"}]}
    _, result, _, _ = execute(tmp_path, monkeypatch, completion=completion)
    report = prepare_report(result)
    assert "private untrusted finish reason" not in json.dumps(report)
    assert all(value["finish_reason_counts"] == {"other": 1} for value in report["by_variant"].values())


@pytest.fixture
def routing_envelope():
    from eval.production_grounding import build_document_requests
    from eval.synthetic_grounding import _snapshot, _target_span
    from eval.synthetic_grounding_v2 import load_balanced_families

    family = load_balanced_families()[0]
    case = next(case for case in family["cases"] if case["gold"]["label"] == "LINK")
    rows = build_document_requests(_snapshot(family, case["world"]), document_id=case["case_id"],
        family_id=family["family_id"], domain=family["domain"], stratum=case["stratum"], text=case["text"],
        target_surface=case["target_surface"], target_span=_target_span(case), gold=case["gold"],
        expected_answer="private source definition", provenance={"source": "authored test"})
    row = next(row for row in rows if row["task"] == "structured_routing")
    row["repeat_id"] = 0
    data = envelope(experiment="semantic_safety")
    data["protocol"]["conditions"] = ["production"]
    data["requests"] = [row]
    return data


def test_full_malformed_response_reaches_safety_grader(routing_envelope, monkeypatch):
    from eval import extended_safety
    row = routing_envelope["requests"][0]
    response = {"selections": [{"surface": row["target_surface"], "entity_id": row["expected_entity_id"]}],
                "answer": "extra QA field"}
    seen = []
    original = extended_safety.grade_safety

    def observe(request, complete_response):
        seen.append(complete_response)
        return original(request, complete_response)

    monkeypatch.setattr(extended_safety, "grade_safety", observe)
    graded = runner.grade_outputs([row], [{"case_id": row["case_id"], "condition": "production",
        "status": "RECEIVED", "response": response}], routing_envelope["protocol"])
    assert len(seen) == 1 and seen[0] is response
    assert graded["by_variant"]["production"]["malformed"] == 1
    assert graded["by_variant"]["production"]["correct"] == 0
    assert graded["by_variant"]["production"]["attempted_nonnull"] == 1


@pytest.mark.parametrize("approved", [True, False])
def test_accepted_and_rejected_wrong_ids_are_distinct(routing_envelope, approved):
    row = routing_envelope["requests"][0]
    selected = row["resolver_authorized_entity_id"] if approved else "unapproved-id"
    assert selected is not None
    row.update(expected_entity_id=None, expected_answer=None, gold={"label": "NIL", "entity_ref": None})
    response = {"selections": [{"surface": row["target_surface"], "entity_id": selected}]}
    graded = runner.grade_outputs([row], [{"case_id": row["case_id"], "condition": "production",
        "status": "RECEIVED", "response": response}], routing_envelope["protocol"])
    values = graded["by_variant"]["production"]
    assert values["accepted_wrong_id"] == int(approved)
    assert values["rejected_wrong_id"] == int(not approved)
    assert values["accepted_wrong_id_rate"] == float(approved)
    assert values["accepted_wrong_id_rate_among_accepted"] == (1.0 if approved else None)
    assert values["over_abstention_rate"] is None
    assert values["correct"] == values["correct_abstention"] == 0


def test_routing_schema_and_private_sealed_regrading(tmp_path, monkeypatch, routing_envelope):
    row = routing_envelope["requests"][0]

    def completion(payload, index):
        return {"choices": [{"message": {"content": json.dumps({"selections": [
            {"surface": row["target_surface"], "entity_id": None}]})}, "finish_reason": "stop"}]}

    _, result, manifest, payloads = execute(tmp_path, monkeypatch, data=routing_envelope, completion=completion)
    assert manifest["answer_schema"] == runner.ROUTING_SCHEMA
    assert payloads[0]["response_format"]["json_schema"]["schema"] == runner.ROUTING_SCHEMA
    summary = prepare_report(result)
    assert summary["by_variant"]["production"]["over_abstention"] == 1
    assert summary["by_variant"]["production"]["over_abstention_rate"] == 1
    assert summary["by_variant"]["production"]["accepted_wrong_id"] == 0
    assert row["case_id"] not in json.dumps(summary)
    assert "Accepted wrong ID" in render_markdown(summary)
