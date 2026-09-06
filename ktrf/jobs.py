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

import dataclasses
import itertools
from dataclasses import dataclass, field
from threading import Lock

from .errors import KtrfApiError
from .offsets import OffsetMap, is_span_record
from .resolver import _validate_context, _validate_options, resolve
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
    """Move every span in a chunk-local mention into document coordinates.

    This used to name the fields it shifted — `span`, `full_span`,
    `prefix.span`, `matched_segments` — and so it silently stopped covering
    the response when M2 added `core_link.span` and `full_surface.span`. A
    mention then carried a correct top-level span beside nested spans still
    measured from the start of its chunk, pointing at unrelated text.
    Recognising a span by its shape means a new one is covered the day it is
    added rather than the day someone remembers this function.
    """
    def walk(value):
        if is_span_record(value):
            return _shift_span(value, omap, cp_shift)
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    out = {k: walk(v) for k, v in m.items()}
    # plain {start, end} pairs are not span records and keep their own handling
    if "matched_segments" in m:
        out["matched_segments"] = [
            {"start": seg["start"] + cp_shift, "end": seg["end"] + cp_shift}
            for seg in m["matched_segments"]
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
    # §18 definitions found in the whole document, shared by every chunk.
    # A definition is a property of the document, not of the piece it happens
    # to fall in.
    doc_local_bindings: list = field(default_factory=list)
    status: str = "QUEUED"  # QUEUED|RUNNING|SUCCEEDED|FAILED|CANCELLED
    # PENDING -> CLAIMED -> DONE, one per chunk. A shared `chunks_done`
    # counter cannot express "someone else is already on chunk 3", which is
    # how two workers both took chunk 0 and the job still reported success.
    chunk_state: list[str] = field(default_factory=list)
    chunk_results: list[list | None] = field(default_factory=list)
    degraded: bool = False
    error: dict | None = None

    def __post_init__(self):
        if not self.chunk_state:
            self.chunk_state = ["PENDING"] * len(self.chunks)
        if not self.chunk_results:
            self.chunk_results = [None] * len(self.chunks)

    @property
    def chunks_done(self) -> int:
        return sum(1 for st in self.chunk_state if st == "DONE")

    @property
    def mentions(self) -> list[dict]:
        """Committed chunks in document order, deduplicated across overlaps.

        Assembled on read rather than appended during processing: mention ids
        then depend on the document, not on which worker happened to finish
        first.
        """
        seen: set[tuple[int, int]] = set()
        out: list[dict] = []
        for chunk in self.chunk_results:
            for m in chunk or ():
                key = (m["span"]["codepoint"]["start"],
                       m["span"]["codepoint"]["end"])
                if key in seen:
                    continue          # §20.3 duplicate merge across overlap
                seen.add(key)
                m = dict(m)
                m["mention_id"] = f"m{len(out) + 1}"
                out.append(m)
        return out


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
        # Validate here, not on the first chunk. Otherwise a typo in the
        # options is accepted, a job id is handed back, and the job fails
        # somewhere in a worker later — the caller has already moved on, and
        # what should have been a rejected request became a failed job.
        _validate_options(options or {})
        _validate_context(context or {})
        job = ResolveJob(
            job_id=f"job-{next(self._ids):06d}",
            snapshot=snapshot,  # single pin for the whole job (REQ-API-006)
            mode=mode,
            text=text,
            options=dict(options or {}),
            context=dict(context or {}),
            chunks=_chunk_boundaries(text, self.max_chunk_bytes),
            # extracted once, from the whole text, against the pinned
            # snapshot (INV-017) — the same bindings every chunk will see
            doc_local_bindings=snapshot.doclocal.extract(text),
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
        with self._lock:
            if job.status == "QUEUED":
                job.status = "RUNNING"
        omap = OffsetMap(job.text)
        opts = dict(job.options)
        opts["return_all_mentions"] = job.options.get("return_all_mentions",
                                                      False)
        budget = max_chunks if max_chunks is not None else len(job.chunks)
        try:
            while budget > 0:
                if job.status == "CANCELLED":
                    return self.status(job_id)
                # claim one chunk: the read and the mark are one step, so two
                # workers cannot both decide that chunk i is next
                with self._lock:
                    idx = next((i for i, st in enumerate(job.chunk_state)
                                if st == "PENDING"), None)
                    if idx is None:
                        break          # nothing left to claim
                    job.chunk_state[idx] = "CLAIMED"
                start, end = job.chunks[idx]
                # §28.3 overlap on BOTH sides. The forward window recovers a
                # mention straddling the end; the backward one gives a mention
                # near the start the left context the scorer reads. With only
                # the forward half, the same sentence scored lower purely
                # because a chunk boundary fell in front of it — the context
                # bonus is computed from a window that was cut off.
                ext_start = max(0, start - self.overlap_chars)
                ext_end = min(len(job.text), end + self.overlap_chars)
                chunk_text = job.text[ext_start:ext_end]
                try:
                    # The bindings are in document coordinates and the chunk
                    # is resolved in its own, so `definition_span` has to be
                    # translated with the text it describes. Without this the
                    # "skip the defining occurrence" rule reads a document
                    # offset against a chunk offset and silently drops the
                    # first use in every later chunk. A definition in another
                    # chunk lands outside this one's range, which is exactly
                    # what should happen.
                    local = [dataclasses.replace(
                        b, definition_span=(b.definition_span[0] - ext_start,
                                            b.definition_span[1] - ext_start))
                        for b in job.doc_local_bindings]
                    resp = resolve(job.snapshot, chunk_text, mode=job.mode,
                                   context=job.context, options=opts,
                                   doc_local_bindings=local)
                except BaseException:
                    with self._lock:
                        if job.chunk_state[idx] == "CLAIMED":
                            job.chunk_state[idx] = "PENDING"
                    raise
                found = []
                for m in resp["mentions"]:
                    cp = m["span"]["codepoint"]
                    global_start = cp["start"] + ext_start
                    # a mention belongs to the chunk its start falls in, so
                    # every position belongs to exactly one chunk: nothing in
                    # either overlap window is counted twice or dropped
                    if not (start <= global_start < end):
                        continue
                    found.append(_globalize_mention(m, omap, ext_start))
                # commit exactly once: a chunk no longer CLAIMED was taken
                # over (cancelled, or reset by a failure) and its result is
                # not ours to record
                with self._lock:
                    if job.chunk_state[idx] != "CLAIMED":
                        continue
                    job.degraded |= resp["degraded"]
                    job.chunk_results[idx] = found
                    job.chunk_state[idx] = "DONE"
                budget -= 1
        except KtrfApiError as e:
            with self._lock:
                job.status = "FAILED"
                job.error = e.to_dict()["error"]
            return self.status(job_id)
        with self._lock:
            if (job.status == "RUNNING"
                    and all(st == "DONE" for st in job.chunk_state)):
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
