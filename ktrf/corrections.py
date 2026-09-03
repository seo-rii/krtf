"""Correction workflow (spec §30) — the label supply path for finetuning.

Approval workflow (§30.3 [normative]): SUBMITTED → REVIEWED → ACCEPTED |
REJECTED. Only ACCEPTED corrections are exportable to calibrator fitting,
adaptation and coverage monitoring (INV-018, REQ-COR-001). Corrections never
mutate the glossary (REQ-COR-002); the store is tenant-isolated
(REQ-COR-004); export applies per-verifier-kind weights and per-principal
caps against poisoning (REQ-COR-003, §52.14).

Privacy (§30.2): submissions carry request references and mention *state*
(spans, scores, decisions) — never raw document text unless the tenant
opts in via ``evidence_text`` and policy allows it.
"""

from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field

CORRECTION_TYPES = {
    "WRONG_ENTITY",
    "WRONG_SPAN",
    "MISSED_MENTION",
    "FALSE_MENTION",
    "SHOULD_BE_KB_MISSING",
    "SHOULD_BE_RESOLVED",
}

VERIFIER_KINDS = {"USER", "REVIEWER", "ADMIN"}
# REQ-COR-003: default weights and per-principal export caps by verifier kind
DEFAULT_VERIFIER_WEIGHTS = {"USER": 1, "REVIEWER": 3, "ADMIN": 5}
DEFAULT_PER_PRINCIPAL_CAP = {"USER": 50, "REVIEWER": 500, "ADMIN": 5000}


class CorrectionError(ValueError):
    pass


@dataclass
class Correction:
    correction_id: str
    tenant_id: str
    request_ref: dict  # {snapshot_id, request_id, mention_id}
    correction_type: str
    corrected: dict
    verifier: dict  # {kind, principal_ref}
    mention_state: dict | None
    comment: str = ""
    evidence_text: str | None = None
    status: str = "SUBMITTED"
    review: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        # deep copies on the way out as well: `export_accepted` feeds
        # calibration training (INV-018), and a consumer holding a live
        # reference into the store could rewrite an approved record
        return {
            "correction_id": self.correction_id,
            "tenant_id": self.tenant_id,
            "request_ref": copy.deepcopy(self.request_ref),
            "correction_type": self.correction_type,
            "corrected": copy.deepcopy(self.corrected),
            "verifier": copy.deepcopy(self.verifier),
            "mention_state": copy.deepcopy(self.mention_state),
            "comment": self.comment,
            "status": self.status,
            "review": copy.deepcopy(self.review),
        }


class CorrectionStore:
    """In-memory tenant-scoped correction queue (M3's durable queue analog)."""

    def __init__(self, allow_evidence_text: bool = False):
        self.allow_evidence_text = allow_evidence_text
        self._by_tenant: dict[str, dict[str, Correction]] = {}
        self._ids = itertools.count(1)

    def submit(
        self,
        tenant_id: str,
        request_ref: dict,
        correction_type: str,
        corrected: dict | None = None,
        verifier: dict | None = None,
        mention_state: dict | None = None,
        comment: str = "",
        evidence_text: str | None = None,
        evidence_text_opt_in: bool = False,
    ) -> Correction:
        if correction_type not in CORRECTION_TYPES:
            raise CorrectionError(f"unknown correction_type {correction_type!r}")
        # take a snapshot of the caller's payload before validating it, so
        # what is checked is what is stored — and so a later edit to the
        # dicts the caller still holds cannot reach an approved record
        corrected = copy.deepcopy(corrected) if corrected else {}
        verifier = (copy.deepcopy(verifier) if verifier
                    else {"kind": "USER", "principal_ref": "anonymous"})
        mention_state = copy.deepcopy(mention_state)
        if verifier.get("kind") not in VERIFIER_KINDS:
            raise CorrectionError(f"unknown verifier kind {verifier.get('kind')!r}")
        if correction_type == "MISSED_MENTION" and not corrected.get("span"):
            raise CorrectionError("MISSED_MENTION requires corrected.span (§30.1)")
        if correction_type in ("WRONG_ENTITY", "SHOULD_BE_RESOLVED") \
                and not corrected.get("entity_id"):
            raise CorrectionError(f"{correction_type} requires corrected.entity_id")
        # §30.2: raw text only with explicit opt-in AND tenant policy
        if evidence_text is not None and not (
            evidence_text_opt_in and self.allow_evidence_text
        ):
            evidence_text = None
        c = Correction(
            correction_id=f"cor-{next(self._ids):06d}",
            tenant_id=tenant_id,
            request_ref=copy.deepcopy(request_ref),
            correction_type=correction_type,
            corrected=corrected,
            verifier=verifier,
            mention_state=mention_state,
            comment=comment,
            evidence_text=evidence_text,
        )
        self._by_tenant.setdefault(tenant_id, {})[c.correction_id] = c
        return c

    def get(self, tenant_id: str, correction_id: str) -> Correction:
        # REQ-COR-004: lookups are tenant-scoped; no cross-tenant access
        try:
            return self._by_tenant[tenant_id][correction_id]
        except KeyError:
            raise CorrectionError(
                f"correction {correction_id!r} not found for tenant {tenant_id!r}"
            )

    def list(self, tenant_id: str, status: str | None = None) -> list[Correction]:
        items = list(self._by_tenant.get(tenant_id, {}).values())
        if status:
            items = [c for c in items if c.status == status]
        return items

    def review(self, tenant_id: str, correction_id: str, decision: str,
               reviewer: str, reason: str = "") -> Correction:
        if decision not in ("ACCEPTED", "REJECTED"):
            raise CorrectionError("decision must be ACCEPTED or REJECTED")
        c = self.get(tenant_id, correction_id)
        if c.status not in ("SUBMITTED", "REVIEWED"):
            raise CorrectionError(f"correction already {c.status}")
        c.status = decision
        c.review = {"decision": decision, "reviewer": reviewer, "reason": reason}
        return c

    def export_accepted(
        self,
        tenant_id: str,
        weights: dict[str, int] | None = None,
        per_principal_cap: dict[str, int] | None = None,
    ) -> list[dict]:
        """ACCEPTED corrections only (INV-018), weighted by verifier kind and
        capped per principal (REQ-COR-003). The result feeds
        :func:`ktrf.calibration.derive_training_examples` and
        :func:`ktrf.calibration.empirical_coverage`."""
        weights = weights or DEFAULT_VERIFIER_WEIGHTS
        caps = per_principal_cap or DEFAULT_PER_PRINCIPAL_CAP
        taken: dict[str, int] = {}
        out: list[dict] = []
        for c in self.list(tenant_id, status="ACCEPTED"):
            kind = c.verifier.get("kind", "USER")
            principal = c.verifier.get("principal_ref", "anonymous")
            if taken.get(principal, 0) >= caps.get(kind, 0):
                continue  # per-source volume cap (§52.14)
            taken[principal] = taken.get(principal, 0) + 1
            d = c.to_dict()
            d["weight"] = weights.get(kind, 1)
            out.append(d)
        return out
