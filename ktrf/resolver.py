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
from .morphology import DISTINCT, SAME
from .segmentation import (BARE, GuardVerdict, MatchEvidence,
                           StructuralPath, distinct_cores, segment_token)
from .snapshot import Snapshot
from .tailparser import MentionProposal, parse_matches

_TOKEN_RE = re.compile(r"[가-힣ㄱ-ㅣ]+|[A-Za-z][A-Za-z0-9]*|[0-9]+")
_MIXED_RUN_RE = re.compile(r"[가-힣ㄱ-ㅣA-Za-z0-9]+")


def _is_hangul_ch(ch: str) -> bool:
    return "가" <= ch <= "힣" or "ㄱ" <= ch <= "ㅣ"


def _abbrev_tokens(text: str):
    """Script runs, plus any run that mixes Hangul with ASCII alphanumerics.

    Korean organisation names change script mid-name — `SK하이닉스`,
    `LG유플러스`, `한전KDN` — so a script change is not a name boundary,
    and an abbreviation coined from one (`SK하닉`) is neither all-Latin nor
    all-Hangul. :data:`_TOKEN_RE` stops at every script change, so the aligner
    only ever received the halves and could not match either.

    The whole run is yielded *in addition to* the halves, and only here. The
    abbreviation channel reasons by subsequence, which does not care what
    alphabet a character belongs to. The fuzzy channel's edit costs are
    defined per script (jamo distance, dubeolsik adjacency) and what a mixed
    run should cost there is a separate question, so it keeps script runs.
    """
    seen: set[tuple[int, int]] = set()
    for m in _MIXED_RUN_RE.finditer(text):
        token = m.group()
        if any(_is_hangul_ch(c) for c in token) and any(
                c.isascii() and c.isalnum() for c in token):
            seen.add(m.span())
            yield m.span(), token
    for m in _TOKEN_RE.finditer(text):
        if m.span() not in seen:
            yield m.span(), m.group()

TRUST_LEVELS = (
    "SERVER_VERIFIED", "AUTH_CLAIM", "APPLICATION_VERIFIED",
    "USER_PROVIDED", "UNTRUSTED_DOCUMENT",
)
_HARD_DENY_TRUST = {"SERVER_VERIFIED", "AUTH_CLAIM"}  # §12.4 [normative]

_CHANNEL_BASE = {
    "exact": 1.0, "normalized": 0.97, "doc_local": 0.85,
    "jamo": 0.85, "keyboard": 0.80, "abbrev": 0.55, "dense": 0.55,
}


@dataclass
class MentionNode:
    core_span: tuple[int, int]
    surface: str
    pool: CandidatePool
    proposal: MentionProposal | None = None  # best exact proposal, if any
    path: StructuralPath | None = None  # accepted by a Level B channel
    doc_local_entities: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    pass2_applied: bool = False


_OPTION_SCHEMA = {
    # name -> (type, validator or None)
    "return_all_mentions": (bool, None),
    "return_features": (bool, None),
    "return_trace": (bool, None),
    "return_eval_trace": (bool, None),
    "detect_unregistered_mentions": (bool, None),
    "max_prediction_set": (int, lambda v: 1 <= v <= 500),
    # §31 wall-clock budget. Level A never yields to it — the deterministic
    # catalog guarantee is not a best-effort stage — so the floor is whatever
    # the exact pass costs, and the deadline governs the optional Level B
    # stages above it.
    "deadline_ms": (int, lambda v: 1 <= v <= 600_000),
}


def _validate_options(options: dict) -> None:
    """§27.2: every runtime option is schema-checked; misconfiguration is a
    typed API error, never a silent quality change or a raw TypeError."""
    for key, value in options.items():
        spec = _OPTION_SCHEMA.get(key)
        if spec is None:
            raise KtrfApiError("INVALID_REQUEST",
                               f"unknown option {key!r}",
                               details={"known": sorted(_OPTION_SCHEMA)})
        typ, check = spec
        # bool is an int subclass — reject True where an int is expected
        if typ is int and isinstance(value, bool) or \
                not isinstance(value, typ):
            raise KtrfApiError(
                "INVALID_REQUEST",
                f"option {key!r} expects {typ.__name__}, "
                f"got {type(value).__name__}")
        if check is not None and not check(value):
            raise KtrfApiError("INVALID_REQUEST",
                               f"option {key!r} out of range: {value!r}")


