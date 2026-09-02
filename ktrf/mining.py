"""Mine the names a glossary does not hold, from what the resolver already
says (VARIANTS_PLAN M4).

The signal needs no new analysis. A mention carrying `full_surface` with an
`identity` other than `SAME_AS_CORE` is the resolver stating that the text
holds a longer name than the one it matched, and `link_decision` says whether
it could put a name to it. Aggregating those statements *is* the backlog —
evidence first, judgement never.

Two findings come out, and the census that shaped this module says they are
not equally trustworthy:

- :class:`SuffixGap` — a residual seen behind **many different entities**.
  A coincidence would have to repeat across unrelated names, so recurrence
  across entities is strong evidence that the chunk is an *ending* rather
  than part of one name. `교육청` appeared behind 14 entities and is not in
  `SUFFIX_CLASSES`: a taxonomy gap, measured instead of guessed.

- :class:`NameGap` — one (entity, residual) pair seen repeatedly. This is the
  finding M4 was written for, and it is the weaker of the two. The
  abbreviation channel matches coincidental prefixes that recur just as
  reliably as real ones, because the *word* is common — `해수` inside
  `해수욕장` held across nine documents. So a name gap is mined only behind a
  core the **exact** channel found: a registered surface, not a subsequence.
  That is the difference between `카카오`+`톡` and `해수`+`욕장`.

Nothing here writes to a glossary. The output is a ranked backlog with its
evidence attached, for an approval loop to carry: a person or an LLM supplies
what a name *means*, and this module supplies only that a name is there.

Only public response fields are read, so the miner runs against any KTRF
deployment's output, including one older than this module.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field

from .morphology import SUFFIX_CLASSES

__all__ = ["SuffixGap", "NameGap", "MiningReport", "VariantMiner",
           "MIN_ENTITIES_FOR_SUFFIX", "MIN_OCCURRENCES_FOR_NAME",
           "MIN_DOCUMENTS_FOR_NAME"]

# A residual behind this many distinct entities is an ending, not a name.
# Two is one coincidence away; at three, every catalogued suffix the census
# corpus contained cleared the bar and the noise below it did not.
MIN_ENTITIES_FOR_SUFFIX = 3
# A name gap has to recur, and recur across documents: one document repeating
# a phrase is one observation written twice.
MIN_OCCURRENCES_FOR_NAME = 3
MIN_DOCUMENTS_FOR_NAME = 2
# Sentences kept per finding, so a reviewer can read the claim rather than
# take it on trust.
MAX_EXAMPLES = 3


@dataclass(frozen=True)
class SuffixGap:
    """An ending the catalog does not classify, seen behind many entities."""

    residual: str
    entities: tuple[str, ...]
    occurrences: int
    documents: int
    relations: tuple[tuple[str, int], ...]  # how the tail parser read it
    examples: tuple[str, ...]

    @property
    def entity_count(self) -> int:
        return len(self.entities)

    def to_dict(self) -> dict:
        return {"kind": "SUFFIX_GAP", "residual": self.residual,
                "entity_count": self.entity_count,
                "entities": list(self.entities),
                "occurrences": self.occurrences, "documents": self.documents,
                "relations": [list(r) for r in self.relations],
                "examples": list(self.examples)}


@dataclass(frozen=True)
class NameGap:
    """A name the text keeps using and the glossary does not hold."""

    entity_id: str
    residual: str
    surface: str            # the whole name, as most often written
    relation: str           # how the tail parser related it to the core
    identity: str
    occurrences: int
    documents: int
    examples: tuple[str, ...]
    # the documents the examples came from, so a proposal can cite where the
    # surface was seen rather than assert that it was
    example_documents: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"kind": "NAME_GAP", "entity_id": self.entity_id,
                "residual": self.residual, "surface": self.surface,
                "relation": self.relation, "identity": self.identity,
                "occurrences": self.occurrences, "documents": self.documents,
                "examples": list(self.examples),
                "example_documents": list(self.example_documents)}

    def to_proposal(self, *, canonical: str, short_definition: str,
                    requested_scope: str = "project") -> dict:
        """Keyword arguments for ``TermProposalStore.submit``.

        ``canonical`` and ``short_definition`` are required arguments with no
        default on purpose. The miner knows a name is there and cannot know
        what it means; inventing either is the one thing this whole loop
        exists to prevent. A caller — a person, or an LLM whose answer is
        then validated — supplies them.

        The origin is ``deterministic_detector``, which the admission policy
        does not treat as explicit: a mined name never auto-activates at any
        scope. The evidence is stronger than an LLM proposal's all the same,
        because ``surface_present`` here is a reading of the corpus rather
        than a claim about it.
        """
        from .registry.proposals import EvidenceRef

        if not canonical.strip() or not short_definition.strip():
            raise ValueError(
                "a mined name gap carries evidence, not meaning: "
                "canonical and short_definition must come from a reviewer")
        refs = tuple(EvidenceRef(entry_id=str(doc), surface_present=True,
                                 definition_pattern=False)
                     for doc in self.example_documents)
        return {"surface": self.surface, "canonical": canonical,
                "short_definition": short_definition,
                "requested_scope": requested_scope,
                "origin": "deterministic_detector", "evidence_refs": refs}

    def to_composition(self, target_entity_id: str,
                       relation_id: str | None = None) -> dict:
        """The ``entity_relations`` entry that closes the loop.

        Registering the mined name as a standalone entity would throw away
        the one thing the miner *did* establish: that this surface begins
        with a core the glossary holds. A `COMPOSES_TO` carrying the residual
        as its ``surface_suffix`` keeps it, and invariant ③ then answers the
        surface by name instead of leaving it unexplained — which is what
        makes the next mining pass count it as already named rather than
        reporting it again.

        ``target_entity_id`` is the entity approval created for this name; the
        miner cannot know it, for the same reason it cannot know a canonical.
        """
        if not target_entity_id:
            raise ValueError("a composition needs the entity approval made")
        rid = relation_id or f"REL_MINED_{self.entity_id}_{self.residual}"
        return {"relation_id": rid, "source_entity_id": self.entity_id,
                "relation_type": "COMPOSES_TO",
                "target_entity_id": target_entity_id,
                "surface_suffix": self.residual}


@dataclass
class MiningReport:
    """What one pass over a corpus found, with the denominators."""

    suffix_gaps: list[SuffixGap] = field(default_factory=list)
    name_gaps: list[NameGap] = field(default_factory=list)
    observed_mentions: int = 0
    wider_surfaces: int = 0
    already_named: int = 0        # a registered COMPOSES_TO answered it
    slots: int = 0                # distinct (entity, residual) pairs seen

    def to_dict(self) -> dict:
        return {"observed_mentions": self.observed_mentions,
                "wider_surfaces": self.wider_surfaces,
                "already_named": self.already_named,
                "distinct_slots": self.slots,
                "suffix_gaps": [g.to_dict() for g in self.suffix_gaps],
                "name_gaps": [g.to_dict() for g in self.name_gaps]}


def _entity_of(mention: dict) -> str | None:
    """Which entity the core was read as, committed or merely proposed.

    A mined name is a lead, so an uncommitted core still counts — but only
    when the prediction set agrees with itself. Two candidate entities on one
    span is a lead pointing two ways, and naming either one is a guess.
    """
    resolved = mention.get("resolved_entity")
    if resolved and resolved.get("entity_id"):
        return resolved["entity_id"]
    members = mention.get("prediction_set", {}).get("members", [])
    ids = {m.get("entity_id") for m in members if m.get("entity_id")}
    return ids.pop() if len(ids) == 1 else None


class VariantMiner:
    """Accumulate resolver responses; emit a ranked backlog.

    Stateful on purpose: the evidence that separates an ending from a name is
    *cross-document*, so a per-response function could not compute it.
    """

    def __init__(self, *, min_entities: int = MIN_ENTITIES_FOR_SUFFIX,
                 min_occurrences: int = MIN_OCCURRENCES_FOR_NAME,
                 min_documents: int = MIN_DOCUMENTS_FOR_NAME,
                 known_suffixes=None):
        self.min_entities = min_entities
        self.min_occurrences = min_occurrences
        self.min_documents = min_documents
        # injectable so a tenant carrying its own catalog mines against that
        # one rather than against this build's
        self.known_suffixes = (SUFFIX_CLASSES if known_suffixes is None
                               else known_suffixes)
        self._slots: dict[tuple[str, str], dict] = {}
        self._observed = 0
        self._wider = 0
        self._already_named = 0

    def observe(self, response: dict, doc_id, text: str = "") -> None:
        """Fold one resolver response in. ``doc_id`` separates documents."""
        for m in response.get("mentions", []):
            self._observed += 1
            fs = m.get("full_surface")
            if not fs:
                continue
            self._wider += 1
            if "composes_to" in fs:
                # invariant ③: the glossary has already answered this one
                self._already_named += 1
                continue
            if fs.get("identity") == "SAME_AS_CORE":
                # the wider surface is the same organisation spelled longer —
                # an alias question, not a missing name
                continue
            core = m.get("core_link", {}).get("surface", "")
            whole = fs.get("surface", "")
            if not core or not whole.startswith(core):
                continue
            residual = whole[len(core):]
            entity = _entity_of(m)
            if not residual or entity is None:
                continue
            slot = self._slots.setdefault(
                (entity, residual),
                {"n": 0, "docs": set(), "surfaces": collections.Counter(),
                 "relations": collections.Counter(), "examples": [],
                 "example_docs": [], "exact": 0,
                 "identity": collections.Counter()})
            slot["n"] += 1
            slot["docs"].add(doc_id)
            slot["surfaces"][whole] += 1
            slot["relations"][m.get("core_link", {}).get("relation")] += 1
            slot["identity"][fs.get("identity")] += 1
            # `exact` is the gate for name gaps: a core the deterministic
            # channel found is a registered surface, not a subsequence a
            # fuzzy channel reached for.
            if "exact" in (m.get("generation_channels") or ()):
                slot["exact"] += 1
            if text and len(slot["examples"]) < MAX_EXAMPLES:
                if text not in slot["examples"]:
                    slot["examples"].append(text)
                    slot["example_docs"].append(doc_id)

    # -- findings ----------------------------------------------------------

    def _by_residual(self) -> dict[str, list[tuple[str, dict]]]:
        out: dict[str, list[tuple[str, dict]]] = collections.defaultdict(list)
        for (entity, residual), slot in self._slots.items():
            out[residual].append((entity, slot))
        return out

    def report(self) -> MiningReport:
        by_residual = self._by_residual()
        cross_entity = {res for res, rows in by_residual.items()
                        if len(rows) >= self.min_entities}

        suffix_gaps = []
        for residual in sorted(cross_entity):
            if residual in self.known_suffixes:
                continue  # the catalog already reads this ending
            rows = by_residual[residual]
            rel: collections.Counter = collections.Counter()
            examples: list[str] = []
            docs: set = set()
            for _, slot in rows:
                rel.update(slot["relations"])
                docs |= slot["docs"]
                for ex in slot["examples"]:
                    if len(examples) < MAX_EXAMPLES and ex not in examples:
                        examples.append(ex)
            suffix_gaps.append(SuffixGap(
                residual=residual,
                entities=tuple(sorted(e for e, _ in rows)),
                occurrences=sum(s["n"] for _, s in rows),
                documents=len(docs),
                relations=tuple(rel.most_common()),
                examples=tuple(examples)))
        suffix_gaps.sort(key=lambda g: (-g.entity_count, -g.occurrences,
                                        g.residual))

        name_gaps = []
        for (entity, residual), slot in self._slots.items():
            if residual in cross_entity:
                continue  # it is an ending; the other finding covers it
            if slot["n"] < self.min_occurrences:
                continue
            if len(slot["docs"]) < self.min_documents:
                continue
            if not slot["exact"]:
                continue  # a coincidental prefix, not a registered core
            name_gaps.append(NameGap(
                entity_id=entity, residual=residual,
                surface=slot["surfaces"].most_common(1)[0][0],
                relation=slot["relations"].most_common(1)[0][0] or "UNKNOWN",
                identity=slot["identity"].most_common(1)[0][0] or "UNKNOWN",
                occurrences=slot["n"], documents=len(slot["docs"]),
                examples=tuple(slot["examples"]),
                example_documents=tuple(str(d) for d in slot["example_docs"])))
        name_gaps.sort(key=lambda g: (-g.occurrences, -g.documents,
                                      g.surface))

        return MiningReport(
            suffix_gaps=suffix_gaps, name_gaps=name_gaps,
            observed_mentions=self._observed, wider_surfaces=self._wider,
            already_named=self._already_named, slots=len(self._slots))
