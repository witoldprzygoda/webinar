"""M2c: fresh independent language judge -> human Gate A readiness."""
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
    RUBRIC,
    RUBRIC_VERSION,
    audience_for,
    canonical_hash,
)
from flows.m2b_verify import load_json, verify_m2a_run  # noqa: E402
from runners.codex_role import CodexRoleRunner, RoleRunnerError  # noqa: E402

LANGUAGE_PROMPT = ROOT / "prompts" / "judge_language.md"
LANGUAGE_CRITERIA = ("L1", "L2", "L3", "L4", "P1")


def language_schema(artifact_sha256: str) -> dict:
    criterion = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "criterion_id": {"type": "string", "enum": list(LANGUAGE_CRITERIA)},
            "status": {
                "type": "string",
                "enum": ["PASS", "FAIL", "NOT_VERIFIED", "NOT_APPLICABLE"],
            },
            "reason": {"type": "string"},
        },
        "required": ["criterion_id", "status", "reason"],
    }
    finding = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "criterion_id": {"type": "string", "enum": list(LANGUAGE_CRITERIA)},
            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
            "quote_or_anchor": {"type": "string"},
            "problem": {"type": "string"},
            "evidence": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "proposed_fix": {"type": "string"},
        },
        "required": [
            "criterion_id", "severity", "quote_or_anchor", "problem",
            "evidence", "confidence", "proposed_fix",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "artifact_sha256": {"type": "string", "enum": [artifact_sha256]},
            "rubric_version": {"type": "string", "enum": [RUBRIC_VERSION]},
            "role": {"type": "string", "enum": ["judge_language"]},
            "verdict": {"type": "string", "enum": ["PASS", "REVISE", "BLOCKED"]},
            "criteria": {
                "type": "array", "minItems": len(LANGUAGE_CRITERIA), "maxItems": len(LANGUAGE_CRITERIA), "items": criterion,
            },
            "coverage_checks": {"type": "array", "items": {"type": "string"}},
            "findings": {"type": "array", "items": finding},
        },
        "required": [
            "artifact_sha256", "rubric_version", "role", "verdict",
            "criteria", "coverage_checks", "findings",
        ],
    }


def validate_language_report(report: dict) -> None:
    ids = [row.get("criterion_id") for row in report.get("criteria", [])]
    if len(ids) != len(LANGUAGE_CRITERIA) or set(ids) != set(LANGUAGE_CRITERIA):
        raise RoleRunnerError(
            "INVALID_OUTPUT",
            "Language judge criteria must contain L1, L2, L3, L4 and P1 exactly once.",
        )
    if report.get("verdict") == "PASS":
        statuses = {row.get("status") for row in report["criteria"]}
        if statuses != {"PASS"}:
            raise RoleRunnerError(
                "INVALID_OUTPUT",
                "Language judge cannot return PASS unless every M2c criterion is PASS.",
            )


def _verify_execution_evidence(run_dir: Path, summary: dict) -> dict:
    evidence = load_json(run_dir / "execution-evidence.json")
    saved_hash = evidence.get("execution_evidence_sha256")
    unhashed = {key: value for key, value in evidence.items() if key != "execution_evidence_sha256"}
    if not isinstance(saved_hash, str) or canonical_hash(unhashed) != saved_hash:
        raise RoleRunnerError("BLOCKED_INPUT", "M2b execution evidence hash is invalid.")
    if summary.get("execution_evidence_sha256") != saved_hash:
        raise RoleRunnerError("BLOCKED_INPUT", "M2b summary points to different execution evidence.")
    if evidence.get("all_examples_passed") is not True:
        raise RoleRunnerError("BLOCKED_INPUT", "M2b execution evidence is not fully passing.")
    return evidence


