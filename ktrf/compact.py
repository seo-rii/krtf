"""Short execution selections backed by one server-held occurrence request.

This adapter changes the response wire format only. It never executes actions
or authorizes an ambiguous candidate. Keep the request object on the server;
send its catalog and response schema to the model in an execution-only request.
Tenant, scope, request and current snapshot IDs must come from authenticated
host state, never from the model or untrusted request fields.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import time
from dataclasses import dataclass, field
from threading import Lock
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from .context import validate_llm_grounding
from .errors import KtrfApiError


def _reject(kind: str) -> dict:
    return {"valid": False, "violations": [{"kind": kind}], "selections": []}


def _identity(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KtrfApiError("INVALID_REQUEST", f"{name} must be a nonempty string")
    return value


def _occurrence_key(occurrence: dict) -> tuple:
    """Validate exact codepoint coordinates before using them as map keys."""
    if not isinstance(occurrence, dict):
        raise KtrfApiError("INVALID_REQUEST", "malformed occurrence")
    mention_id = _identity(occurrence.get("mention_id"), "mention_id")
    coordinates = []
    for name in ("core_span", "full_span"):
        span = occurrence.get(name)
        if (not isinstance(span, dict) or set(span) != {"start", "end"}
                or any(type(span[k]) is not int for k in ("start", "end"))
                or not 0 <= span["start"] < span["end"]):
            raise KtrfApiError("INVALID_REQUEST", "invalid occurrence span")
        coordinates.extend((span["start"], span["end"]))
    cs, ce, fs, fe = coordinates
    if not fs <= cs < ce <= fe:
        raise KtrfApiError("INVALID_REQUEST", "core span must lie in full span")
    return mention_id, cs, ce, fs, fe


@dataclass
class _Attempt:
    lock: Lock = field(default_factory=Lock)
    consumed: bool = False


@dataclass(frozen=True, slots=True)
class CompactExecutionRequest:
    """Immutable authority plus an atomic, single-attempt runtime latch.

    Create with :func:`create_compact_request`. ``catalog`` and
    ``response_schema`` return fresh JSON-compatible values. ``consume``
    accepts ``{"selections": [{"ref": ..., "entity_id": ...}]}`` and returns
    full occurrence selections only when the whole response is valid.

    Every consume attempt closes the request, including malformed output and
    mismatched host context. Retry with a newly created request if necessary.
    Retain this exact object for its lifetime: rebuilding or copying state does
    not provide cross-process replay protection. Hosts must atomically persist
    consumption if requests can move between workers. A valid null/empty
    selection is abstention; downstream actions still need host authorization
    and their own durable idempotency/transaction handling.
    """

    tenant_id: str
    scope_id: str
    request_id: str
    snapshot_id: str
    document_hash: str
    _issued_at: float = field(repr=False)
    _expires_at: float = field(repr=False)
    _clock: Callable[[], float] = field(repr=False, compare=False)
    _pack_json: str = field(repr=False)
    _bindings: Mapping[str, str] = field(repr=False)
    _catalog_json: str = field(repr=False)
    _attempt: _Attempt = field(default_factory=_Attempt, repr=False,
                               compare=False)

    @property
    def catalog(self) -> list[dict]:
        """Selectable resolved occurrences, including their semantic notes."""
        return json.loads(self._catalog_json)

    @property
    def response_schema(self) -> dict:
        """The short wire format; server validation remains authoritative."""
        return {
            "type": "object", "additionalProperties": False,
            "required": ["selections"], "properties": {"selections": {
                "type": "array", "maxItems": len(self._bindings),
                "items": {"type": "object", "additionalProperties": False,
                          "required": ["ref", "entity_id"], "properties": {
                              "ref": {"type": "string"},
                              "entity_id": {"type": ["string", "null"]}}}}}}

    def consume(self, llm_output: dict, *, document_text: str,
                snapshot_id: str, tenant_id: str, scope_id: str,
                request_id: str) -> dict:
        """Validate once using current trusted host identity and document.

        ``clock`` is the trusted clock captured during creation, not a model
        timestamp. Expiration is inclusive; clock rollback/nonfinite values
        fail closed. Each response is checked against the immutable original
        pack with ``purpose='execution', execution_contract='occurrence_v1'``.
        """
        with self._attempt.lock:
            if self._attempt.consumed:
                return _reject("compact_request_consumed")
            self._attempt.consumed = True
            now = self._clock()
            if (type(now) not in (int, float) or not math.isfinite(now)
                    or now < self._issued_at or now >= self._expires_at):
                return _reject("compact_request_expired")
            if (tenant_id != self.tenant_id or scope_id != self.scope_id
                    or request_id != self.request_id):
                return _reject("compact_request_context_mismatch")
            if snapshot_id != self.snapshot_id:
                return _reject("compact_snapshot_mismatch")
            if (not isinstance(document_text, str)
                    or hashlib.sha256(document_text.encode("utf-8")).hexdigest()
                    != self.document_hash):
                return _reject("compact_document_mismatch")
            if (not isinstance(llm_output, dict)
                    or set(llm_output) != {"selections"}
                    or not isinstance(llm_output["selections"], list)
                    or len(llm_output["selections"]) > len(self._bindings)):
                return _reject("malformed_compact_output")
            expanded = []
            seen = set()
            for selection in llm_output["selections"]:
                if (not isinstance(selection, dict)
                        or set(selection) != {"ref", "entity_id"}
                        or not isinstance(selection["ref"], str)
                        or (selection["entity_id"] is not None
                            and (not isinstance(selection["entity_id"], str)
                                 or not selection["entity_id"].strip()))):
                    return _reject("malformed_compact_selection")
                ref = selection["ref"]
                if ref not in self._bindings:
                    return _reject("unknown_compact_reference")
                if ref in seen:
                    return _reject("duplicate_compact_reference")
                seen.add(ref)
                binding = json.loads(self._bindings[ref])
                binding["entity_id"] = selection["entity_id"]
                expanded.append(binding)
            result = validate_llm_grounding(
                {"selections": expanded}, json.loads(self._pack_json),
                purpose="execution", execution_contract="occurrence_v1")
            return {**result, "selections": expanded if result["valid"] else []}


def create_compact_request(
    context_pack: dict, *, document_text: str, tenant_id: str, scope_id: str,
    request_id: str, ttl_seconds: float = 60,
    target_occurrences: Sequence[dict] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> CompactExecutionRequest:
    """Freeze a trusted pack and create fresh, opaque occurrence references.

    ``target_occurrences`` optionally limits selectable occurrences to exact
    ``mention_id``, ``core_span``, ``full_span`` triples from the resolver.
    Unresolved or omitted targets produce no choice, never an authorization.
    Use a separate automation request, not incidental IDs from a QA answer.
    The host authenticates pack provenance, tenant and scope before this call.
    A request is process-local and expires according to its trusted clock.
    """
    tenant_id = _identity(tenant_id, "tenant_id")
    scope_id = _identity(scope_id, "scope_id")
    request_id = _identity(request_id, "request_id")
    if (type(ttl_seconds) not in (int, float) or not math.isfinite(ttl_seconds)
            or ttl_seconds <= 0):
        raise KtrfApiError("INVALID_REQUEST", "ttl_seconds must be finite and positive")
    issued_at = clock()
    if (type(issued_at) not in (int, float) or not math.isfinite(issued_at)
            or not math.isfinite(issued_at + ttl_seconds)):
        raise KtrfApiError("INVALID_REQUEST", "clock must return a finite timestamp")
    if not isinstance(document_text, str):
        raise KtrfApiError("INVALID_REQUEST", "document_text must be a string")
    # JSON strings and a mapping proxy avoid retaining aliases into mutable
    # caller dictionaries. The only mutable state is the per-request latch.
    try:
        pack_json = json.dumps(context_pack, ensure_ascii=False, allow_nan=False)
        pack = json.loads(pack_json)
    except (TypeError, ValueError) as exc:
        raise KtrfApiError("INVALID_REQUEST", "context_pack must be JSON-compatible") from exc
    if (not isinstance(pack, dict)
            or pack.get("execution_contract") != "occurrence_v1"
            or not isinstance(pack.get("resolved_terms"), list)
            or not isinstance(pack.get("ambiguous_mentions"), list)
            or not isinstance(pack.get("snapshot"), dict)):
        raise KtrfApiError("INVALID_REQUEST", "an occurrence-bound context pack is required")
    snapshot_id = _identity(pack["snapshot"].get("snapshot_id"), "snapshot_id")
    document_hash = hashlib.sha256(document_text.encode("utf-8")).hexdigest()
    if pack.get("document_hash") != document_hash:
        raise KtrfApiError("INVALID_REQUEST", "context pack document hash mismatch")
    if target_occurrences is not None:
        if (not isinstance(target_occurrences, (list, tuple))
                or any(not isinstance(t, dict) or set(t) != {
                    "mention_id", "core_span", "full_span"} for t in target_occurrences)):
            raise KtrfApiError("INVALID_REQUEST", "invalid target occurrences")
        targets = {_occurrence_key(t) for t in target_occurrences}
    else:
        targets = None
    bindings = {}
    catalog = []
    seen = set()
    for card in pack["resolved_terms"]:
        if (not isinstance(card, dict) or not isinstance(card.get("resolution"), dict)
                or not isinstance(card.get("mentions"), list)):
            raise KtrfApiError("INVALID_REQUEST", "malformed resolved card")
        entity_id = _identity(card.get("entity_id"), "entity_id")
        if card["resolution"].get("degraded"):
            continue
        for mention in card["mentions"]:
            key = _occurrence_key(mention)
            if key[-1] > len(document_text):
                raise KtrfApiError("INVALID_REQUEST", "occurrence lies outside document")
            if targets is not None and key not in targets:
                continue
            binding = {
                "document_hash": document_hash, "snapshot_id": snapshot_id,
                "surface": _identity(mention.get("surface"), "surface"),
                "mention_id": mention["mention_id"],
                "core_span": mention["core_span"], "full_span": mention["full_span"],
                "entity_id": entity_id,
            }
            checked = validate_llm_grounding(
                {"selections": [binding]}, pack, purpose="execution",
                execution_contract="occurrence_v1")
            if not checked["valid"]:
                raise KtrfApiError("INVALID_REQUEST", "conflicting occurrence authority")
            if key in seen:
                continue
            seen.add(key)
            ref = secrets.token_urlsafe(24)
            while ref in bindings:
                ref = secrets.token_urlsafe(24)
            bindings[ref] = json.dumps(binding, ensure_ascii=False)
            catalog.append({"ref": ref, "entity_id": entity_id,
                            "canonical": card.get("canonical"),
                            "short_definition": card.get("short_definition"),
                            "occurrence": mention})
    return CompactExecutionRequest(
        tenant_id, scope_id, request_id, snapshot_id, document_hash,
        issued_at, issued_at + ttl_seconds, clock, pack_json,
        MappingProxyType(bindings), json.dumps(catalog, ensure_ascii=False))
