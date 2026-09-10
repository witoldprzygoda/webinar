"""Deterministic execution evidence for Python console examples.

No LLM is involved. The executor supports the legacy fixed manifest and the
current artifact-bound execution plan. Both run under an exact CPython runtime
and record inputs, outputs, runtime identity and hashes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


class ExecutionEvidenceError(RuntimeError):
    def __init__(self, status: str, message: str):
        self.status = status
        super().__init__(message)


EXEC_ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "APPDATA", "LOCALAPPDATA",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "USER", "USERNAME",
    "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
}

HELPER = r'''
import builtins, code, contextlib, io, json, platform, sys
request=json.load(sys.stdin)
results=[]
for session in request["sessions"]:
    if hasattr(builtins, "_"):
        delattr(builtins, "_")
    console=code.InteractiveConsole({})
    for item in session["steps"]:
        out=io.StringIO(); err=io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            more=console.push(item["input"])
        results.append({
            "session_id": session["session_id"],
            "example_id": item["example_id"],
            "input": item["input"],
            "stdout": out.getvalue(),
            "stderr": err.getvalue(),
            "incomplete": bool(more),
        })
print(json.dumps({
    "runtime": {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "version_info": list(sys.version_info[:3]),
        "executable": sys.executable,
    },
    "execution_mode": "code.InteractiveConsole",
    "results": results,
}, ensure_ascii=True))
'''


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def execution_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    source = dict(os.environ) if source is None else source
    return {key: value for key, value in source.items() if key.upper() in EXEC_ENV_ALLOWLIST}


def _validate_input(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise ExecutionEvidenceError("INVALID_MANIFEST", f"{label} must be one complete console input.")


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate legacy v1 manifest with predeclared stdout expectations."""
    if set(manifest) != {"schema_version", "expected_runtime", "examples"}:
        raise ExecutionEvidenceError("INVALID_MANIFEST", "Unexpected execution manifest fields.")
    if manifest["schema_version"] != 1:
        raise ExecutionEvidenceError("INVALID_MANIFEST", "Unsupported execution manifest version.")
    if not isinstance(manifest["expected_runtime"], str) or not manifest["expected_runtime"]:
        raise ExecutionEvidenceError("INVALID_MANIFEST", "expected_runtime must be a non-empty string.")
    examples = manifest["examples"]
    if not isinstance(examples, list) or not examples:
        raise ExecutionEvidenceError("INVALID_MANIFEST", "examples must be a non-empty array.")
    seen: set[str] = set()
    for item in examples:
        if not isinstance(item, dict) or set(item) != {"example_id", "input", "expected_stdout"}:
            raise ExecutionEvidenceError("INVALID_MANIFEST", "Each example needs example_id, input and expected_stdout only.")
        if not all(isinstance(item[key], str) for key in item):
            raise ExecutionEvidenceError("INVALID_MANIFEST", "Example fields must be strings.")
        if not item["example_id"] or item["example_id"] in seen:
            raise ExecutionEvidenceError("INVALID_MANIFEST", "Example ids must be unique and non-empty.")
        _validate_input(item["input"], f"Example {item['example_id']}")
        seen.add(item["example_id"])


def validate_execution_plan(plan: dict[str, Any]) -> None:
    """Validate artifact-bound plan. It contains no expected stdout."""
    if not isinstance(plan, dict) or set(plan) != {"schema_version", "sessions"}:
        raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", "Unexpected execution plan fields.")
    if plan["schema_version"] != 1:
        raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", "Unsupported execution plan version.")
    sessions = plan["sessions"]
    if not isinstance(sessions, list) or not sessions:
        raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", "Execution plan needs at least one session.")
    session_ids: set[str] = set()
    example_ids: set[str] = set()
    for session in sessions:
        if not isinstance(session, dict) or set(session) != {"session_id", "steps"}:
            raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", "Each execution session needs session_id and steps only.")
        session_id = session["session_id"]
        if not isinstance(session_id, str) or not session_id or session_id in session_ids:
            raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", "Session ids must be unique and non-empty.")
        session_ids.add(session_id)
        steps = session["steps"]
        if not isinstance(steps, list) or not steps:
            raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", f"Execution session {session_id} has no steps.")
        for item in steps:
            required = {"example_id", "fragment_ids", "input", "expected_outcome", "expected_exception"}
            if not isinstance(item, dict) or set(item) != required:
                raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", "Execution steps have an invalid shape.")
            example_id = item["example_id"]
            if not isinstance(example_id, str) or not example_id or example_id in example_ids:
                raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", "Example ids must be globally unique and non-empty.")
            example_ids.add(example_id)
            refs = item["fragment_ids"]
            if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not ref for ref in refs):
                raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", f"Example {example_id} needs non-empty fragment_ids.")
            _validate_input(item["input"], f"Example {example_id}")
            outcome = item["expected_outcome"]
            expected_exception = item["expected_exception"]
            if outcome not in {"success", "exception"}:
                raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", f"Example {example_id} has invalid expected_outcome.")
            if not isinstance(expected_exception, str):
                raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", f"Example {example_id} expected_exception must be a string.")
            if outcome == "success" and expected_exception:
                raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", f"Successful example {example_id} must not name an exception.")
            if outcome == "exception" and not expected_exception:
                raise ExecutionEvidenceError("INVALID_EXECUTION_PLAN", f"Exception example {example_id} must name expected_exception.")


