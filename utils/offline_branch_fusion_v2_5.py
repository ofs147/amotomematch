"""AOMatch v2.5 multi-branch fusion experiments (offline only)."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Callable, Mapping

import pandas as pd

from utils.multi_branch_v2 import build_multi_branch_profile, recommend_branch_aware
from utils.recommender_v2_1 import recommend_characters_v2_1


@dataclass(frozen=True)
class FusionConfig:
    confidence_threshold: float = 0.55
    support_mode: str = "ratio"  # ratio | sqrt


def support_factor(member_count: int, selected_total: int, mode: str) -> float:
    ratio = member_count / selected_total
    if mode == "ratio":
        return ratio
    if mode == "sqrt":
        return sqrt(ratio)
    raise ValueError("support_mode must be ratio or sqrt")


def prepare_fold(characters: pd.DataFrame, selected_ids: list[str]) -> dict:
    selected = characters[characters.character_id.isin(selected_ids)]
    multi = build_multi_branch_profile(selected)
    core = recommend_characters_v2_1(
        characters, multi["global_profile"], selected_ids,
        top_n=len(characters), sort_by="coverage_adjusted"
    ).reset_index(drop=True)
    core["core_rank"] = core.index + 1
    branches = []
    for branch in multi["branches"]:
        scores = recommend_characters_v2_1(
            characters, branch["profile"], selected_ids,
            top_n=len(characters), sort_by="coverage_adjusted"
        ).reset_index(drop=True)
        scores["branch_rank"] = scores.index + 1
        branches.append({**branch, "scores": scores.set_index("character_id")})
    current = recommend_branch_aware(characters, multi, selected_ids, top_n=len(characters))
    legacy_order = current.sort_values(["multi_branch_score_raw", "character_id"], ascending=[False, True]).reset_index(drop=True)
    legacy_multi_rank = {cid: index+1 for index, cid in enumerate(legacy_order.character_id)}
    return {"selected_ids": selected_ids, "selected_total": len(selected_ids),
            "core": core.set_index("character_id"), "branches": branches,
            "current": current.set_index("character_id"), "legacy_multi_rank": legacy_multi_rank}


def eligible_branches(fold: Mapping, config: FusionConfig):
    return [b for b in fold["branches"] if b["selected_count"] >= 2
            and float(b["confidence"]) >= config.confidence_threshold]


def _gate(branch, fold, config):
    return float(branch["confidence"]) * support_factor(
        branch["selected_count"], fold["selected_total"], config.support_mode)


def _best_branch(candidate_id, fold, config):
    eligible = eligible_branches(fold, config)
    if not eligible:
        return None, None, None
    values = [(float(b["scores"].loc[candidate_id, "coverage_adjusted_final_score_raw"]), b)
              for b in eligible]
    score, branch = max(values, key=lambda x: x[0])
    return score, int(branch["scores"].loc[candidate_id, "branch_rank"]), branch


def _rank(frame, score_column="final_score"):
    return frame.sort_values([score_column, "character_id"], ascending=[False, True]).reset_index(drop=True)


def current_baseline(fold):
    rows = []
    for cid, row in fold["current"].iterrows():
        best_score, best_rank, best = _best_branch(cid, fold, FusionConfig(0.0, "ratio"))
        rows.append({"character_id": cid, "core_score": float(row.core_adjusted_score),
                     "core_rank": int(row.base_rank), "best_branch_score": best_score,
                     "best_branch_rank": best_rank, "legacy_multi_branch_rank": fold["legacy_multi_rank"][cid],
                     "branch_confidence": None if best is None else float(best["confidence"]),
                     "branch_member_count": None if best is None else int(best["selected_count"]),
                     "support_ratio": None if best is None else best["selected_count"]/fold["selected_total"],
                     "applied_weight": 0.0, "bonus": float(row.rerank_bonus),
                     "final_score": float(row.branch_aware_score_raw)})
    return _rank(pd.DataFrame(rows))


def gated_rescue(fold, config: FusionConfig, lam: float):
    rows = []
    for cid, core in fold["core"].iterrows():
        core_score = float(core.coverage_adjusted_final_score_raw)
        branch_score, branch_rank, branch = _best_branch(cid, fold, config)
        gate = 0.0 if branch is None else _gate(branch, fold, config)
        advantage = 0.0 if branch_score is None else max(0.0, branch_score-core_score)
        bonus = lam * gate * advantage
        rows.append({"character_id": cid, "core_score": core_score, "core_rank": int(core.core_rank),
                     "best_branch_score": branch_score, "best_branch_rank": branch_rank,
                     "legacy_multi_branch_rank": fold["legacy_multi_rank"][cid],
                     "branch_confidence": None if branch is None else float(branch["confidence"]),
                     "branch_member_count": None if branch is None else int(branch["selected_count"]),
                     "support_ratio": None if branch is None else branch["selected_count"]/fold["selected_total"],
                     "applied_weight": lam*gate, "bonus": bonus, "final_score": core_score+bonus})
    return _rank(pd.DataFrame(rows))


def dynamic_blend(fold, config: FusionConfig, max_branch_weight: float):
    rows = []
    for cid, core in fold["core"].iterrows():
        core_score = float(core.coverage_adjusted_final_score_raw)
        branch_score, branch_rank, branch = _best_branch(cid, fold, config)
        weight = 0.0 if branch is None else max_branch_weight * _gate(branch, fold, config)
        final = core_score if branch_score is None else (1-weight)*core_score + weight*branch_score
        rows.append({"character_id": cid, "core_score": core_score, "core_rank": int(core.core_rank),
                     "best_branch_score": branch_score, "best_branch_rank": branch_rank,
                     "legacy_multi_branch_rank": fold["legacy_multi_rank"][cid],
                     "branch_confidence": None if branch is None else float(branch["confidence"]),
                     "branch_member_count": None if branch is None else int(branch["selected_count"]),
                     "support_ratio": None if branch is None else branch["selected_count"]/fold["selected_total"],
                     "applied_weight": weight, "bonus": final-core_score, "final_score": final})
    return _rank(pd.DataFrame(rows))


def reciprocal_rank_fusion(fold, config: FusionConfig, k: int):
    branches = eligible_branches(fold, config)
    rows = []
    for cid, core in fold["core"].iterrows():
        score = 1/(k+int(core.core_rank))
        best_score, best_rank, best = _best_branch(cid, fold, config)
        branch_weight = 0.0
        for branch in branches:
            weight = _gate(branch, fold, config)
            branch_weight = max(branch_weight, weight)
            score += weight/(k+int(branch["scores"].loc[cid, "branch_rank"]))
        rows.append({"character_id": cid, "core_score": float(core.coverage_adjusted_final_score_raw),
                     "core_rank": int(core.core_rank), "best_branch_score": best_score,
                     "best_branch_rank": best_rank, "legacy_multi_branch_rank": fold["legacy_multi_rank"][cid],
                     "branch_confidence": None if best is None else float(best["confidence"]),
                     "branch_member_count": None if best is None else int(best["selected_count"]),
                     "support_ratio": None if best is None else best["selected_count"]/fold["selected_total"],
                     "applied_weight": branch_weight, "bonus": None, "final_score": score})
    return _rank(pd.DataFrame(rows))


def candidate_union(fold, config: FusionConfig, top_k: int):
    """Retrieve Core/branch Top-K union, then gated rescue (lambda=1) within it."""
    candidate_ids = set(fold["core"].sort_values("core_rank").head(top_k).index)
    for branch in eligible_branches(fold, config):
        candidate_ids.update(branch["scores"].sort_values("branch_rank").head(top_k).index)
    scored = gated_rescue(fold, config, lam=1.0)
    inside = scored[scored.character_id.isin(candidate_ids)]
    outside = scored[~scored.character_id.isin(candidate_ids)].copy()
    # Outside the retrieval union cannot enter displayed competition, but remains
    # after the union so every positive still has a diagnostic final rank.
    return pd.concat([inside, outside.sort_values(["core_rank", "character_id"])], ignore_index=True)


def fusion_diagnostics(core_rank: int, final_rank: int, target_id: str,
                       ranking: pd.DataFrame, false_boost_threshold: int = 5):
    rescue5 = core_rank > 5 and final_rank <= 5
    rescue3 = core_rank > 3 and final_rank <= 3
    displaced = final_rank > core_rank
    false = ranking[(ranking.character_id != target_id) &
                    ((ranking.core_rank-ranking.index.to_series().add(1)) >= false_boost_threshold)] if displaced else ranking.iloc[0:0]
    return {"positive_rescue_3": rescue3, "positive_rescue_5": rescue5,
            "false_boost_count": len(false),
            "false_boost_rank_gain_sum": float((false.core_rank-(false.index+1)).sum()) if len(false) else 0.0,
            "false_boost_mean_rank_gain": float((false.core_rank-(false.index+1)).mean()) if len(false) else 0.0,
            "top3_false_boost": int(((false.index+1) <= 3).sum()),
            "top5_false_boost": int(((false.index+1) <= 5).sum())}