def resolve(
    snapshot: Snapshot,
    text: str | bytes,
    mode: str = "commit",
    context: dict | None = None,
    options: dict | None = None,
    metrics=None,
) -> dict:
    import time as _time

    _t0 = _time.perf_counter()
    options = options or {}
    context = context or {}
    policy = snapshot.policy
    _validate_options(options)

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

    # §31: a wall-clock budget over the optional stages. Nothing here can
    # stop the exact pass — Level A is a guarantee, not a best-effort stage —
    # so the deadline governs fuzzy, dense and rerank, in the order they run.
    # Each stage is checked before it is entered rather than interrupted
    # part-way, so a skipped stage is skipped whole and the response can name
    # it instead of returning half of one.
    deadline_ms = options.get("deadline_ms")
    deadline_at = (_t0 + deadline_ms / 1000.0) if deadline_ms else None
    deadline_skipped: list[str] = []

    def _past_deadline(stage: str) -> bool:
        if deadline_at is None or _time.perf_counter() < deadline_at:
            return False
        if stage not in deadline_skipped:
            deadline_skipped.append(stage)
        return True

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
    generation_cutoff: int | None = None
    if mode != "fast":
        trace["channels"].extend(["jamo", "keyboard"])
        windows = 0
        budget_hit = False
        for m in _TOKEN_RE.finditer(text):
            if budget_hit:
                break
            span = m.span()
            token = m.group()
            if _past_deadline("fuzzy"):
                # same shape as exhausting the window budget: everything from
                # here on is seen by the exact channel alone, and the mentions
                # that affects say so rather than the whole response carrying
                # one undifferentiated boolean (§27.8/REQ-API-005)
                degraded = True
                trace["drops"].append("deadline_fuzzy")
                generation_cutoff = span[0]
                break
            if len(token) < 2:
                continue
            if any(span[0] < e and s < span[1] for s, e in exact_spans):
                continue
            # M1: the Level B channels read the same decomposition the exact
            # path uses, so a typo carrying a particle reaches the index as
            # its core and the mention span stops at that core rather than
            # swallowing a tail nothing ever analysed (INV-012).
            for path in distinct_cores(
                    _paths_for(snapshot, text, token, span))[
                    :policy.max_segmentation_paths]:
                # A 2-syllable core can only be reached by inferring a tail,
                # and §10.6 disables generic fuzzy for aliases that short, so
                # such a query costs a shortlist scan and can never match.
                if len(path.core) < (2 if path.kind == BARE else 3):
                    continue
                if windows >= policy.max_fuzzy_windows:
                    degraded = True
                    trace["drops"].append("fuzzy_window_budget")
                    # everything from here to the end of the text is scanned
                    # by the exact channel alone: the loop breaks out, so no
                    # later token is offered to fuzzy or keyboard. Remember
                    # where that happened so the mentions it affects can say
                    # so (§27.8/REQ-API-005) instead of the whole response
                    # carrying one undifferentiated boolean.
                    generation_cutoff = span[0]
                    budget_hit = True
                    break
                windows += 1
                for fc in snapshot.fuzzy_index.query_jamo(path.core,
                                                          path.core_span):
                    _add_fuzzy(node_for(path.core_span), fc,
                               snapshot.guard, path)
                for fc in snapshot.fuzzy_index.query_keyboard(path.core,
                                                              path.core_span):
                    _add_fuzzy(node_for(path.core_span), fc,
                               snapshot.guard, path)
        trace["fuzzy_windows"] = windows
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
        dense_queries = 0

        def dense_enrich(span: tuple[int, int], query_text: str) -> None:
            """Pass-2 dense retrieval (§21.6, V2 bi-encoder §22.3)."""
            nonlocal pass2, dense_queries, degraded
            if snapshot.dense is None:
                return
            if _past_deadline("dense"):
                if "deadline_dense" not in trace["drops"]:
                    trace["drops"].append("deadline_dense")
                    degraded = True  # INV-013: a cut generation stage degrades
                return
            if dense_queries >= policy.max_dense_queries_per_request:
                if "dense_query_budget" not in trace["drops"]:
                    trace["drops"].append("dense_query_budget")
                    degraded = True  # INV-013
                return
            dense_queries += 1
            qv = snapshot.dense.encoder.encode_query(query_text)
            lo, hi = getattr(snapshot.dense.encoder, "sim_range", (0.0, 1.0))
            for eid, sim in snapshot.dense.index.search(qv, policy.dense_top_k):
                strength = max(0.0, min(1.0, (sim - lo) / max(1e-6, hi - lo)))
                if strength < 0.2:
                    continue
                n = node_for(span)
                n.sources.add("dense")
                # dense is a Level B channel and answers to the guard like
                # the rest of them. Skipping it does not merely leave one
                # channel unchecked: unblocked evidence for an entity lifts
                # the block when the pool merges, so an unguarded dense hit
                # silently re-allows a commit the tail already refused.
                verdict = _guard_for(snapshot, n, "dense", 1 - strength)
                n.pool.add(Candidate(
                    entity_id=eid, alias_id=None, family_id=None,
                    generation_channels={"dense"},
                    channel_scores={"dense": (_CHANNEL_BASE["dense"]
                                              + 0.3 * strength)
                                    * verdict.score_factor},
                    is_exact=False, retrieval_pass=2,
                    commit_blocked=verdict.blocked_reason,
                    provenance={"dense_sim": round(sim, 4),
                                "guard": list(verdict.reasons)},
                ))
                pass2 = True
                n.pass2_applied = True

        # (b) low-confidence mentions: abbreviation alignment ∪ dense
        for n in list(nodes.values()):
            top = _top_probability(n)
            if top is not None and top < policy.tau_dense:
                for ac in snapshot.abbrev.align_token(n.surface, n.core_span):
                    # this channel must face the same guard as every other
                    # Level B channel: an unguarded candidate for an entity
                    # another channel had blocked *lifts* that block when the
                    # pool merges the two, quietly undoing invariant ②
                    verdict = _guard_for(snapshot, n, "abbrev", 1 - ac.score)
                    n.pool.add(Candidate(
                        entity_id=ac.entity_id, alias_id=None, family_id=None,
                        generation_channels={"abbrev"},
                        channel_scores={"abbrev": (_CHANNEL_BASE["abbrev"]
                                        + 0.3 * ac.score)
                                        * verdict.score_factor},
                        is_exact=False, retrieval_pass=2,
                        commit_blocked=verdict.blocked_reason,
                    ))
                    pass2 = True
                    n.pass2_applied = True
                dense_enrich(n.core_span,
                             _context_window(text, n.core_span, 30))
        # (a) uncovered tokens with no candidates at all
        # (defining occurrences inside doc-local definitions are not scanned)
        covered = [n.core_span for n in nodes.values()]
        covered += [b.definition_span for b in local_bindings]
        for span, token in _abbrev_tokens(text):
            if len(token) < 2 or len(token) > 12:
                continue
            if any(span[0] < e and s < span[1] for s, e in covered):
                continue
            # the same segmentation every other channel uses; this was a
            # private particle-strip loop that no other channel shared
            paths = distinct_cores(
                _paths_for(snapshot, text, token, span))[
                :policy.max_segmentation_paths]
            hit_span = None
            for path in paths:
                cands = snapshot.abbrev.align_token(path.core, path.core_span)
                if not cands:
                    continue
                n = node_for(path.core_span)
                n.sources.add("abbrev")
                if n.path is None:
                    n.path = path
                for ac in cands:
                    ev = MatchEvidence.from_path("abbrev", path,
                                                 transform_cost=1 - ac.score)
                    verdict = snapshot.guard.evaluate(ev)
                    n.pool.add(Candidate(
                        entity_id=ac.entity_id, alias_id=None, family_id=None,
                        generation_channels={"abbrev"},
                        channel_scores={"abbrev": (_CHANNEL_BASE["abbrev"]
                                                   + 0.3 * ac.score)
                                        * verdict.score_factor},
                        is_exact=False, retrieval_pass=2,
                        commit_blocked=verdict.blocked_reason,
                        provenance={"evidence": ev.as_dict(),
                                    "guard": list(verdict.reasons)},
                    ))
                pass2 = True
                n.pass2_applied = True
                hit_span = path.core_span
                break
            if hit_span is not None:
                # union of Pass-2 channels on the same proposal (§21.6)
                dense_enrich(hit_span, _context_window(text, hit_span, 30))
            elif options.get("detect_unregistered_mentions") \
                    and any("가" <= c <= "힣" for c in token):
                # open-world span proposals are Level C and stay behind the
                # feature flag (§19.1 default off; §6: 범용 명사 인식은 비목표)
                core_span = paths[-1].core_span
                dense_enrich(core_span,
                             _context_window(text, core_span, 30))
        if pass2:
            trace["pass2_executed"] = True  # at most once per request
            trace["dense_queries"] = dense_queries
            for n in nodes.values():
                if n.pass2_applied:
                    _fuse(n, snapshot, text, context, mode)

        # ---- conditional cross-encoder rerank (§22.3-22.4, V3 stage) ----
        if snapshot.reranker is not None:
            if _past_deadline("rerank"):
                trace["drops"].append("deadline_rerank")
                # rerank only re-scores candidates it never removes (INV-010),
                # so skipping it leaves the answer whole but less separated —
                # reported, and not counted as a cut generation stage
            else:
                degraded |= _rerank(nodes, snapshot, text, context, mode,
                                    policy, trace)

    # ---- decisions + response assembly ----
    ordered = sorted(nodes.values(), key=lambda n: (n.core_span[0],
                                                    -(n.core_span[1] - n.core_span[0])))
    primary_spans = _select_primary(ordered)

    mentions = []
    return_all = options.get("return_all_mentions", False)
    return_features = options.get("return_features", False)
    max_set = options.get("max_prediction_set", policy.candidate_budget.max_prediction_set)
    included = [n for n in ordered
                if return_all or n.core_span in primary_spans]
    for i, n in enumerate(included):
        m = _mention_response(n, i, snapshot, omap, text, mode, max_set,
                              return_features,
                              options.get("return_eval_trace", False),
                              generation_cutoff)
        m["primary"] = n.core_span in primary_spans
        if n.pool.truncated or n.pool.exact_overflow:
            degraded = True
        mentions.append(m)

    # REQ-BUD-001 asks for the omitted stage to be *exposed*, not only for a
    # boolean. The reasons were already being collected and then dropped on
    # the floor with the internal trace, so a consumer could see that
    # something had been cut and never what.
    limits = list(dict.fromkeys(trace["drops"]))

    resp = {
        "snapshot": {
            "glossary_id": snapshot.glossary.glossary_id,
            "glossary_version": snapshot.glossary_version,
            "snapshot_id": snapshot.snapshot_id,
            # §27.5: null on symbolic-only (V1) snapshots
            "model_bundle_version": snapshot.manifest.get("entity_encoder_hash"),
        },
        "mode": mode,
        "degraded": degraded,
        "limits": limits,
        "mentions": mentions,
    }
    if deadline_ms:
        # what the budget actually bought, whether or not it was exceeded: a
        # deadline that silently changed the answer would be worse than none
        resp["deadline"] = {
            "budget_ms": deadline_ms,
            "elapsed_ms": round(1000 * (_time.perf_counter() - _t0), 3),
            "exceeded": bool(deadline_skipped),
            "skipped_stages": list(deadline_skipped),
        }
    if options.get("return_trace"):
        resp["trace"] = trace
    if metrics is not None:
        metrics.record_resolve(mode, 1000 * (_time.perf_counter() - _t0),
                               resp, trace)
    return resp


