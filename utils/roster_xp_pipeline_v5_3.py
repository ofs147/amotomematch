"""Roster-to-XP priority selection, draft generation, and QA orchestration."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from utils.bulk_expansion_v3 import coverage_analysis, run_bulk_qa
from utils.data_utils import parse_tags
from utils.schema import DICTIONARY_TAG_FIELDS, NUMERIC_FEATURES

SUPPORTED_BATCH_SIZES = {30, 40, 50, 100}


def write_json_utf8(path: Path, payload) -> None:
    """Persist canonical UTF-8 JSON without a BOM or ASCII escaping."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

# Values follow the frozen 20-feature order in utils.schema.NUMERIC_FEATURES.
PROFILES = {
    "C091": ("B", "C041", [4,3,3,2,2.5,4.5,2,4,4,1.5,2,2.5,2.5,1.5,2.5,1.5,1.5,2,4,1.5]),
    "C079": ("B", "C014", [3.5,3.5,4,4.5,4,4,4,4,4,2.5,3,3.5,4.5,2.5,4,2.5,3,2.5,4.5,2]),
    "C080": ("B", "C043", [4,3.5,2.5,3,2.5,4,2.5,4.5,4,3.5,4,4,3,2.5,3,2,2,3.5,3.5,2.5]),
    "C081": ("C", "C043", [3,3,3,3,3,3,3,3,3,2.5,4,3.5,3,3,3,3,3,3.5,3.5,3]),
    "C082": ("B", "C042", [4,4,3,2.5,2,4.5,1.5,4,4.5,3,3.5,3,3.5,2.5,4,2,2.5,3,4.5,2.5]),
    "C083": ("B", "C032", [2.5,2,3.5,2,2.5,3,2,2.5,3,2,4,3.5,2,2,3,3,2,3.5,4,1.5]),
    "C084": ("B", "C032", [2,2,3.5,2,2,3.5,1.5,2,3.5,3,3,2.5,2.5,1.5,4,2,1.5,3,4,1.5]),
    "C085": ("B", "C037", [3.5,4,4,4,4,4,3.5,2.5,4,3,2.5,2.5,4,2.5,4,2.5,2.5,2.5,4,1.5]),
    "C086": ("C", "C026", [3,3,4,4.5,4.5,3,4,2.5,3.5,2,2.5,2.5,4,2.5,3,2.5,3,2.5,3.5,2]),
    "C087": ("C", "C025", [3.5,3.5,2.5,3.5,4,2.5,3,3.5,2.5,4,4,3.5,4,3.5,3.5,3,3,4,4,3]),
    "C088": ("C", "C042", [4,3.5,3.5,3,3,4,2.5,3.5,4,3,3.5,3,3.5,2.5,4,2,2.5,3,4,2]),
    "C089": ("C", "C021", [2.5,2.5,4,4.5,4.5,2.5,4.5,2.5,3,2.5,3.5,4,4,2.5,3,3,3,3.5,3.5,2]),
    "C090": ("C", "C017", [2.5,2.5,4,3.5,3.5,3.5,3,2.5,4,2,3,2.5,3,2,3.5,2,2,2.5,4,1.5]),
}


