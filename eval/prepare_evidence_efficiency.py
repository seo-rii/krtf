"""Seal reviewed fresh source and per-request efficiency schemas before inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from .collect_hf_qa_queue import validate_public_json
from .evidence_efficiency import prepare_evidence_efficiency
from .evidence_efficiency_data import CASES_FILE, REVIEW_FILE, load_evidence_efficiency_records
from .hf_qa import canonical
from .prepare_followup import load_tokenizers
from .routing_confirmation import records_sha256
from .run_extended_suite import validate_requests


def prepare(config, out_dir, *, code_revision):
    if not re.fullmatch(r"[0-9a-f]{40}", code_revision):
        raise ValueError("immutable code revision required")
    if set(config["models"]) != {"gemma12b", "qwen27b"}:
        raise ValueError("both frozen model tokenizers required")
    source_hash = hashlib.sha256(CASES_FILE.read_bytes()).hexdigest()
    review_hash = hashlib.sha256(REVIEW_FILE.read_bytes()).hexdigest()
    if config.get("source_sha256") != source_hash or config.get("review_sha256") != review_hash:
        raise ValueError("source gold or independent review changed after selection")
    # The strict source loader checks full independent review coverage first.
    records = load_evidence_efficiency_records()
    review = json.loads(REVIEW_FILE.read_text())
    if len(records) != 64 or len({row["family_id"] for row in records}) != 8:
        raise ValueError("exactly 64 source documents and 8 source families required")
    split_cases = {split: sum(row["evaluation_split"] == split for row in records)
                  for split in ("development", "confirmation")}
    if split_cases != {"development": 16, "confirmation": 48}:
        raise ValueError("predeclared 16-development/48-confirmation source split required")
    record_hash = records_sha256(records)
    source = {
        "kind": "fresh_ai_authored_evidence_efficiency",
        "evaluation_population": "FRESH_AI_AUTHORED_CONFIRMATION",
        "source_sha256": source_hash, "review_sha256": review_hash,
        "records_sha256": record_hash, "source_gold_before_resolver": True,
        "human_verified": False, "private_workplace_distribution_measured": False,
        "prior_method_selection_run": "ktrf-evidence-20261021T020906Z",
        "independent_ai_review": {
            "reviewer": review["reviewer"], "cases_reviewed": len(review["reviewed_case_ids"]),
            "resolved_before_resolver": review["reviewed_before_resolver"],
            "records_sha256": record_hash,
        },
    }
    models = config["models"]
    envelope, proof = prepare_evidence_efficiency(
        records=records, tokenizers=load_tokenizers(models), models=models,
        code_revision=code_revision, source_provenance=source,
    )
    rows = validate_requests(envelope["requests"], envelope["protocol"])
    if len(rows) != 320:
        raise ValueError("complete 64-source five-condition matrix required")
    proof.update(file="evidence_efficiency.json", request_count=len(rows),
        requests_sha256=hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
        envelope_sha256=hashlib.sha256(canonical(envelope)).hexdigest())
    manifest = {
        "phase": "FINAL_FROZEN", "code_revision": code_revision, "source": source,
        "experiments": {"evidence_efficiency": proof}, "total_planned_model_calls": 640,
        "split_case_counts": split_cases,
        "real_business_shadow_status": "WAITING_FOR_INPUT",
        "raw_request_envelopes_and_individual_answers_remain_private": True,
        "fictional_source_gold_is_versioned": True,
        "methods_selected_from_prior_results_source_sealed_before_new_inference": True,
    }
    validate_public_json(manifest)
    root = Path(out_dir)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    (root / "evidence_efficiency.json").write_bytes(canonical(envelope))
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
    print(json.dumps({"phase": result["phase"], "total_planned_model_calls": 640}))


if __name__ == "__main__":
    main()
