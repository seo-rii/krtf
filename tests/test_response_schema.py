"""The resolve() response has a written contract too.

The review's diagnosis was one contract reimplemented in several places, so a
change in one leaves the others behind. `core_link.span` is the case in point:
it was added to the response, and the chunk translator, the eval harness and
the context builder each learned about it separately — or, in two of the
three, not at all.

The schema does not stop that by itself. It gives the contract one written
form that can be checked against the code, so the pair cannot drift in
silence. Closed on the objects that are contract; open on `trace`,
`eval_trace` and member `features`, which exist to be read rather than
depended on.
"""

import itertools
import random

import pytest

from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.schemas import (
    NAMES,
    load_schema,
    schema_path,
    validate_resolve_response,
)
from ktrf.snapshot import compile_snapshot

pytest.importorskip("jsonschema")

_SURFACES = ["한국전력공사", "한전", "금융감독원", "금감원", "과기정통부",
             "한전노조", "금감원장", "국토교통부", "전 한전", "한전KDN"]
_NEAR_MISSES = ["한국전려공사", "금유감독원", "과기정통부처", "국토교퉁부"]
_DEFINITIONS = ['한국전력공사(이하 "케이피")가 발표했다. 케이피는 답했다']
_LONG = " ".join(["금유감독원과 한국전려공사가 협의했다."] * 40)

_OPTIONS = [
    {"return_all_mentions": True},
    {"return_all_mentions": True, "return_features": True},
    {"return_all_mentions": True, "max_prediction_set": 1},
    {"return_all_mentions": True, "strict_conformal_set": True},
    {"return_all_mentions": True, "return_trace": True},
    {"return_all_mentions": True, "return_eval_trace": True},
    {"return_all_mentions": True, "detect_unregistered_mentions": True},
    {"return_all_mentions": False},
    {"return_all_mentions": True, "deadline_ms": 1},
]


@pytest.fixture(scope="module")
def snapshot():
    return compile_snapshot(load_glossary("examples/realorg_glossary.yaml"))


@pytest.fixture(scope="module")
def responses(snapshot):
    rng = random.Random(3)
    out = []
    for options, mode in itertools.product(_OPTIONS, ("commit", "fast")):
        texts = [" ".join(rng.choice(_SURFACES + _NEAR_MISSES + _DEFINITIONS)
                          for _ in range(rng.randint(1, 6)))
                 for _ in range(6)]
        texts.append(_LONG)
        for text in texts:
            out.append(resolve(snapshot, text, mode=mode, options=options))

    # Long mixed documents, because three of the four link decisions are easy
    # to reach and UNCERTAIN is not: it needs a degraded node that still has
    # an exact candidate, so the KB_MISSING member never joins the set. Seed 7
    # produces three of them across these eight documents; the short fixtures
    # above produce none, and the enum branch would have gone unchecked.
    registered = [b.surface for b in snapshot.glossary.alias_bindings]
    near_misses = ["금유감독원", "한국전려공사", "국토교퉁부", "과기정통부처",
                   "기획재정무", "보건복지무", "행정안전무", "산업통상자원무"]
    rng = random.Random(7)
    for _ in range(8):
        parts = []
        for _ in range(rng.randint(30, 90)):
            pool = near_misses if rng.random() < 0.45 else registered
            parts.append(f"{rng.choice(pool)}이(가) 협의에 참여했다고 한다.")
        out.append(resolve(snapshot, " ".join(parts)[:8000], mode="commit",
                           options={"return_all_mentions": True}))
    return out


# ------------------------------------------------------------- the schemas

@pytest.mark.parametrize("name", NAMES)
def test_each_schema_is_a_schema(name):
    import jsonschema

    jsonschema.Draft7Validator.check_schema(load_schema(name))
    assert schema_path(name).exists()


def test_the_contract_objects_are_closed():
    """Open where it is diagnostics, closed where it is contract."""
    schema = load_schema("resolve_response")
    open_on_purpose = {"trace", "eval_trace", "features"}

    def walk(node, path):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False, path
            for k, v in node.items():
                if k in open_on_purpose:
                    continue
                walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(schema, "")
    for name in open_on_purpose:
        assert '"' + name + '"' in schema_path(
            "resolve_response").read_text(encoding="utf-8")


