from __future__ import annotations

import copy
import unittest

from runners.visual_fact_catalog import (
    build_visual_fact_catalog,
    verify_visual_fact_catalog,
)


class VisualFactCatalogTests(unittest.TestCase):
    def evidence(self) -> dict:
        return {
            "core_examples": [
                {
                    "example_id": "core-div",
                    "fragment_ids": ["frag-02"],
                    "input": "8 / 5",
                    "actual_stdout": "1.6\n",
                },
                {
                    "example_id": "core-tuple",
                    "fragment_ids": ["frag-tuple"],
                    "input": "divmod(125, 60)",
                    "actual_stdout": "(2, 5)\n",
                },
            ],
            "enrichment_checks": [
                {
                    "check_id": "enrich-divmod",
                    "fragment_ids": ["enrichment-01"],
                    "code": "print(divmod(125, 60))",
                    "actual_stdout": "(2, 5)\n",
                },
                {
                    "check_id": "enrich-xor",
                    "fragment_ids": ["enrichment-02"],
                    "code": "print(5 ^ 2, 5 ** 2)\nassert (5 ^ 2) != (5 ** 2)",
                    "actual_stdout": "7 25\n",
                },
            ],
        }

    def test_catalog_contains_core_literal_code_and_stdout_facts(self):
        catalog = build_visual_fact_catalog("artifact", self.evidence())
        by_id = {row["fact_id"]: row for row in catalog["facts"]}
        self.assertEqual(catalog["schema_version"], 2)
        self.assertEqual(
            catalog["presentation_policy"],
            "core_examples_only_enrichment_checks_verification_only",
        )
        self.assertEqual(by_id["fact:core:core-div:code"]["content"], "8 / 5")
        self.assertEqual(by_id["fact:core:core-div:stdout"]["content"], "1.6")

    def test_enrichment_verification_code_and_stdout_are_not_visual_facts(self):
        catalog = build_visual_fact_catalog("artifact", self.evidence())
        fact_ids = [row["fact_id"] for row in catalog["facts"]]
        self.assertFalse(any("enrichment" in fact_id for fact_id in fact_ids))
        contents = [row["content"] for row in catalog["facts"]]
        self.assertNotIn("print(divmod(125, 60))", contents)
        self.assertNotIn("7 25", contents)
        self.assertFalse(any("assert" in content for content in contents))

    def test_tuple_stdout_gets_deterministic_component_state_facts_for_core_example(self):
        catalog = build_visual_fact_catalog("artifact", self.evidence())
        by_id = {row["fact_id"]: row for row in catalog["facts"]}
        first = by_id["fact:core:core-tuple:stdout_literal[0]"]
        second = by_id["fact:core:core-tuple:stdout_literal[1]"]
        self.assertEqual(first["content"], "2")
        self.assertEqual(second["content"], "5")
        self.assertEqual(first["allowed_element_kinds"], ["state"])
        self.assertEqual(first["provenance"], "derived_evidence")
        self.assertEqual(
            first["source_ref"],
            "core_example:core-tuple#stdout_literal[0]",
        )

    def test_catalog_verification_detects_mutation(self):
        catalog = build_visual_fact_catalog("artifact", self.evidence())
        verify_visual_fact_catalog(catalog, artifact_sha256="artifact", evidence=self.evidence())
        changed = copy.deepcopy(catalog)
        changed["facts"][0]["content"] = "999"
        with self.assertRaises(ValueError):
            verify_visual_fact_catalog(changed, artifact_sha256="artifact", evidence=self.evidence())


if __name__ == "__main__":
    unittest.main()
