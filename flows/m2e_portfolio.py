"""M2e: global portfolio arbitration for individually accepted enrichment candidates.

M2d answers whether candidates are worthwhile one by one. M2e answers the
separate question: which subset forms the best compact portfolio for this lesson?
It never edits the core or candidate text.
"""
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

from flows.m2a_content import AUDIENCE_REGISTRY  # noqa: E402
from flows.m2b_verify import load_json  # noqa: E402
from flows.m2c_language import verify_m2b_for_language  # noqa: E402
from runners.audience import load_audience_profile  # noqa: E402
from runners.codex_role import CodexRoleRunner, RoleRunnerError  # noqa: E402

CONFIG = ROOT / "config" / "m2e_enrichment_portfolio.json"
PROMPT = ROOT / "prompts" / "enrichment_portfolio_arbiter.md"
RUBRIC = ROOT / "ENRICHMENT_PORTFOLIO_RUBRIC.md"
RUBRIC_VERSION = "0.2"


def portfolio_schema(artifact_sha256: str, candidate_ids: list[str]) -> dict:
    item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "candidate_id": {"type": "string", "enum": candidate_ids},
            "decision": {"type": "string", "enum": ["KEEP", "DROP"]},
            "reason": {"type": "string"},
        },
        "required": ["candidate_id", "decision", "reason"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "artifact_sha256": {"type": "string", "enum": [artifact_sha256]},
            "rubric_version": {"type": "string", "enum": [RUBRIC_VERSION]},
            "role": {"type": "string", "enum": ["arbiter"]},
            "decisions": {
                "type": "array",
                "minItems": len(candidate_ids),
                "maxItems": len(candidate_ids),
                "items": item,
            },
            "portfolio_note": {"type": "string"},
        },
        "required": ["artifact_sha256", "rubric_version", "role", "decisions", "portfolio_note"],
    }


def validate_portfolio_report(report: dict, candidate_ids: list[str]) -> None:
    ids = [row.get("candidate_id") for row in report.get("decisions", [])]
    if len(ids) != len(candidate_ids) or set(ids) != set(candidate_ids):
        raise RoleRunnerError("INVALID_OUTPUT", "Portfolio arbiter must decide every candidate exactly once.")


def finalize_portfolio(candidates: list[dict], decisions: list[dict], config: dict) -> dict:
    by_id = {row["candidate_id"]: row for row in candidates}
    if len(by_id) != len(candidates):
        raise RoleRunnerError("BLOCKED_INPUT", "Portfolio input contains duplicate candidate ids.")
    decision_by_id = {row["candidate_id"]: row for row in decisions}
    if set(decision_by_id) != set(by_id):
        raise RoleRunnerError("INVALID_OUTPUT", "Portfolio decisions do not match the input candidates.")

    selected_ids = [cid for cid in by_id if decision_by_id[cid]["decision"] == "KEEP"]
    selected_seconds = sum(int(by_id[cid]["estimated_seconds"]) for cid in selected_ids)
    total_candidate_seconds = sum(int(row["estimated_seconds"]) for row in candidates)
    hard_budget = int(config["hard_budget_seconds"])
    soft_budget = int(config["soft_budget_seconds"])
    max_selected = int(config["max_selected_candidates"])

    if len(selected_ids) > max_selected:
        raise RoleRunnerError(
            "INVALID_OUTPUT",
            f"Portfolio selected {len(selected_ids)} candidates; maximum is {max_selected}.",
        )
    if selected_seconds > hard_budget:
        raise RoleRunnerError(
            "INVALID_OUTPUT",
            f"Portfolio costs {selected_seconds}s; hard budget is {hard_budget}s.",
        )

    return {
        "schema_version": 1,
        "selected_candidate_ids": selected_ids,
        "selected_count": len(selected_ids),
        "selected_estimated_seconds": selected_seconds,
        "total_candidate_seconds": total_candidate_seconds,
        "soft_budget_seconds": soft_budget,
        "hard_budget_seconds": hard_budget,
        "soft_budget_exceeded": selected_seconds > soft_budget,
        "max_selected_candidates": max_selected,
        "decisions": [
            {
                "candidate_id": cid,
                "decision": decision_by_id[cid]["decision"],
                "reason": decision_by_id[cid]["reason"],
                "candidate": by_id[cid],
            }
            for cid in by_id
        ],
    }


