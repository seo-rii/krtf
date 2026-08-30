"""Prefix / core / residual / particle parser (spec §16).

Runs after the boundary check (§15.5 execution order): takes surviving exact
matches and produces mention proposals with full tail decomposition.

The tail enumeration itself lives in :mod:`ktrf.segmentation` so the exact
path and the Level B channels cannot drift apart (VARIANTS_PLAN M1); this
module keeps the exact-match-specific work of mapping a decomposition back
onto canonical-unit spans.

Homograph collisions (§16.5, REQ-TAIL-003) are preserved by keeping *all*
tail analyses per proposal (and all overlapping matches, which the matcher
already yields); the parser never hard-selects between a particle reading and
a suffix reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .matcher import RawExactMatch, _right_run, _script
from .morphology import ParticleFST, match_latin_tail, match_prefix_modifier
from .normalization import CanonicalStream
from .segmentation import MAX_TAIL_LEN, TailAnalysis, enumerate_tails

__all__ = ["TailAnalysis", "MentionProposal", "analyze_tail", "parse_matches"]


@dataclass
class MentionProposal:
    binding_id: str
    entity_id: str
    family_id: str
    surface: str  # raw core surface
    core_span: tuple[int, int]  # raw codepoint half-open
    full_span: tuple[int, int]
    matched_segments: list[tuple[int, int]]
    prefix: dict | None  # {surface, kind, spaced, span}
    tail_analyses: list[TailAnalysis]
    channel: str  # generation channel
    transform_cost: float
    transforms: tuple[str, ...]
    boundary_status: str
    proposal_score: float
    extra: dict = field(default_factory=dict)

    @property
    def best_tail(self) -> TailAnalysis | None:
        return self.tail_analyses[0] if self.tail_analyses else None


def analyze_tail(right: str, prev_char: str,
                 fst: ParticleFST) -> list[TailAnalysis]:
    """Deprecated alias for :func:`ktrf.segmentation.enumerate_tails`.

    Kept so existing callers (and the wild-tail evaluation) import one
    implementation rather than a copy of it.
    """
    return enumerate_tails(right, prev_char, fst)


def parse_matches(
    stream: CanonicalStream,
    matches: list[RawExactMatch],
    fst: ParticleFST,
) -> list[MentionProposal]:
    proposals: list[MentionProposal] = []
    units = stream.units
    for m in matches:
        first, last = m.unit_indices[0], m.unit_indices[-1]
        core_start, core_end = m.core_span
        core_last_ch = units[last].ch

        # ---- right side ----
        next_ch = units[last + 1].ch if last + 1 < len(units) else None
        latin_tail = None
        tail_analyses: list[TailAnalysis]
        right_len_units = 0
        if next_ch is not None and _script(next_ch) == "hangul" and _script(core_last_ch) != "other":
            right = _right_run(units, last)[:MAX_TAIL_LEN]
            right_len_units = len(right)
            tail_analyses = analyze_tail(right, core_last_ch, fst)
        elif next_ch is not None and _script(next_ch) == "latin" and m.profile.latin_morph:
            right = _right_run(units, last)
            latin_tail = match_latin_tail(right)
            if latin_tail:
                right_len_units = len(latin_tail[0])
                tail_analyses = [
                    TailAnalysis("", "", (), (), True,
                                 latin_tail=latin_tail[0],
                                 latin_tail_kind=latin_tail[1], score=0.95)
                ]
            else:
                tail_analyses = [TailAnalysis("", "", (), (), True, score=1.0)]
        elif next_ch in ("'", "’") and m.profile.latin_morph:
            right = _right_run(units, last)
            latin_tail = match_latin_tail(right)
            if latin_tail:
                right_len_units = len(latin_tail[0])
                tail_analyses = [
                    TailAnalysis("", "", (), (), True,
                                 latin_tail=latin_tail[0],
                                 latin_tail_kind=latin_tail[1], score=0.95)
                ]
            else:
                tail_analyses = [TailAnalysis("", "", (), (), True, score=1.0)]
        else:
            tail_analyses = [TailAnalysis("", "", (), (), True, score=1.0)]

        # ---- left side: prefix modifier (§16.6) ----
        left_text = "".join(
            u.ch for u in units[max(0, first - 6): first]
        )
        prefix = None
        pfx = match_prefix_modifier(left_text)
        if pfx:
            surface_pfx, kind, spaced = pfx
            consumed = len(surface_pfx) + (1 if spaced else 0)
            pfx_first_unit = first - consumed
            if pfx_first_unit >= 0:
                pfx_last_unit = pfx_first_unit + len(surface_pfx) - 1
                prefix = {
                    "surface": surface_pfx,
                    "kind": kind,
                    "spaced": spaced,
                    "span": (units[pfx_first_unit].raw_start,
                             units[pfx_last_unit].raw_end),
                }

        # ---- spans ----
        full_start = prefix["span"][0] if prefix else core_start
        if right_len_units:
            full_end = units[last + right_len_units].raw_end
        else:
            full_end = core_end
        best = tail_analyses[0]
        boundary_factor = 1.0 if m.boundary.status == "PASS" else 0.6
        score = max(0.05, (1.0 - min(m.transform_cost, 0.5))) * best.score * boundary_factor

        raw_surface = stream.raw_text[core_start:core_end]
        proposals.append(
            MentionProposal(
                binding_id=m.binding.alias_id,
                entity_id=m.binding.entity_id,
                family_id=m.binding.family_id,
                surface=raw_surface,
                core_span=(core_start, core_end),
                full_span=(full_start, full_end),
                matched_segments=m.matched_segments,
                prefix=prefix,
                tail_analyses=tail_analyses,
                channel="exact" if raw_surface == m.binding.surface
                and m.transform_cost == 0 else "normalized",
                transform_cost=m.transform_cost,
                transforms=m.transforms,
                boundary_status=m.boundary.status,
                proposal_score=score,
            )
        )
    return proposals
