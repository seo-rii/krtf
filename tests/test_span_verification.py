"""A span is verified because of its shape, not because of its name.

The review's R6 defect was not that anyone wrote a wrong offset. It was that
`core_link.span` was added to the response and nothing checked it, because
the checker named the one field it knew: `m["span"]`. The next nested span
would have been missed the same way.

`verify_response_spans` walks the whole response and checks anything shaped
like a span record. These tests prove it has teeth by breaking responses in
the exact ways the translator has broken them, and prove it does not cry
wolf over `full_span`, which is deliberately wider than the surface next to
it.
"""

import copy

import pytest

from ktrf.glossary import load_glossary
from ktrf.offsets import OffsetMap, is_span_record, verify_response_spans
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot

GLOSSARY = "examples/realorg_glossary.yaml"

# 전 한전노조 gives a mention with a *nested* core_link span that does not
# start at the document's first character — a mutation on it is a real one.
TEXT = ("금융감독원이 조사에 착수했다. 전 한전노조가 성명을 냈다. "
        "한국전력공사는 별도 입장을 내지 않았다.")


@pytest.fixture(scope="module")
def snapshot():
    return compile_snapshot(load_glossary(GLOSSARY))


@pytest.fixture(scope="module")
def response(snapshot):
    return resolve(snapshot, TEXT, mode="commit",
                   options={"return_all_mentions": True})


def _nested(response):
    """A mention carrying a core_link span away from the document start."""
    for i, m in enumerate(response["mentions"]):
        cl = m.get("core_link")
        if cl and cl["span"]["codepoint"]["start"] > 0:
            return i
    pytest.skip("no nested span in this document")


# ------------------------------------------------------------ recognition

def test_a_span_is_recognised_by_its_shape():
    m = OffsetMap("한국전력공사")
    assert is_span_record(m.span_dict(0, 3))


@pytest.mark.parametrize("value", [
    None, 42, "span", [], {},
    {"byte": {"start": 0, "end": 1}},                    # partial
    {"byte": 0, "codepoint": 0, "utf16": 0},             # not sub-records
    {"byte": {}, "codepoint": {"start": 0}, "utf16": {}},  # no end
])
def test_things_that_are_not_spans(value):
    assert not is_span_record(value)


def test_a_span_under_a_brand_new_name_is_still_checked(response):
    """The whole point: tomorrow's field is covered today."""
    mutated = copy.deepcopy(response)
    mutated["mentions"][0]["some_field_added_next_quarter"] = {
        "span": OffsetMap(TEXT).span_dict(0, 4),
        "surface": "완전히 다른 표면",
    }
    problems = verify_response_spans(mutated, TEXT)
    assert any("some_field_added_next_quarter" in p for p in problems), problems


# ----------------------------------------------------------------- teeth

def test_a_clean_response_has_nothing_to_report(response):
    assert verify_response_spans(response, TEXT) == []


def test_a_nested_span_left_in_chunk_coordinates_is_caught(response):
    """R6, exactly: the translator moved `span` and forgot `core_link.span`."""
    i = _nested(response)
    mutated = copy.deepcopy(response)
    cp = mutated["mentions"][i]["core_link"]["span"]["codepoint"]
    width = cp["end"] - cp["start"]
    cp["start"], cp["end"] = 0, width

    problems = verify_response_spans(mutated, TEXT)
    assert problems, "a nested span pointing at the wrong text was not reported"
    assert all(f"mentions[{i}].core_link.span" in p for p in problems), problems


def test_a_span_past_the_end_of_the_text_is_caught(response):
    mutated = copy.deepcopy(response)
    mutated["mentions"][0]["span"]["codepoint"]["end"] = len(TEXT) + 5
    problems = verify_response_spans(mutated, TEXT)
    assert len(problems) == 1, problems
    assert "outside a text of" in problems[0]


def test_encodings_that_disagree_with_each_other_are_caught(response):
    """REQ-OFF-003: three encodings, one substring."""
    mutated = copy.deepcopy(response)
    mutated["mentions"][0]["span"]["byte"]["start"] += 3
    problems = verify_response_spans(mutated, TEXT)
    assert len(problems) == 1, problems
    assert ".byte:" in problems[0]


def test_a_surface_that_does_not_match_its_span_is_caught(response):
    mutated = copy.deepcopy(response)
    mutated["mentions"][0]["surface"] = "이건 그 자리에 없는 글자"
    problems = verify_response_spans(mutated, TEXT)
    assert any(".surface=" in p for p in problems), problems


def test_every_span_is_reported_not_only_the_first(response):
    mutated = copy.deepcopy(response)
    for m in mutated["mentions"][:2]:
        m["span"]["codepoint"]["end"] = len(TEXT) + 1
    assert len(verify_response_spans(mutated, TEXT)) == 2


# ------------------------------------------------------------ no crying wolf

def test_full_span_is_not_paired_with_the_core_surface(response):
    """`full_span` is wider than `surface` by design, and that is not a bug."""
    wide = [m for m in response["mentions"]
            if m.get("full_span", m["span"]) != m["span"]]
    assert wide, "fixture no longer exercises a widened full_span"
    assert verify_response_spans(response, TEXT) == []


def test_full_surface_still_has_its_own_span_checked(response):
    """It carries `span` + `surface`, so the pairing does apply to it."""
    i = _nested(response)
    mutated = copy.deepcopy(response)
    fs = mutated["mentions"][i]["full_surface"]
    fs["surface"] = fs["surface"] + "군더더기"
    problems = verify_response_spans(mutated, TEXT)
    assert any(f"mentions[{i}].full_surface.span" in p for p in problems), \
        problems


def test_the_chunked_path_carries_document_coordinates(snapshot):
    """The transformation the verifier exists to police."""
    from ktrf.jobs import ResolveJobManager

    nbytes = len(TEXT.encode("utf-8"))
    mgr = ResolveJobManager(max_chunk_bytes=nbytes // 3 + 20)
    jid = mgr.submit(snapshot, TEXT,
                     options={"return_all_mentions": True})["job_id"]
    assert len(mgr._get(jid).chunks) > 1
    mgr.process(jid)
    results = mgr.results(jid, page_size=500)
    assert verify_response_spans(results, TEXT) == []
