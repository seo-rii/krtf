"""Every request field is schema-checked, and checked where it is accepted.

The options table was already strict. Two things around it were not:

* the scope ``context`` was not validated at all, so an unrecognised key was
  silently ignored. That matters more here than anywhere else in the API,
  because the glossary spells the scope dimension ``departments`` and the
  request spells it ``department`` — the likeliest typo in the whole surface
  resolves to nothing, raises nothing, and changes the answer.
* the async API validated options on the first chunk rather than at submit,
  so a bad request got a job id back and failed later in a worker.
"""

import pytest

from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.jobs import ResolveJobManager
from ktrf.resolver import _OPTION_SCHEMA, TRUST_LEVELS, resolve
from ktrf.snapshot import compile_snapshot

GLOSSARY = "examples/realorg_glossary.yaml"
TEXT = "금융감독원이 조사했다"


@pytest.fixture(scope="module")
def snap():
    return compile_snapshot(load_glossary(GLOSSARY))


def _code(excinfo):
    return excinfo.value.to_dict()["error"]["code"]


# ------------------------------------------------------------------ options

@pytest.mark.parametrize("options", [
    {"max_prediction_set": -1},
    {"max_prediction_set": 0},
    {"max_prediction_set": 10 ** 9},
    {"max_prediction_set": "3"},
    {"max_prediction_set": True},       # bool is an int subclass
    {"max_prediction_set": 2.5},
    {"return_all_mentions": 1},         # int is not a bool
    {"no_such_option": 1},
])
def test_a_bad_option_is_a_typed_error(snap, options):
    with pytest.raises(KtrfApiError) as e:
        resolve(snap, TEXT, mode="commit", options=options)
    assert _code(e) == "INVALID_REQUEST"


def test_an_unknown_option_lists_the_known_ones(snap):
    with pytest.raises(KtrfApiError) as e:
        resolve(snap, TEXT, mode="commit", options={"nope": 1})
    known = e.value.to_dict()["error"]["details"]["known"]
    assert "max_prediction_set" in known and "deadline_ms" in known


# ------------------------------------------------------------------ context

def test_the_plural_typo_is_rejected_rather_than_ignored(snap):
    # the glossary side is `departments`, the request side is `department`
    with pytest.raises(KtrfApiError) as e:
        resolve(snap, TEXT, mode="commit",
                context={"departments": {"value": "finance"}})
    assert _code(e) == "INVALID_REQUEST"
    assert "department" in e.value.to_dict()["error"]["details"]["known"]


@pytest.mark.parametrize("context", [
    {"bogus": 1},
    {"department": 5},
    {"department": ["finance"]},
    {"department": {"value": 5}},
    {"department": {"trust": "AUTH_CLAIM"}},          # no value
    {"department": {"value": "f", "trusst": "AUTH_CLAIM"}},
    {"department": {"value": "f", "trust": "SERVER_VERIFED"}},
])
def test_a_bad_context_is_a_typed_error(snap, context):
    with pytest.raises(KtrfApiError) as e:
        resolve(snap, TEXT, mode="commit", context=context)
    assert _code(e) == "INVALID_REQUEST"


def test_a_misspelled_trust_level_does_not_silently_downgrade(snap):
    # it used to fall through every branch and behave as UNTRUSTED — the
    # safe-looking direction, and a silent downgrade of a rule the caller
    # meant to enforce
    with pytest.raises(KtrfApiError) as e:
        resolve(snap, TEXT, mode="commit",
                context={"department": {"value": "finance",
                                        "trust": "AUTH-CLAIM"}})
    assert set(e.value.to_dict()["error"]["details"]["known"]) == set(
        TRUST_LEVELS)


@pytest.mark.parametrize("context", [
    {},
    {"department": "finance"},
    {"department": {"value": "finance"}},
    {"department": {"value": "finance", "trust": "AUTH_CLAIM"}},
    {"department": "finance", "project": {"value": "p1"}},
])
def test_a_valid_context_still_works(snap, context):
    resp = resolve(snap, TEXT, mode="commit", context=context)
    assert resp["mentions"]


# ------------------------------------------------------------- async submit

def test_the_async_api_rejects_a_bad_option_at_submit(snap):
    mgr = ResolveJobManager()
    with pytest.raises(KtrfApiError) as e:
        mgr.submit(snap, TEXT, options={"max_prediction_set": -5})
    assert _code(e) == "INVALID_REQUEST"


def test_the_async_api_rejects_a_bad_context_at_submit(snap):
    mgr = ResolveJobManager()
    with pytest.raises(KtrfApiError) as e:
        mgr.submit(snap, TEXT, context={"departments": "finance"})
    assert _code(e) == "INVALID_REQUEST"


def test_a_rejected_submit_creates_no_job(snap):
    # the failure mode this replaces: a job id handed back for a request that
    # was never going to run
    mgr = ResolveJobManager()
    with pytest.raises(KtrfApiError):
        mgr.submit(snap, TEXT, options={"bogus": True})
    assert mgr._jobs == {}


def test_a_good_submit_still_runs(snap):
    mgr = ResolveJobManager()
    job = mgr.submit(snap, TEXT, options={"max_prediction_set": 3},
                     context={"department": "finance"})
    assert mgr.process(job["job_id"])["status"] == "SUCCEEDED"


# --------------------------------------------------------- the invariant

hypothesis = pytest.importorskip("hypothesis")
st = pytest.importorskip("hypothesis.strategies")
from hypothesis import given, settings  # noqa: E402

_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False)
    | st.text(max_size=12),
    lambda inner: st.lists(inner, max_size=3) | st.dictionaries(
        st.text(max_size=8), inner, max_size=3),
    max_leaves=6,
)


# Draw keys mostly from the REAL option names. Purely random keys are
# rejected as unknown on the first check and never reach a value validator,
# so a test built on them passes without exercising anything.
_OPTION_KEYS = st.sampled_from(sorted(_OPTION_SCHEMA)) | st.text(max_size=8)
_CONTEXT_KEYS = st.sampled_from(["department", "project"]) | st.text(max_size=8)


# The snapshot is fetched inside rather than taken as an argument: hypothesis
# reprs its arguments on failure, and a whole snapshot is 192 kB of noise
# around the one value that actually broke.
_SNAP = None


def _shared_snap():
    global _SNAP
    if _SNAP is None:
        _SNAP = compile_snapshot(load_glossary(GLOSSARY))
    return _SNAP


@settings(max_examples=400, deadline=None)
@given(options=st.dictionaries(_OPTION_KEYS, _VALUES, max_size=3))
def test_no_option_value_escapes_as_an_untyped_error(options):
    """The property the table exists to provide.

    Enumerating bad values by hand is how the gaps got in: the review found
    negatives, zero, huge integers and a raw TypeError on a string, each of
    which someone had to think of. The invariant is simpler than the list —
    every request either resolves or raises KtrfApiError, and nothing else
    reaches the caller.
    """
    try:
        resolve(_shared_snap(), TEXT, mode="commit", options=options)
    except KtrfApiError:
        pass


@settings(max_examples=400, deadline=None)
@given(context=st.dictionaries(_CONTEXT_KEYS, _VALUES, max_size=3))
def test_no_context_value_escapes_as_an_untyped_error(context):
    try:
        resolve(_shared_snap(), TEXT, mode="commit", context=context)
    except KtrfApiError:
        pass
