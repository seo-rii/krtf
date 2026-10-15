"""Pinned HF source acquisition and lossless span-only/QA source adapters.

NER types never become linking gold. TyDi byte offsets are converted only at
valid UTF-8 boundaries; Korean no-answer and yes/no questions are retained.
The optional pyarrow dependency is imported only by the Parquet reader.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime, timezone
import urllib.request


SOURCE_SPECS = {
    "naver_ner": {
        "dataset": "HERIUN/kor-ner-spacy-data",
        "revision": "3427cb52e81bba251311cec48710b47f891073f2",
        "file": "data/naver_ner_dataset.jsonl",
        "enabled": False,
        "license_conflict": True,
        "exclusion_reason": "upstream_competition_agreement_conflicts_with_mirror_license",
    },
    "kbmc": {
        "dataset": "SungJoo/KBMC",
        "revision": "9cd99c088d3192577f9355b4832b96c3087996e8",
        "file": "KBMC.tsv",
        "enabled": True,
        "license": "apache-2.0 (HF card declaration)",
    },
    "tydiqa_ko": {
        "dataset": "google-research-datasets/tydiqa",
        "revision": "da78f23f9119363459acbaf46bf89426ff26c259",
        "file": "primary_task/validation-00000-of-00001.parquet",
        "enabled": True,
        "license": "apache-2.0 (HF card declaration; source Wikipedia rights separate)",
        "expected_bytes": 232035124,
        "expected_sha256": "2e9557a6ea4bfd65f381c64b91122c90554e4b00f86e15a8b4f1353be1c81510",
    },
}


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _acquire_file(url: str, path: Path, *, expected_sha256=None, expected_bytes=None) -> dict:
    """Reuse only a cache whose saved provenance and current bytes agree."""
    sidecar = path.with_name(path.name + ".acquisition.json")
    if path.exists() and sidecar.exists():
        recorded = json.loads(sidecar.read_text(encoding="utf-8"))
        digest, size = _sha_file(path), path.stat().st_size
        if (recorded.get("url") != url or recorded.get("sha256") != digest
                or recorded.get("bytes") != size
                or expected_sha256 is not None and digest != expected_sha256
                or expected_bytes is not None and size != expected_bytes):
            raise ValueError(f"cached source identity mismatch: {path.name}")
        return {**recorded, "path": str(path.resolve()), "cache_hit": True}

    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        digest, size = hashlib.sha256(), 0
        request = urllib.request.Request(url, headers={"User-Agent": "ktrf-hf-eval/1"})
        with os.fdopen(descriptor, "wb") as stream:
            with urllib.request.urlopen(request, timeout=120) as response:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
                    stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        sha256 = digest.hexdigest()
        if expected_sha256 is not None and sha256 != expected_sha256:
            raise ValueError(f"downloaded source SHA-256 mismatch: {path.name}")
        if expected_bytes is not None and size != expected_bytes:
            raise ValueError(f"downloaded source size mismatch: {path.name}")
        record = {"url": url, "path": str(path.resolve()), "sha256": sha256,
                  "bytes": size, "collected_at": datetime.now(timezone.utc).isoformat()}
        os.replace(temporary, path)
        _atomic_json(sidecar, record)
        return {**record, "cache_hit": False}
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def acquire_sources(cache_dir: Path) -> dict:
    """Download immutable source files and their cards, never a moving branch.

    Naver is deliberately excluded: a mirror's card is insufficient to override
    its upstream competition agreement. Cached data are not a redistribution
    authorization; callers retain the individual source/rightsholder notices.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    sources, exclusions = {}, []
    for key, spec in SOURCE_SPECS.items():
        if not spec.get("enabled", True):
            exclusions.append({"source_key": key, "dataset": spec["dataset"],
                               "revision": spec["revision"], "file": spec["file"],
                               "reason": spec["exclusion_reason"],
                               "license_conflict": spec.get("license_conflict", False)})
            continue
        directory = cache_dir / key / spec["revision"]
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        base = f"https://huggingface.co/datasets/{spec['dataset']}/resolve/{spec['revision']}/"
        data = _acquire_file(base + spec["file"], directory / Path(spec["file"]).name,
                             expected_sha256=spec.get("expected_sha256"),
                             expected_bytes=spec.get("expected_bytes"))
        card = _acquire_file(base + "README.md", directory / "README.md")
        sources[key] = {**spec, **data, "source_key": key, "card_path": card["path"],
                        "card_sha256": card["sha256"], "card_url": card["url"],
                        "card_collected_at": card["collected_at"]}
    return {"schema_version": 1, "collected_at": datetime.now(timezone.utc).isoformat(),
            "sources": sources, "exclusions": exclusions}


def _base_record(source_key: str, row_index: int, text: str, source_hash: str) -> dict:
    spec = SOURCE_SPECS[source_key]
    digest = hashlib.sha256(text.encode("utf-8", errors="strict")).hexdigest()
    return {"document_id": f"hf:{source_key}:{spec['revision']}:row:{row_index}",
            "parent_document_id": "sha256:" + digest, "source_row_id": str(row_index),
            "source_key": source_key, "dataset": spec["dataset"],
            "dataset_revision": spec["revision"], "source_file_sha256": source_hash,
            "text": text, "document_sha256": digest}


