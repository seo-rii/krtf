"""No-download authored fixtures for frozen actual-template follow-up plans."""
from copy import deepcopy
from collections import Counter
import hashlib
import json

import pytest

from eval import hf_qa
from eval import prepare_followup as prepare
from eval.hf_retrieval_followup import build_variants
from eval.run_followup_llm import validate_requests


def _record(identifier, kind="SPAN"):
    paragraphs = ["목표 답안은 사과나무다.", "바다와 계곡에 관한 배경이다. " + identifier]
    text = "\n".join(paragraphs)
    start = text.index("사과나무")
    spans = [[0, len(paragraphs[0])], [len(paragraphs[0]) + 1, len(text)]]
    null = {"answer_type": "NO_ANSWER", "answer_span": None, "passage_index": -1,
            "yes_no_answer": "NONE"}
    positive = {"answer_type": kind, "answer_span": [start, start + 4] if kind == "SPAN" else None,
                "passage_index": 0, "yes_no_answer": "YES" if kind == "YES_NO" else "NONE"}
    return {"document_id": identifier, "parent_document_id": "article:" + identifier,
        "text": text, "document_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "question": "목표 답안은 무엇인가요?", "minimal_answer_evaluable": True,
        "annotation_answers": [deepcopy(null) for _ in range(3)] if kind == "NO_ANSWER"
                              else [deepcopy(positive), deepcopy(positive), null],
        "passage_candidates": spans, "answer_spans": [[start, start + 4]] if kind == "SPAN" else [],
        "answer_passage_spans": [spans[0]] if kind != "NO_ANSWER" else []}


def _old_rows(record):
    base = build_variants(record)[0]
    rows = []
    for condition in hf_qa.CONDITIONS:
        row = deepcopy(base)
        row.update(case_id=record["document_id"] + "::generation", condition=condition)
        if condition.startswith("none_"):
            row["source_spans"] = []
        elif condition == "full":
            row["source_spans"] = [[0, len(record["text"])]]
        source = "\n\n".join(record["text"][s:e] for s, e in row["source_spans"])
        row["source_gold_visible"] = bool(row["source_spans"]) if row["positive_gold"] else None
        row["system"] = hf_qa.KNOWLEDGE_POLICY if condition == "none_knowledge" else hf_qa.EVIDENCE_POLICY
        row["user"] = "질문: " + row["question"] + "\n\n<source>\n" + source + "\n</source>"
        if condition == "ktrf_pack":
            row.update(pack_injected=True, pack_policy="저장된 용어 정책", pack_prompt="저장된 용어 자료")
            row["system"] += "\n\n" + row["pack_policy"]
            row["user"] += "\n\n<terminology>\n" + row["pack_prompt"] + "\n</terminology>"
        rows.append(row)
    return hf_qa.validate_requests(rows)


