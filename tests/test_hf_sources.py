"""Tiny authored fixtures exercise source contracts, never copied corpora."""
import hashlib
import io
import json
from pathlib import Path

import pytest

from eval import hf_sources


def test_kbmc_retains_segmented_offsets_and_skips_invalid_bio_rows(tmp_path):
    path = tmp_path / "KBMC.tsv"
    text = "  시험   증상\t부위 . "
    # The source TSV cell can contain whitespace; offsets use the exact cell.
    path.write_text('Sentence\tTags\n"' + text + '"\tDisease-B Disease-I Body-B O\n'
                    "길이 오류\tO\n"
                    "고립\tDisease-I\n"
                    "종류 변경\tDisease-B Body-I\n"
                    "일반 문장\tO O\n", encoding="utf-8")
    records, exclusions = hf_sources.load_ner_records("kbmc", path)
    assert len(records) == 2
    first = records[0]
    assert first["text"] == text
    assert first["ner_annotations"] == [
        {"span": [2, 9], "surface": "시험   증상", "type": "Disease"},
        {"span": [10, 12], "surface": "부위", "type": "Body"},
    ]
    assert [item["reason"] for item in exclusions] == [
        "token_tag_length_mismatch", "invalid_bio_continuation", "invalid_bio_continuation"]
    assert [item["source_row_id"] for item in exclusions] == ["1", "2", "3"]
    assert records[1]["source_row_id"] == "4" and records[1]["ner_annotations"] == []
    assert all(record["linking_gold_status"] == "UNANNOTATED" for record in records)
    assert "entity_id" not in json.dumps(records)


def test_ner_ids_keep_rows_while_identical_content_shares_parent(tmp_path):
    path = tmp_path / "KBMC.tsv"
    path.write_text("Sentence\tTags\n같은 문장\tO O\n같은 문장\tO O\n", encoding="utf-8")
    records, exclusions = hf_sources.load_ner_records("kbmc", path)
    assert not exclusions
    assert records[0]["document_id"] != records[1]["document_id"]
    assert records[0]["parent_document_id"] == records[1]["parent_document_id"]
    assert records[0]["document_sha256"] == hashlib.sha256("같은 문장".encode()).hexdigest()


def test_naver_local_adapter_preserves_codepoints_and_rejects_bad_offsets(tmp_path):
    path = tmp_path / "local.jsonl"
    path.write_text(json.dumps({"text": "가😀 나", "entities": [[1, 2, "PER"], [3, 4, "LOC"]]},
                               ensure_ascii=False) + "\n", encoding="utf-8")
    records, exclusions = hf_sources.load_ner_records("naver_ner", path)
    assert not exclusions
    assert records[0]["ner_annotations"][0] == {"span": [1, 2], "surface": "😀", "type": "PER"}
    path.write_text('{"text":"가","entities":[[0,2,"ORG"]]}\n')
    with pytest.raises(ValueError, match="offsets"):
        hf_sources.load_ner_records("naver_ner", path)


def test_acquisition_pins_data_and_cards_disables_naver_and_checks_cache(tmp_path, monkeypatch):
    data, card = b"authored source bytes", b"authored card"
    specs = {
        "naver_ner": {**hf_sources.SOURCE_SPECS["naver_ner"]},
        "demo": {"dataset": "author/demo", "revision": "a" * 40, "file": "input.tsv",
                 "enabled": True, "expected_sha256": hashlib.sha256(data).hexdigest(),
                 "expected_bytes": len(data)},
    }
    monkeypatch.setattr(hf_sources, "SOURCE_SPECS", specs)
    calls = []

    def open_url(request, timeout):
        calls.append(request.full_url)
        assert "/resolve/" + "a" * 40 + "/" in request.full_url
        return io.BytesIO(card if request.full_url.endswith("README.md") else data)

    monkeypatch.setattr(hf_sources.urllib.request, "urlopen", open_url)
    manifest = hf_sources.acquire_sources(tmp_path)
    assert len(calls) == 2 and set(manifest["sources"]) == {"demo"}
    record = manifest["sources"]["demo"]
    assert record["sha256"] == hashlib.sha256(data).hexdigest()
    assert record["card_sha256"] == hashlib.sha256(card).hexdigest()
    assert manifest["exclusions"][0]["source_key"] == "naver_ner"
    assert manifest["exclusions"][0]["license_conflict"] is True
    assert hf_sources.acquire_sources(tmp_path)["sources"]["demo"]["cache_hit"] is True
    assert len(calls) == 2
    Path(record["path"]).write_bytes(b"altered")
    with pytest.raises(ValueError, match="cache.*mismatch"):
        hf_sources.acquire_sources(tmp_path)


def test_download_hash_failure_leaves_no_partial_target(tmp_path, monkeypatch):
    monkeypatch.setattr(hf_sources.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"wrong"))
    path = tmp_path / "source.bin"
    with pytest.raises(ValueError, match="SHA-256"):
        hf_sources._acquire_file("https://example.test/pinned", path, expected_sha256="0" * 64)
    assert not path.exists() and list(tmp_path.iterdir()) == []


def _tydi_row(text="가😀 나", *, start=1, end=5, passage_index=0, yes="NONE"):
    return {
        "document_plaintext": text, "question_text": "시험 질문?", "document_url": "https://example.test/article",
        "document_title": "시험", "language": "korean",
        "passage_answer_candidates": {"plaintext_start_byte": [0], "plaintext_end_byte": [len(text.encode())]},
        "annotations": {"minimal_answers_start_byte": [start], "minimal_answers_end_byte": [end],
                        "passage_answer_candidate_index": [passage_index], "yes_no_answer": [yes]},
    }


