"""Run the current M2 content chain from source material to human Gate A.

This orchestrates existing M2a/M2b/M2c flows. It does not approve Gate A and
never calls audio or Remotion.
"""
from __future__ import annotations

import json

from prefect import flow, get_run_logger

from flows.m2a_content import m2a_content
from flows.m2b_verify import m2b_verify
from flows.m2c_language import m2c_language
from runners.codex_role import RoleRunnerError


def summarize_chain(m2a: dict, m2b: dict, m2c: dict) -> dict:
    expected = ((m2a, "M2a"), (m2b, "M2b"), (m2c, "M2c"))
    for value, stage in expected:
        if value.get("stage") != stage or value.get("status") != "COMPLETED":
            raise RoleRunnerError("BLOCKED_CHAIN", f"{stage} did not complete successfully.")

    artifact = m2c.get("artifact_sha256")
    if not artifact or artifact != m2b.get("artifact_sha256") or artifact != m2a.get("artifact_sha256"):
        raise RoleRunnerError("BLOCKED_CHAIN", "M2 stages do not refer to one immutable artifact.")
    if m2b.get("artifact_unchanged") is not True or m2c.get("artifact_unchanged") is not True:
        raise RoleRunnerError("BLOCKED_CHAIN", "Artifact changed inside the verification chain.")

    gate_reached = m2c.get("gate_a_reached") is True
    return {
        "stage": "M2",
        "lesson_id": m2c.get("lesson_id"),
        "status": "WAITING_HUMAN" if gate_reached else "REVISION_REQUIRED",
        "rubric_version": m2a.get("rubric_version"),
        "audience_profile": m2a.get("audience_profile"),
        "artifact_sha256": artifact,
        "m2a_run": m2a.get("reports"),
        "m2b_run": m2b.get("reports"),
        "m2c_run": m2c.get("reports"),
        "initial_content_judge_verdict": m2a.get("judge_verdict"),
        "execution_examples_passed": m2b.get("all_examples_passed"),
        "content_judge_pass": m2b.get("content_judge_pass"),
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
    m2c = m2c_language(m2b["reports"])
    result = summarize_chain(m2a, m2b, m2c)
    logger.info("M2 chain finished with business status: %s", result["status"])
    logger.info("Artifact: %s", result["artifact_sha256"])
    return result


if __name__ == "__main__":
    print(json.dumps(m2_content_gate(), indent=2, ensure_ascii=False))
