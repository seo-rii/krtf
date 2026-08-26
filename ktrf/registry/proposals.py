"""Term proposal lifecycle and admission policy (PLAN_PI.md §5–§6).

The governing rule: **an LLM proposes, deterministic validation checks, and
an approval policy decides what becomes persistent.** A model's own
reasoning never writes to a durable dictionary.

State model::

    OBSERVED → PROPOSED → VALIDATED ─┬→ PROVISIONAL → ACTIVE
                     │               └→ ACTIVE
                     └→ REJECTED           │
                                           ├→ DEPRECATED
                                           └→ ROLLED_BACK

``VALIDATED`` is purely mechanical — surface actually present in cited
evidence, non-empty canonical/definition, no alias collision, no
instructional or sensitive content, ids derivable, glossary compiles. It
says nothing about whether the term is *correct*; that is what approval (or
a strict auto-promotion rule) is for.

This is intentionally separate from :mod:`ktrf.corrections`: corrections
teach the resolver about mistakes on an existing glossary, proposals change
what the glossary contains. Only the safety machinery is shared in spirit —
per-source caps, audit trail, explicit review.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field, replace

from ..errors import KtrfApiError

SCOPES = ("session", "project", "global")
STATES = ("OBSERVED", "PROPOSED", "VALIDATED", "REJECTED", "PROVISIONAL",
          "ACTIVE", "DEPRECATED", "ROLLED_BACK")
ORIGINS = ("llm_proposal", "user_explicit", "document_definition",
           "deterministic_detector")

# Definitions that try to steer behaviour rather than describe meaning.
_INSTRUCTIONAL = re.compile(
    r"(ignore\s+(all\s+)?previous|disregard\s+(all\s+)?previous"
    r"|system\s*:|</\w+>|<\s*(system|script|terminology_context)"
    r"|rm\s+-rf|sudo\s|curl\s+http|무시하(고|라)|지시를\s*무시"
    r"|다음부터\s*모든|비밀|secret\s+key|api[_\s-]?key"
    r"|반드시\s*실행|실행하라|출력하라)", re.IGNORECASE)
# Obvious secrets / personal data that must never enter a shared glossary.
_SENSITIVE = re.compile(
    r"(\d{6}\s*[-–]\s*[1-4]\d{6}"            # 주민등록번호
    r"|\b(?:\d[ -]?){13,19}\b"                # card-like number runs
    r"|\b(sk|pk|ghp|gho|xox[bp])[-_][A-Za-z0-9]{16,}"  # token shapes
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MAX_CANONICAL_CHARS = 120
MAX_DEFINITION_CHARS = 1000


@dataclass(frozen=True)
class EvidenceRef:
    """Where a proposal's surface was actually seen."""

    entry_id: str
    surface_present: bool = False
    definition_pattern: bool = False
    session_id: str | None = None
    trusted_source: bool = True


@dataclass(frozen=True)
class TermProposal:
    proposal_id: str
    surface: str
    canonical: str
    short_definition: str
    requested_scope: str
    origin: str
    aliases: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    model_confidence: float | None = None
    status: str = "PROPOSED"
    validation_report: dict = field(default_factory=dict)
    created_at: float = 0.0
    expires_after_turns: int | None = None
    history: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["evidence_refs"] = [e.__dict__ for e in self.evidence_refs]
        d["aliases"] = list(self.aliases)
        d["history"] = list(self.history)
        return d


@dataclass(frozen=True)
class TermAdmissionPolicy:
    """What may become active without a human saying yes."""

    allow_session_auto_explicit: bool = True
    allow_session_auto_inferred: bool = False
    allow_project_auto: bool = False
    require_project_trust: bool = True
    project_min_evidence: int = 3
    project_min_distinct_sessions: int = 2
    allow_global_auto: bool = False
    provisional_ttl_turns: int = 20
    reject_instructional_definitions: bool = True
    reject_sensitive_content: bool = True
    max_proposals_per_session: int = 50