def _load_rows(tmp_path, monkeypatch, rows):
    path = tmp_path / "authored.parquet"
    path.write_bytes(b"reader is replaced by authored rows")
    monkeypatch.setattr(hf_sources, "_iter_tydi_rows", lambda _: iter(enumerate(rows)))
    return hf_sources.load_tydi_records(path)


def test_tydi_utf8_spans_all_candidates_and_unanswerable_denominators(tmp_path, monkeypatch):
    text = "가😀 나"
    span = _tydi_row(text, start=3, end=7)
    span["passage_answer_candidates"] = [
        {"plaintext_start_byte": 0, "plaintext_end_byte": 7},
        {"plaintext_start_byte": 8, "plaintext_end_byte": 11},
    ]
    span["annotations"] = [{"minimal_answers_start_byte": 3, "minimal_answers_end_byte": 7,
                            "passage_answer_candidate_index": 0, "yes_no_answer": "NONE"}]
    no_answer = _tydi_row(text, start=-1, end=-1, passage_index=-1)
    yes_no = _tydi_row(text, start=-1, end=-1, passage_index=0, yes="YES")
    passage_only = _tydi_row(text, start=-1, end=-1, passage_index=0)
    foreign = {"language": "english"}
    records, exclusions = _load_rows(tmp_path, monkeypatch, [foreign, span, no_answer, yes_no, passage_only])
    assert len(records) == 4 and len(exclusions) == 1
    assert records[0]["source_row_id"] == "1"
    assert records[0]["text"] == text and records[0]["answer_spans"] == [[1, 2]]
    assert records[0]["passage_candidates"] == [[0, 2], [3, 4]]
    assert records[0]["answer_passage_spans"] == [[0, 2]]
    assert records[1]["no_answer"] is True and records[1]["answer_spans"] == []
    assert records[2]["no_answer"] is False and records[2]["yes_no_answers"] == ["YES"]
    assert records[3]["annotation_answers"][0]["answer_type"] == "PASSAGE_ONLY"
    assert len({record["parent_document_id"] for record in records}) == 1
    assert len({record["document_id"] for record in records}) == 4


@pytest.mark.parametrize("change", [
    {"minimal_answers_start_byte": [1]},  # Inside the first Korean codepoint.
    {"minimal_answers_end_byte": [-1]},  # An absent answer needs both -1.
    {"passage_answer_candidate_index": [1]},
    {"yes_no_answer": ["UNKNOWN"]},
    {"minimal_answers_start_byte": [3, 3]},  # Unequal column lengths.
])
def test_tydi_bad_annotations_fail_without_silently_reducing_denominator(tmp_path, monkeypatch, change):
    row = _tydi_row(start=3, end=7)
    row["annotations"].update(change)
    with pytest.raises(ValueError):
        _load_rows(tmp_path, monkeypatch, [row])


def test_tydi_candidate_utf8_offsets_are_checked_even_if_not_the_answer(tmp_path, monkeypatch):
    row = _tydi_row(start=-1, end=-1, passage_index=-1)
    row["passage_answer_candidates"]["plaintext_start_byte"] = [1]
    with pytest.raises(ValueError, match="UTF-8"):
        _load_rows(tmp_path, monkeypatch, [row])


def test_tydi_record_invalid_minimal_preserves_question_and_source_annotations(tmp_path, monkeypatch):
    row = _tydi_row(start=3, end=7)
    row["annotations"] = {
        "minimal_answers_start_byte": [-1, 1, 3],
        "minimal_answers_end_byte": [-1, 7, 7],
        "passage_answer_candidate_index": [-1, 0, 0],
        "yes_no_answer": ["NONE", "YES", "NONE"],
    }
    path = tmp_path / "authored.parquet"
    path.write_bytes(b"authored rows")
    monkeypatch.setattr(hf_sources, "_iter_tydi_rows", lambda _: iter([(4, row)]))
    with pytest.raises(ValueError, match="UTF-8"):
        hf_sources.load_tydi_records(path)
    records, exclusions = hf_sources.load_tydi_records(path, invalid_minimal="record")
    assert not exclusions and len(records) == 1
    record = records[0]
    assert record["source_row_id"] == "4" and record["text"] == row["document_plaintext"]
    assert record["minimal_answer_evaluable"] is False and record["no_answer"] is False
    assert record["answer_spans"] == [[1, 2]]  # The valid annotator is retained too.
    assert record["answer_passage_spans"] == [[0, 4]]
    assert record["annotation_answers"][1] == {
        "answer_span": None, "answer_type": "INVALID", "passage_index": 0, "yes_no_answer": "YES"}
    error = record["annotation_errors"][0]
    assert error["annotation_index"] == 1
    assert error["source_start_byte"] == 1 and error["source_end_byte"] == 7
    assert "UTF-8" in error["reason"]


def test_tydi_record_invalid_minimal_never_changes_passage_validation(tmp_path, monkeypatch):
    path = tmp_path / "authored.parquet"
    path.write_bytes(b"authored rows")
    row = _tydi_row(start=1, end=7)
    row["passage_answer_candidates"]["plaintext_start_byte"] = [1]
    monkeypatch.setattr(hf_sources, "_iter_tydi_rows", lambda _: iter([(0, row)]))
    with pytest.raises(ValueError, match="UTF-8.*passage"):
        hf_sources.load_tydi_records(path, invalid_minimal="record")
    with pytest.raises(ValueError, match="invalid_minimal"):
        hf_sources.load_tydi_records(path, invalid_minimal="repair")
