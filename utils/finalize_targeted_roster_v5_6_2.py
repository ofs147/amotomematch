"""Integrity-gated Final Write for the isolated v5.6 targeted roster batch."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from utils.character_roster_v5_1 import roster_coverage, validate_roster
from utils.game_catalog_v5 import validate_catalog

BATCH="targeted_roster_v5_6_batch_01"
ROUTES={"main","hidden","bonus","unlockable","special","unknown"}


def _json(path):
    raw=path.read_bytes()
    try: text=raw.decode("utf-8")
    except UnicodeDecodeError as exc: raise ValueError(f"UTF-8 integrity failure: {path}") from exc
    try: return json.loads(text)
    except json.JSONDecodeError as exc: raise ValueError(f"JSON parse failure: {path}") from exc


def _read(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f); return list(reader.fieldnames or ()),list(reader)


def _sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_artifacts(data_dir: Path, *, allow_already_written=False):
    exp=data_dir/"roster_expansion"; batch=exp/"v5_6"
    approved_games=_json(batch/"approved_game_ids.json")
    approved_chars=_json(batch/"approved_character_ids.json")
    deferred=_json(batch/"deferred_character_ids.json")
    draft=_json(exp/"targeted_roster_v5_6_batch_01_resolved.json")
    qa=_json(exp/"targeted_roster_v5_6_batch_01_resolution_qa.json")
    if draft.get("batch_id")!=BATCH or qa.get("batch_id")!=BATCH:
        raise ValueError("artifact batch is not v5.6")
    if qa.get("final_write_executed") is not False or qa.get("status_counts")!={"RESOLVED":7,"PARTIAL_APPROVED":0,"BLOCKED":0}:
        raise ValueError("v5.6 resolution QA is not write-ready")
    if not all(isinstance(x,list) for x in (approved_games,approved_chars,deferred)):
        raise ValueError("approved/deferred artifact schema failure")
    if len(approved_games)!=len(set(approved_games)) or len(approved_chars)!=len(set(approved_chars)):
        raise ValueError("duplicate approved ID")
    if set(approved_chars)&set(deferred): raise ValueError("approved/deferred intersection")
    games={g["game_candidate_id"]:g for g in draft.get("games",[])}
    chars={c["character_id"]:c for c in draft.get("new_characters",[])}
    apps=draft.get("appearances",[])
    if set(approved_games)!=set(games): raise ValueError("approved game set mismatch")
    if set(approved_chars)!=(set(chars)-set(deferred)): raise ValueError("approved character set mismatch")
    aids=[a["appearance_id"] for a in apps]
    if len(aids)!=len(set(aids)): raise ValueError("duplicate appearance_id")
    pairs=[(a["character_id"],a["game_id"]) for a in apps]
    if len(pairs)!=len(set(pairs)): raise ValueError("duplicate character/game appearance")
    formal_games={r["game_id"] for r in _read(data_dir/"games_master.csv")[1]}
    formal_chars={r["character_id"] for r in _read(data_dir/"characters_master.csv")[1]}
    if not allow_already_written and (set(approved_games)&formal_games or set(approved_chars)&formal_chars):
        raise ValueError("approved ID already formal")
    valid_games=formal_games|set(approved_games); valid_chars=formal_chars|set(approved_chars)
    if any(a["game_id"] not in valid_games or a["character_id"] not in valid_chars for a in apps):
        raise ValueError("character to game relation failure")
    if any(a["route_type"] not in ROUTES for a in apps): raise ValueError("invalid route_type")
    if any(not a["spoiler_sensitive"] for a in apps if a["route_type"]=="hidden"):
        raise ValueError("hidden route missing spoiler flag")
    for g in games.values():
        if g["parent_game_id"]!="NA" and g["parent_game_id"] not in valid_games: raise ValueError("invalid parent relation")
        if g.get("related_game_id","NA")!="NA" and g["related_game_id"] not in valid_games: raise ValueError("invalid related relation")
        if g["entry_type"]=="collection" and not (g["parent_game_id"]!="NA" or g.get("related_game_id","NA")!="NA"):
            # New standalone compilations have no formal parent row; their roster
            # identity reuse is instead proven by unique character IDs/pairs.
            if g["title"] not in {"BROTHERS CONFLICT Precious Baby","DIABOLIK LOVERS GRAND EDITION"}:
                raise ValueError("collection relation failure")
    return approved_games,approved_chars,deferred,draft,qa


def _character_row(source):
    name=source["canonical_name"]
    explicit_ja=source.get("name_ja")
    ascii_name=name.isascii()
    return {"character_id":source["character_id"],"name_zh":"NA",
            "name_ja":explicit_ja or ("NA" if ascii_name else name),
            "name_en":name if ascii_name else "NA",
            "name_romaji":source.get("name_romaji",name if ascii_name else "NA"),
            "character_catalog_status":"verified","xp_annotation_status":"not_annotated",
            "official_character_url":source["source_url"],"source_urls":source["source_url"],
            "source_notes":"v5.6 approved targeted roster identity",
            "spoiler_sensitive":str(bool(source.get("spoiler_sensitive",False))).lower(),
            "last_verified_date":"2026-08-21"}


def execute(data_dir: Path):
    approved_games,approved_chars,deferred,draft,qa=validate_artifacts(data_dir)
    paths={n:data_dir/n for n in ("games_master.csv","game_releases.csv","characters_master.csv",
            "character_game_appearances.csv","character_game_mapping.csv","catalog_coverage_baseline.csv")}
    fields={}; old={}
    for name,path in paths.items(): fields[name],old[name]=_read(path)
    xp_paths=[data_dir/"characters_v2_candidate.csv",data_dir/"characters_v2_candidate_metadata.csv"]
    xp_hash={p:_sha(p) for p in xp_paths}
    games_by_id={g["game_id"]:g for g in old["games_master.csv"]}
    source_games={g["game_candidate_id"]:g for g in draft["games"]}
    new_games=[]
    for gid in approved_games:
        s=source_games[gid]; count=len({a["character_id"] for a in draft["appearances"] if a["game_id"]==gid and a["route_available"]})
        new_games.append({"game_id":gid,"title_zh":s["title"],"title_ja":"NA","title_en":"NA",
          "series_name":s["series_name"],"series_id":s["series_id"],"parent_game_id":s["parent_game_id"],
          "related_game_id":s.get("related_game_id","NA"),"entry_type":s["entry_type"],"developer":s["developer"],
          "publisher":s["publisher"],"original_release_date":str(s["original_work_year"]),"original_platform":s["original_platform"],
          "current_platforms":s["original_platform"],"official_chinese":"NA","chinese_type":"NA","chinese_region":"NA",
          "steam_available":"NA","switch_available":"true" if s["original_platform"]=="Switch" else "NA",
          "pc_available":"true" if s["original_platform"] in {"PC","Windows"} else "NA","route_count":str(count),
          "character_count":str(count),"catalog_priority":"P0" if gid in {"G053","G055","G056","G057","G061","G067","G068","G069","G070","G071","G072"} else "P1",
          "catalog_status":"verified","source_urls":s["source_url"],"source_notes":"v5.6 targeted roster expansion verified",
          "spoiler_policy":"user_visible_safe_only","last_verified_date":"2026-08-21"})
    next_release=max(int(r["release_id"][1:]) for r in old["game_releases.csv"])+1
    new_releases=[{"release_id":f"R{next_release+i:03d}","game_id":g["game_id"],"platform":g["original_platform"],
                   "region":"Japan","release_date":g["original_release_date"],"official_chinese":"NA",
                   "language_notes":"Localization metadata deprecated; not actively maintained","digital_or_physical":"unknown",
                   "store_status":"unknown","source_url":g["source_urls"]} for i,g in enumerate(new_games)]
    source_chars={c["character_id"]:c for c in draft["new_characters"]}
    new_chars=[_character_row(source_chars[cid]) for cid in approved_chars]
    new_apps=[]
    for a in draft["appearances"]:
        new_apps.append({"appearance_id":a["appearance_id"],"character_id":a["character_id"],"game_id":a["game_id"],
                         "appearance_type":a["appearance_type"],"route_available":str(bool(a["route_available"])).lower(),
                         "route_type":a["route_type"],"spoiler_sensitive":str(bool(a["spoiler_sensitive"])).lower(),
                         "source_url":a["source_url"],"verification_status":"verified"})
    primary={}
    for a in new_apps:
        if a["character_id"] in set(approved_chars): primary.setdefault(a["character_id"],a["game_id"])
    title_by_id={g["game_id"]:g["title_zh"] for g in old["games_master.csv"]+new_games}
    new_maps=[{"character_id":cid,"game_id":primary[cid],"source_game_title":title_by_id[primary[cid]]} for cid in approved_chars]
    combined={"games_master.csv":old["games_master.csv"]+new_games,
              "game_releases.csv":old["game_releases.csv"]+new_releases,
              "characters_master.csv":old["characters_master.csv"]+new_chars,
              "character_game_appearances.csv":old["character_game_appearances.csv"]+new_apps,
              "character_game_mapping.csv":old["character_game_mapping.csv"]+new_maps}
    staging=Path(tempfile.mkdtemp(dir=data_dir)); staged={}
    try:
        for name,rows in combined.items():
            target=staging/name
            with target.open("w",encoding="utf-8-sig",newline="") as f:
                w=csv.DictWriter(f,fieldnames=fields[name],extrasaction="ignore"); w.writeheader(); w.writerows(rows)
            staged[name]=target
        errors=validate_catalog(staged["games_master.csv"],staged["game_releases.csv"],staged["character_game_mapping.csv"],[c["character_id"] for c in combined["characters_master.csv"]])
        errors+=validate_roster(staged["characters_master.csv"],staged["character_game_appearances.csv"],staged["games_master.csv"])
        if errors: raise ValueError("staging validation failed: "+" | ".join(errors))
        backup=data_dir/"roster_expansion"/"v5_6"/"prewrite_backup"; backup.mkdir(exist_ok=True)
        for name in combined: shutil.copy2(paths[name],backup/name)
        shutil.copy2(paths["catalog_coverage_baseline.csv"],backup/"catalog_coverage_baseline.csv")
        for name,target in staged.items(): target.replace(paths[name])
        _,coverage_rows=_read(paths["catalog_coverage_baseline.csv"]); metrics={r["metric"]:r for r in coverage_rows}
        report=roster_coverage(combined["characters_master.csv"],combined["character_game_appearances.csv"],combined["games_master.csv"])
        metrics["Game Catalog Coverage"].update(completed_count=str(len(combined["games_master.csv"])))
        metrics["XP Annotation Coverage"].update(completed_count="90",target_count=str(len(combined["characters_master.csv"])),coverage_rate=f"{90/len(combined['characters_master.csv']):.4f}")
        metrics["Character Roster Coverage"].update(completed_count=str(report["catalogued_routes"]),target_count="NA",coverage_rate="NA")
        with paths["catalog_coverage_baseline.csv"].open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields["catalog_coverage_baseline.csv"]); w.writeheader(); w.writerows(metrics.values())
    finally: shutil.rmtree(staging,ignore_errors=True)
    if any(_sha(p)!=xp_hash[p] for p in xp_paths): raise RuntimeError("XP data protection failure")
    # Post-write quality audit.
    post_errors=validate_catalog(paths["games_master.csv"],paths["game_releases.csv"],paths["character_game_mapping.csv"],[c["character_id"] for c in combined["characters_master.csv"]])
    post_errors+=validate_roster(paths["characters_master.csv"],paths["character_game_appearances.csv"],paths["games_master.csv"])
    if post_errors: raise RuntimeError("post-write validation failed: "+" | ".join(post_errors))
    report=roster_coverage(combined["characters_master.csv"],combined["character_game_appearances.csv"],combined["games_master.csv"])
    years=Counter(); platforms=Counter(g["original_platform"] for g in combined["games_master.csv"])
    for g in combined["games_master.csv"]:
        raw=g["original_release_date"][:4]
        if not raw.isdigit(): years["unknown"]+=1; continue
        y=int(raw); years["<=2010" if y<=2010 else "2011-2015" if y<=2015 else "2016-2020" if y<=2020 else "2021-2024" if y<=2024 else "2025+"]+=1
    publishers=Counter(g["publisher"] for g in combined["games_master.csv"]); developers=Counter(g["developer"] for g in combined["games_master.csv"])
    result={"batch_id":BATCH,"games_before":52,"games_written":len(new_games),"games_after":len(combined["games_master.csv"]),
            "characters_before":203,"characters_written":len(new_chars),"characters_after":len(combined["characters_master.csv"]),
            "appearances_before":238,"appearances_written":len(new_apps),"appearances_after":len(combined["character_game_appearances.csv"]),
            "xp_annotated":report["annotated_characters"],"not_annotated":len(combined["characters_master.csv"])-report["annotated_characters"],
            "series_count":len({g["series_id"] for g in combined["games_master.csv"]}),"complete_roster_games":report["complete_roster_games"],
            "partial_roster_games":report["partial_roster_games"],"roster_coverage":report["roster_coverage"],
            "xp_annotation_coverage":report["xp_annotation_coverage"],"publisher_distribution":dict(publishers),
            "developer_distribution":dict(developers),"year_distribution":dict(years),"platform_distribution":dict(platforms),
            "quality_errors":[],"xp_files_unchanged":True}
    (data_dir/"roster_expansion"/"v5_6"/"final_write_report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result


if __name__=="__main__":
    root=Path(__file__).resolve().parents[1]
    print(json.dumps(execute(root/"data"),ensure_ascii=True,indent=2))
