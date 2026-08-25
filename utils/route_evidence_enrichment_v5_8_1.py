"""Evidence-driven partial XP annotation for the fixed v5.7 selection.

Missing evidence is data, not an exception.  Numeric priors from v5.8 remain
diagnostic-only and can never be materialized as candidate values here.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from utils.roster_xp_pipeline_v5_3 import write_json_utf8
from utils.schema import NUMERIC_FEATURES, NUMERIC_FEATURES_BY_LAYER

BATCH_ID = "route_evidence_v5_8_1_batch_01"
EVIDENCE_FILENAME = "route_evidence_v5_8_1.csv"
VALID_STATES = {"OBSERVED", "INFERRED_WITH_EVIDENCE", "UNKNOWN"}
VALID_CONFIDENCE = {"A", "B", "C", "NA"}
VALID_SOURCE_TIERS = {"1", "2", "3"}

# Centralized product thresholds.
REVIEWED_LITE_MIN_COVERAGE = 0.60
REVIEWED_LITE_MIN_ROMANCE_FIELDS = 4
CANDIDATE_ONLY_MIN_COVERAGE = 0.40

EVIDENCE_COLUMNS = (
    "character_id", "field", "value", "numeric_state", "confidence",
    "source_tier", "source_url", "source_note", "internal_evidence",
    "user_visible_evidence", "spoiler_sensitive",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def ensure_evidence_manifest(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVIDENCE_COLUMNS)
        writer.writeheader()


def _parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def validate_evidence_row(row: Mapping[str, str], selected_ids: set[str]) -> list[str]:
    errors = []
    cid, field = row.get("character_id", ""), row.get("field", "")
    state, confidence = row.get("numeric_state", ""), row.get("confidence", "")
    if cid not in selected_ids:
        errors.append("character_id is not in fixed selection")
    if field not in NUMERIC_FEATURES:
        errors.append("unknown numeric field")
    if state not in VALID_STATES:
        errors.append("invalid numeric_state")
    if confidence not in VALID_CONFIDENCE:
        errors.append("invalid confidence")
    if state == "UNKNOWN":
        if str(row.get("value", "")).strip().upper() not in {"", "NA"}:
            errors.append("UNKNOWN must not contain a numeric value")
    else:
        try:
            value = float(row.get("value", ""))
            if not 1 <= value <= 5 or not (value * 2).is_integer():
                errors.append("numeric must be 1..5 in 0.5 steps")
        except ValueError:
            errors.append("resolved evidence requires a numeric value")
        if confidence not in {"A", "B", "C"}:
            errors.append("resolved evidence requires A/B/C confidence")
        if row.get("source_tier", "") not in VALID_SOURCE_TIERS:
            errors.append("resolved evidence requires source tier 1/2/3")
        if not str(row.get("source_url", "")).startswith(("https://", "http://")):
            errors.append("resolved evidence requires a direct source URL")
        if not str(row.get("internal_evidence", "")).strip():
            errors.append("resolved evidence requires internal_evidence")
    return errors


def _classify(numeric_coverage: float, romance_ab: int, has_high: bool,
              gold_candidate: bool) -> str:
    if has_high:
        return "BLOCKED"
    if gold_candidate:
        return "GOLD_REVIEW_CANDIDATE"
    if numeric_coverage >= REVIEWED_LITE_MIN_COVERAGE and romance_ab >= REVIEWED_LITE_MIN_ROMANCE_FIELDS:
        return "AUTO_PASS_REVIEWED_LITE"
    if numeric_coverage >= CANDIDATE_ONLY_MIN_COVERAGE:
        return "CANDIDATE_ONLY"
    return "INSUFFICIENT_EVIDENCE"


def enrich(existing_draft: Mapping[str, Any], evidence_rows: Iterable[Mapping[str, str]]) -> tuple[dict[str, Any], dict[str, Any]]:
    selected_ids = {item["character_id"] for item in existing_draft["characters"]}
    evidence_by_key: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
    exceptions: list[dict[str, str]] = []
    for row in evidence_rows:
        errors = validate_evidence_row(row, selected_ids)
        key = (row.get("character_id", ""), row.get("field", ""))
        if errors:
            exceptions.append({
                "character_id": key[0], "field": key[1], "severity": "HIGH",
                "exception_type": "EVIDENCE_SCHEMA_CONFLICT",
                "reason": "; ".join(errors), "suggested_action": "修复证据记录后重跑。",
            })
        else:
            evidence_by_key[key].append(row)

    # Multiple independent sources are allowed. They become a human exception
    # only when they actually disagree on the resolved numeric value/state.
    for (cid, field), rows in evidence_by_key.items():
        resolved = {(row["numeric_state"], str(row.get("value", "")).strip()) for row in rows}
        if len(resolved) > 1:
            exceptions.append({
                "character_id": cid, "field": field, "severity": "MEDIUM",
                "exception_type": "CONTRADICTORY_ROUTE_EVIDENCE",
                "reason": "可靠来源对该字段给出不一致的状态或数值。",
                "suggested_action": "人工核对字段定义与路线语境；解决前保持 NA。",
            })

    high_exception_ids = {row["character_id"] for row in exceptions if row["severity"] == "HIGH"}
    medium_exception_ids = {row["character_id"] for row in exceptions if row["severity"] == "MEDIUM"}
    characters = []
    statuses = {}
    gold_queue = []
    for old in existing_draft["characters"]:
        cid = old["character_id"]
        numeric: dict[str, object] = {}
        states: dict[str, str] = {}
        confidence: dict[str, str] = {}
        internal: dict[str, str] = {}
        visible: dict[str, str] = {}
        sources: dict[str, list[str]] = {}
        for field in NUMERIC_FEATURES:
            field_evidence = evidence_by_key.get((cid, field), [])
            resolved_pairs = {(row["numeric_state"], str(row.get("value", "")).strip()) for row in field_evidence}
            evidence = field_evidence[0] if len(resolved_pairs) == 1 and field_evidence else None
            if evidence and evidence["numeric_state"] != "UNKNOWN":
                numeric[field] = float(evidence["value"])
                states[field] = evidence["numeric_state"]
                confidence[field] = evidence["confidence"]
                internal[field] = " | ".join(dict.fromkeys(row["internal_evidence"] for row in field_evidence))
                safe_notes = [row.get("user_visible_evidence", "") for row in field_evidence if not _parse_bool(row.get("spoiler_sensitive"))]
                visible[field] = " | ".join(dict.fromkeys(note for note in safe_notes if note))
                sources[field] = list(dict.fromkeys(row["source_url"] for row in field_evidence))
            else:
                numeric[field] = "NA"
                states[field] = "UNKNOWN"
                confidence[field] = "NA"
                internal[field] = ""
                visible[field] = ""
                sources[field] = []

        resolved = sum(value != "NA" for value in numeric.values())
        ab_resolved = sum(numeric[f] != "NA" and confidence[f] in {"A", "B"} for f in NUMERIC_FEATURES)
        romance_ab = sum(numeric[f] != "NA" and confidence[f] in {"A", "B"} for f in NUMERIC_FEATURES_BY_LAYER["ROMANCE"])
        coverage = resolved / len(NUMERIC_FEATURES)
        reliable_coverage = ab_resolved / len(NUMERIC_FEATURES)
        if cid in high_exception_ids:
            status = "BLOCKED"
        elif cid in medium_exception_ids:
            status = "REVIEW_REQUIRED"
        else:
            status = _classify(reliable_coverage, romance_ab, False, old["annotation_tier"] == "A")
        statuses[cid] = status
        if status == "GOLD_REVIEW_CANDIDATE":
            gold_queue.append({
                "character_id": cid, "character": old["character_name"], "game": old["game"],
                "resolved_fields": resolved, "numeric_coverage": coverage,
                "review_fields": [f for f in NUMERIC_FEATURES_BY_LAYER["ROMANCE"] if numeric[f] != "NA"][:5],
                "reason": "Gold 需要 Reviewer 熟悉完整路线并人工确认关键 Numeric；否则降为 Lite/Candidate Only。",
            })
        characters.append({
            **{key: old[key] for key in ("character_id", "character_name", "game", "series", "route_type", "annotation_tier", "target_status", "source_readiness", "roster_game_id")},
            "numeric": numeric, "numeric_state": states, "confidence": confidence,
            "internal_evidence": internal, "user_visible_evidence": visible,
            "evidence_sources": sources, "numeric_coverage": round(coverage, 4),
            "reliable_numeric_coverage": round(reliable_coverage, 4),
            "resolved_count": resolved, "ab_resolved_count": ab_resolved,
            "romance_ab_resolved_count": romance_ab,
            "diagnostic_prior": old["numeric"], "diagnostic_prior_scope": old["prior_scope"],
            "prior_eligible_for_final_write": False,
            "spoiler_safe": True,
        })

    coverage_bands = Counter(
        ">=80%" if item["numeric_coverage"] >= .8 else
        "60-79%" if item["numeric_coverage"] >= .6 else
        "40-59%" if item["numeric_coverage"] >= .4 else "<40%"
        for item in characters
    )
    field_report = {}
    for field in NUMERIC_FEATURES:
        field_report[field] = {
            "resolved_count": sum(item["numeric"][field] != "NA" for item in characters),
            "na_count": sum(item["numeric"][field] == "NA" for item in characters),
            "confidence": dict(Counter(item["confidence"][field] for item in characters)),
            "state": dict(Counter(item["numeric_state"][field] for item in characters)),
        }
    hardest_priority = (
        "push_pull", "dependence", "jealousy", "control", "possessiveness",
        "initiative", "devotion", "protectiveness", "emotional_stability",
        "emotional_expression", "cunning", "personality_maturity", "gap_moe",
        "mystery_level", "danger_level", "humor", "warmth", "extroversion",
        "physical_presence", "visual_maturity",
    )
    hardest_fields = sorted(
        NUMERIC_FEATURES,
        key=lambda field: (field_report[field]["resolved_count"], hardest_priority.index(field)),
    )[:3]
    status_counts = Counter(statuses.values())
    qa = {
        "batch_id": BATCH_ID, "source_batch_id": existing_draft["batch_id"],
        "thresholds": {"reviewed_lite_min_coverage": REVIEWED_LITE_MIN_COVERAGE, "reviewed_lite_min_romance_ab": REVIEWED_LITE_MIN_ROMANCE_FIELDS, "candidate_only_min_coverage": CANDIDATE_ONLY_MIN_COVERAGE},
        "status_counts": dict(status_counts), "statuses": statuses,
        "coverage_bands": {band: coverage_bands.get(band, 0) for band in (">=80%", "60-79%", "40-59%", "<40%")},
        "average_numeric_coverage": round(sum(item["numeric_coverage"] for item in characters) / len(characters), 4),
        "average_reliable_numeric_coverage": round(sum(item["reliable_numeric_coverage"] for item in characters) / len(characters), 4),
        "average_romance_coverage": round(sum(item["romance_ab_resolved_count"] / 8 for item in characters) / len(characters), 4),
        "field_coverage": field_report, "exceptions": exceptions,
        "gold_review_queue": gold_queue, "final_write_allowed": False,
        "median_prior_contamination_count": sum(item["numeric"][field] != "NA" and not item["evidence_sources"][field] for item in characters for field in NUMERIC_FEATURES),
    }
    qa["summary"] = {
        "reviewed_lite_auto_pass": status_counts.get("AUTO_PASS_REVIEWED_LITE", 0),
        "candidate_only": status_counts.get("CANDIDATE_ONLY", 0),
        "insufficient_evidence": status_counts.get("INSUFFICIENT_EVIDENCE", 0),
        "gold_review_candidate": status_counts.get("GOLD_REVIEW_CANDIDATE", 0),
        "review_required": status_counts.get("REVIEW_REQUIRED", 0),
        "blocked": status_counts.get("BLOCKED", 0),
        "true_human_review": sum(status_counts.get(key, 0) for key in ("GOLD_REVIEW_CANDIDATE", "REVIEW_REQUIRED", "BLOCKED")),
        "hardest_evidence_fields": hardest_fields,
        "average_numeric_coverage": qa["average_numeric_coverage"],
        "average_reliable_numeric_coverage": qa["average_reliable_numeric_coverage"],
        "average_romance_coverage": qa["average_romance_coverage"],
        "median_prior_contamination_eliminated": qa["median_prior_contamination_count"] == 0,
        "scalable_to_500_plus": qa["median_prior_contamination_count"] == 0 and qa["average_reliable_numeric_coverage"] >= CANDIDATE_ONLY_MIN_COVERAGE,
        "scalability_note": "代码管线可扩展；达到至少 40% 平均可靠覆盖后，才能判定真实 Evidence Enrichment 适合扩至 500+。",
    }
    draft = {"batch_id": BATCH_ID, "source_batch_id": existing_draft["batch_id"], "selected_size": len(characters), "partial_annotation": True, "characters": characters}
    return draft, qa


def run_pipeline(data_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source = data_dir / "xp_annotation" / "priority_xp_v5_8_batch_01_draft.json"
    with source.open(encoding="utf-8") as handle:
        old = json.load(handle)
    evidence_path = data_dir / "xp_annotation" / EVIDENCE_FILENAME
    ensure_evidence_manifest(evidence_path)
    evidence = _read_csv(evidence_path)
    draft, qa = enrich(old, evidence)
    output = data_dir / "xp_annotation"
    write_json_utf8(output / "route_evidence_v5_8_1_batch_01_draft.json", draft)
    write_json_utf8(output / "route_evidence_v5_8_1_batch_01_qa.json", qa)
    return draft, qa


if __name__ == "__main__":
    root = Path.cwd() if (Path.cwd() / "data").is_dir() else Path(__file__).resolve().parents[1]
    draft, qa = run_pipeline(root / "data")
    print(json.dumps({"selected": draft["selected_size"], **qa["status_counts"], "average_numeric_coverage": qa["average_numeric_coverage"], "average_romance_coverage": qa["average_romance_coverage"]}, ensure_ascii=False, indent=2))
