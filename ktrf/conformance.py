"""Conformance fixture suite (spec §14.8, REQ-NRM-004..006).

Fixtures are generated deterministically from the glossary and the §14.7
variant catalog + §16 morphology catalogs. Each fixture asserts that the
binding's entity appears in the internal exact-path candidates at the
expected raw span. 100% pass is required for compile/activation
(REQ-LVL-002, REQ-NRM-005) — a failure is a release/activation blocker.

Combinatorial control (REQ-NRM-006): representative samples per transform
class, plus the full single-particle sweep and depth-2 chain representatives.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .glossary import Glossary
from .hangul import decompose_syllable, is_syllable, to_jamo_seq
from .morphology import PARTICLES, _constraint_ok
from .normalization import build_canonical_stream

# depth-2 chain representatives (§14.8: 연쇄 depth 2 대표 조합)
_CHAIN_REPRESENTATIVES = [
    ("에서", "도"), ("까지", "는"), ("만", "이라도"),
    ("에", "는"), ("부터", "는"), ("과", "의"), ("으로", "부터"),
]

_SUFFIX_REPRESENTATIVES = ["본부", "담당자", "규정"]
_PREFIX_REPRESENTATIVES = [("구", "TEMPORAL"), ("전", "TEMPORAL")]


@dataclass(frozen=True)
class Fixture:
    text: str
    expected_span: tuple[int, int]  # raw codepoint half-open core span
    entity_id: str
    alias_id: str
    transform_id: str


@dataclass
class ConformanceReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    failures: list = field(default_factory=list)


def _fullwidth(s: str) -> str:
    return "".join(
        chr(ord(c) + 0xFEE0) if 0x21 <= ord(c) <= 0x7E else c for c in s
    )


def _grammatical_particles(last_char: str) -> list[str]:
    out = []
    for p, constraint in PARTICLES.items():
        ok = _constraint_ok(constraint, last_char)
        if ok is not False:  # None (unknown, e.g. Latin core) counts as ok
            out.append(p)
    return out


def generate_fixtures(glossary: Glossary) -> list[Fixture]:
    fixtures: list[Fixture] = []

    def add(text: str, span: tuple[int, int], b, tid: str) -> None:
        fixtures.append(Fixture(text, span, b.entity_id, b.alias_id, tid))

    for b in glossary.alias_bindings:
        surface = b.surface
        if not surface:
            continue
        prof = glossary.binding_profile(b)
        n = len(surface)
        last = surface[-1]
        is_hangul_core = is_syllable(last)
        has_ascii = any(c.isascii() and c.isalnum() for c in surface)

        # T-01 identity (standalone and in context)
        add(surface, (0, n), b, "T-01")
        add(surface + " 관련 문의", (0, n), b, "T-01")

        # T-02 full-width variant
        if has_ascii and prof.width_fold != "none":
            add(_fullwidth(surface), (0, n), b, "T-02")

        # T-03 case variants
        if prof.case_fold == "ascii":
            for v in {surface.lower(), surface.upper()} - {surface}:
                add(v, (0, n), b, "T-03")

        # T-04 punctuation insertion (representative: join with each punct).
        # Surfaces already containing ignorable punctuation are skipped —
        # stacking insertions there exceeds the matcher's bounded gap run,
        # which is outside the T-04 guarantee (deletion is still covered by
        # the channel, e.g. KT&G -> KTG).
        if 2 <= n <= 4 and not any(c in prof.ignore_punctuation
                                   for c in surface):
            for p in prof.ignore_punctuation:
                v = p.join(surface)
                add(v, (0, len(v)), b, "T-04")

        # T-05 spacing insertion (tolerant profiles)
        if prof.spacing_mode == "tolerant" and n >= 2:
            mid = n // 2
            v = surface[:mid] + " " + surface[mid:]
            add(v, (0, len(v)), b, "T-05")

        # T-06 particle attachment: full single sweep + depth-2 chains
        if b.boundary_policy.right == "particle_or_token_boundary":
            for particle in _grammatical_particles(last):
                add(surface + particle, (0, n), b, "T-06")
            for p1, p2 in _CHAIN_REPRESENTATIVES:
                if _constraint_ok(PARTICLES[p1], last) is not False:
                    add(surface + p1 + p2, (0, n), b, "T-06")

        # T-07 suffix residuals (+ particle) for Hangul cores
        if is_hangul_core:
            for sfx in _SUFFIX_REPRESENTATIVES:
                add(surface + sfx, (0, n), b, "T-07")
            add(surface + "본부에서", (0, n), b, "T-07")

        # T-08 compat jamo run composition (first syllable typed as jamo)
        if is_syllable(surface[0]):
            jamo_head = to_jamo_seq(surface[0])
            # only when the head decomposes to simple jamo that recompose
            if decompose_syllable(surface[0]):
                v = jamo_head + surface[1:]
                add(v, (0, len(v)), b, "T-08")

        # T-09 zero-width character removal
        if n >= 2:
            v = surface[0] + "​" + surface[1:]
            add(v, (0, len(v)), b, "T-09")

        # T-10 prefix modifiers (Hangul-boundary cores)
        if b.boundary_policy.left == "hangul_token_boundary":
            for pfx, _kind in _PREFIX_REPRESENTATIVES:
                add(f"{pfx} {surface}", (len(pfx) + 1, len(pfx) + 1 + n), b, "T-10")
                add(f"{pfx}{surface}", (len(pfx), len(pfx) + n), b, "T-10")

        # T-11 Latin morphological tails
        if prof.latin_morph and surface[-1].isascii() and surface[-1].isalpha():
            add(surface + "s", (0, n), b, "T-11")
            add(surface + "'s", (0, n), b, "T-11")

    return fixtures


def run_fixtures(snapshot, fixtures: list[Fixture]) -> ConformanceReport:
    """Run fixtures against the snapshot's exact path (internal candidates)."""
    report = ConformanceReport(total=len(fixtures))
    for f in fixtures:
        stream = build_canonical_stream(f.text)
        matches = snapshot.exact_index.find(stream)
        ok = any(
            m.binding.entity_id == f.entity_id and m.core_span == f.expected_span
            for m in matches
        )
        if ok:
            report.passed += 1
        else:
            report.failed += 1
            report.failures.append(
                {"text": f.text, "alias_id": f.alias_id,
                 "transform": f.transform_id,
                 "expected_span": f.expected_span,
                 "got": [(m.binding.alias_id, m.core_span) for m in matches]}
            )
    return report
