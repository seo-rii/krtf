"""`ktrf.spans` must answer exactly what the linear scans it replaced did."""

from hypothesis import given, settings
from hypothesis import strategies as st

from ktrf.spans import GrowingSpanSet, SpanSet

span = st.tuples(st.integers(0, 40), st.integers(0, 12)).map(
    lambda t: (t[0], t[0] + t[1]))          # includes empty spans


def brute(spans, s, e):
    return any(s2 < e and s < e2 for s2, e2 in spans)


@settings(max_examples=400, deadline=None)
@given(st.lists(span, max_size=30), st.lists(span, min_size=1, max_size=20))
def test_fixed_set_matches_the_scan(stored, queries):
    idx = SpanSet(stored)
    for s, e in queries:
        assert idx.overlaps(s, e) == brute(stored, s, e)


@settings(max_examples=400, deadline=None)
@given(st.lists(span, min_size=1, max_size=40))
def test_greedy_selection_matches_the_scan(ranked):
    """The `_select_primary` loop: take a span unless it overlaps one taken."""
    taken, fast = [], GrowingSpanSet(s for s, _ in ranked)
    picked_fast = []
    for s, e in ranked:
        if not brute(taken, s, e):
            taken.append((s, e))
        if not fast.overlaps(s, e):
            fast.add(s, e)
            picked_fast.append((s, e))
    assert picked_fast == taken


def test_an_undeclared_start_is_refused():
    import pytest

    with pytest.raises(ValueError):
        GrowingSpanSet([1, 2]).add(3, 5)
