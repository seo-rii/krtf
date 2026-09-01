"""Confusion glossaries — negatives that look like the answer.

``run_wild``'s fake glossary asks whether the resolver invents entities out
of unrelated text. It answers yes/no on a question the resolver finds easy:
the fake names share no morphemes with anything the corpus says, so a zero
there means "no gross hallucination", not "picks the right one of two".

Real glossaries fail differently. `한국전력공사` and `한국전략공사` differ by
one 중성; two organisations abbreviate to the same two syllables; a longer
registered name contains a shorter one. Those are the errors a terminology
owner actually reports, and none of them are reachable from a glossary of
invented strangers.

This module builds the negatives that *are* reachable, each anchored to a
real registered entity so a wrong answer is a wrong **entity**, not a
hallucinated one:

``near_miss``
    one 중성 away from a registered full name. Verified absent from the
    corpus, so any commit of it is a false positive by construction — and
    the fuzzy channel is built to reach exactly this distance.
``abbrev_collision``
    a decoy that registers the *same* abbreviation as a real entity. The
    correct behaviour on a real occurrence of that abbreviation changes:
    two senses now exist, so a confident commit of either is an
    over-commit, and the prediction set must carry both (§2 invariant ④).
``prefix_extension``
    a decoy whose name begins with a registered surface (`한국전력` →
    `한국전력기술원`). Tests the boundary rule from the other side: a longer
    registered name must not swallow a mention of the shorter one.

Absence is checked in the space the matcher searches, not in the raw text —
``absent_bindings_only`` already carries that argument, and the same reason
applies here.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ktrf.hangul import compose_syllable, decompose_syllable

_VOWELS = "ㅏㅐㅑㅓㅔㅕㅗㅛㅜㅠㅡㅣ"
_EXTENSIONS = ("기술원", "서비스", "네트웍스", "홀딩스", "인터내셔널")


@dataclass
class ConfusionMeta:
    """What was planted, so the suites can score against it."""

    decoy_entities: set[str] = field(default_factory=set)
    near_miss: dict[str, str] = field(default_factory=dict)      # decoy -> real eid
    collisions: dict[str, list[str]] = field(default_factory=dict)  # abbrev -> eids
    prefix_ext: dict[str, str] = field(default_factory=dict)     # decoy -> real eid
    decoy_surfaces: dict[str, str] = field(default_factory=dict)  # surface -> decoy eid


def _all_hangul(s: str) -> bool:
    return bool(s) and all("가" <= c <= "힣" for c in s)


def _one_vowel_away(name: str, rng: random.Random, taken: set[str]) -> str | None:
    idxs = [i for i, c in enumerate(name) if decompose_syllable(c)]
    for i in rng.sample(idxs, len(idxs)) if idxs else ():
        cho, jung, jong = decompose_syllable(name[i])
        for v in rng.sample(_VOWELS, len(_VOWELS)):
            if v == jung:
                continue
            ch = compose_syllable(cho, v, jong)
            cand = name[:i] + ch + name[i + 1:] if ch else None
            if cand and cand not in taken:
                return cand
    return None


def build_confusion_glossary(base: dict, corpus_texts, seed: int = 20260901,
                             near_miss_n: int = 60, collision_n: int = 25,
                             prefix_n: int = 25) -> tuple[dict, ConfusionMeta]:
    """Return ``base`` extended with decoys, plus what was planted.

    ``base`` is not mutated. Decoys carry their own entity ids, so silver
    scoring against the real glossary keeps working unchanged and every
    decoy commit is attributable.
    """
    from .synthetic import absent_bindings_only

    rng = random.Random(seed)
    meta = ConfusionMeta()
    # A decoy anchored to a term the corpus never says can never be tested:
    # nothing will ever sit next to it. Anchor by observed frequency so the
    # suite spends its decoy budget where the confusion can actually happen.
    joined = chr(10).join(corpus_texts)
    freq: dict[str, int] = {}
    g = {k: (list(v) if isinstance(v, list) else v) for k, v in base.items()}
    g["glossary_id"] = f"{base['glossary_id']}-confusion-s{seed}"
    entities = list(g["entities"])
    families = list(g["alias_families"])
    bindings = list(g["alias_bindings"])

    taken = {b["surface"] for b in bindings}
    by_entity: dict[str, list[dict]] = {}
    for b in bindings:
        by_entity.setdefault(b["entity_id"], []).append(b)

    def add(eid: str, canonical: str, desc: str, surfaces, kinds):
        entities.append({"entity_id": eid, "canonical": canonical,
                         "description": desc, "domain_ids": ["DECOY"]})
        for n, (surface, kind) in enumerate(zip(surfaces, kinds)):
            fid = f"F_{eid}_{n}"
            families.append({"family_id": fid, "representative": surface,
                             "normalization_profile": "korean_org_name"})
            bindings.append({"alias_id": f"A_{eid}_{n}", "family_id": fid,
                             "entity_id": eid, "surface": surface,
                             "kind": kind,
                             "boundary_policy": {"left": "hangul_token_boundary"}})
            taken.add(surface)
            meta.decoy_surfaces[surface] = eid
        meta.decoy_entities.add(eid)

    # --- near miss: one 중성 from a registered full name -------------------
    names = [(b["entity_id"], b["surface"]) for b in bindings
             if b.get("kind") == "name" and _all_hangul(b["surface"])
             and len(b["surface"]) >= 4]
    rng.shuffle(names)
    for _, n in names:
        freq[n] = joined.count(n)
    names.sort(key=lambda en: -freq.get(en[1], 0))
    for real_eid, name in names[:near_miss_n]:
        decoy = _one_vowel_away(name, rng, taken)
        if decoy is None:
            continue
        eid = f"DECOY_NM_{len(meta.near_miss):03d}"
        add(eid, decoy, f"{decoy} — 근접 표면형 대조군", [decoy], ["name"])
        meta.near_miss[decoy] = real_eid

    # --- abbreviation collision: the same short surface, two senses --------
    abbrevs = [(b["entity_id"], b["surface"]) for b in bindings
               if b.get("kind") == "abbreviation" and _all_hangul(b["surface"])
               and b["entity_id"] not in meta.decoy_entities]
    rng.shuffle(abbrevs)
    for _, a in abbrevs:
        freq[a] = joined.count(a)
    abbrevs.sort(key=lambda en: -freq.get(en[1], 0))
    for real_eid, ab in abbrevs[:collision_n]:
        if ab in meta.collisions:
            continue
        # the decoy needs a full name of its own, absent from the corpus,
        # that plausibly abbreviates to `ab`
        full = ab[0] + "성" + ab[1:] + "협동조합"
        if full in taken:
            continue
        eid = f"DECOY_AB_{len(meta.collisions):03d}"
        add(eid, full, f"{full} — 약칭 충돌 대조군", [full, ab],
            ["name", "abbreviation"])
        meta.collisions[ab] = [real_eid, eid]

    # --- prefix extension: a longer registered name over a shorter one -----
    made = 0
    for real_eid, name in names:
        if made >= prefix_n:
            break
        decoy = name + rng.choice(_EXTENSIONS)
        if decoy in taken:
            continue
        eid = f"DECOY_PX_{made:03d}"
        add(eid, decoy, f"{decoy} — 접두 확장 대조군", [decoy], ["name"])
        meta.prefix_ext[decoy] = real_eid
        made += 1

    g["entities"], g["alias_families"], g["alias_bindings"] = (
        entities, families, bindings)

    # Every decoy must be unreachable in the corpus, or a "false positive"
    # would only mean the decoy was real after all. Filter the decoys, keep
    # the base bindings — those are supposed to occur.
    decoy_only = {k: v for k, v in g.items()}
    decoy_only["alias_bindings"] = [b for b in bindings
                                    if b["entity_id"] in meta.decoy_entities]
    decoy_only["alias_families"] = list(families)
    kept, removed = absent_bindings_only(decoy_only, corpus_texts)
    survivors = {b["surface"] for b in kept["alias_bindings"]}
    # a collision abbreviation is *meant* to occur — it is the real entity's
    # surface — so it is exempt from the absence rule
    survivors |= set(meta.collisions)
    g["alias_bindings"] = [b for b in bindings
                           if b["entity_id"] not in meta.decoy_entities
                           or b["surface"] in survivors]
    live = {b["entity_id"] for b in g["alias_bindings"]}
    g["entities"] = [e for e in entities
                     if e["entity_id"] not in meta.decoy_entities
                     or e["entity_id"] in live]
    kept_fids = {b["family_id"] for b in g["alias_bindings"]}
    g["alias_families"] = [f for f in families if f["family_id"] in kept_fids]
    meta.decoy_surfaces = {s: e for s, e in meta.decoy_surfaces.items()
                           if s in survivors}
    meta.near_miss = {d: e for d, e in meta.near_miss.items() if d in survivors}
    meta.prefix_ext = {d: e for d, e in meta.prefix_ext.items() if d in survivors}
    meta.decoy_entities &= live
    return g, meta


def decoy_stats(meta: ConfusionMeta) -> dict:
    return {
        "decoy_entities": len(meta.decoy_entities),
        "near_miss": len(meta.near_miss),
        "abbrev_collisions": len(meta.collisions),
        "prefix_extensions": len(meta.prefix_ext),
    }
