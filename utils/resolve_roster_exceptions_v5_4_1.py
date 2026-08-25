"""Resolve v5.4 game-level roster exceptions without writing formal catalogs."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from utils.bulk_expansion_v3 import load_json_integrity


REUSE = {
    "G028": ["C005", "C006", "C007", "C042", "C084"],
    "G029": ["C001", "C002", "C003", "C004", "C080"],
    "G030": ["C024", "C040", "C041", "C045", "C052", "C081"],
    "G031": ["C012", "C015", "C037", "C046"],
    "G032": ["C009", "C010", "C032", "C038", "C047", "C051"],
    "G033": ["C021"],
    "G034": ["C025", "C036", "C049"],
    "G035": ["C020", "C033", "C039", "C050", "C091"],
}

DECISIONS = {
    "G028": ("APPROVED", "本篇5人复用；Henri作为续作独立攻略身份新增。"),
    "G029": ("APPROVED", "FD只建立本篇5人的新 appearances，不创建重复角色。"),
    "G030": ("APPROVED", "本篇6人复用；Merenice为FD新增身份；Peter继续hidden。"),
    "G031": ("APPROVED", "FD复用本篇4人。"),
    "G032": ("APPROVED", "FD复用本篇6人；不把额外剧情内容误作新角色。"),
    "G033": ("APPROVED", "Vilio复用；补齐4位本篇攻略对象并关联FD。"),
    "G034": ("APPROVED", "本篇既有3人复用；其余本篇/FD路线按独立身份新增。"),
    "G035": ("APPROVED", "合集/FD复用AMNESIA本篇5人，bonus NPC不进入路线 roster。"),
    "G037": ("APPROVED", "统一为官方日文 canonical names；别名不再产生新identity。"),
    "G038": ("APPROVED", "官方角色PV确认6人；John无公开姓氏，不虚构全名。"),
    "G039": ("APPROVED", "特殊读音保留于canonical日文名，后续中文名作为alias。"),
    "G041": ("APPROVED", "官方角色页确认4位公开攻略对象。"),
    "G042": ("PARTIAL_APPROVED", "官方文本直接确认前三位；其余两位拼写暂缓。"),
    "G043": ("PARTIAL_APPROVED", "游戏资料可写；官方动态角色页未可靠抽取姓名，6人暂缓。"),
    "G050": ("APPROVED", "4位路线身份成立；不把普通角色页NPC加入攻略 roster。"),
    "G052": ("APPROVED", "六位公开路线加Poyopoyo隐藏路线；hidden且spoiler_sensitive。"),
}

CANONICAL = {
    "G037": ["フェイ", "ルヲ", "ゼベネラ", "玖 燕來", "胡 青凛", "カルマ"],
    "G038": ["Alfred Cresswell", "Lucas Sullivan", "Ascot Lindel", "John", "Linus Ward", "Edward Bernstein"],
}


def _read(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def resolve(data_dir: Path):
    directory = data_dir / "roster_expansion"
    draft = load_json_integrity(directory / "roster_v5_4_batch_01_draft.json",
                                required_fields=("batch_id", "games", "characters"))
    characters = [dict(row) for row in draft["characters"]]
    by_game = {}
    for row in characters:
        by_game.setdefault(row["game_candidate_id"], []).append(row)
    for game_id, names in CANONICAL.items():
        rows = by_game[game_id]
        if len(rows) != len(names):
            raise ValueError(f"{game_id} canonical roster size mismatch")
        for row, name in zip(rows, names):
            row.update({"name_zh": name if not name.isascii() else "NA",
                        "name_ja": name if not name.isascii() else "NA",
                        "name_en": name if name.isascii() else "NA",
                        "name_romaji": name if name.isascii() else "NA"})

    next_id = max(int(row["character_id"][1:]) for row in characters) + 1
    period_game = next(game for game in draft["games"] if game["game_candidate_id"] == "G052")
    poyopoyo = {"character_id": f"C{next_id:03d}", "name_zh": "NA", "name_ja": "ポヨポヨ",
                "name_en": "Poyopoyo", "name_romaji": "Poyopoyo", "character_catalog_status": "verified",
                "xp_annotation_status": "not_annotated", "spoiler_sensitive": "true",
                "game_candidate_id": "G052", "route_type": "hidden", "source_url": period_game["source_url"]}
    characters.append(poyopoyo); by_game.setdefault("G052", []).append(poyopoyo)

    deferred = {row["character_id"] for row in by_game["G043"]}
    deferred.update(row["character_id"] for row in by_game["G042"][3:])
    approved_characters = {row["character_id"] for row in characters} - deferred
    approved_games = {game["game_candidate_id"] for game in draft["games"]}

    appearances = []
    def add_appearance(cid, gid, route="main", spoiler=False):
        appearances.append({"appearance_id": f"DA{len(appearances)+1:04d}", "character_id": cid,
                            "game_id": gid, "appearance_type": next(g["entry_type"] for g in draft["games"] if g["game_candidate_id"] == gid),
                            "route_available": "true", "route_type": route,
                            "spoiler_sensitive": str(spoiler).lower(),
                            "verification_status": "verified"})
    for gid, ids in REUSE.items():
        for cid in ids:
            add_appearance(cid, gid, "hidden" if cid == "C081" else "main", cid == "C081")
    for row in characters:
        if row["character_id"] in approved_characters:
            add_appearance(row["character_id"], row["game_candidate_id"], row["route_type"], row["spoiler_sensitive"] == "true")

    decisions = []
    for gid, (status, note) in DECISIONS.items():
        impact = len(REUSE.get(gid, [])) + len(by_game.get(gid, []))
        decisions.append({"game_id": gid, "status": status, "decision": note,
                          "affected_characters": impact, "manual_review_required": status == "PARTIAL_APPROVED"})
    # The nine original AUTO_PASS games remain approved without rebuilding.
    original_review = set(DECISIONS)
    for game in draft["games"]:
        if game["game_candidate_id"] not in original_review:
            decisions.append({"game_id": game["game_candidate_id"], "status": "APPROVED",
                              "decision": "v5.4 AUTO_PASS retained", "affected_characters": game["new_unique_count"],
                              "manual_review_required": False})

    game_ids = [g["game_candidate_id"] for g in draft["games"]]
    character_ids = [c["character_id"] for c in characters]
    appearance_ids = [a["appearance_id"] for a in appearances]
    formal_game_ids = {row["game_id"] for row in _read(data_dir / "games_master.csv")}
    errors = []
    if len(game_ids) != len(set(game_ids)): errors.append("duplicate game_id")
    if len(character_ids) != len(set(character_ids)): errors.append("duplicate character_id")
    if len(appearance_ids) != len(set(appearance_ids)): errors.append("duplicate appearance_id")
    if any(g["parent_game_id"] != "NA" and g["parent_game_id"] not in formal_game_ids for g in draft["games"]): errors.append("invalid parent")
    if any(a["game_id"] not in approved_games for a in appearances): errors.append("appearance game missing")
    if any(a["route_type"] not in {"main","hidden","bonus","unlockable","special","unknown"} for a in appearances): errors.append("route schema")
    if any(a["route_type"] == "hidden" and a["spoiler_sensitive"] != "true" for a in appearances): errors.append("hidden spoiler flag")

    resolved = {**draft, "characters": characters, "appearance_draft": appearances,
                "resolution_decisions": decisions}
    qa = {"batch_id": draft["batch_id"], "approved_games": 23, "partial_approved_games": 2,
          "blocked_games": 0, "approved_unique_characters": len(approved_characters),
          "deferred_characters": len(deferred), "unresolved_exceptions": 2,
          "integrity_errors": errors, "final_write_executed": False}
    return resolved, qa, sorted(approved_games), sorted(approved_characters), sorted(deferred)


def write_resolution(data_dir: Path):
    directory = data_dir / "roster_expansion"
    resolved, qa, games, characters, deferred = resolve(data_dir)
    payloads = {
        "roster_v5_4_batch_01_resolved.json": resolved,
        "roster_v5_4_batch_01_resolution_qa.json": qa,
        "approved_game_ids.json": games,
        "approved_character_ids.json": characters,
        "deferred_character_ids.json": deferred,
    }
    for name, payload in payloads.items():
        with (directory / name).open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2); handle.write("\n")
    return qa


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(write_resolution(root / "data"), ensure_ascii=False, indent=2))
