"""Source loss, compact pack and unseen-context sampling invariants."""
from copy import deepcopy
import hashlib
import random
from types import SimpleNamespace

import pytest

from eval import diagnostic_qa as qa
from eval import extended_qa
from eval.collect_hf_qa_queue import validate_public_json
from eval.hf_qa import EVIDENCE_POLICY, canonical
from ktrf.context import QA_CONTEXT_POLICY


class Tokenizer:
    def __init__(self, ratio=4, overhead=32):
        self.ratio, self.overhead = ratio, overhead

    def encode(self, text, **kwargs):
        return [1] * ((len(text) + self.ratio - 1) // self.ratio)

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {"tokenize": True, "add_generation_prompt": True,
                          "enable_thinking": False, "return_dict": False}
        return [1] * (self.overhead + len(self.encode("".join(row["content"] for row in messages))))


def record(index, positive=True):
    rng = random.Random(index)
    text = "금감원 " + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(1600))
    return {"document_id": f"question-{index}", "parent_document_id": f"parent-{index}",
        "document_sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text,
        "question": f"금감원 문서 {index}의 시작 이름은?", "stratum": "SPAN" if positive else "NO_ANSWER",
        "positive_gold": positive, "expected_answers": ["금감원"] if positive else [],
        "answer_spans": [[0, 3]] if positive else [], "title": f"문서 {index}", "source": "authored"}


@pytest.fixture
def prepared(monkeypatch):
    monkeypatch.setattr(qa, "REUSED_PER_STRATUM", 2)
    monkeypatch.setattr(qa, "FRESH_PER_STRATUM", 2)
    monkeypatch.setattr(qa, "PRIOR_TRANSFER_PER_STRATUM", 4)
    monkeypatch.setattr(extended_qa, "TRANSFER_PER_STRATUM", 4)
    monkeypatch.setattr(extended_qa, "SUBSET_PER_STRATUM", 2)
    monkeypatch.setattr(extended_qa, "CORPUS_DOCUMENTS", 12)
    calls = []

    def fake_pack(snapshot, text, *, query, mode, context_policy):
        assert text.startswith(query + "\n")
        assert mode == "commit" and context_policy.profile == "qa_grounding"
        calls.append((query, text[len(query) + 1:]))
        pack = {"resolved_terms": [{"canonical": "금융감독원", "short_definition": "금융 감독 <기관> & 지원",
            "mentions": [{"surface": "금감원", "appears_inside": {"surface": "금감원장", "relation": "HEAD_OF"}}],
            "disambiguation_hints": ["기관 자체만 지칭"]}],
            "ambiguous_mentions": [{"surface": "ABC", "candidates": [
                {"canonical": "과금", "short_definition": "과금 콘솔"},
                {"canonical": "출입", "short_definition": "출입 승인"}]}],
            "coverage": {"complete": False}, "omissions": [{"reason": "token_budget", "entity_id": "secret-omitted-id"}],
            "unknown_mentions": [{"surface": "미등록", "reason": "KB_MISSING"}],
            "document_definitions": [{"surface": "ABC", "authority": "document_asserted", "entity_id": "secret-asserted-id"}]}
        return SimpleNamespace(should_inject=True, context_pack=pack,
            prompt_fragment="<terminology>" + "자료" * 120 + "</terminology>", policy_fragment=QA_CONTEXT_POLICY)

    monkeypatch.setattr(extended_qa, "prepare_llm_context", fake_pack)
    records = [record(i, i % 2 == 0) for i in range(24)]
    tokenizers = {"gemma12b": Tokenizer(), "qwen27b": Tokenizer(ratio=3, overhead=75)}
    kwargs = {"records": records, "snapshot": SimpleNamespace(snapshot_id="snapshot-authored"),
        "tokenizers": tokenizers, "models": {key: {"path": f"/authored/{key}"} for key in tokenizers},
        "code_revision": "a" * 40, "source_identity": {"dataset": "authored"}}
    envelopes, _ = extended_qa.prepare_qa(**kwargs)
    calls.clear()
    return {**kwargs, "prior_budget_envelope": envelopes["budget"],
            "prior_transfer_envelope": envelopes["transfer"]}, calls


