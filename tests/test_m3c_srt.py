from __future__ import annotations

import unittest

from scripts.generate_preview_srt import PreviewSrtError, build_srt


class PreviewSrtTests(unittest.TestCase):
    def test_builds_srt_from_preview_timing_and_approved_narration(self):
        props = {
            "fps": 30,
            "audio_enabled": False,
            "narration": [
                {"fragment_id": "f1", "text": "Pierwszy fragment."},
                {"fragment_id": "f2", "text": "Drugi fragment."},
            ],
            "timing": {
                "timing_kind": "TEMPORARY_ESTIMATE_FOR_SILENT_PREVIEW",
                "fragments": [
                    {"fragment_id": "f1", "start_frame": 0, "end_frame": 45},
                    {"fragment_id": "f2", "start_frame": 45, "end_frame": 90},
                ],
            },
        }
        result = build_srt(props)
        self.assertIn("00:00:00,000 --> 00:00:01,500", result)
        self.assertIn("00:00:01,500 --> 00:00:03,000", result)
        self.assertIn("Pierwszy fragment.", result)
        self.assertIn("Drugi fragment.", result)

    def test_rejects_missing_timed_fragment(self):
        props = {
            "fps": 30,
            "narration": [
                {"fragment_id": "f1", "text": "Pierwszy fragment."},
                {"fragment_id": "f2", "text": "Drugi fragment."},
            ],
            "timing": {
                "timing_kind": "TEMPORARY_ESTIMATE_FOR_SILENT_PREVIEW",
                "fragments": [
                    {"fragment_id": "f1", "start_frame": 0, "end_frame": 30},
                ],
            },
        }
        with self.assertRaises(PreviewSrtError):
            build_srt(props)


if __name__ == "__main__":
    unittest.main()
