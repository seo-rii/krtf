"""Local source-first annotation packets and non-executing resolver replay.

This ingress never calls an LLM or a downstream business API. Source documents
remain private; the manifest describes integrity, not annotation correctness.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import time


SCHEMA_VERSION = 1
ANNOTATION_LABELS = ("LINK", "NIL", "NON_MENTION", "COMPOSITIONAL", "AMBIGUOUS")
SOURCE_KEYS = ("document_id", "family_id", "parent_document_id", "event_id",
               "source_row_id", "source_revision", "source_uri", "collected_at")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def load_shadow_documents(path, *, max_documents=200):
    """Validate unchanged source text; maintain transitive source components."""
    if type(max_documents) is not int or not 1 <= max_documents <= 1000:
        raise ValueError("max_documents must be between 1 and 1000")
    raw = Path(path).read_bytes()
    documents, ids, hashes = [], set(), set()
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"source line {line_number} must be an object")
        for key in ("document_id", "family_id", "text"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"source line {line_number} requires {key}")
        for key in SOURCE_KEYS:
            if key in row and row[key] is not None and (
                    not isinstance(row[key], str) or not row[key].strip()):
                raise ValueError(f"source field {key} must be a nonempty string or null")
        digest = _sha(row["text"].encode("utf-8"))
        if row["document_id"] in ids:
            raise ValueError("duplicate document_id")
        if digest in hashes:
            raise ValueError("duplicate source text; retain one document before sampling")
        if "document_sha256" in row and row["document_sha256"] != digest:
            raise ValueError("document_sha256 does not match unchanged source text")
        partition = row.get("partition", "audit")
        if partition not in {"development", "confirmation", "audit"}:
            raise ValueError("partition must be development, confirmation or audit")
        origin = row.get("source_origin", row.get("origin", "USER_PROVIDED_UNVERIFIED"))
        if origin not in {"AI_AUTHORED", "PUBLIC_SOURCE", "USER_PROVIDED_UNVERIFIED"}:
            raise ValueError("unknown source_origin")
        # Keep the input verbatim separately; never carry proposed labels/results
        # into the blind annotation packet or replay requests.
        source = {key: row.get(key) for key in SOURCE_KEYS}
        source["source_row_id"] = source["source_row_id"] or f"line:{line_number}"
        documents.append({**source, "text": row["text"], "partition": partition,
                          "source_origin": origin, "human_verified": False,
                          "document_sha256": digest, "input_line_number": line_number})
        ids.add(row["document_id"])
        hashes.add(digest)
        if len(documents) > max_documents:
            raise ValueError("document limit exceeded; split source groups explicitly")
    if not documents:
        raise ValueError("at least one source document required")
    parents = list(range(len(documents)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    seen = {}
    for index, row in enumerate(documents):
        tokens = [("family", row["family_id"]), ("document", row["document_id"])]
        if row["parent_document_id"]:
            tokens.append(("document", row["parent_document_id"]))
        if row["event_id"]:
            tokens.append(("event", row["event_id"]))
        for token in tokens:
            if token in seen:
                parents[find(index)] = find(seen[token])
            else:
                seen[token] = index
    components = {}
    for index, row in enumerate(documents):
        components.setdefault(find(index), []).append(row)
    for rows in components.values():
        if len({row["partition"] for row in rows}) > 1:
            raise ValueError("connected source component crosses declared partitions")
        component_id = "source-" + _sha(_json(sorted(
            (row["document_id"], row["document_sha256"]) for row in rows)))
        for row in rows:
            row["source_component_id"] = component_id
    return documents, _sha(raw)


def _write(path, data):
    with open(path, "xb") as handle:
        os.chmod(path, 0o600)
        handle.write(data)


def _percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def prepare_shadow(input_jsonl, glossary_path, out_dir, *, replay=False, repeats=3,
                   max_documents=200):
    """Export a blind packet first, optionally record local resolver proposals.

    ``replay`` emits suggestions for human review only. It deliberately exposes
    no action callback, network endpoint, executable output or automated gold.
    The default packet preparation never invokes the resolver.
    """
    if type(replay) is not bool or type(repeats) is not int or not 1 <= repeats <= 20:
        raise ValueError("replay must be boolean and repeats must be between 1 and 20")
    source_raw = Path(input_jsonl).read_bytes()
    documents, source_hash = load_shadow_documents(input_jsonl, max_documents=max_documents)
    if _sha(source_raw) != source_hash:
        raise ValueError("source changed while preparing the packet")
    glossary_raw = Path(glossary_path).read_bytes()
    import yaml
    from ktrf.glossary import load_glossary
    from ktrf.snapshot import compile_snapshot
    glossary = load_glossary(yaml.safe_load(glossary_raw))
    snapshot = compile_snapshot(glossary, run_conformance=False)
    if any(len(row["text"].encode()) > snapshot.policy.sync_max_input_bytes for row in documents):
        raise ValueError("source document exceeds synchronous limit; no automatic text truncation")
    output = Path(out_dir)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    _write(output / "source.jsonl", source_raw)
    _write(output / "glossary.yaml", glossary_raw)
    packet = {
        "schema_version": SCHEMA_VERSION, "purpose": "BLIND_DOCUMENT_ANNOTATION",
        "source_sha256": source_hash, "glossary_sha256": _sha(glossary_raw),
        "annotation_status": "UNANNOTATED", "annotation_origin": None,
        "human_verified": False, "resolver_output_visible": False,
        "instructions": [
            "Read the entire original document and the reference glossary.",
            "Annotate every relevant occurrence, including missed, NIL and non-mention cases.",
            "Use codepoint {start,end} core_span and full_span; preserve original text.",
            "Record label, entity_id or null, rationale, terminology_needed, reviewer and origin.",
            "Keep first-pass annotations separate from resolver suggestions and adjudication.",
        ],
        "labels": list(ANNOTATION_LABELS),
        "documents": [{**row, "annotations": [], "annotation_status": "UNANNOTATED"}
                      for row in documents],
    }
    _write(output / "blind_annotation.json", _json(packet) + b"\n")
    requests = [{**row, "snapshot_id": snapshot.snapshot_id, "mode": "commit",
                 "purpose": "SHADOW_PROPOSAL_ONLY", "execution_enabled": False}
                for row in documents]
    _write(output / "shadow_requests.jsonl", b"".join(_json(row) + b"\n" for row in requests))
    timing = None
    if replay:
        # Packet has already been written before the first resolver call.
        from ktrf.resolver import resolve
        proposals, cold_ms, repeat_ms = [], [], []
        for row in requests:
            start = time.perf_counter()
            response = resolve(snapshot, row["text"], mode="commit",
                               options={"return_all_mentions": True})
            cold_ms.append((time.perf_counter() - start) * 1000)
            for _ in range(repeats):
                start = time.perf_counter()
                resolve(snapshot, row["text"], mode="commit",
                        options={"return_all_mentions": True})
                repeat_ms.append((time.perf_counter() - start) * 1000)
            proposals.append({
                "document_id": row["document_id"], "document_sha256": row["document_sha256"],
                "source_component_id": row["source_component_id"],
                "snapshot_id": snapshot.snapshot_id, "purpose": "SHADOW_PROPOSAL_ONLY",
                "execution_enabled": False, "action_performed": False,
                "semantic_correctness": None, "resolver_response": response,
            })
        _write(output / "shadow_proposals.jsonl", b"".join(_json(row) + b"\n" for row in proposals))
        timing = {
            "scope": "in_process_symbolic_resolve_only",
            "snapshot_compile_included": False, "llm_included": False,
            "network_included": False, "human_review_time_ms": None,
            "machine": {"platform": platform.platform(), "python": platform.python_version()},
            "first_call_per_document_ms": cold_ms, "repeat_call_ms": repeat_ms,
            "repeat_count_per_document": repeats,
            "repeat_p50_ms": _percentile(repeat_ms, .5),
            "repeat_p95_ms": _percentile(repeat_ms, .95),
            "repeat_p99_ms": _percentile(repeat_ms, .99),
            "independent_samples": False,
        }
        _write(output / "resolver_latency.json", _json(timing) + b"\n")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "SHADOW_REPLAY_COMPLETE" if replay else "ANNOTATION_PACKET_READY",
        "real_business_pilot_status": ("NOT_ACTUAL_BUSINESS_INPUT"
            if all(row["source_origin"] == "AI_AUTHORED" for row in documents)
            else "AWAITING_INDEPENDENT_ANNOTATION"),
        "input_sha256": source_hash, "glossary_sha256": _sha(glossary_raw),
        "snapshot_id": snapshot.snapshot_id, "document_count": len(documents),
        "source_component_count": len({row["source_component_id"] for row in documents}),
        "partition_counts": dict(Counter(row["partition"] for row in documents)),
        "source_origin_counts": dict(Counter(row["source_origin"] for row in documents)),
        "actual_business_data_verified": False,
        "execution_enabled": False, "actions_performed": 0,
        "human_verified": False, "semantic_accuracy": None,
        "resolver_calls": len(documents) * (repeats + 1) if replay else 0,
        "latency_measured": timing is not None,
        "limitations": [
            "User-provided provenance is preserved, not externally authenticated.",
            "Connected source components are grouping units, not proof of statistical independence.",
            "Resolver output is a proposal and does not annotate or authorize the document.",
            "Latency excludes compilation, LLM, network, downstream action and human review.",
        ],
    }
    summary = {key: value for key, value in manifest.items()}
    summary["publication"] = "AGGREGATE_ONLY_NO_SOURCE_TEXT_OR_INDIVIDUAL_TIMINGS"
    summary["latency"] = None
    if timing is not None:
        summary["latency"] = {
            key: timing[key] for key in ("scope", "snapshot_compile_included",
                "llm_included", "network_included", "human_review_time_ms",
                "repeat_count_per_document", "independent_samples")}
        for field in ("first_call_per_document_ms", "repeat_call_ms"):
            values = timing[field]
            summary["latency"][field] = {
                "observations": len(values), "total": sum(values),
                "min": min(values), "max": max(values),
                "p50": _percentile(values, .5), "p95": _percentile(values, .95),
                "p99": _percentile(values, .99),
            }
    _write(output / "summary.json", _json(summary) + b"\n")
    manifest["files"] = {path.name: _sha(path.read_bytes()) for path in sorted(output.iterdir())}
    _write(output / "manifest.json", _json(manifest) + b"\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", required=True, type=Path)
    parser.add_argument("--glossary", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--repeats", default=3, type=int)
    parser.add_argument("--max-documents", default=200, type=int)
    args = parser.parse_args()
    manifest = prepare_shadow(args.documents, args.glossary, args.out_dir,
                              replay=args.replay, repeats=args.repeats,
                              max_documents=args.max_documents)
    print(json.dumps({key: manifest[key] for key in ("status", "document_count",
                     "source_component_count", "execution_enabled", "resolver_calls")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
