"""The same meaning has to survive every transformation the system makes.

The review's diagnosis was not that any one module is wrong. It is that the
same semantic contract is partly reimplemented in several places, so a change
in one leaves the others behind: a new span field the chunk translator does
not know, a new manifest key the loader does not verify, a candidate list cut
in one place and read in another.

Tests over the normal path do not catch that. These do, because they compare
the *whole* structure across a transformation rather than the fields somebody
remembered to check — a field added tomorrow is covered tomorrow.

Six transformations, from the review's own list:

    save -> load                the bundle is the snapshot
    sync -> chunked             a document is a document however it is cut
    full -> truncated display   a display option decides nothing
    compile -> input mutation   the snapshot owns its content
    accepted -> export          an approved label is what was approved
    active -> evicted -> reload eviction is not a state change
"""

import copy
import random
import tempfile
from pathlib import Path

import pytest

from ktrf.artifacts import load_snapshot, save_snapshot
from ktrf.corrections import CorrectionStore
from ktrf.glossary import load_glossary
from ktrf.jobs import ResolveJobManager
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot
from ktrf.tiers import TieredSnapshotStore

GLOSSARY = "examples/realorg_glossary.yaml"


# --------------------------------------------------------------- comparison

def differences(a, b, path="", skip=(), out=None):
    """Every leaf where two structures disagree.

    Structural rather than field-by-field on purpose: naming the fields to
    compare is the same mistake as naming the fields to translate.
    """
    if out is None:
        out = []
    if path.rsplit(".", 1)[-1].split("[")[0] in skip:
        return out
    if type(a) is not type(b):
        out.append(f"{path}: {type(a).__name__} vs {type(b).__name__}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: absent on the left")
            elif k not in b:
                out.append(f"{path}.{k}: absent on the right")
            else:
                differences(a[k], b[k], f"{path}.{k}", skip, out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} items vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            differences(x, y, f"{path}[{i}]", skip, out)
    elif a != b:
        out.append(f"{path}: {a!r} vs {b!r}")
    return out


DOCUMENTS = [
    # plain registered aliases, repeated
    "한전노조가 성명을 냈다. 금융감독원이 조사에 착수했다고 밝혔다. "
    "한국전력공사는 이에 대해 별도 입장을 내지 않았다. "
    "금감원장은 추가 검토가 필요하다고 말했다.",
    # a document that defines its own abbreviation and then uses it: the
    # definition is in the first chunk and the uses are not
    '과학기술정보통신부(이하 "과기정통부")는 대책을 발표했다. '
    "과기정통부는 이어 후속 조치를 설명했다. "
    "국토교통부와 기획재정부도 참여한다고 밝혔다. "
    "과기정통부 관계자는 추가 협의가 필요하다고 말했다.",
    # morphology: particles, suffixes, a prefix modifier
    "한전에서도 확인했다. 전 한전 사장이 참석했다. 한전본부 앞으로 전달했다. "
    "금융위원회와 공정거래위원회가 함께 검토한다.",
]


@pytest.fixture(scope="module")
def snap():
    return compile_snapshot(load_glossary(GLOSSARY))


def _resolve_all(s, text):
    return resolve(s, text, mode="commit",
                   options={"return_all_mentions": True})


# ----------------------------------------------------- sync <-> chunked

