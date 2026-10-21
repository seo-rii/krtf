"""New source-first fictional evidence-efficiency gold, with no resolver/model imports.

Source authorship and independent AI review precede inference. Confirmation
families are disjoint from development families; this is still synthetic gold,
not an independent sample from a real workplace or a human-verified corpus.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures/evidence_efficiency"
CASES_FILE = FIXTURE_DIR / "source_gold.json"
SOURCE_FILE = CASES_FILE
EXCLUSION_FILE = FIXTURE_DIR / "source_exclusion.json"
REVIEW_FILE = FIXTURE_DIR / "independent_review.json"
SOURCE_SHA256 = "0ab031e4425e3d7f58746a2fae89ef9c5ac096b71f44537d34512a6f9c81ecfe"
EXCLUSION_SHA256 = "eec97842292a9f7973a58dfc6f254fa2f8338e067c627e562766e65a79582d95"
# Pinned after an independent reviewer read all 64 final source/gold records.
REVIEW_SHA256: str | None = "51e4536d15a45d2cec50e1be4a82a9c1e741ae723ea4c6fb07752b4661f026eb"
ATTRIBUTES = ("jurisdiction", "temporal_status", "referent_kind", "scope")
DEVELOPMENT_FAMILIES = frozenset(
    f"ee26-family-{n:02d}" for n in (1, 5)
)
ALL_FAMILIES = frozenset(f"ee26-family-{n:02d}" for n in range(1, 9))
CONFIRMATION_FAMILIES = ALL_FAMILIES - DEVELOPMENT_FAMILIES


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
        or artifact.get("dataset_id") != "ktrf-evidence-efficiency-source-v1"
        or artifact.get("annotation_origin") != "AI_AUTHORED"
        or artifact.get("human_verified") is not False
        or not _nonempty(artifact.get("authored_by"))
        or not _nonempty(artifact.get("gold_source"))
        or artifact.get("source_scenario_styles") != 4
        or artifact.get("split_design") != {
            "unit": "family",
            "development_families": 2,
            "confirmation_families": 6,
            "determined_before_inference": True,
        }
    ):
        raise ValueError("source-first AI annotation and family split metadata required")
    families = artifact.get("families", [])
    if len(families) != 8 or {f.get("family_id") for f in families} != ALL_FAMILIES:
        raise ValueError("exactly eight predeclared source families required")
    records = []
    case_ids, documents, text_hashes, entity_ids, prior_names = set(), set(), set(), set(), set()
    events, parents = set(), set()
    styles = Counter()
    for family in families:
        fid = family["family_id"]
        split = "development" if fid in DEVELOPMENT_FAMILIES else "confirmation"
        style = family.get("scenario_style")
        expected_style = ("work_ledger", "support_dialogue", "change_log", "handover_memo")[(int(fid[-2:]) - 1) % 4]
        if style != expected_style:
            raise ValueError("four source writing styles fixed before inference required")
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
        for term in terms:
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
            if eid in entity_ids or eid in family_ids:
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
        shared_target_count = 0
        for original in cases:
            row = deepcopy(original)
            required = ("case_id", "document_id", "event_id", "parent_document_id", "text", "target_surface", "stratum", "rationale")
            if any(not _nonempty(row.get(k)) for k in required):
                raise ValueError("source document, target and rationale required")
            text = row["text"]
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
            shared_target_count += row["target_surface"] in shared
            # Constraints are term metadata, never an annotation of the case.
            if row.get("evidence_design") not in {
                "EXPLICIT_ATTRIBUTES", "CROSS_SENTENCE_ATTRIBUTES",
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
            row.update(
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
                    "dataset_id": "ktrf-evidence-efficiency-source-v1",
                    "family_id": fid,
                    "human_verified": False,
                    "authored_before_resolver": True,
                    "authored_before_generation": True,
                },
            )
            records.append(row)
        if family_labels["LINK"] != 4 or family_labels["AMBIGUOUS"] != 1 or shared_target_count != 2:
            raise ValueError("four LINK/four negative and two shared-alias targets per family required")
    if set(styles) != set(artifact.get("scenario_styles", [])) or set(styles.values()) != {2}:
        raise ValueError("two families per new writing style required")
    return records


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
        or len(exclusion.get("tracked_json_yaml_source_files", [])) < 23
    ):
        raise ValueError("source family/name exclusion proof differs from frozen design")


def load_evidence_efficiency_records(
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
