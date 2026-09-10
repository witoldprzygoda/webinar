"""Record an explicit human Gate A approval for one verified M2f artifact.

The approval is an append-only receipt next to the M2f run. Existing M2f
summaries and judge reports are not mutated. Re-running with the same approval
is idempotent; conflicting approval metadata is rejected.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from gate_a_review_enriched import (
    GateAEnrichedReviewError,
    load_json,
    verify_enriched_chain,
)


class GateAApprovalError(RuntimeError):
    pass


def canonical_hash(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _review_hash_matches(review_path: Path, expected_sha256: str) -> bool:
    """Accept exact bytes or the legacy LF-canonical text hash.

    Older Gate A review receipts hashed the in-memory Markdown string before
    Path.write_text() wrote it. On Windows that write translated LF to CRLF,
    so the receipt and the file differed byte-for-byte even though the reviewed
    text was identical. Keep exact-byte verification first, then allow only the
    newline-normalized legacy representation as a compatibility path.
    """
    raw = review_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() == expected_sha256:
        return True
    try:
        canonical_text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError:
        return False
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest() == expected_sha256


def _load_review_receipt(run_dir: Path, artifact_sha256: str) -> dict:
    path = run_dir / "gate-a-review-receipt.json"
    try:
        receipt = load_json(path)
    except GateAEnrichedReviewError as exc:
        raise GateAApprovalError(
            "Gate A review receipt is missing or invalid; generate the human review first."
        ) from exc
    if receipt.get("approval_recorded") is not False:
        raise GateAApprovalError("Gate A review receipt is not in a pre-approval state.")
    if receipt.get("artifact_sha256") != artifact_sha256:
        raise GateAApprovalError("Gate A review receipt refers to a different artifact.")
    review_file = receipt.get("review_file")
    review_sha = receipt.get("review_sha256")
    if not isinstance(review_file, str) or not isinstance(review_sha, str):
        raise GateAApprovalError("Gate A review receipt lacks review provenance.")
    review_path = Path(review_file).expanduser().resolve()
    if not review_path.is_file():
        raise GateAApprovalError("Reviewed Gate A Markdown file no longer exists.")
    if not _review_hash_matches(review_path, review_sha):
        raise GateAApprovalError("Reviewed Gate A Markdown changed after review receipt creation.")
    return receipt


def _verify_existing(existing: dict, expected: dict) -> dict:
    saved_hash = existing.get("approval_sha256")
    unhashed = {key: value for key, value in existing.items() if key != "approval_sha256"}
    if not isinstance(saved_hash, str) or canonical_hash(unhashed) != saved_hash:
        raise GateAApprovalError("Existing Gate A approval receipt has an invalid self-hash.")
    stable_keys = (
        "schema_version", "gate", "decision", "artifact_sha256",
        "base_artifact_sha256", "approved_by", "review_sha256",
        "source_m2f_run", "rubric_version", "portfolio_rubric_version",
    )
    if any(existing.get(key) != expected.get(key) for key in stable_keys):
        raise GateAApprovalError("A conflicting Gate A approval receipt already exists.")
    return existing


def record_approval(
    run_dir: Path,
    *,
    artifact_sha256: str,
    approved_by: str,
    now_utc: datetime | None = None,
) -> dict:
    if not approved_by.strip():
        raise GateAApprovalError("approved_by must be non-empty.")
    try:
        verified = verify_enriched_chain(run_dir)
    except GateAEnrichedReviewError as exc:
        raise GateAApprovalError(str(exc)) from exc
    if verified["artifact_sha256"] != artifact_sha256:
        raise GateAApprovalError("Requested artifact hash does not match the verified M2f artifact.")

    review = _load_review_receipt(verified["run_dir"], artifact_sha256)
    payload = {
        "schema_version": 1,
        "gate": "A",
        "decision": "APPROVE",
        "artifact_sha256": artifact_sha256,
        "base_artifact_sha256": verified["base_artifact_sha256"],
        "approved_by": approved_by.strip(),
        "approved_at_utc": (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "review_sha256": review["review_sha256"],
        "source_m2f_run": str(verified["run_dir"]),
        "rubric_version": review.get("rubric_version"),
        "portfolio_rubric_version": review.get("portfolio_rubric_version"),
        "selected_candidate_ids": verified["selected_candidate_ids"],
        "llm_called": False,
        "audio_called": False,
        "render_called": False,
    }
    output = verified["run_dir"] / "gate-a-approval.json"
    if output.is_file():
        return _verify_existing(load_json(output), payload)
    payload["approval_sha256"] = canonical_hash(payload)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m2f_run_dir", help="Completed enriched M2f run directory")
    parser.add_argument("--artifact-sha", required=True, help="Exact artifact SHA-256 being approved")
    parser.add_argument("--approved-by", required=True, help="Human approver name")
    args = parser.parse_args()
    try:
        receipt = record_approval(
            Path(args.m2f_run_dir),
            artifact_sha256=args.artifact_sha,
            approved_by=args.approved_by,
        )
    except GateAApprovalError as exc:
        print(json.dumps({"gate_a_approval": "ERROR", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps({
        "gate_a_approval": "APPROVED",
        "artifact_sha256": receipt["artifact_sha256"],
        "approved_by": receipt["approved_by"],
        "approved_at_utc": receipt["approved_at_utc"],
        "approval_sha256": receipt["approval_sha256"],
        "approval_file": str(Path(args.m2f_run_dir).expanduser().resolve() / "gate-a-approval.json"),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
