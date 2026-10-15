"""Authored diagnostics fixtures; no corpus downloads or neural inference."""

from copy import deepcopy
import hashlib
import json

import pytest

from eval import run_hf_benchmark as benchmark


def _ner_record(document_id, terms):
    text, annotations = "", []
    for kind, surface in terms:
        if text:
            text += " "
        start = len(text)
        text += surface
        annotations.append({"span": [start, len(text)], "surface": surface, "type": kind})
    sha = hashlib.sha256(text.encode()).hexdigest()
    return {"document_id": document_id, "parent_document_id": sha,
            "document_sha256": sha, "text": text, "ner_annotations": annotations}


def _mention(start, end, decision="UNJUDGED"):
    return {"span": {"codepoint": {"start": start, "end": end}},
            "link_decision": decision}


@pytest.fixture
def glossary():
    return benchmark.reference_catalog([_ner_record("training", [("ORG", "한전")])])[0]


def _question(document_id, *, answers=(), passages=(), yes_no=()):
    text = "😀 사과 나무의 잎.\n바다 파도와 배."
    split = text.index("\n")
    return {"document_id": document_id, "parent_document_id": "same-article",
            "document_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "text": text, "question": "사과 나무의 잎은?",
            "passage_candidates": [[0, split], [split + 1, len(text)]],
            "answer_spans": list(answers), "answer_passage_spans": list(passages),
            "yes_no_answers": list(yes_no),
            "no_answer": not (answers or passages or yes_no)}


def test_partition_groups_duplicate_content_and_is_input_order_independent():
    originals = [_ner_record(f"document-{index}", [("ORG", f"용어{index:03d}")])
                 for index in range(40)]
    duplicate = {**deepcopy(originals[0]), "document_id": "duplicate-row"}
    training, heldout, duplicates = benchmark.partition_ner([*originals, duplicate])
    reverse_training, reverse_heldout, reverse_duplicates = benchmark.partition_ner(
        list(reversed([*originals, duplicate])))
    training_hashes = {row["document_sha256"] for row in training}
    heldout_hashes = {row["document_sha256"] for row in heldout}
    assert training_hashes and heldout_hashes
    assert not training_hashes & heldout_hashes
    assert len(training) + len(heldout) == len(originals)
    assert duplicates == reverse_duplicates == 1
    assert training_hashes == {row["document_sha256"] for row in reverse_training}
    assert heldout_hashes == {row["document_sha256"] for row in reverse_heldout}


def test_partition_rejects_conflicting_labels_for_identical_source():
    original = _ner_record("first", [("ORG", "같은기관")])
    conflict = deepcopy(original)
    conflict["document_id"] = "second"
    conflict["ner_annotations"][0]["type"] = "PER"
    with pytest.raises(ValueError, match="conflicting NER labels"):
        benchmark.partition_ner([original, conflict])


def test_selection_is_deterministic_and_cannot_use_reference_labels():
    records = [_ner_record(str(index), [("ORG", f"대상{index}")]) for index in range(12)]
    selected = benchmark.select_records(records, 4)
    changed = deepcopy(records)
    for row in changed:
        row["ner_annotations"] = []
    assert [row["document_id"] for row in selected] == [
        row["document_id"] for row in benchmark.select_records(list(reversed(changed)), 4)]
    assert len(benchmark.select_records(records, 100)) == len(records)


@pytest.mark.parametrize("limit", [0, -1])
def test_selection_rejects_nonpositive_limits(limit):
    with pytest.raises(ValueError, match="positive"):
        benchmark.select_records([], limit)


def test_catalog_is_train_only_frequency_capped_and_type_surface_scoped():
    training = [_ner_record("training", [("ORG", f"용어{index:04d}") for index in range(515)])]
    training.append(_ner_record("frequent", [("ORG", "용어0514"), ("ORG", "한")]))
    heldout = _ner_record("heldout", [("ORG", "평가전용기관")])
    glossary, data = benchmark.reference_catalog(training)
    assert len(glossary.entities) == len(data["entities"]) == 512
    canonicals = [entity["canonical"] for entity in data["entities"]]
    assert canonicals[0] == "용어0514"
    assert "용어0513" not in canonicals and "한" not in canonicals
    assert heldout["ner_annotations"][0]["surface"] not in canonicals
    heldout["ner_annotations"][0]["surface"] = "바뀐평가정답"
    assert benchmark.reference_catalog(training)[1] == data
    assert all(entity["metadata"]["identity_scope"] == "type_surface_reference_only"
               for entity in data["entities"])
    _, two_types = benchmark.reference_catalog(
        [_ner_record("types", [("ORG", "동일명칭"), ("PER", "동일명칭")])])
    assert len(two_types["entities"]) == 2
    assert len({entity["entity_id"] for entity in two_types["entities"]}) == 2


