"""The new candidate experiment keeps source gold separate from retrieval."""
from collections import Counter

from eval.review_nano import source_cases


def test_source_cases_preserve_exposed_and_new_targets_without_forced_candidates():
    cases = source_cases()
    assert Counter(c["cohort"] for c in cases) == {
        "development": 384, "heldout": 168, "review_authored_business": 64}
    fresh = [c for c in cases if c["cohort"] == "review_authored_business"]
    assert len({c["family_id"] for c in fresh}) == 16
    assert sum(c["semantic_label"] == "LINK" for c in fresh) == 32
    assert sum(c["stratum"] == "unregistered_typo" for c in fresh) == 4
    assert all("candidates" not in c for c in fresh)
    for case in fresh:
        start, end = case["core_span"]
        assert case["text"][start:end]
        assert case["full_surface_span"][0] <= start < end <= case["full_surface_span"][1]
