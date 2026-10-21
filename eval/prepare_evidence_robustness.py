"""Seal a six-arm robustness diagnostic on previously used fictional source.

The source's development/confirmation labels describe its original collection.
Reusing those documents does not create another independent validation set.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re

from .collect_hf_qa_queue import validate_public_json
from .evidence_efficiency_data import CASES_FILE, REVIEW_FILE, load_evidence_efficiency_records
from .evidence_robustness import CONDITIONS, POPULATION, prepare_evidence_robustness
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
    records = load_evidence_efficiency_records()
    review = json.loads(REVIEW_FILE.read_text())
    originals = {row["case_id"]: row for row in records}
    if (len(records) != 64 or len(originals) != 64
            or len({row["family_id"] for row in records}) != 8):
        raise ValueError("exactly 64 unique source documents and 8 source families required")
    split_cases = dict(Counter(row["evaluation_split"] for row in records))
    split_families = {split: {row["family_id"] for row in records
                              if row["evaluation_split"] == split}
                      for split in ("development", "confirmation")}
    if (split_cases != {"development": 16, "confirmation": 48}
            or len(split_families["development"]) != 2
            or len(split_families["confirmation"]) != 6
            or not split_families["development"].isdisjoint(split_families["confirmation"])):
        raise ValueError("historical 16-development/48-confirmation family split required")
    if (set(review["reviewed_case_ids"]) != set(originals)
            or len(review["reviewed_case_ids"]) != 64
            or review["reviewed_before_resolver"] is not True):
        raise ValueError("historical independent AI review must cover every source case")
    record_hash = records_sha256(records)
    source = {
        "kind": "reused_ai_authored_evidence_efficiency",
        "evaluation_population": POPULATION,
        "source_sha256": source_hash, "review_sha256": review_hash,
        "records_sha256": record_hash, "source_gold_before_resolver": True,
        "human_verified": False, "private_workplace_distribution_measured": False,
        "independent_validation": False, "reused_source": True,
        "prior_source_run": "ktrf-efficiency-20261021T145325Z",
        "methods_predeclared_without_reading_prior_run_responses": True,
        "source_origin_split": "historical_development_confirmation_no_new_holdout",
        "independent_ai_review": {
            "reviewer": review["reviewer"], "cases_reviewed": len(review["reviewed_case_ids"]),
            "resolved_before_resolver": review["reviewed_before_resolver"],
            "records_sha256": record_hash,
        },
    }
    models = config["models"]
    envelope, proof = prepare_evidence_robustness(
        records=records, tokenizers=load_tokenizers(models), models=models,
        code_revision=code_revision, source_provenance=source,
    )
    rows = validate_requests(envelope["requests"], envelope["protocol"])
    grouped = defaultdict(list)
    fixed = ("text", "document_sha256", "target_surface", "target_core_span", "target_full_span",
             "gold", "expected_entity_id", "family_id", "document_id", "parent_document_id",
             "evaluation_split")
    for row in rows:
        original = originals.get(row["case_id"])
        if (original is None or any(row.get(key) != original[key] for key in fixed)
                or row.get("source_origin_split") != original["evaluation_split"]
                or row.get("evaluation_population") != POPULATION
                or row.get("independent_validation") is not False):
            raise ValueError("paired requests changed historical source or reused diagnostic population")
        grouped[row["case_id"]].append(row)
    if (len(rows) != 384 or set(grouped) != set(originals)
            or any(len(group) != 6 or {row["condition"] for row in group} != set(CONDITIONS)
                   for group in grouped.values())):
        raise ValueError("complete 64-source six-condition matrix required")
    proof.update(file="evidence_robustness.json", request_count=len(rows),
        requests_sha256=hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
        envelope_sha256=hashlib.sha256(canonical(envelope)).hexdigest())
    manifest = {
        "phase": "FINAL_FROZEN", "code_revision": code_revision, "source": source,
        "experiments": {"evidence_robustness": proof}, "total_planned_model_calls": 768,
        "split_case_counts": split_cases, "source_origin_split_case_counts": split_cases,
        "split_counts_describe": "historical_source_origin_only_no_new_holdout",
        "independent_validation": False,
        "real_business_shadow_status": "WAITING_FOR_INPUT",
        "raw_request_envelopes_and_individual_answers_remain_private": True,
        "fictional_source_gold_is_versioned": True,
        "methods_predeclared_without_reading_prior_run_responses": True,
    }
    validate_public_json(manifest)
    root = Path(out_dir)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    (root / "evidence_robustness.json").write_bytes(canonical(envelope))
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
    print(json.dumps({"phase": result["phase"], "total_planned_model_calls": 768}))


if __name__ == "__main__":
    main()
