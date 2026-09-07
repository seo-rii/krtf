"""GPU vs CPU encoder benchmark (docs/GPU_PLAN.md Phase G1, spec §53).

Usage: python -m eval.gpu_bench

Measures multilingual-e5-small ONNX on CPU vs CUDA EP:
- batch passage-encoding throughput (compile-time vector cost, §11.1)
- single-query latency (online Pass-2 cost, §21.6)
- numerical agreement between the two providers (fp drift check)

Writes eval/out/gpu_bench.json and reports/GPU_BENCH.md.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

from ktrf.encoders import OnnxE5Encoder

from .metrics import provenance_line, run_manifest
from .synthetic import build_synthetic_glossary

ROOT = Path(__file__).resolve().parent.parent
E5_DIR = ROOT / "models" / "multilingual-e5-small"  # int8, CPU-optimized
E5_FP32_DIR = ROOT / "models" / "multilingual-e5-small-fp32"  # GPU path


def _hardware() -> dict:
    """Which machine produced the speedup.

    A `10.73x` with no device named is not a benchmark result, it is a
    number. Best-effort and never fatal: the report should degrade to
    "unknown" rather than fail to exist, but it must not silently imply
    that any two runs of this file are comparable.
    """
    hw = {"platform": platform.platform(),
          "cpu": platform.processor() or "unknown",
          "gpu": "unknown"}
    try:  # torch is already required for the CUDA runtime this bench uses
        import torch

        if torch.cuda.is_available():
            hw["gpu"] = torch.cuda.get_device_name(0)
            hw["cuda"] = torch.version.cuda
    except Exception:
        pass
    try:
        import onnxruntime

        hw["onnxruntime"] = onnxruntime.__version__
        hw["providers"] = ",".join(onnxruntime.get_available_providers())
    except Exception:
        pass
    return hw


def _passages(n: int) -> list[str]:
    g, _ = build_synthetic_glossary(n, seed=3)
    return [f"{e['canonical']}. {e['description']}" for e in g["entities"]]


def bench_encoder(device: str, passages: list[str], queries: int = 50) -> dict:
    # per-device best artifact: int8 on CPU, fp32 on GPU (int8 ops are not
    # CUDA-resident and would bounce between devices)
    model_dir = E5_FP32_DIR if device == "cuda" and E5_FP32_DIR.exists() else E5_DIR
    enc = OnnxE5Encoder(model_dir, device=device)
    # warmup
    enc.encode_passages(passages[:8])
    t0 = time.perf_counter()
    vectors = enc.encode_passages(passages, batch_size=64)
    batch_s = time.perf_counter() - t0
    q_ms = []
    for i in range(queries):
        t0 = time.perf_counter()
        enc.encode_query(f"{passages[i % len(passages)][:30]} 관련 문의")
        q_ms.append(1000 * (time.perf_counter() - t0))
    q_ms.sort()
    return {
        "requested_device": device,
        "model": model_dir.name,
        "actual_device": enc.device,
        "passages": len(passages),
        "batch_seconds": round(batch_s, 2),
        "passages_per_second": round(len(passages) / batch_s, 1),
        "query_p50_ms": round(q_ms[len(q_ms) // 2], 2),
        "query_p95_ms": round(q_ms[int(len(q_ms) * 0.95)], 2),
        "_vectors": vectors,
    }


def _summarize(samples: list[dict]) -> dict:
    """Median of repeated draws, with the observed range beside it."""
    keys = ("batch_seconds", "passages_per_second", "query_p50_ms",
            "query_p95_ms")
    out = {k: samples[0][k] for k in ("requested_device", "model",
                                      "actual_device", "passages")}
    for k in keys:
        vals = [s[k] for s in samples]
        out[k] = round(statistics.median(vals), 2)
        out[k + "_range"] = [round(min(vals), 2), round(max(vals), 2)]
    out["repeats"] = len(samples)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3,
                    help="draws per arm; the arms alternate between draws")
    args = ap.parse_args()
    if not E5_DIR.exists():
        raise SystemExit("e5 model dir missing — see README neural setup")
    passages = _passages(1000)

    # One draw of each arm, run back to back, was reporting the machine's
    # weather as a result. Four repeats at one commit on this machine spanned
    # 340-387 passages/s on CPU and 4,756-5,344 on GPU: 12-14% each, and 23%
    # once divided into a speedup. Sequential arms make that worse than it
    # needs to be — whatever the machine is doing while the first arm runs is
    # over by the time the second one does — so the arms alternate and the
    # report publishes the median with the range beside it.
    cpu_runs, gpu_runs = [], []
    first_vectors = {}
    for i in range(max(1, args.repeats)):
        order = ("cpu", "cuda") if i % 2 == 0 else ("cuda", "cpu")
        for dev in order:
            r = bench_encoder(dev, passages)
            first_vectors.setdefault(dev, r["_vectors"])
            r.pop("_vectors")
            (cpu_runs if dev == "cpu" else gpu_runs).append(r)
            print(f"  draw {i + 1} {dev}: {r['passages_per_second']} passages/s")

    cpu = _summarize(cpu_runs)
    gpu = _summarize(gpu_runs)

    drift = None
    if gpu["actual_device"] == "cuda":
        import math

        dots = [
            sum(a * b for a, b in zip(u, v))
            / (math.sqrt(sum(a * a for a in u)) * math.sqrt(sum(b * b for b in v)))
            for u, v in zip(first_vectors["cpu"][:100],
                            first_vectors["cuda"][:100])
        ]
        drift = round(1.0 - min(dots), 6)

    speedup = speedup_range = None
    if gpu["actual_device"] == "cuda":
        speedup = round(gpu["passages_per_second"] / cpu["passages_per_second"],
                        2)
        # worst and best the same machine produced, not a confidence interval
        speedup_range = [
            round(gpu["passages_per_second_range"][0]
                  / cpu["passages_per_second_range"][1], 2),
            round(gpu["passages_per_second_range"][1]
                  / cpu["passages_per_second_range"][0], 2),
        ]
    hw = _hardware()
    payload = {"manifest": run_manifest(ROOT), "hardware": hw,
               "repeats": max(1, args.repeats),
               "cpu": cpu, "gpu": gpu, "batch_speedup": speedup,
               "batch_speedup_range": speedup_range,
               "max_cosine_drift_cpu_vs_gpu": drift}
    out = ROOT / "eval" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "gpu_bench.json").write_text(json.dumps(payload, indent=2),
                                        encoding="utf-8")

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    lines = [
        "# GPU vs CPU 인코더 벤치마크 (Phase G1, §53)",
        "",
        "multilingual-e5-small (quantized ONNX), entity-profile 1,000건 배치"
        " 인코딩 + 단건 질의. 재현: `python -m eval.gpu_bench`"
        " (`onnxruntime-gpu` + torch CUDA 런타임 필요).",
        "",
        "| provider | model | 실제 device | batch 1000 | passages/s | query p50 | query p95 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in (cpu, gpu):
        pr = r["passages_per_second_range"]
        lines.append(
            f"| {r['requested_device']} | {r['model']} | {r['actual_device']} "
            f"| {r['batch_seconds']}s | {r['passages_per_second']} "
            f"({pr[0]}–{pr[1]}) "
            f"| {r['query_p50_ms']}ms | {r['query_p95_ms']}ms |")
    rng = payload["batch_speedup_range"]
    lines += [
        "",
        f"표의 값은 arm을 번갈아 {payload['repeats']}회 반복한 **중앙값**이고,"
        " 괄호는 관측된 범위다 — 신뢰구간이 아니라 같은 커밋·같은 기계가"
        " 실제로 낸 폭이다.",
        "",
        f"- **배치 인코딩 speedup: {speedup}×**"
        + (f" (관측 범위 {rng[0]}–{rng[1]}×)" if rng else "")
        + " — compile-time 벡터 생성이 GPU의"
        " 주 수혜 지점이다 (§11.1; 10만 entity 외삽은 아래 참조)."
        " **이 배수를 한 자리 수준으로 인용하지 말 것**: 반복 측정의 폭이"
        " 배수 자체의 20%를 넘는다.",
        f"- int8(CPU)↔fp32(GPU) 코사인 드리프트 최대 {drift} — §46.2"
        " quantization regression 지표. 두 artifact는 `encoder_id`가 다르므로"
        " 스냅샷 벡터는 상호 재사용되지 않는다(§11.3 강제).",
        "- 단건 질의는 kernel launch/전송 오버헤드로 GPU 이득이 없거나 미미하다"
        " — 온라인 경로는 CPU 유지, GPU는 배치(컴파일)와 학습에 사용한다"
        " (docs/GPU_PLAN.md 원칙).",
        "",
        "## 측정 하드웨어",
        "",
        f"- CPU: `{hw['cpu']}`",
        f"- GPU: `{hw['gpu']}`" + (f" (CUDA {hw['cuda']})"
                                   if hw.get("cuda") else ""),
        f"- onnxruntime: `{hw.get('onnxruntime', 'unknown')}`"
        f" · providers `{hw.get('providers', 'unknown')}`",
        f"- platform: `{hw['platform']}`",
        "",
        provenance_line(ROOT, manifest=payload["manifest"]),
        "",
        "*generated by `python -m eval.gpu_bench`*",
    ]
    (reports / "GPU_BENCH.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"wrote {reports / 'GPU_BENCH.md'}")


if __name__ == "__main__":
    main()
