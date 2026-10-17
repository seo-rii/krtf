"""Authored source-only fixtures for bounded independent retrieval diagnostics."""
from copy import deepcopy
import hashlib

import pytest

from eval import hf_retrieval_followup as followup
from eval.run_hf_benchmark import select_evidence


def record(identifier="authored", *, kind="SPAN", paragraphs=None, question="목표 답안은 무엇인가요?"):
    paragraphs = paragraphs or ["배경 바다 파도가 보인다.", "목표 답안은 사과나무다.", "산의 계곡에는 물이 흐른다."]
    # The suffix gives every authored article a distinct content hash.
    paragraphs = [*paragraphs, "문서 식별자 " + identifier]
    text = "\n".join(paragraphs)
    spans, cursor = [], 0
    for passage in paragraphs:
        spans.append([cursor, cursor + len(passage)])
        cursor += len(passage) + 1
    answer_start = text.find("사과나무")
    answer_span = [answer_start, answer_start + len("사과나무")]
    answer_index = next((i for i, span in enumerate(spans)
                         if span[0] <= answer_start < span[1]), 0)
    null = {"answer_type": "NO_ANSWER", "answer_span": None,
            "yes_no_answer": "NONE", "passage_index": -1}
    if kind == "NO_ANSWER":
        annotations = [deepcopy(null) for _ in range(3)]
    else:
        annotation = {"answer_type": kind,
            "answer_span": answer_span if kind == "SPAN" else None,
            "yes_no_answer": "YES" if kind == "YES_NO" else "NONE",
            "passage_index": answer_index}
        annotations = [deepcopy(annotation), deepcopy(annotation), null]
    return {"document_id": identifier, "parent_document_id": "article:" + identifier,
        "document_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "text": text, "question": question, "annotation_answers": annotations,
        "minimal_answer_evaluable": True,
        "answer_spans": [answer_span] if kind == "SPAN" else [],
        "answer_passage_spans": [spans[answer_index]] if kind != "NO_ANSWER" else [],
        "passage_candidates": spans}


def test_rows_use_matched_policy_and_original_document_order():
    source = record()
    rows = followup.build_variants(source)
    assert [row["context_condition"] for row in rows] == list(followup.METHODS)
    assert len({row["case_id"] for row in rows}) == 1
    for row in rows:
        method = row["context_condition"]
        assert row["case_id"] == "authored::followup"
        assert row["condition"] == method + "__free__r0"
        assert row["experiment"] == "retrieval"
        assert row["decoding_mode"] == "free" and row["repeat_id"] == 0
        assert row["source_spans"] == sorted(row["source_spans"])
        assert row["system"] == followup.EVIDENCE_POLICY
        rendered = "\n\n".join(source["text"][s:e] for s, e in row["source_spans"])
        assert row["user"] == "질문: " + source["question"] + "\n\n<source>\n" + rendered + "\n</source>"
        assert row["source_gold_visible"] is True
        assert row["source_text"] == source["text"]
        assert row["pack_injected"] is False
        assert row["deployable_condition"] == (method != "oracle")


@pytest.mark.parametrize("budget,top_k", [(3000, 3), (1000, 1), (1200, 2), (300, 3)])
def test_lexical_reproduces_existing_selector_without_token_filter(budget, top_k):
    source = record(paragraphs=["배경 " * 600, "목표 답안은 사과나무다." * 40,
                                "목표 " * 600, "계곡 " * 550])
    rows = followup.build_variants(source, char_budget=budget, top_k=top_k)
    assert rows[0]["source_spans"] == select_evidence(source["text"], source["question"],
        source["passage_candidates"], budget=budget, top_k=top_k)


