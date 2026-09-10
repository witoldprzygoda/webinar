"""Deterministic execution evidence for integrated enrichment checks.

The plan contains Python code only, never shell commands. `python_cli` checks are
launched with the exact configured CPython runtime and `-c` using shell=False.
`interactive_python` checks reuse the artifact-bound interactive executor.
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from runners.example_executor import (
    ExecutionEvidenceError,
    canonical_sha256,
    discover_runtime,
    execution_environment,
    run_execution_plan,
)


MODES = {"interactive_python", "python_cli"}


def validate_enrichment_plan(plan: dict[str, Any]) -> None:
    if not isinstance(plan, dict) or set(plan) != {"schema_version", "checks"}:
        raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", "Unexpected enrichment plan fields.")
    if plan.get("schema_version") != 1:
        raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", "Unsupported enrichment plan version.")
    checks = plan.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", "Enrichment plan needs at least one check.")

    seen: set[str] = set()
    required = {
        "check_id", "candidate_id", "fragment_ids", "mode", "code",
        "expected_outcome", "expected_exception",
    }
    for item in checks:
        if not isinstance(item, dict) or set(item) != required:
            raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", "Enrichment check has an invalid shape.")
        check_id = item["check_id"]
        if not isinstance(check_id, str) or not check_id or check_id in seen:
            raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", "Check ids must be unique and non-empty.")
        seen.add(check_id)
        if not isinstance(item["candidate_id"], str) or not item["candidate_id"]:
            raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", f"Check {check_id} needs candidate_id.")
        refs = item["fragment_ids"]
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not ref for ref in refs):
            raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", f"Check {check_id} needs fragment_ids.")
        if item["mode"] not in MODES:
            raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", f"Check {check_id} has invalid mode.")
        code = item["code"]
        if not isinstance(code, str) or not code.strip():
            raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", f"Check {check_id} needs Python code.")
        if code.lstrip().lower().startswith(("python ", "python3", "py ")):
            raise ExecutionEvidenceError(
                "INVALID_ENRICHMENT_PLAN",
                f"Check {check_id} contains a launcher; store Python code only.",
            )
        outcome = item["expected_outcome"]
        expected_exception = item["expected_exception"]
        if outcome not in {"success", "exception"} or not isinstance(expected_exception, str):
            raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", f"Check {check_id} has invalid expected outcome.")
        if outcome == "success" and expected_exception:
            raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", f"Successful check {check_id} must not name an exception.")
        if outcome == "exception" and not expected_exception:
            raise ExecutionEvidenceError("INVALID_ENRICHMENT_PLAN", f"Exception check {check_id} must name expected_exception.")


def _observed_exception(stderr: str) -> str:
    matches = re.findall(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)):\s", stderr, flags=re.MULTILINE)
    return matches[-1] if matches else ""


def _run_cli_check(item: dict[str, Any], expected_runtime: str, *, timeout: int) -> dict[str, Any]:
    env = execution_environment()
    prefix, runtime_probe = discover_runtime(expected_runtime)
    command = [*prefix, "-I", "-S", "-B", "-c", item["code"]]
    try:
        result = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExecutionEvidenceError("EXECUTION_TIMEOUT", "Enrichment CLI check timed out; no retry was made.") from exc
    except OSError as exc:
        raise ExecutionEvidenceError("EXECUTION_FAILED", f"Cannot launch target runtime: {exc}") from exc

    stderr = result.stderr
    observed_exception = _observed_exception(stderr)
    if item["expected_outcome"] == "success":
        outcome_ok = result.returncode == 0
    else:
        outcome_ok = result.returncode != 0 and observed_exception == item["expected_exception"]
    return {
        "check_id": item["check_id"],
        "candidate_id": item["candidate_id"],
        "fragment_ids": item["fragment_ids"],
        "mode": "python_cli",
        "code": item["code"],
        "expected_outcome": item["expected_outcome"],
        "expected_exception": item["expected_exception"],
        "actual_stdout": result.stdout,
        "actual_stderr": stderr,
        "observed_exception": observed_exception,
        "returncode": result.returncode,
        "runtime_probe": runtime_probe,
        "pass": bool(outcome_ok),
    }


def _run_interactive_check(item: dict[str, Any], expected_runtime: str, *, timeout: int) -> dict[str, Any]:
    plan = {
        "schema_version": 1,
        "sessions": [{
            "session_id": f"enrichment-{item['check_id']}",
            "steps": [{
                "example_id": item["check_id"],
                "fragment_ids": item["fragment_ids"],
                "input": item["code"],
                "expected_outcome": item["expected_outcome"],
                "expected_exception": item["expected_exception"],
            }],
        }],
    }
    evidence = run_execution_plan(plan, expected_runtime, timeout=timeout)
    row = evidence["results"][0]
    return {
        "check_id": item["check_id"],
        "candidate_id": item["candidate_id"],
        "fragment_ids": item["fragment_ids"],
        "mode": "interactive_python",
        "code": item["code"],
        "expected_outcome": item["expected_outcome"],
        "expected_exception": item["expected_exception"],
        "actual_stdout": row["actual_stdout"],
        "actual_stderr": row["actual_stderr"],
        "observed_exception": row["observed_exception"],
        "returncode": None,
        "runtime_probe": evidence["runtime"],
        "pass": bool(row["pass"]),
    }


def run_enrichment_plan(
    plan: dict[str, Any],
    expected_runtime: str,
    *,
    timeout: int = 30,
) -> dict[str, Any]:
    validate_enrichment_plan(plan)
    rows: list[dict[str, Any]] = []
    for item in plan["checks"]:
        if item["mode"] == "python_cli":
            rows.append(_run_cli_check(item, expected_runtime, timeout=timeout))
        else:
            rows.append(_run_interactive_check(item, expected_runtime, timeout=timeout))

    evidence = {
        "schema_version": 1,
        "executor": "enrichment-structured-python",
        "runtime_requested": expected_runtime,
        "isolation_flags": ["-I", "-S", "-B"],
        "plan_sha256": canonical_sha256(plan),
        "results": rows,
        "all_checks_passed": all(row["pass"] for row in rows),
        "llm_involved": False,
        "shell_used": False,
        "network_used": False,
    }
    evidence["enrichment_execution_evidence_sha256"] = canonical_sha256(evidence)
    return evidence
