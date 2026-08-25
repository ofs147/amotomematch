"""v5.8 fixed-selection XP draft and conservative automated QA.

This module never writes the production XP tables.  A numeric value in this
draft is an annotation prior, not an approved fact: fields without direct,
character-specific evidence stay at Confidence C and enter the exception
queue.  This is intentional; source-readiness must not be converted into fake
certainty merely to increase AUTO_PASS.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

from utils.bulk_expansion_v3 import materialize_character
from utils.roster_xp_pipeline_v5_3 import write_json_utf8
from utils.schema import (
    DICTIONARY_TAG_FIELDS,
    FEATURE_LAYERS,
    NUMERIC_FEATURES,
)

BATCH_ID = "priority_xp_v5_8_batch_01"
SELECTION_FILE = "xp_annotation_priority_v5_7.csv"
ROMANCE_RISK_FIELDS = (
    "initiative", "possessiveness", "protectiveness", "dependence",
    "jealousy", "push_pull", "devotion", "control",
)
DEFINITION_BOUNDARY_FIELDS = (
    "danger_level", "mystery_level", "gap_moe", "emotional_stability",
)
GOLD_REVIEW_FIELDS = (
    "devotion", "control", "initiative", "gap_moe", "danger_level",
)
VALID_CONFIDENCE = {"A", "B", "C", "NA"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _half_step(value: float) -> float:
    return min(5.0, max(1.0, round(value * 2) / 2))


def _safe_source(row: Mapping[str, str]) -> str:
    value = str(row.get("official_character_url", "")).strip()
    return value if value.startswith(("https://", "http://")) else "NA"


def load_fixed_selection(data_dir: Path) -> list[dict[str, str]]:
    rows = _read_csv(data_dir / SELECTION_FILE)
    ids = [row["character_id"] for row in rows]
    if len(rows) != 90 or len(set(ids)) != 90:
        raise ValueError("v5.8 requires exactly 90 unique v5.7 selections")
    tiers = Counter(row["suggested_tier"] for row in rows)
    readiness = Counter(row["source_readiness"] for row in rows)
    if tiers != {"Gold Candidate": 12, "Reviewed Lite": 78}:
        raise ValueError(f"unexpected fixed tier distribution: {dict(tiers)}")
    if readiness != {"HIGH": 48, "MEDIUM": 42}:
        raise ValueError(f"unexpected source-readiness distribution: {dict(readiness)}")
    return rows


def _numeric_priors(xp_rows: list[dict[str, str]]) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    global_prior = {
        field: _half_step(median(float(row[field]) for row in xp_rows))
        for field in NUMERIC_FEATURES
    }
    by_series: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in xp_rows:
        by_series[row.get("series", "")].append(row)
    series_priors = {
        series: {
            field: _half_step(sum(float(row[field]) for row in rows) / len(rows))
            for field in NUMERIC_FEATURES
        }
        for series, rows in by_series.items() if series
    }
    return global_prior, series_priors


def _nearest_reference(prior: Mapping[str, float], references: list[dict[str, str]]) -> tuple[str, float]:
    def distance(row: Mapping[str, str]) -> float:
        return math.sqrt(sum(((prior[f] - float(row[f])) / 4) ** 2 for f in NUMERIC_FEATURES) / 20)
    nearest = min(references, key=distance)
    return nearest["character_id"], round(distance(nearest), 4)


def build_draft(data_dir: Path) -> dict[str, Any]:
    selected = load_fixed_selection(data_dir)
    master_rows = _read_csv(data_dir / "characters_master.csv")
    masters = {row["character_id"]: row for row in master_rows}
    appearances = _read_csv(data_dir / "character_game_appearances.csv")
    games = {row["game_id"]: row for row in _read_csv(data_dir / "games_master.csv")}
    xp_rows = _read_csv(data_dir / "characters_v2_candidate.csv")
    xp_ids = {row["character_id"] for row in xp_rows}
    metadata = {row["character_id"]: row for row in _read_csv(data_dir / "characters_v2_candidate_metadata.csv")}
    references = [row for row in xp_rows if metadata.get(row["character_id"], {}).get("annotation_status") in {"human_reviewed_gold", "human_reviewed"}]
    global_prior, series_priors = _numeric_priors(xp_rows)
    by_character: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in appearances:
        by_character[row["character_id"]].append(row)

    characters: list[dict[str, Any]] = []
    for selection in selected:
        cid = selection["character_id"]
        if cid not in masters or cid in xp_ids:
            raise ValueError(f"selection identity/status conflict: {cid}")
        master = masters[cid]
        links = sorted(by_character.get(cid, []), key=lambda row: (row.get("appearance_type") != "base", row["game_id"]))
        if not links or links[0]["game_id"] not in games:
            raise ValueError(f"missing character/game mapping: {cid}")
        game = games[links[0]["game_id"]]
        prior_scope = "same_series" if selection["series"] in series_priors else "global_median"
        prior = dict(series_priors.get(selection["series"], global_prior))
        reference_id, distance = _nearest_reference(prior, references)
        readiness = selection["source_readiness"]
        # LOOK can be checked from official public art. Personality receives B
        # only for HIGH-readiness pages; route-dependent layers remain C until
        # direct route evidence is reviewed.
        confidence = {
            field: ("B" if FEATURE_LAYERS[field] == "LOOK" else
                    "B" if FEATURE_LAYERS[field] == "PERSONALITY" and readiness == "HIGH" else "C")
            for field in NUMERIC_FEATURES
        }
        source = _safe_source(master)
        evidence = {
            "LOOK": f"官方公开角色页/立绘：{source}",
            "PERSONALITY": f"官方公开角色介绍：{source}；只覆盖路线前可见性格。",
            "ARCHETYPE": "Draft prior；danger/mystery/gap 不由世界观、隐藏身份或悲惨过去自动推高。",
            "ROMANCE": "Draft prior；等待角色本人路线行为证据，不把职责、慢热、依赖或占有混同。",
            "TAGS": "未获得逐项直接证据前保持空集合；不创建新 Tag，也不暴露剧情信息。",
        }
        characters.append({
            "character_id": cid,
            "character_name": selection["character_name"],
            "game": selection["game"],
            "series": selection["series"],
            "route_type": links[0].get("route_type", "unknown"),
            "annotation_tier": "A" if selection["suggested_tier"] == "Gold Candidate" else "B",
            "target_status": "gold_candidate" if selection["suggested_tier"] == "Gold Candidate" else "reviewed_lite",
            "source_readiness": readiness,
            "numeric": prior,
            "confidence_default": "C",
            "confidence_overrides": confidence,
            "evidence": evidence,
            "tags": {field: [] for field in DICTIONARY_TAG_FIELDS} | {"keywords": []},
            "nearest_reference": reference_id,
            "nearest_reference_distance": distance,
            "prior_scope": prior_scope,
            "character_summary": "基于公开资料建立的保守候选档案；关系体验字段仍待路线证据复核。",
            "recommendation_reason_safe_features": [],
            "source_urls": [] if source == "NA" else [source],
            "roster_game_id": links[0]["game_id"],
            "spoiler_safe": True,
        })
    return {
        "batch_id": BATCH_ID,
        "selection_source": SELECTION_FILE,
        "selected_size": len(characters),
        "draft_only": True,
        "coverage_gap_used_for_numeric": False,
        "characters": characters,
    }


def run_qa(draft: Mapping[str, Any], data_dir: Path) -> dict[str, Any]:
    masters = {row["character_id"] for row in _read_csv(data_dir / "characters_master.csv")}
    xp_ids = {row["character_id"] for row in _read_csv(data_dir / "characters_v2_candidate.csv")}
    statuses: dict[str, str] = {}
    exceptions: list[dict[str, str]] = []
    gold_queue: list[dict[str, Any]] = []

    for item in draft["characters"]:
        cid = item["character_id"]
        high: list[str] = []
        if cid not in masters or cid in xp_ids:
            high.append("identity/game mapping conflict")
        if set(item["numeric"]) != set(NUMERIC_FEATURES):
            high.append("incomplete numeric schema")
        for field, value in item["numeric"].items():
            if not 1 <= float(value) <= 5 or float(value) * 2 % 1:
                high.append(f"invalid numeric {field}")
            if item["confidence_overrides"].get(field, "NA") not in VALID_CONFIDENCE:
                high.append(f"invalid confidence {field}")
        if not item.get("spoiler_safe"):
            high.append("spoiler exposure")
        if high:
            statuses[cid] = "BLOCKED"
            for reason in high:
                exceptions.append({"character_id": cid, "character": item["character_name"], "game": item["game"], "field": "schema", "candidate_value": "", "confidence": "NA", "severity": "HIGH", "exception_type": "INTEGRITY_CONFLICT", "reason": reason, "suggested_action": "修复后重新运行 QA。"})
            continue

        unresolved = [field for field in ROMANCE_RISK_FIELDS + DEFINITION_BOUNDARY_FIELDS if item["confidence_overrides"][field] in {"C", "NA"}]
        if item["annotation_tier"] == "A":
            statuses[cid] = "REVIEW_REQUIRED"
            fields = []
            for field in GOLD_REVIEW_FIELDS:
                fields.append({"field": field, "candidate_value": item["numeric"][field], "confidence": item["confidence_overrides"][field], "reason": "Gold 必须由熟悉路线的 Reviewer 以角色本人行为证据确认。"})
            gold_queue.append({"character_id": cid, "character": item["character_name"], "game": item["game"], "fields": fields})
        elif unresolved:
            statuses[cid] = "REVIEW_REQUIRED"
            exceptions.append({
                "character_id": cid, "character": item["character_name"], "game": item["game"],
                "field": ";".join(unresolved), "candidate_value": "grouped review",
                "confidence": "C", "severity": "MEDIUM", "exception_type": "CHARACTER_EVIDENCE_REQUIRED",
                "reason": "公开角色页不足以直接证明关键 Romance / character-definition 数值；已保留保守 prior，未伪装为 A/B。",
                "suggested_action": "快速核对角色本人路线行为；确认后可整体 Lite Pass。",
            })
        else:
            statuses[cid] = "AUTO_PASS"

    counts = Counter(statuses.values())
    severity = Counter(row["severity"] for row in exceptions)
    return {
        "batch_id": BATCH_ID,
        "selection_source": draft["selection_source"],
        "total": len(draft["characters"]),
        "tier_counts": dict(Counter(item["annotation_tier"] for item in draft["characters"])),
        "status_counts": {key: counts.get(key, 0) for key in ("AUTO_PASS", "REVIEW_REQUIRED", "BLOCKED")},
        "exception_severity_counts": {key: severity.get(key, 0) for key in ("HIGH", "MEDIUM", "LOW")},
        "statuses": statuses,
        "exceptions": exceptions,
        "gold_review_queue": gold_queue,
        "final_write_allowed": False,
    }


def _bin_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    result = {}
    for field in NUMERIC_FEATURES:
        values = [float(row["numeric"][field]) for row in rows]
        result[field] = {
            "low_1_2_5": sum(value <= 2.5 for value in values),
            "high_4_5_5": sum(value >= 4.5 for value in values),
        }
    return result


def run_pipeline(data_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    draft = build_draft(data_dir)
    qa = run_qa(draft, data_dir)
    qa["draft_bin_counts"] = _bin_counts(draft["characters"])
    output = data_dir / "xp_annotation"
    write_json_utf8(output / "priority_xp_v5_8_batch_01_draft.json", draft)
    write_json_utf8(output / "priority_xp_v5_8_batch_01_qa.json", qa)
    return draft, qa


if __name__ == "__main__":
    # This project is also used from Windows accounts with non-ASCII names.
    # Some embeddable Python launchers mangle ``__file__`` while cwd remains
    # a valid native path, so prefer the repository cwd when available.
    root = Path.cwd() if (Path.cwd() / "data").is_dir() else Path(__file__).resolve().parents[1]
    draft, qa = run_pipeline(root / "data")
    print(json.dumps({"selected": draft["selected_size"], **qa["status_counts"], "severity": qa["exception_severity_counts"]}, ensure_ascii=False, indent=2))
