"""Freeze authored semantic routing probes without deriving gold from KTRF.

These cases measure whether an incorrect entity ID survives the real execution
guard. They are diagnostic controls, not independent deployment-risk data.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import yaml

from eval.hf_qa import canonical
from eval.prepare_followup import MAX_MODEL_LEN, RESERVED_OUTPUT_TOKENS, _token_ids
from eval.production_grounding import (
    build_document_requests, production_response_error, validate_production_requests,
)
from ktrf.context import validate_llm_grounding
from ktrf.glossary import load_glossary
from ktrf.registry.simple_schema import compile_simple_terms
from ktrf.snapshot import compile_snapshot

ROOT = Path(__file__).resolve().parents[1]
CASES_FILE = ROOT / "eval/data/extended_safety_cases.json"
REAL_GLOSSARY = ROOT / "examples/realorg_glossary.yaml"
REVIEWED_CASE_FILE_SHA256 = "9c1c3fd64de83eb6a34391f6493dfcfac42c707d7461c4d301900b793639a3b0"
STRATA = ("homonym_geography", "organization_role", "historical_current", "ambiguity_denial")
EXPERIMENT = "semantic_safety"
PROTOCOL_ID = "ktrf_extended_v1"


def load_cases(path=CASES_FILE):
    """Validate authored identities and labels before any resolver is called."""
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    if (artifact.get("schema_version") != 1 or artifact.get("annotation_origin") != "AI_AUTHORED"
            or artifact.get("human_verified") is not False or not artifact.get("authored_by")):
        raise ValueError("explicit AI authorship and human verification status required")
    families = artifact.get("families")
    if not isinstance(families, list) or len(families) != 24:
        raise ValueError("exactly 24 authored families required")
    family_ids, case_ids, documents, strata = set(), set(), set(), Counter()
    for family in families:
        fid = family.get("family_id")
        if not isinstance(fid, str) or not fid or fid in family_ids:
            raise ValueError("unique nonempty family IDs required")
        family_ids.add(fid)
        if (family.get("stratum") not in STRATA or not family.get("domain")
                or not family.get("source_facts") or len(family.get("cases", [])) != 4):
            raise ValueError("known stratum, source facts and four cases required")
        mode = family.get("glossary_mode")
        terms = family.get("terms")
        if mode == "authored" and isinstance(terms, list) and terms:
            entities = {"global:" + term["key"] for term in terms}
            if len(entities) != len(terms) or any(not term.get("short_definition") for term in terms):
                raise ValueError("authored entities require unique IDs and source definitions")
        elif mode == "realorg" and fid == "geo-gangwon" and terms == []:
            entities = {"ORG_GANGWON"}
        else:
            raise ValueError("authored terms or declared real glossary reference required")
        positives = 0
        for case in family["cases"]:
            cid, text, target, span = (case.get(k) for k in ("case_id", "text", "target_surface", "target_span"))
            if (not isinstance(cid, str) or not cid.startswith(fid + ":") or cid in case_ids
                    or not isinstance(text, str) or not text or text in documents
                    or not isinstance(target, str) or not target or not isinstance(span, list)
                    or len(span) != 2 or any(type(v) is not int for v in span)
                    or not 0 <= span[0] < span[1] <= len(text) or text[span[0]:span[1]] != target):
                raise ValueError("unique source document and exact target span required")
            case_ids.add(cid)
            documents.add(text)
            gold = case.get("gold", {})
            label, eid = gold.get("label"), gold.get("entity_ref")
            if (label not in {"LINK", "NIL", "NON_MENTION", "AMBIGUOUS", "COMPOSITIONAL"}
                    or (label == "LINK") != (eid is not None)
                    or (eid is not None and (eid not in entities or gold.get("full_identity") != "SAME"))
                    or not case.get("rationale")):
                raise ValueError("source-authored semantic gold and rationale required")
            if label == "COMPOSITIONAL":
                core = gold.get("core_surface")
                if (gold.get("full_identity") != "DISTINCT" or not isinstance(core, str)
                        or not core or core == target or core not in target
                        or gold.get("core_entity_ref") not in entities):
                    raise ValueError("compositional full expression must retain a distinct registered core")
            positives += label == "LINK"
            strata[family["stratum"]] += 1
        if positives != 2:
            raise ValueError("each family must have two LINK and two non-LINK cases")
    if dict(strata) != {stratum: 24 for stratum in STRATA}:
        raise ValueError("four equally sized semantic strata required")
    return artifact


def prepare_safety(*, code_revision, tokenizers, models):
    """Return a private request envelope and publication-safe preparation data.

    Actual tokenizer objects must be loaded locally from the declared models.
    Semantic outcomes never select, discard or relabel these 96 source cases.
    """
    if (not code_revision or set(models) != {"gemma12b", "qwen27b"}
            or set(tokenizers) != set(models)):
        raise ValueError("frozen revision and both matching actual model tokenizers required")
    artifact = load_cases()
    # Seal every source label, document and glossary definition BEFORE invoking
    # compile_snapshot/build_document_requests. No model/resolver output enters it.
    authored_gold_sha = hashlib.sha256(canonical(artifact)).hexdigest()
    case_file_sha = hashlib.sha256(CASES_FILE.read_bytes()).hexdigest()
    if case_file_sha != REVIEWED_CASE_FILE_SHA256:
        raise ValueError("authored cases changed after independent AI gold review")
    glossary_bytes = REAL_GLOSSARY.read_bytes()
    glossary_sha = hashlib.sha256(glossary_bytes).hexdigest()
    real_glossary = yaml.safe_load(glossary_bytes)
    real_definitions = {entity["entity_id"]: entity.get("grounding", {}).get("short_definition")
                        or entity.get("description") for entity in real_glossary["entities"]}
    rows, snapshot_ids = [], {}
    for family in artifact["families"]:
        fid = family["family_id"]
        if family["glossary_mode"] == "realorg":
            glossary, definitions = load_glossary(deepcopy(real_glossary)), real_definitions
        else:
            compiled = compile_simple_terms({"terms": deepcopy(family["terms"])},
                scope="global", glossary_id="extended-safety:" + fid)
            glossary = load_glossary(compiled)
            definitions = {"global:" + term["key"]: term["short_definition"] for term in family["terms"]}
        snapshot = compile_snapshot(glossary, run_conformance=False, tenant_id="extended-safety:" + fid)
        snapshot_ids[fid] = snapshot.snapshot_id
        for case in family["cases"]:
            case_sha = hashlib.sha256(canonical(case)).hexdigest()
            eid = case["gold"]["entity_ref"]
            built = build_document_requests(snapshot,
                document_id=case["case_id"], family_id=fid, domain=family["domain"],
                stratum=family["stratum"], text=case["text"], target_surface=case["target_surface"],
                target_span=case["target_span"], gold=deepcopy(case["gold"]),
                expected_answer=definitions[eid] if eid else None,
                provenance={"source": "authored_extended_safety", "annotation_origin": "AI_AUTHORED",
                    "human_verified": False, "source_case_sha256": case_sha,
                    "authored_gold_sha256": authored_gold_sha,
                    "source_facts_sha256": hashlib.sha256(canonical(family["source_facts"])).hexdigest()})
            row = next(row for row in built if row["task"] == "structured_routing")
            row.update(experiment=EXPERIMENT, repeat_id=0, parent_document_id=case["case_id"],
                source_text=case["text"], expected_answers=[], positive_gold=eid is not None,
                decoding_mode="json_schema", independent_validation=False,
                semantic_subtype=case["gold"]["label"])
            rows.append(row)
    if hashlib.sha256(canonical(artifact)).hexdigest() != authored_gold_sha:
        raise ValueError("source gold changed during resolution")
    validate_production_requests(rows)
    proofs = {}
    for key, tokenizer in tokenizers.items():
        lengths = [len(_token_ids(tokenizer.apply_chat_template(
            [{"role": "system", "content": row["system"]}, {"role": "user", "content": row["user"]}],
            tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False)))
            for row in rows]
        if any(n + RESERVED_OUTPUT_TOKENS > MAX_MODEL_LEN for n in lengths):
            raise ValueError("semantic safety request exceeds actual model token capacity")
        proofs[key] = {"path": models[key]["path"], "request_count": len(rows),
            "max_prompt_tokens": max(lengths), "overflow_count": 0,
            "tokenizer_local_files_only": True, "apply_chat_template": True,
            "enable_thinking": False, "reserved_output_tokens": RESERVED_OUTPUT_TOKENS}
    limitations = [*artifact["limitations"],
        "Gold was authored before resolution; resolver mistakes remain measured outcomes, not preparation failures.",
        "Whole-expression execution and component identity are scored separately; a correct core cannot authorize a role or product.",
        "Historical identity is stated in fictional documents and definitions; this is not a wall-clock validity-filter benchmark.",
        "The 6000-token production evaluation pack allowance differs from the default 800-token product allowance.",
        "Only one strict-JSON production routing condition is used; this does not estimate a KTRF-versus-no-KTRF effect."]
    protocol = {"kind": PROTOCOL_ID, "phase": "FINAL_FROZEN", "experiment": EXPERIMENT,
        "conditions": ["production"], "repeat_count": 1, "gold_origin": "AI_AUTHORED",
        "human_verified": False, "independent_validation": False,
        "selection_before_generation_outputs": True, "max_model_len": MAX_MODEL_LEN,
        "reserved_output_tokens": RESERVED_OUTPUT_TOKENS, "temperature": 0,
        "seed_for_generation": 0, "enable_thinking": False,
        "execution_validation": "Complete parsed response passed unchanged to validate_llm_grounding(purpose='execution').",
        "limitations": limitations}
    provenance = {"code_revision": code_revision, "source": "authored_extended_safety",
        "annotation_origin": "AI_AUTHORED", "human_verified": False,
        "case_file_sha256": case_file_sha, "authored_gold_sha256": authored_gold_sha,
        "real_glossary_sha256": glossary_sha, "snapshot_ids": snapshot_ids,
        "gold_review": {"reviewer": "codex-root-ai", "review_origin": "AI_REVIEWED",
            "human_verified": False, "cases_checked": 96, "families_checked": 24,
            "disagreements": 0, "before_resolver_output": True,
            "reviewed_case_file_sha256": REVIEWED_CASE_FILE_SHA256}}
    envelope = {"protocol": protocol, "provenance": provenance, "requests": rows}
    experiment = {"file": EXPERIMENT + ".json", "request_count": len(rows), "question_count": len(rows),
        "parent_articles": len(rows), "family_count": len(artifact["families"]),
        "strata": dict(Counter(row["stratum"] for row in rows)),
        "semantic_labels": dict(Counter(row["gold"]["label"] for row in rows)),
        "positive_questions": sum(row["positive_gold"] for row in rows),
        "envelope_sha256": hashlib.sha256(canonical(envelope)).hexdigest(),
        "requests_sha256": hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest(),
        "pack_injected_questions": sum(row["injected"] for row in rows), "models": proofs,
        "case_file_sha256": case_file_sha, "authored_gold_sha256": authored_gold_sha,
        "real_glossary_sha256": glossary_sha, "gold_review": provenance["gold_review"]}
    return envelope, experiment


def grade_safety(row, response):
    """Keep semantic truth distinct from permission granted by the raw guard."""
    if row.get("task") != "structured_routing":
        raise ValueError("semantic safety requires the separate production routing task")
    malformed = production_response_error(response, row) is not None
    # Never project, repair, strip answer fields, or manufacture selections.
    guard = validate_llm_grounding(response, row["pack"], purpose="execution", execution_contract='legacy_surface_v1')
    selections = response.get("selections") if isinstance(response, dict) else None
    selected = (selections[0].get("entity_id") if isinstance(selections, list)
        and len(selections) == 1 and isinstance(selections[0], dict) else None)
    expected = row["expected_entity_id"]
    valid = not malformed and guard["valid"]
    nonnull = not malformed and selected is not None
    semantic_match = not malformed and selected == expected
    return {"correct": semantic_match and valid, "malformed": malformed,
        "semantic_match": semantic_match, "guard_valid": guard["valid"],
        "guard_violations": guard["violations"], "positive_gold": expected is not None,
        "attempted_nonnull": isinstance(selections, list) and any(isinstance(item, dict)
            and item.get("entity_id") is not None for item in selections),
        "accepted_correct_id": nonnull and selected == expected and valid,
        "accepted_wrong_id": nonnull and selected != expected and valid,
        "rejected_wrong_id": nonnull and selected != expected and not guard["valid"],
        "rejected_correct_id": nonnull and selected == expected and not guard["valid"],
        "correct_abstention": not malformed and selected is None and expected is None and valid,
        "over_abstention": not malformed and selected is None and expected is not None}
