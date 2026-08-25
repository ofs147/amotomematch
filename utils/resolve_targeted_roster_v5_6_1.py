"""Resolve only the seven v5.6 exception games; never writes formal CSVs."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ALLOWED_ROUTES={"main","hidden","bonus","unlockable","special","unknown"}


def _load(path):
    with path.open(encoding="utf-8") as handle: return json.load(handle)


def _formal_ids(data_dir, filename, field):
    with (data_dir/filename).open(encoding="utf-8-sig",newline="") as f:
        return {r[field] for r in csv.DictReader(f)}


def resolve(data_dir: Path):
    out=data_dir/"roster_expansion"
    draft=_load(out/"targeted_roster_v5_6_batch_01_draft.json")
    qa=_load(out/"targeted_roster_v5_6_batch_01_qa.json")
    assert draft["batch_id"]==qa["batch_id"]=="targeted_roster_v5_6_batch_01"
    games={g["title"]:g for g in draft["games"]}
    chars={c["canonical_name"]:c for c in draft["new_characters"]}
    apps=draft["appearances"]
    decisions=[]

    def decision(title, issue, resolution, affected, confidence="A"):
        decisions.append({"game":title,"issue":issue,"resolution":resolution,
                          "affected_characters":affected,"final_status":"RESOLVED",
                          "evidence_confidence":confidence})
        games[title]["qa_status"]="RESOLVED"

    # Code:Realize: official system calls these separate new stories, not the
    # five main after stories.  They are visible official characters, not hidden.
    for name in ("Finis","Herlock Sholmes"):
        cid=chars[name]["character_id"]
        for a in apps:
            if a["character_id"]==cid and a["game_id"] in {"G053","G054"}: a["route_type"]="special"
    games["Code:Realize ～白银的奇迹～"]["related_game_id"]="G053"
    decision("Code:Realize ～祝福的未来～","Finis / Sholmes route type",
             "两人复用同一 identity；FD 新规故事标为 special，不标 hidden。",["Finis","Herlock Sholmes"])

    # Nil Admirari: Akira already exists as C011. Replace the duplicate draft
    # identity with the actual missing base route Hisui and add base appearances.
    duplicate=chars.pop("鴻上滉"); duplicate["canonical_name"]="星川翡翠"; duplicate["name_ja"]="星川 翡翠"; duplicate["name_romaji"]="NA"; chars["星川翡翠"]=duplicate
    for c in (chars["尾崎隼人"],chars["星川翡翠"]):
        c["name_ja"]="尾崎 隼人" if c["canonical_name"]=="尾崎隼人" else "星川 翡翠"; c["name_romaji"]="NA"
    # Existing C011 is reused in sequel; draft occurrence formerly pointed at
    # the replaced candidate ID, so add C011 and retain the ID for Hisui.
    sequel=games["冷然之天秤 黑百合炎阳谭"]
    if "C011" not in sequel["roster_character_ids"]: sequel["roster_character_ids"].append("C011")
    next_a=max(int(a["appearance_id"][1:]) for a in apps)+1
    for c in (chars["尾崎隼人"],chars["星川翡翠"]):
        apps.append({"appearance_id":f"A{next_a:04d}","character_id":c["character_id"],"game_id":"G013",
                     "appearance_type":"base_game","route_available":True,"route_type":"main",
                     "spoiler_sensitive":False,"source_url":"https://www.otomate.jp/nil-admirari/"}); next_a+=1
    decision("冷然之天秤 黑百合炎阳谭","本篇缺角与 sequel boundary",
             "本篇补尾崎隼人、星川翡翠；鴻上滉复用正式 C011。六名既有路线全部链接续作。",
             ["尾崎隼人","星川翡翠","鴻上滉"],"A")

    # Wand: keep Japanese official names, no invented Latin spelling.
    wand_map={"Julius Fortner":"ユリウス・フォルトナー","Bilal Asad Ithnan Faranbald":"ビラール・アサド・イスナーン・ファランバルド","Lagi El Nagil":"ラギ・エル・ナギル","Solo Monoe":"ソロ・モーン"}
    wand=[]
    for old,new in wand_map.items():
        c=chars.pop(old); c.update({"canonical_name":new,"name_ja":new,"name_romaji":"NA"}); chars[new]=c; wand.append(c)
    for c in wand[:3]:
        apps.append({"appearance_id":f"A{next_a:04d}","character_id":c["character_id"],"game_id":"G011",
                     "appearance_type":"remake","route_available":True,"route_type":"main","spoiler_sensitive":False,
                     "source_url":"https://www.otomate.jp/wandoffortune/vita/chara/"}); next_a+=1
    decision("Wand of Fortune R2","romanization / R2 identity reuse",
             "R既有三人继续复用；补R缺失三人的 base appearance；ソロ・モーン仅新增一次 identity。无官方拉丁拼写时 romaji=NA。",
             list(wand_map.values()),"A")

    games["花合朔 Complete Collection"]["related_game_id"]="G025"
    for n in ("Karakurenai","Utsutsu","Iroha"):
        chars[n]["name_romaji"]="NA"
    decision("花合朔 Complete Collection","四篇 collection identity",
             "G024姬空木与G025蛟直接复用；唐红、宇津都、伊吕波各建一次 identity，仅增加 collection appearance。",
             ["Himeutsugi","Mizuchi","Karakurenai","Utsutsu","Iroha"],"A")

    # Winter's Wish draft had six guessed English names. Official system lists
    # exactly five romance routes. Reuse five IDs, delete the sixth candidate.
    old=["Tomonari Takamura","Ohtaro","Kunitaka","Yoichi","Genjuro Kuga","Kinji"]
    official=["レジス・ド・ルペルティエ","エリアス・ベルニエ","ディラン・ギベール","オスカー・シルヴェストリ","イヴェール"]
    winter_gid=games["冬园 Sacrifice"]["game_candidate_id"]
    dropped=chars[old[-1]]["character_id"]
    for o,n in zip(old,official):
        c=chars.pop(o); c.update({"canonical_name":n,"name_ja":n,"name_romaji":"NA"}); chars[n]=c
    chars.pop(old[-1]); apps[:]=[a for a in apps if a["character_id"]!=dropped]
    games["冬园 Sacrifice"]["roster_character_ids"]=[chars[n]["character_id"] for n in official]
    decision("冬园 Sacrifice","日文名 / romanization",
             "使用官方五条恋爱路线日文名；无可靠官方罗马字，全部 name_romaji=NA；删除第六个错误候选。",official,"A")

    for n in ["真田幸村","天野五月","宮本武蔵","佐々木大和","黒田長政","直江兼続","阿国","柳生宗矩"]:
        chars[n].update({"name_ja":n,"name_romaji":"NA"})
    decision("遥远时空中7","特殊读音 / 八叶 eligibility",
             "官方角色页分别列出八名对象；八人均 main。保留日文名，未采用非官方 romanization。",
             ["真田幸村","天野五月","宮本武蔵","佐々木大和","黒田長政","直江兼続","阿国","柳生宗矩"],"A")

    # GS4: package-facing eight are main; three characters under the official
    # secret/special surface are valid routes but hidden from default UI.
    gs_main={"風真玲太","颯砂希","本多行","七ツ森実","柊夜ノ介","氷室一紀","御影小次郎","白羽大地"}
    gs_hidden={"白羽空也","巴征道","大成功"}
    # Correct official spacing/name: 大成 功, not 大成功.
    c=chars.pop("大成功"); c.update({"canonical_name":"大成 功","name_ja":"大成 功","name_romaji":"NA"}); chars["大成 功"]=c
    gs_hidden.remove("大成功"); gs_hidden.add("大成 功")
    gs_gid=games["心跳回忆 Girl's Side 4th Heart"]["game_candidate_id"]
    for a in apps:
        name=next((n for n,c in chars.items() if c["character_id"]==a["character_id"]),None)
        if a["game_id"]==gs_gid and name in gs_hidden:
            a["route_type"]="hidden"; a["spoiler_sensitive"]=True; chars[name]["spoiler_sensitive"]=True
    decision("心跳回忆 Girl's Side 4th Heart","hidden / special eligibility",
             "官网核心八人标 main；白羽空也、巴征道、大成 功为正式隐藏路线，标 hidden + spoiler_sensitive。",
             sorted(gs_main|gs_hidden),"A")

    draft["new_characters"]=list(chars.values())
    draft["appearances"]=apps
    draft["resolution_decisions"]=decisions
    approved_games=[g["game_candidate_id"] for g in draft["games"]]
    # The approved list is a stable property of this batch artifact.  Do not
    # shrink it when the resolver is re-run after a successful Final Write.
    approved_chars=[c["character_id"] for c in draft["new_characters"]]
    approved_apps=[a["appearance_id"] for a in apps]
    deferred=[]
    # Integrity gate.
    assert len(approved_games)==len(set(approved_games))==20
    assert len(approved_chars)==len(set(approved_chars))
    assert len(approved_apps)==len(set(approved_apps))
    assert not set(approved_chars)&set(deferred)
    assert all(a["route_type"] in ALLOWED_ROUTES for a in apps)
    assert all(a["spoiler_sensitive"] for a in apps if a["route_type"]=="hidden")
    valid_games=_formal_ids(data_dir,"games_master.csv","game_id")|set(approved_games)
    assert all(a["game_id"] in valid_games for a in apps)
    for g in draft["games"]:
        assert g["parent_game_id"]=="NA" or g["parent_game_id"] in valid_games
        assert g.get("related_game_id","NA")=="NA" or g["related_game_id"] in valid_games
    resolved_qa={"batch_id":draft["batch_id"],"status_counts":{"RESOLVED":7,"PARTIAL_APPROVED":0,"BLOCKED":0},
                 "approved_games":len(approved_games),"approved_new_unique_characters":len(approved_chars),
                 "approved_appearances":len(approved_apps),"deferred_characters":0,"decisions":decisions,
                 "projected":{"games":52+len(approved_games),"characters":203+len(approved_chars),"appearances":238+len(approved_apps)},
                 "integrity":{"unique_ids":True,"identity_reuse":True,"route_schema":True,"hidden_spoiler":True,
                              "relations":True,"approved_deferred_disjoint":True,"json_utf8":True},
                 "final_write_executed":False}
    return draft,resolved_qa,approved_games,approved_chars,deferred


def write_resolution(data_dir: Path):
    draft,qa,games,chars,deferred=resolve(data_dir); out=data_dir/"roster_expansion"
    payloads={"targeted_roster_v5_6_batch_01_resolved.json":draft,
              "targeted_roster_v5_6_batch_01_resolution_qa.json":qa}
    for name,payload in payloads.items():
        (out/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        _load(out/name)
    batch_out=out/"v5_6"; batch_out.mkdir(exist_ok=True)
    for name,payload in {"approved_game_ids.json":games,"approved_character_ids.json":chars,
                         "deferred_character_ids.json":deferred}.items():
        (batch_out/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        _load(batch_out/name)
    return qa


if __name__=="__main__":
    root=Path(__file__).resolve().parents[1]
    print(json.dumps(write_resolution(root/"data"),ensure_ascii=True,indent=2))
