"""Freeze review-driven experiments after source annotation, before inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from ktrf import compile_snapshot, load_glossary
from .collect_hf_qa_queue import validate_public_json
from .hf_qa import canonical
from .prepare_followup import load_tokenizers
from .prepare_extended_suite import PINNED_HASHES
from .review_business import (CASES_FILE, REVIEWED_CASE_FILE_SHA256,
                              load_business_records, prepare_review_business)
from .review_qa import prepare_review_qa
from .run_extended_suite import validate_requests
from .run_followup_queue import REVIEW_COUNTS

INPUT_NAMES = {"public_records", "natural_cases", "glossary", "nomiracl_manifest", "annotation_review"}


def prepare(config, out_dir, *, code_revision):
    if not re.fullmatch(r"[0-9a-f]{40}", code_revision) or set(config["inputs"]) != INPUT_NAMES:
        raise ValueError("frozen revision and all source/annotation inputs required")
    paths, hashes = {}, {}
    for name, spec in config["inputs"].items():
        paths[name] = Path(spec["path"])
        hashes[name] = hashlib.sha256(paths[name].read_bytes()).hexdigest()
        if hashes[name] != spec["sha256"]:
            raise ValueError("pinned review input changed: " + name)
    packet = json.loads(paths["public_records"].read_text())
    if (len(packet["records"]) != 64 or not packet["selection_before_resolver_and_generation"]
            or packet["source_file_sha256"] != PINNED_HASHES["source_file"]):
        raise ValueError("all 64 preselected public source contexts must be preserved")
    natural = json.loads(paths["natural_cases"].read_text())
    public_ids = {r["document_id"] for r in packet["records"]}
    if (len(natural["cases"]) != 32
            or not {r["document_id"] for r in natural["cases"]} <= public_ids):
        raise ValueError("natural target audit must retain its shared public context identities")
    review = json.loads(paths["annotation_review"].read_text())
    fixture_hash = hashlib.sha256(CASES_FILE.read_bytes()).hexdigest()
    if (review.get("before_resolver_and_generation") is not True
            or review.get("human_verified") is not False or review.get("reviewed_cases") != 96
            or review.get("authored_sha256") != fixture_hash
            or fixture_hash != REVIEWED_CASE_FILE_SHA256
            or review.get("natural_sha256") != hashes["natural_cases"]):
        raise ValueError("independent AI source/gold review seal required before resolution")
    source = {"source_packet_sha256": hashes["public_records"],
              "klue_revision": "349481ec73fff722f88e0453ca05c77a447d967c",
              "source_selection": packet["selection"], "input_sha256": hashes,
              "authored_sha256": fixture_hash, "annotation_origin": "AI_AUTHORED_AND_AI_REVIEWED",
              "human_verified": False, "shared_public_contexts_across_tracks": True,
              "private_business_distribution_measured": False}
    models = config["models"]
    if set(models) != {"gemma12b", "qwen27b"}:
        raise ValueError("both declared local model tokenizers required")
    tokenizers = load_tokenizers(models)
    # Authored labels and independent review are sealed before this first resolver call.
    routing, routing_proof, business = prepare_review_business(
        natural_cases=paths["natural_cases"], tokenizers=tokenizers,
        models=models, code_revision=code_revision)
    envelopes, experiments, selection = prepare_review_qa(
        records=packet["records"], snapshot=compile_snapshot(load_glossary(str(paths["glossary"]))),
        tokenizers=tokenizers, models=models, code_revision=code_revision, source_identity=source,
        exclusion_texts=(), nomiracl_manifest=paths["nomiracl_manifest"], business_records=business)
    if selection.get("selected_question_ids_sha256") is not None:
        from .run_hf_benchmark import digest
        if selection["selected_question_ids_sha256"] != digest(sorted(public_ids)):
            raise ValueError("public QA sample changed after its source annotation")
    envelopes["review_routing"] = routing
    experiments["review_routing"] = routing_proof
    if set(envelopes) != set(REVIEW_COUNTS):
        raise ValueError("all five review experiments required")
    for name, envelope in envelopes.items():
        rows = validate_requests(envelope["requests"], envelope["protocol"])
        if len(rows) != REVIEW_COUNTS[name]:
            raise ValueError("predeclared request matrix changed: " + name)
        experiments[name].update(file=name + ".json", request_count=len(rows),
            requests_sha256=hashlib.sha256(b"".join(canonical(r) for r in rows)).hexdigest(),
            envelope_sha256=hashlib.sha256(canonical(envelope)).hexdigest())
    manifest = {"phase": "FINAL_FROZEN", "code_revision": code_revision,
                "source": source, "selection": selection, "experiments": experiments,
                "annotation_review": review, "total_planned_model_calls": 2 * sum(REVIEW_COUNTS.values()),
                "raw_source_and_individual_answers_remain_private": True}
    validate_public_json(manifest)
    out_dir = Path(out_dir)
    out_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, envelope in envelopes.items():
        (out_dir / (name + ".json")).write_bytes(canonical(envelope))
    (out_dir / "manifest.json").write_bytes(canonical(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    proof = prepare(json.loads(args.config.read_text()), args.out_dir, code_revision=args.code_revision)
    print(json.dumps({"phase": proof["phase"], "total_planned_model_calls": proof["total_planned_model_calls"]}))


if __name__ == "__main__":
    main()
