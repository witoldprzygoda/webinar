from __future__ import annotations

import copy
import unittest

from flows.m3b_scene_plan import validate_scene_plan
from runners.codex_role import RoleRunnerError


class M3bScenePlanTests(unittest.TestCase):
    def config(self) -> dict:
        return {"scene_types": ["OPEN", "STATE"]}

    def artifact(self) -> dict:
        return {
            "title": "Lekcja",
            "narration": [
                {"fragment_id": "f1", "text": "Krótki wstęp do obliczeń."},
                {
                    "fragment_id": "frag-07",
                    "text": "Nazwa _ wskazuje ostatni wyświetlony wynik. price + _ korzysta z poprzedniej wartości, a round(_, 2) z nowej.",
                },
            ],
        }

    def evidence(self) -> dict:
        return {
            "core_examples": [
                {"example_id": "e1", "input": "price * tax", "actual_stdout": "12.5625\n"},
                {"example_id": "e2", "input": "price + _", "actual_stdout": "113.0625\n"},
                {"example_id": "e3", "input": "round(_, 2)", "actual_stdout": "113.06\n"},
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

    def selected_variant(self) -> dict:
        return {
            "variant_id": "v2",
            "visual_strategy": "state_model",
            "requires_new_component": True,
            "visible_elements": [
                {"kind": "state", "content": "_"},
                {"kind": "state", "content": "12.5625"},
                {"kind": "state", "content": "113.0625"},
                {"kind": "state", "content": "113.06"},
            ],
            "beats": [{"narration_fragment_ids": ["frag-07"]}],
        }

    def plan(self) -> dict:
        return {
            "lesson_title": "Lekcja",
            "selected_calibration_variant_id": "v2",
            "component_requests": [
                {
                    "component_id": "state-box",
                    "purpose": "Pokazuj aktualną wartość _",
                    "used_in_scene_ids": ["s2"],
                    "origin_variant_id": "v2",
                }
            ],
            "scenes": [
                {
                    "scene_id": "s1",
                    "title": "Wstęp",
                    "scene_type": "OPEN",
                    "narration_fragment_ids": ["f1"],
                    "pedagogical_goal": "Ustawić kontekst.",
                    "visual_strategy": "static",
                    "calibration_variant_id": "",
                    "requires_new_component": False,
                    "component_request_id": "",
                    "visible_elements": [
                        {
                            "element_id": "s1-label",
                            "kind": "label",
                            "provenance": "visual_label",
                            "source_ref": "",
                            "content": "Konsola jako kalkulator",
                        }
                    ],
                    "beats": [
                        {
                            "beat_id": "s1-b1",
                            "narration_fragment_id": "f1",
                            "anchor_text": "Krótki wstęp",
                            "action": "Pokaż tytuł.",
                            "focus_target_id": "s1-label",
                            "reveals": ["s1-label"],
                        }
                    ],
                    "risks": [],
                },
                {
                    "scene_id": "s2",
                    "title": "Stan _",
                    "scene_type": "STATE",
                    "narration_fragment_ids": ["frag-07"],
                    "pedagogical_goal": "Pokazać zmianę wartości tej samej nazwy.",
                    "visual_strategy": "state_model",
                    "calibration_variant_id": "v2",
                    "requires_new_component": True,
                    "component_request_id": "state-box",
                    "visible_elements": [
                        {
                            "element_id": "underscore",
                            "kind": "state",
                            "provenance": "approved_narration",
                            "source_ref": "frag-07",
                            "content": "_",
                        },
                        {
                            "element_id": "state-1",
                            "kind": "state",
                            "provenance": "core_example",
                            "source_ref": "e1",
                            "content": "12.5625",
                        },
                        {
                            "element_id": "state-2",
                            "kind": "state",
                            "provenance": "core_example",
                            "source_ref": "e2",
                            "content": "113.0625",
                        },
                        {
                            "element_id": "state-3",
                            "kind": "state",
                            "provenance": "core_example",
                            "source_ref": "e3",
                            "content": "113.06",
                        },
                    ],
                    "beats": [
                        {
                            "beat_id": "s2-b1",
                            "narration_fragment_id": "frag-07",
                            "anchor_text": "Nazwa _ wskazuje",
                            "action": "Pokaż nazwę i pierwszą wartość.",
                            "focus_target_id": "underscore",
                            "reveals": ["underscore", "state-1"],
                        },
                        {
                            "beat_id": "s2-b2",
                            "narration_fragment_id": "frag-07",
                            "anchor_text": "price + _",
                            "action": "Zmień stan po wyniku dodawania.",
                            "focus_target_id": "state-2",
                            "reveals": ["state-2"],
                        },
                        {
                            "beat_id": "s2-b3",
                            "narration_fragment_id": "frag-07",
                            "anchor_text": "round(_, 2)",
                            "action": "Pokaż kolejny stan.",
                            "focus_target_id": "state-3",
                            "reveals": ["state-3"],
                        },
                    ],
                    "risks": [],
                },
            ],
        }

    def validate(self, plan: dict) -> None:
        validate_scene_plan(
            plan,
            artifact=self.artifact(),
            evidence=self.evidence(),
            selected_variant=self.selected_variant(),
            config=self.config(),
        )

    def test_valid_plan_is_accepted(self):
        self.validate(self.plan())

    def test_every_fragment_must_be_covered_in_order(self):
        plan = self.plan()
        plan["scenes"][0]["narration_fragment_ids"] = ["frag-07"]
        with self.assertRaises(RoleRunnerError):
            self.validate(plan)

    def test_anchor_must_be_exact_narration_substring(self):
        plan = self.plan()
        plan["scenes"][1]["beats"][0]["anchor_text"] = "tekst spoza narracji"
        with self.assertRaises(RoleRunnerError):
            self.validate(plan)

    def test_output_cannot_be_invented(self):
        plan = self.plan()
        plan["scenes"][1]["visible_elements"][1]["content"] = "999"
        with self.assertRaises(RoleRunnerError):
            self.validate(plan)

    def test_derived_state_from_verified_tuple_is_accepted(self):
        plan = self.plan()
        plan["scenes"][0]["visible_elements"].append(
            {
                "element_id": "derived-minute",
                "kind": "state",
                "provenance": "derived_evidence",
                "source_ref": "enrichment_check:c-divmod#stdout_literal[0]",
                "content": "2",
            }
        )
        self.validate(plan)

    def test_derived_evidence_is_state_only(self):
        plan = self.plan()
        plan["scenes"][0]["visible_elements"].append(
            {
                "element_id": "bad-derived-output",
                "kind": "output",
                "provenance": "derived_evidence",
                "source_ref": "enrichment_check:c-divmod#stdout_literal[0]",
                "content": "2",
            }
        )
        with self.assertRaises(RoleRunnerError):
            self.validate(plan)

    def test_derived_state_must_match_indexed_value(self):
        plan = self.plan()
        plan["scenes"][0]["visible_elements"].append(
            {
                "element_id": "bad-derived-state",
                "kind": "state",
                "provenance": "derived_evidence",
                "source_ref": "enrichment_check:c-divmod#stdout_literal[1]",
                "content": "2",
            }
        )
        with self.assertRaises(RoleRunnerError):
            self.validate(plan)

    def test_calibration_visual_strategy_is_binding(self):
        plan = self.plan()
        plan["scenes"][1]["visual_strategy"] = "sequential_run"
        with self.assertRaises(RoleRunnerError):
            self.validate(plan)

    def test_calibration_state_model_must_be_preserved(self):
        plan = self.plan()
        plan["scenes"][1]["visible_elements"].pop()
        with self.assertRaises(RoleRunnerError):
            self.validate(plan)


if __name__ == "__main__":
    unittest.main()