def _probe(prefix: list[str], env: dict[str, str]) -> dict[str, Any] | None:
    command = [
        *prefix, "-I", "-S", "-B", "-c",
        "import json,platform,sys; print(json.dumps({'implementation':platform.python_implementation(),'version':platform.python_version(),'executable':sys.executable}))",
    ]
    try:
        result = subprocess.run(
            command, env=env, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15, check=False, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    try:
        value = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def discover_runtime(
    expected_runtime: str,
    *,
    source_env: dict[str, str] | None = None,
    which=shutil.which,
) -> tuple[list[str], dict[str, Any]]:
    env_source = dict(os.environ) if source_env is None else source_env
    env = execution_environment(env_source)
    candidates: list[list[str]] = []
    explicit = env_source.get("WEBINAR_PYTHON_314")
    if explicit:
        candidates.append([str(Path(explicit).expanduser())])
    py = which("py.exe") or which("py")
    if py:
        candidates.append([py, "-3.14"])
    py314 = which("python3.14.exe") or which("python3.14")
    if py314:
        candidates.append([py314])
    python = which("python.exe") or which("python")
    if python:
        candidates.append([python])

    unique: list[list[str]] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)

    observed: list[str] = []
    for candidate in unique:
        meta = _probe(candidate, env)
        if not meta:
            continue
        label = f"{meta.get('implementation')} {meta.get('version')} ({meta.get('executable')})"
        observed.append(label)
        if meta.get("implementation") == "CPython" and meta.get("version") == expected_runtime:
            return candidate, meta
    details = "; ".join(observed) if observed else "no usable Python candidate found"
    raise ExecutionEvidenceError(
        "BLOCKED_RUNTIME",
        f"Exact CPython {expected_runtime} is required; observed: {details}",
    )


def _run_sessions(
    sessions: list[dict[str, Any]],
    expected_runtime: str,
    *,
    source_env: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    env = execution_environment(source_env)
    prefix, _ = discover_runtime(expected_runtime, source_env=source_env)
    command = [*prefix, "-I", "-S", "-B", "-c", HELPER]
    request = {
        "sessions": [
            {
                "session_id": session["session_id"],
                "steps": [
                    {"example_id": item["example_id"], "input": item["input"]}
                    for item in session["steps"]
                ],
            }
            for session in sessions
        ]
    }
    try:
        result = subprocess.run(
            command, input=json.dumps(request, ensure_ascii=True), env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False, shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExecutionEvidenceError("EXECUTION_TIMEOUT", "Example executor timed out; no retry was made.") from exc
    except OSError as exc:
        raise ExecutionEvidenceError("EXECUTION_FAILED", f"Cannot launch target runtime: {exc}") from exc
    if result.returncode:
        raise ExecutionEvidenceError(
            "EXECUTION_FAILED",
            "Target runtime returned a non-zero exit code: " + result.stderr[-1000:],
        )
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ExecutionEvidenceError("EXECUTION_FAILED", "Executor returned invalid JSON.") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("results"), list) or not isinstance(raw.get("runtime"), dict):
        raise ExecutionEvidenceError("EXECUTION_FAILED", "Executor result has an invalid shape.")
    runtime = raw["runtime"]
    if runtime.get("implementation") != "CPython" or runtime.get("version") != expected_runtime:
        raise ExecutionEvidenceError("RUNTIME_CHANGED", "Runtime identity changed between preflight and execution.")
    expected_count = sum(len(session["steps"]) for session in sessions)
    if len(raw["results"]) != expected_count:
        raise ExecutionEvidenceError("EXECUTION_FAILED", "Executor returned the wrong number of examples.")
    return raw


def _observed_exception(stderr: str) -> str:
    matches = re.findall(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)):\s", stderr, flags=re.MULTILINE)
    return matches[-1] if matches else ""