@pytest.mark.parametrize("text", DOCUMENTS)
@pytest.mark.parametrize("pieces", [2, 3, 4])
def test_a_document_resolves_the_same_however_it_is_cut(snap, text, pieces):
    sync = _resolve_all(snap, text)["mentions"]
    nbytes = len(text.encode("utf-8"))
    mgr = ResolveJobManager(max_chunk_bytes=nbytes // pieces + 20)
    job = mgr.submit(snap, text, options={"return_all_mentions": True})
    if len(mgr._get(job["job_id"]).chunks) < 2:
        pytest.skip("document did not actually split")
    mgr.process(job["job_id"])
    chunked = mgr.results(job["job_id"], page_size=1000)["mentions"]
    # mention_id is assigned per response and is expected to be positional
    diff = differences(sync, chunked, "mentions", skip=("mention_id",))
    assert diff == [], "\n".join(diff[:12])


def test_the_definition_reaches_the_chunks_that_use_it(snap):
    # the fixture that found this: without document-wide bindings the
    # abbreviation loses its doc_local evidence in every chunk after the one
    # holding the definition
    text = DOCUMENTS[1]
    nbytes = len(text.encode("utf-8"))
    mgr = ResolveJobManager(max_chunk_bytes=nbytes // 3 + 20)
    job = mgr.submit(snap, text, options={"return_all_mentions": True})
    mgr.process(job["job_id"])
    uses = [m for m in mgr.results(job["job_id"], page_size=1000)["mentions"]
            if m["surface"] == "과기정통부"]
    assert len(uses) >= 3
    # every occurrence of the alias carries the definition, the one inside
    # the parentheses included. Counting *uses* skips the defining site;
    # deciding what it means must not, or a glossary that disagrees wins the
    # one node the document was explicitly talking about.
    assert all("doc_local" in m["generation_channels"] for m in uses), \
        [m["generation_channels"] for m in uses]
    # and the later ones are in chunks the definition is not in
    assert uses[-1]["span"]["codepoint"]["start"] > 60


def test_every_position_belongs_to_exactly_one_chunk(snap):
    # the overlap windows must not duplicate or drop a mention
    text = DOCUMENTS[0]
    nbytes = len(text.encode("utf-8"))
    mgr = ResolveJobManager(max_chunk_bytes=nbytes // 4 + 20)
    job = mgr.submit(snap, text, options={"return_all_mentions": True})
    mgr.process(job["job_id"])
    spans = [(m["span"]["codepoint"]["start"], m["span"]["codepoint"]["end"])
             for m in mgr.results(job["job_id"], page_size=1000)["mentions"]]
    assert len(spans) == len(set(spans))


# ------------------------------------------------------- save <-> load

@pytest.mark.parametrize("text", DOCUMENTS)
def test_a_reloaded_bundle_answers_the_same(snap, text, tmp_path):
    save_snapshot(snap, tmp_path / "bundle")
    back = load_snapshot(tmp_path / "bundle")
    assert back.snapshot_id == snap.snapshot_id
    diff = differences(_resolve_all(snap, text), _resolve_all(back, text),
                       "response")
    assert diff == [], "\n".join(diff[:12])


# --------------------------------------------- full <-> truncated display

@pytest.mark.parametrize("text", DOCUMENTS)
def test_a_display_limit_changes_no_decision(snap, text):
    full = _resolve_all(snap, text)["mentions"]
    cut = resolve(snap, text, mode="commit",
                  options={"return_all_mentions": True,
                           "max_prediction_set": 1})["mentions"]
    assert len(full) == len(cut)
    for a, b in zip(full, cut):
        # everything except the member list itself has to agree
        diff = differences(a, b, a["surface"], skip=("prediction_set",))
        assert diff == [], "\n".join(diff[:8])


# --------------------------------------------- compile <-> input mutation

@pytest.mark.parametrize("text", DOCUMENTS)
def test_mutating_the_input_glossary_changes_no_answer(text):
    g = load_glossary(GLOSSARY)
    s = compile_snapshot(g)
    before = _resolve_all(s, text)
    for e in g.entities:
        e.canonical = "MUTATED"
        e.description = "MUTATED"
    for b in g.alias_bindings:
        b.surface = "MUTATED"
    after = _resolve_all(s, text)
    diff = differences(before, after, "response")
    assert diff == [], "\n".join(diff[:12])


# ------------------------------------------- accepted <-> exported label

def test_an_exported_label_cannot_be_edited_back_into_the_store():
    store = CorrectionStore()
    c = store.submit(
        tenant_id="t1",
        request_ref={"snapshot_id": "s", "request_id": "r1",
                     "mention_id": "m1"},
        correction_type="WRONG_ENTITY",
        corrected={"entity_id": "E_ORIG"},
        verifier={"kind": "REVIEWER", "principal_ref": "p1"},
        mention_state={"prediction_set": {"members": []}})
    store.review("t1", c.correction_id, "ACCEPTED", reviewer="adm")
    first = store.export_accepted("t1")
    snapshot_of_first = copy.deepcopy(first)
    # every kind of edit a consumer could make to what it was handed
    first[0]["corrected"]["entity_id"] = "E_TAMPERED"
    first[0]["verifier"]["kind"] = "ADMIN"
    first[0]["status"] = "REJECTED"
    first[0]["review"]["reviewer"] = "someone else"
    second = store.export_accepted("t1")
    assert differences(snapshot_of_first, second, "export") == []


# ------------------------------------- active <-> evicted <-> reloaded

@pytest.mark.parametrize("text", DOCUMENTS)
def test_eviction_and_cold_start_change_no_answer(text, tmp_path):
    store = TieredSnapshotStore(tmp_path, max_hot=1)
    live = compile_snapshot(load_glossary(GLOSSARY), tenant_id="t1")
    store.activate(live)
    with store.acquire("t1") as hot:
        before = _resolve_all(hot, text)
    # push it out of the hot tier
    store.activate(compile_snapshot(load_glossary(GLOSSARY), tenant_id="t2"))
    assert store.tier_of("t1") == "cold"
    with store.acquire("t1") as cold:
        after = _resolve_all(cold, text)
        assert cold.snapshot_id == live.snapshot_id
    diff = differences(before, after, "response")
    assert diff == [], "\n".join(diff[:12])


# ------------------------------------------------- the comparison itself

def test_the_comparison_can_actually_fail():
    # a structural comparison that never reports anything would make every
    # test above vacuous
    assert differences({"a": 1}, {"a": 2}) == [".a: 1 vs 2"]
    assert differences({"a": 1}, {}) == [".a: absent on the right"]
    assert differences([1], [1, 2]) == [": 1 items vs 2"]
    assert differences({"a": {"b": 1}}, {"a": {"b": 1}}) == []
    assert differences({"a": 1}, {"a": 2}, skip=("a",)) == []


# ----------------------------------------- the same invariant, at scale

def test_the_chunking_invariant_holds_over_generated_documents():
    """Three hand-written documents are three shapes.

    This builds documents out of a synthetic glossary — definitions, particle
    chains, prefix modifiers, repeated surfaces — and checks the same
    invariant across several chunk counts. The seed is fixed so a failure is
    reproducible; the point is coverage of shapes, not randomness.
    """
    from eval.synthetic import build_synthetic_glossary

    g_dict, _meta = build_synthetic_glossary(200, seed=1)
    glossary = load_glossary(g_dict)
    s = compile_snapshot(glossary, strict=False, run_conformance=False)
    surfaces = [b.surface for b in glossary.alias_bindings]
    fillers = ["관련 회의를 진행했다.", "검토 대상이다.", "공유되었다.",
               "앞으로 전달했다.", "에서도 확인했다."]
    rng = random.Random(20260905)

    compared = 0
    for _ in range(8):
        parts = []
        for _ in range(rng.randint(4, 10)):
            surface = rng.choice(surfaces)
            style = rng.randint(0, 3)
            if style == 0:
                parts.append(f"{surface} {rng.choice(fillers)}")
            elif style == 1:
                parts.append(f'{surface}(이하 "{surface[:2]}")는 발표했다.')
            elif style == 2:
                parts.append(f"{surface}에서도 {rng.choice(fillers)}")
            else:
                parts.append(f"구 {surface} 조직 개편안이다.")
        text = " ".join(parts)
        nbytes = len(text.encode("utf-8"))
        sync = resolve(s, text, mode="commit",
                       options={"return_all_mentions": True})["mentions"]
        for pieces in (2, 3):
            mgr = ResolveJobManager(max_chunk_bytes=nbytes // pieces + 20)
            jid = mgr.submit(s, text,
                             options={"return_all_mentions": True})["job_id"]
            if len(mgr._get(jid).chunks) < 2:
                continue
            mgr.process(jid)
            chunked = mgr.results(jid, page_size=2000)["mentions"]
            compared += 1
            diff = differences(sync, chunked, "mentions",
                               skip=("mention_id",))
            assert diff == [], f"{text[:60]!r}\n" + "\n".join(diff[:10])
    assert compared >= 8, "the fixture has to actually produce split documents"
