"""Conservative QA diagnostics alongside a sealed experiment's exact score.

This is a bounded normalization check, not a general semantic judge. It credits
only the complete registered definition with whitespace, one Korean copula, and
one terminal period changed. Additional claims and paraphrases need review.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import unicodedata

from eval.production_grounding import production_response_error
from eval.report_document_context import _read_run

VERSION = "qa_definition_normalization_v1"
STATUSES = ("MATCH", "NULL_CORRECT", "MISMATCH", "UNASSESSED")
COPULAS = ("", "이다", "다", "입니다")


def _normalize(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def _variants(definition):
    definition = _normalize(definition)
    return {definition + suffix + period for suffix in COPULAS for period in ("", ".")} | {
        definition + " " + suffix + period for suffix in COPULAS if suffix for period in ("", ".")}


def assess_qa_answer(answer, expected_definition, definitions, expected_entity_id=None):
    """Return a diagnostic decision without changing the exact response contract.

    ``definitions`` is an ID-to-definition inventory from frozen registry facts,
    never selected according to the model answer. Unknown extra prose receives
    no automatic credit. Missing and malformed responses must be filtered by the
    caller; a real JSON null is the only value eligible for NULL_CORRECT.
    """
    if not isinstance(definitions, dict) or any(not isinstance(eid, str) or not eid or
            not isinstance(text, str) or not text.strip() for eid, text in definitions.items()):
        raise ValueError("definitions must contain nonempty registry IDs and definitions")
    if expected_definition is not None and (not isinstance(expected_definition, str) or not expected_definition.strip()):
        raise ValueError("expected definition must be a nonempty string or null")
    if expected_entity_id is not None and (expected_entity_id not in definitions or
            definitions[expected_entity_id] != expected_definition):
        raise ValueError("expected ID and definition disagree with the frozen inventory")

    def result(status, reason, normalized=None, ids=()):
        return {"status": status, "reason": reason, "normalized_answer": normalized,
                "matched_entity_ids": sorted(ids)}

    if answer is None:
        return result("NULL_CORRECT" if expected_definition is None else "MISMATCH",
                      "gold_null" if expected_definition is None else "positive_abstention")
    if not isinstance(answer, str):
        return result("UNASSESSED", "invalid_answer_type")
    normalized = _normalize(answer)
    if expected_definition is None:
        return result("MISMATCH", "nonnull_answer_for_null_gold", normalized)
    if not normalized:
        return result("MISMATCH", "empty_answer_for_positive_gold", normalized)

    matches = [eid for eid, definition in definitions.items() if normalized in _variants(definition)]
    expected = _normalize(expected_definition)
    other_matches = [eid for eid in matches if _normalize(definitions[eid]) != expected]
    if other_matches:
        return result("MISMATCH", "different_registered_definition", normalized, matches)
    if normalized in _variants(expected_definition):
        # Distinct IDs with identical definitions cannot support an identity claim.
        # QA itself only asks for the definition, so identical text remains a match.
        return result("MATCH", "exact_definition" if answer == expected_definition else
                      "whitespace_copula_or_period_only", normalized, matches)

    mentioned = [eid for eid, definition in definitions.items() if _normalize(definition) in normalized]
    if len({_normalize(definitions[eid]) for eid in mentioned}) > 1:
        return result("UNASSESSED", "multiple_registered_definitions", normalized, mentioned)
    # A definition followed by an explicit denial must not gain containment credit.
    if expected in normalized and re.search(r"(?:아니(?:다|며|라|고|라는|라고|라고요)|아닙니다|아닌|않(?:다|는|습니다)|불가능|없(?:다|는|습니다))", normalized[len(expected):]):
        return result("UNASSESSED", "possible_negation_or_contradiction", normalized, mentioned)
    if mentioned:
        return result("UNASSESSED", "registered_definition_with_extra_text", normalized, mentioned)
    return result("UNASSESSED", "paraphrase_or_unsupported_answer", normalized)


def _candidate_definitions(requests):
    """Recover the complete family catalog from frozen facts, without fixtures."""
    catalogs = defaultdict(dict)
    expected_ids = defaultdict(set)

    def add(family, eid, definition):
        if not isinstance(eid, str) or not isinstance(definition, str) or not definition:
            raise ValueError("invalid frozen candidate definition")
        previous = catalogs[family].setdefault(eid, definition)
        if previous != definition:
            raise ValueError("conflicting frozen candidate definitions")

    def candidates(family, value):
        if isinstance(value, dict):
            if value.get("entity_id") and value.get("short_definition"):
                add(family, value["entity_id"], value["short_definition"])
            for child in value.values():
                candidates(family, child)
        elif isinstance(value, list):
            for child in value:
                candidates(family, child)

    for row in requests:
        family = row["family_id"]
        expected_ids[family].update(row["glossary_entity_ids"])
        if row["expected_entity_id"] is not None:
            add(family, row["expected_entity_id"], row["expected_answer"])
        for eid, definition in row.get("candidate_definitions", {}).items():
            add(family, eid, definition)
        candidates(family, row.get("pack"))
    if any(set(catalogs[family]) != ids for family, ids in expected_ids.items()):
        raise ValueError("frozen definitions must cover exactly every family glossary ID")
    return dict(catalogs)


def prepare_diagnostic(run_dir):
    """Verify the original seal and exact grades, then add a separate diagnostic."""
    manifest, requests, records, graded, _ = _read_run(Path(run_dir))
    inventories = _candidate_definitions(requests)
    outputs = {(record["case_id"], record["condition"]): record for record in records}
    strict = {(case["case_id"], case["condition"]): case for case in graded["cases"]}
    cases = []
    for row in requests:
        if row["task"] != "document_qa":
            continue
        key = row["case_id"], row["condition"]
        record = outputs.get(key)
        if record is None or "response" not in record:
            assessment = {"status": "UNASSESSED", "reason": "missing_response",
                          "normalized_answer": None, "matched_entity_ids": []}
        elif record["status"] != "RECEIVED" or production_response_error(record["response"], row):
            assessment = {"status": "UNASSESSED", "reason": "malformed_response",
                          "normalized_answer": None, "matched_entity_ids": []}
        else:
            assessment = assess_qa_answer(record["response"]["answer"], row["expected_answer"],
                                           inventories[row["family_id"]], row["expected_entity_id"])
        cases.append({"case_id": row["case_id"], "condition": row["condition"],
            "family_id": row["family_id"], "document_id": row["document_id"], "stratum": row["stratum"],
            "positive_gold": row["expected_entity_id"] is not None,
            "strict_exact_match": bool(strict[key].get("semantic_match")),
            "answer": record.get("response", {}).get("answer") if record else None,
            "response_status": record.get("status") if record else "NOT_ATTEMPTED",
            "expected_definition": row["expected_answer"], "expected_entity_id": row["expected_entity_id"],
            **assessment})

    def summarize(group):
        statuses = Counter(case["status"] for case in group)
        strict_correct = sum(case["strict_exact_match"] for case in group)
        diagnostic = statuses["MATCH"] + statuses["NULL_CORRECT"]
        return {"planned": len(group), "strict_exact_correct": strict_correct,
            "diagnostic_credited": diagnostic, "additional_normalized_matches": diagnostic - strict_correct,
            **{status: statuses[status] for status in STATUSES},
            "positive_planned": sum(case["positive_gold"] for case in group),
            "positive_diagnostic_match": sum(case["positive_gold"] and case["status"] == "MATCH" for case in group),
            "reasons": dict(sorted(Counter(case["reason"] for case in group).items()))}

    return {"kind": "sealed_qa_normalization_diagnostic", "version": VERSION,
        "original_model": manifest["requested_model"], "original_code_revision": manifest["code_revision"],
        "verified_manifest_seal_sha256": manifest["seal_sha256"],
        "verified_artifact_sha256": manifest["artifact_sha256"], "original_scores_unchanged": True,
        "automatic_coverage": "Exact registered definition plus whitespace, one copula and one period only. UNASSESSED receives no credit.",
        "inventory_origin": "Frozen positive definition/ID pairs and frozen candidate packs, checked against every glossary ID; no contemporary fixtures or model-answer-dependent inventory.",
        "candidate_definitions_by_family": inventories, "overall": summarize(cases),
        "by_condition": {condition: summarize([case for case in cases if case["condition"] == condition])
                         for condition in sorted({case["condition"] for case in cases})},
        "review_queue": [case for case in cases if case["status"] == "UNASSESSED"], "cases": cases,
        "limitations": ["This bounded deterministic normalization is not a general semantic accuracy estimate.",
                        "Paraphrases, additional assertions, contradictions and multiple candidate definitions need independent review.",
                        "Missing or malformed responses are unassessed failures, never correct abstentions.",
                        "Original AI-authored synthetic gold and information-removal limitations still apply."]}


def render_markdown(summary):
    lines = ["# Frozen QA definition diagnostic", "", f"Model: `{summary['original_model']}`.", "",
        "Original exact scores and sealed artifacts remain unchanged. This diagnostic credits only the complete definition with whitespace, one Korean copula, and one terminal period changed. Additional claims and paraphrases receive no automatic credit.", "",
        "| Condition | Planned | Strict exact correct | Diagnostic credited | Added matches | Unassessed |",
        "|---|---:|---:|---:|---:|---:|"]
    for condition, counts in summary["by_condition"].items():
        lines.append(f"| {condition} | {counts['planned']} | {counts['strict_exact_correct']} | {counts['diagnostic_credited']} | {counts['additional_normalized_matches']} | {counts['UNASSESSED']} |")
    lines.extend(["", "Unassessed items remain failures until reviewed. Their complete raw answers, expected definitions and reasons are preserved in `diagnostic.json` under `review_queue`.", "", "Limitations:", ""])
    lines.extend("- " + limitation for limitation in summary["limitations"])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    summary = prepare_diagnostic(args.run_dir)
    if args.out_dir.resolve() == args.run_dir.resolve():
        parser.error("diagnostics must have their own output directory")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if any((args.out_dir / name).exists() for name in ("diagnostic.json", "RESULTS.md")):
        raise FileExistsError("diagnostic output already exists")
    (args.out_dir / "diagnostic.json").write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / "RESULTS.md").write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps({"model": summary["original_model"], **summary["overall"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
