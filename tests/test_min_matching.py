import json
import runpy
import unicodedata
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def api():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "min" / "krtf.py"))


def test_normalized_aliases_preserve_all_original_coordinates(api):
    snapshot = api["compile_snapshot"]({"terms": [{"key": "org", "canonical": "한전KDN"}]})
    alias = unicodedata.normalize("NFD", "한전") + "ｋＤＮ"
    text = f"🎉 {alias}은 보고했다."
    [mention] = api["resolve"](snapshot, text)["mentions"]
    assert mention["surface"] == alias
    assert mention["generation_channels"] == ["normalized"]
    assert mention["matched_surfaces"] == ["한전KDN"]
    core_start, core_end = 2, 2 + len(alias)
    for unit, width in [("codepoint", len), ("byte", lambda s: len(s.encode("utf-8"))),
                        ("utf16", lambda s: len(s.encode("utf-16-le")) // 2)]:
        assert mention["span"][unit] == {"start": width(text[:core_start]),
                                        "end": width(text[:core_end])}
        assert mention["full_span"][unit]["end"] == width(text[:core_end + 1])


def test_folded_collision_is_ambiguous_even_with_an_exact_spelling(api):
    snapshot = api["compile_snapshot"]({"terms": [
        {"key": "first", "canonical": "ABC"}, {"key": "second", "canonical": "Abc"},
    ]})
    for spelling in ("ABC", "abc", "ＡｂＣ"):
        [mention] = api["resolve"](snapshot, spelling)["mentions"]
        assert mention["link_decision"] == "AMBIGUOUS"
        assert [row["entity_id"] for row in mention["prediction_set"]["members"]] == [
            "project:first", "project:second"]


def test_longest_alias_particles_and_boundaries(api):
    snapshot = api["compile_snapshot"]({"terms": [
        {"key": "short", "canonical": "한전"}, {"key": "long", "canonical": "한전 KDN"},
    ]})
    text = "한전 KDN에서 한전으로부터는 대한전 한전로부터는 _한전 한전마트"
    mentions = api["resolve"](snapshot, text)["mentions"]
    assert [m["surface"] for m in mentions] == ["한전 KDN", "한전"]
    assert mentions[1]["tail"]["particles"] == ["으로", "부터", "는"]
    assert snapshot.matcher is snapshot.matcher


def test_core_and_derived_entity_remain_distinct(api):
    glossary = {"schema_version": 3,
                "entities": [{"entity_id": eid, "canonical": name}
                             for eid, name in (("kepco", "한전"), ("union", "한전노조"),
                                               ("fss", "금감원"))],
                "alias_bindings": [{"entity_id": "kepco", "surface": "한전"},
                                   {"entity_id": "fss", "surface": "금감원"}],
                "entity_relations": [{"relation_id": "u", "relation_type": "COMPOSES_TO",
                                      "source_entity_id": "kepco", "target_entity_id": "union",
                                      "surface_suffix": "노조"}]}
    text = "금감원장이 한전노조를 방문했다."
    role, union = api["resolve"](api["compile_snapshot"](glossary), text)["mentions"]
    assert role["core_link"]["relation"] == "ROLE_OF"
    assert role["resolved_entity"]["entity_id"] == "fss"
    assert role["full_surface"]["identity"] == "DISTINCT_FROM_CORE"
    assert role["full_surface"]["surface"] == "금감원장"
    assert "composes_to" not in role["full_surface"]
    assert union["resolved_entity"]["entity_id"] == "kepco"
    assert union["full_surface"]["composes_to"]["entity_id"] == "union"
    assert union["full_surface"]["surface"] == "한전노조"
    assert union["tail"]["particles"] == ["를"]


def test_compiled_matcher_restores_without_constructing_a_trie(api, monkeypatch):
    snapshot = api["compile_snapshot"]({"terms": [
        {"key": "he", "canonical": "he"}, {"key": "she", "canonical": "she"},
        {"key": "hers", "canonical": "hers"},
    ]})
    original = snapshot.matcher
    data = json.loads(json.dumps(original.to_data()))
    matcher_type = type(original)
    monkeypatch.setattr(matcher_type, "__init__", lambda *args: pytest.fail("rebuilt trie"))
    restored = matcher_type.from_data(snapshot, data)
    assert list(restored.hits("ushers")) == [(1, 4, "she"), (2, 4, "he"), (2, 6, "hers")]


@pytest.mark.parametrize("damage", ["cycle", "wrong_output", "edge", "spelling", "terminal"])
def test_corrupt_compiled_automaton_is_rejected(api, damage):
    snapshot = api["compile_snapshot"]({"terms": [
        {"key": "short", "canonical": "he"}, {"key": "long", "canonical": "she"},
    ]})
    data = json.loads(json.dumps(snapshot.matcher.to_data()))
    state = data["terminal"].index("she")
    if damage == "cycle":
        data["failure"][state] = state
    elif damage == "wrong_output":
        data["output"][state] = 0
    elif damage == "edge":
        data["edges"][state]["x"] = 0
    elif damage == "spelling":
        data["spellings"]["he"] = ["ho"]
    else:
        data["terminal"][state] = None
    with pytest.raises(ValueError):
        api["_Matcher"].from_data(snapshot, data)


def test_decomposed_latin_and_blocked_partial_cluster(api):
    snapshot = api["compile_snapshot"]({"terms": [
        {"key": "coffee", "canonical": "café"}, {"key": "e", "canonical": "e"},
    ]})
    text = "🎵 cafe\u0301. e\u0323\u0301."
    [mention] = api["resolve"](snapshot, text)["mentions"]
    assert mention["span"]["codepoint"] == {"start": 2, "end": 7}
    assert mention["span"]["byte"] == {"start": 5, "end": 11}
    assert mention["span"]["utf16"] == {"start": 3, "end": 8}
    assert mention["surface"] == "cafe\u0301"


def test_registered_suffix_that_also_spells_a_particle_is_unresolved(api):
    glossary = {"schema_version": 3,
                "entities": [{"entity_id": "gangwon", "canonical": "강원"},
                             {"entity_id": "province", "canonical": "강원도"}],
                "alias_bindings": [{"entity_id": "gangwon", "surface": "강원"}],
                "entity_relations": [{"relation_type": "COMPOSES_TO", "surface_suffix": "도",
                                      "source_entity_id": "gangwon", "target_entity_id": "province"}]}
    [m] = api["resolve"](api["compile_snapshot"](glossary), "강원도")["mentions"]
    assert m["resolved_entity"]["entity_id"] == "gangwon"
    assert m["full_surface"]["identity"] == "UNKNOWN"
    assert "composes_to" not in m["full_surface"]
