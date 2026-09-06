"""Published JSON Schemas for KTRF's two output structures.

The review's diagnosis was that the same contract is partly reimplemented in
several places, so a change in one leaves the others behind — `core_link.span`
was added to the response and the chunk translator, the eval harness and the
context builder each learned about it separately, or not at all. A schema does
not stop that on its own. What it does is give the contract one written form
that can be checked against the code, so the two cannot drift apart in
silence.

Both schemas are closed on the objects that are contract
(`additionalProperties: false`), and deliberately open on the diagnostic
payloads — `trace`, `eval_trace`, member `features` — which exist to be read,
not to be depended on.

They ship as package data so a host can validate what it receives with its own
tooling, in its own language, without trusting this package to be honest about
its own output.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import KtrfApiError

_DIR = Path(__file__).parent
_CACHE: dict[str, dict] = {}

NAMES = ("context_pack", "resolve_response")


def schema_path(name: str) -> Path:
    if name not in NAMES:
        raise KtrfApiError("INVALID_REQUEST", f"unknown schema {name!r}",
                           details={"known": list(NAMES)})
    return _DIR / f"{name}.schema.json"


def load_schema(name: str) -> dict:
    """The schema itself, with no third-party dependency."""
    if name not in _CACHE:
        _CACHE[name] = json.loads(
            schema_path(name).read_text(encoding="utf-8"))
    return _CACHE[name]


def validate_against(document: dict, name: str) -> list[str]:
    """Check a document against a published schema; return the problems.

    Needs `jsonschema`, which KTRF does not depend on at runtime: a host that
    wants validation already has a validator, and one that does not should not
    pay for it. Raises :class:`KtrfApiError` when it is missing rather than
    returning "no problems" from a check that never ran.
    """
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise KtrfApiError(
            "INVALID_REQUEST",
            f"validating against the {name} schema needs the `jsonschema` "
            "package (pip install ktrf[dev]); the schema itself is available "
            "from load_schema() without it",
        ) from exc
    validator = jsonschema.Draft7Validator(load_schema(name))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: "
            f"{e.message}"
            for e in sorted(validator.iter_errors(document),
                            key=lambda e: list(e.absolute_path))]


def validate_resolve_response(response: dict) -> list[str]:
    """Check a resolve() response against the published schema."""
    return validate_against(response, "resolve_response")