def verify_m2b_for_language(m2b_run_dir: Path) -> dict:
    m2b_run_dir = m2b_run_dir.expanduser().resolve()
    summary = load_json(m2b_run_dir / "summary.json")
    if summary.get("stage") != "M2b" or summary.get("status") != "COMPLETED":
        raise RoleRunnerError("BLOCKED_INPUT", "Input directory is not a completed M2b run.")
    if summary.get("rubric_version") != RUBRIC_VERSION:
        raise RoleRunnerError("BLOCKED_INPUT", "M2b run uses an obsolete rubric version.")
    if summary.get("artifact_unchanged") is not True:
        raise RoleRunnerError("BLOCKED_INPUT", "M2b did not preserve the M2a artifact.")
    if summary.get("all_examples_passed") is not True:
        raise RoleRunnerError("BLOCKED_INPUT", "M2b examples did not all pass.")
    if summary.get("content_judge_pass") is not True or summary.get("judge_verdict") != "PASS":
        raise RoleRunnerError("BLOCKED_INPUT", "Content judge has not passed this artifact.")

    source_value = summary.get("source_m2a_run")
    if not isinstance(source_value, str) or not source_value:
        raise RoleRunnerError("BLOCKED_INPUT", "M2b summary does not identify its M2a source run.")
    m2a_run_dir = Path(source_value).expanduser().resolve()
    m2a_summary, artifact, source_pack, artifact_sha256 = verify_m2a_run(m2a_run_dir)
    if summary.get("artifact_sha256") != artifact_sha256:
        raise RoleRunnerError("BLOCKED_INPUT", "M2b and M2a artifact hashes differ.")
    if summary.get("source_pack_sha256") != source_pack.get("source_pack_sha256"):
        raise RoleRunnerError("BLOCKED_INPUT", "M2b and M2a source-pack hashes differ.")

    _verify_execution_evidence(m2b_run_dir, summary)
    content_report = load_json(m2b_run_dir / "judge-report-with-execution.json")
    if content_report.get("artifact_sha256") != artifact_sha256:
        raise RoleRunnerError("BLOCKED_INPUT", "Content report evaluates a different artifact.")
    if content_report.get("rubric_version") != RUBRIC_VERSION:
        raise RoleRunnerError("BLOCKED_INPUT", "Content report uses an obsolete rubric version.")
    if content_report.get("verdict") != "PASS":
        raise RoleRunnerError("BLOCKED_INPUT", "Stored content report is not PASS.")

    previous_sessions = {
        value for value in (
            m2a_summary.get("author_session_id"),
            m2a_summary.get("judge_session_id"),
            summary.get("judge_session_id"),
        ) if isinstance(value, str) and value
    }
    if len(previous_sessions) != 3:
        raise RoleRunnerError("BLOCKED_INPUT", "Expected three distinct prior Codex sessions.")

    return {
        "m2a_run_dir": m2a_run_dir,
        "m2b_run_dir": m2b_run_dir,
        "m2a_summary": m2a_summary,
        "m2b_summary": summary,
        "artifact": artifact,
        "artifact_sha256": artifact_sha256,
        "source_pack_sha256": source_pack["source_pack_sha256"],
        "previous_sessions": previous_sessions,
    }


def build_language_payload(config: dict, artifact: dict, artifact_sha256: str) -> dict:
    return {
        "role_instructions": LANGUAGE_PROMPT.read_text(encoding="utf-8"),
        "brief": config["brief"],
        "audience_profile": audience_for(config),
        "language": config["language"],
        "rubric_version": RUBRIC_VERSION,
        "rubric": RUBRIC.read_text(encoding="utf-8"),
        "artifact_sha256": artifact_sha256,
        "canonical_text": {
            "title": artifact["title"],
            "narration": artifact["narration"],
        },
        "evaluation_scope": list(LANGUAGE_CRITERIA),
        "constraints": [
            "You are a fresh independent language judge.",
            "You do not receive the author history, author reasoning, content-judge report, content-judge verdict, execution evidence or source pack.",
            "Evaluate only the canonical spoken narration and its fit to the brief and audience profile.",
            "For L1 assess terminological precision in wording, but do not independently certify factual correctness.",
            "For L4 reject polished but infantilizing narration that teaches assumed knowledge instead of the relevant technical content.",
            "For P1 verify that your report names the supplied artifact hash and rubric version; independence is enforced by the orchestrator.",
            "Do not edit or rewrite the narration. Return only the evaluation report.",
            "Do not invent a target number of findings.",
        ],
    }


