"""Line-delimited JSON-RPC sidecar over stdin/stdout (PLAN_PI.md §11).

Run as ``python -m ktrf.integrations.pi_stdio``. One JSON request per line
in, one JSON response per line out. No sockets, no ports: a host process
owns this child's lifetime.

Operating contract — the parts that matter for a host that must keep
working when terminology does not:

- **stdout carries protocol JSON only.** All diagnostics go to stderr, so a
  stray print can never corrupt the channel.
- **Fail-open.** Every handler error becomes an error *response*, not a
  crash; a malformed line is reported and the loop continues. A host that
  loses this sidecar should degrade to no terminology context, never fail
  the user's request.
- **Bounded work.** Requests over ``MAX_REQUEST_BYTES`` are rejected before
  parsing; text inputs are capped by the snapshot's own input limit.
- **No neural imports.** This runtime is CPU-symbolic by default; a dense
  encoder is only loaded if the host explicitly asks for one.

Methods: ``initialize``, ``load_layers``, ``resolve``, ``resolve_context``,
``lookup``, ``explain``, ``propose_term``, ``validate_proposal``,
``route_proposal``, ``approve_proposal``, ``list_proposals``, ``health``,
``shutdown``.
"""

from __future__ import annotations

import json
import sys
import time
import traceback

PROTOCOL_VERSION = "1"
MAX_REQUEST_BYTES = 4 * 1024 * 1024


def _log(*args) -> None:
    print(*args, file=sys.stderr, flush=True)


class PiRuntime:
    """Stateful handler set; one instance per host session."""

    def __init__(self):
        self.snapshot = None
        self.layer_result = None
        self.proposals = None
        self.started_at = time.time()
        self.requests = 0

    # ------------------------------------------------------------ setup
    def initialize(self, params: dict) -> dict:
        from ..registry.proposals import TermAdmissionPolicy, TermProposalStore

        policy_args = params.get("admission_policy") or {}
        known = set(TermAdmissionPolicy.__dataclass_fields__)
        unknown = set(policy_args) - known
        if unknown:
            raise ValueError(f"unknown admission_policy keys: "
                             f"{sorted(unknown)}")
        self.proposals = TermProposalStore(
            policy=TermAdmissionPolicy(**policy_args))
        return {"protocol_version": PROTOCOL_VERSION,
                "capabilities": sorted(HANDLERS),
                "neural": False}

    def load_layers(self, params: dict) -> dict:
        """params: {sources: {scope: path|doc}, trusted_scopes: [...],
        encoder: "onnx:<dir>" | null, run_conformance: bool}"""
        from ..registry.layers import compile_layered_snapshot, load_term_layers

        sources = params.get("sources") or {}
        trusted = params.get("trusted_scopes")
        layers = load_term_layers(
            sources, set(trusted) if trusted is not None else None)
        encoder = None
        if params.get("encoder"):
            from ..encoders import load_encoder  # optional dependency
            encoder = load_encoder(params["encoder"])
        snapshot, result = compile_layered_snapshot(
            layers, glossary_id=params.get("glossary_id", "layered"),
            version=str(params.get("version", "1")),
            run_conformance=bool(params.get("run_conformance", False)),
            encoder=encoder)
        self.snapshot = snapshot
        self.layer_result = result
        return {
            "snapshot_id": snapshot.snapshot_id,
            "entities": len(snapshot.glossary.entities),
            "bindings": len(snapshot.glossary.alias_bindings),
            "layers": snapshot.manifest.get("layers", []),
            "shadowed": result.shadowed,
            "conflicts": result.conflicts,
            "skipped_layers": result.skipped_layers,
        }

    # ---------------------------------------------------------- queries
    def _require_snapshot(self):
        if self.snapshot is None:
            raise ValueError("no snapshot loaded; call load_layers first")
        return self.snapshot

    def resolve(self, params: dict) -> dict:
        from ..resolver import resolve as _resolve

        snapshot = self._require_snapshot()
        return _resolve(snapshot, params["text"],
                        mode=params.get("mode", "commit"),
                        options=params.get("options") or
                        {"return_all_mentions": True})

    def resolve_context(self, params: dict) -> dict:
        """resolve + context pack + rendered fragment in one round trip."""
        from ..context import ContextPolicy, prepare_llm_context

        snapshot = self._require_snapshot()
        policy_args = params.get("context_policy") or {}
        known = set(ContextPolicy.__dataclass_fields__)
        unknown = set(policy_args) - known
        if unknown:
            raise ValueError(f"unknown context_policy keys: "
                             f"{sorted(unknown)}")
        prepared = prepare_llm_context(
            snapshot, params["text"], query=params.get("query"),
            mode=params.get("mode", "commit"),
            context_policy=ContextPolicy(**policy_args))
        return {"pack": prepared.context_pack,
                "prompt_fragment": prepared.prompt_fragment,
                "policy_fragment": prepared.policy_fragment}

    def lookup(self, params: dict) -> dict:
        from ..explain import lookup_surface

        return lookup_surface(self._require_snapshot(), params["surface"])

    def explain(self, params: dict) -> dict:
        from ..explain import explain_resolution

        return explain_resolution(self._require_snapshot(), params["text"],
                                  surface=params.get("surface"),
                                  occurrence=int(params.get("occurrence", 1)),
                                  mode=params.get("mode", "commit"))

    # -------------------------------------------------------- proposals
    def _require_proposals(self):
        if self.proposals is None:
            raise ValueError("call initialize first")
        return self.proposals

    def propose_term(self, params: dict) -> dict:
        from ..registry.proposals import EvidenceRef

        store = self._require_proposals()
        evidence = tuple(
            EvidenceRef(**{k: v for k, v in e.items()
                           if k in EvidenceRef.__dataclass_fields__})
            for e in params.get("evidence_refs") or [])
        proposal = store.submit(
            surface=params["surface"], canonical=params["canonical"],
            short_definition=params.get("short_definition", ""),
            requested_scope=params.get("scope", "session"),
            origin=params.get("origin", "llm_proposal"),
            evidence_refs=evidence,
            aliases=tuple(params.get("aliases") or ()),
            model_confidence=params.get("model_confidence"),
            session_id=params.get("session_id", "default"))
        return proposal.to_dict()

    def validate_proposal(self, params: dict) -> dict:
        store = self._require_proposals()
        return store.validate(params["proposal_id"],
                              self.snapshot).to_dict()

    def route_proposal(self, params: dict) -> dict:
        store = self._require_proposals()
        return store.route(
            params["proposal_id"],
            project_trusted=bool(params.get("project_trusted", False)),
            evidence_count=int(params.get("evidence_count", 0)),
            distinct_sessions=int(params.get("distinct_sessions", 0))
        ).to_dict()

    def approve_proposal(self, params: dict) -> dict:
        store = self._require_proposals()
        return store.approve(params["proposal_id"],
                             params.get("approver", "user")).to_dict()

    def list_proposals(self, params: dict) -> dict:
        store = self._require_proposals()
        return {"proposals": [p.to_dict() for p in
                              store.list(status=params.get("status"),
                                         scope=params.get("scope"))],
                "audit_entries": len(store.audit)}

    # ------------------------------------------------------------ misc
    def health(self, params: dict) -> dict:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "uptime_seconds": round(time.time() - self.started_at, 2),
            "requests": self.requests,
            "snapshot_id": (self.snapshot.snapshot_id if self.snapshot
                            else None),
            "conflicts": len(self.layer_result.conflicts)
            if self.layer_result else 0,
        }

    def shutdown(self, params: dict) -> dict:
        return {"ok": True}


