"""Overlap queries over half-open spans, without a scan per query.

The resolver asks "does this span overlap any span already taken?" once per
token or per mention, and answered it with ``any(...)`` over a list. That is
linear per question and quadratic per request: a 64 KiB input of registered
names produces thousands of mentions, and three such scans were most of the
time a commit-mode request spent.

Two spans overlap exactly when ``s2 < e and s < e2`` — the predicate the
scans used, kept verbatim, including for empty spans. Read with the stored
span on the left, it says: among stored spans *starting before* ``e``, is
the largest end beyond ``s``? Starts sorted once turn that into a bisect and
a prefix maximum.
"""

from __future__ import annotations

from bisect import bisect_left


class SpanSet:
    """A fixed collection of spans."""

    __slots__ = ("_starts", "_max_end")

    def __init__(self, spans):
        ordered = sorted((s, e) for s, e in spans)
        self._starts = [s for s, _ in ordered]
        self._max_end = []
        best = None
        for _, e in ordered:
            best = e if best is None or e > best else best
            self._max_end.append(best)

    def overlaps(self, s: int, e: int) -> bool:
        k = bisect_left(self._starts, e)      # stored spans with start < e
        return k > 0 and self._max_end[k - 1] > s


class GrowingSpanSet:
    """Spans added over time, from starts known in advance.

    A Fenwick tree of prefix maxima over the candidate starts: adding only
    ever raises a maximum, which is the one update such a tree supports.
    """

    __slots__ = ("_starts", "_tree")

    def __init__(self, possible_starts):
        self._starts = sorted(set(possible_starts))
        self._tree = [None] * (len(self._starts) + 1)

    def add(self, s: int, e: int) -> None:
        i = bisect_left(self._starts, s)
        if i == len(self._starts) or self._starts[i] != s:
            raise ValueError(f"start {s} was not declared")
        i += 1
        while i < len(self._tree):
            cur = self._tree[i]
            if cur is None or e > cur:
                self._tree[i] = e
            i += i & -i

    def overlaps(self, s: int, e: int) -> bool:
        i = bisect_left(self._starts, e)      # declared starts < e
        best = None
        while i > 0:
            cur = self._tree[i]
            if cur is not None and (best is None or cur > best):
                best = cur
            i -= i & -i
        return best is not None and best > s
