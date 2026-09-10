from __future__ import annotations

import unittest

from flows.m2e_portfolio import (
    RUBRIC_VERSION,
    finalize_portfolio,
    portfolio_schema,
    validate_portfolio_report,
)
from runners.codex_role import RoleRunnerError


class M2ePortfolioTests(unittest.TestCase):
    def config(self):
        return {
            "soft_budget_seconds": 45,
            "hard_budget_seconds": 65,
            "max_selected_candidates": 3,
        }

    def candidates(self):
        return [
            {"candidate_id": "c1", "estimated_seconds": 18, "kind": "pitfall"},
            {"candidate_id": "c2", "estimated_seconds": 22, "kind": "practical"},
            {"candidate_id": "c3", "estimated_seconds": 23, "kind": "shortcut"},
            {"candidate_id": "c4", "estimated_seconds": 25, "kind": "pitfall"},
        ]

    def decisions(self, keep_ids):
        keep = set(keep_ids)
        return [
            {
                "candidate_id": row["candidate_id"],
                "decision": "KEEP" if row["candidate_id"] in keep else "DROP",
                "reason": "portfolio choice",
            }
            for row in self.candidates()
        ]

    def test_schema_binds_artifact_and_candidates(self):
        schema = portfolio_schema("a" * 64, ["c1", "c2"])
        self.assertEqual(schema["properties"]["artifact_sha256"]["enum"], ["a" * 64])
        self.assertEqual(schema["properties"]["rubric_version"]["enum"], ["0.1"])
        self.assertEqual(RUBRIC_VERSION, "0.1")
        enum = schema["properties"]["decisions"]["items"]["properties"]["candidate_id"]["enum"]
        self.assertEqual(enum, ["c1", "c2"])

    def test_report_must_decide_every_candidate_once(self):
        validate_portfolio_report({"decisions": [
            {"candidate_id": "c1"}, {"candidate_id": "c2"}
        ]}, ["c1", "c2"])
        with self.assertRaises(RoleRunnerError):
            validate_portfolio_report({"decisions": [
                {"candidate_id": "c1"}, {"candidate_id": "c1"}
            ]}, ["c1", "c2"])

    def test_empty_portfolio_is_valid(self):
        result = finalize_portfolio([], [], self.config())
        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["selected_estimated_seconds"], 0)

    def test_soft_budget_can_be_exceeded_when_hard_budget_is_respected(self):
        result = finalize_portfolio(
            self.candidates(), self.decisions(["c1", "c2", "c3"]), self.config()
        )
        self.assertEqual(result["selected_estimated_seconds"], 63)
        self.assertTrue(result["soft_budget_exceeded"])
        self.assertEqual(result["selected_count"], 3)

    def test_hard_budget_boundary_is_allowed(self):
        result = finalize_portfolio(
            self.candidates(), self.decisions(["c1", "c2", "c4"]), self.config()
        )
        self.assertEqual(result["selected_estimated_seconds"], 65)

    def test_hard_budget_is_enforced(self):
        with self.assertRaises(RoleRunnerError) as caught:
            finalize_portfolio(
                self.candidates(), self.decisions(["c1", "c3", "c4"]), self.config()
            )
        self.assertEqual(caught.exception.status, "INVALID_OUTPUT")

    def test_max_selected_candidates_is_enforced(self):
        config = self.config()
        config["hard_budget_seconds"] = 200
        with self.assertRaises(RoleRunnerError) as caught:
            finalize_portfolio(
                self.candidates(), self.decisions(["c1", "c2", "c3", "c4"]), config
            )
        self.assertEqual(caught.exception.status, "INVALID_OUTPUT")

    def test_decision_set_must_match_candidates(self):
        decisions = self.decisions(["c1"])
        decisions[-1]["candidate_id"] = "other"
        with self.assertRaises(RoleRunnerError):
            finalize_portfolio(self.candidates(), decisions, self.config())


if __name__ == "__main__":
    unittest.main()
