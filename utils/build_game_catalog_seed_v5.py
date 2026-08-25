"""Build the compatibility mapping from legacy character game strings to game_id."""
from __future__ import annotations

import csv
from pathlib import Path

from utils.game_catalog_v5 import MAPPING_FIELDS

TITLE_TO_GAME_ID = {
    "9 R.I.P.": "G001",
    "AMNESIA": "G002", "AMNESIA: Memories": "G002",
    "CLOCK ZERO": "G003", "CLOCK ZERO ～终焉之一秒～": "G003",
    "Code:Realize": "G004", "Code:Realize ～创世的姬君～": "G004",
    "Collar×Malice": "G005", "Cupid Parasite": "G006", "Jack Jeanne": "G007",
    "OVER REQUIEMZ": "G008", "SympathyKiss": "G009", "SympathyKiss 共鸣之吻": "G009",
    "Variable Barricade": "G010", "百密一疏少女心": "G010",
    "Wand of Fortune R": "G011", "even if TEMPEST": "G012",
    "ニル・アドミラリの天秤": "G013", "冷然之天秤": "G013", "冷然之天秤 帝都幻惑绮谭": "G013",
    "大正对称爱丽丝 episode I": "G014", "天狱乱斗": "G015", "奥林匹亚的晚宴": "G016",
    "明治东京恋伽": "G017", "毘卢遮那战姬": "G018", "毘卢遮那战姬 ～源平飞花梦想～": "G018",
    "灾厄黑龙与谎言公主": "G019", "璃梦泡影之世外浮城": "G020", "第六妖守": "G021",
    "终远的威尔修": "G022", "绚烂传说马戏团": "G023",
    "花合朔 -姬空木篇-": "G024", "花合朔 -蛟篇-": "G025",
    "虔诚之花的晚钟": "G026", "蝶之毒 華之鎖": "G027",
}


def build_character_mapping(character_csv: Path, output_csv: Path) -> int:
    with character_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        characters = list(csv.DictReader(handle))
    missing = sorted({row["game"] for row in characters} - TITLE_TO_GAME_ID.keys())
    if missing:
        raise ValueError(f"Unmapped legacy game titles: {missing}")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MAPPING_FIELDS)
        writer.writeheader()
        for row in characters:
            writer.writerow({
                "character_id": row["character_id"],
                "game_id": TITLE_TO_GAME_ID[row["game"]],
                "source_game_title": row["game"],
            })
    return len(characters)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    count = build_character_mapping(
        root / "data" / "characters_v2_candidate.csv",
        root / "data" / "character_game_mapping.csv",
    )
    print(f"Wrote {count} character-to-game mappings")
