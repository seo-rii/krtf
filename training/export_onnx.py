"""Export a trained cross-encoder to ONNX for the KTRF runtime (§34).

Usage: python -m training.export_onnx --model models/xenc-smoke \
           --out models/xenc-smoke-onnx

The output directory (model.onnx + tokenizer.json) loads directly through
``ktrf.rerank.OnnxCrossEncoder`` / ``load_reranker("onnx:<dir>")`` — no
runtime code changes (GPU_PLAN G2 step 5).
"""

from __future__ import annotations

import argparse
from pathlib import Path


def export(model_dir: str, out_dir: str) -> Path:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    enc = tokenizer("문맥 예시", "엔터티 프로필 예시", return_tensors="pt")
    inputs = (enc["input_ids"], enc["attention_mask"])
    input_names = ["input_ids", "attention_mask"]
    dynamic = {n: {0: "batch", 1: "seq"} for n in input_names}
    dynamic["logits"] = {0: "batch"}
    torch.onnx.export(
        model, inputs, str(out / "model.onnx"),
        input_names=input_names, output_names=["logits"],
        dynamic_axes=dynamic, opset_version=17, dynamo=False,
    )
    # fast-tokenizer single-file form consumed by the runtime
    tokenizer.backend_tokenizer.save(str(out / "tokenizer.json"))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    out = export(args.model, args.out)
    print(f"exported -> {out}")


if __name__ == "__main__":
    main()
