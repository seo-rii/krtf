"""Freeze follow-on diagnostics against sealed inputs, without reading model outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from ktrf import compile_snapshot, load_glossary
from .collect_hf_qa_queue import validate_public_json
from .diagnostic_qa import prepare_qa_diagnostics
from .diagnostic_safety import prepare_robustness
from .extended_qa import _corpus_pool, load_mrc_records, select_samples
from .hf_qa import canonical
from .prepare_extended_suite import INPUT_NAMES as SOURCE_INPUTS, PINNED_HASHES, REVISION, load_exclusions
from .prepare_followup import _sha_file, load_tokenizers
from .run_extended_suite import load_request_file, validate_requests
from .run_hf_benchmark import digest
from .run_followup_queue import DIAGNOSTIC_COUNTS, EXTENDED_KIND, validate_plan

PRIOR_EXPERIMENTS = {"prior_budget": "budget", "prior_transfer": "transfer",
                     "prior_corpus": "corpus", "prior_safety": "semantic_safety"}
INPUT_NAMES = {*SOURCE_INPUTS, *PRIOR_EXPERIMENTS, "prior_plan"}


def prior_corpus_exclusions(records, exclusions, prior_transfer, prior_corpus):
    """Reproduce every earlier search document, including unreturned distractors."""
    selected, _, eligible, selection = select_samples(records, exclusions)
    prior_ids = {r["document_id"] for r in prior_transfer["requests"]}
    if {r["document_id"] for r in selected} != prior_ids:
        raise ValueError("earlier frozen question selection cannot be reproduced")
    pool = _corpus_pool([r for r in selected if r["positive_gold"]], eligible)
    pool_hash = digest(sorted(r["document_sha256"] for r in pool))
    for envelope in (prior_transfer, prior_corpus):
        if envelope["provenance"].get("corpus_document_hashes_sha256") != pool_hash:
            raise ValueError("earlier complete retrieval corpus differs from frozen hash")
    return [r["text"] for r in pool], {
        "excluded_search_contexts": len(pool), "excluded_search_context_hashes_sha256": pool_hash,
        "reproduced_prior_selection_sha256": selection["selected_question_ids_sha256"],
        "all_prior_search_contexts_excluded_even_if_not_returned": True}


def prepare(config, out_dir, *, code_revision):
    if not re.fullmatch(r"[0-9a-f]{40}", code_revision) or set(config["inputs"]) != INPUT_NAMES:
        raise ValueError("immutable revision and all pinned source/prior inputs required")
    paths, hashes = {}, {}
    for name, spec in config["inputs"].items():
        paths[name] = Path(spec["path"])
        hashes[name] = _sha_file(paths[name])
        if hashes[name] != spec["sha256"] or name in PINNED_HASHES and hashes[name] != PINNED_HASHES[name]:
            raise ValueError("input differs from pinned identity: " + name)
    old_plan = validate_plan(json.loads(paths["prior_plan"].read_text())["queue_plan"])
    if old_plan["kind"] != EXTENDED_KIND:
        raise ValueError("completed extended protocol must be the declared diagnostic source")
    prior = {}
    for name, experiment in PRIOR_EXPERIMENTS.items():
        stage = next(s for s in old_plan["stages"]
                     if s["experiment"] == experiment and s["model_key"] == "gemma12b")
        rows, protocol, provenance = load_request_file(paths[name])
        if (hashes[name] != stage["envelope_sha256"] or protocol["experiment"] != experiment
                or len(rows) != stage["request_count"] or provenance["code_revision"] != old_plan["code_revision"]
                or hashlib.sha256(b"".join(canonical(r) for r in rows)).hexdigest() != stage["requests_sha256"]):
            raise ValueError("prior envelope differs from published frozen plan")
        prior[name] = {"requests": rows, "protocol": protocol, "provenance": provenance}
    original_source = prior["prior_transfer"]["provenance"]["source"]
    if any(original_source["exclusion_input_sha256"].get(name) != hashes[name] for name in SOURCE_INPUTS):
        raise ValueError("original source or exclusion corpus has changed")
    models = config["models"]
    if set(models) != {"gemma12b", "qwen27b"}:
        raise ValueError("both actual model tokenizers required")
    records, inventory = load_mrc_records(paths["source_file"])
    exclusions, exclusion_inventory = load_exclusions(paths)
    old_corpus, corpus_proof = prior_corpus_exclusions(records, exclusions,
        prior["prior_transfer"], prior["prior_corpus"])
    identity = {"dataset": "klue/klue", "revision": REVISION,
        "file": "mrc/validation-00000-of-00001.parquet", "sha256": hashes["source_file"],
        "card_sha256": hashes["card"], "license": "cc-by-sa-4.0 (HF card declaration)",
        "inventory": inventory, "input_sha256": hashes, "prior_code_revision": old_plan["code_revision"],
        "prior_exclusions": exclusion_inventory, "prior_search_exclusion": corpus_proof}
    tokenizers = load_tokenizers(models)
    envelopes, manifest = prepare_qa_diagnostics(
        prior_budget_envelope=prior["prior_budget"], prior_transfer_envelope=prior["prior_transfer"],
        records=records, snapshot=compile_snapshot(load_glossary(str(paths["glossary"]))),
        tokenizers=tokenizers, models=models, code_revision=code_revision, source_identity=identity,
        exclusion_texts=[*exclusions, *old_corpus])
    safety, safety_proof = prepare_robustness(prior_safety_envelope=prior["prior_safety"],
        code_revision=code_revision, tokenizers=tokenizers, models=models)
    envelopes["safety_robustness"] = safety
    manifest["experiments"]["safety_robustness"] = safety_proof
    if set(envelopes) != set(DIAGNOSTIC_COUNTS):
        raise ValueError("all three diagnostic experiments required")
    for name, envelope in envelopes.items():
        rows = validate_requests(envelope["requests"], envelope["protocol"])
        if len(rows) != DIAGNOSTIC_COUNTS[name]:
            raise ValueError("diagnostic count differs from predeclared matrix")
        manifest["experiments"][name].update(file=name + ".json", request_count=len(rows),
            requests_sha256=hashlib.sha256(b"".join(canonical(r) for r in rows)).hexdigest(),
            envelope_sha256=hashlib.sha256(canonical(envelope)).hexdigest())
    manifest.update(code_revision=code_revision, phase="FINAL_FROZEN", source=identity,
        total_requests_per_model=sum(DIAGNOSTIC_COUNTS.values()),
        total_planned_model_calls=2 * sum(DIAGNOSTIC_COUNTS.values()),
        raw_source_and_individual_answers_remain_private=True)
    validate_public_json(manifest)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
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
