"""Snapshot save/load and the finetune entry point (spec §11, §47.3, §48.3).

Bundle layout (Python analog of §11.1's ``compiled-glossary/``)::

    <dir>/
    ├── manifest.json        # hashes + conformance result (§11.2)
    ├── glossary.yaml        # source of truth for deterministic recompile
    ├── policy.json          # RuntimePolicy + CandidateBudget
    ├── guard.json           # ResolutionGuard configuration
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
import json
from pathlib import Path

import yaml

from .calibration import (
    TunedCalibrator,
    TrainingExample,
    derive_training_examples,
    fit_calibrator,
    partition_examples,
    InsufficientCalibrationData,
)
from .candidates import CandidateBudget
from .corrections import CorrectionStore
from .errors import KtrfApiError
from .glossary import glossary_to_dict, load_glossary
from .immutable import thaw
from .snapshot import (RuntimePolicy, Snapshot, compile_snapshot,
                       compute_snapshot_id, _hash)
from .segmentation import ResolutionGuard


def _policy_to_dict(p: RuntimePolicy) -> dict:
    d = dataclasses.asdict(p)
    return d


def _policy_from_dict(d: dict) -> RuntimePolicy:
    budget = CandidateBudget(**d.pop("candidate_budget"))
    return RuntimePolicy(candidate_budget=budget, **d)


def save_snapshot(snapshot: Snapshot, out_dir: str | Path) -> Path:
    """Persist a compiled snapshot as an artifact bundle."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    gdict = thaw(glossary_to_dict(snapshot.glossary))
    (out / "glossary.yaml").write_text(
        yaml.safe_dump(gdict, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (out / "policy.json").write_text(
        json.dumps(_policy_to_dict(snapshot.policy), indent=2),
        encoding="utf-8",
    )
    (out / "guard.json").write_text(
        json.dumps(dataclasses.asdict(snapshot.guard), indent=2), encoding="utf-8")
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
        guard_path = d / "guard.json"
        guard = (ResolutionGuard(**json.loads(guard_path.read_text(encoding="utf-8")))
                 if guard_path.exists() else ResolutionGuard())
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise KtrfApiError("SNAPSHOT_UNAVAILABLE",
                           f"unreadable bundle {d}: {e}") from e

    snap = compile_snapshot(
        glossary,
        tenant_id=manifest.get("tenant_id", "default"),
        policy=policy,
        guard=guard,
        run_conformance=run_conformance,
    )
    # content-hash verification against the stored manifest (§47.3): the
    # digests are recomputed from the loaded glossary/policy, so tampering
    # with glossary.yaml (any field, descriptions included) or policy.json
    # produces a mismatch and the bundle is refused
    for key in ("compatibility_id", "resolver_semantics_version", "normalizer_hash",
                "morphology_rules_hash", "segmentation_guard_hash", "entities_hash", "policy_hash"):
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
    cal_path = d / "calibrator.json"
    if cal_path.exists():
        cal_dict = json.loads(cal_path.read_text(encoding="utf-8"))
        if manifest.get("calibrator_hash") != _hash(cal_dict):
            raise KtrfApiError("SNAPSHOT_UNAVAILABLE",
                               "bundle verification failed: calibrator_hash mismatch")
        snap = dataclasses.replace(snap, calibrator=TunedCalibrator.from_dict(cal_dict))
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

        dense = DenseArtifacts(
            encoder,
            VectorIndex.from_dict(
                json.loads(vec_path.read_text(encoding="utf-8"))),
        )
        snap = dataclasses.replace(snap, runtime=dataclasses.replace(snap.runtime, dense=dense))
    fus_path = d / "fusion.json"
    if fus_path.exists():
        from .fusion import FusionModel

        fus_dict = json.loads(fus_path.read_text(encoding="utf-8"))
        if manifest.get("fusion_hash") != _hash(fus_dict):
            raise KtrfApiError("SNAPSHOT_UNAVAILABLE",
                               "bundle verification failed: fusion_hash mismatch")
        snap = dataclasses.replace(snap, fusion=FusionModel.from_dict(fus_dict))
    if manifest.get("reranker_id"):
        if reranker is None or reranker.reranker_id != manifest["reranker_id"]:
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE",
                f"bundle expects reranker {manifest['reranker_id']!r}",
            )
        snap = dataclasses.replace(snap, runtime=dataclasses.replace(snap.runtime, reranker=reranker))
    # keep the persisted identity and conformance record
    return dataclasses.replace(snap, manifest=manifest,
                               snapshot_id=manifest.get("snapshot_id", snap.snapshot_id))


# ---------------------------------------------------------------------------
# Finetuning (§48.3 adaptation loop)
# ---------------------------------------------------------------------------


def _fusion_rows(correction: dict) -> list[tuple[dict, TrainingExample]]:
    """Feature-bearing candidate rows retaining their correction provenance."""
    members = [m for m in (correction.get("mention_state") or {}).get(
        "prediction_set", {}).get("members", [])
        if m.get("kind", "ENTITY") == "ENTITY" and m.get("ranking_score") is not None]
    pairs = derive_training_examples(correction)
    return [(m["features"], e) for m, e in zip(members, pairs) if m.get("features")]


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
    fusion_rows: list[tuple[dict, TrainingExample]] = []
    for c in accepted:
        pairs = derive_training_examples(c)
        examples.extend(pairs * c.get("weight", 1))
        if fit_fusion_model:
            fusion_rows.extend(_fusion_rows(c) * c.get("weight", 1))

    fusion = snapshot.fusion
    manifest = dict(snapshot.manifest)
    if fit_fusion_model:
        # learned fusion (§23, V2) — needs feature-bearing mention states
        # (responses produced with options.return_features)
        from .fusion import fit_fusion

        if extra_examples:
            raise ValueError("fusion refit needs source features; extra_examples contain scores only")
        fit_rows, _ = partition_examples([e for _, e in fusion_rows])
        fitting_ids = {id(e) for e in fit_rows}
        fusion = fit_fusion([(f, e.label) for f, e in fusion_rows if id(e) in fitting_ids])
        manifest["fusion_hash"] = _hash(fusion.to_dict())
        # the ranking_score scale changed: refit calibration on the fusion
        # model's own outputs so Platt + conformal stay consistent
        examples = [
            dataclasses.replace(e, ranking_score=fusion.predict(f))
            for f, e in fusion_rows
        ]
    try:
        calibrator = fit_calibrator(examples, alpha=alpha, n_min=n_min)
    except InsufficientCalibrationData as exc:
        raise KtrfApiError("INVALID_REQUEST", str(exc),
                          details={"calibration_status": exc.calibration_status}) from exc

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