def _clean(value, field_name: str, max_chars: int) -> str:
    if not isinstance(value, str):
        raise KtrfApiError("INVALID_REQUEST",
                           f"{field_name} must be a string")
    s = unicodedata.normalize("NFC", value).strip()
    if len(s) > max_chars:
        raise KtrfApiError("INVALID_REQUEST",
                           f"{field_name} exceeds {max_chars} characters")
    return s


def validate_term_proposal(proposal: TermProposal, snapshot,
                           policy: TermAdmissionPolicy | None = None,
                           compile_check=None) -> dict:
    """Deterministic gate. Returns a report; ``ok`` means mechanically sound.

    ``compile_check(proposal) -> bool`` optionally verifies that a candidate
    snapshot containing the term compiles and passes conformance — the
    caller supplies it because compiling is expensive and integration
    specific.
    """
    policy = policy or TermAdmissionPolicy()
    checks: dict[str, bool] = {}
    reasons: list[str] = []

    surface = proposal.surface
    checks["surface_nonempty"] = bool(surface.strip())
    checks["canonical_nonempty"] = bool(proposal.canonical.strip())
    checks["definition_nonempty"] = bool(proposal.short_definition.strip())
    checks["no_control_chars"] = not any(
        _CONTROL.search(x) for x in
        (surface, proposal.canonical, proposal.short_definition))
    checks["length_limits"] = (
        len(proposal.canonical) <= MAX_CANONICAL_CHARS
        and len(proposal.short_definition) <= MAX_DEFINITION_CHARS
        and len(surface) <= MAX_CANONICAL_CHARS)

    # the surface must have been observed, not imagined by the model
    checks["evidence_surface_present"] = any(
        e.surface_present and e.trusted_source
        for e in proposal.evidence_refs)

    text = f"{proposal.canonical}\n{proposal.short_definition}"
    if policy.reject_instructional_definitions:
        checks["not_instructional"] = not bool(_INSTRUCTIONAL.search(text))
    if policy.reject_sensitive_content:
        checks["no_sensitive_content"] = not bool(_SENSITIVE.search(text))

    checks["scope_known"] = proposal.requested_scope in SCOPES
    checks["origin_known"] = proposal.origin in ORIGINS

    # alias collision: the surface must not already resolve elsewhere
    collisions = []
    if snapshot is not None:
        for b in snapshot.glossary.alias_bindings:
            if b.surface == surface:
                collisions.append(b.entity_id)
    checks["no_alias_collision"] = not collisions
    if collisions:
        reasons.append(f"surface already bound to {sorted(set(collisions))}")

    # duplicate canonical under a different key
    duplicate = []
    if snapshot is not None:
        for e in snapshot.glossary.entities:
            if e.canonical.strip().lower() == proposal.canonical.strip().lower():
                duplicate.append(e.entity_id)
    checks["no_duplicate_entity"] = not duplicate
    if duplicate:
        reasons.append(f"canonical duplicates {sorted(set(duplicate))}")

    if compile_check is not None:
        try:
            checks["compiles"] = bool(compile_check(proposal))
        except Exception as exc:  # a failing compile is a validation result
            checks["compiles"] = False
            reasons.append(f"compile failed: {exc}")

    for name, passed in checks.items():
        if not passed and name not in ("no_alias_collision",
                                       "no_duplicate_entity", "compiles"):
            reasons.append(f"failed check: {name}")
    return {"ok": all(checks.values()), "checks": checks,
            "reasons": reasons}


