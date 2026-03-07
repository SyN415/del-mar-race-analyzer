#!/usr/bin/env python3
"""Targeted tests for Santa Anita jockey dataset integration."""

import os
import unittest
from unittest.mock import patch

from race_prediction_engine import RacePredictionEngine


class TestSantaAnitaJockeyIntegration(unittest.TestCase):
    def setUp(self):
        self.engine = self._make_engine(enabled=False)

    def _make_engine(self, enabled: bool) -> RacePredictionEngine:
        with patch.dict(
            os.environ,
            {'ENABLE_TRACK_JOCKEY_RANKINGS': 'true' if enabled else 'false'},
            clear=False,
        ):
            return RacePredictionEngine()

    def test_track_rankings_are_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            engine = RacePredictionEngine()

        self.assertEqual(engine.track_jockey_rankings, {})
        self.assertIsNone(engine.get_track_jockey_stats("H I Berrios", {"track_id": "SA"}))

    def test_matches_abbreviated_jockey_name_to_saved_dataset(self):
        engine = self._make_engine(enabled=True)
        stats = engine.get_track_jockey_stats("H I Berrios", {"track_id": "SA"})

        self.assertIsNotNone(stats)
        self.assertEqual(stats["name"], "Hector Isaac Berrios")
        self.assertEqual(stats["rank"], 5)
        self.assertAlmostEqual(stats["points"], 83.7, places=1)

    def test_predict_race_uses_saved_santa_anita_stats(self):
        engine = self._make_engine(enabled=True)
        race = {
            "race_number": 1,
            "track_id": "SA",
            "race_type": "Allowance",
            "distance": "6f",
            "surface": "Dirt",
            "conditions": "",
            "horses": [
                {"name": "Fast Runner", "post_position": 1, "jockey": "J J Hernandez", "trainer": "Any Trainer"}
            ]
        }

        result = engine.predict_race(race, {"Fast Runner": {}})
        prediction = result["predictions"][0]

        self.assertIn("track_jockey_context", result)
        self.assertIn("track_jockey_stats", prediction)
        self.assertEqual(prediction["track_jockey_stats"]["name"], "Juan J. Hernandez")
        self.assertEqual(prediction["track_jockey_stats"]["rank"], 1)
        self.assertGreater(prediction["factors"]["jockey"], 90.0)

    def test_predict_race_does_not_apply_santa_anita_data_to_other_tracks(self):
        engine = self._make_engine(enabled=True)
        race = {
            "race_number": 1,
            "track_id": "DMR",
            "race_type": "Allowance",
            "distance": "6f",
            "surface": "Dirt",
            "conditions": "",
            "horses": [
                {"name": "Coast Runner", "post_position": 1, "jockey": "J J Hernandez", "trainer": "Any Trainer"}
            ]
        }

        result = engine.predict_race(race, {"Coast Runner": {}})
        prediction = result["predictions"][0]

        self.assertNotIn("track_jockey_context", result)
        self.assertNotIn("track_jockey_stats", prediction)
        self.assertEqual(prediction["factors"]["jockey"], 50.0)


if __name__ == "__main__":
    unittest.main()