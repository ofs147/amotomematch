"""Run the fixed aoko single-reviewer pilot and write reproducible artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from utils.multi_branch_v2 import build_multi_branch_profile, recommend_branch_aware
from utils.offline_eval_v2_4 import CURRENT_WEIGHTS, PREFERRED_WEIGHTS, rank_candidates
from utils.profile_v2 import load_characters_v2


VARIANTS = {
    "Baseline": (CURRENT_WEIGHTS, False),
    "Experiment A": (PREFERRED_WEIGHTS, False),
    "Experiment B": (CURRENT_WEIGHTS, True),
    "Experiment C": (PREFERRED_WEIGHTS, True),
}


def _metrics(frame: pd.DataFrame) -> dict:
    return {
        "folds": len(frame),
        "hit_at_1": float((frame["rank"] <= 1).mean()),
        "hit_at_3": float((frame["rank"] <= 3).mean()),
        "hit_at_5": float((frame["rank"] <= 5).mean()),
        "mrr": float((1 / frame["rank"]).mean()),
        "mean_positive_rank": float(frame["rank"].mean()),
        "median_positive_rank": float(frame["rank"].median()),
        "top5_spread": float(frame["top5_spread"].mean()),
        "mean_adjusted_match": float(frame["adjusted_match"].mean()),
    }


def run(config_path=Path("data/evaluation/aoko_positive_sets_v2_4.json"),
        output_dir=Path("data/evaluation/results_v2_4")):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    characters = load_characters_v2(Path("data/characters_v2_candidate.csv"))
    names = characters.set_index("character_id")["character_name"].to_dict()
    detail = []
    for test_set in config["sets"]:
        likes = test_set["character_ids"]
        for target in likes:
            selected = [item for item in likes if item != target]
            # Current production branch logic is diagnostic and is not used to
            # choose among the four core/salience variants.
            selected_rows = characters[characters.character_id.isin(selected)]
            multi_profile = build_multi_branch_profile(selected_rows)
            branch = recommend_branch_aware(characters, multi_profile, selected, top_n=len(characters))
            branch_target = branch[branch.character_id == target].iloc[0]
            branch_support = {item["branch_id"]: item["selected_count"] for item in multi_profile["branches"]}
            supported_branch_scores = [
                float(score) for branch_id, score in branch_target.branch_adjusted_scores.items()
                if branch_support.get(branch_id, 0) >= 2
            ]
            multi_order = branch.sort_values(["multi_branch_score_raw", "character_id"], ascending=[False, True]).reset_index(drop=True)
            multi_rank = int(multi_order.index[multi_order.character_id == target][0]) + 1
            for variant, (weights, salience) in VARIANTS.items():
                ranked = rank_candidates(characters, selected, weights, salience)
                position = int(ranked.index[ranked.character_id == target][0])
                row = ranked.iloc[position]
                pool_size = len(ranked)
                detail.append({
                    "reviewer": config["reviewer"], "set_id": test_set["set_id"],
                    "set_kind": test_set["kind"], "variant": variant,
                    "selected_ids": ";".join(selected),
                    "selected_characters": ";".join(names[x] for x in selected),
                    "target_id": target, "positive_target": names[target], "rank": position + 1,
                    "raw_match": float(row.raw_match), "adjusted_match": float(row.adjusted_match),
                    "candidate_pool_percentile": 100 * (pool_size-position-1) / max(1, pool_size-1),
                    "top_pool_percent": 100 * (position+1) / pool_size,
                    "top5_spread": float(ranked.iloc[0].adjusted_match-ranked.iloc[min(4,pool_size-1)].adjusted_match),
                    "core_xp_match": float(branch_target.core_adjusted_score),
                    "best_multi_character_branch_match": (
                        max(supported_branch_scores) if supported_branch_scores else None),
                    "hidden_singleton_branch_match": (
                        float(branch_target.best_sub_branch_score)
                        if pd.notna(branch_target.best_sub_branch_score) and branch_target.best_sub_branch_is_singleton
                        else None),
                    "branch_base_rank": int(branch_target.base_rank),
                    "multi_branch_rank": multi_rank,
                    "branch_final_rank": int(branch_target.final_rank),
                    "branch_rerank_bonus": float(branch_target.rerank_bonus),
                })
    frame = pd.DataFrame(detail)
    baseline = frame[frame.variant == "Baseline"].copy()
    b_ranks = frame[frame.variant == "Experiment B"].set_index(["set_id", "target_id"])["rank"]
    baseline["salience_rank"] = [b_ranks.loc[(x.set_id, x.target_id)] for x in baseline.itertuples()]
    baseline["branch_outlier"] = ((baseline.branch_base_rank > 5) &
        ((baseline.best_multi_character_branch_match.fillna(0) >= baseline.core_xp_match + 5) |
         (baseline.hidden_singleton_branch_match.fillna(0) >= baseline.core_xp_match + 5)))

    all_variant_ranks = frame.pivot(index=["set_id", "target_id"], columns="variant", values="rank")
    all_low = all_variant_ranks.min(axis=1) > 5
    def failure_type(row):
        key = (row.set_id, row.target_id)
        if row.branch_base_rank > 5 and (row.multi_branch_rank <= 5 or row.branch_final_rank <= 5):
            return "TYPE C"
        if all_low.loc[key]:
            return "TYPE D"
        if row["rank"] <= 5 and row.adjusted_match < 70:
            return "TYPE A"
        if row["rank"] > 5 and row.adjusted_match < 70:
            return "TYPE B"
        return "NONE"
    baseline["failure_type"] = baseline.apply(failure_type, axis=1)

    summary = {"evaluation_name": config["evaluation_name"], "reviewer_count": 1,
               "positive_character_count": len(config["name_resolution"]),
               "unique_folds": int(len(baseline)), "variant_fold_rows": int(len(frame)),
               "variants": {}, "macro_overall": {}}
    for variant, vf in frame.groupby("variant", sort=False):
        summary["variants"][variant] = {
            kind: _metrics(part) for kind, part in vf.groupby("set_kind", sort=False)
        }
        # Macro overall: equal weight for cohesive and mixed category metrics.
        kinds = list(summary["variants"][variant].values())
        summary["macro_overall"][variant] = {
            key: sum(item[key] for item in kinds)/len(kinds)
            for key in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr",
                        "mean_positive_rank", "median_positive_rank", "top5_spread", "mean_adjusted_match")
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_dir / "loo_folds_all_variants.csv", index=False, encoding="utf-8-sig")
    baseline.to_csv(output_dir / "baseline_diagnostics.csv", index=False, encoding="utf-8-sig")
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary, frame, baseline


if __name__ == "__main__":
    result, _, _ = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