def _rerank(nodes, snapshot: Snapshot, text: str, context: dict, mode: str,
            policy, trace: dict) -> bool:
    """Conditional cross-encoder pass (§22.4): only multi-sense mentions with
    a thin margin, under the pair budget (§31.1). Scores merge into fusion
    as evidence — candidates are never removed (INV-010)."""
    from .dense import entity_profile_text

    pairs_used = 0
    degraded = False
    for n in nodes.values():
        cands = [c for c in n.pool.all_candidates()
                 if c.calibrated_probability is not None]
        if len({c.entity_id for c in cands}) < 2:
            continue
        ranked = sorted(cands, key=lambda c: -(c.calibrated_probability or 0))
        top_p = ranked[0].calibrated_probability or 0
        second_p = ranked[1].calibrated_probability or 0
        if top_p >= policy.resolve_threshold \
                and top_p - second_p >= policy.margin_threshold:
            continue  # already decisive; no rerank needed
        budget_left = policy.max_cross_encoder_pairs - pairs_used
        if budget_left <= 0:
            trace["drops"].append("cross_encoder_budget")
            degraded = True  # INV-013
            break
        batch = ranked[: min(policy.max_rerank_candidates, budget_left)]
        window = _context_window(text, n.core_span, 60)
        pairs = []
        for c in batch:
            ent = snapshot.glossary.entity(c.entity_id)
            pairs.append((window, entity_profile_text(ent) if ent
                          else c.entity_id))
        scores = snapshot.reranker.score_pairs(pairs)
        pairs_used += len(pairs)
        for c, s in zip(batch, scores):
            c.provenance["xenc"] = s
        n.pass2_applied = True
        _fuse(n, snapshot, text, context, mode)
    trace["cross_encoder_pairs"] = pairs_used
    return degraded


