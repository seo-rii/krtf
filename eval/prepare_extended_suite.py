"""Freeze all five extended experiments before any model generation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from ktrf import compile_snapshot, load_glossary
from .collect_hf_qa_queue import validate_public_json
from .extended_qa import load_mrc_records, prepare_qa
from .extended_safety import prepare_safety
from .hf_qa import canonical
from .hf_sources import SOURCE_SPECS, load_tydi_records
from .prepare_followup import _sha_file, load_tokenizers
from .run_extended_suite import validate_requests
from .run_followup_queue import EXTENDED_COUNTS

REVISION = "349481ec73fff722f88e0453ca05c77a447d967c"
PINNED_HASHES = {
    "source_file": "f576c924f471702a6fa3369d314bea2e47545c56736f371a2adb90ed15913738",
    "klue_ner": "db2129c2ae38fc9a7de630d902cd41f80ac6174f620a8318b4d80569e31b9f84",
    "card": "77857d77d4e711c0eb655355667dc5e150edee8668b2048a0f104f7e6ce7db96",
    "tydi": SOURCE_SPECS["tydiqa_ko"]["expected_sha256"],
}
INPUT_NAMES = {*PINNED_HASHES, "glossary", "blind_konec", "blind_koneobench"}


def load_exclusions(paths):
    """Exclude declared previous corpora, including KLUE's annotated sentences."""
    import pyarrow.parquet as pq

    tydi, _ = load_tydi_records(paths["tydi"], invalid_minimal="record")
    groups = {"tydi_korean": [row["text"] for row in tydi]}
    sentences = []
    for row in pq.read_table(paths["klue_ner"]).to_pylist():
        # The sentence field contains <surface:TYPE> markup; do not compare
        # marked-up strings to plain MRC contexts or silently detokenize them.
        plain = re.sub(r"<([^<>]+):[A-Z]+>", r"\1", row["sentence"])
        if plain != "".join(row["tokens"]):
            raise ValueError("KLUE-NER markup and original character tokens disagree")
        sentences.append(plain)
    groups["klue_ner_validation"] = sentences
    for name in ("blind_konec", "blind_koneobench"):
        rows = [json.loads(line) for line in paths[name].read_text().splitlines() if line.strip()]
        groups[name] = [row["text"] for row in rows]
    if any(not isinstance(text, str) or not text for group in groups.values() for text in group):
        raise ValueError("empty or invalid exclusion document")
    return [text for group in groups.values() for text in group], {
        name: {"documents": len(texts), "unique_content_hashes": len({
            hashlib.sha256(text.encode()).hexdigest() for text in texts})}
        for name, texts in groups.items()}


def prepare(config, out_dir, *, code_revision):
    if not re.fullmatch(r"[a-f0-9]{40}", code_revision):
        raise ValueError("immutable code revision required")
    inputs = config["inputs"]
    if set(inputs) != INPUT_NAMES:
        raise ValueError("pinned source, card, glossary and all exclusion inputs required")
    paths, hashes = {}, {}
    for name, spec in inputs.items():
        paths[name] = Path(spec["path"])
        hashes[name] = _sha_file(paths[name])
        if hashes[name] != spec["sha256"] or name in PINNED_HASHES and hashes[name] != PINNED_HASHES[name]:
            raise ValueError("input differs from pinned identity: " + name)
    models = config["models"]
    if set(models) != {"gemma12b", "qwen27b"}:
        raise ValueError("both fixed model tokenizers required")
    records, inventory = load_mrc_records(paths["source_file"])
    exclusions, exclusion_inventory = load_exclusions(paths)
    source_identity = {"dataset": "klue/klue", "revision": REVISION,
        "file": "mrc/validation-00000-of-00001.parquet", "sha256": hashes["source_file"],
        "card_sha256": hashes["card"], "license": "cc-by-sa-4.0 (HF card declaration)",
        "inventory": inventory, "exclusion_input_sha256": hashes,
        "exclusion_inventory": exclusion_inventory}
    tokenizers = load_tokenizers(models)
    envelopes, manifest = prepare_qa(records,
        compile_snapshot(load_glossary(str(paths["glossary"]))), tokenizers, models,
        code_revision=code_revision, source_identity=source_identity, exclusion_texts=exclusions)
    safety, safety_preparation = prepare_safety(code_revision=code_revision,
                                              tokenizers=tokenizers, models=models)
    envelopes["semantic_safety"] = safety
    manifest["experiments"]["semantic_safety"] = safety_preparation
    if set(envelopes) != set(EXTENDED_COUNTS):
        raise ValueError("all five frozen experiments required")
    for experiment, envelope in envelopes.items():
        rows = envelope["requests"]
        validate_requests(rows, envelope["protocol"])
        if len(rows) != EXTENDED_COUNTS[experiment]:
            raise ValueError("request count differs from predeclared experiment")
        spec = manifest["experiments"][experiment]
        spec.update(file=experiment + ".json", request_count=len(rows),
            requests_sha256=hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
            envelope_sha256=hashlib.sha256(canonical(envelope)).hexdigest())
    manifest.update(code_revision=code_revision, phase="FINAL_FROZEN",
        source=source_identity, total_requests_per_model=sum(EXTENDED_COUNTS.values()),
        total_planned_model_calls=2 * sum(EXTENDED_COUNTS.values()),
        raw_source_and_individual_answers_remain_private=True)
    validate_public_json(manifest)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    for experiment, envelope in envelopes.items():
        (out_dir / (experiment + ".json")).write_bytes(canonical(envelope))
    # Completion marker is written only after every validated envelope.
    (out_dir / "manifest.json").write_bytes(canonical(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    result = prepare(json.loads(args.config.read_text()), args.out_dir, code_revision=args.code_revision)
    print(json.dumps({"phase": result["phase"], "total_planned_model_calls": result["total_planned_model_calls"]}))


if __name__ == "__main__":
    main()