def run_execution_plan(
    plan: dict[str, Any],
    expected_runtime: str,
    *,
    source_env: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Run exactly the examples bound to the generated artifact."""
    validate_execution_plan(plan)
    raw = _run_sessions(plan["sessions"], expected_runtime, source_env=source_env, timeout=timeout)
    declared = [
        (session["session_id"], step)
        for session in plan["sessions"]
        for step in session["steps"]
    ]
    rows: list[dict[str, Any]] = []
    for (session_id, expected), actual in zip(declared, raw["results"], strict=True):
        identity_ok = (
            actual.get("session_id") == session_id
            and actual.get("example_id") == expected["example_id"]
            and actual.get("input") == expected["input"]
        )
        stderr = str(actual.get("stderr", ""))
        observed_exception = _observed_exception(stderr)
        if expected["expected_outcome"] == "success":
            outcome_ok = stderr == ""
        else:
            outcome_ok = observed_exception == expected["expected_exception"]
        complete = actual.get("incomplete") is False
        rows.append({
            "session_id": session_id,
            "example_id": expected["example_id"],
            "fragment_ids": expected["fragment_ids"],
            "input": expected["input"],
            "expected_outcome": expected["expected_outcome"],
            "expected_exception": expected["expected_exception"],
            "actual_stdout": actual.get("stdout"),
            "actual_stderr": stderr,
            "observed_exception": observed_exception,
            "input_identity_ok": identity_ok,
            "outcome_matches": outcome_ok,
            "complete_input": complete,
            "pass": bool(identity_ok and outcome_ok and complete),
        })

    evidence = {
        "schema_version": 2,
        "executor": "python-stdlib-interactive-console",
        "execution_mode": raw.get("execution_mode"),
        "isolation_flags": ["-I", "-S", "-B"],
        "runtime_requested": expected_runtime,
        "runtime": raw["runtime"],
        "execution_plan_sha256": canonical_sha256(plan),
        "results": rows,
        "all_examples_passed": all(row["pass"] for row in rows),
        "llm_involved": False,
        "network_used": False,
    }
    evidence["execution_evidence_sha256"] = canonical_sha256(evidence)
    return evidence


def run_manifest(
    manifest: dict[str, Any],
    *,
    source_env: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Run legacy fixed manifest. Kept for regression compatibility only."""
    validate_manifest(manifest)
    sessions = [{
        "session_id": "legacy-manifest",
        "steps": [
            {"example_id": item["example_id"], "input": item["input"]}
            for item in manifest["examples"]
        ],
    }]
    raw = _run_sessions(sessions, manifest["expected_runtime"], source_env=source_env, timeout=timeout)

    rows: list[dict[str, Any]] = []
    for expected, actual in zip(manifest["examples"], raw["results"], strict=True):
        identity_ok = actual.get("example_id") == expected["example_id"] and actual.get("input") == expected["input"]
        stdout_ok = actual.get("stdout") == expected["expected_stdout"]
        stderr_ok = actual.get("stderr") == ""
        complete = actual.get("incomplete") is False
        rows.append({
            "example_id": expected["example_id"],
            "input": expected["input"],
            "expected_stdout": expected["expected_stdout"],
            "actual_stdout": actual.get("stdout"),
            "actual_stderr": actual.get("stderr"),
            "input_identity_ok": identity_ok,
            "stdout_matches": stdout_ok,
            "stderr_empty": stderr_ok,
            "complete_input": complete,
            "pass": bool(identity_ok and stdout_ok and stderr_ok and complete),
        })

    evidence = {
        "schema_version": 1,
        "executor": "python-stdlib-interactive-console",
        "execution_mode": raw.get("execution_mode"),
        "isolation_flags": ["-I", "-S", "-B"],
        "runtime_requested": manifest["expected_runtime"],
        "runtime": raw["runtime"],
        "manifest_sha256": canonical_sha256(manifest),
        "results": rows,
        "all_examples_passed": all(row["pass"] for row in rows),
        "llm_involved": False,
        "network_used": False,
    }
    evidence["execution_evidence_sha256"] = canonical_sha256(evidence)
    return evidence
