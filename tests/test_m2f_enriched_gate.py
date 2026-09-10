from __future__ import annotations

import copy
import unittest

from flows.m2a_content import canonical_hash
from flows.m2f_enriched_gate import (
    integrated_artifact_schema,
    merge_source_packs,
    validate_integrated_artifact,
)
from runners.codex_role import RoleRunnerError
from runners.context_packet import ROLES
from runners.enrichment_executor import validate_enrichment_plan
from runners.example_executor import ExecutionEvidenceError


class M2fEnrichedGateTests(unittest.TestCase):
    def core(self):
        return {
            "title": "T",
            "narration": [
                {"fragment_id": "f1", "text": "A"},
                {"fragment_id": "f2", "text": "B"},
                {"fragment_id": "f3", "text": "C"},
            ],
            "execution_plan": {
                "schema_version": 1,
                "sessions": [{
                    "session_id": "s1",
                    "steps": [{
                        "example_id": "e1", "fragment_ids": ["f1"], "input": "2 + 2",
                        "expected_outcome": "success", "expected_exception": "",
                    }],
                }],
            },
            "claims": [{
                "claim_id": "core-c1", "text": "core", "support_ids": ["material"], "confidence": "high",
            }],
            "coverage": [{"source_id": "material", "status": "used", "note": "core"}],
            "open_questions": [],
        }

    def candidates(self):
        return [
            {
                "candidate_id": "c1", "insertion_point": "after_fragment", "after_fragment_id": "f2",
                "source_support_ids": ["ev1"], "verification_kind": "python_cli",
            },
            {
                "candidate_id": "c2", "insertion_point": "end", "after_fragment_id": "",
                "source_support_ids": ["ev2"], "verification_kind": "python_cli",
            },
        ]

    def pack(self):
        pack = {
            "schema_version": 1, "lesson_id": "lesson", "target_runtime": "Python 3.14",
            "sources": [
                {"id": "material", "role": "material"},
                {"id": "ev1", "role": "evidence"},
                {"id": "ev2", "role": "evidence"},
            ],
        }
        pack["source_pack_sha256"] = canonical_hash(pack)
        return pack

    def integrated(self):
        core = self.core()
        return {
            "title": core["title"],
            "narration": [
                core["narration"][0], core["narration"][1],
                {"fragment_id": "enr-c1", "text": "D"},
                core["narration"][2],
                {"fragment_id": "enr-c2", "text": "E"},
            ],
            "execution_plan": copy.deepcopy(core["execution_plan"]),
            "claims": [
                *copy.deepcopy(core["claims"]),
                {"claim_id": "claim-c1", "text": "x", "support_ids": ["ev1"], "confidence": "high"},
                {"claim_id": "claim-c2", "text": "y", "support_ids": ["ev2"], "confidence": "high"},
            ],
            "coverage": [
                *copy.deepcopy(core["coverage"]),
                {"source_id": "ev1", "status": "used", "note": "c1"},
                {"source_id": "ev2", "status": "used", "note": "c2"},
            ],
            "open_questions": [],
            "enrichment": {
                "selected_candidate_ids": ["c1", "c2"],
                "integration_map": [
                    {"candidate_id": "c1", "fragment_ids": ["enr-c1"], "claim_ids": ["claim-c1"]},
                    {"candidate_id": "c2", "fragment_ids": ["enr-c2"], "claim_ids": ["claim-c2"]},
                ],
                "verification_plan": {
                    "schema_version": 1,
                    "checks": [
                        {"check_id": "check-c1", "candidate_id": "c1", "fragment_ids": ["enr-c1"], "mode": "python_cli", "code": "print(2 ** 3)", "expected_outcome": "success", "expected_exception": ""},
                        {"check_id": "check-c2", "candidate_id": "c2", "fragment_ids": ["enr-c2"], "mode": "python_cli", "code": "print(5 ^ 2)", "expected_outcome": "success", "expected_exception": ""},
                    ],
                },
            },
        }

    def test_context_roles_include_integrator(self):
        self.assertIn("enrichment_integrator", ROLES)

    def test_integrated_schema_requires_enrichment(self):
        schema = integrated_artifact_schema()
        self.assertIn("enrichment", schema["properties"])
        self.assertIn("enrichment", schema["required"])

    def test_valid_integrated_artifact(self):
        validate_integrated_artifact(self.integrated(), self.core(), self.candidates(), self.pack())

    def test_core_fragment_change_is_rejected(self):
        value = self.integrated()
        value["narration"][0]["text"] = "changed"
        with self.assertRaises(RoleRunnerError):
            validate_integrated_artifact(value, self.core(), self.candidates(), self.pack())

    def test_unmapped_extra_fragment_is_rejected(self):
        value = self.integrated()
        value["narration"].append({"fragment_id": "extra", "text": "not selected"})
        with self.assertRaises(RoleRunnerError):
            validate_integrated_artifact(value, self.core(), self.candidates(), self.pack())

    def test_wrong_insertion_slot_is_rejected(self):
        value = self.integrated()
        row = value["narration"].pop(2)
        value["narration"].insert(0, row)
        with self.assertRaises(RoleRunnerError):
            validate_integrated_artifact(value, self.core(), self.candidates(), self.pack())

    def test_executable_candidate_needs_matching_check(self):
        value = self.integrated()
        value["enrichment"]["verification_plan"]["checks"] = [
            value["enrichment"]["verification_plan"]["checks"][0]
        ]
        with self.assertRaises(RoleRunnerError):
            validate_integrated_artifact(value, self.core(), self.candidates(), self.pack())

    def test_merge_source_packs_deduplicates_identical_ids(self):
        base = {
            "schema_version": 1, "lesson_id": "lesson", "target_runtime": "Python 3.14",
            "sources": [{"id": "material", "role": "material"}],
        }
        base["source_pack_sha256"] = canonical_hash(base)
        extra = copy.deepcopy(base)
        extra["sources"].append({"id": "ev", "role": "evidence"})
        extra.pop("source_pack_sha256")
        extra["source_pack_sha256"] = canonical_hash(extra)
        merged = merge_source_packs(base, extra)
        self.assertEqual([row["id"] for row in merged["sources"]], ["material", "ev"])

    def test_merge_source_packs_rejects_conflicting_same_id(self):
        base = {
            "schema_version": 1, "lesson_id": "lesson", "target_runtime": "Python 3.14",
            "sources": [{"id": "x", "role": "material"}],
        }
        base["source_pack_sha256"] = canonical_hash(base)
        extra = {
            "schema_version": 1, "lesson_id": "lesson", "target_runtime": "Python 3.14",
            "sources": [{"id": "x", "role": "evidence"}],
        }
        extra["source_pack_sha256"] = canonical_hash(extra)
        with self.assertRaises(RoleRunnerError):
            merge_source_packs(base, extra)

    def test_enrichment_executor_rejects_shell_launcher(self):
        plan = {
            "schema_version": 1,
            "checks": [{
                "check_id": "c", "candidate_id": "x", "fragment_ids": ["f"],
                "mode": "python_cli", "code": "python -c 'print(1)'",
                "expected_outcome": "success", "expected_exception": "",
            }],
        }
        with self.assertRaises(ExecutionEvidenceError):
            validate_enrichment_plan(plan)


if __name__ == "__main__":
    unittest.main()
