"""Generate a deterministic sidecar SRT for an existing M3c silent preview.

The subtitle text is the approved Gate A narration already embedded in
preview-props.json. Timing comes from the same temporary preview timing used by
Remotion. No LLM, audio service or renderer is called.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class PreviewSrtError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PreviewSrtError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PreviewSrtError(f"Expected JSON object in {path}.")
    return value


def _srt_timestamp(frame: int, fps: int) -> str:
    if fps <= 0 or frame < 0:
        raise PreviewSrtError("Invalid frame/fps for SRT timestamp.")
    milliseconds = round(frame * 1000 / fps)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def build_srt(props: dict[str, Any]) -> str:
    timing = props.get("timing")
    narration = props.get("narration")
    fps = props.get("fps")
    if not isinstance(timing, dict) or not isinstance(narration, list) or not isinstance(fps, int):
        raise PreviewSrtError("preview-props.json lacks timing, narration or integer fps.")
    if timing.get("timing_kind") != "TEMPORARY_ESTIMATE_FOR_SILENT_PREVIEW":
        raise PreviewSrtError("SRT source timing is not marked as temporary silent-preview timing.")

    text_by_id: dict[str, str] = {}
    for row in narration:
        if not isinstance(row, dict):
            continue
        fragment_id = row.get("fragment_id")
        text = row.get("text")
        if isinstance(fragment_id, str) and fragment_id and isinstance(text, str) and text.strip():
            text_by_id[fragment_id] = text.strip()

    entries: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(timing.get("fragments", []), start=1):
        if not isinstance(row, dict):
            raise PreviewSrtError("Invalid fragment timing row.")
        fragment_id = row.get("fragment_id")
        start = row.get("start_frame")
        end = row.get("end_frame")
        if not isinstance(fragment_id, str) or fragment_id not in text_by_id:
            raise PreviewSrtError(f"No approved narration for timed fragment {fragment_id!r}.")
        if fragment_id in seen:
            raise PreviewSrtError(f"Timed fragment {fragment_id!r} appears more than once.")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            raise PreviewSrtError(f"Invalid frame interval for fragment {fragment_id!r}.")
        seen.add(fragment_id)
        entries.extend([
            str(index),
            f"{_srt_timestamp(start, fps)} --> {_srt_timestamp(end, fps)}",
            text_by_id[fragment_id],
            "",
        ])

    if seen != set(text_by_id):
        missing = sorted(set(text_by_id) - seen)
        raise PreviewSrtError("Narration fragments missing from preview timing: " + ", ".join(missing))
    return "\n".join(entries)


def generate_srt(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    props_path = run_dir / "preview-props.json"
    summary_path = run_dir / "summary.json"
    if not props_path.is_file() or not summary_path.is_file():
        raise PreviewSrtError("Input directory is not a completed M3c run.")
    props = _load_json(props_path)
    summary = _load_json(summary_path)
    if summary.get("stage") != "M3c" or summary.get("status") != "COMPLETED":
        raise PreviewSrtError("M3c run is not completed.")
    if props.get("audio_enabled") is not False:
        raise PreviewSrtError("Cannot generate silent-preview SRT from audio-enabled props.")

    srt = build_srt(props)
    data = srt.encode("utf-8")
    output = run_dir / "silent-preview.srt"
    output.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    return {
        "preview_srt": "GENERATED",
        "srt_file": str(output),
        "srt_sha256": digest,
        "subtitle_count": len(props["timing"].get("fragments", [])),
        "timing_kind": props["timing"].get("timing_kind"),
        "audio_called": False,
        "render_called": False,
        "llm_called": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m3c_run_dir", help="Completed M3c run directory")
    args = parser.parse_args()
    try:
        result = generate_srt(Path(args.m3c_run_dir))
    except Exception as exc:
        print(json.dumps({"preview_srt": "ERROR", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
