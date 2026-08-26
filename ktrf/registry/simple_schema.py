"""Simple Terminology Schema → KTRF glossary compiler (PLAN_PI.md §4).

Authors write a short YAML file; the compiler derives everything the
resolver needs (stable entity/alias ids, alias families, normalization
profiles, boundary policies, grounding block, provenance):

.. code-block:: yaml

    schema_version: 1
    terms:
      - key: advanced-billing-console
        canonical: Advanced Billing Console
        surfaces: [ABC, 빌링 콘솔]
        short_definition: 사내 과금 정책과 청구 상태를 관리하는 운영 콘솔
        type: internal_system
        domains: [billing]
        injection: {policy: auto, priority: 20}
        override: true

Design rules:

- **Ids are derived, never authored.** ``entity_id`` is ``<scope>:<key>``
  so the same key in different scopes stays distinguishable, and merging
  layers cannot silently collide (see :mod:`ktrf.registry.layers`).
- **Profiles are inferred from the surface text**, since that is what the
  normalization pipeline actually keys on (Latin acronym vs mixed
  alphanumeric vs Hangul organization name vs generic Korean term).
- **Unknown keys are rejected**, not ignored: a typo in a hand-written
  dictionary must fail loudly rather than silently drop a definition.
"""

from __future__ import annotations

import re
import unicodedata

TERM_KEYS = {"key", "canonical", "surfaces", "short_definition", "type",
             "domains", "injection", "override", "classification",
             "valid_from", "valid_to", "examples"}
INJECTION_KEYS = {"policy", "priority"}
INJECTION_POLICIES = {"auto", "resolved_only", "candidate_only", "never"}
CLASSIFICATIONS = {"public", "internal", "restricted"}

MAX_SURFACE_CHARS = 120
MAX_DEFINITION_CHARS = 1000
MAX_TERMS = 20000

_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,80}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Korean organization-name suffixes: these surfaces need the org profile so
# the particle FST and boundary rules treat them as institution names.
_ORG_SUFFIXES = ("부", "청", "처", "원", "회", "실", "국", "단", "공사", "공단",
                 "법원", "검찰청", "은행", "위원회", "협회", "연합회", "노총",
                 "본부", "재단", "교육청", "센터")
_ORG_TYPES = {"organization", "org", "agency", "company", "institution",
              "government", "team", "department"}


class SimpleTermsError(ValueError):
    """Raised when a terms document cannot be compiled."""


def _clean(value, field: str, max_chars: int) -> str:
    if not isinstance(value, str):
        raise SimpleTermsError(f"{field} must be a string, got "
                               f"{type(value).__name__}")
    s = unicodedata.normalize("NFC", value).strip()
    if _CONTROL.search(s):
        raise SimpleTermsError(f"{field} contains control characters")
    if not s:
        raise SimpleTermsError(f"{field} must not be empty")
    if len(s) > max_chars:
        raise SimpleTermsError(f"{field} exceeds {max_chars} characters")
    return s


def _is_hangul(ch: str) -> bool:
    return "가" <= ch <= "힣" or "ㄱ" <= ch <= "ㅣ"


def infer_profile(surface: str, term_type: str | None) -> str:
    """Pick the normalization profile a surface actually needs."""
    has_hangul = any(_is_hangul(c) for c in surface)
    has_latin = any(c.isascii() and c.isalnum() for c in surface)
    if has_hangul and has_latin:
        return "mixed_alnum"
    if has_latin and not has_hangul:
        letters = [c for c in surface if c.isalpha()]
        if letters and all(c.isupper() for c in letters) and len(surface) <= 8:
            return "latin_acronym"
        return "latin_word"
    if (term_type or "").lower() in _ORG_TYPES or \
            surface.endswith(_ORG_SUFFIXES):
        return "korean_org_name"
    return "korean_term"


def _boundary_policy(surface: str, profile: str) -> dict:
    first = surface[0]
    left = ("latin_token_boundary"
            if first.isascii() and first.isalnum() else
            "hangul_token_boundary" if _is_hangul(first) else
            "unicode_word_boundary")
    policy = {"left": left}
    if profile == "latin_acronym":
        # an acronym must not match inside a longer Latin run (KBS ⊄ KBSN)
        policy["allow_inside_latin_run"] = False
    return policy


def _alias_kind(surface: str, canonical: str, profile: str) -> str:
    if surface == canonical:
        return "name"
    if profile == "latin_acronym":
        return "abbreviation"
    if len(surface) < len(canonical) and _is_hangul(surface[0]) \
            and len(surface) <= 4:
        return "abbreviation"
    return "alias"


