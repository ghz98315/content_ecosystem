import unittest

from image_style_profiles import PROFILES, get_profile, historical_era_lock, history_visual_safe
from stages.image import _build_grid_prompt


class ImageStyleProfileTests(unittest.TestCase):
    def test_each_history_style_has_an_independent_profile(self):
        self.assertEqual(
            {"history_heroic", "history_ink_scroll", "history_gongbi_cinematic"},
            set(PROFILES),
        )
        directions = {profile.direction for profile in PROFILES.values()}
        self.assertEqual(3, len(directions))

    def test_history_profiles_are_available_only_to_social_science(self):
        for style_id in PROFILES:
            self.assertIsNotNone(get_profile(style_id, "social_science"))
            self.assertIsNone(get_profile(style_id, "health"))
            self.assertIsNone(get_profile(style_id, "education"))

    def test_unknown_style_has_no_profile(self):
        self.assertIsNone(get_profile("missing-style", "social_science"))

    def test_grid_prompt_uses_selected_history_profile(self):
        heroic = _build_grid_prompt(["朝堂议政"], "social_science", "history_heroic")
        ancient = _build_grid_prompt(["庭院交谈"], "social_science", "history_ink_scroll")
        republic = _build_grid_prompt(["书房长幼对谈"], "social_science", "history_gongbi_cinematic")
        self.assertIn("正统帝王画卷", heroic)
        self.assertIn("古典世情风俗画", ancient)
        self.assertIn("民国及近代世情风俗画", republic)
        self.assertNotIn("民国及近代世情风俗画", heroic)
        self.assertNotIn("古典世情风俗画", republic)
        self.assertIn("每格按9:16竖版画面构图", heroic)

    def test_historical_era_lock_is_conservative(self):
        self.assertIn("秦汉", historical_era_lock("秦汉朝堂议政"))
        self.assertIn("民国及近代", historical_era_lock("民国书房长衫对谈"))
        self.assertIn("古代未定朝代", historical_era_lock("一段古代故事"))

    def test_history_style_cannot_leak_into_other_categories(self):
        health = _build_grid_prompt(["日常健康管理"], "health", "history_heroic")
        business = _build_grid_prompt(["团队复盘"], "education", "history_gongbi_cinematic")
        self.assertNotIn("正统帝王画卷", health)
        self.assertNotIn("民国及近代世情风俗画", business)
        self.assertNotIn("历史", health)
        self.assertNotIn("历史", business)

    def test_republic_profile_requires_people_and_excludes_ancient_setting(self):
        profile = get_profile("history_gongbi_cinematic", "social_science")
        assert profile is not None
        self.assertIn("至少两位可见人物", profile.positive)
        self.assertIn("无人物的静物", profile.negative)
        self.assertIn("古代宫殿", profile.negative)

    def test_heroic_profile_is_not_limited_to_court_scenes(self):
        profile = get_profile("history_heroic", "social_science")
        assert profile is not None
        self.assertIn("九格场景必须有明显变化", profile.positive)
        self.assertIn("帝王出巡", profile.positive)
        self.assertIn("农耕水利与市井民生", profile.positive)
        self.assertIn("朝堂最多作为其中一至两格", profile.positive)
        self.assertIn("远景长卷", profile.positive)

    def test_sensitive_history_visuals_are_reframed_before_prompt_generation(self):
        safe = history_visual_safe("中国国家分裂、展示中国地图和现代中国政治人物")
        self.assertIn("国家和睦友好相处", safe)
        self.assertIn("无字山水与地域交流意象", safe)
        self.assertNotIn("四分五裂", safe)
        self.assertNotIn("中国地图", safe)
        prompt = _build_grid_prompt(["中国国家分裂、展示中国地图和现代中国政治人物"], "social_science", "history_heroic")
        self.assertNotIn("中国地图", prompt)
        self.assertIn("禁止地图、疆域轮廓", prompt)

    def test_ancient_division_uses_court_and_battle_metaphors_not_maps(self):
        safe = history_visual_safe("东汉末年天下分裂，诸侯各据一方")
        self.assertIn("古代朝廷失序", safe)
        self.assertIn("战场混乱", safe)
        self.assertNotIn("地图", safe)

    def test_modern_map_fragmentation_is_reframed_as_neutral_exchange(self):
        safe = history_visual_safe("中国地图四分五裂，展示边界线")
        self.assertIn("无字山水与地域交流意象", safe)
        self.assertNotIn("中国地图", safe)
        self.assertNotIn("边界线", safe)


if __name__ == "__main__":
    unittest.main()
