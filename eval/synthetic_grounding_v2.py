"""Versioned contrast pairs and opaque IDs; the original v1 corpus stays frozen."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from eval.blind_gold import digest
from eval.synthetic_grounding import (
    EXPANSION_PROTOCOL, _source_entities, build_expanded_requests,
    corpus_manifest, load_families, validate_families,
)

CONTRAST_DIR = Path(__file__).parent / "fixtures" / "grounding_expansion_v2"
V1_SOURCE_SHA256 = "7a169f3caf1a4098fbb3a0947eac5793e71234f4725b895b49823e3288a679ec"
BALANCED_PROTOCOL = {
    **deepcopy(EXPANSION_PROTOCOL),
    "kind": "authored_synthetic_grounding_expansion_v2",
    "corpus_version": "v2",
    "v1_source_semantic_sha256": V1_SOURCE_SHA256,
    "entity_ids": "Scope is retained; all authored keys are deterministically replaced with opaque keys.",
    "contextual_balance": "Each contextual collision has two same-world documents, one gold for each candidate.",
    "minimal_card_order": "Status, opaque entity ID, then binding surface; independent of document and gold.",
    "full_pack_order": "Unchanged production context-pack order; a separate reference beyond the minimal 2x2.",
    "source_preservation": "Original documents and glossary meanings are retained; contrasts are additional documents.",
}


def balance_families(originals, contrasts):
    """Validate authored pairs, then replace ID keys without consulting a resolver."""
    families = deepcopy(originals)
    validate_families(families)
    by_family = {family["family_id"]: family for family in families}
    expected = {case["case_id"]: (family, case) for family in families
                for case in family["cases"] if case["stratum"] == "contextual_collision"}
    seen = set()
    for record in contrasts:
        if (record.get("annotation_origin") != "AI_SYNTHETIC" or
                record.get("human_verified") is not False or not record.get("authored_by")):
            raise ValueError("contrast authorship and human verification status required")
        source_id = record["source_case_id"]
        if source_id not in expected or source_id in seen:
            raise ValueError("unknown or duplicate contextual contrast source")
        family, original = expected[source_id]
        if record["family_id"] != family["family_id"]:
            raise ValueError("contrast must retain its source family")
        contrast = deepcopy(record["case"])
        if (contrast["case_id"] != source_id + "-contrast" or
                contrast["world"] != original["world"] or
                contrast["target_surface"] != original["target_surface"] or
                contrast["stratum"] != "contextual_collision"):
            raise ValueError("contrast must retain source world, target and stratum")
        if contrast["text"] == original["text"]:
            raise ValueError("opposite referents need separately authored contexts")
        entities = _source_entities(family["worlds"][original["world"]])
        target = original["target_surface"]
        colliding = {eid for eid, term in entities.items()
                     if target in [term["canonical"], *term.get("surfaces", [])]}
        golds = {original["gold"].get("entity_ref"), contrast["gold"].get("entity_ref")}
        if (len(colliding) != 2 or golds != colliding or
                any(case["gold"]["label"] != "LINK" for case in (original, contrast))):
            raise ValueError("each contrast pair must select both same-world colliding entities")
        original.update(contrast_pair_id=source_id, contrast_member="original")
        contrast.update(contrast_pair_id=source_id, contrast_member="contrast",
                        authored_by=record["authored_by"])
        by_family[family["family_id"]]["cases"].append(contrast)
        seen.add(source_id)
    if seen != set(expected):
        raise ValueError("every original contextual collision needs exactly one contrast")
    validate_families(families, cases_per_family=None)

    id_map = {}
    for family in families:
        for world in family["worlds"].values():
            sources = ([('global', world["terms"])] if world["mode"] == "simple" else
                       [(layer["scope"], layer["terms"]) for layer in world["layers"]])
            for scope, terms in sources:
                for index, term in enumerate(terms):
                    source_id = scope + ":" + term["key"]
                    key = "e_" + hashlib.sha256(("ktrf-synthetic-v2\0" + family["family_id"] +
                                               "\0" + source_id).encode()).hexdigest()[:24]
                    id_map[(family["family_id"], source_id)] = scope + ":" + key
                    terms[index] = {**term, "key": key}
        family["entity_key_namespace"] = "opaque-v2"
        for case in family["cases"]:
            for field in ("entity_ref", "core_entity_ref"):
                if case["gold"].get(field) is not None:
                    case["gold"][field] = id_map[(family["family_id"], case["gold"][field])]
    if len(set(id_map.values())) != len(id_map):
        raise ValueError("opaque ID collision")
    validate_families(families, cases_per_family=None)
    return families


def load_balanced_families(directory=CONTRAST_DIR):
    originals = load_families()
    if digest(originals) != V1_SOURCE_SHA256:
        raise ValueError("v2 requires the frozen v1 source revision")
    paths = sorted(Path(directory).glob("*.jsonl"))
    if not paths:
        raise ValueError("no authored contrast fixtures")
    contrasts = [json.loads(line) for path in paths for line in path.read_text().splitlines() if line.strip()]
    return balance_families(originals, contrasts)


def build_balanced_requests(families=None):
    families = load_balanced_families() if families is None else deepcopy(families)
    rows = build_expanded_requests(families, cases_per_family=None, candidate_order="opaque_id")
    sources = {case["case_id"]: case for family in families for case in family["cases"]}
    pairs = defaultdict(list)
    for row in rows:
        case = sources[row["document_id"]]
        row["corpus_version"] = "v2"
        if "contrast_pair_id" in case:
            row["contrast_pair_id"] = case["contrast_pair_id"]
            row["contrast_member"] = case["contrast_member"]
            if row["condition"] == "original" and row["task"] == "document_qa":
                pairs[case["contrast_pair_id"]].append(row)
    for members in pairs.values():
        if (len(members) != 2 or members[0]["candidate_hash"] != members[1]["candidate_hash"] or
                len(members[0]["cards"]) != 2 or
                {card["status"] for card in members[0]["cards"]} != {"AMBIGUOUS"} or
                {row["expected_entity_id"] for row in members} !=
                {card["entity_id"] for card in members[0]["cards"]}):
            raise ValueError("paired contexts must retain the same two ambiguous cards and opposite golds")
    return rows


def balanced_corpus_manifest(families, rows):
    manifest = corpus_manifest(families, rows)
    v1_manifest_path = Path(__file__).parents[1] / "reports" / "SYNTHETIC_GROUNDING_CORPUS.json"
    v1_bytes = v1_manifest_path.read_bytes()
    v1 = json.loads(v1_bytes)
    if v1["source_semantic_sha256"] != V1_SOURCE_SHA256:
        raise ValueError("v2 partition lineage requires the frozen v1 manifest")
    assignments = {case["case_id"]: v1["partition_assignments"][case.get("contrast_pair_id", case["case_id"])]
                   for family in families for case in family["cases"]}
    pair_ids = {row["contrast_pair_id"] for row in rows if "contrast_pair_id" in row}
    manifest.update(protocol=BALANCED_PROTOCOL, corpus_version="v2",
                    contextual_pairs=len(pair_ids),
                    v1_source_semantic_sha256=V1_SOURCE_SHA256,
                    v1_manifest_sha256=hashlib.sha256(v1_bytes).hexdigest(),
                    partition_policy="Preserve v1 family assignments; new contrasts inherit their source partition.",
                    partition_assignments=assignments,
                    family_alias_connected_partitions=dict(Counter(assignments.values())))
    return manifest