def test_factorial_preserves_exact_frozen_sources_and_shared_facts(prepared):
    kwargs, calls = prepared
    envelopes, manifest = qa.prepare_qa_diagnostics(**kwargs)
    validate_public_json(manifest)
    assert {key: value["request_count"] for key, value in manifest["experiments"].items()} == {
        "source_pack_factorial": 24, "fresh_compact": 12}
    prior = {(r["document_id"], r["condition"]): r for r in kwargs["prior_budget_envelope"]["requests"]}
    groups = {}
    for row in envelopes["source_pack_factorial"]["requests"]:
        groups.setdefault(row["document_id"], []).append(row)
        condition = "cap1536_bm25" if row["source_variant"] == "full" else "cap1024_bm25_pack"
        assert row["source_spans"] == prior[(row["document_id"], condition)]["source_spans"]
        assert row["rendered_source_sha256"] == prior[(row["document_id"], condition)]["rendered_source_sha256"]
        assert row["system"] == EVIDENCE_POLICY + "\n\n" + QA_CONTEXT_POLICY
        assert "total_prompt_token_cap" not in row
        assert row["evaluation_split"] == "adaptive_reused"
    for rows in groups.values():
        assert len({r["pack_source_sha256"] for r in rows}) == 1
        assert len({r["pack_sha256"] for r in rows}) == 1
        assert len({r["fact_cards_sha256"] for r in rows}) == 1
        assert len({canonical(r["fact_cards"]) for r in rows}) == 1
        assert len({r["system"] for r in rows}) == 1
    # One full-source pack per reused question, one fixed-source pack per fresh question.
    assert len(calls) == 8
    for name, envelope in envelopes.items():
        assert hashlib.sha256(canonical(envelope)).hexdigest() == manifest["experiments"][name]["envelope_sha256"]


def test_compact_keeps_composition_candidates_completeness_and_caveats(prepared):
    kwargs, _ = prepared
    envelopes, _ = qa.prepare_qa_diagnostics(**kwargs)
    for rows in (e["requests"] for e in envelopes.values()):
        for row in rows:
            if row["pack_variant"] != "compact":
                continue
            fragment = row["pack_prompt"]
            for text in ("금융감독원", "금감원장", "같은 대상이 아님", "HEAD_OF", "미확정 후보", "complete=false",
                         "token_budget", "document_asserted", "KB_MISSING", "기관 자체만 지칭"):
                assert text in fragment
            assert "<기관>" not in fragment and "&lt;기관&gt;" in fragment
            assert "secret-omitted-id" not in fragment and "secret-asserted-id" not in fragment
            assert "entity_id" not in fragment
            assert row["fact_cards"]["semantic_caveats"]["compound_relations"][0]["same_entity"] is False


def test_fresh_excludes_entire_prior_transfer_and_declared_corpus_exposure(prepared):
    kwargs, calls = prepared
    prior_ids = {r["document_id"] for r in kwargs["prior_transfer_envelope"]["requests"]}
    available = [r for r in kwargs["records"] if r["document_id"] not in prior_ids]
    # The first full corpus exposure, a near-copy and a sentence-contained exposure.
    exclusions = [available[0], available[1]["text"][:-5] + "*****",
                  available[2]["text"] + ". Additional unrelated material " * 10]
    envelopes, manifest = qa.prepare_qa_diagnostics(**kwargs, exclusion_texts=exclusions)
    fresh_ids = {r["document_id"] for r in envelopes["fresh_compact"]["requests"]}
    assert not fresh_ids & (prior_ids | {r["document_id"] for r in available[:3]})
    assert len(fresh_ids) == 4
    assert manifest["selection"]["exclusions"]["prior_question_identity"] >= len(prior_ids)
    assert manifest["selection"]["exclusions"]["character_5gram_containment"] >= 1
    assert manifest["selection"]["retrieval_success_used_for_selection"] is False
    assert manifest["selection"]["pack_eligibility_used_for_selection"] is False
    assert len(calls) == 8


def test_deterministic_fresh_selection_precedes_any_resolver_call(prepared):
    kwargs, calls = prepared
    baseline = qa.prepare_qa_diagnostics(**kwargs)
    assert baseline == qa.prepare_qa_diagnostics(**{**kwargs, "records": list(reversed(kwargs["records"]))})
    calls.clear()
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA"):
        qa.prepare_qa_diagnostics(**kwargs, exclusion_texts=kwargs["records"])
    assert calls == []


