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
