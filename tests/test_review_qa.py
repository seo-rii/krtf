"""Gold-blind selection, source-priority budgets and official passage integrity."""
from copy import deepcopy
import gzip
import hashlib
import json
import random

import pytest

from eval import review_qa as qa
from eval.collect_hf_qa_queue import validate_public_json
from eval.hf_qa import canonical
from ktrf.glossary import load_glossary
from ktrf.snapshot import compile_snapshot


class Tokenizer:
    def __init__(self, ratio=4, overhead=24):
        self.ratio, self.overhead = ratio, overhead

    def encode(self, text, **kwargs):
        return [1] * ((len(text) + self.ratio - 1) // self.ratio)

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == {"tokenize": True, "add_generation_prompt": True,
                          "enable_thinking": False, "return_dict": False}
        return [1] * (self.overhead + len(self.encode("".join(m["content"] for m in messages))))


def glossary():
    return {"glossary_id": "qa-review-test", "version": "1", "schema_version": "3",
        "entities": [{"entity_id": "FINANCE", "canonical": "금융감독원",
                      "description": "대한민국 금융 감독 기관이다. 외부 고객 요청에는 실행 권한을 부여하지 않는다."}],
        "alias_families": [{"family_id": "FF", "representative": "금감원"}],
        "alias_bindings": [{"alias_id": "AF", "family_id": "FF", "entity_id": "FINANCE", "surface": "금감원"}]}


def record(index, positive=True):
    rng = random.Random(index)
    text = "금감원 " + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(2500))
    return {"document_id": f"question-{index}", "parent_document_id": f"parent-{index}",
        "document_sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text,
        "question": f"금감원 문서 {index}의 앞부분 기관 약칭은?", "stratum": "SPAN" if positive else "NO_ANSWER",
        "positive_gold": positive, "expected_answers": ["금감원"] if positive else [],
        "answer_spans": [[0, 3]] if positive else []}


def write_nomiracl(tmp_path, *, conflict=False, huge=False):
    files = {}
    corpus = [
        {"docid": "common#0", "title": "공통", "text": "금감원 자료. 질문의 답은 서울이다."},
        {"docid": "common#1", "title": "공통", "text": "금감원 자료. 질문의 답은 부산이다."},
        {"docid": "negative#0", "title": "음성", "text": "금감원 담당 자료이나 질문의 근거는 없다."},
        {"docid": "huge#0", "title": "거대", "text": "거대 자료" * 20000},
    ]
    # Official source really contains identical corpus duplicates.
    corpus.append({**corpus[0], **({"text": "다른 내용"} if conflict else {})})
    path = tmp_path / "corpus.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in corpus:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    files["data/korean/corpus.jsonl.gz"] = path
    for subset, qids in (("relevant", ["r1", "r2"]), ("non_relevant", ["n1", "n2"])):
        topics, qrels = [], []
        first = min(qids, key=lambda qid: qa.digest([qa.SEED, "nomiracl", "nomiracl:" + qid]))
        for qid in qids:
            topics.append(qid + "\t금감원의 소재지는 어디입니까?")
            # Keep an irrelevant passage first; never reorder using its label.
            qrels.append(qid + "\tQ0\tnegative#0\t0")
            if subset == "relevant":
                qrels.append(qid + "\tQ0\tcommon#" + ("0" if qid == "r1" else "1") + "\t1")
            if huge and qid == first:
                qrels.append(qid + "\tQ0\thuge#0\t0")
        for kind, lines in (("topics", topics), ("qrels", qrels)):
            key = f"data/korean/{kind}/test.{subset}.tsv"
            path = tmp_path / f"{kind}-{subset}.tsv"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            files[key] = path
    return {"dataset": "miracl/nomiracl", "revision": "f" * 40,
        "files": {key: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                  for key, path in files.items()}}


