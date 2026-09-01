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

from .hangul import decompose_syllable, is_syllable

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
    # M3 실측: `서`(=에서)는 헤드라인체에서 흔하고 미포함 tail 중 두 번째로
    # 잦았다(1,970건 중 14: 국정원서, 방통위서, 외교부서). TOKEN_FINAL 제약이
    # 붙는다 — 아래를 볼 것.
    "서": ANY,
    # 합쇼체 계사 (실측 2). `이다` 계열이 이미 있으므로 그 자리에 맞춘다.
    "입니다": ANY, "입니까": ANY,
}

# §16.2 조사이되 **한글이 더 이어지면 조사가 아닌** 것.
#
# `서`를 그냥 넣으면 `서울본부`가 조사 `서`로 시작하는 것처럼 보이고,
# `한전서울본부`의 경계 판정이 SOFT에서 PASS로 풀린다. 한 음절 조사는 원래
# 명사 첫 음절과 겹치지만(`도`시, `과`학) `서`는 겹치는 명사가 유난히 흔해서
# — 서울·서비스·서류 — 그 완화가 카탈로그 전체로 번진다.
#
# 실제 용법은 그 자리에서 어절이 끝난다: `국정원서 발표`. 그래서 뒤에 한글
# 음절이 더 오면 조사로 읽지 않는다. 14건은 그대로 얻고 `서울`은 잃지 않는다.
TOKEN_FINAL_PARTICLES: frozenset[str] = frozenset({"서"})

# §16.3 기관·역할 suffix catalog (초기), typed by what the *full* surface denotes.
#
# VARIANTS_PLAN §2: a suffix is not just a boundary marker. `금감원` + `장` is a
# person, `한전` + `노조` is a different organisation, `기획재정` + `부` is the
# same organisation. Collapsing all three into one SUFFIX class is what lets a
# consumer read the whole token as the core entity (invariant ②).
#
# Membership is measured, not guessed: the M3 entries carry the count they
# had in a census of 1,970 real post-core tails (eval/run_wild §2 reports the
# same census as coverage). Entries without a count are closed-set siblings of
# a counted one — every 행정규범 type beside the four that were observed —
# and are marked as such so a later reader can tell evidence from taxonomy.
#
# Getting a class wrong is not symmetric. NAME_PART and REFERENTIAL say SAME,
# which *allows* a commit on the whole surface; every other class says
# DISTINCT, which only withholds. So an ending goes in the SAME group only
# when the shorter form is genuinely the same organisation's short name
# (`한국전력`/`한국전력공사`), and anything arguable goes in AFFILIATE —
# which is why `은행` sits beside `증권`, `카드`, `생명` rather than with
# `공사`: 신한은행 and 신한카드 are siblings, not the same body.
NAME_PART = "NAME_PART"      # tail syllables of the org's own name
ORG_UNIT = "ORG_UNIT"        # an internal unit of the core org
ROLE = "ROLE"                # the office holder — a person, not the org
AFFILIATE = "AFFILIATE"      # a separate org sharing the core's name
DERIVED_ORG = "DERIVED_ORG"  # a related but independent organisation
REFERENTIAL = "REFERENTIAL"  # a proxy reference *to* the core org
ARTIFACT = "ARTIFACT"        # a document/system belonging to the core org
MODIFIER = "MODIFIER"        # §16.3 leading modifier inside a residual
UNKNOWN_CLASS = "UNKNOWN"

# class -> (does the full surface denote the core entity?, core→full relation)
SAME, DISTINCT, UNRESOLVED = "SAME", "DISTINCT", "UNKNOWN"
TAIL_CLASSES: dict[str, tuple[str, str]] = {
    NAME_PART: (SAME, "IDENTITY"),
    REFERENTIAL: (SAME, "REFERS_TO"),
    ORG_UNIT: (DISTINCT, "PART_OF"),
    ROLE: (DISTINCT, "ROLE_OF"),
    AFFILIATE: (DISTINCT, "AFFILIATE_OF"),
    DERIVED_ORG: (DISTINCT, "DERIVED_FROM"),
    ARTIFACT: (DISTINCT, "ARTIFACT_OF"),
    MODIFIER: (DISTINCT, "NAMED_VARIANT"),
    UNKNOWN_CLASS: (UNRESOLVED, "UNKNOWN"),
}