def _kbmc_spans(text: str, tags_text: str) -> list[dict]:
    tokens = list(re.finditer(r"\S+", text))
    tags = tags_text.split()
    if not tokens:
        raise ValueError("empty_sentence")
    if len(tokens) != len(tags):
        raise ValueError("token_tag_length_mismatch")
    spans, active = [], None
    for token, tag in zip(tokens, tags):
        if tag == "O":
            if active is not None:
                spans.append(active)
                active = None
            continue
        if "-" not in tag:
            raise ValueError("invalid_bio_tag")
        kind, bio = tag.rsplit("-", 1)
        if not kind or bio not in {"B", "I"}:
            raise ValueError("invalid_bio_tag")
        if bio == "B":
            if active is not None:
                spans.append(active)
            active = {"span": [token.start(), token.end()], "type": kind}
        elif active is None or active["type"] != kind:
            raise ValueError("invalid_bio_continuation")
        else:
            active["span"][1] = token.end()
    if active is not None:
        spans.append(active)
    return [{**span, "surface": text[slice(*span["span"])]} for span in spans]


def load_ner_records(source_key: str, path: Path) -> tuple[list[dict], list[dict]]:
    """Import source boundaries/types; KBMC invalid rows have an explicit ledger.

    Naver support is an adapter for independently authorized local files only;
    acquire_sources never downloads it. No text is detokenized or repaired.
    """
    path = Path(path)
    source_hash = _sha_file(path)
    records, exclusions = [], []
    if source_key == "kbmc":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t", strict=True)
            if reader.fieldnames != ["Sentence", "Tags"]:
                raise ValueError("KBMC requires exactly Sentence/Tags columns")
            for index, row in enumerate(reader):
                try:
                    if None in row or row["Sentence"] is None or row["Tags"] is None:
                        raise ValueError("invalid_columns")
                    text = row["Sentence"]
                    spans = _kbmc_spans(text, row["Tags"])
                except ValueError as error:
                    exclusions.append({"source_key": source_key, "source_row_id": str(index),
                                       "source_line_end": reader.line_num, "reason": str(error)})
                    continue
                records.append({**_base_record(source_key, index, text, source_hash),
                                "ner_annotations": spans, "label_scope": "span_type_only",
                                "linking_gold_status": "UNANNOTATED",
                                "text_representation": "source_segmented_sentence_unchanged"})
    elif source_key == "naver_ner":
        with path.open(encoding="utf-8-sig") as stream:
            for index, line in enumerate(stream):
                if not line.strip():
                    exclusions.append({"source_key": source_key, "source_row_id": str(index),
                                       "reason": "blank_jsonl_line"})
                    continue
                row = json.loads(line)
                text = row["text"]
                if not isinstance(text, str) or not text:
                    raise ValueError(f"invalid Naver text at row {index}")
                spans = []
                for entity in row["entities"]:
                    if not isinstance(entity, list) or len(entity) != 3:
                        raise ValueError(f"invalid Naver span at row {index}")
                    start, end, kind = entity
                    if (type(start) is not int or type(end) is not int
                            or not 0 <= start < end <= len(text)
                            or not isinstance(kind, str) or not kind):
                        raise ValueError(f"invalid Naver offsets/type at row {index}")
                    spans.append({"span": [start, end], "surface": text[start:end], "type": kind})
                records.append({**_base_record(source_key, index, text, source_hash),
                                "ner_annotations": spans, "label_scope": "span_type_only",
                                "linking_gold_status": "UNANNOTATED"})
    else:
        raise ValueError(f"unsupported NER source: {source_key}")
    return records, exclusions


def _struct_rows(value, fields: tuple[str, ...], *, context: str) -> list[dict]:
    """Arrow may expose a sequence of structs or an HF struct of sequences."""
    if isinstance(value, list):
        if not all(isinstance(row, dict) and all(field in row for field in fields) for row in value):
            raise ValueError(f"invalid {context} structs")
        return value
    if not isinstance(value, dict) or any(not isinstance(value.get(field), list) for field in fields):
        raise ValueError(f"invalid {context} columns")
    if len({len(value[field]) for field in fields}) != 1:
        raise ValueError(f"unequal {context} column lengths")
    return [dict(zip(fields, items)) for items in zip(*(value[field] for field in fields))]


def _utf8_boundaries(text: str) -> dict[int, int]:
    boundaries, offset = {0: 0}, 0
    for index, char in enumerate(text):
        offset += len(char.encode("utf-8", errors="strict"))
        boundaries[offset] = index + 1
    return boundaries


def _byte_span(start, end, boundaries: dict[int, int], *, context: str) -> list[int]:
    if (type(start) is not int or type(end) is not int or start >= end
            or start not in boundaries or end not in boundaries):
        raise ValueError(f"invalid UTF-8 byte offsets for {context}")
    return [boundaries[start], boundaries[end]]


