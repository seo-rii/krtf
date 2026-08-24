"""Stage B cross-encoder fine-tuning (spec §35.2, docs/GPU_PLAN.md G2).

Usage:
    python -m training.train_cross_encoder --smoke     # pipeline validation
    python -m training.train_cross_encoder --episodes episodes.jsonl \
        --out models/xenc-klue --epochs 2               # real training

Fine-tunes KLUE-RoBERTa-base (MODEL_RECOMMEND.md Role 1) as a pair scorer
``[mention context × entity profile] -> compatibility``. Training-only
dependencies (torch, transformers) are never required by the KTRF runtime.

**Training gate (GPU_PLAN G2):** refuses to run a production fit below
``--min-labeled`` positives (default 5000) — models fitted under the gate
must pass ``--smoke``/``--allow-under-gate`` and are pipeline-validation
artifacts, not releasable models. Golden sets are never accepted as
training input (§45.8).
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE = "klue/roberta-base"
TRAINING_GATE_MIN_POSITIVES = 5000  # docs/GPU_PLAN.md G2


def _load_episodes(path: str | None, smoke: bool):
    from .episodes import Episode, episodes_from_silver

    if path:
        eps = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                eps.append(Episode(d["context"], d["profile"],
                                   int(d["label"]), d.get("source", "file")))
        return eps
    if smoke:
        from eval.wild_data import load_corpus
        from ktrf.glossary import load_glossary

        glossary = load_glossary(str(ROOT / "examples" / "realorg_glossary.yaml"))
        return episodes_from_silver(glossary, load_corpus())
    raise SystemExit("provide --episodes (or --smoke for pipeline validation)")


def train(args) -> Path:
    import torch
    from torch.utils.data import DataLoader
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    episodes = _load_episodes(args.episodes, args.smoke)
    positives = sum(e.label for e in episodes)
    print(f"episodes: {len(episodes)} ({positives} positives)")
    if positives < args.min_labeled and not (args.smoke or args.allow_under_gate):
        raise SystemExit(
            f"training gate: {positives} labeled positives < "
            f"{args.min_labeled} (GPU_PLAN G2). Accumulate ACCEPTED "
            "corrections; use --smoke only for pipeline validation.")

    device = ("cuda" if torch.cuda.is_available() and args.device != "cpu"
              else "cpu")
    print(f"device: {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device == "cuda" else ""))
    torch.manual_seed(args.seed)
    random.Random(args.seed).shuffle(episodes)

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base, num_labels=1).to(device)
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    scaler = torch.amp.GradScaler(enabled=device == "cuda")

    def collate(batch):
        enc = tokenizer([e.context for e in batch],
                        [e.profile for e in batch],
                        truncation=True, max_length=args.max_length,
                        padding=True, return_tensors="pt")
        # KLUE-RoBERTa has type_vocab_size=1; pair segment ids of 1 would
        # index out of range on the type-embedding table
        enc.pop("token_type_ids", None)
        enc["labels"] = torch.tensor([float(e.label) for e in batch])
        return enc

    loader = DataLoader(episodes, batch_size=args.batch_size, shuffle=True,
                        collate_fn=collate)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    step = 0
    t0 = time.perf_counter()
    for epoch in range(args.epochs):
        for batch in loader:
            labels = batch.pop("labels").to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            with torch.amp.autocast(device_type=device,
                                    enabled=device == "cuda"):
                logits = model(**batch).logits.squeeze(-1)
                loss = loss_fn(logits, labels)
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            step += 1
            if step % 10 == 0 or step == 1:
                print(f"  step {step} loss {loss.item():.4f}")
            if args.max_steps and step >= args.max_steps:
                break
        if args.max_steps and step >= args.max_steps:
            break
    elapsed = time.perf_counter() - t0
    print(f"trained {step} steps in {elapsed:.1f}s on {device}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tokenizer.save_pretrained(out)
    (out / "TRAINING_META.json").write_text(json.dumps({
        "base": args.base, "episodes": len(episodes),
        "positives": positives, "steps": step, "device": device,
        "seconds": round(elapsed, 1),
        "under_gate": positives < args.min_labeled,
        "note": ("PIPELINE-VALIDATION ONLY — trained under the G2 labeled-"
                 "data gate; not a releasable model"
                 if positives < args.min_labeled else "gate satisfied"),
    }, indent=2), encoding="utf-8")
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--episodes")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--allow-under-gate", action="store_true")
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument("--out", default="models/xenc-smoke")
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--max-length", type=int, default=192)
    p.add_argument("--max-steps", type=int, default=None)
    p.add_argument("--min-labeled", type=int,
                   default=TRAINING_GATE_MIN_POSITIVES)
    p.add_argument("--device", default="auto")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    if args.smoke and args.max_steps is None:
        args.max_steps = 30
        args.batch_size = 8
    out = train(args)
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
