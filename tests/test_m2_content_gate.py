from __future__ import annotations

import unittest

from flows.m2_content_gate import summarize_chain
from runners.codex_role import RoleRunnerError


class M2ContentGateTests(unittest.TestCase):
    def passing(self):
        sha = "a" * 64
        return (
            {
                "stage": "M2a", "status": "COMPLETED", "reports": "m2a",
                "artifact_sha256": sha, "rubric_version": "0.2",
                "audience_profile": "technical_competent",
                "judge_verdict": "BLOCKED",
            },
            {
                "stage": "M2b", "status": "COMPLETED", "reports": "m2b",
                "artifact_sha256": sha, "artifact_unchanged": True,
                "all_examples_passed": True, "content_judge_pass": True,
            },
            {
                "stage": "M2c", "status": "COMPLETED", "reports": "m2c",
                "lesson_id": "lesson", "artifact_sha256": sha,
                "artifact_unchanged": True, "language_judge_pass": True,
                "language_findings_count": 0, "gate_a_reached": True,
                "gate_a_status": "PENDING_HUMAN_APPROVAL",
            },
        )

    def test_passing_chain_waits_for_human(self):
        result = summarize_chain(*self.passing())
        self.assertEqual(result["status"], "WAITING_HUMAN")
        self.assertEqual(result["audience_profile"], "technical_competent")
        self.assertEqual(result["rubric_version"], "0.2")
        self.assertTrue(result["gate_a_reached"])
        self.assertFalse(result["gate_a_approved"])
        self.assertFalse(result["audio_called"])
        self.assertFalse(result["render_called"])

    def test_language_nonpass_requires_revision(self):
        m2a, m2b, m2c = self.passing()
        m2c["language_judge_pass"] = False
        m2c["language_findings_count"] = 1
        m2c["gate_a_reached"] = False
        m2c["gate_a_status"] = "NOT_REACHED"
        result = summarize_chain(m2a, m2b, m2c)
        self.assertEqual(result["status"], "REVISION_REQUIRED")
        self.assertFalse(result["gate_a_reached"])

    def test_artifact_mismatch_is_blocked(self):
        m2a, m2b, m2c = self.passing()
        m2b["artifact_sha256"] = "b" * 64
        with self.assertRaises(RoleRunnerError):
            summarize_chain(m2a, m2b, m2c)

    def test_incomplete_stage_is_blocked(self):
        m2a, m2b, m2c = self.passing()
        m2c["status"] = "ERROR"
        with self.assertRaises(RoleRunnerError):
            summarize_chain(m2a, m2b, m2c)


if __name__ == "__main__":
    unittest.main()
