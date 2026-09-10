from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from flows.m2_content_gate import (
    m2_content_gate,
    summarize_chain,
    summarize_content_revision,
)
from runners.codex_role import RoleRunnerError


class M2ContentGateTests(unittest.TestCase):
    def passing(self):
        sha = "a" * 64
        return (
            {
                "stage": "M2a", "status": "COMPLETED", "reports": "m2a",
                "lesson_id": "lesson", "artifact_sha256": sha,
                "rubric_version": "0.2", "audience_profile": "technical_competent",
                "judge_verdict": "BLOCKED",
            },
            {
                "stage": "M2b", "status": "COMPLETED", "reports": "m2b",
                "lesson_id": "lesson", "artifact_sha256": sha,
                "artifact_unchanged": True, "all_examples_passed": True,
                "judge_verdict": "PASS", "findings_count": 0,
                "content_judge_pass": True,
            },
            {
                "stage": "M2c", "status": "COMPLETED", "reports": "m2c",
                "lesson_id": "lesson", "artifact_sha256": sha,
                "artifact_unchanged": True, "language_judge_pass": True,
                "language_findings_count": 0, "gate_a_reached": True,
                "gate_a_status": "PENDING_HUMAN_APPROVAL",
            },
        )

    def revising(self):
        m2a, m2b, _ = self.passing()
        m2b["judge_verdict"] = "REVISE"
        m2b["findings_count"] = 3
        m2b["content_judge_pass"] = False
        return m2a, m2b

    def test_passing_chain_waits_for_human(self):
        result = summarize_chain(*self.passing())
        self.assertEqual(result["status"], "WAITING_HUMAN")
        self.assertEqual(result["audience_profile"], "technical_competent")
        self.assertEqual(result["rubric_version"], "0.2")
        self.assertTrue(result["gate_a_reached"])
        self.assertFalse(result["gate_a_approved"])
        self.assertTrue(result["language_judge_called"])
        self.assertFalse(result["audio_called"])
        self.assertFalse(result["render_called"])

    def test_content_revise_is_normal_business_state(self):
        m2a, m2b = self.revising()
        result = summarize_content_revision(m2a, m2b)
        self.assertEqual(result["status"], "REVISION_REQUIRED")
        self.assertEqual(result["stop_reason"], "CONTENT_JUDGE_REVISE")
        self.assertEqual(result["content_judge_verdict"], "REVISE")
        self.assertEqual(result["content_findings_count"], 3)
        self.assertFalse(result["content_judge_pass"])
        self.assertFalse(result["language_judge_called"])
        self.assertIsNone(result["m2c_run"])
        self.assertFalse(result["gate_a_reached"])

    def test_flow_does_not_call_language_judge_after_content_revise(self):
        m2a, m2b = self.revising()
        logger = MagicMock()
        with patch("flows.m2_content_gate.get_run_logger", return_value=logger), \
             patch("flows.m2_content_gate.m2a_content", return_value=m2a), \
             patch("flows.m2_content_gate.m2b_verify", return_value=m2b), \
             patch("flows.m2_content_gate.m2c_language") as language:
            result = m2_content_gate.fn()
        language.assert_not_called()
        self.assertEqual(result["status"], "REVISION_REQUIRED")

    def test_language_nonpass_requires_revision(self):
        m2a, m2b, m2c = self.passing()
        m2c["language_judge_pass"] = False
        m2c["language_findings_count"] = 1
        m2c["gate_a_reached"] = False
        m2c["gate_a_status"] = "NOT_REACHED"
        result = summarize_chain(m2a, m2b, m2c)
        self.assertEqual(result["status"], "REVISION_REQUIRED")
        self.assertEqual(result["stop_reason"], "LANGUAGE_JUDGE_NONPASS")
        self.assertFalse(result["gate_a_reached"])

    def test_artifact_mismatch_is_blocked(self):
        m2a, m2b, m2c = self.passing()
        m2b["artifact_sha256"] = "b" * 64
        with self.assertRaises(RoleRunnerError):
            summarize_chain(m2a, m2b, m2c)

    def test_language_stage_cannot_run_after_content_nonpass(self):
        m2a, m2b = self.revising()
        _, _, m2c = self.passing()
        with self.assertRaises(RoleRunnerError):
            summarize_chain(m2a, m2b, m2c)

    def test_incomplete_stage_is_blocked(self):
        m2a, m2b, m2c = self.passing()
        m2c["status"] = "ERROR"
        with self.assertRaises(RoleRunnerError):
            summarize_chain(m2a, m2b, m2c)


if __name__ == "__main__":
    unittest.main()
