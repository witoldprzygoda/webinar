from __future__ import annotations

import copy
import unittest

from flows.m3c_preview import compile_preview_timing, validate_preview_payload


class M3cPreviewTests(unittest.TestCase):
    def config(self) -> dict:
        return {
            "fps": 30,
            "words_per_minute": 120,
            "minimum_fragment_seconds": 3.0,
            "scene_lead_in_seconds": 0.5,
            "scene_tail_seconds": 0.5,
            "minimum_beat_spacing_frames": 4,
        }

    def artifact(self) -> dict:
        return {
            "narration": [
                {"fragment_id": "frag-01", "text": "Pierwszy fragment pokazuje wartość i jej typ."},
                {"fragment_id": "frag-02", "text": "Drugi fragment pokazuje wynik i stan sesji."},
            ]
        }

    def scene_plan(self) -> dict:
        return {
            "lesson_title": "Test",
            "scenes": [
                {
                    "scene_id": "s01",
                    "narration_fragment_ids": ["frag-01", "frag-02"],
                    "visible_elements": [
                        {"element_id": "e1", "content": "A"},
                        {"element_id": "e2", "content": "B"},
                    ],
                    "beats": [
                        {
                            "beat_id": "b1",
                            "narration_fragment_id": "frag-01",
                            "anchor_text": "Pierwszy fragment",
                            "focus_target_id": "e1",
                            "reveals": ["e1"],
                        },
                        {
                            "beat_id": "b2",
                            "narration_fragment_id": "frag-01",
                            "anchor_text": "jej typ",
                            "focus_target_id": "e2",
                            "reveals": ["e2"],
                        },
                        {
                            "beat_id": "b3",
                            "narration_fragment_id": "frag-02",
                            "anchor_text": "Drugi fragment",
                            "focus_target_id": "e2",
                            "reveals": [],
                        },
                    ],
                }
            ],
        }

    def test_timing_is_monotonic_and_temporary(self):
        timing = compile_preview_timing(
            artifact=self.artifact(), scene_plan=self.scene_plan(), config=self.config()
        )
        self.assertEqual(timing["timing_kind"], "TEMPORARY_ESTIMATE_FOR_SILENT_PREVIEW")
        self.assertTrue(timing["replace_with_audio_alignment"])
        self.assertGreater(timing["total_frames"], 0)
        starts = [row["start_frame"] for row in timing["beats"]]
        self.assertEqual(starts, sorted(starts))
        self.assertGreaterEqual(starts[1] - starts[0], 4)
        self.assertLess(timing["fragments"][0]["end_frame"], timing["fragments"][1]["end_frame"])

    def test_same_inputs_produce_same_timing_hash(self):
        first = compile_preview_timing(
            artifact=self.artifact(), scene_plan=self.scene_plan(), config=self.config()
        )
        second = compile_preview_timing(
            artifact=self.artifact(), scene_plan=self.scene_plan(), config=self.config()
        )
        self.assertEqual(first, second)

    def test_payload_rejects_audio_or_render(self):
        timing = compile_preview_timing(
            artifact=self.artifact(), scene_plan=self.scene_plan(), config=self.config()
        )
        base = {
            "audio_enabled": False,
            "render_requested": False,
            "timing": timing,
            "scene_plan": self.scene_plan(),
        }
        validate_preview_payload(base)
        bad_audio = copy.deepcopy(base)
        bad_audio["audio_enabled"] = True
        with self.assertRaises(Exception):
            validate_preview_payload(bad_audio)
        bad_render = copy.deepcopy(base)
        bad_render["render_requested"] = True
        with self.assertRaises(Exception):
            validate_preview_payload(bad_render)


if __name__ == "__main__":
    unittest.main()