def _iter_tydi_rows(path: Path):
    try:
        import pyarrow.parquet as parquet
    except ImportError as error:
        raise ImportError("TyDi Parquet loading requires optional pyarrow") from error
    index = 0
    for batch in parquet.ParquetFile(path).iter_batches(batch_size=256):
        for row in batch.to_pylist():
            yield index, row
            index += 1


def load_tydi_records(path: Path, *, invalid_minimal="error") -> tuple[list[dict], list[dict]]:
    """Retain every Korean validation question, including no-answer/yes-no.

    Invalid Korean offsets fail by default. ``invalid_minimal="record"`` keeps
    questions with invalid minimal-answer boundaries, recording original bytes
    and marking that question unevaluable for minimal-answer metrics. Passage
    offsets and annotation structure remain strict. Offsets always refer to the
    original document_plaintext, never a reconstructed or normalized article.
    """
    if invalid_minimal not in {"error", "record"}:
        raise ValueError("invalid_minimal must be error or record")
    path = Path(path)
    source_hash = _sha_file(path)
    records, exclusions = [], []
    passage_fields = ("plaintext_start_byte", "plaintext_end_byte")
    answer_fields = ("minimal_answers_start_byte", "minimal_answers_end_byte",
                     "passage_answer_candidate_index", "yes_no_answer")
    for index, row in _iter_tydi_rows(path):
        if row.get("language") not in {"korean", "ko"}:
            exclusions.append({"source_key": "tydiqa_ko", "source_row_id": str(index),
                               "language": row.get("language"), "reason": "non_korean"})
            continue
        text, question = row["document_plaintext"], row["question_text"]
        if not isinstance(text, str) or not text or not isinstance(question, str) or not question:
            raise ValueError(f"empty/invalid Korean TyDi document/question at row {index}")
        boundaries = _utf8_boundaries(text)
        candidates = _struct_rows(row["passage_answer_candidates"], passage_fields, context="passage candidates")
        passages = [_byte_span(candidate[passage_fields[0]], candidate[passage_fields[1]],
                               boundaries, context=f"passage row {index}") for candidate in candidates]
        annotations = _struct_rows(row["annotations"], answer_fields, context="annotations")
        if not annotations:
            raise ValueError(f"Korean TyDi row {index} has no annotation records")
        answers, selected_passages, yes_no, interpreted, annotation_errors = [], [], [], [], []
        for annotation_index, annotation in enumerate(annotations):
            start, end = annotation[answer_fields[0]], annotation[answer_fields[1]]
            if type(start) is not int or type(end) is not int:
                raise ValueError(f"non-integer TyDi minimal answer offsets at row {index}")
            invalid = False
            if start == end == -1:
                span = None
            else:
                try:
                    span = _byte_span(start, end, boundaries, context=f"minimal answer row {index}")
                except ValueError as error:
                    if invalid_minimal == "error":
                        raise
                    span, invalid = None, True
                    annotation_errors.append({"annotation_index": annotation_index,
                                              "source_start_byte": start, "source_end_byte": end,
                                              "reason": str(error)})
                if span is not None and span not in answers:
                    answers.append(span)
            passage_index, yes = annotation[answer_fields[2]], annotation[answer_fields[3]]
            if (type(passage_index) is not int or passage_index < -1 or passage_index >= len(passages)
                    or yes not in {"YES", "NO", "NONE"}):
                raise ValueError(f"invalid TyDi passage index/yes-no annotation at row {index}")
            if passage_index >= 0:
                selected = passages[passage_index]
                if selected not in selected_passages:
                    selected_passages.append(selected)
            if yes not in yes_no:
                yes_no.append(yes)
            answer_type = ("INVALID" if invalid else "SPAN" if span is not None else "YES_NO" if yes != "NONE"
                           else "PASSAGE_ONLY" if passage_index >= 0 else "NO_ANSWER")
            interpreted.append({"answer_span": span, "passage_index": passage_index,
                                "yes_no_answer": yes, "answer_type": answer_type})
        url = row.get("document_url")
        if not isinstance(url, str) or not url:
            raise ValueError(f"missing TyDi document URL at row {index}")
        record = _base_record("tydiqa_ko", index, text, source_hash)
        record.update(parent_document_id="tydiqa-url-sha256:" + hashlib.sha256(url.encode()).hexdigest(),
                      question=question, answer_spans=answers, answer_passage_spans=selected_passages,
                      passage_candidates=passages, yes_no_answers=yes_no, annotation_answers=interpreted,
                      annotation_errors=annotation_errors, minimal_answer_evaluable=not annotation_errors,
                      no_answer=not annotation_errors and all(
                          answer["answer_type"] == "NO_ANSWER" for answer in interpreted),
                      document_url=url, title=row.get("document_title", ""), language=row["language"],
                      label_scope="source_qa_offsets_only", linking_gold_status="UNANNOTATED")
        records.append(record)
    return records, exclusions
