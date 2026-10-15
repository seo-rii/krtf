"""Freeze source occurrences for the evidence-selection development and holdout.

Candidate construction uses only the complete registered family catalog and
production typed segmentation. Authored labels are grading metadata. The old
challenge is explicitly development data; newly authored families remain a
separate cohort and are never used to choose proposal thresholds.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from eval.context_ranking_challenge import (
    FIXTURE as DEVELOPMENT_PATH, _prior_catalog_identity, _snapshot, _target_span,
    _validate_catalog, hypotheses,
)
from eval.context_ranking_corpus import LABELS, _digest, _path_from_dict, _profile, _sha, _structural_path

VERSION = "occurrence_evidence_corpus_v1"
HELDOUT_PATH = Path(__file__).parent / "fixtures" / "occurrence_evidence_holdout" / "families.jsonl"
INVENTORIES = {
    "development": {"families": 24, "documents": 336, "events": 384,
                    "documents_per_family": 14, "events_per_family": 16, "multi_per_family": 2},
    "heldout": {"families": 12, "documents": 144, "events": 168,
                "documents_per_family": 12, "events_per_family": 14, "multi_per_family": 2},
}
HISTORY = {
    "development": "Previously scored and inspected AI-authored challenge; used to develop evidence selection, not held out.",
    "heldout": "New separately authored AI-synthetic families; source/catalog blind AI review before inference; not an independent human or deployment audit.",
}


def _cohort(cohort):
    if cohort not in INVENTORIES:
        raise ValueError("cohort must be development or heldout")
    return INVENTORIES[cohort]


def build_cases(path=None, cohort="development", *, require_inventory=True):
    """Preserve every target and both registered entities without gold pruning."""
    _cohort(cohort)
    path = Path(path) if path is not None else (DEVELOPMENT_PATH if cohort == "development" else HELDOUT_PATH)
    payload = path.read_bytes()
    families = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]
    if len({family["family_id"] for family in families}) != len(families):
        raise ValueError("each source family must occur exactly once")
    cases = []
    for family in families:
        family_id, terms = family["family_id"], family["terms"]
        snapshot = _snapshot(terms, family_id)
        knowledge = family["knowledge_document"]
        for document in family["documents"]:
            text = document["text"]
            for target in document["targets"]:
                occurrence = target.get("occurrence", 0)
                target_span = _target_span(text, target["surface"], occurrence)
                structural = _structural_path(text, target_span, terms, snapshot)
                # These complete hypotheses are frozen before labels are read.
                candidates = [{"entity_id": "global:" + term["key"], "profile": _profile(term),
                               "canonical": term["canonical"], "aliases": deepcopy(term["surfaces"]),
                               "short_definition": term["short_definition"], "path": asdict(structural),
                               "channel": "abbrev", "transform_cost": 0.0} for term in terms]
                authored = deepcopy(target["gold"])
                entity_id = authored.get("entity_ref")
                chosen = next((term for term in terms if "global:" + term["key"] == entity_id), None)
                annotation = {"gold": authored, "decisive_evidence": target["decisive_evidence"],
                              "rationale": target["rationale"]}
                cases.append({
                    "protocol_version": VERSION, "cohort": cohort,
                    "case_id": document["document_id"] + "::" + target["target_id"],
                    "document_id": document["document_id"], "target_id": target["target_id"],
                    "target_group_id": document["document_id"] if len(document["targets"]) > 1 else None,
                    "source_document_target_count": len(document["targets"]),
                    "family_id": family_id, "domain": family["domain"],
                    "source": "AI_AUTHORED_SYNTHETIC", "source_collection": "occurrence_evidence_" + cohort,
                    "annotation_origin": family["annotation_origin"], "human_verified": family["human_verified"],
                    "evaluation_history": HISTORY[cohort], "seen_prior_context": cohort == "development",
                    "fixture_sha256": hashlib.sha256(payload).hexdigest(), "split": cohort,
                    "stratum": target["stratum"], "title": document["title"], "text": text, "source_text": text,
                    "document_sha256": _sha(text), "target_surface": target["surface"],
                    "target_occurrence": occurrence, "target_span": list(target_span),
                    "core_span": list(structural.core_span), "full_surface_span": list(structural.surface_span),
                    "full_identity": structural.full_identity, "relation": structural.relation,
                    "knowledge_document_id": knowledge["document_id"], "knowledge_text": knowledge["text"],
                    "knowledge_sha256": _sha(knowledge["text"]), "catalog_terms": deepcopy(terms),
                    "catalog_sha256": _digest(terms), "snapshot_id": snapshot.snapshot_id,
                    "candidates": candidates, "candidate_sha256": _digest(candidates),
                    "world_gold": authored, "authored_annotation_sha256": _digest(annotation),
                    "expected_entity_id": entity_id,
                    "expected_answer": chosen["short_definition"] if chosen and authored["label"] == "LINK" else None,
                    "gold": [{"entity_id": entity_id, "core_span": list(structural.core_span),
                              "full_identity": structural.full_identity}] if authored["label"] == "LINK" else [],
                    "ambiguity": "resolvable" if authored["label"] == "LINK" else "nil",
                    "semantic_label": authored["label"], "decisive_evidence": deepcopy(target["decisive_evidence"]),
                    "rationale": target["rationale"],
                })
    return validate_cases(cases, require_inventory=require_inventory)


def validate_cases(cases, *, require_inventory=True):
    """Recompute actual paths and verify source, grading and cohort identities.

    The inventory is fixed, but semantic label totals are deliberately not
    enforced: blind review may correct authored labels before inference.
    """
    if not isinstance(cases, list) or not cases:
        raise ValueError("a nonempty frozen target event list is required")
    prior_keys, prior_surfaces, prior_families = _prior_catalog_identity()
    development_keys, development_surfaces, development_families = set(), set(), set()
    # Heldout-only annotation preparation must also reject reuse of the old
    # development catalog, before a later combined-cohort validation occurs.
    if any(case.get("cohort") == "heldout" for case in cases):
        for line in DEVELOPMENT_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            family = json.loads(line)
            development_families.add(family["family_id"])
            for term in family["terms"]:
                development_keys.add(term["key"])
                development_surfaces.update(term["surfaces"])
                development_surfaces.add(term["canonical"])
    seen, documents, catalogs, knowledge, domains, snapshots = set(), {}, {}, {}, {}, {}
    cohort_cases = {cohort: [] for cohort in INVENTORIES}
    hashes = {cohort: set() for cohort in INVENTORIES}
    for case in cases:
        cohort = case["cohort"]
        _cohort(cohort)
        if (case["protocol_version"] != VERSION or case["split"] != cohort
                or case["source_collection"] != "occurrence_evidence_" + cohort):
            raise ValueError("source cohort protocol mismatch")
        if (case["evaluation_history"] != HISTORY[cohort]
                or case["seen_prior_context"] is not (cohort == "development")):
            raise ValueError("development exposure and heldout history must remain explicit")
        if (case["source"] != "AI_AUTHORED_SYNTHETIC" or case["annotation_origin"] != "AI_AUTHORED_SYNTHETIC"
                or case["human_verified"] is not False):
            raise ValueError("synthetic authorship must not claim human verification")
        if (case["case_id"] != case["document_id"] + "::" + case["target_id"] or case["case_id"] in seen):
            raise ValueError("stable unique case identity is required")
        seen.add(case["case_id"])
        cohort_cases[cohort].append(case)
        fixture_hash = case["fixture_sha256"]
        if not isinstance(fixture_hash, str) or len(fixture_hash) != 64 or set(fixture_hash) - set("0123456789abcdef"):
            raise ValueError("fixture hash must be a SHA-256 identity")
        hashes[cohort].add(fixture_hash)
        text = case["text"]
        if case["source_text"] != text or case["document_sha256"] != _sha(text):
            raise ValueError("original source hash mismatch")
        target_span = _target_span(text, case["target_surface"], case["target_occurrence"])
        if list(target_span) != case["target_span"]:
            raise ValueError("designated occurrence offset mismatch")
        family_id, terms = case["family_id"], case["catalog_terms"]
        if family_id in prior_families or case["catalog_sha256"] != _digest(terms):
            raise ValueError("family identity or catalog hash mismatch")
        if cohort == "heldout" and family_id in development_families:
            raise ValueError("heldout family must be disjoint from the old development catalog")
        if family_id not in catalogs:
            _validate_catalog(terms, prior_keys, prior_surfaces)
            if cohort == "heldout":
                _validate_catalog(terms, development_keys, development_surfaces)
            catalogs[family_id] = (cohort, deepcopy(terms))
            snapshots[family_id] = _snapshot(terms, family_id)
        if catalogs[family_id] != (cohort, terms):
            raise ValueError("a family catalog cannot change or cross cohorts")
        if not isinstance(case["domain"], str) or not case["domain"]:
            raise ValueError("family domain must be retained")
        domains.setdefault(family_id, case["domain"])
        if domains[family_id] != case["domain"]:
            raise ValueError("family domain changed")
        snapshot = snapshots[family_id]
        if case["snapshot_id"] != snapshot.snapshot_id:
            raise ValueError("catalog snapshot identity mismatch")
        structural = _structural_path(text, target_span, terms, snapshot)
        candidates = case["candidates"]
        if (case["candidate_sha256"] != _digest(candidates)
                or [candidate["entity_id"] for candidate in candidates] != ["global:" + term["key"] for term in terms]):
            raise ValueError("complete fixed candidate inventory or hash mismatch")
        for candidate, term in zip(candidates, terms):
            if (candidate["profile"] != _profile(term) or candidate["canonical"] != term["canonical"]
                    or candidate["aliases"] != term["surfaces"] or candidate["short_definition"] != term["short_definition"]
                    or _path_from_dict(candidate["path"]) != structural
                    or candidate["channel"] != "abbrev" or candidate["transform_cost"] != 0.0):
                raise ValueError("candidate must retain unchanged catalog profile and actual structural path")
        if (case["core_span"] != list(structural.core_span) or case["full_surface_span"] != list(structural.surface_span)
                or case["full_identity"] != structural.full_identity or case["relation"] != structural.relation):
            raise ValueError("production core/full-surface contract mismatch")
        if case["knowledge_sha256"] != _sha(case["knowledge_text"]):
            raise ValueError("knowledge source hash mismatch")
        knowledge.setdefault(family_id, (case["knowledge_document_id"], case["knowledge_text"]))
        if knowledge[family_id] != (case["knowledge_document_id"], case["knowledge_text"]):
            raise ValueError("family knowledge source changed")
        authored, label = case["world_gold"], case["semantic_label"]
        entity_id = authored.get("entity_ref")
        if label not in LABELS or authored["label"] != label or case["expected_entity_id"] != entity_id:
            raise ValueError("independent authored label mismatch")
        annotation = {"gold": authored, "decisive_evidence": case["decisive_evidence"], "rationale": case["rationale"]}
        if case["authored_annotation_sha256"] != _digest(annotation):
            raise ValueError("authored annotation hash mismatch")
        if label == "LINK":
            selected = next((candidate for candidate in candidates if candidate["entity_id"] == entity_id), None)
            expected = [{"entity_id": entity_id, "core_span": list(structural.core_span), "full_identity": structural.full_identity}]
            if (selected is None or structural.full_identity != "SAME" or case["gold"] != expected
                    or case["expected_answer"] != selected["short_definition"] or case["ambiguity"] != "resolvable"):
                raise ValueError("positive label requires a registered SAME exact-link identity")
        elif entity_id is not None or case["expected_answer"] is not None or case["gold"] or case["ambiguity"] != "nil":
            raise ValueError("every semantic negative requires abstention")
        for evidence in case["decisive_evidence"]:
            location = evidence["document"]
            original = text if location == "source" else case["knowledge_text"]
            if location not in {"source", "knowledge"} or not evidence["quote"] or evidence["quote"] not in original:
                raise ValueError("annotation evidence must be a verbatim source or knowledge quote")
        documents.setdefault(case["document_id"], []).append(case)
    keys, surfaces = set(), set()
    for _, terms in catalogs.values():
        family_keys = {term["key"] for term in terms}
        family_surfaces = {surface for term in terms for surface in term["surfaces"]}
        if keys & family_keys or surfaces & family_surfaces:
            raise ValueError("family catalogs must remain disjoint across both cohorts")
        keys.update(family_keys)
        surfaces.update(family_surfaces)
    per_family_docs, per_family_multi, source_cohorts = Counter(), Counter(), {}
    for document_id, targets in documents.items():
        first = targets[0]
        source_cohorts.setdefault(first["document_sha256"], first["cohort"])
        if source_cohorts[first["document_sha256"]] != first["cohort"]:
            raise ValueError("source document content cannot be reused across cohorts")
        if len(targets) not in {1, 2}:
            raise ValueError("each source document must retain one or two targets")
        for target in targets:
            if any(target[key] != first[key] for key in ("cohort", "family_id", "text", "title", "document_sha256")):
                raise ValueError("a source document identity cannot cross sources or cohorts")
            if (target["source_document_target_count"] != len(targets)
                    or target["target_group_id"] != (document_id if len(targets) == 2 else None)):
                raise ValueError("complete source occurrence grouping mismatch")
        if len({tuple(target["target_span"]) for target in targets}) != len(targets):
            raise ValueError("multiple targets must identify distinct occurrences")
        per_family_docs[first["family_id"]] += 1
        per_family_multi[first["family_id"]] += len(targets) == 2
    for cohort, group in cohort_cases.items():
        if not group:
            continue
        if len(hashes[cohort]) != 1:
            raise ValueError("each cohort must have one frozen fixture revision")
        if require_inventory:
            inventory = INVENTORIES[cohort]
            family_counts = Counter(row["family_id"] for row in group)
            if (len(group) != inventory["events"] or len(family_counts) != inventory["families"]
                    or len({row["document_id"] for row in group}) != inventory["documents"]
                    or any(count != inventory["events_per_family"] for count in family_counts.values())
                    or any(per_family_docs[family] != inventory["documents_per_family"]
                           or per_family_multi[family] != inventory["multi_per_family"] for family in family_counts)):
                raise ValueError("complete frozen cohort family/document/occurrence inventory is required")
    return cases


def load_cases(path, *, require_inventory=True):
    return validate_cases([json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
                           if line.strip()], require_inventory=require_inventory)


def blind_projection(cases):
    """Expose only source/catalog and occurrence, with opaque unordered IDs."""
    return sorted([{"case_id": "case-" + _sha(case["case_id"])[:24],
                    "document_id": "document-" + _sha(case["document_id"])[:24],
                    "family_id": "family-" + _sha(case["family_id"])[:24],
                    "text": case["text"], "target_surface": case["target_surface"],
                    "target_occurrence": case["target_occurrence"], "target_span": deepcopy(case["target_span"]),
                    "catalog_terms": deepcopy(case["catalog_terms"])} for case in cases], key=lambda row: row["case_id"])


def blind_binding_map(cases):
    return {"case-" + _sha(case["case_id"])[:24]: case["case_id"] for case in cases}
