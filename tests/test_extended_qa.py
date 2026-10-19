"""Offline invariants for independently sampled, bounded extended QA tracks."""
from copy import deepcopy
import hashlib
import json
import random
from types import SimpleNamespace

import pytest

from eval import extended_qa as qa
from eval.hf_qa import EVIDENCE_POLICY, canonical
from eval.collect_hf_qa_queue import validate_public_json


class Tokenizer:
    def __init__(self, ratio=4, overhead=32):
        self.ratio, self.overhead = ratio, overhead

    def encode(self, text, **kwargs):
        return [1] * ((len(text) + self.ratio - 1) // self.ratio)

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {"tokenize": True, "add_generation_prompt": True,
                          "enable_thinking": False, "return_dict": False}
        return [1] * (self.overhead + len(self.encode("".join(row["content"] for row in messages))))


def record(index, positive=True, length=1600):
    rng = random.Random(index)
    text = "금감원 " + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(length))
    return {"document_id": f"question-{index}", "parent_document_id": f"parent-{index}",
        "document_sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text,
        "question": f"금감원 문서 {index}의 시작 이름은?", "stratum": "SPAN" if positive else "NO_ANSWER",
        "positive_gold": positive, "expected_answers": ["금감원"] if positive else [],
        "answer_spans": [[0, 3]] if positive else [], "title": f"문서 {index}", "source": "authored"}


@pytest.fixture
def prepared(monkeypatch):
    monkeypatch.setattr(qa, "TRANSFER_PER_STRATUM", 4)
    monkeypatch.setattr(qa, "SUBSET_PER_STRATUM", 2)
    monkeypatch.setattr(qa, "CORPUS_DOCUMENTS", 12)
    calls = []

    def fake_pack(snapshot, text, *, query, mode, context_policy):
        assert mode == "commit" and context_policy.profile == "qa_grounding"
        assert context_policy.max_tokens == 800
        assert text.startswith(query + "\n")
        calls.append((query, text[len(query) + 1:]))
        pack = {"resolved_terms": [{"canonical": "금융감독원", "short_definition": "금융 감독 <기관> & 지원",
            "mentions": [{"surface": "금감원", "appears_inside": {"surface": "금감원장"}}]}],
            "ambiguous_mentions": [{"surface": "ABC", "candidates": [
                {"canonical": "과금", "short_definition": "과금 콘솔"},
                {"canonical": "출입", "short_definition": "출입 승인"}]}],
            "metadata_never_in_factorial": "hidden"}
        return SimpleNamespace(should_inject=True, context_pack=pack,
            prompt_fragment="<terminology>" + "자료" * 100 + "</terminology>",
            policy_fragment="미확정 후보를 검증된 연결로 취급하지 마세요.")

    monkeypatch.setattr(qa, "prepare_llm_context", fake_pack)
    records = [record(i, i % 2 == 0) for i in range(16)]
    tokenizers = {"gemma12b": Tokenizer(), "qwen27b": Tokenizer(ratio=3, overhead=75)}
    return {"records": records, "snapshot": SimpleNamespace(snapshot_id="snapshot-authored"),
        "tokenizers": tokenizers, "models": {key: {"path": f"/authored/{key}"} for key in tokenizers},
        "code_revision": "a" * 40, "source_identity": {"dataset": "authored"}}, calls


def test_adapter_discards_impossible_plausible_answers_and_validates_codepoints(tmp_path):
    rows = [
        {"guid": "valid", "context": "😀 서울은 수도다.", "question": "도시는?", "is_impossible": False,
         "answers": {"text": ["서울"], "answer_start": [2]}},
        {"guid": "null", "context": "😀 부산은 항구다.", "question": "없는 내용?", "is_impossible": True,
         "answers": {"text": ["부산"], "answer_start": [2]}},
        {"guid": "bad-offset", "context": "😀 서울은 수도다.", "question": "도시는?", "is_impossible": False,
         "answers": {"text": ["서울"], "answer_start": [5]}},
        {"guid": "bad-array", "context": "원문", "question": "질문", "is_impossible": False,
         "answers": {"text": ["원문"], "answer_start": []}},
    ]
    path = tmp_path / "mrc.json"
    path.write_text(json.dumps(rows, ensure_ascii=False))
    records, inventory = qa.load_mrc_records(path)
    assert len(records) == 2 and inventory["rejected_rows"] == 2
    assert records[0]["answer_spans"] == [(2, 4)]
    assert records[1]["stratum"] == "NO_ANSWER"
    assert records[1]["expected_answers"] == records[1]["answer_spans"] == []
    assert records[0]["parent_document_id"].startswith("klue-mrc-context:")
    assert inventory["impossible_plausible_answers_never_used_as_gold"] is True


