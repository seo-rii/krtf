import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "min" / "krtf.py"
api = runpy.run_path(str(SCRIPT))


def cli(*args, stdin=None, check=True):
    return subprocess.run([sys.executable, "-I", "-S", SCRIPT, *args], input=stdin,
                          encoding="utf-8", capture_output=True, check=check, timeout=20)


@pytest.mark.parametrize(("ext", "delimiter"), [("csv", ","), ("tsv", "\t")])
def test_table_compile_and_batch(tmp_path, ext, delimiter):
    source = tmp_path / f"terms.{ext}"
    data = [["id", "canonical", "alias", "definition"],
            ["ORG", "한국전력공사", "한전", '"전력, 공기업"'],
            ["ORG", "한국전력공사", "KEPCO", ""]]
    source.write_text("\n".join(delimiter.join(row) for row in data), encoding="utf-8-sig")
    artifact = tmp_path / "terms.krtf"
    cli("compile", source, artifact)
    source.unlink()
    lines = ['{"id":1,"text":"한전에서"}', '{broken', '{"id":"b","text":"kepco"}']
    result = cli("batch", artifact, stdin="\n".join(lines), check=False)
    assert result.returncode == 1
    first, error, last = map(json.loads, result.stdout.splitlines())
    assert first["id"] == 1 and last["id"] == "b"
    assert error["line"] == 2 and error["error"]
    for row in (first, last):
        assert row["mentions"][0]["resolved_entity"]["entity_id"] == "ORG"
    assert json.loads(cli("lookup", artifact, "ＫＥＰＣＯ").stdout)["candidates"][0][
        "definition"] == "전력, 공기업"


def test_project_scope_and_dates_survive_compilation(tmp_path):
    doc = {"schema_version": 3, "entities": [
        {"entity_id": "A", "canonical": "첫번째", "valid_from": "2026-03-01"},
        {"entity_id": "B", "canonical": "두번째"}], "alias_bindings": [
            {"surface": "MX", "entity_id": "A", "scope": {"allow": {"departments": ["network"]}}},
            {"surface": "MX", "entity_id": "B", "scope": {"allow": {"projects": ["billing"]}}},
            {"surface": "MX", "entity_id": "B", "scope": {"allow": {"projects": ["review"]}}}]}
    artifact = tmp_path / "table.krtf"
    api["save_snapshot"](api["compile_snapshot"](doc), artifact)
    snap = api["load_snapshot"](artifact)
    def hits(**context):
        return api["resolve"](snap, "MX", **context)["mentions"]
    assert hits()[0]["link_decision"] == "AMBIGUOUS"
    assert hits(department="network", project="else", as_of="2026-03-01")[0][
        "resolved_entity"]["entity_id"] == "A"
    assert hits(department="network", project="review", as_of="2025-12-31")[0][
        "resolved_entity"]["entity_id"] == "B"
    assert hits(department="network", project="else", as_of="2026-02-28") == []


def test_layered_compile_lookup_and_conflict_inventory(tmp_path):
    base = tmp_path / "base.json"
    project = tmp_path / "project.json"
    output = tmp_path / "both.krtf"
    base.write_text(json.dumps({"terms": [{"key": "base", "canonical": "General", "surfaces": ["ABC"]}]}))
    project.write_text(json.dumps({"terms": [{"key": "local", "canonical": "Billing", "surfaces": ["abc"]}]}))
    cli("compile", base, output, "--layer", f"project={project}")
    for alias in ("ABC", "abc", "ＡＢＣ"):
        [mention] = json.loads(cli("load", output, alias).stdout)["mentions"]
        assert mention["resolved_entity"]["entity_id"] == "project:local"
    assert json.loads(cli("info", output).stdout)["conflicts"][0]["shadowed"] == ["base:base"]
    assert json.loads(cli("explain", output, "abc").stdout)["mentions"][0]["link_reason"]
    assert json.loads(cli("diff", base, output).stdout)["surfaces"]["removed"] == ["ABC"]
    assert json.loads(cli("lint", project).stdout) == []


def test_v1_snapshot_load_and_resave_preserve_unknown_restriction(tmp_path):
    body = json.dumps({"names": {"org": "한전"}, "buckets": {"한": [["한전", {"org": False}]]}}).encode()
    artifact = tmp_path / "legacy.krtf"
    artifact.write_bytes(b"KRTF-MIN/1\n" + hashlib.sha256(body).hexdigest().encode() + b"\n" + body)
    snapshot = api["load_snapshot"](artifact)
    api["save_snapshot"](snapshot, artifact)
    assert artifact.read_bytes().startswith(b"KRTF-MIN/2\n")
    mention, = json.loads(cli("load", artifact, "한전에서", "--department", "network").stdout)["mentions"]
    assert mention["link_decision"] == "AMBIGUOUS"
