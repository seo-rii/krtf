"""Matched source interventions, frozen preparation and strict combined payloads."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from eval import prepare_combined_followup as prepare
from eval import run_followup_llm as runner
from eval.collect_hf_qa_queue import validate_public_json
from eval.hf_qa import EVIDENCE_POLICY, canonical
from eval.report_followup_llm import prepare_report


def parent_rows(kinds=("SPAN", "NO_ANSWER")):
    result = []
    for index, kind in enumerate(kinds):
        text = f"표식은 푸른색이다. {index}\n다른 문단은 붉은색이다."
        cut = text.index("\n")
        answer_start = text.index("푸른색")
        for context in runner.CONTEXTS["retrieval"]:
            spans = [[cut + 1, len(text)]] if context == "bm25" else [[0, cut]]
            source = "\n\n".join(text[start:end] for start, end in spans)
            result.append({"case_id": f"private-case-{index}", "condition": context + "__free__r0",
                "experiment": "retrieval", "context_condition": context, "decoding_mode": "free", "repeat_id": 0,
                "task": "document_qa", "parent_document_id": f"private-parent-{index}",
                "document_sha256": hashlib.sha256(text.encode()).hexdigest(), "source_text": text,
                "question": f"표식은 무엇인가요? {index}", "source_spans": spans, "stratum": kind,
                "positive_gold": kind != "NO_ANSWER",
                "expected_answers": [] if kind == "NO_ANSWER" else ["YES"] if kind == "YES_NO" else ["푸른색"],
                "answer_spans": [[answer_start, answer_start + 3]] if kind == "SPAN" else [],
                "answer_passage_spans": [[0, cut]] if kind != "NO_ANSWER" else [],
                "source_gold_visible": None if kind == "NO_ANSWER" else context != "bm25",
                "pack_injected": False, "system": EVIDENCE_POLICY,
                "user": "질문: " + f"표식은 무엇인가요? {index}" + "\n\n<source>\n" + source + "\n</source>"})
    return runner.validate_requests(result, "retrieval")


@pytest.fixture
def pack_calls(monkeypatch):
    calls = []
    def fake(snapshot, text, *, query, mode, context_policy):
        assert mode == "commit" and context_policy.max_tokens == 800
        calls.append((text, query))
        injected = "붉은색" in text
        return SimpleNamespace(should_inject=injected, context_pack={"source": text},
            prompt_fragment="고정 보조 용어", policy_fragment="고정 용어 정책")
    monkeypatch.setattr(prepare, "prepare_llm_context", fake)
    return calls


def test_rebuilds_pack_from_each_ranker_source_and_preserves_all_questions(pack_calls):
    parents = parent_rows()
    rows = prepare.build_combined(parents, object(), expected_questions=2)
    assert len(rows) == 24 and len(pack_calls) == 4
    assert any("붉은색" in text for text, _ in pack_calls)
    assert any("푸른색" in text and "붉은색" not in text for text, _ in pack_calls)
    original = {(r["case_id"], r["context_condition"]): r for r in parents}
    for row in rows:
        assert row["decoding_mode"] == "json_schema" and row["repeat_id"] in range(3)
        context = row["context_condition"]
        parent = original[(row["case_id"].removesuffix("::combined"), context.removesuffix("_pack"))]
        for field in ("source_spans", "source_gold_visible", "source_text", "expected_answers"):
            assert row[field] == parent[field]
        assert row["pack_injected"] == (context == "bm25_pack")
        assert row["independent_validation"] is False
        if not row["pack_injected"]:
            assert (row["system"], row["user"]) == (parent["system"], parent["user"])


def test_rejects_pack_from_different_source_even_when_prompt_is_consistent(pack_calls):
    rows = prepare.build_combined(parent_rows(), object(), expected_questions=2)
    for row in rows:
        if row["context_condition"] == "bm25_pack":
            row["source_spans"] = [[0, row["source_text"].index("\n")]]
            row["source_gold_visible"] = row["positive_gold"] or None
            source = row["source_text"][slice(*row["source_spans"][0])]
            row["user"] = "질문: " + row["question"] + "\n\n<source>\n" + source + "\n</source>\n\n<terminology>\n" + row["pack_prompt"] + "\n</terminology>"
    with pytest.raises(ValueError, match="matched ranker source"):
        runner.validate_requests(rows, "combined")


def test_schema_payloads_and_sealed_regrading_with_repeat_metrics(tmp_path, monkeypatch, pack_calls):
    rows = prepare.build_combined(parent_rows(), object(), expected_questions=2)
    envelope = {"protocol": {"kind": runner.PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": "combined",
        "limitations": ["Reused adaptive diagnostic; repeats are not independent."]},
        "provenance": {"authored": True}, "requests": rows}
    frozen = tmp_path / "frozen.json"
    frozen.write_bytes(canonical(envelope))
    payloads = []
    def api(url, *, payload=None, timeout):
        if url.endswith("/models"):
            return {"data": [{"id": "authored-model"}]}
        payloads.append(payload)
        return {"choices": [{"message": {"content": '{"answer": "푸른색"}'}, "finish_reason": "stop"}]}
    monkeypatch.setattr(runner, "_request_json", api)
    out = tmp_path / "out"
    manifest = runner.run_benchmark(requests_file=frozen, endpoint="http://localhost/v1", model="authored-model",
        out_dir=out, code_revision="authored-revision")
    assert manifest["status"] == "COMPLETE" and len(payloads) == 24
    for payload in payloads:
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert payload["response_format"]["json_schema"]["schema"] == runner.ANSWER_SCHEMA
        assert set(payload) == {"model", "messages", "response_format", *runner.DECODING}
        assert "private-case" not in json.dumps(payload)
    summary = prepare_report(out)
    assert len(summary["paired"]) == 5
    assert summary["questions"] == 2
    for context, value in summary["by_variant"].items():
        assert value["questions"] == 2
        assert value["pack_injected_questions"] == (2 if context.startswith("bm25_pack") else 0)
    assert all(value["repeat_count"] == 3 for value in summary["repeat_agreement"].values())
    validate_public_json(summary)


class Tokenizer:
    def encode(self, text, **kwargs):
        return list(range(len(text)))

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs["enable_thinking"] is False
        return list(range(sum(len(message["content"]) for message in messages) + 10))


def test_preparation_binds_previous_envelope_and_actual_tokenizers(tmp_path, monkeypatch, pack_calls):
    rows = parent_rows(("SPAN",) * 40 + ("YES_NO",) * 8 + ("NO_ANSWER",) * 80)
    envelope = {"protocol": {"kind": runner.PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": "retrieval",
        "limitations": ["Authored prior diagnostic."]},
        "provenance": {"code_revision": "parent-revision", "source": {"dataset": "authored"}}, "requests": rows}
    parent = tmp_path / "parent.json"
    parent.write_bytes(canonical(envelope))
    parent_hash = hashlib.sha256(parent.read_bytes()).hexdigest()
    prior = tmp_path / "prior_manifest.json"
    prior.write_bytes(canonical({"phase": "FINAL_FROZEN", "experiments": {"retrieval": {
        "request_count": len(rows), "requests_sha256": hashlib.sha256(b"".join(canonical(r) for r in rows)).hexdigest(),
        "envelope_sha256": parent_hash}}}))
    monkeypatch.setattr(prepare, "load_glossary", lambda path: object())
    monkeypatch.setattr(prepare, "compile_snapshot", lambda glossary: SimpleNamespace(snapshot_id="authored-snapshot"))
    glossary = tmp_path / "glossary.yaml"
    glossary.write_text("authored glossary")
    models = {key: {"path": "/models/" + key} for key in ("gemma12b", "qwen27b")}
    args = dict(code_revision="current-revision", parent_envelope_sha256=parent_hash,
        glossary_file=glossary, tokenizers={key: Tokenizer() for key in models})
    manifest = prepare.prepare(parent, prior, models, tmp_path / "prepared", **args)
    assert manifest["total_planned_model_calls"] == 3072
    experiment = manifest["experiments"]["combined"]
    assert experiment["strata"] == {"SPAN": 40, "YES_NO": 8, "NO_ANSWER": 80}
    assert experiment["pack_injected_questions_by_ranker"] == {"lexical": 0, "bm25": 128}
    assert all(value["max_source_tokens"] <= 1536 for value in experiment["models"].values())
    validate_public_json(manifest)
    public = json.dumps(manifest, ensure_ascii=False)
    assert "푸른색" not in public and "private-case" not in public and "expected_answers" not in public
    frozen = tmp_path / "prepared/combined.json"
    assert hashlib.sha256(frozen.read_bytes()).hexdigest() == experiment["envelope_sha256"]
    with pytest.raises(ValueError, match="pinned prior queue"):
        prepare.prepare(parent, prior, models, tmp_path / "bad", **{**args, "parent_envelope_sha256": "0" * 64})
    assert not (tmp_path / "bad").exists()


def test_combined_rejects_partial_matrix_and_free_decoding(pack_calls):
    rows = prepare.build_combined(parent_rows(), object(), expected_questions=2)
    with pytest.raises(ValueError, match="matrix"):
        runner.validate_requests(rows[:-1], "combined")
    changed = deepcopy(rows)
    changed[0]["decoding_mode"] = "free"
    with pytest.raises(ValueError, match="unknown context"):
        runner.validate_requests(changed, "combined")
