"""M1a diagnostic adapter. NOT a production runner or a filesystem boundary."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Any


class RunnerError(RuntimeError):
    def __init__(self, status: str, message: str):
        self.status = status
        super().__init__(message)


# Keep login location and OS essentials, but never pass API keys or custom URLs.
ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "APPDATA", "LOCALAPPDATA",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "USER", "USERNAME",
    "TEMP", "TMP", "TMPDIR", "TERM", "LANG", "LC_ALL", "CODEX_HOME",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR",
}


def child_environment(source: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in source.items() if key.upper() in ENV_ALLOWLIST}


def resolve_cli(*, windows: bool | None = None) -> list[str]:
    """Avoid shell=True and Windows .cmd quoting by using npm's JS entry point."""
    if windows is None:
        windows = os.name == "nt"
    names = ("codex.exe", "codex.cmd", "codex") if windows else ("codex",)
    found = next((path for name in names if (path := shutil.which(name))), None)
    if not found:
        raise RunnerError("BLOCKED_SETUP", "Codex not found in PATH.")
    path = Path(found).resolve()
    if not windows or path.suffix.lower() == ".exe":
        return [str(path)]
    entry = path.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    node = shutil.which("node.exe") or shutil.which("node")
    if not entry.is_file() or not node:
        raise RunnerError(
            "BLOCKED_SETUP",
            "Cannot resolve the npm Codex launcher. Run 'type -a codex' and 'node --version'.",
        )
    return [node, str(entry)]


def command(launcher: list[str], model: str, schema: Path) -> list[str]:
    args = [*launcher, "exec", "--ignore-user-config", "--ephemeral",
            "--sandbox", "read-only", "--skip-git-repo-check", "--json",
            "--output-schema", str(schema), "--model", model]
    settings = [
        'forced_login_method="chatgpt"', 'model_provider="openai"',
        'approval_policy="never"', 'model_reasoning_effort="medium"',
        'project_doc_max_bytes=0', 'history.persistence="none"',
        'memories.use_memories=false', 'web_search="disabled"',
        'features.shell_tool=false', 'features.unified_exec=false',
        'features.shell_snapshot=false', 'features.multi_agent=false',
        'hide_agent_reasoning=true',
    ]
    for setting in settings:
        args.extend(["-c", setting])
    # Prompt on stdin: no shell interpolation and no prompt in process arguments.
    return [*args, "-"]


def classify_failure(text: str) -> str:
    text = text.lower()
    if any(term in text for term in (
        "usage_limit_reached", "rate_limit_exceeded", "usage limit", "rate limit",
        "insufficient_quota",
    )):
        return "BLOCKED_LIMIT"
    return "EXEC_FAILED"


