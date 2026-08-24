"""Morphology catalogs and the particle FST (spec §16).

- Single-particle catalog with batchim allomorph constraints (§16.2)
- Particle chains via composition with a depth cap, never enumeration
  (REQ-TAIL-001; default depth 3, §52.13 / OQ-001)
- Institutional/role suffix catalog (§16.3)
- Prefix modifier catalog (§16.6)
- Latin morphological tails (§16.7)

Ungrammatical batchim combinations are not hard-rejected; they parse with
``grammatical=False`` so ranking can down-weight them (§16.2).
"""

from __future__ import annotations

from dataclasses import dataclass

from .hangul import decompose_syllable

# batchim constraint classes
ANY = "ANY"
BATCHIM = "BATCHIM"  # requires 받침
NO_BATCHIM = "NO_BATCHIM"  # requires no 받침
RIEUL_OR_NO_BATCHIM = "RIEUL_OR_NO_BATCHIM"  # 로-family
BATCHIM_NOT_RIEUL = "BATCHIM_NOT_RIEUL"  # 으로-family

# §16.2 single-particle catalog (초기)
PARTICLES: dict[str, str] = {
    # 격·보조
    "은": BATCHIM, "는": NO_BATCHIM,
    "이": BATCHIM, "가": NO_BATCHIM,
    "을": BATCHIM, "를": NO_BATCHIM,
    "과": BATCHIM, "와": NO_BATCHIM,
    "의": ANY,
    "도": ANY, "만": ANY, "뿐": ANY, "밖에": ANY, "조차": ANY, "마저": ANY,
    "마다": ANY, "대로": ANY, "만큼": ANY,
    "처럼": ANY, "보다": ANY, "같이": ANY, "부터": ANY, "까지": ANY,
    # 부사격
    "에": ANY, "에서": ANY, "에게": ANY, "에게서": ANY,
    "한테": ANY, "한테서": ANY, "께": ANY, "께서": ANY,
    "으로": BATCHIM_NOT_RIEUL, "로": RIEUL_OR_NO_BATCHIM,
    "으로서": BATCHIM_NOT_RIEUL, "로서": RIEUL_OR_NO_BATCHIM,
    "으로써": BATCHIM_NOT_RIEUL, "로써": RIEUL_OR_NO_BATCHIM,
    "이랑": BATCHIM, "랑": NO_BATCHIM,
    "하고": ANY,
    "이나": BATCHIM, "나": NO_BATCHIM,
    "이든": BATCHIM, "든": NO_BATCHIM,
    "이라도": BATCHIM, "라도": NO_BATCHIM,
    "이야": BATCHIM, "야": NO_BATCHIM,
    # 계사·종결 (초기)
    "이다": ANY, "인": ANY, "이라": ANY, "이면": ANY,
    "였다": NO_BATCHIM, "임": ANY, "이며": ANY, "이고": ANY,
    # 축약형 — wild-corpus 실측(§3.5 분포 커버리지 신호)으로 추가:
    # 엔(=에는), 에선(=에서는), 껜(=께는)
    "엔": ANY, "에선": ANY, "껜": ANY,
}

# §16.3 기관·역할 suffix catalog (초기)
SUFFIXES: set[str] = {
    "부", "처", "청", "원", "국", "실", "과", "팀",
    "본부", "지사", "센터", "사무국",
    "연구원", "연구소", "위원회",
    "병원", "대학", "재단", "협회", "공단",
    "담당자", "직원", "측", "규정", "시스템",
    # 직책 suffix — wild-corpus 실측으로 추가 (금감원장, 기상청장, 교육부 장관류)
    "장", "장관", "차관", "청장", "원장", "위원장", "총장",
    "사장", "회장", "이사장", "대표",
    # 기업 계열 suffix — wild-corpus 실측으로 추가 (현대차그룹, ○○증권)
    "그룹", "증권", "카드", "생명", "전자", "건설",
}

# §16.6 prefix modifier catalog (초기)
PREFIXES: dict[str, str] = {
    "구": "TEMPORAL", "신": "TEMPORAL", "전": "TEMPORAL", "현": "TEMPORAL",
    "舊": "TEMPORAL", "新": "TEMPORAL", "前": "TEMPORAL", "現": "TEMPORAL",
    "가칭": "NAMING", "약칭": "NAMING", "이른바": "NAMING",
}

# §16.7 Latin morphological tails
LATIN_TAILS: dict[str, str] = {
    "'s": "LATIN_POSSESSIVE", "’s": "LATIN_POSSESSIVE",
    "es": "LATIN_PLURAL", "s": "LATIN_PLURAL",
}

DEFAULT_CHAIN_DEPTH = 3  # §16.2, config; OQ-001


def _constraint_ok(constraint: str, prev_char: str) -> bool | None:
    """Check a batchim constraint against the preceding character.

    Returns True/False for Hangul syllables, None (= unknown, treated as
    satisfied) for non-Hangul cores such as Latin acronyms ("AP에서").
    """
    d = decompose_syllable(prev_char) if prev_char else None
    if d is None:
        return None
    jong = d[2]
    if constraint == ANY:
        return True
    if constraint == BATCHIM:
        return jong != ""
    if constraint == NO_BATCHIM:
        return jong == ""
    if constraint == RIEUL_OR_NO_BATCHIM:
        return jong in ("", "ㄹ")
    if constraint == BATCHIM_NOT_RIEUL:
        return jong not in ("", "ㄹ")
    return True


@dataclass(frozen=True)
class ParticleParse:
    particles: tuple[str, ...]
    grammatical: bool
    consumed: int  # total characters consumed


