"""The wheel's contract, checked without building a wheel.

`scripts/build_wheel.py` is the real proof - it installs into a clean venv
and runs the thing. That takes half a minute, so it is not in this suite.
What is here are the invariants that a wheel build would fail on, phrased
so they fail *at edit time* instead: a new subpackage without an
``__init__.py``, an import that reaches into `eval/`, a stray non-Python
file that would need package-data it does not have.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "ktrf"


def _pyproject() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def _package_dirs() -> list[Path]:
    return [d for d in PKG.rglob("*")
            if d.is_dir() and "__pycache__" not in d.parts]


def test_every_subpackage_is_importable_as_a_package():
    """setuptools' ``packages.find`` collects packages, not directories.

    A subpackage that forgets ``__init__.py`` is silently dropped from the
    wheel: the source tree keeps working (namespace packages), the wheel
    ships nothing, and the failure only appears on someone else's machine.
    """
    missing = [d.relative_to(ROOT) for d in _package_dirs()
               if not (d / "__init__.py").exists()]
    assert not missing, f"subpackages without __init__.py: {missing}"


def test_the_package_ships_no_data_files_it_has_not_declared():
    """Only ``py.typed`` is package data; anything else needs declaring."""
    declared = set(
        _pyproject()["tool"]["setuptools"]["package-data"].get("ktrf", []))
    on_disk = {p.name for p in PKG.rglob("*")
               if p.is_file() and p.suffix != ".py"
               and "__pycache__" not in p.parts}
    assert on_disk <= declared, (
        f"non-Python files present but not in [tool.setuptools.package-data]: "
        f"{sorted(on_disk - declared)}")


def test_py_typed_is_present_and_declared():
    """Annotations are pervasive here; without the marker no consumer's
    type checker is allowed to read a single one of them (PEP 561)."""
    assert (PKG / "py.typed").exists()
    declared = _pyproject()["tool"]["setuptools"]["package-data"].get("ktrf")
    assert "py.typed" in declared


def test_the_runtime_never_imports_the_measurement_harness():
    """`eval/`, `tests/` and `training/` are not in the wheel by design.

    An import of any of them from `ktrf/` is an ImportError on a clean
    install - the exact class of defect that only shows up downstream.
    """
    pattern = re.compile(r"^\s*(?:from|import)\s+(eval|tests|training)\b",
                         re.MULTILINE)
    offenders = []
    for path in PKG.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(ROOT)}: {match.group(0)!r}")
    assert not offenders, offenders


def test_every_module_parses_as_utf8():
    """Korean is everywhere in this package. A file written through a
    Windows ANSI code page decodes as mojibake or not at all."""
    for path in PKG.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        # composed syllables only: decomposed jamo compare unequal to the
        # glossary keys they are supposed to match
        assert not any("ᄀ" <= c <= "ᇿ" for c in source), (
            f"{path.relative_to(ROOT)} contains decomposed jamo")


def test_the_declared_console_script_actually_resolves():
    entry = _pyproject()["project"]["scripts"]
    assert entry, "no console scripts declared"
    for name, target in entry.items():
        module, _, func = target.partition(":")
        mod = pytest.importorskip(module)
        assert callable(getattr(mod, func, None)), (
            f"console script {name} points at {target}, which is not callable")


def test_the_base_install_stays_dependency_light():
    """The symbolic core is the product; the neural stack is an option.

    If a heavy runtime ever lands in ``dependencies``, every consumer who
    only wanted Level A pays for it.
    """
    deps = _pyproject()["project"]["dependencies"]
    assert deps == ["PyYAML>=6.0"], (
        f"base dependencies changed to {deps}; heavy runtimes belong in "
        f"[project.optional-dependencies]")
    heavy = {"torch", "onnxruntime", "onnxruntime-gpu", "transformers",
             "numpy", "tokenizers"}
    assert not {d.split(">")[0].split("=")[0] for d in deps} & heavy


def test_the_version_is_single_sourced():
    """`ktrf.__version__` must come from the metadata, never a second
    literal that drifts from the one in pyproject.toml."""
    import ktrf

    source = (PKG / "__init__.py").read_text(encoding="utf-8")
    assert "importlib.metadata" in source
    # The only literal allowed is the "never installed" sentinel. A real
    # version number here is a second source of truth waiting to drift.
    literals = set(re.findall(r'__version__\s*=\s*["\']([^"\']+)', source))
    assert literals <= {"0.0.0+unknown"}, (
        f"__version__ is hard-coded as {sorted(literals)}; it must be read "
        f"from package metadata")
    # in an installed/editable tree it should agree with pyproject
    if ktrf.__version__ != "0.0.0+unknown":
        assert ktrf.__version__ == _pyproject()["project"]["version"]


def test_the_license_is_declared_and_the_file_it_names_exists():
    """Metadata and file, or neither.

    A `license` field naming a file that is not there produces a wheel that
    claims terms it does not carry, which is worse than the state before —
    no field and no file, where at least nothing was asserted. The SPDX
    expression form (PEP 639) is what is checked, because a `License ::`
    classifier is deprecated and would be read by nothing.
    """
    project = _pyproject()["project"]
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    for name in project["license-files"]:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "MIT License" in text
        assert re.search(r"Copyright \(c\) \d{4}", text)
    # the classifier form must not linger beside the expression: two
    # declarations can disagree, and only one of them is authoritative
    assert not [c for c in project["classifiers"] if c.startswith("License ::")]


def test_the_build_backend_is_new_enough_for_the_license_form():
    """PEP 639 needs setuptools 77+; an older one drops the field silently.

    Pinning the floor is what turns "the wheel has no license" from a thing
    someone notices on PyPI into a build error.
    """
    requires = _pyproject()["build-system"]["requires"]
    floor = next(r for r in requires if r.startswith("setuptools"))
    assert int(re.search(r">=(\d+)", floor).group(1)) >= 77
