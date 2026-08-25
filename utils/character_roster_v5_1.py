"""Character roster schemas, bulk QA, and coverage metrics."""
from __future__ import annotations

import csv
from pathlib import Path

CHARACTER_FIELDS = (
    "character_id", "name_zh", "name_ja", "name_en", "name_romaji",
    "character_catalog_status", "xp_annotation_status", "official_character_url",
    "source_urls", "source_notes", "spoiler_sensitive", "last_verified_date",
)
APPEARANCE_FIELDS = (
    "appearance_id", "character_id", "game_id", "appearance_type",
    "route_available", "route_type", "spoiler_sensitive", "source_url",
    "verification_status",
)
ROSTER_STATUSES = {"verified", "partially_verified", "candidate", "needs_review"}
XP_STATUSES = {"human_reviewed_gold", "legacy_human_reviewed", "reviewed_lite", "candidate_only", "not_annotated"}
BOOLEAN_VALUES = {"true", "false", "unknown"}
ROUTE_TYPES = {"main", "hidden", "bonus", "unlockable", "special", "unknown"}
APPEARANCE_TYPES = {"base_game", "fan_disc", "sequel", "remake", "collection", "spin_off"}


def read_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames or ()), list(reader)


def validate_roster(characters_path: Path, appearances_path: Path, games_path: Path) -> list[str]:
    errors: list[str] = []
    fields, characters = read_rows(characters_path)
    appearance_fields, appearances = read_rows(appearances_path)
    _, games = read_rows(games_path)
    if fields != CHARACTER_FIELDS:
        errors.append("characters_master.csv schema mismatch")
    if appearance_fields != APPEARANCE_FIELDS:
        errors.append("character_game_appearances.csv schema mismatch")
    ids = [row["character_id"] for row in characters]
    known_characters, known_games = set(ids), {row["game_id"] for row in games}
    if len(ids) != len(known_characters):
        errors.append("character_id must be unique")
    normalized_names = {}
    for row in characters:
        if row["spoiler_sensitive"] not in BOOLEAN_VALUES:
            errors.append(f"{row['character_id']} invalid spoiler_sensitive")
        if row["character_catalog_status"] not in ROSTER_STATUSES:
            errors.append(f"{row['character_id']} invalid character_catalog_status")
        if row["xp_annotation_status"] not in XP_STATUSES:
            errors.append(f"{row['character_id']} invalid xp_annotation_status")
        identity = tuple(row[field].strip().casefold() for field in ("name_ja", "name_en", "name_romaji") if row[field] != "NA")
        if identity and identity in normalized_names:
            errors.append(f"possible duplicate identity: {row['character_id']}")
        if identity:
            normalized_names[identity] = row["character_id"]
    appearance_ids = [row["appearance_id"] for row in appearances]
    pairs = [(row["character_id"], row["game_id"]) for row in appearances]
    if len(appearance_ids) != len(set(appearance_ids)):
        errors.append("appearance_id must be unique")
    if len(pairs) != len(set(pairs)):
        errors.append("duplicate character/game appearance")
    for row in appearances:
        if row["character_id"] not in known_characters:
            errors.append("appearance references unknown character_id")
        if row["game_id"] not in known_games:
            errors.append("appearance references unknown game_id")
        if row["route_available"] not in BOOLEAN_VALUES:
            errors.append("appearance has invalid route_available")
        if row["spoiler_sensitive"] not in BOOLEAN_VALUES:
            errors.append("appearance has invalid spoiler_sensitive")
        if row["route_type"] not in ROUTE_TYPES:
            errors.append("appearance has invalid route_type")
        if row["appearance_type"] not in APPEARANCE_TYPES:
            errors.append("appearance has invalid appearance_type")
        if row["verification_status"] not in ROSTER_STATUSES:
            errors.append("appearance has invalid verification_status")
        if row["verification_status"] == "verified" and not row["source_url"].startswith("https://"):
            errors.append("verified appearance requires official source")
    if known_characters - {row["character_id"] for row in appearances}:
        errors.append("character without game appearance")
    route_by_game = {}
    for row in appearances:
        if row["route_available"] == "true":
            route_by_game.setdefault(row["game_id"], set()).add(row["character_id"])
    for game in games:
        expected = game.get("route_count", "NA")
        if expected not in {"", "NA"} and len(route_by_game.get(game["game_id"], set())) > int(expected):
            errors.append(f"{game['game_id']} catalogued routes exceed expected count")
    return errors


def roster_coverage(characters, appearances, games):
    annotated = {row["character_id"] for row in characters if row["xp_annotation_status"] != "not_annotated"}
    route_by_game, verified_by_game = {}, {}
    for row in appearances:
        if row["route_available"] == "true":
            route_by_game.setdefault(row["game_id"], set()).add(row["character_id"])
            if row["verification_status"] == "verified":
                verified_by_game.setdefault(row["game_id"], set()).add(row["character_id"])
    per_game = []
    for game in games:
        ids = route_by_game.get(game["game_id"], set())
        verified_ids = verified_by_game.get(game["game_id"], set())
        expected_raw = game.get("route_count", "NA")
        expected = None if expected_raw in {"", "NA"} else int(expected_raw)
        catalogued, verified, annotated_count = len(ids), len(verified_ids), len(ids & annotated)
        per_game.append({
            "game_id": game["game_id"], "expected_route_count": expected,
            "catalogued_route_count": catalogued, "verified_route_count": verified,
            "annotated_route_count": annotated_count,
            "roster_coverage": None if expected is None else catalogued / expected,
            "verified_roster_coverage": None if expected is None else verified / expected,
            "xp_annotation_coverage": None if not catalogued else annotated_count / catalogued,
        })
    known = [row for row in per_game if row["expected_route_count"] is not None]
    expected_total = sum(row["expected_route_count"] for row in known)
    catalogued_total = sum(row["catalogued_route_count"] for row in per_game)
    return {
        "per_game": per_game,
        "complete_roster_games": sum(row["roster_coverage"] == 1 for row in known),
        "partial_roster_games": sum(row["roster_coverage"] is None or row["roster_coverage"] < 1 for row in per_game),
        "catalogued_routes": catalogued_total,
        "annotated_characters": len(annotated),
        "roster_coverage": None if not expected_total else sum(row["catalogued_route_count"] for row in known) / expected_total,
        "verified_roster_coverage": None if not expected_total else sum(row["verified_route_count"] for row in known) / expected_total,
        "xp_annotation_coverage": None if not characters else len(annotated) / len(characters),
    }
