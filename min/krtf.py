#!/usr/bin/env python3
"""Find glossary terms in Korean text with Python 3.11+.

    python krtf.py terms.json "한전KDN은 AP를 점검했다."
    python krtf.py terms.json < document.txt
    python krtf.py compile terms.json terms.krtf
    python krtf.py load terms.krtf "한전에서 발표했다."

JSON needs only the standard library. YAML needs PyYAML. From Python, reuse
compile_snapshot(load_glossary(path)) across calls to resolve(snapshot, text).
Lookup preserves original offsets through normalization and reports inferred
spellings as candidates. Run a subcommand with --help for its arguments.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from pathlib import Path


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


def _iso_date(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid ISO date: {value!r}") from exc


def _condition(row):
    """Canonical AND rule for one entity or one alias binding."""
    rule = {}
    for key in ("valid_from", "valid_to"):
        if row.get(key) is not None:
            rule[key] = _iso_date(row[key])
    if rule.get("valid_from", "") > rule.get("valid_to", "9999-12-31"):
        raise ValueError("valid_from is after valid_to")
    scope = row.get("scope") or {}
    if not isinstance(scope, dict):
        raise ValueError("scope must be an object")
    if not ({"allow", "deny"} & scope.keys()):
        scope = {"allow": scope}
    for policy, dimensions in scope.items():
        if policy not in ("allow", "deny") or not isinstance(dimensions, dict):
            raise ValueError("scope must use allow or deny")
        for dimension, values in dimensions.items():
            if dimension not in ("departments", "projects") or not isinstance(values, list):
                raise ValueError("scope supports lists of departments and projects")
            if values:
                rule.setdefault(policy, {})[dimension] = [_name(v, dimension) for v in values]
    return rule


def _rule_status(rule, department, project, as_of):
    """True applies, False needs more context, None explicitly does not apply."""
    known = True
    for dimension, value in (("departments", department), ("projects", project)):
        allow = rule.get("allow", {}).get(dimension, ())
        deny = rule.get("deny", {}).get(dimension, ())
        if not value and (allow or deny):
            known = False
        elif value and (value in deny or (allow and value not in allow)):
            return None
    if "valid_from" in rule or "valid_to" in rule:
        if as_of is None:
            known = False
        elif not rule.get("valid_from", "") <= _iso_date(as_of) <= rule.get("valid_to", "9999-12-31"):
            return None
    return known


def _entity_status(snapshot, eid, department, project, as_of):
    rule = snapshot.meta.get("entity_rules", {}).get(eid, {})
    return _rule_status(rule, department, project, as_of)


def _eligible_ids(snapshot, surfaces, department, project, as_of):
    result = {}
    conditions = snapshot.meta.get("conditions", {})
    for surface in surfaces:
        for eid, unconditional in snapshot.aliases.get(surface, {}).items():
            entity_status = _entity_status(snapshot, eid, department, project, as_of)
            if entity_status is None:
                continue
            rules = conditions.get(surface, {}).get(eid)
            if rules is None:
                # A v1 snapshot records only a flag; absent evidence cannot lift a restriction.
                eligible = unconditional
            else:
                statuses = [_rule_status(r, department, project, as_of) for r in rules]
                if all(status is None for status in statuses):
                    continue
                eligible = any(status is True for status in statuses)
            result[eid] = result.get(eid, False) or (entity_status and eligible)
    return result


@dataclass
class Snapshot:
    names: dict[str, str]
    # Surface -> entity ID -> at least one unconditional binding.
    aliases: dict[str, dict[str, bool]]
    by_initial: dict[str, list[str]]
    meta: dict = field(default_factory=dict)

    @cached_property
    def matcher(self):
        return _Matcher(self)

    @cached_property
    def recovery_index(self):
        return _RecoveryIndex(self)


# The format version identifies the serialized indexes and metadata.
_SNAPSHOT_HEADER = b"KRTF-MIN/2\n"


def save_snapshot(snapshot: Snapshot, path) -> Path:
    """Atomically save the compiled lookup index in a standalone min snapshot."""
    path = Path(path)
    # Store each surface once, in lookup order within its first-character bucket.
    buckets = {
        initial: [[surface, snapshot.aliases[surface]] for surface in surfaces]
        for initial, surfaces in snapshot.by_initial.items()
    }
    payload = json.dumps({"names": snapshot.names, "buckets": buckets, "meta": snapshot.meta,
                          "matcher": snapshot.matcher.to_data()},
                         ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest().encode("ascii")
    temporary = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
    try:
        with temporary as stream:
            stream.write(_SNAPSHOT_HEADER + digest + b"\n")
            stream.write(payload)
        os.replace(temporary.name, path)
    finally:
        Path(temporary.name).unlink(missing_ok=True)
    return path


def load_snapshot(path) -> Snapshot:
    """Restore compiled candidates and lookup order without the source glossary."""
    with Path(path).open("rb") as stream:
        header = stream.readline(len(_SNAPSHOT_HEADER) + 1)
        if header not in (b"KRTF-MIN/1\n", _SNAPSHOT_HEADER):
            raise ValueError("unsupported min snapshot format or version")
        digest = stream.readline(66)
        payload = stream.read()
    if digest != hashlib.sha256(payload).hexdigest().encode("ascii") + b"\n":
        raise ValueError("min snapshot checksum mismatch")
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("invalid min snapshot index")
    names = data.get("names")
    buckets = data.get("buckets")
    if not isinstance(names, dict) or not isinstance(buckets, dict):
        raise ValueError("invalid min snapshot index")
    for entity_id, canonical in names.items():
        _name(entity_id, "entity_id")
        _name(canonical, "canonical")
    aliases = {}
    by_initial = {}
    for initial, rows in buckets.items():
        if len(initial) != 1 or not isinstance(rows, list) or not rows:
            raise ValueError("invalid min snapshot lookup bucket")
        surfaces = []
        for row in rows:
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError("invalid min snapshot alias record")
            surface, candidates = row
            if (not isinstance(surface, str) or not surface.startswith(initial)
                    or surface in aliases or (surfaces and len(surface) > len(surfaces[-1]))):
                raise ValueError("invalid min snapshot lookup order or surface")
            if (not isinstance(candidates, dict) or not candidates
                    or any(eid not in names or type(eligible) is not bool
                           for eid, eligible in candidates.items())):
                raise ValueError("invalid min snapshot candidates")
            surfaces.append(surface)
            aliases[surface] = candidates
        by_initial[initial] = surfaces
    meta = data.get("meta") if header == _SNAPSHOT_HEADER else {}
    _validate_metadata(meta, names, aliases)
    snapshot = Snapshot(names, aliases, by_initial, meta)
    if header == _SNAPSHOT_HEADER:
        snapshot.matcher = _Matcher.from_data(snapshot, data.get("matcher"))
    return snapshot


def compile_snapshot(doc, *, layer="project"):
    """Index one simple v1 terms document or literal bindings from a v3 glossary."""
    if not isinstance(doc, dict):
        raise ValueError("glossary must be an object")
    version = str(doc.get("schema_version", "1" if "terms" in doc else "3"))
    names = {}
    aliases = {}
    meta = {"definitions": {}, "entity_rules": {}, "conditions": {}, "relations": [],
            "layers": {}, "conflicts": [], "no_fuzzy": {}, "no_keyboard": {}}
    policies = {}

    def add_entity(entity_id, row):
        if entity_id in names:
            raise ValueError(f"duplicate entity ID: {entity_id}")
        names[entity_id] = _name(row.get("canonical"), "canonical")
        meta["layers"][entity_id] = layer
        definition = row.get("short_definition") or row.get("description")
        if definition:
            meta["definitions"][entity_id] = _name(definition, "definition")
        if rule := _condition(row):
            meta["entity_rules"][entity_id] = rule

    def bind(surface, entity_id, row):
        surface = _name(surface, "surface")
        rule = _condition(row)
        eligible = not rule and entity_id not in meta["entity_rules"]
        candidates = aliases.setdefault(surface, {})
        previous = candidates.get(entity_id)
        candidates[entity_id] = candidates.get(entity_id, False) or eligible
        if not eligible or previous is False:
            alternatives = meta["conditions"].setdefault(surface, {}).setdefault(entity_id, [])
            if previous and {} not in alternatives:
                alternatives.append({})
            if rule not in alternatives:
                alternatives.append(rule)
        fuzzy = row.get("fuzzy_policy") or {}
        if not isinstance(fuzzy, dict):
            raise ValueError("fuzzy_policy must be an object")
        for key, flag in (("no_fuzzy", "enabled"), ("no_keyboard", "keyboard_recovery")):
            disabled = fuzzy.get(flag) is False
            identity = (key, surface, entity_id)
            policies[identity] = policies.get(identity, True) and disabled

    if version == "1":
        for term in _records(doc, "terms"):
            key = _name(term.get("key"), "key")
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", key):
                raise ValueError(f"invalid term key: {key!r}")
            entity_id = f"{layer}:{key}"
            add_entity(entity_id, term)
            surfaces = term.get("surfaces", [])
            if not isinstance(surfaces, list):
                raise ValueError("surfaces must be a list")
            for surface in [names[entity_id], *surfaces]:
                bind(surface, entity_id, {})
    elif version == "3":
        if doc.get("policies") or doc.get("normalization_profiles"):
            raise ValueError("custom glossary policies and normalization profiles need full KTRF")
        for entity in _records(doc, "entities"):
            entity_id = _name(entity.get("entity_id"), "entity_id")
            add_entity(entity_id, entity)
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
            bind(binding.get("surface"), entity_id, binding)
        for rel in _records(doc, "entity_relations") if "entity_relations" in doc else ():
            if rel.get("relation_type") != "COMPOSES_TO":
                continue
            relation = {k: _name(rel.get(k), k) for k in (
                "source_entity_id", "target_entity_id", "surface_suffix", "relation_type")}
            if rel.get("relation_id"):
                relation["relation_id"] = _name(rel["relation_id"], "relation_id")
            if any(relation[k] not in names for k in ("source_entity_id", "target_entity_id")):
                raise ValueError("relation references unknown entity")
            meta["relations"].append(relation)
    else:
        raise ValueError(f"unsupported schema_version: {version!r}")

    for (key, surface, eid), disabled in policies.items():
        if disabled:
            meta[key].setdefault(surface, []).append(eid)
    return _snapshot_from_maps(names, aliases, meta)


def _snapshot_from_maps(names, aliases, meta):
    by_initial = {}
    for surface in sorted(aliases, key=len, reverse=True):
        by_initial.setdefault(surface[0], []).append(surface)
    return Snapshot(names, aliases, by_initial, meta)


def _validate_metadata(meta, names, aliases):
    if not isinstance(meta, dict):
        raise ValueError("invalid min snapshot metadata")

    def check_rule(rule):
        if not isinstance(rule, dict) or set(rule) - {"allow", "deny", "valid_from", "valid_to"}:
            raise ValueError("invalid snapshot scope rule")
        parsed = _condition({**rule, "scope": {k: rule[k] for k in ("allow", "deny") if k in rule}})
        if parsed != rule:
            raise ValueError("invalid snapshot scope rule")

    for field_name in ("definitions", "layers", "entity_rules", "conditions", "no_fuzzy", "no_keyboard"):
        if not isinstance(meta.get(field_name, {}), dict):
            raise ValueError(f"invalid min snapshot {field_name}")
    for field_name in ("definitions", "layers", "entity_rules"):
        for eid, value in meta.get(field_name, {}).items():
            if eid not in names:
                raise ValueError("unknown metadata entity")
            if field_name == "entity_rules":
                check_rule(value)
            else:
                _name(value, field_name)
    for surface, ids in meta.get("conditions", {}).items():
        if surface not in aliases or not isinstance(ids, dict):
            raise ValueError("invalid min snapshot conditions")
        for eid, rules in ids.items():
            if eid not in aliases[surface] or not isinstance(rules, list) or not rules:
                raise ValueError("invalid min snapshot binding conditions")
            for rule in rules:
                check_rule(rule)
    for field_name in ("no_fuzzy", "no_keyboard"):
        for surface, ids in meta.get(field_name, {}).items():
            if (surface not in aliases or not isinstance(ids, list)
                    or any(not isinstance(eid, str) or eid not in aliases[surface] for eid in ids)):
                raise ValueError(f"invalid min snapshot {field_name}")
    relations = meta.get("relations", [])
    if not isinstance(relations, list):
        raise ValueError("invalid min snapshot relations")
    for rel in relations:
        if not isinstance(rel, dict) or rel.get("relation_type") != "COMPOSES_TO":
            raise ValueError("invalid min snapshot relation")
        for key in ("source_entity_id", "target_entity_id"):
            if _name(rel.get(key), key) not in names:
                raise ValueError("unknown relation entity")
        _name(rel.get("surface_suffix"), "surface_suffix")
    conflicts = meta.get("conflicts", [])
    if not isinstance(conflicts, list) or not all(isinstance(c, dict) for c in conflicts):
        raise ValueError("invalid min snapshot conflicts")


_LAYERS = ("base", "global", "project", "session", "document")


def compile_layers(documents):
    """Compile (layer name, glossary) pairs. A narrower layer owns a shared spelling."""
    docs = list(documents)
    labels = [label for label, _ in docs]
    if (not docs or len(set(labels)) != len(labels)
            or any(label not in _LAYERS for label in labels)):
        raise ValueError("expected unique layers from " + ", ".join(_LAYERS))
    names = {}
    aliases = {}
    meta = {"definitions": {}, "layers": {}, "entity_rules": {}, "conditions": {},
            "no_fuzzy": {}, "no_keyboard": {}, "relations": [], "conflicts": []}
    owners = {}
    for label, doc in sorted(docs, key=lambda item: _LAYERS.index(item[0])):
        part = compile_snapshot(doc, layer=label)
        for eid, name in part.names.items():
            if eid in names and (names[eid] != name or meta["entity_rules"].get(eid)
                                 != part.meta["entity_rules"].get(eid)):
                raise ValueError(f"conflicting entity identity or scope across layers: {eid}")
            names[eid] = name
        for field_name in ("definitions", "layers", "entity_rules"):
            meta[field_name].update(part.meta[field_name])
        meta["relations"].extend(part.meta["relations"])
        groups = {}
        for surface in part.aliases:
            groups.setdefault(_fold_text(surface), []).append(surface)
        for key, surfaces in groups.items():
            previous = owners.get(key, [])
            if previous:
                previous_ids = sorted({eid for s in previous for eid in aliases[s]})
                active_ids = sorted({eid for s in surfaces for eid in part.aliases[s]})
                if previous_ids != active_ids:
                    meta["conflicts"].append({"surface": surfaces[0], "layer": label,
                                              "shadowed": previous_ids, "active": active_ids})
                for old_surface in previous:
                    del aliases[old_surface]
                    for field_name in ("conditions", "no_fuzzy", "no_keyboard"):
                        meta[field_name].pop(old_surface, None)
            owners[key] = surfaces
            for surface in surfaces:
                aliases[surface] = part.aliases[surface]
                for field_name in ("conditions", "no_fuzzy", "no_keyboard"):
                    if surface in part.meta[field_name]:
                        meta[field_name][surface] = part.meta[field_name][surface]
    return _snapshot_from_maps(names, aliases, meta)


# Dubeolsik keys indexed by the Unicode initial, vowel and final jamo numbers.
_CHO_KEYS = "r R s e E f a q Q t T d w W c z x v g".split()
_JUNG_KEYS = "k o i O j p u P h hk ho hl y n nj np nl b m ml l".split()
_JONG_KEYS = [""] + "r R rt s sw sg e f fr fa fq ft fx fv fg a q qt t T d w c z x v g".split()
_COMPAT_KEYS = dict(zip("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ", _CHO_KEYS))
_COMPAT_KEYS.update(zip("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ", _JUNG_KEYS))


def _keyboard_keys(word):
    keys = []
    for ch in word:
        if "가" <= ch <= "힣":
            onset_vowel, final = divmod(ord(ch) - ord("가"), 28)
            onset, vowel = divmod(onset_vowel, 21)
            keys.extend((_CHO_KEYS[onset], _JUNG_KEYS[vowel], _JONG_KEYS[final]))
        elif ch in _COMPAT_KEYS:
            keys.append(_COMPAT_KEYS[ch])
        else:
            return ""
    return "".join(keys)


def _one_edit(a, b):
    """One jamo insertion, deletion or substitution."""
    if len(a) > len(b):
        a, b = b, a
    if len(b) - len(a) > 1 or a == b:
        return False
    for i, ch in enumerate(a):
        if ch != b[i]:
            return a[i + (len(a) == len(b)):] == b[i + 1:]
    return True


class _RecoveryIndex:
    def __init__(self, snapshot):
        self.keyboard = {}
        self.latin = {}
        self.initials = {}
        self.subsequence = {}
        self.edit = {}
        self.jamo = {}
        self.symbols = set()
        for surface in snapshot.aliases:
            words = surface.split()
            compact = "".join(words)
            if len(words) >= 3 and all(w.isascii() and w.isalpha() for w in words):
                self.initials.setdefault("".join(w[0].upper() for w in words), []).append(surface)
            if re.fullmatch(r"[가-힣]{4,60}", compact):
                entry = (compact, surface)
                for syllable in set(compact[1:-1]):
                    self.subsequence.setdefault((compact[0], compact[-1], syllable), []).append(entry)
            if re.fullmatch(r"[A-Za-z]{2,32}", surface):
                self.latin.setdefault(surface.lower(), []).append(surface)
            if not re.fullmatch(r"[가-힣]{2,32}", surface):
                continue
            self.keyboard.setdefault(_keyboard_keys(surface), []).append(surface)
            if len(surface) >= 3:
                jamo = unicodedata.normalize("NFD", surface)
                self.jamo[jamo] = surface
                self.symbols.update(jamo)
                half = len(jamo) // 2
                for side, part in ((0, jamo[:half]), (1, jamo[half:])):
                    self.edit.setdefault((len(jamo), side, part), []).append((jamo, surface))

    def typos(self, query):
        # One edit leaves either the prefix half or the suffix half intact.
        buckets = []
        for length in range(len(query) - 1, len(query) + 2):
            half = length // 2
            for side, part in ((0, query[:half]), (1, query[-(length - half):])):
                buckets.append(self.edit.get((length, side, part), ()))
        if sum(map(len, buckets)) <= 256:
            return {surface for bucket in buckets for target, surface in bucket
                    if _one_edit(query, target)}
        # Many institutions can share an entire prefix. In dense buckets look
        # up edits of the query directly, bounding work by length and alphabet.
        matches = set()
        for i in range(len(query) + 1):
            before, after = query[:i], query[i:]
            if after and before + after[1:] in self.jamo:
                matches.add(self.jamo[before + after[1:]])
            for ch in self.symbols:
                insert = self.jamo.get(before + ch + after)
                if insert:
                    matches.add(insert)
                if after and ch != after[0]:
                    replace = self.jamo.get(before + ch + after[1:])
                    if replace:
                        matches.add(replace)
        return matches

    def matches(self, word):
        hits = {}
        if re.fullmatch(r"[A-Za-z]{3,96}", word):
            if word in self.keyboard:
                hits["keyboard"] = self.keyboard[word]
            if word in self.initials:
                hits["abbrev"] = self.initials[word]
        if re.fullmatch(r"[가-힣ㄱ-ㅎㅏ-ㅣ]{1,32}", word):
            keys = _keyboard_keys(word).lower()
            # A lone spoken syllable such as 네 is weak evidence for an acronym.
            layout_input = any(ch in _COMPAT_KEYS for ch in word) or len(word) >= 2
            if layout_input and keys in self.latin:
                hits["keyboard"] = self.latin[keys]
        if re.fullmatch(r"[가-힣]{3,32}", word):
            # Retain both endpoints, at least half as many syllables as the name,
            # and more than a one-syllable deletion. Ordinary short words collide.
            buckets = (self.subsequence.get((word[0], word[-1], ch), ()) for ch in word[1:-1])
            for target, surface in min(buckets, key=len):
                if len(word) + 2 <= len(target) <= len(word) * 2:
                    remaining = iter(target)
                    if all(ch in remaining for ch in word):
                        hits.setdefault("abbrev", set()).add(surface)
            typos = self.typos(unicodedata.normalize("NFD", word))
            if typos:
                hits["jamo"] = typos
        return hits


_SHORT_WORD = r"[A-Za-z가-힣][A-Za-z가-힣0-9]{1,19}"
_QUOTED_SHORT = rf"""\s*["'“‘]?({_SHORT_WORD})["'”’]?"""
_LOCAL_PAREN = re.compile(rf"\s*\(\s*(?:이하\s*)?{_QUOTED_SHORT}(?:이?라\s+한다)?\s*\)")
_LOCAL_IHA = re.compile(rf"\s*,?\s*이하\s+{_QUOTED_SHORT}(?!\w)")
_LOCAL_REVERSE = re.compile(rf"(?<!\w)({_SHORT_WORD})\s*\(\s*$")
_RECOVERY_WORD = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣA-Za-z0-9Ａ-Ｚａ-ｚ０-９]+")


