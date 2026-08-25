"""Validation helpers for the AOMatch game and roster catalogs."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Mapping, Sequence

GAME_FIELDS = (
    "game_id", "title_zh", "title_ja", "title_en", "series_name", "series_id",
    "parent_game_id", "related_game_id", "entry_type", "developer", "publisher",
    "original_release_date", "original_platform", "current_platforms",
    "official_chinese", "chinese_type", "chinese_region",
    "steam_available", "switch_available", "pc_available", "route_count",
    "character_count", "catalog_priority", "catalog_status", "source_urls",
    "source_notes", "spoiler_policy", "last_verified_date",
)
RELEASE_FIELDS = (
    "release_id", "game_id", "platform", "region", "release_date",
    "official_chinese", "language_notes", "digital_or_physical", "store_status",
    "source_url",
)
MAPPING_FIELDS = ("character_id", "game_id", "source_game_title")
DISCOVERY_FIELDS = (
    "title_zh", "title_ja", "title_en", "developer", "official_chinese",
    "known_platforms", "suggested_priority", "why_include", "verification_status",
)
BOOLEAN_VALUES = {"true", "false", "NA"}
CHINESE_TYPES = {"simplified", "traditional", "both", "none", "NA"}
CATALOG_PRIORITIES = {"P0", "P1", "P2", "P3"}
CATALOG_STATUSES = {"verified", "partially_verified", "candidate", "needs_review"}
ENTRY_TYPES = {"base_game", "fan_disc", "sequel", "remake", "collection", "spin_off"}


def read_rows(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), list(reader)


def normalized_title(value: str) -> str:
    return re.sub(r"[\s:：・･×xX～~\-—–]+", "", value).casefold()


def validate_catalog(
    games_path: Path, releases_path: Path, mapping_path: Path,
    character_ids: Sequence[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    game_fields, games = read_rows(games_path)
    release_fields, releases = read_rows(releases_path)
    mapping_fields, mappings = read_rows(mapping_path)
    if game_fields != GAME_FIELDS:
        errors.append("games_master.csv schema mismatch")
    if release_fields != RELEASE_FIELDS:
        errors.append("game_releases.csv schema mismatch")
    if mapping_fields != MAPPING_FIELDS:
        errors.append("character_game_mapping.csv schema mismatch")
    game_ids = [row["game_id"] for row in games]
    known_games = set(game_ids)
    if len(game_ids) != len(known_games):
        errors.append("game_id must be unique")
    release_ids = [row["release_id"] for row in releases]
    if len(release_ids) != len(set(release_ids)):
        errors.append("release_id must be unique")
    if any(row["game_id"] not in known_games for row in releases):
        errors.append("release references unknown game_id")
    mapped = [row["character_id"] for row in mappings]
    if len(mapped) != len(set(mapped)):
        errors.append("character mapping must be unique")
    if any(row["game_id"] not in known_games for row in mappings):
        errors.append("character mapping references unknown game_id")
    if character_ids is not None and set(mapped) != set(character_ids):
        errors.append("character mapping does not cover the formal character database")

    seen_titles: dict[tuple[str, str], str] = {}
    for row in games:
        for field in ("title_zh", "title_ja", "title_en"):
            value = row.get(field, "").strip()
            if value in {"", "NA"}:
                continue
            key = (field, normalized_title(value))
            if key in seen_titles:
                errors.append(f"duplicate {field}: {value}")
            seen_titles[key] = row["game_id"]
        for field in ("official_chinese", "steam_available", "switch_available", "pc_available"):
            if row.get(field) not in BOOLEAN_VALUES:
                errors.append(f"{row['game_id']} invalid {field}")
        if row.get("chinese_type") not in CHINESE_TYPES:
            errors.append(f"{row['game_id']} invalid chinese_type")
        if row.get("catalog_priority") not in CATALOG_PRIORITIES:
            errors.append(f"{row['game_id']} invalid catalog_priority")
        if row.get("catalog_status") not in CATALOG_STATUSES:
            errors.append(f"{row['game_id']} invalid catalog_status")
        if row.get("entry_type") not in ENTRY_TYPES:
            errors.append(f"{row['game_id']} invalid entry_type")
        parent = row.get("parent_game_id", "")
        if parent not in {"", "NA"} and parent not in known_games:
            errors.append(f"{row['game_id']} unknown parent_game_id")
        if row.get("entry_type") == "fan_disc" and parent in {"", "NA"}:
            errors.append(f"{row['game_id']} fan_disc requires parent_game_id")
        related = row.get("related_game_id", "")
        if related not in {"", "NA"}:
            for related_id in related.split("|"):
                if related_id not in known_games:
                    errors.append(f"{row['game_id']} unknown related_game_id")
        if row.get("catalog_status") == "verified" and not row.get("source_urls", "").strip():
            errors.append(f"{row['game_id']} verified row requires source_urls")
    series_names: dict[str, str] = {}
    series_ids: dict[str, str] = {}
    for row in games:
        series_id, series_name = row.get("series_id", ""), row.get("series_name", "")
        if series_id in {"", "NA"} or series_name in {"", "NA"}:
            errors.append(f"{row['game_id']} requires series_id and series_name")
            continue
        if series_id in series_names and series_names[series_id] != series_name:
            errors.append(f"{series_id} maps to multiple series names")
        if series_name in series_ids and series_ids[series_name] != series_id:
            errors.append(f"{series_name} maps to multiple series IDs")
        series_names[series_id] = series_name
        series_ids[series_name] = series_id
    return errors


def validate_discovery(path: Path, games_path: Path | None = None) -> list[str]:
    fields, rows = read_rows(path)
    errors = [] if fields == DISCOVERY_FIELDS else ["discovery schema mismatch"]
    formal_titles: set[str] = set()
    if games_path:
        _, games = read_rows(games_path)
        formal_titles = {normalized_title(row[field]) for row in games
                         for field in ("title_zh", "title_ja", "title_en")
                         if row.get(field) not in {"", "NA"}}
    for index, row in enumerate(rows, 2):
        if row.get("suggested_priority") not in CATALOG_PRIORITIES:
            errors.append(f"discovery row {index} invalid priority")
        if row.get("verification_status") not in {"candidate", "needs_review"}:
            errors.append(f"discovery row {index} invalid status")
        titles = [row.get(field, "") for field in ("title_zh", "title_ja", "title_en")]
        if formal_titles.intersection(normalized_title(x) for x in titles if x not in {"", "NA"}):
            errors.append(f"discovery row {index} already formal")
    return errors


def catalog_summary(games: Sequence[Mapping[str, str]]) -> dict[str, object]:
    statuses = {status: 0 for status in CATALOG_STATUSES}
    priorities = {priority: 0 for priority in CATALOG_PRIORITIES}
    for row in games:
        statuses[row["catalog_status"]] += 1
        priorities[row["catalog_priority"]] += 1
    return {"game_count": len(games), "statuses": statuses, "priorities": priorities}
