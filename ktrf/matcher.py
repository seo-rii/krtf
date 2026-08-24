"""Exact alias matcher and boundary policies (spec §15).

Bindings are grouped by effective normalization profile signature; each group
shares one search channel (§14.3) and one Aho-Corasick automaton over the
normalized alias keys. Matches map back to raw spans through canonical-unit
provenance (INV-012), keep every sense (INV-004) and every overlapping match
(§15.1), then pass a left/right boundary check (REQ-BND-001) before becoming
proposals.

Boundary <-> particle FST interface follows §15.5: the boundary checker only
issues prefix-accept queries (REQ-BND-002/003); full tail decomposition is the
tail parser's job (tailparser.py).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .glossary import AliasBinding, Glossary
from .hangul import is_hangul
from .morphology import ParticleFST, match_latin_tail, match_prefix_modifier
from .normalization import (
    CanonicalStream,
    Channel,
    NormalizationProfile,
    build_channel,
    normalize_alias,
)

# per-skipped-unit cost inside a tolerant match (T-04/T-05)
GAP_COST = 0.05
MAX_GAP_RUN = 2  # max consecutive skipped canonical units inside a match


class AhoCorasick:
    def __init__(self, keys: list[str]):
        # nodes: dict transitions, fail link, output keys
        self.goto: list[dict[str, int]] = [{}]
        self.fail: list[int] = [0]
        self.out: list[list[str]] = [[]]
        for key in keys:
            self._insert(key)
        self._build_links()

    def _insert(self, key: str) -> None:
        node = 0
        for ch in key:
            nxt = self.goto[node].get(ch)
            if nxt is None:
                self.goto.append({})
                self.fail.append(0)
                self.out.append([])
                nxt = len(self.goto) - 1
                self.goto[node][ch] = nxt
            node = nxt
        self.out[node].append(key)

    def _build_links(self) -> None:
        q: deque[int] = deque()
        for child in self.goto[0].values():
            q.append(child)
        while q:
            node = q.popleft()
            for ch, child in self.goto[node].items():
                q.append(child)
                f = self.fail[node]
                while f and ch not in self.goto[f]:
                    f = self.fail[f]
                self.fail[child] = self.goto[f].get(ch, 0) if self.goto[f].get(ch, 0) != child else 0
                self.out[child] = self.out[child] + self.out[self.fail[child]]

    def iter_matches(self, text: str):
        """Yield (start, end, key) for every occurrence (overlaps included)."""
        node = 0
        for i, ch in enumerate(text):
            while node and ch not in self.goto[node]:
                node = self.fail[node]
            node = self.goto[node].get(ch, 0)
            for key in self.out[node]:
                yield i - len(key) + 1, i + 1, key


# ---------------------------------------------------------------------------
# Boundary policies (§15.3)
# ---------------------------------------------------------------------------

PASS, SOFT, FAIL = "PASS", "SOFT", "FAIL"


@dataclass
class BoundaryResult:
    status: str  # PASS | SOFT | FAIL
    left_prefix: tuple[str, str, bool] | None = None  # (surface, kind, spaced)
    right_latin_tail: tuple[str, str] | None = None  # (tail, kind)
    notes: list[str] = field(default_factory=list)


def _script(ch: str) -> str:
    if is_hangul(ch):
        return "hangul"
    if ch.isascii() and ch.isalnum():
        return "latin"
    if ch.isspace():
        return "space"
    return "other"


def _is_token_boundary(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return True
    sa, sb = _script(a), _script(b)
    if sa in ("space", "other") or sb in ("space", "other"):
        return True
    return sa != sb


def check_boundary(
    stream: CanonicalStream,
    unit_indices: list[int],
    policy_left: str,
    policy_right: str,
    allow_inside_latin_run: bool,
    profile: NormalizationProfile,
    fst: ParticleFST,
) -> BoundaryResult:
    units = stream.units
    first, last = unit_indices[0], unit_indices[-1]
    prev_ch = units[first - 1].ch if first > 0 else None
    next_ch = units[last + 1].ch if last + 1 < len(units) else None
    core_last_ch = units[last].ch
    res = BoundaryResult(PASS)

    # ---- left ----
    if policy_left == "any":
        pass
    elif policy_left == "latin_token_boundary":
        if prev_ch is not None and _script(prev_ch) == "latin":
            return BoundaryResult(FAIL, notes=["left:inside_latin_run"])
    elif policy_left == "hangul_token_boundary":
        if prev_ch is not None and _script(prev_ch) == "hangul":
            left_run = _left_hangul_run(units, first)
            pfx = match_prefix_modifier(left_run)
            if pfx and len(pfx[0]) == len(left_run):
                res.left_prefix = pfx
                res.notes.append(f"left:prefix_modifier:{pfx[0]}")
            else:
                return BoundaryResult(FAIL, notes=["left:hangul_attached"])
    else:  # unicode_word_boundary (default)
        if prev_ch is not None and _script(prev_ch) in ("latin", "hangul"):
            return BoundaryResult(FAIL, notes=["left:word_attached"])

    # ---- right ----
    if policy_right == "any":
        return res
    if _is_token_boundary(core_last_ch, next_ch):
        return res
    right_run = _right_run(units, last)
    if policy_right in ("particle_or_token_boundary", "latin_token_boundary"):
        if _script(next_ch) == "hangul":
            if policy_right == "particle_or_token_boundary" and fst.accepts_prefix(
                right_run, core_last_ch
            ):
                # REQ-BND-002: prefix-accept passes; parser decomposes later
                res.notes.append("right:particle_prefix_accept")
                return res
            # residual continuation (서울본부 etc.): soft-kept (§16.5)
            res.status = SOFT
            res.notes.append("right:hangul_residual")
            return res
        # Latin/digit continuation
        if profile.latin_morph:
            tail = match_latin_tail(right_run)
            if tail:
                res.right_latin_tail = tail
                res.notes.append(f"right:latin_tail:{tail[0]}")
                return res
        if allow_inside_latin_run:
            res.status = SOFT
            res.notes.append("right:inside_latin_run_allowed")
            return res
        return BoundaryResult(FAIL, notes=["right:inside_latin_run"])
    # unknown policy value: be conservative
    return BoundaryResult(FAIL, notes=[f"right:unknown_policy:{policy_right}"])


def _left_hangul_run(units, first: int) -> str:
    i = first - 1
    chars: list[str] = []
    while i >= 0 and _script(units[i].ch) == "hangul":
        chars.append(units[i].ch)
        i -= 1
    return "".join(reversed(chars))


def _right_run(units, last: int) -> str:
    """Characters after the core in the same attached run (no spaces)."""
    out: list[str] = []
    i = last + 1
    while i < len(units):
        ch = units[i].ch
        if _script(ch) in ("space",) or (_script(ch) == "other" and ch not in "'’"):
            break
        out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Exact index (§15.1)
# ---------------------------------------------------------------------------


@dataclass
class RawExactMatch:
    binding: AliasBinding
    key: str
    unit_indices: list[int]
    core_span: tuple[int, int]  # raw codepoint half-open
    matched_segments: list[tuple[int, int]]
    transform_cost: float
    transforms: tuple[str, ...]
    boundary: BoundaryResult
    profile: NormalizationProfile


class ExactIndex:
    """Grouped Aho-Corasick automatons over per-profile channels."""

    def __init__(self, glossary: Glossary, fst: ParticleFST | None = None):
        self.glossary = glossary
        self.fst = fst or ParticleFST()
        # group bindings by profile signature
        self._groups: dict[tuple, dict] = {}
        for b in glossary.alias_bindings:
            prof = glossary.binding_profile(b)
            sig = (prof.case_fold, prof.ignore_punctuation, prof.spacing_mode,
                   prof.width_fold)
            grp = self._groups.setdefault(sig, {"profile": prof, "keys": {}})
            key = normalize_alias(b.surface, prof)
            if key:
                grp["keys"].setdefault(key, []).append(b)
        for grp in self._groups.values():
            grp["ac"] = AhoCorasick(list(grp["keys"]))

    def find(self, stream: CanonicalStream) -> list[RawExactMatch]:
        results: list[RawExactMatch] = []
        for grp in self._groups.values():
            profile: NormalizationProfile = grp["profile"]
            channel = build_channel(stream, profile)
            for start, end, key in grp["ac"].iter_matches(channel.chars):
                match = self._materialize(stream, channel, start, end, key, grp)
                if match is None:
                    continue
                results.extend(match)
        return results

    def _materialize(self, stream, channel: Channel, start, end, key, grp):
        unit_indices = channel.unit_idx[start:end]
        units = stream.units
        # gap constraints + cost
        cost = 0.0
        transforms: set[str] = set()
        for pos in range(start, end):
            if channel.pos_transform[pos]:
                transforms.add(channel.pos_transform[pos])
            transforms.update(units[channel.unit_idx[pos]].transforms)
        for a, b in zip(unit_indices, unit_indices[1:]):
            gap = b - a - 1
            if gap > MAX_GAP_RUN:
                return None
            if gap:
                cost += GAP_COST * gap
                for skipped in range(a + 1, b):
                    ch = units[skipped].ch
                    transforms.add("T-05" if ch.isspace() else "T-04")
        # segments: contiguous unit runs -> raw spans
        segments: list[tuple[int, int]] = []
        seg_start = unit_indices[0]
        prev = unit_indices[0]
        for idx in unit_indices[1:]:
            if idx != prev + 1:
                segments.append((units[seg_start].raw_start, units[prev].raw_end))
                seg_start = idx
            prev = idx
        segments.append((units[seg_start].raw_start, units[prev].raw_end))
        core_span = (units[unit_indices[0]].raw_start, units[unit_indices[-1]].raw_end)

        out = []
        for binding in grp["keys"][key]:
            boundary = check_boundary(
                stream,
                unit_indices,
                binding.boundary_policy.left,
                binding.boundary_policy.right,
                binding.boundary_policy.allow_inside_latin_run,
                grp["profile"],
                self.fst,
            )
            if boundary.status == FAIL:
                continue  # REQ-BND-001
            out.append(
                RawExactMatch(
                    binding=binding,
                    key=key,
                    unit_indices=list(unit_indices),
                    core_span=core_span,
                    matched_segments=segments,
                    transform_cost=cost,
                    transforms=tuple(sorted(transforms)),
                    boundary=boundary,
                    profile=grp["profile"],
                )
            )
        return out
