"""Read-only XP annotation priority selection for the 316-character roster."""
from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from utils.schema import NUMERIC_FEATURES

FIELDS=("character_id","character_name","game","series","developer_publisher","priority_score",
        "coverage_gap","series_diversity_value","source_readiness","suggested_tier")

TARGET_PUBLISHERS={"Ruby Party","Koei Tecmo","Konami","Broccoli","HuneX","dramatic create","D3 Publisher","Extend"}
FAMILIAR_GAMES={"G028","G030","G033","G034","G037","G038","G039","G040","G041","G042",
                "G043","G044","G046","G047","G053","G054","G055","G057","G058","G059",
                "G060","G068","G071"}

GAP_BY_GAME={
 "G053":"special-route关系体验 / gap_moe边界","G054":"关系延续型 / 中等initiative",
 "G055":"多主人公关系差异 / 平衡型","G056":"理性投入 / 高独立 / 低占有",
 "G057":"成熟平衡型 / 中等devotion","G058":"多原型差异 / LOOK两端",
 "G059":"成长型 / 低personality_maturity","G060":"高control / 高possessiveness稀缺区",
 "G061":"非传统守护者 / mystery与LOOK差异","G062":"高danger / 高control稀缺区",
 "G063":"低情绪表达 / 稳定型","G064":"低关系浓度 / 平衡型",
 "G065":"initiative差异 / 解锁型关系","G066":"成长型 / 低personality_maturity",
 "G067":"成长型 / 低中devotion / LOOK年龄差","G068":"高control / possessiveness / jealousy",
 "G069":"低占有 / 低嫉妒 / 理性投入","G070":"中等devotion / 平衡关系",
 "G071":"低danger / 低关系浓度 / 高独立","G072":"initiative与LOOK两端",
 "G043":"关系阵营差异 / high possessiveness边界","G042":"低initiative但非低devotion",
 "G044":"多主人公关系差异 / 低依赖","G045":"理性投入 / 高独立",
 "G046":"低情绪表达 / devotion中段","G047":"人格成熟度与initiative两端",
 "G048":"mystery / gap_moe两端","G049":"低关系浓度 / mystery",
 "G050":"低initiative / 情绪表达差异","G051":"成长型 / personality_maturity低端",
 "G052":"高control与高danger稀缺区","G036":"多原型 / devotion中段",
 "G037":"LOOK两端 / initiative差异","G038":"成熟度与关系投入中段",
 "G039":"LOOK纤细端 / 低protectiveness","G040":"中等devotion / 低占有",
 "G041":"低关系浓度 / 理性投入","G033":"平衡关系 / 低依赖",
 "G034":"高danger与control边界","G028":"低protectiveness / 高独立",
 "G030":"低中devotion / 表里一致","G013":"成熟平衡型 / 本篇补缺",
 "G011":"成长型 / initiative低端",
}


def _read(path):
    with path.open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))


def _name(row):
    for key in ("name_zh","name_en","name_ja","name_romaji"):
        if row.get(key) not in {"",None,"NA"}: return row[key]
    return row["character_id"]


def _readiness(character, game):
    url=character.get("official_character_url","") or character.get("source_urls","")
    if not url.startswith("https://"): return "LOW"
    if any(token in url.lower() for token in ("/chara","character","/system","/product")): return "HIGH"
    return "MEDIUM" if game.get("catalog_status") in {"verified","partially_verified"} else "LOW"


def numeric_distribution(xp_rows):
    return {field:{"min":min(v:=[float(r[field]) for r in xp_rows]),"max":max(v),
                   "mean":round(statistics.mean(v),3),"std":round(statistics.pstdev(v),3),
                   "low_1_25":sum(x<=2.5 for x in v),"high_45_5":sum(x>=4.5 for x in v)}
            for field in NUMERIC_FEATURES}


