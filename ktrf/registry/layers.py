"""Layered terminology scopes (PLAN_PI.md §3).

Five scopes, lowest to highest interpretation precedence::

    base → global → project → session → document

A surface may be claimed by several scopes. The higher scope wins for
*interpretation*, but nothing is silently overwritten: the losing binding is
dropped from the compiled glossary and recorded as ``shadowed`` provenance
on the winner, so a context pack can tell the model (and a human reviewer)
that another meaning exists in a wider scope.

Shadowing a lower scope requires the winning term to declare
``override: true``. Without it the merge reports a conflict — an accidental
project-level redefinition of a company-wide term should fail review, not
quietly change what a word means.

Note the deliberate limit: precedence applies to *terminology meaning*
only. Nothing here grants document- or session-scoped text authority over
system instructions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..glossary import load_glossary
from .simple_schema import SimpleTermsError, compile_simple_terms

LAYER_ORDER = ("base", "global", "project", "session", "document")
_RANK = {name: i for i, name in enumerate(LAYER_ORDER)}


@dataclass
class TermLayer:
    """One scope's terminology source (a Simple Terminology document)."""

    scope: str
    doc: dict
    source: str | None = None
    trusted: bool = True

    def __post_init__(self):
        if self.scope not in _RANK:
            raise SimpleTermsError(
                f"unknown scope {self.scope!r}; expected one of "
                f"{list(LAYER_ORDER)}")


@dataclass
class LayeredCompileResult:
    glossary_dict: dict
    shadowed: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    skipped_layers: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts


def load_term_layers(sources: dict[str, str | Path | dict],
                     trusted_scopes: set[str] | None = None
                     ) -> list[TermLayer]:
    """Load ``{scope: path-or-doc}`` into layers, ordered by precedence.

    ``trusted_scopes`` marks which scopes may be read at all — project and
    document terminology comes from the working tree, so an integration
    must be able to withhold trust (PLAN_PI.md §4: never read
    ``.pi/ktrf/terms.yaml`` before the project is trusted).
    """
    import yaml

    layers: list[TermLayer] = []
    for scope, src in sources.items():
        trusted = trusted_scopes is None or scope in trusted_scopes
        if isinstance(src, dict):
            doc, origin = src, None
        else:
            path = Path(src)
            origin = str(path)
            if not trusted:
                layers.append(TermLayer(scope=scope, doc={"terms": []},
                                        source=origin, trusted=False))
                continue
            if not path.exists():
                continue
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        layers.append(TermLayer(scope=scope, doc=doc, source=origin,
                                trusted=trusted))
    layers.sort(key=lambda lyr: _RANK[lyr.scope])
    return layers


def compile_layered_glossary(layers: list[TermLayer],
                             glossary_id: str = "layered",
                             version: str = "1") -> LayeredCompileResult:
    """Merge layers into one glossary dict with shadowing provenance."""
    entities: list[dict] = []
    families: list[dict] = []
    bindings: list[dict] = []
    shadowed: list[dict] = []
    conflicts: list[dict] = []
    skipped: list[dict] = []
    # surface -> (rank, binding, entity_id, override)
    claimed: dict[str, tuple] = {}

    for layer in sorted(layers, key=lambda lyr: _RANK[lyr.scope]):
        if not layer.trusted:
            skipped.append({"scope": layer.scope, "source": layer.source,
                            "reason": "untrusted"})
            continue
        compiled = compile_simple_terms(layer.doc, scope=layer.scope,
                                        source=layer.source)
        entities.extend(compiled["entities"])
        families.extend(compiled["alias_families"])
        override_by_entity = {
            e["entity_id"]: e["provenance"].get("override", False)
            for e in compiled["entities"]}
        rank = _RANK[layer.scope]
        for binding in compiled["alias_bindings"]:
            surface = binding["surface"]
            prior = claimed.get(surface)
            override = override_by_entity.get(binding["entity_id"], False)
            if prior is None:
                claimed[surface] = (rank, binding, binding["entity_id"],
                                    override)
                bindings.append(binding)
                continue
            prior_rank, prior_binding, prior_entity, _ = prior
            if prior_entity == binding["entity_id"]:
                continue  # same entity re-declared; keep the first binding
            # higher scope wins interpretation, lower one is shadowed
            bindings.remove(prior_binding)
            binding.setdefault("provenance", {})["shadows"] = [prior_entity]
            claimed[surface] = (rank, binding, binding["entity_id"], override)
            bindings.append(binding)
            record = {
                "surface": surface,
                "winner": {"entity_id": binding["entity_id"],
                           "scope": layer.scope},
                "shadowed": {"entity_id": prior_entity,
                             "scope": LAYER_ORDER[prior_rank]},
                "declared_override": override,
            }
            shadowed.append(record)
            if not override:
                conflicts.append({
                    **record,
                    "reason": "higher-scope term shadows a wider-scope "
                              "meaning without override: true",
                })

    # drop families and entities that ended up with no live binding
    live_families = {b["family_id"] for b in bindings}
    families = [f for f in families if f["family_id"] in live_families]
    live_entities = {b["entity_id"] for b in bindings}
    entities = [e for e in entities if e["entity_id"] in live_entities]

    return LayeredCompileResult(
        glossary_dict={
            "glossary_id": glossary_id,
            "version": version,
            "schema_version": "3",
            "entities": entities,
            "alias_families": families,
            "alias_bindings": bindings,
        },
        shadowed=shadowed, conflicts=conflicts, skipped_layers=skipped,
    )


def compile_layered_snapshot(layers: list[TermLayer], *,
                             glossary_id: str = "layered",
                             version: str = "1",
                             strict_conflicts: bool = False,
                             **compile_kwargs):
    """Layers → merged glossary → compiled snapshot.

    ``compile_kwargs`` passes through to
    :func:`ktrf.snapshot.compile_snapshot` (tenant_id, encoder, policy,
    run_conformance …). Returns ``(snapshot, LayeredCompileResult)`` so the
    caller can surface shadowing/conflict diagnostics to a reviewer.
    """
    from ..snapshot import compile_snapshot, compute_snapshot_id

    result = compile_layered_glossary(layers, glossary_id=glossary_id,
                                      version=version)
    if strict_conflicts and result.conflicts:
        raise SimpleTermsError(
            f"layer conflicts require override: true — {result.conflicts}")
    snapshot = compile_snapshot(load_glossary(result.glossary_dict),
                                **compile_kwargs)
    snapshot.manifest["layers"] = [
        {"scope": lyr.scope, "source": lyr.source, "trusted": lyr.trusted}
        for lyr in sorted(layers, key=lambda x: _RANK[x.scope])]
    snapshot.manifest["shadowed_surfaces"] = len(result.shadowed)
    # the manifest gained fields after compile, so the identity must be
    # recomputed — a stored id that does not match its manifest is refused
    # at load time (§47.3), and that equation must hold here too
    snapshot.snapshot_id = compute_snapshot_id(snapshot.manifest)
    return snapshot, result
