"""M2d: optional enrichment scout -> independent judge -> arbiter for MAYBE.

This stage never edits the core artifact. It selects optional candidates only.
A later integration stage must create a new artifact hash and re-run execution,
content and language review before Gate A.
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

from flows.m2a_content import AUDIENCE_REGISTRY, canonical_hash  # noqa: E402
from flows.m2b_verify import load_json  # noqa: E402
from flows.m2c_language import verify_m2b_for_language  # noqa: E402
from runners.audience import load_audience_profile  # noqa: E402
from runners.codex_role import CodexRoleRunner, RoleRunnerError  # noqa: E402
from runners.source_pack import SourcePackError, build_source_pack  # noqa: E402

CONFIG = ROOT / "config" / "m2d_enrichment_console.json"
SCOUT_PROMPT = ROOT / "prompts" / "enrichment_scout.md"
JUDGE_PROMPT = ROOT / "prompts" / "judge_enrichment.md"
ARBITER_PROMPT = ROOT / "prompts" / "enrichment_arbiter.md"
RUBRIC = ROOT / "ENRICHMENT_RUBRIC.md"
RUBRIC_VERSION = "0.1"
KINDS = ("pitfall", "practical", "shortcut", "cross_language", "curiosity", "semantic_edge_case")
VERIFICATION_KINDS = ("interactive_python", "python_cli", "documentation_only")


def candidate_schema(max_candidates: int) -> dict:
    item = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "candidate_id": {"type": "string"},
            "kind": {"type": "string", "enum": list(KINDS)},
            "title": {"type": "string"},
            "insertion_point": {"type": "string", "enum": ["after_fragment", "end"]},
            "after_fragment_id": {"type": "string"},
            "proposed_narration": {"type": "string"},
            "value_rationale": {"type": "string"},
            "estimated_seconds": {"type": "integer", "minimum": 3, "maximum": 90},
            "source_support_ids": {
                "type": "array", "minItems": 1, "items": {"type": "string"}
            },
            "verification_kind": {"type": "string", "enum": list(VERIFICATION_KINDS)},
            "verification_commands": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "candidate_id", "kind", "title", "insertion_point", "after_fragment_id",
            "proposed_narration", "value_rationale", "estimated_seconds",
            "source_support_ids", "verification_kind", "verification_commands",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "artifact_sha256": {"type": "string"},
            "role": {"type": "string", "enum": ["enrichment_scout"]},
            "candidates": {"type": "array", "maxItems": max_candidates, "items": item},
            "search_summary": {"type": "string"},
        },
        "required": ["artifact_sha256", "role", "candidates", "search_summary"],
    }


def judge_schema(artifact_sha256: str, candidate_ids: list[str]) -> dict:
    review = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "candidate_id": {"type": "string", "enum": candidate_ids},
            "decision": {"type": "string", "enum": ["KEEP", "MAYBE", "DROP"]},
            "relevance": {"type": "integer", "enum": [0, 1, 2]},
            "novelty_for_audience": {"type": "integer", "enum": [0, 1, 2]},
            "practical_transfer_value": {"type": "integer", "enum": [0, 1, 2]},
            "clarity_gain": {"type": "integer", "enum": [0, 1, 2]},
            "digression_risk": {"type": "integer", "enum": [0, 1, 2]},
            "prerequisite_burden": {"type": "integer", "enum": [0, 1, 2]},
            "reason": {"type": "string"},
            "evidence": {"type": "string"},
        },
        "required": [
            "candidate_id", "decision", "relevance", "novelty_for_audience",
            "practical_transfer_value", "clarity_gain", "digression_risk",
            "prerequisite_burden", "reason", "evidence",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "artifact_sha256": {"type": "string", "enum": [artifact_sha256]},
            "rubric_version": {"type": "string", "enum": [RUBRIC_VERSION]},
            "role": {"type": "string", "enum": ["judge_enrichment"]},
            "reviews": {
                "type": "array", "minItems": len(candidate_ids),
                "maxItems": len(candidate_ids), "items": review,
            },
            "overall_note": {"type": "string"},
        },
        "required": ["artifact_sha256", "rubric_version", "role", "reviews", "overall_note"],
    }


def arbiter_schema(artifact_sha256: str, candidate_ids: list[str]) -> dict:
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
                "type": "array", "minItems": len(candidate_ids),
                "maxItems": len(candidate_ids), "items": item,
            },
        },
        "required": ["artifact_sha256", "rubric_version", "role", "decisions"],
    }


def validate_candidates(output: dict, artifact: dict, source_pack: dict, artifact_sha256: str) -> None:
    if output.get("artifact_sha256") != artifact_sha256:
        raise RoleRunnerError("INVALID_OUTPUT", "Scout returned a different artifact hash.")
    fragments = {row.get("fragment_id") for row in artifact.get("narration", [])}
    source_ids = {row.get("id") for row in source_pack.get("sources", [])}
    seen: set[str] = set()
    for candidate in output.get("candidates", []):
        cid = candidate.get("candidate_id")
        if not isinstance(cid, str) or not cid or cid in seen:
            raise RoleRunnerError("INVALID_OUTPUT", "Enrichment candidate ids must be unique and non-empty.")
        seen.add(cid)
        if candidate.get("insertion_point") == "after_fragment":
            if candidate.get("after_fragment_id") not in fragments:
                raise RoleRunnerError("INVALID_OUTPUT", f"Candidate {cid} references an unknown fragment.")
        elif candidate.get("after_fragment_id") != "":
            raise RoleRunnerError("INVALID_OUTPUT", f"End candidate {cid} must use empty after_fragment_id.")
        supports = candidate.get("source_support_ids", [])
        if not supports or any(value not in source_ids for value in supports):
            raise RoleRunnerError("INVALID_OUTPUT", f"Candidate {cid} has invalid source support ids.")
        if candidate.get("verification_kind") == "documentation_only" and candidate.get("verification_commands"):
            raise RoleRunnerError("INVALID_OUTPUT", f"Documentation-only candidate {cid} must not invent execution commands.")
        if candidate.get("verification_kind") != "documentation_only" and not candidate.get("verification_commands"):
            raise RoleRunnerError("INVALID_OUTPUT", f"Executable candidate {cid} must provide verification commands.")


def validate_reviews(report: dict, candidate_ids: list[str]) -> None:
    ids = [row.get("candidate_id") for row in report.get("reviews", [])]
    if len(ids) != len(candidate_ids) or set(ids) != set(candidate_ids):
        raise RoleRunnerError("INVALID_OUTPUT", "Enrichment judge must review every candidate exactly once.")


def validate_arbiter(report: dict, candidate_ids: list[str]) -> None:
    ids = [row.get("candidate_id") for row in report.get("decisions", [])]
    if len(ids) != len(candidate_ids) or set(ids) != set(candidate_ids):
        raise RoleRunnerError("INVALID_OUTPUT", "Arbiter must resolve every MAYBE candidate exactly once.")


def selection_from(candidates: list[dict], reviews: list[dict], arbiter: dict | None) -> dict:
    by_id = {row["candidate_id"]: row for row in candidates}
    review_by_id = {row["candidate_id"]: row for row in reviews}
    arbiter_by_id = {
        row["candidate_id"]: row for row in (arbiter or {}).get("decisions", [])
    }
    selected_ids: list[str] = []
    rows: list[dict] = []
    for cid, candidate in by_id.items():
        review = review_by_id[cid]
        final = review["decision"]
        if final == "MAYBE":
            final = arbiter_by_id[cid]["decision"]
        if final == "KEEP":
            selected_ids.append(cid)
        rows.append({
            "candidate_id": cid,
            "judge_decision": review["decision"],
            "arbiter_decision": arbiter_by_id.get(cid, {}).get("decision"),
            "final_decision": final,
            "candidate": candidate,
        })
    return {
        "schema_version": 1,
        "selected_candidate_ids": selected_ids,
        "selected_count": len(selected_ids),
        "candidates": rows,
    }


@task(name="m2d-resolve-enrichment-sources", retries=0, cache_policy=NO_CACHE, persist_result=False)
def resolve_enrichment_sources(config: dict) -> dict:
    try:
        return build_source_pack(config)
    except SourcePackError as exc:
        raise RoleRunnerError("BLOCKED_SOURCE", str(exc)) from exc


@task(name="m2d-enrichment-scout", retries=0, cache_policy=NO_CACHE, persist_result=False)
def scout_task(config: dict, artifact: dict, artifact_sha256: str, source_pack: dict, run_dir: str) -> dict:
    runner = CodexRoleRunner(model=config["model"], reasoning_effort=config["reasoning_effort"])
    runner.preflight()
    audience = load_audience_profile(config, AUDIENCE_REGISTRY)
    payload = {
        "role_instructions": SCOUT_PROMPT.read_text(encoding="utf-8"),
        "artifact_sha256": artifact_sha256,
        "core_artifact": artifact,
        "audience_profile": audience,
        "target_runtime": config["target_runtime"],
        "enrichment_sources": source_pack,
        "max_candidates": config["max_candidates"],
        "constraints": [
            "The core has already passed content review; do not rewrite or repair it.",
            "Candidates are optional and zero candidates is acceptable.",
            "Use only source_support_ids present in the enrichment source pack.",
            "Prefer compact technical value over trivia.",
            "Do not claim execution results. Describe verification commands when execution is appropriate.",
        ],
    }
    return runner.run_json(
        role="enrichment_scout", payload=payload,
        schema=candidate_schema(config["max_candidates"]),
        report_dir=Path(run_dir) / "scout",
    )


@task(name="m2d-independent-enrichment-judge", retries=0, cache_policy=NO_CACHE, persist_result=False)
def judge_task(config: dict, artifact: dict, artifact_sha256: str, source_pack: dict, candidates: list[dict], run_dir: str) -> dict:
    runner = CodexRoleRunner(model=config["model"], reasoning_effort=config["reasoning_effort"])
    runner.preflight()
    payload = {
        "role_instructions": JUDGE_PROMPT.read_text(encoding="utf-8"),
        "artifact_sha256": artifact_sha256,
        "core_artifact": artifact,
        "audience_profile": load_audience_profile(config, AUDIENCE_REGISTRY),
        "target_runtime": config["target_runtime"],
        "rubric_version": RUBRIC_VERSION,
        "rubric": RUBRIC.read_text(encoding="utf-8"),
        "enrichment_sources": source_pack,
        "candidates": candidates,
        "constraints": [
            "You do not receive scout history or reasoning.",
            "Review every candidate exactly once.",
            "There is no quota for KEEP.",
            "Choose MAYBE when arbitration is genuinely needed, not as a default compromise.",
        ],
    }
    ids = [row["candidate_id"] for row in candidates]
    return runner.run_json(
        role="judge_enrichment", payload=payload,
        schema=judge_schema(artifact_sha256, ids),
        report_dir=Path(run_dir) / "judge_enrichment",
    )


@task(name="m2d-enrichment-arbiter", retries=0, cache_policy=NO_CACHE, persist_result=False)
def arbiter_task(config: dict, artifact: dict, artifact_sha256: str, source_pack: dict, candidates: list[dict], reviews: list[dict], run_dir: str) -> dict:
    runner = CodexRoleRunner(model=config["model"], reasoning_effort=config["reasoning_effort"])
    runner.preflight()
    ids = [row["candidate_id"] for row in candidates]
    payload = {
        "role_instructions": ARBITER_PROMPT.read_text(encoding="utf-8"),
        "artifact_sha256": artifact_sha256,
        "core_artifact": artifact,
        "audience_profile": load_audience_profile(config, AUDIENCE_REGISTRY),
        "rubric_version": RUBRIC_VERSION,
        "rubric": RUBRIC.read_text(encoding="utf-8"),
        "enrichment_sources": source_pack,
        "maybe_candidates": candidates,
        "judge_reviews": reviews,
        "constraints": [
            "Resolve only the supplied MAYBE candidates.",
            "Do not create new candidates and do not rewrite the core.",
            "KEEP and DROP are the only final decisions.",
        ],
    }
    return runner.run_json(
        role="arbiter", payload=payload,
        schema=arbiter_schema(artifact_sha256, ids),
        report_dir=Path(run_dir) / "arbiter",
    )


@flow(name="video-production-m2d-enrichment-selection", retries=0, persist_result=False)
def m2d_enrichment(m2b_run_dir: str) -> dict:
    logger = get_run_logger()
    input_dir = Path(m2b_run_dir).expanduser().resolve()
    config = load_json(CONFIG)
    run_dir = ROOT / "runs" / "m2d-enrichment" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "stage": "M2d",
        "lesson_id": config["lesson_id"],
        "status": "ERROR",
        "source_m2b_run": str(input_dir),
        "reports": str(run_dir),
        "rubric_version": RUBRIC_VERSION,
        "audience_profile": config["audience_profile"],
        "artifact_unchanged": True,
        "gate_a_reached": False,
        "audio_called": False,
        "render_called": False,
        "production_ready": False,
    }
    try:
        verified = verify_m2b_for_language(input_dir)
        artifact = verified["artifact"]
        artifact_sha256 = verified["artifact_sha256"]
        previous_sessions = set(verified["previous_sessions"])

        source_pack = resolve_enrichment_sources(config)
        (run_dir / "enrichment-source-pack.json").write_text(
            json.dumps(source_pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        scout = scout_task(config, artifact, artifact_sha256, source_pack, str(run_dir))
        scout_session = scout["receipt"]["session_id"]
        if scout_session in previous_sessions:
            raise RoleRunnerError("SESSION_REUSED", "Enrichment scout reused a previous Codex session.")
        candidates_output = scout["output"]
        validate_candidates(candidates_output, artifact, source_pack, artifact_sha256)
        candidates = candidates_output["candidates"]
        (run_dir / "candidates.json").write_text(
            json.dumps(candidates_output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        if not candidates:
            selection = selection_from([], [], None)
            (run_dir / "selection.json").write_text(
                json.dumps(selection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            summary.update(
                status="COMPLETED", artifact_sha256=artifact_sha256,
                scout_session_id=scout_session, candidate_count=0,
                judge_called=False, arbiter_called=False,
                keep_count=0, maybe_count=0, drop_count=0,
                selected_count=0, selected_candidate_ids=[],
                next_action="PROCEED_CORE_UNCHANGED",
            )
            logger.info("M2d completed: scout proposed no enrichment; core remains unchanged.")
            return summary

        judge = judge_task(config, artifact, artifact_sha256, source_pack, candidates, str(run_dir))
        judge_session = judge["receipt"]["session_id"]
        if judge_session in previous_sessions or judge_session == scout_session:
            raise RoleRunnerError("SESSION_REUSED", "Enrichment judge reused an earlier Codex session.")
        report = judge["output"]
        validate_reviews(report, [row["candidate_id"] for row in candidates])
        (run_dir / "judge-enrichment-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        reviews = report["reviews"]
        maybe_ids = [row["candidate_id"] for row in reviews if row["decision"] == "MAYBE"]
        arbiter_output = None
        arbiter_session = None
        if maybe_ids:
            maybe_set = set(maybe_ids)
            maybe_candidates = [row for row in candidates if row["candidate_id"] in maybe_set]
            maybe_reviews = [row for row in reviews if row["candidate_id"] in maybe_set]
            arbiter = arbiter_task(
                config, artifact, artifact_sha256, source_pack,
                maybe_candidates, maybe_reviews, str(run_dir),
            )
            arbiter_session = arbiter["receipt"]["session_id"]
            if arbiter_session in previous_sessions or arbiter_session in {scout_session, judge_session}:
                raise RoleRunnerError("SESSION_REUSED", "Enrichment arbiter reused an earlier Codex session.")
            arbiter_output = arbiter["output"]
            validate_arbiter(arbiter_output, maybe_ids)
            (run_dir / "arbiter-report.json").write_text(
                json.dumps(arbiter_output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

        selection = selection_from(candidates, reviews, arbiter_output)
        (run_dir / "selection.json").write_text(
            json.dumps(selection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        keep_count = sum(row["decision"] == "KEEP" for row in reviews)
        maybe_count = sum(row["decision"] == "MAYBE" for row in reviews)
        drop_count = sum(row["decision"] == "DROP" for row in reviews)
        summary.update(
            status="COMPLETED", artifact_sha256=artifact_sha256,
            enrichment_source_pack_sha256=source_pack["source_pack_sha256"],
            scout_session_id=scout_session, candidate_count=len(candidates),
            judge_called=True, judge_session_id=judge_session,
            keep_count=keep_count, maybe_count=maybe_count, drop_count=drop_count,
            arbiter_called=bool(maybe_ids), arbiter_session_id=arbiter_session,
            selected_count=selection["selected_count"],
            selected_candidate_ids=selection["selected_candidate_ids"],
            next_action="INTEGRATE_SELECTED" if selection["selected_count"] else "PROCEED_CORE_UNCHANGED",
        )
        logger.info(
            "M2d completed. candidates=%d keep=%d maybe=%d drop=%d selected=%d",
            len(candidates), keep_count, maybe_count, drop_count, selection["selected_count"],
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
    print(json.dumps(m2d_enrichment(args.m2b_run_dir), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