class ParticleFST:
    """Composed particle chains over the single-particle catalog.

    A read-only shared component (§15.5/REQ-BND-003): the boundary checker
    only calls :meth:`accepts_prefix`; full decomposition is done by the tail
    parser via :meth:`parse_full` / :meth:`parse_prefixes`.
    """

    def __init__(self, particles: dict[str, str] | None = None,
                 max_depth: int = DEFAULT_CHAIN_DEPTH):
        self.particles = dict(particles or PARTICLES)
        self.max_depth = max_depth
        self._by_first: dict[str, list[str]] = {}
        for p in self.particles:
            self._by_first.setdefault(p[0], []).append(p)
        for lst in self._by_first.values():
            lst.sort(key=len, reverse=True)

    # -- boundary interface (prefix-accept only, REQ-BND-002/003) -----------

    def accepts_prefix(self, s: str, prev_char: str = "") -> bool:
        """True if some catalog particle is a prefix of ``s``.

        Grammaticality is NOT enforced here: ungrammatical attachment is a
        soft signal (§16.2), so the boundary stays permissive.
        """
        for p in self._by_first.get(s[:1], ()):
            if s.startswith(p):
                return True
        return False

    # -- parsing interface ---------------------------------------------------

    def parse_full(self, s: str, prev_char: str = "") -> list[ParticleParse]:
        """All decompositions of the *entire* string into a particle chain."""
        return [p for p in self._parse(s, prev_char) if p.consumed == len(s)]

    def parse_prefixes(self, s: str, prev_char: str = "") -> list[ParticleParse]:
        """All decompositions of any nonempty prefix of ``s`` into a chain."""
        return self._parse(s, prev_char)

    def _parse(self, s: str, prev_char: str) -> list[ParticleParse]:
        results: list[ParticleParse] = []
        seen: set[tuple[tuple[str, ...], int]] = set()

        def dfs(pos: int, prev: str, chain: tuple[str, ...], grammatical: bool):
            if len(chain) >= self.max_depth:
                return
            rest = s[pos:]
            for p in self._by_first.get(rest[:1], ()):
                if not rest.startswith(p):
                    continue
                ok = _constraint_ok(self.particles[p], prev)
                g2 = grammatical and (ok is not False)
                new_chain = chain + (p,)
                key = (new_chain, pos + len(p))
                if key in seen:
                    continue
                seen.add(key)
                results.append(ParticleParse(new_chain, g2, pos + len(p)))
                dfs(pos + len(p), p[-1], new_chain, g2)

        if s:
            dfs(0, prev_char, (), True)
        return results


@dataclass(frozen=True)
class ResidualAnalysis:
    text: str
    kind: str  # SUFFIX | SUFFIX_WITH_MODIFIER | UNKNOWN
    parts: tuple[str, ...] = ()


def analyze_residual(chunk: str) -> ResidualAnalysis:
    """Classify a post-core Hangul chunk (residual, §7.6/§16.3).

    - decomposes fully into catalog suffixes -> SUFFIX (예: 본부, 담당자)
    - ends with a catalog suffix after a short modifier -> SUFFIX_WITH_MODIFIER
      (예: 서울본부 = 서울 + 본부)
    - otherwise UNKNOWN (kept at low confidence, §16.5)
    """
    if not chunk:
        return ResidualAnalysis("", "SUFFIX", ())
    parts = _suffix_decompose(chunk)
    if parts is not None:
        return ResidualAnalysis(chunk, "SUFFIX", tuple(parts))
    # longest catalog suffix at the end, with a short leading modifier
    for cut in range(1, len(chunk)):
        tail_parts = _suffix_decompose(chunk[cut:])
        if tail_parts is not None and cut <= 4:
            return ResidualAnalysis(
                chunk, "SUFFIX_WITH_MODIFIER", (chunk[:cut], *tail_parts)
            )
    return ResidualAnalysis(chunk, "UNKNOWN", (chunk,))


def _suffix_decompose(chunk: str) -> list[str] | None:
    """Greedy longest-first decomposition into catalog suffixes."""
    if not chunk:
        return []
    for length in range(min(len(chunk), 4), 0, -1):
        head = chunk[:length]
        if head in SUFFIXES:
            rest = _suffix_decompose(chunk[length:])
            if rest is not None:
                return [head, *rest]
    return None


def match_prefix_modifier(left_context: str) -> tuple[str, str, bool] | None:
    """Detect a prefix modifier immediately before a core (§16.6).

    ``left_context`` is the text immediately preceding the core span.
    Returns (prefix_surface, kind, spaced) or None. Handles both
    "구 한전" (spaced) and "구한전" (unspaced).
    """
    for pfx, kind in sorted(PREFIXES.items(), key=lambda kv: -len(kv[0])):
        if left_context.endswith(pfx + " "):
            before = left_context[: -len(pfx) - 1]
            if _token_start_ok(before):
                return pfx, kind, True
        if left_context.endswith(pfx):
            before = left_context[: -len(pfx)]
            if _token_start_ok(before):
                return pfx, kind, False
    return None


def _token_start_ok(before: str) -> bool:
    if not before:
        return True
    last = before[-1]
    return not (("가" <= last <= "힣") or last.isalnum())


def match_latin_tail(right_context: str) -> tuple[str, str] | None:
    """Detect a Latin morphological tail (s/es/'s) at a token end (§16.7)."""
    for tail, kind in LATIN_TAILS.items():
        if right_context.startswith(tail):
            after = right_context[len(tail):]
            if not after or not (after[0].isascii() and after[0].isalnum()):
                return tail, kind
    return None