def fresh_session(new_session: str, previous_sessions: set[str]) -> bool:
    return bool(new_session) and new_session not in previous_sessions


def gate_a_state(*, content_pass: bool, language_pass: bool) -> tuple[bool, str]:
    reached = bool(content_pass and language_pass)
    return reached, "PENDING_HUMAN_APPROVAL" if reached else "NOT_REACHED"


@task(name="m2c-independent-language-judge", retries=0, cache_policy=NO_CACHE, persist_result=False)
def language_task(config: dict, artifact: dict, artifact_sha256: str, run_dir: str) -> dict:
    runner = CodexRoleRunner(model=config["model"], reasoning_effort=config["reasoning_effort"])
    runner.preflight()
    payload = build_language_payload(config, artifact, artifact_sha256)
    result = runner.run_json(
        role="judge_language",
        payload=payload,
        schema=language_schema(artifact_sha256),
        report_dir=Path(run_dir) / "judge_language",
    )
    validate_language_report(result["output"])
    return result


@flow(name="video-production-m2c-language-gate", retries=0, persist_result=False)
def m2c_language(m2b_run_dir: str) -> dict:
    logger = get_run_logger()
    input_dir = Path(m2b_run_dir).expanduser().resolve()
    config = load_json(M2A_CONFIG)
    run_dir = ROOT / "runs" / "m2c-language" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "stage": "M2c",
        "lesson_id": config["lesson_id"],
        "status": "ERROR",
        "production_ready": False,
        "gate_a_reached": False,
        "gate_a_approved": False,
        "gate_a_status": "NOT_REACHED",
        "audio_called": False,
        "render_called": False,
        "revision_cycle": 0,
        "rubric_version": RUBRIC_VERSION,
        "audience_profile": config.get("audience_profile"),
        "source_m2b_run": str(input_dir),
        "reports": str(run_dir),
    }
    try:
        verified = verify_m2b_for_language(input_dir)
        result = language_task(
            config,
            verified["artifact"],
            verified["artifact_sha256"],
            str(run_dir),
        )
        report = result["output"]
        (run_dir / "judge-language-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        new_session = result["receipt"]["session_id"]
        if not fresh_session(new_session, verified["previous_sessions"]):
            raise RoleRunnerError("SESSION_REUSED", "Language judge reused an earlier Codex session id.")

        language_pass = report["verdict"] == "PASS"
        reached, gate_status = gate_a_state(content_pass=True, language_pass=language_pass)
        gate_package = {
            "schema_version": 1,
            "gate": "A",
            "lesson_id": config["lesson_id"],
            "artifact_sha256": verified["artifact_sha256"],
            "source_pack_sha256": verified["source_pack_sha256"],
            "rubric_version": RUBRIC_VERSION,
            "audience_profile": config.get("audience_profile"),
            "content_judge": {
                "status": "PASS",
                "session_id": verified["m2b_summary"]["judge_session_id"],
                "report": str(verified["m2b_run_dir"] / "judge-report-with-execution.json"),
            },
            "language_judge": {
                "status": report["verdict"],
                "session_id": new_session,
                "report": str(run_dir / "judge-language-report.json"),
            },
            "human_approval": gate_status,
        }
        (run_dir / "gate-a-package.json").write_text(
            json.dumps(gate_package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        summary.update(
            status="COMPLETED",
            source_m2a_run=str(verified["m2a_run_dir"]),
            artifact_sha256=verified["artifact_sha256"],
            artifact_unchanged=True,
            content_judge_pass=True,
            language_judge_session_id=new_session,
            language_judge_session_new=True,
            language_judge_verdict=report["verdict"],
            language_findings_count=len(report["findings"]),
            language_judge_pass=language_pass,
            gate_a_reached=reached,
            gate_a_status=gate_status,
            revision_required=not language_pass,
        )
        logger.info(
            "M2c completed. Language judge: %s; Gate A: %s",
            report["verdict"], gate_status,
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
    parser.add_argument("m2b_run_dir", help="Path to a completed, content-PASS M2b run")
    args = parser.parse_args()
    print(json.dumps(m2c_language(args.m2b_run_dir), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
