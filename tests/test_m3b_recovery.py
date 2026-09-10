from __future__ import annotations

import unittest

from scripts.recover_m3b_evidence_refs import M3bRecoveryError, repair_evidence_refs


class M3bRecoveryTests(unittest.TestCase):
    def evidence(self) -> dict:
        return {
            "core_examples": [
                {
                    "example_id": "e1",
                    "fragment_ids": ["f1"],
                    "input": "8 / 5",
                    "actual_stdout": "1.6\n",
                },
                {
                    "example_id": "e2",
                    "fragment_ids": ["f1"],
                    "input": "17 / 3",
                    "actual_stdout": "5.666666666666667\n",
                },
                {
                    "example_id": "e-other",
                    "fragment_ids": ["other"],
                    "input": "8 / 5",
                    "actual_stdout": "1.6\n",
                },
            ],
            "enrichment_checks": [],
        }

    def plan(self, *, source_ref: str = "e2", content: str = "1.6") -> dict:
        return {
            "scenes": [
                {
                    "scene_id": "s1",
                    "narration_fragment_ids": ["f1"],
                    "visible_elements": [
                        {
                            "element_id": "out",
                            "kind": "output",
                            "provenance": "core_example",
                            "source_ref": source_ref,
                            "content": content,
                        }
                    ],
                }
            ]
        }

    def test_unique_wrong_ref_is_rebound_without_changing_content(self):
        original = self.plan()
        repaired, changes = repair_evidence_refs(original, self.evidence())
        element = repaired["scenes"][0]["visible_elements"][0]
        self.assertEqual(element["source_ref"], "e1")
        self.assertEqual(element["content"], "1.6")
        self.assertEqual(original["scenes"][0]["visible_elements"][0]["source_ref"], "e2")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["old_source_ref"], "e2")
        self.assertEqual(changes[0]["new_source_ref"], "e1")

    def test_already_valid_binding_is_unchanged(self):
        repaired, changes = repair_evidence_refs(
            self.plan(source_ref="e1", content="1.6"), self.evidence()
        )
        self.assertEqual(repaired["scenes"][0]["visible_elements"][0]["source_ref"], "e1")
        self.assertEqual(changes, [])

    def test_matching_row_from_other_fragment_is_not_used(self):
        evidence = self.evidence()
        evidence["core_examples"] = [evidence["core_examples"][2]]
        with self.assertRaises(M3bRecoveryError):
            repair_evidence_refs(self.plan(), evidence)

    def test_ambiguous_same_fragment_match_is_rejected(self):
        evidence = self.evidence()
        evidence["core_examples"].append({
            "example_id": "e3",
            "fragment_ids": ["f1"],
            "input": "float('1.6')",
            "actual_stdout": "1.6\n",
        })
        with self.assertRaises(M3bRecoveryError):
            repair_evidence_refs(self.plan(), evidence)

    def test_invented_output_is_rejected(self):
        with self.assertRaises(M3bRecoveryError):
            repair_evidence_refs(self.plan(content="999"), self.evidence())

    def test_code_can_be_rebound_by_exact_input(self):
        plan = self.plan(source_ref="e2", content="8 / 5")
        plan["scenes"][0]["visible_elements"][0]["kind"] = "code"
        repaired, changes = repair_evidence_refs(plan, self.evidence())
        element = repaired["scenes"][0]["visible_elements"][0]
        self.assertEqual(element["source_ref"], "e1")
        self.assertEqual(element["content"], "8 / 5")
        self.assertEqual(len(changes), 1)


if __name__ == "__main__":
    unittest.main()
