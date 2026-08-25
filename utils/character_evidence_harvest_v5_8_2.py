"""Read-only metrics and QA for the v5.8.2 character evidence pilot."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from utils.schema import NUMERIC_FEATURES, NUMERIC_FEATURES_BY_LAYER

EVIDENCE_FIELDS = {
    "evidence_id", "character_id", "game_id", "character_name", "source_url",
    "source_title", "source_type", "source_tier", "field_candidate",
    "evidence_text_internal", "evidence_strength", "spoiler_sensitive",
    "supports_direction", "consistency", "notes",
}
VALID_STRENGTH = {"DIRECT", "STRONG", "MODERATE", "WEAK"}
VALID_DIRECTION = {"LOW", "MID", "HIGH", "UNKNOWN"}
VALID_CONSISTENCY = {"CONSISTENT", "PARTIAL_CONFLICT", "CONFLICT"}
ROMANCE = set(NUMERIC_FEATURES_BY_LAYER["ROMANCE"])


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def audit(selection: list[dict[str, str]], evidence: list[dict[str, str]],
          resolution: list[dict[str, str]]) -> dict[str, Any]:
    errors: list[str] = []
    selected = {row["character_id"]: row for row in selection}
    evidence_by_id: dict[str, dict[str, str]] = {}
    for row in evidence:
        eid = row.get("evidence_id", "")
        if eid in evidence_by_id:
            errors.append(f"duplicate evidence_id: {eid}")
        if set(row) != EVIDENCE_FIELDS:
            errors.append(f"invalid evidence columns: {eid}")
        if row.get("character_id") not in selected:
            errors.append(f"evidence outside pilot: {eid}")
        if row.get("field_candidate") not in NUMERIC_FEATURES:
            errors.append(f"invalid field: {eid}")
        if row.get("evidence_strength") not in VALID_STRENGTH:
            errors.append(f"invalid strength: {eid}")
        if row.get("supports_direction") not in VALID_DIRECTION:
            errors.append(f"invalid direction: {eid}")
        if row.get("consistency") not in VALID_CONSISTENCY:
            errors.append(f"invalid consistency: {eid}")
        if not row.get("source_url", "").startswith(("https://", "http://")):
            errors.append(f"invalid source URL: {eid}")
        evidence_by_id[eid] = row

    resolved_by_character: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in resolution:
        cid, field = row.get("character_id", ""), row.get("field", "")
        if cid not in selected or field not in NUMERIC_FEATURES:
            errors.append(f"invalid resolution target: {cid}/{field}")
            continue
        try:
            value = float(row["value"])
            if not 1 <= value <= 5 or not (value * 2).is_integer():
                errors.append(f"invalid numeric value: {cid}/{field}")
        except ValueError:
            errors.append(f"invalid numeric value: {cid}/{field}")
        if row.get("confidence") not in {"A", "B", "C"}:
            errors.append(f"invalid confidence: {cid}/{field}")
        ids = [item for item in row.get("evidence_ids", "").split("|") if item]
        if not ids or any(item not in evidence_by_id for item in ids):
            errors.append(f"missing evidence link: {cid}/{field}")
        if any(evidence_by_id[item]["character_id"] != cid or evidence_by_id[item]["field_candidate"] != field for item in ids if item in evidence_by_id):
            errors.append(f"cross-character/field evidence link: {cid}/{field}")
        resolved_by_character[cid].append(row)

    per_character = {}
    reviewed_lite = candidate_only = insufficient = 0
    for cid in selected:
        units = [row for row in evidence if row["character_id"] == cid]
        rows = resolved_by_character[cid]
        ab = [row for row in rows if row["confidence"] in {"A", "B"}]
        romance_ab = [row for row in ab if row["field"] in ROMANCE]
        ab_coverage, romance_coverage = len(ab) / 20, len(romance_ab) / 8
        if ab_coverage >= .6 and len(romance_ab) >= 4:
            status = "REVIEWED_LITE"
            reviewed_lite += 1
        elif ab_coverage >= .4:
            status = "CANDIDATE_ONLY"
            candidate_only += 1
        else:
            status = "INSUFFICIENT_EVIDENCE"
            insufficient += 1
        per_character[cid] = {
            "evidence_units": len(units),
            "unique_sources": len({row["source_url"] for row in units}),
            "ab_numeric_coverage": round(ab_coverage, 4),
            "resolved_numeric_coverage": round(len(rows) / 20, 4),
            "romance_ab_coverage": round(romance_coverage, 4),
            "status": status,
        }

    field_ab = Counter(row["field"] for row in resolution if row["confidence"] in {"A", "B"})
    source_yield = Counter(row["source_type"] for row in evidence)
    n = len(selection)
    average_ab = sum(row["ab_numeric_coverage"] for row in per_character.values()) / n
    average_romance = sum(row["romance_ab_coverage"] for row in per_character.values()) / n
    decision = "GREEN" if average_ab >= .6 and average_romance >= .5 and reviewed_lite / n >= .7 else "YELLOW" if average_ab >= .4 else "RED"
    return {
        "batch_id": "character_evidence_harvest_v5_8_2",
        "pilot_characters": n,
        "series_count": len({row["series"] for row in selection}),
        "evidence_units": len(evidence),
        "average_evidence_units_per_character": round(len(evidence) / n, 4),
        "average_unique_sources_per_character": round(sum(row["unique_sources"] for row in per_character.values()) / n, 4),
        "median_evidence_units_per_character": median(row["evidence_units"] for row in per_character.values()),
        "median_sources_per_character": median(row["unique_sources"] for row in per_character.values()),
        "average_ab_numeric_coverage": round(average_ab, 4),
        "average_resolved_numeric_coverage": round(sum(row["resolved_numeric_coverage"] for row in per_character.values()) / n, 4),
        "average_romance_ab_coverage": round(average_romance, 4),
        "reviewed_lite": reviewed_lite,
        "candidate_only": candidate_only,
        "insufficient_evidence": insufficient,
        "priority_field_reliable_characters": {field: field_ab[field] for field in ("push_pull", "dependence", "jealousy")},
        "most_effective_source_types": source_yield.most_common(5),
        "hardest_numeric": sorted(NUMERIC_FEATURES, key=lambda field: (field_ab[field], field))[:5],
        "decision": decision,
        "expand_to_remaining_90": decision != "RED",
        "errors": errors,
        "final_write_allowed": False,
        "per_character": per_character,
    }


def run(data_dir: Path) -> dict[str, Any]:
    root = data_dir / "xp_annotation" / "evidence"
    return audit(
        read_csv(root / "character_evidence_pilot_selection_v5_8_2.csv"),
        read_csv(root / "character_evidence_manifest_v5_8_2.csv"),
        read_csv(root / "numeric_resolution_pilot_v5_8_2.csv"),
    )


if __name__ == "__main__":
    project = Path.cwd() if (Path.cwd() / "data").is_dir() else Path(__file__).resolve().parents[1]
    print(json.dumps(run(project / "data"), ensure_ascii=False, indent=2))
