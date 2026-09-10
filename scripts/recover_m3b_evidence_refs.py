"""Recover an M3b draft rejected only because evidence source_ref is wrong.

This recovery never changes narration, visual content, code, output, scene layout,
or design decisions. It may only rebind an evidence-backed element to another
existing example_id/check_id when the element content has exactly one matching
evidence row linked to the same scene narration fragments. The original failed
M3b run remains untouched; a successful recovery creates a new M3b run.
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


def _candidate_rows(
    provenance: str,
    *,
    evidence: dict[str, Any],
    scene_fragment_ids: set[str],
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
        refs = row.get("fragment_ids", [])
        if not isinstance(ref, str) or not ref:
            continue
        if not isinstance(refs, list) or not scene_fragment_ids.intersection(refs):
            continue
        candidates.append((ref, row))
    return candidates


def _row_value(row: dict[str, Any], provenance: str, kind: str) -> str | None:
    if kind == "code":
        value = row.get("input") if provenance == "core_example" else row.get("code")
        return value if isinstance(value, str) and value else None
    if kind in {"output", "state"}:
        value = str(row.get("actual_stdout", "")).strip()
        return value or None
    return None


def repair_evidence_refs(
    plan: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Return a copy with only uniquely recoverable evidence source_refs changed."""
    repaired = copy.deepcopy(plan)
    changes: list[dict[str, str]] = []

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

            rows = _candidate_rows(
                provenance,
                evidence=evidence,
                scene_fragment_ids=fragment_ids,
            )
            current = [row for ref, row in rows if ref == old_ref]
            if len(current) == 1 and _row_value(current[0], provenance, kind) == content:
                continue

            matches = [
                (ref, row)
                for ref, row in rows
                if _row_value(row, provenance, kind) == content
            ]
            if len(matches) != 1:
                element_id = element.get("element_id")
                if not matches:
                    raise M3bRecoveryError(
                        f"Cannot recover {scene_id}/{element_id}: content {content!r} "
                        "matches no evidence row in the scene fragments."
                    )
                raise M3bRecoveryError(
                    f"Cannot recover {scene_id}/{element_id}: content {content!r} "
                    "matches multiple evidence rows in the scene fragments."
                )

            new_ref = matches[0][0]
            element["source_ref"] = new_ref
            changes.append({
                "scene_id": scene_id,
                "element_id": str(element.get("element_id", "")),
                "provenance": str(provenance),
                "kind": str(kind),
                "content": content,
                "old_source_ref": str(old_ref or ""),
                "new_source_ref": new_ref,
            })

    return repaired, changes


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

    repaired, changes = repair_evidence_refs(draft, evidence)
    _require(changes, "Draft needs no deterministic source_ref recovery.")
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
        "schema_version": 1,
        "recovery_kind": "evidence_source_ref_only",
        "source_failed_m3b_run": str(failed_run_dir),
        "source_designer_session_id": receipt.get("session_id"),
        "source_designer_output_sha256": receipt.get("output_sha256"),
        "llm_called": False,
        "content_changed": False,
        "source_ref_changes": changes,
        "repaired_binding_count": len(changes),
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
        "repaired_binding_count": len(changes),
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
