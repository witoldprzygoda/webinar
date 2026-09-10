"""M1c: audit explicit role packets using Codex model-visible prompt input.

No model request, lesson content, audio or render is executed by this audit.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runners.context_packet import (  # noqa: E402
    child_environment,
    debug_prompt_command,
    exec_command,
    global_instruction_files,
    make_packet,
    real_codex_home,
    resolve_cli,
)

ROLES = ("author", "judge_content", "arbiter")
EXPECTED_VERSION = "codex-cli 0.153.4"
REPO_SENTINELS = (
    "Nie osłabiaj kryteriów",
    "PRODUCTION_WORKFLOW.md jest nadrzędny",
)


def run_process(args: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=cwd, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
        shell=False,
    )


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)


def audit_one(*, launcher: list[str], audit_home: Path, workdir: Path,
              role: str, marker: str, forbidden: list[str], run_dir: Path) -> dict:
    payload = {
        "task": "synthetic context-isolation audit",
        "role_marker": marker,
        "material": "SYNTHETIC_NEUTRAL_MATERIAL",
    }
    prompt = make_packet(role, payload)
    command = debug_prompt_command(launcher, workdir, prompt)
    env = child_environment(dict(os.environ), codex_home=audit_home)
    result = run_process(command, cwd=workdir, env=env)
    (run_dir / f"{role}-stderr.log").write_text(result.stderr, encoding="utf-8")
    (run_dir / f"{role}-stdout.json").write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        return {"role": role, "status": "ERROR", "stage": "debug_prompt_input",
                "exit_code": result.returncode, "message": result.stderr[-2000:]}
    try:
        model_input = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return {"role": role, "status": "ERROR", "stage": "parse_prompt_input",
                "message": str(error)}
    flattened = "\n".join(strings(model_input))
    checks = {
        "own_marker_visible": marker in flattened,
        "foreign_markers_absent": not any(value in flattened for value in forbidden),
        "repo_instructions_absent": not any(value in flattened for value in REPO_SENTINELS),
    }
    return {
        "role": role,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "model_input_sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
    }


def run_audit() -> dict:
    run_dir = ROOT / "runs" / "context-isolation" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "context_isolation_audit": "ERROR",
        "model_request_sent": False,
        "llm_called": False,
        "audio_called": False,
        "production_ready": False,
        "filesystem_acl_required_for_this_test": False,
        "roles": [],
    }
    try:
        launcher = resolve_cli()
        env = child_environment(dict(os.environ))
        with tempfile.TemporaryDirectory(prefix="webinar-context-preflight-") as tmp:
            work = Path(tmp)
            version = run_process([*launcher, "--version"], cwd=work, env=env, timeout=30)
            if version.returncode:
                raise RuntimeError("Cannot obtain Codex version.")
            report["cli_version"] = version.stdout.strip()
            if report["cli_version"] != EXPECTED_VERSION:
                raise RuntimeError(
                    f"Audit is pinned to {EXPECTED_VERSION}; found {report['cli_version']!r}."
                )
            login = run_process([*launcher, "login", "status"], cwd=work, env=env, timeout=30)
            login_lines = {line.strip().lower() for line in (login.stdout + login.stderr).splitlines()}
            if login.returncode or "logged in using chatgpt" not in login_lines:
                raise RuntimeError("ChatGPT login not confirmed.")
            report["login_method"] = "chatgpt"

        global_files = global_instruction_files(real_codex_home())
        report["global_instruction_files"] = [str(path) for path in global_files]
        if global_files:
            raise RuntimeError(
                "Global CODEX_HOME AGENTS instructions are present. They must be handled before "
                "claiming an independent judge context."
            )

        # Debug prompt-input gets an empty CODEX_HOME, so no auth/config/history/global
        # AGENTS is copied or read. It does not send a model request.
        with tempfile.TemporaryDirectory(prefix="webinar-audit-home-") as home_tmp, \
             tempfile.TemporaryDirectory(prefix="webinar-audit-work-") as work_tmp:
            audit_home = Path(home_tmp).resolve()
            work_root = Path(work_tmp).resolve()
            markers = {role: f"CTX_{role.upper()}_{uuid.uuid4().hex}" for role in ROLES}
            for role in ROLES:
                workdir = work_root / role
                workdir.mkdir()
                forbidden = [value for other, value in markers.items() if other != role]
                row = audit_one(
                    launcher=launcher,
                    audit_home=audit_home,
                    workdir=workdir,
                    role=role,
                    marker=markers[role],
                    forbidden=forbidden,
                    run_dir=run_dir,
                )
                report["roles"].append(row)
                if row["status"] == "ERROR":
                    break

        states = [row["status"] for row in report["roles"]]
        if len(states) != len(ROLES) or "ERROR" in states:
            report["context_isolation_audit"] = "ERROR"
        elif all(state == "PASS" for state in states):
            report["context_isolation_audit"] = "PASS"
        else:
            report["context_isolation_audit"] = "FAIL"

        # Static production-contract evidence: a real role call will be fresh,
        # ephemeral, ignore user config/rules, use stdin, and never resume/fork.
        with tempfile.TemporaryDirectory(prefix="webinar-exec-contract-") as tmp:
            schema = Path(tmp) / "schema.json"
            command = exec_command(launcher, "gpt-6-astra", schema)
        report["exec_contract"] = {
            "stdin_packet": command[-1] == "-",
            "ephemeral": "--ephemeral" in command,
            "ignore_user_config": "--ignore-user-config" in command,
            "ignore_rules": "--ignore-rules" in command,
            "read_only": "read-only" in command,
            "no_resume_or_fork": "resume" not in command and "fork" not in command,
        }
        if not all(report["exec_contract"].values()):
            report["context_isolation_audit"] = "FAIL"
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        report["context_isolation_audit"] = "ERROR"
        report["error"] = str(error)
    finally:
        (run_dir / "summary.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
        report["report"] = str(run_dir / "summary.json")
    return report


def main() -> int:
    report = run_audit()
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["context_isolation_audit"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
