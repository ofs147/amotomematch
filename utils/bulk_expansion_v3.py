"""AOMatch v3.2 bulk annotation QA and controlled final-write helpers.

Drafts live outside the production CSV.  This module is deliberately independent
from matching/ranking code: it validates annotation data and produces a compact
exception queue for a reviewer.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

from utils.data_utils import parse_tags
from utils.data_validation import validate_rows
from utils.schema import CSV_COLUMNS, DICTIONARY_TAG_FIELDS, NUMERIC_FEATURES, TAG_DICTIONARY

SEVERITY_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
ROMANCE_RISK_FIELDS = {
    "initiative", "possessiveness", "protectiveness", "dependence",
    "jealousy", "push_pull", "devotion", "control",
}
SETTING_RISK_FIELDS = {"danger_level", "mystery_level", "gap_moe"}
SPOILER_MARKERS = {
    "spoiler_sensitive", "hidden_identity", "future_identity", "plot_truth",
    "隐藏身份", "未来身份", "剧情真相", "真凶",
}
VALID_TIERS = {"A", "B", "C"}


def load_json_integrity(path: Path | str, *, required_fields: Iterable[str] = ()) -> Any:
    """Load a UTF-8 JSON artifact strictly and reject incomplete payloads.

    ``utf-8-sig`` accepts both canonical UTF-8 and an optional BOM while still
    decoding strictly.  Parse/encoding/schema failures deliberately propagate;
    Final Write must never guess or silently fall back.
    """
    artifact = Path(path)
    try:
        with artifact.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON integrity validation failed: {artifact}: {exc}") from exc
    if required_fields:
        if not isinstance(payload, Mapping):
            raise ValueError(f"JSON integrity validation failed: {artifact} must contain an object")
        missing = [field for field in required_fields if field not in payload]
        if missing:
            raise ValueError(f"JSON integrity validation failed: {artifact} missing {missing}")
    return payload


@dataclass(frozen=True)
class ExceptionItem:
    character_id: str
    character: str
    game: str
    field: str
    candidate_value: str
    confidence: str
    exception_type: str
    severity: str
    reason: str
    suggested_action: str


def load_bulk_draft(path: Path | str) -> dict[str, Any]:
    payload = load_json_integrity(path, required_fields=("batch_id", "characters"))
    if not isinstance(payload.get("characters"), list):
        raise ValueError("Bulk draft 必须包含 characters list")
    # Compact bulk manifests may store the fixed 20-dimensional vector as an
    # ordered list. Expand it immediately so the rest of QA remains unchanged.
    for item in payload["characters"]:
        if "numeric_values" in item:
            values = item.pop("numeric_values")
            if len(values) != len(NUMERIC_FEATURES):
                raise ValueError(
                    f"{item.get('character_id', '?')} numeric_values 必须恰好有20项"
                )
            item["numeric"] = dict(zip(NUMERIC_FEATURES, values))
    return payload


def load_bulk_final_write_inputs(*, approved_path: Path | str, draft_path: Path | str,
                                 qa_path: Path | str) -> tuple[set[str], dict[str, Any], dict[str, Any]]:
    """Integrity-gated loader for the file-based Bulk Final Write workflow."""
    approved_payload = load_json_integrity(approved_path)
    if isinstance(approved_payload, list):
        approved_ids = {str(value) for value in approved_payload}
    elif isinstance(approved_payload, Mapping) and isinstance(approved_payload.get("approved_ids"), list):
        approved_ids = {str(value) for value in approved_payload["approved_ids"]}
    else:
        raise ValueError("Approved IDs JSON must be a list or contain approved_ids list")
    draft = load_json_integrity(draft_path, required_fields=("batch_id", "characters"))
    qa = load_json_integrity(qa_path, required_fields=("batch_id", "statuses", "exceptions"))
    if draft["batch_id"] != qa["batch_id"]:
        raise ValueError("JSON integrity validation failed: draft/QA batch_id mismatch")
    draft_ids = {str(item.get("character_id", "")) for item in draft["characters"]}
    if not approved_ids <= draft_ids:
        raise ValueError("JSON integrity validation failed: approved IDs are not all present in draft")
    return approved_ids, draft, qa


def materialize_character(item: Mapping[str, Any]) -> dict[str, str]:
    """Turn the compact draft representation into one production-shaped row."""
    row = {column: "" for column in CSV_COLUMNS}
    for field in CSV_COLUMNS:
        if field in item:
            row[field] = str(item[field])
    for field, value in item.get("numeric", {}).items():
        row[field] = str(value)
    for field, value in item.get("tags", {}).items():
        row[field] = ";".join(value) if isinstance(value, list) else str(value)
    return row


def field_confidence(item: Mapping[str, Any], field: str) -> str:
    return str(item.get("confidence_overrides", {}).get(field, item.get("confidence_default", "NA"))).upper()


def field_evidence(item: Mapping[str, Any], field: str) -> str:
    overrides = item.get("evidence_overrides", {})
    if field in overrides:
        return str(overrides[field]).strip()
    if field in NUMERIC_FEATURES:
        if field in ROMANCE_RISK_FIELDS:
            return str(item.get("evidence", {}).get("ROMANCE", "")).strip()
        if field in SETTING_RISK_FIELDS:
            return str(item.get("evidence", {}).get("ARCHETYPE", "")).strip()
        layer = "LOOK" if field in {"visual_maturity", "physical_presence"} else "PERSONALITY"
        return str(item.get("evidence", {}).get(layer, "")).strip()
    return str(item.get("evidence", {}).get("TAGS", "")).strip()


def _exception(item: Mapping[str, Any], field: str, kind: str, severity: str,
               reason: str, action: str, value: object | None = None) -> ExceptionItem:
    row = materialize_character(item)
    return ExceptionItem(
        character_id=row["character_id"], character=row["character_name"], game=row["game"],
        field=field, candidate_value=str(row.get(field, "") if value is None else value),
        confidence=field_confidence(item, field), exception_type=kind, severity=severity,
        reason=reason, suggested_action=action,
    )


def _normalized_distance(left: Mapping[str, str], right: Mapping[str, str]) -> float:
    values = []
    for field in NUMERIC_FEATURES:
        try:
            values.append(((float(left[field]) - float(right[field])) / 4.0) ** 2)
        except (TypeError, ValueError):
            continue
    return math.sqrt(sum(values) / len(values)) if values else math.inf


def nearest_reference(item: Mapping[str, Any], gold_rows: Sequence[Mapping[str, str]]) -> tuple[str, float]:
    row = materialize_character(item)
    if not gold_rows:
        return "", math.inf
    nearest = min(gold_rows, key=lambda ref: _normalized_distance(row, ref))
    return str(nearest.get("character_id", "")), _normalized_distance(row, nearest)


def qa_character(item: Mapping[str, Any], existing_rows: Sequence[Mapping[str, str]],
                 gold_rows: Sequence[Mapping[str, str]]) -> list[ExceptionItem]:
    exceptions: list[ExceptionItem] = []
    tier = str(item.get("annotation_tier", ""))
    if tier not in VALID_TIERS:
        exceptions.append(_exception(item, "annotation_tier", "SCHEMA_CONFLICT", "HIGH",
                                     "annotation_tier 不是 A/B/C。", "修正 Tier 后重跑 QA。", tier))

    # Gold is never silently created from an AI draft.
    if tier == "A" and not item.get("human_review_confirmed", False):
        exceptions.append(_exception(item, "annotation_status", "GOLD_REVIEW_REQUIRED", "HIGH",
                                     "Tier A 必须由熟悉路线的 Reviewer 明确确认。",
                                     "完成人工确认后标记 human_reviewed_gold。", "draft"))

    for field in NUMERIC_FEATURES:
        confidence = field_confidence(item, field)
        evidence = field_evidence(item, field)
        value = item.get("numeric", {}).get(field, "")
        # Tier C is retrieval-only: confidence/extreme review is intentionally
        # skipped unless a severe conflict is supplied through risk_flags.
        if tier != "C" and confidence in {"C", "NA"}:
            exceptions.append(_exception(item, field, "LOW_CONFIDENCE", "MEDIUM",
                                         "该字段为 Confidence C/NA。", "快速核对路线证据或保留 Candidate Only。", value))
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if tier != "C" and numeric in {1.0, 1.5, 4.5, 5.0} and (
            confidence in {"C", "NA"} or len(evidence) < 12
        ):
            exceptions.append(_exception(item, field, "UNSUPPORTED_EXTREME", "MEDIUM",
                                         "极端值证据不足或置信度过低。", "确认、降至相邻值或补充证据。", value))

    row = materialize_character(item)
    for field in DICTIONARY_TAG_FIELDS:
        for tag in parse_tags(row[field]):
            if tag not in TAG_DICTIONARY[field]:
                exceptions.append(_exception(item, field, "NEW_TAG", "MEDIUM",
                                             f"标签“{tag}”不在固定词典。", "复用现有 Tag 或提交 Tag Governance Review。", tag))

    risk_flags = item.get("risk_flags", [])
    for flag in risk_flags:
        severity = str(flag.get("severity", "MEDIUM")).upper()
        exceptions.append(_exception(item, str(flag.get("field", "character")),
                                     str(flag.get("type", "SOURCE_CONFLICT")), severity,
                                     str(flag.get("reason", "需要人工确认。")),
                                     str(flag.get("action", "核对证据后决定。")), flag.get("value")))

    visible_text = " ".join(str(row[field]).lower() for field in CSV_COLUMNS)
    if any(marker in visible_text for marker in SPOILER_MARKERS):
        exceptions.append(_exception(item, "user_visible_fields", "SPOILER_RISK", "HIGH",
                                     "用户可见字段命中 spoiler-sensitive marker。",
                                     "移除或替换为安全表述后重跑。", "redacted"))

    aliases = {a.strip().casefold() for a in item.get("aliases", []) if str(a).strip()}
    aliases.add(row["character_name"].strip().casefold())
    for existing in existing_rows:
        existing_names = {str(existing.get("character_name", "")).strip().casefold(),
                          str(existing.get("character_id", "")).strip().casefold()}
        if row["character_id"] == existing.get("character_id") or aliases & existing_names:
            exceptions.append(_exception(item, "character_id/aliases", "DUPLICATE_ALIAS", "HIGH",
                                         "与正式库 character_id 或 alias 冲突。", "阻止写入并合并/更正身份。",
                                         row["character_id"]))
            break

    reference_id, distance = nearest_reference(item, gold_rows)
    if distance > 0.62 and not str(item.get("reference_difference_note", "")).strip():
        exceptions.append(_exception(item, "nearest_gold_reference", "REFERENCE_OUTLIER", "MEDIUM",
                                     f"距最近 Gold {reference_id or 'N/A'} 的归一化距离为 {distance:.2f}，缺少解释。",
                                     "补充差异说明或复核整条向量。", f"{reference_id}:{distance:.2f}"))
    return exceptions


def _dedupe_exceptions(items: Iterable[ExceptionItem]) -> list[ExceptionItem]:
    unique = {(x.character_id, x.field, x.exception_type, x.reason): x for x in items}
    return sorted(unique.values(), key=lambda x: (-SEVERITY_ORDER[x.severity], x.character_id, x.field))


def run_bulk_qa(draft: Mapping[str, Any], existing_rows: Sequence[Mapping[str, str]],
                gold_rows: Sequence[Mapping[str, str]] | None = None) -> dict[str, Any]:
    started = perf_counter()
    characters = draft["characters"]
    materialized = [materialize_character(item) for item in characters]
    structural = validate_rows(CSV_COLUMNS, materialized)
    exceptions: list[ExceptionItem] = []
    for item in characters:
        exceptions.extend(qa_character(item, existing_rows, gold_rows or existing_rows))
    # Structural errors are blocking and stay batch-level when the validator cannot map safely.
    for error in structural:
        exceptions.append(ExceptionItem("BATCH", "整批", "", "schema", "", "NA",
                                        "FORMAT_VALIDATION", "HIGH", error, "修复 Draft 后重跑 QA。"))
    exceptions = _dedupe_exceptions(exceptions)
    by_character: dict[str, list[ExceptionItem]] = {}
    for exception in exceptions:
        by_character.setdefault(exception.character_id, []).append(exception)

    statuses: dict[str, str] = {}
    for item in characters:
        cid = str(item["character_id"])
        found = by_character.get(cid, [])
        if structural or any(x.exception_type in {"DUPLICATE_ALIAS", "SPOILER_RISK", "FORMAT_VALIDATION"} and x.severity == "HIGH" for x in found):
            statuses[cid] = "BLOCKED"
        elif any(x.severity in {"MEDIUM", "HIGH"} for x in found):
            statuses[cid] = "REVIEW_REQUIRED"
        else:
            statuses[cid] = "AUTO_PASS"

    tier_counts = Counter(str(item.get("annotation_tier", "")) for item in characters)
    status_counts = Counter(statuses.values())
    return {
        "batch_id": draft.get("batch_id", ""), "total": len(characters),
        "tier_counts": dict(tier_counts), "status_counts": dict(status_counts),
        "statuses": statuses, "exceptions": [asdict(x) for x in exceptions],
        "elapsed_seconds": perf_counter() - started,
    }


def build_metadata_rows(draft: Mapping[str, Any], qa: Mapping[str, Any]) -> list[dict[str, str]]:
    exception_counts = Counter(x["character_id"] for x in qa["exceptions"])
    output = []
    for item in draft["characters"]:
        cid, tier = str(item["character_id"]), str(item["annotation_tier"])
        qa_status = qa["statuses"][cid]
        if qa_status == "BLOCKED":
            annotation_status = "blocked"
        elif tier == "A":
            annotation_status = "human_reviewed_gold" if item.get("human_review_confirmed") else "blocked"
        elif tier == "B":
            annotation_status = "reviewed_lite" if qa_status == "AUTO_PASS" else "blocked"
        else:
            annotation_status = "candidate_only" if qa_status != "BLOCKED" else "blocked"
        confidences = Counter(field_confidence(item, field) for field in NUMERIC_FEATURES)
        summary = ";".join(f"{key}:{confidences.get(key, 0)}" for key in ("A", "B", "C", "NA"))
        output.append({
            "character_id": cid, "annotation_status": annotation_status,
            "annotation_source": str(draft.get("batch_id", "bulk_draft")), "merge_note": "bulk_final_write",
            "annotation_tier": tier, "review_mode": "gold_manual" if tier == "A" else ("exception_only" if tier == "B" else "automated_qa"),
            "confidence_summary": summary, "exception_count": str(exception_counts[cid]),
        })
    return output


def coverage_analysis(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    numeric = {}
    for field in NUMERIC_FEATURES:
        values = [float(row[field]) for row in rows if str(row.get(field, "")).strip().upper() not in {"", "NA"}]
        numeric[field] = {
            "count": len(values), "min": min(values) if values else None, "max": max(values) if values else None,
            "mean": sum(values) / len(values) if values else None,
            "sparse_bins": [name for name, low, high in (("1-1.5", 1, 1.5), ("2-2.5", 2, 2.5), ("3", 3, 3), ("3.5-4", 3.5, 4), ("4.5-5", 4.5, 5))
                            if sum(low <= value <= high for value in values) < 3],
        }
    return {
        "numeric": numeric,
        "title_coverage": dict(Counter(row.get("game", "") for row in rows)),
        "franchise_coverage": dict(Counter(row.get("series", "") for row in rows)),
        "archetype_coverage": dict(Counter(tag for row in rows for tag in parse_tags(row.get("archetype_tags", "")))),
        "romance_coverage": dict(Counter(tag for row in rows for tag in parse_tags(row.get("romance_tags", "")))),
    }


def bulk_final_write(*, approved_ids: set[str], draft: Mapping[str, Any], qa: Mapping[str, Any],
                     character_path: Path, metadata_path: Path) -> int:
    """Append an approved set atomically. Caller must explicitly supply approved IDs."""
    blocked = {cid for cid, status in qa["statuses"].items() if status == "BLOCKED"}
    if approved_ids & blocked:
        raise ValueError(f"BLOCKED 角色不得写入：{sorted(approved_ids & blocked)}")
    selected = [item for item in draft["characters"] if item["character_id"] in approved_ids]
    if not selected:
        return 0
    with character_path.open(encoding="utf-8-sig", newline="") as handle:
        existing = list(csv.DictReader(handle))
    combined = existing + [materialize_character(item) for item in selected]
    errors = validate_rows(CSV_COLUMNS, combined)
    if errors:
        raise ValueError("Bulk Final Write validation failed: " + " | ".join(errors))
    # Imports are local to keep the read/QA path side-effect free.
    import tempfile
    metadata_fields = ("character_id", "annotation_status", "annotation_source", "merge_note",
                       "annotation_tier", "review_mode", "confidence_summary", "exception_count")
    with metadata_path.open(encoding="utf-8-sig", newline="") as handle:
        old_metadata = list(csv.DictReader(handle))
    new_metadata = [row for row in build_metadata_rows(draft, qa) if row["character_id"] in approved_ids]
    for path, fields, rows in ((character_path, CSV_COLUMNS, combined), (metadata_path, metadata_fields, old_metadata + new_metadata)):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", delete=False, dir=path.parent) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader(); writer.writerows(rows)
            temp_path = Path(handle.name)
        temp_path.replace(path)
    return len(selected)
