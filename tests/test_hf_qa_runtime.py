"""Private generation runner/report and token-screening integration contracts."""
import copy
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

from eval.hf_qa import CONDITIONS, LIMITATIONS, PROTOCOL_ID, build_question_requests, canonical
from eval.prepare_hf_qa import screen_and_freeze
from eval import run_product_llm
from eval.report_hf_qa import prepare_report, render_markdown
from ktrf import compile_snapshot, load_glossary


@pytest.fixture
def frozen_envelope():
    glossary = load_glossary({"glossary_id": "authored", "version": "1", "schema_version": "3",
        "entities": [{"entity_id": "E", "canonical": "가상기관"}],
        "alias_families": [{"family_id": "F", "representative": "가상기관"}],
        "alias_bindings": [{"alias_id": "A", "family_id": "F", "entity_id": "E", "surface": "가상기관"}]})
    text = "가상기관은 푸른 표식을 사용한다."
    record = {"document_id": "authored", "parent_document_id": "article-authored", "text": text,
        "document_sha256": hashlib.sha256(text.encode()).hexdigest(), "question": "가상기관은 어떤 표식을 쓰나?",
        "annotation_answers": [{"answer_type": "SPAN", "answer_span": [6, 8]}] * 3,
        "answer_spans": [[6, 8]], "answer_passage_spans": [[0, len(text)]],
        "passage_candidates": [[0, len(text)]], "minimal_answer_evaluable": True}
    return {"protocol": {"kind": PROTOCOL_ID, "phase": "FINAL_FROZEN", "conditions": list(CONDITIONS),
                         "limitations": LIMITATIONS},
            "provenance": {"authored": True},
            "requests": build_question_requests(record, compile_snapshot(glossary))}


def test_runner_and_private_regrading_publish_no_source(tmp_path, monkeypatch, frozen_envelope):
    path = tmp_path / "frozen.json"
    path.write_bytes(canonical(frozen_envelope))
    seen = []
    def fake_api(url, *, payload=None, timeout):
        if url.endswith("/models"):
            return {"data": [{"id": "authored-model"}]}
        seen.append(payload)
        return {"choices": [{"message": {"content": '{"answer":"푸른"}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}}
    monkeypatch.setattr(run_product_llm, "_request_json", fake_api)
    out = tmp_path / "result"
    manifest = run_product_llm.run_benchmark(endpoint="http://localhost:1234/v1", model="authored-model",
        out_dir=out, code_revision="authored-revision", track="hf_qa", requests_file=path)
    assert manifest["status"] == "COMPLETE"
    assert manifest["request_count"] == len(CONDITIONS)
    assert len(seen) == len(CONDITIONS)
    assert all(set(call) == {"model", "messages", "temperature", "max_tokens", "chat_template_kwargs", "seed"}
               for call in seen)
    summary = prepare_report(out)
    assert summary["counts"]["missing_count"] == 0
    from eval.collect_hf_qa_queue import validate_public_json
    assert validate_public_json(summary) is summary
    assert frozen_envelope["requests"][0]["question"] not in json.dumps(summary, ensure_ascii=False)
    assert "none_knowledge" in render_markdown(summary)
    (out / "responses.jsonl").write_text((out / "responses.jsonl").read_text() + "\n")
    with pytest.raises(ValueError, match="artifact hash"):
        prepare_report(out)


def test_screening_uses_both_templates_and_refuses_overflow(tmp_path, monkeypatch, frozen_envelope):
    import eval.prepare_hf_qa as prepare
    monkeypatch.setattr(prepare, "QUOTAS", {"SPAN": 1, "YES_NO": 0, "NO_ANSWER": 0})
    pool = copy.deepcopy(frozen_envelope)
    pool["protocol"]["phase"] = "SCREENING_POOL"
    path = tmp_path / "pool.json"
    path.write_bytes(canonical(pool))
    calls = []
    class Tokenizer:
        def apply_chat_template(self, messages, **options):
            calls.append((messages, options))
            return [1] * 20
    fake = SimpleNamespace(AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **k: Tokenizer()))
    monkeypatch.setitem(sys.modules, "transformers", fake)
    out = tmp_path / "screened"
    result = screen_and_freeze(path, {"gemma12b": {"path": "one"}, "qwen27b": {"path": "two"}},
                               out, code_revision="frozen-code")
    assert len(calls) == len(CONDITIONS) * 2
    assert result["request_count"] == len(CONDITIONS)
    final = json.loads((out / "questions.json").read_text())
    assert final["protocol"]["phase"] == "FINAL_FROZEN"
    assert canonical(final["requests"]) == canonical(pool["requests"])
    assert all(options["enable_thinking"] is False for _, options in calls)

    class TooLong(Tokenizer):
        def apply_chat_template(self, messages, **options):
            return [1] * 8065
    fake.AutoTokenizer.from_pretrained = lambda *a, **k: TooLong()
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA"):
        screen_and_freeze(path, {"gemma12b": {"path": "one"}, "qwen27b": {"path": "two"}},
                          tmp_path / "overflow", code_revision="frozen-code")
    assert (tmp_path / "overflow/screening.json").exists()
    assert not (tmp_path / "overflow/questions.json").exists()


def test_hf_runner_requires_final_frozen_request_file(tmp_path):
    with pytest.raises(ValueError, match="frozen"):
        run_product_llm.run_benchmark(endpoint="http://localhost:1234/v1", model="model",
                                     out_dir=tmp_path / "unused", code_revision="revision", track="hf_qa")
