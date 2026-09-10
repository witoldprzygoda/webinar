from __future__ import annotations

import unittest

from flows.m2d_enrichment import (
    RUBRIC_VERSION,
    arbiter_schema,
    candidate_schema,
    judge_schema,
    selection_from,
    validate_arbiter,
    validate_candidates,
    validate_reviews,
)
from runners.codex_role import RoleRunnerError
from runners.context_packet import ROLES


class M2dEnrichmentTests(unittest.TestCase):
    def artifact(self):
        return {
            "title": "T",
            "narration": [
                {"fragment_id": "f1", "text": "A"},
                {"fragment_id": "f2", "text": "B"},
                {"fragment_id": "f3", "text": "C"},
            ],
            "claims": [],
            "coverage": [],
            "open_questions": [],
            "execution_plan": {"schema_version": 1, "sessions": []},
        }

    def source_pack(self):
        return {
            "sources": [
                {"id": "material", "role": "material"},
                {"id": "evidence", "role": "evidence"},
            ]
        }

    def candidate(self, cid="c1", decision=None):
        value = {
            "candidate_id": cid,
            "kind": "pitfall",
            "title": "XOR is not power",
            "insertion_point": "after_fragment",
            "after_fragment_id": "f2",
            "proposed_narration": "Nie myl operatorów.",
            "value_rationale": "Krótka pułapka.",
            "estimated_seconds": 12,
            "source_support_ids": ["evidence"],
            "verification_kind": "interactive_python",
            "verification_commands": ["2 ^ 3", "2 ** 3"],
        }
        if decision is not None:
            value["decision"] = decision
        return value

    def review(self, cid="c1", decision="KEEP"):
        return {
            "candidate_id": cid,
            "decision": decision,
            "relevance": 2,
            "novelty_for_audience": 2,
            "practical_transfer_value": 2,
            "clarity_gain": 2,
            "digression_risk": 0,
            "prerequisite_burden": 0,
            "reason": "worth it",
            "evidence": "official docs",
        }

    def test_context_roles_include_enrichment_roles(self):
        self.assertIn("enrichment_scout", ROLES)
        self.assertIn("judge_enrichment", ROLES)
        self.assertIn("arbiter", ROLES)

    def test_candidate_schema_allows_zero_candidates(self):
        schema = candidate_schema(8)
        self.assertNotIn("minItems", schema["properties"]["candidates"])
        self.assertEqual(schema["properties"]["candidates"]["maxItems"], 8)

    def test_enrichment_rubric_is_separate_version(self):
        self.assertEqual(RUBRIC_VERSION, "0.1")

    def test_valid_candidate_is_accepted(self):
        output = {
            "artifact_sha256": "a" * 64,
            "role": "enrichment_scout",
            "candidates": [self.candidate()],
            "search_summary": "one",
        }
        validate_candidates(output, self.artifact(), self.source_pack(), "a" * 64)

    def test_unknown_fragment_is_rejected(self):
        candidate = self.candidate()
        candidate["after_fragment_id"] = "missing"
        output = {
            "artifact_sha256": "a" * 64,
            "role": "enrichment_scout",
            "candidates": [candidate],
            "search_summary": "one",
        }
        with self.assertRaises(RoleRunnerError):
            validate_candidates(output, self.artifact(), self.source_pack(), "a" * 64)

    def test_unknown_source_is_rejected(self):
        candidate = self.candidate()
        candidate["source_support_ids"] = ["unknown"]
        output = {
            "artifact_sha256": "a" * 64,
            "role": "enrichment_scout",
            "candidates": [candidate],
            "search_summary": "one",
        }
        with self.assertRaises(RoleRunnerError):
            validate_candidates(output, self.artifact(), self.source_pack(), "a" * 64)

    def test_documentation_only_candidate_must_not_fake_commands(self):
        candidate = self.candidate()
        candidate["verification_kind"] = "documentation_only"
        output = {
            "artifact_sha256": "a" * 64,
            "role": "enrichment_scout",
            "candidates": [candidate],
            "search_summary": "one",
        }
        with self.assertRaises(RoleRunnerError):
            validate_candidates(output, self.artifact(), self.source_pack(), "a" * 64)

    def test_judge_must_review_every_candidate_once(self):
        validate_reviews({"reviews": [self.review("c1"), self.review("c2")]}, ["c1", "c2"])
        with self.assertRaises(RoleRunnerError):
            validate_reviews({"reviews": [self.review("c1"), self.review("c1")]}, ["c1", "c2"])

    def test_arbiter_must_resolve_every_maybe_once(self):
        validate_arbiter({"decisions": [
            {"candidate_id": "c1", "decision": "KEEP", "reason": "ok"},
            {"candidate_id": "c2", "decision": "DROP", "reason": "no"},
        ]}, ["c1", "c2"])
        with self.assertRaises(RoleRunnerError):
            validate_arbiter({"decisions": [
                {"candidate_id": "c1", "decision": "KEEP", "reason": "ok"},
            ]}, ["c1", "c2"])

    def test_selection_keeps_keep_drops_drop_and_requires_arbiter_for_maybe(self):
        candidates = [self.candidate("c1"), self.candidate("c2"), self.candidate("c3")]
        reviews = [self.review("c1", "KEEP"), self.review("c2", "DROP"), self.review("c3", "MAYBE")]
        arbiter = {"decisions": [{"candidate_id": "c3", "decision": "KEEP", "reason": "worth it"}]}
        selection = selection_from(candidates, reviews, arbiter)
        self.assertEqual(selection["selected_candidate_ids"], ["c1", "c3"])
        self.assertEqual(selection["selected_count"], 2)

    def test_empty_selection_is_valid(self):
        selection = selection_from([], [], None)
        self.assertEqual(selection["selected_count"], 0)
        self.assertEqual(selection["selected_candidate_ids"], [])

    def test_schemas_bind_candidate_ids(self):
        judge = judge_schema("a" * 64, ["c1", "c2"])
        enum = judge["properties"]["reviews"]["items"]["properties"]["candidate_id"]["enum"]
        self.assertEqual(enum, ["c1", "c2"])
        arbiter = arbiter_schema("a" * 64, ["c2"])
        enum2 = arbiter["properties"]["decisions"]["items"]["properties"]["candidate_id"]["enum"]
        self.assertEqual(enum2, ["c2"])


if __name__ == "__main__":
    unittest.main()
