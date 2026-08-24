"""Resolve pipeline (spec §9 architecture, §20 mention graph, §26 modes, §27 API).

V1 symbolic pipeline:

    canonical normalization -> exact match + boundary -> tail/prefix parse
    -> doc-local + fuzzy channels (Pass 1) -> preliminary fusion
    -> conditional Pass 2 (abbreviation alignment; once per request,
       REQ-CAND-004) -> heuristic fusion -> termness/link decisions
    -> mention graph primary selection -> API response

``fast`` mode runs only the deterministic Pass-1 channels, no ranking or
calibration (§26.1, REQ-API-001, REQ-CAND-005).

Calibration here is the V1 "global conservative calibrator" placeholder
(§48.1): heuristic marginals, conservatively capped, clearly not conformal
(M4 scope). Probability semantics still follow §7.12: per-candidate
marginals, never normalized across the prediction set (INV-019).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .calibration import calibration_group
from .candidates import Candidate, CandidatePool
from .errors import KtrfApiError
from .offsets import OffsetMap, check_span_invariant
from .normalization import build_canonical_stream
from .snapshot import Snapshot
from .tailparser import MentionProposal, parse_matches

_TOKEN_RE = re.compile(r"[가-힣ㄱ-ㅣ]+|[A-Za-z][A-Za-z0-9]*|[0-9]+")

TRUST_LEVELS = (
    "SERVER_VERIFIED", "AUTH_CLAIM", "APPLICATION_VERIFIED",
    "USER_PROVIDED", "UNTRUSTED_DOCUMENT",
)
_HARD_DENY_TRUST = {"SERVER_VERIFIED", "AUTH_CLAIM"}  # §12.4 [normative]

_CHANNEL_BASE = {
    "exact": 1.0, "normalized": 0.97, "doc_local": 0.85,
    "jamo": 0.85, "keyboard": 0.80, "abbrev": 0.55,
}


@dataclass
class MentionNode:
    core_span: tuple[int, int]
    surface: str
    pool: CandidatePool
    proposal: MentionProposal | None = None  # best exact proposal, if any
    doc_local_entities: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    pass2_applied: bool = False


def resolve(
    snapshot: Snapshot,
    text: str | bytes,
    mode: str = "commit",
    context: dict | None = None,
    options: dict | None = None,
) -> dict:
    options = options or {}
    context = context or {}
    policy = snapshot.policy

    # ---- input validation (§13.6, §27.2) ----
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8", errors="strict")
        except UnicodeDecodeError as e:
            raise KtrfApiError("INVALID_UTF8",
                               f"malformed UTF-8 at byte {e.start}") from e
    if mode not in ("fast", "aggressive", "commit"):
        raise KtrfApiError("INVALID_REQUEST", f"unknown mode {mode!r}")
    nbytes = len(text.encode("utf-8"))
    if nbytes > policy.sync_max_input_bytes:
        raise KtrfApiError(
            "INPUT_TOO_LARGE",
            f"input is {nbytes} bytes; sync limit is {policy.sync_max_input_bytes}",
            details={"hint": "use the async document resolve API (§28)"},
        )

    trace: dict = {"channels": [], "pass2_executed": False, "drops": []}
    degraded = False

    stream = build_canonical_stream(text)
    omap = OffsetMap(text)

    # ---- Pass 1: exact + tail/prefix (deterministic core) ----
    raw_matches = snapshot.exact_index.find(stream)
    proposals = parse_matches(stream, raw_matches, snapshot.fst)
    trace["channels"].append("exact")

    nodes: dict[tuple[int, int], MentionNode] = {}

    def node_for(span: tuple[int, int]) -> MentionNode:
        n = nodes.get(span)
        if n is None:
            n = MentionNode(span, text[span[0]:span[1]],
                            CandidatePool(policy.candidate_budget))
            nodes[span] = n
        return n

    for p in proposals:
        n = node_for(p.core_span)
        n.sources.add(p.channel)
        if n.proposal is None or p.proposal_score > n.proposal.proposal_score:
            n.proposal = p
        n.pool.add(Candidate(
            entity_id=p.entity_id, alias_id=p.binding_id, family_id=p.family_id,
            generation_channels={p.channel},
            channel_scores={p.channel: p.proposal_score
                            * _CHANNEL_BASE[p.channel]},
            surface_transform_cost=p.transform_cost,
            is_exact=True,
            provenance={"boundary": p.boundary_status,
                        "transforms": list(p.transforms)},
        ))

    # ---- doc-local channel (§18) ----
    local_bindings = snapshot.doclocal.extract(text)
    if local_bindings:
        trace["channels"].append("doc_local")
    for occ in snapshot.doclocal.find_occurrences(text, local_bindings):
        n = node_for(occ.span)
        n.sources.add("doc_local")
        n.doc_local_entities.update(occ.binding.entity_ids)
        for eid in occ.binding.entity_ids:
            n.pool.add(Candidate(
                entity_id=eid, alias_id=None, family_id=None,
                generation_channels={"doc_local"},
                channel_scores={"doc_local": _CHANNEL_BASE["doc_local"]},
                is_exact=False,
                provenance={"definition_span": occ.binding.definition_span,
                            "trust_level": occ.binding.trust_level},
            ))
    # definitional boost for merged nodes (INV-009: additive only)
    for b in local_bindings:
        for n in nodes.values():
            if n.surface == b.alias_surface:
                n.doc_local_entities.update(b.entity_ids)

    # ---- fuzzy channels (Pass 1, not in fast: §26.1) ----
    exact_spans = [n.core_span for n in nodes.values()
                   if n.pool.exact]
    if mode != "fast":
        trace["channels"].extend(["jamo", "keyboard"])
        windows = 0
        for m in _TOKEN_RE.finditer(text):
            if windows >= policy.max_fuzzy_windows:
                degraded = True
                trace["drops"].append("fuzzy_window_budget")
                break
            span = m.span()
            token = m.group()
            if len(token) < 2:
                continue
            if any(span[0] < e and s < span[1] for s, e in exact_spans):
                continue
            windows += 1
            for fc in snapshot.fuzzy_index.query_jamo(token, span):
                _add_fuzzy(node_for(span), fc)
            for fc in snapshot.fuzzy_index.query_keyboard(token, span):
                _add_fuzzy(node_for(span), fc)
        # drop nodes that gained no candidates
        nodes = {k: n for k, n in nodes.items() if n.pool.all_candidates()}

    # ---- proposal budget (§31) ----
    if len(nodes) > policy.max_total_mention_proposals:
        degraded = True
        trace["drops"].append("mention_proposal_budget")
        keep = sorted(
            nodes.values(),
            key=lambda n: -max((c.channel_scores.get(ch, 0)
                                for c in n.pool.all_candidates()
                                for ch in c.generation_channels), default=0),
        )[: policy.max_total_mention_proposals]
        nodes = {n.core_span: n for n in keep}

    # ---- preliminary fusion + conditional Pass 2 (§21.6) ----
    for n in nodes.values():
        _fuse(n, snapshot, text, context, mode)

    if mode != "fast":
        pass2 = False
        # (b) low-confidence mentions: enrich with abbreviation alignment
        for n in nodes.values():
            top = _top_probability(n)
            if top is not None and top < policy.tau_dense:
                for ac in snapshot.abbrev.align_token(n.surface, n.core_span):
                    n.pool.add(Candidate(
                        entity_id=ac.entity_id, alias_id=None, family_id=None,
                        generation_channels={"abbrev"},
                        channel_scores={"abbrev": _CHANNEL_BASE["abbrev"]
                                        + 0.3 * ac.score},
                        is_exact=False, retrieval_pass=2,
                    ))
                    pass2 = True
                    n.pass2_applied = True
        # (a) uncovered tokens with no candidates at all
        # (defining occurrences inside doc-local definitions are not scanned)
        covered = [n.core_span for n in nodes.values()]
        covered += [b.definition_span for b in local_bindings]
        for m in _TOKEN_RE.finditer(text):
            span, token = m.span(), m.group()
            if len(token) < 2 or len(token) > 12:
                continue
            if any(span[0] < e and s < span[1] for s, e in covered):
                continue
            # try the token itself, then particle-stripped cores
            # (과기정통부에서 -> 과기정통부)
            cores = [(token, span)]
            for cut in range(len(token) - 1, 1, -1):
                if snapshot.fst.parse_full(token[cut:], token[cut - 1]):
                    cores.append((token[:cut], (span[0], span[0] + cut)))
            for core, core_span in cores:
                cands = snapshot.abbrev.align_token(core, core_span)
                if not cands:
                    continue
                n = node_for(core_span)
                n.sources.add("abbrev")
                for ac in cands:
                    n.pool.add(Candidate(
                        entity_id=ac.entity_id, alias_id=None, family_id=None,
                        generation_channels={"abbrev"},
                        channel_scores={"abbrev": _CHANNEL_BASE["abbrev"]
                                        + 0.3 * ac.score},
                        is_exact=False, retrieval_pass=2,
                    ))
                pass2 = True
                n.pass2_applied = True
                break
        if pass2:
            trace["pass2_executed"] = True  # at most once per request
            for n in nodes.values():
                if n.pass2_applied:
                    _fuse(n, snapshot, text, context, mode)

    # ---- decisions + response assembly ----
    ordered = sorted(nodes.values(), key=lambda n: (n.core_span[0],
                                                    -(n.core_span[1] - n.core_span[0])))
    primary_spans = _select_primary(ordered)

    mentions = []
    return_all = options.get("return_all_mentions", False)
    max_set = options.get("max_prediction_set", policy.candidate_budget.max_prediction_set)
    included = [n for n in ordered
                if return_all or n.core_span in primary_spans]
    for i, n in enumerate(included):
        m = _mention_response(n, i, snapshot, omap, text, mode, max_set)
        m["primary"] = n.core_span in primary_spans
        if n.pool.truncated or n.pool.exact_overflow:
            degraded = True
        mentions.append(m)

    resp = {
        "snapshot": {
            "glossary_id": snapshot.glossary.glossary_id,
            "glossary_version": snapshot.glossary_version,
            "snapshot_id": snapshot.snapshot_id,
            "model_bundle_version": None,  # V1: symbolic only
        },
        "mode": mode,
        "degraded": degraded,
        "mentions": mentions,
    }
    if options.get("return_trace"):
        resp["trace"] = trace
    return resp


def _add_fuzzy(node: MentionNode, fc) -> None:
    node.sources.add(fc.channel)
    base = _CHANNEL_BASE[fc.channel]
    node.pool.add(Candidate(
        entity_id=fc.binding.entity_id,
        alias_id=fc.binding.alias_id,
        family_id=fc.binding.family_id,
        generation_channels={fc.channel},
        channel_scores={fc.channel: max(0.1, base - fc.cost)},
        surface_transform_cost=fc.cost,
        is_exact=False,
        provenance={"fuzzy_cost": fc.cost},
    ))


# ---------------------------------------------------------------------------
# Fusion + heuristic conservative calibration (V1)
# ---------------------------------------------------------------------------


def _context_window(text: str, span: tuple[int, int], width: int = 40) -> str:
    return text[max(0, span[0] - width): span[1] + width]


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def _fuse(node: MentionNode, snapshot: Snapshot, text: str,
          context: dict, mode: str) -> None:
    window = _context_window(text, node.core_span)
    window_grams = _bigrams(window) - _bigrams(node.surface)
    n_exact = len([c for c in node.pool.exact.values() if c.drop_reason is None])
    for cand in node.pool.all_candidates(include_dropped=True):
        base = max(cand.channel_scores.values(), default=0.0)
        score = base
        entity = snapshot.glossary.entity(cand.entity_id)
        if entity is not None and window_grams:
            # character-bigram context overlap: robust against Korean
            # particle variation (장애를/장애가 still share 장애)
            signals: set[str] = set()
            for src in (entity.description, entity.canonical, *entity.examples):
                signals |= _bigrams(src)
            for d in entity.domain_ids:
                signals |= _bigrams(d.lower())
            overlap = len(window_grams & signals)
            if overlap:
                score += 0.15 * min(1.0, overlap / 4.0)
        if cand.entity_id in node.doc_local_entities:
            score += 0.20  # document-local definitional boost (§18.3)
        score += _scope_adjust(cand, snapshot, context, node)
        cand.ranking_score = round(score, 4)
        if mode != "fast" and cand.drop_reason is None \
                and snapshot.calibrator is not None:
            # finetuned tenant calibrator (§48.3): Platt-scaled marginal
            cand.calibrated_probability = \
                snapshot.calibrator.calibrate_marginal(cand.ranking_score)
        elif mode != "fast" and cand.drop_reason is None:
            # global conservative calibrator (heuristic placeholder, §48.1):
            # a sense-count prior scaled by surface-path quality, shifted by
            # context/scope evidence. Marginal per candidate, never
            # normalized across the prediction set (§7.12/INV-019).
            if cand.is_exact:
                prior = 0.92 if n_exact <= 1 else max(0.15, 0.80 / n_exact)
                prior -= min(0.2, cand.surface_transform_cost)
                quality = min(1.0, base / _CHANNEL_BASE["exact"])
                prior *= 0.7 + 0.3 * quality  # SOFT boundary / weak tails
            elif "doc_local" in cand.generation_channels:
                prior = 0.60
            elif cand.generation_channels & {"jamo", "keyboard"}:
                prior = max(0.20, 0.50 - 0.3 * cand.surface_transform_cost)
            else:  # abbrev / future dense: prior scales with alignment quality
                prior = 0.30 + max(0.0, base - _CHANNEL_BASE["abbrev"])
            cand.calibrated_probability = round(
                min(0.98, max(0.02, prior + 0.6 * (score - base))), 3)


_SCOPE_DIMS = {"departments": "department", "projects": "project"}


def _scope_adjust(cand: Candidate, snapshot: Snapshot, context: dict,
                  node: MentionNode) -> float:
    if cand.alias_id is None:
        return 0.0
    binding = next((b for b in snapshot.glossary.alias_bindings
                    if b.alias_id == cand.alias_id), None)
    if binding is None:
        return 0.0
    adj = 0.0
    for dim, ctx_key in _SCOPE_DIMS.items():
        ctx = context.get(ctx_key)
        if not ctx:
            continue  # context absent: neutral (§10.5)
        value = ctx.get("value") if isinstance(ctx, dict) else ctx
        trust = (ctx.get("trust", "USER_PROVIDED")
                 if isinstance(ctx, dict) else "USER_PROVIDED")
        allow = binding.scope.allow.get(dim, [])
        deny = binding.scope.deny.get(dim, [])
        if value in deny:
            if trust in _HARD_DENY_TRUST:
                # §12.4: hard removal only at server-verified trust levels
                node.pool.hard_drop(cand.entity_id, f"scope_deny:{dim}={value}")
            elif trust == "APPLICATION_VERIFIED":
                adj -= 0.20
            elif trust == "USER_PROVIDED":
                adj -= 0.10
            # UNTRUSTED_DOCUMENT: ignore
        elif allow:
            if value in allow:
                cand.scope_match = True
                adj += 0.05
            else:
                # REQ-TEN-003: allow-mismatch is always soft
                cand.scope_match = False
                adj -= 0.08
    return adj


def _top_probability(node: MentionNode) -> float | None:
    ps = [c.calibrated_probability for c in node.pool.all_candidates()
          if c.calibrated_probability is not None]
    return max(ps) if ps else 0.0


# ---------------------------------------------------------------------------
# Decisions (§7.8/§7.9, §24, §25.6, §26.1)
# ---------------------------------------------------------------------------


def _mention_response(node: MentionNode, idx: int, snapshot: Snapshot,
                      omap: OffsetMap, text: str, mode: str,
                      max_set: int) -> dict:
    s, e = node.core_span
    check_span_invariant(text, s, e, node.surface)  # INV-002
    cands = node.pool.all_candidates()

    m: dict = {
        "mention_id": f"m{idx + 1}",
        "surface": node.surface,
        "span": omap.span_dict(s, e),
        "generation_channels": sorted(node.sources),
    }
    if node.proposal is not None:
        p = node.proposal
        m["full_span"] = omap.span_dict(*p.full_span)
        if p.prefix:
            m["prefix"] = {
                "surface": p.prefix["surface"], "kind": p.prefix["kind"],
                "span": omap.span_dict(*p.prefix["span"]),
            }
        best = p.best_tail
        if best and (best.particles or best.residual or best.latin_tail):
            m["tail"] = {
                "particles": list(best.particles),
                "residual": best.residual,
                "residual_kind": best.residual_kind,
                "latin_tail": best.latin_tail,
                "grammatical": best.grammatical,
            }
        if len(p.matched_segments) > 1:
            m["matched_segments"] = [
                omap.span_dict(a, b)["codepoint"] for a, b in p.matched_segments]

    if mode == "fast":
        # §26.1: deterministic only, no calibration, no ranking
        senses = sorted({c.entity_id for c in cands if c.is_exact}) or sorted(
            {c.entity_id for c in cands})
        m["mention_decision"] = "TERM" if any(
            c.is_exact or "doc_local" in c.generation_channels for c in cands
        ) else "UNCERTAIN"
        if len(senses) == 1:
            m["link_decision"] = "RESOLVED"
            ent = snapshot.glossary.entity(senses[0])
            m["resolved_entity"] = {
                "entity_id": senses[0],
                "canonical": ent.canonical if ent else None,
            }
        else:
            m["link_decision"] = "AMBIGUOUS"
            m["prediction_set"] = {
                "members": [{"kind": "ENTITY", "entity_id": eid}
                            for eid in senses],
            }
        return m

    # ---- calibrated path (aggressive/commit) ----
    ranked = sorted(cands, key=lambda c: (-(c.calibrated_probability or 0),
                                          c.entity_id))
    top = ranked[0] if ranked else None
    top_p = top.calibrated_probability if top else 0.0

    has_strong = any(c.is_exact or "doc_local" in c.generation_channels
                     for c in cands)
    mention_decision = "TERM" if (has_strong or (top_p or 0) >= 0.6) else "UNCERTAIN"

    calibrator = snapshot.calibrator
    calibration_fallback = False
    if calibrator is not None:
        # conformal membership: s = 1 − marginal ≤ q̂(group) (§25.2 step 4)
        n_senses = len({c.entity_id for c in cands})
        members = []
        for c in ranked:
            group = calibration_group(c.generation_channels, n_senses)
            included, fb = calibrator.in_prediction_set(
                c.calibrated_probability or 0.0, group)
            calibration_fallback |= fb
            if included:
                members.append(c)
    else:
        members = [c for c in ranked
                   if (c.calibrated_probability or 0)
                   >= snapshot.policy.prediction_set_min_p]
    if top is not None and top not in members:
        members = [top] + members
    members = members[:max_set]

    kb_member = None
    # §24.3: KB_MISSING joins the set only when no candidate clears the
    # context-compatibility bar AND there is no exact alias evidence
    # (an exact match proves the concept exists in this glossary).
    if (top_p or 0) < 0.6 and not any(c.is_exact for c in cands):
        kb_p = round(min(0.9, max(0.05, 0.8 - (top_p or 0))), 3)
        kb_member = {"kind": "KB_MISSING", "calibrated_probability": kb_p}

    node_degraded = node.pool.truncated or node.pool.exact_overflow

    set_members = [
        {"kind": "ENTITY", "entity_id": c.entity_id,
         "calibrated_probability": c.calibrated_probability,
         "ranking_score": c.ranking_score,
         "generation_channels": sorted(c.generation_channels),
         "retrieval_pass": c.retrieval_pass}
        for c in members
    ]
    if kb_member:
        set_members.append(kb_member)

    policy = snapshot.policy
    second_p = (members[1].calibrated_probability
                if len(members) > 1 else 0.0) or 0.0

    if node.pool.exact_overflow:
        # §21.5: safety-limit overflow -> AMBIGUOUS + degraded, never a 500
        link = "AMBIGUOUS"
    elif not set_members:
        link = "UNCERTAIN"
    elif kb_member and (kb_member["calibrated_probability"] > (top_p or 0)):
        link = "KB_MISSING"
    elif (
        mention_decision == "TERM"  # INV-016/REQ-TRM-001
        and not node_degraded  # §27.8/REQ-API-005
        and top is not None
        and (top_p or 0) >= policy.resolve_threshold
        and (len(set_members) == 1 or (top_p or 0) - second_p >= policy.margin_threshold)
        and not kb_member
    ):
        link = "RESOLVED"
    elif node_degraded and len(set_members) <= 1:
        link = "UNCERTAIN"
    else:
        link = "AMBIGUOUS"

    m["mention_decision"] = mention_decision
    m["link_decision"] = link
    if link == "RESOLVED":
        ent = snapshot.glossary.entity(top.entity_id)
        m["resolved_entity"] = {
            "entity_id": top.entity_id,
            "canonical": ent.canonical if ent else None,
            "calibrated_probability": top_p,
        }
    m["prediction_set"] = {
        "set_confidence": (calibrator.set_confidence if calibrator is not None
                           else policy.set_confidence),
        "members": set_members,
    }
    if calibration_fallback:
        # REQ-CAL-002: group sample below n_min → pooled-quantile fallback
        m["prediction_set"]["calibration_fallback"] = True
    if node_degraded:
        m["degraded"] = True
    return m


# ---------------------------------------------------------------------------
# Primary mention selection (§20.4, REQ-GRPH-001)
# ---------------------------------------------------------------------------


def _select_primary(ordered: list[MentionNode]) -> set[tuple[int, int]]:
    def min_alias(n: MentionNode) -> str:
        ids = [c.alias_id for c in n.pool.all_candidates() if c.alias_id]
        return min(ids) if ids else "￿"

    ranked = sorted(
        ordered,
        key=lambda n: (
            0 if n.pool.exact else 1,  # full exact binding first
            -(n.core_span[1] - n.core_span[0]),  # longer core span
            n.core_span[0],  # earlier start
            min_alias(n),  # alias_id lexicographic
        ),
    )
    selected: list[tuple[int, int]] = []
    out: set[tuple[int, int]] = set()
    for n in ranked:
        s, e = n.core_span
        if any(s < e2 and s2 < e for s2, e2 in selected):
            continue
        selected.append((s, e))
        out.add((s, e))
    return out
