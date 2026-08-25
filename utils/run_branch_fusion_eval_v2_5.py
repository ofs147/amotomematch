"""Grid and select v2.5 offline branch-fusion experiments."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from utils.offline_branch_fusion_v2_5 import (
    FusionConfig, candidate_union, current_baseline, dynamic_blend,
    fusion_diagnostics, gated_rescue, prepare_fold, reciprocal_rank_fusion,
)
from utils.profile_v2 import load_characters_v2


def metrics(df):
    return {"folds": len(df), "hit_at_1": float((df.final_rank<=1).mean()),
            "hit_at_3": float((df.final_rank<=3).mean()), "hit_at_5": float((df.final_rank<=5).mean()),
            "mrr": float((1/df.final_rank).mean()), "mean_positive_rank": float(df.final_rank.mean()),
            "median_positive_rank": float(df.final_rank.median()),
            "positive_rescue_count": int(df.positive_rescue_5.sum()),
            "rescue_at_3": int(df.positive_rescue_3.sum()), "rescue_at_5": int(df.positive_rescue_5.sum()),
            "false_boost_count": int(df.false_boost_count.sum()),
            "false_boost_mean_rank_gain": float(df.false_boost_rank_gain_sum.sum()/df.false_boost_count.sum()) if df.false_boost_count.sum() else 0.0,
            "top3_false_boost": int(df.top3_false_boost.sum()), "top5_false_boost": int(df.top5_false_boost.sum())}


def _evaluate(folds, method, family, params):
    rows=[]
    for meta, fold in folds:
        ranking=method(fold).reset_index(drop=True); ranking["final_rank"]=ranking.index+1
        target=ranking[ranking.character_id==meta["target_id"]].iloc[0]
        diag=fusion_diagnostics(int(target.core_rank),int(target.final_rank),meta["target_id"],ranking)
        rows.append({**meta,"family":family,"params":json.dumps(params,sort_keys=True),
                     "core_rank":int(target.core_rank),"best_branch_rank":target.best_branch_rank,
                     "legacy_multi_branch_rank":int(target.legacy_multi_branch_rank),
                     "final_rank":int(target.final_rank),"core_score":float(target.core_score),
                     "branch_score":target.best_branch_score,"branch_confidence":target.branch_confidence,
                     "branch_member_count":target.branch_member_count,"support_ratio":target.support_ratio,
                     "applied_weight":float(target.applied_weight),"bonus":target.bonus,**diag})
    return pd.DataFrame(rows)


def _group_metrics(frame):
    return {kind:metrics(part) for kind,part in frame.groupby("set_kind")}|{"overall":metrics(frame)}


def _pick(results, baseline_hit5):
    valid=[]
    for key, frame in results.items():
        m=_group_metrics(frame)
        if m["cohesive"]["hit_at_5"] >= baseline_hit5-1/13-1e-9:
            valid.append((key,m))
    return max(valid,key=lambda item:(item[1]["mixed"]["hit_at_3"],item[1]["mixed"]["hit_at_5"],
        item[1]["mixed"]["mrr"],item[1]["overall"]["mrr"],-item[1]["overall"]["false_boost_count"]))[0]


def run(config_path=Path("data/evaluation/aoko_positive_sets_v2_4.json"),
        output_dir=Path("data/evaluation/results_v2_5")):
    config=json.loads(config_path.read_text(encoding="utf-8")); chars=load_characters_v2(Path("data/characters_v2_candidate.csv"))
    folds=[]
    for s in config["sets"]:
        for target in s["character_ids"]:
            selected=[x for x in s["character_ids"] if x!=target]
            folds.append(({"set_id":s["set_id"],"set_kind":s["kind"],"target_id":target,
                           "positive_target":chars.set_index("character_id").loc[target,"character_name"]},prepare_fold(chars,selected)))
    baseline=_evaluate(folds,current_baseline,"Current Baseline",{})
    results={}
    thresholds=(.55,.65,.75); modes=("ratio","sqrt")
    for t in thresholds:
      for mode in modes:
        cfg=FusionConfig(t,mode)
        for lam in (.25,.50,.75,1.0):
            p={"confidence_threshold":t,"support_mode":mode,"lambda":lam}; results[("Gated Rescue",json.dumps(p,sort_keys=True))]=_evaluate(folds,lambda f,cfg=cfg,lam=lam:gated_rescue(f,cfg,lam),"Gated Rescue",p)
        for weight in (.20,.30,.40,.50):
            p={"confidence_threshold":t,"support_mode":mode,"max_branch_weight":weight}; results[("Dynamic Blend",json.dumps(p,sort_keys=True))]=_evaluate(folds,lambda f,cfg=cfg,w=weight:dynamic_blend(f,cfg,w),"Dynamic Blend",p)
        for k in (20,40,60):
            p={"confidence_threshold":t,"support_mode":mode,"rrf_k":k}; results[("RRF",json.dumps(p,sort_keys=True))]=_evaluate(folds,lambda f,cfg=cfg,k=k:reciprocal_rank_fusion(f,cfg,k),"RRF",p)
        for k in (5,8,10):
            p={"confidence_threshold":t,"support_mode":mode,"top_k":k,"stage2":"gated_lambda_1"}; results[("Candidate Union",json.dumps(p,sort_keys=True))]=_evaluate(folds,lambda f,cfg=cfg,k=k:candidate_union(f,cfg,k),"Candidate Union",p)
    base_metrics=_group_metrics(baseline); winners={}
    for family in ("Gated Rescue","Dynamic Blend","RRF","Candidate Union"):
        subset={k:v for k,v in results.items() if k[0]==family}; winners[family]=_pick(subset,base_metrics["cohesive"]["hit_at_5"])
    selected={"Current Baseline":baseline}|{family:results[key] for family,key in winners.items()}
    summary={"evaluation_name":"AOMatch v2.5 Branch Fusion / Single-Reviewer Pilot",
             "selection_rule":"Mixed Hit@3, Hit@5, MRR; cohesive Hit@5 may lose at most one of 13 folds",
             "selected":{name:{"params":json.loads(frame.params.iloc[0]),"metrics":_group_metrics(frame)} for name,frame in selected.items()}}
    all_grid=pd.concat(results.values(),ignore_index=True); chosen=pd.concat(selected.values(),ignore_index=True)
    vilio=chosen[(chosen.set_id=="aoko_set_06")&(chosen.target_id=="C021")].copy()
    output_dir.mkdir(parents=True,exist_ok=True)
    all_grid.to_csv(output_dir/"all_grid_folds.csv",index=False,encoding="utf-8-sig")
    chosen.to_csv(output_dir/"selected_methods_folds.csv",index=False,encoding="utf-8-sig")
    vilio.to_csv(output_dir/"vilio_case.csv",index=False,encoding="utf-8-sig")
    (output_dir/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return summary,chosen,vilio


if __name__=="__main__":
    summary,_,_=run(); print(json.dumps(summary,ensure_ascii=False,indent=2))
