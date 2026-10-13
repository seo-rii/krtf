"""Archive annotation decisions without document text, surfaces, or free-text notes.

CLI: python -m eval.annotation_archive export --annotations local.jsonl --out archive.jsonl
     python -m eval.annotation_archive restore --annotations archive.jsonl --documents documents.jsonl --out local.jsonl

This is a lossy archive: restore recreates surfaces from matching original documents,
but never recovers discarded notes or arbitrary extra fields. original_annotation_sha256
is blind_gold.digest of the complete original packet, not its JSONL bytes; restored
packets will generally have a different digest. Independent annotation hashes retain
their original meaning and must not be compared to digests of restored packets.
archive_sha256 detects changes to archived fields; it is not an authenticity signature.
Identifiers and other required metadata are preserved verbatim and may contain words
from a source. Only document text, surfaces, and unrestricted notes are excluded.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

from eval.blind_gold import digest, load_jsonl, validate_annotation


ANNOTATION_ARCHIVE_VERSION = 1
ADJUDICATION_REASON_CODES = frozenset({
    "MENTION_COVERAGE", "ENTITY_LINK", "NIL_STATUS", "MENTION_BOUNDARY",
    "FULL_SURFACE", "COMMIT_ELIGIBILITY", "MENTION_TYPE", "FAMILY_ASSIGNMENT",
    "ANNOTATION_AGREEMENT",
})
MENTION_TYPES = frozenset({"ORG", "PERSON", "LOCATION", "PRODUCT", "WORK", "EVENT", "TERM"})
PACKET_FIELDS = frozenset({
    "document_id", "document_sha256", "complete", "annotator", "annotation_origin",
    "human_verified", "model_family", "annotation_ids", "had_disagreement", "adjudicated",
    "independent_annotation_hashes", "adjudication_reason_codes", "family_ids", "mentions",
})
MENTION_FIELDS = frozenset({
    "span", "label", "entity_id", "should_commit", "full_span", "full_identity",
    "mention_type", "family_ids",
})
ARCHIVE_FIELDS = PACKET_FIELDS | {
    "annotation_archive_version", "original_annotation_sha256", "archive_sha256",
}


def _require_string(value, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")


def _require_hash(value, field: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{field} must be a SHA-256 digest")


def _require_string_list(value, field: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    for item in value:
        _require_string(item, field)
    if len(set(value)) != len(value):
        raise ValueError(f"{field} contains duplicates")


def _index_documents(rows: list[dict]) -> dict[str, dict]:
    indexed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("document must be an object")
        _require_string(row.get("document_id"), "document_id")
        if row["document_id"] in indexed:
            raise ValueError("duplicate document_id")
        indexed[row["document_id"]] = row
    return indexed


def _validate_fields(packet: dict, *, archived: bool) -> None:
    """Validate source-independent shapes before slicing text or invoking gold validation."""
    if not isinstance(packet, dict):
        raise ValueError("annotation must be an object")
    if archived:
        if set(packet) - ARCHIVE_FIELDS:
            raise ValueError("unknown archive fields")
        version = packet.get("annotation_archive_version")
        if type(version) is not int or version != ANNOTATION_ARCHIVE_VERSION:
            raise ValueError("unsupported annotation archive version")
        for field in ("original_annotation_sha256", "archive_sha256"):
            _require_hash(packet.get(field), field)
    _require_string(packet.get("document_id"), "document_id")
    _require_hash(packet.get("document_sha256"), "document_sha256")
    _require_string(packet.get("annotator"), "annotator")
    if packet.get("complete") is not True:
        raise ValueError("annotation must be complete")
    if packet.get("annotation_origin") not in ("AI", "HUMAN"):
        raise ValueError("explicit annotation_origin AI or HUMAN required")
    if type(packet.get("human_verified")) is not bool:
        raise ValueError("explicit human_verified boolean required")
    if packet["annotation_origin"] == "AI":
        if packet["human_verified"]:
            raise ValueError("AI annotation must have human_verified false")
        _require_string(packet.get("model_family"), "model_family")
    elif "model_family" in packet:
        _require_string(packet["model_family"], "model_family")
    for field in ("had_disagreement", "adjudicated"):
        if field in packet and type(packet[field]) is not bool:
            raise ValueError(f"{field} must be a boolean")
    for field in ("family_ids", "annotation_ids", "adjudication_reason_codes"):
        if field in packet:
            _require_string_list(packet[field], field)
    if "adjudication_reason_codes" in packet:
        if not packet["adjudication_reason_codes"] or set(packet["adjudication_reason_codes"]) - ADJUDICATION_REASON_CODES:
            raise ValueError("unknown or empty adjudication_reason_codes")
    if "independent_annotation_hashes" in packet:
        hashes = packet["independent_annotation_hashes"]
        if not isinstance(hashes, list):
            raise ValueError("independent_annotation_hashes must be a list")
        for value in hashes:
            _require_hash(value, "independent_annotation_hashes")
        if len(hashes) != len(packet.get("annotation_ids", [])):
            raise ValueError("independent annotation hash count differs")
    if packet.get("adjudicated"):
        if (len(packet.get("annotation_ids", [])) < 2 or
                len(packet.get("independent_annotation_hashes", [])) < 2 or
                "had_disagreement" not in packet):
            raise ValueError("adjudicated annotations require independent provenance")
    if packet.get("had_disagreement") and not packet.get("adjudicated"):
        raise ValueError("disagreement requires adjudication")
    if not isinstance(packet.get("mentions"), list):
        raise ValueError("mentions must be a list")
    for mention in packet["mentions"]:
        if not isinstance(mention, dict):
            raise ValueError("mention must be an object")
        if archived and set(mention) - MENTION_FIELDS:
            raise ValueError("unknown archived mention fields")
        for field in ("span", "full_span"):
            span = mention.get(field)
            if (not isinstance(span, list) or len(span) != 2 or
                    any(type(offset) is not int for offset in span) or
                    not 0 <= span[0] < span[1]):
                raise ValueError(f"invalid {field}")
        start, end = mention["span"]
        full_start, full_end = mention["full_span"]
        if not full_start <= start < end <= full_end:
            raise ValueError("full span must contain core span")
        if mention.get("label") not in ("LINK", "NIL", "AMBIGUOUS", "NON_MENTION"):
            raise ValueError("unknown mention label")
        if "entity_id" in mention and mention["entity_id"] is not None:
            _require_string(mention["entity_id"], "entity_id")
        if mention["label"] == "LINK" and not mention.get("entity_id"):
            raise ValueError("linked mentions require entity_id")
        if mention["label"] == "NIL" and mention.get("entity_id"):
            raise ValueError("NIL means absent from the frozen glossary")
        if type(mention.get("should_commit")) is not bool:
            raise ValueError("explicit should_commit boolean required")
        if mention["label"] != "LINK" and mention["should_commit"]:
            raise ValueError("only LINK can authorize a commit")
        if mention.get("full_identity") not in ("SAME", "DISTINCT", "JUXTAPOSED"):
            raise ValueError("explicit full-surface semantics required")
        if "mention_type" in mention:
            if not isinstance(mention["mention_type"], str) or mention["mention_type"] not in MENTION_TYPES:
                raise ValueError("unknown mention_type")
        if "family_ids" in mention:
            _require_string_list(mention["family_ids"], "family_ids")


def export_annotations(annotations: list[dict]) -> list[dict]:
    """Validate complete packets, then retain only approved decisions and provenance."""
    _index_documents(annotations)
    result = []
    for packet in annotations:
        _validate_fields(packet, archived=False)
        if not isinstance(packet.get("text"), str):
            raise ValueError("annotation text must be a string")
        validate_annotation(packet)
        record = {key: copy.deepcopy(value) for key, value in packet.items() if key in PACKET_FIELDS}
        record["mentions"] = [
            {key: copy.deepcopy(value) for key, value in mention.items() if key in MENTION_FIELDS}
            for mention in packet["mentions"]
        ]
        record["annotation_archive_version"] = ANNOTATION_ARCHIVE_VERSION
        record["original_annotation_sha256"] = digest(packet)
        record["archive_sha256"] = digest(record)
        result.append(record)
    return result


def restore_annotations(annotations: list[dict], documents: list[dict]) -> list[dict]:
    """Restore packets against the exact source corpus, including zero-mention documents."""
    archive_by_id = _index_documents(annotations)
    documents_by_id = _index_documents(documents)
    if set(archive_by_id) != set(documents_by_id):
        raise ValueError("documents must cover exactly the archived document IDs")
    result = []
    for record in annotations:
        _validate_fields(record, archived=True)
        if digest({key: value for key, value in record.items() if key != "archive_sha256"}) != record["archive_sha256"]:
            raise ValueError("annotation archive hash mismatch")
        document = documents_by_id[record["document_id"]]
        if not isinstance(document.get("text"), str):
            raise ValueError("document text must be a string")
        _require_hash(document.get("document_sha256"), "document_sha256")
        if hashlib.sha256(document["text"].encode()).hexdigest() != document["document_sha256"]:
            raise ValueError("source document hash mismatch")
        if document["document_sha256"] != record["document_sha256"]:
            raise ValueError("archived document hash differs from source document")
        packet = {key: copy.deepcopy(value) for key, value in record.items() if key in PACKET_FIELDS}
        packet["original_annotation_sha256"] = record["original_annotation_sha256"]
        packet["text"] = document["text"]
        for mention in packet["mentions"]:
            start, end = mention["span"]
            mention["surface"] = packet["text"][start:end]
        if packet.get("adjudicated"):
            codes = packet.get("adjudication_reason_codes", [])
            packet["adjudication_note"] = (
                "Source-free adjudication reason codes: " + ", ".join(codes) if codes else
                "Restored adjudicated decisions; original free-text rationale was omitted."
            )
        validate_annotation(packet)
        result.append(packet)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("export", "restore"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--annotations", required=True)
        command_parser.add_argument("--out", required=True)
        if command == "restore":
            command_parser.add_argument("--documents", required=True)
    args = parser.parse_args()
    annotations = load_jsonl(args.annotations)
    if args.command == "export":
        result = export_annotations(annotations)
    else:
        result = restore_annotations(annotations, load_jsonl(args.documents))
    with Path(args.out).open("x", encoding="utf-8") as stream:
        for packet in result:
            stream.write(json.dumps(packet, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
