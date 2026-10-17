"""Freeze private independent retrieval and matched-prompt stability requests.

Run with the two installed model tokenizers. This command performs no model
generation and never downloads models or source data. Only ``manifest.json``
and ``retrieval_diagnostics.json`` are aggregate publication candidates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

from .hf_qa import (LIMITATIONS, canonical, classify_gold,
                    validate_requests as validate_old_requests)
from .hf_retrieval_followup import (DEFAULT_CHAR_BUDGET, DEFAULT_TOP_K, METHODS,
    SEED, build_variants, choose_heldout, evaluate_retrieval)
from .hf_sources import SOURCE_SPECS, load_tydi_records
from .run_followup_llm import PROTOCOL_ID, validate_requests
from .run_hf_benchmark import digest


SOURCE_TOKEN_CAP = 1536
MAX_MODEL_LEN = 8192
RESERVED_OUTPUT_TOKENS = 128


def _sha_file(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _token_ids(value):
    if not isinstance(value, list) or any(type(token) is not int for token in value):
        raise ValueError("actual tokenizer must return flat integer token IDs")
    return value


def load_tokenizers(models):
    from transformers import AutoTokenizer
    return {key: AutoTokenizer.from_pretrained(model["path"], local_files_only=True)
            for key, model in models.items()}


class SourceBudget:
    """Cache actual source-only lengths for common two-model feasibility."""

    def __init__(self, tokenizers, cap=SOURCE_TOKEN_CAP):
        if not tokenizers or type(cap) is not int or cap < 1:
            raise ValueError("actual tokenizers and a positive source cap required")
        self.tokenizers, self.cap = tokenizers, cap
        self.cache = {}

    def lengths(self, record, spans):
        key = (record["document_sha256"], tuple(tuple(span) for span in spans))
        if key not in self.cache:
            source = "\n\n".join(record["text"][start:end] for start, end in spans)
            self.cache[key] = {model: len(_token_ids(tokenizer.encode(source, add_special_tokens=False)))
                               for model, tokenizer in self.tokenizers.items()}
        return self.cache[key]

    def factory(self, record):
        return lambda spans: all(n <= self.cap for n in self.lengths(record, spans).values())


def _prior_exclusions(records, old, pool, blind_rows):
    by_id = {row["document_id"]: row for row in records}
    if len(by_id) != len(records):
        raise ValueError("duplicate source question IDs")
    old_rows = validate_old_requests(old["requests"])
    pool_rows = validate_old_requests(pool["requests"])
    if (old.get("protocol", {}).get("phase") != "FINAL_FROZEN"
            or pool.get("protocol", {}).get("phase") != "SCREENING_POOL"):
        raise ValueError("expected final old requests and original screening pool")
    prior_ids = set(pool.get("prior_evidence_question_ids", []))
    if not prior_ids:
        raise ValueError("original 256-question evidence exclusions are required")
    old_ids = {row["document_id"] for row in old_rows}
    pool_ids = {row["document_id"] for row in pool_rows}
    if (old_ids | pool_ids | prior_ids) - set(by_id):
        raise ValueError("prior question IDs are absent from pinned source")
    parents, hashes = set(), set()
    for row in old_rows + pool_rows:
        source = by_id[row["document_id"]]
        if any(row[key] != source[replacement] for key, replacement in (
                ("document_sha256", "document_sha256"), ("parent_document_id", "parent_document_id"),
                ("source_text", "text"), ("question", "question"))):
            raise ValueError("old prompt source differs from pinned article")
        gold = classify_gold(source)
        if any(row[key] != gold[replacement] for key, replacement in (
                ("stratum", "stratum"), ("positive_gold", "positive"),
                ("expected_answers", "expected_answers"))):
            raise ValueError("old prompt gold differs from pinned annotations")
        parents.add(source["parent_document_id"])
        hashes.add(source["document_sha256"])
    for identifier in prior_ids:
        parents.add(by_id[identifier]["parent_document_id"])
        hashes.add(by_id[identifier]["document_sha256"])
    if not blind_rows:
        raise ValueError("blind document exclusions cannot be empty")
    for row in blind_rows:
        if not row.get("parent_document_id"):
            raise ValueError("blind document parent identity required")
        parents.add(row["parent_document_id"])
        for key in ("document_sha256", "source_document_sha256"):
            if row.get(key):
                hashes.add(row[key])
        if isinstance(row.get("text"), str):
            hashes.add(hashlib.sha256(row["text"].encode()).hexdigest())
        identifier = row.get("source_document_id")
        if identifier:
            if identifier not in by_id:
                raise ValueError("blind source question ID absent from pinned source")
            source = by_id[identifier]
            if source["parent_document_id"] != row["parent_document_id"]:
                raise ValueError("blind parent identity differs from source")
            parents.add(source["parent_document_id"])
            hashes.add(source["document_sha256"])
    return parents, hashes, old_ids, {
        "old_generation_questions": len(old_ids), "old_screening_pool_questions": len(pool_ids),
        "prior_evidence_questions": len(prior_ids), "blind_document_rows": len(blind_rows),
        "excluded_parent_articles": len(parents), "excluded_content_hashes": len(hashes),
        "all_old_screening_pool_articles_excluded": True,
        "all_prior_evidence_articles_excluded": True, "blind_parents_excluded": True,
        "near_duplicate_check_performed": False}


def build_stability(old_rows):
    """Keep source and exact original prompts; change only execution labels."""
    validate_old_requests(old_rows)
    selected = [row for row in old_rows if row["condition"] in {"retrieved", "ktrf_pack"}]
    rows = []
    for old in selected:
        context = old["condition"]
        for decoding in ("free", "json_schema"):
            for repeat in range(3):
                row = deepcopy(old)
                row.update(case_id=old["document_id"] + "::stability", experiment="stability",
                    context_condition=context, decoding_mode=decoding, repeat_id=repeat,
                    condition=f"{context}__{decoding}__r{repeat}",
                    original_prompt_sha256=digest([old["system"], old["user"]]),
                    reused_original_question=True, independent_validation=False)
                rows.append(row)
    return _ordered_rows(rows, "stability")


def _ordered_rows(rows, experiment):
    cases = defaultdict(list)
    for row in rows:
        cases[row["case_id"]].append(row)
    result = []
    for index, case_id in enumerate(sorted(cases, key=lambda key: (digest([SEED, experiment, key]), key))):
        case = sorted(cases[case_id], key=lambda row: row["condition"])
        rotation = index % len(case)
        result.extend(case[rotation:] + case[:rotation])
    return result


def prompt_proof(rows, tokenizers, models, experiment, budget):
    """Actual model chat-template lengths; same prompts in free/schema modes."""
    validate_requests(rows, experiment)
    proofs = {}
    for model_key, tokenizer in tokenizers.items():
        cache, lengths, source_lengths = {}, [], []
        for row in rows:
            key = (row["system"], row["user"])
            if key not in cache:
                ids = tokenizer.apply_chat_template(
                    [{"role": "system", "content": row["system"]},
                     {"role": "user", "content": row["user"]}],
                    tokenize=True, add_generation_prompt=True,
                    enable_thinking=False, return_dict=False)
                cache[key] = len(_token_ids(ids))
            lengths.append(cache[key])
            if experiment == "retrieval":
                source = {"text": row["source_text"], "document_sha256": row["document_sha256"]}
                source_lengths.append(budget.lengths(source, row["source_spans"])[model_key])
        overflow = sum(length + RESERVED_OUTPUT_TOKENS > MAX_MODEL_LEN for length in lengths)
        if overflow or any(length > SOURCE_TOKEN_CAP for length in source_lengths):
            raise ValueError("frozen request exceeds common actual-token capacity")
        proofs[model_key] = {"path": models[model_key]["path"], "request_count": len(rows),
            "max_prompt_tokens": max(lengths), "overflow_count": overflow,
            "max_source_tokens": max(source_lengths) if source_lengths else None,
            "source_token_cap": SOURCE_TOKEN_CAP if experiment == "retrieval" else None,
            "tokenizer_local_files_only": True, "apply_chat_template": True,
            "enable_thinking": False, "reserved_output_tokens": RESERVED_OUTPUT_TOKENS}
    return proofs


def prepare_from_records(records, old, pool, blind_rows, *, tokenizers, models,
                         code_revision, source_identity, input_hashes,
                         retrieval_quotas=None, expected_old_questions=128):
    """Core preparation, with injectable actual-tokenizer interfaces for tests."""
    if not code_revision or set(tokenizers) != set(models) or not tokenizers:
        raise ValueError("code revision and matching model tokenizers required")
    parents, hashes, old_ids, exclusions = _prior_exclusions(records, old, pool, blind_rows)
    if expected_old_questions is not None and len(old_ids) != expected_old_questions:
        raise ValueError("old frozen question count differs from declared stability sample")
    by_id = {row["document_id"]: row for row in records}
    development = [by_id[identifier] for identifier in sorted(old_ids)]
    budget = SourceBudget(tokenizers)
    variants_cache = {}

    def variants(record):
        identifier = record["document_id"]
        if identifier not in variants_cache:
            variants_cache[identifier] = build_variants(record, budget_fits=budget.factory(record))
        return variants_cache[identifier]

    def eligible(record):
        # Gold availability only determines a predeclared diagnostic capacity
        # stratum. It is checked before any held-out generation or threshold use.
        return not classify_gold(record)["positive"] or variants(record)[-1]["oracle_budget_fit"] is True

    heldout, inventory = choose_heldout(records, excluded_parents=parents, excluded_hashes=hashes,
                                       quotas=retrieval_quotas, eligible=eligible)
    retrieval = _ordered_rows([row for record in heldout for row in variants(record)], "retrieval")
    stability = build_stability(old["requests"])
    diagnostics = {"protocol": PROTOCOL_ID, "phase": "BEFORE_GENERATION",
        "development": evaluate_retrieval(development, budget_fits_factory=budget.factory),
        "heldout": evaluate_retrieval(heldout, budget_fits_factory=budget.factory),
        "development_is_reused_old_generation_sample": True,
        "development_winner_is_descriptive_all_three_rankers_remain_in_heldout": True,
        "heldout_selection": inventory, "prior_exclusions": exclusions,
        "oracle_positive_requires_complete_original_annotated_passage": True,
        "source_only_token_cap_per_model": SOURCE_TOKEN_CAP,
        "no_generation_outputs_used": True, "raw_text_or_individual_answers_published": False}
    envelopes, experiment_manifests = {}, {}
    for name, rows in (("retrieval", retrieval), ("stability", stability)):
        validate_requests(rows, name)
        proofs = prompt_proof(rows, tokenizers, models, name, budget)
        limitations = [*LIMITATIONS,
            "Oracle supplies gold-annotated source passages and is diagnostic only, never deployable.",
            "Retrieval sampling excludes all declared prior article parents and content hashes; near duplicates are not detected.",
            "Retrieval sample is conditional on a complete original oracle passage fitting both tokenizers and the character budget.",
            "Stability reuses the original questions and exact prompts; repeats are not independent validation samples.",
            "Retrieval has a common source-token cap; stability intentionally preserves the older source lengths unchanged.",
            "Deterministic decoding can still vary with inference scheduling and hardware; repeats diagnose this variation."]
        protocol = {"kind": PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": name,
            "seed": SEED, "conditions": sorted({row["condition"] for row in rows}),
            "max_model_len": MAX_MODEL_LEN, "reserved_output_tokens": RESERVED_OUTPUT_TOKENS,
            "temperature": 0, "seed_for_generation": 0, "enable_thinking": False,
            "source_only_token_cap_per_model": SOURCE_TOKEN_CAP if name == "retrieval" else None,
            "source_character_cap": DEFAULT_CHAR_BUDGET, "source_passage_cap": DEFAULT_TOP_K,
            "selection_before_generation_outputs": True, "limitations": limitations,
            "independent_from_prior_declared_articles": name == "retrieval"}
        provenance = {"code_revision": code_revision, "source": source_identity,
            "exclusion_input_sha256": input_hashes, "prior_exclusions": exclusions,
            "selection": inventory if name == "retrieval" else {
                "reused_original_questions": len(old_ids), "independent_validation": False,
                "original_prompts_preserved_exactly": True}}
        envelope = {"protocol": protocol, "provenance": provenance, "requests": rows}
        envelopes[name] = envelope
        experiment_manifests[name] = {"file": name + ".json", "request_count": len(rows),
            "question_count": len({row["case_id"] for row in rows}),
            "parent_articles": len({row["parent_document_id"] for row in rows}),
            "strata": dict(Counter(row["stratum"] for row in rows[::len(protocol["conditions"])])),
            "envelope_sha256": hashlib.sha256(canonical(envelope)).hexdigest(),
            "requests_sha256": hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
            "models": proofs}
    manifest = {"schema_version": 1, "protocol": PROTOCOL_ID, "phase": "FINAL_FROZEN",
        "code_revision": code_revision, "source": source_identity,
        "exclusion_input_sha256": input_hashes, "prior_exclusions": exclusions,
        "retrieval_selection": inventory, "experiments": experiment_manifests,
        "retrieval_diagnostics_sha256": hashlib.sha256(canonical(diagnostics)).hexdigest(),
        "source_token_cap_per_model_retrieval_only": SOURCE_TOKEN_CAP,
        "max_model_len": MAX_MODEL_LEN, "reserved_output_tokens": RESERVED_OUTPUT_TOKENS,
        "total_requests_per_model": sum(value["request_count"] for value in experiment_manifests.values()),
        "total_planned_model_calls": len(models) * sum(value["request_count"] for value in experiment_manifests.values()),
        "raw_source_and_individual_answers_remain_private": True}
    return envelopes, diagnostics, manifest


def prepare(source_file, old_requests, prior_pool, blind_documents, models, out_dir, *, code_revision,
            tokenizers=None):
    source_file, old_requests, prior_pool, blind_documents = map(Path,
        (source_file, old_requests, prior_pool, blind_documents))
    source_sha = _sha_file(source_file)
    spec = SOURCE_SPECS["tydiqa_ko"]
    if source_sha != spec["expected_sha256"]:
        raise ValueError("cached TyDiQA source differs from pinned source SHA256")
    records, exclusions = load_tydi_records(source_file, invalid_minimal="record")
    old, pool = (json.loads(path.read_text()) for path in (old_requests, prior_pool))
    blind_rows = [json.loads(line) for line in blind_documents.read_text().splitlines() if line.strip()]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    source_identity = {"dataset": spec["dataset"], "revision": spec["revision"],
        "file": spec["file"], "sha256": source_sha, "korean_questions": len(records),
        "non_korean_source_rows": len(exclusions),
        "invalid_minimal_questions": sum(not row["minimal_answer_evaluable"] for row in records)}
    inputs = {name: _sha_file(path) for name, path in (
        ("old_requests", old_requests), ("prior_pool", prior_pool), ("blind_documents", blind_documents))}
    try:
        envelopes, diagnostics, manifest = prepare_from_records(records, old, pool, blind_rows,
            tokenizers=tokenizers or load_tokenizers(models), models=models,
            code_revision=code_revision, source_identity=source_identity, input_hashes=inputs)
    except ValueError as error:
        if hasattr(error, "inventory"):
            (out_dir / "selection_failure.json").write_bytes(canonical(error.inventory))
        raise
    for experiment, envelope in envelopes.items():
        (out_dir / (experiment + ".json")).write_bytes(canonical(envelope))
    (out_dir / "retrieval_diagnostics.json").write_bytes(canonical(diagnostics))
    # The manifest is written last: its presence seals all request envelopes.
    (out_dir / "manifest.json").write_bytes(canonical(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--old-requests", type=Path, required=True)
    parser.add_argument("--prior-pool", type=Path, required=True)
    parser.add_argument("--blind-documents", type=Path, required=True)
    parser.add_argument("--models-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    result = prepare(args.source_file, args.old_requests, args.prior_pool, args.blind_documents,
        json.loads(args.models_file.read_text()), args.out_dir, code_revision=args.code_revision)
    print(json.dumps({"phase": result["phase"], "total_planned_model_calls": result["total_planned_model_calls"],
        "experiments": {key: {field: value[field] for field in ("question_count", "request_count")}
                        for key, value in result["experiments"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