def test_actual_token_budget_callback_applies_to_every_method_and_canonical_source():
    source = record()
    observed = []

    def fits(spans):
        observed.append(deepcopy(spans))
        assert spans == sorted(spans)
        return len(spans) <= 1 and sum(end - start for start, end in spans) <= 30

    rows = followup.build_variants(source, budget_fits=fits)
    assert observed
    for row in rows:
        assert len(row["source_spans"]) <= 1
        assert row["source_character_count"] <= 30
    assert rows[-1]["oracle_budget_fit"] is True


@pytest.mark.parametrize("method", ["lexical", "bm25", "adjacent"])
def test_deployable_rankings_never_read_gold(method):
    source = record()
    expected = followup.ranked_passages(source, method)
    for field in ("annotation_answers", "answer_spans", "answer_passage_spans", "minimal_answer_evaluable"):
        source.pop(field)
    assert followup.ranked_passages(source, method) == expected


def test_bm25_uses_frequencies_and_keeps_korean_particle_overlap():
    source = record(paragraphs=["무관 " * 200 + "한국은행 " * 20,
                                "한국은행의 결정은 사과나무에 관한 것이다.",
                                "목표 답안은 사과나무다."], question="한국은행은 어떤 결정을 내렸나요?")
    ranked = followup.ranked_passages(source, "bm25")
    assert ranked == followup.ranked_passages(source, "bm25")
    assert ranked[0] == tuple(source["passage_candidates"][1])
    assert followup._bm25_terms("한국은행은 한국은행은")['gram:한국'] == 2
    assert followup._bm25_terms("ABC 2026") == {"word:abc": 1, "word:2026": 1}


def test_adjacent_visits_neighbours_before_next_lexical_centre():
    source = record(paragraphs=["바다", "산", "목표 답안은 사과나무다.", "강", "들"])
    ranked = followup.ranked_passages(source, "adjacent")
    candidates = list(map(tuple, source["passage_candidates"]))
    assert ranked[:3] == [candidates[2], candidates[1], candidates[3]]
    assert len(ranked) == len(set(ranked)) == len(candidates)
    selected = followup.build_variants(source)[2]["source_spans"]
    assert selected == sorted([candidates[1], candidates[2], candidates[3]])


def test_oracle_is_complete_original_gold_passage_not_an_answer_window():
    source = record(paragraphs=["😀 배경", "비밀 시작 " + "서술 " * 50 + "사과나무" + " 부연" * 50, "목표 답안"])
    oracle = followup.build_variants(source)[-1]
    assert oracle["source_spans"] == [tuple(source["passage_candidates"][1])]
    assert oracle["source_spans"] != source["answer_spans"]
    assert oracle["oracle_status"] == "GOLD_PASSAGE_FITS"
    assert oracle["oracle_budget_fit"] is True
    assert oracle["oracle_uses_gold"] is True


@pytest.mark.parametrize("filter_kind", ["tokens", "characters"])
def test_oversized_oracle_is_marked_unavailable_without_truncating_or_falling_back(filter_kind):
    source = record(paragraphs=["목표", "배경 " * 30 + "사과나무", "강"])
    options = {"budget_fits": lambda spans: sum(end - start for start, end in spans) < 30}
    if filter_kind == "characters":
        options = {"char_budget": 30}
    rows = followup.build_variants(source, **options)
    oracle = rows[-1]
    assert rows[0]["source_spans"]
    assert oracle["source_spans"] == []
    assert oracle["oracle_status"] == "GOLD_PASSAGE_OVER_BUDGET"
    assert oracle["oracle_budget_fit"] is False
    assert oracle["source_gold_visible"] is False
    assert "사과나무" not in oracle["user"]


def test_absent_original_gold_passage_cannot_be_reconstructed_from_minimal_answer():
    source = record()
    source["answer_passage_spans"] = []
    oracle = followup.build_variants(source)[-1]
    assert oracle["oracle_status"] == "NO_ANNOTATED_PASSAGE"
    assert oracle["source_spans"] == []
    assert oracle["oracle_budget_fit"] is False


