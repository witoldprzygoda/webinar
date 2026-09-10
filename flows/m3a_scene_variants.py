"""M3a: approved Gate A artifact -> three scene-design variants -> human choice.

No narration, audio or render is changed here. The scene designer receives only
an approved artifact, execution evidence for the selected fragment and an
explicit pinned visual know-how pack. Output is conceptual scene variants, not
a full lesson scene plan.
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
from runners.codex_role import CodexRoleRunner, RoleRunnerError  # noqa: E402
from runners.source_pack import SourcePackError, build_source_pack  # noqa: E402
from scripts.gate_a_review_enriched import verify_enriched_chain  # noqa: E402
from scripts.record_gate_a_approval import canonical_hash as approval_hash  # noqa: E402

CONFIG = ROOT / "config" / "m3a_scene_variants.json"
PROMPT = ROOT / "prompts" / "scene_variant_designer.md"

VISUAL_KINDS = (
    "code", "output", "label", "state", "pointer_target", "panel", "diagram", "other"
)
VISUAL_SOURCES = ("approved_artifact", "execution_evidence", "visual_label")
STRATEGIES = ("sequential_run", "split_view", "state_model", "code_morph", "custom")


def variant_schema(artifact_sha256: str, approval_sha256: str, variant_count: int) -> dict:
    element = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "element_id": {"type": "string"},
            "kind": {"type": "string", "enum": list(VISUAL_KINDS)},
            "source": {"type": "string", "enum": list(VISUAL_SOURCES)},
            "content": {"type": "string"},
        },
        "required": ["element_id", "kind", "source", "content"],
    }
    beat = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "beat_id": {"type": "string"},
            "narration_fragment_ids": {
                "type": "array", "minItems": 1, "items": {"type": "string"}
            },
            "action": {"type": "string"},
            "focus_target_id": {"type": "string"},
            "reveals": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "beat_id", "narration_fragment_ids", "action", "focus_target_id", "reveals"
        ],
    }
    variant = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "variant_id": {"type": "string"},
            "title": {"type": "string"},
            "concept": {"type": "string"},
            "pedagogical_rationale": {"type": "string"},
            "visual_strategy": {"type": "string", "enum": list(STRATEGIES)},
            "requires_new_component": {"type": "boolean"},
            "new_component_request": {"type": "string"},
            "visible_elements": {"type": "array", "minItems": 1, "items": element},
            "beats": {"type": "array", "minItems": 1, "items": beat},
            "risks": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "variant_id", "title", "concept", "pedagogical_rationale",
            "visual_strategy", "requires_new_component", "new_component_request",
            "visible_elements", "beats", "risks",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "artifact_sha256": {"type": "string", "enum": [artifact_sha256]},
            "gate_a_approval_sha256": {"type": "string", "enum": [approval_sha256]},
            "role": {"type": "string", "enum": ["scene_designer"]},
            "target_fragment_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "design_axis": {"type": "string"},
            "variants": {
                "type": "array", "minItems": variant_count,
                "maxItems": variant_count, "items": variant,
            },
            "comparison_note": {"type": "string"},
        },
        "required": [
            "artifact_sha256", "gate_a_approval_sha256", "role",
            "target_fragment_ids", "design_axis", "variants", "comparison_note",
        ],
    }


def verify_gate_a_approval(m2f_run_dir: Path) -> dict:
    verified = verify_enriched_chain(m2f_run_dir)
    approval_path = verified["run_dir"] / "gate-a-approval.json"
    approval = load_json(approval_path)
    saved_hash = approval.get("approval_sha256")
    unhashed = {key: value for key, value in approval.items() if key != "approval_sha256"}
    if not isinstance(saved_hash, str) or approval_hash(unhashed) != saved_hash:
        raise RoleRunnerError("BLOCKED_GATE_A", "Gate A approval receipt has an invalid self-hash.")
    if approval.get("gate") != "A" or approval.get("decision") != "APPROVE":
        raise RoleRunnerError("BLOCKED_GATE_A", "Gate A approval receipt is not an APPROVE decision.")
    if approval.get("artifact_sha256") != verified["artifact_sha256"]:
        raise RoleRunnerError("BLOCKED_GATE_A", "Gate A approval refers to a different artifact.")
    if approval.get("source_m2f_run") != str(verified["run_dir"]):
        raise RoleRunnerError("BLOCKED_GATE_A", "Gate A approval refers to a different M2f run.")
    return {**verified, "approval": approval, "approval_sha256": saved_hash}


def _collect_summary_sessions(summary: dict) -> set[str]:
    return {
        value for key, value in summary.items()
        if "session_id" in key and isinstance(value, str) and value
    }


def collect_prior_sessions(verified: dict) -> set[str]:
    sessions = _collect_summary_sessions(verified["summary"])
    path_keys = [
        (verified["summary"], "source_m2e_run"),
    ]
    seen_paths: set[str] = set()
    while path_keys:
        parent_summary, key = path_keys.pop()
        value = parent_summary.get(key)
        if not isinstance(value, str) or not value or value in seen_paths:
            continue
        seen_paths.add(value)
        summary_path = Path(value).expanduser().resolve() / "summary.json"
        if not summary_path.is_file():
            continue
        child = load_json(summary_path)
        sessions.update(_collect_summary_sessions(child))
        for next_key in ("source_m2d_run", "source_m2b_run", "source_m2a_run"):
            if isinstance(child.get(next_key), str) and child.get(next_key):
                path_keys.append((child, next_key))
    return sessions


def target_packet(verified: dict, target_fragment_ids: list[str]) -> dict:
    target_set = set(target_fragment_ids)
    narration = [
        row for row in verified["artifact"].get("narration", [])
        if row.get("fragment_id") in target_set
    ]
    found = [row.get("fragment_id") for row in narration]
    if found != target_fragment_ids:
        raise RoleRunnerError("BLOCKED_INPUT", "Configured M3 target fragments are missing or out of order.")

    core_rows = [
        row for row in verified["core_evidence"].get("results", [])
        if target_set.intersection(row.get("fragment_ids", []))
    ]
    enrichment_rows = [
        row for row in verified["enrichment_evidence"].get("results", [])
        if target_set.intersection(row.get("fragment_ids", []))
    ]
    if not core_rows and not enrichment_rows:
        raise RoleRunnerError("BLOCKED_INPUT", "No execution evidence is linked to the M3 target fragment.")
    return {
        "narration": narration,
        "execution_evidence": [*core_rows, *enrichment_rows],
    }


def validate_variants(output: dict, *, target_fragment_ids: list[str], variant_count: int) -> None:
    if output.get("target_fragment_ids") != target_fragment_ids:
        raise RoleRunnerError("INVALID_OUTPUT", "Scene designer changed the target fragment list.")
    variants = output.get("variants", [])
    if not isinstance(variants, list) or len(variants) != variant_count:
        raise RoleRunnerError("INVALID_OUTPUT", "Scene designer returned the wrong number of variants.")
    variant_ids = [row.get("variant_id") for row in variants if isinstance(row, dict)]
    if len(variant_ids) != variant_count or len(set(variant_ids)) != variant_count or any(not value for value in variant_ids):
        raise RoleRunnerError("INVALID_OUTPUT", "Scene variant ids must be unique and non-empty.")

    allowed_fragments = set(target_fragment_ids)
    strategies: set[str] = set()
    for variant in variants:
        strategies.add(variant.get("visual_strategy"))
        elements = variant.get("visible_elements", [])
        element_ids = [row.get("element_id") for row in elements if isinstance(row, dict)]
        if len(element_ids) != len(elements) or len(set(element_ids)) != len(element_ids) or any(not value for value in element_ids):
            raise RoleRunnerError("INVALID_OUTPUT", f"Variant {variant.get('variant_id')} has invalid element ids.")
        known_elements = set(element_ids)
        beats = variant.get("beats", [])
        beat_ids = [row.get("beat_id") for row in beats if isinstance(row, dict)]
        if len(beat_ids) != len(beats) or len(set(beat_ids)) != len(beat_ids) or any(not value for value in beat_ids):
            raise RoleRunnerError("INVALID_OUTPUT", f"Variant {variant.get('variant_id')} has invalid beat ids.")
        for beat in beats:
            refs = beat.get("narration_fragment_ids", [])
            if not refs or any(ref not in allowed_fragments for ref in refs):
                raise RoleRunnerError("INVALID_OUTPUT", f"Variant {variant.get('variant_id')} beat references another narration fragment.")
            if beat.get("focus_target_id") not in known_elements:
                raise RoleRunnerError("INVALID_OUTPUT", f"Variant {variant.get('variant_id')} beat has an unknown focus target.")
            if any(ref not in known_elements for ref in beat.get("reveals", [])):
                raise RoleRunnerError("INVALID_OUTPUT", f"Variant {variant.get('variant_id')} beat reveals an unknown element.")
        requires_new = variant.get("requires_new_component") is True
        request = variant.get("new_component_request")
        if requires_new and (not isinstance(request, str) or not request.strip()):
            raise RoleRunnerError("INVALID_OUTPUT", f"Variant {variant.get('variant_id')} needs a component request.")
        if not requires_new and request != "":
            raise RoleRunnerError("INVALID_OUTPUT", f"Variant {variant.get('variant_id')} must leave new_component_request empty.")
    if len(strategies) < 2:
        raise RoleRunnerError("INVALID_OUTPUT", "Scene variants are not meaningfully distinct in visual strategy.")


@task(name="m3a-resolve-visual-knowhow", retries=0, cache_policy=NO_CACHE, persist_result=False)
def resolve_knowhow(config: dict) -> dict:
    try:
        return build_source_pack(config)
    except SourcePackError as exc:
        raise RoleRunnerError("BLOCKED_SOURCE", str(exc)) from exc


@task(name="m3a-scene-variant-designer", retries=0, cache_policy=NO_CACHE, persist_result=False)
def design_task(config: dict, verified: dict, packet: dict, knowhow: dict, run_dir: str) -> dict:
    runner = CodexRoleRunner(model=config["model"], reasoning_effort=config["reasoning_effort"])
    runner.preflight()
    payload = {
        "role_instructions": PROMPT.read_text(encoding="utf-8"),
        "artifact_sha256": verified["artifact_sha256"],
        "gate_a_approval_sha256": verified["approval_sha256"],
        "approved_target": packet,
        "target_fragment_ids": config["target_fragment_ids"],
        "variant_count": config["variant_count"],
        "visual_knowhow_source_pack": knowhow,
        "constraints": [
            "Gate A is immutable: do not change, shorten, paraphrase or extend narration.",
            "Use only code/results present in approved_target when showing factual execution output.",
            "Variants must differ in explanatory mechanics, not merely styling.",
            "No absolute seconds, pixel coordinates, audio or TTS decisions.",
            "Every beat must bind to the configured narration fragment and a semantic element_id.",
            "If a new visual component is required, request it explicitly but do not implement it.",
            "Return conceptual variants only; do not build the whole-lesson scene plan.",
        ],
    }
    return runner.run_json(
        role="scene_designer",
        payload=payload,
        schema=variant_schema(
            verified["artifact_sha256"], verified["approval_sha256"], config["variant_count"]
        ),
        report_dir=Path(run_dir) / "scene_designer",
    )


@flow(name="video-production-m3a-scene-variants", retries=0, persist_result=False)
def m3a_scene_variants(m2f_run_dir: str) -> dict:
    logger = get_run_logger()
    input_dir = Path(m2f_run_dir).expanduser().resolve()
    config = load_json(CONFIG)
    run_dir = ROOT / "runs" / "m3a-scene-variants" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "stage": "M3a",
        "lesson_id": config["lesson_id"],
        "status": "ERROR",
        "outcome": "ERROR",
        "source_m2f_run": str(input_dir),
        "reports": str(run_dir),
        "gate_a_required": True,
        "gate_b_reached": False,
        "gate_b_approved": False,
        "audio_called": False,
        "render_called": False,
        "production_ready": False,
    }
    try:
        verified = verify_gate_a_approval(input_dir)
        if verified["summary"].get("lesson_id") != config["lesson_id"]:
            raise RoleRunnerError("BLOCKED_INPUT", "M3 config and approved lesson id differ.")
        target_ids = config.get("target_fragment_ids")
        if not isinstance(target_ids, list) or not target_ids or any(not isinstance(x, str) or not x for x in target_ids):
            raise RoleRunnerError("BLOCKED_INPUT", "M3 target_fragment_ids must be a non-empty string list.")
        variant_count = config.get("variant_count")
        if not isinstance(variant_count, int) or variant_count < 2 or variant_count > 3:
            raise RoleRunnerError("BLOCKED_INPUT", "M3 variant_count must be 2 or 3.")

        packet = target_packet(verified, target_ids)
        knowhow = resolve_knowhow(config)
        (run_dir / "visual-knowhow-source-pack.json").write_text(
            json.dumps(knowhow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        result = design_task(config, verified, packet, knowhow, str(run_dir))
        output = result["output"]
        validate_variants(output, target_fragment_ids=target_ids, variant_count=variant_count)
        session_id = result["receipt"]["session_id"]
        if session_id in collect_prior_sessions(verified):
            raise RoleRunnerError("SESSION_REUSED", "Scene designer reused an earlier Codex session.")
        (run_dir / "scene-variants.json").write_text(
            json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        summary.update(
            status="COMPLETED",
            outcome="WAITING_HUMAN_VARIANT_SELECTION",
            artifact_sha256=verified["artifact_sha256"],
            gate_a_approval_sha256=verified["approval_sha256"],
            approved_by=verified["approval"].get("approved_by"),
            target_fragment_ids=target_ids,
            variant_count=variant_count,
            scene_designer_session_id=session_id,
            scene_variants_sha256=approval_hash(output),
            next_action="HUMAN_SELECT_SCENE_VARIANT",
        )
        logger.info(
            "M3a completed for %s. %d variants await human selection.",
            ", ".join(target_ids), variant_count,
        )
        logger.info("Artifacts: %s", run_dir)
        return summary
    except RoleRunnerError as exc:
        summary["status"] = exc.status
        summary["outcome"] = exc.status
        summary["error"] = str(exc)
        logger.error("%s: %s", exc.status, exc)
        raise
    finally:
        (run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m2f_run_dir", help="Approved M2f enriched run directory")
    args = parser.parse_args()
    print(json.dumps(m3a_scene_variants(args.m2f_run_dir), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
