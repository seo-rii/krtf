"""Variant families — the unit this evaluation counts.

Counting mentions answers "how much of the corpus did we get", and the
frequent terms decide that number. The question KTRF exists to answer is a
different one: *given a registered term, do we recover it when real text
deforms it?* That is one question per term, not one per occurrence, so the
unit here is the **variant family** — an entity together with the surfaces
it can take — and the headline is a macro average over families. A term
mentioned 500 times and a term mentioned once weigh the same, because a
glossary owner cares equally about both.

A family's surfaces come from two places, and the difference matters:

- **observed** — occurrences a plain string scan finds in the wild corpus.
  Independent of the resolver, but it only covers the deformations the
  corpus happens to contain, and never the rare ones.
- **injected** — a registered surface deformed by one typed *formation* and
  placed back into a real sentence. Reaches the rare ones on demand, at the
  cost of a synthetic surface in a genuine context.

Formations are typed against VARIANTS_PLAN §2, a specification written
before this evaluation and independent of the resolver's guard rules. Each
carries what §2 says about committing the *whole surface* to the core
entity:

``SAME``
    the whole surface is that entity; committing is the correct answer and
    withholding is a recall miss.
``CONDITIONAL``
    it may be, on evidence. Neither committing nor withholding is an error,
    so this slice reports rates and never a verdict.
``FORBIDDEN``
    the whole surface is something else (``한전노조``, ``금감원장``).
    Committing the parent to it violates invariant ②. The *core* may still
    be a candidate — that is invariant ④, and the two are measured apart.

Reading that column off the resolver's own catalog would make this a
conformance test that passes by construction. It comes from the plan
document instead, and the endings the FORBIDDEN formations use are owned
here, deliberately mixed between endings the catalog knows and endings it
does not: the contract holds either way, so a catalog change must move the
*label* numbers without moving the *violation* numbers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ktrf.hangul import (compose_syllable, decompose_syllable, hangul_to_keys,
                         to_jamo_seq)

SAME = "SAME"
CONDITIONAL = "CONDITIONAL"
FORBIDDEN = "FORBIDDEN"


@dataclass(frozen=True)
class Formation:
    """One typed way a registered surface shows up deformed in real text."""

    key: str
    contract_row: str   # the VARIANTS_PLAN §2 row this belongs to
    commit: str         # SAME | CONDITIONAL | FORBIDDEN
    tier: str           # A: deterministic normalisation/segmentation reaches it
                        # B: only a fuzzy channel does, so the guard applies
    note: str


# Endings the eval owns, on purpose. `노조`/`장`/`장관` are in the resolver's
# catalog today; `대변인`/`출입기자단`/`협력업체`/`고문` are not. Both groups
# mean the same thing for the contract — the full surface is not the
# registered entity — so a catalog change may move how well the relation is
# *labelled* and must not move whether the commit is *withheld*.
#
# The first version of this file held only these two lists, and the first
# paired run against an M3 catalog change came back **byte-identical**: the
# suite could not see catalog work at all, because every ending it used was
# one the catalog had been left without on purpose. The two lists below fix
# that without turning the suite into a conformance test — their members are
# read off a census of real post-core tails (`docs/VARIANTS_PLAN.md` M3), not
# off ``SUFFIX_CLASSES``, so the catalog has to come to them.
DERIVATIVE_ORG_ENDINGS = ("노조", "노동조합", "지부", "출입기자단",
                          "협력업체", "동호회")
DERIVATIVE_ROLE_ENDINGS = ("장", "장관", "차장", "대변인", "고문")

# 실측 tail: 이사회 ×6. The rest are the same kind of internal body, listed
# by hand before checking what the catalog knew.
ORG_UNIT_ENDINGS = ("이사회", "본부", "지사", "사무국", "지회", "분회",
                    "대책위", "출장소")
# 실측 tail: 법 ×26, 판결 ×8, 고시 ×5, 훈령 ×2, 조례 ×2, 규칙 ×2.
ARTIFACT_ENDINGS = ("법", "판결", "고시", "훈령", "조례", "규칙",
                    "지침", "예규", "요강")

# §16.6 temporal/naming modifiers, quoted from the plan, not imported: the
# point is to test the resolver against the spec's list.
BASE_MODIFIERS = ("전", "현", "구", "신")

_PARTICLES_BATCHIM = ("은", "이", "을", "과", "으로")
_PARTICLES_OPEN = ("는", "가", "를", "와", "로")
_CHAINS_ANY = ("에서도", "에서는", "에게도", "까지도", "부터는", "만큼도")

_VOWELS = "ㅏㅐㅑㅓㅔㅕㅗㅛㅜㅠㅡㅣ"


def _has_batchim(ch: str) -> bool:
    d = decompose_syllable(ch)
    return bool(d and d[2])


def _particle_for(core: str, rng: random.Random) -> str:
    pool = _PARTICLES_BATCHIM if _has_batchim(core[-1]) else _PARTICLES_OPEN
    return rng.choice(pool)


def _all_hangul(s: str) -> bool:
    return bool(s) and all("가" <= c <= "힣" for c in s)


def _single_jamo_typo(core: str, rng: random.Random) -> str | None:
    """Perturb one 중성 of one syllable — the §17.2 near-miss class."""
    idxs = [i for i, c in enumerate(core) if decompose_syllable(c)]
    for i in rng.sample(idxs, len(idxs)) if idxs else ():
        cho, jung, jong = decompose_syllable(core[i])
        alt = [v for v in _VOWELS if v != jung]
        out = compose_syllable(cho, rng.choice(alt), jong) if alt else None
        if out and out != core[i]:
            return core[:i] + out + core[i + 1:]
    return None


# --------------------------------------------------------------------------
# Generators: (surface, rng) -> (token, core_offset, core_text) or None
#
# ``None`` means the formation does not apply to this surface — a Latin
# acronym has no 중성 to perturb, a Hangul name has no halfwidth form. That
# is why the macro average is taken over *applicable* formations per family
# rather than over a fixed grid: pretending an inapplicable cell is a miss
# would punish families for their script.
# --------------------------------------------------------------------------

def _gen_bare(s, rng):
    return (s, 0, s)


def _gen_particle(s, rng):
    if not _all_hangul(s):
        return None
    return (s + _particle_for(s, rng), 0, s)


def _gen_particle_chain(s, rng):
    if not _all_hangul(s):
        return None
    return (s + rng.choice(_CHAINS_ANY), 0, s)


def _gen_spaced(s, rng):
    """`한 전` — an equivalent surface under the spacing profile (§2 row 1)."""
    if len(s) < 2:
        return None
    i = rng.randrange(1, len(s))
    spaced = s[:i] + " " + s[i:]
    return (spaced, 0, spaced)


def _gen_fullwidth(s, rng):
    """`ＡＰ` — width folding, so only surfaces with ASCII qualify."""
    if not any(c.isascii() and c.isalnum() for c in s):
        return None
    wide = "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in s)
    return (wide, 0, wide)


def _gen_typo(s, rng):
    t = _single_jamo_typo(s, rng) if _all_hangul(s) else None
    return None if t is None else (t, 0, t)


def _gen_typo_particle(s, rng):
    t = _single_jamo_typo(s, rng) if _all_hangul(s) else None
    return None if t is None else (t + _particle_for(t, rng), 0, t)


def _gen_keyboard(s, rng):
    """영타 오입력 — the whole surface typed in English mode (§17.4)."""
    if not _all_hangul(s):
        return None
    keys = hangul_to_keys(s)
    return None if not keys.isascii() else (keys, 0, keys)


def _gen_jamo(s, rng):
    """Broken IME / copy-paste leaves a bare compat-jamo run (T-08)."""
    if not _all_hangul(s):
        return None
    j = to_jamo_seq(s)
    return None if j == s else (j, 0, j)


def _gen_base_modifier(s, rng):
    """`전 한전` — §2 leaves the full surface conditional, not equal."""
    if not _all_hangul(s):
        return None
    token = rng.choice(BASE_MODIFIERS) + " " + s
    return (token, len(token) - len(s), s)


def _gen_derivative_org(s, rng):
    if not _all_hangul(s):
        return None
    return (s + rng.choice(DERIVATIVE_ORG_ENDINGS), 0, s)


def _gen_derivative_role(s, rng):
    if not _all_hangul(s) or s[-1] == "장":
        return None
    return (s + rng.choice(DERIVATIVE_ROLE_ENDINGS), 0, s)


def _gen_org_unit(s, rng):
    """`한전본부` — a body inside the org: the core is mentioned, the whole is not."""
    if not _all_hangul(s):
        return None
    return (s + rng.choice(ORG_UNIT_ENDINGS), 0, s)


def _gen_artifact(s, rng):
    """`한국은행법` — a document *of* the org, not the org (실측 tail 1위)."""
    if not _all_hangul(s):
        return None
    return (s + rng.choice(ARTIFACT_ENDINGS), 0, s)


def _gen_derivative_particle(s, rng):
    """The derivative inflected — the case a bare-token index cannot see."""
    if not _all_hangul(s):
        return None
    end = rng.choice(DERIVATIVE_ORG_ENDINGS + DERIVATIVE_ROLE_ENDINGS)
    return (s + end + _particle_for(end, rng), 0, s)


FORMATIONS: tuple[Formation, ...] = (
    Formation("bare", "동등 표면형", SAME, "A",
              "the registered surface itself — the floor for everything else"),
    Formation("spaced", "동등 표면형", SAME, "A",
              "`한 전`: spacing is not part of the name"),
    Formation("fullwidth", "동등 표면형", SAME, "A",
              "`ＡＰ`: width folding, Latin-bearing surfaces only"),
    Formation("particle", "굴절", SAME, "A",
              "조사 1개 — the commonest deformation in Korean prose"),
    Formation("particle_chain", "굴절", SAME, "A",
              "조사 연쇄 (`에서도`) — §16.2 depth > 1"),
    Formation("typo", "제한된 오타", CONDITIONAL, "B",
              "one 중성 perturbed (§17.2)"),
    Formation("typo_particle", "제한된 오타", CONDITIONAL, "B",
              "typo *and* 조사 — the M1 failure, kept as a regression guard"),
    Formation("keyboard", "제한된 오타", CONDITIONAL, "B",
              "영타 오입력: the whole surface as dubeolsik keys (§17.4)"),
    Formation("jamo", "동등 표면형", SAME, "A",
              "compat-jamo run from a broken IME (T-08)"),
    Formation("base_modifier", "base modifier", CONDITIONAL, "A",
              "`전 한전`: §2 says conditional, so this slice has no verdict"),
    Formation("derivative_org", "관련 파생", FORBIDDEN, "A",
              "`한전노조` is a different organisation (invariant ②)"),
    Formation("derivative_role", "관련 파생", FORBIDDEN, "A",
              "`금감원장` is a person (invariant ②)"),
    Formation("derivative_particle", "관련 파생", FORBIDDEN, "A",
              "the derivative inflected — must be blocked through 조사 too"),
    Formation("org_unit", "관련 파생", FORBIDDEN, "A",
              "`한전본부`: a body inside the org is not the org (실측 이사회)"),
    Formation("artifact", "관련 파생", FORBIDDEN, "A",
              "`한국은행법`: the document is not the organisation (실측 1위)"),
)

_GENERATORS = {
    "bare": _gen_bare, "spaced": _gen_spaced, "fullwidth": _gen_fullwidth,
    "particle": _gen_particle, "particle_chain": _gen_particle_chain,
    "typo": _gen_typo, "typo_particle": _gen_typo_particle,
    "keyboard": _gen_keyboard, "jamo": _gen_jamo,
    "base_modifier": _gen_base_modifier,
    "derivative_org": _gen_derivative_org,
    "derivative_role": _gen_derivative_role,
    "derivative_particle": _gen_derivative_particle,
    "org_unit": _gen_org_unit, "artifact": _gen_artifact,
}

BY_KEY = {f.key: f for f in FORMATIONS}
assert set(BY_KEY) == set(_GENERATORS)


@dataclass
class VariantCase:
    """One deformed surface placed in one real sentence."""

    entity_id: str          # the family this case belongs to
    formation: str
    registered: str         # the surface as the glossary holds it
    text: str               # a real sentence with the deformation in it
    token: str              # the deformed token as written
    core: str               # what the resolver's core span should cover
    core_span: tuple[int, int]
    full_span: tuple[int, int]   # token span; wider than core for derivatives

    @property
    def commit_contract(self) -> str:
        return BY_KEY[self.formation].commit


@dataclass
class FamilyPlan:
    """The registered surfaces of one entity, as the case builder sees them."""

    entity_id: str
    surfaces: list[str] = field(default_factory=list)


def family_plans(glossary, min_len: int = 2) -> list[FamilyPlan]:
    """Group registered surfaces by entity — one family per registered term.

    ``kind`` is not filtered: an abbreviation is as much a way the term
    appears as its full name, and a family whose only realistic surface is
    an abbreviation should not drop out of the denominator.
    """
    by_entity: dict[str, list[str]] = {}
    for b in glossary.alias_bindings:
        if len(b.surface) >= min_len:
            by_entity.setdefault(b.entity_id, []).append(b.surface)
    return [FamilyPlan(eid, sorted(set(s)))
            for eid, s in sorted(by_entity.items())]


def usable_hosts(corpus, lo: int = 20, hi: int = 160) -> list[str]:
    return [r["text"] for r in corpus if lo <= len(r["text"]) <= hi]


def place(token: str, host: str) -> tuple[str, int]:
    """Put ``token`` at a clean left boundary inside a real sentence.

    The deformation is synthetic; the context around it is not. Splitting at
    the host's first space usually keeps the token off position zero, so a
    resolver that only worked at the start of a string could not pass by
    accident. A host with no space in its first 40 characters falls back to
    position zero rather than being dropped — losing the case would bias the
    sample toward sentences that happen to be spaced a particular way.
    """
    cut = host.find(" ")
    prefix = host[:cut + 1] if 0 < cut < 40 else ""
    rest = host[cut + 1:] if prefix else host
    return f"{prefix}{token} {rest}", len(prefix)


def build_cases(corpus, glossary, per_cell: int = 2,
                seed: int = 20260901,
                formations: tuple[str, ...] | None = None) -> list[VariantCase]:
    """One case per (family, formation, repeat), over real host sentences.

    Every family is visited for every formation, so the macro average has a
    denominator that does not depend on which terms the corpus happens to
    mention. Inapplicable cells are simply absent rather than scored zero.
    """
    rng = random.Random(seed)
    hosts = usable_hosts(corpus)
    rng.shuffle(hosts)
    keys = formations or tuple(f.key for f in FORMATIONS)
    cases: list[VariantCase] = []
    hi = 0
    for plan in family_plans(glossary):
        for key in keys:
            gen = _GENERATORS[key]
            made = 0
            for surface in rng.sample(plan.surfaces, len(plan.surfaces)):
                if made >= per_cell:
                    break
                out = gen(surface, rng)
                if out is None:
                    continue
                token, off, core = out
                # a host already containing the surface would leave two
                # candidate spans for one gold answer
                for _ in range(len(hosts)):
                    host = hosts[hi % len(hosts)]
                    hi += 1
                    if surface not in host and core not in host:
                        break
                else:  # pragma: no cover - corpus is far larger than this
                    continue
                text, start = place(token, host)
                cases.append(VariantCase(
                    entity_id=plan.entity_id, formation=key,
                    registered=surface, text=text, token=token, core=core,
                    core_span=(start + off, start + off + len(core)),
                    full_span=(start, start + len(token)),
                ))
                made += 1
    return cases
