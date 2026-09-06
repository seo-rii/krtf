#!/usr/bin/env python3
"""Build the KTRF wheel + sdist, then prove the wheel actually works.

Building is the easy half. The half that catches real defects is the
verification: install the built wheel into a *throwaway* venv, from a
*different working directory*, and exercise it. Running the smoke test
from the repository root is the classic false pass - ``import ktrf`` finds
the source tree and the wheel is never touched, so a wheel that ships no
modules at all still "passes".

Cross-platform by construction: no shell, no shell quoting, and the venv
layout difference (Scripts/ vs bin/) is the only branch in the file.

    python scripts/build_wheel.py             # build + verify
    python scripts/build_wheel.py --no-verify
    python scripts/build_wheel.py --keep      # keep the verification venv
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

# Weights are fetched, never shipped (docs/PACKAGING.md). A wheel that grew
# past a few MB has almost certainly swallowed a model directory or the
# evaluation corpus, so fail loudly well before PyPI's 100MB file limit.
MAX_WHEEL_BYTES = 8 * 1024 * 1024


def _env() -> dict[str, str]:
    """UTF-8 everywhere. This project's sources are full of Korean, and on
    Windows a child Python still defaults to the ANSI code page, which has
    produced mojibake and hard build failures here before."""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(cmd: list, cwd: Path | None = None) -> None:
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, env=_env(), check=True)


def venv_python(root: Path) -> Path:
    """Scripts/python.exe on Windows, bin/python elsewhere."""
    if os.name == "nt":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def venv_script(root: Path, name: str) -> Path:
    bindir = root / ("Scripts" if os.name == "nt" else "bin")
    return bindir / (name + ".exe" if os.name == "nt" else name)


def clean() -> None:
    print("[1/4] clean")
    for path in (DIST, ROOT / "build"):
        if path.exists():
            shutil.rmtree(path)
            print("  removed " + str(path.relative_to(ROOT)))
    for egg in ROOT.glob("*.egg-info"):
        shutil.rmtree(egg)
        print("  removed " + str(egg.relative_to(ROOT)))


def build() -> None:
    print("[2/4] build")
    try:
        import build  # noqa: F401
    except ImportError:
        print("  'build' not installed; installing it into this interpreter")
        run([sys.executable, "-m", "pip", "install", "--quiet", "build>=1.2"])
    run([sys.executable, "-m", "build", "--outdir", DIST], cwd=ROOT)


def _dist_version(names: list) -> str:
    for n in names:
        if n.endswith(".dist-info/METADATA"):
            return n.split("/")[0][len("ktrf-"):-len(".dist-info")]
    raise SystemExit("wheel has no .dist-info/METADATA")


def inspect() -> Path:
    """Report what the wheel contains and refuse the obvious mistakes."""
    print("[3/4] inspect")
    wheels = sorted(DIST.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("expected exactly one wheel in dist/, got "
                         + str([w.name for w in wheels]))
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        size = sum(i.file_size for i in z.infolist())

    tops = sorted({n.split("/")[0] for n in names})
    allowed = {"ktrf", "ktrf-" + _dist_version(names) + ".dist-info"}
    print("  " + wheel.name)
    print("  {} entries, {} KiB uncompressed, {} KiB on disk".format(
        len(names), size // 1024, wheel.stat().st_size // 1024))
    print("  top-level: " + str(tops))

    stray = sorted(set(tops) - allowed)
    if stray:
        raise SystemExit("wheel ships unexpected top-level names: "
                         + str(stray))
    if size > MAX_WHEEL_BYTES:
        raise SystemExit("wheel is {} MiB - it has probably absorbed model "
                         "weights or eval data".format(size // 1024 // 1024))
    if "ktrf/py.typed" not in names:
        raise SystemExit("ktrf/py.typed is missing: consumers get no types")
    print("  py.typed present, no stray top-level names, size sane")

    _inspect_sdist()
    return wheel


def _inspect_sdist() -> None:
    """MANIFEST.in is an allowlist, so exclusion is by silence. Silence is
    not proof - check that the things that must never ship really did not,
    and that the archive did not quietly balloon."""
    sdists = sorted(DIST.glob("*.tar.gz"))
    if not sdists:
        return
    sdist = sdists[0]
    import tarfile

    with tarfile.open(sdist) as t:
        members = [m.name.split("/", 1)[1]
                   for m in t.getmembers() if m.isfile() and "/" in m.name]
        size = sum(m.size for m in t.getmembers() if m.isfile())

    forbidden = [n for n in members
                 if n.startswith(("models/", "reports/", "eval/out/"))
                 or n.endswith((".pyc", ".onnx", ".safetensors", ".bundle"))
                 or n.startswith("REVIEW")]
    if forbidden:
        raise SystemExit("sdist ships files it must not: " + str(forbidden[:8]))
    if size > MAX_WHEEL_BYTES:
        raise SystemExit("sdist is {} MiB - check MANIFEST.in".format(
            size // 1024 // 1024))
    print("  {}: {} files, {} KiB, no weights or measurement output".format(
        sdist.name, len(members), size // 1024))


SMOKE = r'''
import importlib
import pkgutil
import sys
from pathlib import Path

import ktrf

# 1. The wheel is what got imported, not the source tree next door.
here = Path(ktrf.__file__).resolve()
assert "site-packages" in here.parts, "imported the source tree: %s" % here

# 2. Every module imports with only the base dependency installed. This is
#    what catches a subpackage that setuptools silently dropped.
mods = [m.name for m in pkgutil.walk_packages(ktrf.__path__, "ktrf.")]
bad = []
for name in mods:
    try:
        importlib.import_module(name)
    except Exception as exc:
        bad.append((name, type(exc).__name__, str(exc)[:80]))
assert not bad, "import failures: %s" % (bad,)

# 3. py.typed survived as real package data, not just a metadata claim.
assert (here.parent / "py.typed").exists(), "py.typed missing from install"

# 3b. So did the published schemas. They are read off disk, so a wheel that
#     ships the code without the data raises on a host's machine while
#     passing from every source checkout.
from ktrf.schemas import NAMES, load_schema
for _name in NAMES:
    assert load_schema(_name)["$id"].endswith("%s.schema.json" % _name)

# 4. It actually resolves Korean text end to end.
glossary = ktrf.load_glossary(sys.argv[1])
snapshot = ktrf.compile_snapshot(glossary)
resp = ktrf.resolve(snapshot, "한전KDN은 AP 장애 "
                              "내용을 QMS에 "
                              "등록했다.", mode="commit")
surfaces = [m["surface"] for m in resp["mentions"]]
assert surfaces, "resolve returned no mentions"

print("    version   %s" % ktrf.__version__)
print("    modules   %d imported, 0 failures" % len(mods))
print("    resolve   %s" % surfaces)
print("    schemas   %s" % ", ".join(NAMES))
'''


def verify(wheel: Path, keep: bool) -> None:
    print("[4/4] verify")
    tmp = Path(tempfile.mkdtemp(prefix="ktrf-verify-"))
    try:
        env_dir = tmp / "venv"
        print("  creating a clean venv at " + str(env_dir))
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
        py = venv_python(env_dir)
        run([py, "-m", "pip", "install", "--quiet", wheel])

        smoke = tmp / "smoke.py"
        smoke.write_text(SMOKE, encoding="utf-8")
        glossary = ROOT / "examples" / "demo_glossary.yaml"
        # cwd=tmp so `import ktrf` cannot fall back to the source tree
        run([py, smoke, glossary], cwd=tmp)

        # The console script is generated at install time, so check that it
        # exists and launches rather than trusting the metadata alone.
        script = venv_script(env_dir, "ktrf-pi")
        if not script.exists():
            raise SystemExit("console script not installed at " + str(script))
        proc = subprocess.run([str(script)], input="", capture_output=True,
                              text=True, env=_env(), timeout=120)
        if proc.returncode != 0:
            raise SystemExit("ktrf-pi exited {}: {}".format(
                proc.returncode, proc.stderr[:300]))
        print("    entry     ktrf-pi runs, exits 0 on empty stdin")
    finally:
        if keep:
            print("  kept " + str(tmp))
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build and verify the KTRF wheel.")
    ap.add_argument("--no-verify", action="store_true",
                    help="build only; skip the clean-venv install check")
    ap.add_argument("--keep", action="store_true",
                    help="keep the verification venv for inspection")
    args = ap.parse_args()

    print("KTRF wheel build - Python {} on {}".format(
        sys.version.split()[0], sys.platform))
    clean()
    build()
    wheel = inspect()
    if args.no_verify:
        print("[4/4] verify SKIPPED (--no-verify)")
    else:
        verify(wheel, args.keep)

    print("\nartifacts in dist/:")
    for f in sorted(DIST.iterdir()):
        print("  {}  ({} KiB)".format(f.name, f.stat().st_size // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
