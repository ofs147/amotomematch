"""Read-only catalog coverage audit and gap-candidate generation."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

FIELDS = ("title", "series", "developer", "publisher", "entry_type",
          "original_release_year", "original_platform", "gap_reason",
          "suggested_priority", "estimated_roster_characters", "next_batch", "source_url")


def gap(title, series, developer, publisher, entry, year, platform, reason, priority, roster, source, plan=False):
    return dict(zip(FIELDS, (title, series, developer, publisher, entry, str(year), platform,
                             reason, priority, str(roster), str(plan).lower(), source)))


GAPS = [
    gap("Code:Realize ～祝福的未来～", "Code:Realize", "Design Factory", "Idea Factory", "fan_disc", 2016, "PS Vita", "已收录本篇但缺第一FD", "P0", 0, "https://www.otomate.jp/code-realize/fd/", True),
    gap("Code:Realize ～白银的奇迹～", "Code:Realize", "Design Factory", "Idea Factory", "fan_disc", 2017, "PS Vita", "重要系列缺第二FD", "P1", 0, "https://www.otomate.jp/code-realize/fd2/", True),
    gap("NORN9 LAST ERA", "NORN9", "Idea Factory", "Idea Factory", "fan_disc", 2015, "PS Vita", "已收录本篇但缺核心FD", "P0", 0, "https://www.otomate.jp/norn9/last-era/", True),
    gap("BUSTAFELLOWS season2", "BUSTAFELLOWS", "Extend", "Extend", "sequel", 2023, "Switch", "已收录本篇但缺独立续作", "P0", 5, "https://joqrextend.co.jp/extend/bustafellows2/", True),
    gap("冷然之天秤 黑百合炎阳谭", "冷然之天秤", "Otomate", "Idea Factory", "sequel", 2017, "PS Vita", "已收录本篇但缺续作", "P0", 1, "https://www.otomate.jp/nil-admirari/fd/", True),
    gap("大正×对称爱丽丝 all in one", "TAISHO x ALICE", "Primula", "PROTOTYPE", "collection", 2019, "Switch", "当前仅有episode I，缺其余主体内容", "P0", 5, "https://www.prot.co.jp/switch/taishoalice/", True),
    gap("Wand of Fortune R2", "Wand of Fortune", "Design Factory", "Idea Factory", "sequel", 2017, "PS Vita", "已收录R但缺R2", "P1", 2, "https://www.otomate.jp/wandoffortune2/vita/", True),
    gap("花合朔 Complete Collection", "花合朔", "WoGa", "dramatic create", "collection", 2023, "Switch", "当前只收录两篇，缺完整四篇结构", "P1", 3, "https://dramaticcreate.com/hanayaka/", True),
    gap("幻奏咖啡厅Enchante", "幻奏咖啡厅Enchante", "Design Factory", "Idea Factory", "base_game", 2019, "Switch", "高认知度Otomate作品完全缺失", "P0", 5, "https://www.otomate.jp/enchante/", True),
    gap("Steam Prison", "Steam Prison", "HuneX", "dramatic create", "base_game", 2016, "Windows", "补PC/HuneX及全球长尾覆盖", "P0", 6, "https://www.hunex.co.jp/steamprison/", True),
    gap("百花百狼 ～战国忍法帖～", "Nightshade", "Red Entertainment", "D3 Publisher", "base_game", 2016, "PS Vita", "D3 Publisher代表作缺失", "P0", 5, "https://www.d3p.co.jp/hyakka/", True),
    gap("Lover Pretend", "Lover Pretend", "Design Factory", "Idea Factory", "base_game", 2021, "Switch", "现代题材覆盖不足", "P1", 5, "https://www.otomate.jp/loverpretend/", True),
    gap("Paradigm Paradox", "Paradigm Paradox", "Design Factory", "Idea Factory", "base_game", 2021, "Switch", "科幻/变身题材缺口", "P1", 8, "https://www.otomate.jp/paradigm_paradox/", False),
    gap("冬园Sacrifice", "Winter's Wish", "Design Factory", "Idea Factory", "base_game", 2022, "Switch", "近年和风新系列缺口", "P1", 6, "https://www.otomate.jp/senwasa/", True),
    gap("BAD APPLE WARS", "BAD APPLE WARS", "Design Factory", "Idea Factory", "base_game", 2015, "PS Vita", "Vita时期代表作缺失", "P1", 5, "https://www.otomate.jp/baw/", True),
    gap("BROTHERS CONFLICT Precious Baby", "BROTHERS CONFLICT", "Idea Factory", "Idea Factory", "collection", 2017, "PS Vita", "高认知度多路线经典系列完全缺失", "P0", 13, "https://www.otomate.jp/bc/precious_baby/", True),
    gap("DIABOLIK LOVERS GRAND EDITION", "DIABOLIK LOVERS", "Rejet", "Idea Factory", "collection", 2018, "Switch", "Rejet代表系列与极端关系类型缺失", "P0", 10, "https://www.otomate.jp/dialover/grand_edition/", True),
    gap("安琪莉可 Luminarise", "Angelique", "Ruby Party", "Koei Tecmo", "base_game", 2021, "Switch", "Neo Romance核心IP完全缺失", "P0", 9, "https://www.gamecity.ne.jp/anmina/", True),
    gap("遥远时空中7", "Harukanaru Toki no Naka de", "Ruby Party", "Koei Tecmo", "base_game", 2020, "Switch", "Neo Romance核心系列完全缺失", "P0", 8, "https://www.gamecity.ne.jp/haruka7/", True),
    gap("金色琴弦 Octave", "La Corda d'Oro", "Ruby Party", "Koei Tecmo", "base_game", 2019, "Switch", "音乐育成/Neo Romance厂牌缺失", "P1", 12, "https://www.gamecity.ne.jp/corda-octave/", False),
    gap("心跳回忆 Girl's Side 4th Heart", "Tokimeki Memorial Girl's Side", "Konami", "Konami", "base_game", 2021, "Switch", "Konami与养成型乙女核心缺口", "P0", 12, "https://www.konami.com/games/girls_side/4th_Heart/", True),
    gap("歌之王子殿下 Repeat LOVE", "Uta no Prince-sama", "Nippon Ichi Software", "Broccoli", "remake", 2017, "PS Vita", "Broccoli代表系列完全缺失", "P0", 7, "https://www.utapri.com/game/repeat_love/", True),
    gap("绯色的欠片 ～回忆之色～", "Hiiro no Kakera", "Design Factory", "Idea Factory", "remake", 2025, "Switch", "早期Otomate核心IP及2025作品缺失", "P1", 5, "https://www.otomate.jp/hiiro/switch/", False),
    gap("苍黑之楔 ～绯色的欠片～", "Hiiro no Kakera", "Design Factory", "Idea Factory", "sequel", 2025, "Switch", "绯色系列续作及2025时间段缺失", "P1", 6, "https://www.otomate.jp/hiiro_soukoku/switch/", False),
    gap("猛兽使与王子殿下 ～Flower & Snow～", "Beastmaster and Princes", "Design Factory", "Idea Factory", "collection", 2015, "PS Vita", "Otomate经典幻想系列缺失", "P2", 6, "https://www.otomate.jp/moujuutsukai/vita/", False),
    gap("Dance with Devils", "Dance with Devils", "Rejet", "Rejet", "base_game", 2016, "PS Vita", "Rejet作品覆盖不足", "P1", 6, "https://rejetweb.jp/dwd/game/", False),
    gap("Dance with Devils My Carol", "Dance with Devils", "Rejet", "Rejet", "fan_disc", 2018, "PS Vita", "缺本篇配套FD", "P2", 0, "https://rejetweb.jp/dwd/mycarol/", False),
    gap("Sweet Clown ～午前三时的点心师～", "Sweet Clown", "Takuyo", "Takuyo", "base_game", 2015, "PS Vita", "Takuyo厂牌完全缺失", "P2", 5, "https://www.takuyo.co.jp/products/sweetclown/", False),
    gap("Un:BIRTHDAY SONG", "honeybee Re:Un Birthday Song", "honeybee", "Asgard", "base_game", 2015, "Windows", "补PC/honeybee覆盖", "P2", 3, "https://www.honeybee-cd.com/re_birth_un_birth/", False),
    gap("Re:BIRTHDAY SONG", "honeybee Re:Un Birthday Song", "honeybee", "Asgard", "base_game", 2015, "Windows", "补PC/honeybee系列另一主体", "P2", 4, "https://www.honeybee-cd.com/re_birth_un_birth/", False),
    gap("白与黑的爱丽丝", "Shiro to Kuro no Alice", "Design Factory", "Idea Factory", "base_game", 2017, "PS Vita", "Alice系幻想题材仍有缺口", "P1", 5, "https://www.otomate.jp/bw_alice/", False),
    gap("DesperaDrops", "DesperaDrops", "Red Entertainment", "D3 Publisher", "base_game", 2023, "Switch", "补D3与公路逃亡题材", "P1", 6, "https://www.d3p.co.jp/desperadrops/", False),
    gap("My9Swallows TOPSTARS LEAGUE", "My9Swallows", "Design Factory", "Idea Factory", "base_game", 2024, "Switch", "运动题材覆盖不足", "P2", 9, "https://www.otomate.jp/my9swallows/", False),
    gap("茉莉花之炯 天命华烛传", "茉莉花之炯", "Idea Factory", "Idea Factory", "fan_disc", 2026, "Switch", "当前系列缺最新FD并补2025+", "P1", 2, "https://www.otomate.jp/mk/fd/", False),
]

INCOMPLETE_SERIES = {"AMNESIA", "BUSTAFELLOWS", "Code:Realize", "NORN9 命运九重奏",
                     "TAISHO x ALICE", "Wand of Fortune", "冷然之天秤", "花合朔", "薄樱鬼 真改"}


def _read(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def audit(data_dir: Path):
    games = _read(data_dir / "games_master.csv")
    characters = _read(data_dir / "characters_master.csv")
    appearances = _read(data_dir / "character_game_appearances.csv")
    years = Counter()
    for game in games:
        raw = game["original_release_date"][:4]
        if not raw.isdigit(): years["unknown"] += 1; continue
        year = int(raw)
        years["≤2010" if year <= 2010 else "2011–2015" if year <= 2015 else "2016–2020" if year <= 2020 else "2021–2024" if year <= 2024 else "2025+"] += 1
    roster = Counter(a["game_id"] for a in appearances if a["route_available"] == "true")
    partial = []
    for game in games:
        expected = game["route_count"]
        actual = roster[game["game_id"]]
        if expected == "NA" or actual != int(expected):
            if game["game_id"] == "G042": category = "A_deferred_character"
            elif game["game_id"] == "G043": category = "D_source_extraction"
            elif expected == "NA": category = "B_route_count_unknown"
            else: category = "C_hidden_or_missing_route"
            partial.append({"game_id": game["game_id"], "title": game["title_zh"], "category": category,
                            "expected": expected, "catalogued": actual})
    series = {g["series_name"] for g in games}
    incomplete = series & INCOMPLETE_SERIES
    report = {
        "game_count": len(games), "series_count": len({g["series_id"] for g in games}),
        "complete_series_count": len(series - incomplete), "incomplete_series_count": len(incomplete),
        "developer_distribution": dict(Counter(g["developer"] for g in games)),
        "publisher_distribution": dict(Counter(g["publisher"] for g in games)),
        "platform_distribution": dict(Counter(g["original_platform"] for g in games)),
        "year_distribution": dict(years), "entry_type_distribution": dict(Counter(g["entry_type"] for g in games)),
        "roster_size_by_game": {g["game_id"]: roster[g["game_id"]] for g in games},
        "partial_games": partial, "roster_characters": len(characters),
        "xp_annotated": sum(c["xp_annotation_status"] != "not_annotated" for c in characters),
        "next_batch_games": sum(row["next_batch"] == "true" for row in GAPS),
        "next_batch_estimated_characters": sum(int(row["estimated_roster_characters"]) for row in GAPS if row["next_batch"] == "true"),
    }
    return report


def write_audit(data_dir: Path):
    with (data_dir / "catalog_gap_candidates.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(GAPS)
    report = audit(data_dir)
    (data_dir / "catalog_coverage_audit_v5_5.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(write_audit(root / "data"), ensure_ascii=False, indent=2))
