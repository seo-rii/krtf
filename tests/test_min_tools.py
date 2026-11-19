import runpy
from pathlib import Path


mini = runpy.run_path(str(Path(__file__).resolve().parents[1] / "min" / "krtf.py"))


def test_lint_collects_v3_problems_and_accepts_minimal_bindings():
    doc = {"entities": [{"entity_id": "a", "canonical": "기관"}],
           "alias_bindings": [{"entity_id": "a", "surface": "기관"}]}
    assert mini["lint_glossary"](doc) == []
    doc["alias_families"] = [{"family_id": "f"}, {"family_id": "f"}]
    doc["alias_bindings"].append({"entity_id": "missing", "surface": "기관", "family_id": "unknown",
                                  "valid_from": "2025-09-23", "valid_to": "2024-01-31"})
    doc["entities"][0].update({"descriptino": "contains\x00control"})
    issues = mini["lint_glossary"](doc)
    assert {i["code"] for i in issues if i["severity"] == "error"} >= {
        "DUPLICATE_ID", "UNKNOWN_FIELD", "DANGLING_FAMILY_REF", "DANGLING_ENTITY_REF",
        "INVALID_VALIDITY_WINDOW", "CONTROL_CHARACTER",
    }
    assert any(i["severity"] == "warning" and i["code"] == "SHARED_ALIAS" for i in issues)


def test_lint_simple_terms_collisions_and_invalid_shape():
    terms = [{"key": "a", "canonical": "AP"}, {"key": "b", "canonical": "ap"},
             {"key": "b", "canonical": "AP", "valid_from": "not-a-date", "surfaces": 2}]
    issues = mini["lint_glossary"]({"terms": terms})
    assert {i["code"] for i in issues} >= {
        "DUPLICATE_ID", "SHARED_ALIAS", "NORMALIZED_ALIAS_COLLISION", "INVALID_DATE", "INVALID_SURFACES",
    }
    assert mini["lint_glossary"]({"terms": [None]})[0]["severity"] == "error"


def test_lint_repository_glossaries():
    root = Path(__file__).resolve().parents[1] / "examples"
    for path in sorted(root.glob("*.yaml")):
        issues = mini["lint_glossary"](mini["load_glossary"](path))
        assert not [i for i in issues if i["severity"] == "error"], (path, issues)


def test_lookup_explain_and_snapshot_diff():
    original = {"key": "network", "canonical": "Access Point", "surfaces": ["AP"],
                "short_definition": "무선 장비"}
    other = {"key": "approval", "canonical": "승인", "surfaces": ["AP"]}
    before = mini["compile_snapshot"]({"terms": [original]})
    after = mini["compile_snapshot"]({"terms": [{**original, "short_definition": "무선 단말 장비"},
                                               other]})
    info = mini["snapshot_info"](after)
    assert (info["entities"], info["surfaces"], info["bindings"], info["shared_surfaces"]) == (2, 3, 4, 1)
    lookup = mini["lookup_surface"](after, "ａｐ")
    assert lookup["matched_surfaces"] == ["AP"]
    assert [c["entity_id"] for c in lookup["candidates"]] == ["project:approval", "project:network"]
    assert lookup["candidates"][1]["definition"] == "무선 단말 장비"
    assert mini["lookup_surface"](after, "missing")["candidates"] == []
    mention, = mini["explain_resolution"](after, "AP를 확인했다.")["mentions"]
    assert mention["link_decision"] == "AMBIGUOUS"
    assert mention["matched_surfaces"] == ["AP"] and mention["link_reason"]
    assert mention["generation_channels"]
    assert sorted(c["entity_id"] for c in mention["candidates"]) == ["project:approval", "project:network"]
    delta = mini["diff_snapshots"](before, after)
    assert delta["entities"] == {"added": ["project:approval"], "removed": [], "changed": ["project:network"]}
    assert delta["surfaces"] == {"added": ["승인"], "removed": [], "changed": ["AP"]}
    assert "definitions" in delta["metadata_changed"]
    assert mini["diff_snapshots"](after, before)["surfaces"]["removed"] == ["승인"]


def test_explain_and_diff_entity_scope():
    term = {"key": "ap", "canonical": "AP", "scope": {"allow": {"departments": ["it"]}}}
    assert mini["lint_glossary"]({"terms": [term]}) == []
    before = mini["compile_snapshot"]({"terms": [term]})
    assert not mini["explain_resolution"](before, "AP")["mentions"][0]["candidates"][0]["eligible"]
    hit, = mini["explain_resolution"](before, "AP", department="it")["mentions"]
    assert hit["candidates"][0]["eligible"] and hit["link_decision"] == "RESOLVED"
    different_scope = {**term, "scope": {"allow": {"departments": ["sales"]}}}
    after = mini["compile_snapshot"]({"terms": [different_scope]})
    assert mini["diff_snapshots"](before, after)["entities"]["changed"] == ["project:ap"]
