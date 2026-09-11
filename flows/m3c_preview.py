"""M3c: accepted M3b scene plan -> deterministic silent-preview inputs.

This stage does not call an LLM, audio provider or renderer. It verifies the
explicit M3b preview-build acceptance, binds the exact approved Gate A narration,
and compiles temporary timing plus Remotion input props. Timing is deliberately
estimated and must later be replaced by real audio alignment.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
import uuid
from typing import Any

from prefect import flow, get_run_logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flows.m2b_verify import load_json  # noqa: E402
from flows.m3b_scene_plan import verify_m3a_selection  # noqa: E402
from scripts.m3b_review import M3bReviewError, verify_m3b  # noqa: E402
from scripts.record_gate_a_approval import canonical_hash  # noqa: E402

CONFIG = ROOT / "config" / "m3c_preview.json"
ACCEPTANCE_FILE = "m3b-preview-acceptance.json"


class M3cPreviewError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise M3cPreviewError(message)


def verify_m3b_preview_acceptance(m3b_run_dir: Path) -> dict[str, Any]:
    try:
        verified = verify_m3b(m3b_run_dir)
    except M3bReviewError as exc:
        raise M3cPreviewError(str(exc)) from exc

    receipt_path = verified["run_dir"] / ACCEPTANCE_FILE
    _require(receipt_path.is_file(), "M3b plan has no human acceptance for silent preview build.")
    receipt = load_json(receipt_path)
    saved_hash = receipt.get("acceptance_sha256")
    unhashed = {key: value for key, value in receipt.items() if key != "acceptance_sha256"}
    _require(
        isinstance(saved_hash, str) and canonical_hash(unhashed) == saved_hash,
        "M3b preview acceptance has an invalid self-hash.",
    )
    _require(receipt.get("decision") == "ACCEPT_FOR_SILENT_PREVIEW_BUILD", "M3b receipt is not a preview-build acceptance.")
    _require(receipt.get("gate_b") is False, "M3b preview-build acceptance must not claim Gate B.")
    _require(receipt.get("audio_called") is False, "M3b preview-build acceptance unexpectedly records audio.")
    _require(receipt.get("render_called") is False, "M3b preview-build acceptance unexpectedly records rendering.")

    summary = verified["summary"]
    for key in (
        "artifact_sha256",
        "gate_a_approval_sha256",
        "m3a_selection_sha256",
        "visual_fact_catalog_sha256",
        "scene_plan_sha256",
    ):
        _require(receipt.get(key) == summary.get(key), f"M3b preview acceptance {key} mismatch.")
    _require(receipt.get("source_m3b_run") == str(verified["run_dir"]), "M3b preview acceptance points to another run.")
    return {**verified, "acceptance": receipt, "acceptance_sha256": saved_hash}


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+(?:[-’']\w+)*", text, flags=re.UNICODE))


def _fragment_duration_frames(text: str, config: dict[str, Any]) -> int:
    fps = int(config["fps"])
    words_per_minute = float(config["words_per_minute"])
    minimum_seconds = float(config["minimum_fragment_seconds"])
    spoken_seconds = (_word_count(text) / words_per_minute) * 60.0 if text else 0.0
    return max(1, math.ceil(max(minimum_seconds, spoken_seconds) * fps))


def _fragment_map(artifact: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in artifact.get("narration", []):
        if isinstance(row, dict) and isinstance(row.get("fragment_id"), str) and isinstance(row.get("text"), str):
            result[row["fragment_id"]] = row["text"]
    return result


def _beat_starts(
    beats: list[dict[str, Any]],
    fragment_id: str,
    text: str,
    start_frame: int,
    end_frame: int,
    minimum_spacing: int,
) -> list[tuple[dict[str, Any], int]]:
    rows = [beat for beat in beats if beat.get("narration_fragment_id") == fragment_id]
    if not rows:
        raise M3cPreviewError(f"Fragment {fragment_id} has no beats.")
    duration = end_frame - start_frame
    if duration <= 0:
        raise M3cPreviewError(f"Fragment {fragment_id} has invalid timing duration.")
    if duration < 1 + minimum_spacing * (len(rows) - 1):
        raise M3cPreviewError(f"Fragment {fragment_id} is too short for deterministic beat spacing.")

    result: list[tuple[dict[str, Any], int]] = []
    previous = start_frame - minimum_spacing
    text_denominator = max(1, len(text) - 1)
    for index, beat in enumerate(rows):
        anchor = beat.get("anchor_text")
        if not isinstance(anchor, str) or not anchor:
            raise M3cPreviewError(f"Beat {beat.get('beat_id')} has no anchor text.")
        anchor_index = text.find(anchor)
        if anchor_index < 0:
            raise M3cPreviewError(f"Beat {beat.get('beat_id')} anchor is absent from approved narration.")
        ratio = anchor_index / text_denominator
        candidate = start_frame + int(round(ratio * max(0, duration - 1)))
        earliest = previous + minimum_spacing
        remaining = len(rows) - index - 1
        latest = end_frame - 1 - remaining * minimum_spacing
        chosen = min(max(candidate, earliest), latest)
        result.append((beat, chosen))
        previous = chosen
    return result


def compile_preview_timing(
    *,
    artifact: dict[str, Any],
    scene_plan: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    fps = int(config["fps"])
    lead = max(0, round(float(config["scene_lead_in_seconds"]) * fps))
    tail = max(0, round(float(config["scene_tail_seconds"]) * fps))
    minimum_spacing = max(1, int(config["minimum_beat_spacing_frames"]))
    fragments = _fragment_map(artifact)
    cursor = 0
    scene_rows: list[dict[str, Any]] = []
    fragment_rows: list[dict[str, Any]] = []
    beat_rows: list[dict[str, Any]] = []

    for scene in scene_plan.get("scenes", []):
        scene_id = scene.get("scene_id")
        if not isinstance(scene_id, str) or not scene_id:
            raise M3cPreviewError("Scene plan contains an invalid scene id.")
        scene_start = cursor
        content_cursor = scene_start + lead
        local_fragments: list[dict[str, Any]] = []
        local_beats: list[dict[str, Any]] = []

        for fragment_id in scene.get("narration_fragment_ids", []):
            text = fragments.get(fragment_id)
            if text is None:
                raise M3cPreviewError(f"Scene {scene_id} references unknown narration fragment {fragment_id}.")
            duration = _fragment_duration_frames(text, config)
            fragment_start = content_cursor
            fragment_end = fragment_start + duration
            fragment_row = {
                "fragment_id": fragment_id,
                "scene_id": scene_id,
                "start_frame": fragment_start,
                "end_frame": fragment_end,
                "duration_frames": duration,
                "timing_source": "estimated_words_per_minute",
            }
            local_fragments.append(fragment_row)
            fragment_rows.append(fragment_row)

            positioned = _beat_starts(
                scene.get("beats", []),
                fragment_id,
                text,
                fragment_start,
                fragment_end,
                minimum_spacing,
            )
            for beat_index, (beat, beat_start) in enumerate(positioned):
                next_start = positioned[beat_index + 1][1] if beat_index + 1 < len(positioned) else fragment_end
                beat_row = {
                    "beat_id": beat["beat_id"],
                    "scene_id": scene_id,
                    "fragment_id": fragment_id,
                    "start_frame": beat_start,
                    "end_frame": next_start,
                    "focus_target_id": beat["focus_target_id"],
                    "reveals": list(beat.get("reveals", [])),
                }
                local_beats.append(beat_row)
                beat_rows.append(beat_row)
            content_cursor = fragment_end

        scene_end = content_cursor + tail
        scene_rows.append({
            "scene_id": scene_id,
            "start_frame": scene_start,
            "content_start_frame": scene_start + lead,
            "content_end_frame": content_cursor,
            "end_frame": scene_end,
            "duration_frames": scene_end - scene_start,
            "fragment_ids": [row["fragment_id"] for row in local_fragments],
            "beat_ids": [row["beat_id"] for row in local_beats],
        })
        cursor = scene_end

    _require(bool(scene_rows), "Scene plan contains no scenes.")
    timing = {
        "schema_version": 1,
        "timing_kind": "TEMPORARY_ESTIMATE_FOR_SILENT_PREVIEW",
        "replace_with_audio_alignment": True,
        "fps": fps,
        "words_per_minute": float(config["words_per_minute"]),
        "total_frames": cursor,
        "scenes": scene_rows,
        "fragments": fragment_rows,
        "beats": beat_rows,
    }
    timing["preview_timing_sha256"] = canonical_hash(timing)
    return timing


def validate_preview_payload(payload: dict[str, Any]) -> None:
    _require(payload.get("audio_enabled") is False, "Silent preview payload cannot enable audio.")
    _require(payload.get("render_requested") is False, "M3c compiler cannot request a render.")
    timing = payload.get("timing", {})
    _require(timing.get("timing_kind") == "TEMPORARY_ESTIMATE_FOR_SILENT_PREVIEW", "Preview timing is not marked temporary.")
    _require(timing.get("replace_with_audio_alignment") is True, "Preview timing must declare later audio replacement.")
    scene_plan = payload.get("scene_plan", {})
    element_ids = {
        element.get("element_id")
        for scene in scene_plan.get("scenes", [])
        for element in scene.get("visible_elements", [])
        if isinstance(element, dict)
    }
    for beat in timing.get("beats", []):
        _require(beat.get("focus_target_id") in element_ids, f"Unknown focus target {beat.get('focus_target_id')} in preview timing.")
        _require(all(ref in element_ids for ref in beat.get("reveals", [])), f"Unknown reveal target in beat {beat.get('beat_id')}.")
    _require(timing.get("total_frames", 0) > 0, "Preview duration is empty.")


@flow(name="video-production-m3c-silent-preview-compile", retries=0, persist_result=False)
def m3c_preview(m3b_run_dir: str) -> dict[str, Any]:
    logger = get_run_logger()
    input_dir = Path(m3b_run_dir).expanduser().resolve()
    run_dir = ROOT / "runs" / "m3c-preview" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    summary: dict[str, Any] = {
        "stage": "M3c",
        "status": "ERROR",
        "outcome": "ERROR",
        "source_m3b_run": str(input_dir),
        "reports": str(run_dir),
        "gate_b_reached": False,
        "gate_b_approved": False,
        "llm_called": False,
        "audio_called": False,
        "render_called": False,
        "remotion_studio_called": False,
        "production_ready": False,
    }
    try:
        config = load_json(CONFIG)
        _require(config.get("audio_enabled") is False, "M3c config must keep audio disabled.")
        _require(config.get("render_enabled") is False, "M3c compiler must not render automatically.")
        verified = verify_m3b_preview_acceptance(input_dir)
        m3b_summary = verified["summary"]
        _require(m3b_summary.get("lesson_id") == config.get("lesson_id"), "M3b and M3c lesson ids differ.")

        source_m3a = m3b_summary.get("source_m3a_run")
        _require(isinstance(source_m3a, str) and source_m3a, "M3b does not identify its M3a source run.")
        selected = verify_m3a_selection(Path(source_m3a))
        approved = selected["approved"]
        _require(approved["artifact_sha256"] == m3b_summary["artifact_sha256"], "M3c resolved a different Gate A artifact.")
        _require(approved["approval_sha256"] == m3b_summary["gate_a_approval_sha256"], "M3c resolved a different Gate A approval.")

        timing = compile_preview_timing(
            artifact=approved["artifact"],
            scene_plan=verified["plan"],
            config=config,
        )
        timing_path = run_dir / "preview-timing.json"
        timing_path.write_bytes((json.dumps(timing, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

        payload = {
            "schema_version": 1,
            "lesson_id": config["lesson_id"],
            "lesson_title": verified["plan"]["lesson_title"],
            "artifact_sha256": m3b_summary["artifact_sha256"],
            "gate_a_approval_sha256": m3b_summary["gate_a_approval_sha256"],
            "m3a_selection_sha256": m3b_summary["m3a_selection_sha256"],
            "visual_fact_catalog_sha256": m3b_summary["visual_fact_catalog_sha256"],
            "scene_plan_sha256": m3b_summary["scene_plan_sha256"],
            "m3b_preview_acceptance_sha256": verified["acceptance_sha256"],
            "fps": int(config["fps"]),
            "width": int(config["width"]),
            "height": int(config["height"]),
            "review_strip_height": int(config["review_strip_height"]),
            "audio_enabled": False,
            "render_requested": False,
            "narration": approved["artifact"]["narration"],
            "scene_plan": verified["plan"],
            "timing": timing,
        }
        validate_preview_payload(payload)
        props_sha = canonical_hash(payload)
        payload["preview_props_sha256"] = props_sha
        props_path = run_dir / "preview-props.json"
        props_path.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

        relative_props = Path("..") / "runs" / "m3c-preview" / run_dir.name / "preview-props.json"
        summary.update(
            status="COMPLETED",
            outcome="READY_FOR_REMOTION_STUDIO",
            artifact_sha256=m3b_summary["artifact_sha256"],
            gate_a_approval_sha256=m3b_summary["gate_a_approval_sha256"],
            m3a_selection_sha256=m3b_summary["m3a_selection_sha256"],
            scene_plan_sha256=m3b_summary["scene_plan_sha256"],
            m3b_preview_acceptance_sha256=verified["acceptance_sha256"],
            preview_timing_sha256=timing["preview_timing_sha256"],
            preview_props_sha256=props_sha,
            total_frames=timing["total_frames"],
            fps=timing["fps"],
            estimated_duration_seconds=round(timing["total_frames"] / timing["fps"], 3),
            timing_temporary=True,
            remotion_project=str(ROOT / "remotion"),
            preview_props=str(props_path),
            studio_props_argument=relative_props.as_posix(),
            next_action="OPEN_REMOTION_STUDIO",
        )
        logger.info("M3c inputs compiled for %d scenes; audio and rendering remain disabled.", len(timing["scenes"]))
        return summary
    except Exception as exc:
        summary["status"] = "ERROR"
        summary["outcome"] = "ERROR"
        summary["error"] = str(exc)
        logger.error("M3c compile failed: %s", exc)
        return summary
    finally:
        (run_dir / "summary.json").write_bytes((json.dumps(summary, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m3b_run_dir", help="Accepted M3b run directory")
    args = parser.parse_args()
    result = m3c_preview(args.m3b_run_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
