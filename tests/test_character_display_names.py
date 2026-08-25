"""Preview-only Chinese display-name localization tests."""

import unittest
from pathlib import Path

import pandas as pd

from utils.tag_recommender_v6 import load_tag_characters


class CharacterDisplayNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = Path("data")
        cls.characters = load_tag_characters(
            data / "core_xp_tags_v6.csv",
            data / "core_xp_tags_v6_2_review.csv",
            data / "character_display_names_zh.csv",
            data / "series_display_names_zh.csv",
        )
        cls.catalog = pd.DataFrame(
            {
                "character_id": item.character_id,
                "shown": item.character_name,
                "display_title": item.game_title,
            }
            for item in cls.characters
        )
        cls.tag_rows = pd.read_csv(data / "core_xp_tags_v6.csv", dtype=str)
        cls.names = pd.read_csv(Path("data/character_display_names_zh.csv"))
        cls.series_names = pd.read_csv(Path("data/series_display_names_zh.csv"))

    def test_catalog_matches_current_tag_first_baseline(self):
        self.assertEqual(len(self.characters), 478)
        self.assertFalse(self.catalog["character_id"].duplicated().any())
        self.assertEqual(
            set(self.catalog["character_id"]),
            set(self.tag_rows["character_id"]),
        )

    def test_mapping_ids_are_unique_and_exist(self):
        self.assertFalse(self.names["character_id"].duplicated().any())
        self.assertTrue(set(self.names["character_id"]).issubset(
            set(self.catalog["character_id"])
        ))

    def test_amnesia_names_remain_english(self):
        amnesia_ids = {"C020", "C033", "C039", "C050"}
        self.assertFalse(amnesia_ids & set(self.names["character_id"]))
        actual = set(self.catalog.loc[
            self.catalog["character_id"].isin(amnesia_ids), "shown"
        ])
        self.assertEqual(actual, {"Shin", "Toma", "Ukyo", "Ikki"})

    def test_romanized_japanese_examples_have_chinese_display_names(self):
        mapping = dict(zip(self.names["character_id"], self.names["display_name_zh"]))
        self.assertEqual(mapping["C049"], "平知盛")
        self.assertEqual(mapping["C069"], "姬空木")
        self.assertEqual(mapping["C075"], "森鸥外")

    def test_mixed_name_titles_are_consistently_chinese(self):
        chinese_series = {"虔诚之花的晚钟", "终远的威尔修", "共生丘比特"}
        rows = self.catalog[self.catalog["display_title"].isin(chinese_series)]
        self.assertTrue(rows["shown"].str.contains(r"[^A-Za-z0-9 .,'’\-]").all())

    def test_series_variants_use_one_main_display_title(self):
        mapping = dict(zip(
            self.series_names["source_series"], self.series_names["display_title"]
        ))
        self.assertEqual(mapping["CLOCK ZERO ～终焉之一秒～"], "CLOCK ZERO")
        self.assertEqual(mapping["Steam Prison"], "蒸汽监狱")
        self.assertEqual(mapping["AMNESIA: Memories"], "失忆症")

    def test_nil_admirari_uses_only_chinese_main_title(self):
        target_ids = {"C011", "C029", "C067", "C068"}
        rows = self.catalog[self.catalog["character_id"].isin(target_ids)]
        self.assertEqual(set(rows["display_title"]), {"冷然之天秤"})
        names = dict(zip(self.names["character_id"], self.names["display_name_zh"]))
        self.assertEqual(names["C011"], "鸿上滉")


if __name__ == "__main__":
    unittest.main()
