"""Offline tests: no real Codex, credentials, network or Windows sandbox."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "boundary", Path(__file__).resolve().parents[1] / "scripts/check_codex_boundary.py")
boundary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boundary)


class BoundaryTests(unittest.TestCase):
    def test_toml_windows_paths_roundtrip(self):
        value = {"filesystem": {r"C:\Users\wit\Documents\test": "read"},
                 "network": {"enabled": False}}
        self.assertEqual(tomllib.loads("value=" + boundary.toml(value))["value"], value)

    def test_toml_rejects_unsupported_values(self):
        with self.assertRaises(TypeError):
            boundary.toml(["unexpected"])

    def test_command_uses_host_sandbox_not_windows_subcommand(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = boundary.sandbox_command(["codex.exe"], root, "judge")
        index = command.index("sandbox")
        self.assertEqual(command[index + 1], "-P")
        self.assertNotIn("windows", command)
        self.assertNotIn("exec", command)
        self.assertIn("--include-managed-config", command)
        self.assertIn(sys.executable, command)
        self.assertIn("--", command)

    def test_profile_has_no_broad_root_read_and_no_network(self):
        root = Path("/synthetic").resolve()
        config = boundary.permission_config(root, "judge")[boundary.PROFILE]
        self.assertNotIn(":root", config["filesystem"])
        self.assertEqual(config["filesystem"][str(root / "author")], "deny")
        self.assertEqual(config["filesystem"][str(root / "arbiter")], "deny")
        self.assertEqual(config["filesystem"][str(root / "judge/out")], "write")
        self.assertFalse(config["network"]["enabled"])

    def test_environment_does_not_forward_keys_or_code_injection(self):
        with patch.dict("os.environ", {"PATH": "x", "HOME": "h", "CODEX_HOME": "c",
                                       "OPENAI_API_KEY": "x", "NODE_OPTIONS": "bad",
                                       "PYTHONPATH": "bad", "BASH_ENV": "bad"}, clear=True):
            self.assertEqual(boundary.environment(), {"PATH": "x", "HOME": "h", "CODEX_HOME": "c"})

    def test_real_positive_control_without_sandbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boundary.create_fixtures(root)
            original = {str(p): p.read_bytes() for p in root.rglob("*.txt")}
            for role in boundary.ROLES:
                checks = boundary.probes(root, role)
                child = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", boundary.PROBE,
                                        json.dumps(checks)], capture_output=True, text=True, timeout=10)
                self.assertEqual(child.returncode, 0, child.stderr)
                actual = boundary.parse_result(child.stdout, checks)
                self.assertTrue(all(row["outcome"] == "ALLOWED" for row in actual.values()))
                self.assertEqual(len(actual), 12)
            self.assertEqual({p: Path(p).read_bytes() for p in original}, original)

    def test_missing_file_is_error_not_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            checks = {"missing": {"path": str(Path(tmp) / "absent"), "operation": "read"}}
            child = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", boundary.PROBE,
                                    json.dumps(checks)], capture_output=True, text=True, timeout=10)
            self.assertEqual(boundary.parse_result(child.stdout, checks)["missing"]["outcome"], "ERROR")

    def test_no_result_is_not_denial_success(self):
        with self.assertRaises(ValueError):
            boundary.parse_result("access denied while launching", {"x": {}})

    def test_result_keys_must_match(self):
        with self.assertRaises(ValueError):
            boundary.parse_result(boundary.PREFIX + '{}', {"x": {}})

    def test_duplicate_results_rejected(self):
        text = boundary.PREFIX + '{"x":{"outcome":"DENIED"}}'
        with self.assertRaises(ValueError):
            boundary.parse_result(text + "\n" + text, {"x": {}})

    def test_malformed_outcome_rejected(self):
        for outcome in ("PASSED", True, None):
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                boundary.parse_result(boundary.PREFIX + json.dumps({"x": {"outcome": outcome}}), {"x": {}})

    def test_synthetic_denial_result_is_parsed(self):
        text = boundary.PREFIX + '{"x":{"outcome":"DENIED","errno":13}}'
        self.assertEqual(boundary.parse_result(text, {"x": {}})["x"]["outcome"], "DENIED")


if __name__ == "__main__":
    unittest.main()
