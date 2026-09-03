"""A bundle must reload as the snapshot it was saved from (§47.3, INV-015).

Both defects here came from an external review and reproduced against the
shipped code. Neither could be caught by a roundtrip test that only compares
snapshot ids — the ids matched while the behaviour did not.
"""

import dataclasses
import json

import pytest

from ktrf.artifacts import load_snapshot, save_snapshot
from ktrf.errors import KtrfApiError
from ktrf.glossary import load_glossary
from ktrf.segmentation import ResolutionGuard
from ktrf.snapshot import compile_snapshot

GLOSSARY = "examples/realorg_glossary.yaml"


@pytest.fixture(scope="module")
def glossary():
    return load_glossary(GLOSSARY)


def test_a_custom_guard_survives_the_roundtrip(glossary, tmp_path):
    """The guard was never written to the bundle, so load recompiled the
    default one — then `snap.manifest = manifest` restored the stored hash,
    leaving a snapshot that advertised a guard it was not using. Same
    snapshot_id, different resolution.
    """
    guard = ResolutionGuard(stripped_tail_factor=0.123,
                            ungrammatical_factor=0.456)
    snap = compile_snapshot(glossary, guard=guard)
    save_snapshot(snap, tmp_path / "bundle")
    back = load_snapshot(tmp_path / "bundle")

    assert back.snapshot_id == snap.snapshot_id
    assert dataclasses.asdict(back.guard) == dataclasses.asdict(guard)
    assert back.manifest["segmentation_guard_hash"] == \
        snap.manifest["segmentation_guard_hash"]


def test_a_tampered_guard_is_refused(glossary, tmp_path):
    """The guard hash is now verified like every other content hash, so
    editing guard.json cannot pass as the bundle it claims to be."""
    snap = compile_snapshot(glossary,
                            guard=ResolutionGuard(stripped_tail_factor=0.5))
    bundle = tmp_path / "bundle"
    save_snapshot(snap, bundle)
    tampered = json.loads((bundle / "guard.json").read_text(encoding="utf-8"))
    tampered["stripped_tail_factor"] = 0.99
    (bundle / "guard.json").write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(KtrfApiError) as excinfo:
        load_snapshot(bundle)
    assert "segmentation_guard_hash" in str(excinfo.value)


def test_a_bundle_missing_its_guard_is_refused_not_defaulted(glossary,
                                                             tmp_path):
    """Deleting guard.json makes load recompile the default — which is the
    old silent-downgrade path, so it must now fail instead."""
    snap = compile_snapshot(glossary,
                            guard=ResolutionGuard(stripped_tail_factor=0.5))
    bundle = tmp_path / "bundle"
    save_snapshot(snap, bundle)
    (bundle / "guard.json").unlink()

    with pytest.raises(KtrfApiError):
        load_snapshot(bundle)


def test_a_default_guard_bundle_still_loads(glossary, tmp_path):
    snap = compile_snapshot(glossary)
    save_snapshot(snap, tmp_path / "bundle")
    back = load_snapshot(tmp_path / "bundle")
    assert back.snapshot_id == snap.snapshot_id
    assert dataclasses.asdict(back.guard) == dataclasses.asdict(
        ResolutionGuard())


def test_saving_over_a_bundle_clears_artifacts_that_no_longer_apply(
        glossary, tmp_path):
    """Save wrote optional artifacts only when present, so one left by an
    earlier save stayed in the directory and load picked it up. A bundle is
    the snapshot, not the union of every snapshot written to that path."""
    bundle = tmp_path / "bundle"
    snap = compile_snapshot(glossary)
    save_snapshot(snap, bundle)
    (bundle / "entity-vectors.json").write_text('{"stale": true}',
                                                encoding="utf-8")
    (bundle / "calibrator.json").write_text('{"stale": true}',
                                            encoding="utf-8")

    save_snapshot(snap, bundle)

    assert not (bundle / "entity-vectors.json").exists()
    assert not (bundle / "calibrator.json").exists()
    load_snapshot(bundle)   # and the bundle is loadable, not half-refused


# ---------------------------------------------------------------------------
# vectors decide retrieval, so the manifest has to vouch for them
# ---------------------------------------------------------------------------


class _StubEncoder:
    encoder_id = "stub-enc-1"

    def encode_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def encode_passages(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def encode_query(self, text):
        return [1.0, 0.0]


def _dense_bundle(glossary, tmp_path):
    from ktrf.dense import DenseArtifacts, VectorIndex

    snap = compile_snapshot(glossary, seal=False)
    snap.dense = DenseArtifacts(
        _StubEncoder(),
        VectorIndex(["ORG_KEPCO", "ORG_FSS"], [[1.0, 0.0], [0.0, 1.0]]))
    bundle = tmp_path / "bundle"
    save_snapshot(snap, bundle)
    return bundle


def test_edited_entity_vectors_are_refused(glossary, tmp_path):
    """`entity_encoder_hash` names who produced the vectors and says nothing
    about what the file holds, so repointing one entity's vector at another
    entity loaded clean — silently changing dense retrieval under an
    unchanged snapshot id."""
    bundle = _dense_bundle(glossary, tmp_path)
    load_snapshot(bundle, encoder=_StubEncoder())     # clean bundle loads

    vectors = json.loads((bundle / "entity-vectors.json").read_text(
        encoding="utf-8"))
    vectors["vectors"][0] = [0.0, 1.0]                # KEPCO -> FSS's vector
    (bundle / "entity-vectors.json").write_text(json.dumps(vectors),
                                                encoding="utf-8")

    with pytest.raises(KtrfApiError) as excinfo:
        load_snapshot(bundle, encoder=_StubEncoder())
    assert "entity_vectors_hash" in str(excinfo.value)


def test_vectors_with_no_hash_in_the_manifest_are_refused(glossary, tmp_path):
    """An unverifiable vector file is the case the check exists for, so it
    is refused rather than trusted for being old."""
    bundle = _dense_bundle(glossary, tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text(
        encoding="utf-8"))
    manifest.pop("entity_vectors_hash")
    (bundle / "manifest.json").write_text(json.dumps(manifest),
                                          encoding="utf-8")

    with pytest.raises(KtrfApiError):
        load_snapshot(bundle, encoder=_StubEncoder())


def test_the_snapshot_id_covers_the_vectors(glossary, tmp_path):
    from ktrf.dense import DenseArtifacts, VectorIndex

    def _id_for(vectors):
        snap = compile_snapshot(glossary, seal=False)
        snap.dense = DenseArtifacts(
            _StubEncoder(),
            VectorIndex(["ORG_KEPCO", "ORG_FSS"], vectors))
        out = tmp_path / f"b{abs(hash(str(vectors)))}"
        save_snapshot(snap, out)
        return json.loads((out / "manifest.json").read_text(
            encoding="utf-8"))["snapshot_id"]

    assert _id_for([[1.0, 0.0], [0.0, 1.0]]) != _id_for([[0.0, 1.0],
                                                         [1.0, 0.0]])
