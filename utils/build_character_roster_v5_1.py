"""Build the initial roster catalog from the 77 XP-annotated characters."""
from __future__ import annotations

import csv
from pathlib import Path

from utils.character_roster_v5_1 import APPEARANCE_FIELDS, CHARACTER_FIELDS
from utils.game_catalog_v5 import DISCOVERY_FIELDS, GAME_FIELDS, RELEASE_FIELDS

XP_STATUS_MAP = {
    "human_reviewed": "legacy_human_reviewed",
    "human_reviewed_gold": "human_reviewed_gold",
    "reviewed_lite": "reviewed_lite",
    "candidate_only": "candidate_only",
}
VERIFIED_ROSTERS = {
    "G012": (4, "https://products.voltage.co.jp/tempest/english/characters/"),
    "G014": (2, "https://store.steampowered.com/app/1056570/TAISHO_x_ALICE_episode_1/"),
    "G022": (6, "https://www.otomate.jp/virche/chara/"),
}


def _read(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def build(data_dir: Path) -> None:
    characters = _read(data_dir / "characters_v2_candidate.csv")
    metadata = {row["character_id"]: row for row in _read(data_dir / "characters_v2_candidate_metadata.csv")}
    mappings = {row["character_id"]: row for row in _read(data_dir / "character_game_mapping.csv")}
    games = _read(data_dir / "games_master.csv")
    game_entry = {row["game_id"]: row["entry_type"] for row in games}
    master_rows, appearance_rows = [], []
    for row in characters:
        cid = row["character_id"]
        game_id = mappings[cid]["game_id"]
        primary_name = row["character_name"]
        ascii_name = primary_name.isascii()
        verified = game_id in VERIFIED_ROSTERS
        source = VERIFIED_ROSTERS[game_id][1] if verified else "NA"
        master_rows.append({
            "character_id": cid, "name_zh": "NA" if ascii_name else primary_name,
            "name_ja": "NA", "name_en": primary_name if ascii_name else "NA",
            "name_romaji": primary_name if ascii_name else "NA", "official_character_url": source,
            "character_catalog_status": "verified" if verified else "partially_verified",
            "xp_annotation_status": XP_STATUS_MAP[metadata[cid]["annotation_status"]],
            "spoiler_sensitive": "false", "source_urls": source,
            "source_notes": "Seeded from the existing XP database; identity fields remain compatible",
            "last_verified_date": "2026-08-21" if verified else "NA",
        })
        appearance_rows.append({
            "appearance_id": f"A{len(appearance_rows)+1:04d}", "character_id": cid,
            "game_id": game_id, "appearance_type": game_entry[game_id],
            "route_available": "true", "route_type": "main", "spoiler_sensitive": "false",
            "source_url": source,
            "verification_status": "verified" if verified else "partially_verified",
        })
    for game in games:
        if game["game_id"] in VERIFIED_ROSTERS:
            expected, source = VERIFIED_ROSTERS[game["game_id"]]
            game["route_count"] = str(expected)
            game["character_count"] = str(expected)
            if source not in game["source_urls"]:
                game["source_urls"] = source
    _write(data_dir / "characters_master.csv", CHARACTER_FIELDS, master_rows)
    _write(data_dir / "character_game_appearances.csv", APPEARANCE_FIELDS, appearance_rows)
    _write(data_dir / "games_master.csv", GAME_FIELDS, games)

    _write(data_dir / "game_releases.csv", RELEASE_FIELDS, _read(data_dir / "game_releases.csv"))
    _write(
        data_dir / "catalog_discovery_candidates.csv",
        DISCOVERY_FIELDS,
        _read(data_dir / "catalog_discovery_candidates.csv"),
    )


if __name__ == "__main__":
    build(Path(__file__).resolve().parents[1] / "data")
