"""Async Document Resolve API (spec §28) — library-level job manager.

Long documents (up to ``async_max_input_bytes``) are chunked on sentence/
paragraph boundaries, every chunk is processed against the snapshot pinned at
job start (INV-017 / REQ-API-006 — a glossary activation mid-job never mixes
versions), mention offsets are returned in global document coordinates
(§28.3), and results paginate. Processing is driven by :meth:`process`
(callable from a worker loop or inline); jobs can be cancelled between
chunks.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from threading import Lock

from .errors import KtrfApiError
from .offsets import OffsetMap
from .resolver import resolve
from .snapshot import Snapshot

DEFAULT_ASYNC_MAX_INPUT_BYTES = 10 * 1024 * 1024  # §28.1
DEFAULT_MAX_CHUNK_BYTES = 8192  # §31.1
CHUNK_OVERLAP_CHARS = 64  # §28.3 overlap window

_SENTENCE_BREAKS = ("\n\n", "\n", ". ", "다. ", "요. ", "! ", "? ")


def _chunk_boundaries(text: str, max_chunk_bytes: int) -> list[tuple[int, int]]:
    """Contiguous [start, end) codepoint chunks, preferring sentence breaks."""
    chunks: list[tuple[int, int]] = []
    n = len(text)
    start = 0
    while start < n:
        # grow to the byte budget
        end = start
        size = 0
        while end < n and size < max_chunk_bytes:
            size += len(text[end].encode("utf-8"))
            end += 1
        if end < n:
            # §28.3: prefer sentence/paragraph boundaries near the cut
            window = text[max(start + 1, end - 200):end]
            best = -1
            for brk in _SENTENCE_BREAKS:
                i = window.rfind(brk)
                if i > best:
                    best = i + len(brk)
                    break  # breaks are ordered by preference
            if best > 0:
                end = max(start + 1, end - 200) + best
        chunks.append((start, end))
        start = end
    return chunks


def _shift_span(span: dict, omap: OffsetMap, cp_shift: int) -> dict:
    cp = span["codepoint"]
    return omap.span_dict(cp["start"] + cp_shift, cp["end"] + cp_shift)


def _globalize_mention(m: dict, omap: OffsetMap, cp_shift: int) -> dict:
    out = dict(m)
    for key in ("span", "full_span"):
        if key in out:
            out[key] = _shift_span(out[key], omap, cp_shift)
    if "prefix" in out and out["prefix"].get("span"):
        p = dict(out["prefix"])
        p["span"] = _shift_span(p["span"], omap, cp_shift)
        out["prefix"] = p
    if "matched_segments" in out:
        out["matched_segments"] = [
            {"start": seg["start"] + cp_shift, "end": seg["end"] + cp_shift}
            for seg in out["matched_segments"]
        ]
    return out


@dataclass
class ResolveJob:
    job_id: str
    snapshot: Snapshot  # pinned at submit time (INV-017)
    mode: str
    text: str
    options: dict
    context: dict
    chunks: list[tuple[int, int]]
    status: str = "QUEUED"  # QUEUED|RUNNING|SUCCEEDED|FAILED|CANCELLED
    chunks_done: int = 0
    mentions: list[dict] = field(default_factory=list)
    degraded: bool = False
    error: dict | None = None
    _seen_spans: set = field(default_factory=set)


class ResolveJobManager:
    """§28 job lifecycle: submit -> process -> status/results -> cancel."""

    def __init__(
        self,
        async_max_input_bytes: int = DEFAULT_ASYNC_MAX_INPUT_BYTES,
        max_chunk_bytes: int = DEFAULT_MAX_CHUNK_BYTES,
        overlap_chars: int = CHUNK_OVERLAP_CHARS,
    ):
        self.async_max_input_bytes = async_max_input_bytes
        self.max_chunk_bytes = max_chunk_bytes
        self.overlap_chars = overlap_chars
        self._jobs: dict[str, ResolveJob] = {}
        self._ids = itertools.count(1)
        self._lock = Lock()

    def submit(self, snapshot: Snapshot, text: str | bytes, mode: str = "commit",
               context: dict | None = None, options: dict | None = None) -> dict:
        if isinstance(text, bytes):
            try:
                text = text.decode("utf-8", errors="strict")
            except UnicodeDecodeError as e:
                raise KtrfApiError("INVALID_UTF8",
                                   f"malformed UTF-8 at byte {e.start}") from e
        nbytes = len(text.encode("utf-8"))
        if nbytes > self.async_max_input_bytes:
            raise KtrfApiError(
                "INPUT_TOO_LARGE",
                f"input is {nbytes} bytes; async limit is "
                f"{self.async_max_input_bytes}",
            )
        if mode not in ("fast", "aggressive", "commit"):
            raise KtrfApiError("INVALID_REQUEST", f"unknown mode {mode!r}")
        job = ResolveJob(
            job_id=f"job-{next(self._ids):06d}",
            snapshot=snapshot,  # single pin for the whole job (REQ-API-006)
            mode=mode,
            text=text,
            options=dict(options or {}),
            context=dict(context or {}),
            chunks=_chunk_boundaries(text, self.max_chunk_bytes),
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return {"job_id": job.job_id, "status": job.status}

    def _get(self, job_id: str) -> ResolveJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise KtrfApiError("INVALID_REQUEST", f"unknown job {job_id!r}")
        return job

    def process(self, job_id: str, max_chunks: int | None = None) -> dict:
        """Drive processing; call until status is terminal.

        Every chunk uses the snapshot pinned at submit (INV-017), including
        chunks processed after a new glossary version was activated.
        """
        job = self._get(job_id)
        if job.status in ("SUCCEEDED", "FAILED", "CANCELLED"):
            return self.status(job_id)
        job.status = "RUNNING"
        omap = OffsetMap(job.text)
        opts = dict(job.options)
        opts["return_all_mentions"] = job.options.get("return_all_mentions",
                                                      False)
        budget = max_chunks if max_chunks is not None else len(job.chunks)
        try:
            while job.chunks_done < len(job.chunks) and budget > 0:
                if job.status == "CANCELLED":
                    return self.status(job_id)
                start, end = job.chunks[job.chunks_done]
                # §28.3 overlap window recovers boundary-straddling mentions
                ext_end = min(len(job.text), end + self.overlap_chars)
                chunk_text = job.text[start:ext_end]
                resp = resolve(job.snapshot, chunk_text, mode=job.mode,
                               context=job.context, options=opts)
                job.degraded |= resp["degraded"]
                for m in resp["mentions"]:
                    cp = m["span"]["codepoint"]
                    if cp["start"] + start >= end:
                        continue  # belongs to the next chunk's window
                    g = _globalize_mention(m, omap, start)
                    key = (g["span"]["codepoint"]["start"],
                           g["span"]["codepoint"]["end"])
                    if key in job._seen_spans:
                        continue  # §20.3 duplicate merge across overlap
                    job._seen_spans.add(key)
                    g["mention_id"] = f"m{len(job.mentions) + 1}"
                    job.mentions.append(g)
                job.chunks_done += 1
                budget -= 1
        except KtrfApiError as e:
            job.status = "FAILED"
            job.error = e.to_dict()["error"]
            return self.status(job_id)
        if job.chunks_done >= len(job.chunks):
            job.status = "SUCCEEDED"
        return self.status(job_id)

    def status(self, job_id: str) -> dict:
        job = self._get(job_id)
        return {
            "job_id": job.job_id,
            "status": job.status,
            "snapshot": {
                "glossary_id": job.snapshot.glossary.glossary_id,
                "glossary_version": job.snapshot.glossary_version,
                "snapshot_id": job.snapshot.snapshot_id,
            },
            "progress": {"chunks_done": job.chunks_done,
                         "chunks_total": len(job.chunks)},
            "degraded": job.degraded,
            "error": job.error,
        }

    def results(self, job_id: str, page_token: str | None = None,
                page_size: int = 100) -> dict:
        job = self._get(job_id)
        if job.status not in ("SUCCEEDED", "RUNNING"):
            raise KtrfApiError("INVALID_REQUEST",
                               f"job {job_id} has no results ({job.status})")
        offset = int(page_token) if page_token else 0
        page = job.mentions[offset:offset + page_size]
        nxt = offset + page_size
        return {
            "mentions": page,
            "next_page_token": str(nxt) if nxt < len(job.mentions) else None,
        }

    def cancel(self, job_id: str) -> dict:
        job = self._get(job_id)
        if job.status in ("QUEUED", "RUNNING"):
            job.status = "CANCELLED"
        return self.status(job_id)
