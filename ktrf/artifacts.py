"""Snapshot save/load and the finetune entry point (spec §11, §47.3, §48.3).

Bundle layout (Python analog of §11.1's ``compiled-glossary/``)::

    <dir>/
    ├── manifest.json        # hashes + conformance result (§11.2)
    ├── glossary.yaml        # source of truth for deterministic recompile
    ├── policy.json          # RuntimePolicy + CandidateBudget
    └── calibrator.json      # optional TunedCalibrator artifact

Loading recompiles the indexes deterministically from ``glossary.yaml`` and
verifies the recomputed content hashes against the stored manifest — a
mismatch (tampered or incompatible bundle) refuses to load (§47.3, INV-015).

``finetune`` implements the §48.3 adaptation loop for V1: ACCEPTED
corrections → fitted tenant calibrator → golden-set regression → a *new*
immutable snapshot (the current one is never mutated; activation stays an
explicit registry step, §11.4).
"""

from __future__ import annotations

import dataclasses
import os
import itertools
import shutil
import json
from pathlib import Path

import yaml

from .calibration import (
    TunedCalibrator,
    TrainingExample,
    derive_training_examples,
    fit_with_folds,
    split_examples,
)
from .candidates import CandidateBudget
from .corrections import CorrectionStore
from .errors import KtrfApiError
from .glossary import glossary_to_dict, load_glossary
from .segmentation import ResolutionGuard
from .snapshot import (RuntimePolicy, Snapshot, compile_snapshot,
                       compute_snapshot_id, _hash)


def _policy_to_dict(p: RuntimePolicy) -> dict:
    d = dataclasses.asdict(p)
    return d


def _policy_from_dict(d: dict) -> RuntimePolicy:
    budget = CandidateBudget(**d.pop("candidate_budget"))
    return RuntimePolicy(candidate_budget=budget, **d)


_save_seq = itertools.count(1)


def _publish(staging: Path, out: Path) -> None:
    """Put a finished bundle in place of whatever is there.

    Writing straight into the destination meant a failure partway through a
    re-save left the directory holding the new glossary beside the old
    manifest — a bundle that verified against neither and could no longer be
    loaded at all. The previous good bundle was destroyed by an interrupted
    attempt to replace it.

    A directory rename is the closest thing to atomic that a plain filesystem
    offers here. The old bundle is moved aside first (Windows will not replace
    a directory that exists), and it is only deleted once the new one is in
    place; if the second rename fails, the old one goes back. The residual
    window is between the two renames, and it is not zero — a reader arriving
    in it finds no bundle rather than a broken one, which is the failure worth
    having.
    """
    backup = None
    if out.exists():
        backup = out.parent / f".{out.name}.replaced-{os.getpid()}-{next(_save_seq)}"
        shutil.rmtree(backup, ignore_errors=True)
        os.replace(out, backup)
    try:
        os.replace(staging, out)
    except BaseException:
        if backup is not None:
            os.replace(backup, out)      # the old bundle is still the truth
        raise
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)


