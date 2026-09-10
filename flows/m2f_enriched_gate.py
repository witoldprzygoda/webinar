"""M2f: integrate selected enrichment -> execute -> content judge -> language judge -> Gate A.

The accepted core narration is immutable. A fresh integrator may add only the
portfolio-selected enrichment fragments. The resulting new artifact hash is
fully re-verified before human Gate A.
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

from flows.m2a_content import (  # noqa: E402
    AUDIENCE_REGISTRY,
    CONFIG as M2A_CONFIG,
    CONTENT_CRITERIA,
    JUDGE_PROMPT,
    RUBRIC,
    RUBRIC_VERSION,
    audience_for,
    author_schema,
    canonical_hash,
    judge_schema,
    validate_author_artifact,
    validate_judge_report,
)
from flows.m2b_verify import load_json  # noqa: E402
from flows.m2c_language import (  # noqa: E402
    fresh_session,
    language_task,
    verify_m2b_for_language,
)
from flows.m2e_portfolio import (  # noqa: E402
    RUBRIC_VERSION as PORTFOLIO_RUBRIC_VERSION,
    verify_m2d_run,
)
from runners.codex_role import CodexRoleRunner, RoleRunnerError  # noqa: E402
from runners.enrichment_executor import run_enrichment_plan  # noqa: E402
from runners.example_executor import ExecutionEvidenceError, run_execution_plan  # noqa: E402

INTEGRATOR_PROMPT = ROOT / "prompts" / "enrichment_integrator.md"


def verification_plan_schema() -> dict:
    check = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "check_id": {"type": "string"},
            "candidate_id": {"type": "string"},
            "fragment_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "mode": {"type": "string", "enum": ["interactive_python", "python_cli"]},
            "code": {"type": "string"},
            "expected_outcome": {"type": "string", "enum": ["success", "exception"]},
            "expected_exception": {"type": "string"},
        },
        "required": [
            "check_id", "candidate_id", "fragment_ids", "mode", "code",
            "expected_outcome", "expected_exception",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "integer", "enum": [1]},
            "checks": {"type": "array", "items": check},
        },
        "required": ["schema_version", "checks"],
    }


def integrated_artifact_schema() -> dict:
    schema = author_schema()
    schema["properties"]["enrichment"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "selected_candidate_ids": {"type": "array", "items": {"type": "string"}},
            "integration_map": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "fragment_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                        "claim_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    },
                    "required": ["candidate_id", "fragment_ids", "claim_ids"],
                },
            },
            "verification_plan": verification_plan_schema(),
        },
        "required": ["selected_candidate_ids", "integration_map", "verification_plan"],
    }
    schema["required"] = [*schema["required"], "enrichment"]
    return schema


def _validate_pack_hash(pack: dict, label: str) -> None:
    saved = pack.get("source_pack_sha256")
    unhashed = {key: value for key, value in pack.items() if key != "source_pack_sha256"}
    if not isinstance(saved, str) or canonical_hash(unhashed) != saved:
        raise RoleRunnerError("BLOCKED_INPUT", f"{label} source-pack hash is invalid.")


def merge_source_packs(base: dict, enrichment: dict) -> dict:
    _validate_pack_hash(base, "Core")
    _validate_pack_hash(enrichment, "Enrichment")
    if base.get("lesson_id") != enrichment.get("lesson_id"):
        raise RoleRunnerError("BLOCKED_INPUT", "Core and enrichment source packs refer to different lessons.")

    by_id: dict[str, dict] = {}
    ordered: list[dict] = []
    for source in [*base.get("sources", []), *enrichment.get("sources", [])]:
        source_id = source.get("id") if isinstance(source, dict) else None
        if not isinstance(source_id, str) or not source_id:
            raise RoleRunnerError("BLOCKED_INPUT", "Source pack contains an invalid source id.")
        if source_id in by_id:
            if by_id[source_id] != source:
                raise RoleRunnerError("BLOCKED_INPUT", f"Source id {source_id} has conflicting provenance.")
            continue
        by_id[source_id] = source
        ordered.append(source)

    merged = {
        "schema_version": 1,
        "lesson_id": base.get("lesson_id"),
        "target_runtime": base.get("target_runtime"),
        "sources": ordered,
    }
    merged["source_pack_sha256"] = canonical_hash(merged)
    return merged


def verify_m2e_run(m2e_run_dir: Path) -> dict:
    run_dir = m2e_run_dir.expanduser().resolve()
    summary = load_json(run_dir / "summary.json")
    if summary.get("stage") != "M2e" or summary.get("status") != "COMPLETED":
        raise RoleRunnerError("BLOCKED_INPUT", "Input directory is not a completed M2e run.")
    if summary.get("rubric_version") != PORTFOLIO_RUBRIC_VERSION:
        raise RoleRunnerError("BLOCKED_INPUT", "M2e run uses an obsolete portfolio rubric.")
    if summary.get("artifact_unchanged") is not True:
        raise RoleRunnerError("BLOCKED_INPUT", "M2e did not preserve the core artifact.")

    source_m2d = summary.get("source_m2d_run")
    if not isinstance(source_m2d, str) or not source_m2d:
        raise RoleRunnerError("BLOCKED_INPUT", "M2e summary does not identify its M2d source run.")
    m2d = verify_m2d_run(Path(source_m2d))
    if summary.get("artifact_sha256") != m2d["artifact_sha256"]:
        raise RoleRunnerError("BLOCKED_INPUT", "M2e and M2d artifact hashes differ.")

    portfolio = load_json(run_dir / "portfolio-selection.json")
    selected_ids = portfolio.get("selected_candidate_ids")
    if not isinstance(selected_ids, list) or portfolio.get("selected_count") != len(selected_ids):
        raise RoleRunnerError("BLOCKED_INPUT", "M2e portfolio selection count is inconsistent.")
    if summary.get("selected_candidate_ids") != selected_ids:
        raise RoleRunnerError("BLOCKED_INPUT", "M2e summary and portfolio selection ids differ.")
    if not selected_ids:
        raise RoleRunnerError("BLOCKED_INPUT", "M2f integration requires at least one selected enrichment candidate.")

    decisions = portfolio.get("decisions")
    if not isinstance(decisions, list):
        raise RoleRunnerError("BLOCKED_INPUT", "M2e portfolio decisions are missing.")
    selected_candidates = [
        row.get("candidate") for row in decisions
        if isinstance(row, dict) and row.get("decision") == "KEEP"
    ]
    if any(not isinstance(row, dict) for row in selected_candidates):
        raise RoleRunnerError("BLOCKED_INPUT", "M2e selected candidate payload is invalid.")
    if [row.get("candidate_id") for row in selected_candidates] != selected_ids:
        raise RoleRunnerError("BLOCKED_INPUT", "M2e selected candidate payload does not match selected ids.")

    m2d_dir = Path(source_m2d).expanduser().resolve()
    m2d_summary = load_json(m2d_dir / "summary.json")
    source_m2b = m2d_summary.get("source_m2b_run")
    if not isinstance(source_m2b, str) or not source_m2b:
        raise RoleRunnerError("BLOCKED_INPUT", "M2d summary does not identify its M2b source run.")
    base = verify_m2b_for_language(Path(source_m2b))
    base_source_pack = load_json(base["m2a_run_dir"] / "source-pack.json")
    enrichment_source_pack = load_json(m2d_dir / "enrichment-source-pack.json")
    merged_source_pack = merge_source_packs(base_source_pack, enrichment_source_pack)

    previous_sessions = set(m2d["previous_sessions"])
    portfolio_session = summary.get("portfolio_arbiter_session_id")
    if isinstance(portfolio_session, str) and portfolio_session:
        if portfolio_session in previous_sessions:
            raise RoleRunnerError("BLOCKED_INPUT", "M2e portfolio arbiter reused an earlier session.")
        previous_sessions.add(portfolio_session)

    return {
        "m2e_run_dir": run_dir,
        "m2e_summary": summary,
        "m2d_run_dir": m2d_dir,
        "base_m2b_run_dir": Path(source_m2b).expanduser().resolve(),
        "core_artifact": base["artifact"],
        "core_artifact_sha256": base["artifact_sha256"],
        "selected_candidates": selected_candidates,
        "selected_candidate_ids": selected_ids,
        "merged_source_pack": merged_source_pack,
        "previous_sessions": previous_sessions,
    }


def validate_integrated_artifact(artifact: dict, core: dict, selected_candidates: list[dict], source_pack: dict) -> None:
    validate_author_artifact(artifact)
    if artifact.get("title") != core.get("title"):
        raise RoleRunnerError("INVALID_OUTPUT", "Integrator changed the accepted core title.")
    if artifact.get("execution_plan") != core.get("execution_plan"):
        raise RoleRunnerError("INVALID_OUTPUT", "Integrator changed the accepted core execution plan.")

    final_rows = artifact.get("narration", [])
    final_by_id = {row.get("fragment_id"): row for row in final_rows if isinstance(row, dict)}
    final_ids = [row.get("fragment_id") for row in final_rows if isinstance(row, dict)]
    core_rows = core.get("narration", [])
    core_ids = [row.get("fragment_id") for row in core_rows]
    for row in core_rows:
        if final_by_id.get(row.get("fragment_id")) != row:
            raise RoleRunnerError("INVALID_OUTPUT", f"Integrator changed core fragment {row.get('fragment_id')}.")
    if [fragment_id for fragment_id in final_ids if fragment_id in set(core_ids)] != core_ids:
        raise RoleRunnerError("INVALID_OUTPUT", "Integrator changed the order of core narration fragments.")

    if artifact.get("claims", [])[:len(core.get("claims", []))] != core.get("claims", []):
        raise RoleRunnerError("INVALID_OUTPUT", "Integrator changed existing core claims.")
    if artifact.get("coverage", [])[:len(core.get("coverage", []))] != core.get("coverage", []):
        raise RoleRunnerError("INVALID_OUTPUT", "Integrator changed existing core coverage.")
    if artifact.get("open_questions", [])[:len(core.get("open_questions", []))] != core.get("open_questions", []):
        raise RoleRunnerError("INVALID_OUTPUT", "Integrator changed existing core open questions.")

    selected_ids = [row["candidate_id"] for row in selected_candidates]
    enrichment = artifact.get("enrichment")
    if not isinstance(enrichment, dict) or enrichment.get("selected_candidate_ids") != selected_ids:
        raise RoleRunnerError("INVALID_OUTPUT", "Integrated artifact does not bind the exact selected candidate ids.")
    maps = enrichment.get("integration_map")
    if not isinstance(maps, list) or [row.get("candidate_id") for row in maps] != selected_ids:
        raise RoleRunnerError("INVALID_OUTPUT", "Integration map must cover every selected candidate exactly once in order.")

    new_fragment_ids = [fragment_id for fragment_id in final_ids if fragment_id not in set(core_ids)]
    mapped_fragment_ids: list[str] = []
    candidate_by_id = {row["candidate_id"]: row for row in selected_candidates}
    claim_rows = artifact.get("claims", [])
    claim_by_id = {row.get("claim_id"): row for row in claim_rows if isinstance(row, dict)}
    base_claim_ids = {row.get("claim_id") for row in core.get("claims", [])}
    source_ids = {row.get("id") for row in source_pack.get("sources", []) if isinstance(row, dict)}

    for mapping in maps:
        cid = mapping["candidate_id"]
        candidate = candidate_by_id[cid]
        frag_ids = mapping.get("fragment_ids", [])
        claim_ids = mapping.get("claim_ids", [])
        if not frag_ids or any(fragment_id not in new_fragment_ids for fragment_id in frag_ids):
            raise RoleRunnerError("INVALID_OUTPUT", f"Candidate {cid} mapping must reference only new enrichment fragments.")
        mapped_fragment_ids.extend(frag_ids)
        if not claim_ids or any(claim_id in base_claim_ids or claim_id not in claim_by_id for claim_id in claim_ids):
            raise RoleRunnerError("INVALID_OUTPUT", f"Candidate {cid} mapping must reference new claims.")
        supports = set()
        for claim_id in claim_ids:
            claim_support = claim_by_id[claim_id].get("support_ids", [])
            if any(source_id not in source_ids for source_id in claim_support):
                raise RoleRunnerError("INVALID_OUTPUT", f"Candidate {cid} claim uses an unknown source id.")
            supports.update(claim_support)
        if not set(candidate.get("source_support_ids", [])).issubset(supports):
            raise RoleRunnerError("INVALID_OUTPUT", f"Candidate {cid} claims do not preserve its selected source support.")

        indices = [final_ids.index(fragment_id) for fragment_id in frag_ids]
        if indices != sorted(indices):
            raise RoleRunnerError("INVALID_OUTPUT", f"Candidate {cid} enrichment fragments are out of order.")
        if candidate.get("insertion_point") == "end":
            last_core = max(final_ids.index(fragment_id) for fragment_id in core_ids)
            if min(indices) <= last_core:
                raise RoleRunnerError("INVALID_OUTPUT", f"End candidate {cid} was not inserted after the core.")
        else:
            anchor = candidate.get("after_fragment_id")
            if anchor not in core_ids:
                raise RoleRunnerError("INVALID_OUTPUT", f"Candidate {cid} has invalid insertion anchor.")
            anchor_pos = final_ids.index(anchor)
            next_core = None
            core_index = core_ids.index(anchor)
            if core_index + 1 < len(core_ids):
                next_core = final_ids.index(core_ids[core_index + 1])
            if min(indices) <= anchor_pos or (next_core is not None and max(indices) >= next_core):
                raise RoleRunnerError("INVALID_OUTPUT", f"Candidate {cid} was inserted outside its declared slot.")

    if len(mapped_fragment_ids) != len(set(mapped_fragment_ids)) or set(mapped_fragment_ids) != set(new_fragment_ids):
        raise RoleRunnerError("INVALID_OUTPUT", "Every new narration fragment must belong to exactly one selected candidate.")

    plan = enrichment.get("verification_plan")
    if not isinstance(plan, dict) or plan.get("schema_version") != 1 or not isinstance(plan.get("checks"), list):
        raise RoleRunnerError("INVALID_OUTPUT", "Integrated artifact needs enrichment verification_plan schema version 1.")
    checks = plan["checks"]
    check_ids = [row.get("check_id") for row in checks if isinstance(row, dict)]
    if len(check_ids) != len(checks) or any(not isinstance(value, str) or not value for value in check_ids) or len(check_ids) != len(set(check_ids)):
        raise RoleRunnerError("INVALID_OUTPUT", "Enrichment verification check ids must be unique and non-empty.")
    for candidate in selected_candidates:
        cid = candidate["candidate_id"]
        candidate_checks = [row for row in checks if row.get("candidate_id") == cid]
        if candidate.get("verification_kind") == "documentation_only":
            continue
        if not candidate_checks:
            raise RoleRunnerError("INVALID_OUTPUT", f"Executable candidate {cid} has no structured verification check.")
        expected_mode = "python_cli" if candidate.get("verification_kind") == "python_cli" else "interactive_python"
        if not any(row.get("mode") == expected_mode for row in candidate_checks):
            raise RoleRunnerError("INVALID_OUTPUT", f"Candidate {cid} has no verification check in its declared execution mode.")
        allowed_fragments = set(next(row["fragment_ids"] for row in maps if row["candidate_id"] == cid))
        for row in candidate_checks:
            if not set(row.get("fragment_ids", [])).issubset(allowed_fragments):
                raise RoleRunnerError("INVALID_OUTPUT", f"Candidate {cid} verification references another candidate's fragment.")


@task(name="m2f-enrichment-integrator", retries=0, cache_policy=NO_CACHE, persist_result=False)
def integrator_task(config: dict, verified: dict, run_dir: str) -> dict:
    runner = CodexRoleRunner(model=config["model"], reasoning_effort=config["reasoning_effort"])
    runner.preflight()
    payload = {
        "role_instructions": INTEGRATOR_PROMPT.read_text(encoding="utf-8"),
        "brief": config["brief"],
        "audience_profile": audience_for(config),
        "language": config["language"],
        "target_runtime": config["target_runtime"],
        "execution_runtime": config["execution_runtime"],
        "core_artifact_sha256": verified["core_artifact_sha256"],
        "core_artifact": verified["core_artifact"],
        "selected_candidates": verified["selected_candidates"],
        "merged_source_pack": verified["merged_source_pack"],
        "constraints": [
            "Preserve every core narration fragment byte-for-byte and in order.",
            "Preserve title, core execution_plan, existing claims, coverage and open_questions.",
            "Add only selected enrichment; do not resurrect dropped candidates or invent new enrichment.",
            "Use new stable fragment_id and claim_id values for enrichment.",
            "Use `python -c` in canonical narration when describing the generic CLI interface; exact runtime naming belongs to the executor.",
            "For enrichment verification store Python code only, never a shell launcher or shell quoting.",
            "Do not claim that verification was executed.",
        ],
    }
    result = runner.run_json(
        role="enrichment_integrator",
        payload=payload,
        schema=integrated_artifact_schema(),
        report_dir=Path(run_dir) / "integrator",
    )
    validate_integrated_artifact(
        result["output"], verified["core_artifact"],
        verified["selected_candidates"], verified["merged_source_pack"],
    )
    return result


@task(name="m2f-execute-integrated-artifact", retries=0, cache_policy=NO_CACHE, persist_result=False)
def execute_integrated_task(artifact: dict, expected_runtime: str) -> dict:
    try:
        core = run_execution_plan(artifact["execution_plan"], expected_runtime)
        enrichment = run_enrichment_plan(artifact["enrichment"]["verification_plan"], expected_runtime)
    except ExecutionEvidenceError as exc:
        raise RoleRunnerError(exc.status, str(exc)) from exc
    return {"core": core, "enrichment": enrichment}


@task(name="m2f-independent-content-judge", retries=0, cache_policy=NO_CACHE, persist_result=False)
def content_judge_task(config: dict, source_pack: dict, artifact: dict, artifact_sha256: str, evidence: dict, run_dir: str) -> dict:
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
        "execution_evidence": evidence,
        "constraints": [
            "You are a fresh independent content judge. You receive no prior judge verdicts or integration history.",
            "The artifact contains immutable core narration plus selected optional enrichment; judge the resulting whole lecture.",
            "For E1/E2 use both core and enrichment execution evidence and compare actual stdout/stderr with every concrete narrated example.",
            "A python_cli check is actual `-c` execution under the exact runtime, not simulated REPL evidence.",
            "Apply L4 to the whole narration, including enrichment.",
            "Do not treat optional enrichment as mandatory coverage, but reject enrichment that damages coherence, correctness or proportionality.",
            "Use evidence-role sources for factual/version-dependent claims.",
            "Do not rewrite the artifact. Return only the evaluation report.",
        ],
    }
    result = runner.run_json(
        role="judge_content",
        payload=payload,
        schema=judge_schema(artifact_sha256),
        report_dir=Path(run_dir) / "judge_content",
    )
    validate_judge_report(result["output"])
    return result


@flow(name="video-production-m2f-enriched-gate", retries=0, persist_result=False)
def m2f_enriched_gate(m2e_run_dir: str) -> dict:
    logger = get_run_logger()
    input_dir = Path(m2e_run_dir).expanduser().resolve()
    config = load_json(M2A_CONFIG)
    run_dir = ROOT / "runs" / "m2f-enriched" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "stage": "M2f",
        "lesson_id": config["lesson_id"],
        "status": "ERROR",
        "outcome": "ERROR",
        "source_m2e_run": str(input_dir),
        "reports": str(run_dir),
        "rubric_version": RUBRIC_VERSION,
        "portfolio_rubric_version": PORTFOLIO_RUBRIC_VERSION,
        "audience_profile": config["audience_profile"],
        "gate_a_reached": False,
        "gate_a_approved": False,
        "gate_a_status": "NOT_REACHED",
        "audio_called": False,
        "render_called": False,
        "production_ready": False,
    }
    try:
        verified = verify_m2e_run(input_dir)
        merged_pack = verified["merged_source_pack"]
        (run_dir / "source-pack.json").write_text(
            json.dumps(merged_pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        integrated = integrator_task(config, verified, str(run_dir))
        integrator_session = integrated["receipt"]["session_id"]
        if integrator_session in verified["previous_sessions"]:
            raise RoleRunnerError("SESSION_REUSED", "Enrichment integrator reused an earlier Codex session.")
        artifact = integrated["output"]
        artifact_sha256 = canonical_hash(artifact)
        (run_dir / "artifact.json").write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        evidence = execute_integrated_task(artifact, config["execution_runtime"])
        core_evidence = evidence["core"]
        enrichment_evidence = evidence["enrichment"]
        (run_dir / "core-execution-evidence.json").write_text(
            json.dumps(core_evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (run_dir / "enrichment-execution-evidence.json").write_text(
            json.dumps(enrichment_evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if core_evidence.get("all_examples_passed") is not True or enrichment_evidence.get("all_checks_passed") is not True:
            summary.update(
                status="COMPLETED", outcome="EXECUTION_MISMATCH",
                base_artifact_sha256=verified["core_artifact_sha256"],
                artifact_sha256=artifact_sha256,
                artifact_changed=True,
                selected_candidate_ids=verified["selected_candidate_ids"],
                integrator_session_id=integrator_session,
                core_examples_passed=core_evidence.get("all_examples_passed"),
                enrichment_checks_passed=enrichment_evidence.get("all_checks_passed"),
                content_judge_called=False,
                language_judge_called=False,
                next_action="REVISION_REQUIRED",
            )
            return summary

        prior_sessions = set(verified["previous_sessions"])
        prior_sessions.add(integrator_session)
        content = content_judge_task(
            config, merged_pack, artifact, artifact_sha256, evidence, str(run_dir)
        )
        content_session = content["receipt"]["session_id"]
        if content_session in prior_sessions:
            raise RoleRunnerError("SESSION_REUSED", "M2f content judge reused an earlier Codex session.")
        content_report = content["output"]
        (run_dir / "judge-content-report.json").write_text(
            json.dumps(content_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if content_report["verdict"] != "PASS":
            summary.update(
                status="COMPLETED", outcome="REVISION_REQUIRED",
                stop_reason=f"CONTENT_JUDGE_{content_report['verdict']}",
                base_artifact_sha256=verified["core_artifact_sha256"],
                artifact_sha256=artifact_sha256,
                artifact_changed=True,
                selected_candidate_ids=verified["selected_candidate_ids"],
                integrator_session_id=integrator_session,
                core_examples_passed=True,
                enrichment_checks_passed=True,
                content_judge_called=True,
                content_judge_session_id=content_session,
                content_judge_verdict=content_report["verdict"],
                content_findings_count=len(content_report["findings"]),
                language_judge_called=False,
                next_action="REVISION_REQUIRED",
            )
            return summary

        prior_sessions.add(content_session)
        language = language_task(config, artifact, artifact_sha256, str(run_dir))
        language_session = language["receipt"]["session_id"]
        if not fresh_session(language_session, prior_sessions):
            raise RoleRunnerError("SESSION_REUSED", "M2f language judge reused an earlier Codex session.")
        language_report = language["output"]
        (run_dir / "judge-language-report.json").write_text(
            json.dumps(language_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        language_pass = language_report["verdict"] == "PASS"
        gate_reached = language_pass
        gate_status = "PENDING_HUMAN_APPROVAL" if gate_reached else "NOT_REACHED"

        if gate_reached:
            package = {
                "schema_version": 2,
                "gate": "A",
                "lesson_id": config["lesson_id"],
                "artifact_sha256": artifact_sha256,
                "base_artifact_sha256": verified["core_artifact_sha256"],
                "source_pack_sha256": merged_pack["source_pack_sha256"],
                "rubric_version": RUBRIC_VERSION,
                "portfolio_rubric_version": PORTFOLIO_RUBRIC_VERSION,
                "audience_profile": config["audience_profile"],
                "selected_candidate_ids": verified["selected_candidate_ids"],
                "core_execution_evidence_sha256": core_evidence["execution_evidence_sha256"],
                "enrichment_execution_evidence_sha256": enrichment_evidence["enrichment_execution_evidence_sha256"],
                "content_judge": {
                    "status": "PASS", "session_id": content_session,
                    "report": str(run_dir / "judge-content-report.json"),
                },
                "language_judge": {
                    "status": "PASS", "session_id": language_session,
                    "report": str(run_dir / "judge-language-report.json"),
                },
                "human_approval": gate_status,
            }
            (run_dir / "gate-a-package.json").write_text(
                json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

        summary.update(
            status="COMPLETED",
            outcome="WAITING_HUMAN" if gate_reached else "REVISION_REQUIRED",
            stop_reason=None if gate_reached else f"LANGUAGE_JUDGE_{language_report['verdict']}",
            base_artifact_sha256=verified["core_artifact_sha256"],
            artifact_sha256=artifact_sha256,
            artifact_changed=artifact_sha256 != verified["core_artifact_sha256"],
            source_pack_sha256=merged_pack["source_pack_sha256"],
            selected_candidate_ids=verified["selected_candidate_ids"],
            selected_count=len(verified["selected_candidate_ids"]),
            integrator_session_id=integrator_session,
            core_execution_evidence_sha256=core_evidence["execution_evidence_sha256"],
            enrichment_execution_evidence_sha256=enrichment_evidence["enrichment_execution_evidence_sha256"],
            core_examples_passed=True,
            enrichment_checks_passed=True,
            content_judge_called=True,
            content_judge_session_id=content_session,
            content_judge_verdict="PASS",
            content_findings_count=len(content_report["findings"]),
            language_judge_called=True,
            language_judge_session_id=language_session,
            language_judge_verdict=language_report["verdict"],
            language_findings_count=len(language_report["findings"]),
            gate_a_reached=gate_reached,
            gate_a_status=gate_status,
            next_action="HUMAN_GATE_A" if gate_reached else "REVISION_REQUIRED",
        )
        logger.info(
            "M2f completed. integrated=%s content=%s language=%s gate=%s",
            artifact_sha256, content_report["verdict"], language_report["verdict"], gate_status,
        )
        logger.info("Artifacts: %s", run_dir)
        return summary
    except RoleRunnerError as exc:
        summary["status"] = exc.status
        summary["outcome"] = exc.status
        summary["error"] = str(exc)
        logger.error("%s: %s", exc.status, exc)
        raise
    finally:
        (run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m2e_run_dir", help="Path to a completed M2e portfolio run")
    args = parser.parse_args()
    print(json.dumps(m2f_enriched_gate(args.m2e_run_dir), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
