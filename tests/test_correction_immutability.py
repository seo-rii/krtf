"""An approved correction is a record, not a view of the caller's dict
(§30, INV-018, REQ-COR-003)."""

import pytest

from ktrf.corrections import CorrectionStore


def _approved(store, corrected, verifier):
    c = store.submit(tenant_id="t", request_ref={"request_id": "r1"},
                     correction_type="WRONG_ENTITY",
                     corrected=corrected, verifier=verifier)
    store.review("t", c.correction_id, "ACCEPTED", reviewer="rev")
    return c


def test_editing_the_submitted_payload_cannot_rewrite_an_approved_record():
    """The store kept the caller's dicts, so a correction approved as one
    thing could be exported as another."""
    store = CorrectionStore()
    corrected = {"entity_id": "E_ORIGINAL"}
    _approved(store, corrected, {"kind": "USER", "principal_ref": "u1"})

    corrected["entity_id"] = "E_MUTATED"

    exported = store.export_accepted("t")
    assert exported[0]["corrected"]["entity_id"] == "E_ORIGINAL"


def test_the_verifier_kind_is_fixed_at_submission():
    """Verifier kind sets the export weight and the per-principal cap
    (REQ-COR-003), so a mutable one lets an approved USER correction be
    promoted to ADMIN weight afterwards."""
    store = CorrectionStore()
    verifier = {"kind": "USER", "principal_ref": "u1"}
    _approved(store, {"entity_id": "E1"}, verifier)

    verifier["kind"] = "ADMIN"

    exported = store.export_accepted("t")
    assert exported[0]["verifier"]["kind"] == "USER"
    assert exported[0]["weight"] == 1


def test_the_export_is_a_copy_not_a_handle_into_the_store():
    """`export_accepted` feeds calibration training; a consumer holding a
    live reference could edit the store it read from."""
    store = CorrectionStore()
    _approved(store, {"entity_id": "E1"},
              {"kind": "USER", "principal_ref": "u1"})

    first = store.export_accepted("t")
    first[0]["corrected"]["entity_id"] = "E_VIA_EXPORT"

    assert store.export_accepted("t")[0]["corrected"]["entity_id"] == "E1"


def test_nested_payload_is_copied_too():
    store = CorrectionStore()
    corrected = {"entity_id": "E1", "span": {"codepoint": {"start": 0,
                                                           "end": 3}}}
    _approved(store, corrected, {"kind": "USER", "principal_ref": "u1"})

    corrected["span"]["codepoint"]["start"] = 999

    got = store.export_accepted("t")[0]["corrected"]["span"]["codepoint"]
    assert got["start"] == 0


# ---------------------------------------- the store owns the approval state

def _one(store, tenant="t1"):
    return store.submit(
        tenant_id=tenant,
        request_ref={"snapshot_id": "s", "request_id": "r1",
                     "mention_id": "m1"},
        correction_type="WRONG_ENTITY",
        corrected={"entity_id": "E_ORIG"},
        verifier={"kind": "REVIEWER", "principal_ref": "p1"},
        mention_state={"prediction_set": {"members": []}},
    )


def test_setting_status_on_the_returned_object_is_not_an_approval():
    # `submit` handed back the stored record, so `c.status = "ACCEPTED"` put
    # the correction into the training export with no review, no reviewer and
    # no audit trail. The approval path belongs to the store.
    from ktrf.corrections import CorrectionStore

    store = CorrectionStore()
    c = _one(store)
    c.status = "ACCEPTED"
    assert store.export_accepted("t1") == []
    assert store.get("t1", c.correction_id).status == "SUBMITTED"


def test_setting_status_through_get_is_not_an_approval():
    from ktrf.corrections import CorrectionStore

    store = CorrectionStore()
    c = _one(store)
    store.get("t1", c.correction_id).status = "ACCEPTED"
    assert store.export_accepted("t1") == []


def test_setting_status_through_list_is_not_an_approval():
    from ktrf.corrections import CorrectionStore

    store = CorrectionStore()
    _one(store)
    for item in store.list("t1"):
        item.status = "ACCEPTED"
    assert store.export_accepted("t1") == []


def test_the_object_review_returns_is_also_a_copy():
    from ktrf.corrections import CorrectionStore

    store = CorrectionStore()
    c = _one(store)
    approved = store.review("t1", c.correction_id, "ACCEPTED", reviewer="adm")
    approved.corrected["entity_id"] = "E_TAMPERED"
    assert store.export_accepted("t1")[0]["corrected"]["entity_id"] == "E_ORIG"


def test_export_requires_the_audit_record_to_agree_with_the_status():
    # defence in depth: even if a status reaches ACCEPTED some other way, the
    # export is where believing it would put unreviewed labels into training
    from ktrf.corrections import CorrectionStore

    store = CorrectionStore()
    c = _one(store)
    record = store._record("t1", c.correction_id)
    record.status = "ACCEPTED"          # status without a review record
    assert store.export_accepted("t1") == []
    store2 = CorrectionStore()
    c2 = _one(store2)
    store2.review("t1", c2.correction_id, "ACCEPTED", reviewer="adm")
    assert len(store2.export_accepted("t1")) == 1


def test_a_real_approval_still_exports():
    from ktrf.corrections import CorrectionStore

    store = CorrectionStore()
    c = _one(store)
    store.review("t1", c.correction_id, "ACCEPTED", reviewer="adm")
    exported = store.export_accepted("t1")
    assert len(exported) == 1
    assert exported[0]["corrected"]["entity_id"] == "E_ORIG"
    assert exported[0]["review"]["reviewer"] == "adm"
