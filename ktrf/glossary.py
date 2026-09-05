"""Glossary schema, loading and strict validation (spec §10, §47.7).

Schema version 3 (v0.3). schema_version "2" glossaries are readable with a
migration warning; their legacy flat ``scope`` maps to ``scope.allow`` (§10.5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from .normalization import DEFAULT_PROFILES, NormalizationProfile, normalize_alias


class GlossaryError(Exception):
    pass


@dataclass
class Diagnostic:
    severity: str  # "error" | "warning"
    code: str
    message: str

    def __repr__(self) -> str:
        return f"[{self.severity}] {self.code}: {self.message}"


@dataclass
class Entity:
    entity_id: str
    canonical: str
    language: str | None = None
    type_ids: list[str] = field(default_factory=list)
    domain_ids: list[str] = field(default_factory=list)
    description: str = ""
    examples: list[str] = field(default_factory=list)
    valid_from: str | None = None
    valid_to: str | None = None
    metadata: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    # LLM-grounding block (context packs): short_definition,
    # disambiguation_hints, injection_policy (auto|resolved_only|
    # candidate_only|never), priority, classification
    # (public|internal|restricted)
    grounding: dict = field(default_factory=dict)


@dataclass
class AliasFamily:
    family_id: str
    representative: str
    normalization_profile: str = "korean_term"


@dataclass
class Scope:
    allow: dict[str, list[str]] = field(default_factory=dict)
    deny: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class BoundaryPolicy:
    left: str = "unicode_word_boundary"
    right: str = "particle_or_token_boundary"
    allow_inside_latin_run: bool = False


@dataclass
class FuzzyPolicy:
    enabled: bool | None = None  # None = derive from length defaults (§10.6)
    keyboard_recovery: bool = True
    max_edit_cost: float | None = None


@dataclass
class AliasBinding:
    alias_id: str
    family_id: str
    entity_id: str
    surface: str
    kind: str = "alias"
    boundary_policy: BoundaryPolicy = field(default_factory=BoundaryPolicy)
    normalization_policy: dict = field(default_factory=dict)
    fuzzy_policy: FuzzyPolicy = field(default_factory=FuzzyPolicy)
    scope: Scope = field(default_factory=Scope)
    valid_from: str | None = None
    valid_to: str | None = None
    provenance: dict = field(default_factory=dict)


@dataclass
class EntityRelation:
    relation_id: str
    source_entity_id: str
    relation_type: str  # SUBSIDIARY_OR_UNIT_OF | COMPOSES_TO | ...
    target_entity_id: str
    surface_suffix: str | None = None


@dataclass(frozen=True)
class Composition:
    """A registered `core + suffix -> other entity` reading (§2 invariant ③).

    ``한전`` + ``노조`` is not 한국전력공사 under a longer span; it is a
    different organisation. When the glossary declares that relation, the
    resolver reports the declared target instead of leaving the derivative
    unexplained — a registered relation always beats an inferred one.
    """

    relation_id: str
    source_entity_id: str
    surface_suffix: str
    target_entity_id: str


def composition_index(g: "Glossary") -> dict[tuple[str, str], Composition]:
    """Index COMPOSES_TO relations by (source entity, surface suffix).

    Only relations that carry a ``surface_suffix`` are indexed: without one
    there is no surface to recognise, and the relation stays a pure KB fact.
    The suffix is matched literally, so this lookup is as deterministic as
    the exact channel it complements.
    """
    idx: dict[tuple[str, str], Composition] = {}
    for r in g.entity_relations:
        if r.relation_type != "COMPOSES_TO" or not r.surface_suffix:
            continue
        idx.setdefault(
            (r.source_entity_id, r.surface_suffix),
            Composition(r.relation_id, r.source_entity_id, r.surface_suffix,
                        r.target_entity_id),
        )
    return idx


@dataclass
class Glossary:
    glossary_id: str
    version: str
    schema_version: str
    entities: list[Entity]
    alias_families: list[AliasFamily]
    alias_bindings: list[AliasBinding]
    entity_relations: list[EntityRelation]
    normalization_profiles: dict[str, NormalizationProfile]
    policies: dict = field(default_factory=dict)

    def entity(self, entity_id: str) -> Entity | None:
        return self._entity_index.get(entity_id)

    def family(self, family_id: str) -> AliasFamily | None:
        return self._family_index.get(family_id)

    def binding(self, alias_id: str) -> AliasBinding | None:
        """Look up a binding by alias id.

        Scope adjustment needs this once per candidate, and did it with a
        linear scan over every binding in the glossary — 6,261 bindings times
        1,070 candidates was 6.7M comparisons per 3,200-character document.
        Built here alongside the other two indexes because it is derived data,
        so it costs nothing in the snapshot id.
        """
        return self._binding_index.get(alias_id)

    def __post_init__(self):
        self._entity_index = {e.entity_id: e for e in self.entities}
        self._family_index = {f.family_id: f for f in self.alias_families}
        # first wins, matching the scan this replaced
        self._binding_index: dict[str, AliasBinding] = {}
        for b in self.alias_bindings:
            self._binding_index.setdefault(b.alias_id, b)

    def binding_profile(self, binding: AliasBinding) -> NormalizationProfile:
        """Effective profile: binding override > family profile > default (REQ-NRM-001)."""
        fam = self.family(binding.family_id)
        prof_name = fam.normalization_profile if fam else "korean_term"
        prof = self.normalization_profiles.get(prof_name) or DEFAULT_PROFILES.get(prof_name)
        if prof is None:
            prof = DEFAULT_PROFILES["korean_term"]
        if binding.normalization_policy:
            prof = prof.merged(binding.normalization_policy)
        return prof


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _parse_scope(raw: dict | None) -> Scope:
    if not raw:
        return Scope()
    if "allow" in raw or "deny" in raw:
        return Scope(
            allow={k: list(v or []) for k, v in (raw.get("allow") or {}).items()},
            deny={k: list(v or []) for k, v in (raw.get("deny") or {}).items()},
        )
    # v0.2 compat: flat scope means allow (§10.5)
    return Scope(allow={k: list(v or []) for k, v in raw.items()})


def _parse_boundary(raw: dict | None, surface: str) -> BoundaryPolicy:
    if raw:
        return BoundaryPolicy(
            left=raw.get("left", _default_left(surface)),
            right=raw.get("right", "particle_or_token_boundary"),
            allow_inside_latin_run=raw.get("allow_inside_latin_run", False),
        )
    return BoundaryPolicy(left=_default_left(surface))


def _default_left(surface: str) -> str:
    first = surface[:1]
    if first and ("가" <= first <= "힣"):
        return "hangul_token_boundary"
    if first.isascii() and first.isalnum():
        return "latin_token_boundary"
    return "unicode_word_boundary"


def load_glossary(source: str | dict) -> Glossary:
    """Load a glossary from a YAML path or an already-parsed dict."""
    if isinstance(source, str):
        with open(source, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    else:
        data = source
    if not isinstance(data, dict):
        raise GlossaryError("glossary document must be a mapping")

    schema_version = str(data.get("schema_version", "3"))

    profiles = dict(DEFAULT_PROFILES)
    for p in data.get("normalization_profiles") or []:
        prof = NormalizationProfile(
            id=p["id"],
            nfc=p.get("nfc", True),
            width_fold=p.get("width_fold", "ascii_compat"),
            case_fold=p.get("case_fold", "none"),
            ignore_punctuation=tuple(p.get("ignore_punctuation", ())),
            spacing_mode=p.get("spacing_mode", "strict"),
            latin_morph=p.get("latin_morph", False),
        )
        if prof.id in DEFAULT_PROFILES and prof != DEFAULT_PROFILES[prof.id]:
            # §14.6: tenants must not change the meaning of default profiles
            raise GlossaryError(
                f"normalization profile {prof.id!r} redefines a system default profile"
            )
        profiles[prof.id] = prof

    entities = [
        Entity(
            entity_id=e["entity_id"],
            canonical=e.get("canonical", ""),
            language=e.get("language"),
            type_ids=list(e.get("type_ids") or []),
            domain_ids=list(e.get("domain_ids") or []),
            description=e.get("description") or "",
            examples=list(e.get("examples") or []),
            valid_from=e.get("valid_from"),
            valid_to=e.get("valid_to"),
            metadata=e.get("metadata") or {},
            provenance=e.get("provenance") or {},
            grounding=e.get("grounding") or {},
        )
        for e in data.get("entities") or []
    ]

    families = [
        AliasFamily(
            family_id=f["family_id"],
            representative=f["representative"],
            normalization_profile=f.get("normalization_profile", "korean_term"),
        )
        for f in data.get("alias_families") or []
    ]

    bindings = []
    for b in data.get("alias_bindings") or []:
        fz = b.get("fuzzy_policy") or {}
        bindings.append(
            AliasBinding(
                alias_id=b["alias_id"],
                family_id=b["family_id"],
                entity_id=b["entity_id"],
                surface=b["surface"],
                kind=b.get("kind", "alias"),
                boundary_policy=_parse_boundary(b.get("boundary_policy"), b["surface"]),
                normalization_policy=b.get("normalization_policy") or {},
                fuzzy_policy=FuzzyPolicy(
                    enabled=fz.get("enabled"),
                    keyboard_recovery=fz.get("keyboard_recovery", True),
                    max_edit_cost=fz.get("max_edit_cost"),
                ),
                scope=_parse_scope(b.get("scope")),
                valid_from=b.get("valid_from"),
                valid_to=b.get("valid_to"),
                provenance=b.get("provenance") or {},
            )
        )

    relations = [
        EntityRelation(
            relation_id=r["relation_id"],
            source_entity_id=r["source_entity_id"],
            relation_type=r["relation_type"],
            target_entity_id=r["target_entity_id"],
            surface_suffix=r.get("surface_suffix"),
        )
        for r in data.get("entity_relations") or []
    ]

    return Glossary(
        glossary_id=data.get("glossary_id", "unnamed"),
        version=str(data.get("version", "0")),
        schema_version=schema_version,
        entities=entities,
        alias_families=families,
        alias_bindings=bindings,
        entity_relations=relations,
        normalization_profiles=profiles,
        policies=data.get("policies") or {},
    )


# ---------------------------------------------------------------------------
# Strict validation (§10.8) + content lint (§47.7)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = re.compile(
    r"(ignore (all|previous|above)|disregard (the|previous)|system prompt"
    r"|다음 지시를 무시|지시를 따르|프롬프트를 무시|you must now|</?script"
    r"|<\s*/?\s*(system|instructions?)\b)",
    re.IGNORECASE,
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MAX_DESCRIPTION_LEN = 500  # §47.7 recommended cap


def _lint_content(text: str, where: str, diags: list[Diagnostic]) -> None:
    if not text:
        return
    if _CONTROL_CHARS.search(text):
        diags.append(Diagnostic("error", "CONTENT_CONTROL_CHARS",
                                f"{where}: control characters present"))
    if _INJECTION_PATTERNS.search(text):
        diags.append(Diagnostic("warning", "CONTENT_INJECTION_PATTERN",
                                f"{where}: instruction-like pattern detected"))
    if len(text) > _MAX_DESCRIPTION_LEN:
        diags.append(Diagnostic("warning", "CONTENT_TOO_LONG",
                                f"{where}: exceeds {_MAX_DESCRIPTION_LEN} chars"))


def validate_glossary(g: Glossary, strict: bool = True) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    if g.schema_version == "2":
        diags.append(Diagnostic("warning", "SCHEMA_V2_MIGRATION",
                                "schema_version 2 glossary: legacy scope mapped to allow"))

    seen_entities: set[str] = set()
    for e in g.entities:
        if e.entity_id in seen_entities:
            diags.append(Diagnostic("error", "DUPLICATE_ENTITY_ID", e.entity_id))
        seen_entities.add(e.entity_id)
        if not e.canonical.strip():
            diags.append(Diagnostic("error", "EMPTY_CANONICAL", e.entity_id))
        _lint_content(e.description, f"{e.entity_id}.description", diags)
        for i, ex in enumerate(e.examples):
            _lint_content(ex, f"{e.entity_id}.examples[{i}]", diags)

    family_ids = {f.family_id for f in g.alias_families}
    seen_bindings: set[str] = set()
    normalized_map: dict[str, list[AliasBinding]] = {}
    for b in g.alias_bindings:
        if b.alias_id in seen_bindings:
            diags.append(Diagnostic("error", "DUPLICATE_ALIAS_ID", b.alias_id))
        seen_bindings.add(b.alias_id)
        if b.entity_id not in seen_entities:
            diags.append(Diagnostic("error", "DANGLING_ENTITY_REF",
                                    f"{b.alias_id} -> {b.entity_id}"))
        if b.family_id not in family_ids:
            diags.append(Diagnostic("error", "DANGLING_FAMILY_REF",
                                    f"{b.alias_id} -> {b.family_id}"))
        if not b.surface.strip():
            diags.append(Diagnostic("error", "EMPTY_SURFACE", b.alias_id))
            continue
        prof = g.binding_profile(b)
        key = normalize_alias(b.surface, prof)
        normalized_map.setdefault(key, []).append(b)
        # dangerous short Latin alias without an explicit boundary policy
        if (
            len(key) <= 2
            and b.surface[:1].isascii()
            and b.surface[:1].isalpha()
            and b.boundary_policy.left == "unicode_word_boundary"
        ):
            diags.append(Diagnostic("warning", "SHORT_LATIN_NO_BOUNDARY", b.alias_id))
        # scope: same value in allow and deny (§10.8)
        for dim, denied in b.scope.deny.items():
            overlap = set(denied) & set(b.scope.allow.get(dim, []))
            if overlap:
                diags.append(Diagnostic("error", "SCOPE_ALLOW_DENY_OVERLAP",
                                        f"{b.alias_id}: {dim}={sorted(overlap)}"))
        # conflicting validity window
        if b.valid_from and b.valid_to and b.valid_from > b.valid_to:
            diags.append(Diagnostic("error", "INVALID_VALIDITY_WINDOW", b.alias_id))

    # ambiguity without distinguishing signals; collisions after normalization
    for key, bindings in normalized_map.items():
        entity_ids = {b.entity_id for b in bindings}
        if len(entity_ids) > 1:
            undistinguished = [
                eid for eid in entity_ids
                if (ent := g.entity(eid)) is not None
                and not (ent.description or ent.type_ids or ent.domain_ids or ent.examples)
            ]
            if len(undistinguished) == len(entity_ids):
                diags.append(Diagnostic(
                    "warning", "AMBIGUOUS_ALIAS_NO_SIGNALS",
                    f"alias {key!r} has {len(entity_ids)} senses with no distinguishing info",
                ))
            if len(entity_ids) > 8 and len(key) <= 3:
                diags.append(Diagnostic("warning", "SHORT_ALIAS_MANY_SENSES",
                                        f"alias {key!r}: {len(entity_ids)} senses"))
        surfaces = {b.surface for b in bindings}
        if len(surfaces) > 1:
            diags.append(Diagnostic(
                "warning", "NORMALIZED_ALIAS_COLLISION",
                f"surfaces {sorted(surfaces)} collide on normalized key {key!r}",
            ))

    # relations: dangling refs and trivial cycles
    for r in g.entity_relations:
        for eid in (r.source_entity_id, r.target_entity_id):
            if eid not in seen_entities:
                diags.append(Diagnostic("error", "DANGLING_RELATION_REF",
                                        f"{r.relation_id} -> {eid}"))
        if r.source_entity_id == r.target_entity_id:
            diags.append(Diagnostic("error", "RELATION_SELF_CYCLE", r.relation_id))
    _check_relation_cycles(g, diags)

    return diags


def _check_relation_cycles(g: Glossary, diags: list[Diagnostic]) -> None:
    graph: dict[str, list[str]] = {}
    for r in g.entity_relations:
        if r.relation_type in ("SUBSIDIARY_OR_UNIT_OF", "COMPOSES_TO"):
            graph.setdefault(r.source_entity_id, []).append(r.target_entity_id)
    state: dict[str, int] = {}

    def dfs(node: str, path: list[str]) -> None:
        state[node] = 1
        for nxt in graph.get(node, []):
            if state.get(nxt) == 1:
                diags.append(Diagnostic("error", "RELATION_CYCLE",
                                        " -> ".join(path + [nxt])))
            elif state.get(nxt) is None:
                dfs(nxt, path + [nxt])
        state[node] = 2

    for node in graph:
        if state.get(node) is None:
            dfs(node, [node])


def has_errors(diags: list[Diagnostic]) -> bool:
    return any(d.severity == "error" for d in diags)


# ---------------------------------------------------------------------------
# Serialization (artifact save path, §11)
# ---------------------------------------------------------------------------


def glossary_to_dict(g: Glossary) -> dict:
    """Serialize back to the schema-3 document form (load_glossary inverse)."""
    return {
        "glossary_id": g.glossary_id,
        "version": g.version,
        "schema_version": g.schema_version,
        "normalization_profiles": [
            {
                "id": p.id, "nfc": p.nfc, "width_fold": p.width_fold,
                "case_fold": p.case_fold,
                "ignore_punctuation": list(p.ignore_punctuation),
                "spacing_mode": p.spacing_mode, "latin_morph": p.latin_morph,
            }
            for pid, p in g.normalization_profiles.items()
            if pid not in DEFAULT_PROFILES
        ],
        "entities": [
            {
                "entity_id": e.entity_id, "canonical": e.canonical,
                "language": e.language, "type_ids": e.type_ids,
                "domain_ids": e.domain_ids, "description": e.description,
                "examples": e.examples, "valid_from": e.valid_from,
                "valid_to": e.valid_to, "metadata": e.metadata,
                "provenance": e.provenance, "grounding": e.grounding,
            }
            for e in g.entities
        ],
        "alias_families": [
            {
                "family_id": f.family_id, "representative": f.representative,
                "normalization_profile": f.normalization_profile,
            }
            for f in g.alias_families
        ],
        "alias_bindings": [
            {
                "alias_id": b.alias_id, "family_id": b.family_id,
                "entity_id": b.entity_id, "surface": b.surface,
                "kind": b.kind,
                "boundary_policy": {
                    "left": b.boundary_policy.left,
                    "right": b.boundary_policy.right,
                    "allow_inside_latin_run":
                        b.boundary_policy.allow_inside_latin_run,
                },
                "normalization_policy": b.normalization_policy,
                "fuzzy_policy": {
                    "enabled": b.fuzzy_policy.enabled,
                    "keyboard_recovery": b.fuzzy_policy.keyboard_recovery,
                    "max_edit_cost": b.fuzzy_policy.max_edit_cost,
                },
                "scope": {"allow": b.scope.allow, "deny": b.scope.deny},
                "valid_from": b.valid_from, "valid_to": b.valid_to,
                "provenance": b.provenance,
            }
            for b in g.alias_bindings
        ],
        "entity_relations": [
            {
                "relation_id": r.relation_id,
                "source_entity_id": r.source_entity_id,
                "relation_type": r.relation_type,
                "target_entity_id": r.target_entity_id,
                "surface_suffix": r.surface_suffix,
            }
            for r in g.entity_relations
        ],
        "policies": g.policies,
    }
