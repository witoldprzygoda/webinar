"""Deterministic visual facts derived from approved execution evidence.

The scene designer should select fact_id values instead of copying executable
code, stdout, or provenance metadata by hand.  This module is deliberately
LLM-free: the catalog is a pure function of already approved execution evidence.
"""
from __future__ import annotations

import ast
import hashlib
import json
from typing import Any


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def canonical_stdout(value: Any) -> str:
    """Remove terminal line endings only; preserve all other whitespace."""
    return str(value if value is not None else "").rstrip("\r\n")


def _scalar_display(value: Any) -> str | None:
    if value is None or isinstance(value, (bool, int, float)):
        return str(value)
    if isinstance(value, str):
        return repr(value)
    return None


def _literal_components(stdout: str) -> list[tuple[int, str]]:
    """Return safe top-level tuple/list scalar components from actual stdout."""
    try:
        value = ast.literal_eval(stdout)
    except (SyntaxError, ValueError):
        return []
    if not isinstance(value, (tuple, list)) or len(value) > 16:
        return []
    result: list[tuple[int, str]] = []
    for index, item in enumerate(value):
        display = _scalar_display(item)
        if display is not None:
            result.append((index, display))
    return result


def _append_row_facts(
    facts: list[dict[str, Any]],
    *,
    namespace: str,
    provenance: str,
    row_id: str,
    code: str,
    stdout: str,
    fragment_ids: list[str],
) -> None:
    facts.append({
        "fact_id": f"fact:{namespace}:{row_id}:code",
        "content": code,
        "allowed_element_kinds": ["code"],
        "provenance": provenance,
        "source_ref": row_id,
        "fragment_ids": fragment_ids,
        "derivation": "literal_code",
    })
    if stdout:
        facts.append({
            "fact_id": f"fact:{namespace}:{row_id}:stdout",
            "content": stdout,
            "allowed_element_kinds": ["output", "state"],
            "provenance": provenance,
            "source_ref": row_id,
            "fragment_ids": fragment_ids,
            "derivation": "literal_stdout",
        })
        for index, display in _literal_components(stdout):
            facts.append({
                "fact_id": f"fact:{namespace}:{row_id}:stdout_literal[{index}]",
                "content": display,
                "allowed_element_kinds": ["state"],
                "provenance": "derived_evidence",
                "source_ref": f"{provenance}:{row_id}#stdout_literal[{index}]",
                "fragment_ids": fragment_ids,
                "derivation": f"stdout_literal[{index}]",
            })


def build_visual_fact_catalog(artifact_sha256: str, evidence: dict[str, Any]) -> dict[str, Any]:
    facts: list[dict[str, Any]] = []
    for row in evidence.get("core_examples", []):
        if not isinstance(row, dict):
            continue
        row_id = row.get("example_id")
        code = row.get("input")
        if not isinstance(row_id, str) or not row_id or not isinstance(code, str) or not code:
            continue
        _append_row_facts(
            facts,
            namespace="core",
            provenance="core_example",
            row_id=row_id,
            code=code,
            stdout=canonical_stdout(row.get("actual_stdout", "")),
            fragment_ids=[value for value in row.get("fragment_ids", []) if isinstance(value, str) and value],
        )
    for row in evidence.get("enrichment_checks", []):
        if not isinstance(row, dict):
            continue
        row_id = row.get("check_id")
        code = row.get("code")
        if not isinstance(row_id, str) or not row_id or not isinstance(code, str) or not code:
            continue
        _append_row_facts(
            facts,
            namespace="enrichment",
            provenance="enrichment_check",
            row_id=row_id,
            code=code,
            stdout=canonical_stdout(row.get("actual_stdout", "")),
            fragment_ids=[value for value in row.get("fragment_ids", []) if isinstance(value, str) and value],
        )

    fact_ids = [row["fact_id"] for row in facts]
    if len(fact_ids) != len(set(fact_ids)):
        raise ValueError("Visual fact ids are not unique.")
    catalog = {
        "schema_version": 1,
        "artifact_sha256": artifact_sha256,
        "facts": facts,
    }
    catalog["visual_fact_catalog_sha256"] = canonical_hash(catalog)
    return catalog


def verify_visual_fact_catalog(
    catalog: dict[str, Any],
    *,
    artifact_sha256: str,
    evidence: dict[str, Any],
) -> None:
    expected = build_visual_fact_catalog(artifact_sha256, evidence)
    if catalog != expected:
        raise ValueError("Visual fact catalog does not match approved execution evidence.")