def save_snapshot(snapshot: Snapshot, out_dir: str | Path) -> Path:
    """Persist a compiled snapshot as an artifact bundle.

    The bundle is built in a staging directory and published by rename, so a
    write that fails halfway leaves the previous bundle exactly as it was.
    """
    out = Path(out_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = out.parent / f".{out.name}.staging-{os.getpid()}-{next(_save_seq)}"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        _write_bundle(snapshot, staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    _publish(staging, out)
    return out


def _write_bundle(snapshot: Snapshot, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    gdict = glossary_to_dict(snapshot.glossary)
    (out / "glossary.yaml").write_text(
        yaml.safe_dump(gdict, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (out / "policy.json").write_text(
        json.dumps(_policy_to_dict(snapshot.policy), indent=2),
        encoding="utf-8",
    )
    # the guard changes resolution and is hashed into the manifest, so it
    # has to travel with the bundle; without it load recompiled the default
    # and the bundle advertised a guard it was not using
    (out / "guard.json").write_text(
        json.dumps(dataclasses.asdict(snapshot.guard), indent=2),
        encoding="utf-8",
    )
    # A bundle is the snapshot, not the union of every snapshot ever written
    # here. That used to need an explicit unlink of each optional artifact a
    # previous save might have left; building in an empty staging directory
    # gives it for free, and gives it for files nobody remembered to list.
    manifest = dict(snapshot.manifest)
    if snapshot.calibrator is not None:
        cal = snapshot.calibrator.to_dict()
        (out / "calibrator.json").write_text(json.dumps(cal, indent=2),
                                             encoding="utf-8")
        manifest["calibrator_hash"] = _hash(cal)
    if snapshot.dense is not None:
        vec = snapshot.dense.index.to_dict()
        (out / "entity-vectors.json").write_text(json.dumps(vec),
                                                 encoding="utf-8")
        manifest["entity_encoder_hash"] = snapshot.dense.encoder_id
        # the encoder id names who produced the vectors; it says nothing
        # about what the file now contains. Vectors decide dense retrieval,
        # so they are content-hashed like the calibrator and fusion files.
        manifest["entity_vectors_hash"] = _hash(vec)
        manifest["vector_dimension"] = snapshot.dense.index.dim
        manifest["index_type"] = "flat_ip"
    if snapshot.fusion is not None:
        fus = snapshot.fusion.to_dict()
        (out / "fusion.json").write_text(json.dumps(fus, indent=2),
                                         encoding="utf-8")
        manifest["fusion_hash"] = _hash(fus)
    if snapshot.reranker is not None:
        manifest["reranker_id"] = snapshot.reranker.reranker_id
    # the persisted id always matches the persisted manifest content — if
    # artifacts were attached after compile, the bundle gets the id of what
    # it actually contains (load re-verifies this equation)
    manifest["snapshot_id"] = compute_snapshot_id(manifest)
    manifest["tenant_id"] = snapshot.tenant_id
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_snapshot(bundle_dir: str | Path, run_conformance: bool = False,
                  encoder=None, reranker=None) -> Snapshot:
    """Load a bundle: recompile deterministically, verify manifest hashes.

    Verification failures raise ``SNAPSHOT_UNAVAILABLE`` and nothing is
    activated (§47.3: 검증 실패 artifact는 activation 금지; INV-015).
    By default conformance is not re-run (the manifest carries the compile
    -time result); pass ``run_conformance=True`` to re-verify (§11.4 step 3).
    """
    d = Path(bundle_dir)
    try:
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        glossary = load_glossary(str(d / "glossary.yaml"))
        policy = _policy_from_dict(
            json.loads((d / "policy.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError) as e:
        raise KtrfApiError("SNAPSHOT_UNAVAILABLE",
                           f"unreadable bundle {d}: {e}") from e

    guard_path = d / "guard.json"
    guard = None
    if guard_path.exists():
        try:
            guard = ResolutionGuard(
                **json.loads(guard_path.read_text(encoding="utf-8")))
        except (ValueError, TypeError) as e:
            raise KtrfApiError("SNAPSHOT_UNAVAILABLE",
                               f"unreadable guard in bundle {d}: {e}") from e
    snap = compile_snapshot(
        glossary,
        tenant_id=manifest.get("tenant_id", "default"),
        policy=policy,
        guard=guard,
        run_conformance=run_conformance,
        seal=False,   # the bundle's own identity is restored below, then sealed
    )
    # content-hash verification against the stored manifest (§47.3): the
    # digests are recomputed from the loaded glossary/policy, so tampering
    # with glossary.yaml (any field, descriptions included) or policy.json
    # produces a mismatch and the bundle is refused
    for key in ("compatibility_id", "normalizer_hash",
                "morphology_rules_hash", "entities_hash", "policy_hash",
                "segmentation_guard_hash"):
        if snap.manifest.get(key) != manifest.get(key):
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE",
                f"bundle verification failed: {key} mismatch "
                f"(stored {manifest.get(key)}, recomputed {snap.manifest.get(key)})",
            )
    # the stored id must equal the id recomputed from the stored manifest —
    # a manifest whose snapshot_id was edited (or whose fields no longer
    # match its id) is refused rather than trusted (§47.3)
    if manifest.get("snapshot_id") != compute_snapshot_id(manifest):
        raise KtrfApiError(
            "SNAPSHOT_UNAVAILABLE",
            "bundle verification failed: snapshot_id does not match "
            "manifest content",
        )
    # A manifest entry is a claim about what this bundle contains. Optional
    # artifacts were verified only `if the file exists`, so deleting a
    # declared file took away the check along with its subject: the bundle
    # loaded with calibrator=None while the manifest still said there was
    # one, and the two disagreed silently. Absence is checked against the
    # declaration, not against the directory listing.
    for key, filename in (("calibrator_hash", "calibrator.json"),
                          ("fusion_hash", "fusion.json"),
                          ("entity_vectors_hash", "entity-vectors.json"),
                          ("segmentation_guard_hash", "guard.json")):
        if manifest.get(key) is not None and not (d / filename).exists():
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE",
                f"bundle declares {key} but {filename} is missing; the "
                "manifest describes artifacts the bundle does not have")
    cal_path = d / "calibrator.json"
    if cal_path.exists():
        cal_dict = json.loads(cal_path.read_text(encoding="utf-8"))
        if manifest.get("calibrator_hash") != _hash(cal_dict):
            raise KtrfApiError("SNAPSHOT_UNAVAILABLE",
                               "bundle verification failed: calibrator_hash mismatch")
        snap.calibrator = TunedCalibrator.from_dict(cal_dict)
    vec_path = d / "entity-vectors.json"
    if vec_path.exists():
        # §11.3: vectors are only reusable under the exact same encoder
        if encoder is None:
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE",
                "bundle carries entity vectors; pass the matching encoder "
                f"({manifest.get('entity_encoder_hash')})",
            )
        if encoder.encoder_id != manifest.get("entity_encoder_hash"):
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE",
                f"encoder mismatch: bundle={manifest.get('entity_encoder_hash')} "
                f"given={encoder.encoder_id} (INV-015)",
            )
        from .dense import DenseArtifacts, VectorIndex

        vec_dict = json.loads(vec_path.read_text(encoding="utf-8"))
        stored_vec_hash = manifest.get("entity_vectors_hash")
        if stored_vec_hash is None:
            # a vector file the manifest cannot vouch for is exactly the
            # case this check exists for, so it is refused rather than
            # trusted for being old
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE",
                "bundle carries entity vectors with no entity_vectors_hash "
                "in its manifest; it cannot be verified (§47.3)",
            )
        if stored_vec_hash != _hash(vec_dict):
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE",
                "bundle verification failed: entity_vectors_hash mismatch",
            )
        snap.dense = DenseArtifacts(encoder, VectorIndex.from_dict(vec_dict))
    fus_path = d / "fusion.json"
    if fus_path.exists():
        from .fusion import FusionModel

        fus_dict = json.loads(fus_path.read_text(encoding="utf-8"))
        if manifest.get("fusion_hash") != _hash(fus_dict):
            raise KtrfApiError("SNAPSHOT_UNAVAILABLE",
                               "bundle verification failed: fusion_hash mismatch")
        snap.fusion = FusionModel.from_dict(fus_dict)
    if manifest.get("reranker_id"):
        if reranker is None or reranker.reranker_id != manifest["reranker_id"]:
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE",
                f"bundle expects reranker {manifest['reranker_id']!r}",
            )
        snap.reranker = reranker
    # keep the persisted identity and conformance record
    snap.manifest = manifest
    snap.snapshot_id = manifest.get("snapshot_id", snap.snapshot_id)
    snap.seal()
    return snap


# ---------------------------------------------------------------------------
# Finetuning (§48.3 adaptation loop)
# ---------------------------------------------------------------------------


def _fusion_rows(correction: dict) -> list[tuple[dict, int, str, dict]]:
    """(features, label, calibration_group, groups) rows from one ACCEPTED
    correction whose mention_state members carry feature vectors.

    The group identities travel with the row rather than being recovered by
    position later: fusion rows and calibration rows are filtered by different
    predicates, so the two lists are not index-aligned and never were.
    """
    from .calibration import calibration_group, correction_groups

    state = correction.get("mention_state") or {}
    members = [m for m in state.get("prediction_set", {}).get("members", [])
               if m.get("kind", "ENTITY") == "ENTITY" and m.get("features")]
    ctype = correction.get("correction_type")
    if ctype not in ("WRONG_ENTITY", "SHOULD_BE_RESOLVED") or not members:
        return []
    gold = (correction.get("corrected") or {}).get("entity_id")
    n = len(members)
    groups = correction_groups(correction)
    return [
        (m["features"], int(m.get("entity_id") == gold),
         calibration_group(set(m.get("generation_channels", [])), n),
         dict(groups))
        for m in members
    ]


#: Four folds when a ranker is being trained; three when there is none and the
#: 40% would otherwise sit idle. The locked fold is reserved either way — it is
#: the only data left that no part of the fit has seen.
_FOUR_WAY = {"ranker": 0.4, "platt": 0.2, "conformal": 0.2, "test": 0.2}
_THREE_WAY = {"platt": 0.4, "conformal": 0.4, "test": 0.2}


def _locked_coverage(calibrator, locked: list[TrainingExample],
                     alpha: float) -> dict:
    """Coverage on rows no part of the fit touched.

    The only coverage figure in the system that is measured rather than
    assumed, so it is recorded whether or not it flatters the fit.
    """
    positives = [e for e in locked if e.label == 1]
    covered = sum(
        int(calibrator.in_prediction_set(
            calibrator.calibrate_marginal(e.ranking_score), e.group)[0])
        for e in positives)
    return {
        "n": len(positives),
        "coverage": (round(covered / len(positives), 4) if positives else None),
        "target": round(1.0 - alpha, 4),
        "basis": calibrator.split_basis,
    }


def finetune(
    snapshot: Snapshot,
    store: CorrectionStore,
    alpha: float = 0.05,
    n_min: int = 500,
    golden_check=None,
    extra_examples: list[TrainingExample] | None = None,
    fit_fusion_model: bool = False,
) -> Snapshot:
    """Fit a tenant calibrator from approved corrections; return a NEW snapshot.

    - labels come only from ``store.export_accepted`` (INV-018/REQ-COR-001),
      weighted per verifier kind (REQ-COR-003 — weights repeat examples);
    - the glossary and indexes are untouched (REQ-COR-002): only the
      calibrator artifact changes, mirroring adapter policy (§48.4);
    - ``golden_check(candidate_snapshot) -> bool`` gates the result — a
      failing regression refuses the finetune and leaves the input snapshot
      as-is (§48.3, §41 safeguard);
    - the input snapshot is never mutated; activation of the returned
      snapshot remains an explicit ``SnapshotRegistry.activate`` call.
    """
    accepted = store.export_accepted(snapshot.tenant_id)
    examples: list[TrainingExample] = list(extra_examples or [])
    fusion_rows: list[tuple[dict, int]] = []
    for c in accepted:
        pairs = derive_training_examples(c)
        examples.extend(pairs * c.get("weight", 1))
        if fit_fusion_model:
            fusion_rows.extend(_fusion_rows(c) * c.get("weight", 1))

    fusion = snapshot.fusion
    manifest = dict(snapshot.manifest)
    shares = _THREE_WAY
    if fit_fusion_model:
        # learned fusion (§23, V2) — needs feature-bearing mention states
        # (responses produced with options.return_features)
        from .fusion import fit_fusion

        # §25.2: the ranker gets a fold of its own. Fitting fusion on every
        # row and then calibrating on the fusion's output for those same rows
        # calibrates a model against its own training data; the probabilities
        # come out overconfident, and a conformal quantile measured on the
        # same rows cannot see it.
        shares = _FOUR_WAY
        examples = [TrainingExample(0.0, group, y, groups=dict(g))
                    for _f, y, group, g in fusion_rows]
        split = split_examples(examples, shares=shares)
        fusion = fit_fusion([(fusion_rows[i][0], fusion_rows[i][1])
                             for i in split.folds["ranker"]])
        manifest["fusion_hash"] = _hash(fusion.to_dict())
        # the ranking_score scale changed: re-express every row through the
        # fusion model so Platt and conformal share one scale. Row order and
        # group identities are untouched, so the split below reproduces the
        # same folds and the ranker's own rows stay out of the calibration.
        examples = [
            TrainingExample(fusion.predict(f), group, y, groups=dict(g))
            for f, y, group, g in fusion_rows
        ]
    fitted = fit_with_folds(examples, alpha=alpha, n_min=n_min, shares=shares)
    calibrator = fitted.calibrator
    manifest["calibration_holdout"] = _locked_coverage(
        calibrator, fitted.locked, alpha)

    manifest["calibrator_hash"] = _hash(calibrator.to_dict())
    candidate = dataclasses.replace(
        snapshot,
        calibrator=calibrator,
        fusion=fusion,
        manifest=manifest,
        snapshot_id=compute_snapshot_id(manifest),
    )
    if golden_check is not None and not golden_check(candidate):
        raise KtrfApiError(
            "SNAPSHOT_UNAVAILABLE",
            "finetune rejected: golden-set regression failed (§48.3)",
        )
    return candidate
