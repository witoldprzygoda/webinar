"""Run the current M2 content chain from source material to human Gate A.

This orchestrates existing M2a/M2b/M2c flows. Expected review outcomes such as
REVISE are business states, not flow failures. The chain does not approve Gate A
and never calls audio or Remotion.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from prefect import flow, get_run_logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flows.m2a_content import m2a_content  # noqa: E402
from flows.m2b_verify import m2b_verify  # noqa: E402
from flows.m2c_language import m2c_language  # noqa: E402
from runners.codex_role import RoleRunnerError  # noqa: E402


def _require_completed(value: dict, stage: str) -> None:
    if value.get("stage") != stage or value.get("status") != "COMPLETED":
        raise RoleRunnerError("BLOCKED_CHAIN", f"{stage} did not complete successfully.")


def _require_same_artifact(m2a: dict, m2b: dict) -> str:
    artifact = m2b.get("artifact_sha256")
    if not artifact or artifact != m2a.get("artifact_sha256"):
        raise RoleRunnerError("BLOCKED_CHAIN", "M2a and M2b do not refer to one immutable artifact.")
    if m2b.get("artifact_unchanged") is not True:
        raise RoleRunnerError("BLOCKED_CHAIN", "Artifact changed inside M2b verification.")
    return artifact


def summarize_content_revision(m2a: dict, m2b: dict) -> dict:
    """Return a normal business result when content review says REVISE/BLOCKED."""
    _require_completed(m2a, "M2a")
    _require_completed(m2b, "M2b")
    artifact = _require_same_artifact(m2a, m2b)
    if m2b.get("content_judge_pass") is True or m2b.get("judge_verdict") == "PASS":
        raise RoleRunnerError("BLOCKED_CHAIN", "Content revision summary requested for a passing review.")

    verdict = m2b.get("judge_verdict")
    return {
        "stage": "M2",
        "lesson_id": m2b.get("lesson_id") or m2a.get("lesson_id"),
        "status": "REVISION_REQUIRED",
        "stop_reason": f"CONTENT_JUDGE_{verdict or 'NONPASS'}",
        "rubric_version": m2a.get("rubric_version"),
        "audience_profile": m2a.get("audience_profile"),
        "artifact_sha256": artifact,
        "m2a_run": m2a.get("reports"),
        "m2b_run": m2b.get("reports"),
        "m2c_run": None,
        "initial_content_judge_verdict": m2a.get("judge_verdict"),
        "execution_examples_passed": m2b.get("all_examples_passed"),
        "content_judge_verdict": verdict,
        "content_findings_count": m2b.get("findings_count"),
        "content_judge_pass": False,
        "language_judge_called": False,
        "language_judge_pass": None,
        "language_findings_count": None,
        "gate_a_reached": False,
        "gate_a_approved": False,
        "gate_a_status": "NOT_REACHED",
        "audio_called": False,
        "render_called": False,
        "production_ready": False,
    }


def summarize_chain(m2a: dict, m2b: dict, m2c: dict) -> dict:
    for value, stage in ((m2a, "M2a"), (m2b, "M2b"), (m2c, "M2c")):
        _require_completed(value, stage)

    artifact = _require_same_artifact(m2a, m2b)
    if artifact != m2c.get("artifact_sha256"):
        raise RoleRunnerError("BLOCKED_CHAIN", "M2c evaluates a different artifact.")
    if m2c.get("artifact_unchanged") is not True:
        raise RoleRunnerError("BLOCKED_CHAIN", "Artifact changed inside M2c verification.")
    if m2b.get("content_judge_pass") is not True:
        raise RoleRunnerError("BLOCKED_CHAIN", "Language review ran without a passing content review.")

    gate_reached = m2c.get("gate_a_reached") is True
    return {
        "stage": "M2",
        "lesson_id": m2c.get("lesson_id"),
        "status": "WAITING_HUMAN" if gate_reached else "REVISION_REQUIRED",
        "stop_reason": None if gate_reached else "LANGUAGE_JUDGE_NONPASS",
        "rubric_version": m2a.get("rubric_version"),
        "audience_profile": m2a.get("audience_profile"),
        "artifact_sha256": artifact,
        "m2a_run": m2a.get("reports"),
        "m2b_run": m2b.get("reports"),
        "m2c_run": m2c.get("reports"),
        "initial_content_judge_verdict": m2a.get("judge_verdict"),
        "execution_examples_passed": m2b.get("all_examples_passed"),
        "content_judge_verdict": m2b.get("judge_verdict"),
        "content_findings_count": m2b.get("findings_count"),
        "content_judge_pass": True,
        "language_judge_called": True,
        "language_judge_pass": m2c.get("language_judge_pass"),
        "language_findings_count": m2c.get("language_findings_count"),
        "gate_a_reached": gate_reached,
        "gate_a_approved": False,
        "gate_a_status": m2c.get("gate_a_status"),
        "audio_called": False,
        "render_called": False,
        "production_ready": False,
    }


@flow(name="video-production-m2-content-gate", retries=0, persist_result=False)
def m2_content_gate() -> dict:
    logger = get_run_logger()
    m2a = m2a_content()
    m2b = m2b_verify(m2a["reports"])

    # A negative content verdict is expected control flow: stop here and hand the
    # immutable artifact plus findings to the revision stage. Do not call the
    # language judge, because M2c is intentionally defined only for content-PASS.
    if m2b.get("status") == "COMPLETED" and m2b.get("content_judge_pass") is not True:
        result = summarize_content_revision(m2a, m2b)
        logger.info(
            "M2 stopped normally for revision. Content judge: %s; findings: %s",
            result["content_judge_verdict"],
            result["content_findings_count"],
        )
        logger.info("Artifact: %s", result["artifact_sha256"])
        return result

    m2c = m2c_language(m2b["reports"])
    result = summarize_chain(m2a, m2b, m2c)
    logger.info("M2 chain finished with business status: %s", result["status"])
    logger.info("Artifact: %s", result["artifact_sha256"])
    return result


if __name__ == "__main__":
    print(json.dumps(m2_content_gate(), indent=2, ensure_ascii=False))
