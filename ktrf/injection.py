"""Terminology injection payload rendering (spec §49.2, §47.7).

Builds the ``<resolved_terms>`` block that downstream RAG/LLM integrations
embed in prompts. Every attribute value is XML-escaped and descriptions are
length-capped before insertion; raw string interpolation and CDATA are
forbidden (REQ-SEC-001). AMBIGUOUS mentions emit their prediction set (top-k)
— never a single forced canonical (§49.2).

.. note:: Legacy renderer. New integrations should use
   :mod:`ktrf.context` (``prepare_llm_context`` / ``build_context_pack``),
   which separates RESOLVED facts from AMBIGUOUS candidates structurally,
   deduplicates entities, applies a hard token budget with omission
   metadata, and ships a fixed terminology policy fragment.
"""

from __future__ import annotations

from xml.sax.saxutils import quoteattr

from .glossary import Glossary

MAX_DESCRIPTION_CHARS = 200


def _attr(value) -> str:
    # quoteattr escapes <>&" and never emits CDATA
    return quoteattr("" if value is None else str(value))


def render_resolved_terms(response: dict, glossary: Glossary,
                          top_k: int = 3) -> str:
    snap = response.get("snapshot", {})
    header = f"{snap.get('glossary_id')}:{snap.get('glossary_version')}"
    lines = [f"<resolved_terms snapshot={_attr(header)}>"]
    for m in response.get("mentions", []):
        surface = m.get("surface", "")
        if m.get("link_decision") == "RESOLVED":
            members = [{
                "entity_id": m["resolved_entity"]["entity_id"],
                "calibrated_probability":
                    m["resolved_entity"].get("calibrated_probability"),
            }]
        else:
            members = [x for x in m.get("prediction_set", {}).get("members", [])
                       if x.get("kind", "ENTITY") == "ENTITY"][:top_k]
        for member in members:
            entity = glossary.entity(member["entity_id"])
            if entity is None:
                continue
            desc = (entity.description or "")[:MAX_DESCRIPTION_CHARS]
            attrs = [
                f"surface={_attr(surface)}",
                f"entity_id={_attr(entity.entity_id)}",
                f"canonical={_attr(entity.canonical)}",
            ]
            p = member.get("calibrated_probability")
            if p is not None:
                attrs.append(f"probability={_attr(p)}")
            attrs.append(f"link_decision={_attr(m.get('link_decision'))}")
            attrs.append(f"description={_attr(desc)}")
            lines.append(f"  <term {' '.join(attrs)} />")
    lines.append("</resolved_terms>")
    return "\n".join(lines)
