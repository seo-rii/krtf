"""Measure pack placement and a generic semantic check on frozen routing cases.

The previous 96 cases remain explicitly exposed diagnostics. Another 64 cases
use new authored entity families; neither split is deployment-risk evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from eval.extended_safety import STRATA, load_cases as load_prior_cases
from eval.hf_qa import canonical
from eval.prepare_followup import MAX_MODEL_LEN, RESERVED_OUTPUT_TOKENS, _token_ids
from eval.production_grounding import build_document_requests, validate_production_requests
from ktrf.context import CharTokenCounter
from ktrf.glossary import load_glossary
from ktrf.registry.simple_schema import compile_simple_terms
from ktrf.snapshot import compile_snapshot

ROOT = Path(__file__).resolve().parents[1]
CASES_FILE = ROOT / "eval/data/diagnostic_safety_cases.json"
# Set only after independent source/gold review, before resolver preparation.
REVIEWED_CASE_FILE_SHA256 = "05a92bc26e0c27ab878bac3df9cc312f6f3ab8e6eb2c179172b05b547e4cac71"
EXPERIMENT = "safety_robustness"
CONDITIONS = ("pack_first_baseline", "pack_last_baseline",
              "pack_first_semantic_check", "pack_last_semantic_check")
SEMANTIC_POLICY = (
    "추가 의미 확인: 이름이 같다는 사실만으로 동일한 대상이라고 판단하지 않는다. "
    "문서에 명시된 국가·관할, 시점·설립 이력, 대상의 종류, 전체 표현의 의미를 "
    "후보 정의와 대조한다. 서로 모순되거나 의미를 하나로 구별할 수 없으면 entity_id는 null로 둔다. "
    "기관 자체와 기관장·산출물 같은 파생 대상을 구별한다. "
    "이 확인은 실행 guard의 허용 범위를 넓히지 않으며 검증되지 않은 ID를 허용하지 않는다."
)
_METADATA = {"production_system", "production_user", "production_estimated_input_tokens",
             "production_experiment", "production_row_keys", "production_row_sha256",
             "evaluation_split", "placement", "semantic_check"}


def _sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def load_cases(path=CASES_FILE):
    """Validate exactly 16 new source-authored families before any resolution."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if (data.get("schema_version") != 1 or data.get("annotation_origin") != "AI_AUTHORED"
            or data.get("human_verified") is not False or not data.get("authored_by")
            or not data.get("gold_source") or not data.get("limitations")):
        raise ValueError("explicit AI authorship, source gold and limitations required")
    families = data.get("families")
    if not isinstance(families, list) or len(families) != 16:
        raise ValueError("exactly 16 fresh families required")
    prior = load_prior_cases()
    prior_ids = {f["family_id"] for f in prior["families"]}
    prior_terms = {t["key"] for f in prior["families"] for t in f["terms"]}
    prior_names = {t["canonical"] for f in prior["families"] for t in f["terms"]}
    prior_names.update(s for f in prior["families"] for t in f["terms"] for s in t.get("surfaces", []))
    family_ids, case_ids, texts, entity_keys, strata = set(), set(), set(), set(), Counter()
    for family in families:
        fid = family.get("family_id")
        if not isinstance(fid, str) or not fid or fid in family_ids or fid in prior_ids:
            raise ValueError("fresh family identity must be unique and disjoint from prior families")
        family_ids.add(fid)
        terms = family.get("terms")
        if (family.get("glossary_mode") != "authored" or family.get("stratum") not in STRATA
                or family.get("domain") != "fictional_robustness" or not family.get("source_facts")
                or not isinstance(terms, list) or not terms or len(family.get("cases", [])) != 4):
            raise ValueError("fictional source facts, authored terms and four cases required")
        entities = set()
        for term in terms:
            key = term.get("key")
            surfaces = term.get("surfaces", [])
            if (not isinstance(key, str) or not key or key in entity_keys or key in prior_terms
                    or not isinstance(term.get("canonical"), str) or not term["canonical"]
                    or not term.get("short_definition") or not isinstance(surfaces, list)
                    or any(not isinstance(s, str) or not s for s in surfaces)
                    or ({term["canonical"]} | set(surfaces)) & prior_names):
                raise ValueError("fresh entities and names must be disjoint from prior terms")
            entity_keys.add(key)
            entities.add("global:" + key)
        positives = 0
        for case in family["cases"]:
            cid, text, target, span = (case.get(k) for k in ("case_id", "text", "target_surface", "target_span"))
            if (not isinstance(cid, str) or not cid.startswith(fid + ":") or cid in case_ids
                    or not isinstance(text, str) or not text or text in texts
                    or not isinstance(target, str) or not target or not isinstance(span, list)
                    or len(span) != 2 or any(type(n) is not int for n in span)
                    or not 0 <= span[0] < span[1] <= len(text) or text[span[0]:span[1]] != target):
                raise ValueError("unique source case and exact target span required")
            case_ids.add(cid)
            texts.add(text)
            gold = case.get("gold", {})
            label, eid = gold.get("label"), gold.get("entity_ref")
            if (label not in {"LINK", "NIL", "NON_MENTION", "AMBIGUOUS", "COMPOSITIONAL"}
                    or (label == "LINK") != (eid is not None)
                    or (eid is not None and (eid not in entities or gold.get("full_identity") != "SAME"))
                    or not case.get("rationale")):
                raise ValueError("source-authored semantic gold and rationale required")
            if label == "COMPOSITIONAL":
                core = gold.get("core_surface")
                if (gold.get("full_identity") != "DISTINCT" or not isinstance(core, str)
                        or not core or core == target or core not in target
                        or gold.get("core_entity_ref") not in entities):
                    raise ValueError("whole-expression gold must distinguish the registered core")
            positives += label == "LINK"
            strata[family["stratum"]] += 1
        if positives != 2:
            raise ValueError("each family requires two LINK and two non-LINK cases")
    if dict(strata) != {key: 16 for key in STRATA}:
        raise ValueError("four equally sized semantic strata required")
    return data