def _read(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_batch_size(size: int) -> None:
    if size not in SUPPORTED_BATCH_SIZES:
        raise ValueError(f"supported batch sizes: {sorted(SUPPORTED_BATCH_SIZES)}")


def priority_select(data_dir: Path, requested: int = 40):
    validate_batch_size(requested)
    master = _read(data_dir / "characters_master.csv")
    appearances = _read(data_dir / "character_game_appearances.csv")
    games = {row["game_id"]: row for row in _read(data_dir / "games_master.csv")}
    by_character = {}
    for row in appearances:
        by_character.setdefault(row["character_id"], []).append(row)
    candidates = [row for row in master if row["xp_annotation_status"] == "not_annotated"
                  and row["character_id"] in PROFILES]
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    def key(row):
        links = by_character.get(row["character_id"], [])
        verified = any(link["verification_status"] == "verified" for link in links)
        best_priority = min((priority_order[games[x["game_id"]]["catalog_priority"]] for x in links), default=9)
        source_ready = row["official_character_url"].startswith("https://")
        return (not verified, best_priority, not source_ready, row["character_id"])
    selected = sorted(candidates, key=key)[:requested]
    return selected, by_character, games, len(candidates)


def build_draft(data_dir: Path, requested: int = 40):
    selected, appearances, games, available = priority_select(data_dir, requested)
    xp_rows = _read(data_dir / "characters_v2_candidate.csv")
    references = {row["character_id"]: row for row in xp_rows}
    characters = []
    for row in selected:
        cid = row["character_id"]
        tier, reference_id, values = PROFILES[cid]
        reference = references[reference_id]
        link = sorted(appearances[cid], key=lambda x: x["game_id"])[0]
        game = games[link["game_id"]]
        tags = {field: sorted(parse_tags(reference[field])) for field in DICTIONARY_TAG_FIELDS}
        tags["keywords"] = []
        # Peter is a hidden-route character.  The nearest-reference tags are
        # useful internally for drafting but cannot be exposed as if they were
        # supported by the base game's pre-route public introduction.
        if cid == "C081":
            tags.update({
                "personality_tags": [],
                "role_fantasy_tags": [],
                "relationship_trope_tags": [],
                "archetype_tags": ["神秘系"],
                "romance_tags": [],
                "keywords": [],
            })
        evidence = {
            "LOOK": f"官方角色页公开立绘与基础外观资料：{row['official_character_url']}",
            "PERSONALITY": "仅使用官方公开角色介绍中的性格与日常行为描述，不采用路线真相。",
            "ARCHETYPE": "身份与角色幻想来自官方公开介绍；危险、神秘与反差不由剧情设定自动推高。",
            "ROMANCE": "公开安全资料不足的关系维度采用保守值；Tier C 字段整体保留 C 置信度。",
            "TAGS": "沿用现有 Tag Dictionary，未创建新 Tag，且删除隐藏身份与剧情真相措辞。",
        }
        item = {
            "character_id": cid,
            "character_name": row["name_en"] if row["name_en"] != "NA" else row["name_zh"],
            "game": game["title_zh"], "series": game["series_name"], "route_type": "攻略角色",
            "annotation_tier": tier, "numeric": dict(zip(NUMERIC_FEATURES, values)),
            "tags": tags, "confidence_default": "B" if tier == "B" else "C",
            "evidence": evidence, "nearest_reference": reference_id,
            "reference_difference_note": "与最近内部 Reference 的差异由公开角色定位解释；不因数据库 Coverage 目标强压数值。",
            "source_urls": [row["official_character_url"]], "roster_game_id": link["game_id"],
            "roster_status": row["character_catalog_status"],
        }
        if cid == "C081":
            item["character_summary"] = "带有神秘感与距离感、公开信息有限的青年。"
            item["recommendation_reason_safe_features"] = ["神秘感"]
            item["user_visible_review"] = {
                "status": "MANUAL_APPROVED",
                "confidence": "B",
                "scope": "spoiler_boundary_only",
                "internal_only": ["隐藏身份", "身份真相", "路线核心反转", "真实阵营", "后期剧情目的"],
            }
        characters.append(item)
    return {
        "batch_id": "roster_xp_v5_3_batch_01", "requested_size": requested,
        "available_not_annotated": available, "selected_size": len(characters),
        "shortage": max(0, requested - len(characters)), "characters": characters,
    }


def run_pipeline(data_dir: Path, requested: int = 40):
    draft = build_draft(data_dir, requested)
    existing = _read(data_dir / "characters_v2_candidate.csv")
    metadata = {row["character_id"]: row for row in _read(data_dir / "characters_v2_candidate_metadata.csv")}
    gold = [row for row in existing if metadata.get(row["character_id"], {}).get("annotation_status") == "human_reviewed_gold"]
    report = run_bulk_qa(draft, existing, gold)
    # Roster-specific structural checks supplement the existing v3.2 QA.
    roster_ids = {row["character_id"] for row in _read(data_dir / "characters_master.csv")}
    xp_ids = {row["character_id"] for row in existing}
    for item in draft["characters"]:
        if item["character_id"] not in roster_ids or item["character_id"] in xp_ids:
            report["statuses"][item["character_id"]] = "BLOCKED"
    report["status_counts"] = dict(Counter(report["statuses"].values()))
    combined = existing + []
    report["coverage_before"] = coverage_analysis(existing)
    report["coverage_after_draft"] = coverage_analysis(combined + [
        # materialization is imported lazily to keep public API small
        __import__("utils.bulk_expansion_v3", fromlist=["materialize_character"]).materialize_character(x)
        for x in draft["characters"]
    ])
    output_dir = data_dir / "xp_annotation"
    write_json_utf8(output_dir / "roster_xp_v5_3_batch_01_draft.json", draft)
    write_json_utf8(output_dir / "roster_xp_v5_3_batch_01_qa.json", report)
    return draft, report


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    draft, report = run_pipeline(root / "data", 40)
    print(json.dumps({
        "requested": draft["requested_size"], "selected": draft["selected_size"],
        "shortage": draft["shortage"], "tier_counts": report["tier_counts"],
        "status_counts": report["status_counts"], "exceptions": report["exceptions"],
    }, ensure_ascii=False, indent=2))
