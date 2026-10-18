"""Freeze a small article-disjoint check of the already selected QA methods.

The source, every earlier screening/exposure input, and the glossary are pinned.
No generation outputs, pack eligibility, or retrieval success select questions.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

from ktrf import compile_snapshot, load_glossary
from .hf_qa import LIMITATIONS, canonical, classify_gold
from .hf_retrieval_followup import build_variants, choose_heldout
from .hf_sources import SOURCE_SPECS, load_tydi_records
from .prepare_combined_followup import build_combined
from .prepare_followup import (MAX_MODEL_LEN, RESERVED_OUTPUT_TOKENS, SOURCE_TOKEN_CAP,
    SourceBudget, _prior_exclusions, _sha_file, load_tokenizers, prompt_proof)
from .run_followup_llm import PROTOCOL_ID, load_request_file, validate_requests

QUOTAS = {"SPAN": 6, "YES_NO": 12, "NO_ANSWER": 18}
INPUT_NAMES = {"source_file", "old_requests", "prior_pool", "blind_documents",
               "prior_retrieval", "prior_combined", "glossary"}


def prepare_from_records(records, old, pool, blind_rows, prior_retrieval, prior_combined,
                         *, snapshot, tokenizers, models, code_revision, source_identity,
                         input_hashes, quotas=None):
    if not code_revision or set(models) != {"gemma12b", "qwen27b"} or set(tokenizers) != set(models):
        raise ValueError("frozen revision and both actual model tokenizers required")
    parents, hashes, _, exclusions = _prior_exclusions(records, old, pool, blind_rows)
    by_id = {row["document_id"]: row for row in records}
    exposed_ids = []
    for experiment, rows in (("retrieval", prior_retrieval), ("combined", prior_combined)):
        validate_requests(rows, experiment)
        identifiers = set()
        for row in rows:
            identifier = row.get("document_id")
            if identifier not in by_id:
                raise ValueError("prior followup question absent from pinned source")
            source = by_id[identifier]
            gold = classify_gold(source)
            if (any(row[key] != source[field] for key, field in (
                    ("parent_document_id", "parent_document_id"), ("document_sha256", "document_sha256"),
                    ("source_text", "text"), ("question", "question")))
                    or any(row[key] != gold[field] for key, field in (
                        ("stratum", "stratum"), ("positive_gold", "positive"),
                        ("expected_answers", "expected_answers")))):
                raise ValueError("prior followup source or gold differs from pinned records")
            identifiers.add(identifier)
            parents.add(source["parent_document_id"])
            hashes.add(source["document_sha256"])
        exposed_ids.append(identifiers)
    if exposed_ids[0] != exposed_ids[1]:
        raise ValueError("prior combined must preserve the complete retrieval sample")
    exclusions.update(prior_retrieval_questions=len(exposed_ids[0]),
        prior_combined_questions=len(exposed_ids[1]), excluded_parent_articles=len(parents),
        excluded_content_hashes=len(hashes), all_prior_followup_articles_excluded=True)
    quotas = dict(QUOTAS if quotas is None else quotas)
    if not (set(quotas) == set(QUOTAS) and all(type(n) is int and n >= 0 for n in quotas.values())
            and 0 < quotas["SPAN"] + quotas["YES_NO"] and quotas["NO_ANSWER"] > 0
            and sum(quotas.values()) <= 128):
        raise ValueError("bounded positive and negative predeclared strata required")
    # Select before constructing any source windows or terminology packs. There
    # is deliberately no oracle-fit or retrieved-gold-visibility eligibility.
    selected, inventory = choose_heldout(records, excluded_parents=parents,
        excluded_hashes=hashes, quotas=quotas)
    budget = SourceBudget(tokenizers)
    parent_rows = [row for record in selected
                   for row in build_variants(record, budget_fits=budget.factory(record))]
    rows = build_combined(parent_rows, snapshot, expected_questions=len(selected))
    for row in rows:
        row.update(reused_original_question=False, independent_validation=False,
                   independent_from_prior_declared_articles=True)
    validate_requests(rows, "combined")
    proofs = prompt_proof(rows, tokenizers, models, "combined", budget)
    design = {"kind": "fresh_document_holdout", "question_count": len(selected),
        "strata": quotas, "repeat_count": 3, "independent_from_prior_declared_articles": True}
    limitations = [*LIMITATIONS,
        "This small same-corpus holdout excludes every declared earlier article parent and exact content hash.",
        f"This sample contains {quotas['SPAN']} SPAN and {quotas['YES_NO']} YES_NO positive articles; efficacy and operational risk are not established.",
        "Methods were chosen using earlier articles; these selected questions have no earlier generation outputs.",
        "Near-duplicate articles, other corpora, and model pretraining overlap are not ruled out.",
        "Three repetitions do not increase the independent question count.",
        "Sampling uses gold type but neither retrieval success, oracle capacity nor pack injection eligibility.",
        "All four conditions use strict JSON; pack and no-pack share the exact ranker source windows.",
        "Search is within a known article, not corpus-level document retrieval.",
        "Pack and its policy form one intervention; common source caps do not equal actual prompt costs."]
    protocol = {"kind": PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": "combined",
        "sample_design": design, "conditions": sorted({row["condition"] for row in rows}),
        "repeat_count": 3, "max_model_len": MAX_MODEL_LEN,
        "reserved_output_tokens": RESERVED_OUTPUT_TOKENS,
        "source_only_token_cap_per_model": SOURCE_TOKEN_CAP, "temperature": 0,
        "seed_for_generation": 0, "enable_thinking": False,
        "selection_before_generation_outputs": True, "limitations": limitations}
    identity = {"code_revision": code_revision, "source": source_identity,
        "exclusion_input_sha256": input_hashes, "prior_exclusions": exclusions,
        "selection": inventory, "snapshot_id": snapshot.snapshot_id}
    envelope = {"protocol": protocol, "provenance": identity, "requests": rows}
    first = [row for row in rows if row["repeat_id"] == 0]
    counts = Counter(classify_gold(row)["stratum"] for row in selected)
    strata = {kind: counts[kind] for kind in QUOTAS}
    experiment = {"file": "combined.json", "request_count": len(rows),
        "question_count": len(selected), "parent_articles": len({r["parent_document_id"] for r in selected}),
        "strata": strata, "envelope_sha256": hashlib.sha256(canonical(envelope)).hexdigest(),
        "requests_sha256": hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
        "pack_injected_questions_by_ranker": {ranker: sum(row["pack_injected"] for row in first
            if row["context_condition"] == ranker + "_pack") for ranker in ("lexical", "bm25")},
        "models": proofs}
    manifest = {"schema_version": 1, "protocol": PROTOCOL_ID, "phase": "FINAL_FROZEN",
        **identity, "sample_design": design, "experiments": {"combined": experiment},
        "total_requests_per_model": len(rows), "total_planned_model_calls": 2 * len(rows),
        "raw_source_and_individual_answers_remain_private": True}
    return envelope, manifest


def prepare(config, out_dir, *, code_revision):
    inputs = config["inputs"]
    if set(inputs) != INPUT_NAMES:
        raise ValueError("all source, glossary and prior exposure inputs are required")
    paths, hashes = {}, {}
    for name, spec in inputs.items():
        paths[name] = Path(spec["path"])
        hashes[name] = _sha_file(paths[name])
        if hashes[name] != spec["sha256"]:
            raise ValueError("pinned input hash differs: " + name)
    source_spec = SOURCE_SPECS["tydiqa_ko"]
    if hashes["source_file"] != source_spec["expected_sha256"]:
        raise ValueError("source is not the declared TyDiQA revision")
    records, excluded = load_tydi_records(paths["source_file"], invalid_minimal="record")
    old, pool = (json.loads(paths[name].read_text()) for name in ("old_requests", "prior_pool"))
    blind = [json.loads(line) for line in paths["blind_documents"].read_text().splitlines() if line.strip()]
    prior_rows = []
    for name, experiment in (("prior_retrieval", "retrieval"), ("prior_combined", "combined")):
        rows, protocol, _ = load_request_file(paths[name])
        if protocol["experiment"] != experiment:
            raise ValueError("wrong prior exposure experiment")
        prior_rows.append(rows)
    models = config["models"]
    source_identity = {"dataset": source_spec["dataset"], "revision": source_spec["revision"],
        "file": source_spec["file"], "sha256": hashes["source_file"],
        "korean_questions": len(records), "non_korean_source_rows": len(excluded)}
    envelope, manifest = prepare_from_records(records, old, pool, blind, *prior_rows,
        snapshot=compile_snapshot(load_glossary(str(paths["glossary"]))),
        tokenizers=load_tokenizers(models), models=models, code_revision=code_revision,
        source_identity=source_identity, input_hashes=hashes)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    (out_dir / "combined.json").write_bytes(canonical(envelope))
    (out_dir / "manifest.json").write_bytes(canonical(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    manifest = prepare(json.loads(args.config.read_text()), args.out_dir, code_revision=args.code_revision)
    print(json.dumps({"phase": manifest["phase"], "sample_design": manifest["sample_design"],
                      "total_planned_model_calls": manifest["total_planned_model_calls"]}))


if __name__ == "__main__":
    main()