def reconstruct_variant(row, condition):
    """Return exact system/user strings from sealed original production prompts."""
    if condition not in CONDITIONS:
        raise ValueError("unknown robustness condition")
    system, user = row["production_system"], row["production_user"]
    if condition.startswith("pack_last") and row["injected"]:
        prefix = row["prompt_fragment"] + "\n"
        if not user.startswith(prefix):
            raise ValueError("sealed production prompt must start with the injected pack")
        user = user[len(prefix):] + "\n" + row["prompt_fragment"]
    if condition.endswith("semantic_check"):
        system += "\n" + SEMANTIC_POLICY
    return system, user


def _production_row(row):
    keys = row.get("production_row_keys")
    if (not isinstance(keys, list) or not keys or len(set(keys)) != len(keys)
            or any(not isinstance(k, str) or k not in row or k in _METADATA for k in keys)):
        raise ValueError("original production field inventory required")
    baseline = {key: deepcopy(row[key]) for key in keys}
    baseline.update(condition="production", experiment=row["production_experiment"],
        system=row["production_system"], user=row["production_user"],
        estimated_input_tokens=row["production_estimated_input_tokens"])
    if _sha(baseline) != row.get("production_row_sha256"):
        raise ValueError("sealed original production row changed")
    return baseline


def validate_robustness_requests(rows):
    """Reject changed source/pack, asymmetric conditions, or split contamination."""
    if not isinstance(rows, list) or len(rows) != 640 or any(not isinstance(r, dict) for r in rows):
        raise ValueError("complete 160-case by four-condition matrix required")
    groups, family_splits, sources = defaultdict(list), defaultdict(set), []
    for row in rows:
        condition, split = row.get("condition"), row.get("evaluation_split")
        if (condition not in CONDITIONS or split not in {"exposed_diagnostic", "fresh_family"}
                or row.get("experiment") != EXPERIMENT or row.get("task") != "structured_routing"
                or row.get("repeat_id") != 0 or type(row.get("repeat_id")) is not int
                or row.get("placement") != ("pack_first" if condition.startswith("pack_first") else "pack_last")
                or row.get("semantic_check") is not condition.endswith("semantic_check")):
            raise ValueError("unknown robustness condition, split or metadata")
        if any(key not in row for key in _METADATA):
            raise ValueError("sealed production metadata required")
        baseline = _production_row(row)
        if (row.get("source_text") != row.get("text")
                or row.get("parent_document_id") != row.get("document_id")
                or row.get("positive_gold") is not (row.get("expected_entity_id") is not None)
                or row.get("expected_answers") != []
                or row.get("independent_validation") is not False):
            raise ValueError("original semantic source metadata changed")
        if (row.get("system"), row.get("user")) != reconstruct_variant(row, condition):
            raise ValueError("robustness variant prompt differs from sealed production source")
        if row.get("estimated_input_tokens") != CharTokenCounter().count(row["system"] + row["user"]):
            raise ValueError("variant token estimate differs from rendered prompts")
        groups[row["case_id"]].append((row, baseline))
        family_splits[row["family_id"]].add(split)
    if any(len(splits) != 1 for splits in family_splits.values()):
        raise ValueError("a family cannot cross evaluation splits")
    split_counts, split_families, strata = Counter(), defaultdict(set), defaultdict(Counter)
    for group in groups.values():
        if len(group) != 4 or {r["condition"] for r, _ in group} != set(CONDITIONS):
            raise ValueError("each case requires every condition exactly once")
        row, source = group[0]
        if any(other != source or candidate["evaluation_split"] != row["evaluation_split"]
               for candidate, other in group):
            raise ValueError("variants must preserve identical source, gold and complete pack")
        sources.append(source)
        split = row["evaluation_split"]
        split_counts[split] += 1
        split_families[split].add(row["family_id"])
        strata[split][row["stratum"]] += 1
    if (dict(split_counts) != {"exposed_diagnostic": 96, "fresh_family": 64}
            or {s: len(v) for s, v in split_families.items()} != {"exposed_diagnostic": 24, "fresh_family": 16}
            or any(dict(strata[s]) != {key: n for key in STRATA}
                   for s, n in (("exposed_diagnostic", 24), ("fresh_family", 16)))):
        raise ValueError("predeclared split and family counts must be preserved")
    validate_production_requests(sources, check_current_policy=False)
    return rows


