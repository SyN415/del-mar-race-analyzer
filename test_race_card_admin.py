import unittest

from services.race_card_admin import extract_json_object, normalize_admin_results


class RaceCardAdminTests(unittest.TestCase):
    def test_extract_json_object_handles_fenced_json(self):
        payload = extract_json_object(
            """```json
            {"race_analyses": [{"race_number": 1, "predictions": [{"horse_name": "Alpha"}]}]}
            ```"""
        )

        self.assertEqual(payload["race_analyses"][0]["race_number"], 1)

    def test_normalize_admin_results_maps_predictions_and_summary(self):
        structured = {
            "overview": "Del Mar Friday card",
            "races": [
                {
                    "number": 1,
                    "type": "Allowance",
                    "distance": "6f",
                    "surface": "Dirt",
                    "entries": [
                        {"horse": "Alpha", "post": 1, "jockey": "A. Rider", "trainer": "T. One", "rating": 92},
                        {"horse": "Bravo", "post": 4, "jockey": "B. Rider", "trainer": "T. Two", "rating": 84},
                    ],
                }
            ],
        }

        results = normalize_admin_results(
            structured,
            race_date="2026-03-13",
            track_id="DMR",
            llm_model="x-ai/grok-4.20-beta",
            source_urls=["https://example.com/card"],
            admin_notes="Imported from notes",
            analysis_duration_seconds=1.25,
        )

        self.assertEqual(results["summary"]["total_races"], 1)
        self.assertEqual(results["race_analyses"][0]["predictions"][0]["horse_name"], "Alpha")
        self.assertEqual(results["race_analyses"][0]["top_pick"]["horse_name"], "Alpha")
        self.assertEqual(results["admin_metadata"]["model_used"], "x-ai/grok-4.20-beta")
        self.assertAlmostEqual(
            sum(pred["win_probability"] for pred in results["race_analyses"][0]["predictions"]),
            100.0,
            places=1,
        )


if __name__ == "__main__":
    unittest.main()