"""Dictionary-conditioned training episodes (spec §36, §40.5).

An episode is a (mention context, entity profile, label) pair — the model
learns glossary-entry ↔ context compatibility, never fixed entity IDs
(§36.1). Two sources:

- :func:`episodes_from_corrections` — the production path: ACCEPTED
  corrections whose ``mention_state`` carries the prediction set. Same-
  surface competitors become hard negatives (§40.5).
- :func:`episodes_from_silver` — real-text silver labels (KLUE wild corpus ×
  real-org glossary), used for **pipeline validation only**: silver volume is
  far below the G2 training gate and carries no sense ambiguity.

Negative sampling prefers same-domain / lexically-near entities over random
(§36.3), seeded and deterministic.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ktrf.dense import entity_profile_text
from ktrf.glossary import Glossary


@dataclass
class Episode:
    context: str
    profile: str
    label: int
    source: str  # "correction" | "silver"


def _negatives(glossary: Glossary, gold_id: str, k: int,
               rng: random.Random) -> list[str]:
    gold = glossary.entity(gold_id)
    scored = []
    for e in glossary.entities:
        if e.entity_id == gold_id:
            continue
        score = 0
        if gold and set(e.domain_ids) & set(gold.domain_ids):
            score += 2  # same-domain distractor (§36.3)
        if gold and e.canonical[:1] == gold.canonical[:1]:
            score += 1  # lexically near
        scored.append((score, rng.random(), e.entity_id))
    scored.sort(reverse=True)
    return [eid for _, _, eid in scored[:k]]


def episodes_from_corrections(accepted: list[dict], glossary: Glossary,
                              context_of=None) -> list[Episode]:
    """ACCEPTED corrections -> episodes. ``context_of(request_ref)`` supplies
    the mention context window (§30.2: the store holds no raw text unless
    the tenant opted in; the caller resolves the reference)."""
    out: list[Episode] = []
    for c in accepted:
        if c.get("correction_type") not in ("WRONG_ENTITY", "SHOULD_BE_RESOLVED"):
            continue
        gold = (c.get("corrected") or {}).get("entity_id")
        state = c.get("mention_state") or {}
        context = (c.get("evidence_text")
                   or (context_of(c["request_ref"]) if context_of else None))
        if not gold or not context:
            continue
        members = [m.get("entity_id") for m in
                   state.get("prediction_set", {}).get("members", [])
                   if m.get("kind", "ENTITY") == "ENTITY"]
        gold_ent = glossary.entity(gold)
        if gold_ent is None:
            continue
        out.append(Episode(context, entity_profile_text(gold_ent), 1,
                           "correction"))
        # same-surface competitors are the hard negatives (§40.5)
        for eid in members:
            ent = glossary.entity(eid)
            if ent is not None and eid != gold:
                out.append(Episode(context, entity_profile_text(ent), 0,
                                   "correction"))
    return out


def episodes_from_silver(glossary: Glossary, corpus: list[dict],
                         negatives_per_positive: int = 3,
                         seed: int = 13) -> list[Episode]:
    """Real-text silver episodes (validation-scale; NOT the training gate)."""
    rng = random.Random(seed)
    alias_to_entity = {b.surface: b.entity_id for b in glossary.alias_bindings
                       if len(b.surface) >= 3}
    out: list[Episode] = []
    for row in corpus:
        text = row["text"]
        for surface, eid in alias_to_entity.items():
            i = text.find(surface)
            if i < 0:
                continue
            prev = text[i - 1] if i > 0 else ""
            if prev and ("가" <= prev <= "힣" or (prev.isascii() and prev.isalnum())):
                continue
            ent = glossary.entity(eid)
            if ent is None:
                continue
            out.append(Episode(text, entity_profile_text(ent), 1, "silver"))
            for neg in _negatives(glossary, eid, negatives_per_positive, rng):
                nent = glossary.entity(neg)
                out.append(Episode(text, entity_profile_text(nent), 0,
                                   "silver"))
            break
    return out
