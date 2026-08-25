"""AOMatch v2.4 offline-only salience and ranking experiments.

This module deliberately has no imports from the Preview/UI.  It accepts explicit
reviewer preference sets; it never manufactures positives from character data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from typing import Iterable, Mapping, Sequence

import pandas as pd

from utils.data_utils import normalize_numeric_score, parse_tags
from utils.profile_v2_1 import build_xp_profile_v2_1
from utils.recommender_v2_1 import calculate_candidate_layer_coverage, shrink_similarity
from utils.schema import LAYERS, MATCH_COMPONENT_WEIGHTS, NUMERIC_FEATURES_BY_LAYER, TAG_FIELDS_BY_LAYER


CURRENT_WEIGHTS = dict(zip(LAYERS, (0.15, 0.25, 0.25, 0.35)))
PREFERRED_WEIGHTS = dict(zip(LAYERS, (0.10, 0.25, 0.25, 0.40)))


@dataclass(frozen=True)
class SalienceConfig:
    neutral: float = 3.0
    scale_radius: float = 2.0
    max_std: float = 2.0
    extremeness_floor: float = 0.4
    extremeness_power: float = 1.0
    minimum_weight: float = 0.0


def layer_weight_grid() -> list[dict[str, float]]:
    axes = ((.05, .10, .15), (.20, .25, .30), (.20, .25, .30), (.35, .40, .45, .50))
    return [dict(zip(LAYERS, xs)) for xs in product(*axes) if abs(sum(xs) - 1) < 1e-9]


def feature_salience(selected: pd.DataFrame, config: SalienceConfig = SalienceConfig()):
    """Return interpretable components and weights, normalized within each layer.

    raw = coverage * consistency * (floor + (1-floor) * extremeness**power)
    Layer normalization makes available feature weights sum to one.
    """
    output = {}
    total = len(selected)
    for layer in LAYERS:
        details = {}
        for feature in NUMERIC_FEATURES_BY_LAYER[layer]:
            values = pd.to_numeric(selected[feature], errors="coerce").dropna()
            coverage = len(values) / total
            mean = float(values.mean()) if len(values) else config.neutral
            std = float(values.std(ddof=0)) if len(values) else config.max_std
            consistency = max(0.0, 1 - std / config.max_std)
            extremeness = min(1.0, abs(mean - config.neutral) / config.scale_radius)
            raw = coverage * consistency * (config.extremeness_floor +
                  (1 - config.extremeness_floor) * extremeness ** config.extremeness_power)
            details[feature] = {"coverage": coverage, "mean": mean, "std": std,
                "consistency": consistency, "extremeness": extremeness,
                "raw_salience": max(config.minimum_weight, raw)}
        denom = sum(d["raw_salience"] for d in details.values())
        for detail in details.values():
            detail["weight"] = detail["raw_salience"] / denom if denom else 1 / len(details)
        output[layer] = details
    return output


def _weighted_available(values, weights):
    pairs = [(v, weights[k]) for k, v in values.items() if v is not None]
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs) if pairs else None


def _score(profile, candidate, salience, layer_weights):
    raw_layers, adjusted_layers, coverages = {}, {}, {}
    for layer in LAYERS:
        numeric = {}
        for feature in NUMERIC_FEATURES_BY_LAYER[layer]:
            left = normalize_numeric_score(profile[layer]["numeric"].get(feature))
            right = normalize_numeric_score(candidate.get(feature))
            numeric[feature] = None if left is None or right is None else 1 - abs(left-right)
        numeric_score = _weighted_available(numeric, {f: salience[layer][f]["weight"] for f in numeric})

        tag_scores = {}
        for field in TAG_FIELDS_BY_LAYER[layer]:
            frequencies = profile[layer]["tags"][field].get("frequencies", {})
            candidate_tags = parse_tags(candidate.get(field))
            if not frequencies or not candidate_tags:
                tag_scores[field] = None
                continue
            # global_support is support_count / all selected, not conditional field frequency.
            union = set(frequencies) | candidate_tags
            num = sum(min(float(frequencies.get(t, {}).get("global_support", 0)), float(t in candidate_tags)) for t in union)
            den = sum(max(float(frequencies.get(t, {}).get("global_support", 0)), float(t in candidate_tags)) for t in union)
            tag_scores[field] = num / den if den else None
        tag_score = _weighted_available(tag_scores, {f: 1 for f in tag_scores})
        raw = _weighted_available({"numeric": numeric_score, "tag": tag_score}, MATCH_COMPONENT_WEIGHTS[layer])
        coverage = calculate_candidate_layer_coverage(layer, profile[layer], candidate)["layer_coverage"]
        raw_layers[layer], coverages[layer] = raw, coverage
        adjusted_layers[layer] = shrink_similarity(raw, coverage)
    raw_final = _weighted_available(raw_layers, layer_weights) or 0
    adjusted_final = sum(adjusted_layers[x] * layer_weights[x] for x in LAYERS)
    return raw_final * 100, adjusted_final * 100, sum(coverages[x] * layer_weights[x] for x in LAYERS)


def rank_candidates(characters, selected_ids, layer_weights=CURRENT_WEIGHTS, use_salience=False,
                    salience_config=SalienceConfig()):
    selected = characters[characters.character_id.isin(selected_ids)]
    if len(selected) != len(set(selected_ids)):
        raise ValueError("selected_ids contains an unknown or duplicate character")
    profile = build_xp_profile_v2_1(selected)
    salience = feature_salience(selected, salience_config) if use_salience else {
        layer: {f: {"weight": 1/len(NUMERIC_FEATURES_BY_LAYER[layer])} for f in NUMERIC_FEATURES_BY_LAYER[layer]}
        for layer in LAYERS}
    rows = []
    for _, candidate in characters[~characters.character_id.isin(selected_ids)].iterrows():
        raw, adjusted, coverage = _score(profile, candidate, salience, layer_weights)
        rows.append({"character_id": candidate.character_id, "character_name": candidate.character_name,
                     "raw_match": raw, "adjusted_match": adjusted, "coverage": coverage})
    return pd.DataFrame(rows).sort_values(["adjusted_match", "character_id"], ascending=[False, True]).reset_index(drop=True)


def evaluate(characters: pd.DataFrame, preference_sets: Mapping[str, Sequence[str]],
             layer_weights=CURRENT_WEIGHTS, use_salience=False, salience_config=SalienceConfig()):
    """LOO evaluation. Each set must contain 4 or 5 explicit liked characters."""
    trials = []
    for reviewer, likes in preference_sets.items():
        if len(likes) not in (4, 5) or len(set(likes)) != len(likes):
            raise ValueError(f"{reviewer}: expected 4 or 5 unique liked characters")
        for target in likes:
            selected = [x for x in likes if x != target]
            ranked = rank_candidates(characters, selected, layer_weights, use_salience, salience_config)
            hit = ranked.index[ranked.character_id == target]
            if len(hit) != 1:
                raise ValueError(f"{reviewer}: unknown positive target {target}")
            rank = int(hit[0]) + 1
            row = ranked.iloc[rank-1]
            spread = float(ranked.iloc[0].adjusted_match - ranked.iloc[min(4, len(ranked)-1)].adjusted_match)
            trials.append({"reviewer": reviewer, "target": target, "selected": ";".join(selected),
                "rank": rank, "raw_match": row.raw_match, "adjusted_match": row.adjusted_match,
                "hit_at_1": rank <= 1, "hit_at_3": rank <= 3, "hit_at_5": rank <= 5,
                "reciprocal_rank": 1/rank, "top5_spread": spread})
    detail = pd.DataFrame(trials)
    summary = {"trials": len(detail), "hit_at_1": detail.hit_at_1.mean(),
        "hit_at_3": detail.hit_at_3.mean(), "hit_at_5": detail.hit_at_5.mean(),
        "mrr": detail.reciprocal_rank.mean(), "positive_mean_rank": detail["rank"].mean(),
        "top5_spread": detail.top5_spread.mean(), "positive_raw_match": detail.raw_match.mean(),
        "positive_adjusted_match": detail.adjusted_match.mean(), "weights": dict(layer_weights),
        "salience": use_salience, "salience_config": asdict(salience_config)}
    return summary, detail


def compare_required_experiments(characters, preference_sets, config=SalienceConfig()):
    variants = {"Baseline": (CURRENT_WEIGHTS, False), "Experiment A": (PREFERRED_WEIGHTS, False),
                "Experiment B": (CURRENT_WEIGHTS, True), "Experiment C": (PREFERRED_WEIGHTS, True)}
    return {name: evaluate(characters, preference_sets, weights, salience, config)
            for name, (weights, salience) in variants.items()}