def _paths_for(snapshot: Snapshot, text: str, token: str,
               span: tuple[int, int]):
    """The shared typed decomposition of one raw token (VARIANTS_PLAN M1)."""
    return segment_token(token, span, snapshot.fst,
                         left_context=text[max(0, span[0] - 6):span[0]])


def _guard_for(snapshot, node, channel: str, transform_cost: float):
    """Guard verdict for evidence a channel produced on ``node``'s core span.

    Channels that do not carry a :class:`StructuralPath` of their own still
    have to answer for the decomposition the node was built from, or they
    become a way around the guard.

    Either origin will do. A node the exact channel opened records its tail
    on the proposal rather than as a path, and reading only the path let a
    Level B candidate ride onto an exact node's span unguarded — dense
    proposing ORG_MSIT inside `한국전력공사노조` while the tail says the
    surface is a different organisation. Which channel found the *core* does
    not change what the tail means; only the channel asking to commit does,
    and that is what :attr:`MatchEvidence.level_a` already decides.
    """
    if node.path is not None:
        ev = MatchEvidence.from_path(channel, node.path,
                                     transform_cost=transform_cost)
    elif node.proposal is not None and node.proposal.best_tail is not None:
        t = node.proposal.best_tail
        ev = MatchEvidence(
            channel=channel, path_kind=t.kind, core_surface=node.surface,
            core_span=node.core_span, full_span=node.proposal.full_span,
            transform_cost=transform_cost, residual_kind=t.residual_kind,
            full_identity=t.full_identity, relation=t.relation,
            particles=t.particles, grammatical=t.grammatical,
            tail_stripped=bool(t.residual or t.particles or t.latin_tail),
        )
    else:
        return GuardVerdict()
    return snapshot.guard.evaluate(ev)


