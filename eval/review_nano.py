"""Compare lexical/nano on actual resolver candidates, including new source gold."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from .collect_hf_qa_queue import validate_public_json
from .hf_qa import canonical
from .occurrence_evidence_corpus import build_cases
from .review_business import CASES_FILE, REVIEWED_CASE_FILE_SHA256, load_business_records
from .review_cpu import evaluate_actual_candidates
from .run_context_ranking import StrictLocalScalarScorer
from .run_rerank_ablation import model_digest
from ktrf.rerank import LexicalCrossEncoder


def source_cases():
    if hashlib.sha256(CASES_FILE.read_bytes()).hexdigest() != REVIEWED_CASE_FILE_SHA256:
        raise ValueError("authored annotation changed after independent review")
    cases = [*build_cases(cohort="development"), *build_cases(cohort="heldout")]
    for record in load_business_records():
        core, full = record["target_core_span"], record["target_full_span"]
        cases.append({"case_id": record["case_id"], "cohort": "review_authored_business",
            "document_id": record["document_id"], "family_id": record["family_id"],
            "catalog_terms": record["terms"], "text": record["text"],
            "document_sha256": record["document_sha256"],
            "core_span": [core["start"], core["end"]],
            "full_surface_span": [full["start"], full["end"]],
            "stratum": record["stratum"], "semantic_label": record["gold"]["label"],
            "expected_entity_id": record["expected_entity_id"]})
    return cases


def run(out_dir, model_dir, *, device, code_revision):
    if not re.fullmatch(r"[0-9a-f]{40}", code_revision):
        raise ValueError("frozen code revision required")
    cases = source_cases()
    lexical = evaluate_actual_candidates(cases, LexicalCrossEncoder(), backend="lexical")
    scorer = StrictLocalScalarScorer(Path(model_dir), 1024, device)
    nano = evaluate_actual_candidates(cases, scorer, backend="nano")
    if lexical["input_sha256"] != nano["input_sha256"]:
        raise ValueError("candidate and evidence inputs changed between scorers")
    proof = {"protocol": "ktrf_review_actual_candidate_nano_v1", "code_revision": code_revision,
        "authored_source_sha256": REVIEWED_CASE_FILE_SHA256,
        "model_content_sha256": model_digest(Path(model_dir)),
        "actual_candidates_only": True, "gold_forced_candidates": False,
        "lexical": lexical, "nano": nano, "coverage_valid": False, "production_authorized": False,
        "limitations": ["Older development and heldout cohorts are exposed diagnostics.",
            "New business cases are AI authored and reviewed, with related templates and one registered entity per family.",
            "Frozen exploratory thresholds are not fitted or certified for the new actual-candidate distribution.",
            "Semantic evidence selection does not override structural guards or grant execution authority."]}
    validate_public_json(proof)
    target = Path(out_dir)
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    (target / "summary.json").write_bytes(canonical(proof))
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    proof = run(args.out_dir, args.model_dir, device=args.device, code_revision=args.code_revision)
    print(json.dumps({"status": "COMPLETE", "targets": proof["nano"]["target_events"]}))


if __name__ == "__main__":
    main()
