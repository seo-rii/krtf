"""Candidate pool and budgets (spec §21, §31).

Union semantics over generation channels; the exact pool is exempt from every
budget (INV-005 / REQ-CAND-001): ``max_non_exact_candidates`` only caps the
non-exact pool, and truncation there is surfaced as ``degraded`` (INV-013).
Fuzzy/doc-local/dense candidates can only *add* to the union — they never
displace exact results (INV-010, INV-009).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CandidateBudget:
    max_exact_senses: int = 4096  # safety limit, §21.5 procedure beyond
    max_non_exact_candidates: int = 256
    max_rerank_candidates: int = 64
    max_final_candidates: int = 32
    max_prediction_set: int = 10


@dataclass
class Candidate:
    entity_id: str
    alias_id: str | None
    family_id: str | None
    generation_channels: set[str] = field(default_factory=set)
    channel_scores: dict[str, float] = field(default_factory=dict)
    surface_transform_cost: float = 0.0
    boundary_valid: bool = True
    scope_match: bool | None = None  # soft feature (§10.5)
    retrieval_pass: int = 1
    is_exact: bool = False
    provenance: dict = field(default_factory=dict)
    # fusion inputs/outputs
    features: dict = field(default_factory=dict)  # §23.2 feature vector
    ranking_score: float = 0.0
    calibrated_probability: float | None = None
    drop_reason: str | None = None  # set only for hard validity drops (§23.1)


@dataclass
class PoolStats:
    exact_added: int = 0
    non_exact_added: int = 0
    non_exact_truncated: int = 0
    hard_dropped: int = 0


class CandidatePool:
    """Per-mention candidate union with budget accounting."""

    def __init__(self, budget: CandidateBudget):
        self.budget = budget
        self.exact: dict[str, Candidate] = {}
        self.non_exact: dict[str, Candidate] = {}
        self.stats = PoolStats()
        self.exact_overflow = False  # §21.5: safety-limit exceeded

    def add(self, cand: Candidate) -> None:
        pool = self.exact if cand.is_exact else self.non_exact
        # evidence for the same entity merges across pools: an entity already
        # in the exact pool absorbs fuzzy evidence, and exact evidence
        # promotes a previously fuzzy-only candidate (INV-010)
        existing = (pool.get(cand.entity_id)
                    or self.exact.get(cand.entity_id)
                    or self.non_exact.get(cand.entity_id))
        if existing is not None:
            existing.generation_channels |= cand.generation_channels
            for ch, sc in cand.channel_scores.items():
                existing.channel_scores[ch] = max(
                    existing.channel_scores.get(ch, 0.0), sc)
            existing.surface_transform_cost = min(
                existing.surface_transform_cost, cand.surface_transform_cost)
            existing.retrieval_pass = min(existing.retrieval_pass,
                                          cand.retrieval_pass)
            if cand.is_exact and not existing.is_exact:
                # promote: exact evidence arrived after a fuzzy candidate
                existing.is_exact = True
                self.non_exact.pop(cand.entity_id, None)
                self.exact[cand.entity_id] = existing
            return
        if cand.is_exact:
            # INV-004/INV-005: never budget-cut; beyond the safety limit,
            # flag for the §21.5 degraded-AMBIGUOUS procedure.
            self.exact[cand.entity_id] = cand
            self.stats.exact_added += 1
            if len(self.exact) > self.budget.max_exact_senses:
                self.exact_overflow = True
            return
        if len(self.non_exact) >= self.budget.max_non_exact_candidates:
            self.stats.non_exact_truncated += 1
            return
        self.non_exact[cand.entity_id] = cand
        self.stats.non_exact_added += 1

    def hard_drop(self, entity_id: str, reason: str) -> None:
        """§23.1 hard validity drop (e.g. scope deny at verified trust)."""
        for pool in (self.exact, self.non_exact):
            if entity_id in pool:
                pool[entity_id].drop_reason = reason
                self.stats.hard_dropped += 1

    def all_candidates(self, include_dropped: bool = False) -> list[Candidate]:
        cands = list(self.exact.values()) + list(self.non_exact.values())
        if not include_dropped:
            cands = [c for c in cands if c.drop_reason is None]
        return cands

    @property
    def truncated(self) -> bool:
        return self.stats.non_exact_truncated > 0
