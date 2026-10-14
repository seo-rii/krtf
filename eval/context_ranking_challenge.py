"""Freeze newly authored, family-disjoint context-ranking challenge events.

Each target occurrence is an event, so two events may share one source
document. Candidate construction reads the registered catalog and production
segmentation only. Authored semantic labels are grading metadata, never a
candidate filter or an input to a reranker or the blind annotation projection.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from eval.context_ranking_corpus import (
    FIXTURES as PRIOR_FIXTURES, LABELS, _digest, _path_from_dict, _profile,
    _sha, _structural_path,
)
from ktrf.glossary import load_glossary
from ktrf.registry.simple_schema import compile_simple_terms
from ktrf.rerank import LinkingHypothesis
from ktrf.snapshot import compile_snapshot

VERSION = "context_ranking_challenge_v1"
FIXTURE = Path(__file__).parent / "fixtures" / "context_ranking_challenge" / "families.jsonl"
FAMILIES = tuple(f"ch{number:02}" for number in range(1, 25))
PARTITION = "external_test"
SOURCE_COLLECTION = "context_ranking_challenge"
EVALUATION_HISTORY = (
    "New AI-authored synthetic families, held out from the prior context-ranking "
    "experiment and not scored at corpus preparation; not a sealed real-world audit."
)
LABEL_COUNTS = {"LINK": 240, "AMBIGUOUS": 24, "NIL": 48,
                "NON_MENTION": 48, "COMPOSITIONAL": 24}


def _prior_catalog_identity():
    """Compare catalog identity with both already evaluated source collections."""
    keys, surfaces, family_ids = set(), set(), set()
    for source in PRIOR_FIXTURES.values():
        families = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
                    if line.strip()]
        for family in families:
            family_ids.add(family["family_id"])
            for term in family["terms"]:
                keys.add(term["key"])
                surfaces.update(term["surfaces"])
                surfaces.add(term["canonical"])
    return keys, surfaces, family_ids


def _snapshot(terms, family_id):
    compiled = compile_simple_terms({"terms": terms}, scope="global", glossary_id=family_id)
    return compile_snapshot(load_glossary(compiled), run_conformance=False, tenant_id=family_id)


def _target_span(text, surface, occurrence):
    if not isinstance(surface, str) or not surface or type(occurrence) is not int or occurrence < 0:
        raise ValueError("target requires a nonempty surface and nonnegative integer occurrence")
    start = -1
    for _ in range(occurrence + 1):
        start = text.find(surface, start + 1)
        if start < 0:
            raise ValueError("designated target occurrence is absent from the source document")
    return start, start + len(surface)


def build_cases(fixture_path=None):
    """Freeze 384 target events from 336 new documents, with two candidates each.

    No target text, source quotation, catalog definition or authored answer is
    rewritten. All families are external test: the earlier selected thresholds
    must be applied without tuning against these events.
    """
    path = FIXTURE if fixture_path is None else Path(fixture_path)
    payload = path.read_bytes()
    families = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]
    if Counter(family["family_id"] for family in families) != Counter(FAMILIES):
        raise ValueError("the 24 new challenge families are required exactly once")
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
                # Keep every registered candidate before reading grading labels.
                candidates = [
                    {"entity_id": "global:" + term["key"], "profile": _profile(term),
                     "canonical": term["canonical"], "aliases": deepcopy(term["surfaces"]),
                     "short_definition": term["short_definition"], "path": asdict(structural),
                     "channel": "abbrev", "transform_cost": 0.0}
                    for term in terms
                ]
                authored = deepcopy(target["gold"])
                entity_id = authored.get("entity_ref")
                selected = next((term for term in terms if "global:" + term["key"] == entity_id), None)
                expected_answer = selected["short_definition"] if authored["label"] == "LINK" and selected else None
                gold = [{"entity_id": entity_id, "core_span": list(structural.core_span),
                         "full_identity": structural.full_identity}] if authored["label"] == "LINK" else []
                annotation = {"gold": authored, "decisive_evidence": target["decisive_evidence"],
                              "rationale": target["rationale"]}
                cases.append({
                    "protocol_version": VERSION,
                    "case_id": document["document_id"] + "::" + target["target_id"],
                    "document_id": document["document_id"], "target_id": target["target_id"],
                    "target_group_id": document["document_id"] if len(document["targets"]) > 1 else None,
                    "source_document_target_count": len(document["targets"]),
                    "family_id": family_id, "domain": family["domain"],
                    "source": "AI_AUTHORED_SYNTHETIC", "source_collection": SOURCE_COLLECTION,
                    "annotation_origin": family["annotation_origin"],
                    "human_verified": family["human_verified"],
                    "evaluation_history": EVALUATION_HISTORY, "seen_prior_context": False,
                    "fixture_sha256": hashlib.sha256(payload).hexdigest(),
                    "split": PARTITION, "stratum": target["stratum"],
                    "title": document["title"], "text": text, "source_text": text,
                    "document_sha256": _sha(text), "target_surface": target["surface"],
                    "target_occurrence": occurrence, "target_span": list(target_span),
                    "core_span": list(structural.core_span),
                    "full_surface_span": list(structural.surface_span),
                    "full_identity": structural.full_identity, "relation": structural.relation,
                    "knowledge_document_id": knowledge["document_id"],
                    "knowledge_text": knowledge["text"], "knowledge_sha256": _sha(knowledge["text"]),
                    "catalog_terms": deepcopy(terms), "catalog_sha256": _digest(terms),
                    "snapshot_id": snapshot.snapshot_id, "candidates": candidates,
                    "candidate_sha256": _digest(candidates), "world_gold": authored,
                    "authored_annotation_sha256": _digest(annotation),
                    "expected_entity_id": entity_id, "expected_answer": expected_answer, "gold": gold,
                    "ambiguity": "resolvable" if authored["label"] == "LINK" else "nil",
                    "semantic_label": authored["label"],
                    "decisive_evidence": deepcopy(target["decisive_evidence"]),
                    "rationale": target["rationale"],
                })
    return validate_cases(cases)


def hypotheses(case, budget=None):
    """Restore both fixed catalog hypotheses and their production typed path."""
    if budget is not None and budget < len(case["candidates"]):
        raise ValueError("candidate budget cannot remove a fixed challenge candidate")
    return [LinkingHypothesis(_path_from_dict(candidate["path"]), candidate["entity_id"],
                              candidate["profile"], candidate["channel"], candidate["transform_cost"])
            for candidate in case["candidates"]]


def _validate_catalog(terms, prior_keys, prior_surfaces):
    if not isinstance(terms, list) or len(terms) != 2:
        raise ValueError("the complete fixed family catalog requires exactly two entities")
    if len({term["key"] for term in terms}) != 2 or len({term["canonical"] for term in terms}) != 2:
        raise ValueError("catalog entity keys and canonical names must be distinct")
    common = set(terms[0]["surfaces"]) & set(terms[1]["surfaces"])
    if len(common) != 1:
        raise ValueError("both family entities must share exactly one registered alias")
    for term in terms:
        if (not all(isinstance(term.get(field), str) and term[field]
                    for field in ("key", "canonical", "short_definition"))
                or not isinstance(term["surfaces"], list) or len(term["surfaces"]) != 2
                or len(set(term["surfaces"])) != 2
                or term["canonical"] not in term["surfaces"]):
            raise ValueError("catalog must preserve a canonical, shared alias and full definition")
        if term["key"] in prior_keys or (set(term["surfaces"]) | {term["canonical"]}) & prior_surfaces:
            raise ValueError("new catalog keys, aliases and canonical names must be disjoint from prior families")


def validate_cases(cases):
    """Validate source occurrences, complete candidates and independent families.

    Structural paths are recomputed from the frozen text and catalog. Rehashing
    a forged SAME path therefore cannot remove a typed derivative's guard.
    Multiple targets share a document identity and count as one source cluster.
    """
    if not isinstance(cases, list) or len(cases) != 384:
        raise ValueError("all 384 challenge target events must be retained")
    prior_keys, prior_surfaces, prior_families = _prior_catalog_identity()
    seen, documents, family_catalogs, family_knowledge, family_domains = set(), {}, {}, {}, {}
    snapshots, fixture_hashes = {}, set()
    for case in cases:
        if case["protocol_version"] != VERSION or case["source_collection"] != SOURCE_COLLECTION:
            raise ValueError("wrong challenge corpus protocol or source collection")
        if case["family_id"] not in FAMILIES or case["family_id"] in prior_families:
            raise ValueError("challenge family must be absent from the prior context corpus")
        if case["split"] != PARTITION:
            raise ValueError("all new families must remain external test without retuning")
        if (case["case_id"] != case["document_id"] + "::" + case["target_id"]
                or case["case_id"] in seen):
            raise ValueError("each target event requires a stable unique case identity")
        seen.add(case["case_id"])
        family_id = case["family_id"]
        if (case["source"] != "AI_AUTHORED_SYNTHETIC"
                or case["annotation_origin"] != "AI_AUTHORED_SYNTHETIC"
                or case["human_verified"] is not False):
            raise ValueError("AI authorship disclosure must not claim human verification")
        if case["evaluation_history"] != EVALUATION_HISTORY or case["seen_prior_context"] is not False:
            raise ValueError("new synthetic-data evaluation history must be disclosed")
        fixture_hash = case["fixture_sha256"]
        if not isinstance(fixture_hash, str) or len(fixture_hash) != 64 or any(c not in "0123456789abcdef" for c in fixture_hash):
            raise ValueError("fixture revision must be a valid SHA-256 hash")
        fixture_hashes.add(fixture_hash)
        if not isinstance(case["domain"], str) or not case["domain"]:
            raise ValueError("challenge family domain must be retained")
        if family_id in family_domains and family_domains[family_id] != case["domain"]:
            raise ValueError("family domain changed between target events")
        family_domains[family_id] = case["domain"]
        text = case["text"]
        if case["source_text"] != text or case["document_sha256"] != _sha(text):
            raise ValueError("original source hash mismatch")
        target_span = _target_span(text, case["target_surface"], case["target_occurrence"])
        if case["target_span"] != list(target_span):
            raise ValueError("designated target occurrence offset mismatch")
        documents.setdefault(case["document_id"], []).append(case)
        terms = case["catalog_terms"]
        if case["catalog_sha256"] != _digest(terms):
            raise ValueError("fixed catalog hash mismatch")
        if family_id in family_catalogs and family_catalogs[family_id] != terms:
            raise ValueError("all family events must retain the same complete catalog")
        if family_id not in family_catalogs:
            _validate_catalog(terms, prior_keys, prior_surfaces)
            family_catalogs[family_id] = terms
            snapshots[family_id] = _snapshot(terms, family_id)
        snapshot = snapshots[family_id]
        if case["snapshot_id"] != snapshot.snapshot_id:
            raise ValueError("snapshot identity differs from the frozen registered catalog")
        structural = _structural_path(text, target_span, terms, snapshot)
        candidates = case["candidates"]
        if case["candidate_sha256"] != _digest(candidates):
            raise ValueError("fixed candidate hash mismatch")
        if [candidate["entity_id"] for candidate in candidates] != ["global:" + term["key"] for term in terms]:
            raise ValueError("candidate inventory or order differs from the complete catalog")
        for candidate, term in zip(candidates, terms):
            if (candidate["profile"] != _profile(term) or candidate["canonical"] != term["canonical"]
                    or candidate["aliases"] != term["surfaces"]
                    or candidate["short_definition"] != term["short_definition"]):
                raise ValueError("candidate profile must contain the unchanged registered term")
            if (_path_from_dict(candidate["path"]) != structural
                    or candidate["channel"] != "abbrev" or candidate["transform_cost"] != 0.0):
                raise ValueError("candidate must retain the actual shared structural path and guard channel")
        if (case["core_span"] != list(structural.core_span)
                or case["full_surface_span"] != list(structural.surface_span)
                or case["full_identity"] != structural.full_identity or case["relation"] != structural.relation):
            raise ValueError("core/full-surface contract differs from production typed segmentation")
        if case["knowledge_sha256"] != _sha(case["knowledge_text"]):
            raise ValueError("original knowledge hash mismatch")
        knowledge = (case["knowledge_document_id"], case["knowledge_text"])
        if family_id in family_knowledge and family_knowledge[family_id] != knowledge:
            raise ValueError("all family events must retain the same knowledge document")
        family_knowledge[family_id] = knowledge
        authored, label = case["world_gold"], case["semantic_label"]
        entity_id = authored.get("entity_ref")
        if label not in LABELS or authored["label"] != label or case["expected_entity_id"] != entity_id:
            raise ValueError("authored semantic grading label mismatch")
        annotation = {"gold": authored, "decisive_evidence": case["decisive_evidence"],
                      "rationale": case["rationale"]}
        if case["authored_annotation_sha256"] != _digest(annotation):
            raise ValueError("authored annotation hash mismatch")
        if label == "LINK":
            selected = next((candidate for candidate in candidates if candidate["entity_id"] == entity_id), None)
            gold = [{"entity_id": entity_id, "core_span": list(structural.core_span),
                     "full_identity": structural.full_identity}]
            if (selected is None or case["expected_answer"] != selected["short_definition"]
                    or case["gold"] != gold or case["ambiguity"] != "resolvable"
                    or structural.full_identity != "SAME"):
                raise ValueError("positive gold must reference the registered exact-link identity")
        elif (entity_id is not None or case["expected_answer"] is not None
              or case["gold"] or case["ambiguity"] != "nil"):
            raise ValueError("all semantic negative events require abstention, including genuine ambiguity")
        for evidence in case["decisive_evidence"]:
            location = evidence["document"]
            original = text if location == "source" else case["knowledge_text"]
            if location not in {"source", "knowledge"} or not evidence["quote"] or evidence["quote"] not in original:
                raise ValueError("annotation evidence must remain a verbatim source or catalog quote")
    if len(fixture_hashes) != 1:
        raise ValueError("all cases must belong to one frozen fixture revision")
    if set(family_catalogs) != set(FAMILIES):
        raise ValueError("all 24 new families must be retained")
    keys, surfaces = set(), set()
    for terms in family_catalogs.values():
        family_keys = {term["key"] for term in terms}
        family_surfaces = {surface for term in terms for surface in term["surfaces"]}
        if keys & family_keys or surfaces & family_surfaces:
            raise ValueError("challenge catalogs must not share keys, aliases or canonical names across families")
        keys.update(family_keys)
        surfaces.update(family_surfaces)
    per_family = Counter()
    multi_per_family = Counter()
    for document_id, targets in documents.items():
        first = targets[0]
        if len(targets) not in {1, 2}:
            raise ValueError("each challenge document must contain one or two designated target events")
        identity = (first["family_id"], first["title"], first["text"], first["document_sha256"])
        for target in targets:
            if (target["family_id"], target["title"], target["text"], target["document_sha256"]) != identity:
                raise ValueError("events sharing a document ID must share the complete original source")
            if target["source_document_target_count"] != len(targets):
                raise ValueError("document target count differs from the complete event inventory")
            expected_group = document_id if len(targets) > 1 else None
            if target["target_group_id"] != expected_group:
                raise ValueError("multitarget grouping must preserve source document identity")
        if len({tuple(target["target_span"]) for target in targets}) != len(targets):
            raise ValueError("two document events must identify distinct occurrences")
        per_family[first["family_id"]] += 1
        multi_per_family[first["family_id"]] += len(targets) == 2
    if len(documents) != 336 or any(per_family[family] != 14 or multi_per_family[family] != 2 for family in FAMILIES):
        raise ValueError("each new family requires 14 documents including two multitarget documents")
    # Designed label totals are descriptive. A blind review may change grading
    # labels while preserving all 384 inputs; never force a reviewed answer to
    # match the author's intended positive/negative count.
    return cases


def load_cases(path):
    """Load frozen JSONL events without rereading their mutable source fixture."""
    cases = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return validate_cases(cases)


def blind_projection(cases):
    """Project source/catalog inputs for a fresh AI review, without authored gold.

    Hash identifiers hide generator document ordering and stratum names. Titles,
    gold, rationale, evidence and all grading fields are absent. The root process
    keeps the separate binding map; reviewers receive only this projection.
    """
    projected = [{"case_id": "case-" + _sha(case["case_id"])[:24],
             "document_id": "document-" + _sha(case["document_id"])[:24],
             "family_id": "family-" + _sha(case["family_id"])[:24],
             "text": case["text"], "target_surface": case["target_surface"],
             "target_occurrence": case["target_occurrence"],
             "target_span": deepcopy(case["target_span"]),
             "catalog_terms": deepcopy(case["catalog_terms"])} for case in cases]
    return sorted(projected, key=lambda row: row["case_id"])


def blind_binding_map(cases):
    """Keep opaque review identities separate from the authored event IDs."""
    return {"case-" + _sha(case["case_id"])[:24]: case["case_id"] for case in cases}
