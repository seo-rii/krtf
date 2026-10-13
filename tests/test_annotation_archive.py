"""Synthetic fixtures only: these tests do not read local corpus documents."""
import copy
import hashlib
import json
import subprocess
import sys

import pytest

from eval.annotation_archive import export_annotations, restore_annotations
from eval.blind_gold import digest, load_jsonl, validate_annotation


def packet(document_id="synthetic-1"):
    text = "  금감원장이 가상의 조직을 언급했다."
    return {
        "document_id": document_id,
        "document_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "text": text,
        "complete": True,
        "annotator": "ai-adjudicator",
        "annotation_origin": "AI",
        "human_verified": False,
        "model_family": "synthetic-model-family",
        "annotation_ids": ["ai-a", "ai-b"],
        "independent_annotation_hashes": [digest({"annotator": "ai-a"}), digest({"annotator": "ai-b"})],
        "had_disagreement": True,
        "adjudicated": True,
        "adjudication_reason_codes": ["FULL_SURFACE", "MENTION_COVERAGE"],
        "adjudication_note": "The private source says: " + text,
        "family_ids": ["family-fss"],
        "mentions": [{
            "span": [2, 5], "surface": "금감원", "label": "LINK", "entity_id": "ORG_FSS",
            "should_commit": True, "full_span": [2, 6], "full_identity": "DISTINCT",
            "mention_type": "ORG", "family_ids": ["family-fss"],
        }],
    }


def document(source):
    return {key: source[key] for key in ("document_id", "document_sha256", "text")}


def reseal(record):
    record["archive_sha256"] = digest({key: value for key, value in record.items() if key != "archive_sha256"})


def test_roundtrip_preserves_decisions_and_explicit_provenance():
    first = packet("synthetic-1\tmetadata")
    second = packet("synthetic-2")
    second["mentions"] = []
    originals = copy.deepcopy([first, second])
    archive = export_annotations(originals)
    restored = restore_annotations(archive, [document(second), document(first)])
    assert originals == [first, second]
    assert [row["document_id"] for row in restored] == [first["document_id"], second["document_id"]]
    for original, record, result in zip(originals, archive, restored):
        validate_annotation(result)
        for key in original.keys() - {"adjudication_note"}:
            assert result[key] == original[key]
        assert result["original_annotation_sha256"] == digest(original)
        assert record["original_annotation_sha256"] == digest(original)
        assert digest(result) != digest(original)  # Notes and metadata are intentionally lossy.
        assert "FULL_SURFACE, MENTION_COVERAGE" in result["adjudication_note"]
        assert record["archive_sha256"] == digest({k: v for k, v in record.items() if k != "archive_sha256"})


def test_export_whitelists_at_every_level_and_never_archives_free_text():
    source = packet()
    secret = "비공개 원문이 자유 서술에 복제된 테스트 문자열"
    source.update({"review_notes": secret, "unexpected": {"raw_document": secret}, "adjudication_note": secret})
    source["mentions"][0].update({"review_notes": secret, "full_surface": source["text"], "unexpected": secret})
    record = export_annotations([source])[0]
    serialized = json.dumps(record, ensure_ascii=False)
    for forbidden in (source["text"], source["mentions"][0]["surface"], secret,
                      '"text"', '"surface"', '"review_notes"', '"adjudication_note"', '"unexpected"'):
        assert forbidden not in serialized
    assert record["original_annotation_sha256"] == digest(source)


@pytest.mark.parametrize("label,identity", [("NIL", "SAME"), ("AMBIGUOUS", "JUXTAPOSED"), ("NON_MENTION", "DISTINCT")])
def test_roundtrip_preserves_non_link_decisions(label, identity):
    source = packet()
    source["mentions"][0].update(label=label, entity_id=None, should_commit=False, full_identity=identity)
    restored = restore_annotations(export_annotations([source]), [document(source)])[0]
    assert restored["mentions"] == source["mentions"]


@pytest.mark.parametrize("origin,verified", [("HUMAN", True), ("HUMAN", False), ("AI", False)])
def test_origin_and_human_verification_are_preserved_without_inference(origin, verified):
    source = packet()
    source.update(annotation_origin=origin, human_verified=verified)
    if origin == "HUMAN":
        source.pop("model_family")
    restored = restore_annotations(export_annotations([source]), [document(source)])[0]
    assert restored["annotation_origin"] == origin
    assert restored["human_verified"] is verified
    assert ("model_family" in restored) == (origin == "AI")


@pytest.mark.parametrize("field,value", [
    ("annotation_origin", None), ("annotation_origin", "UNKNOWN"),
    ("human_verified", None), ("human_verified", True), ("human_verified", 0),
    ("model_family", None), ("annotator", ""), ("complete", 1),
    ("annotation_ids", ["same", "same"]), ("independent_annotation_hashes", ["unverified"]),
    ("adjudication_reason_codes", ["A sentence from the private text"]),
    ("adjudication_reason_codes", []), ("adjudicated", "yes"),
])
def test_export_rejects_missing_or_invalid_provenance(field, value):
    source = packet()
    source[field] = value
    with pytest.raises(ValueError):
        export_annotations([source])


def test_export_requires_original_text_and_surface_to_validate():
    source = packet()
    source["mentions"][0]["surface"] = "wrong surface"
    with pytest.raises(ValueError, match="surface"):
        export_annotations([source])
    source = packet()
    source["text"] += " changed"
    with pytest.raises(ValueError, match="hash"):
        export_annotations([source])


