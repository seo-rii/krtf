"""Resolver-independent document gold and reproducible split/report manifests.

CLI: python -m eval.blind_gold prepare --documents ... --out ... --seed ...
Annotation contains whole documents, never resolver predictions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def load_jsonl(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _validate_document(document: dict) -> None:
    for field in ("document_id", "parent_document_id", "source_row_id", "dataset_revision",
                  "collected_at", "document_sha256", "text"):
        if not document.get(field):
            raise ValueError(f"missing provenance: {field}; redownload legacy/unknown-revision corpus")
    if hashlib.sha256(document["text"].encode()).hexdigest() != document["document_sha256"]:
        raise ValueError("document content hash mismatch")


def annotation_packets(documents: list[dict], annotator: str) -> list[dict]:
    if not annotator:
        raise ValueError("annotator identity required")
    packets = []
    for doc in documents:
        _validate_document(doc)
        # Whitelist prevents accidentally revealing resolver-derived annotations.
        packets.append({"document_id": doc["document_id"], "text": doc["text"],
                        "document_sha256": doc["document_sha256"], "annotator": annotator,
                        "complete": False, "mentions": []})
    return packets


def validate_annotation(packet: dict) -> None:
    if packet.get("complete") is not True or not packet.get("annotator"):
        raise ValueError("annotation must be independently completed and identified")
    if hashlib.sha256(packet["text"].encode()).hexdigest() != packet["document_sha256"]:
        raise ValueError("annotation document hash mismatch")
    seen = set()
    for mention in packet["mentions"]:
        start, end = mention["span"]
        if not (type(start) is int and type(end) is int and 0 <= start < end <= len(packet["text"])):
            raise ValueError("invalid character span")
        if mention.get("surface") != packet["text"][start:end]:
            raise ValueError("surface does not match span")
        if (start, end) in seen:
            raise ValueError("duplicate mention")
        seen.add((start, end))
        label = mention["label"]
        if label not in {"LINK", "NIL", "AMBIGUOUS", "NON_MENTION"}:
            raise ValueError("unknown mention label")
        if label == "LINK" and not mention.get("entity_id"):
            raise ValueError("linked mentions require entity_id")
        if label == "NIL" and mention.get("entity_id"):
            raise ValueError("NIL means absent from the frozen glossary")
        if not isinstance(mention.get("should_commit"), bool):
            raise ValueError("explicit should_commit judgment required")
        if label != "LINK" and mention["should_commit"]:
            raise ValueError("only LINK can authorize a commit")
        if mention.get("full_identity") not in {"SAME", "DISTINCT", "JUXTAPOSED"}:
            raise ValueError("explicit full-surface semantics required")
        full_start, full_end = mention["full_span"]
        if not (type(full_start) is int and type(full_end) is int and 0 <= full_start <= start < end <= full_end <= len(packet["text"])):
            raise ValueError("full span must contain core span")


def adjudicate(first: dict, second: dict, decision: dict | None = None) -> dict:
    for packet in (first, second):
        validate_annotation(packet)
    if first["annotator"] == second["annotator"]:
        raise ValueError("two independent annotators required")
    for field in ("document_id", "text", "document_sha256"):
        if first[field] != second[field]:
            raise ValueError("annotators saw different documents")
    ordered = lambda p: sorted(p["mentions"], key=lambda m: m["span"])
    disagreement = ordered(first) != ordered(second)
    if disagreement and decision is None:
        raise ValueError("disagreement requires explicit adjudication")
    final = decision if disagreement else first
    if decision is not None:
        validate_annotation(decision)
        if decision["document_id"] != first["document_id"] or decision["text"] != first["text"]:
            raise ValueError("adjudication document mismatch")
        if not decision.get("adjudication_note"):
            raise ValueError("adjudication rationale required")
    return {**final, "annotation_ids": [first["annotator"], second["annotator"]],
            "had_disagreement": disagreement, "adjudicated": True,
            "independent_annotation_hashes": [digest(first), digest(second)]}


def grouped_split(documents: list[dict], seed: str = "blind-v1",
                  fractions: tuple[float, float, float] = (.6, .2, .2)) -> dict[str, str]:
    """Connected components prevent both document and family leakage.

    family_ids must be assigned independently of resolver output before splitting.
    Large connected families may yield empty partitions: report, do not row-split.
    """
    if len(fractions) != 3 or any(x < 0 for x in fractions) or abs(sum(fractions) - 1) > 1e-9:
        raise ValueError("train/validation/test fractions must sum to one")
    parents: dict[str, str] = {}
    def find(key):
        parents.setdefault(key, key)
        if parents[key] != key:
            parents[key] = find(parents[key])
        return parents[key]
    def union(a, b):
        a, b = find(a), find(b)
        parents[max(a, b)] = min(a, b)
    ids = set()
    for doc in documents:
        _validate_document(doc)
        doc_id = doc["document_id"]
        if doc_id in ids:
            raise ValueError("duplicate document_id")
        ids.add(doc_id)
        node = "doc:" + doc_id
        union(node, "parent:" + doc["parent_document_id"])
        union(node, "content:" + doc["document_sha256"])
        for family in doc.get("family_ids", []):
            union(node, "family:" + family)
    components: dict[str, list[str]] = {}
    for doc_id in sorted(ids):
        components.setdefault(find("doc:" + doc_id), []).append(doc_id)
    result = {}
    for members in components.values():
        # Based on sorted document IDs, independent of input order / union roots.
        value = int(digest([seed, members])[:16], 16) / 2**64
        part = "train" if value < fractions[0] else "validation" if value < sum(fractions[:2]) else "test"
        result.update({member: part for member in members})
    return result


def seal_manifest(documents: list[dict], assignments: dict[str, str], *, glossary_hash: str,
                  seed: str, code_revision: str, protocol: dict) -> dict:
    if not glossary_hash or not code_revision or not protocol:
        raise ValueError("glossary, code revision and predeclared protocol required")
    if set(assignments) != {d["document_id"] for d in documents}:
        raise ValueError("split must cover exactly the selected documents")
    manifest = {"schema_version": 1, "seed": seed, "code_revision": code_revision,
                "glossary_sha256": glossary_hash, "protocol": protocol,
                "documents": sorted([{k: d[k] for k in ("document_id", "parent_document_id",
                    "source_row_id", "dataset_revision", "document_sha256", "collected_at")} |
                    {"family_ids": sorted(d.get("family_ids", [])), "partition": assignments[d["document_id"]]}
                    for d in documents], key=lambda d: d["document_id"])}
    manifest["seal_sha256"] = digest(manifest)
    return manifest


def verify_manifest(manifest: dict, documents: list[dict]) -> None:
    payload = {k: v for k, v in manifest.items() if k != "seal_sha256"}
    if digest(payload) != manifest.get("seal_sha256"):
        raise ValueError("sealed manifest changed")
    actual = {d["document_id"]: d for d in documents}
    if set(actual) != {d["document_id"] for d in manifest["documents"]}:
        raise ValueError("document membership changed")
    for expected in manifest["documents"]:
        document = actual[expected["document_id"]]
        _validate_document(document)
        for field in ("parent_document_id", "source_row_id", "dataset_revision", "document_sha256", "collected_at"):
            if document[field] != expected[field]:
                raise ValueError("document provenance changed")
        if sorted(document.get("family_ids", [])) != expected["family_ids"]:
            raise ValueError("family membership changed")


def score_documents(gold: list[dict], predictions: dict[str, dict]) -> dict:
    """Score every annotated document, including mentions never retrieved."""
    if len({g["document_id"] for g in gold}) != len(gold):
        raise ValueError("duplicate gold document")
    if set(predictions) != {g["document_id"] for g in gold}:
        raise ValueError("predictions must cover exactly the audited documents")
    records = []
    families: dict[str, list[int]] = {}
    for packet in gold:
        validate_annotation(packet)
        if not packet.get("adjudicated") or len(set(packet.get("annotation_ids", []))) < 2:
            raise ValueError("independent, adjudicated document gold required")
        response = predictions[packet["document_id"]]
        if response.get("document_sha256") != packet["document_sha256"]:
            raise ValueError("prediction document hash mismatch")
        emitted = response.get("mentions", [])
        by_span = {}
        for mention in emitted:
            cp = mention["span"]["codepoint"]
            key = (cp["start"], cp["end"])
            if key in by_span:
                raise ValueError("duplicate prediction span")
            by_span[key] = mention
        counts = {"linked_mentions": 0, "candidate_hits": 0, "commit_eligible": 0,
                  "correct_commits": 0, "commits": 0, "commit_errors": 0,
                  "nil_mentions": 0, "nil_false_commits": 0,
                  "full_surface_checks": 0, "full_surface_errors": 0}
        expected = {tuple(m["span"]): m for m in packet["mentions"]}
        for span, mention in expected.items():
            got = by_span.get(span, {})
            committed = got.get("link_decision") == "RESOLVED"
            if mention["label"] == "LINK":
                counts["linked_mentions"] += 1
                candidates = {m.get("entity_id") for m in got.get("prediction_set", {}).get("members", [])}
                candidates.add(got.get("resolved_entity", {}).get("entity_id"))
                hit = mention["entity_id"] in candidates
                counts["candidate_hits"] += hit
                for family in mention.get("family_ids", [mention["entity_id"]]):
                    total_hit = families.setdefault(family, [0, 0])
                    total_hit[0] += 1
                    total_hit[1] += hit
                counts["commit_eligible"] += mention["should_commit"]
                counts["correct_commits"] += bool(committed and mention["should_commit"] and
                    got.get("resolved_entity", {}).get("entity_id") == mention["entity_id"])
                counts["full_surface_checks"] += 1
                identity = got.get("full_surface", {}).get("identity")
                identity_correct = identity == {"SAME": "SAME_AS_CORE", "DISTINCT": "DISTINCT_FROM_CORE",
                                                "JUXTAPOSED": "JUXTAPOSED"}[mention["full_identity"]]
                if mention["full_identity"] == "SAME" and identity is None and got and mention["full_span"] == mention["span"]:
                    identity_correct = True
                counts["full_surface_errors"] += not identity_correct
            if mention["label"] == "NIL":
                counts["nil_mentions"] += 1
                counts["nil_false_commits"] += committed
        for span, got in by_span.items():
            if got.get("link_decision") != "RESOLVED":
                continue
            counts["commits"] += 1
            target = expected.get(span)
            correct = bool(target and target["label"] == "LINK" and target["should_commit"] and
                           got.get("resolved_entity", {}).get("entity_id") == target["entity_id"])
            counts["commit_errors"] += not correct
        records.append({"document_id": packet["document_id"], **counts})
    totals = {k: sum(r[k] for r in records) for k in records[0] if k != "document_id"} if records else {}
    ratio = lambda num, den: totals.get(num, 0) / totals[den] if totals.get(den) else None
    return {"conditioning": "E2E_BLIND_DOCUMENT", "documents": len(gold), "counts": totals,
            "candidate_exact_link_recall": ratio("candidate_hits", "linked_mentions"),
            "family_macro_exact_link_recall": sum(h / n for n, h in families.values()) / len(families) if families else None,
            "eligible_commit_recall": ratio("correct_commits", "commit_eligible"),
            "commit_error_rate": ratio("commit_errors", "commits"),
            "nil_false_commit_rate": ratio("nil_false_commits", "nil_mentions"),
            "document_counts": records,
            "risk_status": "UNVALIDATED",  # correlated mention counts are not binomial risk evidence
            "quality_status": "MEASURED" if gold else "INSUFFICIENT_DATA"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--documents", required=True)
    prepare.add_argument("--out", required=True)
    prepare.add_argument("--seed", default="blind-v1")
    prepare.add_argument("--count", type=int, default=100)
    prepare.add_argument("--glossary", required=True)
    prepare.add_argument("--code-revision", required=True)
    prepare.add_argument("--protocol", required=True, help="predeclared protocol JSON")
    reconcile = sub.add_parser("adjudicate")
    reconcile.add_argument("--first", required=True)
    reconcile.add_argument("--second", required=True)
    reconcile.add_argument("--decisions", help="JSONL only for disputed documents")
    reconcile.add_argument("--out", required=True)
    score = sub.add_parser("score")
    for name in ("documents", "manifest", "gold", "predictions", "out"):
        score.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        if args.count <= 0:
            parser.error("count must be positive")
        documents = sorted(load_jsonl(args.documents), key=lambda d: digest([args.seed, d["document_id"]]))[:args.count]
        assignments = grouped_split(documents, args.seed)
        manifest = seal_manifest(documents, assignments, glossary_hash=hashlib.sha256(Path(args.glossary).read_bytes()).hexdigest(),
                                 seed=args.seed, code_revision=args.code_revision,
                                 protocol=json.loads(Path(args.protocol).read_text()))
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=False)
        for annotator in ("annotator-a", "annotator-b"):
            with (out / f"{annotator}.jsonl").open("w", encoding="utf-8") as stream:
                for packet in annotation_packets(documents, annotator):
                    stream.write(json.dumps(packet, ensure_ascii=False) + "\n")
        (out / "documents.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in documents), encoding="utf-8")
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    elif args.command == "adjudicate":
        first = load_jsonl(args.first)
        second_rows = load_jsonl(args.second)
        second = {p["document_id"]: p for p in second_rows}
        if len(second) != len(second_rows) or len({p["document_id"] for p in first}) != len(first):
            raise ValueError("duplicate annotation document")
        if set(second) != {p["document_id"] for p in first}:
            raise ValueError("annotation document membership differs")
        decisions = {p["document_id"]: p for p in load_jsonl(args.decisions)} if args.decisions else {}
        result = [adjudicate(p, second[p["document_id"]], decisions.get(p["document_id"])) for p in first]
        with Path(args.out).open("x", encoding="utf-8") as stream:
            for packet in result:
                stream.write(json.dumps(packet, ensure_ascii=False) + "\n")
    else:
        documents = load_jsonl(args.documents)
        manifest = json.loads(Path(args.manifest).read_text())
        verify_manifest(manifest, documents)
        test_ids = {d["document_id"] for d in manifest["documents"] if d["partition"] == "test"}
        gold = load_jsonl(args.gold)
        if {g["document_id"] for g in gold} != test_ids:
            raise ValueError("gold must cover the entire sealed test partition")
        by_id = {d["document_id"]: d for d in documents}
        for packet in gold:
            if packet["text"] != by_id[packet["document_id"]]["text"]:
                raise ValueError("gold document differs from sealed corpus")
        rows = load_jsonl(args.predictions)
        predictions = {r["document_id"]: r for r in rows}
        if len(predictions) != len(rows):
            raise ValueError("duplicate prediction document")
        report = score_documents(gold, predictions)
        report.update({"manifest_seal_sha256": manifest["seal_sha256"],
                       "gold_sha256": hashlib.sha256(Path(args.gold).read_bytes()).hexdigest(),
                       "predictions_sha256": hashlib.sha256(Path(args.predictions).read_bytes()).hexdigest()})
        with Path(args.out).open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
