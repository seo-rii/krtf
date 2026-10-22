"""Fresh final-confirmation source-first fictional evidence-closure gold, with no resolver/model imports.

Source authorship and independent AI review precede inference. All twelve families are sealed final confirmation; this is still synthetic gold,
not an independent sample from a real workplace or a human-verified corpus.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures/evidence_closure"
CASES_FILE = FIXTURE_DIR / "source_gold.json"
SOURCE_FILE = CASES_FILE
EXCLUSION_FILE = FIXTURE_DIR / "source_exclusion.json"
REVIEW_FILE = FIXTURE_DIR / "independent_review.json"
SOURCE_SHA256 = "e75e65721ef4344fb21f889561fb3821c609fd4f77d619ba25b5d86f2439424c"
EXCLUSION_SHA256 = "1ba83eef886ba566012deabfa0f66686d8d4f2779edff99906a377f36ed9049e"
# Must be pinned by the independent reviewer before any model/resolver preparation.
REVIEW_SHA256: str | None = "7b80997a7dbcea618b0ccb5cad9d7cf53ef50e72408646a8560c8c7c408c5c17"
ATTRIBUTES = ("jurisdiction", "temporal_status", "referent_kind", "scope")
DEVELOPMENT_FAMILIES = frozenset()
ALL_FAMILIES = frozenset(f"ec26-family-{n:02d}" for n in range(1, 13))
CONFIRMATION_FAMILIES = ALL_FAMILIES
BALANCE_DESIGN = {
    "entity_roles": ["a", "b"],
    "jurisdiction_by_role": {role: {"domestic": 6, "foreign": 6} for role in ("a", "b")},
    "referent_kind_by_role": {role: {"procedure": 6, "system": 6} for role in ("a", "b")},
    "shared_alias_link_by_role": {"a": 6, "b": 6},
    "length_by_label": {
        "long": {"LINK": 24, "negative": 24},
        "short": {"LINK": 24, "negative": 24},
    },
    "long_document_codepoints": {"minimum": 1200, "maximum": 2000},
    "shared_alias_link_jurisdiction": {"domestic": 6, "foreign": 6},
    "shared_alias_link_referent_kind": {"procedure": 6, "system": 6},
    "shared_alias_link_temporal_status": {"current": 6, "pilot": 6},
}

def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _span(span: object, text: str) -> bool:
    return (
        isinstance(span, dict)
        and set(span) == {"start", "end"}
        and all(type(v) is int for v in span.values())
        and 0 <= span["start"] < span["end"] <= len(text)
    )


def validate_source_artifact(artifact: dict) -> list[dict]:
    """Validate source identity/structure and return independent deep copies.

    This is deliberately separate from the byte seal so mutation regressions
    exercise the substantive invariants, rather than just comparing a hash.
    It does not approve an artifact for inference; use the sealed loader.
    """
    if (
        artifact.get("schema_version") != 1
        or artifact.get("dataset_id") != "ktrf-evidence-closure-source-v1"
        or artifact.get("annotation_origin") != "AI_AUTHORED"
        or artifact.get("human_verified") is not False
        or not _nonempty(artifact.get("authored_by"))
        or not _nonempty(artifact.get("gold_source"))
        or artifact.get("reuse_policy") != "FINAL_CONFIRMATION_ONLY_NO_METHOD_SELECTION"
        or artifact.get("source_scenario_styles") != 3
        or artifact.get("balance_design") != BALANCE_DESIGN
        or artifact.get("split_design") != {
            "unit": "family",
            "development_families": 0,
            "confirmation_families": 12,
            "determined_before_inference": True,
        }
    ):
        raise ValueError("source-first AI annotation and family split metadata required")
    families = artifact.get("families", [])
    if len(families) != 12 or {f.get("family_id") for f in families} != ALL_FAMILIES:
        raise ValueError("exactly twelve predeclared final-confirmation families required")
    records = []
    case_ids, documents, text_hashes, entity_ids, prior_names = set(), set(), set(), set(), set()
    events, parents = set(), set()
    styles = Counter()
    role_jurisdictions = {role: Counter() for role in ("a", "b")}
    role_kinds = {role: Counter() for role in ("a", "b")}
    shared_roles, shared_jurisdictions, shared_kinds, shared_statuses = (Counter() for _ in range(4))
    lengths_by_label = {length: Counter() for length in ("long", "short")}
    for family in families:
        fid = family["family_id"]
        split = "development" if fid in DEVELOPMENT_FAMILIES else "confirmation"
        style = family.get("scenario_style")
        expected_style = ("approval_minutes", "vendor_incident_email", "operations_handover")[(int(fid[-2:]) - 1) // 4]
        if style != expected_style:
            raise ValueError("three source writing styles fixed before inference required")
        styles[style] += 1
        if family.get("evaluation_split") != split:
            raise ValueError("source family split differs from pre-inference declaration")
        if not _nonempty(family.get("source_facts")):
            raise ValueError("family source facts required")
        terms = family.get("terms")
        if not isinstance(terms, list) or len(terms) != 2:
            raise ValueError("two distinct glossary entities per family required")
        family_ids = set()
        family_names = set()
        constraints = {}
        surfaces = []
        for role, term in zip(("a", "b"), terms):
            if (
                not _nonempty(term.get("key"))
                or not _nonempty(term.get("canonical"))
                or not _nonempty(term.get("short_definition"))
                or not isinstance(term.get("surfaces"), list)
                or len(term["surfaces"]) != 2
                or len(set(term["surfaces"])) != 2
                or any(not _nonempty(v) for v in term["surfaces"])
            ):
                raise ValueError("whole definitions and two distinct aliases required")
            eid = "global:" + term["key"]
            if term["key"] != fid + "-" + role or eid in entity_ids or eid in family_ids:
                raise ValueError("globally unique source entity identity required")
            family_ids.add(eid)
            names = {term["canonical"], *term["surfaces"]}
            family_names.update(names)
            surfaces.append(set(term["surfaces"]))
            attributes = term.get("applicability")
            if (
                not isinstance(attributes, dict)
                or set(attributes) != set(ATTRIBUTES)
                or any(
                    not isinstance(v, list)
                    or not v
                    or len(set(v)) != len(v)
                    or any(not _nonempty(item) for item in v)
                    for v in attributes.values()
                )
            ):
                raise ValueError("four entity-level applicability attributes required")
            if any(
                value not in term["short_definition"]
                for values in attributes.values()
                for value in values
            ):
                raise ValueError("applicability must be explicitly grounded in whole definition")
            constraints[eid] = deepcopy(attributes)
            if (
                len(attributes["jurisdiction"]) != 1
                or attributes["referent_kind"] not in (["절차"], ["시스템"])
                or attributes["temporal_status"] not in (["현행"], ["시험 운영"])
            ):
                raise ValueError("source entity balance requires one country, kind and status")
            role_jurisdictions[role]["domestic" if attributes["jurisdiction"] == ["대한민국"] else "foreign"] += 1
            role_kinds[role]["procedure" if attributes["referent_kind"] == ["절차"] else "system"] += 1
        shared = surfaces[0] & surfaces[1]
        if (
            len(shared) != 1
            or terms[0]["canonical"] == terms[1]["canonical"]
            or family_names & prior_names
        ):
            raise ValueError("one shared alias per family and no cross-family lexical overlap required")
        prior_names.update(family_names)
        entity_ids.update(family_ids)
        cases = family.get("cases", [])
        if len(cases) != 8:
            raise ValueError("eight separately authored source documents per family required")
        cleaned_terms = [
            {k: deepcopy(v) for k, v in term.items() if k != "applicability"}
            for term in terms
        ]
        family_labels = Counter()
        family_lengths = {length: Counter() for length in ("long", "short")}
        shared_target_count = 0
        for original in cases:
            row = deepcopy(original)
            required = ("case_id", "document_id", "event_id", "parent_document_id", "text", "target_surface", "stratum", "rationale")
            if any(not _nonempty(row.get(k)) for k in required):
                raise ValueError("source document, target and rationale required")
            text = row["text"]
            length = row.get("document_length_stratum")
            if (
                length not in {"long", "short"}
                or (length == "long" and not 1200 <= len(text) <= 2000)
                or (length == "short" and len(text) >= 1200)
                or not isinstance(row.get("source_features"), list)
                or (length == "long" and "long_complete_source" not in row["source_features"])
            ):
                raise ValueError("long source documents must preserve 1200..2000 codepoints and length metadata")
            digest = hashlib.sha256(text.encode()).hexdigest()
            if row.get("document_sha256") != digest:
                raise ValueError("source text does not match document content hash")
            if (
                row["case_id"] in case_ids
                or row["document_id"] in documents
                or digest in text_hashes
                or not row["case_id"].startswith(fid + ":")
                or not row["document_id"].startswith(fid + ":")
                or row["event_id"] in events
                or row["parent_document_id"] in parents
                or not row["event_id"].startswith(fid + ":")
                or not row["parent_document_id"].startswith(fid + ":")
            ):
                raise ValueError("unique case, document and source text identities required")
            events.add(row["event_id"])
            parents.add(row["parent_document_id"])
            case_ids.add(row["case_id"])
            documents.add(row["document_id"])
            text_hashes.add(digest)
            core, full = row.get("target_core_span"), row.get("target_full_span")
            if (
                not _span(core, text)
                or not _span(full, text)
                or not full["start"] <= core["start"] < core["end"] <= full["end"]
                or text[full["start"] : full["end"]] != row["target_surface"]
            ):
                raise ValueError("exact codepoint source target spans required")
            occurrences = [match.start() for match in re.finditer(re.escape(row["target_surface"]), text)]
            occurrence_index = row.get("target_occurrence_index")
            if (
                type(occurrence_index) is not int
                or not 0 <= occurrence_index < len(occurrences)
                or occurrences[occurrence_index] != full["start"]
                or text[core["start"]:core["end"]] not in family_names
            ):
                raise ValueError("selected source occurrence must match the exact authored occurrence index")
            eid, gold = row.get("expected_entity_id"), row.get("gold", {})
            label = gold.get("label")
            if (
                label not in {"LINK", "NIL", "NON_MENTION", "COMPOSITIONAL", "AMBIGUOUS"}
                or gold.get("entity_ref") != eid
                or (label == "LINK") != (eid is not None)
                or (eid is not None and eid not in family_ids)
                or gold.get("full_identity")
                != ("SAME" if eid else "DISTINCT_OR_UNSUPPORTED")
            ):
                raise ValueError("gold entity must belong to the same source glossary family")
            if eid is not None:
                term = next(t for t in terms if "global:" + t["key"] == eid)
                if text[core["start"] : core["end"]] not in {
                    term["canonical"], *term["surfaces"]
                }:
                    raise ValueError("LINK target identity differs from authored glossary")
            qa = row.get("qa", {})
            if (
                not _nonempty(qa.get("question"))
                or not isinstance(qa.get("answers"), list)
                or any(not _nonempty(v) for v in qa["answers"])
                or qa.get("is_impossible") is not (eid is None)
                or qa.get("requires_terminology") is not True
                or (eid is not None and qa["answers"] != [term["canonical"]])
                or (eid is None and qa["answers"])
            ):
                raise ValueError("source-authored QA identity metadata required")
            family_labels[label] += 1
            category = "LINK" if eid is not None else "negative"
            family_lengths[length][category] += 1
            lengths_by_label[length][category] += 1
            shared_target_count += row["target_surface"] in shared
            if label == "COMPOSITIONAL" and (
                full["start"] != core["start"]
                or text[core["end"]:full["end"]] != "담당자"
            ):
                raise ValueError("compositional gold must preserve the person suffix outside the core")
            if eid is not None and row["target_surface"] in shared:
                shared_roles[eid[-1]] += 1
                attrs = constraints[eid]
                shared_jurisdictions["domestic" if attrs["jurisdiction"] == ["대한민국"] else "foreign"] += 1
                shared_kinds["procedure" if attrs["referent_kind"] == ["절차"] else "system"] += 1
                shared_statuses["current" if attrs["temporal_status"] == ["현행"] else "pilot"] += 1
            # Constraints are term metadata, never an annotation of the case.
            if row.get("evidence_design") not in {
                "EXPLICIT_ATTRIBUTES", "CROSS_PARAGRAPH_ATTRIBUTES",
                "IMPLICIT_ATTRIBUTE_POSITIVE", "NEGATIVE",
            }:
                raise ValueError("source-authored evidence design required")
            if (row["evidence_design"] == "NEGATIVE") != (eid is None):
                raise ValueError("evidence design must preserve source-authored identity label")
            if row["evidence_design"] == "IMPLICIT_ATTRIBUTE_POSITIVE":
                missing = [
                    key for key, values in constraints[eid].items()
                    if not any(value in text for value in values)
                ]
                if not {"jurisdiction", "temporal_status"} <= set(missing):
                    raise ValueError("implicit positive must omit country/status literal evidence")
            _validate_support_annotations(row, family_ids, constraints)
            row.update(
                document_length_band=length,
                family_id=fid,
                scenario_style=style,
                evaluation_split=split,
                terms=deepcopy(cleaned_terms),
                entity_constraints=deepcopy(constraints),
                source_facts=family["source_facts"],
                annotation_origin="AI_AUTHORED",
                human_verified=False,
                source_provenance={
                    "kind": "fictional_business_world",
                    "dataset_id": "ktrf-evidence-closure-source-v1",
                    "family_id": fid,
                    "human_verified": False,
                    "authored_before_resolver": True,
                    "authored_before_generation": True,
                },
            )
            records.append(row)
        if family_labels["LINK"] != 4 or family_labels["AMBIGUOUS"] != 1 or shared_target_count != 2:
            raise ValueError("four LINK/four negative and two shared-alias targets per family required")
        if any(counts != {"LINK": 2, "negative": 2} for counts in family_lengths.values()):
            raise ValueError("long/short source labels must be balanced within each family")
    if set(styles) != set(artifact.get("scenario_styles", [])) or set(styles.values()) != {4}:
        raise ValueError("four families per new writing style required")
    if (
        role_jurisdictions != BALANCE_DESIGN["jurisdiction_by_role"]
        or role_kinds != BALANCE_DESIGN["referent_kind_by_role"]
        or shared_roles != BALANCE_DESIGN["shared_alias_link_by_role"]
        or shared_jurisdictions != BALANCE_DESIGN["shared_alias_link_jurisdiction"]
        or shared_kinds != BALANCE_DESIGN["shared_alias_link_referent_kind"]
        or shared_statuses != BALANCE_DESIGN["shared_alias_link_temporal_status"]
        or lengths_by_label != BALANCE_DESIGN["length_by_label"]
    ):
        raise ValueError("source role, shared-target attributes and length labels must match pre-inference balance")
    return records


def _validate_support_annotations(row: dict, family_ids: set[str], constraints: dict) -> None:
    """Check author-provided literal spans without generating or changing labels."""
    annotations = row.get("source_support_annotations", {})
    text = row["text"]
    if (
        annotations.get("authored_before_resolver") is not True
        or annotations.get("authored_before_generation") is not True
        or not _nonempty(annotations.get("attribution_notes"))
        or not isinstance(annotations.get("support_units"), list)
        or not isinstance(annotations.get("contradictions"), list)
        or not isinstance(annotations.get("allowed_missing_attributes"), list)
    ):
        raise ValueError("source-authored support attribution and provenance required")
    supported = set()
    for unit in annotations["support_units"]:
        attribute, value, eid = unit.get("attribute"), unit.get("value"), unit.get("entity_id")
        span = unit.get("span")
        if (
            attribute not in ATTRIBUTES
            or eid not in family_ids
            or value not in constraints[eid][attribute]
            or unit.get("assertion") != "SUPPORT"
            or not _span(span, text)
            or text[span["start"]:span["end"]] != value
        ):
            raise ValueError("support attribute must be literally grounded and owned by a family entity")
        if eid == row["expected_entity_id"]:
            supported.add(attribute)
    missing = annotations["allowed_missing_attributes"]
    if len(set(missing)) != len(missing) or not set(missing) <= set(ATTRIBUTES):
        raise ValueError("missing attribute declarations must be unique known attributes")
    if row["expected_entity_id"] is not None:
        if supported & set(missing) or supported | set(missing) != set(ATTRIBUTES):
            raise ValueError("LINK support and explicitly allowed omissions must partition four attributes")
        if annotations["contradictions"]:
            raise ValueError("LINK source annotation cannot contain an unresolved contradiction")
        if row["evidence_design"] == "CROSS_PARAGRAPH_ATTRIBUTES" and "\n\n" not in text:
            raise ValueError("cross-paragraph source must preserve paragraph boundaries")
    for contradiction in annotations["contradictions"]:
        if (
            contradiction.get("attribute") not in ATTRIBUTES
            or not _span(contradiction.get("span"), text)
            or not _nonempty(contradiction.get("reason"))
        ):
            raise ValueError("source contradictions require exact spans and ownership rationale")
    if row["gold"]["label"] in {"NIL", "NON_MENTION", "COMPOSITIONAL"} and not annotations["contradictions"]:
        raise ValueError("negative sources must identify the contradiction or referent mismatch")


def _validate_exclusion(artifact: dict, exclusion: dict) -> None:
    new_names = {
        value
        for family in artifact["families"]
        for term in family["terms"]
        for value in [term["canonical"], *term["surfaces"]]
    }
    if (
        exclusion.get("schema_version") != 1
        or exclusion.get("source_sha256") != SOURCE_SHA256
        or exclusion.get("new_name_string_overlap_count") != 0
        or set(exclusion.get("new_family_ids", [])) != ALL_FAMILIES
        or set(exclusion.get("new_lexical_names", [])) != new_names
        or exclusion.get("collisions") != []
        or len(exclusion.get("tracked_json_yaml_source_files", [])) < 20
    ):
        raise ValueError("source family/name exclusion proof differs from frozen design")


def load_evidence_closure_records(
    split: str | None = None,
    *,
    require_review: bool = True,
    path: str | Path = CASES_FILE,
    review_path: str | Path = REVIEW_FILE,
    exclusion_path: str | Path = EXCLUSION_FILE,
) -> list[dict]:
    """Load sealed data without invoking a resolver, retrieval engine or model.

    ``require_review=False`` is solely for source review and unit diagnostics.
    Experiment preparation must retain the default strict review requirement.
    """
    if split not in {None, "development", "confirmation"}:
        raise ValueError("split must be development or confirmation")
    if file_sha256(path) != SOURCE_SHA256:
        raise ValueError("source artifact differs from immutable source/gold seal")
    if file_sha256(exclusion_path) != EXCLUSION_SHA256:
        raise ValueError("source exclusion artifact differs from frozen seal")
    artifact = json.loads(Path(path).read_text())
    exclusion = json.loads(Path(exclusion_path).read_text())
    records = validate_source_artifact(artifact)
    _validate_exclusion(artifact, exclusion)
    if require_review:
        if REVIEW_SHA256 is None or not Path(review_path).is_file():
            raise ValueError("independent source/gold review is required before inference")
        if file_sha256(review_path) != REVIEW_SHA256:
            raise ValueError("independent review differs from immutable review seal")
        review = json.loads(Path(review_path).read_text())
        if (
            review.get("schema_version") != 1
            or review.get("status") != "APPROVED"
            or review.get("source_sha256") != SOURCE_SHA256
            or not _nonempty(review.get("reviewer"))
            or review["reviewer"] == artifact["authored_by"]
            or review.get("reviewed_case_ids") != sorted(r["case_id"] for r in records)
            or review.get("reviewed_before_resolver") is not True
            or review.get("reviewed_before_generation") is not True
            or review.get("human_verified") is not False
            or type(review.get("unresolved_disagreements")) is not int
            or review["unresolved_disagreements"] != 0
        ):
            raise ValueError("independent complete pre-inference source/gold review required")
    for row in records:
        row["source_provenance"].update(
            source_sha256=SOURCE_SHA256,
            exclusion_sha256=EXCLUSION_SHA256,
            review_sha256=REVIEW_SHA256 if require_review else None,
            independent_ai_reviewed=require_review,
        )
    return [row for row in records if split is None or row["evaluation_split"] == split]