def select(data_dir: Path, target=90):
    xp=_read(data_dir/"characters_v2_candidate.csv"); master=_read(data_dir/"characters_master.csv")
    games=_read(data_dir/"games_master.csv"); apps=_read(data_dir/"character_game_appearances.csv")
    xp_ids={r["character_id"] for r in xp}; by_char={r["character_id"]:r for r in master}; by_game={r["game_id"]:r for r in games}
    char_games=defaultdict(list)
    for a in apps:
        if a["route_available"]=="true": char_games[a["character_id"]].append(a["game_id"])
    # Prefer a base entry, otherwise the first stable appearance.
    primary={cid:min(gids,key=lambda gid:(by_game[gid]["entry_type"]!="base_game",int(gid[1:]))) for cid,gids in char_games.items()}
    annotated_series=Counter(by_game[primary[cid]]["series_id"] for cid in xp_ids if cid in primary)
    annotated_games=Counter(primary[cid] for cid in xp_ids if cid in primary)
    annotated_publishers=Counter(by_game[primary[cid]]["publisher"] for cid in xp_ids if cid in primary)
    candidates=[]
    for cid,c in by_char.items():
        if cid in xp_ids or c["xp_annotation_status"]!="not_annotated" or cid not in primary: continue
        gid=primary[cid]; g=by_game[gid]; readiness=_readiness(c,g)
        series_value=round(20/(1+annotated_series[g["series_id"]]),2)
        game_gap=12/(1+annotated_games[gid])
        dev_value=12 if g["publisher"] in TARGET_PUBLISHERS else max(2,8-annotated_publishers[g["publisher"]]/8)
        expected=10 if gid in GAP_BY_GAME else 5
        source={"HIGH":10,"MEDIUM":6,"LOW":1}[readiness]
        spoiler_penalty=4 if c["spoiler_sensitive"]=="true" else 0
        score=round(series_value+game_gap+dev_value+expected+source-spoiler_penalty,2)
        candidates.append({"character_id":cid,"character_name":_name(c),"game_id":gid,"game":g["title_zh"],
          "series":g["series_name"],"series_id":g["series_id"],"developer_publisher":f"{g['developer']} / {g['publisher']}",
          "publisher":g["publisher"],"developer":g["developer"],"priority_score":score,
          "coverage_gap":GAP_BY_GAME.get(gid,"新系列基线 / annotation后确认稀疏方向"),
          "series_diversity_value":series_value,"source_readiness":readiness,"spoiler":c["spoiler_sensitive"]=="true"})
    candidates.sort(key=lambda r:(-r["priority_score"],r["character_id"]))
    selected=[]; selected_ids=set(); game_count=Counter(); series_count=Counter()
    # Breadth pass: one representative per available game.
    for row in candidates:
        if game_count[row["game_id"]]==0:
            selected.append(row); selected_ids.add(row["character_id"]); game_count[row["game_id"]]+=1; series_count[row["series_id"]]+=1
    # Diversity pass: maximum four per game/series, with non-dominant publishers naturally scoring higher.
    for row in candidates:
        if len(selected)>=target: break
        if row["character_id"] in selected_ids or game_count[row["game_id"]]>=4 or series_count[row["series_id"]]>=4: continue
        selected.append(row); selected_ids.add(row["character_id"]); game_count[row["game_id"]]+=1; series_count[row["series_id"]]+=1
    if len(selected)!=target: raise ValueError(f"could only select {len(selected)} of {target}")
    # Tier is assigned after selection and never participates in score.
    gold_left=12
    for row in selected:
        if gold_left and row["game_id"] in FAMILIAR_GAMES and row["source_readiness"]=="HIGH" and not row["spoiler"]:
            row["suggested_tier"]="Gold Candidate"; gold_left-=1
        elif row["source_readiness"]=="LOW" or row["spoiler"]:
            row["suggested_tier"]="Candidate Only"
        else: row["suggested_tier"]="Reviewed Lite"
    selected.sort(key=lambda r:(-r["priority_score"],r["game"],r["character_id"]))
    return selected,numeric_distribution(xp)


def write_selection(data_dir: Path, target=90):
    selected,distribution=select(data_dir,target)
    with (data_dir/"xp_annotation_priority_v5_7.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore"); w.writeheader(); w.writerows(selected)
    readiness=Counter(r["source_readiness"] for r in selected); tiers=Counter(r["suggested_tier"] for r in selected)
    target_counts=Counter()
    for r in selected:
        for label in TARGET_PUBLISHERS:
            if label in {r["publisher"],r["developer"]}: target_counts[label]+=1
    dominant=sum(r["publisher"]=="Idea Factory" or r["developer"] in {"Idea Factory","Design Factory","Otomate"} for r in selected)
    report={"selected":len(selected),"games":len({r["game_id"] for r in selected}),"series":len({r["series_id"] for r in selected}),
            "idea_factory_otomate_count":dominant,"idea_factory_otomate_rate":dominant/len(selected),
            "target_publisher_counts":dict(target_counts),"source_readiness":dict(readiness),"tiers":dict(tiers),
            "coverage_after":(90+len(selected))/316,"not_annotated_after":226-len(selected),
            "numeric_distribution_before":distribution,"score_formula":"series_gap + game_xp_gap + developer_diversity + expected_xp_diversity + source_readiness - spoiler_penalty",
            "reviewer_like_score_used":False}
    (data_dir/"xp_annotation_priority_v5_7_summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


if __name__=="__main__":
    root=Path(__file__).resolve().parents[1]
    print(json.dumps(write_selection(root/"data"),ensure_ascii=True,indent=2))