def compile_simple_terms(doc: dict, scope: str = "project",
                         glossary_id: str | None = None,
                         version: str = "1",
                         source: str | None = None) -> dict:
    """Compile a Simple Terminology document into a KTRF glossary dict.

    The result is accepted by :func:`ktrf.glossary.load_glossary` as-is.
    ``scope`` becomes part of every id and is recorded in provenance so
    layered compilation can reason about precedence.
    """
    if not isinstance(doc, dict):
        raise SimpleTermsError("terms document must be a mapping")
    unknown_top = set(doc) - {"schema_version", "terms", "glossary_id",
                              "version"}
    if unknown_top:
        raise SimpleTermsError(f"unknown top-level keys: "
                               f"{sorted(unknown_top)}")
    if str(doc.get("schema_version", "1")) != "1":
        raise SimpleTermsError(
            f"unsupported schema_version {doc.get('schema_version')!r}")
    terms = doc.get("terms") or []
    if not isinstance(terms, list):
        raise SimpleTermsError("terms must be a list")
    if len(terms) > MAX_TERMS:
        raise SimpleTermsError(f"too many terms (>{MAX_TERMS})")

    entities: list[dict] = []
    families: list[dict] = []
    bindings: list[dict] = []
    seen_keys: set[str] = set()

    for i, term in enumerate(terms):
        if not isinstance(term, dict):
            raise SimpleTermsError(f"terms[{i}] must be a mapping")
        unknown = set(term) - TERM_KEYS
        if unknown:
            raise SimpleTermsError(
                f"terms[{i}] has unknown keys: {sorted(unknown)}")
        key = _clean(term.get("key"), f"terms[{i}].key", 80)
        if not _KEY_RE.match(key):
            raise SimpleTermsError(
                f"terms[{i}].key {key!r} must be lowercase "
                "alphanumeric with . _ -")
        if key in seen_keys:
            raise SimpleTermsError(f"duplicate term key {key!r}")
        seen_keys.add(key)

        canonical = _clean(term.get("canonical"), f"terms[{i}].canonical",
                           MAX_SURFACE_CHARS)
        raw_surfaces = term.get("surfaces") or []
        if not isinstance(raw_surfaces, list):
            raise SimpleTermsError(f"terms[{i}].surfaces must be a list")
        surfaces = [_clean(s, f"terms[{i}].surfaces[{j}]", MAX_SURFACE_CHARS)
                    for j, s in enumerate(raw_surfaces)]
        # the canonical form is always matchable, listed first
        all_surfaces = list(dict.fromkeys([canonical, *surfaces]))

        short_def = ""
        if term.get("short_definition") is not None:
            short_def = _clean(term["short_definition"],
                               f"terms[{i}].short_definition",
                               MAX_DEFINITION_CHARS)
        injection = term.get("injection") or {}
        if not isinstance(injection, dict):
            raise SimpleTermsError(f"terms[{i}].injection must be a mapping")
        unknown_inj = set(injection) - INJECTION_KEYS
        if unknown_inj:
            raise SimpleTermsError(
                f"terms[{i}].injection has unknown keys: "
                f"{sorted(unknown_inj)}")
        inj_policy = injection.get("policy", "auto")
        if inj_policy not in INJECTION_POLICIES:
            raise SimpleTermsError(
                f"terms[{i}].injection.policy {inj_policy!r} invalid")
        priority = injection.get("priority", 0)
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise SimpleTermsError(
                f"terms[{i}].injection.priority must be an integer")
        classification = term.get("classification", "internal")
        if classification not in CLASSIFICATIONS:
            raise SimpleTermsError(
                f"terms[{i}].classification {classification!r} invalid")

        entity_id = f"{scope}:{key}"
        term_type = term.get("type")
        entities.append({
            "entity_id": entity_id,
            "canonical": canonical,
            "type_ids": [term_type] if term_type else [],
            "domain_ids": list(term.get("domains") or []),
            "description": short_def,
            "examples": list(term.get("examples") or []),
            "valid_from": term.get("valid_from"),
            "valid_to": term.get("valid_to"),
            "grounding": {
                "short_definition": short_def,
                "injection_policy": inj_policy,
                "priority": priority,
                "classification": classification,
            },
            "provenance": {"scope": scope, "key": key,
                           "source": source,
                           "override": bool(term.get("override", False))},
        })

        # one alias family per (term, profile): a family is the group of
        # surfaces that share normalization behaviour
        by_profile: dict[str, list[str]] = {}
        for surface in all_surfaces:
            by_profile.setdefault(infer_profile(surface, term_type),
                                  []).append(surface)
        for profile, group in sorted(by_profile.items()):
            family_id = f"{entity_id}:{profile}"
            families.append({"family_id": family_id,
                             "representative": group[0],
                             "normalization_profile": profile})
            for n, surface in enumerate(group):
                bindings.append({
                    "alias_id": f"{family_id}:{n}",
                    "family_id": family_id,
                    "entity_id": entity_id,
                    "surface": surface,
                    "kind": _alias_kind(surface, canonical, profile),
                    "boundary_policy": _boundary_policy(surface, profile),
                    "provenance": {"scope": scope, "key": key},
                })

    return {
        "glossary_id": glossary_id or doc.get("glossary_id") or f"{scope}-terms",
        "version": str(doc.get("version") or version),
        "schema_version": "3",
        "entities": entities,
        "alias_families": families,
        "alias_bindings": bindings,
    }
