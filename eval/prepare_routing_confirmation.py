"""Seal new source-reviewed occurrence requests before any model generation."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re

from ktrf.registry.simple_schema import compile_simple_terms
from .collect_hf_qa_queue import validate_public_json
from .hf_qa import canonical
from .prepare_followup import load_tokenizers
from .routing_confirmation import prepare_routing_confirmation, records_sha256
from .routing_confirmation_data import (
    CASES_FILE, REVIEW_FILE, load_routing_confirmation_records,
)
from .run_extended_suite import validate_requests


def prepare(config, out_dir, *, code_revision):
    if not re.fullmatch(r"[0-9a-f]{40}", code_revision):
        raise ValueError("immutable code revision required")
    if set(config["models"]) != {"gemma12b", "qwen27b"}:
        raise ValueError("both frozen model tokenizers required")
    source_hash = hashlib.sha256(CASES_FILE.read_bytes()).hexdigest()
    review_hash = hashlib.sha256(REVIEW_FILE.read_bytes()).hexdigest()
    if config.get("source_sha256") != source_hash or config.get("review_sha256") != review_hash:
        raise ValueError("source gold or independent review changed after queue selection")
    # Loader verifies exact review coverage before any production resolution.
    records = load_routing_confirmation_records()
    review = json.loads(REVIEW_FILE.read_text())
    record_hash = records_sha256(records)
    source = {
        "kind": "fresh_ai_authored_routing_families",
        "source_sha256": source_hash, "review_sha256": review_hash,
        "records_sha256": record_hash, "source_gold_before_resolver": True,
        "human_verified": False, "private_workplace_distribution_measured": False,
        "independent_ai_review": {
            "reviewer": review["reviewer"], "cases_reviewed": len(review["reviewed_case_ids"]),
            "resolved_before_resolver": review["reviewed_before_resolver"],
            "records_sha256": record_hash,
        },
    }
    models = config["models"]
    envelope, proof = prepare_routing_confirmation(
        records=records, tokenizers=load_tokenizers(models), models=models,
        code_revision=code_revision, source_provenance=source,
    )
    rows = validate_requests(envelope["requests"], envelope["protocol"])
    if len(rows) != 1152 or len(records) != 192:
        raise ValueError("complete 192-target six-condition matrix required")
    proof.update(
        file="routing_confirmation.json", request_count=len(rows),
        requests_sha256=hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
        envelope_sha256=hashlib.sha256(canonical(envelope)).hexdigest(),
    )
    manifest = {
        "phase": "FINAL_FROZEN", "code_revision": code_revision, "source": source,
        "experiments": {"routing_confirmation": proof},
        "total_planned_model_calls": 2304,
        "real_business_shadow_status": "WAITING_FOR_INPUT",
        "raw_request_envelopes_and_individual_answers_remain_private": True,
        "fictional_source_gold_is_versioned": True,
    }
    validate_public_json(manifest)
    root = Path(out_dir)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    (root / "routing_confirmation.json").write_bytes(canonical(envelope))
    # This replay exercises the ingress pipeline, not a real workplace audit.
    shadow_rows = [{
        "document_id": row["document_id"], "family_id": row["family_id"],
        "text": row["text"], "source_origin": "AI_AUTHORED",
        "source_revision": source_hash, "partition": row["evaluation_split"],
    } for row in records]
    terms = {}
    for row in records:
        for term in row["terms"]:
            item = deepcopy(term)
            item.pop("applicability", None)
            if item["key"] in terms and terms[item["key"]] != item:
                raise ValueError("conflicting source-world glossary entry")
            terms[item["key"]] = item
    glossary = compile_simple_terms(
        {"terms": list(terms.values())}, scope="global",
        glossary_id="synthetic-confirmation-shadow",
    )
    (root / "synthetic_shadow.jsonl").write_bytes(b"".join(canonical(row) for row in shadow_rows))
    (root / "synthetic_glossary.json").write_bytes(canonical(glossary))
    (root / "manifest.json").write_bytes(canonical(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    result = prepare(json.loads(args.config.read_text()), args.out_dir, code_revision=args.code_revision)
    print(json.dumps({"phase": result["phase"], "total_planned_model_calls": 2304}))


if __name__ == "__main__":
    main()