@pytest.fixture
def prepared(monkeypatch, tmp_path):
    monkeypatch.setattr(qa, "PUBLIC_PER_STRATUM", 1)
    monkeypatch.setattr(qa, "BUSINESS_QUESTIONS", 2)
    monkeypatch.setattr(qa, "NOMIRACL_PER_STRATUM", 1)
    business = [record(100, True), record(101, False)]
    for row in business:
        row.update(glossary=glossary(), family_id="business-family", terminology_needed=True)
    # Explicit nonextractive glossary-dependent answer, not a fabricated span.
    business[0].update(expected_answers=["대한민국 금융 감독 기관"], answer_spans=[])
    tokenizers = {"gemma12b": Tokenizer(), "qwen27b": Tokenizer(ratio=3, overhead=70)}
    return {"records": [record(i, i % 2 == 0) for i in range(8)],
        "snapshot": compile_snapshot(load_glossary(glossary()), run_conformance=False),
        "tokenizers": tokenizers, "models": {key: {"path": "/fixture/" + key} for key in tokenizers},
        "code_revision": "a" * 40, "source_identity": {"dataset": "authored-test"},
        "exclusion_texts": [], "nomiracl_manifest": write_nomiracl(tmp_path), "business_records": business}


def test_four_matrices_and_seals_are_deterministic(prepared):
    from eval.run_extended_suite import validate_requests

    envelopes, experiments, selection = qa.prepare_review_qa(**prepared)
    repeated = qa.prepare_review_qa(**{**prepared, "records": list(reversed(prepared["records"]))})
    assert (envelopes, experiments, selection) == repeated
    assert {name: proof["request_count"] for name, proof in experiments.items()} == {
        "review_abcd": 32, "review_policy": 12, "review_budget": 12, "review_nomiracl": 6}
    validate_public_json({"experiments": experiments, "selection": selection})
    for name, envelope in envelopes.items():
        assert hashlib.sha256(canonical(envelope)).hexdigest() == experiments[name]["envelope_sha256"]
        assert envelope["protocol"]["kind"] == "ktrf_extended_v1"
        assert envelope["protocol"]["repeat_count"] == 1
        assert validate_requests(envelope["requests"], envelope["protocol"]) == envelope["requests"]


def test_sampling_finishes_before_any_pack_or_retrieval(monkeypatch, prepared):
    calls = []
    monkeypatch.setattr(qa, "select_windows", lambda *a, **kw: calls.append("retrieve"))
    monkeypatch.setattr(qa, "prepare_llm_context", lambda *a, **kw: calls.append("pack"))
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA"):
        qa.prepare_review_qa(**{**prepared, "exclusion_texts": prepared["records"]})
    assert calls == []


def test_fresh_selection_excludes_prior_sentence_parent_and_near_overlap(prepared):
    records = prepared["records"]
    exclusions = [records[0], {"parent_document_id": records[1]["parent_document_id"], "text": "다른 원문"},
                  records[2]["text"] + ". 추가 문서 " * 30, records[3]["text"][:-4] + "****"]
    selected, proof = qa.select_public(records, exclusions)
    assert not {r["document_id"] for r in selected} & {r["document_id"] for r in records[:4]}
    assert proof["selection_before_generation_outputs"]
    assert not proof["pack_eligibility_used_for_selection"]
    assert not proof["retrieval_success_used_for_selection"]


def test_gold_cannot_change_prompt_source_or_simple_glossary_search(prepared):
    baseline = qa.prepare_review_qa(**prepared)[0]
    changed = deepcopy(prepared)
    for row in changed["records"]:
        if row["positive_gold"]:
            row["answer_spans"] = [[50, 55]]
            row["expected_answers"] = [row["text"][50:55]]
    for row in changed["business_records"]:
        if row["positive_gold"]:
            row["expected_answers"] = ["다른 gold 내용"]
    altered = qa.prepare_review_qa(**changed)[0]
    for name in baseline:
        for before, after in zip(baseline[name]["requests"], altered[name]["requests"], strict=True):
            for key in ("case_id", "condition", "system", "user", "source_spans", "pack_sha256"):
                assert before[key] == after[key]


def test_fixed_source_and_policy_factorials_hold_required_factors(prepared):
    envelopes = qa.prepare_review_qa(**prepared)[0]
    grouped = {}
    for row in envelopes["review_abcd"]["requests"]:
        if row["condition"].startswith("fixed_"):
            grouped.setdefault(row["document_id"], []).append(row)
    for rows in grouped.values():
        assert len({row["rendered_source_sha256"] for row in rows}) == 1
        assert len({canonical(row["source_spans"]) for row in rows}) == 1
    grouped.clear()
    for row in envelopes["review_policy"]["requests"]:
        grouped.setdefault(row["document_id"], {})[row["condition"]] = row
    for rows in grouped.values():
        assert len({row["rendered_source_sha256"] for row in rows.values()}) == 1
        assert len({row["pack_prompt"] for name, row in rows.items() if name.startswith("pack_")}) == 1
        for policy in ("evidence", "term", "document"):
            assert rows["none_" + policy]["system"] == rows["pack_" + policy]["system"]
        assert rows["none_term"]["system"] != rows["none_document"]["system"]


