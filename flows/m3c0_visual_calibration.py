"""M3c0: generate and optionally render visual-language calibration clips.

This stage intentionally precedes full visual acceptance. It does not modify the
Gate A narration. For the first few scenes it creates multiple visual variants,
a props JSON per variant, and a sidecar SRT per clip using the exact approved
narration and the same temporary scene timing shifted to clip-local time.

No LLM and no audio provider are called. With --render, Remotion renders finite
MP4 clips and the process exits after all clips are complete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flows.m2b_verify import load_json  # noqa: E402

CONFIG = ROOT / "config" / "m3c0_visual_calibration.json"


class M3c0Error(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise M3c0Error(message)


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _srt_timestamp(frame: int, fps: int) -> str:
    _require(frame >= 0 and fps > 0, "Invalid local frame/fps for SRT.")
    milliseconds = round(frame * 1000 / fps)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def _narration_map(props: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in props.get("narration", []):
        if not isinstance(row, dict):
            continue
        fragment_id = row.get("fragment_id")
        text = row.get("text")
        if isinstance(fragment_id, str) and fragment_id and isinstance(text, str) and text.strip():
            result[fragment_id] = text.strip()
    return result


def _scene_srt(
    *,
    props: dict[str, Any],
    scene_timing: dict[str, Any],
    scene_start: int,
) -> tuple[str, int]:
    fps = int(props["fps"])
    text_by_id = _narration_map(props)
    fragment_ids = scene_timing.get("fragment_ids", [])
    timing_by_id = {
        row.get("fragment_id"): row
        for row in props.get("timing", {}).get("fragments", [])
        if isinstance(row, dict) and row.get("scene_id") == scene_timing.get("scene_id")
    }
    entries: list[str] = []
    count = 0
    for fragment_id in fragment_ids:
        _require(fragment_id in text_by_id, f"Missing approved narration for {fragment_id}.")
        row = timing_by_id.get(fragment_id)
        _require(isinstance(row, dict), f"Missing timing for {fragment_id}.")
        start = int(row["start_frame"]) - scene_start
        end = int(row["end_frame"]) - scene_start
        _require(end > start >= 0, f"Invalid local timing for {fragment_id}.")
        count += 1
        entries.extend([
            str(count),
            f"{_srt_timestamp(start, fps)} --> {_srt_timestamp(end, fps)}",
            text_by_id[fragment_id],
            "",
        ])
    _require(count > 0, f"Scene {scene_timing.get('scene_id')} has no subtitle entries.")
    return "\n".join(entries), count


def _has_code(scene: dict[str, Any]) -> bool:
    return any(
        isinstance(element, dict) and element.get("kind") == "code"
        for element in scene.get("visible_elements", [])
    )


def _variant_rows(config: dict[str, Any], scene: dict[str, Any]) -> list[dict[str, Any]]:
    key = "repl_variants" if _has_code(scene) else "intro_variants"
    rows = config.get(key, [])
    _require(isinstance(rows, list) and rows, f"No variants configured in {key}.")
    return rows


def _screen_copy(config: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    scene_id = scene.get("scene_id")
    configured = config.get("screen_copy", {}).get(scene_id)
    if isinstance(configured, dict):
        copy = configured
    else:
        copy = {
            "eyebrow": scene.get("scene_type", "SCENE"),
            "title": scene.get("title", scene_id or "Scene"),
            "items": [],
            "footer": "silent visual calibration",
        }
    _require(isinstance(copy.get("title"), str) and copy["title"], f"Invalid screen copy for {scene_id}.")
    _require(isinstance(copy.get("items"), list), f"Invalid screen-copy items for {scene_id}.")
    return {
        "eyebrow": str(copy.get("eyebrow", "")),
        "title": copy["title"],
        "items": [str(item) for item in copy["items"]],
        "footer": str(copy.get("footer", "")),
    }


def create_calibration_bundle(m3c_run_dir: Path, scene_count: int | None = None) -> dict[str, Any]:
    input_dir = m3c_run_dir.expanduser().resolve()
    props_path = input_dir / "preview-props.json"
    summary_path = input_dir / "summary.json"
    _require(props_path.is_file() and summary_path.is_file(), "Input is not an M3c preview run.")

    props = load_json(props_path)
    summary = load_json(summary_path)
    config = load_json(CONFIG)
    _require(summary.get("stage") == "M3c" and summary.get("status") == "COMPLETED", "M3c run is not completed.")
    _require(props.get("audio_enabled") is False, "M3c0 only accepts silent preview props.")
    _require(props.get("lesson_id") == config.get("lesson_id"), "M3c0 config is for another lesson.")
    _require(props.get("timing", {}).get("timing_kind") == "TEMPORARY_ESTIMATE_FOR_SILENT_PREVIEW", "M3c0 requires temporary preview timing.")

    plan_scenes = props.get("scene_plan", {}).get("scenes", [])
    timing_scenes = props.get("timing", {}).get("scenes", [])
    _require(isinstance(plan_scenes, list) and isinstance(timing_scenes, list), "M3c props have no scene lists.")
    plan_by_id = {row.get("scene_id"): row for row in plan_scenes if isinstance(row, dict)}

    requested = scene_count if scene_count is not None else int(config.get("scene_count", 3))
    _require(requested > 0, "scene_count must be positive.")
    selected_timing = timing_scenes[:requested]
    _require(len(selected_timing) == requested, f"Requested {requested} scenes, only {len(selected_timing)} available.")

    run_dir = ROOT / "runs" / "m3c0-calibration" / uuid.uuid4().hex
    props_dir = run_dir / "props"
    clips_dir = run_dir / "clips"
    props_dir.mkdir(parents=True, exist_ok=False)
    clips_dir.mkdir(parents=True, exist_ok=False)

    manifest_rows: list[dict[str, Any]] = []
    for scene_index, scene_timing in enumerate(selected_timing, start=1):
        _require(isinstance(scene_timing, dict), "Invalid scene timing row.")
        scene_id = scene_timing.get("scene_id")
        scene = plan_by_id.get(scene_id)
        _require(isinstance(scene, dict), f"No scene plan for {scene_id}.")
        scene_start = int(scene_timing["start_frame"])
        scene_end = int(scene_timing["end_frame"])
        duration = scene_end - scene_start
        _require(duration > 0, f"Scene {scene_id} has invalid duration.")
        local_content_start = int(scene_timing["content_start_frame"]) - scene_start
        local_content_end = int(scene_timing["content_end_frame"]) - scene_start
        copy = _screen_copy(config, scene)
        fragment_ids = list(scene_timing.get("fragment_ids", []))
        narration = _narration_map(props)
        narration_text = "\n".join(narration[fragment_id] for fragment_id in fragment_ids)
        srt_text, subtitle_count = _scene_srt(props=props, scene_timing=scene_timing, scene_start=scene_start)

        for variant in _variant_rows(config, scene):
            _require(isinstance(variant, dict) and isinstance(variant.get("variant_id"), str), f"Invalid variant for {scene_id}.")
            variant_id = variant["variant_id"]
            stem = f"{scene_id}-{variant_id}"
            variant_props = {
                "schema_version": 1,
                "lesson_id": props["lesson_id"],
                "scene_id": scene_id,
                "scene_index": scene_index,
                "variant_id": variant_id,
                "theme": variant["theme"],
                "layout": variant["layout"],
                "motion": variant["motion"],
                "fps": int(props["fps"]),
                "width": int(props["width"]),
                "height": int(props["height"]),
                "duration_frames": duration,
                "content_start_frame": local_content_start,
                "content_end_frame": local_content_end,
                "narration_fragment_ids": fragment_ids,
                "narration_text": narration_text,
                "screen_copy": copy,
                "original_scene": scene,
            }
            variant_props_path = props_dir / f"{stem}.json"
            _write_json(variant_props_path, variant_props)
            srt_path = clips_dir / f"{stem}.srt"
            srt_path.write_bytes(srt_text.encode("utf-8"))
            mp4_path = clips_dir / f"{stem}.mp4"
            manifest_rows.append({
                "scene_id": scene_id,
                "scene_index": scene_index,
                "variant_id": variant_id,
                "theme": variant["theme"],
                "layout": variant["layout"],
                "motion": variant["motion"],
                "duration_frames": duration,
                "estimated_duration_seconds": round(duration / int(props["fps"]), 3),
                "props_file": str(variant_props_path),
                "props_sha256": _sha256(variant_props_path),
                "srt_file": str(srt_path),
                "srt_sha256": _sha256(srt_path),
                "subtitle_count": subtitle_count,
                "mp4_file": str(mp4_path),
                "render_status": "NOT_RENDERED",
            })

    manifest = {
        "stage": "M3c0",
        "status": "COMPLETED",
        "outcome": "READY_FOR_CALIBRATION_RENDER",
        "source_m3c_run": str(input_dir),
        "lesson_id": props["lesson_id"],
        "artifact_sha256": props.get("artifact_sha256"),
        "gate_a_approval_sha256": props.get("gate_a_approval_sha256"),
        "scene_count": requested,
        "variant_count": len(manifest_rows),
        "screen_copy_is_separate_from_narration": True,
        "narration_mutated": False,
        "subtitle_timing": "TEMPORARY_ESTIMATE_FOR_SILENT_PREVIEW",
        "llm_called": False,
        "audio_called": False,
        "render_called": False,
        "clips": manifest_rows,
    }
    manifest_path = run_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    return {"run_dir": run_dir, "manifest_path": manifest_path, "manifest": manifest}


def _npx_command() -> str:
    command = shutil.which("npx.cmd") if sys.platform.startswith("win") else None
    command = command or shutil.which("npx")
    if not command:
        raise M3c0Error("npx was not found on PATH.")
    return command


def render_calibration_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    manifest_path: Path = bundle["manifest_path"]
    manifest = load_json(manifest_path)
    remotion_dir = ROOT / "remotion"
    _require(remotion_dir.is_dir(), "Remotion project directory is missing.")
    npx = _npx_command()
    config = load_json(CONFIG)
    codec = str(config.get("render", {}).get("codec", "h264"))
    crf = int(config.get("render", {}).get("crf", 18))

    completed = 0
    for row in manifest["clips"]:
        props_path = Path(row["props_file"]).resolve()
        output_path = Path(row["mp4_file"]).resolve()
        command = [
            npx,
            "remotion",
            "render",
            "src/index.ts",
            "VisualCalibration",
            str(output_path),
            f"--props={props_path}",
            f"--codec={codec}",
            f"--crf={crf}",
        ]
        print(f"\n[M3c0] Rendering {row['scene_id']} / {row['variant_id']}")
        subprocess.run(command, cwd=remotion_dir, check=True)
        _require(output_path.is_file(), f"Remotion returned successfully but {output_path} is missing.")
        row["render_status"] = "RENDERED"
        row["mp4_sha256"] = _sha256(output_path)
        completed += 1
        _write_json(manifest_path, manifest)

    manifest["outcome"] = "READY_FOR_HUMAN_VISUAL_CALIBRATION"
    manifest["render_called"] = True
    manifest["rendered_clip_count"] = completed
    _write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m3c_run_dir", help="Completed M3c run directory containing preview-props.json")
    parser.add_argument("--scene-count", type=int, default=None, help="Number of leading scenes to calibrate (default from config: 3)")
    parser.add_argument("--render", action="store_true", help="Render all calibration MP4 clips and exit when complete")
    args = parser.parse_args()
    try:
        bundle = create_calibration_bundle(Path(args.m3c_run_dir), scene_count=args.scene_count)
        result = render_calibration_bundle(bundle) if args.render else bundle["manifest"]
    except Exception as exc:
        print(json.dumps({"stage": "M3c0", "status": "ERROR", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
