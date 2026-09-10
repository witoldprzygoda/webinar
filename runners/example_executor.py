"""Deterministic execution evidence for Python console examples.

No LLM is involved. The executor runs a fixed manifest under an exact CPython
runtime and records inputs, outputs, runtime identity and hashes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
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
import code, contextlib, io, json, platform, sys
request=json.load(sys.stdin)
console=code.InteractiveConsole({})
results=[]
for item in request["examples"]:
    out=io.StringIO(); err=io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        more=console.push(item["input"])
    results.append({
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


def validate_manifest(manifest: dict[str, Any]) -> None:
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
        if "\n" in item["input"] or "\r" in item["input"] or not item["input"].strip():
            raise ExecutionEvidenceError("INVALID_MANIFEST", "M2b accepts one complete console input per example.")
        seen.add(item["example_id"])


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
        f"Exact CPython {expected_runtime} is required for M2b; observed: {details}",
    )


def run_manifest(
    manifest: dict[str, Any],
    *,
    source_env: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    validate_manifest(manifest)
    env = execution_environment(source_env)
    prefix, _ = discover_runtime(manifest["expected_runtime"], source_env=source_env)
    command = [*prefix, "-I", "-S", "-B", "-c", HELPER]
    request = {
        "examples": [
            {"example_id": item["example_id"], "input": item["input"]}
            for item in manifest["examples"]
        ]
    }
    try:
        result = subprocess.run(
            command, input=json.dumps(request, ensure_ascii=True), env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False, shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExecutionEvidenceError(
            "EXECUTION_TIMEOUT", "Example executor timed out; no retry was made."
        ) from exc
    except OSError as exc:
        raise ExecutionEvidenceError(
            "EXECUTION_FAILED", f"Cannot launch target runtime: {exc}"
        ) from exc
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
    if runtime.get("implementation") != "CPython" or runtime.get("version") != manifest["expected_runtime"]:
        raise ExecutionEvidenceError(
            "RUNTIME_CHANGED", "Runtime identity changed between preflight and execution."
        )
    if len(raw["results"]) != len(manifest["examples"]):
        raise ExecutionEvidenceError(
            "EXECUTION_FAILED", "Executor returned the wrong number of examples."
        )

    rows: list[dict[str, Any]] = []
    for expected, actual in zip(manifest["examples"], raw["results"], strict=True):
        identity_ok = (
            actual.get("example_id") == expected["example_id"]
            and actual.get("input") == expected["input"]
        )
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
        "runtime": runtime,
        "manifest_sha256": canonical_sha256(manifest),
        "results": rows,
        "all_examples_passed": all(row["pass"] for row in rows),
        "llm_involved": False,
        "network_used": False,
    }
    evidence["execution_evidence_sha256"] = canonical_sha256(evidence)
    return evidence