def _add_fuzzy(node: MentionNode, fc, guard, path) -> None:
    node.sources.add(fc.channel)
    if path is not None and node.path is None:
        node.path = path
    base = _CHANNEL_BASE[fc.channel]
    prov = {"fuzzy_cost": fc.cost}
    blocked = None
    factor = 1.0
    if path is not None:
        ev = MatchEvidence.from_path(fc.channel, path, transform_cost=fc.cost)
        verdict = guard.evaluate(ev)
        blocked, factor = verdict.blocked_reason, verdict.score_factor
        prov["evidence"] = ev.as_dict()
        if verdict.reasons:
            prov["guard"] = list(verdict.reasons)
    node.pool.add(Candidate(
        entity_id=fc.binding.entity_id,
        alias_id=fc.binding.alias_id,
        family_id=fc.binding.family_id,
        generation_channels={fc.channel},
        channel_scores={fc.channel: max(0.1, base - fc.cost) * factor},
        surface_transform_cost=fc.cost,
        is_exact=False,
        commit_blocked=blocked,
        provenance=prov,
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
        entity = snapshot.glossary.entity(cand.entity_id)
        context_bonus = 0.0
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
                context_bonus = 0.15 * min(1.0, overlap / 4.0)
        doclocal_boost = (0.20 if cand.entity_id in node.doc_local_entities
                          else 0.0)  # §18.3
        scope_adj = _scope_adjust(cand, snapshot, context, node)
        xenc = cand.provenance.get("xenc")
        # feature vector (§23.2): always computed; heuristic or learned
        # fusion consumes it, and it exports for fusion training (§48.3)
        cand.features = {
            "exact_score": max(
                (v for ch, v in cand.channel_scores.items()
                 if ch in ("exact", "normalized")), default=0.0),
            "doc_local_score": cand.channel_scores.get("doc_local", 0.0),
            "fuzzy_score": max(
                (v for ch, v in cand.channel_scores.items()
                 if ch in ("jamo", "keyboard")), default=0.0),
            "abbrev_score": cand.channel_scores.get("abbrev", 0.0),
            "dense_score": cand.channel_scores.get("dense", 0.0),
            "context_overlap": round(context_bonus, 4),
            "scope_adj": round(scope_adj, 4),
            "doc_local_boost": doclocal_boost,
            "xenc": xenc if xenc is not None else 0.5,
            "transform_cost": cand.surface_transform_cost,
            "is_exact": 1.0 if cand.is_exact else 0.0,
            "single_sense": (1.0 / max(1, n_exact)) if cand.is_exact else 0.0,
        }
        score = base + context_bonus + doclocal_boost + scope_adj
        if xenc is not None:
            score += 0.25 * (xenc - 0.5)  # cross-encoder evidence (§22.3)
        if snapshot.fusion is not None:
            # learned fusion (V2, §23): logistic over the feature vector
            cand.ranking_score = snapshot.fusion.predict(cand.features)
        else:
            cand.ranking_score = round(score, 4)
        if mode == "fast" or cand.drop_reason is not None:
            continue
        if snapshot.calibrator is not None:
            # finetuned tenant calibrator (§48.3): Platt-scaled marginal
            cand.calibrated_probability = \
                snapshot.calibrator.calibrate_marginal(cand.ranking_score)
        elif snapshot.fusion is not None:
            # fusion output is a logistic probability; conservative cap
            cand.calibrated_probability = round(
                min(0.95, max(0.02, cand.ranking_score)), 3)
        else:
            # global conservative calibrator (heuristic placeholder, §48.1):
            # a sense-count prior scaled by surface-path quality, shifted by
            # context/scope evidence. Marginal per candidate, never
            # normalized across the prediction set (§7.12/INV-019).
            if cand.is_exact:
                prior = 0.92 if n_exact <= 1 else max(0.15, 0.80 / n_exact)
                prior -= min(0.2, cand.surface_transform_cost)
                # surface-path quality gates the prior hard: SOFT boundaries
                # and UNKNOWN residuals must not reach commit thresholds on
                # the prior alone (§4.6 확정은 보수적으로, §16.5). Quality comes
                # from the exact/normalized channels only — merged fuzzy or
                # Pass-2 evidence must not restore a weak surface path.
                exact_base = max(
                    (v for ch, v in cand.channel_scores.items()
                     if ch in ("exact", "normalized")), default=0.0)
                quality = min(1.0, exact_base / _CHANNEL_BASE["exact"])
                prior *= 0.35 + 0.65 * quality
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
    binding = snapshot.glossary.binding(cand.alias_id)
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


def _eval_trace(node: MentionNode, ranked: list, members: list,
                set_truncated: bool) -> dict:
    """Pre-threshold view of one mention, for evaluation only (M0 item 3).

    Reporting only what survived thresholding hides the two failures that
    matter most when a number moves: a gold candidate that was generated but
    ranked below the cut, and a pool that was truncated before ranking ever
    ran. Neither is visible in ``prediction_set``. This is diagnostic output,
    never an input to any decision.
    """
    member_ids = {c.entity_id for c in members}
    return {
        "pool": {
            "exact": len(node.pool.exact),
            "non_exact": len(node.pool.non_exact),
            "truncated": node.pool.truncated,
            "non_exact_dropped": node.pool.stats.non_exact_truncated,
            "exact_overflow": node.pool.exact_overflow,
        },
        "prediction_set_truncated": set_truncated,
        "sources": sorted(node.sources),
        # every candidate in rank order, including those the thresholds cut:
        # rank is pre-threshold, so a gold entity at rank 3 is distinguishable
        # from a gold entity that was never generated at all
        "ranked": [
            {"rank": i, "entity_id": c.entity_id,
             "calibrated_probability": c.calibrated_probability,
             "ranking_score": c.ranking_score,
             "channels": sorted(c.generation_channels),
             "in_prediction_set": c.entity_id in member_ids,
             "commit_blocked": c.commit_blocked,
             "evidence": c.provenance.get("evidence")}
            for i, c in enumerate(ranked)
        ],
    }


_IDENTITY_LABEL = {SAME: "SAME_AS_CORE", DISTINCT: "DISTINCT_FROM_CORE",
                   "UNKNOWN": "UNKNOWN"}


def _tail_of(node: MentionNode):
    """The typed tail this mention was read with, from either channel.

    The exact path records it on its proposal, a Level B channel on the
    structural path it accepted. Both are the same :mod:`ktrf.segmentation`
    analysis, so one reader serves both (M1).
    """
    if node.proposal is not None:
        best = node.proposal.best_tail
        prefix = node.proposal.prefix
        pfx = ((prefix["span"][0], prefix.get("kind", "")) if prefix
               else (None, ""))
        if best is not None:
            return (best.residual, best.governing_class, best.full_identity,
                    best.relation, *pfx)
    if node.path is not None:
        pth = node.path
        pfx = ((pth.prefix_span[0], pth.prefix_kind) if pth.prefix_span
               else (None, ""))
        return (pth.residual, pth.governing_class, pth.full_identity,
                pth.relation, *pfx)
    return None


def _surface_record(node: MentionNode, snapshot: Snapshot, omap: OffsetMap,
                    text: str, entity_ids: list[str]) -> dict | None:
    """Separate what the core links to from what the whole surface denotes.

    Returns ``None`` when the core *is* the whole surface — the common case,
    where there is nothing to separate. Otherwise the caller gets both spans
    and an explicit verdict, so ``full_span`` can no longer be mistaken for
    the entity's extent (VARIANTS_PLAN §2 invariant ②).
    """
    tail = _tail_of(node)
    if tail is None:
        return None
    (residual, governing_class, identity, relation, prefix_start,
     prefix_kind) = tail
    cs, ce = node.core_span
    start = prefix_start if prefix_start is not None else cs
    end = ce + len(residual)
    if (start, end) == (cs, ce):
        return None  # core and surface coincide

    core_link = {"span": omap.span_dict(cs, ce), "surface": text[cs:ce],
                 "relation": relation}
    full = {"span": omap.span_dict(start, end), "surface": text[start:end],
            "identity": _IDENTITY_LABEL.get(identity, "UNKNOWN")}
    if prefix_kind:
        # §16.6: `전 한전` denotes 한전 at another time, and VARIANTS_PLAN §2
        # calls identifying the whole with the core *conditional* here. Say
        # which modifier widened the surface rather than assert bare identity.
        full["prefix_kind"] = prefix_kind
    if governing_class:
        # the class the verdict came from, not merely the last one: a
        # response whose tail_class and identity disagree is worse than
        # one that omits it (`장과` heads on NAME_PART but means a person)
        full["tail_class"] = governing_class

    # invariant ③: a *registered* relation outranks anything we infer. When
    # the glossary declares 한전 + 노조 -> ORG_KEPCO_UNION, that target is the
    # answer for the full surface; the parent stays out of it either way.
    if residual and snapshot.compositions:
        for eid in entity_ids:
            comp = snapshot.compositions.get((eid, residual))
            if comp is None:
                continue
            ent = snapshot.glossary.entity(comp.target_entity_id)
            full["composes_to"] = {
                "entity_id": comp.target_entity_id,
                "canonical": ent.canonical if ent else None,
                "from_entity_id": eid,
                "relation_id": comp.relation_id,
            }
            break
    return {"core_link": core_link, "full_surface": full}


def _mention_response(node: MentionNode, idx: int, snapshot: Snapshot,
                      omap: OffsetMap, text: str, mode: str,
                      max_set: int, return_features: bool = False,
                      return_eval_trace: bool = False,
                      generation_cutoff: int | None = None) -> dict:
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

    # M2: `span` is the core, `full_span` the raw token. Neither says whether
    # the whole surface means the same thing as the core, and a consumer that
    # highlights `full_span` on 금감원장 overcommits the organisation onto a
    # person. This record answers that question explicitly.
    rec = _surface_record(
        node, snapshot, omap, text,
        [c.entity_id for c in sorted(
            cands, key=lambda c: (-(c.calibrated_probability or 0.0),
                                  c.entity_id))],
    )
    if rec:
        m.update(rec)

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
    # "always offer at least the top candidate" is a usability contract, not
    # the conformal one: this member is in the set because the caller needs an
    # answer, not because the quantile admitted it. Adding it cannot lower
    # coverage, but it does mean the set is no longer the conformal set, and
    # anything measuring set size has to be able to tell (review P0-3).
    forced_top = top is not None and top not in members
    if forced_top:
        members = [top] + members
    # truncation drops tail members from a conformal set — the coverage
    # guarantee no longer holds for a cut set, and we must say so instead
    # of exposing set_confidence as if it were still valid (§25.2)
    set_truncated = len(members) > max_set
    members = members[:max_set]

    kb_member = None
    # §24.3: KB_MISSING joins the set only when no candidate clears the
    # context-compatibility bar AND there is no exact alias evidence
    # (an exact match proves the concept exists in this glossary).
    if (top_p or 0) < 0.6 and not any(c.is_exact for c in cands):
        kb_p = round(min(0.9, max(0.05, 0.8 - (top_p or 0))), 3)
        kb_member = {"kind": "KB_MISSING", "calibrated_probability": kb_p}

    # A global budget can stop a channel partway through the text, and
    # `max_fuzzy_windows` is exhausted from about 400 characters — after which
    # every remaining mention is offered to the exact channel alone. Report
    # that on the mention (below); it is real and a consumer should see it.
    bounded = (generation_cutoff is not None
               and node.core_span[0] >= generation_cutoff)

    # §27.8/REQ-API-005 downgrades a mention whose candidate *generation* was
    # incomplete. Pool truncation is that. A missing fuzzy pass is not, when
    # the answer rests on an exact match: Level A is complete by construction
    # and fuzzy is additive recall, so letting a capped Level B channel veto a
    # Level A commit inverts the layering.
    #
    # Measured rather than argued. Re-running these documents with the budget
    # lifted changed 0 of 207 decisions, while downgrading every mention past
    # the cutoff would have cost 26 of 31 commits at 3,200 characters. The
    # requirement is honoured where the cut channel is the one the answer
    # stands on, and nowhere else.
    node_degraded = (node.pool.truncated or node.pool.exact_overflow
                     or (bounded and not any(c.is_exact for c in cands)))

    set_members = []
    for c in members:
        member = {"kind": "ENTITY", "entity_id": c.entity_id,
                  "calibrated_probability": c.calibrated_probability,
                  "ranking_score": c.ranking_score,
                  "generation_channels": sorted(c.generation_channels),
                  "retrieval_pass": c.retrieval_pass}
        if c.commit_blocked:
            member["commit_blocked"] = c.commit_blocked
        if return_features:
            member["features"] = dict(c.features)  # fusion training export
        set_members.append(member)
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
        and top.commit_blocked is None  # VARIANTS_PLAN §2 ①②
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
    if set_truncated:
        m["prediction_set"]["truncated"] = True
        if calibrator is not None:
            m["prediction_set"]["coverage_valid"] = False
    if calibrator is not None and (not calibrator.split_disjoint
                                   or calibrator.split_basis == "row_fallback"):
        # Either the calibrator was fit without a disjoint split, or the rows
        # were known to be correlated and were split by row anyway. Both mean
        # set_confidence is a nominal level for every set it produces, cut or
        # not (§25.2).
        m["prediction_set"]["coverage_valid"] = False
    if calibrator is not None:
        # Disjointness is not the whole claim. A split by row index can be
        # perfectly disjoint and still put the same document on both sides,
        # which is the leak the guarantee actually rests on. Say which kind of
        # split produced this set instead of leaving a consumer to assume.
        m["prediction_set"]["coverage_basis"] = calibrator.split_basis
    if forced_top:
        m["prediction_set"]["forced_top"] = True
    if calibration_fallback:
        # REQ-CAL-002: group sample below n_min → pooled-quantile fallback
        m["prediction_set"]["calibration_fallback"] = True
    if node_degraded:
        m["degraded"] = True
    if bounded:
        # distinct from `degraded`: a channel was not offered this mention,
        # which a consumer should know even when the answer does not rest on
        # it. Reads alongside `generation_channels`.
        m["channels_bounded"] = True
    if return_eval_trace:
        m["eval_trace"] = _eval_trace(node, ranked, members, set_truncated)
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
            # among Level B nodes a better-supported core beats a longer one,
            # so an under-stripped span cannot shadow the analysed core. The
            # term is constant for exact nodes, whose order is unchanged.
            0.0 if n.pool.exact else -(_top_probability(n) or 0.0),
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