@pytest.mark.parametrize("field,value", [
    ("span", [True, 5]), ("span", [2.0, 5]), ("span", [2]), ("span", [2, 2]),
    ("span", [-1, 5]), ("full_span", [2, False]), ("full_span", [3, 6]),
    ("label", []), ("should_commit", 1), ("full_identity", []),
    ("mention_type", "Free-text private mention"), ("family_ids", [{"text": "private"}]),
])
def test_invalid_mention_shapes_are_rejected_on_export_and_restore(field, value):
    source = packet()
    invalid_source = copy.deepcopy(source)
    invalid_source["mentions"][0][field] = value
    with pytest.raises(ValueError):
        export_annotations([invalid_source])
    record = export_annotations([source])[0]
    record["mentions"][0][field] = value
    reseal(record)
    with pytest.raises(ValueError):
        restore_annotations([record], [document(source)])


def test_restore_detects_valid_looking_archive_tampering():
    source = packet()
    record = export_annotations([source])[0]
    record["mentions"][0]["should_commit"] = False
    with pytest.raises(ValueError, match="archive hash"):
        restore_annotations([record], [document(source)])


@pytest.mark.parametrize("change", ["unknown_top_level", "unknown_mention", "version", "boolean_version", "provenance"])
def test_restore_refuses_malformed_rows_even_if_resealed(change):
    source = packet()
    record = export_annotations([source])[0]
    if change == "unknown_top_level":
        record["text"] = "leaked"
    elif change == "unknown_mention":
        record["mentions"][0]["surface"] = "leaked"
    elif change == "version":
        record["annotation_archive_version"] = 99
    elif change == "boolean_version":
        record["annotation_archive_version"] = True
    else:
        del record["annotation_origin"]
    reseal(record)
    with pytest.raises(ValueError):
        restore_annotations([record], [document(source)])


def test_restore_checks_source_hash_and_archived_hash_separately():
    source = packet()
    archive = export_annotations([source])
    changed = document(source)
    changed["text"] += "changed"
    with pytest.raises(ValueError, match="source document hash"):
        restore_annotations(archive, [changed])
    changed["document_sha256"] = hashlib.sha256(changed["text"].encode()).hexdigest()
    with pytest.raises(ValueError, match="archived document hash"):
        restore_annotations(archive, [changed])


def test_restore_refuses_swapped_documents():
    first, second = packet("first"), packet("second")
    second["text"] = second["text"].replace("가상의", "미지의")
    second["document_sha256"] = hashlib.sha256(second["text"].encode()).hexdigest()
    archive = export_annotations([first, second])
    swapped = [document(first), document(second)]
    swapped[0]["document_id"], swapped[1]["document_id"] = swapped[1]["document_id"], swapped[0]["document_id"]
    with pytest.raises(ValueError, match="archived document hash"):
        restore_annotations(archive, swapped)


def test_membership_must_cover_all_documents_and_reject_duplicates():
    source, extra = packet(), packet("extra")
    archive = export_annotations([source])
    with pytest.raises(ValueError, match="duplicate"):
        export_annotations([source, source])
    for annotations, documents, message in [
        (archive, [], "exactly"), (archive, [document(source), document(extra)], "exactly"),
        (archive, [document(extra)], "exactly"),
        (archive * 2, [document(source)], "duplicate"),
        (archive, [document(source)] * 2, "duplicate"),
    ]:
        with pytest.raises(ValueError, match=message):
            restore_annotations(annotations, documents)


def test_restore_checks_span_bounds_and_duplicate_mentions_using_full_document():
    source = packet()
    record = export_annotations([source])[0]
    record["mentions"][0]["full_span"][1] = len(source["text"]) + 1
    reseal(record)
    with pytest.raises(ValueError, match="full span"):
        restore_annotations([record], [document(source)])
    record = export_annotations([source])[0]
    record["mentions"] *= 2
    reseal(record)
    with pytest.raises(ValueError, match="duplicate mention"):
        restore_annotations([record], [document(source)])


def test_individual_annotation_and_adjudication_without_codes_can_restore():
    source = packet()
    del source["adjudication_reason_codes"]
    restored = restore_annotations(export_annotations([source]), [source])[0]
    assert "original free-text rationale was omitted" in restored["adjudication_note"]
    for field in ("adjudicated", "had_disagreement", "adjudication_note", "annotation_ids", "independent_annotation_hashes"):
        source.pop(field)
    restored = restore_annotations(export_annotations([source]), [source])[0]
    assert restored["mentions"] == source["mentions"]
    assert "adjudication_note" not in restored


def test_cli_exports_and_restores_with_original_packets_and_exclusive_output(tmp_path):
    source = packet()
    local_path, archive_path, restored_path = [tmp_path / name for name in ("local.jsonl", "archive.jsonl", "restored.jsonl")]
    local_path.write_text(json.dumps(source, ensure_ascii=False) + "\n", encoding="utf-8")
    def run(*args, check=True):
        return subprocess.run([sys.executable, "-m", "eval.annotation_archive", *args], check=check, capture_output=True)
    run("export", "--annotations", str(local_path), "--out", str(archive_path))
    run("restore", "--annotations", str(archive_path), "--documents", str(local_path), "--out", str(restored_path))
    assert load_jsonl(restored_path)[0]["mentions"] == source["mentions"]
    assert run("export", "--annotations", str(local_path), "--out", str(archive_path), check=False).returncode != 0
    bad = copy.deepcopy(source)
    bad["document_id"] = "invalid-second"
    bad["mentions"][0]["surface"] = "wrong"
    local_path.write_text("\n".join(json.dumps(row) for row in [source, bad]), encoding="utf-8")
    failed_path = tmp_path / "failed.jsonl"
    assert run("export", "--annotations", str(local_path), "--out", str(failed_path), check=False).returncode != 0
    assert not failed_path.exists()
