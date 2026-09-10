"""M3b: selected M3a variant -> full lesson scene plan.

The Gate A narration remains immutable. A fresh scene-designer session expands
the human-selected calibration mechanic into a traceable whole-lesson plan.
No audio or render is produced in this stage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flows.m2b_verify import load_json  # noqa: E402
from flows.m3a_scene_variants import collect_prior_sessions, verify_gate_a_approval  # noqa: E402
from runners.codex_role import CodexRoleRunner, RoleRunnerError  # noqa: E402
from scripts.m3a_review import M3aReviewError, verify_m3a  # noqa: E402
from scripts.record_gate_a_approval import canonical_hash  # noqa: E402

CONFIG = ROOT / "config" / "m3b_scene_plan.json"
PROMPT = ROOT / "prompts" / "scene_plan_designer.md"
ELEMENT_KINDS = ("code", "output", "label", "state", "panel", "diagram", "pointer_target", "other")
PROVENANCE = ("approved_narration", "core_example", "enrichment_check", "visual_label")


def scene_plan_schema(config: dict, artifact_sha256: str, approval_sha256: str, selection_sha256: str) -> dict:
    element = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "element_id": {"type": "string"},
            "kind": {"type": "string", "enum": list(ELEMENT_KINDS)},
            "provenance": {"type": "string", "enum": list(PROVENANCE)},
            "source_ref": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["element_id", "kind", "provenance", "source_ref", "content"],
    }
    beat = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "beat_id": {"type": "string"},
            "narration_fragment_id": {"type": "string"},
            "anchor_text": {"type": "string"},
            "action": {"type": "string"},
            "focus_target_id": {"type": "string"},
            "reveals": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "beat_id", "narration_fragment_id", "anchor_text", "action",
            "focus_target_id", "reveals",
        ],
    }
    scene = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "scene_id": {"type": "string"},
            "title": {"type": "string"},
            "scene_type": {"type": "string", "enum": config["scene_types"]},
            "narration_fragment_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "pedagogical_goal": {"type": "string"},
            "visual_strategy": {"type": "string"},
            "calibration_variant_id": {"type": "string"},
            "requires_new_component": {"type": "boolean"},
            "component_request_id": {"type": "string"},
            "visible_elements": {"type": "array", "minItems": 1, "items": element},
            "beats": {"type": "array", "minItems": 1, "items": beat},
            "risks": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "scene_id", "title", "scene_type", "narration_fragment_ids",
            "pedagogical_goal", "visual_strategy", "calibration_variant_id",
            "requires_new_component", "component_request_id", "visible_elements",
            "beats", "risks",
        ],
    }
    component = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "component_id": {"type": "string"},
            "purpose": {"type": "string"},
            "used_in_scene_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "origin_variant_id": {"type": "string"},
        },
        "required": ["component_id", "purpose", "used_in_scene_ids", "origin_variant_id"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "integer", "enum": [1]},
            "artifact_sha256": {"type": "string", "enum": [artifact_sha256]},
            "gate_a_approval_sha256": {"type": "string", "enum": [approval_sha256]},
            "m3a_selection_sha256": {"type": "string", "enum": [selection_sha256]},
            "role": {"type": "string", "enum": ["scene_designer"]},
            "lesson_title": {"type": "string"},
            "selected_calibration_variant_id": {"type": "string"},
            "scenes": {"type": "array", "minItems": 1, "items": scene},
            "component_requests": {"type": "array", "items": component},
            "design_note": {"type": "string"},
        },
        "required": [
            "schema_version", "artifact_sha256", "gate_a_approval_sha256",
            "m3a_selection_sha256", "role", "lesson_title",
            "selected_calibration_variant_id", "scenes", "component_requests",
            "design_note",
        ],
    }


def _verify_self_hash(value: dict, key: str, status: str, message: str) -> str:
    saved = value.get(key)
    unhashed = {name: item for name, item in value.items() if name != key}
    if not isinstance(saved, str) or canonical_hash(unhashed) != saved:
        raise RoleRunnerError(status, message)
    return saved


def verify_m3a_selection(m3a_run_dir: Path) -> dict:
    try:
        reviewed = verify_m3a(m3a_run_dir)
    except M3aReviewError as exc:
        raise RoleRunnerError("BLOCKED_SELECTION", str(exc)) from exc
    summary = reviewed["summary"]
    selection = load_json(reviewed["run_dir"] / "m3a-selection.json")
    selection_sha = _verify_self_hash(
        selection, "selection_sha256", "BLOCKED_SELECTION", "M3a selection receipt has an invalid self-hash."
    )
    if selection.get("decision") != "SELECT":
        raise RoleRunnerError("BLOCKED_SELECTION", "M3a selection receipt is not a SELECT decision.")
    for key in ("artifact_sha256", "gate_a_approval_sha256", "scene_variants_sha256"):
        if selection.get(key) != summary.get(key):
            raise RoleRunnerError("BLOCKED_SELECTION", f"M3a selection {key} does not match the M3a run.")
    if selection.get("source_m3a_run") != str(reviewed["run_dir"]):
        raise RoleRunnerError("BLOCKED_SELECTION", "M3a selection points to another run directory.")

    variant_id = selection.get("selected_variant_id")
    variants = reviewed["variants"].get("variants", [])
    matches = [row for row in variants if isinstance(row, dict) and row.get("variant_id") == variant_id]
    if len(matches) != 1:
        raise RoleRunnerError("BLOCKED_SELECTION", "Selected M3a variant is missing or ambiguous.")
    selected_variant = matches[0]
    if selection.get("selected_variant_sha256") != canonical_hash(selected_variant):
        raise RoleRunnerError("BLOCKED_SELECTION", "Selected M3a variant payload changed after selection.")

    source_m2f = summary.get("source_m2f_run")
    if not isinstance(source_m2f, str) or not source_m2f:
        raise RoleRunnerError("BLOCKED_INPUT", "M3a does not identify its M2f source.")
    approved = verify_gate_a_approval(Path(source_m2f))
    if approved["artifact_sha256"] != summary.get("artifact_sha256"):
        raise RoleRunnerError("BLOCKED_GATE_A", "M3a and Gate A artifact hashes differ.")
    if approved["approval_sha256"] != summary.get("gate_a_approval_sha256"):
        raise RoleRunnerError("BLOCKED_GATE_A", "M3a and Gate A approval hashes differ.")

    knowhow = load_json(reviewed["run_dir"] / "visual-knowhow-source-pack.json")
    _verify_self_hash(
        knowhow, "source_pack_sha256", "BLOCKED_SOURCE", "M3a visual know-how source pack hash is invalid."
    )
    return {
        "m3a_run_dir": reviewed["run_dir"],
        "m3a_summary": summary,
        "selection": selection,
        "selection_sha256": selection_sha,
        "selected_variant": selected_variant,
        "approved": approved,
        "knowhow": knowhow,
    }


def build_evidence_packet(approved: dict) -> dict:
    core = approved["core_evidence"].get("results", [])
    enrichment = approved["enrichment_evidence"].get("results", [])
    return {
        "core_examples": core,
        "enrichment_checks": enrichment,
    }


def _evidence_maps(evidence: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    core = {row.get("example_id"): row for row in evidence.get("core_examples", []) if isinstance(row, dict)}
    enrichment = {row.get("check_id"): row for row in evidence.get("enrichment_checks", []) if isinstance(row, dict)}
    return core, enrichment


def _validate_element(element: dict, fragments: dict[str, str], core: dict[str, dict], enrichment: dict[str, dict]) -> None:
    provenance = element["provenance"]
    ref = element["source_ref"]
    content = element["content"]
    kind = element["kind"]
    if not isinstance(content, str) or not content:
        raise RoleRunnerError("INVALID_OUTPUT", "Visible element content must be non-empty.")
    if provenance == "visual_label":
        if ref != "":
            raise RoleRunnerError("INVALID_OUTPUT", "visual_label elements must have empty source_ref.")
        if len(content.split()) > 5:
            raise RoleRunnerError("INVALID_OUTPUT", "visual_label elements may contain at most five words.")
        return
    if provenance == "approved_narration":
        if ref not in fragments or content not in fragments[ref]:
            raise RoleRunnerError("INVALID_OUTPUT", "approved_narration element is not an exact narration substring.")
        return
    table = core if provenance == "core_example" else enrichment
    if ref not in table:
        raise RoleRunnerError("INVALID_OUTPUT", f"Visible element references unknown evidence id {ref!r}.")
    row = table[ref]
    code = row.get("input") if provenance == "core_example" else row.get("code")
    stdout = str(row.get("actual_stdout", "")).strip()
    if kind == "code":
        if content != code:
            raise RoleRunnerError("INVALID_OUTPUT", f"Code element {element['element_id']} differs from evidence.")
    elif kind in {"output", "state"}:
        if not stdout or content != stdout:
            raise RoleRunnerError("INVALID_OUTPUT", f"Output/state element {element['element_id']} differs from evidence.")
    else:
        raise RoleRunnerError(
            "INVALID_OUTPUT",
            f"Evidence-backed element {element['element_id']} must be code, output or state.",
        )


def validate_scene_plan(plan: dict, *, artifact: dict, evidence: dict, selected_variant: dict, config: dict) -> None:
    if plan.get("lesson_title") != artifact.get("title"):
        raise RoleRunnerError("INVALID_OUTPUT", "Scene planner changed the approved lesson title.")
    selected_id = selected_variant.get("variant_id")
    if plan.get("selected_calibration_variant_id") != selected_id:
        raise RoleRunnerError("INVALID_OUTPUT", "Scene plan does not bind the human-selected calibration variant.")

    narration = artifact.get("narration", [])
    fragment_ids = [row.get("fragment_id") for row in narration if isinstance(row, dict)]
    fragments = {row["fragment_id"]: row["text"] for row in narration}
    scenes = plan.get("scenes", [])
    flat = [fragment_id for scene in scenes for fragment_id in scene.get("narration_fragment_ids", [])]
    if flat != fragment_ids:
        raise RoleRunnerError(
            "INVALID_OUTPUT",
            "Scenes must cover every approved narration fragment exactly once and preserve order.",
        )

    scene_ids = [scene.get("scene_id") for scene in scenes]
    if len(scene_ids) != len(set(scene_ids)) or any(not isinstance(value, str) or not value for value in scene_ids):
        raise RoleRunnerError("INVALID_OUTPUT", "Scene ids must be unique and non-empty.")
    core, enrichment = _evidence_maps(evidence)
    component_rows = plan.get("component_requests", [])
    component_ids = [row.get("component_id") for row in component_rows if isinstance(row, dict)]
    if len(component_ids) != len(component_rows) or len(component_ids) != len(set(component_ids)) or any(not value for value in component_ids):
        raise RoleRunnerError("INVALID_OUTPUT", "Component request ids must be unique and non-empty.")
    component_by_id = {row["component_id"]: row for row in component_rows}
    scene_id_set = set(scene_ids)
    for row in component_rows:
        used = row.get("used_in_scene_ids", [])
        if not used or any(scene_id not in scene_id_set for scene_id in used):
            raise RoleRunnerError("INVALID_OUTPUT", f"Component {row.get('component_id')} has invalid scene references.")

    calibration_fragments = set()
    for variant_beat in selected_variant.get("beats", []):
        calibration_fragments.update(variant_beat.get("narration_fragment_ids", []))
    selected_scenes = [scene for scene in scenes if calibration_fragments.intersection(scene["narration_fragment_ids"])]
    if len(selected_scenes) != 1:
        raise RoleRunnerError("INVALID_OUTPUT", "Selected calibration fragments must remain together in one scene.")
    selected_scene = selected_scenes[0]
    if selected_scene.get("calibration_variant_id") != selected_id:
        raise RoleRunnerError("INVALID_OUTPUT", "Calibration scene does not name the selected variant.")
    if selected_scene.get("visual_strategy") != selected_variant.get("visual_strategy"):
        raise RoleRunnerError("INVALID_OUTPUT", "Calibration scene changed the selected visual strategy.")
    if selected_variant.get("requires_new_component") is True and selected_scene.get("requires_new_component") is not True:
        raise RoleRunnerError("INVALID_OUTPUT", "Calibration scene dropped the selected variant's required component.")

    all_beat_fragments: set[str] = set()
    all_element_ids: set[str] = set()
    for scene in scenes:
        if scene is not selected_scene and scene.get("calibration_variant_id") != "":
            raise RoleRunnerError("INVALID_OUTPUT", "Only the calibration scene may name an M3a variant.")
        if scene.get("requires_new_component") is True:
            request_id = scene.get("component_request_id")
            if request_id not in component_by_id or scene["scene_id"] not in component_by_id[request_id]["used_in_scene_ids"]:
                raise RoleRunnerError("INVALID_OUTPUT", f"Scene {scene['scene_id']} has an invalid component request binding.")
        elif scene.get("component_request_id") != "":
            raise RoleRunnerError("INVALID_OUTPUT", f"Scene {scene['scene_id']} must have empty component_request_id.")

        elements = scene.get("visible_elements", [])
        element_ids = [row.get("element_id") for row in elements if isinstance(row, dict)]
        if len(element_ids) != len(elements) or len(element_ids) != len(set(element_ids)) or any(not value for value in element_ids):
            raise RoleRunnerError("INVALID_OUTPUT", f"Scene {scene['scene_id']} has invalid element ids.")
        if all_element_ids.intersection(element_ids):
            raise RoleRunnerError("INVALID_OUTPUT", "Visible element ids must be globally unique across the scene plan.")
        all_element_ids.update(element_ids)
        for element in elements:
            _validate_element(element, fragments, core, enrichment)
        known_elements = set(element_ids)

        scene_fragments = set(scene["narration_fragment_ids"])
        beat_ids: set[str] = set()
        for beat in scene.get("beats", []):
            beat_id = beat.get("beat_id")
            if not isinstance(beat_id, str) or not beat_id or beat_id in beat_ids:
                raise RoleRunnerError("INVALID_OUTPUT", f"Scene {scene['scene_id']} has invalid beat ids.")
            beat_ids.add(beat_id)
            fragment_id = beat.get("narration_fragment_id")
            if fragment_id not in scene_fragments:
                raise RoleRunnerError("INVALID_OUTPUT", f"Beat {beat_id} references a fragment outside its scene.")
            anchor = beat.get("anchor_text")
            if not isinstance(anchor, str) or not anchor or anchor not in fragments[fragment_id]:
                raise RoleRunnerError("INVALID_OUTPUT", f"Beat {beat_id} anchor is not an exact substring of approved narration.")
            if beat.get("focus_target_id") not in known_elements:
                raise RoleRunnerError("INVALID_OUTPUT", f"Beat {beat_id} has an unknown focus target.")
            if any(ref not in known_elements for ref in beat.get("reveals", [])):
                raise RoleRunnerError("INVALID_OUTPUT", f"Beat {beat_id} reveals an unknown element.")
            all_beat_fragments.add(fragment_id)

    if all_beat_fragments != set(fragment_ids):
        missing = sorted(set(fragment_ids) - all_beat_fragments)
        raise RoleRunnerError("INVALID_OUTPUT", "Every narration fragment needs at least one beat; missing: " + ", ".join(missing))

    if selected_variant.get("requires_new_component") is True:
        request_id = selected_scene.get("component_request_id")
        request = component_by_id.get(request_id, {})
        if request.get("origin_variant_id") != selected_id:
            raise RoleRunnerError("INVALID_OUTPUT", "Calibration component request lost its M3a variant provenance.")

    required_states = {
        element.get("content") for element in selected_variant.get("visible_elements", [])
        if isinstance(element, dict) and element.get("kind") == "state"
    }
    planned_states = {
        element.get("content") for element in selected_scene.get("visible_elements", [])
        if isinstance(element, dict) and element.get("kind") == "state"
    }
    if not required_states.issubset(planned_states):
        raise RoleRunnerError("INVALID_OUTPUT", "Calibration scene does not preserve the selected variant's state model.")


@task(name="m3b-full-scene-plan-designer", retries=0, cache_policy=NO_CACHE, persist_result=False)
def design_task(config: dict, verified: dict, evidence: dict, run_dir: str) -> dict:
    runner = CodexRoleRunner(model=config["model"], reasoning_effort=config["reasoning_effort"])
    runner.preflight()
    approved = verified["approved"]
    selection = verified["selection"]
    selected_variant = verified["selected_variant"]
    payload = {
        "role_instructions": PROMPT.read_text(encoding="utf-8"),
        "artifact_sha256": approved["artifact_sha256"],
        "gate_a_approval_sha256": approved["approval_sha256"],
        "m3a_selection_sha256": verified["selection_sha256"],
        "approved_artifact": {
            "title": approved["artifact"]["title"],
            "narration": approved["artifact"]["narration"],
        },
        "execution_evidence": evidence,
        "selected_calibration": {
            "target_fragment_ids": verified["m3a_summary"]["target_fragment_ids"],
            "variant": selected_variant,
            "selected_by": selection["selected_by"],
        },
        "visual_knowhow_source_pack": verified["knowhow"],
        "allowed_scene_types": config["scene_types"],
        "constraints": [
            "Gate A narration and title are immutable.",
            "Cover every narration fragment exactly once and preserve fragment order.",
            "Every fragment needs at least one semantic beat with an exact narration anchor substring.",
            "Every factual code/output/state visual must be traceable to supplied execution evidence.",
            "Use the selected M3a variant as binding mechanics for its test fragment, but do not copy it indiscriminately to other scenes.",
            "No absolute timing, pixel geometry, TTS, audio, rendering or publication decisions.",
            "Do not include previous author/judge history because it is not supplied.",
        ],
    }
    return runner.run_json(
        role="scene_designer",
        payload=payload,
        schema=scene_plan_schema(
            config, approved["artifact_sha256"], approved["approval_sha256"], verified["selection_sha256"]
        ),
        report_dir=Path(run_dir) / "scene_designer",
    )


@flow(name="video-production-m3b-full-scene-plan", retries=0, persist_result=False)
def m3b_scene_plan(m3a_run_dir: str) -> dict:
    logger = get_run_logger()
    input_dir = Path(m3a_run_dir).expanduser().resolve()
    config = load_json(CONFIG)
    run_dir = ROOT / "runs" / "m3b-scene-plan" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "stage": "M3b",
        "lesson_id": config["lesson_id"],
        "status": "ERROR",
        "outcome": "ERROR",
        "source_m3a_run": str(input_dir),
        "reports": str(run_dir),
        "gate_a_required": True,
        "m3a_selection_required": True,
        "gate_b_reached": False,
        "gate_b_approved": False,
        "audio_called": False,
        "render_called": False,
        "production_ready": False,
    }
    try:
        verified = verify_m3a_selection(input_dir)
        approved = verified["approved"]
        if approved["summary"].get("lesson_id") != config["lesson_id"]:
            raise RoleRunnerError("BLOCKED_INPUT", "M3b config and approved lesson id differ.")
        evidence = build_evidence_packet(approved)
        result = design_task(config, verified, evidence, str(run_dir))
        plan = result["output"]
        validate_scene_plan(
            plan,
            artifact=approved["artifact"],
            evidence=evidence,
            selected_variant=verified["selected_variant"],
            config=config,
        )
        session_id = result["receipt"]["session_id"]
        prior_sessions = collect_prior_sessions(approved)
        prior_sessions.add(verified["m3a_summary"].get("scene_designer_session_id"))
        if session_id in prior_sessions:
            raise RoleRunnerError("SESSION_REUSED", "M3b scene designer reused an earlier Codex session.")

        plan_sha = canonical_hash(plan)
        (run_dir / "scene-plan.json").write_bytes(
            (json.dumps(plan, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        )
        summary.update(
            status="COMPLETED",
            outcome="READY_FOR_PREVIEW_BUILD",
            artifact_sha256=approved["artifact_sha256"],
            gate_a_approval_sha256=approved["approval_sha256"],
            m3a_selection_sha256=verified["selection_sha256"],
            selected_variant_id=verified["selection"]["selected_variant_id"],
            selected_by=verified["selection"]["selected_by"],
            scene_designer_session_id=session_id,
            scene_designer_session_new=True,
            scene_plan_sha256=plan_sha,
            scene_count=len(plan["scenes"]),
            component_request_count=len(plan["component_requests"]),
            next_action="BUILD_PREVIEW",
        )
        logger.info("M3b completed: %d scenes; preview may be built next.", len(plan["scenes"]))
        return summary
    except RoleRunnerError as exc:
        summary["status"] = exc.status
        summary["outcome"] = exc.status
        summary["error"] = str(exc)
        logger.error("%s: %s", exc.status, exc)
        raise
    finally:
        (run_dir / "summary.json").write_bytes(
            (json.dumps(summary, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m3a_run_dir", help="Completed M3a run with a human selection receipt")
    args = parser.parse_args()
    print(json.dumps(m3b_scene_plan(args.m3a_run_dir), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