def _local_bindings(text, mentions):
    aliases, anchors, declarations = {}, {}, set()
    for m in mentions:
        start, end = (m["span"]["codepoint"][k] for k in ("start", "end"))
        long_form = m["surface"]
        forward = _LOCAL_PAREN.match(text, end) or _LOCAL_IHA.match(text, end)
        reverse = None
        if re.match(r"\s*\)", text[end:end + 8]):
            reverse = _LOCAL_REVERSE.search(text, max(0, start - 24), start)
        for declaration in (forward, reverse):
            if declaration is None:
                continue
            short = _fold_text(declaration.group(1))
            if len(short) >= len(_fold_text(long_form)):
                continue
            declarations.add(declaration.span(1))
            anchors.setdefault(short, set()).update(m["matched_surfaces"])
            local = aliases.setdefault(short, {})
            if m["link_decision"] == "RESOLVED":
                local[m["resolved_entity"]["entity_id"]] = True
            else:
                for candidate in m["prediction_set"]["members"]:
                    local.setdefault(candidate["entity_id"], False)
    return aliases, anchors, declarations


def _local_candidates(snapshot, local_ids, key, context):
    ids = dict(local_ids)
    spellings = snapshot.matcher.spellings.get(key, ())
    allowed = _eligible_ids(snapshot, spellings, *context)
    for spelling in spellings:
        for eid in snapshot.aliases[spelling]:
            if eid in allowed:
                ids[eid] = allowed[eid]
            else:
                ids.pop(eid, None)
    return ids, spellings


