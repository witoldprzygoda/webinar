from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from runners.example_executor import (
    ExecutionEvidenceError,
    canonical_sha256,
    execution_environment,
    run_execution_plan,
    run_manifest,
    validate_execution_plan,
    validate_manifest,
)


class ExecutorTests(unittest.TestCase):
    def runtime(self):
        return ".".join(map(str, sys.version_info[:3]))

    def fake_meta(self):
        return {"implementation": "CPython", "version": self.runtime(), "executable": sys.executable}

    def manifest(self):
        return {
            "schema_version": 1,
            "expected_runtime": self.runtime(),
            "examples": [
                {"example_id": "expr", "input": "2 + 2", "expected_stdout": "4\n"},
                {"example_id": "assign", "input": "x = 4", "expected_stdout": ""},
                {"example_id": "underscore", "input": "_", "expected_stdout": "4\n"},
            ],
        }

    def plan(self):
        return {
            "schema_version": 1,
            "sessions": [
                {
                    "session_id": "price-session",
                    "steps": [
                        {"example_id": "tax", "fragment_ids": ["f7"], "input": "tax = 12.5 / 100", "expected_outcome": "success", "expected_exception": ""},
                        {"example_id": "price", "fragment_ids": ["f7"], "input": "price = 100.50", "expected_outcome": "success", "expected_exception": ""},
                        {"example_id": "tax-value", "fragment_ids": ["f7"], "input": "price * tax", "expected_outcome": "success", "expected_exception": ""},
                        {"example_id": "underscore-use", "fragment_ids": ["f7"], "input": "price + _", "expected_outcome": "success", "expected_exception": ""},
                    ],
                },
                {
                    "session_id": "fresh-session",
                    "steps": [
                        {"example_id": "underscore-missing", "fragment_ids": ["f7"], "input": "_", "expected_outcome": "exception", "expected_exception": "NameError"},
                    ],
                },
            ],
        }

    def test_manifest_rejects_duplicate_ids(self):
        value = self.manifest(); value["examples"].append(dict(value["examples"][0]))
        with self.assertRaises(ExecutionEvidenceError):
            validate_manifest(value)

    def test_manifest_rejects_multiline_input(self):
        value = self.manifest(); value["examples"][0]["input"] = "x=1\ny=2"
        with self.assertRaises(ExecutionEvidenceError):
            validate_manifest(value)

    def test_plan_rejects_duplicate_example_ids_across_sessions(self):
        value = self.plan()
        value["sessions"][1]["steps"][0]["example_id"] = "price"
        with self.assertRaises(ExecutionEvidenceError):
            validate_execution_plan(value)

    def test_plan_has_no_expected_stdout(self):
        validate_execution_plan(self.plan())
        self.assertTrue(all("expected_stdout" not in step for session in self.plan()["sessions"] for step in session["steps"]))

    def test_environment_drops_python_injection_and_api_keys(self):
        env = execution_environment({"PATH": "x", "HOME": "h", "PYTHONPATH": "bad", "PYTHONSTARTUP": "bad", "OPENAI_API_KEY": "secret"})
        self.assertEqual(env, {"PATH": "x", "HOME": "h"})

    def test_hash_is_order_independent_for_objects(self):
        self.assertEqual(canonical_sha256({"a": 1, "b": 2}), canonical_sha256({"b": 2, "a": 1}))

    def test_real_interactive_semantics_current_interpreter_legacy(self):
        with patch("runners.example_executor.discover_runtime", return_value=([sys.executable], self.fake_meta())):
            evidence = run_manifest(self.manifest())
        self.assertTrue(evidence["all_examples_passed"])
        self.assertEqual([row["actual_stdout"] for row in evidence["results"]], ["4\n", "", "4\n"])
        self.assertFalse(evidence["llm_involved"]); self.assertFalse(evidence["network_used"])

    def test_artifact_plan_records_actual_outputs_and_resets_sessions(self):
        with patch("runners.example_executor.discover_runtime", return_value=([sys.executable], self.fake_meta())):
            evidence = run_execution_plan(self.plan(), self.runtime())
        self.assertTrue(evidence["all_examples_passed"])
        self.assertEqual(evidence["schema_version"], 2)
        by_id = {row["example_id"]: row for row in evidence["results"]}
        self.assertEqual(by_id["tax-value"]["actual_stdout"], "12.5625\n")
        self.assertEqual(by_id["underscore-use"]["actual_stdout"], "113.0625\n")
        self.assertEqual(by_id["underscore-missing"]["observed_exception"], "NameError")
        self.assertTrue(by_id["underscore-missing"]["pass"])
        self.assertEqual(by_id["tax-value"]["fragment_ids"], ["f7"])

    def test_wrong_expected_exception_is_evidence_failure(self):
        plan = self.plan()
        plan["sessions"][1]["steps"][0]["expected_exception"] = "TypeError"
        with patch("runners.example_executor.discover_runtime", return_value=([sys.executable], self.fake_meta())):
            evidence = run_execution_plan(plan, self.runtime())
        self.assertFalse(evidence["all_examples_passed"])
        self.assertFalse(evidence["results"][-1]["outcome_matches"])

    def test_output_mismatch_is_evidence_failure_not_process_error_legacy(self):
        manifest = self.manifest(); manifest["examples"][0]["expected_stdout"] = "5\n"
        with patch("runners.example_executor.discover_runtime", return_value=([sys.executable], self.fake_meta())):
            evidence = run_manifest(manifest)
        self.assertFalse(evidence["all_examples_passed"])
        self.assertFalse(evidence["results"][0]["stdout_matches"])

    def test_runtime_change_is_rejected(self):
        manifest = self.manifest(); manifest["expected_runtime"] = "0.0.0"
        fake_meta = {"implementation": "CPython", "version": "0.0.0", "executable": sys.executable}
        with patch("runners.example_executor.discover_runtime", return_value=([sys.executable], fake_meta)):
            with self.assertRaises(ExecutionEvidenceError) as caught:
                run_manifest(manifest)
        self.assertEqual(caught.exception.status, "RUNTIME_CHANGED")


if __name__ == "__main__":
    unittest.main()
