"""Record explicit human acceptance of one M3b plan for silent preview build.

This is not Gate B. It only authorizes M3c to build a silent preview from the
exact reviewed scene-plan hash. Existing M3b artifacts are not mutated except
for this append-only receipt. Repeating the same acceptance is idempotent;
conflicting acceptance data are rejected.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flows.m2b_verify import load_json  # noqa: E402
from scripts.m3b_review import M3bReviewError, verify_m3b  # noqa: E402
from scripts.record_gate_a_approval import canonical_hash  # noqa: E402


class M3bPreviewAcceptanceError(RuntimeError):
    pass


def _verify_existing(existing: dict, expected: dict) -> dict:
    saved = existing.get("acceptance_sha256")
    unhashed = {key: value for key, value in existing.items() if key != "acceptance_sha256"}
    if not isinstance(saved, str) or canonical_hash(unhashed) != saved:
        raise M3bPreviewAcceptanceError("Existing M3b preview acceptance has an invalid self-hash.")
    stable_keys = (
        "schema_version",
        "decision",
        "artifact_sha256",
        "gate_a_approval_sha256",
        "m3a_selection_sha256",
        "visual_fact_catalog_sha256",
        "scene_plan_sha256",
        "source_m3b_run",
        "accepted_by",
    )
    if any(existing.get(key) != expected.get(key) for key in stable_keys):
        raise M3bPreviewAcceptanceError("A conflicting M3b preview acceptance already exists.")
    return existing


def record_acceptance(
    run_dir: Path,
    *,
    accepted_by: str,
    now_utc: datetime | None = None,
) -> dict:
    if not accepted_by.strip():
        raise M3bPreviewAcceptanceError("accepted_by must be non-empty.")
    try:
        verified = verify_m3b(run_dir)
    except M3bReviewError as exc:
        raise M3bPreviewAcceptanceError(str(exc)) from exc

    summary = verified["summary"]
    payload = {
        "schema_version": 1,
        "decision": "ACCEPT_FOR_SILENT_PREVIEW_BUILD",
        "artifact_sha256": summary["artifact_sha256"],
        "gate_a_approval_sha256": summary["gate_a_approval_sha256"],
        "m3a_selection_sha256": summary["m3a_selection_sha256"],
        "visual_fact_catalog_sha256": summary["visual_fact_catalog_sha256"],
        "scene_plan_sha256": summary["scene_plan_sha256"],
        "source_m3b_run": str(verified["run_dir"]),
        "accepted_by": accepted_by.strip(),
        "accepted_at_utc": (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "gate_b": False,
        "llm_called": False,
        "render_called": False,
        "audio_called": False,
    }
    output = verified["run_dir"] / "m3b-preview-acceptance.json"
    if output.is_file():
        return _verify_existing(load_json(output), payload)
    payload["acceptance_sha256"] = canonical_hash(payload)
    output.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m3b_run_dir", help="Completed and reviewed M3b v2 run")
    parser.add_argument("--accepted-by", required=True, help="Human accepting the plan for silent preview build")
    args = parser.parse_args()
    try:
        receipt = record_acceptance(Path(args.m3b_run_dir), accepted_by=args.accepted_by)
    except M3bPreviewAcceptanceError as exc:
        print(json.dumps({"m3b_preview_acceptance": "ERROR", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps({
        "m3b_preview_acceptance": "ACCEPTED",
        "decision": receipt["decision"],
        "scene_plan_sha256": receipt["scene_plan_sha256"],
        "accepted_by": receipt["accepted_by"],
        "accepted_at_utc": receipt["accepted_at_utc"],
        "acceptance_sha256": receipt["acceptance_sha256"],
        "acceptance_file": str(Path(args.m3b_run_dir).expanduser().resolve() / "m3b-preview-acceptance.json"),
        "gate_b": False,
        "audio_called": False,
        "render_called": False,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
