"""The ContextPack has a written contract, and the packs have to meet it.

§16.8 asks for JSON Schema validation. The point is not that a host *can*
validate — it is that the schema and the builder can be checked against each
other, so the written contract cannot drift away from the thing it describes
while every other test still passes. The schema is closed
(`additionalProperties: false`) for exactly that reason, and it earned its
keep on the first run by catching an omission shape
(`token_budget_unreachable` carrying `requested`/`rendered`) that nothing had
written down.
"""

import json
import random

import pytest

from ktrf.context import (
    ContextPolicy,
    PROFILES,
    build_context_pack,
    context_pack_schema,
    validate_context_pack,
)
from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

pytest.importorskip("jsonschema")

GLOSSARY = "examples/realorg_glossary.yaml"

_SURFACES = ["한국전력공사", "한전", "금융감독원", "금감원", "과기정통부",
             "한전노조", "금감원장", "국토교통부"]
_NEAR_MISSES = ["한국전려공사", "금유감독원", "과기정통부처", "국토교퉁부"]
_DEFINITIONS = ['한국전력공사(이하 "케이피")가 발표했다. 케이피는 답했다',
                "금융감독원(이하 금감원)이 조사했다"]


@pytest.fixture(scope="module")
def snapshot():
    return compile_snapshot(load_glossary(GLOSSARY))


def _packs(snapshot, n, seed):
    rng = random.Random(seed)
    fragments = _SURFACES + _NEAR_MISSES + _DEFINITIONS + ["가나다", ""]
    for _ in range(n):
        text = " ".join(rng.choice(fragments)
                        for _ in range(rng.randint(0, 6)))
        policy = ContextPolicy(
            profile=rng.choice(PROFILES),
            max_tokens=rng.randint(1, 2000),
            max_entities=rng.randint(1, 30),
            max_candidates_per_mention=rng.randint(1, 5),
            max_description_chars=rng.randint(1, 300),
            include_ambiguous=rng.random() < 0.8,
            include_unknown_mentions=rng.random() < 0.5,
            query_aware=rng.random() < 0.5,
            ambiguity_scope=rng.choice(["query", "all"]),
            expose_entity_ids=rng.random() < 0.5,
            include_numeric_probabilities=rng.random() < 0.5,
            classification_clearance=rng.choice(
                ["public", "internal", "restricted"]))
        resp = resolve(snapshot, text, mode="commit",
                       options={"return_all_mentions": True,
                                "max_prediction_set": 50})
        yield build_context_pack(
            snapshot, resp,
            query=rng.choice([None, "한전은 무엇인가"]), policy=policy)


# ------------------------------------------------------------- the schema

def test_the_schema_is_a_schema():
    import jsonschema

    schema = context_pack_schema()
    jsonschema.Draft7Validator.check_schema(schema)
    assert schema["title"] == "KTRF ContextPack"
    assert schema["additionalProperties"] is False


def test_the_schema_is_closed_all_the_way_down():
    """An open sub-object is where the drift would hide."""
    def closed(node, path):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False, path
            for k, v in node.items():
                closed(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                closed(v, f"{path}[{i}]")

    closed(context_pack_schema(), "")


# -------------------------------------------------------------- the packs

def test_every_generated_pack_meets_the_contract(snapshot):
    problems = {}
    n = 0
    for pack in _packs(snapshot, 120, seed=99):
        n += 1
        for msg in validate_context_pack(pack):
            problems.setdefault(msg, 0)
            problems[msg] += 1
    assert n == 120
    assert problems == {}, problems


def test_the_generated_packs_exercise_the_optional_shapes(snapshot):
    """A schema only checks the shapes it is shown."""
    seen = set()
    for pack in _packs(snapshot, 120, seed=99):
        for name in ("resolved_terms", "ambiguous_mentions",
                     "unknown_mentions", "document_definitions", "omissions"):
            if pack[name]:
                seen.add(name)
        for o in pack["omissions"]:
            seen.add("omission:" + o["reason"])
    assert {"resolved_terms", "ambiguous_mentions", "unknown_mentions",
            "document_definitions", "omissions"} <= seen, seen
    assert any(s.startswith("omission:") for s in seen), seen


# ---------------------------------------------------------------- teeth

def test_an_unexpected_field_is_caught(snapshot):
    pack = next(_packs(snapshot, 1, seed=1))
    pack["surprise"] = 1
    assert any("surprise" in p for p in validate_context_pack(pack))


def test_a_missing_field_is_caught(snapshot):
    pack = next(_packs(snapshot, 1, seed=1))
    del pack["coverage"]
    assert any("coverage" in p for p in validate_context_pack(pack))


def test_a_wrong_type_is_caught(snapshot):
    pack = next(_packs(snapshot, 1, seed=1))
    pack["coverage"]["complete"] = "yes"
    problems = validate_context_pack(pack)
    assert any("complete" in p for p in problems), problems


def test_a_candidate_promoted_into_a_card_is_caught(snapshot):
    """The shape of the state-separation bug, not just any type error."""
    pack = next(_packs(snapshot, 1, seed=1))
    pack["resolved_terms"].append({"entity_id": "X", "canonical": "X",
                                   "mentions": [], "resolution": {},
                                   "candidates": [{"entity_id": "Y"}]})
    problems = validate_context_pack(pack)
    assert any("candidates" in p for p in problems), problems


def test_a_pack_id_that_is_not_one_is_caught(snapshot):
    pack = next(_packs(snapshot, 1, seed=1))
    pack["pack_id"] = "whatever"
    assert any("pack_id" in p for p in validate_context_pack(pack))


# --------------------------------------------------------------- packaging

def test_the_schema_is_json_on_disk():
    from ktrf.context import _SCHEMA_PATH

    assert _SCHEMA_PATH.exists(), _SCHEMA_PATH
    json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_the_wheel_is_told_to_carry_it():
    """`context_pack_schema()` reads a file; an installed copy has to have
    it, and package-data is the only thing that puts it there."""
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = data["tool"]["setuptools"]["package-data"]["ktrf"]
    assert "schemas/*.json" in patterns, patterns


def test_validation_without_the_validator_says_so(monkeypatch):
    """Returning "no problems" from a check that did not run is worse than
    refusing to run it."""
    import builtins

    real_import = builtins.__import__

    def no_jsonschema(name, *args, **kw):
        if name == "jsonschema":
            raise ImportError("not installed")
        return real_import(name, *args, **kw)

    monkeypatch.setattr(builtins, "__import__", no_jsonschema)
    with pytest.raises(KtrfApiError) as e:
        validate_context_pack({})
    assert "jsonschema" in str(e.value)