def test_prior_parent_and_normalized_sentence_and_near_content_are_excluded(prepared):
    kwargs, calls = prepared
    records = kwargs["records"]
    # Parent exclusion must apply even when content is different.
    parent = {"parent_document_id": records[0]["parent_document_id"], "text": "별도 내용"}
    exact = " " + records[1]["text"].upper() + "\n"
    # A sentence shared inside a much larger article is excluded too.
    sentence = records[2]["text"] + ". " + "별도 내용 " * 50
    near = records[3]["text"][:-5] + "*****"
    selected, _, eligible, inventory = qa.select_samples(records, [parent, exact, sentence, near])
    assert not {row["document_id"] for row in records[:4]} & {row["document_id"] for row in eligible}
    assert len(selected) == 8
    assert inventory["exclusions"] == {"prior_parent_overlap": 1, "normalized_exact_overlap": 1,
        "exact_sentence_overlap": 1, "character_5gram_containment": 1}
    assert calls == []


def test_insufficient_data_fails_before_ranking_or_pack_generation(prepared):
    kwargs, calls = prepared
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA"):
        qa.prepare_qa(**{**kwargs, "records": kwargs["records"][:5]})
    assert calls == []


def test_full_preparation_is_deterministic_and_tracks_are_nested(prepared):
    kwargs, _ = prepared
    envelopes, manifest = qa.prepare_qa(**kwargs)
    validate_public_json(manifest)
    repeated = qa.prepare_qa(**{**kwargs, "records": list(reversed(kwargs["records"]))})
    assert (envelopes, manifest) == repeated
    assert {name: data["request_count"] for name, data in manifest["experiments"].items()} == {
        "transfer": 32, "budget": 16, "corpus": 16, "pack": 20}
    ids = {name: {row["document_id"] for row in envelope["requests"]} for name, envelope in envelopes.items()}
    assert ids["budget"] == ids["pack"] < ids["transfer"]
    assert ids["corpus"] < ids["transfer"]
    assert all(row["positive_gold"] for row in envelopes["corpus"]["requests"])
    assert envelopes["budget"]["protocol"]["comparisons"] == [
        ["cap1024_bm25", "cap1024_bm25_pack"],
        ["cap1536_bm25", "cap1536_bm25_pack"]]
    assert all(row["repeat_id"] == 0 and row["decoding_mode"] == "json_schema"
               for envelope in envelopes.values() for row in envelope["requests"])
    for name, envelope in envelopes.items():
        actual = hashlib.sha256(canonical(envelope)).hexdigest()
        assert actual == manifest["experiments"][name]["envelope_sha256"]


def test_total_budget_measures_both_full_templates_and_never_pads(prepared):
    kwargs, _ = prepared
    envelopes, _ = qa.prepare_qa(**kwargs)
    budget_rows = envelopes["budget"]["requests"]
    for row in budget_rows:
        for model, tokenizer in kwargs["tokenizers"].items():
            actual = len(tokenizer.apply_chat_template(
                [{"role": "system", "content": row["system"]}, {"role": "user", "content": row["user"]}],
                tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False))
            assert actual == row["prompt_tokens"][model] <= row["total_prompt_token_cap"]
            assert row["prompt_budget_utilization"][model] == actual / row["total_prompt_token_cap"]
        assert row["source_character_count"] <= 3000
        assert row["user"].endswith("</terminology>" if row["pack_injected"] else "</source>")
    # Larger model overhead must constrain the common selected source.
    assert any(row["prompt_tokens"]["qwen27b"] > row["prompt_tokens"]["gemma12b"] for row in budget_rows)
    assert any(row["prompt_tokens"]["gemma12b"] < row["total_prompt_token_cap"] for row in budget_rows)


