from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from runners.example_executor import (
    ExecutionEvidenceError,
    canonical_sha256,
    execution_environment,
    run_manifest,
    validate_manifest,
)


class ExecutorTests(unittest.TestCase):
    def manifest(self):
        return {
            "schema_version": 1,
            "expected_runtime": ".".join(map(str, sys.version_info[:3])),
            "examples": [
                {"example_id": "expr", "input": "2 + 2", "expected_stdout": "4\n"},
                {"example_id": "assign", "input": "x = 4", "expected_stdout": ""},
                {"example_id": "underscore", "input": "_", "expected_stdout": "4\n"},
            ],
        }

    def test_manifest_rejects_duplicate_ids(self):
        value = self.manifest()
        value["examples"].append(dict(value["examples"][0]))
        with self.assertRaises(ExecutionEvidenceError):
            validate_manifest(value)

    def test_manifest_rejects_multiline_input(self):
        value = self.manifest()
        value["examples"][0]["input"] = "x=1\ny=2"
        with self.assertRaises(ExecutionEvidenceError):
            validate_manifest(value)

    def test_environment_drops_python_injection_and_api_keys(self):
        env = execution_environment({
            "PATH": "x",
            "HOME": "h",
            "PYTHONPATH": "bad",
            "PYTHONSTARTUP": "bad",
            "OPENAI_API_KEY": "secret",
        })
        self.assertEqual(env, {"PATH": "x", "HOME": "h"})

    def test_hash_is_order_independent_for_objects(self):
        self.assertEqual(
            canonical_sha256({"a": 1, "b": 2}),
            canonical_sha256({"b": 2, "a": 1}),
        )

    def test_real_interactive_semantics_current_interpreter(self):
        manifest = self.manifest()
        fake_meta = {
            "implementation": "CPython",
            "version": manifest["expected_runtime"],
            "executable": sys.executable,
        }
        with patch(
            "runners.example_executor.discover_runtime",
            return_value=([sys.executable], fake_meta),
        ):
            evidence = run_manifest(manifest)
        self.assertTrue(evidence["all_examples_passed"])
        self.assertEqual(
            [row["actual_stdout"] for row in evidence["results"]],
            ["4\n", "", "4\n"],
        )
        self.assertFalse(evidence["llm_involved"])
        self.assertFalse(evidence["network_used"])

    def test_output_mismatch_is_evidence_failure_not_process_error(self):
        manifest = self.manifest()
        manifest["examples"][0]["expected_stdout"] = "5\n"
        fake_meta = {
            "implementation": "CPython",
            "version": manifest["expected_runtime"],
            "executable": sys.executable,
        }
        with patch(
            "runners.example_executor.discover_runtime",
            return_value=([sys.executable], fake_meta),
        ):
            evidence = run_manifest(manifest)
        self.assertFalse(evidence["all_examples_passed"])
        self.assertFalse(evidence["results"][0]["stdout_matches"])

    def test_runtime_change_is_rejected(self):
        manifest = self.manifest()
        manifest["expected_runtime"] = "0.0.0"
        fake_meta = {"implementation": "CPython", "version": "0.0.0", "executable": sys.executable}
        with patch(
            "runners.example_executor.discover_runtime",
            return_value=([sys.executable], fake_meta),
        ):
            with self.assertRaises(ExecutionEvidenceError) as caught:
                run_manifest(manifest)
        self.assertEqual(caught.exception.status, "RUNTIME_CHANGED")


if __name__ == "__main__":
    unittest.main()
