from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.record_gate_a_approval import canonical_hash
from scripts.record_m3a_selection import M3aSelectionError, record_selection


class M3aSelectionTests(unittest.TestCase):
    def verified(self, root: Path) -> dict:
        variants = {
            "artifact_sha256": "a" * 64,
            "gate_a_approval_sha256": "b" * 64,
            "variants": [
                {"variant_id": "v1", "visual_strategy": "sequential_run"},
                {"variant_id": "v2", "visual_strategy": "state_model"},
            ],
        }
        summary = {
            "artifact_sha256": "a" * 64,
            "gate_a_approval_sha256": "b" * 64,
            "scene_variants_sha256": canonical_hash(variants),
        }
        return {"run_dir": root, "summary": summary, "variants": variants}

    def test_records_exact_selected_variant_hash(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            fixed = datetime(2026, 9, 10, 23, 5, tzinfo=timezone.utc)
            with patch("scripts.record_m3a_selection.verify_m3a", return_value=self.verified(root)):
                receipt = record_selection(root, variant_id="v2", selected_by="Witold Przygoda", now_utc=fixed)
            self.assertEqual(receipt["decision"], "SELECT")
            self.assertEqual(receipt["selected_variant_id"], "v2")
            self.assertEqual(
                receipt["selected_variant_sha256"],
                canonical_hash({"variant_id": "v2", "visual_strategy": "state_model"}),
            )
            saved = receipt["selection_sha256"]
            self.assertEqual(saved, canonical_hash({k: v for k, v in receipt.items() if k != "selection_sha256"}))

    def test_same_selection_is_idempotent(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            fixed = datetime(2026, 9, 10, 23, 5, tzinfo=timezone.utc)
            with patch("scripts.record_m3a_selection.verify_m3a", return_value=self.verified(root)):
                first = record_selection(root, variant_id="v2", selected_by="Witold Przygoda", now_utc=fixed)
                second = record_selection(root, variant_id="v2", selected_by="Witold Przygoda", now_utc=fixed)
            self.assertEqual(first, second)

    def test_conflicting_second_selection_is_rejected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            fixed = datetime(2026, 9, 10, 23, 5, tzinfo=timezone.utc)
            with patch("scripts.record_m3a_selection.verify_m3a", return_value=self.verified(root)):
                record_selection(root, variant_id="v2", selected_by="Witold Przygoda", now_utc=fixed)
                with self.assertRaises(M3aSelectionError):
                    record_selection(root, variant_id="v1", selected_by="Witold Przygoda", now_utc=fixed)

    def test_unknown_variant_is_rejected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with patch("scripts.record_m3a_selection.verify_m3a", return_value=self.verified(root)):
                with self.assertRaises(M3aSelectionError):
                    record_selection(root, variant_id="v9", selected_by="Witold Przygoda")


if __name__ == "__main__":
    unittest.main()
