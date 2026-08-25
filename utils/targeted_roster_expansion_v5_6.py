"""AOMatch v5.6 targeted game/roster staging pipeline.

The module writes draft/QA artifacts only.  Formal catalog and XP tables are
opened read-only and are never mutated.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


def game(title, entry, series, parent, year, platform, developer, publisher,
         source, roster, status="AUTO_PASS", issue=""):
    return {"title": title, "entry_type": entry, "series_name": series,
            "parent_game_id": parent, "original_work_year": year,
            "original_platform": platform, "developer": developer,
            "publisher": publisher, "source_url": source, "roster": roster,
            "qa_status": status, "issue": issue}


SPECS = [
 game("Code:Realize ～祝福的未来～","fan_disc","Code:Realize","G004",2016,"PS Vita","Design Factory","Idea Factory","https://www.otomate.jp/code-realize/fd/",["@G004","Finis","Herlock Sholmes"],"REVIEW_REQUIRED","Finis/Sholmes 的 route_type 与本篇 identity 边界"),
 game("Code:Realize ～白银的奇迹～","fan_disc","Code:Realize","G004",2017,"PS Vita","Design Factory","Idea Factory","https://www.otomate.jp/code-realize/fd2/",["@G004","Finis","Herlock Sholmes"]),
 game("NORN9 LAST ERA","fan_disc","NORN9 命运九重奏","G044",2015,"PS Vita","Idea Factory","Idea Factory","https://www.otomate.jp/norn9/last-era/chara/",["@G044"]),
 game("BUSTAFELLOWS season2","sequel","BUSTAFELLOWS","G045",2023,"Switch","Nippon Cultural Broadcasting Extend","Extend","https://joqrextend.co.jp/extend/bustafellows2/character/",["@G045"]),
 game("冷然之天秤 黑百合炎阳谭","sequel","冷然之天秤","G013",2017,"PS Vita","Otomate","Idea Factory","https://www.otomate.jp/nil-admirari/fd/",["@G013","尾崎隼人","鴻上滉"],"REVIEW_REQUIRED","本篇缺角与续作 appearance 边界需确认"),
 game("大正×对称爱丽丝 all in one","collection","TAISHO x ALICE","G014",2015,"Switch","Primula","PROTOTYPE","https://www.prot.co.jp/switch/taishoalice/",["@G014","Kaguya","Gretel","Snow White","Wizard","Alice"]),
 game("Wand of Fortune R2","sequel","Wand of Fortune","G011",2011,"PS Vita","Design Factory","Idea Factory","https://www.otomate.jp/wandoffortune2/vita/",["@G011","Julius Fortner","Bilal Asad Ithnan Faranbald","Lagi El Nagil","Solo Monoe"],"REVIEW_REQUIRED","长名 romanization 与 R/R2 复用确认"),
 game("花合朔 Complete Collection","collection","花合朔","G024",2012,"Switch","WoGa","dramatic create","https://dramaticcreate.com/hanayaka/",["@G024","@G025","Karakurenai","Utsutsu","Iroha"],"REVIEW_REQUIRED","四篇合集的跨篇 identity/appearance 关系"),
 game("幻奏咖啡厅 Enchante","base_game","幻奏咖啡厅 Enchante","NA",2019,"Switch","Design Factory","Idea Factory","https://www.otomate.jp/enchante/",["Canus Espada","Ignis Carbunculus","Kaoru Rindo","Il Fado de Rie","Misyr Rex"]),
 game("Steam Prison","base_game","Steam Prison","NA",2016,"Windows","HuneX","dramatic create","https://www.hunex.co.jp/steamprison/",["Eltcreed Valentine","Ulrik Ferrie","Adage","Ines Heinrich Heine","Yune Sekiei","Fin Euclase"]),
 game("百花百狼 ～战国忍法帖～","base_game","Nightshade","NA",2016,"PS Vita","Red Entertainment","D3 Publisher","https://www.d3p.co.jp/hyakka/",["Gekkamaru","Kuroyuki","Chojiro Momochi","Goemon Ishikawa","Hanzo Hattori"]),
 game("Lover Pretend","base_game","Lover Pretend","NA",2021,"Switch","Design Factory","Idea Factory","https://www.otomate.jp/loverpretend/",["Kazuma Kamikubo","Harumi Makino","Riku Nishijima","Yukito Sena","Asagi"]),
 game("冬园 Sacrifice","base_game","Winter's Wish","NA",2022,"Switch","Design Factory","Idea Factory","https://www.otomate.jp/senwasa/",["Tomonari Takamura","Ohtaro","Kunitaka","Yoichi","Genjuro Kuga","Kinji"],"REVIEW_REQUIRED","官方日文名与英文 romanization 对齐"),
 game("BAD APPLE WARS","base_game","BAD APPLE WARS","NA",2015,"PS Vita","Design Factory","Idea Factory","https://www.otomate.jp/baw/",["Alma","Higa","Satoru","Shikishima","White Mask"]),
 game("BROTHERS CONFLICT Precious Baby","collection","BROTHERS CONFLICT","NA",2012,"PS Vita","Idea Factory","Idea Factory","https://www.otomate.jp/bc/precious_baby/",["Masaomi Asahina","Ukyo Asahina","Kaname Asahina","Hikaru Asahina","Tsubaki Asahina","Azusa Asahina","Natsume Asahina","Louis Asahina","Subaru Asahina","Iori Asahina","Yusuke Asahina","Futo Asahina","Wataru Asahina"]),
 game("DIABOLIK LOVERS GRAND EDITION","collection","DIABOLIK LOVERS","NA",2012,"Switch","Rejet","Idea Factory","https://www.otomate.jp/dialover/grand_edition/",["Ayato Sakamaki","Kanato Sakamaki","Laito Sakamaki","Shu Sakamaki","Reiji Sakamaki","Subaru Sakamaki","Ruki Mukami","Kou Mukami","Yuma Mukami","Azusa Mukami"]),
 game("安琪莉可 Luminarise","base_game","Angelique","NA",2021,"Switch","Ruby Party","Koei Tecmo","https://www.gamecity.ne.jp/anmina/",["Yue","Noah","Vergil","Kanata","Shuri","Milan","Xeno","Felix","Lorenzo"]),
 game("遥远时空中7","base_game","Harukanaru Toki no Naka de","NA",2020,"Switch","Ruby Party","Koei Tecmo","https://gw.gamecity.ne.jp/haruka7/chara.html",["真田幸村","天野五月","宮本武蔵","佐々木大和","黒田長政","直江兼続","阿国","柳生宗矩"],"REVIEW_REQUIRED","特殊读音/罗马字及八叶攻略身份快速确认"),
 game("心跳回忆 Girl's Side 4th Heart","base_game","Tokimeki Memorial Girl's Side","NA",2021,"Switch","Konami","Konami","https://www.konami.com/games/girls_side/4th_Heart/",["風真玲太","颯砂希","本多行","七ツ森実","柊夜ノ介","氷室一紀","御影小次郎","白羽大地","白羽空也","巴征道","大成功"],"REVIEW_REQUIRED","隐藏/特殊攻略路线资格需确认；御影先生按御影小次郎 alias 处理，不重复建人"),
 game("歌之王子殿下 Repeat LOVE","remake","Uta no Prince-sama","NA",2010,"PS Vita","Nippon Ichi Software","Broccoli","https://www.utapri.com/game/repeat_love/",["一十木音也","聖川真斗","四ノ宮那月","一ノ瀬トキヤ","神宮寺レン","来栖翔","愛島セシル"]),
]

DEFERRED = [
 ("C146","G042","Mylan","https://ifi.games/temirana/chara/"),
 ("C147","G042","Walt","https://ifi.games/temirana/chara/"),
 ("C148","G043","エリヤ","https://www.otomate.jp/honey_vibes/product/"),
 ("C149","G043","フィン","https://www.otomate.jp/honey_vibes/product/"),
 ("C150","G043","アルヴィン","https://www.otomate.jp/honey_vibes/product/"),
 ("C151","G043","イーノ","https://www.otomate.jp/honey_vibes/product/"),
 ("C152","G043","ミロ","https://www.otomate.jp/honey_vibes/product/"),
 ("C153","G043","テオ","https://www.otomate.jp/honey_vibes/product/"),
]


def _read(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build(data_dir: Path):
    games = _read(data_dir / "games_master.csv")
    chars = _read(data_dir / "characters_master.csv")
    apps = _read(data_dir / "character_game_appearances.csv")
    by_game = {}
    for row in apps: by_game.setdefault(row["game_id"], []).append(row["character_id"])
    next_cid = max(int(c["character_id"][1:]) for c in chars) + 1
    next_aid = max(int(a["appearance_id"][1:]) for a in apps) + 1
    next_sid = max(int(g["series_id"][1:]) for g in games) + 1
    series_ids = {g["series_name"]: g["series_id"] for g in games}
    draft_games=[]; draft_chars=[]; draft_apps=[]; exceptions=[]
    identity={}
    for offset,spec in enumerate(SPECS):
        gid=f"G{53+offset:03d}"
        sid=series_ids.get(spec["series_name"])
        if not sid:
            sid=f"S{next_sid:03d}"; next_sid+=1; series_ids[spec["series_name"]]=sid
        roster_ids=[]
        for item in spec["roster"]:
            if item.startswith("@"):
                roster_ids.extend(by_game[item[1:]]); continue
            key=item.casefold()
            if key not in identity:
                identity[key]=f"C{next_cid:03d}"; next_cid+=1
                draft_chars.append({"character_id":identity[key],"canonical_name":item,
                                    "xp_annotation_status":"not_annotated","spoiler_sensitive":False,
                                    "source_url":spec["source_url"]})
            roster_ids.append(identity[key])
        for cid in dict.fromkeys(roster_ids):
            draft_apps.append({"appearance_id":f"A{next_aid:04d}","character_id":cid,"game_id":gid,
                               "appearance_type":spec["entry_type"],"route_available":True,
                               "route_type":"main","spoiler_sensitive":False,"source_url":spec["source_url"]})
            next_aid+=1
        draft_games.append({k:v for k,v in spec.items() if k not in {"roster","issue"}} |
                           {"game_candidate_id":gid,"series_id":sid,"roster_character_ids":list(dict.fromkeys(roster_ids))})
        if spec["qa_status"] == "REVIEW_REQUIRED":
            exceptions.append({"game":spec["title"],"game_candidate_id":gid,"severity":"MEDIUM",
                               "exception_type":"IDENTITY_OR_ROUTE_REVIEW","reason":spec["issue"],
                               "suggested_action":"仅快速确认所列 identity/route 边界；其余数据可自动通过。"})
    # Deferred IDs were never written formally; preserve their stable IDs in staging.
    for cid,gid,name,source in DEFERRED:
        draft_chars.append({"character_id":cid,"canonical_name":name,"xp_annotation_status":"not_annotated",
                            "spoiler_sensitive":False,"source_url":source,"resolved_from_deferred":True})
        draft_apps.append({"appearance_id":f"A{next_aid:04d}","character_id":cid,"game_id":gid,
                           "appearance_type":"base_game","route_available":True,"route_type":"main",
                           "spoiler_sensitive":False,"source_url":source}); next_aid+=1
    counts=Counter(g["qa_status"] for g in draft_games)
    projected_publishers=Counter(g["publisher"] for g in games); projected_publishers.update(g["publisher"] for g in draft_games)
    draft={"batch_id":"targeted_roster_v5_6_batch_01","formal_counts_before":{"games":len(games),"characters":len(chars),"appearances":len(apps)},
           "games":draft_games,"new_characters":draft_chars,"appearances":draft_apps,"deferred_resolution":{"resolved":8,"still_deferred":0}}
    qa={"batch_id":draft["batch_id"],"status_counts":{"AUTO_PASS":counts["AUTO_PASS"],"REVIEW_REQUIRED":counts["REVIEW_REQUIRED"],"BLOCKED":0},
        "new_game_ids":len(draft_games),"reused_game_ids":0,"estimated_new_unique_characters":len(draft_chars),
        "estimated_new_appearances":len(draft_apps),"exceptions":exceptions,
        "projected":{"games":len(games)+len(draft_games),"characters":len(chars)+len(draft_chars),"appearances":len(apps)+len(draft_apps),"series":len(set(series_ids.values())),"publisher_distribution":dict(projected_publishers)},
        "final_write_executed":False}
    return draft,qa


def write_draft(data_dir: Path):
    draft,qa=build(data_dir); out=data_dir/"roster_expansion"; out.mkdir(exist_ok=True)
    for name,payload in (("targeted_roster_v5_6_batch_01_draft.json",draft),("targeted_roster_v5_6_batch_01_qa.json",qa)):
        (out/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return draft,qa


if __name__ == "__main__":
    root=Path(__file__).resolve().parents[1]
    print(json.dumps(write_draft(root/"data")[1],ensure_ascii=False,indent=2))
