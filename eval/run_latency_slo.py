"""Where does the time go, and where does the resolver stop doing the work?

Usage: python -m eval.run_latency_slo [--scales 200,1000,3000]
                                      [--sizes 200,800,3200]
                                      [--repeats N] [--threads N]
                                      [--json PATH] [--compare PATH]
                                      [--render-only PATH]

The ROADMAP asks for a latency/memory gate — p95/p99 by document size and
entity scale, plus concurrency, hot-swap and rollback under load. This is the
measurement half; the correctness half is `tests/test_concurrency_and_swap.py`.

The gate is deliberately *relative*. An absolute SLO names reference hardware,
§53 leaves that open, and a threshold measured on whatever machine CI happened
to schedule is a coin flip dressed as a contract. So the report records the
machine and only a `--compare` against a control payload can fail.

Two things measuring this taught, both of which shaped the harness:

**A document built by repetition measures the cache.** Filling a document by
repeating one sentence made latency go *sublinear* — 7x the text for 1.8x the
time — because the same handful of tokens were being answered over and over.
Documents here are built from distinct real corpus sentences instead.

**Latency plateaus because the resolver stops, not because it is fast.** Past
a few hundred characters a response comes back `degraded`, and after that
point more text does not cost proportionally more time. So the number worth
publishing is not a p95 at some arbitrary size — it is the size at which the
resolver begins capping its own work, measured against the input the
synchronous API actually accepts.

Writes eval/out/latency_slo.json and reports/LATENCY_SLO.md.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import statistics
import sys
import threading
import time
import tracemalloc
from pathlib import Path

from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import SnapshotRegistry, compile_snapshot

from .metrics import provenance_line
from .synthetic import build_synthetic_glossary
from .wild_data import corpus_fingerprint, load_corpus

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260903
ONSET_STEPS = (50, 100, 150, 200, 250, 300, 350, 400, 500, 600, 800,
               1200, 1600, 2400, 3200)

#: Concurrency levels for the sweep. Every level does the SAME total work, so
#: the comparison is "the same requests, arranged differently" rather than
#: "more threads, more requests" — otherwise the arms are not comparable and
#: the wall clock says nothing.
CONCURRENCY_LEVELS = (1, 10, 100)
SWEEP_RESOLVES = 100

# Smallest `--compare` difference worth reading, as a fraction of the control.
#
# Measured, not chosen: two full runs of this harness at the same commit on the
# same machine disagreed by up to 26% on p50. The interleaved-block drift each
# cell reports is an order of magnitude smaller (<2%) because it only sees
# noise *inside* one run — and a comparison is always across two, usually in
# two worktrees. Using the within-run number as the threshold would have
# reported a quarter of the machine's own weather as a regression.
BETWEEN_RUN_FLOOR = 0.25


def _pct(values: list[float], q: float) -> float:
    """Nearest-rank percentile — no interpolation between two timings."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(q * len(ordered) + 0.5)) - 1))
    return round(ordered[k], 3)


class _Documents:
    """Documents of a target length, built from *distinct* real sentences.

    Repetition would measure the caches rather than the work; the same
    generator with one repeated sentence turned a linear curve sublinear.
    """

    def __init__(self, pool: list[str]):
        self.pool = pool

    def of(self, chars: int, offset: int = 0) -> str:
        out, total, i = [], 0, offset
        while total < chars:
            s = self.pool[i % len(self.pool)]
            out.append(s)
            total += len(s) + 1
            i += 1
        return " ".join(out)[:chars]


def _time_resolves(snap, text: str, repeats: int) -> list[float]:
    out = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        resolve(snap, text, mode="commit")
        out.append((time.perf_counter() - t0) * 1000)
    return out


