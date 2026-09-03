"""Evaluation metrics with mandatory conditioning (spec §43).

Every metric must state its measurement condition (REQ-EVAL-001):
``E2E`` / ``|mention`` / ``|candidate`` / ``|commit``. Conformance is
reported as a *failure count*, never merged into coverage percentages
(REQ-LVL-003, §3.5).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

CONDITIONS = {"E2E", "|mention", "|candidate", "|commit"}


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion (§43.8)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


@dataclass
class Metric:
    name: str
    conditioning: str
    hits: int
    total: int

    @property
    def value(self) -> float:
        return self.hits / self.total if self.total else 0.0

    @property
    def ci95(self) -> tuple[float, float]:
        return wilson_interval(self.hits, self.total)

    def to_dict(self) -> dict:
        lo, hi = self.ci95
        return {
            "name": self.name,
            "conditioning": self.conditioning,
            "value": round(self.value, 4),
            "hits": self.hits,
            "total": self.total,
            "ci95": [round(lo, 4), round(hi, 4)],
        }


@dataclass
class EvalReport:
    metrics: list[Metric] = field(default_factory=list)
    # §3.5: conformance is failure-count based, kept apart from coverage
    conformance: dict = field(default_factory=dict)
    slices: dict[str, list[Metric]] = field(default_factory=dict)

    def add_metric(self, name: str, conditioning: str, hits: int, total: int,
                   slice_key: str | None = None) -> Metric:
        if conditioning not in CONDITIONS:
            raise ValueError(
                f"metric {name!r}: conditioning must be one of {sorted(CONDITIONS)} "
                f"(REQ-EVAL-001), got {conditioning!r}"
            )
        if "conformance" in name.lower():
            raise ValueError(
                "conformance is failure-count based and must not be reported "
                "as a coverage metric (REQ-LVL-003); use set_conformance()"
            )
        m = Metric(name, conditioning, hits, total)
        if slice_key is None:
            self.metrics.append(m)
        else:
            self.slices.setdefault(slice_key, []).append(m)
        return m

    def set_conformance(self, total: int, failed: int,
                        failures: list | None = None) -> None:
        self.conformance = {
            "total_fixtures": total,
            "failure_count": failed,  # target: 0 (REQ-LVL-002)
            "failures": failures or [],
        }

    def to_dict(self) -> dict:
        return {
            "conformance": self.conformance,
            "metrics": [m.to_dict() for m in self.metrics],
            "slices": {k: [m.to_dict() for m in v]
                       for k, v in self.slices.items()},
        }


def git_commit(repo_root=None) -> str | None:
    """Short HEAD SHA, ``-dirty`` if tracked files differ, None outside a repo.

    Every generated report stamps this. Without it a report and the code that
    produced it drift silently: a resolver change makes the committed numbers
    unreproducible, and nothing in the file says so.

    The suffix matters as much as the SHA. A report regenerated before its code
    was committed stamps the *parent* commit and looks authoritative — the
    numbers describe code that no commit contains. Only tracked files count;
    untracked scratch beside the repo is not part of what ran.

    ``reports/`` is excluded, and not as a convenience. Writing a report
    modifies a tracked file, so without the exclusion every regenerated report
    would stamp *itself* as proof the code had diverged — an alarm that fires
    on every run says nothing on the run that matters. Generated output cannot
    change what was measured; everything else can, and still counts.
    """
    import subprocess

    def _git(*args) -> str | None:
        try:
            out = subprocess.run(["git", *args],
                                 cwd=str(repo_root) if repo_root else None,
                                 capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout if out.returncode == 0 else None

    head = _git("rev-parse", "--short", "HEAD")
    if not head or not head.strip():
        return None
    status = _git("status", "--porcelain", "--untracked-files=no")
    changed = [ln for ln in (status or "").splitlines()
               if ln.strip() and not ln[3:].lstrip('"').startswith("reports/")]
    return head.strip() + ("-dirty" if changed else "")


def data_provenance(fingerprint: dict | None = None) -> str:
    """Identity of the wild corpus behind a report.

    Asked rather than declared: a harness that never read the corpus stamps
    nothing, and one that did cannot forget to. Harnesses whose inputs are
    synthetic have no data line, which is the honest result for them.

    A ``--render-only`` pass re-renders markdown from a saved payload without
    loading anything, so asking this process would drop the data line from a
    report that certainly had one. Those callers pass the fingerprint their
    payload recorded: the footer then names the corpus that produced the
    numbers, not whatever this process happens to hold.
    """
    fp = fingerprint
    if fp is None:
        try:
            from .wild_data import corpus_fingerprint
        except Exception:  # eval/ importable without its data module
            return ""
        fp = corpus_fingerprint()
    if not fp:
        return ""
    line = (f" · 코퍼스 `{fp['sha256']}` ({fp['sentences']:,}문장,"
            f" {fp['sources']}개 출처)")
    declared = fp.get("declared_sentences")
    if declared is not None and declared != fp["sentences"]:
        line += f" **캐시가 선언한 {declared:,}문장과 불일치**"
    return line


def provenance_line(repo_root=None, extra: str = "",
                    corpus: dict | None = None) -> str:
    """Markdown footer naming the code and data a report was measured at."""
    import time

    commit = git_commit(repo_root) or "unknown"
    stamp = time.strftime("%Y-%m-%d")
    tail = f" · {extra}" if extra else ""
    warn = (" **작업 트리가 커밋과 다르다 — 이 수치는 어떤 커밋에도 없는"
            " 코드의 것이다.**" if commit.endswith("-dirty") else "")
    return (f"*측정 시점: commit `{commit}`, {stamp}{tail}"
            f"{data_provenance(corpus)}.{warn} "
            "리포트와 코드가 어긋나면 코드가 맞다 — 재생성해서 확인할 것.*")
