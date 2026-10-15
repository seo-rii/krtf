"""Authored generation-contract fixtures; no downloads or model inference."""

from copy import deepcopy
import hashlib
import json

import pytest

from eval import hf_qa
from ktrf import compile_snapshot, load_glossary


def _annotation(kind, span=None, yes="NONE"):
    return {"answer_type": kind, "answer_span": span,
            "yes_no_answer": yes,
            "passage_index": -1 if kind == "NO_ANSWER" else 0}


def _record(document_id="authored-1", kind="SPAN", surface="사과나무"):
    text = f"😀 금감원 담당자는 {surface}를 조사했다.\n바다 파도가 보인다."
    split = text.index("\n")
    start = text.index(surface)
    span = [start, start + len(surface)]
    if kind == "SPAN":
        annotations = [_annotation("SPAN", span), _annotation("SPAN", span),
                       _annotation("NO_ANSWER")]
    elif kind == "YES_NO":
        annotations = [_annotation("YES_NO", yes="YES"),
                       _annotation("YES_NO", yes="YES"), _annotation("NO_ANSWER")]
    elif kind == "NO_ANSWER":
        annotations = [_annotation("NO_ANSWER") for _ in range(3)]
    else:
        raise AssertionError("unsupported authored stratum")
    return {"document_id": document_id, "parent_document_id": "article-" + document_id,
            "document_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "text": text, "question": "금감원 담당자는 어떤 나무를 조사했나요?",
            "annotation_answers": annotations, "minimal_answer_evaluable": True,
            "answer_spans": [span] if kind == "SPAN" else [],
            "answer_passage_spans": [[0, split]] if kind != "NO_ANSWER" else [],
            "passage_candidates": [[0, split], [split + 1, len(text)]]}


@pytest.fixture(scope="module")
def snapshot():
    glossary = load_glossary({
        "glossary_id": "hf-qa-authored", "version": "1", "schema_version": "3",
        "entities": [{"entity_id": "E_FSS", "canonical": "금융감독원",
                      "description": "금융기관을 검사하고 감독하는 기관"}],
        "alias_families": [{"family_id": "F_FSS", "representative": "금감원"}],
        "alias_bindings": [{"alias_id": "A_FSS", "family_id": "F_FSS",
                            "entity_id": "E_FSS", "surface": "금감원"}],
    })
    return compile_snapshot(glossary, run_conformance=False)


@pytest.fixture
def rows(snapshot):
    return [row for kind in hf_qa.QUOTAS
            for row in hf_qa.build_question_requests(_record(kind, kind), snapshot)]


def _output(row, value=None, *, status="RECEIVED"):
    return {"case_id": row["case_id"], "condition": row["condition"],
            "status": status, "response": {"answer": value}}


def test_gold_uses_two_nonnull_votes_and_all_acceptable_span_answers():
    record = _record()
    short_start = record["text"].index("나무")
    record["annotation_answers"][1]["answer_span"] = [short_start, short_start + 2]
    gold = hf_qa.classify_gold(record)
    assert gold == {"stratum": "SPAN", "positive": True,
                    "expected_answers": ["나무", "사과나무"], "nonnull_votes": 2,
                    "reason": None}
    record["annotation_answers"][1] = _annotation("NO_ANSWER")
    rejected = hf_qa.classify_gold(record)
    assert rejected["stratum"] == "EXCLUDED" and rejected["positive"] is None
    assert rejected["nonnull_votes"] == 1
    assert rejected["reason"] == "passage_only_or_disputed_minimal_vote"


def test_gold_keeps_yes_no_and_unanimous_article_no_answer_separate():
    yes = hf_qa.classify_gold(_record(kind="YES_NO"))
    assert yes["stratum"] == "YES_NO" and yes["positive"] is True
    assert yes["expected_answers"] == ["YES"] and yes["nonnull_votes"] == 2
    no_answer = hf_qa.classify_gold(_record(kind="NO_ANSWER"))
    assert no_answer == {"stratum": "NO_ANSWER", "positive": False,
                         "expected_answers": [], "nonnull_votes": 0, "reason": None}


@pytest.mark.parametrize("count", [0, 1, 2, 4, 5])
def test_unexpected_gold_annotation_count_is_excluded(count):
    record = _record(kind="NO_ANSWER")
    record["annotation_answers"] = [_annotation("NO_ANSWER") for _ in range(count)]
    assert hf_qa.classify_gold(record)["reason"] == "unexpected_annotation_count"


