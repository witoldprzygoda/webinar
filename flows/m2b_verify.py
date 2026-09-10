"""M2b: artifact-bound execution evidence -> fresh independent content re-review."""
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

from flows.m2a_content import (  # noqa: E402
    CONFIG as M2A_CONFIG,
    CONTENT_CRITERIA,
    JUDGE_PROMPT,
    RUBRIC,
    RUBRIC_VERSION,
    audience_for,
    canonical_hash,
    judge_schema,
    validate_author_artifact,
    validate_judge_report,
)
from runners.codex_role import CodexRoleRunner, RoleRunnerError  # noqa: E402
from runners.example_executor import ExecutionEvidenceError, run_execution_plan  # noqa: E402


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RoleRunnerError("BLOCKED_INPUT", f"Cannot read valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RoleRunnerError("BLOCKED_INPUT", f"JSON root must be an object: {path}")
    return value


def verify_m2a_run(run_dir: Path) -> tuple[dict, dict, dict, str]:
    summary = load_json(run_dir / "summary.json")
    artifact = load_json(run_dir / "artifact.json")
    source_pack = load_json(run_dir / "source-pack.json")
    if summary.get("stage") != "M2a" or summary.get("status") != "COMPLETED":
        raise RoleRunnerError("BLOCKED_INPUT", "Input directory is not a completed M2a run.")
    if summary.get("rubric_version") != RUBRIC_VERSION:
        raise RoleRunnerError("BLOCKED_INPUT", "M2a run uses an obsolete rubric version.")
    validate_author_artifact(artifact)
    artifact_sha256 = canonical_hash(artifact)
    if summary.get("artifact_sha256") != artifact_sha256:
        raise RoleRunnerError("BLOCKED_INPUT", "M2a artifact hash does not match summary.json.")
    plan_hash = canonical_hash(artifact["execution_plan"])
    if summary.get("execution_plan_sha256") != plan_hash:
        raise RoleRunnerError("BLOCKED_INPUT", "M2a execution plan hash does not match summary.json.")
    pack_hash = source_pack.get("source_pack_sha256")
    unhashed = {key: value for key, value in source_pack.items() if key != "source_pack_sha256"}
    if not isinstance(pack_hash, str) or canonical_hash(unhashed) != pack_hash:
        raise RoleRunnerError("BLOCKED_INPUT", "M2a source pack hash is invalid.")
    if summary.get("source_pack_sha256") != pack_hash:
        raise RoleRunnerError("BLOCKED_INPUT", "M2a source pack hash does not match summary.json.")
    return summary, artifact, source_pack, artifact_sha256


@task(name="m2b-execute-artifact-examples", retries=0, cache_policy=NO_CACHE, persist_result=False)
def execute_task(plan: dict, expected_runtime: str) -> dict:
    try:
        return run_execution_plan(plan, expected_runtime)
    except ExecutionEvidenceError as exc:
        raise RoleRunnerError(exc.status, str(exc)) from exc


@task(name="m2b-independent-content-rejudge", retries=0, cache_policy=NO_CACHE, persist_result=False)
def judge_task(
    config: dict,
    source_pack: dict,
    artifact: dict,
    artifact_sha256: str,
    execution_evidence: dict,
    run_dir: str,
) -> dict:
    runner = CodexRoleRunner(model=config["model"], reasoning_effort=config["reasoning_effort"])
    runner.preflight()
    payload = {
        "role_instructions": JUDGE_PROMPT.read_text(encoding="utf-8"),
        "brief": config["brief"],
        "audience_profile": audience_for(config),
        "target_runtime": config["target_runtime"],
        "rubric_version": RUBRIC_VERSION,
        "rubric": RUBRIC.read_text(encoding="utf-8"),
        "artifact_sha256": artifact_sha256,
        "artifact": artifact,
        "source_pack": source_pack,
        "evaluation_scope": list(CONTENT_CRITERIA),
        "execution_evidence": execution_evidence,
        "constraints": [
            "You are a fresh independent judge. No previous judge report or verdict is supplied.",
            "This is the same immutable artifact as in M2a; do not reward a revision because there was none.",
            "Execution evidence was generated directly from artifact.execution_plan, preserving session_id, example_id, fragment_ids and exact inputs.",
            "Assess E1 and E2 against the actual stdout/stderr and verify that every concrete narrated code example is represented by sufficient execution evidence.",
            "A successful executor run does not itself prove that the narration quoted the result correctly; compare the actual result with the text.",
            "Apply L4 independently against the explicit audience profile.",
            "Material is not automatically factual evidence; prefer evidence-role sources for version-dependent claims.",
            "Do not rewrite the artifact. Return only the evaluation report.",
            "Do not invent a target number of findings."
        ]
    }
    result = runner.run_json(
        role="judge_content",
        payload=payload,
        schema=judge_schema(artifact_sha256),
        report_dir=Path(run_dir) / "judge_content",
    )
    validate_judge_report(result["output"])
    return result


@flow(name="video-production-m2b-execution-evidence", retries=0, persist_result=False)
def m2b_verify(m2a_run_dir: str) -> dict:
    logger = get_run_logger()
    input_dir = Path(m2a_run_dir).expanduser().resolve()
    config = load_json(M2A_CONFIG)
    run_dir = ROOT / "runs" / "m2b-execution" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "stage": "M2b",
        "lesson_id": config["lesson_id"],
        "status": "ERROR",
        "production_ready": False,
        "gate_a_reached": False,
        "audio_called": False,
        "render_called": False,
        "revision_cycle": 0,
        "rubric_version": RUBRIC_VERSION,
        "audience_profile": config.get("audience_profile"),
        "source_m2a_run": str(input_dir),
        "reports": str(run_dir),
    }
    try:
        old_summary, artifact, source_pack, artifact_sha256 = verify_m2a_run(input_dir)
        plan = artifact["execution_plan"]
        evidence = execute_task(plan, config["execution_runtime"])
        (run_dir / "execution-evidence.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if not evidence["all_examples_passed"]:
            summary.update(
                status="EXECUTION_MISMATCH",
                artifact_sha256=artifact_sha256,
                artifact_unchanged=True,
                execution_plan_sha256=canonical_hash(plan),
                execution_evidence_sha256=evidence["execution_evidence_sha256"],
                runtime_actual=evidence["runtime"]["version"],
                all_examples_passed=False,
            )
            logger.error("Artifact-bound execution evidence contains mismatches; judge was not called.")
            return summary

        judge = judge_task(config, source_pack, artifact, artifact_sha256, evidence, str(run_dir))
        report = judge["output"]
        (run_dir / "judge-report-with-execution.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        new_session = judge["receipt"]["session_id"]
        old_sessions = {old_summary.get("author_session_id"), old_summary.get("judge_session_id")}
        if new_session in old_sessions:
            raise RoleRunnerError("SESSION_REUSED", "M2b judge reused an earlier M2a Codex session id.")
        summary.update(
            status="COMPLETED",
            artifact_sha256=artifact_sha256,
            artifact_unchanged=True,
            source_pack_sha256=source_pack["source_pack_sha256"],
            execution_plan_sha256=evidence["execution_plan_sha256"],
            execution_evidence_sha256=evidence["execution_evidence_sha256"],
            runtime_requested=evidence["runtime_requested"],
            runtime_actual=evidence["runtime"]["version"],
            all_examples_passed=True,
            prior_author_session_id=old_summary.get("author_session_id"),
            prior_judge_session_id=old_summary.get("judge_session_id"),
            judge_session_id=new_session,
            judge_session_new=True,
            judge_verdict=report["verdict"],
            findings_count=len(report["findings"]),
            content_judge_pass=report["verdict"] == "PASS",
        )
        logger.info(
            "M2b completed. Same artifact: %s; judge verdict: %s",
            artifact_sha256,
            report["verdict"],
        )
        logger.info("Artifacts: %s", run_dir)
        return summary
    except RoleRunnerError as exc:
        summary["status"] = exc.status
        summary["error"] = str(exc)
        logger.error("%s: %s", exc.status, exc)
        raise
    finally:
        (run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m2a_run_dir", help="Path to a completed M2a run directory")
    args = parser.parse_args()
    print(json.dumps(m2b_verify(args.m2a_run_dir), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