def _record_extra(m, snapshot, ids, spellings, channels):
    m["candidate_eligibility"] = dict(sorted(ids.items()))
    m["matched_surfaces"] = sorted(set(m.get("matched_surfaces", ())) | set(spellings))
    m["generation_channels"] = sorted(set(m.get("generation_channels", ())) | set(channels))
    if len(ids) == 1 and all(ids.values()):
        eid = next(iter(ids))
        m["link_decision"] = "RESOLVED"
        m["link_reason"] = "document_local_definition"
        m["resolved_entity"] = {"entity_id": eid, "canonical": snapshot.names[eid]}
        m.pop("prediction_set", None)
    else:
        m["link_decision"] = "AMBIGUOUS"
        if "doc_local" not in channels:
            m["link_reason"] = "recovery_candidate_only"
        elif len(ids) > 1:
            m["link_reason"] = "shared_alias"
        else:
            m["link_reason"] = "eligibility_unconfirmed"
        m.pop("resolved_entity", None)
        if "full_surface" in m:
            m["full_surface"].pop("composes_to", None)
        m["prediction_set"] = {"members": [{"kind": "ENTITY", "entity_id": eid}
                                           for eid in sorted(ids)]}


def _recovered_candidates(snapshot, core, context):
    ids, surfaces, channels = {}, set(), set()
    for channel, matches in snapshot.recovery_index.matches(core).items():
        flag = {"jamo": "no_fuzzy", "keyboard": "no_keyboard"}.get(channel)
        disabled = snapshot.meta.get(flag, {})
        for surface in matches:
            eligible = _eligible_ids(snapshot, [surface], *context)
            allowed = eligible.keys() - set(disabled.get(surface, ()))
            if allowed:
                surfaces.add(surface)
                channels.add(channel)
                ids.update(dict.fromkeys(allowed, False))
    return ids, surfaces, channels


