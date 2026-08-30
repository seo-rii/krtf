"""Immutable runtime snapshot, compile and atomic activation (spec §11).

A snapshot bundles glossary + indexes + morphology + policies behind a single
``snapshot_id`` (INV-006). Activation is atomic per tenant: the registry swaps
the active pointer only after validation + conformance pass; failures leave
the previous snapshot untouched (INV-014, §11.4).

Deviation from the production spec: artifacts are in-memory objects with a
hashed manifest instead of mmap ``.bin`` files (REQ-MEM-001 is Rust-core
scope).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from threading import Lock

from .abbrev import AbbrevAligner
from .candidates import CandidateBudget
from .doclocal import DocLocalDetector
from .errors import KtrfApiError
from .fuzzy import FuzzyIndex
from .glossary import (Glossary, GlossaryError, glossary_to_dict, has_errors,
                       validate_glossary)
from .matcher import ExactIndex
from .segmentation import ResolutionGuard
from .morphology import DEFAULT_CHAIN_DEPTH, PARTICLES, PREFIXES, SUFFIXES, ParticleFST

COMPATIBILITY_ID = "ktrf-py-v1"
NORMALIZER_VERSION = "nrm-1"


@dataclass
class RuntimePolicy:
    sync_max_input_bytes: int = 65536  # §27.2, REQ-API-003
    max_total_mention_proposals: int = 512
    max_fuzzy_windows: int = 96  # counts core queries, not raw tokens
    # typed decompositions considered per token (VARIANTS_PLAN M1). 1 keeps
    # the pre-M1 behaviour of querying the raw token only, and is the A/B
    # control; higher values trade Pass-1 latency for variant recall.
    max_segmentation_paths: int = 4
    tau_dense: float = 0.75  # Pass 2 trigger threshold (§21.6)
    max_dense_queries_per_request: int = 16  # §31.1
    dense_top_k: int = 8
    max_cross_encoder_pairs: int = 256  # §31.1
    max_rerank_candidates: int = 8  # per mention (§22.4 conditional exec)
    resolve_threshold: float = 0.70  # §25.6 commit rules
    margin_threshold: float = 0.25
    set_confidence: float = 0.95  # target 1-alpha exposed in responses
    prediction_set_min_p: float = 0.15
    candidate_budget: CandidateBudget = field(default_factory=CandidateBudget)


@dataclass
class Snapshot:
    snapshot_id: str
    tenant_id: str
    glossary: Glossary
    exact_index: ExactIndex
    fuzzy_index: FuzzyIndex
    abbrev: AbbrevAligner
    doclocal: DocLocalDetector
    fst: ParticleFST
    policy: RuntimePolicy
    guard: ResolutionGuard
    manifest: dict
    diagnostics: list = field(default_factory=list)
    calibrator: object | None = None  # TunedCalibrator once finetuned (§48.3)
    dense: object | None = None  # DenseArtifacts (V2 bi-encoder, §22.3)
    reranker: object | None = None  # cross-encoder backend (§22.3)
    fusion: object | None = None  # learned FusionModel (§23, V2)

    @property
    def glossary_version(self) -> str:
        return self.glossary.version


def _hash(obj) -> str:
    """Full SHA-256 over a canonical JSON serialization.

    Content-identity hashes are never truncated: a snapshot's semantics are
    exactly what these digests cover, so any two artifacts that behave
    differently must hash differently (§11.2, INV-015).
    """
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def compute_snapshot_id(manifest: dict) -> str:
    """Deterministic snapshot identity over the *complete* manifest.

    Excludes only ``snapshot_id`` itself and ``tenant_id`` (deployment
    binding, not content). 128-bit prefix of SHA-256 — collision-safe for
    any realistic artifact population, unlike the previous 32-bit id.
    """
    content = {k: v for k, v in manifest.items()
               if k not in ("snapshot_id", "tenant_id")}
    return "snap-" + hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False,
                   default=str).encode()
    ).hexdigest()[:32]


def _guard_hash(guard: ResolutionGuard) -> str:
    return _hash(dataclasses.asdict(guard))


def _morphology_hash() -> str:
    return _hash({"particles": sorted(PARTICLES), "suffixes": sorted(SUFFIXES),
                  "prefixes": sorted(PREFIXES), "depth": DEFAULT_CHAIN_DEPTH})


def compile_snapshot(
    glossary: Glossary,
    tenant_id: str = "default",
    policy: RuntimePolicy | None = None,
    strict: bool = True,
    run_conformance: bool = True,
    encoder=None,
    reranker=None,
    guard: ResolutionGuard | None = None,
) -> Snapshot:
    """Compile a glossary into an immutable snapshot (§11.4 steps 1-5).

    Validation errors abort the compile in strict mode; the conformance
    fixture suite (§14.8) must pass 100% or compilation fails
    (REQ-NRM-005 — conformance failure is an activation blocker).
    """
    diagnostics = validate_glossary(glossary)
    if strict and has_errors(diagnostics):
        raise GlossaryError(
            f"strict validation failed: {[d for d in diagnostics if d.severity == 'error']}"
        )

    policy = policy or RuntimePolicy()
    guard = guard or ResolutionGuard()
    fst = ParticleFST()
    exact_index = ExactIndex(glossary, fst)
    snapshot = Snapshot(
        snapshot_id="",
        tenant_id=tenant_id,
        glossary=glossary,
        exact_index=exact_index,
        fuzzy_index=FuzzyIndex(glossary),
        abbrev=AbbrevAligner(glossary),
        doclocal=DocLocalDetector(exact_index),
        fst=fst,
        policy=policy,
        guard=guard,
        manifest={},
        diagnostics=diagnostics,
    )

    # Full-content identity (§11.2): the digest covers the complete glossary
    # serialization — descriptions, domains, normalization profiles, binding
    # kinds, boundary/fuzzy policies, relations — not just IDs and surfaces.
    # Any semantically meaningful edit therefore changes the snapshot_id.
    glossary_hash = _hash(glossary_to_dict(glossary))
    policy_hash = _hash(dataclasses.asdict(policy))
    manifest = {
        "schema_version": glossary.schema_version,
        "glossary_id": glossary.glossary_id,
        "glossary_version": glossary.version,
        "compatibility_id": COMPATIBILITY_ID,
        "normalizer_hash": _hash(NORMALIZER_VERSION),
        "morphology_rules_hash": _morphology_hash(),
        # invariant 6: a guard change changes resolution, so it changes
        # snapshot identity too
        "segmentation_guard_hash": _guard_hash(guard),
        "entities_hash": glossary_hash,
        "policy_hash": policy_hash,
        "calibrator_hash": None,
        # V2 dense retrieval artifact identity (§11.2); null = Level A-only
        "entity_encoder_hash": None,
        "vector_dimension": None,
        "index_type": None,
        "reranker_id": None,
        "fusion_hash": None,
        "conformance_fixtures_hash": None,
        "conformance": None,
    }
    if encoder is not None:
        from .dense import DenseArtifacts

        snapshot.dense = DenseArtifacts.build(glossary, encoder)
        manifest["entity_encoder_hash"] = encoder.encoder_id
        manifest["vector_dimension"] = snapshot.dense.index.dim
        manifest["index_type"] = "flat_ip"
    if reranker is not None:
        snapshot.reranker = reranker
        manifest["reranker_id"] = reranker.reranker_id
    snapshot.manifest = manifest

    if run_conformance:
        from .conformance import generate_fixtures, run_fixtures

        fixtures = generate_fixtures(glossary)
        report = run_fixtures(snapshot, fixtures)
        manifest["conformance_fixtures_hash"] = _hash(
            [f.text for f in fixtures])
        manifest["conformance"] = {
            "total": report.total, "passed": report.passed,
            "failed": report.failed,
        }
        if report.failed:
            raise GlossaryError(
                f"conformance suite failed: {report.failed}/{report.total} "
                f"fixtures failed; first: {report.failures[:3]}"
            )
    # identity is assigned only after every manifest field — including the
    # conformance record — is final (§11.2: the id names the whole artifact)
    snapshot.snapshot_id = compute_snapshot_id(manifest)
    return snapshot


class SnapshotRegistry:
    """Per-tenant active-snapshot registry with atomic activation (§11.4)."""

    def __init__(self):
        self._active: dict[str, Snapshot] = {}
        self._lock = Lock()

    def activate(self, snapshot: Snapshot,
                 allow_unverified: bool = False) -> None:
        """Atomic swap; only pre-validated snapshots reach this point.

        Compatibility mismatch refuses activation (INV-015). A snapshot with
        no conformance record — compiled with ``run_conformance=False`` —
        is refused too (§11.4 step 3: conformance is an activation gate,
        not an optional extra); ``allow_unverified=True`` is an explicit,
        test-only escape hatch. The previous snapshot always survives
        failures (INV-014).
        """
        if snapshot.manifest.get("compatibility_id") != COMPATIBILITY_ID:
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE",
                f"compatibility mismatch: {snapshot.manifest.get('compatibility_id')}",
            )
        conf = snapshot.manifest.get("conformance")
        if conf is None and not allow_unverified:
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE",
                "snapshot has no conformance record; compile with "
                "run_conformance=True (or pass allow_unverified=True in "
                "tests) — §11.4 step 3",
            )
        if conf is not None and conf.get("failed"):
            raise KtrfApiError(
                "SNAPSHOT_UNAVAILABLE", "conformance failures block activation")
        with self._lock:
            self._active[snapshot.tenant_id] = snapshot

    def get_active(self, tenant_id: str) -> Snapshot:
        snap = self._active.get(tenant_id)
        if snap is None:
            raise KtrfApiError("GLOSSARY_NOT_FOUND",
                               f"no active snapshot for tenant {tenant_id!r}")
        return snap

    def resolve_tenant(self, tenant_id: str, glossary_id: str | None,
                       expected_version: str | None,
                       version_policy: str = "strict") -> Snapshot:
        """§12.1 + §27.1: tenant from auth context; glossary must be in scope."""
        snap = self.get_active(tenant_id)
        if glossary_id is not None and glossary_id != snap.glossary.glossary_id:
            raise KtrfApiError(
                "FORBIDDEN_GLOSSARY",
                f"glossary {glossary_id!r} not in tenant scope",
            )
        if expected_version and version_policy == "strict":
            if expected_version != snap.glossary_version:
                raise KtrfApiError(
                    "GLOSSARY_VERSION_MISMATCH",
                    f"expected {expected_version} but active is {snap.glossary_version}",
                    details={"active_version": snap.glossary_version},
                )
        return snap
