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
                    "input": "17 // 3",
                    "actual_stdout": "5\n",
                },
            ],
            "enrichment_checks": [
                {
                    "check_id": "c-divmod",
                    "fragment_ids": ["f1"],
                    "code": "print(divmod(125, 60))",
                    "actual_stdout": "(2, 5)\n",
                }
            ],
        }

    def artifact(self, text: str = "Przykład: minuty, sekundy = divmod(125, 60).") -> dict:
        return {
            "narration": [
                {"fragment_id": "f1", "text": text},
                {"fragment_id": "other", "text": "Inny fragment."},
            ]
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

    def repair(self, plan: dict, evidence: dict | None = None, artifact: dict | None = None):
        return repair_evidence_refs(
            plan,
            self.evidence() if evidence is None else evidence,
            self.artifact() if artifact is None else artifact,
        )

    def test_unique_wrong_ref_is_rebound_without_changing_semantic_content(self):
        original = self.plan()
        repaired, ref_changes, normalizations, provenance_changes = self.repair(original)
        element = repaired["scenes"][0]["visible_elements"][0]
        self.assertEqual(element["source_ref"], "e1")
        self.assertEqual(element["content"], "1.6")
        self.assertEqual(original["scenes"][0]["visible_elements"][0]["source_ref"], "e2")
        self.assertEqual(len(ref_changes), 1)
        self.assertEqual(ref_changes[0]["old_source_ref"], "e2")
        self.assertEqual(ref_changes[0]["new_source_ref"], "e1")
        self.assertEqual(ref_changes[0]["match_scope"], "scene_fragments")
        self.assertEqual(normalizations, [])
        self.assertEqual(provenance_changes, [])

    def test_trailing_newline_is_canonicalized_and_wrong_ref_is_rebound(self):
        original = self.plan(content="1.6\n")
        repaired, ref_changes, normalizations, provenance_changes = self.repair(original)
        element = repaired["scenes"][0]["visible_elements"][0]
        self.assertEqual(element["content"], "1.6")
        self.assertEqual(element["source_ref"], "e1")
        self.assertEqual(len(ref_changes), 1)
        self.assertEqual(len(normalizations), 1)
        self.assertEqual(normalizations[0]["old_content"], "1.6\n")
        self.assertEqual(normalizations[0]["new_content"], "1.6")
        self.assertEqual(normalizations[0]["normalization"], "remove_trailing_crlf_only")
        self.assertEqual(original["scenes"][0]["visible_elements"][0]["content"], "1.6\n")
        self.assertEqual(provenance_changes, [])

    def test_trailing_newline_with_correct_ref_needs_only_normalization(self):
        repaired, ref_changes, normalizations, provenance_changes = self.repair(
            self.plan(source_ref="e1", content="1.6\n")
        )
        element = repaired["scenes"][0]["visible_elements"][0]
        self.assertEqual(element["source_ref"], "e1")
        self.assertEqual(element["content"], "1.6")
        self.assertEqual(ref_changes, [])
        self.assertEqual(len(normalizations), 1)
        self.assertEqual(provenance_changes, [])

    def test_crlf_is_canonicalized_but_spaces_are_preserved(self):
        evidence = self.evidence()
        evidence["core_examples"][0]["actual_stdout"] = " 1.6 \r\n"
        repaired, ref_changes, normalizations, provenance_changes = self.repair(
            self.plan(source_ref="e1", content=" 1.6 \r\n"), evidence=evidence
        )
        element = repaired["scenes"][0]["visible_elements"][0]
        self.assertEqual(element["content"], " 1.6 ")
        self.assertEqual(ref_changes, [])
        self.assertEqual(len(normalizations), 1)
        self.assertEqual(provenance_changes, [])

    def test_already_valid_binding_is_unchanged(self):
        repaired, ref_changes, normalizations, provenance_changes = self.repair(
            self.plan(source_ref="e1", content="1.6")
        )
        self.assertEqual(repaired["scenes"][0]["visible_elements"][0]["source_ref"], "e1")
        self.assertEqual(ref_changes, [])
        self.assertEqual(normalizations, [])
        self.assertEqual(provenance_changes, [])

    def test_valid_binding_from_other_fragment_is_accepted(self):
        plan = self.plan(source_ref="e-other", content="17 // 3")
        plan["scenes"][0]["visible_elements"][0]["kind"] = "code"
        repaired, ref_changes, normalizations, provenance_changes = self.repair(plan)
        self.assertEqual(repaired["scenes"][0]["visible_elements"][0]["source_ref"], "e-other")
        self.assertEqual(ref_changes, [])
        self.assertEqual(normalizations, [])
        self.assertEqual(provenance_changes, [])

    def test_unique_row_from_other_fragment_can_be_rebound_globally(self):
        plan = self.plan(source_ref="e2", content="17 // 3")
        plan["scenes"][0]["visible_elements"][0]["kind"] = "code"
        repaired, ref_changes, normalizations, provenance_changes = self.repair(plan)
        element = repaired["scenes"][0]["visible_elements"][0]
        self.assertEqual(element["source_ref"], "e-other")
        self.assertEqual(element["content"], "17 // 3")
        self.assertEqual(len(ref_changes), 1)
        self.assertEqual(ref_changes[0]["match_scope"], "global_unique")
        self.assertEqual(normalizations, [])
        self.assertEqual(provenance_changes, [])

    def test_exact_unexecuted_code_in_scene_narration_is_reclassified(self):
        code = "minuty, sekundy = divmod(125, 60)"
        plan = self.plan(source_ref="missing-check", content=code)
        plan["scenes"][0]["visible_elements"][0]["kind"] = "code"
        plan["scenes"][0]["visible_elements"][0]["provenance"] = "enrichment_check"
        repaired, ref_changes, normalizations, provenance_changes = self.repair(plan)
        element = repaired["scenes"][0]["visible_elements"][0]
        self.assertEqual(element["content"], code)
        self.assertEqual(element["provenance"], "approved_narration")
        self.assertEqual(element["source_ref"], "f1")
        self.assertEqual(ref_changes, [])
        self.assertEqual(normalizations, [])
        self.assertEqual(len(provenance_changes), 1)
        self.assertEqual(provenance_changes[0]["old_provenance"], "enrichment_check")
        self.assertEqual(provenance_changes[0]["new_provenance"], "approved_narration")
        self.assertEqual(provenance_changes[0]["match_scope"], "scene_fragments")

    def test_state_can_be_derived_from_current_structured_stdout(self):
        plan = self.plan(source_ref="c-divmod", content="2")
        element = plan["scenes"][0]["visible_elements"][0]
        element["kind"] = "state"
        element["provenance"] = "enrichment_check"
        repaired, ref_changes, normalizations, provenance_changes = self.repair(plan)
        result = repaired["scenes"][0]["visible_elements"][0]
        self.assertEqual(result["content"], "2")
        self.assertEqual(result["provenance"], "derived_evidence")
        self.assertEqual(result["source_ref"], "enrichment_check:c-divmod#stdout_literal[0]")
        self.assertEqual(ref_changes, [])
        self.assertEqual(normalizations, [])
        self.assertEqual(len(provenance_changes), 1)
        self.assertEqual(provenance_changes[0]["derivation"], "stdout_literal[0]")
        self.assertEqual(provenance_changes[0]["match_scope"], "current_source_ref")

    def test_second_state_can_be_derived_from_same_structured_stdout(self):
        plan = self.plan(source_ref="c-divmod", content="5")
        element = plan["scenes"][0]["visible_elements"][0]
        element["kind"] = "state"
        element["provenance"] = "enrichment_check"
        repaired, _, _, provenance_changes = self.repair(plan)
        result = repaired["scenes"][0]["visible_elements"][0]
        self.assertEqual(result["source_ref"], "enrichment_check:c-divmod#stdout_literal[1]")
        self.assertEqual(len(provenance_changes), 1)

    def test_output_can_never_use_derived_or_narration_fallback(self):
        plan = self.plan(source_ref="c-divmod", content="2")
        plan["scenes"][0]["visible_elements"][0]["provenance"] = "enrichment_check"
        artifact = self.artifact("Narracja wymienia wynik 2.")
        with self.assertRaises(M3bRecoveryError):
            self.repair(plan, artifact=artifact)

    def test_code_not_in_evidence_or_approved_narration_is_rejected(self):
        plan = self.plan(source_ref="missing", content="x = 999")
        plan["scenes"][0]["visible_elements"][0]["kind"] = "code"
        with self.assertRaises(M3bRecoveryError):
            self.repair(plan)

    def test_ambiguous_same_fragment_match_is_rejected(self):
        evidence = self.evidence()
        evidence["core_examples"].append({
            "example_id": "e3",
            "fragment_ids": ["f1"],
            "input": "float('1.6')",
            "actual_stdout": "1.6\n",
        })
        with self.assertRaises(M3bRecoveryError):
            self.repair(self.plan(), evidence=evidence)

    def test_ambiguous_global_fallback_is_rejected(self):
        evidence = self.evidence()
        evidence["core_examples"].append({
            "example_id": "e-other-2",
            "fragment_ids": ["other-2"],
            "input": "17 // 3",
            "actual_stdout": "5\n",
        })
        plan = self.plan(source_ref="e2", content="17 // 3")
        plan["scenes"][0]["visible_elements"][0]["kind"] = "code"
        with self.assertRaises(M3bRecoveryError):
            self.repair(plan, evidence=evidence)

    def test_ambiguous_derived_item_in_current_stdout_is_rejected(self):
        evidence = self.evidence()
        evidence["enrichment_checks"][0]["actual_stdout"] = "(2, 2)\n"
        plan = self.plan(source_ref="c-divmod", content="2")
        element = plan["scenes"][0]["visible_elements"][0]
        element["kind"] = "state"
        element["provenance"] = "enrichment_check"
        with self.assertRaises(M3bRecoveryError):
            self.repair(plan, evidence=evidence)

    def test_invented_output_is_rejected(self):
        with self.assertRaises(M3bRecoveryError):
            self.repair(self.plan(content="999\n"))

    def test_code_can_be_rebound_by_exact_input(self):
        plan = self.plan(source_ref="e2", content="8 / 5")
        plan["scenes"][0]["visible_elements"][0]["kind"] = "code"
        repaired, ref_changes, normalizations, provenance_changes = self.repair(plan)
        element = repaired["scenes"][0]["visible_elements"][0]
        self.assertEqual(element["source_ref"], "e1")
        self.assertEqual(element["content"], "8 / 5")
        self.assertEqual(len(ref_changes), 1)
        self.assertEqual(normalizations, [])
        self.assertEqual(provenance_changes, [])

    def test_code_trailing_newline_is_not_normalized(self):
        plan = self.plan(source_ref="e1", content="8 / 5\n")
        plan["scenes"][0]["visible_elements"][0]["kind"] = "code"
        with self.assertRaises(M3bRecoveryError):
            self.repair(plan)


if __name__ == "__main__":
    unittest.main()
