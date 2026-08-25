"""Real Korean text acquisition from HuggingFace (wild-corpus benchmarks).

Downloads open-license Korean sentences through the HF datasets-server rows
API (plain HTTPS/JSON, no `datasets` dependency) and caches them locally:

- ``klue/klue`` config ``ynat``: Yonhap news headlines — dense with real
  organization mentions (CC BY-SA 4.0);
- ``klue/klue`` config ``nli``: colloquial/wiki premises (CC BY-SA 4.0);
- ``klue/klue`` config ``sts``: paraphrase sentences (CC BY-SA 4.0).

Cache: ``eval/data/wild_corpus.jsonl`` (gitignored — data is redistributed
under its own license, so the repo ships the downloader, not the text).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE = DATA_DIR / "wild_corpus.jsonl"
API = "https://datasets-server.huggingface.co/rows"

SOURCES = [
    # (dataset, config, split, text_field, max_rows)
    # ynat = Yonhap news headlines (org-dense) — take the full splits
    ("klue/klue", "ynat", "train", "title", 45678),
    ("klue/klue", "ynat", "validation", "title", 9107),
    ("klue/klue", "nli", "train", "premise", 15000),
    ("klue/klue", "nli", "validation", "premise", 3000),
    ("klue/klue", "sts", "train", "sentence1", 11668),
    ("klue/klue", "sts", "validation", "sentence1", 519),
]
LICENSE = "CC BY-SA 4.0 (KLUE benchmark, https://huggingface.co/datasets/klue)"
PAGE = 100


class WildDataUnavailable(RuntimeError):
    pass


def _fetch_page(dataset: str, config: str, split: str, offset: int) -> dict:
    qs = urllib.parse.urlencode({
        "dataset": dataset, "config": config, "split": split,
        "offset": offset, "length": PAGE,
    })
    req = urllib.request.Request(
        f"{API}?{qs}", headers={"User-Agent": "ktrf-eval/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download(force: bool = False, verbose: bool = True) -> Path:
    if CACHE.exists() and not force:
        return CACHE
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    seen: set[str] = set()
    for dataset, config, split, field, max_rows in SOURCES:
        fetched = 0
        offset = 0
        errors = 0
        while fetched < max_rows:
            try:
                page = _fetch_page(dataset, config, split, offset)
            except urllib.error.HTTPError as e:
                errors += 1
                if errors > 8:
                    break  # give up on this source, keep others
                time.sleep(30.0 if e.code == 429 else 2.0)  # rate-limit backoff
                continue
            except OSError:
                errors += 1
                if errors > 8:
                    break
                time.sleep(2.0)
                continue
            errors = 0  # consecutive-error budget: reset on success
            got = page.get("rows", [])
            if not got:
                break
            for r in got:
                text = (r["row"].get(field) or "").strip()
                if len(text) >= 8 and text not in seen:
                    seen.add(text)
                    rows.append({"text": text,
                                 "source": f"{dataset}:{config}:{split}"})
            fetched += len(got)
            offset += PAGE
            time.sleep(0.15)  # be polite to the public API
        if verbose:
            print(f"  {dataset}:{config}:{split}: {fetched} rows fetched"
                  + (f" ({errors} errors)" if errors else ""))
    if not rows:
        raise WildDataUnavailable("cannot reach HuggingFace datasets-server")
    with open(CACHE, "w", encoding="utf-8") as f:
        f.write(json.dumps({"meta": {"license": LICENSE,
                                     "sentences": len(rows)}},
                           ensure_ascii=False) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if verbose:
        print(f"  cached {len(rows)} unique sentences -> {CACHE}")
    return CACHE


def load_corpus() -> list[dict]:
    """Load cached sentences, downloading on first use."""
    path = download(verbose=True)
    out = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            d = json.loads(line)
            if i == 0 and "meta" in d:
                continue
            out.append(d)
    return out


if __name__ == "__main__":
    download(force=True)