def test_fresh_source_policy_and_actual_templates(prepared):
    kwargs, _ = prepared
    envelopes, _ = qa.prepare_qa_diagnostics(**kwargs)
    groups = {}
    for row in envelopes["fresh_compact"]["requests"]:
        groups.setdefault(row["case_id"], []).append(row)
        assert row["evaluation_split"] == "fresh_context_holdout"
        assert row["system"] == EVIDENCE_POLICY + ("\n\n" + QA_CONTEXT_POLICY if row["pack_injected"] else "")
        assert row["source_character_count"] <= 3000 and len(row["source_spans"]) <= 3
    for rows in groups.values():
        assert len({r["rendered_source_sha256"] for r in rows}) == 1
        assert len({r["pack_sha256"] for r in rows}) == 1
    for envelope in envelopes.values():
        for row in envelope["requests"]:
            for model, tok in kwargs["tokenizers"].items():
                actual = len(tok.apply_chat_template(
                    [{"role": "system", "content": row["system"]}, {"role": "user", "content": row["user"]}],
                    tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False))
                assert actual == row["prompt_tokens"][model] <= 8064
                assert row["source_tokens"][model] <= 1536


def test_frozen_rows_pass_shared_runtime_validation(prepared):
    from eval.run_extended_suite import validate_requests

    kwargs, _ = prepared
    envelopes, _ = qa.prepare_qa_diagnostics(**kwargs)
    for envelope in envelopes.values():
        assert validate_requests(envelope["requests"], envelope["protocol"]) == envelope["requests"]


def test_gold_cannot_change_any_prompt_or_source_selection(prepared):
    kwargs, _ = prepared
    baseline, _ = qa.prepare_qa_diagnostics(**kwargs)
    changed = deepcopy(kwargs)
    for record in changed["records"]:
        if record["positive_gold"]:
            record["answer_spans"] = [[20, 25]]
            record["expected_answers"] = [record["text"][20:25]]
    for name in ("prior_budget_envelope", "prior_transfer_envelope"):
        for row in changed[name]["requests"]:
            if row["positive_gold"]:
                row["answer_spans"] = [[20, 25]]
                row["expected_answers"] = [row["source_text"][20:25]]
    altered, _ = qa.prepare_qa_diagnostics(**changed)
    for name in baseline:
        for before, after in zip(baseline[name]["requests"], altered[name]["requests"]):
            for field in ("case_id", "condition", "source_spans", "user", "system", "pack_sha256"):
                assert before[field] == after[field]


def test_ungrounded_pack_never_injected_but_factorial_policy_stays_constant(prepared, monkeypatch):
    kwargs, _ = prepared
    monkeypatch.setattr(extended_qa, "prepare_llm_context", lambda *args, **kw: SimpleNamespace(
        should_inject=False, context_pack={"coverage": {"query_grounded": False}},
        prompt_fragment="MUST NOT APPEAR", policy_fragment=QA_CONTEXT_POLICY))
    envelopes, _ = qa.prepare_qa_diagnostics(**kwargs)
    for name, envelope in envelopes.items():
        for row in envelope["requests"]:
            assert not row["pack_injected"] and row["pack_prompt"] is None
            assert "MUST NOT APPEAR" not in row["user"]
            assert row["system"] == EVIDENCE_POLICY + ("\n\n" + QA_CONTEXT_POLICY if name == "source_pack_factorial" else "")


@pytest.mark.parametrize("tamper", ["spans", "gold", "snapshot", "conditions"])
def test_invalid_prior_provenance_or_spans_fail_before_pack_building(prepared, tamper):
    kwargs, calls = prepared
    changed = deepcopy(kwargs)
    prior = changed["prior_budget_envelope"]
    if tamper == "spans":
        prior["requests"][0]["source_spans"] = [[0, 999999]]
    elif tamper == "gold":
        positive = next(row for row in prior["requests"] if row["positive_gold"])
        positive["expected_answers"] = ["wrong"]
    elif tamper == "snapshot":
        prior["provenance"]["snapshot_id"] = "other"
    else:
        prior["requests"].pop()
    with pytest.raises(ValueError):
        qa.prepare_qa_diagnostics(**changed)
    assert calls == []


def test_prompt_overflow_fails_without_silent_source_changes(prepared):
    kwargs, _ = prepared
    changed = {**kwargs, "tokenizers": {key: Tokenizer(overhead=9000) for key in kwargs["tokenizers"]}}
    with pytest.raises(ValueError, match="actual chat template exceeds"):
        qa.prepare_qa_diagnostics(**changed)
