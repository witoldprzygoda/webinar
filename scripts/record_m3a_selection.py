"""Record an explicit human selection of one M3a scene-design variant.

The selection is append-only. It binds the approved Gate A artifact, the exact
M3a variant set and the exact selected variant payload. Existing M3a outputs are
not mutated. Re-running the same choice is idempotent; conflicting choices are
rejected.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flows.m2b_verify import load_json  # noqa: E402
from scripts.m3a_review import M3aReviewError, verify_m3a  # noqa: E402
from scripts.record_gate_a_approval import canonical_hash  # noqa: E402


class M3aSelectionError(RuntimeError):
    pass


def _selected_variant(variants: dict, variant_id: str) -> dict:
    rows = variants.get("variants")
    if not isinstance(rows, list):
        raise M3aSelectionError("M3a variants payload is invalid.")
    matches = [row for row in rows if isinstance(row, dict) and row.get("variant_id") == variant_id]
    if len(matches) != 1:
        raise M3aSelectionError(f"Variant {variant_id!r} does not identify exactly one M3a variant.")
    return matches[0]


def _verify_existing(existing: dict, expected: dict) -> dict:
    saved = existing.get("selection_sha256")
    unhashed = {key: value for key, value in existing.items() if key != "selection_sha256"}
    if not isinstance(saved, str) or canonical_hash(unhashed) != saved:
        raise M3aSelectionError("Existing M3a selection receipt has an invalid self-hash.")
    stable_keys = (
        "schema_version", "decision", "artifact_sha256", "gate_a_approval_sha256",
        "source_m3a_run", "scene_variants_sha256", "selected_variant_id",
        "selected_variant_sha256", "selected_by",
    )
    if any(existing.get(key) != expected.get(key) for key in stable_keys):
        raise M3aSelectionError("A conflicting M3a variant selection already exists.")
    return existing


def record_selection(
    run_dir: Path,
    *,
    variant_id: str,
    selected_by: str,
    now_utc: datetime | None = None,
) -> dict:
    if not variant_id.strip():
        raise M3aSelectionError("variant_id must be non-empty.")
    if not selected_by.strip():
        raise M3aSelectionError("selected_by must be non-empty.")
    try:
        verified = verify_m3a(run_dir)
    except M3aReviewError as exc:
        raise M3aSelectionError(str(exc)) from exc

    summary = verified["summary"]
    variants = verified["variants"]
    selected = _selected_variant(variants, variant_id.strip())
    payload = {
        "schema_version": 1,
        "decision": "SELECT",
        "artifact_sha256": summary["artifact_sha256"],
        "gate_a_approval_sha256": summary["gate_a_approval_sha256"],
        "source_m3a_run": str(verified["run_dir"]),
        "scene_variants_sha256": summary["scene_variants_sha256"],
        "selected_variant_id": variant_id.strip(),
        "selected_variant_sha256": canonical_hash(selected),
        "selected_by": selected_by.strip(),
        "selected_at_utc": (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "llm_called": False,
        "render_called": False,
        "audio_called": False,
    }
    output = verified["run_dir"] / "m3a-selection.json"
    if output.is_file():
        return _verify_existing(load_json(output), payload)
    payload["selection_sha256"] = canonical_hash(payload)
    output.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m3a_run_dir", help="Completed M3a scene-variant run")
    parser.add_argument("--variant-id", required=True, help="Exact selected variant_id")
    parser.add_argument("--selected-by", required=True, help="Human selector name")
    args = parser.parse_args()
    try:
        receipt = record_selection(
            Path(args.m3a_run_dir), variant_id=args.variant_id, selected_by=args.selected_by
        )
    except M3aSelectionError as exc:
        print(json.dumps({"m3a_selection": "ERROR", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps({
        "m3a_selection": "SELECTED",
        "artifact_sha256": receipt["artifact_sha256"],
        "selected_variant_id": receipt["selected_variant_id"],
        "selected_by": receipt["selected_by"],
        "selected_at_utc": receipt["selected_at_utc"],
        "selection_sha256": receipt["selection_sha256"],
        "selection_file": str(Path(args.m3a_run_dir).expanduser().resolve() / "m3a-selection.json"),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