SUFFIX_CLASSES: dict[str, str] = {
    # 기관명 자체의 끝음절 — 같은 기관을 가리킨다
    "부": NAME_PART, "처": NAME_PART, "청": NAME_PART, "원": NAME_PART,
    "국": NAME_PART, "실": NAME_PART, "과": NAME_PART, "팀": NAME_PART,
    "위원회": NAME_PART,
    # 다음절 기관 종결어 (M3). `한국전력` + `공사`는 한국전력공사이지 그 계열사가
    # 아니다 — 짧은 쪽은 같은 조직의 통칭이다. `공단`은 M2까지 AFFILIATE였는데,
    # 그 분류라면 `국민연금` + `공단`이 국민연금공단과 다른 조직이 된다.
    "공사": NAME_PART, "공단": NAME_PART,
    # 내부 조직 — 부분이지 전체가 아니다
    "본부": ORG_UNIT, "지사": ORG_UNIT, "센터": ORG_UNIT,
    "사무국": ORG_UNIT, "연구원": ORG_UNIT, "연구소": ORG_UNIT,
    "이사회": ORG_UNIT,                                    # 실측 6
    "사무처": ORG_UNIT, "지회": ORG_UNIT, "분회": ORG_UNIT,
    "지점": ORG_UNIT, "출장소": ORG_UNIT,
    # 직책 — 사람이다 (wild-corpus 실측으로 추가된 항목)
    "장": ROLE, "장관": ROLE, "차관": ROLE, "청장": ROLE,
    "원장": ROLE, "위원장": ROLE, "총장": ROLE,
    "사장": ROLE, "회장": ROLE, "이사장": ROLE, "대표": ROLE,
    "담당자": ROLE, "직원": ROLE,
    # 계열·동명 기관 — 이름을 공유하는 별도 조직
    "그룹": AFFILIATE, "증권": AFFILIATE, "카드": AFFILIATE,
    "생명": AFFILIATE, "전자": AFFILIATE, "건설": AFFILIATE,
    "병원": AFFILIATE, "대학": AFFILIATE, "재단": AFFILIATE,
    "협회": AFFILIATE,
    "교향악단": AFFILIATE, "서비스": AFFILIATE, "써비스": AFFILIATE,
    "헬스케어": AFFILIATE, "케미칼": AFFILIATE, "네트웍스": AFFILIATE,
    "투자": AFFILIATE, "리츠": AFFILIATE, "제약": AFFILIATE,
    "미디어": AFFILIATE, "몰": AFFILIATE, "기술": AFFILIATE,   # 이상 실측
    "은행": AFFILIATE, "홀딩스": AFFILIATE, "화학": AFFILIATE,
    "중공업": AFFILIATE, "물산": AFFILIATE, "해운": AFFILIATE,
    "캐피탈": AFFILIATE, "자산운용": AFFILIATE, "화재": AFFILIATE,
    # 관련 파생 조직 — VARIANTS_PLAN §2의 `한전노조` 사례
    "노조": DERIVED_ORG, "노동조합": DERIVED_ORG,
    # 지시적 — 여전히 그 기관을 가리킨다
    #
    # `내`(內)는 실측 2건이 있었지만 넣지 않았다. REFERENTIAL은 SAME이라
    # 전체 표면형의 **확정을 허용**하는데, `서울시내`는 서울시가 아니라
    # 서울 시내다 — `eval/run_wild.py`의 DETECTION_ONLY가 이미 그 충돌을
    # 이유로 서울시를 재현율 분모에서 빼고 있다. 2건을 얻자고 SAME 쪽으로
    # 넣을 근거가 못 된다.
    "측": REFERENTIAL,
    # 산물 — 기관이 아니라 기관의 것
    "규정": ARTIFACT, "시스템": ARTIFACT,
    "법": ARTIFACT, "법안": ARTIFACT, "판결": ARTIFACT,      # 실측 26/8
    "고시": ARTIFACT, "훈령": ARTIFACT, "조례": ARTIFACT,    # 실측 5/2/2
    "규칙": ARTIFACT,                                        # 실측 2
    "시행령": ARTIFACT, "시행규칙": ARTIFACT, "지침": ARTIFACT,
    "예규": ARTIFACT, "공고": ARTIFACT, "약관": ARTIFACT,
    "정관": ARTIFACT,
}

