"""Integrity-gated v5.4.2 large roster final write."""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
from pathlib import Path

from utils.bulk_expansion_v3 import load_json_integrity
from utils.character_roster_v5_1 import roster_coverage, validate_roster
from utils.game_catalog_v5 import validate_catalog


def _read(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def _temp_csv(path: Path, fields, rows):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", delete=False,
                                     dir=path.parent) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
        return Path(handle.name)


def execute(data_dir: Path):
    expansion = data_dir / "roster_expansion"
    game_ids = set(load_json_integrity(expansion / "approved_game_ids.json"))
    character_ids = set(load_json_integrity(expansion / "approved_character_ids.json"))
    deferred_ids = set(load_json_integrity(expansion / "deferred_character_ids.json"))
    draft = load_json_integrity(expansion / "roster_v5_4_batch_01_resolved.json",
                                required_fields=("batch_id", "games", "characters", "appearance_draft"))
    qa = load_json_integrity(expansion / "roster_v5_4_batch_01_resolution_qa.json",
                             required_fields=("batch_id", "integrity_errors"))
    if draft["batch_id"] != qa["batch_id"] or qa["integrity_errors"]:
        raise ValueError("artifact identity/integrity failure")
    if character_ids & deferred_ids:
        raise ValueError("approved/deferred character overlap")
    if game_ids != {g["game_candidate_id"] for g in draft["games"]}:
        raise ValueError("approved games do not match resolved draft")
    draft_characters = {c["character_id"]: c for c in draft["characters"]}
    if not character_ids <= set(draft_characters):
        raise ValueError("approved character missing from resolved draft")

    paths = {name: data_dir / name for name in (
        "games_master.csv", "game_releases.csv", "characters_master.csv",
        "character_game_appearances.csv", "character_game_mapping.csv",
        "catalog_coverage_baseline.csv")}
    game_fields, old_games = _read(paths["games_master.csv"])
    release_fields, old_releases = _read(paths["game_releases.csv"])
    char_fields, old_characters = _read(paths["characters_master.csv"])
    app_fields, old_apps = _read(paths["character_game_appearances.csv"])
    mapping_fields, old_mappings = _read(paths["character_game_mapping.csv"])
    coverage_fields, old_coverage = _read(paths["catalog_coverage_baseline.csv"])
    if game_ids & {g["game_id"] for g in old_games} or character_ids & {c["character_id"] for c in old_characters}:
        raise ValueError("approved IDs already exist in formal catalogs")

    old_game_by_id = {g["game_id"]: g for g in old_games}
    max_series = max(int(g["series_id"][1:]) for g in old_games)
    next_series = max_series + 1
    new_games, game_source = [], {}
    partial = {d["game_id"] for d in draft["resolution_decisions"] if d["status"] == "PARTIAL_APPROVED"}
    for source in draft["games"]:
        gid = source["game_candidate_id"]
        parent = source["parent_game_id"]
        if parent != "NA":
            series_id, series_name = old_game_by_id[parent]["series_id"], old_game_by_id[parent]["series_name"]
        else:
            series_id, series_name = f"S{next_series:03d}", source["title_zh"]
            next_series += 1
        game_source[gid] = source["source_url"]
        app_count = sum(a["game_id"] == gid and a["character_id"] not in deferred_ids for a in draft["appearance_draft"])
        entry_type = "collection" if gid == "G035" else source["entry_type"]
        new_games.append({
            "game_id": gid, "title_zh": source["title_zh"], "title_ja": source["title_ja"],
            "title_en": source["title_en"], "series_name": series_name, "series_id": series_id,
            "parent_game_id": parent, "related_game_id": "NA", "entry_type": entry_type,
            "developer": source["developer"], "publisher": source["publisher"],
            "original_release_date": source["original_release_date"], "original_platform": source["original_platform"],
            "current_platforms": source["original_platform"], "official_chinese": "NA", "chinese_type": "NA",
            "chinese_region": "NA", "steam_available": "NA",
            "switch_available": "true" if source["original_platform"] == "Switch" else "NA",
            "pc_available": "true" if source["original_platform"] == "Windows" else "NA",
            "route_count": "NA" if gid in partial else str(app_count), "character_count": str(app_count),
            "catalog_priority": "P1", "catalog_status": "partially_verified" if gid in partial else "verified",
            "source_urls": source["source_url"],
            "source_notes": "v5.4 game-first roster expansion; deferred identities excluded" if gid in partial else "v5.4 game-first roster expansion verified",
            "spoiler_policy": "user_visible_safe_only", "last_verified_date": "2026-08-21",
        })

    max_release = max((int(r["release_id"][1:]) for r in old_releases), default=0)
    new_releases = []
    for index, game in enumerate(new_games, max_release + 1):
        new_releases.append({"release_id": f"R{index:03d}", "game_id": game["game_id"],
                             "platform": game["original_platform"], "region": "Japan",
                             "release_date": game["original_release_date"], "official_chinese": "NA",
                             "language_notes": "Localization metadata deprecated; not actively maintained",
                             "digital_or_physical": "unknown", "store_status": "unknown",
                             "source_url": game["source_urls"]})

    new_characters = []
    for cid in sorted(character_ids):
        row = draft_characters[cid]
        source = row["source_url"]
        new_characters.append({"character_id": cid, "name_zh": row["name_zh"], "name_ja": row["name_ja"],
                               "name_en": row["name_en"], "name_romaji": row["name_romaji"],
                               "character_catalog_status": "verified", "xp_annotation_status": "not_annotated",
                               "official_character_url": source, "source_urls": source,
                               "source_notes": "v5.4 approved roster identity", "spoiler_sensitive": row["spoiler_sensitive"],
                               "last_verified_date": "2026-08-21"})

    approved_appearances = [a for a in draft["appearance_draft"]
                            if a["game_id"] in game_ids and a["character_id"] not in deferred_ids]
    next_app = max(int(a["appearance_id"][1:]) for a in old_apps) + 1
    new_apps = []
    for offset, row in enumerate(approved_appearances):
        new_apps.append({**row, "appearance_id": f"A{next_app + offset:04d}",
                         "source_url": game_source[row["game_id"]]})
    primary_game = {}
    for row in new_apps:
        if row["character_id"] in character_ids:
            primary_game.setdefault(row["character_id"], row["game_id"])
    new_mappings = [{"character_id": cid, "game_id": primary_game[cid],
                     "source_game_title": next(g["title_zh"] for g in new_games if g["game_id"] == primary_game[cid])}
                    for cid in sorted(character_ids)]

    combined = {
        "games_master.csv": old_games + new_games,
        "game_releases.csv": old_releases + new_releases,
        "characters_master.csv": old_characters + new_characters,
        "character_game_appearances.csv": old_apps + new_apps,
        "character_game_mapping.csv": old_mappings + new_mappings,
    }
    staging = Path(tempfile.mkdtemp(dir=data_dir))
    staged = {}
    try:
        field_map = {"games_master.csv": game_fields, "game_releases.csv": release_fields,
                     "characters_master.csv": char_fields, "character_game_appearances.csv": app_fields,
                     "character_game_mapping.csv": mapping_fields}
        for name, rows in combined.items():
            target = staging / name
            with target.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=field_map[name], extrasaction="ignore")
                writer.writeheader(); writer.writerows(rows)
            staged[name] = target
        errors = validate_catalog(staged["games_master.csv"], staged["game_releases.csv"],
                                  staged["character_game_mapping.csv"], [c["character_id"] for c in combined["characters_master.csv"]])
        errors += validate_roster(staged["characters_master.csv"], staged["character_game_appearances.csv"], staged["games_master.csv"])
        if errors:
            raise ValueError("Final Write staging validation failed: " + " | ".join(errors))
        backup = expansion / "v5_4_2_prewrite_backup"; backup.mkdir(exist_ok=True)
        for name in combined:
            shutil.copy2(paths[name], backup / name)
        for name, source in staged.items():
            source.replace(paths[name])
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    _, games_after = _read(paths["games_master.csv"])
    _, chars_after = _read(paths["characters_master.csv"])
    _, apps_after = _read(paths["character_game_appearances.csv"])
    report = roster_coverage(chars_after, apps_after, games_after)
    metrics = {row["metric"]: row for row in old_coverage}
    metrics["Game Catalog Coverage"].update(completed_count=str(len(games_after)))
    metrics["XP Annotation Coverage"].update(completed_count="90", target_count=str(len(chars_after)),
                                               coverage_rate=f"{90/len(chars_after):.4f}")
    metrics["Character Roster Coverage"].update(completed_count=str(report["catalogued_routes"]), target_count="NA",
                                                  coverage_rate="NA")
    coverage_temp = _temp_csv(paths["catalog_coverage_baseline.csv"], coverage_fields, list(metrics.values()))
    coverage_temp.replace(paths["catalog_coverage_baseline.csv"])
    return {"games_before": len(old_games), "games_written": len(new_games), "games_after": len(games_after),
            "characters_before": len(old_characters), "characters_written": len(new_characters),
            "characters_after": len(chars_after), "appearances_after": len(apps_after),
            "complete_roster_games": report["complete_roster_games"],
            "partial_roster_games": report["partial_roster_games"],
            "annotated": report["annotated_characters"], "not_annotated": len(chars_after)-report["annotated_characters"]}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(execute(root / "data"), ensure_ascii=False, indent=2))