def _extra_mentions(snapshot, text, mentions, span, department, project, as_of, recover):
    local, anchors, declarations = _local_bindings(text, mentions)
    if not (local or recover):
        return []
    context = department, project, as_of
    for m in mentions:
        key = _fold_text(m["surface"])
        if key in local:
            ids, spellings = _local_candidates(snapshot, local[key], key, context)
            if ids:
                _record_extra(m, snapshot, ids, anchors[key].union(spellings), {"doc_local"})

    occupied = sorted((m["span"]["codepoint"]["start"], m["full_span"]["codepoint"]["end"])
                      for m in mentions)
    out, interval = [], 0
    for token in _RECOVERY_WORD.finditer(text):
        start, stop = token.span()
        if ((start and _word_char(text[start - 1]))
                or (stop < len(text) and _word_char(text[stop]))):
            continue
        while interval < len(occupied) and occupied[interval][1] <= start:
            interval += 1
        if interval < len(occupied) and occupied[interval][0] < stop:
            continue
        word = token.group()
        if len(word) > 96 + 3 * _MAX_PARTICLE_LEN:
            continue
        cuts = [len(word)]
        cuts.extend(i for i in range(max(1, len(word) - 3 * _MAX_PARTICLE_LEN), len(word))
                    if _full_end(text, start + i) == stop)
        for cut in cuts:
            core = word[:cut]
            end = start + cut
            key = _fold_text(core)
            if key in local:
                if (start, end) in declarations:
                    break
                ids, known = _local_candidates(snapshot, local[key], key, context)
                surfaces = anchors[key].union(known)
                channels = {"doc_local"}
            elif recover:
                ids, surfaces, channels = _recovered_candidates(snapshot, core, context)
            else:
                continue
            if not ids:
                continue
            m = {"surface": core, "span": span(start, end), "full_span": span(start, stop),
                 "mention_decision": "TERM" if key in local else "UNCERTAIN"}
            _record_extra(m, snapshot, ids, surfaces, channels)
            out.append(m)
            break
    return out


