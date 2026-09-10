from __future__ import annotations

import unittest

from scripts.gate_a_review_enriched import build_enriched_markdown


class EnrichedGateAReviewTests(unittest.TestCase):
    def test_markdown_marks_enrichment_and_both_evidence_streams(self):
        verified = {
            "summary": {
                "lesson_id": "lesson",
                "audience_profile": "technical_competent",
            },
            "artifact": {
                "title": "T",
                "narration": [
                    {"fragment_id": "f1", "text": "Core."},
                    {"fragment_id": "enr-1", "text": "Dodatek."},
                ],
                "enrichment": {
                    "integration_map": [{
                        "candidate_id": "c1", "fragment_ids": ["enr-1"], "claim_ids": ["claim-1"],
                    }],
                },
            },
            "base_artifact_sha256": "a" * 64,
            "artifact_sha256": "b" * 64,
            "selected_candidate_ids": ["c1"],
            "core_evidence": {
                "runtime": {"implementation": "CPython", "version": "3.14.7"},
            },
            "core_evidence_sha256": "c" * 64,
            "enrichment_evidence": {
                "results": [{
                    "candidate_id": "c1", "mode": "python_cli", "code": "print(2 ** 3)",
                    "pass": True, "actual_stdout": "8\n",
                }],
            },
            "enrichment_evidence_sha256": "d" * 64,
            "content_report": {
                "verdict": "PASS",
                "criteria": [{"criterion_id": "F1", "status": "PASS", "reason": "ok"}],
                "findings": [],
            },
            "language_report": {
                "verdict": "PASS",
                "criteria": [{"criterion_id": "L4", "status": "PASS", "reason": "ok"}],
                "findings": [],
            },
        }
        text = build_enriched_markdown(verified)
        self.assertIn("ENRICHMENT c1", text)
        self.assertIn("python_cli", text)
        self.assertIn("print(2 ** 3)", text)
        self.assertIn("Bazowy artefakt", text)
        self.assertIn("Nowy artefakt", text)
        self.assertIn("NIEZAREJESTROWANA", text)


if __name__ == "__main__":
    unittest.main()
