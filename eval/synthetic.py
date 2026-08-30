"""Synthetic glossary generation with controlled adversarial structure.

Unlike the demo glossary (8 bindings), these glossaries are built to stress
the properties that a small example can hide:

- **natural abbreviation collisions**: 한국전력공사 and 한국전자공단 both
  abbreviate to 한전 → multi-sense aliases at scale;
- **near-miss siblings**: full names differing in exactly one syllable
  (전력 vs 전략) → fuzzy channel precision stress;
- **nested extensions**: base org + suffix as a *separate* entity
  (한국전력공사연구원) → overlapping mention stress;
- **Latin acronym reuse**: small acronym alphabet forces multi-sense.

Everything is seeded and deterministic.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

_PRE = ["한국", "대한", "국가", "중앙", "지역", "미래", "국제", "동부", "서부",
        "남부", "북부", "수도", "글로벌", "차세대", "통합", "광역", "신규",
        "공공", "민간", "종합"]
_MID = ["전력", "전략", "정보", "정밀", "기술", "기계", "도로", "도시", "철도",
        "환경", "안전", "금융", "데이터", "품질", "에너지", "통신", "보안",
        "물류", "재난", "자원", "해양", "항공", "우주", "바이오", "화학",
        "전자", "소재", "관광", "문화", "교육"]
_ORG = ["공사", "공단", "연구원", "진흥원", "협회", "위원회", "재단", "센터"]
_EXT = ["연구소", "사무국", "지사"]


@dataclass
class SynthMeta:
    """What the generator planted — used by adversarial suites."""

    hangul_abbrevs: dict[str, list[str]] = field(default_factory=dict)  # abbrev -> entity_ids
    full_names: dict[str, str] = field(default_factory=dict)  # name -> entity_id
    acronyms: dict[str, list[str]] = field(default_factory=dict)
    near_miss_pairs: list[tuple[str, str]] = field(default_factory=list)  # (name_a, name_b)
    nested_pairs: list[tuple[str, str]] = field(default_factory=list)  # (base, extended)
    all_surfaces: set[str] = field(default_factory=set)


def build_synthetic_glossary(
    n_entities: int,
    seed: int = 1,
    near_miss_rate: float = 0.15,
    nested_rate: float = 0.10,
    acronym_rate: float = 0.30,
) -> tuple[dict, SynthMeta]:
    rng = random.Random(seed)
    meta = SynthMeta()
    entities, families, bindings = [], [], []

    def add_binding(eid, surface, profile, kind="alias", left=None):
        fid = f"F_{eid}_{len(bindings)}"
        families.append({"family_id": fid, "representative": surface,
                         "normalization_profile": profile})
        b = {"alias_id": f"A_{eid}_{len(bindings)}", "family_id": fid,
             "entity_id": eid, "surface": surface, "kind": kind}
        if left:
            b["boundary_policy"] = {"left": left,
                                    "right": "particle_or_token_boundary"}
        bindings.append(b)
        meta.all_surfaces.add(surface)

    def add_entity(eid, name, desc, domains):
        entities.append({"entity_id": eid, "canonical": name,
                         "description": desc, "domain_ids": domains})

    used_names: set[str] = set()
    combos = [(p, m, o) for p in _PRE for m in _MID for o in _ORG]
    rng.shuffle(combos)
    i = 0
    while len(entities) < n_entities and i < len(combos):
        p, m, o = combos[i]
        i += 1
        name = p + m + o
        if name in used_names:
            continue
        used_names.add(name)
        eid = f"E{len(entities):05d}"
        add_entity(eid, name, f"{p} 지역의 {m} 분야 {o} 조직", [m])
        add_binding(eid, name, "korean_org_name", kind="name",
                    left="hangul_token_boundary")
        meta.full_names[name] = eid

        # natural 2-syllable abbreviation: 한국전력공사 -> 한전
        abbrev = p[0] + m[0]
        add_binding(eid, abbrev, "korean_org_name", kind="abbreviation",
                    left="hangul_token_boundary")
        meta.hangul_abbrevs.setdefault(abbrev, []).append(eid)

        # Latin acronym from a deliberately small alphabet -> collisions
        if rng.random() < acronym_rate:
            acr = "".join(rng.choice("ABCDEFGHKMPQS")
                          for _ in range(rng.choice((2, 3, 3))))
            add_binding(eid, acr, "latin_acronym", kind="abbreviation",
                        left="latin_token_boundary")
            meta.acronyms.setdefault(acr, []).append(eid)

        # near-miss sibling: swap the middle morpheme for a confusable one
        if rng.random() < near_miss_rate:
            alt_mid = rng.choice([x for x in _MID if x != m and x[0] == m[0]]
                                 or [x for x in _MID if x != m])
            sib_name = p + alt_mid + o
            if sib_name not in used_names and len(entities) < n_entities:
                used_names.add(sib_name)
                sid = f"E{len(entities):05d}"
                add_entity(sid, sib_name,
                           f"{p} 지역의 {alt_mid} 분야 {o} 조직", [alt_mid])
                add_binding(sid, sib_name, "korean_org_name", kind="name",
                            left="hangul_token_boundary")
                meta.full_names[sib_name] = sid
                meta.near_miss_pairs.append((name, sib_name))

        # nested extension entity: base + 연구소 as its own entity
        if rng.random() < nested_rate and len(entities) < n_entities:
            ext = rng.choice(_EXT)
            ext_name = name + ext
            xid = f"E{len(entities):05d}"
            add_entity(xid, ext_name, f"{name} 산하 {ext}", [m])
            add_binding(xid, ext_name, "korean_org_name", kind="name",
                        left="hangul_token_boundary")
            meta.full_names[ext_name] = xid
            meta.nested_pairs.append((name, ext_name))

    glossary = {
        "glossary_id": f"synth-{n_entities}-s{seed}",
        "version": "1",
        "schema_version": "3",
        "entities": entities,
        "alias_families": families,
        "alias_bindings": bindings,
    }
    return glossary, meta


def collision_stats(meta: SynthMeta) -> dict:
    multi_h = {a: len(e) for a, e in meta.hangul_abbrevs.items() if len(e) > 1}
    multi_a = {a: len(e) for a, e in meta.acronyms.items() if len(e) > 1}
    return {
        "hangul_abbrevs": len(meta.hangul_abbrevs),
        "hangul_multi_sense": len(multi_h),
        "max_hangul_senses": max(multi_h.values(), default=1),
        "latin_acronyms": len(meta.acronyms),
        "latin_multi_sense": len(multi_a),
        "max_latin_senses": max(multi_a.values(), default=1),
        "near_miss_pairs": len(meta.near_miss_pairs),
        "nested_pairs": len(meta.nested_pairs),
    }


def absent_bindings_only(g_dict: dict, texts) -> tuple[dict, int]:
    """Keep only bindings whose surface truly cannot occur in ``texts``.

    A plain ``surface not in text`` check is wrong here: the resolver matches
    through a *normalized* channel (case folding, width folding, punctuation
    and spacing rules), so a case-sensitive filter lets `gb` survive a corpus
    containing `GB`, the resolver then matches it, and a construction error
    gets scored as a product false positive. The absence claim has to be made
    in the same space the matcher searches, under every default profile,
    because a surface only has to be reachable through one of them.
    """
    from ktrf.glossary import DEFAULT_PROFILES
    from ktrf.normalization import (build_canonical_stream, build_channel,
                                    normalize_alias)

    joined = chr(10).join(texts)
    stream = build_canonical_stream(joined)
    haystacks = {name: build_channel(stream, profile).chars
                 for name, profile in DEFAULT_PROFILES.items()}

    def reachable(surface: str) -> bool:
        if surface in joined:
            return True
        return any(
            (key := normalize_alias(surface, DEFAULT_PROFILES[name])) and key in hay
            for name, hay in haystacks.items()
        )

    kept = [b for b in g_dict["alias_bindings"] if not reachable(b["surface"])]
    removed = len(g_dict["alias_bindings"]) - len(kept)
    kept_fids = {b["family_id"] for b in kept}
    g_dict["alias_bindings"] = kept
    g_dict["alias_families"] = [f for f in g_dict["alias_families"]
                                if f["family_id"] in kept_fids]
    return g_dict, removed