def test_boundary_counts_separate_exact_overlap_and_unjudged_outputs():
    text = "😀대한 병원 미등록 기타"
    record = {"text": text, "ner_annotations": [
        {"span": [1, 3], "surface": "대한", "type": "ORG"},
        {"span": [4, 6], "surface": "병원", "type": "ORG"},
        {"span": [7, 10], "surface": "미등록", "type": "OTHER"},
    ]}
    mentions = [_mention(1, 3, "RESOLVED"), _mention(1, 3, "RESOLVED"),
                _mention(4, 5), _mention(11, 13, "RESOLVED")]
    counts, by_type = benchmark.boundary_counts(record, mentions, {"대한"})
    assert text[1:3] == "대한"  # Dict offsets are codepoints, not UTF-8 bytes or UTF-16 units.
    assert counts["reference_spans"] == 3  # Unregistered references remain in the denominator.
    assert counts["prediction_spans"] == 3  # Duplicate output spans count once.
    assert counts["exact_reference_hits"] == 1
    assert counts["overlap_reference_hits"] == 2
    assert counts["resolved_exact_reference_hits"] == 1
    assert counts["off_reference_predictions_unjudged"] == 2
    assert counts["resolved_outputs_unjudged"] == 2
    assert counts["alias_representable_reference_count"] == 1
    assert counts["exact_representable_hits"] == 1
    assert by_type["ORG"]["reference_spans"] == 2
    assert by_type["OTHER"]["reference_spans"] == 1
    assert not any("precision" in key or "false_positive" in key for key in counts)


def test_boundary_evaluation_uses_real_resolver_and_reports_mode_agreement(glossary):
    row = _ner_record("source", [("ORG", "한전"), ("OTHER", "미등록")])
    row["text"] = "😀 " + row["text"]
    row["document_sha256"] = hashlib.sha256(row["text"].encode()).hexdigest()
    for annotation in row["ner_annotations"]:
        annotation["span"] = [offset + 2 for offset in annotation["span"]]
    report, ledgers = benchmark.evaluate_boundaries([row], glossary)
    assert set(report["modes"]) == {"literal", "fast", "commit", "aggressive"}
    assert report["commit_aggressive_agreement"] == {
        "compared_successful_documents": 1, "different_mention_responses": 0}
    assert ledgers["commit"][0]["counts"] == ledgers["aggressive"][0]["counts"]
    for mode in report["modes"].values():
        assert mode["documents"] == 1 and mode["reference_spans"] == 2
        assert mode["failure_count"] == 0
        assert mode["catalog_reference_coverage"] == .5
        assert mode["semantic_precision_evaluated"] is False
        assert mode["entity_linking_evaluated"] is False
    assert report["modes"]["literal"]["exact_reference_recall"] == .5


def test_boundary_failures_keep_all_documents_and_reference_denominators(glossary, monkeypatch):
    records = [_ner_record("first", [("ORG", "한전"), ("OTHER", "미등록")]),
               _ner_record("second", [("ORG", "한전")])]

    def fail(*args, **kwargs):
        raise RuntimeError("authored resolver failure")

    monkeypatch.setattr(benchmark, "resolve", fail)
    report, ledgers = benchmark.evaluate_boundaries(records, glossary, modes=("commit", "aggressive"))
    for mode, summary in report["modes"].items():
        assert summary["documents"] == len(ledgers[mode]) == 2
        assert summary["reference_spans"] == 3
        assert summary["exact_reference_recall"] == summary["overlap_reference_recall"] == 0
        assert summary["failure_count"] == 2 and summary["errors"] == {"RuntimeError": 2}
        assert all(row["error"] == "RuntimeError" for row in ledgers[mode])
    assert report["commit_aggressive_agreement"]["compared_successful_documents"] == 0


def test_source_retrieval_respects_question_ranking_top_k_and_character_budget():
    text = "😀 사과 나무.\n사과 꽃.\n바다 파도."
    first_end, last_start = text.index("\n"), text.rindex("\n") + 1
    middle = (first_end + 1, last_start - 1)
    candidates = [(0, first_end), middle, (last_start, len(text))]
    assert benchmark.select_evidence(text, "사과", candidates, top_k=1) == [middle]
    assert benchmark.select_evidence(text, "사과", candidates, budget=middle[1] - middle[0]) == [middle]
    assert benchmark.select_evidence(text, "사과", candidates, budget=1) == []
    selected = benchmark.select_evidence(text, "사과", candidates, budget=30, top_k=2)
    assert len(selected) == 2 and sum(end - start for start, end in selected) <= 30
    assert all(0 <= start < end <= len(text) for start, end in selected)
    assert text[middle[0]:middle[1]] == "사과 꽃."


