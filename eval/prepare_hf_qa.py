"""Prepare a private HF QA pool, screen both templates, then freeze final requests."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path

from ktrf import compile_snapshot, load_glossary
from .hf_sources import acquire_sources, load_tydi_records
from .hf_qa import (CONDITIONS, LIMITATIONS, PROTOCOL_ID, QUOTAS, SEED,
                    build_question_requests, build_screening_pool, canonical, validate_requests)
from .run_hf_benchmark import digest, known_prior_documents, select_records

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    Path(path).write_bytes(canonical(value))


def freeze_pool(out_dir, *, code_revision, cache_dir=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    manifest = acquire_sources(cache_dir or ROOT / "eval/data/hf_external_v1")
    source = manifest["sources"]["tydiqa_ko"]
    records, exclusions = load_tydi_records(Path(source["path"]), invalid_minimal="record")
    hashes, parents, prior = known_prior_documents([
        ROOT / "eval/data/wild_documents.jsonl", ROOT / "eval/data/wild_corpus.jsonl",
        ROOT / "eval/fixtures/production_real_holdout/documents.jsonl",
        ROOT / "eval/data/blind_review_20261013/konec/documents.jsonl",
        ROOT / "eval/data/blind_review_20261013/koneobench/documents.jsonl"])
    fresh = [row for row in records if row["document_sha256"] not in hashes
             and row["parent_document_id"] not in parents and row["document_url"] not in parents]
    selected, inventory = build_screening_pool(fresh)
    glossary_file = ROOT / "examples/realorg_glossary.yaml"
    snapshot = compile_snapshot(load_glossary(str(glossary_file)))
    requests = [row for record in selected for row in build_question_requests(record, snapshot)]
    validate_requests(requests)
    inventory.update(prior_overlap_exclusions=len(records) - len(fresh), prior_overlap_audit=prior,
                     invalid_minimal_questions=sum(not r["minimal_answer_evaluable"] for r in records),
                     non_korean_rows=len(exclusions), snapshot_id=snapshot.snapshot_id,
                     glossary_sha256=hashlib.sha256(glossary_file.read_bytes()).hexdigest())
    protocol = {"kind": PROTOCOL_ID, "phase": "SCREENING_POOL", "conditions": list(CONDITIONS),
        "seed": SEED, "quotas": QUOTAS, "max_model_len": 8192, "reserved_output_tokens": 128,
        "generation_metric": "NFC_casefold_whitespace_collapsed_EM_and_diagnostic_character_F1",
        "source_positive_rule": "at_least_two_valid_SPAN_or_YES_NO_annotations_without_mixed_types",
        "source_negative_rule": "three_unanimous_NO_ANSWER_annotations",
        "limitations": LIMITATIONS}
    envelope = {"protocol": protocol, "provenance": {"code_revision": code_revision,
        "source_revision": source["revision"], "source_file_sha256": source["sha256"],
        "source_dataset": source["dataset"], "source_file": source["file"],
        "inventory": inventory, "preparation_scope": "before_any_generation_outputs"},
        "requests": requests,
        "prior_evidence_question_ids": [row["document_id"] for row in select_records(fresh, 256)]}
    write_json(out_dir / "pool.json", envelope)
    write_json(out_dir / "inventory.json", inventory)
    return {"pool": str(out_dir / "pool.json"), "pool_sha256": hashlib.sha256(canonical(envelope)).hexdigest(),
            "candidate_questions": len(selected), "request_count": len(requests), "inventory": inventory}


def screen_and_freeze(pool_file, models, out_dir, *, code_revision):
    from transformers import AutoTokenizer
    pool_file, out_dir = Path(pool_file), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    pool = json.loads(pool_file.read_text())
    if pool["protocol"]["kind"] != PROTOCOL_ID or pool["protocol"]["phase"] != "SCREENING_POOL":
        raise ValueError("expected a sealed screening pool")
    rows = validate_requests(pool["requests"])
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["case_id"]].append(row)
    lengths = {}
    for model_key, model in models.items():
        tokenizer = AutoTokenizer.from_pretrained(model["path"], local_files_only=True)
        values = []
        for row in rows:
            tokens = tokenizer.apply_chat_template(
                [{"role": "system", "content": row["system"]}, {"role": "user", "content": row["user"]}],
                tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False)
            if not isinstance(tokens, list) or not tokens or any(type(token) is not int for token in tokens):
                raise ValueError("actual template must yield flat token IDs")
            values.append(len(tokens))
        lengths[model_key] = values
    by_key = {(row["case_id"], row["condition"]): index for index, row in enumerate(rows)}
    eligible = {}
    rejected = []
    for case_id, case in grouped.items():
        overflow = {model: [row["condition"] for row in case
                           if values[by_key[(case_id, row["condition"])]] + 128 > 8192]
                    for model, values in lengths.items()}
        if any(overflow.values()):
            rejected.append({"case_id": case_id, "stratum": case[0]["stratum"],
                             "reason": "context_capacity", "overflow_by_model": overflow})
        else:
            eligible[case_id] = case
    chosen, used_parents = [], set()
    for kind in ("YES_NO", "SPAN", "NO_ANSWER"):
        candidates = sorted((key for key, case in eligible.items() if case[0]["stratum"] == kind),
                            key=lambda key: digest([SEED, key]))
        for key in candidates:
            parent = eligible[key][0]["parent_document_id"]
            if parent not in used_parents:
                chosen.append(key)
                used_parents.add(parent)
                if sum(eligible[item][0]["stratum"] == kind for item in chosen) == QUOTAS[kind]:
                    break
    counts = Counter(eligible[key][0]["stratum"] for key in chosen)
    screening = {"code_revision": code_revision, "pool_sha256": hashlib.sha256(pool_file.read_bytes()).hexdigest(),
        "candidate_questions": len(grouped), "common_fit_questions": len(eligible),
        "candidate_by_stratum": dict(Counter(case[0]["stratum"] for case in grouped.values())),
        "common_fit_by_stratum": dict(Counter(case[0]["stratum"] for case in eligible.values())),
        "selected_by_stratum": dict(counts), "rejected_questions": rejected,
        "one_question_per_parent_article": True,
        "models": {key: {"path": models[key]["path"], "max_pool_prompt_tokens": max(values),
                         "overflow_requests": sum(n + 128 > 8192 for n in values)}
                   for key, values in lengths.items()}}
    write_json(out_dir / "screening.json", screening)
    if any(counts[kind] != quota for kind, quota in QUOTAS.items()):
        raise ValueError("INSUFFICIENT_DATA: not enough common-fit distinct parent articles for declared quotas")
    final = []
    for index, key in enumerate(sorted(chosen, key=lambda key: digest([SEED, key]))):
        case = {row["condition"]: row for row in eligible[key]}
        order = CONDITIONS[index % len(CONDITIONS):] + CONDITIONS[:index % len(CONDITIONS)]
        final.extend(case[condition] for condition in order)
    protocol = {**pool["protocol"], "phase": "FINAL_FROZEN", "selection": {
        "question_count": len(chosen), "parent_articles": len(used_parents),
        "question_ids_sha256": digest(sorted(chosen)), "common_fit_selection": True,
        "strata": dict(counts), "screening_sha256": hashlib.sha256(canonical(screening)).hexdigest(),
        "overlap_with_prior_evidence_questions": len(
            {eligible[key][0]["document_id"] for key in chosen} & set(pool.get("prior_evidence_question_ids", [])))},
        "sampling_limit": "A predeclared hash-ordered three-times-quota screening pool, not all Korean articles."}
    envelope = {"protocol": protocol, "provenance": {**pool["provenance"], "code_revision": code_revision,
        "pool_file_sha256": hashlib.sha256(pool_file.read_bytes()).hexdigest(),
        "screening_sha256": hashlib.sha256(canonical(screening)).hexdigest(),
        "capacity_screening": {key: value for key, value in screening.items() if key != "rejected_questions"}
            | {"rejected_question_count": len(rejected)}}, "requests": final}
    write_json(out_dir / "questions.json", envelope)
    summary = {"code_revision": code_revision, "file": "questions.json",
        "envelope_sha256": hashlib.sha256(canonical(envelope)).hexdigest(),
        "requests_sha256": hashlib.sha256(b"".join(canonical(row) for row in final)).hexdigest(),
        "request_count": len(final), "question_count": len(chosen), "parent_articles": len(used_parents)}
    write_json(out_dir / "manifest.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--code-revision")
    parser.add_argument("--pool-file", type=Path)
    parser.add_argument("--models-file", type=Path)
    parser.add_argument("--check-tokens-plan", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.check_tokens_plan:
        from .prepare_document_context import check_tokens
        result = check_tokens(json.loads(args.check_tokens_plan.read_text()))
        print(json.dumps({"exit_code": result["exit_code"], "models": {
            key: {field: value[field] for field in ("request_count", "max_prompt_tokens", "overflow_count")}
            for key, value in result["models"].items()}}))
        return result["exit_code"]
    if not args.out_dir or not args.code_revision:
        parser.error("--out-dir and --code-revision required")
    if args.pool_file:
        if not args.models_file:
            parser.error("--models-file required for template screening")
        result = screen_and_freeze(args.pool_file, json.loads(args.models_file.read_text()),
                                   args.out_dir, code_revision=args.code_revision)
    else:
        result = freeze_pool(args.out_dir, code_revision=args.code_revision)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
