"""Offline tests for the packet/context boundary. No Codex or network calls."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from runners.context_packet import (
    CONTEXT_OVERRIDES,
    child_environment,
    config_args,
    exec_command,
    global_instruction_files,
    make_packet,
)
from scripts.check_context_isolation import REPO_SENTINELS, strings


class PacketTests(unittest.TestCase):
    def test_packet_contains_only_supplied_payload(self):
        prompt = make_packet("judge_content", {"artifact": "A", "marker": "JUDGE_ONLY"})
        self.assertIn("JUDGE_ONLY", prompt)
        self.assertNotIn("AUTHOR_ONLY", prompt)
        self.assertIn('"role":"judge_content"', prompt)

    def test_unknown_role_rejected(self):
        with self.assertRaises(ValueError):
            make_packet("producer_judge", {})

    def test_non_object_payload_rejected(self):
        with self.assertRaises(TypeError):
            make_packet("author", ["bad"])

    def test_context_features_are_explicitly_disabled(self):
        joined = "\n".join(CONTEXT_OVERRIDES)
        for expected in (
            "project_doc_max_bytes=0",
            "include_environment_context=false",
            "include_apps_instructions=false",
            "include_collaboration_mode_instructions=false",
            "skills.include_instructions=false",
            "skills.bundled.enabled=false",
            "memories.use_memories=false",
            "memories.generate_memories=false",
            "orchestrator.skills.enabled=false",
            "orchestrator.mcp.enabled=false",
            "mcp_servers={}",
            'web_search="disabled"',
            "features.shell_tool=false",
            "features.unified_exec=false",
            "features.multi_agent=false",
        ):
            self.assertIn(expected, joined)

    def test_exec_is_fresh_ephemeral_stdin_contract(self):
        command = exec_command(["codex"], "gpt-6-astra", Path("schema.json"))
        self.assertEqual(command[-1], "-")
        for flag in ("--strict-config", "--ignore-user-config", "--ignore-rules",
                     "--ephemeral", "--skip-git-repo-check", "--json"):
            self.assertIn(flag, command)
        self.assertIn("read-only", command)
        self.assertNotIn("resume", command)
        self.assertNotIn("fork", command)
        self.assertNotIn("danger-full-access", command)

    def test_exec_forces_chatgpt_provider(self):
        command = exec_command(["codex"], "gpt-6-astra", Path("schema.json"))
        joined = "\n".join(command)
        self.assertIn('forced_login_method="chatgpt"', joined)
        self.assertIn('model_provider="openai"', joined)
        self.assertIn('approval_policy="never"', joined)

    def test_environment_filters_api_keys_and_injection(self):
        source = {
            "PATH": "bin", "HOME": "home", "CODEX_HOME": "codex-home",
            "OPENAI_API_KEY": "secret", "CODEX_API_KEY": "secret",
            "OPENAI_BASE_URL": "other", "ANTHROPIC_API_KEY": "secret",
            "NODE_OPTIONS": "--require x", "PYTHONPATH": "x", "BASH_ENV": "x",
        }
        env = child_environment(source)
        self.assertEqual(set(env), {"PATH", "HOME", "CODEX_HOME"})

    def test_audit_home_override_does_not_copy_auth(self):
        env = child_environment({"CODEX_HOME": "real", "HOME": "h"}, codex_home=Path("audit"))
        self.assertEqual(env["CODEX_HOME"], "audit")
        self.assertNotIn("OPENAI_API_KEY", env)

    def test_global_agents_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(global_instruction_files(root), [])
            (root / "AGENTS.md").write_text("x", encoding="utf-8")
            self.assertEqual(global_instruction_files(root), [root / "AGENTS.md"])

    def test_recursive_string_scan_finds_nested_marker(self):
        value = {"a": [{"b": "CTX_JUDGE"}]}
        self.assertIn("CTX_JUDGE", "\n".join(strings(value)))

    def test_repo_sentinels_are_specific(self):
        self.assertGreaterEqual(len(REPO_SENTINELS), 2)
        self.assertTrue(all(len(value) > 15 for value in REPO_SENTINELS))

    def test_config_args_are_pairs(self):
        args = config_args(include_exec_only=False)
        self.assertEqual(len(args) % 2, 0)
        self.assertTrue(all(args[index] == "-c" for index in range(0, len(args), 2)))


if __name__ == "__main__":
    unittest.main()
