"""Authored synthetic documents with gold independent of resolver output.

Five input conditions: a fixed 2x2 surface/policy-field diagnostic, plus a
separate full context-pack reference. Family clusters are retained throughout.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from eval.blind_gold import digest, grouped_split
from eval.product_utility import grade_outputs, malformed_response_field
from ktrf.context import (CharTokenCounter, ContextPolicy, EXECUTION_POLICY,
                         prepare_llm_context, validate_llm_grounding)
from ktrf.glossary import load_glossary
from ktrf.registry.layers import TermLayer, compile_layered_snapshot
from ktrf.registry.simple_schema import compile_simple_terms
from ktrf.snapshot import compile_snapshot

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "grounding_expansion"
CONDITIONS = ("original", "surface_only", "schema_only", "both", "full_pack")
STRATA = {"exact", "particle", "multi_entity", "typo", "ambiguous",
          "contextual_collision", "glossary_swap", "project_override",
          "session_override", "untrusted_override", "derived_role",
          "compound_nonmention", "nil", "unicode_spacing"}
EXPANSION_PROTOCOL = {
    "kind": "authored_synthetic_grounding_expansion",
    "conditions": list(CONDITIONS), "selector": "ktrf", "policy": "evidence_only",
    "format": "structured", "gold_origin": "AI_SYNTHETIC", "human_verified": False,
    "gold_source": "Authored glossary worlds and document semantics; never resolver output.",
    "full_pack_is_separate_reference": True,
    "fixed": ["document", "question", "candidate_facts", "system_policy", "execution_guard"],
    "ordering": "Per-task rotating conditions; stateless serial calls.",
    "inference": {"temperature": 0, "seed": 0, "max_tokens": 128, "thinking": False},
    "limitations": ["Synthetic cases are not deployment traffic or independent human gold.",
                    "QA uses exact definitions; paraphrases need separate review.",
                    "The full-pack condition adds information and is not a factor-isolation cell.",
                    "All partitions are descriptive evaluations; no sealed risk test is claimed."],
}


def load_families(directory=FIXTURE_DIR):
    families = []
    paths = sorted(Path(directory).glob("*.jsonl"))
    if not paths:
        raise ValueError("no authored fixture files")
    for path in paths:
        families.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    validate_families(families)
    return families


def _source_entities(world):
    if world.get("mode") == "simple":
        sources = [("global", world["terms"])]
    elif world.get("mode") == "layered":
        sources = [(layer["scope"], layer["terms"]) for layer in world["layers"]
                   if layer.get("trusted", True)]
    else:
        raise ValueError("unknown glossary world mode")
    result = {}
    for scope, terms in sources:
        for term in terms:
            eid = f"{scope}:{term['key']}"
            if eid in result:
                raise ValueError("duplicate source entity ID")
            if not isinstance(term.get("short_definition"), str) or not term["short_definition"].strip():
                raise ValueError("each authored entity needs a definition")
            if len(term["short_definition"]) > 180:
                raise ValueError("definitions exceed the frozen context allowance")
            result[eid] = term
    return result


def _target_span(case):
    text, target = case["text"], case["target_surface"]
    if not isinstance(text, str) or not isinstance(target, str) or not target:
        raise ValueError("document text and nonempty target required")
    occurrence = case.get("target_occurrence", 0)
    if type(occurrence) is not int or occurrence < 0:
        raise ValueError("target occurrence must be a nonnegative integer")
    start = -1
    for _ in range(occurrence + 1):
        start = text.find(target, start + 1)
        if start < 0:
            raise ValueError("authored target is absent from the document")
    return [start, start + len(target)]


def validate_families(families):
    ids, case_ids = set(), set()
    for family in families:
        fid = family["family_id"]
        if not isinstance(fid, str) or not fid or fid in ids:
            raise ValueError("duplicate or invalid family ID")
        ids.add(fid)
        if (family.get("annotation_origin") != "AI_SYNTHETIC" or
                family.get("human_verified") is not False or not family.get("authored_by")):
            raise ValueError("explicit synthetic authorship and human verification status required")
        if not family.get("domain") or not family.get("worlds"):
            raise ValueError("domain and authored glossary worlds required")
        source = {name: _source_entities(world) for name, world in family["worlds"].items()}
        if len(family["worlds"]) < 2 or len(family["cases"]) != 4:
            raise ValueError("each family needs at least two worlds and four documents")
        for case in family["cases"]:
            if case["case_id"] in case_ids:
                raise ValueError("duplicate case ID")
            case_ids.add(case["case_id"])
            if not case["case_id"].startswith(fid + ":"):
                raise ValueError("case must retain its source family ID")
            if case["world"] not in source or case["stratum"] not in STRATA:
                raise ValueError("unknown case world or stratum")
            _target_span(case)
            gold = case["gold"]
            if gold["label"] not in {"LINK", "NIL", "AMBIGUOUS", "NON_MENTION"}:
                raise ValueError("unknown semantic gold label")
            if gold.get("full_identity") not in {"SAME", "DISTINCT", "JUXTAPOSED"}:
                raise ValueError("full-surface identity required")
            if gold["label"] == "LINK":
                if gold.get("entity_ref") not in source[case["world"]]:
                    raise ValueError("gold LINK must refer to the authored world")
                if gold["full_identity"] != "SAME":
                    raise ValueError("whole-target LINK cannot borrow a derived component ID")
            elif gold.get("entity_ref") is not None:
                raise ValueError("only LINK can have a target entity ID")
            if gold.get("core_surface") is not None:
                if gold["core_surface"] not in case["target_surface"]:
                    raise ValueError("core must be inside the target surface")
                if gold.get("core_entity_ref") not in source[case["world"]]:
                    raise ValueError("core ID must belong to the authored world")
            if not case.get("rationale"):
                raise ValueError("authored semantic rationale required")


def _snapshot(family, world_name):
    world = family["worlds"][world_name]
    name = family["family_id"] + ":" + world_name
    if world["mode"] == "simple":
        compiled = compile_simple_terms({"terms": world["terms"]}, scope="global", glossary_id=name)
        return compile_snapshot(load_glossary(compiled), run_conformance=False,
                                tenant_id=family["family_id"])
    layers = [TermLayer(layer["scope"], {"terms": layer["terms"]},
                        trusted=layer.get("trusted", True)) for layer in world["layers"]]
    snap, _ = compile_layered_snapshot(layers, glossary_id=name,
        tenant_id=family["family_id"], strict_conflicts=True, run_conformance=False)
    return snap


def _binding_cards(pack):
    cards = []
    for term in pack["resolved_terms"]:
        for surface in sorted({m["surface"] for m in term["mentions"]}):
            cards.append({"entity_id": term["entity_id"], "canonical": term["canonical"],
                          "definition": term["short_definition"], "status": "RESOLVED",
                          "binding_surface": surface})
    for mention in pack["ambiguous_mentions"]:
        for term in mention["candidates"]:
            cards.append({"entity_id": term["entity_id"], "canonical": term["canonical"],
                          "definition": term["short_definition"], "status": "AMBIGUOUS",
                          "binding_surface": mention["surface"]})
    # Repeated mentions must not inflate identical candidate cards.
    return list({digest(c): c for c in cards}.values())


def build_expanded_requests(families=None):
    families = load_families() if families is None else deepcopy(families)
    validate_families(families)
    rows, task_counts = [], Counter()
    for family in families:
        snapshots = {name: _snapshot(family, name) for name in family["worlds"]}
        definitions = {name: _source_entities(world) for name, world in family["worlds"].items()}
        for case in family["cases"]:
            target, span, gold = case["target_surface"], _target_span(case), case["gold"]
            snap = snapshots[case["world"]]
            eid = gold.get("entity_ref")
            if eid and snap.glossary.entity(eid) is None:
                raise ValueError("authored LINK refers to an inactive glossary entity")
            prepared = prepare_llm_context(snap, case["text"], query=target,
                context_policy=ContextPolicy(max_tokens=6000, max_entities=12,
                                              max_candidates_per_mention=6))
            pack = prepared.context_pack
            binding_cards = _binding_cards(pack)
            if len(binding_cards) > 24:
                raise ValueError("input cards exceed the declared allowance; never silently truncate")
            cards = [{k: v for k, v in c.items() if k != "binding_surface"} for c in binding_cards]
            authorized = {c["entity_id"] for c in pack["resolved_terms"]
                          if not c["resolution"].get("degraded") and
                          any(m["surface"] == target for m in c["mentions"])}
            allowed_id = next(iter(authorized)) if len(authorized) == 1 else None
            answer = definitions[case["world"]][eid]["short_definition"] if eid else None
            for task in ("document_qa", "structured_routing"):
                question = ("사전에 등록된 이 전체 표현의 현행 정의를 answer에 반환하라."
                            if task == "document_qa" else
                            "이 전체 표현에 대해 검증된 담당 대상 entity_id를 반환하라.")
                prompt = (f"문서: {case['text']}\n대상 전체 표현: {target}\n"
                          f"대상 codepoint span: [{span[0]}, {span[1]}]\n질문: {question}\n"
                          "다른 표현의 정의나 ID를 대신 반환하지 않는다. 대상 연결을 확정할 수 없으면 null.\n"
                          'JSON {"answer": string|null, "entity_id": string|null}.')
                common = {"case_id": case["case_id"] + ":" + task,
                    "document_id": case["case_id"], "family_id": family["family_id"],
                    "domain": family["domain"], "stratum": case["stratum"],
                    "world": family["family_id"] + ":" + case["world"], "task": task,
                    "text": case["text"], "target_surface": target, "target_span": span,
                    "document_sha256": hashlib.sha256(case["text"].encode()).hexdigest(),
                    "gold": gold, "expected_entity_id": eid, "expected_answer": answer,
                    "pack": pack, "cards": cards, "snapshot_id": snap.snapshot_id,
                    "resolver_authorized_entity_id": allowed_id,
                    "gold_entity_in_candidates": bool(eid and any(c["entity_id"] == eid and
                        c["binding_surface"] == target for c in binding_cards)),
                    "candidate_hash": digest(cards), "binding_hash": digest(binding_cards),
                    "system": EXECUTION_POLICY + "답변도 제공된 근거에만 의존한다."}
                offset = task_counts[task] % len(CONDITIONS)
                task_counts[task] += 1
                for position, condition in enumerate(CONDITIONS[offset:] + CONDITIONS[:offset]):
                    surface = condition in ("surface_only", "both")
                    schema = condition in ("schema_only", "both")
                    rendered_cards = [dict(c, **({"surface": b["binding_surface"]} if surface else {}))
                                      for c, b in zip(cards, binding_cards)]
                    if condition == "full_pack":
                        data = {"terminology_context": pack}
                    elif schema:
                        ambiguous = [c for c in rendered_cards if c["status"] == "AMBIGUOUS"]
                        data = {"resolved_terms": [c for c in rendered_cards if c["status"] == "RESOLVED"],
                                "ambiguous_mentions": [{"candidates": ambiguous}] if ambiguous else []}
                    else:
                        data = {"terminology_data": rendered_cards}
                    row = deepcopy(common)
                    row.update(condition=condition, condition_position=position,
                               factors={"surface_binding": surface, "policy_named_fields": schema},
                               user=json.dumps(data, ensure_ascii=False) + "\n" + prompt)
                    row["estimated_input_tokens"] = CharTokenCounter().count(row["user"] + row["system"])
                    rows.append(row)
    return rows


def grade_expanded_outputs(requests, outputs):
    """End-to-end semantic gold and execution authorization stay separate."""
    requests, outputs = list(requests), list(outputs)
    result = grade_outputs(requests, outputs)
    known = {(r["case_id"], r["condition"]): r for r in requests}
    observations = defaultdict(list)
    for output in outputs:
        row = known[(output["case_id"], output["condition"])]
        field = "answer" if row["task"] == "document_qa" else "entity_id"
        expected = row["expected_answer"] if field == "answer" else row["expected_entity_id"]
        response = output["response"]
        raw = response.get(field)
        malformed = malformed_response_field(response, field)
        valid = validate_llm_grounding({"selections": [{"surface": row["target_surface"],
            "entity_id": None if malformed else raw}]}, row["pack"], purpose="execution")["valid"] if field == "entity_id" else True
        observations[row["condition"]].append({"row": row, "correct": not malformed and raw == expected and valid,
            "semantic_match": not malformed and raw == expected, "malformed": malformed,
            "abstained": not malformed and raw is None, "valid": valid,
            "wrong_id": field == "entity_id" and not malformed and raw is not None and raw != expected,
            "nonnull_id": field == "entity_id" and not malformed and raw is not None})

    def summarize(items):
        positives = [x for x in items if x["row"]["expected_entity_id"] is not None]
        return {"observed": len(items), "success": sum(x["correct"] for x in items),
            "semantic_match": sum(x["semantic_match"] for x in items),
            "answerable": len(positives), "answerable_success": sum(x["correct"] for x in positives),
            "over_abstention": sum(x["abstained"] for x in positives),
            "safe_abstention": sum(x["abstained"] and x["row"]["expected_entity_id"] is None for x in items),
            "wrong_ids": sum(x["wrong_id"] for x in items),
            "guard_rejections": sum(x["nonnull_id"] and not x["valid"] for x in items),
            "accepted_unauthorized_ids": sum(x["wrong_id"] and x["valid"] for x in items),
            "malformed": sum(x["malformed"] for x in items)}

    details = {}
    for condition in sorted({r["condition"] for r in requests}):
        items = observations[condition]
        strata = {r["stratum"] for r in requests}
        families = sorted({r["family_id"] for r in requests})
        per_family = [summarize([x for x in items if x["row"]["family_id"] == fid]) for fid in families]
        observed_families = [x for x in per_family if x["observed"]]
        details[condition] = {"overall": summarize(items),
            "by_task": {task: summarize([x for x in items if x["row"]["task"] == task])
                        for task in ("document_qa", "structured_routing")},
            "by_stratum": {s: summarize([x for x in items if x["row"]["stratum"] == s]) for s in sorted(strata)},
            "family_macro_success": (sum(x["success"] / x["observed"] for x in observed_families)
                                     / len(observed_families)) if observed_families else None,
            "families_observed": len(observed_families)}
    result["expanded_diagnostics"] = details
    result["limitations"] += ["Authored semantic gold is independent of resolver output, but AI synthetic.",
                               "Routing success requires both semantic correctness and the unchanged execution gate."]
    return result


def corpus_manifest(families, rows):
    documents, aliases = [], Counter()
    source_revision = digest(families)
    for family in families:
        family_aliases = {s.casefold() for world in family["worlds"].values()
                          for term in _source_entities(world).values()
                          for s in [term["canonical"], *term.get("surfaces", [])]}
        aliases.update(family_aliases)
        for case in family["cases"]:
            documents.append({"document_id": case["case_id"], "parent_document_id": family["family_id"],
                "source_row_id": case["case_id"], "dataset_revision": source_revision,
                "collected_at": "AI_AUTHORED_SYNTHETIC", "text": case["text"],
                "document_sha256": hashlib.sha256(case["text"].encode()).hexdigest(),
                "family_ids": [family["family_id"], *("alias:" + s for s in sorted(family_aliases))]})
    assignments = grouped_split(documents, seed="synthetic-grounding-expansion-v1")
    unique_rows = [r for r in rows if r["condition"] == "original"]
    unique_docs = [r for r in unique_rows if r["task"] == "document_qa"]
    return {"status": "SYNTHETIC_CORPUS_VALIDATED", "annotation_origin": "AI_SYNTHETIC",
        "human_verified": False, "protocol": EXPANSION_PROTOCOL, "families": len(families),
        "documents": len(documents), "unique_document_hashes": len({d["document_sha256"] for d in documents}),
        "glossary_worlds": sum(len(f["worlds"]) for f in families), "task_cases": len(unique_rows),
        "model_requests": len(rows), "gold_labels": dict(Counter(r["gold"]["label"] for r in unique_docs)),
        "strata": dict(sorted(Counter(r["stratum"] for r in unique_docs).items())),
        "shared_aliases_across_families": sum(n > 1 for n in aliases.values()),
        "family_alias_connected_partitions": dict(Counter(assignments.values())),
        "partition_assignments": assignments, "source_semantic_sha256": digest(families),
        "requests_sha256": hashlib.sha256(b"".join((json.dumps(r, ensure_ascii=False, sort_keys=True)+"\n").encode() for r in rows)).hexdigest(),
        "resolver_pipeline": {"gold_LINK_documents": sum(r["expected_entity_id"] is not None for r in unique_docs),
            "gold_entity_in_target_candidates": sum(r["gold_entity_in_candidates"] for r in unique_docs),
            "correct_target_authorizations": sum(r["expected_entity_id"] is not None and r["resolver_authorized_entity_id"] == r["expected_entity_id"] for r in unique_docs),
            "nonnull_authorizations_for_negative_gold": sum(r["expected_entity_id"] is None and r["resolver_authorized_entity_id"] is not None for r in unique_docs)},
        "quality_claim": False}
