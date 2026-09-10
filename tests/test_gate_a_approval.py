from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import unittest
from unittest.mock import patch

from scripts.record_gate_a_approval import (
    GateAApprovalError,
    canonical_hash,
    record_approval,
)


class GateAApprovalTests(unittest.TestCase):
    def verified(self, root: Path) -> dict:
        return {
            "run_dir": root,
            "artifact_sha256": "a" * 64,
            "base_artifact_sha256": "b" * 64,
            "selected_candidate_ids": ["e1", "e2"],
        }

    def review(self, root: Path) -> dict:
        review_path = root / "gate-a-review.md"
        review_path.write_bytes(b"review\n")
        return {
            "approval_recorded": False,
            "artifact_sha256": "a" * 64,
            "review_file": str(review_path),
            "review_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
            "rubric_version": "0.2",
            "portfolio_rubric_version": "0.2",
        }

    def test_records_self_hashed_approval_without_mutating_summary(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "summary.json").write_text('{"unchanged": true}\n', encoding="utf-8")
            review = self.review(root)
            (root / "gate-a-review-receipt.json").write_text(
                json.dumps(review), encoding="utf-8"
            )
            fixed = datetime(2026, 9, 10, 22, 42, tzinfo=timezone.utc)
            with patch(
                "scripts.record_gate_a_approval.verify_enriched_chain",
                return_value=self.verified(root),
            ):
                receipt = record_approval(
                    root,
                    artifact_sha256="a" * 64,
                    approved_by="Witold Przygoda",
                    now_utc=fixed,
                )
            self.assertEqual(receipt["decision"], "APPROVE")
            self.assertEqual(receipt["approved_by"], "Witold Przygoda")
            saved_hash = receipt["approval_sha256"]
            unhashed = {k: v for k, v in receipt.items() if k != "approval_sha256"}
            self.assertEqual(saved_hash, canonical_hash(unhashed))
            self.assertEqual(
                (root / "summary.json").read_text(encoding="utf-8"),
                '{"unchanged": true}\n',
            )

    def test_accepts_legacy_receipt_when_only_line_endings_changed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            review_path = root / "gate-a-review.md"
            review_path.write_bytes(b"line one\r\nline two\r\n")
            legacy_lf = b"line one\nline two\n"
            review = {
                "approval_recorded": False,
                "artifact_sha256": "a" * 64,
                "review_file": str(review_path),
                "review_sha256": hashlib.sha256(legacy_lf).hexdigest(),
                "rubric_version": "0.2",
                "portfolio_rubric_version": "0.2",
            }
            (root / "gate-a-review-receipt.json").write_text(
                json.dumps(review), encoding="utf-8"
            )
            with patch(
                "scripts.record_gate_a_approval.verify_enriched_chain",
                return_value=self.verified(root),
            ):
                receipt = record_approval(
                    root,
                    artifact_sha256="a" * 64,
                    approved_by="Witold Przygoda",
                    now_utc=datetime(2026, 9, 10, 22, 42, tzinfo=timezone.utc),
                )
            self.assertEqual(receipt["decision"], "APPROVE")
            self.assertEqual(receipt["review_sha256"], review["review_sha256"])

    def test_rejects_real_review_content_change(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            review_path = root / "gate-a-review.md"
            review_path.write_bytes(b"changed content\r\n")
            review = {
                "approval_recorded": False,
                "artifact_sha256": "a" * 64,
                "review_file": str(review_path),
                "review_sha256": hashlib.sha256(b"original content\n").hexdigest(),
                "rubric_version": "0.2",
                "portfolio_rubric_version": "0.2",
            }
            (root / "gate-a-review-receipt.json").write_text(
                json.dumps(review), encoding="utf-8"
            )
            with patch(
                "scripts.record_gate_a_approval.verify_enriched_chain",
                return_value=self.verified(root),
            ):
                with self.assertRaises(GateAApprovalError):
                    record_approval(
                        root,
                        artifact_sha256="a" * 64,
                        approved_by="Witold Przygoda",
                    )

    def test_rejects_wrong_artifact_hash(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with patch(
                "scripts.record_gate_a_approval.verify_enriched_chain",
                return_value=self.verified(root),
            ):
                with self.assertRaises(GateAApprovalError):
                    record_approval(
                        root,
                        artifact_sha256="c" * 64,
                        approved_by="Witold Przygoda",
                    )

    def test_idempotent_same_approval(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            review = self.review(root)
            (root / "gate-a-review-receipt.json").write_text(
                json.dumps(review), encoding="utf-8"
            )
            fixed = datetime(2026, 9, 10, 22, 42, tzinfo=timezone.utc)
            with patch(
                "scripts.record_gate_a_approval.verify_enriched_chain",
                return_value=self.verified(root),
            ):
                first = record_approval(
                    root,
                    artifact_sha256="a" * 64,
                    approved_by="Witold Przygoda",
                    now_utc=fixed,
                )
                second = record_approval(
                    root,
                    artifact_sha256="a" * 64,
                    approved_by="Witold Przygoda",
                    now_utc=fixed,
                )
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
