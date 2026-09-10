"""Build a human-readable Gate A packet from a completed M2c run.

No LLM, audio, render or approval action is performed. The script validates the
artifact and review chain, then writes and prints one Markdown review packet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

RUBRIC_VERSION = "0.2"


class GateAReviewError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateAReviewError(f"Cannot read valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise GateAReviewError(f"JSON root must be an object: {path}")
    return value


def canonical_hash(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GateAReviewError(message)


def _criteria_all_pass(report: dict[str, Any]) -> bool:
    rows = report.get("criteria")
    return bool(rows) and isinstance(rows, list) and all(
        isinstance(row, dict) and row.get("status") == "PASS" for row in rows
    )


def verify_chain(m2c_dir: Path) -> dict[str, Any]:
    m2c_dir = m2c_dir.expanduser().resolve()
    m2c = load_json(m2c_dir / "summary.json")
    _require(m2c.get("stage") == "M2c", "Input is not an M2c run.")
    _require(m2c.get("status") == "COMPLETED", "M2c is not completed.")
    _require(m2c.get("rubric_version") == RUBRIC_VERSION, "Gate A run uses an obsolete rubric version.")
    audience_profile = m2c.get("audience_profile")
    _require(isinstance(audience_profile, str) and audience_profile, "Gate A run has no audience profile.")
    _require(m2c.get("gate_a_reached") is True, "Gate A was not reached.")
    _require(m2c.get("gate_a_approved") is False, "Gate A is already marked approved.")
    _require(
        m2c.get("gate_a_status") == "PENDING_HUMAN_APPROVAL",
        "Gate A is not pending human approval.",
    )
    expected_sha = m2c.get("artifact_sha256")
    _require(isinstance(expected_sha, str) and len(expected_sha) == 64, "Missing artifact SHA.")

    package = load_json(m2c_dir / "gate-a-package.json")
    _require(package.get("gate") == "A", "Invalid Gate A package.")
    _require(package.get("artifact_sha256") == expected_sha, "Gate package artifact hash mismatch.")
    _require(package.get("rubric_version") == RUBRIC_VERSION, "Gate package rubric version mismatch.")
    _require(package.get("audience_profile") == audience_profile, "Gate package audience profile mismatch.")
    _require(
        package.get("human_approval") == "PENDING_HUMAN_APPROVAL",
        "Gate package is not pending human approval.",
    )

    source_m2a = m2c.get("source_m2a_run")
    source_m2b = m2c.get("source_m2b_run")
    _require(isinstance(source_m2a, str) and source_m2a, "M2c does not identify M2a source run.")
    _require(isinstance(source_m2b, str) and source_m2b, "M2c does not identify M2b source run.")
    m2a_dir = Path(source_m2a).expanduser().resolve()
    m2b_dir = Path(source_m2b).expanduser().resolve()

    m2a = load_json(m2a_dir / "summary.json")
    artifact = load_json(m2a_dir / "artifact.json")
    _require(m2a.get("stage") == "M2a" and m2a.get("status") == "COMPLETED", "Invalid M2a source run.")
    _require(m2a.get("rubric_version") == RUBRIC_VERSION, "M2a source run uses an obsolete rubric version.")
    _require(m2a.get("audience_profile") == audience_profile, "M2a audience profile mismatch.")
    _require(canonical_hash(artifact) == expected_sha, "Artifact bytes/content no longer match Gate A hash.")
    _require(m2a.get("artifact_sha256") == expected_sha, "M2a summary artifact hash mismatch.")

    m2b = load_json(m2b_dir / "summary.json")
    content_report = load_json(m2b_dir / "judge-report-with-execution.json")
    evidence = load_json(m2b_dir / "execution-evidence.json")
    _require(m2b.get("stage") == "M2b" and m2b.get("status") == "COMPLETED", "Invalid M2b source run.")
    _require(m2b.get("rubric_version") == RUBRIC_VERSION, "M2b source run uses an obsolete rubric version.")
    _require(m2b.get("audience_profile") == audience_profile, "M2b audience profile mismatch.")
    _require(m2b.get("artifact_sha256") == expected_sha, "M2b artifact hash mismatch.")
    _require(m2b.get("artifact_unchanged") is True, "M2b did not preserve the artifact.")
    _require(m2b.get("content_judge_pass") is True, "Content judge is not passing.")
    _require(content_report.get("artifact_sha256") == expected_sha, "Content report evaluates another artifact.")
    _require(content_report.get("rubric_version") == RUBRIC_VERSION, "Content report uses an obsolete rubric version.")
    _require(content_report.get("verdict") == "PASS", "Content report verdict is not PASS.")
    _require(_criteria_all_pass(content_report), "Not every content criterion is PASS.")

    evidence_hash = evidence.get("execution_evidence_sha256")
    unhashed_evidence = {key: value for key, value in evidence.items() if key != "execution_evidence_sha256"}
    _require(
        isinstance(evidence_hash, str) and canonical_hash(unhashed_evidence) == evidence_hash,
        "Execution evidence hash is invalid.",
    )
    _require(m2b.get("execution_evidence_sha256") == evidence_hash, "M2b evidence hash mismatch.")
    _require(evidence.get("all_examples_passed") is True, "Execution evidence contains failures.")

    language_report = load_json(m2c_dir / "judge-language-report.json")
    _require(language_report.get("artifact_sha256") == expected_sha, "Language report evaluates another artifact.")
    _require(language_report.get("rubric_version") == RUBRIC_VERSION, "Language report uses an obsolete rubric version.")
    _require(language_report.get("verdict") == "PASS", "Language report verdict is not PASS.")
    _require(_criteria_all_pass(language_report), "Not every language criterion is PASS.")
    language_ids = {row.get("criterion_id") for row in language_report.get("criteria", [])}
    _require("L4" in language_ids, "Language report did not evaluate audience-level criterion L4.")

    return {
        "m2c_dir": m2c_dir,
        "m2a_dir": m2a_dir,
        "m2b_dir": m2b_dir,
        "m2c_summary": m2c,
        "artifact": artifact,
        "content_report": content_report,
        "language_report": language_report,
        "execution_evidence": evidence,
        "artifact_sha256": expected_sha,
        "execution_evidence_sha256": evidence_hash,
        "audience_profile": audience_profile,
    }


def _criteria_table(report: dict[str, Any]) -> list[str]:
    lines = ["| Kryterium | Status | Uzasadnienie |", "| --- | --- | --- |"]
    for row in report["criteria"]:
        reason = str(row.get("reason", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row.get('criterion_id')} | {row.get('status')} | {reason} |")
    return lines


def _findings_section(report: dict[str, Any]) -> list[str]:
    findings = report.get("findings", [])
    if not findings:
        return ["Brak uwag."]
    lines: list[str] = []
    for index, item in enumerate(findings, start=1):
        lines.extend([
            f"{index}. **{item.get('criterion_id')} / {item.get('severity')}** — {item.get('problem')}",
            f"   - Miejsce: {item.get('quote_or_anchor')}",
            f"   - Dowód: {item.get('evidence')}",
            f"   - Proponowana poprawka: {item.get('proposed_fix')}",
        ])
    return lines


def build_markdown(verified: dict[str, Any]) -> str:
    artifact = verified["artifact"]
    content = verified["content_report"]
    language = verified["language_report"]
    evidence = verified["execution_evidence"]
    m2c = verified["m2c_summary"]

    runtime = evidence.get("runtime", {})
    lines = [
        "# Gate A — przegląd treści przez człowieka",
        "",
        f"- Lekcja: `{m2c.get('lesson_id')}`",
        f"- Profil odbiorcy: `{verified['audience_profile']}`",
        f"- Rubric: `{RUBRIC_VERSION}`",
        f"- Artefakt SHA-256: `{verified['artifact_sha256']}`",
        "- Stan: **PENDING_HUMAN_APPROVAL**",
        "- Ten raport **nie zatwierdza** Gate A.",
        "",
        "## Dowód wykonania przykładów",
        "",
        f"- Runtime: `{runtime.get('implementation')} {runtime.get('version')}`",
        f"- Wszystkie przykłady: `{'PASS' if evidence.get('all_examples_passed') else 'FAIL'}`",
        f"- Execution evidence SHA-256: `{verified['execution_evidence_sha256']}`",
        "",
        "## Narracja kanoniczna",
        "",
        f"### {artifact.get('title', '')}",
        "",
    ]
    for fragment in artifact.get("narration", []):
        lines.extend([
            f"**{fragment.get('fragment_id', '')}**",
            "",
            str(fragment.get("text", "")),
            "",
        ])

    lines.extend([
        "## Niezależny sędzia merytoryczny",
        "",
        f"Werdykt: **{content.get('verdict')}**",
        "",
        *_criteria_table(content),
        "",
        "### Uwagi merytoryczne",
        "",
        *_findings_section(content),
        "",
        "## Niezależny sędzia językowy",
        "",
        f"Werdykt: **{language.get('verdict')}**",
        "",
        *_criteria_table(language),
        "",
        "### Uwagi językowe",
        "",
        *_findings_section(language),
        "",
        "## Decyzja człowieka",
        "",
        "**NIEZAREJESTROWANA.**",
        "",
        "Przed przejściem do projektowania scen człowiek musi jawnie zaakceptować albo odrzucić dokładnie powyższy artefakt SHA-256.",
        "",
    ])
    return "\n".join(lines)


def make_review(m2c_dir: Path) -> tuple[Path, str, dict[str, Any]]:
    verified = verify_chain(m2c_dir)
    markdown = build_markdown(verified)
    output = verified["m2c_dir"] / "gate-a-review.md"
    output.write_text(markdown, encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "gate": "A",
        "status": "READY_FOR_HUMAN_REVIEW",
        "approval_recorded": False,
        "rubric_version": RUBRIC_VERSION,
        "audience_profile": verified["audience_profile"],
        "artifact_sha256": verified["artifact_sha256"],
        "execution_evidence_sha256": verified["execution_evidence_sha256"],
        "review_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "review_file": str(output),
        "llm_called": False,
        "audio_called": False,
        "render_called": False,
    }
    receipt_path = verified["m2c_dir"] / "gate-a-review-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output, markdown, receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m2c_run_dir", help="Path to the completed M2c run awaiting Gate A")
    args = parser.parse_args()
    try:
        output, markdown, receipt = make_review(Path(args.m2c_run_dir))
    except GateAReviewError as exc:
        print(json.dumps({"gate_a_review": "ERROR", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(markdown)
    print("\n---")
    print(json.dumps({
        "gate_a_review": "READY_FOR_HUMAN_REVIEW",
        "rubric_version": receipt["rubric_version"],
        "audience_profile": receipt["audience_profile"],
        "artifact_sha256": receipt["artifact_sha256"],
        "approval_recorded": False,
        "review_file": str(output),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
