"""Recover an M3b draft rejected by evidence binding/display formatting.

This recovery is deterministic. It never changes narration, scene layout, code,
semantic values, beats, or visual design decisions. It may only:

1. remove trailing CR/LF characters from evidence-backed output/state content;
2. rebind source_ref to another existing example_id/check_id when the canonical
   content identifies exactly one evidence row. Matching prefers evidence linked
   to the current scene fragments, but may fall back to a globally unique row;
3. for kind=code only, reclassify an evidence-backed element as
   approved_narration when the exact code string occurs verbatim in exactly one
   approved narration fragment (preferring the current scene). This is not
   execution evidence and is recorded separately;
4. for kind=state only, reclassify a scalar value as derived_evidence when it is
   exactly one indexed item of a tuple/list parsed from actual_stdout. The
   source_ref records the original evidence id and item index.

Output elements can never use narration or derived-state fallbacks. The original
failed M3b run remains untouched; a successful recovery creates a new M3b run
and records every permitted change.
"""
from __future__ import annotations

import argparse
import ast
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
    canonical_stdout_display,
    encode_derived_ref,
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
        value = canonical_stdout_display(row.get("actual_stdout", ""))
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


def _derived_matches(
    rows: list[tuple[str, dict[str, Any]]],
    *,
    content: str,
) -> list[tuple[str, int]]:
    """Find scalar tuple/list items whose Python repr is exactly content."""
    matches: list[tuple[str, int]] = []
    for ref, row in rows:
        stdout = canonical_stdout_display(row.get("actual_stdout", ""))
        if not stdout:
            continue
        try:
            parsed = ast.literal_eval(stdout)
        except (SyntaxError, ValueError):
            continue
        if not isinstance(parsed, (tuple, list)):
            continue
        for index, value in enumerate(parsed):
            if value is not None and not isinstance(value, (str, int, float, bool, complex)):
                continue
            if repr(value) == content:
                matches.append((ref, index))
    return matches


def _narration_matches(
    artifact: dict[str, Any] | None,
    content: str,
    scene_fragment_ids: set[str] | None,
) -> list[str]:
    if not isinstance(artifact, dict):
        return []
    matches: list[str] = []
    for row in artifact.get("narration", []):
        if not isinstance(row, dict):
            continue
        fragment_id = row.get("fragment_id")
        text = row.get("text")
        if not isinstance(fragment_id, str) or not fragment_id or not isinstance(text, str):
            continue
        if scene_fragment_ids is not None and fragment_id not in scene_fragment_ids:
            continue
        if content in text:
            matches.append(fragment_id)
    return matches


def _apply_derived_state(
    element: dict[str, Any],
    *,
    scene_id: str,
    provenance: str,
    old_ref: Any,
    evidence_ref: str,
    index: int,
    match_scope: str,
    provenance_changes: list[dict[str, str]],
) -> None:
    new_ref = encode_derived_ref(provenance, evidence_ref, index)
    content = str(element.get("content", ""))
    element["provenance"] = "derived_evidence"
    element["source_ref"] = new_ref
    provenance_changes.append({
        "scene_id": scene_id,
        "element_id": str(element.get("element_id", "")),
        "kind": "state",
        "content": content,
        "old_provenance": provenance,
        "new_provenance": "derived_evidence",
        "old_source_ref": str(old_ref or ""),
        "new_source_ref": new_ref,
        "match_scope": match_scope,
        "derivation": f"stdout_literal[{index}]",
        "reason": "scalar_item_of_verified_tuple_or_list_stdout",
    })