def _word_char(ch):
    return ch.isalnum() or ch == "_" or unicodedata.category(ch).startswith("M")


# Only ASCII letters and fullwidth ASCII take part in the case/width fold.
# In particular, Unicode casefold would equate ß with ss and change lengths.
_ASCII_FOLD = {i: chr(i).lower() for i in range(ord("A"), ord("Z") + 1)}
_ASCII_FOLD.update({i: chr(i - 0xFEE0).lower() for i in range(0xFF01, 0xFF5F)})
_ASCII_FOLD[0x3000] = " "


def _fold_text(text):
    return unicodedata.normalize("NFC", text).translate(_ASCII_FOLD)


def _normalized_input(text):
    """Map whole NFC clusters back to raw boundaries, including Hangul L+V(+T)."""
    pieces, boundaries = [], [0]
    start = 0
    while start < len(text):
        end = start + 1
        while end < len(text):
            nxt = text[end]
            if nxt.isascii() or "가" <= nxt <= "힣":
                break
            if not unicodedata.category(nxt).startswith("M"):
                # Jamo and some other script letters compose despite having
                # combining class zero. NFC of the boundary pair decides.
                left = unicodedata.normalize("NFC", text[start:end])[-1]
                pair = left + unicodedata.normalize("NFC", nxt)
                if unicodedata.normalize("NFC", pair) == pair:
                    break
            end += 1
        piece = _fold_text(text[start:end])
        pieces.append(piece)
        boundaries.extend([None] * (len(piece) - 1))
        boundaries.append(end)
        start = end
    return "".join(pieces), boundaries


