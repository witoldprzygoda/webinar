"""Generic fresh-session Codex JSON role runner for controlled context packets."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any

from runners.context_packet import (
    child_environment,
    exec_command,
    global_instruction_files,
    make_packet,
    real_codex_home,
    resolve_cli,
)


class RoleRunnerError(RuntimeError):
    def __init__(self, status: str, message: str):
        self.status = status
        super().__init__(message)


def classify_failure(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in (
        "usage_limit_reached", "rate_limit_exceeded", "usage limit", "rate limit",
        "insufficient_quota",
    )):
        return "BLOCKED_LIMIT"
    return "EXEC_FAILED"


def parse_json_events(text: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    threads: list[str] = []
    messages: list[str] = []
    usages: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RoleRunnerError("INVALID_PROTOCOL", "Non-JSON line in codex exec --json output.") from exc
        if not isinstance(event, dict):
            raise RoleRunnerError("INVALID_PROTOCOL", "Invalid Codex event object.")
        kind = event.get("type")
        if kind in {"error", "turn.failed"}:
            raise RoleRunnerError(classify_failure(line), "Codex reported a failed turn.")
        if kind == "thread.started":
            thread_id = event.get("thread_id")
            if not isinstance(thread_id, str) or not thread_id:
                raise RoleRunnerError("INVALID_PROTOCOL", "Missing thread_id.")
            threads.append(thread_id)
        elif kind == "turn.completed":
            usage = event.get("usage", {})
            if not isinstance(usage, dict):
                raise RoleRunnerError("INVALID_PROTOCOL", "Invalid usage object.")
            usages.append(usage)
        elif kind in {"item.started", "item.updated", "item.completed"}:
            item = event.get("item")
            if not isinstance(item, dict):
                raise RoleRunnerError("INVALID_PROTOCOL", "Invalid item event.")
            item_type = item.get("type")
            if item_type not in {"agent_message", "reasoning"}:
                raise RoleRunnerError(
                    "UNEXPECTED_TOOL_ACTIVITY",
                    f"Tool or unsupported activity detected in tool-free role: {item_type!r}.",
                )
            if kind == "item.completed" and item_type == "agent_message":
                value = item.get("text")
                if not isinstance(value, str):
                    raise RoleRunnerError("INVALID_PROTOCOL", "Invalid final agent message.")
                messages.append(value)
        elif kind != "turn.started":
            raise RoleRunnerError("INVALID_PROTOCOL", f"Unsupported event type: {kind!r}.")
    if len(threads) != 1 or len(usages) != 1 or not messages:
        raise RoleRunnerError("INVALID_PROTOCOL", "Expected one fresh thread and one completed turn.")
    try:
        output = json.loads(messages[-1])
    except json.JSONDecodeError as exc:
        raise RoleRunnerError("INVALID_OUTPUT", "Final agent message is not JSON.") from exc
    if not isinstance(output, dict):
        raise RoleRunnerError("INVALID_OUTPUT", "Final JSON must be an object.")
    return threads[0], output, usages[0]


class CodexRoleRunner:
    def __init__(self, *, model: str = "gpt-6-astra", reasoning_effort: str = "high", timeout: int = 600):
        if reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("Unsupported reasoning effort.")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout
        self.launcher = resolve_cli()
        self.env = child_environment(dict(os.environ))
        self.cli_version = ""

    def preflight(self) -> dict[str, Any]:
        global_files = global_instruction_files(real_codex_home())
        if global_files:
            raise RoleRunnerError(
                "BLOCKED_CONTEXT",
                "Global CODEX_HOME AGENTS instructions are present: "
                + ", ".join(str(path) for path in global_files),
            )
        with tempfile.TemporaryDirectory(prefix="webinar-role-preflight-") as tmp:
            work = Path(tmp)
            version = subprocess.run(
                [*self.launcher, "--version"], cwd=work, env=self.env,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, check=False,
            )
            login = subprocess.run(
                [*self.launcher, "login", "status"], cwd=work, env=self.env,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, check=False,
            )
        if version.returncode:
            raise RoleRunnerError("BLOCKED_SETUP", "Cannot obtain Codex version.")
        lines = {line.strip().lower() for line in (login.stdout + login.stderr).splitlines()}
        if login.returncode or "logged in using chatgpt" not in lines:
            raise RoleRunnerError("BLOCKED_AUTH", "ChatGPT login not confirmed for current CODEX_HOME.")
        self.cli_version = (version.stdout + version.stderr).strip()
        return {
            "cli_version": self.cli_version,
            "login_method": "chatgpt",
            "global_instruction_files": [],
        }

    def run_json(self, *, role: str, payload: dict[str, Any], schema: dict[str, Any], report_dir: Path) -> dict[str, Any]:
        if not self.cli_version:
            raise RoleRunnerError("BLOCKED_SETUP", "preflight() must succeed first.")
        report_dir.mkdir(parents=True, exist_ok=False)
        prompt = make_packet(role, payload)
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix=f"webinar-{role}-") as tmp:
            work = Path(tmp)
            schema_path = work / "output-schema.json"
            schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
            command = exec_command(self.launcher, self.model, schema_path)
            command[-1:-1] = ["-c", f'model_reasoning_effort="{self.reasoning_effort}"']
            process = subprocess.Popen(
                command, cwd=work, env=self.env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", shell=False,
                start_new_session=os.name != "nt",
            )
            try:
                stdout, stderr = process.communicate(prompt, timeout=self.timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.communicate()
                raise RoleRunnerError("TIMEOUT_NO_RETRY", "Codex role timed out; no automatic retry was made.") from exc
            (report_dir / "events.jsonl").write_text(stdout, encoding="utf-8")
            (report_dir / "stderr.log").write_text(stderr, encoding="utf-8")
            if process.returncode:
                raise RoleRunnerError(classify_failure(stdout + stderr), "Codex role failed; inspect local logs.")
            session_id, output, usage = parse_json_events(stdout)
        receipt = {
            "role": role,
            "session_id": session_id,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "cli_version": self.cli_version,
            "input_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "output_sha256": hashlib.sha256(
                json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "usage": usage,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "fresh_session": True,
            "tool_activity": False,
        }
        (report_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        (report_dir / "output.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"output": output, "receipt": receipt}
