from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.gate_a_review import GateAReviewError, RUBRIC_VERSION, canonical_hash, make_review, verify_chain


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def fixture(root: Path) -> Path:
    m2a = root / "m2a"
    m2b = root / "m2b"
    m2c = root / "m2c"
    audience = "cs_year3"
    artifact = {
        "title": "T",
        "narration": [
            {"fragment_id": "f1", "text": "Pierwszy fragment."},
            {"fragment_id": "f2", "text": "Drugi fragment."},
        ],
        "claims": [], "coverage": [], "open_questions": [],
    }
    artifact_sha = canonical_hash(artifact)
    write_json(m2a / "artifact.json", artifact)
    write_json(m2a / "summary.json", {
        "stage": "M2a", "status": "COMPLETED", "artifact_sha256": artifact_sha,
        "rubric_version": RUBRIC_VERSION, "audience_profile": audience,
    })
    content_report = {
        "artifact_sha256": artifact_sha,
        "rubric_version": RUBRIC_VERSION,
        "verdict": "PASS",
        "criteria": [
            {"criterion_id": key, "status": "PASS", "reason": "ok"}
            for key in ("F1", "F2", "E1", "E2", "L1", "L2", "L3", "L4", "D1", "P1")
        ],
        "findings": [],
    }
    evidence = {
        "schema_version": 1,
        "runtime": {"implementation": "CPython", "version": "3.14.7"},
        "all_examples_passed": True,
    }
    evidence["execution_evidence_sha256"] = canonical_hash(evidence)
    write_json(m2b / "judge-report-with-execution.json", content_report)
    write_json(m2b / "execution-evidence.json", evidence)
    write_json(m2b / "summary.json", {
        "stage": "M2b", "status": "COMPLETED", "artifact_sha256": artifact_sha,
        "rubric_version": RUBRIC_VERSION, "audience_profile": audience,
        "artifact_unchanged": True, "content_judge_pass": True,
        "execution_evidence_sha256": evidence["execution_evidence_sha256"],
    })
    language_report = {
        "artifact_sha256": artifact_sha,
        "rubric_version": RUBRIC_VERSION,
        "verdict": "PASS",
        "criteria": [
            {"criterion_id": key, "status": "PASS", "reason": "ok"}
            for key in ("L1", "L2", "L3", "L4", "P1")
        ],
        "findings": [],
    }
    write_json(m2c / "judge-language-report.json", language_report)
    write_json(m2c / "gate-a-package.json", {
        "gate": "A", "artifact_sha256": artifact_sha,
        "rubric_version": RUBRIC_VERSION, "audience_profile": audience,
        "human_approval": "PENDING_HUMAN_APPROVAL",
    })
    write_json(m2c / "summary.json", {
        "stage": "M2c", "status": "COMPLETED", "lesson_id": "lesson",
        "rubric_version": RUBRIC_VERSION, "audience_profile": audience,
        "gate_a_reached": True, "gate_a_approved": False,
        "gate_a_status": "PENDING_HUMAN_APPROVAL",
        "artifact_sha256": artifact_sha,
        "source_m2a_run": str(m2a), "source_m2b_run": str(m2b),
    })
    return m2c


class GateAReviewTests(unittest.TestCase):
    def test_valid_chain_builds_review_without_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            m2c = fixture(Path(tmp))
            output, text, receipt = make_review(m2c)
            self.assertTrue(output.is_file())
            self.assertIn("Pierwszy fragment.", text)
            self.assertIn("Profil odbiorcy: `cs_year3`", text)
            self.assertIn("Rubric: `0.2`", text)
            self.assertIn("Niezależny sędzia merytoryczny", text)
            self.assertIn("Niezależny sędzia językowy", text)
            self.assertIn("NIEZAREJESTROWANA", text)
            self.assertFalse(receipt["approval_recorded"])
            self.assertFalse(receipt["llm_called"])

    def test_artifact_change_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            m2c = fixture(Path(tmp))
            m2a = Path(load(m2c / "summary.json")["source_m2a_run"])
            artifact = load(m2a / "artifact.json")
            artifact["title"] = "changed"
            write_json(m2a / "artifact.json", artifact)
            with self.assertRaises(GateAReviewError):
                verify_chain(m2c)

    def test_content_nonpass_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            m2c = fixture(Path(tmp))
            m2b = Path(load(m2c / "summary.json")["source_m2b_run"])
            report = load(m2b / "judge-report-with-execution.json")
            report["criteria"][0]["status"] = "FAIL"
            write_json(m2b / "judge-report-with-execution.json", report)
            with self.assertRaises(GateAReviewError):
                verify_chain(m2c)

    def test_obsolete_rubric_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            m2c = fixture(Path(tmp))
            summary = load(m2c / "summary.json")
            summary["rubric_version"] = "0.1"
            write_json(m2c / "summary.json", summary)
            with self.assertRaises(GateAReviewError):
                verify_chain(m2c)

    def test_missing_l4_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            m2c = fixture(Path(tmp))
            report_path = m2c / "judge-language-report.json"
            report = load(report_path)
            report["criteria"] = [row for row in report["criteria"] if row["criterion_id"] != "L4"]
            write_json(report_path, report)
            with self.assertRaises(GateAReviewError):
                verify_chain(m2c)

    def test_gate_must_still_be_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            m2c = fixture(Path(tmp))
            summary = load(m2c / "summary.json")
            summary["gate_a_approved"] = True
            summary["gate_a_status"] = "APPROVED"
            write_json(m2c / "summary.json", summary)
            with self.assertRaises(GateAReviewError):
                verify_chain(m2c)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
