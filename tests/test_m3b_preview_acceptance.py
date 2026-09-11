from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.record_gate_a_approval import canonical_hash
from scripts.record_m3b_preview_acceptance import (
    M3bPreviewAcceptanceError,
    record_acceptance,
)


class M3bPreviewAcceptanceTests(unittest.TestCase):
    def verified(self, run_dir: Path) -> dict:
        return {
            "run_dir": run_dir.resolve(),
            "summary": {
                "artifact_sha256": "artifact",
                "gate_a_approval_sha256": "gate-a",
                "m3a_selection_sha256": "m3a",
                "visual_fact_catalog_sha256": "catalog",
                "scene_plan_sha256": "scene-plan",
            },
        }

    def test_records_hash_bound_non_gate_b_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            now = datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc)
            with patch(
                "scripts.record_m3b_preview_acceptance.verify_m3b",
                return_value=self.verified(run_dir),
            ):
                receipt = record_acceptance(run_dir, accepted_by="Witold Przygoda", now_utc=now)

            self.assertEqual(receipt["decision"], "ACCEPT_FOR_SILENT_PREVIEW_BUILD")
            self.assertEqual(receipt["scene_plan_sha256"], "scene-plan")
            self.assertFalse(receipt["gate_b"])
            self.assertFalse(receipt["audio_called"])
            self.assertFalse(receipt["render_called"])
            saved = json.loads((run_dir / "m3b-preview-acceptance.json").read_text(encoding="utf-8"))
            saved_hash = saved.pop("acceptance_sha256")
            self.assertEqual(saved_hash, canonical_hash(saved))

    def test_same_acceptance_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            now = datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc)
            with patch(
                "scripts.record_m3b_preview_acceptance.verify_m3b",
                return_value=self.verified(run_dir),
            ):
                first = record_acceptance(run_dir, accepted_by="Witold Przygoda", now_utc=now)
                second = record_acceptance(run_dir, accepted_by="Witold Przygoda")
            self.assertEqual(first, second)

    def test_conflicting_acceptor_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            with patch(
                "scripts.record_m3b_preview_acceptance.verify_m3b",
                return_value=self.verified(run_dir),
            ):
                record_acceptance(run_dir, accepted_by="Witold Przygoda")
                with self.assertRaises(M3bPreviewAcceptanceError):
                    record_acceptance(run_dir, accepted_by="Other Person")


if __name__ == "__main__":
    unittest.main()