def decide_admission(proposal: TermProposal, policy: TermAdmissionPolicy,
                     *, project_trusted: bool = False,
                     evidence_count: int = 0,
                     distinct_sessions: int = 0) -> tuple[str, str]:
    """Post-validation routing: (target_state, reason).

    Never returns ACTIVE for project/global unless the policy explicitly
    opens that door AND every strict condition holds — an LLM confidence
    score alone is never sufficient.
    """
    scope = proposal.requested_scope
    explicit = proposal.origin in ("user_explicit", "document_definition")
    if scope == "session":
        if explicit and policy.allow_session_auto_explicit:
            return "ACTIVE", "explicit user definition in session scope"
        if policy.allow_session_auto_inferred:
            return "PROVISIONAL", "inferred term admitted provisionally"
        return "PROVISIONAL" if proposal.origin == "llm_proposal" \
            else "VALIDATED", "session auto-activation not permitted"
    if scope == "project":
        if not policy.allow_project_auto:
            return "VALIDATED", "project scope requires confirmation"
        if policy.require_project_trust and not project_trusted:
            return "VALIDATED", "project is not trusted"
        if not explicit:
            return "VALIDATED", "project auto-promotion needs explicit "\
                                "definition evidence"
        if evidence_count < policy.project_min_evidence:
            return "VALIDATED", (f"evidence {evidence_count} < "
                                 f"{policy.project_min_evidence}")
        if distinct_sessions < policy.project_min_distinct_sessions:
            return "VALIDATED", (f"distinct sessions {distinct_sessions} < "
                                 f"{policy.project_min_distinct_sessions}")
        return "ACTIVE", "project auto-promotion conditions met"
    if not policy.allow_global_auto:
        return "VALIDATED", "global scope always requires confirmation"
    return "VALIDATED", "global auto-activation disabled by default"