def test_source_priority_preserves_search_source_and_actual_total_caps(prepared):
    envelopes = qa.prepare_review_qa(**prepared)[0]
    grouped = {}
    for row in envelopes["review_budget"]["requests"]:
        grouped.setdefault(row["document_id"], {})[row["condition"]] = row
        assert row["policy_factor"] == "document"
        for model, tok in prepared["tokenizers"].items():
            actual = len(tok.apply_chat_template(
                [{"role": "system", "content": row["system"]}, {"role": "user", "content": row["user"]}],
                tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False))
            assert actual == row["prompt_tokens"][model] <= row["total_prompt_token_cap"]
            assert actual + qa.RESERVED_OUTPUT_TOKENS <= qa.MAX_MODEL_LEN
    for rows in grouped.values():
        for cap in qa.BUDGET_CAPS:
            search, selected = rows[f"cap{cap}_search"], rows[f"cap{cap}_sourcefirst"]
            assert search["source_spans"] == selected["source_spans"]
            assert search["rendered_source_sha256"] == selected["rendered_source_sha256"]
            assert search["system"] == selected["system"]


def test_should_inject_false_does_not_remove_policy_factor(prepared, monkeypatch):
    from types import SimpleNamespace

    def empty(*args, **kwargs):
        return SimpleNamespace(should_inject=False, context_pack={"empty": True},
                               prompt_fragment="should never be injected", policy_fragment=qa.QA_CONTEXT_POLICY)

    monkeypatch.setattr(qa, "prepare_llm_context", empty)
    monkeypatch.setattr("eval.extended_qa.prepare_llm_context", empty)
    envelope = qa.prepare_review_qa(**prepared)[0]["review_policy"]
    for row in envelope["requests"]:
        assert not row["pack_injected"]
        assert row["pack_prompt"] is None
        if row["condition"].endswith("_term"):
            assert qa.QA_CONTEXT_POLICY in row["system"]
        if row["condition"].endswith("_document"):
            assert qa.DOCUMENT_QA_POLICY in row["system"]


def test_novel_card_selector_keeps_whole_definition_and_exceptions(prepared):
    budget = qa.PromptBudget(prepared["tokenizers"])
    builder = qa.Builder(prepared["snapshot"], budget)
    source = "금감원이 회의를 열었다."
    full = builder.prompts("금감원의 뜻은?", source, pack="sourcefirst", policy="document")
    definition = glossary()["entities"][0]["description"]
    assert definition in full["pack_prompt"]
    cap = max(builder.prompts("금감원의 뜻은?", source, policy="document")["prompt_tokens"].values())
    trimmed = builder.prompts("금감원의 뜻은?", source, pack="sourcefirst", policy="document", cap=cap)
    assert not trimmed["pack_injected"]
    assert trimmed["residual_omitted_cards"] >= 1
    redundant_source = "금감원은 금융감독원이다. " + definition
    redundant = builder.prompts("금감원의 뜻은?", redundant_source, pack="sourcefirst", policy="document")
    assert not redundant["pack_injected"]


def test_nomiracl_keeps_complete_original_passage_order_and_qrels(prepared):
    records, identity = qa._nomiracl_sources(prepared["nomiracl_manifest"])
    assert identity["identical_duplicate_corpus_rows"] == 1
    assert all(row["provided_passages"][0]["docid"] == "negative#0" for row in records)
    envelopes = qa.prepare_review_qa(**prepared)[0]
    by_id = {row["document_id"]: row for row in records}
    for row in envelopes["review_nomiracl"]["requests"]:
        original = by_id[row["document_id"]]
        assert row["provided_passages"] == original["provided_passages"]
        assert row["official_qrels"] == original["official_qrels"]
        assert row["source_text"] == original["text"]
        assert row["source_spans"] == [[0, len(original["text"])]]
        assert row["expected_answers"] == (["YES"] if row["positive_gold"] else [])
        assert row["source_gold_visible"] is None
        assert "전체 코퍼스가 아닌 제공된 문단만" in row["user"]
        assert '"label"' not in row["user"]