class _Matcher:
    """Aho-Corasick trie. Each output link visits the next shorter matched alias."""
    def __init__(self, snapshot):
        self.spellings = {}
        for surface in sorted(snapshot.aliases):
            self.spellings.setdefault(_fold_text(surface), []).append(surface)
        self.edges, self.failure, self.output, self.terminal = [{}], [0], [0], [None]
        for key in self.spellings:
            state = 0
            for ch in key:
                if ch not in self.edges[state]:
                    self.edges[state][ch] = len(self.edges)
                    self.edges.append({})
                    self.failure.append(0)
                    self.output.append(0)
                    self.terminal.append(None)
                state = self.edges[state][ch]
            self.terminal[state] = key

        for state, fallback, output in self._expected_links():
            self.failure[state] = fallback
            self.output[state] = output
        self._index_relations(snapshot)

    def _expected_links(self):
        """Visit parents before children so every fallback used here is already known."""
        from collections import deque

        queue = deque(self.edges[0].values())
        for child in queue:
            yield child, 0, 0
        while queue:
            state = queue.popleft()
            for ch, child in self.edges[state].items():
                fallback = self.failure[state]
                while fallback and ch not in self.edges[fallback]:
                    fallback = self.failure[fallback]
                fallback = self.edges[fallback].get(ch, 0)
                yield child, fallback, fallback if self.terminal[fallback] else self.output[fallback]
                queue.append(child)

    def _index_relations(self, snapshot):
        self.compositions = {}
        self.max_suffix = max(map(len, _SUFFIX_TYPES))
        for row in snapshot.meta.get("relations", ()):
            if row.get("relation_type") == "COMPOSES_TO" and row.get("surface_suffix"):
                source = row["source_entity_id"]
                suffix = _fold_text(row["surface_suffix"])
                self.compositions.setdefault(source, {}).setdefault(suffix, []).append(row)
                self.max_suffix = max(self.max_suffix, len(suffix))

    def to_data(self):
        """The search state consists entirely of JSON-native tables."""
        return {"edges": self.edges, "failure": self.failure, "output": self.output,
                "terminal": self.terminal, "spellings": self.spellings}

    @classmethod
    def from_data(cls, snapshot, data):
        """Validate and adopt the compiled transition tables without inserting any aliases."""
        if not isinstance(data, dict) or set(data) != {"edges", "failure", "output", "terminal", "spellings"}:
            raise ValueError("invalid compiled matcher tables")
        edges, failure, output, terminal = (data[k] for k in ("edges", "failure", "output", "terminal"))
        if (not all(isinstance(table, list) for table in (edges, failure, output, terminal))
                or not edges or not (len(edges) == len(failure) == len(output) == len(terminal))):
            raise ValueError("invalid compiled matcher table lengths")
        size = len(edges)
        if (any(type(link) is not int or not 0 <= link < size for table in (failure, output)
                for link in table) or (failure[0], output[0], terminal[0]) != (0, 0, None)):
            raise ValueError("invalid compiled matcher root or link")
        # Children are allocated after their parent and have a single incoming
        # edge. Together with reachability these properties rule out trie cycles.
        seen = {0}
        for state, children in enumerate(edges):
            if state not in seen or not isinstance(children, dict):
                raise ValueError("invalid compiled matcher state")
            if state and not children and terminal[state] is None:
                raise ValueError("compiled matcher has an unused leaf")
            for ch, child in children.items():
                if (not isinstance(ch, str) or len(ch) != 1 or type(child) is not int
                        or not state < child < size or child in seen):
                    raise ValueError("invalid compiled matcher transition")
                seen.add(child)

        spellings = data["spellings"]
        if not isinstance(spellings, dict):
            raise ValueError("invalid compiled matcher spelling map")
        registered = set()
        for key, surfaces in spellings.items():
            if (not isinstance(key, str) or not key or not isinstance(surfaces, list) or not surfaces
                    or any(not isinstance(s, str) for s in surfaces) or surfaces != sorted(surfaces)):
                raise ValueError("invalid compiled matcher spelling group")
            for s in surfaces:
                if s not in snapshot.aliases or s in registered or _fold_text(s) != key:
                    raise ValueError("compiled matcher disagrees with the aliases")
                registered.add(s)
            state = 0
            for ch in key:
                if ch not in edges[state]:
                    raise ValueError("compiled matcher is missing an alias transition")
                state = edges[state][ch]
            if terminal[state] != key:
                raise ValueError("invalid compiled matcher terminal")
        if registered != snapshot.aliases.keys() or sum(k is not None for k in terminal) != len(spellings):
            raise ValueError("incomplete compiled matcher aliases or terminals")

        matcher = cls.__new__(cls)
        matcher.edges, matcher.failure, matcher.output = edges, failure, output
        matcher.terminal, matcher.spellings = terminal, spellings
        for state, fallback, suffix in matcher._expected_links():
            if (failure[state], output[state]) != (fallback, suffix):
                raise ValueError("invalid compiled matcher failure or output link")
        matcher._index_relations(snapshot)
        return matcher

    def hits(self, text):
        state = 0
        for end, ch in enumerate(text, 1):
            while state and ch not in self.edges[state]:
                state = self.failure[state]
            state = self.edges[state].get(ch, 0)
            terminal = state if self.terminal[state] else self.output[state]
            while terminal:
                key = self.terminal[terminal]
                yield end - len(key), end, key
                terminal = self.output[terminal]


