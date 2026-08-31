"""Decision explanation for a single surface (PLAN_PI.md §7 ``ktrf_explain``).

Answers "why did this text resolve the way it did?" in terms a reviewer —
or an agent surfacing a `/terms explain` command — can act on: which
channels produced the candidate, which scope the winning term came from,
what the competing senses were, and, when nothing was committed, *which
threshold the evidence failed to clear*.

This is a read-only view over a normal ``resolve`` call; it never changes
resolver behaviour.
"""

from __future__ import annotations

from .glossary import Glossary
from .resolver import resolve
from .snapshot import Snapshot


def _entity_view(glossary: Glossary, entity_id: str) -> dict:
    ent = glossary.entity(entity_id)
    if ent is None:
        return {"entity_id": entity_id, "known": False}
    prov = ent.provenance or {}
    return {
        "entity_id": entity_id,
        "canonical": ent.canonical,
        "scope": prov.get("scope"),
        "source": prov.get("source"),
        "known": True,
    }


def _shadowed_for(glossary: Glossary, surface: str) -> list[str]:
    out: list[str] = []
    for b in glossary.alias_bindings:
        if b.surface == surface:
            out.extend((b.provenance or {}).get("shadows", []))
    return out


def _blocking_reason(mention: dict, policy) -> dict | None:
    """Why a non-RESOLVED mention stopped short of a commit."""
    link = mention.get("link_decision")
    if link == "RESOLVED":
        return None
    members = [m for m in mention.get("prediction_set", {}).get("members", [])
               if m.get("kind", "ENTITY") == "ENTITY"]
    top_p = members[0].get("calibrated_probability", 0.0) if members else 0.0
    second_p = (members[1].get("calibrated_probability", 0.0)
                if len(members) > 1 else 0.0)
    if mention.get("degraded"):
        return {"reason": "degraded_result",
                "detail": "candidate pool was truncated; commits are "
                          "withheld on degraded mentions"}
    if mention.get("mention_decision") != "TERM":
        return {"reason": "mention_not_term",
                "detail": "no exact/document-local evidence and the top "
                          "candidate stayed below the term threshold"}
    if link == "KB_MISSING":
        return {"reason": "kb_missing_dominates",
                "detail": "no registered sense cleared the context bar"}
    if not members:
        return {"reason": "no_candidates", "detail": "no sense survived"}
    if members[0].get("commit_blocked"):
        # a Level B guard withheld the commit even though the score cleared
        # the thresholds (VARIANTS_PLAN 2); say which invariant, because the
        # fix is a catalog edit, not a threshold change
        return {"reason": "guard_blocked",
                "guard": members[0]["commit_blocked"],
                "top_probability": top_p,
                "detail": "the top sense is supported only by evidence a "
                          "Level B invariant refuses to commit on"}
    if (top_p or 0) < policy.resolve_threshold:
        return {"reason": "below_resolve_threshold",
                "top_probability": top_p,
                "threshold": policy.resolve_threshold}
    margin = (top_p or 0) - (second_p or 0)
    if len(members) > 1 and margin < policy.margin_threshold:
        return {"reason": "insufficient_margin", "margin": round(margin, 4),
                "threshold": policy.margin_threshold,
                "detail": "two senses were too close to separate"}
    return {"reason": "ambiguous", "detail": "multiple senses retained"}


def explain_resolution(snapshot: Snapshot, text: str,
                       surface: str | None = None,
                       occurrence: int = 1, mode: str = "commit") -> dict:
    """Explain how ``text`` resolves, optionally for one surface only.

    ``occurrence`` selects the n-th match when a surface repeats.
    """
    resp = resolve(snapshot, text, mode=mode,
                   options={"return_all_mentions": True,
                            "max_prediction_set": 50,
                            "detect_unregistered_mentions": True})
    glossary = snapshot.glossary
    policy = snapshot.policy
    explanations = []
    seen = 0
    for m in resp["mentions"]:
        if surface is not None:
            if surface not in m["surface"] and m["surface"] not in surface:
                continue
            seen += 1
            if seen != occurrence:
                continue
        members = [x for x in m.get("prediction_set", {}).get("members", [])
                   if x.get("kind", "ENTITY") == "ENTITY"]
        channels = sorted(m.get("generation_channels", []))
        entry = {
            "surface": m["surface"],
            "span": m.get("span", {}).get("codepoint"),
            "mention_decision": m.get("mention_decision"),
            "link_decision": m.get("link_decision"),
            "evidence": {
                "channels": channels,
                "exact_alias": "exact" in channels or "normalized" in channels,
                "document_local": "doc_local" in channels,
                "fuzzy": bool({"jamo", "keyboard"} & set(channels)),
                "dense_retrieval": "dense" in channels,
                "abbreviation_alignment": "abbrev" in channels,
                "tail": m.get("tail"),
                # why a commit was withheld is often "the surface is wider
                # than the core", so the explanation has to show that pair
                "core_link": m.get("core_link"),
                "full_surface": m.get("full_surface"),
                "calibration_fallback": bool(
                    m.get("prediction_set", {}).get("calibration_fallback")),
                "prediction_set_truncated": bool(
                    m.get("prediction_set", {}).get("truncated")),
            },
            "candidates": [
                {**_entity_view(glossary, x["entity_id"]),
                 "calibrated_probability": x.get("calibrated_probability"),
                 "ranking_score": x.get("ranking_score"),
                 "channels": sorted(x.get("generation_channels", [])),
                 "retrieval_pass": x.get("retrieval_pass")}
                for x in members],
            "shadowed_entities": _shadowed_for(glossary, m["surface"]),
        }
        if m.get("link_decision") == "RESOLVED":
            entry["resolved"] = {
                **_entity_view(glossary,
                               m["resolved_entity"]["entity_id"]),
                "calibrated_probability":
                    m["resolved_entity"].get("calibrated_probability"),
            }
        else:
            entry["not_resolved_because"] = _blocking_reason(m, policy)
        explanations.append(entry)
        if surface is not None:
            break

    return {
        "snapshot": resp.get("snapshot", {}),
        "mode": mode,
        "query_surface": surface,
        "mentions": explanations,
        "found": bool(explanations),
    }


def lookup_surface(snapshot: Snapshot, surface: str) -> dict:
    """Dictionary lookup without any text context (``ktrf_lookup``)."""
    matches = []
    for b in snapshot.glossary.alias_bindings:
        if b.surface == surface:
            view = _entity_view(snapshot.glossary, b.entity_id)
            matches.append({**view, "alias_kind": b.kind,
                            "alias_id": b.alias_id,
                            "shadows": (b.provenance or {}).get("shadows", [])})
    return {"surface": surface, "matches": matches,
            "ambiguous": len({m["entity_id"] for m in matches}) > 1}
