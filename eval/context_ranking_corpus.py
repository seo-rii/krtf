"""Freeze existing authored documents for candidate-by-context ranking.

Candidate inventory, structural analysis and family partitioning consult only
the registered glossary and source document. Authored labels remain grading
metadata. In particular an AMBIGUOUS document requires abstention, rather than
making both entities positive ranking targets.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, fields
import hashlib
import json
from pathlib import Path

from ktrf.glossary import load_glossary
from ktrf.registry.simple_schema import compile_simple_terms
from ktrf.rerank import LinkingHypothesis
from ktrf.segmentation import StructuralPath, segment_token
from ktrf.snapshot import compile_snapshot

VERSION = "context_ranking_corpus_v1"
FIXTURES = {
    name: Path(__file__).parent / "fixtures" / name / "families.jsonl"
    for name in ("document_context", "context_definitions")
}
SPLIT_SEED = "context-ranking-family-v1:"
# Predeclared by hashing family IDs, before inspecting labels or model scores.
TUNE_FAMILIES = ("f05", "f03", "f01", "f02")
TEST_FAMILIES = ("f08", "f06", "f04", "f07")
LABELS = frozenset({"LINK", "NIL", "AMBIGUOUS", "COMPOSITIONAL", "NON_MENTION"})


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest(value):
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def family_split(family_id):
    """A fixed 4/4 family split shared by both original source collections."""
    if family_id in TUNE_FAMILIES:
        return "tune"
    if family_id in TEST_FAMILIES:
        return "test"
    raise ValueError("family not in the predeclared ranking split")


def _profile(term):
    # Exact definitions and all aliases are available for both candidates.
    # The entity ID is metadata, not linguistic evidence inside the profile.
    return ("정식 명칭: " + term["canonical"] + "\n"
            + "표면형: " + ", ".join(term["surfaces"]) + "\n"
            + "정의: " + term["short_definition"])


def _structural_path(text, target_span, terms, snapshot):
    """Use the same typed segmentation as production, without a gold winner."""
    start, end = target_span
    target = text[start:end]
    aliases = {alias for term in terms for alias in term["surfaces"]}
    paths = segment_token(target, (start, end), snapshot.fst,
                          left_context=text[max(0, start - 6):start], max_paths=64)
    matching = [path for path in paths
                if path.core in aliases and path.surface_span == (start, end)]
    if len(matching) != 1:
        raise ValueError("registered alias must have one typed whole-target path")
    return matching[0]


def build_cases(fixture_paths=None):
    """Return 64 frozen cases with both registered candidates in every case.

    Optional paths let tests independently change authored labels while
    retaining the exact same glossary, candidates and structural hypotheses.
    No source text, quotation or answer is rewritten during preparation.
    """
    fixture_paths = FIXTURES if fixture_paths is None else fixture_paths
    if set(fixture_paths) != set(FIXTURES):
        raise ValueError("both original source collections are required")
    cases, catalogs, knowledge_by_family = [], {}, {}
    for source_collection, source_path in fixture_paths.items():
        path = Path(source_path)
        payload = path.read_bytes()
        families = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]
        if {family["family_id"] for family in families} != set(TUNE_FAMILIES + TEST_FAMILIES):
            raise ValueError("original eight families required in each collection")
        for family in families:
            family_id, terms = family["family_id"], family["terms"]
            if family.get("annotation_origin") != "AI_AUTHORED_SYNTHETIC" or family.get("human_verified") is not False:
                raise ValueError("original corpus must disclose AI authorship")
            if len(terms) != 2:
                raise ValueError("the fixed family shortlist contains exactly two registered entities")
            if family_id in catalogs and catalogs[family_id] != terms:
                raise ValueError("glossary must be unchanged between source collections")
            catalogs[family_id] = deepcopy(terms)
            knowledge = family["knowledge_document"]
            if family_id in knowledge_by_family and knowledge_by_family[family_id] != knowledge:
                raise ValueError("knowledge documents must be unchanged between collections")
            knowledge_by_family[family_id] = deepcopy(knowledge)
            compiled = compile_simple_terms({"terms": terms}, scope="global", glossary_id=family_id)
            snapshot = compile_snapshot(load_glossary(compiled), run_conformance=False, tenant_id=family_id)
            for document in family["documents"]:
                text, target = document["text"], document["target_surface"]
                start = -1
                for _ in range(document.get("target_occurrence", 0) + 1):
                    start = text.find(target, start + 1)
                    if start < 0:
                        raise ValueError("designated target is absent from the original document")
                target_span = (start, start + len(target))
                structural = _structural_path(text, target_span, terms, snapshot)
                # Candidate construction intentionally precedes all gold use.
                candidates = [{"entity_id": "global:" + term["key"], "profile": _profile(term),
                               "canonical": term["canonical"], "aliases": deepcopy(term["surfaces"]),
                               "short_definition": term["short_definition"], "path": asdict(structural),
                               "channel": "abbrev", "transform_cost": 0.0}
                              for term in terms]
                authored = deepcopy(document["gold"])
                entity_id = authored.get("entity_ref")
                gold = [{"entity_id": entity_id, "core_span": list(structural.core_span),
                         "full_identity": structural.full_identity}] if authored["label"] == "LINK" else []
                cases.append({
                    "protocol_version": VERSION, "case_id": document["document_id"],
                    "document_id": document["document_id"], "family_id": family_id,
                    "source": "AI_AUTHORED_SYNTHETIC", "source_collection": source_collection,
                    "annotation_origin": "AI_AUTHORED_SYNTHETIC", "human_verified": False,
                    "evaluation_history": "Previously inspected and evaluated synthetic documents; not an independent sealed real-world audit.",
                    "fixture_sha256": hashlib.sha256(payload).hexdigest(),
                    "split": family_split(family_id), "stratum": document["stratum"],
                    "title": document["title"], "text": text, "source_text": text,
                    "document_sha256": _sha(text), "target_surface": target,
                    "target_occurrence": document.get("target_occurrence", 0),
                    "target_span": list(target_span), "core_span": list(structural.core_span),
                    "full_surface_span": list(structural.surface_span),
                    "full_identity": structural.full_identity, "relation": structural.relation,
                    "knowledge_document_id": knowledge["document_id"], "knowledge_text": knowledge["text"],
                    "knowledge_sha256": _sha(knowledge["text"]), "catalog_terms": deepcopy(terms),
                    "catalog_sha256": _digest(terms), "snapshot_id": snapshot.snapshot_id,
                    "candidates": candidates, "candidate_sha256": _digest(candidates),
                    "world_gold": authored, "expected_entity_id": entity_id,
                    "expected_answer": document["expected_answer"],
                    "gold": gold, "ambiguity": "resolvable" if authored["label"] == "LINK" else "nil",
                    "semantic_label": authored["label"],
                    "decisive_evidence": deepcopy(document["decisive_evidence"]),
                    "rationale": document["rationale"],
                })
    validate_cases(cases)
    return cases


def _path_from_dict(value):
    features = dict(value)
    unknown = set(features) - {field.name for field in fields(StructuralPath)}
    if unknown:
        raise ValueError("unknown structural path fields")
    for key in ("core_span", "token_span", "particles", "residual_parts", "residual_classes", "prefix_span"):
        if key in features and features[key] is not None:
            features[key] = tuple(features[key])
    return StructuralPath(**features)


def hypotheses(case, budget=None):
    """Reconstruct frozen hypotheses; never prune a two-candidate family."""
    if budget is not None and budget < len(case["candidates"]):
        raise ValueError("candidate budget cannot remove a fixed family candidate")
    return [LinkingHypothesis(_path_from_dict(candidate["path"]), candidate["entity_id"],
                              candidate["profile"], candidate["channel"], candidate["transform_cost"])
            for candidate in case["candidates"]]


def validate_cases(cases):
    """Check frozen identity, full-source spans, candidate completeness and gold."""
    if not isinstance(cases, list) or len(cases) != 64:
        raise ValueError("all 64 original documents must be retained")
    seen, groups, family_catalogs, family_knowledge = set(), {}, {}, {}
    for case in cases:
        if case["protocol_version"] != VERSION or case["source_collection"] not in FIXTURES:
            raise ValueError("wrong corpus protocol or source collection")
        if case["case_id"] != case["document_id"] or case["document_id"] in seen:
            raise ValueError("stable unique document identities required")
        seen.add(case["document_id"])
        family_id = case["family_id"]
        if case["split"] != family_split(family_id):
            raise ValueError("family split cannot be changed after freezing")
        groups.setdefault((case["source_collection"], family_id), []).append(case)
        if case["annotation_origin"] != "AI_AUTHORED_SYNTHETIC" or case["human_verified"] is not False:
            raise ValueError("AI authorship disclosure required")
        if case.get("evaluation_history") != "Previously inspected and evaluated synthetic documents; not an independent sealed real-world audit.":
            raise ValueError("previously evaluated synthetic-data limitation must be disclosed")
        text, target = case["text"], case["target_surface"]
        if case["source_text"] != text or case["document_sha256"] != _sha(text):
            raise ValueError("original source hash mismatch")
        start, end = case["target_span"]
        if not 0 <= start < end <= len(text) or text[start:end] != target:
            raise ValueError("target offset mismatch")
        positions = [i for i in range(len(text)) if text.startswith(target, i)]
        if positions[case["target_occurrence"]] != start:
            raise ValueError("designated occurrence changed")
        terms = case["catalog_terms"]
        if len(terms) != 2 or case["catalog_sha256"] != _digest(terms):
            raise ValueError("fixed catalog hash mismatch")
        if family_id in family_catalogs and family_catalogs[family_id] != terms:
            raise ValueError("all family documents must share the same glossary")
        family_catalogs[family_id] = terms
        candidates = case["candidates"]
        if case["candidate_sha256"] != _digest(candidates):
            raise ValueError("fixed candidate hash mismatch")
        if [c["entity_id"] for c in candidates] != ["global:" + t["key"] for t in terms]:
            raise ValueError("candidate set or ordering differs from the complete registered catalog")
        compiled = compile_simple_terms({"terms": terms}, scope="global", glossary_id=family_id)
        snapshot = compile_snapshot(load_glossary(compiled), run_conformance=False, tenant_id=family_id)
        structural = _structural_path(text, (start, end), terms, snapshot)
        for candidate, term in zip(candidates, terms):
            if (candidate["profile"] != _profile(term) or candidate["canonical"] != term["canonical"]
                    or candidate["aliases"] != term["surfaces"]
                    or candidate["short_definition"] != term["short_definition"]):
                raise ValueError("candidate profile must contain the unchanged registered term")
            if _path_from_dict(candidate["path"]) != structural or candidate["channel"] != "abbrev":
                raise ValueError("candidate must preserve the actual shared structural path and guard channel")
            if candidate["transform_cost"] != 0.0:
                raise ValueError("catalog candidate transform cost must be fixed")
        if (case["core_span"] != list(structural.core_span)
                or case["full_surface_span"] != list(structural.surface_span)
                or case["full_identity"] != structural.full_identity or case["relation"] != structural.relation):
            raise ValueError("core/full-surface contract differs from typed segmentation")
        if case["knowledge_sha256"] != _sha(case["knowledge_text"]):
            raise ValueError("original knowledge hash mismatch")
        knowledge_identity = (case["knowledge_document_id"], case["knowledge_text"])
        if family_id in family_knowledge and family_knowledge[family_id] != knowledge_identity:
            raise ValueError("all family documents must share the unchanged knowledge memo")
        family_knowledge[family_id] = knowledge_identity
        authored = case["world_gold"]
        label = authored["label"]
        entity_id = authored.get("entity_ref")
        if label not in LABELS or case["semantic_label"] != label or case["expected_entity_id"] != entity_id:
            raise ValueError("authored semantic label mismatch")
        if label == "LINK":
            selected = next((c for c in candidates if c["entity_id"] == entity_id), None)
            expected_gold = [{"entity_id": entity_id, "core_span": list(structural.core_span),
                              "full_identity": structural.full_identity}]
            if selected is None or case["expected_answer"] != selected["short_definition"]:
                raise ValueError("positive gold must reference a registered exact definition")
            if case["gold"] != expected_gold or case["ambiguity"] != "resolvable":
                raise ValueError("positive ranking identity mismatch")
        elif entity_id is not None or case["expected_answer"] is not None or case["gold"] or case["ambiguity"] != "nil":
            raise ValueError("all semantic negative cases require abstention, including genuine ambiguity")
        for evidence in case["decisive_evidence"]:
            original = text if evidence["document"] == "source" else case["knowledge_text"]
            if evidence["document"] not in {"source", "knowledge"} or not evidence["quote"] or evidence["quote"] not in original:
                raise ValueError("annotation evidence must remain a verbatim original quote")
    if len(groups) != 16 or any(len(group) != 4 for group in groups.values()):
        raise ValueError("four documents per family per source collection required")
    return cases


def load_cases(path):
    """Load JSONL frozen cases without rereading mutable source fixtures."""
    cases = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return validate_cases(cases)
