#!/usr/bin/env python3
"""Find glossary terms in Korean text with Python 3.11+.

    python krtf.py terms.json "한전KDN은 AP를 점검했다."
    python krtf.py terms.json < document.txt

JSON needs only the standard library. YAML needs PyYAML. From Python, reuse
compile_snapshot(load_glossary(path)) across calls to resolve(snapshot, text).
Matches are case-sensitive literals. The longest eligible alias wins at each
position. A recognized particle belongs to full_span but not to the core span.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import NamedTuple


# Common particles and fixed chains, grouped by the first particle's 받침 rule.
_PARTICLES = {
    "any": "의 에 에서 에게 에게서 한테 한테서 께 께서 도 만 뿐 부터 까지 처럼 보다 "
           "마다 만큼 에는 에도 에서도 에서는 에게도 에게는 까지도 부터는",
    "closed": "은 이 을 과 이랑 이나",
    "open": "는 가 를 와 랑 나",
    "rieul_or_open": "로 로서 로써 로는 로도",
    "other_closed": "으로 으로서 으로써 으로는 으로도",
}
_PARTICLE_RULE = {word: rule for rule, words in _PARTICLES.items() for word in words.split()}
_MAX_TAIL = max(map(len, _PARTICLE_RULE))


def load_glossary(path):
    """Read a UTF-8 JSON or YAML glossary."""
    path = Path(path)
    with path.open(encoding="utf-8-sig") as stream:
        if path.suffix.lower() == ".json":
            return json.load(stream)
        if path.suffix.lower() not in {".yaml", ".yml"}:
            raise ValueError("expected a .json, .yaml, or .yml glossary")
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("YAML needs PyYAML (python -m pip install PyYAML), or use JSON") from exc
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML: {exc}") from exc


def _records(doc, field):
    rows = doc.get(field)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{field} must be a list of objects")
    return rows


def _name(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def _restricted(row):
    return bool(row.get("scope") or row.get("valid_from") or row.get("valid_to"))


class Snapshot(NamedTuple):
    names: dict[str, str]
    # Surface -> entity ID -> at least one unconditional binding.
    aliases: dict[str, dict[str, bool]]
    by_initial: dict[str, list[str]]


def compile_snapshot(doc):
    """Index one simple v1 terms document or literal bindings from a v3 glossary."""
    if not isinstance(doc, dict):
        raise ValueError("glossary must be an object")
    version = str(doc.get("schema_version", "1" if "terms" in doc else "3"))
    names = {}
    aliases = {}

    def add_entity(entity_id, canonical):
        if entity_id in names:
            raise ValueError(f"duplicate entity ID: {entity_id}")
        names[entity_id] = _name(canonical, "canonical")

    def bind(surface, entity_id, eligible):
        candidates = aliases.setdefault(_name(surface, "surface"), {})
        candidates[entity_id] = candidates.get(entity_id, False) or eligible

    if version == "1":
        for term in _records(doc, "terms"):
            key = _name(term.get("key"), "key")
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", key):
                raise ValueError(f"invalid term key: {key!r}")
            entity_id = f"project:{key}"
            add_entity(entity_id, term.get("canonical"))
            surfaces = term.get("surfaces", [])
            if not isinstance(surfaces, list):
                raise ValueError("surfaces must be a list")
            for surface in [names[entity_id], *surfaces]:
                bind(surface, entity_id, not _restricted(term))
    elif version == "3":
        if doc.get("policies") or doc.get("normalization_profiles"):
            raise ValueError("custom glossary policies and normalization profiles need full KTRF")
        restricted_ids = set()
        for entity in _records(doc, "entities"):
            entity_id = _name(entity.get("entity_id"), "entity_id")
            add_entity(entity_id, entity.get("canonical"))
            if _restricted(entity):
                restricted_ids.add(entity_id)
        for binding in _records(doc, "alias_bindings"):
            entity_id = _name(binding.get("entity_id"), "entity_id")
            if entity_id not in names:
                raise ValueError(f"alias references unknown entity: {entity_id}")
            boundary = binding.get("boundary_policy", {})
            if not isinstance(boundary, dict):
                raise ValueError("boundary_policy must be an object")
            if (binding.get("normalization_policy")
                    or boundary.get("right", "particle_or_token_boundary") != "particle_or_token_boundary"
                    or boundary.get("left") not in (None, "latin_token_boundary",
                                                     "hangul_token_boundary", "unicode_word_boundary")
                    or boundary.get("allow_inside_latin_run")):
                raise ValueError("custom alias matching policies need full KTRF")
            bind(binding.get("surface"), entity_id,
                 entity_id not in restricted_ids and not _restricted(binding))
    else:
        raise ValueError(f"unsupported schema_version: {version!r}")

    by_initial = {}
    for surface in sorted(aliases, key=len, reverse=True):
        by_initial.setdefault(surface[0], []).append(surface)
    return Snapshot(names, aliases, by_initial)


def _word_char(ch):
    return ch.isalnum() or ch == "_" or unicodedata.category(ch).startswith("M")


def _full_end(text, end):
    """Require a token boundary, optionally after a whole, grammatical particle."""
    stop = end
    while stop < len(text) and _word_char(text[stop]):
        stop += 1
        if stop - end > _MAX_TAIL:
            return None
    if stop == end:
        return end
    rule = _PARTICLE_RULE.get(text[end:stop])
    if rule is None:
        return None
    last = text[end - 1]
    if rule != "any" and "가" <= last <= "힣":
        jong = (ord(last) - ord("가")) % 28  # ㄹ is jongseong index 8
        compatible = {
            "closed": jong != 0,
            "open": jong == 0,
            "rieul_or_open": jong in (0, 8),
            "other_closed": jong not in (0, 8),
        }
        if not compatible[rule]:
            return None
    return stop


def resolve(snapshot, text):
    """Return literal glossary mentions with half-open offsets in the original text."""
    byte = [0]
    utf16 = [0]
    for ch in text:
        byte.append(byte[-1] + len(ch.encode("utf-8")))
        utf16.append(utf16[-1] + (2 if ord(ch) > 0xffff else 1))

    def span(start, end):
        return {"codepoint": {"start": start, "end": end},
                "byte": {"start": byte[start], "end": byte[end]},
                "utf16": {"start": utf16[start], "end": utf16[end]}}

    mentions = []
    start = 0
    while start < len(text):
        if start and _word_char(text[start - 1]):
            start += 1
            continue
        for surface in snapshot.by_initial.get(text[start], ()):
            if not text.startswith(surface, start):
                continue
            end = start + len(surface)
            full_end = _full_end(text, end)
            if full_end is None:
                continue
            mention = {"surface": surface, "span": span(start, end),
                       "full_span": span(start, full_end), "mention_decision": "TERM"}
            ids = snapshot.aliases[surface]
            if len(ids) == 1 and all(ids.values()):
                entity_id = next(iter(ids))
                mention["link_decision"] = "RESOLVED"
                mention["resolved_entity"] = {"entity_id": entity_id,
                                              "canonical": snapshot.names[entity_id]}
            else:
                mention["link_decision"] = "AMBIGUOUS"
                mention["prediction_set"] = {
                    "members": [{"kind": "ENTITY", "entity_id": eid} for eid in sorted(ids)]}
            mentions.append(mention)
            start = full_end
            break
        else:
            start += 1
    return {"mode": "literal", "mentions": mentions}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("glossary", help="v1 terms or v3 glossary in JSON or YAML")
    parser.add_argument("text", nargs="?", help="input text (default: UTF-8 stdin)")
    args = parser.parse_args()
    try:
        snapshot = compile_snapshot(load_glossary(args.glossary))
        text = args.text if args.text is not None else sys.stdin.buffer.read().decode("utf-8")
        result = resolve(snapshot, text)
        sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"{parser.prog}: {exc}\n")


if __name__ == "__main__":
    main()