def _timed_halves(snap, text: str, repeats: int) -> tuple[list, float]:
    """Every sample, plus how stable the cell was *within this run*.

    The repeats are split into two interleaved blocks and the gap between
    their medians is published beside the number. It says the cell agrees with
    itself; it is emphatically **not** the comparison threshold, which lives
    in :data:`BETWEEN_RUN_FLOOR` — the within-run figure came out under 2%
    while two runs at the same commit disagreed by 26%, and using the small
    one as a gate would report the machine's weather as a regression.
    """
    a, b = [], []
    for i in range(repeats):
        t0 = time.perf_counter()
        resolve(snap, text, mode="commit")
        (a if i % 2 == 0 else b).append((time.perf_counter() - t0) * 1000)
    drift = (abs(statistics.median(a) - statistics.median(b))
             if a and b else 0.0)
    return a + b, round(drift, 1)


def _degradation_onset(snap, docs: _Documents) -> dict:
    """Smallest measured document length whose response comes back degraded.

    `degraded` is one boolean for the whole response, so this is the point
    past which *some* answer in it was capped — the consumer is not told which.
    """
    first = None
    seen = []
    for n in ONSET_STEPS:
        # three different documents at each length: onset is a property of the
        # length, not of whichever sentences happened to land there
        hits = sum(1 for k in range(3)
                   if resolve(snap, docs.of(n, offset=k * 37),
                              mode="commit")["degraded"])
        seen.append({"chars": n, "degraded_of_3": hits})
        if first is None and hits == 3:
            first = n
    return {"first_always_degraded_chars": first, "ladder": seen}


