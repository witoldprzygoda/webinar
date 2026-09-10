"""Build a human-readable Gate A packet from a completed M2f enriched run.

No LLM, audio, render or approval action is performed. The script verifies the
new integrated artifact, both execution evidence streams and both independent
judge reports before presenting the narration to the human reviewer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

QUALITY_RUBRIC_VERSION = "0.2"
PORTFOLIO_RUBRIC_VERSION = "0.2"


class GateAEnrichedReviewError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateAEnrichedReviewError(f"Cannot read valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise GateAEnrichedReviewError(f"JSON root must be an object: {path}")
    return value


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GateAEnrichedReviewError(message)


def _criteria_all_pass(report: dict[str, Any]) -> bool:
    rows = report.get("criteria")
    return bool(rows) and isinstance(rows, list) and all(
        isinstance(row, dict) and row.get("status") == "PASS" for row in rows
    )


def _verify_self_hash(value: dict[str, Any], key: str, message: str) -> str:
    saved = value.get(key)
    unhashed = {name: item for name, item in value.items() if name != key}
    _require(isinstance(saved, str) and canonical_hash(unhashed) == saved, message)
    return saved


def verify_enriched_chain(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    summary = load_json(run_dir / "summary.json")
    _require(summary.get("stage") == "M2f", "Input is not an M2f enriched run.")
    _require(summary.get("status") == "COMPLETED", "M2f is not completed.")
    _require(summary.get("outcome") == "WAITING_HUMAN", "M2f is not waiting for human review.")
    _require(summary.get("rubric_version") == QUALITY_RUBRIC_VERSION, "M2f uses an obsolete quality rubric.")
    _require(summary.get("portfolio_rubric_version") == PORTFOLIO_RUBRIC_VERSION, "M2f uses an obsolete portfolio rubric.")
    _require(summary.get("gate_a_reached") is True, "Gate A was not reached.")
    _require(summary.get("gate_a_approved") is False, "Gate A is already marked approved.")
    _require(summary.get("gate_a_status") == "PENDING_HUMAN_APPROVAL", "Gate A is not pending human approval.")

    artifact = load_json(run_dir / "artifact.json")
    artifact_sha = canonical_hash(artifact)
    _require(summary.get("artifact_sha256") == artifact_sha, "Integrated artifact hash mismatch.")
    base_sha = summary.get("base_artifact_sha256")
    _require(isinstance(base_sha, str) and len(base_sha) == 64 and base_sha != artifact_sha, "Missing distinct base artifact hash.")

    source_pack = load_json(run_dir / "source-pack.json")
    source_pack_sha = _verify_self_hash(source_pack, "source_pack_sha256", "Merged source-pack hash is invalid.")
    _require(summary.get("source_pack_sha256") == source_pack_sha, "M2f summary source-pack hash mismatch.")

    core_evidence = load_json(run_dir / "core-execution-evidence.json")
    core_sha = _verify_self_hash(core_evidence, "execution_evidence_sha256", "Core execution evidence hash is invalid.")
    _require(core_evidence.get("all_examples_passed") is True, "Core execution evidence contains failures.")
    _require(summary.get("core_execution_evidence_sha256") == core_sha, "Core evidence hash mismatch.")

    enrichment_evidence = load_json(run_dir / "enrichment-execution-evidence.json")
    enrichment_sha = _verify_self_hash(
        enrichment_evidence,
        "enrichment_execution_evidence_sha256",
        "Enrichment execution evidence hash is invalid.",
    )
    _require(enrichment_evidence.get("all_checks_passed") is True, "Enrichment execution evidence contains failures.")
    _require(summary.get("enrichment_execution_evidence_sha256") == enrichment_sha, "Enrichment evidence hash mismatch.")

    content_report = load_json(run_dir / "judge-content-report.json")
    language_report = load_json(run_dir / "judge-language-report.json")
    for label, report in (("Content", content_report), ("Language", language_report)):
        _require(report.get("artifact_sha256") == artifact_sha, f"{label} report evaluates another artifact.")
        _require(report.get("rubric_version") == QUALITY_RUBRIC_VERSION, f"{label} report uses an obsolete rubric.")
        _require(report.get("verdict") == "PASS", f"{label} report verdict is not PASS.")
        _require(_criteria_all_pass(report), f"Not every {label.lower()} criterion is PASS.")
    language_ids = {row.get("criterion_id") for row in language_report.get("criteria", [])}
    _require("L4" in language_ids, "Language report did not evaluate audience calibration L4.")

    package = load_json(run_dir / "gate-a-package.json")
    _require(package.get("gate") == "A", "Invalid Gate A package.")
    _require(package.get("artifact_sha256") == artifact_sha, "Gate package artifact hash mismatch.")
    _require(package.get("base_artifact_sha256") == base_sha, "Gate package base artifact hash mismatch.")
    _require(package.get("source_pack_sha256") == source_pack_sha, "Gate package source-pack hash mismatch.")
    _require(package.get("human_approval") == "PENDING_HUMAN_APPROVAL", "Gate package is not pending human approval.")
    _require(package.get("selected_candidate_ids") == summary.get("selected_candidate_ids"), "Gate package selected candidates mismatch.")
    _require(package.get("core_execution_evidence_sha256") == core_sha, "Gate package core evidence mismatch.")
    _require(package.get("enrichment_execution_evidence_sha256") == enrichment_sha, "Gate package enrichment evidence mismatch.")

    source_m2e = summary.get("source_m2e_run")
    _require(isinstance(source_m2e, str) and source_m2e, "M2f does not identify its M2e source run.")
    m2e_dir = Path(source_m2e).expanduser().resolve()
    m2e_summary = load_json(m2e_dir / "summary.json")
    portfolio = load_json(m2e_dir / "portfolio-selection.json")
    _require(m2e_summary.get("stage") == "M2e" and m2e_summary.get("status") == "COMPLETED", "Invalid M2e source run.")
    _require(m2e_summary.get("artifact_sha256") == base_sha, "M2e base artifact hash mismatch.")
    _require(portfolio.get("selected_candidate_ids") == summary.get("selected_candidate_ids"), "M2e portfolio differs from integrated selection.")

    return {
        "run_dir": run_dir,
        "summary": summary,
        "artifact": artifact,
        "artifact_sha256": artifact_sha,
        "base_artifact_sha256": base_sha,
        "source_pack_sha256": source_pack_sha,
        "core_evidence": core_evidence,
        "core_evidence_sha256": core_sha,
        "enrichment_evidence": enrichment_evidence,
        "enrichment_evidence_sha256": enrichment_sha,
        "content_report": content_report,
        "language_report": language_report,
        "selected_candidate_ids": summary.get("selected_candidate_ids", []),
    }


def _criteria_table(report: dict[str, Any]) -> list[str]:
    lines = ["| Kryterium | Status | Uzasadnienie |", "| --- | --- | --- |"]
    for row in report["criteria"]:
        reason = str(row.get("reason", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row.get('criterion_id')} | {row.get('status')} | {reason} |")
    return lines


def _findings(report: dict[str, Any]) -> list[str]:
    values = report.get("findings", [])
    if not values:
        return ["Brak uwag."]
    lines: list[str] = []
    for index, item in enumerate(values, 1):
        lines.append(f"{index}. **{item.get('criterion_id')} / {item.get('severity')}** — {item.get('problem')}")
    return lines


def build_enriched_markdown(verified: dict[str, Any]) -> str:
    artifact = verified["artifact"]
    summary = verified["summary"]
    enrichment = artifact.get("enrichment", {})
    enrichment_fragments = {
        fragment_id: mapping.get("candidate_id")
        for mapping in enrichment.get("integration_map", [])
        for fragment_id in mapping.get("fragment_ids", [])
    }
    core_runtime = verified["core_evidence"].get("runtime", {})
    lines = [
        "# Gate A — wzbogacona narracja do przeglądu przez człowieka",
        "",
        f"- Lekcja: `{summary.get('lesson_id')}`",
        f"- Profil odbiorcy: `{summary.get('audience_profile')}`",
        f"- Quality rubric: `{QUALITY_RUBRIC_VERSION}`",
        f"- Portfolio rubric: `{PORTFOLIO_RUBRIC_VERSION}`",
        f"- Bazowy artefakt SHA-256: `{verified['base_artifact_sha256']}`",
        f"- Nowy artefakt SHA-256: `{verified['artifact_sha256']}`",
        f"- Wybrane enrichmenty: `{', '.join(verified['selected_candidate_ids'])}`",
        "- Stan: **PENDING_HUMAN_APPROVAL**",
        "- Ten raport **nie zatwierdza** Gate A.",
        "",
        "## Dowody wykonania",
        "",
        f"- Rdzeń: `{core_runtime.get('implementation')} {core_runtime.get('version')}` — `PASS`",
        f"- Enrichment checks: `{len(verified['enrichment_evidence'].get('results', []))}` — `PASS`",
        f"- Core evidence SHA-256: `{verified['core_evidence_sha256']}`",
        f"- Enrichment evidence SHA-256: `{verified['enrichment_evidence_sha256']}`",
        "",
        "### Wykonane sprawdzenia enrichmentu",
        "",
    ]
    for row in verified["enrichment_evidence"].get("results", []):
        stdout = str(row.get("actual_stdout", "")).strip().replace("\n", " ")
        lines.append(
            f"- `{row.get('candidate_id')}` / `{row.get('mode')}`: `{row.get('code')}` -> "
            f"`{'PASS' if row.get('pass') else 'FAIL'}`; stdout: `{stdout}`"
        )

    lines.extend(["", "## Narracja kanoniczna", "", f"### {artifact.get('title', '')}", ""])
    for fragment in artifact.get("narration", []):
        fragment_id = fragment.get("fragment_id", "")
        candidate_id = enrichment_fragments.get(fragment_id)
        marker = f" — **ENRICHMENT {candidate_id}**" if candidate_id else ""
        lines.extend([
            f"**{fragment_id}**{marker}",
            "",
            str(fragment.get("text", "")),
            "",
        ])

    lines.extend([
        "## Niezależny sędzia merytoryczny",
        "",
        f"Werdykt: **{verified['content_report'].get('verdict')}**",
        "",
        *_criteria_table(verified["content_report"]),
        "",
        "### Uwagi merytoryczne",
        "",
        *_findings(verified["content_report"]),
        "",
        "## Niezależny sędzia językowy",
        "",
        f"Werdykt: **{verified['language_report'].get('verdict')}**",
        "",
        *_criteria_table(verified["language_report"]),
        "",
        "### Uwagi językowe",
        "",
        *_findings(verified["language_report"]),
        "",
        "## Decyzja człowieka",
        "",
        "**NIEZAREJESTROWANA.**",
        "",
        "Przejście do projektowania scen wymaga jawnej akceptacji dokładnie powyższego nowego artefaktu SHA-256.",
        "",
    ])
    return "\n".join(lines)


def make_enriched_review(run_dir: Path) -> tuple[Path, str, dict[str, Any]]:
    verified = verify_enriched_chain(run_dir)
    markdown = build_enriched_markdown(verified)
    output = verified["run_dir"] / "gate-a-review.md"
    output.write_text(markdown, encoding="utf-8")
    receipt = {
        "schema_version": 2,
        "gate": "A",
        "status": "READY_FOR_HUMAN_REVIEW",
        "approval_recorded": False,
        "rubric_version": QUALITY_RUBRIC_VERSION,
        "portfolio_rubric_version": PORTFOLIO_RUBRIC_VERSION,
        "audience_profile": verified["summary"].get("audience_profile"),
        "base_artifact_sha256": verified["base_artifact_sha256"],
        "artifact_sha256": verified["artifact_sha256"],
        "review_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "review_file": str(output),
        "llm_called": False,
        "audio_called": False,
        "render_called": False,
    }
    (verified["run_dir"] / "gate-a-review-receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return output, markdown, receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m2f_run_dir", help="Path to completed M2f run awaiting enriched Gate A")
    args = parser.parse_args()
    try:
        output, markdown, receipt = make_enriched_review(Path(args.m2f_run_dir))
    except GateAEnrichedReviewError as exc:
        print(json.dumps({"gate_a_review": "ERROR", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(markdown)
    print("\n---")
    print(json.dumps({
        "gate_a_review": "READY_FOR_HUMAN_REVIEW",
        "artifact_sha256": receipt["artifact_sha256"],
        "base_artifact_sha256": receipt["base_artifact_sha256"],
        "approval_recorded": False,
        "review_file": str(output),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
