"""Freeze a reused-sample lexical/BM25 x pack comparison with strict JSON.

No search tuning, sample filtering, model generation, or data downloads occur.
Each pack sees only the question and that ranker's frozen source windows.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

from ktrf import ContextPolicy, compile_snapshot, load_glossary, prepare_llm_context
from .hf_qa import LIMITATIONS, canonical
from .prepare_followup import (MAX_MODEL_LEN, RESERVED_OUTPUT_TOKENS, SOURCE_TOKEN_CAP,
                               SourceBudget, _ordered_rows, load_tokenizers, prompt_proof)
from .run_followup_llm import PROTOCOL_ID, load_request_file, validate_requests
from .run_hf_benchmark import digest

ROOT = Path(__file__).resolve().parents[1]


def build_combined(parent_rows, snapshot, *, expected_questions=128):
    """Rebuild packs for both source selections; keep all questions and offsets."""
    validate_requests(parent_rows, "retrieval")
    selected = [row for row in parent_rows if row["context_condition"] in {"lexical", "bm25"}]
    question_count = len({row["case_id"] for row in selected})
    if expected_questions is not None and question_count != expected_questions:
        raise ValueError("parent question count differs from declared reused sample")
    result = []
    for parent in selected:
        ranker = parent["context_condition"]
        source = "\n\n".join(parent["source_text"][start:end] for start, end in parent["source_spans"])
        prepared = prepare_llm_context(snapshot, parent["question"] + "\n" + source,
            query=parent["question"], mode="commit",
            context_policy=ContextPolicy(profile="qa_grounding", max_tokens=800))
        for with_pack in (False, True):
            injected = bool(with_pack and prepared.should_inject)
            context = ranker + ("_pack" if with_pack else "")
            for repeat in range(3):
                row = deepcopy(parent)
                row.update(case_id=parent["case_id"] + "::combined", experiment="combined",
                    context_condition=context, decoding_mode="json_schema", repeat_id=repeat,
                    condition=f"{context}__json_schema__r{repeat}",
                    reused_original_question=True, independent_validation=False,
                    pack_injected=injected,
                    pack_sha256=digest(prepared.context_pack) if with_pack else None,
                    pack_prompt=prepared.prompt_fragment if injected else None,
                    pack_policy=prepared.policy_fragment if injected else None)
                if injected:
                    row["system"] += "\n\n" + prepared.policy_fragment
                    row["user"] += "\n\n<terminology>\n" + prepared.prompt_fragment + "\n</terminology>"
                result.append(row)
    rows = _ordered_rows(result, "combined")
    return validate_requests(rows, "combined")


def prepare(parent_requests, parent_manifest, models, out_dir, *, code_revision,
            parent_envelope_sha256, glossary_file=None, tokenizers=None):
    """Bind the previous request seal, actual tokenizers and fixed glossary."""
    parent_requests, parent_manifest = map(Path, (parent_requests, parent_manifest))
    parent_bytes = parent_requests.read_bytes()
    if hashlib.sha256(parent_bytes).hexdigest() != parent_envelope_sha256:
        raise ValueError("parent envelope differs from pinned prior queue")
    parent_rows, protocol, provenance = load_request_file(parent_requests)
    prior = json.loads(parent_manifest.read_text())
    if protocol["experiment"] != "retrieval":
        raise ValueError("parent must be the frozen retrieval experiment")
    parent_corpus_sha = hashlib.sha256(b"".join(canonical(row) for row in parent_rows)).hexdigest()
    preparation = prior.get("experiments", {}).get("retrieval", {})
    if (prior.get("phase") != "FINAL_FROZEN" or any(preparation.get(key) != value for key, value in {
            "request_count": len(parent_rows), "requests_sha256": parent_corpus_sha,
            "envelope_sha256": parent_envelope_sha256}.items())):
        raise ValueError("parent preparation does not bind the frozen retrieval requests")
    if set(models) != {"gemma12b", "qwen27b"} or not code_revision:
        raise ValueError("two frozen model declarations and code revision required")
    glossary_file = Path(glossary_file or ROOT / "examples/realorg_glossary.yaml")
    snapshot = compile_snapshot(load_glossary(str(glossary_file)))
    rows = build_combined(parent_rows, snapshot)
    tokenizers = tokenizers or load_tokenizers(models)
    if set(tokenizers) != set(models):
        raise ValueError("actual tokenizers must match declared models")
    proofs = prompt_proof(rows, tokenizers, models, "combined", SourceBudget(tokenizers))
    first_repeat = [row for row in rows if row["repeat_id"] == 0]
    base = [row for row in first_repeat if row["context_condition"] == "lexical"]
    strata = dict(Counter(row["stratum"] for row in base))
    if strata != {"SPAN": 40, "YES_NO": 8, "NO_ANSWER": 80}:
        raise ValueError("reused sample must preserve all original 48 positive / 80 no-answer questions")
    injected = {ranker: sum(row["pack_injected"] for row in first_repeat
                          if row["context_condition"] == ranker + "_pack")
                for ranker in ("lexical", "bm25")}
    limitations = [*LIMITATIONS,
        "This is an adaptive followup on previously inspected retrieval questions, not independent validation.",
        "All 128 prior questions and exact lexical/BM25 source offsets are retained without output-based filtering.",
        "All four conditions use strict JSON schema; this run does not isolate the decoding effect.",
        "Three repetitions measure stability and do not increase the independent sample size.",
        "Pack and no-pack retain identical ranker source windows; actual prompt lengths differ.",
        "Packs are recomputed from each ranker's question and selected source only; gold and oracle are never pack inputs.",
        "Search selects passages inside the known article, not documents from a corpus.",
        "The common source-token cap is not equal actual token consumption or total prompt cost."]
    frozen_protocol = {"kind": PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": "combined",
        "conditions": sorted({row["condition"] for row in rows}), "repeat_count": 3,
        "max_model_len": MAX_MODEL_LEN, "reserved_output_tokens": RESERVED_OUTPUT_TOKENS,
        "source_only_token_cap_per_model": SOURCE_TOKEN_CAP,
        "temperature": 0, "seed_for_generation": 0, "enable_thinking": False,
        "selection_before_combined_generation_outputs": True, "independent_validation": False,
        "previous_results_informed_choice_of_methods": True, "limitations": limitations}
    identity = {"code_revision": code_revision, "source": provenance["source"],
        "parent_code_revision": provenance["code_revision"],
        "parent_envelope_sha256": parent_envelope_sha256,
        "parent_requests_sha256": parent_corpus_sha,
        "parent_preparation_sha256": hashlib.sha256(parent_manifest.read_bytes()).hexdigest(),
        "glossary_sha256": hashlib.sha256(glossary_file.read_bytes()).hexdigest(),
        "snapshot_id": snapshot.snapshot_id, "reused_questions": len(base)}
    envelope = {"protocol": frozen_protocol, "provenance": identity, "requests": rows}
    experiment = {"file": "combined.json", "request_count": len(rows), "question_count": len(base),
        "parent_articles": len({row["parent_document_id"] for row in base}), "strata": strata,
        "envelope_sha256": hashlib.sha256(canonical(envelope)).hexdigest(),
        "requests_sha256": hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
        "pack_injected_questions_by_ranker": injected, "models": proofs}
    manifest = {"schema_version": 1, "protocol": PROTOCOL_ID, "phase": "FINAL_FROZEN",
        **identity, "experiments": {"combined": experiment},
        "total_requests_per_model": len(rows), "total_planned_model_calls": len(models) * len(rows),
        "raw_source_and_individual_answers_remain_private": True}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    (out_dir / "combined.json").write_bytes(canonical(envelope))
    (out_dir / "manifest.json").write_bytes(canonical(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-requests", type=Path, required=True)
    parser.add_argument("--parent-manifest", type=Path, required=True)
    parser.add_argument("--parent-envelope-sha256", required=True)
    parser.add_argument("--models-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    result = prepare(args.parent_requests, args.parent_manifest, json.loads(args.models_file.read_text()),
        args.out_dir, code_revision=args.code_revision, parent_envelope_sha256=args.parent_envelope_sha256)
    print(json.dumps({"phase": result["phase"], "total_planned_model_calls": result["total_planned_model_calls"],
        "experiment": result["experiments"]["combined"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