def verify_m2d_run(m2d_run_dir: Path) -> dict:
    run_dir = m2d_run_dir.expanduser().resolve()
    summary = load_json(run_dir / "summary.json")
    if summary.get("stage") != "M2d" or summary.get("status") != "COMPLETED":
        raise RoleRunnerError("BLOCKED_INPUT", "Input directory is not a completed M2d run.")
    if summary.get("artifact_unchanged") is not True:
        raise RoleRunnerError("BLOCKED_INPUT", "M2d did not preserve the core artifact.")

    source_m2b = summary.get("source_m2b_run")
    if not isinstance(source_m2b, str) or not source_m2b:
        raise RoleRunnerError("BLOCKED_INPUT", "M2d summary does not identify its M2b source run.")
    verified = verify_m2b_for_language(Path(source_m2b))
    if summary.get("artifact_sha256") != verified["artifact_sha256"]:
        raise RoleRunnerError("BLOCKED_INPUT", "M2d and M2b artifact hashes differ.")

    selection = load_json(run_dir / "selection.json")
    rows = selection.get("candidates", [])
    if not isinstance(rows, list):
        raise RoleRunnerError("BLOCKED_INPUT", "M2d selection candidates must be a list.")
    selected_ids = selection.get("selected_candidate_ids", [])
    if not isinstance(selected_ids, list) or selection.get("selected_count") != len(selected_ids):
        raise RoleRunnerError("BLOCKED_INPUT", "M2d selection count is inconsistent.")

    selected_rows = [row for row in rows if row.get("final_decision") == "KEEP"]
    selected_from_rows = [row.get("candidate_id") for row in selected_rows]
    if selected_from_rows != selected_ids:
        raise RoleRunnerError("BLOCKED_INPUT", "M2d selection ids are inconsistent with final decisions.")
    candidates = [row.get("candidate") for row in selected_rows]
    if any(not isinstance(row, dict) for row in candidates):
        raise RoleRunnerError("BLOCKED_INPUT", "M2d selection contains an invalid candidate payload.")

    judge_report = None
    judge_path = run_dir / "judge-enrichment-report.json"
    if judge_path.is_file():
        judge_report = load_json(judge_path)
        if judge_report.get("artifact_sha256") != verified["artifact_sha256"]:
            raise RoleRunnerError("BLOCKED_INPUT", "M2d judge report refers to a different artifact.")
    reviews_by_id = {
        row.get("candidate_id"): row
        for row in (judge_report or {}).get("reviews", [])
        if isinstance(row, dict)
    }

    previous_sessions = set(verified["previous_sessions"])
    for key in ("scout_session_id", "judge_session_id", "arbiter_session_id"):
        value = summary.get(key)
        if isinstance(value, str) and value:
            previous_sessions.add(value)

    return {
        "m2d_run_dir": run_dir,
        "m2d_summary": summary,
        "artifact": verified["artifact"],
        "artifact_sha256": verified["artifact_sha256"],
        "audience_profile": summary.get("audience_profile"),
        "candidates": candidates,
        "candidate_context": [
            {
                "candidate": candidate,
                "individual_review": reviews_by_id.get(candidate["candidate_id"]),
            }
            for candidate in candidates
        ],
        "previous_sessions": previous_sessions,
    }


@task(name="m2e-enrichment-portfolio-arbiter", retries=0, cache_policy=NO_CACHE, persist_result=False)
def portfolio_task(config: dict, verified: dict, run_dir: str) -> dict:
    runner = CodexRoleRunner(model=config["model"], reasoning_effort=config["reasoning_effort"])
    runner.preflight()
    audience_id = verified.get("audience_profile")
    audience = load_audience_profile({"audience_profile": audience_id}, AUDIENCE_REGISTRY)
    candidate_ids = [row["candidate_id"] for row in verified["candidates"]]
    payload = {
        "role_instructions": PROMPT.read_text(encoding="utf-8"),
        "artifact_sha256": verified["artifact_sha256"],
        "core_artifact": {
            "title": verified["artifact"]["title"],
            "narration": verified["artifact"]["narration"],
        },
        "audience_profile": audience,
        "rubric_version": RUBRIC_VERSION,
        "rubric": RUBRIC.read_text(encoding="utf-8"),
        "portfolio_constraints": {
            "soft_budget_seconds": config["soft_budget_seconds"],
            "hard_budget_seconds": config["hard_budget_seconds"],
            "max_selected_candidates": config["max_selected_candidates"],
        },
        "candidates": verified["candidate_context"],
        "constraints": [
            "All candidates already survived individual enrichment selection; this does not mean they all belong in the final portfolio.",
            "Optimize marginal and orthogonal value relative to the core and other selected candidates, not mere proximity to the core's main axis.",
            "Assess redundancy, thematic balance, insertion clustering and total time across the set.",
            "Soft budget is not a target to hit exactly; exceeding it is allowed when an additional candidate brings distinct high value within the hard limit.",
            "You may select zero candidates.",
            "Do not edit candidate wording or invent a replacement candidate.",
            "Return one KEEP or DROP decision for every supplied candidate.",
        ],
    }
    return runner.run_json(
        role="arbiter",
        payload=payload,
        schema=portfolio_schema(verified["artifact_sha256"], candidate_ids),
        report_dir=Path(run_dir) / "portfolio_arbiter",
    )