def test_oracle_passage_ranking_uses_positive_votes_then_original_start():
    source = record(paragraphs=["사과나무가 먼저 등장한다.", "사과나무가 다시 등장한다."])
    second = source["text"].index("사과나무", 1)
    source["annotation_answers"] = [
        {"answer_type": "SPAN", "answer_span": [second, second + 4],
         "yes_no_answer": "NONE", "passage_index": 1},
        {"answer_type": "SPAN", "answer_span": [second, second + 4],
         "yes_no_answer": "NONE", "passage_index": 1},
        {"answer_type": "SPAN", "answer_span": [0, 4],
         "yes_no_answer": "NONE", "passage_index": 0}]
    source["answer_spans"] = [[0, 4], [second, second + 4]]
    source["answer_passage_spans"] = source["passage_candidates"][:2]
    assert followup.ranked_passages(source, "oracle") == [
        tuple(source["passage_candidates"][1]), tuple(source["passage_candidates"][0])]


def test_negative_oracle_is_exactly_matched_lexical_without_gold_visibility_credit():
    source = record(kind="NO_ANSWER")
    rows = followup.build_variants(source)
    lexical, oracle = rows[0], rows[-1]
    assert oracle["source_spans"] == lexical["source_spans"]
    assert oracle["user"] == lexical["user"]
    assert oracle["oracle_status"] == "NEGATIVE_MATCHED_LEXICAL"
    assert oracle["oracle_uses_gold"] is False
    assert oracle["oracle_budget_fit"] is None
    assert all(row["source_gold_visible"] is None for row in rows)


def test_yes_no_visibility_requires_full_original_passage():
    source = record(kind="YES_NO")
    rows = followup.build_variants(source)
    assert all(row["source_gold_visible"] is True for row in rows)
    blocked = followup.build_variants(source, budget_fits=lambda spans:
        not any(s <= source["answer_passage_spans"][0][0] and source["answer_passage_spans"][0][1] <= e
                for s, e in spans))
    assert all(row["source_gold_visible"] is False for row in blocked)


@pytest.mark.parametrize("key,span", [("passage_candidates", [-1, 2]),
    ("passage_candidates", [0, 10000]), ("passage_candidates", [True, 2]),
    ("answer_passage_spans", [0, 10000])])
def test_invalid_source_spans_fail_closed(key, span):
    source = record()
    source[key] = [span]
    with pytest.raises(ValueError, match="span|source"):
        followup.build_variants(source)


@pytest.mark.parametrize("kwargs", [{"char_budget": 0}, {"char_budget": True}, {"top_k": 0}, {"top_k": 1.5}])
def test_invalid_budgets_are_rejected(kwargs):
    with pytest.raises(ValueError, match="budget"):
        followup.build_variants(record(), **kwargs)


def test_source_hash_gold_and_method_validation():
    source = record()
    source["text"] += "changed"
    with pytest.raises(ValueError, match="source text changed"):
        followup.build_variants(source)
    source = record()
    source["minimal_answer_evaluable"] = False
    with pytest.raises(ValueError, match="unscorable source gold"):
        followup.build_variants(source)
    with pytest.raises(ValueError, match="unknown retrieval method"):
        followup.ranked_passages(record(), "mystery")


def test_empty_source_candidates_do_not_fabricate_evidence():
    source = record(kind="NO_ANSWER")
    source["passage_candidates"] = []
    rows = followup.build_variants(source)
    assert all(row["source_spans"] == [] for row in rows)


