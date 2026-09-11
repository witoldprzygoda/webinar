from __future__ import annotations

import unittest

from flows.m3c0_visual_calibration import _scene_srt, _variant_rows


class M3c0VisualCalibrationTests(unittest.TestCase):
    def test_scene_srt_uses_exact_narration_and_local_time(self):
        props = {
            "fps": 30,
            "narration": [
                {"fragment_id": "frag-01", "text": "Pierwszy tekst."},
                {"fragment_id": "frag-02", "text": "Drugi tekst."},
            ],
            "timing": {
                "fragments": [
                    {"fragment_id": "frag-01", "scene_id": "s01", "start_frame": 120, "end_frame": 180},
                    {"fragment_id": "frag-02", "scene_id": "s01", "start_frame": 180, "end_frame": 270},
                ]
            },
        }
        scene_timing = {
            "scene_id": "s01",
            "fragment_ids": ["frag-01", "frag-02"],
        }
        srt, count = _scene_srt(props=props, scene_timing=scene_timing, scene_start=90)
        self.assertEqual(count, 2)
        self.assertIn("00:00:01,000 --> 00:00:03,000", srt)
        self.assertIn("Pierwszy tekst.", srt)
        self.assertIn("00:00:03,000 --> 00:00:06,000", srt)
        self.assertIn("Drugi tekst.", srt)

    def test_variant_family_depends_on_code_facts(self):
        config = {
            "intro_variants": [{"variant_id": "intro"}],
            "repl_variants": [{"variant_id": "repl"}],
        }
        intro = {"visible_elements": [{"kind": "label", "content": "A"}]}
        repl = {"visible_elements": [{"kind": "code", "content": "8 / 5"}]}
        self.assertEqual(_variant_rows(config, intro)[0]["variant_id"], "intro")
        self.assertEqual(_variant_rows(config, repl)[0]["variant_id"], "repl")


if __name__ == "__main__":
    unittest.main()
