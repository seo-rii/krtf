"""The same input against the same snapshot answers the same in every process.

Within one process the resolver was deterministic, which is all the existing
determinism tests could see. Across processes it was not: the jamo
shortlist broke count ties in set-iteration order, so which tied entries
survived its truncation depended on PYTHONHASHSEED. A wild-corpus sentence
against the 1,000-entity synthetic glossary returned three prediction-set
members under seeds 0, 5 and 9 and two under the rest — found only because a
differential run of two code versions compared two processes.

Each seed runs in its own interpreter, because the hash seed is fixed at
interpreter start.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROBE = r"""
import json, sys
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot
from eval.synthetic import build_synthetic_glossary

texts = json.loads(sys.stdin.buffer.read().decode("utf-8"))
snaps = {
    "realorg": compile_snapshot(
        load_glossary("examples/realorg_glossary.yaml"), strict=False),
    "synthetic": compile_snapshot(
        load_glossary(build_synthetic_glossary(1000, seed=20260903)[0]),
        run_conformance=False),
}
out = []
for name, snap in snaps.items():
    for t in texts:
        for mode in ("commit", "fast"):
            r = resolve(snap, t, mode=mode)
            for k in ("elapsed_ms", "timing", "deadline", "trace"):
                r.pop(k, None)
            out.append(json.dumps(r, ensure_ascii=False, sort_keys=True,
                                  default=str))
sys.stdout.buffer.write(json.dumps(out).encode("utf-8"))
"""

TEXTS = [
    # the sentence that exposed it
    "각 전기공급약관은 한국전력공사법에 따라 주무부장관에 인가신청하고 "
    "기획재정부장관과의 협의와 산하 전기위원회의 심의를 거쳐 인가한다.",
    # typo-bearing text, so the jamo and keyboard channels have work to do
    "한국전력공시가 국토교통뷰와 협의했다. 겁찰청은 gkswjs 관련 수사를 했다.",
    "산업통상자윈부와 과학기술정보통싱부, 그리고 금융위원회가 발표했다.",
    "한전KDN이 구한전 자회사이며 국정원의 발표는 없었다.",
]


def _run(seed: str) -> list[str]:
    env = {**os.environ, "PYTHONHASHSEED": seed,
           "PYTHONPATH": str(ROOT) + os.pathsep
           + os.environ.get("PYTHONPATH", "")}
    proc = subprocess.run([sys.executable, "-c", PROBE],
                          input=json.dumps(TEXTS, ensure_ascii=False)
                          .encode("utf-8"),
                          capture_output=True, cwd=ROOT, env=env,
                          timeout=300)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return json.loads(proc.stdout.decode("utf-8"))


def test_answers_do_not_depend_on_the_hash_seed():
    baseline = _run("1")
    for seed in ("0", "5", "9"):
        other = _run(seed)
        bad = [i for i, (a, b) in enumerate(zip(baseline, other)) if a != b]
        assert not bad, f"seed {seed} differs from seed 1 at responses {bad}"