def test_selection_is_order_independent_parent_and_content_disjoint():
    sources = [record(f"{kind}-{i}", kind=kind) for kind in followup.QUOTAS for i in range(5)]
    # Exclude a complete old parent and an old content copy separately.
    old_parent = sources[0]["parent_document_id"]
    old_sha = sources[1]["document_sha256"]
    # Two distinct question IDs for one article must never both be selected.
    duplicate = deepcopy(sources[2])
    duplicate["document_id"] += "-another-question"
    sources.append(duplicate)
    quotas = {"SPAN": 2, "YES_NO": 1, "NO_ANSWER": 2}
    options = dict(excluded_parents=[old_parent], excluded_hashes=[old_sha], quotas=quotas)
    selected, inventory = followup.choose_heldout(sources, **options)
    reversed_selected, reversed_inventory = followup.choose_heldout(list(reversed(sources)), **options)
    assert selected == reversed_selected and inventory == reversed_inventory
    assert len(selected) == 5
    assert len({r["parent_document_id"] for r in selected}) == 5
    assert len({r["document_sha256"] for r in selected}) == 5
    assert all(row["parent_document_id"] != old_parent and row["document_sha256"] != old_sha for row in selected)
    assert inventory["selected_by_stratum"] == quotas
    assert inventory["exclusions"] == {"prior_parent_or_content_overlap": 2}
    assert inventory["selection_before_generation_outputs"] is True


def test_selection_capacity_rule_and_insufficiency_are_explicit():
    sources = [record("fits"), record("blocked")]
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA") as caught:
        followup.choose_heldout(sources, quotas={"SPAN": 2}, eligible=lambda row: row["document_id"] == "fits")
    assert caught.value.inventory["selected_by_stratum"] == {"SPAN": 1}
    assert caught.value.inventory["exclusions"] == {"predeclared_capacity_rule": 1}


def test_selection_rejects_duplicate_source_id_and_skips_unscorable_gold():
    with pytest.raises(ValueError, match="duplicate source question"):
        followup.choose_heldout([record(), record()], quotas={"SPAN": 1})
    source = record("invalid")
    source["minimal_answer_evaluable"] = False
    selected, inventory = followup.choose_heldout([source, record("valid")], quotas={"SPAN": 1})
    assert [r["document_id"] for r in selected] == ["valid"]
    assert inventory["exclusions"] == {"invalid_minimal_offsets": 1}


@pytest.mark.parametrize("quotas", [{}, {"UNKNOWN": 1}, {"SPAN": -1}, {"SPAN": True}])
def test_invalid_selection_quotas(quotas):
    with pytest.raises(ValueError, match="quotas"):
        followup.choose_heldout([record()], quotas=quotas)


def test_aggregate_cpu_report_preserves_visibility_denominators_and_no_raw_text():
    sources = [record("span"), record("yes", kind="YES_NO"), record("null", kind="NO_ANSWER")]
    report = followup.evaluate_retrieval(sources)
    assert report["questions"] == 3
    assert report["llm_accuracy_measured"] is False
    assert report["entity_linking_measured"] is False
    assert report["oracle_deployable"] is False
    assert report["deployable_winner_by_visibility"] == "lexical"
    for method, values in report["methods"].items():
        assert values["questions"] == 3
        assert values["positive_questions"] == values["gold_visible"] == 2
        assert values["gold_visibility_rate"] == 1
        assert values["gold_informed_diagnostic"] == (method == "oracle")
        assert values["by_stratum"]["NO_ANSWER"]["gold_visible"] == 0
    serialized = repr(report)
    assert all(source["text"] not in serialized and source["question"] not in serialized for source in sources)
    assert "expected_answers" not in serialized and "document_id" not in serialized


def test_aggregate_token_budget_factory_is_invoked_per_source():
    calls = []

    def factory(source):
        calls.append(source["document_id"])
        return lambda spans: False

    result = followup.evaluate_retrieval([record("span"), record("null", kind="NO_ANSWER")],
                                        budget_fits_factory=factory)
    assert calls == ["span", "null"]
    assert result["additional_actual_token_budget_enforced"] is True
    assert result["methods"]["oracle"]["oracle_unavailable"] == 1
    assert all(method["gold_visible"] == 0 and method["empty_sources"] == 2
               for method in result["methods"].values())
