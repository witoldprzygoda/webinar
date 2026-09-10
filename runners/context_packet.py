"""Explicit context packets for isolated Codex roles.

This module defines the boundary used by M1 context isolation.  It does not
resolve sources or decide quality; Prefect owns those handoffs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from typing import Any


ROLES = {
    "author",
    "judge_content",
    "judge_language",
    "enrichment_scout",
    "judge_enrichment",
    "arbiter",
    "scene_designer",
    "judge_visual",
}

ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "APPDATA", "LOCALAPPDATA",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "USER", "USERNAME",
    "TEMP", "TMP", "TMPDIR", "TERM", "LANG", "LC_ALL", "CODEX_HOME",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR",
}

# These overrides are shared by the production-like exec contract and the
# model-visible-input audit.  The audit uses an empty temporary CODEX_HOME.
CONTEXT_OVERRIDES = (
    'project_doc_max_bytes=0',
    'include_environment_context=false',
    'include_permissions_instructions=false',
    'include_apps_instructions=false',
    'include_collaboration_mode_instructions=false',
    'skills.include_instructions=false',
    'skills.bundled.enabled=false',
    'memories.use_memories=false',
    'memories.generate_memories=false',
    'memories.dedicated_tools=false',
    'orchestrator.skills.enabled=false',
    'orchestrator.mcp.enabled=false',
    'mcp_servers={}',
    'web_search="disabled"',
    'features.shell_tool=false',
    'features.unified_exec=false',
    'features.shell_snapshot=false',
    'features.multi_agent=false',
    'history.persistence="none"',
    'hide_agent_reasoning=true',
)

EXEC_ONLY_OVERRIDES = (
    'forced_login_method="chatgpt"',
    'model_provider="openai"',
    'approval_policy="never"',
)


def resolve_cli(*, windows: bool | None = None) -> list[str]:
    """Resolve the npm Codex launcher without shell=True."""
    if windows is None:
        windows = os.name == "nt"
    names = ("codex.exe", "codex.cmd", "codex") if windows else ("codex",)
    found = next((path for name in names if (path := shutil.which(name))), None)
    if not found:
        raise RuntimeError("Codex not found in PATH.")
    path = Path(found).resolve()
    if not windows or path.suffix.lower() == ".exe":
        return [str(path)]
    entry = path.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    node = shutil.which("node.exe") or shutil.which("node")
    if not entry.is_file() or not node:
        raise RuntimeError("Cannot resolve the npm Codex launcher through node.")
    return [node, str(entry)]


def child_environment(source: dict[str, str], *, codex_home: Path | None = None) -> dict[str, str]:
    env = {key: value for key, value in source.items() if key.upper() in ENV_ALLOWLIST}
    if codex_home is not None:
        env["CODEX_HOME"] = str(codex_home)
    return env


def real_codex_home(source: dict[str, str] | None = None) -> Path:
    source = os.environ if source is None else source
    raw = source.get("CODEX_HOME")
    return Path(raw).expanduser().resolve() if raw else (Path.home() / ".codex").resolve()


def global_instruction_files(codex_home: Path) -> list[Path]:
    """Codex 0.153.4 loads these independently of config.toml."""
    return [path for path in (
        codex_home / "AGENTS.override.md",
        codex_home / "AGENTS.md",
    ) if path.is_file()]


def config_args(*, include_exec_only: bool) -> list[str]:
    values = list(CONTEXT_OVERRIDES)
    if include_exec_only:
        values.extend(EXEC_ONLY_OVERRIDES)
    args: list[str] = []
    for value in values:
        args.extend(["-c", value])
    return args


def make_packet(role: str, payload: dict[str, Any]) -> str:
    if role not in ROLES:
        raise ValueError(f"Unknown role: {role}")
    if not isinstance(payload, dict):
        raise TypeError("Packet payload must be an object.")
    packet = {
        "protocol": "webinar-context-packet/v1",
        "role": role,
        "payload": payload,
    }
    return (
        "Use only the following explicit input packet for task-specific facts and instructions. "
        "Do not infer access to producer history, previous sessions, hidden files, or prior verdicts.\n"
        "BEGIN_INPUT_PACKET_JSON\n"
        + json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\nEND_INPUT_PACKET_JSON"
    )


def exec_command(launcher: list[str], model: str, schema_path: Path) -> list[str]:
    """Fresh, tool-free, non-resumed Codex process; packet is supplied on stdin."""
    return [
        *launcher,
        "exec",
        "--strict-config",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--sandbox", "read-only",
        "--skip-git-repo-check",
        "--json",
        "--output-schema", str(schema_path),
        "--model", model,
        *config_args(include_exec_only=True),
        "-",
    ]


def debug_prompt_command(launcher: list[str], workdir: Path, prompt: str) -> list[str]:
    """Local model-visible-input audit. Prompt is synthetic, so argv exposure is harmless."""
    return [
        *launcher,
        "-C", str(workdir),
        *config_args(include_exec_only=False),
        "debug", "prompt-input", prompt,
    ]