class TermProposalStore:
    """In-memory proposal store with an append-only audit trail."""

    def __init__(self, policy: TermAdmissionPolicy | None = None,
                 clock=time.time):
        self.policy = policy or TermAdmissionPolicy()
        self._clock = clock
        self._by_id: dict[str, TermProposal] = {}
        self._session_counts: dict[str, int] = {}
        self.audit: list[dict] = []

    # ---------------------------------------------------------------- io
    def _log(self, action: str, proposal: TermProposal, **extra) -> None:
        self.audit.append({
            "at": self._clock(), "action": action,
            "proposal_id": proposal.proposal_id, "surface": proposal.surface,
            "scope": proposal.requested_scope, "status": proposal.status,
            **extra})

    def submit(self, *, surface: str, canonical: str, short_definition: str,
               requested_scope: str = "session", origin: str = "llm_proposal",
               evidence_refs: tuple[EvidenceRef, ...] = (),
               aliases: tuple[str, ...] = (),
               model_confidence: float | None = None,
               session_id: str = "default") -> TermProposal:
        if requested_scope not in SCOPES:
            raise KtrfApiError("INVALID_REQUEST",
                               f"unknown scope {requested_scope!r}",
                               details={"known": list(SCOPES)})
        if origin not in ORIGINS:
            raise KtrfApiError("INVALID_REQUEST",
                               f"unknown origin {origin!r}",
                               details={"known": list(ORIGINS)})
        used = self._session_counts.get(session_id, 0)
        if used >= self.policy.max_proposals_per_session:
            raise KtrfApiError(
                "RATE_LIMITED",
                f"session {session_id!r} exceeded "
                f"{self.policy.max_proposals_per_session} proposals")
        self._session_counts[session_id] = used + 1

        surface = _clean(surface, "surface", MAX_CANONICAL_CHARS)
        canonical = _clean(canonical, "canonical", MAX_CANONICAL_CHARS)
        definition = _clean(short_definition, "short_definition",
                            MAX_DEFINITION_CHARS)
        pid = "tp-" + hashlib.sha256(
            json.dumps([surface, canonical, requested_scope, session_id,
                        len(self._by_id)], ensure_ascii=False).encode()
        ).hexdigest()[:12]
        proposal = TermProposal(
            proposal_id=pid, surface=surface, canonical=canonical,
            short_definition=definition, requested_scope=requested_scope,
            origin=origin, aliases=tuple(aliases),
            evidence_refs=tuple(evidence_refs),
            model_confidence=model_confidence, status="PROPOSED",
            created_at=self._clock(),
            history=({"state": "PROPOSED", "at": self._clock()},))
        self._by_id[pid] = proposal
        self._log("submit", proposal, session_id=session_id)
        return proposal

    def _transition(self, proposal: TermProposal, state: str,
                    reason: str) -> TermProposal:
        if state not in STATES:
            raise KtrfApiError("INVALID_REQUEST", f"unknown state {state!r}")
        updated = replace(
            proposal, status=state,
            history=proposal.history + ({"state": state, "reason": reason,
                                         "at": self._clock()},))
        self._by_id[proposal.proposal_id] = updated
        self._log("transition", updated, to=state, reason=reason)
        return updated

    # ------------------------------------------------------------ flow
    def validate(self, proposal_id: str, snapshot,
                 compile_check=None) -> TermProposal:
        proposal = self.get(proposal_id)
        report = validate_term_proposal(proposal, snapshot, self.policy,
                                        compile_check)
        proposal = replace(proposal, validation_report=report)
        self._by_id[proposal_id] = proposal
        return self._transition(
            proposal, "VALIDATED" if report["ok"] else "REJECTED",
            "; ".join(report["reasons"]) or "all checks passed")

    def route(self, proposal_id: str, *, project_trusted: bool = False,
              evidence_count: int = 0,
              distinct_sessions: int = 0) -> TermProposal:
        """Apply the admission policy to a VALIDATED proposal."""
        proposal = self.get(proposal_id)
        if proposal.status != "VALIDATED":
            raise KtrfApiError(
                "INVALID_REQUEST",
                f"proposal {proposal_id} is {proposal.status}, not VALIDATED")
        state, reason = decide_admission(
            proposal, self.policy, project_trusted=project_trusted,
            evidence_count=evidence_count,
            distinct_sessions=distinct_sessions)
        if state == "PROVISIONAL":
            proposal = replace(
                proposal,
                expires_after_turns=self.policy.provisional_ttl_turns)
            self._by_id[proposal_id] = proposal
        return self._transition(proposal, state, reason)

    def approve(self, proposal_id: str, approver: str) -> TermProposal:
        """Human approval — the only path to ACTIVE for project/global."""
        proposal = self.get(proposal_id)
        if proposal.status not in ("VALIDATED", "PROVISIONAL"):
            raise KtrfApiError(
                "INVALID_REQUEST",
                f"cannot approve a {proposal.status} proposal")
        return self._transition(proposal, "ACTIVE",
                                f"approved by {approver}")

    def reject(self, proposal_id: str, approver: str,
               reason: str = "") -> TermProposal:
        return self._transition(self.get(proposal_id), "REJECTED",
                                f"rejected by {approver}: {reason}".strip())

    def rollback(self, proposal_id: str, reason: str = "") -> TermProposal:
        proposal = self.get(proposal_id)
        if proposal.status != "ACTIVE":
            raise KtrfApiError("INVALID_REQUEST",
                               "only ACTIVE terms can be rolled back")
        return self._transition(proposal, "ROLLED_BACK", reason)

    def expire_provisional(self, turns_elapsed: int) -> list[TermProposal]:
        """TTL sweep: provisional terms do not linger silently."""
        expired = []
        for proposal in list(self._by_id.values()):
            if proposal.status == "PROVISIONAL" \
                    and proposal.expires_after_turns is not None \
                    and turns_elapsed >= proposal.expires_after_turns:
                expired.append(self._transition(proposal, "DEPRECATED",
                                                "provisional TTL elapsed"))
        return expired

    # ----------------------------------------------------------- access
    def get(self, proposal_id: str) -> TermProposal:
        proposal = self._by_id.get(proposal_id)
        if proposal is None:
            raise KtrfApiError("NOT_FOUND",
                               f"unknown proposal {proposal_id!r}")
        return proposal

    def list(self, status: str | None = None,
             scope: str | None = None) -> list[TermProposal]:
        out = list(self._by_id.values())
        if status:
            out = [p for p in out if p.status == status]
        if scope:
            out = [p for p in out if p.requested_scope == scope]
        return sorted(out, key=lambda p: p.created_at)

    def active_terms_doc(self, scope: str) -> dict:
        """ACTIVE proposals for one scope as a Simple Terminology document,
        ready for :func:`ktrf.registry.simple_schema.compile_simple_terms`."""
        terms = []
        for p in self.list(status="ACTIVE", scope=scope):
            key = re.sub(r"[^a-z0-9._-]+", "-",
                         p.canonical.lower()).strip("-") or p.proposal_id
            terms.append({
                "key": key, "canonical": p.canonical,
                "surfaces": [p.surface, *p.aliases],
                "short_definition": p.short_definition,
            })
        return {"schema_version": 1, "terms": terms}