def parse_events(text: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Use CLI events as evidence; reject tool activity in this text-only test."""
    threads: list[str] = []
    messages: list[str] = []
    usages: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RunnerError("INVALID_PROTOCOL", "Non-JSON output from codex exec --json.") from exc
        if not isinstance(event, dict):
            raise RunnerError("INVALID_PROTOCOL", "Invalid CLI event.")
        kind = event.get("type")
        if kind in {"error", "turn.failed"}:
            raise RunnerError(classify_failure(line), "Codex reported a failed turn; inspect local logs.")
        if kind == "thread.started":
            thread_id = event.get("thread_id")
            if not isinstance(thread_id, str) or not thread_id:
                raise RunnerError("INVALID_PROTOCOL", "Missing thread ID.")
            threads.append(thread_id)
        elif kind == "turn.completed":
            usage = event.get("usage", {})
            if not isinstance(usage, dict):
                raise RunnerError("INVALID_PROTOCOL", "Invalid usage event.")
            usages.append(usage)
        elif kind in {"item.started", "item.updated", "item.completed"}:
            item = event.get("item")
            if not isinstance(item, dict):
                raise RunnerError("INVALID_PROTOCOL", "Invalid item event.")
            if item.get("type") not in {"agent_message", "reasoning"}:
                raise RunnerError("UNEXPECTED_TOOL_ACTIVITY", "This smoke test must not use tools.")
            if kind == "item.completed" and item.get("type") == "agent_message":
                value = item.get("text")
                if not isinstance(value, str):
                    raise RunnerError("INVALID_PROTOCOL", "Invalid agent message.")
                messages.append(value)
        elif kind != "turn.started":
            raise RunnerError("INVALID_PROTOCOL", f"Unsupported event type: {kind!r}.")
    if len(threads) != 1 or len(usages) != 1 or not messages:
        raise RunnerError("INVALID_PROTOCOL", "Expected one new thread and one completed turn.")
    try:
        answer = json.loads(messages[-1])
    except json.JSONDecodeError as exc:
        raise RunnerError("INVALID_OUTPUT", "Final message is not JSON.") from exc
    if (not isinstance(answer, dict) or set(answer) != {"role", "marker"}
            or not all(isinstance(value, str) for value in answer.values())):
        raise RunnerError("INVALID_OUTPUT", "Final JSON violates the output contract.")
    return threads[0], answer, usages[0]


def _stop(process: subprocess.Popen[str]) -> None:
    """Terminate only our process tree. A timeout is never automatically retried."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()


class CodexSmokeRunner:
    """Only accepts synthetic author/judge diagnostics; no course input yet."""
    def __init__(self, model: str = "gpt-6-astra", timeout: int = 300):
        if not model or timeout < 1:
            raise ValueError("A model and positive timeout are required.")
        self.model = model
        self.timeout = timeout
        self.launcher = resolve_cli()
        self.env = child_environment(dict(os.environ))
        self.version = ""

    def preflight(self) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="webinar-preflight-") as work:
            def read(args: list[str]) -> subprocess.CompletedProcess[str]:
                return subprocess.run([*self.launcher, *args], cwd=work, env=self.env,
                                      capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=30, check=False)
            version = read(["--version"])
            help_result = read(["exec", "--help"])
            login = read(["login", "status"])
        if version.returncode or help_result.returncode:
            raise RunnerError("BLOCKED_SETUP", "Cannot read Codex version or exec help.")
        help_text = help_result.stdout + help_result.stderr
        required = ("--ignore-user-config", "--ephemeral", "--output-schema", "--json")
        missing = [flag for flag in required if flag not in help_text]
        if missing:
            raise RunnerError("BLOCKED_SETUP", "CLI does not advertise required flags: " + ", ".join(missing))
        login_lines = {line.strip().lower() for line in (login.stdout + login.stderr).splitlines()}
        if login.returncode or "logged in using chatgpt" not in login_lines:
            raise RunnerError("BLOCKED_AUTH", "ChatGPT login not confirmed. Run 'codex login status'.")
        self.version = (version.stdout + version.stderr).strip()
        return {"cli_version": self.version, "login_method": "chatgpt",
                "api_fallback": False, "automatic_credit_purchase": False}

    def run(self, role: str, report_dir: Path) -> dict[str, Any]:
        if role not in {"author", "judge"}:
            raise ValueError("Only synthetic author and judge smoke jobs are supported.")
        if not self.version:
            raise RunnerError("BLOCKED_SETUP", "preflight() must succeed before model calls.")
        report_dir.mkdir(parents=True, exist_ok=False)
        marker = f"CODEX_{role.upper()}_OK"
        prompt = (
            "Synthetic connection test, not a content review. Do not use tools or read files. "
            "Do not create subagents. Return only a JSON object with exactly these values: "
            + json.dumps({"role": role, "marker": marker})
        )
        schema = {
            "type": "object", "additionalProperties": False,
            "properties": {"role": {"type": "string"}, "marker": {"type": "string"}},
            "required": ["role", "marker"],
        }
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix=f"webinar-{role}-") as work:
            schema_path = Path(work) / "output-schema.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            with subprocess.Popen(
                command(self.launcher, self.model, schema_path),
                cwd=work, env=self.env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", shell=False,
                start_new_session=os.name != "nt",
            ) as process:
                timed_out = False
                try:
                    stdout, stderr = process.communicate(prompt, timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    _stop(process)
                    stdout, stderr = process.communicate(timeout=15)
                except BaseException:
                    _stop(process)
                    raise
                # Logs stay locally in ignored runs/. Never upload auth/config/log files.
                (report_dir / "events.jsonl").write_text(stdout, encoding="utf-8")
                (report_dir / "stderr.log").write_text(stderr, encoding="utf-8")
                if timed_out:
                    raise RunnerError("TIMEOUT_NO_RETRY", "Codex timed out. No automatic retry was made.")
                if process.returncode:
                    raise RunnerError(classify_failure(stdout + stderr), "Codex failed; inspect local logs.")
                thread_id, answer, usage = parse_events(stdout)
                if answer != {"role": role, "marker": marker}:
                    raise RunnerError("INVALID_OUTPUT", "Unexpected marker or role.")
                receipt = {
                    "role": role, "pid": process.pid, "session_id": thread_id,
                    "working_directory": work, "model_requested": self.model,
                    "cli_version": self.version,
                    "input_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "output_sha256": hashlib.sha256(json.dumps(answer, sort_keys=True).encode()).hexdigest(),
                    "response": answer, "usage": usage,
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "filesystem_isolation_verified": False,
                    "instruction_isolation_verified": False,
                    "production_ready": False,
                }
        (report_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return receipt