# Later particles in a chain attach to the preceding particle, so 받침 must
# be tested again there. Limit continuation to common case/focus markers.
_PARTICLE_TYPES = dict(_PARTICLE_RULE)
_PARTICLE_TYPES.update(dict.fromkeys("밖에 조차 마저 대로 같이 하고 엔 에선 껜 서".split(), "any"))
_PARTICLE_TYPES.update({"이든": "closed", "든": "open", "이라도": "closed", "라도": "open"})
_CONTINUATIONS = frozenset("부터 까지 만 도 뿐 은 는 이 가 을 를 의 조차 마저".split())
_MAX_PARTICLE_LEN = max(map(len, _PARTICLE_TYPES))


def _compatible(rule, last):
    if not ("가" <= last <= "힣"):
        return True
    jong = (ord(last) - 0xAC00) % 28
    return (rule == "any" or (rule == "closed" and jong != 0)
            or (rule == "open" and jong == 0) or (rule == "rieul_or_open" and jong in (0, 8))
            or (rule == "other_closed" and jong not in (0, 8)))


def _particles(tail, last, depth=0):
    if not tail:
        return ()
    if depth == 3:
        return None
    for length in range(1, min(_MAX_PARTICLE_LEN, len(tail)) + 1):
        part = tail[:length]
        rule = _PARTICLE_TYPES.get(part)
        if rule is None or (depth and part not in _CONTINUATIONS) or not _compatible(rule, last):
            continue
        if part == "서" and tail[length:]:
            continue
        rest = _particles(tail[length:], part[-1], depth + 1)
        if rest is not None:
            return (part, *rest)
    return None


def _full_end(text, end):
    """Find a bare boundary or a grammatical particle-only ending for a token."""
    stop = end
    while stop < len(text) and _word_char(text[stop]):
        stop += 1
        if stop - end > 3 * _MAX_PARTICLE_LEN:
            return None
    return stop if _particles(text[end:stop], text[end - 1]) is not None else None


_SUFFIX_TYPES = {
    **dict.fromkeys("장 장관 차관 청장 원장 위원장 총장 사장 회장 이사장 대표 담당자 직원".split(),
                    ("ROLE", "ROLE_OF")),
    **dict.fromkeys("노조 노동조합".split(), ("DERIVED_ORG", "DERIVED_FROM")),
    **dict.fromkeys("본부 지사 센터 사무국 연구원 연구소 지점".split(), ("ORG_UNIT", "PART_OF")),
}


def _analyze_tail(tail, last, matcher, ids):
    if not tail:
        return "", (), False
    chain = _particles(tail, last)
    readings = [("", chain)] if chain is not None else []
    suffixes = set() if readings else set(_SUFFIX_TYPES)
    for eid in ids:
        suffixes.update(matcher.compositions.get(eid, {}))
    for suffix in sorted(suffixes, key=len, reverse=True):
        if tail.startswith(suffix):
            chain = _particles(tail[len(suffix):], suffix[-1])
            if chain is not None:
                readings.append((suffix, chain))
    if not readings:
        return None
    # A registered suffix can itself spell a particle. The core is known,
    # but assigning the full expression to either entity would be a guess.
    suffix, particles = max(readings, key=lambda reading: len(reading[0]))
    return suffix, particles, len(readings) > 1