HANDLERS = {
    "initialize": PiRuntime.initialize,
    "load_layers": PiRuntime.load_layers,
    "resolve": PiRuntime.resolve,
    "resolve_context": PiRuntime.resolve_context,
    "lookup": PiRuntime.lookup,
    "explain": PiRuntime.explain,
    "propose_term": PiRuntime.propose_term,
    "validate_proposal": PiRuntime.validate_proposal,
    "route_proposal": PiRuntime.route_proposal,
    "approve_proposal": PiRuntime.approve_proposal,
    "list_proposals": PiRuntime.list_proposals,
    "health": PiRuntime.health,
    "shutdown": PiRuntime.shutdown,
}


def handle_request(runtime: PiRuntime, request: dict) -> dict:
    """Dispatch one parsed request to a response dict (never raises)."""
    rid = request.get("id")
    method = request.get("method")
    handler = HANDLERS.get(method)
    if handler is None:
        return {"id": rid, "error": {"code": "UNKNOWN_METHOD",
                                     "message": f"unknown method {method!r}",
                                     "known": sorted(HANDLERS)}}
    runtime.requests += 1
    t0 = time.perf_counter()
    try:
        result = handler(runtime, request.get("params") or {})
        return {"id": rid, "result": result,
                "elapsed_ms": round(1000 * (time.perf_counter() - t0), 2)}
    except Exception as exc:
        code = getattr(exc, "code", None) or type(exc).__name__
        _log(f"[ktrf] {method} failed: {exc}")
        _log(traceback.format_exc())
        return {"id": rid, "error": {"code": code, "message": str(exc)}}


def _force_utf8(stream):
    """Protocol streams are UTF-8 regardless of the host locale.

    Without this the sidecar decodes Korean payloads with the platform
    codepage (cp949 on a Korean Windows host) and produces surrogates that
    cannot be re-encoded — the process would answer every request with an
    encoding error.
    """
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # already wrapped / not a TextIO
        pass
    return stream


def serve(stdin=None, stdout=None) -> int:
    """Read requests until EOF or ``shutdown``; returns an exit code."""
    stdin = _force_utf8(stdin or sys.stdin)
    stdout = _force_utf8(stdout or sys.stdout)
    runtime = PiRuntime()
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        if len(line.encode("utf-8", "ignore")) > MAX_REQUEST_BYTES:
            response = {"id": None,
                        "error": {"code": "INPUT_TOO_LARGE",
                                  "message": f"request exceeds "
                                             f"{MAX_REQUEST_BYTES} bytes"}}
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")
        except (ValueError, TypeError) as exc:
            # a malformed line is isolated: report and keep serving
            stdout.write(json.dumps(
                {"id": None, "error": {"code": "MALFORMED_REQUEST",
                                       "message": str(exc)}},
                ensure_ascii=False) + "\n")
            stdout.flush()
            continue
        response = handle_request(runtime, request)
        stdout.write(json.dumps(response, ensure_ascii=False,
                                default=str) + "\n")
        stdout.flush()
        if request.get("method") == "shutdown":
            return 0
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(serve())
