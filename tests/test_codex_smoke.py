"""Offline tests only. These tests do NOT prove real Codex or OS isolation."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from runners.codex_smoke import (
    CodexSmokeRunner, RunnerError, child_environment, classify_failure,
    command, parse_events, resolve_cli,
)


def events(*, thread: str = "test-thread", response: object = None) -> str:
    if response is None:
        response = {"role": "author", "marker": "CODEX_AUTHOR_OK"}
    return "\n".join(json.dumps(item) for item in [
        {"type": "thread.started", "thread_id": thread},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {
            "type": "agent_message", "text": json.dumps(response)}},
        {"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 2}},
    ])


class ProtocolTests(unittest.TestCase):
    def test_reads_cli_session_and_json(self):
        thread, answer, usage = parse_events(events())
        self.assertEqual(thread, "test-thread")
        self.assertEqual(answer["marker"], "CODEX_AUTHOR_OK")
        self.assertEqual(usage["input_tokens"], 5)

    def test_rejects_plain_text(self):
        with self.assertRaises(RunnerError):
            parse_events("CODEX_AUTHOR_OK")

    def test_rejects_multiple_threads(self):
        with self.assertRaises(RunnerError):
            parse_events(events() + '\n{"type":"thread.started","thread_id":"other"}')

    def test_rejects_missing_completed_turn(self):
        with self.assertRaises(RunnerError):
            parse_events('\n'.join(events().splitlines()[:-1]))

    def test_rejects_bad_schema(self):
        for response in ([], {"role": "author"}, {"role": "author", "marker": 12},
                         {"role": "author", "marker": "ok", "extra": 1}):
            with self.subTest(response=response), self.assertRaises(RunnerError):
                parse_events(events(response=response))

    def test_rejects_tool_events(self):
        for tool in ("command_execution", "mcp_tool_call", "web_search", "file_change"):
            extra = json.dumps({"type": "item.started", "item": {"type": tool}})
            with self.subTest(tool=tool), self.assertRaises(RunnerError) as caught:
                parse_events(events() + "\n" + extra)
            self.assertEqual(caught.exception.status, "UNEXPECTED_TOOL_ACTIVITY")

    def test_rejects_failed_turn(self):
        with self.assertRaises(RunnerError) as caught:
            parse_events('{"type":"turn.failed","error":{"message":"usage limit"}}')
        self.assertEqual(caught.exception.status, "BLOCKED_LIMIT")

    def test_rejects_unknown_event(self):
        with self.assertRaises(RunnerError):
            parse_events(events() + '\n{"type":"unexpected"}')


class LaunchTests(unittest.TestCase):
    def test_filters_credentials_and_custom_endpoints(self):
        env = child_environment({
            "PATH": "bin", "HOME": "home", "CODEX_HOME": "codex-home",
            "OPENAI_API_KEY": "secret", "CODEX_API_KEY": "secret",
            "OPENAI_BASE_URL": "other", "ANTHROPIC_API_KEY": "secret",
            "NODE_OPTIONS": "--require other.js", "BASH_ENV": "other.sh",
        })
        self.assertEqual(set(env), {"PATH", "HOME", "CODEX_HOME"})

    def test_explicit_subscription_and_no_resume(self):
        args = command(["codex"], "gpt-6-astra", Path("schema.json"))
        self.assertIn('forced_login_method="chatgpt"', args)
        self.assertIn("--ephemeral", args)
        self.assertIn("--ignore-user-config", args)
        self.assertIn("read-only", args)
        self.assertNotIn("resume", args)
        self.assertNotIn("danger-full-access", args)
        self.assertEqual(args[-1], "-")

    def test_windows_npm_launcher_uses_node_without_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            shim = Path(tmp) / "codex.cmd"
            shim.write_text("shim")
            entry = Path(tmp) / "node_modules/@openai/codex/bin/codex.js"
            entry.parent.mkdir(parents=True)
            entry.write_text("// fake")
            paths = {"codex.cmd": str(shim), "node.exe": "node.exe"}
            with patch("shutil.which", side_effect=lambda name: paths.get(name)):
                self.assertEqual(resolve_cli(windows=True), ["node.exe", str(entry.resolve())])

    def test_missing_cli_blocks(self):
        with patch("shutil.which", return_value=None), self.assertRaises(RunnerError):
            resolve_cli()

    def test_failure_classification(self):
        self.assertEqual(classify_failure("rate_limit_exceeded"), "BLOCKED_LIMIT")
        self.assertEqual(classify_failure("Network failure"), "EXEC_FAILED")

    def test_login_with_api_is_rejected_before_model(self):
        responses = [
            subprocess.CompletedProcess([], 0, "codex-cli fake", ""),
            subprocess.CompletedProcess([], 0, "--ignore-user-config --ephemeral --output-schema --json", ""),
            subprocess.CompletedProcess([], 0, "Logged in using an API key", ""),
        ]
        with patch("runners.codex_smoke.resolve_cli", return_value=["codex"]):
            runner = CodexSmokeRunner()
        with patch("subprocess.run", side_effect=responses), self.assertRaises(RunnerError) as caught:
            runner.preflight()
        self.assertEqual(caught.exception.status, "BLOCKED_AUTH")

    def test_run_requires_preflight(self):
        with patch("runners.codex_smoke.resolve_cli", return_value=["codex"]):
            runner = CodexSmokeRunner()
        with self.assertRaises(RunnerError):
            runner.run("author", Path("unused"))

    def test_two_real_subprocesses_with_fake_codex(self):
        # Exercises process launch, stdin, JSONL parsing and receipts without any API.
        fake = '''import json,sys,uuid
args=sys.argv[1:]
if args == ["--version"]:
    print("codex-cli offline-fake")
elif args == ["exec", "--help"]:
    print("--ignore-user-config --ephemeral --output-schema --json")
elif args == ["login", "status"]:
    print("Logged in using ChatGPT")
else:
    text=sys.stdin.read()
    answer=json.loads(text[text.index("{"):])
    print(json.dumps({"type":"thread.started","thread_id":str(uuid.uuid4())}))
    print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":json.dumps(answer)}}))
    print(json.dumps({"type":"turn.completed","usage":{}}))
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "fake_codex.py"
            script.write_text(fake, encoding="utf-8")
            with patch("runners.codex_smoke.resolve_cli", return_value=[sys.executable, str(script)]):
                runner = CodexSmokeRunner()
            runner.preflight()
            author = runner.run("author", root / "author")
            judge = runner.run("judge", root / "judge")
            self.assertNotEqual(author["session_id"], judge["session_id"])
            self.assertNotEqual(author["working_directory"], judge["working_directory"])
            self.assertFalse(judge["filesystem_isolation_verified"])
            self.assertFalse(judge["production_ready"])
            self.assertTrue((root / "judge/receipt.json").is_file())
            self.assertFalse(Path(judge["working_directory"]).exists())


if __name__ == "__main__":
    unittest.main()
