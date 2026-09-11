"""Canonical M3c entrypoint: compile preview inputs and always generate sidecar SRT.

This wrapper preserves the existing deterministic M3c compiler and adds the
subtitle artifact required for human preview. It does not call an LLM, audio
provider, Remotion Studio or renderer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flows.m3c_preview import m3c_preview
from scripts.generate_preview_srt import generate_srt


def m3c_preview_bundle(m3b_run_dir: str) -> dict:
    result = m3c_preview(m3b_run_dir)
    if result.get("status") != "COMPLETED":
        return result

    run_dir = Path(result["reports"])
    srt = generate_srt(run_dir)

    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        outcome="READY_FOR_SILENT_PREVIEW_RENDER",
        preview_srt=srt["srt_file"],
        preview_srt_sha256=srt["srt_sha256"],
        subtitle_count=srt["subtitle_count"],
        next_action="RENDER_SILENT_PREVIEW",
    )
    summary_path.write_bytes((json.dumps(summary, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m3b_run_dir", help="Accepted M3b run directory")
    args = parser.parse_args()
    result = m3c_preview_bundle(args.m3b_run_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
