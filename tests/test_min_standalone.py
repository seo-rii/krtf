import json
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cli(tmp_path):
    script = shutil.copy(ROOT / "min" / "krtf.py", tmp_path)

    def run(*args, stdin=None, check=True):
        return subprocess.run(
            [sys.executable, "-I", "-S", script, *args],
            cwd=tmp_path, input=stdin, capture_output=True, encoding="utf-8",
            check=check, timeout=10,
        )

    return run


@pytest.fixture
def run_cli(tmp_path, cli):
    glossary = tmp_path / "glossary.json"

    def run(doc, *args, **kwargs):
        glossary.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return cli(glossary, *args, **kwargs)

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


def test_compiled_cli_works_after_removing_source(tmp_path, cli):
    demo = yaml.safe_load((ROOT / "examples/demo_glossary.yaml").read_text(encoding="utf-8"))
    source = tmp_path / "demo.json"
    source.write_text(json.dumps(demo, ensure_ascii=False), encoding="utf-8")
    artifact = tmp_path / "demo.snapshot"
    text = "🎉 한전KDN은 AP 장애 내용을 QMS에 등록했다."
    expected = json.loads(cli(source, text).stdout)
    cli("compile", source, artifact)
    source.unlink()
    assert json.loads(cli("load", artifact, stdin=text).stdout) == expected
    assert json.loads(cli("load", artifact, text).stdout) == expected


def test_snapshot_api_preserves_alias_restrictions(tmp_path):
    api = runpy.run_path(str(ROOT / "min" / "krtf.py"))
    doc = {"schema_version": 3, "entities": [{"entity_id": "local", "canonical": "강원도"}],
           "alias_bindings": [{"entity_id": "local", "surface": "강원도",
                               "scope": {"allow": {"departments": ["local"]}}}]}
    original = api["compile_snapshot"](doc)
    artifact = tmp_path / "only.snapshot"
    api["save_snapshot"](original, artifact)
    loaded = api["load_snapshot"](artifact)
    text = "강원도에서 발표했다."
    result = api["resolve"](loaded, text)
    assert result == api["resolve"](original, text)
    mention, = result["mentions"]
    assert mention["link_decision"] == "AMBIGUOUS"
    assert mention["prediction_set"]["members"] == [{"kind": "ENTITY", "entity_id": "local"}]


def test_load_rejects_invalid_artifacts(tmp_path, cli):
    source = tmp_path / "terms.json"
    source.write_text('{"terms":[{"key":"org","canonical":"ABC"}]}', encoding="utf-8")
    artifact = tmp_path / "terms.snapshot"
    cli("compile", source, artifact)
    data = artifact.read_bytes()
    damaged = bytearray(data)
    damaged[len(data) // 2] ^= 1
    for invalid in (damaged, data[:len(data) // 2], b'{"format":"unknown"}'):
        artifact.write_bytes(invalid)
        result = cli("load", artifact, "ABC", check=False)
        assert result.returncode != 0
        assert result.stderr.strip()
        assert not result.stdout.strip()


def test_failed_compile_preserves_previous_snapshot(tmp_path, cli):
    source = tmp_path / "terms.json"
    source.write_text('{"terms":[{"key":"org","canonical":"ABC"}]}', encoding="utf-8")
    artifact = tmp_path / "terms.snapshot"
    cli("compile", source, artifact)
    previous = artifact.read_bytes()
    source.write_text("{", encoding="utf-8")
    assert cli("compile", source, artifact, check=False).returncode != 0
    assert artifact.read_bytes() == previous
    mention, = json.loads(cli("load", artifact, "ABC").stdout)["mentions"]
    assert mention["resolved_entity"]["entity_id"] == "project:org"