def prepare_robustness(*, prior_safety_envelope, code_revision, tokenizers, models):
    """Prepare paired requests without reading model outputs or selecting errors."""
    if (not code_revision or set(models) != {"gemma12b", "qwen27b"}
            or set(tokenizers) != set(models)):
        raise ValueError("frozen revision and both matching actual model tokenizers required")
    artifact = load_cases()
    gold_sha = _sha(artifact)
    case_file_sha = hashlib.sha256(CASES_FILE.read_bytes()).hexdigest()
    if case_file_sha != REVIEWED_CASE_FILE_SHA256:
        raise ValueError("source fixture requires independent gold review before resolution")
    if isinstance(prior_safety_envelope, (str, Path)):
        prior = json.loads(Path(prior_safety_envelope).read_text(encoding="utf-8"))
    else:
        prior = deepcopy(prior_safety_envelope)
    protocol = prior.get("protocol", {}) if isinstance(prior, dict) else {}
    if (protocol.get("kind") != "ktrf_extended_v1" or protocol.get("phase") != "FINAL_FROZEN"
            or protocol.get("experiment") != "semantic_safety" or protocol.get("conditions") != ["production"]
            or protocol.get("repeat_count") != 1 or not prior.get("provenance", {}).get("code_revision")):
        raise ValueError("prior sealed semantic-safety envelope required")
    old = prior.get("requests")
    validate_production_requests(old, check_current_policy=False)
    prior_authored = load_prior_cases()
    source_cases = {case["case_id"]: case for f in prior_authored["families"] for case in f["cases"]}
    if len(old) != 96 or {row["document_id"] for row in old} != set(source_cases):
        raise ValueError("all 96 exposed source cases must be retained")
    for row in old:
        source = source_cases[row["document_id"]]
        if (row["task"] != "structured_routing" or any(row[k] != source[k]
                for k in ("text", "target_surface", "target_span", "gold"))):
            raise ValueError("prior source semantics differ from sealed authored cases")
    fresh, snapshots = [], {}
    for family in artifact["families"]:
        fid = family["family_id"]
        glossary = load_glossary(compile_simple_terms({"terms": deepcopy(family["terms"])},
            scope="global", glossary_id="diagnostic-safety:" + fid))
        snapshot = compile_snapshot(glossary, run_conformance=False, tenant_id="diagnostic-safety:" + fid)
        snapshots[fid] = snapshot.snapshot_id
        definitions = {"global:" + t["key"]: t["short_definition"] for t in family["terms"]}
        for case in family["cases"]:
            eid = case["gold"]["entity_ref"]
            built = build_document_requests(snapshot,
                document_id=case["case_id"], family_id=fid, domain=family["domain"],
                stratum=family["stratum"], text=case["text"], target_surface=case["target_surface"],
                target_span=case["target_span"], gold=deepcopy(case["gold"]),
                expected_answer=definitions[eid] if eid else None,
                provenance={"source": "authored_diagnostic_safety", "annotation_origin": "AI_AUTHORED",
                    "human_verified": False, "source_case_sha256": _sha(case),
                    "authored_gold_sha256": gold_sha, "source_facts_sha256": _sha(family["source_facts"])})
            row = next(r for r in built if r["task"] == "structured_routing")
            row.update(experiment="semantic_safety", repeat_id=0, parent_document_id=case["case_id"],
                source_text=case["text"], expected_answers=[], positive_gold=eid is not None,
                decoding_mode="json_schema", independent_validation=False,
                semantic_subtype=case["gold"]["label"])
            fresh.append(row)
    if _sha(artifact) != gold_sha:
        raise ValueError("authored source changed during resolution")
    validate_production_requests(fresh)
    rows = []
    for split, originals in (("exposed_diagnostic", old), ("fresh_family", fresh)):
        for base in originals:
            for condition in CONDITIONS:
                row = deepcopy(base)
                row.update(experiment=EXPERIMENT, condition=condition, evaluation_split=split,
                    placement="pack_first" if condition.startswith("pack_first") else "pack_last",
                    semantic_check=condition.endswith("semantic_check"),
                    production_system=base["system"], production_user=base["user"],
                    production_estimated_input_tokens=base["estimated_input_tokens"],
                    production_experiment=base["experiment"], production_row_keys=sorted(base),
                    production_row_sha256=_sha(base))
                row["system"], row["user"] = reconstruct_variant(row, condition)
                row["estimated_input_tokens"] = CharTokenCounter().count(row["system"] + row["user"])
                rows.append(row)
    validate_robustness_requests(rows)
    proofs = {}
    for key, tokenizer in tokenizers.items():
        lengths = [len(_token_ids(tokenizer.apply_chat_template(
            [{"role": "system", "content": r["system"]}, {"role": "user", "content": r["user"]}],
            tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False))) for r in rows]
        if any(n + RESERVED_OUTPUT_TOKENS > MAX_MODEL_LEN for n in lengths):
            raise ValueError("robustness request exceeds actual model token capacity")
        proofs[key] = {"path": models[key]["path"], "request_count": len(rows),
            "max_prompt_tokens": max(lengths), "overflow_count": 0,
            "tokenizer_local_files_only": True, "apply_chat_template": True,
            "enable_thinking": False, "reserved_output_tokens": RESERVED_OUTPUT_TOKENS}
    review = {"reviewer": "codex-root-ai", "review_origin": "AI_REVIEWED", "human_verified": False,
              "cases_checked": 64, "families_checked": 16, "disagreements": 0,
              "before_resolver_output": True, "reviewed_case_file_sha256": REVIEWED_CASE_FILE_SHA256}
    provenance = {"source": "sealed_semantic_safety_and_fresh_authored_families", "code_revision": code_revision,
        "prior_envelope_sha256": _sha(prior), "prior_code_revision": prior["provenance"]["code_revision"],
        "case_file_sha256": case_file_sha, "authored_gold_sha256": gold_sha,
        "gold_review": review, "fresh_snapshot_ids": snapshots}
    protocol = {"kind": "ktrf_extended_v1", "phase": "FINAL_FROZEN", "experiment": EXPERIMENT,
        "conditions": list(CONDITIONS), "repeat_count": 1, "gold_origin": "AI_AUTHORED",
        "human_verified": False, "independent_validation": False,
        "selection_before_generation_outputs": True, "max_model_len": MAX_MODEL_LEN,
        "reserved_output_tokens": RESERVED_OUTPUT_TOKENS, "temperature": 0,
        "seed_for_generation": 0, "enable_thinking": False,
        "comparisons": [["pack_first_baseline", "pack_last_baseline"],
                        ["pack_first_baseline", "pack_first_semantic_check"],
                        ["pack_last_baseline", "pack_last_semantic_check"],
                        ["pack_first_semantic_check", "pack_last_semantic_check"]],
        "evaluation_splits": {"exposed_diagnostic": 96, "fresh_family": 64},
        "execution_validation": "Complete parsed response passed unchanged to validate_llm_grounding(purpose='execution').",
        "limitations": [*artifact["limitations"],
            "Previously evaluated 96 cases are exposed diagnostics and reported separately from 64 fresh-family cases.",
            "All 160 cases are retained regardless of resolver or previous model outcomes; no selection by failures.",
            "Pack placement moves only the same XML block before or after the identical user task; the production system policy is unchanged.",
            "Semantic-check wording is identical for every case and condition that enables it; no gold or case rationale reaches the prompt.",
            "The exposed split preserves its previous sealed packs; fresh packs use the current frozen revision.",
            "No production resolver or execution-guard policy changes are evaluated.",
            "The 6000-token evaluation pack allowance differs from the default 800-token product allowance."]}
    envelope = {"protocol": protocol, "provenance": provenance, "requests": rows}
    unique = old + fresh
    experiment = {"file": EXPERIMENT + ".json", "request_count": len(rows), "question_count": len(unique),
        "parent_articles": len(unique), "family_count": 40,
        "strata": dict(Counter(r["stratum"] for r in unique)),
        "semantic_labels": dict(Counter(r["gold"]["label"] for r in unique)),
        "positive_questions": sum(r["positive_gold"] for r in unique),
        "pack_injected_questions": sum(r["injected"] for r in unique),
        "evaluation_splits": {"exposed_diagnostic": {"question_count": 96, "family_count": 24},
                              "fresh_family": {"question_count": 64, "family_count": 16}},
        "envelope_sha256": _sha(envelope),
        "requests_sha256": hashlib.sha256(b"".join(canonical(r) for r in rows)).hexdigest(),
        "models": proofs, "case_file_sha256": case_file_sha, "authored_gold_sha256": gold_sha,
        "prior_envelope_sha256": _sha(prior), "gold_review": review}
    return envelope, experiment
