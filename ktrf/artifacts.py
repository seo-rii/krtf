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
import hashlib
import json
from pathlib import Path

import yaml

from .calibration import (
    TunedCalibrator,
    TrainingExample,
    derive_training_examples,
    fit_calibrator,
)
from .candidates import CandidateBudget
from .corrections import CorrectionStore
from .errors import KtrfApiError
from .glossary import glossary_to_dict, load_glossary
from .snapshot import RuntimePolicy, Snapshot, compile_snapshot, _hash


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
    gdict = glossary_to_dict(snapshot.glossary)
    (out / "glossary.yaml").write_text(
        yaml.safe_dump(gdict, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (out / "policy.json").write_text(
        json.dumps(_policy_to_dict(snapshot.policy), indent=2),
        encoding="utf-8",
    )
    manifest = dict(snapshot.manifest)
    if snapshot.calibrator is not None:
        cal = snapshot.calibrator.to_dict()
        (out / "calibrator.json").write_text(json.dumps(cal, indent=2),
                                             encoding="utf-8")
        manifest["calibrator_hash"] = _hash(cal)
    manifest["snapshot_id"] = snapshot.snapshot_id
    manifest["tenant_id"] = snapshot.tenant_id
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_snapshot(bundle_dir: str | Path, run_conformance: bool = False) -> Snapshot:
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

    snap = compile_snapshot(
        glossary,
        tenant_id=manifest.get("tenant_id", "default"),
        policy=policy,
        run_conformance=run_conformance,
    )
    # content-hash verification against the stored manifest (§47.3)
    for key in ("compatibility_id", "normalizer_hash",
                "morphology_rules_hash", "entities_hash"):
        if snap.manifest.get(key) != manifest.get(key):
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE",
                f"bundle verification failed: {key} mismatch "
                f"(stored {manifest.get(key)}, recomputed {snap.manifest.get(key)})",
            )
    cal_path = d / "calibrator.json"
    if cal_path.exists():
        cal_dict = json.loads(cal_path.read_text(encoding="utf-8"))
        if manifest.get("calibrator_hash") != _hash(cal_dict):
            raise KtrfApiError("SNAPSHOT_UNAVAILABLE",
                               "bundle verification failed: calibrator_hash mismatch")
        snap.calibrator = TunedCalibrator.from_dict(cal_dict)
    # keep the persisted identity and conformance record
    snap.manifest = manifest
    snap.snapshot_id = manifest.get("snapshot_id", snap.snapshot_id)
    return snap


# ---------------------------------------------------------------------------
# Finetuning (§48.3 adaptation loop)
# ---------------------------------------------------------------------------


def finetune(
    snapshot: Snapshot,
    store: CorrectionStore,
    alpha: float = 0.05,
    n_min: int = 500,
    golden_check=None,
    extra_examples: list[TrainingExample] | None = None,
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
    for c in accepted:
        pairs = derive_training_examples(c)
        examples.extend(pairs * c.get("weight", 1))
    calibrator = fit_calibrator(examples, alpha=alpha, n_min=n_min)

    manifest = dict(snapshot.manifest)
    manifest["calibrator_hash"] = _hash(calibrator.to_dict())
    candidate = dataclasses.replace(
        snapshot,
        calibrator=calibrator,
        manifest=manifest,
        snapshot_id="snap-" + hashlib.sha256(
            json.dumps(manifest, sort_keys=True, default=str).encode()
        ).hexdigest()[:8],
    )
    if golden_check is not None and not golden_check(candidate):
        raise KtrfApiError(
            "SNAPSHOT_UNAVAILABLE",
            "finetune rejected: golden-set regression failed (§48.3)",
        )
    return candidate
