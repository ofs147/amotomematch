"""Shared current-product fixtures and lightweight test-suite classification."""
from pathlib import Path

import pandas as pd
import pytest

from utils.tag_recommender_v6 import load_tag_characters


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

CURRENT_MODULES = {
    "test_ai_xp_interpreter_v6.py",
    "test_aoprofile_v1.py",
    "test_character_display_names.py",
    "test_current_product_contract.py",
    "test_result_ui_v6.py",
    "test_selection_ui_v6.py",
    "test_share_card_v6.py",
    "test_tag_recommender_v6.py",
}

ENVIRONMENT_MODULES = {
    "test_catalog_coverage_audit_v5_5.py",
    "test_character_roster_v5_1.py",
    "test_game_catalog_v5.py",
    "test_large_roster_expansion_v5_4.py",
    "test_priority_xp_bulk_v5_8.py",
    "test_roster_exception_resolution_v5_4_1.py",
    "test_roster_xp_pipeline_v5_3.py",
    "test_targeted_roster_expansion_v5_6.py",
    "test_targeted_roster_final_write_v5_6_2.py",
    "test_targeted_roster_resolution_v5_6_1.py",
    "test_xp_annotation_priority_v5_7.py",
}


@pytest.fixture(scope="session")
def current_characters():
    """The exact public selectable-character path used by the website."""
    return load_tag_characters(
        DATA / "core_xp_tags_v6.csv",
        DATA / "core_xp_tags_v6_2_review.csv",
        DATA / "character_display_names_zh.csv",
        DATA / "series_display_names_zh.csv",
    )


@pytest.fixture(scope="session")
def current_character_ids(current_characters):
    return {item.character_id for item in current_characters}


@pytest.fixture(scope="session")
def current_dictionary():
    rows = pd.read_csv(DATA / "core_xp_tag_dictionary_v6.csv", dtype=str, keep_default_na=False)
    return set(rows["canonical_tag"])


@pytest.fixture(scope="session")
def current_display_names():
    return pd.read_csv(DATA / "character_display_names_zh.csv", dtype=str, keep_default_na=False)


@pytest.fixture(scope="session")
def current_games(current_characters):
    return {item.game_title for item in current_characters}


def pytest_collection_modifyitems(items):
    """Classify tests without changing whether the full suite executes them."""
    for item in items:
        module_name = Path(str(item.fspath)).name
        if module_name in CURRENT_MODULES:
            item.add_marker(pytest.mark.current)
        else:
            item.add_marker(pytest.mark.legacy)
        if module_name in ENVIRONMENT_MODULES:
            item.add_marker(pytest.mark.environment)
            item.add_marker(pytest.mark.integration)
        if "ai" in module_name:
            item.add_marker(pytest.mark.ai)
        if "roster" in module_name:
            item.add_marker(pytest.mark.roster)
