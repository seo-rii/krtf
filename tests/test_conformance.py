"""Conformance suite tests (spec §14.8, §45.2, §45.3).

REQ-LVL-001/002, REQ-NRM-003/004/006. This suite doubles as the
property-based test of §45.2: variants are generated from the glossary and
catalogs, and the exact path must retain the gold entity at the exact span.
"""

import pytest

from ktrf.conformance import generate_fixtures, run_fixtures
from ktrf.glossary import load_glossary
from ktrf.snapshot import compile_snapshot


@pytest.fixture(scope="module")
def glossary():
    return load_glossary("examples/demo_glossary.yaml")


@pytest.fixture(scope="module")
def snap(glossary):
    return compile_snapshot(glossary, run_conformance=False)


def test_demo_glossary_conformance_100(glossary, snap):
    # REQ-LVL-002/REQ-NRM-005: catalog fixtures pass 100%
    fixtures = generate_fixtures(glossary)
    report = run_fixtures(snap, fixtures)
    assert report.total > 300
    assert report.failed == 0, report.failures[:5]


def test_fixture_generation_deterministic(glossary):
    # REQ-NRM-004: fixtures derive deterministically from glossary + catalog
    a = generate_fixtures(glossary)
    b = generate_fixtures(glossary)
    assert a == b


def test_single_particle_sweep_included(glossary):
    # REQ-NRM-006: full single-particle sweep for each eligible binding
    from ktrf.morphology import PARTICLES, _constraint_ok

    fixtures = generate_fixtures(glossary)
    kepco_t06 = {f.text for f in fixtures
                 if f.alias_id == "KEPCO_KR" and f.transform_id == "T-06"}
    for particle, constraint in PARTICLES.items():
        if _constraint_ok(constraint, "전") is not False:
            assert ("한전" + particle) in kepco_t06, particle
    # depth-2 chain representatives present
    assert "한전에서도" in kepco_t06
    assert "한전까지는" in kepco_t06


def test_fixtures_cover_catalog_transforms(glossary):
    # §14.7 transform classes exercised by the demo glossary
    fixtures = generate_fixtures(glossary)
    tids = {f.transform_id for f in fixtures}
    assert {"T-01", "T-02", "T-03", "T-04", "T-05", "T-06", "T-07",
            "T-08", "T-09", "T-10", "T-11"} <= tids


def test_out_of_catalog_variants_not_guaranteed(snap):
    # REQ-NRM-003: typos are Level B, not part of the exact-path guarantee
    from ktrf.normalization import build_canonical_stream

    stream = build_canonical_stream("한젅에서")  # jamo typo
    assert not [m for m in snap.exact_index.find(stream)
                if m.binding.alias_id == "KEPCO_KR"]
