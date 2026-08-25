"""AOMatch v5.4 game-first catalog/roster expansion draft.

This module only creates staging JSON.  It never mutates the formal game,
character, appearance, or XP tables.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


def _spec(title, ja, en, source, roster, *, status="AUTO_PASS", issue="", entry="base_game", parent="NA"):
    return {"title_zh": title, "title_ja": ja, "title_en": en, "source_url": source,
            "roster": roster, "qa_status": status, "issue": issue,
            "entry_type": entry, "parent_game_id": parent}


GAME_SPECS = [
    _spec("虔诚之花的晚钟 -Episodio1926-", "ピオフィオーレの晩鐘 -Episodio1926-", "Piofiore: Episodio 1926", "https://www.otomate.jp/piofiore/1926/", ["Henri Lambert"], status="REVIEW_REQUIRED", issue="FD roster与本篇身份复用需确认", entry="sequel", parent="G026"),
    _spec("Collar×Malice -Unlimited-", "Collar×Malice -Unlimited-", "Collar X Malice -Unlimited-", "https://www.otomate.jp/collar_malice/fd/", [], status="REVIEW_REQUIRED", issue="FD需建立对本篇5人的复用 appearances", entry="fan_disc", parent="G005"),
    _spec("共生丘比特 -Sweet & Spicy Darling.-", "キューピット・パラサイト -Sweet & Spicy Darling.-", "Cupid Parasite: Sweet and Spicy Darling", "https://www.otomate.jp/cp/fd/", ["Merenice Levin"], status="REVIEW_REQUIRED", issue="新增攻略角色与本篇隐藏角色复用边界", entry="fan_disc", parent="G006"),
    _spec("even if TEMPEST 连缀之时的拂晓", "even if TEMPEST 連綴せし時の暁", "even if TEMPEST: Dawning Connections", "https://products.voltage.co.jp/tempest/fd/", [], status="REVIEW_REQUIRED", issue="FD需建立对本篇4人的复用 appearances", entry="fan_disc", parent="G012"),
    _spec("终远的威尔修 -EpiC:lycoris-", "終遠のヴィルシュ -EpiC:lycoris-", "Virche Evermore: EpiC Lycoris", "https://www.otomate.jp/virche/fd/", [], status="REVIEW_REQUIRED", issue="FD需建立对本篇角色的复用 appearances 并确认特殊路线", entry="fan_disc", parent="G022"),
    _spec("绚烂传说马戏团 -A Fanfare!-", "ラディアンテイル ～ファンファーレ！～", "Radiant Tale: Fanfare", "https://www.otomate.jp/radiant_tale/fd/", ["Zafora", "Paschalia", "Ion", "Radie"], status="REVIEW_REQUIRED", issue="应先补齐本篇G023，再复用至FD", entry="fan_disc", parent="G023"),
    _spec("毘卢遮那战姬 ～一树之风～", "ビルシャナ戦姫 ～一樹の風～", "Birushana: Winds of Fate", "https://www.otomate.jp/birushana/fd/", ["Noritsune Taira", "Benkei Musashibo", "Shungen", "Yoritomo Minamoto", "Tadanobu Sato", "Tsugunobu Sato", "Shigehira Taira", "Takatsuna Sasaki"], status="REVIEW_REQUIRED", issue="本篇缺角与FD追加路线需拆分复用", entry="fan_disc", parent="G018"),
    _spec("失忆症 LATER×CROWD", "AMNESIA LATER×CROWD", "Amnesia: Later x Crowd", "https://www.otomate.jp/amnesia/later_crowd/", [], status="REVIEW_REQUIRED", issue="FD需复用本篇5人并确认bonus内容不误作正式路线", entry="fan_disc", parent="G002"),
    _spec("CharadeManiacs", "シャレードマニアクス", "Charade Maniacs", "https://www.otomate.jp/smp/charade_maniacs/chara.php", ["明瀬京也", "萬城朋世", "茅ヶ裂守", "陀宰明", "獲端圭", "双巳良一", "凝部奏汰", "廃寺拓海", "射落水樹"]),
    _spec("茉莉花之炯 天命胤异传", "マツリカの炯-kEi- 天命胤異伝", "Matsurika no Kei", "https://www.otomate.jp/mk/chara/fey.php", ["フェイ", "ルヲ", "ゼベネラ", "燕來", "白玖", "胡青凛"], status="REVIEW_REQUIRED", issue="中文/罗马字别名需统一"),
    _spec("米斯托尼亚的翅望", "ミストニアの翅望 -The Lost Delight-", "Mistonia's Hope: The Lost Delight", "https://www.otomate.jp/mistonia/chara/alfred.php", ["Alfred Cresswell", "Lucas Sullivan", "Ascot Lindström", "John", "Linus Ward", "Edward"] ,status="REVIEW_REQUIRED", issue="John/Edward全名及攻略身份需官方页逐项确认"),
    _spec("Cendrillon palikA", "Cendrillon palikA", "Cendrillon palikA", "https://www.otomate.jp/cendrillon_palika/chara/", ["紫鳶", "憂漣", "廻螺", "黒禰", "綸燈", "泣虎", "歌紫歌"], status="REVIEW_REQUIRED", issue="特殊读音与罗马字 alias 需确认"),
    _spec("十三支演义 偃月三国传 1・2", "十三支演義 偃月三国伝1・2", "Juuzaengi: Engetsu Sangokuden 1・2", "https://www.otomate.jp/jyuzaengi/switch/", ["劉備", "張飛", "趙雲", "曹操", "夏侯惇", "張遼"]),
    _spec("如果世界上有神明存在的话", "もし、この世界に神様がいるとするならば。", "MoshiKami", "https://rejetweb.jp/moshikami/", ["細波エース", "弓倉ネジ", "神里キョウ", "指乃シュリ"], status="REVIEW_REQUIRED", issue="官方站旧页面的完整攻略身份需复核"),
    _spec("提米拉纳国的好运公主与悲运骑士团", "テミラーナ国の強運姫と悲運騎士団", "Temirana: The Lucky Princess", "https://www.otomate.jp/tsuitsui/chara/", ["Josef", "Adel", "Tobias", "Mylan", "Walt"] ,status="REVIEW_REQUIRED", issue="英文/罗马字官方拼写待核"),
    _spec("Honey Vibes", "Honey Vibes", "Honey Vibes", "https://www.otomate.jp/honey_vibes/chara/", ["Elvin", "Finn", "Albie", "Mew", "Theo", "Liam"], status="REVIEW_REQUIRED", issue="官方罗马字与完整路线数待核"),
    _spec("NORN9 命运九重奏", "NORN9 ノルン＋ノネット", "NORN9 Var Commons", "https://www.otomate.jp/smp/norn9/le/chara.php", ["結賀駆", "市ノ瀬千里", "遠矢正宗", "吾妻夏彦", "二条朔也", "加賀見一月", "宿吏暁人", "室星ロン", "乙丸平士"]),
    _spec("BUSTAFELLOWS", "BUSTAFELLOWS", "BUSTAFELLOWS", "https://joqrextend.co.jp/extend/bustafellows/character/", ["Limbo Fitzgerald", "Shu", "Helvetica", "Mozu", "Scarecrow"]),
    _spec("剑为君舞", "剣が君 for S", "Ken ga Kimi for S", "https://rejetweb.jp/kengakimi/switch/character/", ["九十九丸", "螢", "黒羽実彰", "縁", "鷺原左京", "鈴懸"]),
    _spec("薄樱鬼 真改", "薄桜鬼 真改", "Hakuoki: Kyoto Winds / Edo Blossoms", "https://www.otomate.jp/hakuoki/shinkai/", ["土方歳三", "沖田総司", "斎藤一", "藤堂平助", "原田左之助", "風間千景", "永倉新八", "山南敬助", "山崎烝", "伊庭八郎", "相馬主計", "坂本龍馬"]),
    _spec("7'scarlet", "7'scarlet", "7'scarlet", "https://www.otomate.jp/7scarlet/chara/", ["迦具土ヒノ", "甘梨イソラ", "櫛奈雫トア", "建比良ソウスケ", "叢雲ユヅキ"]),
    _spec("黑蝶幻境", "黒蝶のサイケデリカ", "Psychedelica of the Black Butterfly", "https://www.otomate.jp/psychedelica/chara/", ["緋影", "鴉翅", "山都", "紋白", "鉤翅"]),
    _spec("灰鹰幻境", "灰鷹のサイケデリカ", "Psychedelica of the Ashen Hawk", "https://www.otomate.jp/psychedelica-aa/chara/", ["ラヴァン", "レビ", "ルーガス", "ヒュー"] ,status="REVIEW_REQUIRED", issue="特殊/解锁路线边界需确认"),
    _spec("KLAP!!", "KLAP!! ～Kind Love And Punish～", "KLAP!! Kind Love And Punish", "https://www.otomate.jp/klap/chara/", ["美作燈真", "周防壮介", "駿河明人", "カミル＝セッツェリン", "播磨奏", "出雲紫苑"]),
    _spec("Period Cube ～鸟笼的阿玛迪斯～", "ピリオドキューブ ～鳥籠のアマデウス～", "Period Cube: Shackles of Amadeus", "https://www.otomate.jp/period-cube/chara/", ["ヒロヤ", "ラディウス", "リベラ", "アストラム", "ザイン", "ディメント"], status="REVIEW_REQUIRED", issue="隐藏/特殊路线及route_type需确认"),
]

# Product facts are kept separate from roster identity review. Dates/platforms
# refer to the named Japanese release/edition in this batch.
PRODUCT_META = {
    "虔诚之花的晚钟 -Episodio1926-": ("Design Factory", "Idea Factory", "2020-11-12", "Switch"),
    "Collar×Malice -Unlimited-": ("Design Factory", "Idea Factory", "2018-07-26", "PS Vita"),
    "共生丘比特 -Sweet & Spicy Darling.-": ("Idea Factory", "Idea Factory", "2023-11-30", "Switch"),
    "even if TEMPEST 连缀之时的拂晓": ("Voltage", "Voltage", "2023-08-03", "Switch"),
    "终远的威尔修 -EpiC:lycoris-": ("Idea Factory", "Idea Factory", "2023-09-07", "Switch"),
    "绚烂传说马戏团 -A Fanfare!-": ("Design Factory", "Idea Factory", "2023-08-31", "Switch"),
    "毘卢遮那战姬 ～一树之风～": ("Red Entertainment", "Idea Factory", "2022-03-31", "Switch"),
    "失忆症 LATER×CROWD": ("Design Factory", "Idea Factory", "2019-10-03", "Switch"),
    "CharadeManiacs": ("Idea Factory", "Idea Factory", "2018-08-09", "PS Vita"),
    "茉莉花之炯 天命胤异传": ("Idea Factory", "Idea Factory", "2024-02-29", "Switch"),
    "米斯托尼亚的翅望": ("Design Factory", "Idea Factory", "2024-07-18", "Switch"),
    "Cendrillon palikA": ("Design Factory", "Idea Factory", "2018-10-25", "PS Vita"),
    "十三支演义 偃月三国传 1・2": ("Red Entertainment", "Idea Factory", "2022-09-22", "Switch"),
    "如果世界上有神明存在的话": ("Rejet", "Rejet", "2016-02-25", "PS Vita"),
    "提米拉纳国的好运公主与悲运骑士团": ("Design Factory", "Idea Factory", "2023-04-27", "Switch"),
    "Honey Vibes": ("Idea Factory", "Idea Factory", "2024-10-03", "Switch"),
    "NORN9 命运九重奏": ("Idea Factory", "Idea Factory", "2013-05-23", "PSP"),
    "BUSTAFELLOWS": ("Nippon Cultural Broadcasting Extend", "Extend", "2019-12-19", "Switch"),
    "剑为君舞": ("Rejet", "Rejet", "2013-12-19", "Windows"),
    "薄樱鬼 真改": ("Design Factory", "Idea Factory", "2015-09-25", "PS Vita"),
    "7'scarlet": ("Toybox", "Idea Factory", "2016-07-21", "PS Vita"),
    "黑蝶幻境": ("Otomate", "Idea Factory", "2015-01-29", "PS Vita"),
    "灰鹰幻境": ("Otomate", "Idea Factory", "2016-09-29", "PS Vita"),
    "KLAP!!": ("Design Factory", "Idea Factory", "2015-07-30", "PS Vita"),
    "Period Cube ～鸟笼的阿玛迪斯～": ("Design Factory", "Idea Factory", "2016-05-19", "PS Vita"),
}


def build_v5_4_draft(data_dir: Path) -> tuple[dict, dict]:
    with (data_dir / "characters_master.csv").open(encoding="utf-8-sig", newline="") as f:
        existing = list(csv.DictReader(f))
    existing_names = {value.strip().casefold() for row in existing for key, value in row.items()
                      if key.startswith("name_") and value and value != "NA"}
    next_id = max(int(row["character_id"][1:]) for row in existing) + 1
    games, characters, exceptions = [], [], []
    for offset, spec in enumerate(GAME_SPECS):
        game_id = f"G{28 + offset:03d}"
        new_names = []
        for name in spec["roster"]:
            if name.casefold() in existing_names:
                continue
            cid = f"C{next_id:03d}"; next_id += 1
            new_names.append(name)
            characters.append({"character_id": cid, "name_zh": name if any(ord(c) > 127 for c in name) else "NA",
                               "name_ja": name if any(ord(c) > 127 for c in name) else "NA",
                               "name_en": name if name.isascii() else "NA", "name_romaji": name if name.isascii() else "NA",
                               "character_catalog_status": "verified" if spec["qa_status"] == "AUTO_PASS" else "candidate",
                               "xp_annotation_status": "not_annotated", "spoiler_sensitive": "false",
                               "game_candidate_id": game_id, "route_type": "main", "source_url": spec["source_url"]})
        game = {k: v for k, v in spec.items() if k != "roster"}
        developer, publisher, release_date, platform = PRODUCT_META[spec["title_zh"]]
        game.update({"game_candidate_id": game_id, "catalog_status": "verified" if spec["qa_status"] == "AUTO_PASS" else "needs_review",
                     "expected_route_count": len(spec["roster"]), "new_unique_count": len(new_names),
                     "developer": developer, "publisher": publisher,
                     "original_release_date": release_date, "original_platform": platform})
        games.append(game)
        if spec["qa_status"] != "AUTO_PASS":
            exceptions.append({"game_candidate_id": game_id, "game": spec["title_zh"], "severity": "MEDIUM",
                               "exception_type": "ROSTER_OR_IDENTITY_REVIEW", "reason": spec["issue"],
                               "suggested_action": "按官方角色页批量核对 alias、route_type 与复用 identity。"})
    status_counts = Counter(g["qa_status"] for g in games)
    draft = {"batch_id": "roster_v5_4_batch_01", "formal_games_before": 27, "formal_characters_before": len(existing),
             "games": games, "characters": characters}
    qa = {"batch_id": draft["batch_id"], "game_count": len(games), "new_unique_characters": len(characters),
          "status_counts": dict(status_counts), "exceptions": exceptions, "final_write_executed": False}
    return draft, qa


def write_draft(data_dir: Path):
    draft, qa = build_v5_4_draft(data_dir)
    out = data_dir / "roster_expansion"; out.mkdir(parents=True, exist_ok=True)
    for name, payload in (("roster_v5_4_batch_01_draft.json", draft), ("roster_v5_4_batch_01_qa.json", qa)):
        with (out / name).open("w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2); f.write("\n")
    return draft, qa


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    _, report = write_draft(root / "data")
    print(json.dumps(report, ensure_ascii=False, indent=2))