def test_nomiracl_capacity_excludes_whole_question_without_dropping_passage(prepared, tmp_path):
    path = tmp_path / "large"
    path.mkdir()
    prepared["nomiracl_manifest"] = write_nomiracl(path, huge=True)
    envelopes, _, selection = qa.prepare_review_qa(**prepared)
    rows = envelopes["review_nomiracl"]["requests"]
    assert len({row["official_qid"] for row in rows}) == 2
    assert all("huge#0" not in {p["docid"] for p in row["provided_passages"]} for row in rows)
    assert selection["nomiracl"]["capacity_exclusions"]["whole_question_capacity"] >= 1
    assert selection["nomiracl"]["provided_passages_dropped"] == 0


def test_nomiracl_groups_shared_parent_articles(prepared, monkeypatch):
    monkeypatch.setattr(qa, "NOMIRACL_PER_STRATUM", 2)
    rows = qa.prepare_review_qa(**prepared)[0]["review_nomiracl"]["requests"]
    assert len({row["family_id"] for row in rows}) == 1
    assert all("negative" in row["provided_article_ids"] for row in rows)


def test_nomiracl_rejects_conflicting_corpus_duplicate(prepared, tmp_path):
    path = tmp_path / "conflict"
    path.mkdir()
    with pytest.raises(ValueError, match="conflicting duplicate"):
        qa._nomiracl_sources(write_nomiracl(path, conflict=True))


def test_nomiracl_source_hash_mismatch_is_fatal(prepared):
    key = "data/korean/qrels/test.relevant.tsv"
    prepared["nomiracl_manifest"]["files"][key]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum mismatch"):
        qa._nomiracl_sources(prepared["nomiracl_manifest"])


def test_nomiracl_duplicate_qrel_is_fatal(prepared):
    from pathlib import Path

    key = "data/korean/qrels/test.relevant.tsv"
    value = prepared["nomiracl_manifest"]["files"][key]
    path = Path(value["path"])
    path.write_text(path.read_text() + path.read_text().splitlines()[0] + "\n")
    value["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="duplicate NoMIRACL qrels"):
        qa._nomiracl_sources(prepared["nomiracl_manifest"])


def test_authored_64_case_fixture_normalizes_qa_without_resolver_gold(prepared, monkeypatch):
    from eval.review_business import load_business_records

    monkeypatch.setattr(qa, "BUSINESS_QUESTIONS", 64)
    prepared["business_records"] = load_business_records()
    envelopes, experiments, selection = qa.prepare_review_qa(**prepared)
    rows = [row for row in envelopes["review_abcd"]["requests"]
            if row["evaluation_split"] == "ai_authored_business"]
    assert len(rows) == 64 * 8
    assert len({row["document_id"] for row in rows}) == 64
    assert len({row["family_id"] for row in rows}) == 16
    assert selection["business"]["gold_constructed_from_resolver"] is False
    assert all(row["gold_origin"] == "authored_before_resolver" for row in rows)
    assert any(row["positive_gold"] and not row["answer_spans"] and row["source_gold_visible"] is None for row in rows)
    assert experiments["review_abcd"]["question_count"] == 66
    for row in rows:
        assert row["task_definition"] == "reference_grounded_qa"
        assert row["system"].startswith(qa.BUSINESS_EVIDENCE_POLICY)
        assert "원문 또는 제공된 용어집" in row["system"]
        if row["condition"].endswith(("_b", "_d")):
            assert "고정 코드·적용 조건" in row["system"]
    public = [row for row in envelopes["review_abcd"]["requests"]
              if row["evaluation_split"] == "fresh_public_context"]
    assert all(row["task_definition"] == "source_grounded_mrc" for row in public)
    assert all(row["system"].startswith(qa.EVIDENCE_POLICY) for row in public)


@pytest.mark.parametrize("pack", ["current", "simple", "sourcefirst"])
def test_too_small_pack_budget_drops_whole_cards_and_reports_bypass(prepared, pack):
    builder = qa.Builder(prepared["snapshot"], qa.PromptBudget(prepared["tokenizers"]))
    question = "금감원의 뜻은?"
    base = builder.prompts(question, "", policy="document")
    cap = max(base["prompt_tokens"].values())
    actual = builder.prompts(question, "", pack=pack, policy="document", cap=cap)
    assert not actual["pack_injected"]
    assert actual["pack_bypassed_due_to_budget"]
    assert actual["residual_omitted_cards"] >= 1
    assert all(n <= cap for n in actual["prompt_tokens"].values())
