"""Shared token segmentation and Level-B guards (spec §16; VARIANTS_PLAN M1).

Every candidate-generating channel must interpret an input token the same
way. Before this module only the exact channel did: it decomposed 조사 and
suffixes through the tail parser, while the fuzzy (jamo/keyboard),
abbreviation and dense channels fed *whole raw tokens* to their indexes.
That made ``한국전려`` recoverable and ``한국전려에서도`` unrecoverable — a
decomposition disagreement between channels, not a model-capacity limit —
and let a fuzzy mention span cover the particle it never analysed, breaking
the offset contract the exact path upholds (INV-012).

:func:`segment_token` is the single entry point. It enumerates every typed
:class:`StructuralPath` (prefix / core / residual / particle chain), ranked
but never pruned to one reading (REQ-TAIL-003): callers rank and guard, the
segmenter does not hard-select.

:class:`ResolutionGuard` applies the VARIANTS_PLAN §2 invariants to the
:class:`MatchEvidence` a channel produces. It is scoped to Level B channels
by construction: the Level A exact path already carries the §15 boundary and
§16 tail contract, and its determinism must not depend on this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from .hangul import is_syllable
from .morphology import (
    DISTINCT,
    SAME,
    SPLITTABLE_PARTICLES,
    UNRESOLVED,
    ParticleFST,
    analyze_residual,
    match_latin_tail,
    match_prefix_modifier,
)

MAX_TAIL_LEN = 12
MIN_CORE_SYLLABLES = 2  # §10.6: 1-2 char cores get no generic fuzzy anyway
UNKNOWN_TAIL_MIN_CORE = 3  # a core reached past an unanalysed tail
MAX_PATHS_PER_TOKEN = 4

# path kinds — the typed vocabulary channels and reports share
BARE = "BARE"
PARTICLE = "PARTICLE"
SUFFIX = "SUFFIX"
SUFFIX_PARTICLE = "SUFFIX_PARTICLE"
UNKNOWN_TAIL = "UNKNOWN_TAIL"
LATIN_TAIL = "LATIN_TAIL"

_RESIDUAL_BASE = {"": 1.0, "SUFFIX": 0.9, "SUFFIX_WITH_MODIFIER": 0.75,
                  "UNKNOWN": 0.3}


@dataclass(frozen=True)
class TailAnalysis:
    """One [residual][particle-chain] reading of the text after a core.

    Frozen: :func:`_decompose` caches these and hands the same instance to
    every occurrence of a token, so a mutation would leak across documents.
    """

    residual: str
    residual_kind: str  # "" | SUFFIX | SUFFIX_WITH_MODIFIER | UNKNOWN
    residual_parts: tuple[str, ...]
    particles: tuple[str, ...]
    grammatical: bool
    latin_tail: str = ""
    latin_tail_kind: str = ""
    score: float = 1.0
    # M2 typed tail: what core+residual denotes relative to the core alone.
    # SAME (기획재정 + 부), DISTINCT (금감원 + 장 is a person), UNKNOWN.
    residual_classes: tuple[str, ...] = ()
    governing_class: str = ""
    full_identity: str = SAME
    relation: str = "IDENTITY"

    @property
    def length(self) -> int:
        """Characters this analysis consumes after the core."""
        return (len(self.residual) + sum(len(p) for p in self.particles)
                + len(self.latin_tail))

    @property
    def kind(self) -> str:
        if self.latin_tail:
            return LATIN_TAIL
        if self.residual_kind == "UNKNOWN":
            return UNKNOWN_TAIL
        if self.residual and self.particles:
            return SUFFIX_PARTICLE
        if self.residual:
            return SUFFIX
        if self.particles:
            return PARTICLE
        return BARE


def _ends_the_name(a: TailAnalysis) -> bool:
    """Does this reading say where the name stops and grammar starts?

    Only used to break score ties, and a tie here is always between the two
    readings of the same characters: `카카오톡에` is either one unexplained
    chunk or `카카오톡` plus 에, and `서울시장과` is either 장 + 과(부서) or
    장 plus the conjunctive 과. Every scoring input is equal, because
    :data:`_RESIDUAL_BASE` and the grammaticality factor give eight distinct
    products — a tie therefore means the same ``residual_kind`` and the same
    grammaticality, and the verdict, relation and commit are already decided.
    What is left to choose is only *where the reported name ends*.

    The particle reading wins, but only for particles that cannot end a name
    (:data:`SPLITTABLE_PARTICLES`). Choosing wrong is not symmetric: keeping
    a 조사 inside the name reports a superstring of a real name, while
    splitting one that was a name syllable reports `카카오게` — a span that
    spells nothing and leaves 임 outside the mention.
    """
    return bool(a.particles) and all(p in SPLITTABLE_PARTICLES
                                     for p in a.particles)


def enumerate_tails(right: str, prev_char: str,
                    fst: ParticleFST) -> list[TailAnalysis]:
    """Enumerate every [residual][particle-chain] split of ``right``.

    All analyses are preserved (REQ-TAIL-003); callers rank, never prune.
    Shared by the exact tail parser and the Level B channels so that both
    agree on what counts as a core.
    """
    if not right:
        return [TailAnalysis("", "", (), (), True, score=1.0)]
    analyses: list[TailAnalysis] = []
    n = min(len(right), MAX_TAIL_LEN)
    right = right[:n]
    for cut in range(0, n + 1):
        residual, particle_part = right[:cut], right[cut:]
        if residual and not all(is_syllable(c) for c in residual):
            continue  # residuals are Hangul chunks; Latin tails handled apart
        if cut == n:
            r = analyze_residual(residual, prev_char)
            kind = r.kind if residual else ""
            analyses.append(TailAnalysis(
                residual, kind, r.parts if residual else (), (), True,
                score=_RESIDUAL_BASE.get(kind, 0.3),
                residual_classes=r.classes if residual else (),
                governing_class=r.governing_class if residual else "",
                full_identity=r.full_identity, relation=r.relation))
            continue
        prev = residual[-1] if residual else prev_char
        for parse in fst.parse_full(particle_part, prev):
            r = analyze_residual(residual, prev_char)
            kind = r.kind if residual else ""
            base = _RESIDUAL_BASE.get(kind, 0.3)
            analyses.append(TailAnalysis(
                residual, kind, r.parts if residual else (),
                parse.particles, parse.grammatical,
                score=base * (1.0 if parse.grammatical else 0.7),
                residual_classes=r.classes if residual else (),
                governing_class=r.governing_class if residual else "",
                full_identity=r.full_identity, relation=r.relation))
    if not analyses:
        analyses.append(TailAnalysis(
            right, "UNKNOWN", (right,), (), True, score=0.3,
            residual_classes=("UNKNOWN",), governing_class="UNKNOWN",
            full_identity=UNRESOLVED, relation="UNKNOWN"))
    analyses.sort(key=lambda a: (-a.score, not _ends_the_name(a),
                                 len(a.particles)))
    return analyses


# ---------------------------------------------------------------------------
# Typed structural paths
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructuralPath:
    """A typed decomposition of one raw token into prefix / core / tail.

    ``core_span`` is a raw codepoint half-open span into the *document*, not
    into the token, so a Level B channel that accepts this path produces the
    same span discipline as the exact path (INV-012).
    """

    token: str
    token_span: tuple[int, int]
    core: str
    core_span: tuple[int, int]
    kind: str = BARE
    prefix: str = ""
    prefix_kind: str = ""
    prefix_span: tuple[int, int] | None = None
    residual: str = ""
    residual_kind: str = ""
    residual_parts: tuple[str, ...] = ()
    residual_classes: tuple[str, ...] = ()
    governing_class: str = ""
    full_identity: str = SAME
    relation: str = "IDENTITY"
    particles: tuple[str, ...] = ()
    latin_tail: str = ""
    latin_tail_kind: str = ""
    grammatical: bool = True
    score: float = 1.0

    @property
    def strips_tail(self) -> bool:
        """True when the core is shorter than the token it came from."""
        return self.core != self.token

    @property
    def full_span(self) -> tuple[int, int]:
        """The whole token: prefix, core, residual, particles, Latin tail."""
        start = self.prefix_span[0] if self.prefix_span else self.core_span[0]
        tail_len = (len(self.residual)
                    + sum(len(p) for p in self.particles)
                    + len(self.latin_tail))
        return (start, self.core_span[1] + tail_len)

    @property
    def surface_span(self) -> tuple[int, int]:
        """The *nominal* extent: prefix + core + residual, no particles.

        ``full_span`` answers "which characters did this token occupy";
        this answers "which characters spell a name". A 조사 is grammar, not
        part of a name, so the two differ for `한전은` and agree for
        `한전노조`. Consumers that highlight or substitute want this one.
        """
        start = self.prefix_span[0] if self.prefix_span else self.core_span[0]
        return (start, self.core_span[1] + len(self.residual))

    def as_dict(self) -> dict:
        d = {"kind": self.kind, "core": self.core,
             "core_span": list(self.core_span), "score": round(self.score, 4)}
        if self.prefix:
            d["prefix"] = self.prefix
            d["prefix_kind"] = self.prefix_kind
        if self.residual:
            d["residual"] = self.residual
            d["residual_kind"] = self.residual_kind
            d["residual_classes"] = list(self.residual_classes)
            d["full_identity"] = self.full_identity
            d["relation"] = self.relation
        if self.particles:
            d["particles"] = list(self.particles)
            d["grammatical"] = self.grammatical
        if self.latin_tail:
            d["latin_tail"] = self.latin_tail
        return d


@lru_cache(maxsize=16384)
def _decompose(token: str, fst: ParticleFST, min_core: int,
               max_paths: int) -> tuple[tuple[int, TailAnalysis, float], ...]:
    """Position-independent readings of ``token``: (core_len, tail, score).

    Cached because this is Pass-1 hot path work that depends only on the
    token and the morphology catalogs, never on where the token sits. The
    caller reattaches document offsets, which is why spans are not in here.

    ``fst`` is part of the key so a snapshot with custom particle catalogs
    never reads another snapshot's readings; the cache therefore keeps a
    strong reference to each FST it has seen (a catalog dict, not an index),
    which is why it is bounded.
    """
    bare = TailAnalysis("", "", (), (), True, score=1.0)
    out: list[tuple[int, TailAnalysis, float]] = [(len(token), bare, 1.0)]

    if all(is_syllable(c) for c in token):
        # Hangul token: every core length that leaves an analysable tail
        for core_len in range(len(token) - 1, min_core - 1, -1):
            right = token[core_len:]
            if len(right) > MAX_TAIL_LEN:
                continue
            for tail in enumerate_tails(right, token[core_len - 1], fst):
                if tail.length != len(right):
                    continue
                if tail.residual_kind == "UNKNOWN":
                    # an unanalysable remainder is not a segmentation, only a
                    # shorter prefix of the same token (§16.5). It survives
                    # only when a particle chain closes the token *and* the
                    # core is long enough to identify something on its own —
                    # otherwise `셀트루온에서` yields the core `셀트`.
                    if not tail.particles or core_len < UNKNOWN_TAIL_MIN_CORE:
                        continue
                # shorter cores are weaker readings: charge the tail length
                score = tail.score * (1.0 - 0.04 * len(right))
                out.append((core_len, tail, max(0.05, score)))
    elif match_latin_tail(token) is None:
        for cut in range(len(token) - 1, min_core - 1, -1):
            lt = match_latin_tail(token[cut:])
            if lt and len(lt[0]) == len(token) - cut:
                out.append((cut, TailAnalysis(
                    "", "", (), (), True, latin_tail=lt[0],
                    latin_tail_kind=lt[1], score=0.95), 0.95))
                break

    # stable, deterministic order: score desc, longer core first
    out.sort(key=lambda r: (-r[2], -r[0]))
    deduped: list[tuple[int, TailAnalysis, float]] = []
    seen: set[tuple] = set()
    for core_len, tail, score in out:
        key = (core_len, tail.kind, tail.particles, tail.residual)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((core_len, tail, score))
    return tuple(deduped[:max_paths])


def segment_token(
    token: str,
    span: tuple[int, int],
    fst: ParticleFST,
    left_context: str = "",
    min_core: int = MIN_CORE_SYLLABLES,
    max_paths: int = MAX_PATHS_PER_TOKEN,
) -> list[StructuralPath]:
    """Enumerate the typed decompositions of one raw token, best first.

    ``span`` is the token raw codepoint span; ``left_context`` is the text
    immediately preceding it (for §16.6 prefix modifiers). The bare reading is
    always present and ranks first, so a channel that consults only
    ``paths[0]`` keeps its pre-M1 behaviour.
    """
    start, _end = span
    prefix = prefix_kind = ""
    prefix_span: tuple[int, int] | None = None
    if left_context:
        pfx = match_prefix_modifier(left_context)
        if pfx:
            prefix, prefix_kind, spaced = pfx
            consumed = len(prefix) + (1 if spaced else 0)
            if consumed <= len(left_context):
                prefix_span = (start - consumed,
                               start - consumed + len(prefix))

    return [
        StructuralPath(
            token=token, token_span=span,
            core=token[:core_len], core_span=(start, start + core_len),
            kind=tail.kind, prefix=prefix, prefix_kind=prefix_kind,
            prefix_span=prefix_span,
            residual=tail.residual, residual_kind=tail.residual_kind,
            residual_parts=tail.residual_parts,
            residual_classes=tail.residual_classes,
            governing_class=tail.governing_class,
            full_identity=tail.full_identity, relation=tail.relation,
            particles=tail.particles,
            latin_tail=tail.latin_tail, latin_tail_kind=tail.latin_tail_kind,
            grammatical=tail.grammatical, score=score,
        )
        for core_len, tail, score in _decompose(token, fst, min_core, max_paths)
    ]


def distinct_cores(paths: list[StructuralPath]) -> list[StructuralPath]:
    """One best path per distinct core span (channel query deduplication)."""
    out: list[StructuralPath] = []
    seen: set[tuple[int, int]] = set()
    for p in paths:
        if p.core_span in seen:
            continue
        seen.add(p.core_span)
        out.append(p)
    return out


# ---------------------------------------------------------------------------
# Match evidence + Level B guards (VARIANTS_PLAN §2)
# ---------------------------------------------------------------------------

LEVEL_A_CHANNELS = frozenset({"exact", "normalized"})


@dataclass(frozen=True)
class MatchEvidence:
    """Why one candidate exists: channel + the structural path it accepted.

    Recorded on every Level B candidate so that a commit decision, an
    explanation and an eval-only trace read the same record instead of each
    re-deriving it from free-form provenance dicts.
    """

    channel: str
    path_kind: str
    core_surface: str
    core_span: tuple[int, int]
    full_span: tuple[int, int]
    transform_cost: float = 0.0
    residual_kind: str = ""
    full_identity: str = SAME
    relation: str = "IDENTITY"
    particles: tuple[str, ...] = ()
    grammatical: bool = True
    tail_stripped: bool = False
    notes: tuple[str, ...] = ()

    @classmethod
    def from_path(cls, channel: str, path: StructuralPath,
                  transform_cost: float = 0.0,
                  notes: tuple[str, ...] = ()) -> "MatchEvidence":
        return cls(
            channel=channel, path_kind=path.kind, core_surface=path.core,
            core_span=path.core_span, full_span=path.full_span,
            transform_cost=transform_cost, residual_kind=path.residual_kind,
            full_identity=path.full_identity, relation=path.relation,
            particles=path.particles, grammatical=path.grammatical,
            tail_stripped=path.strips_tail, notes=notes,
        )

    @property
    def level_a(self) -> bool:
        return self.channel in LEVEL_A_CHANNELS

    def as_dict(self) -> dict:
        d = {"channel": self.channel, "path_kind": self.path_kind,
             "core": self.core_surface, "core_span": list(self.core_span)}
        if self.tail_stripped:
            d["tail_stripped"] = True
        if self.particles:
            d["particles"] = list(self.particles)
        if self.residual_kind:
            d["residual_kind"] = self.residual_kind
        if self.full_identity != SAME:
            d["full_identity"] = self.full_identity
            d["relation"] = self.relation
        if not self.grammatical:
            d["grammatical"] = False
        if self.notes:
            d["notes"] = list(self.notes)
        return d


@dataclass(frozen=True)
class GuardVerdict:
    commit_allowed: bool = True
    score_factor: float = 1.0
    reasons: tuple[str, ...] = ()

    @property
    def blocked_reason(self) -> str | None:
        if self.commit_allowed or not self.reasons:
            return None
        return self.reasons[0]


@dataclass
class ResolutionGuard:
    """VARIANTS_PLAN §2 invariants over Level B match evidence.

    The guard never applies to Level A evidence: the exact path's boundary
    and tail contract already decides those, and routing them through here
    would make the deterministic catalog guarantee depend on Level B tuning.
    A verdict can damp a score or withhold *commit*; it never removes a
    candidate, because candidate generation and commit stay separate
    (invariant ④).
    """

    stripped_tail_factor: float = 0.92
    ungrammatical_factor: float = 0.80
    derivative_factor: float = 0.60
    min_core_syllables: int = MIN_CORE_SYLLABLES
    rules: list[str] = field(default_factory=lambda: [
        "short_core", "derivative_full_surface",
        "ungrammatical_particle", "inferred_tail",
    ])

    def evaluate(self, evidence: MatchEvidence) -> GuardVerdict:
        if evidence.level_a:
            return GuardVerdict()
        commit = True
        factor = 1.0
        reasons: list[str] = []

        # invariant ①: a core too short to carry identity never commits
        if ("short_core" in self.rules
                and len(evidence.core_surface) < self.min_core_syllables):
            commit = False
            reasons.append("short_core")

        # invariant ②: when the tail says core+residual is not the core
        # entity — an unanalysable remainder, or a typed derivative such as
        # 한전+노조 (another organisation) or 금감원+장 (a person) — the parent
        # must not take the full surface. A registered COMPOSES_TO relation
        # does not lift this: it names the *derivative's* own entity, which
        # is a different answer, not a reason to let the parent through.
        if "derivative_full_surface" in self.rules:
            # an unanalysed remainder can never be "the same thing", however
            # the evidence was built — check the kind as well as the verdict
            if (evidence.full_identity == UNRESOLVED
                    or evidence.residual_kind == "UNKNOWN"):
                commit = False
                factor *= self.derivative_factor
                reasons.append("unknown_residual_derivative")
            elif evidence.full_identity == DISTINCT:
                commit = False
                factor *= self.derivative_factor
                reasons.append("typed_derivative")

        # §16.2: ungrammatical attachment is a soft signal, not a rejection
        if "ungrammatical_particle" in self.rules and not evidence.grammatical:
            factor *= self.ungrammatical_factor
            reasons.append("ungrammatical_particle")

        # invariant ④: a tail we inferred rather than observed is weaker
        # evidence than a bare-token match, so it must not outrank one
        if "inferred_tail" in self.rules and evidence.tail_stripped:
            factor *= self.stripped_tail_factor
            reasons.append("inferred_tail")

        return GuardVerdict(commit, round(factor, 4), tuple(reasons))


DEFAULT_GUARD = ResolutionGuard()
