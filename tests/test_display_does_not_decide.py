"""A response option must not choose which entity a document is about.

`max_prediction_set` is a display limit. It was applied to `members` before
the decision was read off that same list, so asking for one member did not
just hide the second sense — it removed the evidence that there *was* a second
sense. The margin test then found a singleton and committed.

The observable failure: two candidates tied at 0.99, AMBIGUOUS at
`max_prediction_set=10`, RESOLVED to whichever sorted first at 1. Nothing
about the scoring changed between the two calls.
"""

import pytest

from ktrf.calibration import TunedCalibrator
from ktrf.glossary import load_glossary
from ktrf.resolver import resolve
from ktrf.snapshot import compile_snapshot


def _two_sense_glossary():
    return load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [
            {"entity_id": "E_AP_NET", "canonical": "Access Point",
             "description": "wireless network device", "domain_ids": ["NET"]},
            {"entity_id": "E_AP_WF", "canonical": "Approval Process",
             "description": "approval workflow", "domain_ids": ["WF"]},
        ],
        "alias_families": [
            {"family_id": "F_AP", "representative": "AP",
             "normalization_profile": "latin_acronym"},
        ],
        "alias_bindings": [
            {"alias_id": "A_AP1", "family_id": "F_AP",
             "entity_id": "E_AP_NET", "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary"}},
            {"alias_id": "A_AP2", "family_id": "F_AP",
             "entity_id": "E_AP_WF", "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary"}},
        ],
    })


@pytest.fixture(scope="module")
def confident_snap():
    """Both senses well above the resolve threshold, and tied.

    The calibrator is built directly rather than fitted: the point is the
    decision logic, and a fixture that has to be lucky about scores tests
    the luck instead. seal=False because the calibrator is part of the
    sealed identity.
    """
    snap = compile_snapshot(_two_sense_glossary(), seal=False)
    snap.calibrator = TunedCalibrator(
        platt_a=8.0, platt_b=0.0, alpha=0.1,
        group_quantiles={}, global_quantile=1.0, fallback_quantile=1.0,
        group_counts={}, n_min=1)
    return snap


TEXT = "AP 확인 부탁드립니다"


def _ap(resp):
    return next(m for m in resp["mentions"] if m["surface"] == "AP")


@pytest.mark.parametrize("limit", [1, 2, 3, 10, 100])
def test_the_decision_is_the_same_at_every_display_limit(confident_snap, limit):
    m = _ap(resolve(confident_snap, TEXT, mode="commit",
                    options={"max_prediction_set": limit}))
    assert m["link_decision"] == "AMBIGUOUS"
    assert "resolved_entity" not in m


def test_a_limit_of_one_still_hides_the_second_sense(confident_snap):
    # the option must still do its job — this is not a fix by ignoring it
    m = _ap(resolve(confident_snap, TEXT, mode="commit",
                    options={"max_prediction_set": 1}))
    members = [x for x in m["prediction_set"]["members"]
               if x.get("kind") == "ENTITY"]
    assert len(members) == 1
    assert m["prediction_set"]["truncated"] is True
    assert m["prediction_set"]["coverage_valid"] is False


def test_the_full_set_is_two_tied_senses(confident_snap):
    m = _ap(resolve(confident_snap, TEXT, mode="commit",
                    options={"max_prediction_set": 10}))
    members = [x for x in m["prediction_set"]["members"]
               if x.get("kind") == "ENTITY"]
    assert len(members) == 2
    assert members[0]["calibrated_probability"] == \
           members[1]["calibrated_probability"]


def test_a_genuine_singleton_still_commits(confident_snap):
    # the margin rule must still fire when there really is one sense: a fix
    # that made everything AMBIGUOUS would pass the test above and be useless
    single = compile_snapshot(load_glossary({
        "glossary_id": "t", "version": "1", "schema_version": "3",
        "entities": [{"entity_id": "E_ONLY", "canonical": "Access Point",
                      "description": "wireless network device"}],
        "alias_families": [{"family_id": "F_AP", "representative": "AP",
                            "normalization_profile": "latin_acronym"}],
        "alias_bindings": [
            {"alias_id": "A_AP1", "family_id": "F_AP", "entity_id": "E_ONLY",
             "surface": "AP",
             "boundary_policy": {"left": "latin_token_boundary"}}],
    }), seal=False)
    single.calibrator = confident_snap.calibrator
    m = _ap(resolve(single, TEXT, mode="commit"))
    assert m["link_decision"] == "RESOLVED"
    assert m["resolved_entity"]["entity_id"] == "E_ONLY"


def test_the_resolved_entity_never_depends_on_the_limit(confident_snap):
    # the sharpest form of the bug: which entity you get back depended on a
    # display option, through the sort order of a list that had been cut
    seen = set()
    for limit in (1, 2, 5, 10):
        m = _ap(resolve(confident_snap, TEXT, mode="commit",
                        options={"max_prediction_set": limit}))
        seen.add((m["link_decision"],
                  (m.get("resolved_entity") or {}).get("entity_id")))
    assert len(seen) == 1, seen
