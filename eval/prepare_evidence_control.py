"""Freeze the exposed-development evidence control before new GPU generation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from .collect_hf_qa_queue import validate_public_json
from .evidence_control import prepare_evidence_control
from .hf_qa import canonical
from .prepare_followup import load_tokenizers
from .routing_confirmation import records_sha256
from .routing_confirmation_data import CASES_FILE, REVIEW_FILE, load_routing_confirmation_records
from .run_extended_suite import validate_requests


def prepare(config, out_dir, *, code_revision):
    if not re.fullmatch(r"[0-9a-f]{40}", code_revision):
        raise ValueError("immutable code revision required")
    if set(config["models"]) != {"gemma12b", "qwen27b"}:
        raise ValueError("both frozen model tokenizers required")
    source_hash = hashlib.sha256(CASES_FILE.read_bytes()).hexdigest()
    review_hash = hashlib.sha256(REVIEW_FILE.read_bytes()).hexdigest()
    if config.get("source_sha256") != source_hash or config.get("review_sha256") != review_hash:
        raise ValueError("source gold or independent review changed")
    records = load_routing_confirmation_records("development")
    review = json.loads(REVIEW_FILE.read_text())
    record_hash = records_sha256(records)
    if len(records) != 64 or len({row["family_id"] for row in records}) != 8:
        raise ValueError("exactly 64 exposed development cases from 8 families required")
    source = {
        "kind": "exposed_confirmation_development_diagnostic",
        "evaluation_population": "EXPOSED_DIAGNOSTIC", "selected_split": "development",
        "source_sha256": source_hash, "review_sha256": review_hash,
        "records_sha256": record_hash, "source_gold_before_resolver": True,
        "human_verified": False, "private_workplace_distribution_measured": False,
        "prior_generation_run": "ktrf-confirmation-20261020T105734Z",
        "original_review_applies_to_source_labels_only": True,
        "independent_ai_review": {
            "reviewer": review["reviewer"], "cases_reviewed": len(records),
            "original_cases_reviewed": len(review["reviewed_case_ids"]),
            "resolved_before_resolver": review["reviewed_before_resolver"],
            "records_sha256": record_hash,
        },
    }
    models = config["models"]
    envelope, proof = prepare_evidence_control(
        records=records, tokenizers=load_tokenizers(models), models=models,
        code_revision=code_revision, source_provenance=source,
    )
    rows = validate_requests(envelope["requests"], envelope["protocol"])
    if len(rows) != 256:
        raise ValueError("complete 64-case four-condition matrix required")
    proof.update(file="evidence_control.json", request_count=len(rows),
        requests_sha256=hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
        envelope_sha256=hashlib.sha256(canonical(envelope)).hexdigest())
    manifest = {
        "phase": "FINAL_FROZEN", "code_revision": code_revision, "source": source,
        "experiments": {"evidence_control": proof}, "total_planned_model_calls": 512,
        "real_business_shadow_status": "WAITING_FOR_INPUT",
        "raw_request_envelopes_and_individual_answers_remain_private": True,
        "fictional_source_gold_is_versioned": True,
        "posthoc_method_selection_not_independent_confirmation": True,
    }
    validate_public_json(manifest)
    root = Path(out_dir)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    (root / "evidence_control.json").write_bytes(canonical(envelope))
    (root / "manifest.json").write_bytes(canonical(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    result = prepare(json.loads(args.config.read_text()), args.out_dir,
                     code_revision=args.code_revision)
    print(json.dumps({"phase": result["phase"], "total_planned_model_calls": 512}))


if __name__ == "__main__":
    main()
