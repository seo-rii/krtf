"""Import independent KLUE/KONEC BIO boundaries without inventing entity IDs.

The original KLUE sentence ID groups KLUE and KONEC even when source text was
corrected. Imported NER labels are NOT linking gold; complete blind annotation
against a frozen glossary separately.
"""
from __future__ import annotations

import argparse
import csv
import io
import hashlib
import json
from pathlib import Path

SOURCES = {
    "klue": "https://github.com/KLUE-benchmark/KLUE",
    "konec": "https://github.com/korean-named-entity/konec",
}


def import_ner_tsv(content: str, *, source: str, revision: str, collected_at: str) -> list[dict]:
    if source not in SOURCES or not revision or not collected_at:
        raise ValueError("source, immutable revision and collection time required")
    records = []
    omitted_empty_ids = []
    row_id = None
    chars, tags = [], []
    source_file_hash = hashlib.sha256(content.encode()).hexdigest()
    def finish():
        if row_id is None:
            return
        text = "".join(chars)
        if not text:
            omitted_empty_ids.append(row_id)
            return
        spans = []
        active = None
        offset = 0
        for char, tag in zip(chars, tags):
            if tag == "O" or tag.startswith("B-"):
                if active is not None:
                    spans.append({"span": [active[0], offset], "type": active[1],
                                  "surface": text[active[0]:offset]})
                    active = None
                if tag.startswith("B-"):
                    active = (offset, tag[2:])
            elif tag.startswith("I-"):
                if active is None or active[1] != tag[2:]:
                    raise ValueError(f"invalid BIO continuation in {row_id}")
            else:
                raise ValueError(f"invalid BIO tag in {row_id}")
            offset += len(char)
        if active is not None:
            spans.append({"span": [active[0], offset], "type": active[1], "surface": text[active[0]:offset]})
        sha = hashlib.sha256(text.encode()).hexdigest()
        records.append({"document_id": f"{source}:{revision}:{row_id}",
                        "parent_document_id": "klue-ner:" + row_id, "source_row_id": row_id,
                        "dataset_revision": revision, "revision_kind": "pinned_local_source",
                        "collected_at": collected_at, "document_sha256": sha, "text": text,
                        "source": SOURCES[source], "source_file_sha256": source_file_hash,
                        "family_ids": [], "ner_annotations": spans,
                        "label_scope": "span_type_only", "linking_gold_status": "UNANNOTATED"})
    for line in content.splitlines():
        if line.startswith("## "):
            finish()
            row_id = line[3:].split(" ", 1)[0]
            chars, tags = [], []
        elif not line:
            continue
        elif line.startswith("#"):
            continue
        else:
            if row_id is None or "\t" not in line:
                raise ValueError("NER token outside sentence header or missing tab")
            char, tag = line.rsplit("\t", 1)
            if not char:
                raise ValueError("empty BIO token")
            chars.append(char)
            tags.append(tag)
    finish()
    if len({r["document_id"] for r in records}) != len(records):
        raise ValueError("duplicate original sentence ID")
    if records:
        records[0]["import_exclusions"] = {"empty_source_sentence_ids": omitted_empty_ids}
    return records


def import_koneobench_csv(content: str, *, revision: str, collected_at: str,
                         formations: tuple[str, ...] = ("축약", "혼성")) -> list[dict]:
    """Task-2 formation examples, with explicit reconstruction of masked usage.

    Source components form family keys, preventing component-overlap leakage.
    Entries still require independently annotated entity IDs/core/full semantics.
    """
    if not revision or not collected_at or not formations:
        raise ValueError("revision, collection time and formation scope required")
    records = []
    source_hash = hashlib.sha256(content.encode()).hexdigest()
    for row in csv.DictReader(io.StringIO(content.lstrip("\ufeff"))):
        if row["단어 형성법"] not in formations:
            continue
        term = row["정답 (표제어)"]
        components = [c.strip() for c in row["형태소 분석"].split("+") if c.strip()]
        masked = row["용례 (표제어 [MASK])"]
        if not row["IDX"] or not term or not components or not masked:
            raise ValueError("incomplete Task-2 formation record")
        text = masked.replace("[MASK]", term)
        sha = hashlib.sha256(text.encode()).hexdigest()
        records.append({"document_id": f"koneobench:{revision}:{row['IDX']}",
                        "parent_document_id": "koneobench:" + row["IDX"],
                        "source_row_id": row["IDX"], "dataset_revision": revision,
                        "revision_kind": "pinned_local_source", "collected_at": collected_at,
                        "source": "https://github.com/bcmilab/ko-neobench",
                        "source_file_sha256": source_hash, "document_sha256": sha, "text": text,
                        "source_masked_text": masked, "transformation": "replace_MASK_with_gold_headword" if "[MASK]" in masked else "source_usage_unchanged",
                        "term": term, "definition": row["뜻풀이"], "components": components,
                        "formation": row["단어 형성법"], "collection_year": row["수집 연도"],
                        "family_ids": ["koneobench-component:" + c for c in components],
                        "label_scope": "lexical_formation_only", "linking_gold_status": "UNANNOTATED"})
    if len({r["document_id"] for r in records}) != len(records):
        raise ValueError("duplicate KoNeoBench source ID")
    return records

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--source", choices=sorted(SOURCES) + ["koneobench"], required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--collected-at", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    content = Path(args.input).read_text(encoding="utf-8-sig")
    if args.source == "koneobench":
        records = import_koneobench_csv(content, revision=args.revision, collected_at=args.collected_at)
    else:
        records = import_ner_tsv(content, source=args.source, revision=args.revision, collected_at=args.collected_at)
    with Path(args.out).open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
