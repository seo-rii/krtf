"""Sealed, resolver-independent AI audit of real source paragraphs.

Raw source, independent annotations and predictions stay in the ignored bundle.
Only aggregate ``summary.json`` and the source-free manifest may be published.
This small exploratory audit neither fits calibration nor certifies deployment.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from .blind_gold import (adjudicate, digest, load_jsonl, score_documents,
                         seal_manifest, validate_annotation, verify_manifest)

PROTOCOL_ID = "blind_real_document_followup_v1_20261018"
SEED = "blind-document-followup-v1-20261018"
PARTITIONS = ("development", "calibration", "test")
LIMITATIONS = [
    "Two independent AI annotation passes, not human gold or independent human validation.",
    "Twenty-four source-first paragraphs do not represent deployment document prevalence.",
    "The finite existing 170-entity registry was fixed before reading resolver outputs.",
    "Named organizations and Korean first-level administrative regions are audited; persons, "
    "countries, historical polities, religions, products and competition events are outside scope.",
    "Within a proper organization name, a country adjective is not a separate mention; "
    "explicit alternative organization names and referential abbreviations are separate mentions.",
    "Parent articles and exact source content are disjoint from the previous HF generation "
    "pool, evidence sample and known local blind/wild documents; near-duplicate audit was not performed.",
    "All splits use the frozen policy. No threshold, calibration or model is fit from these data.",
    "Splits isolate parent documents, not entity families; no family-generalization claim is made.",
    "Reported errors are descriptive; correlated mentions and eight test documents cannot certify risk.",
    "All observed full-surface identities are SAME; this sample does not validate derived-sense guards.",
]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_private(path, value, *, lines=False):
    path = Path(path)
    data = ("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in value)
            if lines else json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    with path.open("x", encoding="utf-8") as stream:
        stream.write(data)
    path.chmod(0o600)


def _semantic_packet(packet):
    """Annotation prose is evidence; only semantic fields define agreement."""
    result = dict(packet)
    fields = ("span", "surface", "label", "entity_id", "should_commit", "full_span", "full_identity")
    result["mentions"] = sorted(
        [{key: mention.get(key) for key in fields} for mention in packet["mentions"]],
        key=lambda mention: mention["span"])
    return result


def validate_inputs(documents, first, second, glossary):
    """Require reviewed negatives as well as annotated positive documents."""
    from ktrf import load_glossary

    if len(documents) != 24 or len({doc["parent_document_id"] for doc in documents}) != 24:
        raise ValueError("exactly 24 parent-disjoint documents required")
    counts = Counter(doc.get("partition") for doc in documents)
    if counts != Counter({partition: 8 for partition in PARTITIONS}):
        raise ValueError("eight complete parent documents per partition required")
    ids = [doc["document_id"] for doc in documents]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate document IDs")
    known_entities = {entity.entity_id for entity in load_glossary(str(glossary)).entities}
    for annotations in (first, second):
        if len(annotations) != len(ids) or {row["document_id"] for row in annotations} != set(ids):
            raise ValueError("annotations must exhaustively cover every document, including negatives")
        by_id = {row["document_id"]: row for row in annotations}
        for document in documents:
            packet = by_id[document["document_id"]]
            validate_annotation(packet)
            if packet.get("annotation_kind") != "AI" or packet.get("resolver_outputs_seen", False):
                raise ValueError("explicit blind AI annotation provenance required")
            if not packet.get("review_note"):
                raise ValueError("each document requires an exhaustive-review note, including negatives")
            if any(packet.get(key) != document[key] for key in ("text", "document_sha256")):
                raise ValueError("annotation source drift")
            for mention in packet["mentions"]:
                if mention["label"] == "LINK" and mention["entity_id"] not in known_entities:
                    raise ValueError("LINK target absent from frozen glossary")


def seal_bundle(bundle, *, glossary, code_revision):
    """Run only before resolve; preserve both original passes and decisions."""
    bundle = Path(bundle)
    if (bundle / "gold.jsonl").exists() or (bundle / "manifest.json").exists():
        raise ValueError("bundle already sealed; do not overwrite")
    documents = load_jsonl(bundle / "documents.jsonl")
    first, second = [load_jsonl(bundle / f"annotator-{label}.jsonl") for label in ("a", "b")]
    validate_inputs(documents, first, second, glossary)
    second_by_id = {row["document_id"]: row for row in second}
    decisions = {row["document_id"]: row for row in load_jsonl(bundle / "decisions.jsonl")}
    gold, disagreements = [], []
    for original in first:
        other = second_by_id[original["document_id"]]
        a, b = _semantic_packet(original), _semantic_packet(other)
        disputed = a["mentions"] != b["mentions"]
        decision = decisions.get(original["document_id"])
        if disputed:
            disagreements.append(original["document_id"])
        if bool(decision) != disputed:
            raise ValueError("manual decisions must cover exactly semantic disagreements")
        final = adjudicate(a, b, _semantic_packet(decision) if decision else None)
        final["annotation_kind"] = "AI"
        final["resolver_outputs_seen"] = False
        final["independent_annotation_hashes"] = [digest(original), digest(other)]
        gold.append(final)
    validate_inputs(documents, gold, gold, glossary)
    _write_private(bundle / "gold.jsonl", gold, lines=True)
    assignments = {doc["document_id"]: doc["partition"] for doc in documents}
    manifest = seal_manifest(documents, assignments, glossary_hash=_sha(glossary), seed=SEED,
        code_revision=code_revision, protocol={"kind": PROTOCOL_ID,
        "annotation_kind": "AI", "annotation_before_resolver": True,
        "modes": ["fast", "commit"], "selection": "hash parent IDs; first literal source paragraph "
        "of 120..1200 codepoints; no term-presence filter", "limitations": LIMITATIONS})
    manifest.pop("seal_sha256")
    manifest["bundle_files"] = {name: _sha(bundle / name) for name in (
        "documents.jsonl", "annotator-a.jsonl", "annotator-b.jsonl", "decisions.jsonl", "gold.jsonl",
        "exclusions.json")}
    manifest["semantic_disagreement_documents"] = len(disagreements)
    manifest["preparation_module_sha256"] = _sha(__file__)
    manifest["source_intervals"] = [{key: doc[key] for key in (
        "document_id", "source_document_id", "source_document_sha256", "source_span", "source_file_sha256")}
        for doc in documents]
    manifest["seal_sha256"] = digest(manifest)
    _write_private(bundle / "manifest.json", manifest)
    return manifest


def verify_bundle(bundle, *, glossary, source):
    """Validate the sealed source intervals before evaluating any predictions."""
    from .hf_sources import load_tydi_records

    bundle = Path(bundle)
    manifest = json.loads((bundle / "manifest.json").read_text())
    documents = load_jsonl(bundle / "documents.jsonl")
    verify_manifest(manifest, documents)
    if manifest["glossary_sha256"] != _sha(glossary):
        raise ValueError("frozen glossary changed")
    for name, expected in manifest["bundle_files"].items():
        if _sha(bundle / name) != expected:
            raise ValueError("sealed annotation or input file changed")
    if {doc["source_file_sha256"] for doc in documents} != {_sha(source)}:
        raise ValueError("source file hash changed")
    source_records, _ = load_tydi_records(Path(source), invalid_minimal="record")
    by_id = {record["document_id"]: record for record in source_records}
    exclusions = json.loads((bundle / "exclusions.json").read_text())
    for document in documents:
        original = by_id[document["source_document_id"]]
        start, end = document["source_span"]
        if original["text"][start:end] != document["text"] or any(
                document[key] != original[key] for key in (
                "parent_document_id", "source_row_id", "dataset_revision", "source_file_sha256")):
            raise ValueError("source offset/provenance drift")
        if document["source_document_sha256"] != original["document_sha256"]:
            raise ValueError("source article hash drift")
        if (document["parent_document_id"] in exclusions["prior_parents"]
                or document["source_document_sha256"] in exclusions["prior_content_hashes"]):
            raise ValueError("prior document leakage")
    return manifest, documents, load_jsonl(bundle / "gold.jsonl")


def evaluate(bundle, *, glossary, source, code_revision, out_dir):
    """CPU queue step; raw predictions are private and never part of summaries."""
    from ktrf import compile_snapshot, load_glossary, resolve

    manifest, documents, gold = verify_bundle(bundle, glossary=glossary, source=source)
    snapshot = compile_snapshot(load_glossary(str(glossary)))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    outputs = {}
    for mode in ("fast", "commit"):
        predictions, elapsed = {}, []
        for document in documents:
            before = time.perf_counter()
            response = resolve(snapshot, document["text"], mode=mode,
                               options={"return_all_mentions": True})
            elapsed.append((time.perf_counter() - before) * 1000)
            predictions[document["document_id"]] = {
                "document_sha256": document["document_sha256"], "mentions": response["mentions"]}
        _write_private(out_dir / f"{mode}-predictions.json", predictions)
        all_scores = score_documents(gold, predictions)
        all_scores.pop("document_counts")
        splits = {}
        for partition in PARTITIONS:
            ids = {d["document_id"] for d in documents if d["partition"] == partition}
            part = score_documents([g for g in gold if g["document_id"] in ids],
                                   {key: value for key, value in predictions.items() if key in ids})
            part.pop("document_counts")
            splits[partition] = part
        outputs[mode] = {"all_documents": all_scores, "partitions": splits,
                         "latency_ms": {"total": sum(elapsed), "max": max(elapsed)},
                         "calibration_status": "HEURISTIC", "coverage_valid": False,
                         "risk_validation_status": "INSUFFICIENT_DATA"}
    counts = Counter(mention["label"] for packet in gold for mention in packet["mentions"])
    summary = {"schema_version": 1, "protocol": PROTOCOL_ID, "code_revision": code_revision,
        "measured_at": datetime.now(timezone.utc).isoformat(), "source_revision": documents[0]["dataset_revision"],
        "annotation_kind": "two_independent_AI_passes_manually_adjudicated", "documents": len(documents),
        "parent_articles": len({d["parent_document_id"] for d in documents}),
        "negative_documents": sum(not p["mentions"] for p in gold), "annotation_counts": dict(counts),
        "partition_documents": dict(Counter(d["partition"] for d in documents)),
        "semantic_disagreement_documents": manifest["semantic_disagreement_documents"],
        "manifest_seal_sha256": manifest["seal_sha256"], "glossary_sha256": _sha(glossary),
        "snapshot_id": snapshot.snapshot_id, "modes": outputs,
        "calibration_fit_status": "INSUFFICIENT_DATA", "calibration_fit_performed": False,
        "calibration_reasons": ["Only eight calibration parent documents; positive evidence may be absent.",
            "No predeclared independent risk-certified threshold fit; descriptive audit only."],
        "risk_validation_status": "INSUFFICIENT_DATA", "coverage_valid": False, "set_confidence": None,
        "limitations": LIMITATIONS}
    _write_private(out_dir / "summary.json", summary)
    _write_private(out_dir / "manifest.json", manifest)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--glossary", type=Path, default=Path("examples/realorg_glossary.yaml"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--seal-only", action="store_true")
    args = parser.parse_args()
    if args.seal_only:
        manifest = seal_bundle(args.bundle, glossary=args.glossary, code_revision=args.code_revision)
        print(json.dumps({"status": "SEALED", "seal_sha256": manifest["seal_sha256"]}))
    else:
        if args.source is None or args.out_dir is None:
            parser.error("evaluation requires --source and --out-dir")
        result = evaluate(args.bundle, glossary=args.glossary, source=args.source,
                          code_revision=args.code_revision, out_dir=args.out_dir)
        print(json.dumps({"status": "COMPLETED", "documents": result["documents"],
                          "risk_validation_status": result["risk_validation_status"]}))


if __name__ == "__main__":
    main()