def repair_evidence_refs(
    plan: dict[str, Any],
    evidence: dict[str, Any],
    artifact: dict[str, Any] | None = None,
) -> tuple[
    dict[str, Any],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    """Return a copy with only safe display/binding/provenance repairs."""
    repaired = copy.deepcopy(plan)
    ref_changes: list[dict[str, str]] = []
    content_normalizations: list[dict[str, str]] = []
    provenance_changes: list[dict[str, str]] = []

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
                canonical = canonical_stdout_display(content)
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
            current_pairs = [(ref, row) for ref, row in all_rows if ref == old_ref]
            if len(current_pairs) == 1:
                current_row = current_pairs[0][1]
                if _row_value(current_row, provenance, kind) == content:
                    continue
                if kind == "state":
                    current_derived = _derived_matches(current_pairs, content=content)
                    if len(current_derived) == 1:
                        evidence_ref, index = current_derived[0]
                        _apply_derived_state(
                            element,
                            scene_id=scene_id,
                            provenance=provenance,
                            old_ref=old_ref,
                            evidence_ref=evidence_ref,
                            index=index,
                            match_scope="current_source_ref",
                            provenance_changes=provenance_changes,
                        )
                        continue
                    if len(current_derived) > 1:
                        raise M3bRecoveryError(
                            f"Cannot recover {scene_id}/{element_id}: state {content!r} is ambiguous "
                            "within the currently referenced structured stdout."
                        )

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
                elif len(global_matches) > 1:
                    raise M3bRecoveryError(
                        f"Cannot recover {scene_id}/{element_id}: canonical content {content!r} "
                        "matches multiple evidence rows globally and none is uniquely linked to the scene."
                    )
                else:
                    matches = []
                    match_scope = ""

            if matches:
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
                continue

            # State is allowed to expose one scalar item of an executed tuple/list.
            # Prefer the current scene, then require a globally unique derivation.
            if kind == "state":
                scene_derived = _derived_matches(scene_rows, content=content)
                if len(scene_derived) == 1:
                    derived_matches = scene_derived
                    derived_scope = "scene_fragments"
                elif len(scene_derived) > 1:
                    raise M3bRecoveryError(
                        f"Cannot recover {scene_id}/{element_id}: state {content!r} matches multiple "
                        "derived items in structured stdout linked to the scene."
                    )
                else:
                    global_derived = _derived_matches(all_rows, content=content)
                    if len(global_derived) == 1:
                        derived_matches = global_derived
                        derived_scope = "global_unique"
                    elif len(global_derived) > 1:
                        raise M3bRecoveryError(
                            f"Cannot recover {scene_id}/{element_id}: state {content!r} matches multiple "
                            "derived items globally and none is unique in the scene."
                        )
                    else:
                        derived_matches = []
                        derived_scope = ""
                if derived_matches:
                    evidence_ref, index = derived_matches[0]
                    _apply_derived_state(
                        element,
                        scene_id=scene_id,
                        provenance=provenance,
                        old_ref=old_ref,
                        evidence_ref=evidence_ref,
                        index=index,
                        match_scope=derived_scope,
                        provenance_changes=provenance_changes,
                    )
                    continue

            # No exact execution-evidence row exists. For CODE only, an exact
            # approved narration substring is a legal provenance source. This
            # preserves the displayed code and does not pretend it was executed.
            if kind == "code":
                scene_narration_matches = _narration_matches(artifact, content, fragment_ids)
                if len(scene_narration_matches) == 1:
                    narration_matches = scene_narration_matches
                    narration_scope = "scene_fragments"
                elif len(scene_narration_matches) > 1:
                    raise M3bRecoveryError(
                        f"Cannot recover {scene_id}/{element_id}: code {content!r} occurs in multiple "
                        "approved narration fragments in the scene."
                    )
                else:
                    global_narration_matches = _narration_matches(artifact, content, None)
                    if len(global_narration_matches) == 1:
                        narration_matches = global_narration_matches
                        narration_scope = "global_unique"
                    elif len(global_narration_matches) > 1:
                        raise M3bRecoveryError(
                            f"Cannot recover {scene_id}/{element_id}: code {content!r} occurs in multiple "
                            "approved narration fragments globally and none is unique in the scene."
                        )
                    else:
                        narration_matches = []
                        narration_scope = ""

                if narration_matches:
                    new_ref = narration_matches[0]
                    element["provenance"] = "approved_narration"
                    element["source_ref"] = new_ref
                    provenance_changes.append({
                        "scene_id": scene_id,
                        "element_id": element_id,
                        "kind": "code",
                        "content": content,
                        "old_provenance": str(provenance),
                        "new_provenance": "approved_narration",
                        "old_source_ref": str(old_ref or ""),
                        "new_source_ref": new_ref,
                        "match_scope": narration_scope,
                        "reason": "exact_code_substring_of_approved_narration",
                    })
                    continue

            raise M3bRecoveryError(
                f"Cannot recover {scene_id}/{element_id}: canonical content {content!r} "
                "has no permitted exact or deterministic provenance."
            )

    return repaired, ref_changes, content_normalizations, provenance_changes


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

    repaired, ref_changes, content_normalizations, provenance_changes = repair_evidence_refs(
        draft,
        evidence,
        approved["artifact"],
    )
    _require(
        ref_changes or content_normalizations or provenance_changes,
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
    derived_count = sum(
        1 for row in provenance_changes if row.get("new_provenance") == "derived_evidence"
    )
    narration_reclass_count = sum(
        1 for row in provenance_changes if row.get("new_provenance") == "approved_narration"
    )
    recovery_report = {
        "schema_version": 5,
        "recovery_kind": "evidence_binding_stdout_narration_code_and_derived_state",
        "source_failed_m3b_run": str(failed_run_dir),
        "source_designer_session_id": receipt.get("session_id"),
        "source_designer_output_sha256": receipt.get("output_sha256"),
        "llm_called": False,
        "semantic_content_changed": False,
        "allowed_content_normalization": "remove_trailing_crlf_only",
        "binding_policy": "prefer_current_ref_then_scene_fragment_match_then_global_unique",
        "approved_narration_fallback": "code_only_exact_substring",
        "derived_state_policy": "state_only_scalar_index_from_tuple_or_list_actual_stdout",
        "content_normalizations": content_normalizations,
        "content_normalization_count": len(content_normalizations),
        "source_ref_changes": ref_changes,
        "repaired_binding_count": len(ref_changes),
        "provenance_changes": provenance_changes,
        "provenance_change_count": len(provenance_changes),
        "derived_state_count": derived_count,
        "approved_narration_reclassification_count": narration_reclass_count,
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
        "provenance_change_count": len(provenance_changes),
        "derived_state_count": derived_count,
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