class Tokenizer:
    def __init__(self, divisor=2, prompt_overhead=17):
        self.divisor, self.prompt_overhead = divisor, prompt_overhead
        self.encoded, self.templates = [], []

    def encode(self, text, *, add_special_tokens):
        assert add_special_tokens is False
        self.encoded.append(text)
        return list(range(len(text) // self.divisor))

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {"tokenize": True, "add_generation_prompt": True,
            "enable_thinking": False, "return_dict": False}
        self.templates.append(deepcopy(messages))
        return list(range(sum(len(message["content"]) for message in messages) // self.divisor
                          + self.prompt_overhead))


@pytest.fixture
def prepared_inputs():
    old_records = [_record("old-span"), _record("old-null", "NO_ANSWER")]
    pool_extra = [_record("pool-span"), _record("pool-yes", "YES_NO")]
    prior_records = [_record("prior-evidence-span"), _record("prior-evidence-yes", "YES_NO")]
    blind = _record("blind-article")
    fresh = [_record(f"new-{kind}-{index}", kind) for kind in hf_qa.QUOTAS for index in range(4)]
    old = {"protocol": {"phase": "FINAL_FROZEN"},
           "requests": [row for source in old_records for row in _old_rows(source)]}
    pool = {"protocol": {"phase": "SCREENING_POOL"},
        "requests": [row for source in old_records + pool_extra for row in _old_rows(source)],
        "prior_evidence_question_ids": [row["document_id"] for row in prior_records]}
    blind_rows = [{"parent_document_id": blind["parent_document_id"],
        "source_document_id": blind["document_id"], "source_document_sha256": blind["document_sha256"],
        "text": "부분 문단", "document_sha256": hashlib.sha256("부분 문단".encode()).hexdigest()}]
    return dict(records=old_records + pool_extra + prior_records + [blind] + fresh,
        old=old, pool=pool, blind_rows=blind_rows,
        tokenizers={"gemma12b": Tokenizer(2), "qwen27b": Tokenizer(3)},
        models={"gemma12b": {"path": "/models/gemma"}, "qwen27b": {"path": "/models/qwen"}},
        code_revision="authored-revision", source_identity={"dataset": "authored", "sha256": "a" * 64},
        input_hashes={"old_requests": "b" * 64, "prior_pool": "c" * 64, "blind_documents": "d" * 64},
        retrieval_quotas={"SPAN": 2, "YES_NO": 1, "NO_ANSWER": 2}, expected_old_questions=2)


def test_prepare_seals_complete_independent_matrices_and_actual_token_proofs(prepared_inputs):
    envelopes, diagnostics, manifest = prepare.prepare_from_records(**prepared_inputs)
    assert set(envelopes) == {"retrieval", "stability"}
    assert manifest["total_requests_per_model"] == 20 + 24
    assert manifest["total_planned_model_calls"] == 88
    assert manifest["source_token_cap_per_model_retrieval_only"] == 1536
    for name, expected in (("retrieval", 20), ("stability", 24)):
        envelope = envelopes[name]
        rows = validate_requests(envelope["requests"], name)
        assert len(rows) == expected
        assert envelope["protocol"]["kind"] == "hf_followup_v1"
        assert envelope["protocol"]["phase"] == "FINAL_FROZEN"
        assert envelope["protocol"]["independent_from_prior_declared_articles"] == (name == "retrieval")
        assert envelope["protocol"]["source_only_token_cap_per_model"] == (1536 if name == "retrieval" else None)
        proof = manifest["experiments"][name]
        assert proof["envelope_sha256"] == hashlib.sha256(hf_qa.canonical(envelope)).hexdigest()
        assert proof["requests_sha256"] == hashlib.sha256(b"".join(hf_qa.canonical(row) for row in rows)).hexdigest()
        assert proof["request_count"] == expected
        assert sum(proof["strata"].values()) == proof["question_count"]
        for key, tokens in proof["models"].items():
            assert tokens["path"] == prepared_inputs["models"][key]["path"]
            assert tokens["request_count"] == expected
            assert tokens["overflow_count"] == 0 and 0 < tokens["max_prompt_tokens"] < 8192 - 128
            assert tokens["max_source_tokens"] <= 1536 if name == "retrieval" else tokens["max_source_tokens"] is None
    old_parents = {row["parent_document_id"] for row in prepared_inputs["records"] if not row["document_id"].startswith("new-")}
    assert all(row["parent_document_id"] not in old_parents for row in envelopes["retrieval"]["requests"])
    assert diagnostics["development"]["questions"] == 2
    assert diagnostics["heldout"]["questions"] == 5
    assert diagnostics["no_generation_outputs_used"] is True
    assert manifest["retrieval_diagnostics_sha256"] == hashlib.sha256(hf_qa.canonical(diagnostics)).hexdigest()


def test_stability_preserves_every_original_prompt_and_matches_sources(prepared_inputs):
    originals = {(row["document_id"], row["condition"]): row for row in prepared_inputs["old"]["requests"]}
    rows = prepare.build_stability(prepared_inputs["old"]["requests"])
    validate_requests(rows, "stability")
    assert len(rows) == 24
    for row in rows:
        original = originals[(row["document_id"], row["context_condition"])]
        for field in ("system", "user", "source_spans", "source_gold_visible", "pack_injected",
                      "pack_prompt", "pack_policy", "source_text", "expected_answers"):
            assert row[field] == original[field]
        assert row["independent_validation"] is False
        assert row["reused_original_question"] is True


def test_public_preparation_artifacts_contain_no_raw_ids_text_answers(prepared_inputs):
    _, diagnostics, manifest = prepare.prepare_from_records(**prepared_inputs)
    public = json.dumps([diagnostics, manifest], ensure_ascii=False)
    for row in prepared_inputs["records"]:
        assert row["document_id"] not in public
        assert row["text"] not in public
        assert row["question"] not in public
    assert "사과나무" not in public and "expected_answers" not in public


def test_source_budget_uses_stricter_model_and_counts_actual_separators():
    first, second = Tokenizer(1), Tokenizer(2)
    budget = prepare.SourceBudget({"strict": first, "loose": second}, cap=5)
    source = {"text": "가나다\n라마바", "document_sha256": "authored"}
    spans = [(0, 3), (4, 7)]
    assert budget.lengths(source, spans) == {"strict": 8, "loose": 4}
    assert budget.factory(source)(spans) is False
    assert first.encoded == ["가나다\n\n라마바"]
    assert budget.lengths(source, spans)["strict"] == 8
    assert len(first.encoded) == len(second.encoded) == 1


def test_input_order_does_not_change_frozen_rows_or_manifest(prepared_inputs):
    envelopes, diagnostics, manifest = prepare.prepare_from_records(**prepared_inputs)
    reversed_inputs = {**prepared_inputs, "records": list(reversed(prepared_inputs["records"]))}
    again = prepare.prepare_from_records(**reversed_inputs)
    assert again == (envelopes, diagnostics, manifest)


@pytest.mark.parametrize("bad_input", ["missing_prior_ids", "unknown_prior_id", "old_source_changed",
    "old_parent_changed", "old_gold_changed", "empty_blind", "blind_parent_changed", "wrong_phase"])
def test_prior_exclusions_fail_closed(prepared_inputs, bad_input):
    kwargs = deepcopy(prepared_inputs)
    if bad_input == "missing_prior_ids":
        kwargs["pool"].pop("prior_evidence_question_ids")
    elif bad_input == "unknown_prior_id":
        kwargs["pool"]["prior_evidence_question_ids"].append("unknown")
    elif bad_input == "old_source_changed":
        for row in kwargs["old"]["requests"]:
            row["question"] += "변경"
            row["user"] = row["user"].replace("질문: 목표", "질문: 변경목표")
    elif bad_input == "old_parent_changed":
        for row in kwargs["old"]["requests"]:
            row["parent_document_id"] += "changed"
    elif bad_input == "old_gold_changed":
        for row in kwargs["old"]["requests"]:
            if row["positive_gold"]:
                row["expected_answers"] = ["새 정답"]
    elif bad_input == "empty_blind":
        kwargs["blind_rows"] = []
    elif bad_input == "blind_parent_changed":
        kwargs["blind_rows"][0]["parent_document_id"] = "otherarticle"
    elif bad_input == "wrong_phase":
        kwargs["pool"]["protocol"]["phase"] = "FINAL_FROZEN"
    with pytest.raises(ValueError):
        prepare.prepare_from_records(**kwargs)


def test_default_old_sample_count_is_enforced(prepared_inputs):
    prepared_inputs.pop("expected_old_questions")
    with pytest.raises(ValueError, match="old frozen question count"):
        prepare.prepare_from_records(**prepared_inputs)


def test_default_fixed_quota_amendment_keeps_128_independent_articles_and_all_exclusions(prepared_inputs):
    prepared_inputs.pop("retrieval_quotas")
    for kind, quota in prepare.RETRIEVAL_QUOTAS.items():
        prepared_inputs["records"].extend(_record(f"new-{kind}-{index}", kind)
                                          for index in range(4, quota))
    envelopes, diagnostics, manifest = prepare.prepare_from_records(**prepared_inputs)
    retrieval = manifest["experiments"]["retrieval"]
    assert retrieval["question_count"] == retrieval["parent_articles"] == 128
    assert retrieval["request_count"] == 512
    assert retrieval["strata"] == {"SPAN": 40, "YES_NO": 8, "NO_ANSWER": 80}
    assert retrieval["strata"]["SPAN"] + retrieval["strata"]["YES_NO"] == 48
    amendment = manifest["retrieval_quota_amendment"]
    assert amendment["initial_target"] == {"SPAN": 56, "YES_NO": 8, "NO_ANSWER": 64}
    assert amendment["final_target"] == prepare.RETRIEVAL_QUOTAS
    assert amendment["before_any_followup_generation"] is True
    assert amendment["prior_article_exclusions_relaxed"] is False
    assert amendment == diagnostics["quota_amendment"]
    assert amendment == envelopes["retrieval"]["provenance"]["quota_amendment"]
    assert manifest["retrieval_selection"]["exclusions"]["prior_parent_or_content_overlap"] == 7


def test_insufficient_independent_sample_is_reported_without_silent_relaxation(prepared_inputs):
    prepared_inputs["retrieval_quotas"] = {"SPAN": 99}
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA") as caught:
        prepare.prepare_from_records(**prepared_inputs)
    assert caught.value.inventory["selected_by_stratum"] == {"SPAN": 4}
    assert caught.value.inventory["exclusions"]["prior_parent_or_content_overlap"] == 7


def test_complete_oracle_capacity_is_applied_before_heldout_selection(prepared_inputs):
    record = _record("new-bad-oracle")
    text = "목표 답안은 사과나무다." + "긴문단" * 1200
    record.update(text=text, document_sha256=hashlib.sha256(text.encode()).hexdigest(),
        passage_candidates=[[0, len(text)]], answer_passage_spans=[[0, len(text)]])
    prepared_inputs["records"].append(record)
    envelopes, _, manifest = prepare.prepare_from_records(**prepared_inputs)
    assert manifest["retrieval_selection"]["exclusions"]["predeclared_capacity_rule"] == 1
    assert all(row["document_id"] != "new-bad-oracle" for row in envelopes["retrieval"]["requests"])


def test_actual_chat_template_capacity_is_checked_before_sealing(prepared_inputs):
    prepared_inputs["tokenizers"]["gemma12b"].prompt_overhead = 9000
    with pytest.raises(ValueError, match="actual-token capacity"):
        prepare.prepare_from_records(**prepared_inputs)


def test_prompt_proof_reuses_identical_template_calls_across_repeats(prepared_inputs):
    prepare.prepare_from_records(**prepared_inputs)
    # Five retrieval questions x up to four unique prompts, and exactly two
    # original contexts per old question; schema/repeat never modify prompts.
    for tokenizer in prepared_inputs["tokenizers"].values():
        counts = Counter(tuple((message["role"], message["content"]) for message in messages)
                         for messages in tokenizer.templates)
        assert max(counts.values()) <= 2  # Independent experiment proof caches.


def test_prepare_rejects_missing_or_mismatched_model_tokenizers(prepared_inputs):
    prepared_inputs["tokenizers"] = {"missing": Tokenizer()}
    with pytest.raises(ValueError, match="matching model tokenizers"):
        prepare.prepare_from_records(**prepared_inputs)


@pytest.mark.parametrize("ids", [[True], [[1, 2]], "text", None])
def test_invalid_actual_tokenizer_outputs_are_rejected(ids):
    with pytest.raises(ValueError, match="flat integer token IDs"):
        prepare._token_ids(ids)