# §16.3 문맥 의존 종결어 (M3). 한 철자에 두 뜻이 있고, **core가 무엇으로
# 끝나는지**가 그것을 가른다: 도 뒤의 `지사`는 知事(사람)이고 회사 뒤의
# `지사`는 支社(지점)다. 두 해석 모두 DISTINCT라 commit 안전성은 어느 쪽이든
# 같다 — 갈리는 것은 relation 라벨뿐이라, 작은 표로 충분하고 파서는 필요 없다.
# 규칙은 잔여부의 **맨 왼쪽** part에만 적용된다. 그 자리만이 core와 맞닿는다.
CONTEXTUAL_SUFFIX_CLASSES: dict[str, tuple[tuple[str, ...], str, str]] = {
    # 종결어 -> (첫 class를 고르는 core 끝음절, 그때의 class, 그 밖의 class)
    "지사": (("도",), ROLE, ORG_UNIT),
}

# the untyped view, kept because it is part of this module's public
# surface (§16.3); nothing inside KTRF reads it any more
SUFFIXES: frozenset[str] = frozenset(SUFFIX_CLASSES)

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
        soft signal (§16.2), so the boundary stays permissive. The one thing
        that *is* enforced is :data:`TOKEN_FINAL_PARTICLES` — a particle that
        only exists at the end of an 어절 is not a boundary when more Hangul
        follows it.
        """
        for p in self._by_first.get(s[:1], ()):
            if s.startswith(p) and self._final_ok(p, s[len(p):]):
                return True
        return False

    @staticmethod
    def _final_ok(particle: str, rest: str) -> bool:
        return (particle not in TOKEN_FINAL_PARTICLES
                or not rest or not is_syllable(rest[0]))

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
                if not self._final_ok(p, rest[len(p):]):
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
    """A classified post-core chunk: what it is made of and what it implies.

    ``kind`` answers "did the catalog explain this chunk"; ``classes`` and
    :attr:`full_identity` answer the semantic question the resolver actually
    needs — whether ``core + residual`` still denotes the core entity.
    """

    text: str
    kind: str  # SUFFIX | SUFFIX_WITH_MODIFIER | UNKNOWN
    parts: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()

    @property
    def head_class(self) -> str:
        """Class of the rightmost part — Korean compounds are head-final."""
        return self.classes[-1] if self.classes else NAME_PART

    @property
    def governing_class(self) -> str:
        """The part that decides identity: the rightmost *distinct* one.

        Head-final governs the relation, but not the verdict. `은행장과`
        decomposes as 장 + 과 and its head 과 is a NAME_PART, so a head-only
        rule calls the whole thing the bank — while the 장 in the middle
        already made it a person. Once any part says "not the core", no
        later part can take that back.
        """
        for cls in reversed(self.classes):
            if TAIL_CLASSES.get(cls, (SAME, ""))[0] == DISTINCT:
                return cls
        return self.head_class

    @property
    def full_identity(self) -> str:
        """SAME | DISTINCT | UNKNOWN for ``core + residual`` vs the core.

        A leading modifier always makes the whole a distinct name
        (``서울본부``), even when the head alone would be a name part —
        :attr:`governing_class` carries that, because MODIFIER is itself a
        DISTINCT class sitting leftmost, so it is the fallback when no part
        to its right objects.
        """
        if not self.text:
            return SAME
        if self.kind == "UNKNOWN":
            return UNRESOLVED
        return TAIL_CLASSES.get(self.governing_class, (UNRESOLVED, ""))[0]

    @property
    def relation(self) -> str:
        """How the full surface relates to the core entity.

        Read off the same part the verdict came from. Short-circuiting a
        modifier to NAMED_VARIANT here is what made `한국투자증권` report
        ``tail_class=AFFILIATE`` beside ``relation=NAMED_VARIANT``: the
        modifier says the *name* differs, but 증권 still says how the two
        organisations relate, and that is the more specific answer.
        """
        if not self.text:
            return "IDENTITY"
        if self.kind == "UNKNOWN":
            return "UNKNOWN"
        return TAIL_CLASSES.get(self.governing_class, ("", "UNKNOWN"))[1]


def classify_suffix(part: str, core_end: str = "") -> str:
    """Semantic class of one catalog suffix (MODIFIER when uncatalogued).

    ``core_end`` is the character the core ends in, and only matters for the
    handful of endings in :data:`CONTEXTUAL_SUFFIX_CLASSES`. Callers that do
    not have it get the context-free reading, which is the safer of the two
    for every entry in that table.
    """
    ctx = CONTEXTUAL_SUFFIX_CLASSES.get(part)
    if ctx is not None and core_end:
        endings, when, otherwise = ctx
        return when if core_end.endswith(endings) else otherwise
    return SUFFIX_CLASSES.get(part, MODIFIER)


def _classes(parts, core_end: str) -> tuple[str, ...]:
    """Class each part, giving only the leftmost one the core as context."""
    return tuple(classify_suffix(p, core_end if i == 0 else "")
                 for i, p in enumerate(parts))


def analyze_residual(chunk: str, core_end: str = "") -> ResidualAnalysis:
    """Classify a post-core Hangul chunk (residual, §7.6/§16.3).

    - decomposes fully into catalog suffixes -> SUFFIX (예: 본부, 담당자)
    - ends with a catalog suffix after a short modifier -> SUFFIX_WITH_MODIFIER
      (예: 서울본부 = 서울 + 본부)
    - otherwise UNKNOWN (kept at low confidence, §16.5)

    Every part carries its :data:`SUFFIX_CLASSES` class so callers read the
    semantics off the analysis instead of re-deriving them from the surface.
    ``core_end`` is the last character of the core, passed through for the
    context-dependent endings; omitting it costs a label, never safety.
    """
    if not chunk:
        return ResidualAnalysis("", "SUFFIX", (), ())
    parts = _suffix_decompose(chunk)
    if parts is not None:
        return ResidualAnalysis(chunk, "SUFFIX", tuple(parts),
                                _classes(parts, core_end))
    # longest catalog suffix at the end, with a short leading modifier
    for cut in range(1, len(chunk)):
        tail_parts = _suffix_decompose(chunk[cut:])
        if tail_parts is not None and cut <= 4:
            all_parts = (chunk[:cut], *tail_parts)
            # the modifier, not the core, is what the suffix now sits behind
            return ResidualAnalysis(
                chunk, "SUFFIX_WITH_MODIFIER", all_parts,
                (MODIFIER, *_classes(tail_parts, chunk[:cut])),
            )
    return ResidualAnalysis(chunk, "UNKNOWN", (chunk,), (UNKNOWN_CLASS,))


def _suffix_decompose(chunk: str) -> list[str] | None:
    """Greedy longest-first decomposition into catalog suffixes."""
    if not chunk:
        return []
    for length in range(min(len(chunk), 4), 0, -1):
        head = chunk[:length]
        if head in SUFFIX_CLASSES:
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
