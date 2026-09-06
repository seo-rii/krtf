"""Async job defects found by an external review (§28, INV-017).

Both reproduced against the shipped code before these tests existed, and both
passed the whole suite while broken: the existing job tests drive `process()`
from one thread and check only the top-level span.
"""

import threading

import pytest

from ktrf.glossary import load_glossary
from ktrf.jobs import ResolveJobManager
from ktrf.snapshot import compile_snapshot


@pytest.fixture(scope="module")
def snap():
    return compile_snapshot(load_glossary("examples/realorg_glossary.yaml"))


def _two_chunk_job(snap, mgr_kwargs=None):
    text = ("한국전력공사가 발표했다. " * 8) + ("금융감독원이 조사했다. " * 8)
    kwargs = {"max_chunk_bytes": len(text.encode("utf-8")) // 2 + 20}
    kwargs.update(mgr_kwargs or {})
    mgr = ResolveJobManager(**kwargs)
    job_id = mgr.submit(snap, text)["job_id"]
    assert len(mgr._get(job_id).chunks) == 2
    return mgr, job_id, text


def test_two_workers_do_not_take_the_same_chunk(snap):
    """Both workers read `chunks_done == 0`, both processed chunk 0, and both
    incremented — leaving the job SUCCEEDED at 2/2 with the second chunk
    never resolved. Data loss reported as success.

    A barrier rather than a sleep: the failure needs the two reads to
    interleave, and a timing-based test would pass on a quiet machine.
    """
    mgr, job_id, _text = _two_chunk_job(snap)
    barrier = threading.Barrier(2)
    errors = []

    def worker():
        try:
            barrier.wait(timeout=10)
            mgr.process(job_id, max_chunks=1)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, errors
    surfaces = {m["surface"] for m in mgr.results(job_id)["mentions"]}
    assert surfaces == {"한국전력공사", "금융감독원"}, surfaces


def test_a_job_succeeds_only_when_every_chunk_is_done(snap):
    mgr, job_id, _text = _two_chunk_job(snap)
    st = mgr.process(job_id, max_chunks=1)
    assert st["status"] == "RUNNING"
    assert st["progress"]["chunks_done"] == 1
    st = mgr.process(job_id, max_chunks=1)
    assert st["status"] == "SUCCEEDED"
    assert st["progress"]["chunks_done"] == 2


def test_mention_ids_do_not_depend_on_worker_order(snap):
    """Ids are assigned when results are read, so the document decides them
    rather than whichever worker finished first."""
    serial_mgr, serial_id, _ = _two_chunk_job(snap)
    serial_mgr.process(serial_id)
    serial = [(m["mention_id"], m["surface"]) for m in
              serial_mgr.results(serial_id)["mentions"]]

    mgr, job_id, _ = _two_chunk_job(snap)
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait(timeout=10)
        mgr.process(job_id)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert [(m["mention_id"], m["surface"]) for m in
            mgr.results(job_id)["mentions"]] == serial


# ---------------------------------------------------------------------------
# every span, not the ones someone remembered
# ---------------------------------------------------------------------------


def _spans_with_surfaces(mention):
    """(label, span, surface) for every span the response carries."""
    yield "span", mention["span"], mention["surface"]
    for field in ("core_link", "full_surface"):
        block = mention.get(field)
        if isinstance(block, dict) and isinstance(block.get("span"), dict):
            yield field, block["span"], block.get("surface")


def test_every_nested_span_is_in_document_coordinates(snap):
    """`_globalize_mention` named the fields it shifted, so `core_link.span`
    and `full_surface.span` — added by M2 — stayed chunk-relative. One
    mention then carried a correct top-level span beside nested spans
    pointing at unrelated text.
    """
    head = "가나다라마바사아자차 " * 14
    text = head + "네이버웹툰이 신작을 공개했다."
    mgr = ResolveJobManager(
        max_chunk_bytes=len("가나다라마바사아자차 ".encode("utf-8")) * 10 + 5)
    job_id = mgr.submit(snap, text)["job_id"]
    assert len(mgr._get(job_id).chunks) > 1
    mgr.process(job_id)

    checked = 0
    for m in mgr.results(job_id, page_size=500)["mentions"]:
        for label, span, surface in _spans_with_surfaces(m):
            if surface is None:
                continue
            checked += 1
            for enc, cut in (("codepoint", lambda s, e: text[s:e]),
                             ("utf16", None),
                             ("byte", None)):
                if enc != "codepoint":
                    continue
                cp = span["codepoint"]
                assert cut(cp["start"], cp["end"]) == surface, (
                    f"{label}: span says "
                    f"{cut(cp['start'], cp['end'])!r}, surface is {surface!r}")
    assert checked >= 3, f"only {checked} spans carried a surface to check"


def test_a_span_added_later_is_covered_without_editing_the_shifter():
    """The shape is what makes a span, not a name on a list — which is how
    the previous version stopped covering the response."""
    from ktrf.jobs import _globalize_mention
    from ktrf.offsets import OffsetMap, is_span_record

    text = "가나다라 한국전력공사"
    omap = OffsetMap(text)
    m = {"deeply": {"nested": [{"span": omap.span_dict(0, 2)}]}}
    assert is_span_record(omap.span_dict(0, 2))
    out = _globalize_mention(m, omap, 5)
    moved = out["deeply"]["nested"][0]["span"]["codepoint"]
    assert (moved["start"], moved["end"]) == (5, 7)