def test_corpus_ranker_cannot_read_anchor_or_gold(prepared, monkeypatch):
    kwargs, _ = prepared
    original = qa.CorpusIndex.search
    inputs = []

    def checked(self, question, method):
        assert all(set(row) == {"parent_document_id", "document_sha256", "text"} for row in self.documents)
        assert isinstance(question, str)
        inputs.append((question, method))
        return original(self, question, method)

    monkeypatch.setattr(qa.CorpusIndex, "search", checked)
    envelopes, _ = qa.prepare_qa(**kwargs)
    assert len(inputs) == 8
    for row in envelopes["corpus"]["requests"]:
        assert row["corpus_document_count"] == 12
        assert len(row["selected_documents"]) <= 3
        assert row["source_gold_visible"] == any(
            doc["document_sha256"] == row["document_sha256"] and
            any(qa.contains_span(doc["spans"], answer) for answer in row["answer_spans"])
            for doc in row["selected_documents"])


def test_gold_changes_do_not_change_ranker_or_pack_prompts(prepared):
    kwargs, _ = prepared
    baseline, _ = qa.prepare_qa(**kwargs)
    altered = deepcopy(kwargs["records"])
    for row in altered:
        if row["positive_gold"]:
            row["answer_spans"] = [[20, 25]]
            row["expected_answers"] = [row["text"][20:25]]
    changed, _ = qa.prepare_qa(**{**kwargs, "records": altered})
    for name in baseline:
        original_rows, new_rows = baseline[name]["requests"], changed[name]["requests"]
        for before, after in zip(original_rows, new_rows):
            for field in ("case_id", "condition", "source_spans", "system", "user", "pack_sha256"):
                assert before[field] == after[field]


def test_factorial_preserves_fact_cards_and_source_while_changing_only_declared_factors(prepared):
    kwargs, _ = prepared
    envelopes, _ = qa.prepare_qa(**kwargs)
    groups = {}
    for row in envelopes["pack"]["requests"]:
        groups.setdefault(row["case_id"], {})[row["condition"]] = row
    for rows in groups.values():
        factors = [row for key, row in rows.items() if key != "none"]
        assert len({row["fact_cards_sha256"] for row in factors}) == 1
        assert len({row["pack_sha256"] for row in factors}) == 1
        assert len({row["rendered_source_sha256"] for row in rows.values()}) == 1
        assert rows["text_neutral"]["system"] == rows["json_neutral"]["system"] == EVIDENCE_POLICY
        assert rows["text_conservative"]["system"] == rows["json_conservative"]["system"]
        assert rows["text_conservative"]["user"] == rows["text_neutral"]["user"]
        assert rows["json_conservative"]["user"] == rows["json_neutral"]["user"]
        assert json.loads(rows["json_neutral"]["pack_prompt"]) == rows["text_neutral"]["fact_cards"]
        assert "metadata_never_in_factorial" not in rows["json_neutral"]["pack_prompt"]
        assert "<기관>" not in rows["json_neutral"]["pack_prompt"]
        assert "<기관>" not in rows["text_neutral"]["pack_prompt"]
        assert "금감원장" in rows["text_neutral"]["pack_prompt"]


def test_empty_or_ungrounded_pack_never_injected(prepared, monkeypatch):
    kwargs, _ = prepared
    monkeypatch.setattr(qa, "prepare_llm_context", lambda *args, **kw: SimpleNamespace(
        should_inject=False, context_pack={"coverage": {"query_grounded": False}},
        prompt_fragment="must not appear", policy_fragment="must not appear"))
    envelopes, _ = qa.prepare_qa(**kwargs)
    for envelope in envelopes.values():
        assert all(not row["pack_injected"] and row["pack_prompt"] is None
                   and row["system"] == EVIDENCE_POLICY for row in envelope["requests"])


def test_question_policy_overflow_fails_without_silent_question_truncation(prepared):
    kwargs, _ = prepared
    kwargs["tokenizers"] = {key: Tokenizer(overhead=1100) for key in kwargs["tokenizers"]}
    with pytest.raises(ValueError, match="even without source"):
        qa.prepare_qa(**kwargs)
