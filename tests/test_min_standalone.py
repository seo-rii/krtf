import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def run_cli(tmp_path):
    script = shutil.copy(ROOT / "min" / "krtf.py", tmp_path)
    glossary = tmp_path / "glossary.json"

    def run(doc, *args, stdin=None, check=True):
        glossary.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-I", "-S", script, glossary, *args],
            cwd=tmp_path, input=stdin, capture_output=True, encoding="utf-8",
            check=check, timeout=10,
        )

    return run


def test_demo_links_and_offsets_from_stdin(run_cli):
    demo = yaml.safe_load((ROOT / "examples/demo_glossary.yaml").read_text(encoding="utf-8"))
    output = run_cli(demo, stdin="🎉 한전KDN은 AP 장애 내용을 QMS에 등록했다.")
    mentions = json.loads(output.stdout)["mentions"]
    assert [m["surface"] for m in mentions] == ["한전KDN", "AP", "QMS"]
    kdn, ap, qms = mentions
    assert kdn["link_decision"] == qms["link_decision"] == "RESOLVED"
    assert kdn["resolved_entity"]["entity_id"] == "ORG_KEPCO_KDN"
    assert qms["resolved_entity"]["entity_id"] == "SYSTEM_QUALITY_MANAGEMENT"
    assert ap["link_decision"] == "AMBIGUOUS"
    assert not ap.get("resolved_entity")
    assert {m["entity_id"] for m in ap["prediction_set"]["members"]} == {
        "NETWORK_ACCESS_POINT", "WORKFLOW_APPROVAL_PROCESS",
    }
    for unit, start, end, full_end in [("byte", 5, 14, 17), ("codepoint", 2, 7, 8),
                                       ("utf16", 3, 8, 9)]:
        assert kdn["span"][unit] == {"start": start, "end": end}
        assert kdn["full_span"][unit] == {"start": start, "end": full_end}


def test_simple_terms_boundaries_and_longest_match(run_cli):
    doc = {"schema_version": 1, "terms": [
        {"key": "billing", "canonical": "빌링", "surfaces": ["ABC", "ABC"]},
        {"key": "console", "canonical": "빌링 콘솔"},
    ]}
    text = "ABC는 ABCD와 abc, 빌링 콘솔에 빌링."
    mentions = json.loads(run_cli(doc, text).stdout)["mentions"]
    assert [(m["surface"], m["resolved_entity"]["entity_id"]) for m in mentions] == [
        ("ABC", "project:billing"),
        ("빌링 콘솔", "project:console"),
        ("빌링", "project:billing"),
    ]


def test_invalid_glossary_fails_without_results(run_cli):
    result = run_cli({"schema_version": 1, "terms": [{"key": "broken"}]}, "ABC", check=False)
    assert result.returncode != 0
    assert result.stderr.strip()
    assert not result.stdout.strip()


def test_scoped_alias_and_derived_surface(run_cli):
    doc = {"schema_version": 3, "entities": [{"entity_id": "org", "canonical": "한국전력공사"}],
           "alias_bindings": [{"entity_id": "org", "surface": "한전",
                               "scope": {"allow": {"departments": ["network"]}}}]}
    result = run_cli(doc, "한전노조는 한전에서 협의했다.")
    mention, = json.loads(result.stdout)["mentions"]
    assert mention["span"]["codepoint"] == {"start": 6, "end": 8}
    assert mention["link_decision"] == "AMBIGUOUS"
    assert mention["prediction_set"]["members"] == [{"kind": "ENTITY", "entity_id": "org"}]