def test_mixed_span_yesno_passage_only_and_invalid_gold_are_not_repaired():
    record = _record()
    record["annotation_answers"][1] = _annotation("YES_NO", yes="YES")
    assert hf_qa.classify_gold(record)["reason"] == "mixed_span_and_yesno"
    record["annotation_answers"] = [_annotation("PASSAGE_ONLY") for _ in range(3)]
    assert hf_qa.classify_gold(record)["reason"] == "passage_only_or_disputed_minimal_vote"
    record = _record()
    record["minimal_answer_evaluable"] = False
    # Even two intact alternatives do not rescue a question with invalid source gold.
    assert hf_qa.classify_gold(record)["reason"] == "invalid_minimal_offsets"


@pytest.mark.parametrize("value,expected", [
    ("  예  ", "yes"), ("네", "yes"), ("YES", "yes"),
    ("아니오", "no"), ("아니요", "no"), ("NO", "no"),
    ("  1.2\tKG  ", "1.2 kg"), ("\u1100\u1161", "가"),
])
def test_normalization_is_literal_and_preserves_numeric_punctuation(value, expected):
    assert hf_qa.normalize_answer(value, yes_no=True) == expected
    assert hf_qa.normalize_answer("1.2") != hf_qa.normalize_answer("12")
    assert hf_qa.normalize_answer("-3") != hf_qa.normalize_answer("3")
    assert hf_qa.normalize_answer("1,000") != hf_qa.normalize_answer("1000")


def test_yes_no_aliases_cannot_rewrite_quoted_span_answers():
    assert hf_qa.normalize_answer("예") == "예"
    assert hf_qa.normalize_answer("네") == "네"
    assert hf_qa.normalize_answer("아니요") == "아니요"
    assert hf_qa.normalize_answer("예", yes_no=True) == "yes"
    assert hf_qa.character_f1("네", "YES") == 0


def test_character_f1_is_only_partial_overlap_not_semantic_or_exact_correctness():
    assert hf_qa.character_f1("사과나무", "사과") == pytest.approx(2 / 3)
    assert hf_qa.character_f1("무관", "사과") == 0
    assert hf_qa.character_f1("네", "YES", yes_no=True) == 1
    # A character multiset cannot establish answer correctness or digit ordering.
    assert hf_qa.character_f1("1969", "1996") == 1
    assert hf_qa.normalize_answer("1969") != hf_qa.normalize_answer("1996")