def test_long_passage_chunks_preserve_source_offsets_without_overlapping_budget():
    text = "😀" + "사과나무" * 700
    selected = benchmark.select_evidence(text, "사과나무", [(0, len(text))], budget=2000, top_k=3)
    assert selected and len(selected) <= 3
    assert sum(end - start for start, end in selected) <= 2000
    assert all(0 <= start < end <= len(text) and end - start <= 1000 for start, end in selected)
    assert all(first_end <= second_start for (_, first_end), (second_start, _) in zip(selected, selected[1:]))


@pytest.mark.parametrize("options", [{"budget": 0}, {"top_k": 0}, {"budget": -1}, {"top_k": -1}])
def test_retrieval_rejects_invalid_limits(options):
    with pytest.raises(ValueError, match="positive"):
        benchmark.select_evidence("사과", "사과", [(0, 2)], **options)


@pytest.mark.parametrize("span", [(-1, 1), (0, 3), (1, 1), (2, 1)])
def test_retrieval_rejects_invalid_candidate_offsets(span):
    with pytest.raises(ValueError, match="outside source"):
        benchmark.select_evidence("사과", "사과", [span])


def test_answer_containment_requires_one_complete_source_span():
    selected = [(1, 4), (6, 9)]
    assert benchmark.contains_span(selected, [1, 4])
    assert benchmark.contains_span(selected, [2, 3])
    assert not benchmark.contains_span(selected, [3, 7])
    assert not benchmark.contains_span(selected, [0, 2])
    assert not benchmark.contains_span([], [1, 2])
    record = _question("partial", answers=[[2, 4], [14, 16]], passages=[[0, 11]])
    counts = benchmark.evidence_counts(record, [(2, 4)])
    assert counts["minimal_answerable_questions"] == counts["minimal_answer_preserved"] == 1
    assert counts["annotated_passage_questions"] == 1 and counts["annotated_passage_preserved"] == 0


def test_evidence_selection_does_not_consult_gold_answers_or_passages(glossary):
    row = _question("unchanged-input", answers=[[2, 4]], passages=[[0, 11]])
    changed = deepcopy(row)
    changed["answer_spans"] = [[12, 14]]
    changed["answer_passage_spans"] = [[12, len(row["text"])]]
    _, before = benchmark.evaluate_evidence([row], glossary, budget=30, top_k=1)
    _, after = benchmark.evaluate_evidence([changed], glossary, budget=30, top_k=1)
    for condition in ("retrieved", "ktrf_expanded"):
        assert before[condition][0]["selected_spans"] == after[condition][0]["selected_spans"]
        assert before[condition][0]["counts"]["minimal_answer_preserved"] == 1
        assert after[condition][0]["counts"]["minimal_answer_preserved"] == 0


def test_evidence_evaluation_retains_multi_answer_no_answer_yes_no_and_passage_only(glossary):
    rows = [_question("multi", answers=[[2, 4], [12, 14]], passages=[[0, 11], [12, 21]]),
            _question("no-answer"),
            _question("yes-no", passages=[[0, 11]], yes_no=["YES"]),
            _question("passage-only", passages=[[12, 21]])]
    report, ledgers = benchmark.evaluate_evidence(rows, glossary, budget=30, top_k=1)
    for condition, summary in report["conditions"].items():
        assert summary["questions"] == len(ledgers[condition]) == 4
        assert {row["document_id"] for row in ledgers[condition]} == {row["document_id"] for row in rows}
        assert summary["minimal_answerable_questions"] == 1
        assert summary["no_minimal_answer_questions"] == 3
        assert summary["annotated_passage_questions"] == 3
        assert summary["questions_with_yes_no_annotation"] == 1
        assert summary["llm_answer_accuracy_evaluated"] is False
        assert summary["failure_count"] == 0
    assert report["conditions"]["none"]["minimal_answer_preservation"] == 0
    assert report["conditions"]["full"]["minimal_answer_preservation"] == 1
    assert report["conditions"]["full"]["annotated_passage_preservation"] == 1
    assert report["conditions"]["full"]["mean_selected_characters"] == len(rows[0]["text"])


def test_prior_document_audit_collects_both_content_and_parent_identifiers(tmp_path):
    path = tmp_path / "prior.jsonl"
    rows = [{"text": "😀 이전 문서", "document_sha256": "explicit-source-hash",
             "parent_document_id": "parent-1", "document_url": "https://example.test/article"},
            {"text": None, "parent_document_id": "parent-2"}]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    missing = tmp_path / "unavailable.jsonl"
    hashes, parents, audit = benchmark.known_prior_documents([path, missing])
    assert hashes == {"explicit-source-hash", hashlib.sha256(rows[0]["text"].encode()).hexdigest()}
    assert parents == {"parent-1", "parent-2", "https://example.test/article"}
    assert audit["inspected"] == [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
    assert audit["unavailable"] == [str(missing)]
    assert audit["near_duplicate_check_performed"] is False
