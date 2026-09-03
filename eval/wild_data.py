"""Real Korean text acquisition from HuggingFace (wild-corpus benchmarks).

Downloads open Korean text through the HF datasets-server rows API (plain
HTTPS/JSON, no `datasets` dependency) and caches it locally as sentences.
Multi-domain by design — news headlines alone under-represent the target
distribution (government documents, legal prose, civic text, encyclopedia):

- ``klue/klue`` ynat/nli/sts: Yonhap headlines + wiki premises (CC BY-SA 4.0)
- ``heegyu/korean-petitions``: 청와대 국민청원 — civic/administrative text,
  extremely ministry-dense (public-record petitions)
- ``joonhok-exo-ai/korean_law_open_data_precedents``: 국가법령정보 공공데이터
  판례 전문 — court/agency-dense legal prose (KOGL open data)
- ``KorQuAD/squad_kor_v1`` contexts + ``wikimedia/wikipedia`` 20231101.ko +
  ``skt/kobest_v1`` boolq paragraphs: encyclopedic prose (CC BY-SA / BY-ND)

Cache: ``eval/data/wild_corpus.jsonl`` (gitignored — each source carries its
own license, so the repo ships the downloader, not the text).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE = DATA_DIR / "wild_corpus.jsonl"
API = "https://datasets-server.huggingface.co/rows"

# (dataset, config, split, text_field, max_rows, split_sentences,
#  max_keep, start_offset)
# max_rows = rows fetched from the API; max_keep = sentences kept after
# optional splitting (long-document sources are capped so no single domain
# dominates the corpus); start_offset skips archaic leading rows.
SOURCES = [
    # news headlines / short sentences (KLUE) — kept whole
    ("klue/klue", "ynat", "train", "title", 45678, False, None, 0),
    ("klue/klue", "ynat", "validation", "title", 9107, False, None, 0),
    ("klue/klue", "nli", "train", "premise", 15000, False, None, 0),
    ("klue/klue", "nli", "validation", "premise", 3000, False, None, 0),
    ("klue/klue", "sts", "train", "sentence1", 11668, False, None, 0),
    ("klue/klue", "sts", "validation", "sentence1", 519, False, None, 0),
    # government / civic documents (user-requested domain)
    ("heegyu/korean-petitions", "default", "train", "content",
     3000, True, 12000, 0),
    ("joonhok-exo-ai/korean_law_open_data_precedents", "default", "train",
     "전문", 2000, True, 12000, 50000),
    # encyclopedic prose
    ("KorQuAD/squad_kor_v1", "squad_kor_v1", "train", "context",
     6000, True, 8000, 0),
    ("wikimedia/wikipedia", "20231101.ko", "train", "text",
     1500, True, 8000, 0),
    ("skt/kobest_v1", "boolq", "train", "paragraph", 3665, True, 3000, 0),
]
LICENSES = {
    "klue/klue": "CC BY-SA 4.0 (KLUE benchmark)",
    "heegyu/korean-petitions": "public petition records "
                               "(https://huggingface.co/datasets/heegyu/korean-petitions)",
    "joonhok-exo-ai/korean_law_open_data_precedents":
        "KOGL open data (국가법령정보 공동활용)",
    "KorQuAD/squad_kor_v1": "CC BY-ND 2.0 KR (KorQuAD 1.0)",
    "wikimedia/wikipedia": "CC BY-SA 4.0 (Wikipedia)",
    "skt/kobest_v1": "CC BY-SA 4.0 (KoBEST)",
}
PAGE = 100

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_MIN_LEN, _MAX_LEN = 8, 300


def _sentences(text: str, split_sentences: bool) -> list[str]:
    if not split_sentences:
        return [text.strip()]
    return [s.strip() for s in _SENT_SPLIT.split(text)
            if _MIN_LEN <= len(s.strip()) <= _MAX_LEN]


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
    for (dataset, config, split, field, max_rows, do_split,
         max_keep, start_offset) in SOURCES:
        fetched = 0
        kept = 0
        offset = start_offset
        errors = 0
        while fetched < max_rows and (max_keep is None or kept < max_keep):
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
                raw = (r["row"].get(field) or "").strip()
                for text in _sentences(raw, do_split):
                    if max_keep is not None and kept >= max_keep:
                        break
                    if len(text) >= _MIN_LEN and text not in seen:
                        seen.add(text)
                        kept += 1
                        rows.append({"text": text,
                                     "source": f"{dataset}:{config}:{split}"})
            fetched += len(got)
            offset += PAGE
            time.sleep(0.15)  # be polite to the public API
        if verbose:
            print(f"  {dataset}:{config}:{split}: {fetched} rows fetched, "
                  f"{kept} sentences kept"
                  + (f" ({errors} errors)" if errors else ""))
    if not rows:
        raise WildDataUnavailable("cannot reach HuggingFace datasets-server")
    by_source: dict[str, int] = {}
    for r in rows:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
    with open(CACHE, "w", encoding="utf-8") as f:
        f.write(json.dumps({"meta": {"licenses": LICENSES,
                                     "sentences": len(rows),
                                     "by_source": by_source}},
                           ensure_ascii=False) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if verbose:
        print(f"  cached {len(rows)} unique sentences -> {CACHE}")
    return CACHE


# What the last :func:`load_corpus` in this process actually read. A report
# has to be able to name its *data*, not only its code: two runs at the same
# commit against different caches produce different numbers and identical
# provenance lines, which is the stale-report failure one level down. Recording
# it here rather than asking each harness to declare it means the stamp says
# what was read instead of what someone remembered to pass along.
_LOADED: dict | None = None


def corpus_fingerprint() -> dict | None:
    """Identity of the corpus loaded in this process, or None if none was."""
    return dict(_LOADED) if _LOADED else None


def load_corpus() -> list[dict]:
    """Load cached sentences, downloading on first use."""
    global _LOADED
    path = download(verbose=True)
    digest = hashlib.sha256()
    meta: dict = {}
    out = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            digest.update(line.encode("utf-8"))
            d = json.loads(line)
            if i == 0 and "meta" in d:
                meta = d["meta"]
                continue
            out.append(d)
    _LOADED = {
        "sha256": digest.hexdigest()[:16],
        "sentences": len(out),
        # the recorded count and the row count disagreeing means a truncated
        # or hand-edited cache, which is worth seeing in the footer
        "declared_sentences": meta.get("sentences"),
        "sources": len(meta.get("by_source") or {}),
    }
    return out


if __name__ == "__main__":
    download(force=True)