def test_screening_is_fixed_by_source_ids_and_strata_before_resolver_outputs(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("screening must not invoke the resolver or context builder")

    monkeypatch.setattr(hf_qa, "resolve", forbidden)
    monkeypatch.setattr(hf_qa, "prepare_llm_context", forbidden)
    monkeypatch.setattr(hf_qa, "QUOTAS", {"SPAN": 2, "YES_NO": 1, "NO_ANSWER": 2})
    records = [_record(f"{kind}-{index}", kind) for kind in hf_qa.QUOTAS for index in range(8)]
    excluded = _record("invalid")
    excluded["minimal_answer_evaluable"] = False
    records.append(excluded)
    selected, inventory = hf_qa.build_screening_pool(records, multiplier=2)
    changed = deepcopy(list(reversed(records)))
    for record in changed:
        record["model_response"] = {"answer": "a misleading previous model answer"}
        record["resolver_output"] = {"link_decision": "RESOLVED"}
    after, reversed_inventory = hf_qa.build_screening_pool(changed, multiplier=2)
    assert [r["document_id"] for r in selected] == [r["document_id"] for r in after]
    assert inventory == reversed_inventory
    assert inventory["source_questions"] == 25
    assert inventory["eligible_by_stratum"] == {"SPAN": 8, "YES_NO": 8, "NO_ANSWER": 8}
    assert inventory["screened_by_stratum"] == {"SPAN": 4, "YES_NO": 2, "NO_ANSWER": 4}
    assert inventory["source_exclusions"] == {"invalid_minimal_offsets": 1}
    assert len(selected) == 10


@pytest.mark.parametrize("multiplier", [0, -1])
def test_screening_rejects_nonpositive_multiplier(multiplier):
    with pytest.raises(ValueError, match="positive pool multiplier"):
        hf_qa.build_screening_pool([_record()], multiplier=multiplier)


def test_six_arms_preserve_gold_complete_original_and_actual_visible_source(snapshot):
    record = _record()
    original = deepcopy(record)
    requests = hf_qa.build_question_requests(record, snapshot)
    assert record == original
    assert tuple(row["condition"] for row in requests) == hf_qa.CONDITIONS
    assert hf_qa.validate_requests(requests) == requests
    by_condition = {row["condition"]: row for row in requests}
    for row in requests:
        assert row["source_text"] == record["text"]
        assert row["document_sha256"] == hashlib.sha256(record["text"].encode()).hexdigest()
        assert row["expected_answers"] == ["사과나무"]
        assert row["positive_gold"] is True
        rendered = "\n\n".join(record["text"][s:e] for s, e in row["source_spans"])
        assert "<source>\n" + rendered + "\n</source>" in row["user"]
    for condition in ("none_knowledge", "none_evidence"):
        row = by_condition[condition]
        assert row["source_spans"] == [] and row["source_gold_visible"] is False
        assert record["text"] not in row["user"]
        assert "사과나무" not in row["user"]
    assert by_condition["full"]["source_spans"] == [(0, len(record["text"]))]
    assert record["text"] in by_condition["full"]["user"]
    assert by_condition["retrieved"]["source_spans"] == by_condition["ktrf_pack"]["source_spans"]
    assert by_condition["ktrf_expanded"]["query_expansion_count"] == 1
    assert by_condition["ktrf_pack"]["pack_injected"] is True
    assert by_condition["ktrf_pack"]["pack_sha256"]
    for condition in ("none_evidence", "full", "retrieved", "ktrf_expanded"):
        assert by_condition[condition]["system"] == hf_qa.EVIDENCE_POLICY
    assert by_condition["none_knowledge"]["system"] == hf_qa.KNOWLEDGE_POLICY
    assert by_condition["ktrf_pack"]["system"].startswith(hf_qa.EVIDENCE_POLICY)


def test_request_inputs_are_independent_of_source_gold_offsets(snapshot):
    original = _record()
    changed = deepcopy(original)
    changed["answer_spans"] = [[0, 1]]
    for annotation in changed["annotation_answers"]:
        if annotation["answer_type"] == "SPAN":
            annotation["answer_span"] = [0, 1]
    before = hf_qa.build_question_requests(original, snapshot)
    after = hf_qa.build_question_requests(changed, snapshot)
    for first, second in zip(before, after):
        assert first["expected_answers"] != second["expected_answers"]
        assert first["system"] == second["system"]
        assert first["user"] == second["user"]
        assert first["source_spans"] == second["source_spans"]


def test_excluded_gold_cannot_enter_generation_requests(snapshot):
    record = _record()
    record["minimal_answer_evaluable"] = False
    with pytest.raises(ValueError, match="unscorable source gold"):
        hf_qa.build_question_requests(record, snapshot)


@pytest.mark.parametrize("mutation,message", [
    (lambda rows: rows[0].update(source_text="changed original"), "source text changed"),
    (lambda rows: rows[0].update(expected_answers=["different gold"]), "conditions disagree"),
    (lambda rows: rows[0].update(question="different question"), "rendered prompt differs"),
    (lambda rows: rows[0].update(parent_document_id="different parent"), "conditions disagree"),
    (lambda rows: rows[0].update(source_spans=[[-1, 1]]), "outside document"),
    (lambda rows: rows[0].update(condition="unknown"), "condition/task"),
    (lambda rows: rows[0].update(task="structured_routing"), "condition/task"),
    (lambda rows: rows[0].update(positive_gold=False), "stratum disagrees"),
])
def test_frozen_matrix_rejects_changed_sources_gold_and_contract(rows, mutation, message):
    mutation(rows)
    with pytest.raises(ValueError, match=message):
        hf_qa.validate_requests(rows)


@pytest.mark.parametrize("change", ["missing_arm", "duplicate_arm", "empty"])
def test_frozen_matrix_requires_all_six_conditions(rows, change):
    if change == "missing_arm":
        rows.pop(0)
    elif change == "duplicate_arm":
        # Both use evidence policy, so this reaches the matrix check itself.
        rows[2]["condition"] = rows[3]["condition"]
    else:
        rows.clear()
    with pytest.raises(ValueError, match="six-condition|nonempty"):
        hf_qa.validate_requests(rows)


def test_request_file_roundtrip_requires_frozen_protocol(tmp_path, rows):
    path = tmp_path / "authored-requests.json"
    envelope = {"protocol": {"kind": hf_qa.PROTOCOL_ID, "phase": "FINAL_FROZEN"},
                "provenance": {"authored": True},
                "requests": rows}
    path.write_text(json.dumps(envelope, ensure_ascii=False))
    loaded, protocol, provenance = hf_qa.load_request_file(path)
    assert len(loaded) == len(rows) and protocol == envelope["protocol"]
    assert provenance == {"authored": True}
    envelope["protocol"]["kind"] = "unrelated-protocol"
    path.write_text(json.dumps(envelope))
    with pytest.raises(ValueError, match="wrong HF QA protocol"):
        hf_qa.load_request_file(path)


@pytest.mark.parametrize("phase", [None, "SCREENING_POOL", "screening", "FINAL"])
def test_screening_or_unsealed_request_files_cannot_be_inferred(tmp_path, rows, phase):
    protocol = {"kind": hf_qa.PROTOCOL_ID}
    if phase is not None:
        protocol["phase"] = phase
    path = tmp_path / "not-final.json"
    path.write_text(json.dumps({"protocol": protocol, "provenance": {}, "requests": rows}))
    with pytest.raises(ValueError, match="screening pools cannot be used for live inference"):
        hf_qa.load_request_file(path)


@pytest.mark.parametrize("field", ["user", "system"])
def test_rendered_prompt_cannot_change_without_the_frozen_source_or_policy(rows, field):
    row = next(row for row in rows if row["condition"] == "retrieved")
    row[field] += "\nEXTRA UNFROZEN INSTRUCTION"
    with pytest.raises(ValueError, match="rendered prompt differs"):
        hf_qa.validate_requests(rows)


def _rerender_source(row):
    rendered = "\n\n".join(row["source_text"][s:e] for s, e in row["source_spans"])
    row["user"] = "질문: " + row["question"] + "\n\n<source>\n" + rendered + "\n</source>"
    if row["pack_injected"]:
        row["user"] += "\n\n<terminology>\n" + row["pack_prompt"] + "\n</terminology>"


@pytest.mark.parametrize("condition", ["none_knowledge", "none_evidence"])
def test_no_context_metadata_and_prompt_cannot_smuggle_an_original_passage(rows, condition):
    row = next(row for row in rows if row["condition"] == condition)
    row["source_spans"] = [(0, len(row["source_text"]))]
    _rerender_source(row)
    with pytest.raises(ValueError, match="no-context conditions cannot include source passages"):
        hf_qa.validate_requests(rows)


def test_full_source_cannot_be_silently_shortened_even_with_consistent_rendering(rows):
    row = next(row for row in rows if row["condition"] == "full")
    row["source_spans"] = [(0, len(row["source_text"]) - 1)]
    _rerender_source(row)
    with pytest.raises(ValueError, match="full-source condition must preserve"):
        hf_qa.validate_requests(rows)


def test_pack_must_add_to_the_same_retrieved_source_instead_of_replacing_it(rows):
    row = next(row for row in rows if row["condition"] == "ktrf_pack")
    row["source_spans"] = [(len(row["source_text"]) - 3, len(row["source_text"]))]
    _rerender_source(row)
    with pytest.raises(ValueError, match="retain the matched retrieved passages"):
        hf_qa.validate_requests(rows)


@pytest.mark.parametrize("field", ["pack_prompt", "pack_policy"])
def test_injected_pack_fragments_are_frozen_and_required(rows, field):
    row = next(row for row in rows if row["condition"] == "ktrf_pack")
    assert row["pack_injected"] and row[field]
    original = row[field]
    row[field] += " CHANGED"
    with pytest.raises(ValueError, match="rendered prompt differs"):
        hf_qa.validate_requests(rows)
    row[field] = ""
    with pytest.raises(ValueError, match="injected pack needs its frozen fragments"):
        hf_qa.validate_requests(rows)
    row[field] = original
    hf_qa.validate_requests(rows)


@pytest.mark.parametrize("response", [None, [], "answer", {}, {"answer": ""},
    {"answer": " \n\t"}, {"answer": 1}, {"answer": False}, {"answer": []},
    {"answer": {"text": "yes"}}, {"answer": None, "extra": "unexpected"}])
def test_response_contract_rejects_empty_malformed_and_additional_fields(response):
    assert hf_qa.response_error(response) is not None


@pytest.mark.parametrize("answer", [None, "YES", "NO", "0", "사과나무"])
def test_response_contract_accepts_explicit_null_or_nonempty_string(answer):
    assert hf_qa.response_error({"answer": answer}) is None


@pytest.mark.parametrize("corruption", ["missing", "empty", "extra", "wrong_type", "api_error"])
def test_unavailable_or_malformed_output_never_earns_null_credit(rows, corruption):
    selected = [row for row in rows if row["stratum"] == "NO_ANSWER"]
    outputs = [_output(row) for row in selected]
    target = outputs[0]
    if corruption == "missing":
        outputs.pop(0)
    elif corruption == "empty":
        target["response"]["answer"] = ""
    elif corruption == "extra":
        target["response"]["extra"] = "irrelevant"
    elif corruption == "wrong_type":
        target["response"]["answer"] = False
    else:
        target["status"] = "ERROR"
    graded = hf_qa.grade_outputs(selected, outputs)
    damaged = next(case for case in graded["cases"] if case["condition"] == "none_knowledge")
    assert not damaged["null"] and not damaged["nonnull"] and not damaged["exact_match"]
    assert damaged["missing"] is (corruption == "missing")
    assert damaged["malformed"] is (corruption != "missing")
    assert graded["by_condition"]["none_knowledge"]["article_no_answer_null"] == 0


def test_explicit_null_counts_as_abstention_but_not_positive_answer(rows):
    graded = hf_qa.grade_outputs(rows, [_output(row) for row in rows])
    for condition, result in graded["by_condition"].items():
        assert result["planned"] == 3
        assert result["positive_planned"] == 2 and result["positive_exact"] == 0
        assert result["positive_null"] == 2 and result["article_no_answer_null"] == 1
        assert result["malformed"] == result["missing"] == 0
        assert result["closed_book_no_answer_outcome_unjudged"] is (condition == "none_knowledge")


def test_no_answer_closed_book_answers_remain_unjudged_with_separate_positive_score(rows):
    outputs = [_output(row, "사과나무" if row["stratum"] == "SPAN"
                       else "네" if row["stratum"] == "YES_NO"
                       else "independent knowledge may answer this") for row in rows]
    graded = hf_qa.grade_outputs(rows, outputs)
    knowledge = graded["by_condition"]["none_knowledge"]
    assert knowledge["positive_exact"] == knowledge["positive_planned"] == 2
    assert knowledge["positive_character_f1_sum"] == 2
    assert knowledge["article_no_answer_nonnull"] == 1
    assert knowledge["closed_book_no_answer_outcome_unjudged"] is True
    assert graded["by_condition"]["full"]["closed_book_no_answer_outcome_unjudged"] is False


def test_span_grading_cannot_award_yes_no_alias_credit(snapshot):
    record = _record("quoted-word", surface="예")
    record["question"] = "금감원 담당자가 조사한 글자는 무엇인가요?"
    rows = hf_qa.build_question_requests(record, snapshot)
    graded = hf_qa.grade_outputs(rows, [_output(row, "YES") for row in rows])
    assert all(not case["exact_match"] for case in graded["cases"])
    assert all(case["character_f1"] == 0 for case in graded["cases"])
    literal = hf_qa.grade_outputs(rows, [_output(row, "예") for row in rows])
    assert all(case["exact_match"] for case in literal["cases"])


def test_unknown_or_duplicate_outputs_are_rejected(rows):
    output = _output(rows[0])
    with pytest.raises(ValueError, match="unknown/duplicate"):
        hf_qa.grade_outputs(rows, [output, deepcopy(output)])
    changed = deepcopy(output)
    changed["condition"] = "unregistered-condition"
    with pytest.raises(ValueError, match="unknown/duplicate"):
        hf_qa.grade_outputs(rows, [changed])


def test_paired_flips_exclude_incomplete_cases_and_separate_real_answer_changes(rows):
    outputs = [_output(row, "사과나무" if row["stratum"] == "SPAN" else None) for row in rows]
    for output in outputs:
        if output["condition"] == "ktrf_pack" and output["case_id"].startswith("SPAN::"):
            output["response"]["answer"] = None
        if output["condition"] == "ktrf_pack" and output["case_id"].startswith("YES_NO::"):
            output["response"]["answer"] = "YES"
        if output["condition"] == "full" and output["case_id"].startswith("NO_ANSWER::"):
            output["response"]["answer"] = ""
    graded = hf_qa.grade_outputs(rows, outputs)
    assert graded["paired"]["retrieved_to_ktrf_pack"] == {
        "comparable": 3, "incomplete_or_malformed": 0, "helpful": 1, "harmful": 1}
    assert graded["paired"]["retrieved_to_full"] == {
        "comparable": 2, "incomplete_or_malformed": 1, "helpful": 0, "harmful": 0}
