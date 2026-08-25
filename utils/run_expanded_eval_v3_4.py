"""AOMatch v3.4 expanded-pool evaluation (read-only ranking evaluation)."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pandas as pd

from utils.multi_branch_v2 import build_multi_branch_profile, recommend_branch_aware_gated_rescue
from utils.profile_v2 import load_characters_v2


FROZEN_MAX_ID = 31
NEW_MIN_ID = 32


def numeric_id(character_id: str) -> int:
    return int(character_id.removeprefix("C"))


def summarize(detail: pd.DataFrame) -> dict:
    return {
        "folds": len(detail),
        "hit_at_1": float((detail["new_rank"] <= 1).mean()),
        "hit_at_3": float((detail["new_rank"] <= 3).mean()),
        "hit_at_5": float((detail["new_rank"] <= 5).mean()),
        "mrr": float((1 / detail["new_rank"]).mean()),
        "mean_positive_rank": float(detail["new_rank"].mean()),
        "median_positive_rank": float(detail["new_rank"].median()),
        "mean_top1_score": float(detail["new_top1_score"].mean()),
        "mean_top5_score": float(detail["new_top5_score"].mean()),
        "mean_top5_spread": float(detail["new_top5_spread"].mean()),
    }


def historical_summary(detail: pd.DataFrame) -> dict:
    return {
        "folds": len(detail),
        "hit_at_1": float((detail["old_rank"] <= 1).mean()),
        "hit_at_3": float((detail["old_rank"] <= 3).mean()),
        "hit_at_5": float((detail["old_rank"] <= 5).mean()),
        "mrr": float((1 / detail["old_rank"]).mean()),
        "mean_positive_rank": float(detail["old_rank"].mean()),
        "median_positive_rank": float(detail["old_rank"].median()),
        "mean_top1_score": float(detail["old_top1_score"].mean()),
        "mean_top5_score": float(detail["old_top5_score"].mean()),
        "mean_top5_spread": float(detail["old_top5_spread"].mean()),
    }


def rank_fold(characters: pd.DataFrame, selected_ids: list[str]) -> pd.DataFrame:
    selected = characters[characters.character_id.isin(selected_ids)]
    profile = build_multi_branch_profile(selected)
    return recommend_branch_aware_gated_rescue(
        characters, profile, selected_ids, top_n=len(characters),
    ).reset_index(drop=True)


def evaluate(old_pool: pd.DataFrame, new_pool: pd.DataFrame, config: dict) -> pd.DataFrame:
    records = []
    for preference_set in config["sets"]:
        likes = preference_set["character_ids"]
        for target in likes:
            selected = [character_id for character_id in likes if character_id != target]
            old = rank_fold(old_pool, selected)
            new = rank_fold(new_pool, selected)
            old_position = int(old.index[old.character_id == target][0])
            new_position = int(new.index[new.character_id == target][0])
            old_rank, new_rank = old_position + 1, new_position + 1
            rank_change = old_rank - new_rank
            top5 = new.head(5)
            new_above_target = new.iloc[:new_position]
            records.append({
                "set_id": preference_set["set_id"], "kind": preference_set["kind"],
                "target_id": target,
                "target_name": str(new_pool.set_index("character_id").loc[target, "character_name"]),
                "selected_ids": ";".join(selected), "old_rank": old_rank, "new_rank": new_rank,
                "rank_change": rank_change,
                "classification": "IMPROVED" if rank_change > 0 else ("WORSE" if rank_change < 0 else "STABLE"),
                "old_top1_score": float(old.iloc[0]["final_score"]),
                "old_top5_score": float(old.iloc[min(4, len(old)-1)]["final_score"]),
                "old_top5_spread": float(old.iloc[0]["final_score"] - old.iloc[min(4, len(old)-1)]["final_score"]),
                "new_top1_score": float(new.iloc[0]["final_score"]),
                "new_top5_score": float(new.iloc[min(4, len(new)-1)]["final_score"]),
                "new_top5_spread": float(new.iloc[0]["final_score"] - new.iloc[min(4, len(new)-1)]["final_score"]),
                "new_top5_ids": ";".join(top5.character_id),
                "expanded_candidates_in_top5": int(sum(numeric_id(cid) >= NEW_MIN_ID for cid in top5.character_id)),
                "expanded_candidates_above_positive": int(sum(numeric_id(cid) >= NEW_MIN_ID for cid in new_above_target.character_id)),
                "positive_rescue_bonus": float(new.iloc[new_position]["rescue_bonus"]),
            })
    return pd.DataFrame(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--characters", type=Path, default=Path("data/characters_v2_candidate.csv"))
    parser.add_argument("--metadata", type=Path, default=Path("data/characters_v2_candidate_metadata.csv"))
    parser.add_argument("--ground-truth", type=Path, default=Path("data/evaluation/aoko_positive_sets_v2_4.json"))
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/results_v3_4"))
    args = parser.parse_args()

    characters = load_characters_v2(args.characters)
    old_pool = characters[characters.character_id.map(numeric_id) <= FROZEN_MAX_ID].copy()
    config = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    with args.metadata.open(encoding="utf-8-sig", newline="") as handle:
        metadata = {row["character_id"]: row for row in csv.DictReader(handle)}
    positive_ids = {cid for item in config["sets"] for cid in item["character_ids"]}
    invalid = [cid for cid in positive_ids if metadata[cid]["annotation_status"] not in {"human_reviewed", "human_reviewed_gold"}]
    if invalid:
        raise ValueError(f"Ground Truth purity violation: {invalid}")

    detail = evaluate(old_pool, characters, config)
    summary = {
        "evaluation_name": "AOMatch v3.4 Expanded Database / Frozen Gated Rescue",
        "parameters": {"confidence_threshold": 0.55, "support_mode": "sqrt", "lambda": 1.0},
        "pool": {"old": len(old_pool), "current": len(characters)},
        "ground_truth": {"folds": len(detail), "positive_ids": sorted(positive_ids), "purity_check": "passed"},
        "old": {}, "current": {},
        "rank_change_counts": detail["classification"].value_counts().to_dict(),
        "expansion_effect": {
            "folds_with_expanded_candidate_in_top5": int((detail.expanded_candidates_in_top5 > 0).sum()),
            "mean_expanded_candidates_in_top5": float(detail.expanded_candidates_in_top5.mean()),
            "mean_expanded_candidates_above_positive": float(detail.expanded_candidates_above_positive.mean()),
        },
    }
    for kind in ("cohesive", "mixed", "overall"):
        subset = detail if kind == "overall" else detail[detail.kind == kind]
        summary["old"][kind] = historical_summary(subset)
        summary["current"][kind] = summarize(subset)

    args.output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(args.output / "folds.csv", index=False, encoding="utf-8-sig")
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
