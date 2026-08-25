"""Small, authoritative contracts for the currently selectable product."""
from collections import defaultdict
from pathlib import Path

import pandas as pd

from utils.tag_recommender_v6 import build_fallback_result


DATA = Path(__file__).resolve().parents[1] / "data"


def test_public_pool_is_authoritative_unique_and_dictionary_valid(
    current_characters, current_character_ids, current_dictionary,
):
    production = pd.read_csv(DATA / "core_xp_tags_v6.csv", dtype=str, keep_default_na=False)
    assert len(current_characters) == len(current_character_ids) == len(production) == 478
    assert current_character_ids == set(production["character_id"])
    assert all(2 <= len(item.tags) <= 3 for item in current_characters)
    assert all(set(item.tags) <= current_dictionary for item in current_characters)


def test_game_first_catalog_has_no_empty_or_duplicate_identity(current_characters, current_games):
    by_game = defaultdict(list)
    for item in current_characters:
        by_game[item.game_title].append(item.character_id)
    assert current_games
    assert all(title.strip() and ids for title, ids in by_game.items())
    assert all(len(ids) == len(set(ids)) for ids in by_game.values())
    assert "蒸汽监狱" in current_games
    assert "Steam Prison" not in current_games


def test_current_recommendation_contract_is_evidence_backed_and_spoiler_safe(current_characters):
    by_id = {item.character_id: item for item in current_characters}
    selected = [by_id[item] for item in ("C005", "C087", "C001", "C077", "C004")]
    result = build_fallback_result(selected, current_characters)
    selected_ids = {item.character_id for item in selected}
    recommendation_ids = {
        item.character_id for item in [*result.high_matches, *result.explorations]
    }
    assert 1 <= len(result.heart_signals) <= 3
    assert len(result.high_matches) == 5
    assert len(result.explorations) == 3
    assert not (selected_ids & recommendation_ids)
    assert len(recommendation_ids) == 8
    assert not ({"C336", "C356"} & recommendation_ids)
    assert all(signal.tags and signal.supporting_character_ids for signal in result.heart_signals)
    assert all(card.reason.strip() for card in [*result.high_matches, *result.explorations])


def test_display_mapping_is_a_subset_of_the_live_directory(
    current_display_names, current_character_ids,
):
    assert not current_display_names["character_id"].duplicated().any()
    assert set(current_display_names["character_id"]) <= current_character_ids


def test_heat_tag_uses_the_narrow_highly_expressive_threshold():
    production = pd.read_csv(DATA / "core_xp_tags_v6.csv", dtype=str, keep_default_na=False)
    tags_by_id = {
        row["character_id"]: {
            row["core_tag_1"], row["core_tag_2"], row["core_tag_3"],
        }
        for _, row in production.iterrows()
    }
    assert "热血" in tags_by_id["C004"]  # 榎本峰雄 is the calibration anchor.
    assert all("热血" not in tags_by_id[character_id] for character_id in (
        "C114",  # 斐伊
        "C139",  # 细波艾斯
        "C222",  # 尤里乌斯·福特纳
        "C384",  # 尤纳卡·吉斯贝尔特
        "C034", "C044", "C076", "C079", "C089", "C105", "C154",
        "C160", "C168", "C184", "C186", "C193", "C265", "C267",
        "C269", "C282", "C287", "C295", "C308", "C312", "C322",
        "C352", "C367", "C392", "C435", "C443",
    ))
    assert all("热血" in tags_by_id[character_id] for character_id in (
        "C143", "C298", "C330", "C338", "C364", "C426", "C480", "C490",
    ))
