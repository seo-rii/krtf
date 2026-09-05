"""A wall-clock budget, and the index that made scope adjustment linear.

The performance review asked for two things the code could not do: a deadline
that sheds the optional stages instead of running to completion, and an index
from alias id to binding so scope adjustment stops scanning the glossary once
per candidate.

The deadline is deliberately not a hard latency cap. Level A is a
deterministic guarantee, not a best-effort stage, so the exact pass always
runs and the floor is whatever it costs. What the budget governs is
everything above it — and what makes it usable is that the response says which
stages it dropped, rather than quietly returning a thinner answer.
"""

import random

import pytest

from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

GLOSSARY = "examples/realorg_glossary.yaml"


@pytest.fixture(scope="module")
def glossary():
    return load_glossary(GLOSSARY)


@pytest.fixture(scope="module")
def snap(glossary):
    return compile_snapshot(glossary)


@pytest.fixture(scope="module")
def long_text(glossary):
    rng = random.Random(11)
    surfaces = [b.surface for b in glossary.alias_bindings]
    parts = []
    while sum(len(p) for p in parts) < 2000:
        parts.append(f"{rng.choice(surfaces)} 관련 검토 내용을 정리한다.")
    return " ".join(parts)[:2000]


# ------------------------------------------------------------- alias index

def test_the_index_returns_what_the_scan_returned(glossary):
    for b in glossary.alias_bindings[:20]:
        assert glossary.binding(b.alias_id) is not None
        assert glossary.binding(b.alias_id).alias_id == b.alias_id


def test_a_duplicate_alias_id_resolves_to_the_first_one(glossary):
    # the scan this replaced took the first match, so the index must too
    seen = {}
    for b in glossary.alias_bindings:
        seen.setdefault(b.alias_id, b)
    for alias_id, first in list(seen.items())[:50]:
        assert glossary.binding(alias_id) is first


def test_an_unknown_alias_id_is_a_miss_not_an_error(glossary):
    assert glossary.binding("no-such-alias") is None


# ---------------------------------------------------------------- deadline

def test_without_a_deadline_the_response_does_not_mention_one(snap):
    resp = resolve(snap, "금융감독원이 조사했다", mode="commit")
    assert "deadline" not in resp


def test_a_generous_deadline_skips_nothing(snap):
    resp = resolve(snap, "금융감독원이 조사했다", mode="commit",
                   options={"deadline_ms": 600_000})
    assert resp["deadline"]["exceeded"] is False
    assert resp["deadline"]["skipped_stages"] == []
    assert "deadline_fuzzy" not in resp["limits"]


def test_an_expired_deadline_sheds_the_fuzzy_stage_and_says_so(snap,
                                                               long_text):
    resp = resolve(snap, long_text, mode="commit",
                   options={"deadline_ms": 1})
    assert resp["deadline"]["exceeded"] is True
    assert "fuzzy" in resp["deadline"]["skipped_stages"]
    # `limits` is the field a consumer reads without asking for the trace
    assert "deadline_fuzzy" in resp["limits"]
    assert resp["degraded"] is True


def test_level_a_survives_a_deadline_that_expires_immediately(snap):
    # the exact channel is a guarantee and is not shed under load; a budget
    # that could drop it would be trading correctness for latency
    text = "금융감독원이 조사했다"
    full = resolve(snap, text, mode="commit")
    starved = resolve(snap, text, mode="commit", options={"deadline_ms": 1})
    assert [m["surface"] for m in starved["mentions"]] == \
           [m["surface"] for m in full["mentions"]]
    assert [m["link_decision"] for m in starved["mentions"]] == \
           [m["link_decision"] for m in full["mentions"]]


def test_the_deadline_block_reports_what_the_budget_actually_bought(snap,
                                                                    long_text):
    resp = resolve(snap, long_text, mode="commit",
                   options={"deadline_ms": 5})
    d = resp["deadline"]
    assert d["budget_ms"] == 5
    # honest about overshoot: the exact pass cannot be skipped, so elapsed can
    # exceed the budget and the response says by how much rather than hiding it
    assert d["elapsed_ms"] > 0


def test_a_deadline_shortens_the_work(snap, long_text):
    import time

    def timed(options):
        t0 = time.perf_counter()
        resolve(snap, long_text, mode="commit", options=options)
        return time.perf_counter() - t0

    unbounded = min(timed({}) for _ in range(3))
    bounded = min(timed({"deadline_ms": 1}) for _ in range(3))
    assert bounded < unbounded


# ------------------------------------------------------- option validation

@pytest.mark.parametrize("value", [0, -1, 600_001, "50", True, 2.5, None])
def test_a_bad_deadline_is_a_typed_error_not_a_surprise(snap, value):
    with pytest.raises(KtrfApiError) as e:
        resolve(snap, "금융감독원이 조사했다", mode="commit",
                options={"deadline_ms": value})
    assert e.value.to_dict()["error"]["code"] == "INVALID_REQUEST"


# --------------------------------------------------- dense and rerank paths

def test_an_expired_deadline_also_sheds_dense_and_rerank():
    from ktrf.encoders import HashEncoder
    from ktrf.rerank import LexicalCrossEncoder

    glossary = load_glossary(GLOSSARY)
    snap = compile_snapshot(glossary, encoder=HashEncoder(),
                            reranker=LexicalCrossEncoder())
    rng = random.Random(3)
    surfaces = [b.surface for b in glossary.alias_bindings]
    text = " ".join(f"{rng.choice(surfaces)} 관련 검토를 진행한다."
                    for _ in range(60))
    resp = resolve(snap, text, mode="commit", options={"deadline_ms": 1})
    skipped = set(resp["deadline"]["skipped_stages"])
    # fuzzy is reached first, so it is always the first to go; the later
    # stages are shed too once the budget is already spent
    assert "fuzzy" in skipped
    assert skipped & {"dense", "rerank"}, skipped
