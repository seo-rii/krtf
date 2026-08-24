"""Requirement traceability verification (spec §1.2, §45.7, REQ-EVAL-003).

CI fails when: a REQ maps to a nonexistent test, a spec REQ is neither
implemented nor deferred, or a REQ appears in both lists.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "docs" / "traceability.yaml"
SPEC = ROOT / "PLAN.md"

_REQ_RE = re.compile(r"REQ-[A-Z]+-\d+")


def _load():
    with open(MATRIX, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_mapped_tests_exist():
    data = _load()
    for entry in data["implemented"]:
        assert entry["tests"], f"{entry['req']}: empty test list"
        for ref in entry["tests"]:
            path, _, func = ref.partition("::")
            file = ROOT / path
            assert file.exists(), f"{entry['req']}: missing file {path}"
            assert func, f"{entry['req']}: test ref {ref} lacks ::function"
            src = file.read_text(encoding="utf-8")
            assert f"def {func}(" in src, (
                f"{entry['req']}: {path} does not define {func}"
            )


def test_all_reqs_mapped():
    # REQ-EVAL-003: every spec REQ id is either implemented(+tested) or
    # explicitly deferred with a reason
    data = _load()
    implemented = {e["req"] for e in data["implemented"]}
    deferred = {e["req"] for e in data["deferred"]}
    assert not implemented & deferred, implemented & deferred
    spec_reqs = set(_REQ_RE.findall(SPEC.read_text(encoding="utf-8")))
    unmapped = spec_reqs - implemented - deferred
    assert not unmapped, f"unmapped spec REQs: {sorted(unmapped)}"
    for e in data["deferred"]:
        assert e.get("reason"), f"{e['req']}: deferred without reason"


def test_no_unknown_reqs_in_matrix():
    data = _load()
    spec_reqs = set(_REQ_RE.findall(SPEC.read_text(encoding="utf-8")))
    for section in ("implemented", "deferred"):
        for e in data[section]:
            assert e["req"] in spec_reqs, f"{e['req']} not defined in PLAN.md"
