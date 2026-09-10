"""Recover an M3b draft rejected by evidence binding/display formatting.

This recovery is deterministic. It never changes narration, scene layout, code,
semantic output, beats, or visual design decisions. It may only:

1. remove trailing CR/LF characters from evidence-backed output/state content;
2. rebind source_ref to another existing example_id/check_id when the canonical
   content identifies exactly one evidence row. Matching prefers evidence linked
   to the current scene fragments, but may fall back to a globally unique row
   because the M3b validator permits verified examples to be reused as visual
   context in later scenes.

The original failed M3b run remains untouched; a successful recovery creates a
new M3b run and records every permitted change.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import uuid
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flows.m2b_verify import load_json  # noqa: E402
from flows.m3b_scene_plan import (  # noqa: E402
    build_evidence_packet,
    validate_scene_plan,
    verify_m3a_selection,
)
from scripts.record_gate_a_approval import canonical_hash  # noqa: E402


class M3bRecoveryError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise M3bRecoveryError(message)


def _canonical_output(value: Any) -> str:
    """Remove only terminal line endings; preserve all other whitespace."""
    return str(value if value is not None else "").rstrip("\r\n")


def _candidate_rows(
    provenance: str,
    *,
    evidence: dict[str, Any],
    scene_fragment_ids: set[str] | None,
) -> list[tuple[str, dict[str, Any]]]:
    if provenance == "core_example":
        rows = evidence.get("core_examples", [])
        key = "example_id"
    elif provenance == "enrichment_check":
        rows = evidence.get("enrichment_checks", [])
        key = "check_id"
    else:
        return []

    candidates: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ref = row.get(key)
        if not isinstance(ref, str) or not ref:
            continue
        if scene_fragment_ids is not None:
            refs = row.get("fragment_ids", [])
            if not isinstance(refs, list) or not scene_fragment_ids.intersection(refs):
                continue
        candidates.append((ref, row))
    return candidates


def _row_value(row: dict[str, Any], provenance: str, kind: str) -> str | None:
    if kind == "code":
        value = row.get("input") if provenance == "core_example" else row.get("code")
        return value if isinstance(value, str) and value else None
    if kind in {"output", "state"}:
        value = _canonical_output(row.get("actual_stdout", ""))
        return value or None
    return None


def _matching_rows(
    rows: list[tuple[str, dict[str, Any]]],
    *,
    provenance: str,
    kind: str,
    content: str,
) -> list[tuple[str, dict[str, Any]]]:
    return [
        (ref, row)
        for ref, row in rows
        if _row_value(row, provenance, kind) == content
    ]


def repair_evidence_refs(
    plan: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    """Return copy with only safe stdout canonicalization/source_ref repairs."""
    repaired = copy.deepcopy(plan)
    ref_changes: list[dict[str, str]] = []
    content_normalizations: list[dict[str, str]] = []

    for scene in repaired.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("scene_id", ""))
        fragment_ids = {
            value for value in scene.get("narration_fragment_ids", [])
            if isinstance(value, str) and value
        }
        for element in scene.get("visible_elements", []):
            if not isinstance(element, dict):
                continue
            provenance = element.get("provenance")
            if provenance not in {"core_example", "enrichment_check"}:
                continue
            kind = element.get("kind")
            content = element.get("content")
            old_ref = element.get("source_ref")
            if kind not in {"code", "output", "state"} or not isinstance(content, str):
                continue

            element_id = str(element.get("element_id", ""))
            if kind in {"output", "state"}:
                canonical = _canonical_output(content)
                if canonical != content:
                    element["content"] = canonical
                    content_normalizations.append({
                        "scene_id": scene_id,
                        "element_id": element_id,
                        "kind": str(kind),
                        "old_content": content,
                        "new_content": canonical,
                        "normalization": "remove_trailing_crlf_only",
                    })
                    content = canonical

            all_rows = _candidate_rows(
                provenance,
                evidence=evidence,
                scene_fragment_ids=None,
            )
            current = [row for ref, row in all_rows if ref == old_ref]
            if len(current) == 1 and _row_value(current[0], provenance, kind) == content:
                continue

            scene_rows = _candidate_rows(
                provenance,
                evidence=evidence,
                scene_fragment_ids=fragment_ids,
            )
            scene_matches = _matching_rows(
                scene_rows,
                provenance=provenance,
                kind=kind,
                content=content,
            )
            if len(scene_matches) == 1:
                matches = scene_matches
                match_scope = "scene_fragments"
            elif len(scene_matches) > 1:
                raise M3bRecoveryError(
                    f"Cannot recover {scene_id}/{element_id}: canonical content {content!r} "
                    "matches multiple evidence rows in the scene fragments."
                )
            else:
                global_matches = _matching_rows(
                    all_rows,
                    provenance=provenance,
                    kind=kind,
                    content=content,
                )
                if len(global_matches) == 1:
                    matches = global_matches
                    match_scope = "global_unique"
                elif not global_matches:
                    raise M3bRecoveryError(
                        f"Cannot recover {scene_id}/{element_id}: canonical content {content!r} "
                        "matches no evidence row globally."
                    )
                else:
                    raise M3bRecoveryError(
                        f"Cannot recover {scene_id}/{element_id}: canonical content {content!r} "
                        "matches multiple evidence rows globally and none is uniquely linked to the scene."
                    )

            new_ref = matches[0][0]
            element["source_ref"] = new_ref
            ref_changes.append({
                "scene_id": scene_id,
                "element_id": element_id,
                "provenance": str(provenance),
                "kind": str(kind),
                "content": content,
                "old_source_ref": str(old_ref or ""),
                "new_source_ref": new_ref,
                "match_scope": match_scope,
            })

    return repaired, ref_changes, content_normalizations


def recover_failed_m3b(failed_run_dir: Path) -> dict[str, Any]:
    failed_run_dir = failed_run_dir.expanduser().resolve()
    failed_summary = load_json(failed_run_dir / "summary.json")
    _require(failed_summary.get("stage") == "M3b", "Input is not an M3b run.")
    _require(
        failed_summary.get("status") == "INVALID_OUTPUT"
        and failed_summary.get("outcome") == "INVALID_OUTPUT",
        "Recovery accepts only an M3b run rejected as INVALID_OUTPUT.",
    )

    designer_dir = failed_run_dir / "scene_designer"
    draft = load_json(designer_dir / "output.json")
    receipt = load_json(designer_dir / "receipt.json")
    _require(
        receipt.get("output_sha256") == canonical_hash(draft),
        "Saved scene-designer output does not match its receipt hash.",
    )

    source_m3a = failed_summary.get("source_m3a_run")
    _require(isinstance(source_m3a, str) and source_m3a, "Failed M3b run has no M3a source.")
    verified = verify_m3a_selection(Path(source_m3a))
    approved = verified["approved"]
    evidence = build_evidence_packet(approved)

    repaired, ref_changes, content_normalizations = repair_evidence_refs(draft, evidence)
    _require(
        ref_changes or content_normalizations,
        "Draft needs no deterministic evidence/display recovery.",
    )
    validate_scene_plan(
        repaired,
        artifact=approved["artifact"],
        evidence=evidence,
        selected_variant=verified["selected_variant"],
        config=load_json(ROOT / "config" / "m3b_scene_plan.json"),
    )

    run_dir = ROOT / "runs" / "m3b-scene-plan" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    plan_sha = canonical_hash(repaired)
    (run_dir / "scene-plan.json").write_bytes(
        (json.dumps(repaired, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    recovery_report = {
        "schema_version": 3,
        "recovery_kind": "evidence_binding_and_stdout_canonicalization",
        "source_failed_m3b_run": str(failed_run_dir),
        "source_designer_session_id": receipt.get("session_id"),
        "source_designer_output_sha256": receipt.get("output_sha256"),
        "llm_called": False,
        "semantic_content_changed": False,
        "allowed_content_normalization": "remove_trailing_crlf_only",
        "binding_policy": "prefer_scene_fragment_match_then_global_unique",
        "content_normalizations": content_normalizations,
        "content_normalization_count": len(content_normalizations),
        "source_ref_changes": ref_changes,
        "repaired_binding_count": len(ref_changes),
        "scene_plan_sha256": plan_sha,
    }
    recovery_report["recovery_report_sha256"] = canonical_hash(recovery_report)
    (run_dir / "recovery-report.json").write_bytes(
        (json.dumps(recovery_report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )

    summary = {
        "stage": "M3b",
        "lesson_id": failed_summary.get("lesson_id"),
        "status": "COMPLETED",
        "outcome": "READY_FOR_PREVIEW_BUILD",
        "source_m3a_run": source_m3a,
        "reports": str(run_dir),
        "gate_a_required": True,
        "m3a_selection_required": True,
        "gate_b_reached": False,
        "gate_b_approved": False,
        "audio_called": False,
        "render_called": False,
        "production_ready": False,
        "artifact_sha256": approved["artifact_sha256"],
        "gate_a_approval_sha256": approved["approval_sha256"],
        "m3a_selection_sha256": verified["selection_sha256"],
        "selected_variant_id": verified["selection"]["selected_variant_id"],
        "selected_by": verified["selection"]["selected_by"],
        "scene_designer_session_id": receipt.get("session_id"),
        "scene_designer_session_new": False,
        "recovered_from_m3b_run": str(failed_run_dir),
        "deterministic_recovery": True,
        "recovery_report_sha256": recovery_report["recovery_report_sha256"],
        "content_normalization_count": len(content_normalizations),
        "repaired_binding_count": len(ref_changes),
        "scene_plan_sha256": plan_sha,
        "scene_count": len(repaired.get("scenes", [])),
        "component_request_count": len(repaired.get("component_requests", [])),
        "next_action": "BUILD_PREVIEW",
    }
    (run_dir / "summary.json").write_bytes(
        (json.dumps(summary, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("failed_m3b_run_dir", help="M3b run rejected as INVALID_OUTPUT")
    args = parser.parse_args()
    try:
        summary = recover_failed_m3b(Path(args.failed_m3b_run_dir))
    except Exception as exc:
        print(json.dumps({"m3b_recovery": "ERROR", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