def _concurrency_sweep(snap, text: str,
                       levels=CONCURRENCY_LEVELS) -> list[dict]:
    """The same work at 1, 10 and 100 concurrent callers.

    Under the GIL this is not a throughput claim. What it can answer is
    whether contention degrades the tail or breaks anything — a p95 that
    collapses at 100 callers, or a single error, is the finding.
    """
    out = []
    for level in levels:
        per = max(1, SWEEP_RESOLVES // level)
        lock = threading.Lock()
        samples: list[float] = []
        errors: list[Exception] = []

        def worker():
            try:
                mine = _time_resolves(snap, text, per)
            except Exception as exc:            # noqa: BLE001 - reported
                with lock:
                    errors.append(exc)
                return
            with lock:
                samples.extend(mine)

        pool = [threading.Thread(target=worker) for _ in range(level)]
        t0 = time.perf_counter()
        for t in pool:
            t.start()
        for t in pool:
            t.join()
        wall = time.perf_counter() - t0
        done = per * level
        out.append({
            "concurrency": level,
            "resolves": done,
            "wall_s": round(wall, 2),
            "throughput_per_s": round(done / wall, 1) if wall else None,
            "p50_ms": _pct(samples, 0.50),
            "p95_ms": _pct(samples, 0.95),
            "max_ms": round(max(samples), 1) if samples else None,
            "errors": len(errors),
        })
    return out


def _deadline_effect(snap, text: str, unbounded: list[float],
                     repeats: int) -> dict:
    """What a wall-clock budget actually buys on the tail.

    The budget is set at the unbounded p50, so half the requests would have
    finished inside it anyway and the interesting half is the other one. The
    floor is not zero and is not meant to be: Level A always runs, so a budget
    below the exact pass buys nothing further, and the overshoot is reported
    rather than smoothed away.
    """
    budget = max(1, int(_pct(unbounded, 0.50)))
    samples, shed = [], 0
    for _ in range(repeats):
        t0 = time.perf_counter()
        resp = resolve(snap, text, mode="commit",
                       options={"deadline_ms": budget})
        samples.append((time.perf_counter() - t0) * 1000)
        shed += int(bool(resp.get("deadline", {}).get("skipped_stages")))
    return {
        "budget_ms": budget,
        "unbounded_p95_ms": _pct(unbounded, 0.95),
        "unbounded_max_ms": round(max(unbounded), 1),
        "bounded_p95_ms": _pct(samples, 0.95),
        "bounded_max_ms": round(max(samples), 1),
        "shed_rate": round(shed / repeats, 3) if repeats else None,
    }


def measure(scales, sizes, repeats, threads) -> dict:
    corpus = [r["text"] if isinstance(r, dict) else r for r in load_corpus()]
    docs = _Documents(random.Random(SEED).sample(corpus, min(6000,
                                                             len(corpus))))
    rows, build, memory, concurrency, onsets = [], [], [], [], []
    deadlines: list[dict] = []
    sweeps: list[dict] = []

    for n in scales:
        doc, _meta = build_synthetic_glossary(n, seed=SEED)
        glossary = load_glossary(doc)

        tracemalloc.start()
        t0 = time.perf_counter()
        snap = compile_snapshot(glossary, run_conformance=False)
        compile_ms = (time.perf_counter() - t0) * 1000
        _cur, compile_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Cold: the first resolve a freshly compiled snapshot ever serves.
        # Taken here, before anything else touches the snapshot, because
        # every later measurement in this loop is warm by construction.
        cold_text = docs.of(sizes[len(sizes) // 2])
        _t = time.perf_counter()
        resolve(snap, cold_text, mode="commit")
        cold_ms = (time.perf_counter() - _t) * 1000

        reg = SnapshotRegistry()
        # measured apart from compile: this is what a hot swap costs, and it
        # is dominated by the integrity re-check rather than by the swap
        act, ver = [], []
        for _ in range(7):
            t0 = time.perf_counter()
            snap.verify_integrity()
            ver.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            reg.activate(snap, allow_unverified=True)
            act.append((time.perf_counter() - t0) * 1000)

        build.append({
            "entities": n,
            "compile_ms": round(compile_ms, 1),
            "verify_integrity_ms_p50": round(statistics.median(ver), 1),
            "activate_ms_p50": round(statistics.median(act), 1),
            "compile_peak_mb": round(compile_peak / 1e6, 1),
            "cold_resolve_ms": round(cold_ms, 1),
            "cold_doc_chars": sizes[len(sizes) // 2],
        })

        for size in sizes:
            text = docs.of(size)
            _time_resolves(snap, text, 2)          # warm
            samples, drift = _timed_halves(snap, text, repeats)
            degraded = resolve(snap, text, mode="commit")["degraded"]
            rows.append({
                "entities": n, "doc_chars": size,
                "p50_ms": _pct(samples, 0.50),
                "p95_ms": _pct(samples, 0.95),
                # a p99 over 30 draws is the maximum wearing a percentile's
                # name; report it only when there are enough samples for the
                # rank to mean something
                "p99_ms": (_pct(samples, 0.99) if len(samples) >= 100
                           else None),
                "max_ms": round(max(samples), 3),
                "drift_ms": drift,
                "degraded": degraded,
                "samples": len(samples),
            })

        onsets.append({"entities": n, **_degradation_onset(snap, docs)})

        # the budget is exercised at the largest size, where the tail is
        largest = docs.of(sizes[-1])
        # fewer repeats than a latency cell: this arm is asking whether the
        # budget bites, not publishing a percentile, and the largest document
        # at the largest scale is the most expensive sample in the harness
        budget_repeats = max(8, repeats // 3)
        unbounded, _drift = _timed_halves(snap, largest, budget_repeats)
        deadlines.append({"entities": n, "doc_chars": sizes[-1],
                          **_deadline_effect(snap, largest, unbounded,
                                             budget_repeats)})
        # the sweep uses the smallest document: it is asking about contention,
        # not about how long one document takes
        sweeps.append({"entities": n, "doc_chars": sizes[0],
                       "levels": _concurrency_sweep(snap, docs.of(sizes[0]))})

        mid = docs.of(sizes[len(sizes) // 2])
        tracemalloc.start()
        _time_resolves(snap, mid, 10)
        _cur, resolve_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory.append({"entities": n,
                       "resolve_peak_mb": round(resolve_peak / 1e6, 2),
                       "doc_chars": sizes[len(sizes) // 2]})

        # Under the GIL this is not a parallelism claim; it checks that
        # contention does not make things *worse* and that nothing errors.
        #
        # The two arms are alternated and reduced to medians. Run once each,
        # minutes apart, they measure drift as much as contention: the first
        # version of this had a serial arm reporting 1,486 ms per resolve
        # against its own p50 of 710 ms, and a 1,000-entity glossary looking
        # slower than a 3,000-entity one.
        per_thread = max(2, repeats // 10)
        errors: list[Exception] = []

        def worker():
            try:
                _time_resolves(snap, mid, per_thread)
            except Exception as exc:
                errors.append(exc)

        serial_runs, threaded_runs = [], []
        for _ in range(3):
            t0 = time.perf_counter()
            _time_resolves(snap, mid, per_thread * threads)
            serial_runs.append(time.perf_counter() - t0)

            pool = [threading.Thread(target=worker) for _ in range(threads)]
            t0 = time.perf_counter()
            for t in pool:
                t.start()
            for t in pool:
                t.join()
            threaded_runs.append(time.perf_counter() - t0)

        serial_s = statistics.median(serial_runs)
        threaded_s = statistics.median(threaded_runs)
        done = per_thread * threads
        concurrency.append({
            "entities": n, "threads": threads,
            "resolves_per_arm": done,
            "serial_ms_per_resolve": round(serial_s / done * 1000, 1),
            "threaded_ms_per_resolve": round(threaded_s / done * 1000, 1),
            "spread_serial_ms": round((max(serial_runs) - min(serial_runs))
                                      / done * 1000, 1),
            "ratio": round(serial_s / threaded_s, 2) if threaded_s else None,
            "errors": len(errors),
        })

    sample = compile_snapshot(load_glossary(
        build_synthetic_glossary(scales[0], seed=SEED)[0]),
        run_conformance=False)
    return {
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor() or platform.machine(),
            "python": sys.version.split()[0],
        },
        "corpus": corpus_fingerprint(),
        "seed": SEED,
        "repeats": repeats,
        "sync_max_input_bytes": sample.policy.sync_max_input_bytes,
        "latency": rows,
        "build": build,
        "memory": memory,
        "degradation": onsets,
        "concurrency": concurrency,
        "concurrency_sweep": sweeps,
        "deadline": deadlines,
    }


def write_markdown(t: dict, control: dict | None, out_path: Path) -> None:
    m = t["machine"]
    limit = t.get("sync_max_input_bytes") or 0
    limit_chars = limit // 3
    onset = next((o["first_always_degraded_chars"] for o in t["degradation"]
                  if o["first_always_degraded_chars"]), None)
    lines = [
        "# 지연·메모리 측정 — 그리고 resolver가 일을 멈추는 지점",
        "",
        "ROADMAP 백로그는 p95/p99 SLO와 동시성·hot-swap·rollback 부하 테스트를"
        " 요구한다. 이 리포트는 **측정** 절반이고, 정확성 절반은"
        " `tests/test_concurrency_and_swap.py`가 고정한다.",
        "",
        "게이트는 일부러 **상대적**이다. 절대 SLO는 기준 하드웨어를 지목해야"
        " 하는데(§53) 그것이 정해져 있지 않고, CI가 배정한 아무 머신에서 잰"
        " 임계값은 계약의 얼굴을 한 동전 던지기다. 그래서 머신을 기록하고"
        " `--compare`만 실패할 수 있게 했다.",
        "",
        "재현: `python -m eval.run_latency_slo`.",
        "",
        f"측정 머신: `{m['platform']}` · `{m['processor']}` · Python"
        f" {m['python']} · 반복 {t['repeats']}회/셀.",
        "",
        "## 0. 이 측정을 만들면서 두 번 틀렸다",
        "",
        "- **반복으로 채운 문서는 캐시를 잰다.** 한 문장을 반복해 문서를 채웠더니"
        " 지연이 **하위선형**으로 나왔다 — 텍스트 7배에 시간 1.8배. 같은 토큰을"
        " 반복해서 답하고 있었기 때문이다. 지금은 **서로 다른 실문장**으로"
        " 채운다.",
        "- **평탄해지는 것은 빨라서가 아니라 멈춰서다.** 수백 자를 넘기면 응답이"
        " `degraded`로 돌아오고, 그 뒤로는 텍스트가 늘어도 시간이 비례해서 늘지"
        " 않는다. 그래서 publish할 값은 임의 크기의 p95가 아니라 **resolver가"
        " 스스로 일을 자르기 시작하는 크기**다.",
        "",
        "## 1. 언제 일을 자르기 시작하나 — 그리고 API는 얼마나 받나",
        "",
    ]
    if onset and limit_chars:
        lines += [
            f"동기 API가 받는 입력은 `sync_max_input_bytes` = **{limit:,}바이트**"
            f"(한글 약 {limit_chars:,}자)인데, 응답이 항상 `degraded`가 되는"
            f" 지점은 **약 {onset:,}자**다 — 받아주는 크기가 온전히 처리하는"
            f" 크기의 **{limit_chars // max(onset, 1)}배**다.",
            "",
            "이것이 이 리포트에서 제일 실용적인 수치다. 그 위에서는 지연이"
            " 평탄해 보이지만, 평탄한 이유는 답의 일부가 잘렸기 때문이다.",
            "",
        ]
    lines += [
        "| entity | 항상 degraded가 되는 길이 |",
        "|---:|---:|",
    ]
    for o in t["degradation"]:
        v = o["first_always_degraded_chars"]
        lines.append(f"| {o['entities']:,} | "
                     + (f"{v:,}자" if v else "측정 범위 내 없음") + " |")
    lines += [
        "",
        "사다리(길이별로 서로 다른 문서 3건 중 몇 건이 degraded인지) — 시작점이"
        " 그 길이의 성질이지 마침 거기 온 문장의 성질이 아님을 보이기 위한 것:",
        "",
        "| 길이 | " + " | ".join(f"{o['entities']:,}" for o in t["degradation"])
        + " |",
        "|---:|" + "---:|" * len(t["degradation"]),
    ]
    for i, step in enumerate(ONSET_STEPS):
        cells = []
        for o in t["degradation"]:
            row = o["ladder"][i] if i < len(o["ladder"]) else None
            cells.append(f"{row['degraded_of_3']}/3" if row else "—")
        lines.append(f"| {step:,}자 | " + " | ".join(cells) + " |")

    lines += [
        "",
        "> 이 측정이 계약 두 개가 걸려 있지 않다는 것을 찾았고, 그 뒤에"
        " 고쳤다. 응답은 이제 `limits`로 **어느 stage가 생략됐는지**"
        " 말하고(REQ-BUD-001), cutoff 뒤의 mention은 `channels_bounded`로"
        " 자기에게 제공되지 않은 채널이 있음을 말한다. 하향(REQ-API-005)은"
        " **잘린 채널이 그 답이 딛고 선 채널일 때만** 적용한다 — 전부"
        " 하향하는 버전은 3,200자에서 확정을 31에서 5로 무너뜨렸고, 예산을"
        " 풀고 재보니 결정은 207개 중 0개만 달라졌다. 자세한 것은"
        " ROADMAP.",
        "",
        "## 2. resolve 지연 — 두 축을 동시에",
        "",
        "p95를 문서 크기 없이 인용하면 그것은 resolver에 대한 진술이 아니라"
        " **그 수치를 만든 코퍼스에 대한 진술**이다. `degraded` 열이 붙은 행은"
        " 위 이유로 낮게 나온 것이다.",
        "",
        "`드리프트`는 같은 셀의 반복을 **번갈아 두 블록**으로 나눠 잰 중앙값"
        " 차이다 — 한 실행 **안**의 안정성이며, 2% 미만이면 그 셀의 수치는"
        " 자기 자신과 일관된다는 뜻이다.",
        "",
        "**그것을 비교 임계값으로 쓰면 안 된다.** 비교는 언제나 두 실행"
        " 사이에서 일어나고, 같은 commit·같은 머신에서 이 하네스를 두 번 돌린"
        f" 결과가 p50에서 최대 26% 어긋났다. 그래서 `--compare` 판정은"
        f" **대조군의 {int(BETWEEN_RUN_FLOOR * 100)}%**를 바닥으로 쓴다 —"
        " 셀 안의 드리프트를 쓰면 머신의 날씨 4분의 1을 회귀로 보고하게"
        " 된다.",
        "",
        "| entity | 문서 길이 | p50 (ms) | p95 | p99 | 최대 | 드리프트 |"
        " degraded |",
        "|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in t["latency"]:
        lines.append(f"| {r['entities']:,} | {r['doc_chars']:,}자 |"
                     f" {r['p50_ms']} | {r['p95_ms']} |"
                     f" {r['p99_ms'] if r['p99_ms'] is not None else '표본 부족'} |"
                     f" {r['max_ms']} | ±{r.get('drift_ms', 0)} |"
                     f" {'예' if r['degraded'] else '아니오'} |")

    lines += [
        "",
        "## 3. 컴파일과 활성화 — hot swap이 실제로 치르는 값",
        "",
        "`SnapshotRegistry.activate`는 `verify_integrity()`로 내용 digest를 다시"
        " 계산한다 — 살아 있는 snapshot이 자기 id와 어긋난 채 모든 요청이 읽는"
        " 것이 되지 못하게 하는 게이트다. 그 대가는 **사전 규모에 비례**하며,"
        " 놀라움이 아니라 표에 있어야 한다. 락 바깥에서 계산하므로 진행 중인"
        " 읽기를 막지는 않는다.",
        "",
        "`cold`는 갓 컴파일된 snapshot이 **처음** 응답한 한 건이고, 2절의"
        " p50은 예열 뒤의 정상 상태다. 배포 직후·hot swap 직후에 서비스가"
        " 겪는 것은 앞의 값이므로 따로 싣는다.",
        "",
        "다만 **한 건은 한 건이다** — 이 머신은 같은 커밋에서 두 번 돌린"
        " 결과가 26% 어긋난다. 아래 값이 warm p50보다 낮게 나오더라도 그것은"
        " cold가 더 빠르다는 뜻이 아니라 **측정 가능한 cold 페널티가 없다**는"
        " 뜻으로 읽어야 한다. 인덱스는 compile에서 만들어지고 그 비용은 왼쪽"
        " 열에 이미 있다.",
        "",
        "| entity | compile (ms) | cold resolve 1건 | verify_integrity p50 |"
        " activate p50 | compile 최대 메모리 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in t["build"]:
        cold = r.get("cold_resolve_ms")
        lines.append(f"| {r['entities']:,} | {r['compile_ms']} |"
                     f" {cold if cold is not None else '—'}"
                     f" ({r.get('cold_doc_chars', '?')}자) |"
                     f" {r['verify_integrity_ms_p50']} |"
                     f" {r['activate_ms_p50']} | {r['compile_peak_mb']} MB |")

    if t.get("deadline"):
        lines += [
            "",
            "## 3.5 마감 시간(deadline)이 실제로 꼬리를 자르는가",
            "",
            "이 리포트의 원래 약점은 지연을 **재기만** 했다는 것이다. 느린"
            " 응답을 어떻게 할 것인가에 대한 답이 없었다. `deadline_ms`는"
            " 선택 단계(fuzzy → dense → rerank)를 순서대로 버리고, 무엇을"
            " 버렸는지 응답에 적는다.",
            "",
            "**바닥은 0이 아니다.** Level A는 결정적 보장이지 best-effort"
            " 단계가 아니므로 exact 패스는 어떤 예산에서도 돌아간다. 따라서"
            " exact 패스 비용 아래로는 예산을 줄여도 더 빨라지지 않으며, 아래"
            " 표의 초과분은 감추지 않고 그대로 적는다.",
            "",
            "예산은 **무제한 p50**으로 잡았다 — 절반은 원래 그 안에 끝났을"
            " 요청이고, 볼 값은 나머지 절반이다.",
            "",
            "| entity | 문서 | 예산 | 무제한 p95 / 최대 | 예산 p95 / 최대 |"
            " 단계 버린 비율 |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
        for r in t["deadline"]:
            lines.append(
                f"| {r['entities']:,} | {r['doc_chars']:,}자 |"
                f" {r['budget_ms']}ms |"
                f" {r['unbounded_p95_ms']} / {r['unbounded_max_ms']} |"
                f" {r['bounded_p95_ms']} / {r['bounded_max_ms']} |"
                f" {r['shed_rate']:.0%} |")

    if t.get("concurrency_sweep"):
        lines += [
            "",
            "## 5.5 동시 요청 1 / 10 / 100",
            "",
            "**모든 수준이 같은 총량을 처리한다** — 스레드가 늘면 스레드당"
            " 건수가 줄어든다. 그래야 두 팔이 같은 일을 다르게 배치한 것이"
            " 되고, 벽시계가 의미를 갖는다.",
            "",
            "GIL 아래에서 처리량이 늘 것을 기대하는 표가 아니다. 여기서 읽을"
            " 것은 **꼬리가 무너지는가**와 **오류가 나는가** 둘이다.",
            "",
            "| entity | 동시 | 건수 | 벽시계 | 처리량/s | p50 | p95 | 최대 |"
            " 오류 |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for grp in t["concurrency_sweep"]:
            for r in grp["levels"]:
                lines.append(
                    f"| {grp['entities']:,} | {r['concurrency']} |"
                    f" {r['resolves']} | {r['wall_s']}s |"
                    f" {r['throughput_per_s']} | {r['p50_ms']} |"
                    f" {r['p95_ms']} | {r['max_ms']} | {r['errors']} |")

    lines += [
        "",
        "## 4. 요청당 메모리",
        "",
        "컴파일 최대치(인덱스 상주 비용)와 분리해서 잰다 — 합치면 상주와"
        " 요청당 할당을 구분할 수 없다.",
        "",
        "| entity | 문서 길이 | resolve 최대 메모리 |",
        "|---:|---:|---:|",
    ]
    for r in t["memory"]:
        lines.append(f"| {r['entities']:,} | {r['doc_chars']:,}자 |"
                     f" {r['resolve_peak_mb']} MB |")

    lines += [
        "",
        "## 5. 동시성",
        "",
        "**속도 주장이 아니다.** GIL 아래에서 스레드를 늘린다고 병렬성이 늘지"
        " 않으므로, 여기서 확인하는 것은 경합이 결과를 **더 나쁘게 만들지"
        " 않는다**는 것과 오류가 0이라는 것이다. 교차 읽기·hot swap·rollback·"
        "tenant 격리 같은 정확성은 `tests/test_concurrency_and_swap.py`가"
        " 고정한다.",
        "",
        "두 팔은 **번갈아 3회씩** 돌리고 중앙값을 쓴다. 각각 한 번씩만 재면"
        " 경합이 아니라 **드리프트**를 재게 된다 — 첫 판이 그랬고, 순차 팔이"
        " 자기 p50의 두 배를 보고했다. `순차 편차`는 그 3회의 최대-최소이며,"
        " 그것보다 작은 차이는 읽을 값이 아니다.",
        "",
        "| entity | 스레드 | 팔당 resolve | 순차 (ms/건) | 병렬 (ms/건) |"
        " 순차 편차 | 비 | 오류 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in t["concurrency"]:
        lines.append(f"| {r['entities']:,} | {r['threads']} |"
                     f" {r['resolves_per_arm']} |"
                     f" {r['serial_ms_per_resolve']} |"
                     f" {r['threaded_ms_per_resolve']} |"
                     f" ±{r['spread_serial_ms']} |"
                     f" {r['ratio']} | {r['errors']} |")

    if control:
        cm = control.get("machine", {})
        if cm.get("processor") and cm.get("processor") != m.get("processor"):
            lines += [
                "",
                "> **두 팔이 서로 다른 머신에서 측정됐다.** 아래 비교는 변경의"
                " 효과가 아니라 하드웨어 차이를 포함한다.",
            ]
        idx = {(r["entities"], r["doc_chars"]): r for r in control["latency"]}
        lines += [
            "",
            "## 6. 대조군 대비 (p95)",
            "",
            "| entity | 문서 길이 | 대조군 | 현재 | 변화 | 판정 |",
            "|---:|---:|---:|---:|---:|---|",
        ]
        for r in t["latency"]:
            c = idx.get((r["entities"], r["doc_chars"]))
            if not c:
                continue
            gap = r["p95_ms"] - c["p95_ms"]
            floor = max(r.get("drift_ms", 0), c.get("drift_ms", 0),
                        BETWEEN_RUN_FLOOR * c["p95_ms"])
            delta = (f"{(r['p95_ms'] / c['p95_ms'] - 1) * 100:+.0f}%"
                     if c["p95_ms"] else "—")
            verdict = "읽을 값" if abs(gap) > floor else "노이즈 바닥 이하"
            lines.append(f"| {r['entities']:,} | {r['doc_chars']:,}자 |"
                         f" {c['p95_ms']} | {r['p95_ms']} | {delta} |"
                         f" {verdict} |")

    lines += [
        "",
        "## 이 리포트가 말하지 않는 것",
        "",
        "- **SLO 준수 여부.** 기준 하드웨어가 정의되기 전까지 절대 임계값은"
        " 계약이 아니다. 수치는 이 머신의 것이고, 판정은 `--compare`의 상대"
        f" 비교뿐이며 그마저 {int(BETWEEN_RUN_FLOOR * 100)}% 바닥 위에서만"
        " 읽힌다 — 이 하네스는 작은 회귀를 잡지 못한다.",
        "- **정확성.** 지연만 잰다. 같은 입력에 같은 답이 나오는지는"
        " conformance와 동시성 테스트가 본다.",
        "- **무엇이 잘렸는지.** `degraded`는 잘렸다는 것만 말한다. 어느"
        " mention의 무엇이 잘렸는지는 응답에 없다.",
        "- **사전 구성의 영향.** 합성 사전이며 실제 tenant 사전의 표면형 분포와"
        " 다르다. 축의 모양을 보기 위한 것이지 용량 계획을 위한 것이 아니다.",
        "",
        provenance_line(ROOT, f"entity {t['build'][-1]['entities']:,}까지",
                        corpus=t.get("corpus")),
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", type=str, default="200,1000,3000")
    ap.add_argument("--sizes", type=str, default="200,800,3200")
    ap.add_argument("--repeats", type=int, default=30)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--json", type=str, default=None)
    ap.add_argument("--compare", type=str, default=None)
    ap.add_argument("--render-only", type=str, default=None)
    args = ap.parse_args()

    out_md = ROOT / "reports" / "LATENCY_SLO.md"
    control = (json.loads(Path(args.compare).read_text(encoding="utf-8"))
               if args.compare else None)

    if args.render_only:
        payload = json.loads(Path(args.render_only).read_text(encoding="utf-8"))
        write_markdown(payload, control, out_md)
        print(f"rendered {out_md} from {args.render_only}")
        return

    scales = [int(x) for x in args.scales.split(",") if x]
    sizes = [int(x) for x in args.sizes.split(",") if x]
    payload = measure(scales, sizes, args.repeats, args.threads)

    out_json = ROOT / "eval" / "out" / "latency_slo.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=1)
    out_json.write_text(body, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(body, encoding="utf-8")
    write_markdown(payload, control, out_md)
    for r in payload["latency"]:
        print(f"  {r['entities']:>6,} entities x {r['doc_chars']:>6,} chars: "
              f"p50 {r['p50_ms']:>8} p95 {r['p95_ms']:>8} "
              f"{'degraded' if r['degraded'] else ''}")
    for o in payload["degradation"]:
        print(f"  degradation onset @ {o['entities']:,} entities: "
              f"{o['first_always_degraded_chars']} chars")
    print(f"wrote {out_json} and {out_md}")


if __name__ == "__main__":
    main()