@flow(name="video-production-m2e-enrichment-portfolio", retries=0, persist_result=False)
def m2e_portfolio(m2d_run_dir: str) -> dict:
    logger = get_run_logger()
    input_dir = Path(m2d_run_dir).expanduser().resolve()
    config = load_json(CONFIG)
    run_dir = ROOT / "runs" / "m2e-portfolio" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "stage": "M2e",
        "status": "ERROR",
        "source_m2d_run": str(input_dir),
        "reports": str(run_dir),
        "rubric_version": RUBRIC_VERSION,
        "artifact_unchanged": True,
        "gate_a_reached": False,
        "audio_called": False,
        "render_called": False,
        "production_ready": False,
    }
    try:
        verified = verify_m2d_run(input_dir)
        candidates = verified["candidates"]
        summary.update(
            artifact_sha256=verified["artifact_sha256"],
            audience_profile=verified["audience_profile"],
            input_selected_count=len(candidates),
            input_estimated_seconds=sum(int(row["estimated_seconds"]) for row in candidates),
        )

        if len(candidates) <= 1:
            decisions = [
                {"candidate_id": row["candidate_id"], "decision": "KEEP", "reason": "Single surviving candidate; no portfolio conflict."}
                for row in candidates
            ]
            portfolio = finalize_portfolio(candidates, decisions, config)
            (run_dir / "portfolio-selection.json").write_text(
                json.dumps(portfolio, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            summary.update(
                status="COMPLETED", portfolio_arbiter_called=False,
                selected_count=portfolio["selected_count"],
                selected_candidate_ids=portfolio["selected_candidate_ids"],
                selected_estimated_seconds=portfolio["selected_estimated_seconds"],
                soft_budget_exceeded=portfolio["soft_budget_exceeded"],
                next_action="INTEGRATE_SELECTED" if portfolio["selected_count"] else "PROCEED_CORE_UNCHANGED",
            )
            return summary

        result = portfolio_task(config, verified, str(run_dir))
        report = result["output"]
        candidate_ids = [row["candidate_id"] for row in candidates]
        validate_portfolio_report(report, candidate_ids)
        session_id = result["receipt"]["session_id"]
        if session_id in verified["previous_sessions"]:
            raise RoleRunnerError("SESSION_REUSED", "Portfolio arbiter reused an earlier Codex session.")
        (run_dir / "portfolio-arbiter-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        portfolio = finalize_portfolio(candidates, report["decisions"], config)
        portfolio["portfolio_note"] = report["portfolio_note"]
        (run_dir / "portfolio-selection.json").write_text(
            json.dumps(portfolio, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        summary.update(
            status="COMPLETED", portfolio_arbiter_called=True,
            portfolio_arbiter_session_id=session_id,
            selected_count=portfolio["selected_count"],
            selected_candidate_ids=portfolio["selected_candidate_ids"],
            selected_estimated_seconds=portfolio["selected_estimated_seconds"],
            soft_budget_seconds=portfolio["soft_budget_seconds"],
            hard_budget_seconds=portfolio["hard_budget_seconds"],
            soft_budget_exceeded=portfolio["soft_budget_exceeded"],
            next_action="INTEGRATE_SELECTED" if portfolio["selected_count"] else "PROCEED_CORE_UNCHANGED",
        )
        logger.info(
            "M2e completed. input=%d/%ds selected=%d/%ds soft=%ds hard=%ds",
            len(candidates), portfolio["total_candidate_seconds"],
            portfolio["selected_count"], portfolio["selected_estimated_seconds"],
            portfolio["soft_budget_seconds"], portfolio["hard_budget_seconds"],
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
    parser.add_argument("m2d_run_dir", help="Path to a completed M2d enrichment run")
    args = parser.parse_args()
    print(json.dumps(m2e_portfolio(args.m2d_run_dir), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