# ------------------------------------------------------------ the responses

def test_every_response_meets_the_contract(responses):
    problems = {}
    for resp in responses:
        for msg in validate_resolve_response(resp):
            problems[msg] = problems.get(msg, 0) + 1
    assert len(responses) == 134
    assert problems == {}, problems


def test_the_responses_reach_the_optional_shapes(responses):
    """A schema only checks the shapes it is shown, so show it these."""
    seen = set()
    for resp in responses:
        seen |= {k for k in ("deadline", "trace") if k in resp}
        for m in resp["mentions"]:
            seen |= {k for k in ("full_span", "prefix", "tail", "core_link",
                                 "full_surface", "degraded",
                                 "channels_bounded", "eval_trace",
                                 "resolved_entity") if k in m}
            seen.add("decision:" + m["link_decision"])
            pset = m.get("prediction_set") or {}
            seen |= {"set:" + k for k in ("truncated", "strict_conformal")
                     if k in pset}
            for member in pset.get("members", []):
                seen.add("member:" + member.get("kind", "?"))
                if "features" in member:
                    seen.add("member:features")
                if "commit_blocked" in member:
                    seen.add("member:commit_blocked")

    required = {
        "deadline", "trace", "full_span", "prefix", "tail", "core_link",
        "full_surface", "degraded", "channels_bounded", "eval_trace",
        "resolved_entity", "set:truncated", "set:strict_conformal",
        "member:ENTITY", "member:KB_MISSING", "member:features",
        "member:commit_blocked",
        "decision:RESOLVED", "decision:AMBIGUOUS", "decision:KB_MISSING",
        "decision:UNCERTAIN",
    }
    assert required <= seen, sorted(required - seen)


def test_a_registered_composition_validates():
    """`composes_to` needs a glossary that declares one, which the realorg
    fixture does not — so it would have been an unchecked guess."""
    snap = compile_snapshot(load_glossary("examples/demo_glossary.yaml"))
    resp = resolve(snap, "한전노조가 파업을 예고했다.", mode="commit",
                   options={"return_all_mentions": True})
    composed = [m for m in resp["mentions"]
                if "composes_to" in (m.get("full_surface") or {})]
    assert composed, "fixture no longer exercises a registered composition"
    assert validate_resolve_response(resp) == []


# ----------------------------------------------------------------- teeth

def _one(snapshot):
    return resolve(snapshot, "금유감독원이 조사했다. 한전은 답했다.",
                   mode="commit", options={"return_all_mentions": True})


def test_an_unexpected_top_level_field_is_caught(snapshot):
    resp = _one(snapshot)
    resp["surprise"] = 1
    assert any("surprise" in p for p in validate_resolve_response(resp))


def test_a_nested_span_that_lost_an_encoding_is_caught(snapshot):
    """The R6 shape: a span field edited in one place and not another."""
    resp = _one(snapshot)
    target = next(m for m in resp["mentions"] if "span" in m)
    del target["span"]["utf16"]
    problems = validate_resolve_response(resp)
    assert any("utf16" in p for p in problems), problems


def test_a_span_that_grew_a_field_is_caught(snapshot):
    resp = _one(snapshot)
    next(m for m in resp["mentions"])["span"]["char"] = {"start": 0, "end": 1}
    assert any("char" in p for p in validate_resolve_response(resp))


def test_an_unknown_decision_is_caught(snapshot):
    resp = _one(snapshot)
    resp["mentions"][0]["link_decision"] = "PROBABLY"
    problems = validate_resolve_response(resp)
    assert any("PROBABLY" in p for p in problems), problems


def test_a_set_member_without_a_kind_is_caught(snapshot):
    resp = _one(snapshot)
    target = next(m for m in resp["mentions"] if m.get("prediction_set"))
    target["prediction_set"]["members"].append({"entity_id": "X"})
    assert any("kind" in p for p in validate_resolve_response(resp))


def test_the_schemas_are_declared_as_package_data():
    import fnmatch
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = data["tool"]["setuptools"]["package-data"]["ktrf"]
    for name in NAMES:
        rel = f"schemas/{name}.schema.json"
        assert any(fnmatch.fnmatch(rel, pat) for pat in patterns), rel