def resolve(snapshot, text, *, department=None, project=None, as_of=None, recover=True):
    """Find terms with original source spans and distinguish core and derived referents."""
    normalized, raw = _normalized_input(text)
    byte, utf16 = [0], [0]
    for ch in text:
        byte.append(byte[-1] + len(ch.encode("utf-8")))
        utf16.append(utf16[-1] + (2 if ord(ch) > 0xffff else 1))

    def span(start, end):
        return {"codepoint": {"start": start, "end": end},
                "byte": {"start": byte[start], "end": byte[end]},
                "utf16": {"start": utf16[start], "end": utf16[end]}}

    matcher = snapshot.matcher
    # Several keys can begin at one boundary (한국, 한국 전력, ...). Prefer
    # the longest after checking its scope and tail, then skip covered hits.
    matches = {}
    for start, end, key in matcher.hits(normalized):
        if raw[start] is None or raw[end] is None or (start and _word_char(normalized[start - 1])):
            continue
        matches.setdefault(start, []).append((end, key))

    token_ends = list(range(len(normalized) + 1))
    for index in range(len(normalized) - 1, -1, -1):
        if _word_char(normalized[index]):
            token_ends[index] = token_ends[index + 1]
    mentions = []
    consumed = 0
    for start, alternatives in sorted(matches.items()):
        if start < consumed:
            continue
        for end, key in reversed(alternatives):
            surfaces = matcher.spellings[key]
            ids = _eligible_ids(snapshot, surfaces, department, project, as_of)
            if not ids:
                continue
            stop = token_ends[end]
            if stop - end > matcher.max_suffix + 3 * _MAX_PARTICLE_LEN:
                continue
            analysis = _analyze_tail(normalized[end:stop], key[-1], matcher, ids)
            if analysis is None or raw[stop] is None:
                continue
            suffix, particles, uncertain_suffix = analysis
            suffix_end = raw[end + len(suffix)]
            if suffix_end is None:
                continue
            original = text[raw[start]:raw[end]]
            channel = "exact" if original in surfaces else "normalized"
            mention = {"surface": original, "span": span(raw[start], raw[end]),
                       "full_span": span(raw[start], raw[stop]), "mention_decision": "TERM",
                       "candidate_eligibility": dict(sorted(ids.items())),
                       "matched_surfaces": list(surfaces), "generation_channels": [channel]}
            if len(ids) == 1 and all(ids.values()):
                eid = next(iter(ids))
                mention["link_decision"] = "RESOLVED"
                mention["link_reason"] = "unique_eligible_alias"
                mention["resolved_entity"] = {"entity_id": eid, "canonical": snapshot.names[eid]}
            else:
                mention["link_decision"] = "AMBIGUOUS"
                mention["link_reason"] = "shared_alias" if len(ids) > 1 else "eligibility_unconfirmed"
                mention["prediction_set"] = {
                    "members": [{"kind": "ENTITY", "entity_id": eid} for eid in sorted(ids)]}
            if particles or suffix:
                mention["tail"] = {"particles": list(particles), "residual": suffix}
            if suffix:
                kind, relation = _SUFFIX_TYPES.get(suffix, ("REGISTERED", "COMPOSES_TO"))
                if uncertain_suffix:
                    kind, relation = "AMBIGUOUS", "UNKNOWN"
                mention["core_link"] = {"surface": original, "span": mention["span"],
                                        "relation": relation}
                full = {"surface": text[raw[start]:suffix_end], "span": span(raw[start], suffix_end),
                        "identity": "UNKNOWN" if uncertain_suffix else "DISTINCT_FROM_CORE",
                        "tail_class": kind}
                if mention["link_decision"] == "RESOLVED" and not uncertain_suffix:
                    registered = matcher.compositions.get(eid, {}).get(suffix, [])
                    if len(registered) == 1:
                        row = registered[0]
                        target = row["target_entity_id"]
                        if _entity_status(snapshot, target, department, project, as_of) is True:
                            full["composes_to"] = {"entity_id": target, "canonical": snapshot.names[target],
                                                   "from_entity_id": eid,
                                                   "relation_id": row.get("relation_id")}
                mention["full_surface"] = full
            mentions.append(mention)
            consumed = stop
            break
    mentions.extend(_extra_mentions(snapshot, text, mentions, span, department, project, as_of, recover))
    mentions.sort(key=lambda mention: mention["span"]["codepoint"]["start"])
    return {"mode": "symbolic", "mentions": mentions}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("compile", help="compile a JSON or YAML glossary to a file")
    build.add_argument("glossary", type=Path)
    build.add_argument("output", type=Path)
    raw = commands.add_parser("resolve", help="look up text using a source glossary (default)")
    raw.add_argument("glossary", type=Path)
    load = commands.add_parser("load", help="look up text using a compiled min snapshot")
    load.add_argument("snapshot", type=Path)
    for lookup in (raw, load):
        lookup.add_argument("text", nargs="?", help="input text (default: UTF-8 stdin)")
    argv = sys.argv[1:]
    if argv and argv[0] not in {*commands.choices, "-h", "--help"}:
        argv.insert(0, "resolve")  # Original positional CLI: GLOSSARY [TEXT].
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            if args.glossary.resolve() == args.output.resolve():
                raise ValueError("snapshot output must differ from the source glossary")
            save_snapshot(compile_snapshot(load_glossary(args.glossary)), args.output)
            return
        if args.command == "load":
            snapshot = load_snapshot(args.snapshot)
        else:
            snapshot = compile_snapshot(load_glossary(args.glossary))
        text = args.text if args.text is not None else sys.stdin.buffer.read().decode("utf-8")
        result = resolve(snapshot, text)
        sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"{parser.prog}: {exc}\n")


if __name__ == "__main__":
    main()
