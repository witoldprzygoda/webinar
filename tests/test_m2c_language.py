"""Offline tests for M2c language review and Gate A readiness."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from flows.m2a_content import RUBRIC_VERSION, canonical_hash
from flows.m2c_language import (
    LANGUAGE_CRITERIA,
    build_language_payload,
    fresh_session,
    gate_a_state,
    language_schema,
    validate_language_report,
    verify_m2b_for_language,
)
from runners.codex_role import RoleRunnerError


def artifact() -> dict:
    return {
        "title": "Synthetic lesson",
        "narration": [
            {"fragment_id": "f1", "text": "Pierwsze zdanie."},
            {"fragment_id": "f2", "text": "Drugie zdanie."},
            {"fragment_id": "f3", "text": "Trzecie zdanie."},
        ],
        "claims": [],
        "coverage": [],
        "open_questions": [],
    }


def passing_language_report(sha: str) -> dict:
    return {
        "artifact_sha256": sha,
        "rubric_version": RUBRIC_VERSION,
        "role": "judge_language",
        "verdict": "PASS",
        "criteria": [
            {"criterion_id": key, "status": "PASS", "reason": "ok"}
            for key in LANGUAGE_CRITERIA
        ],
        "coverage_checks": ["all"],
        "findings": [],
    }


def build_run_tree(root: Path) -> tuple[Path, Path, str]:
    m2a = root / "m2a"
    m2b = root / "m2b"
    m2a.mkdir(); m2b.mkdir()
    art = artifact()
    art_hash = canonical_hash(art)
    pack = {
        "schema_version": 1,
        "lesson_id": "python-console-calculator",
        "target_runtime": "Python 3.14",
        "sources": [],
    }
    pack["source_pack_sha256"] = canonical_hash(pack)
    (m2a / "artifact.json").write_text(json.dumps(art), encoding="utf-8")
    (m2a / "source-pack.json").write_text(json.dumps(pack), encoding="utf-8")
    (m2a / "summary.json").write_text(json.dumps({
        "stage": "M2a", "status": "COMPLETED",
        "rubric_version": RUBRIC_VERSION,
        "audience_profile": "cs_year3",
        "artifact_sha256": art_hash,
        "source_pack_sha256": pack["source_pack_sha256"],
        "author_session_id": "author-session",
        "judge_session_id": "first-content-session",
    }), encoding="utf-8")
    evidence = {
        "schema_version": 1,
        "runtime_requested": "3.14.7",
        "runtime": {"version": "3.14.7"},
        "results": [],
        "all_examples_passed": True,
    }
    evidence["execution_evidence_sha256"] = canonical_hash(evidence)
    (m2b / "execution-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    (m2b / "judge-report-with-execution.json").write_text(json.dumps({
        "artifact_sha256": art_hash,
        "rubric_version": RUBRIC_VERSION,
        "verdict": "PASS",
    }), encoding="utf-8")
    (m2b / "summary.json").write_text(json.dumps({
        "stage": "M2b", "status": "COMPLETED",
        "rubric_version": RUBRIC_VERSION,
        "audience_profile": "cs_year3",
        "source_m2a_run": str(m2a),
        "artifact_sha256": art_hash,
        "artifact_unchanged": True,
        "source_pack_sha256": pack["source_pack_sha256"],
        "execution_evidence_sha256": evidence["execution_evidence_sha256"],
        "all_examples_passed": True,
        "judge_verdict": "PASS",
        "content_judge_pass": True,
        "judge_session_id": "second-content-session",
    }), encoding="utf-8")
    return m2a, m2b, art_hash


class M2cTests(unittest.TestCase):
    def test_schema_has_exact_language_criteria_including_l4(self):
        schema = language_schema("a" * 64)
        enum = schema["properties"]["criteria"]["items"]["properties"]["criterion_id"]["enum"]
        self.assertEqual(tuple(enum), LANGUAGE_CRITERIA)
        self.assertEqual(LANGUAGE_CRITERIA, ("L1", "L2", "L3", "L4", "P1"))
        self.assertEqual(schema["properties"]["criteria"]["minItems"], 5)
        self.assertEqual(schema["properties"]["criteria"]["maxItems"], 5)
        self.assertEqual(schema["properties"]["rubric_version"]["enum"], ["0.2"])

    def test_valid_pass_report(self):
        validate_language_report(passing_language_report("a" * 64))

    def test_duplicate_criterion_rejected(self):
        report = passing_language_report("a" * 64)
        report["criteria"][-1]["criterion_id"] = "L1"
        with self.assertRaises(RoleRunnerError):
            validate_language_report(report)

    def test_pass_requires_all_criteria_pass(self):
        report = passing_language_report("a" * 64)
        report["criteria"][0]["status"] = "NOT_VERIFIED"
        with self.assertRaises(RoleRunnerError):
            validate_language_report(report)

    def test_language_packet_excludes_content_review_and_execution(self):
        config = {"brief": "brief", "language": "pl", "audience_profile": "cs_year3"}
        payload = build_language_payload(config, artifact(), "a" * 64)
        self.assertNotIn("source_pack", payload)
        self.assertNotIn("execution_evidence", payload)
        self.assertNotIn("content_judge_report", payload)
        self.assertNotIn("content_judge_verdict", payload)
        flattened = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("first-content-session", flattened)
        self.assertNotIn("second-content-session", flattened)

    def test_language_packet_contains_audience_and_only_spoken_artifact_view(self):
        config = {"brief": "brief", "language": "pl", "audience_profile": "cs_year3"}
        payload = build_language_payload(config, artifact(), "a" * 64)
        self.assertEqual(payload["audience_profile"]["profile_id"], "cs_year3")
        self.assertEqual(set(payload["canonical_text"]), {"title", "narration"})
        self.assertNotIn("claims", payload["canonical_text"])
        self.assertEqual(payload["evaluation_scope"], list(LANGUAGE_CRITERIA))
        self.assertIn("L4", payload["evaluation_scope"])

    def test_completed_passing_m2b_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, m2b, art_hash = build_run_tree(Path(tmp))
            verified = verify_m2b_for_language(m2b)
        self.assertEqual(verified["artifact_sha256"], art_hash)
        self.assertEqual(len(verified["previous_sessions"]), 3)

    def test_obsolete_rubric_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, m2b, _ = build_run_tree(Path(tmp))
            summary_path = m2b / "summary.json"
            summary = json.loads(summary_path.read_text())
            summary["rubric_version"] = "0.1"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaises(RoleRunnerError):
                verify_m2b_for_language(m2b)

    def test_nonpassing_content_judge_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, m2b, _ = build_run_tree(Path(tmp))
            summary_path = m2b / "summary.json"
            summary = json.loads(summary_path.read_text())
            summary["content_judge_pass"] = False
            summary["judge_verdict"] = "REVISE"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaises(RoleRunnerError):
                verify_m2b_for_language(m2b)

    def test_changed_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            m2a, m2b, _ = build_run_tree(Path(tmp))
            art = json.loads((m2a / "artifact.json").read_text())
            art["title"] = "tampered"
            (m2a / "artifact.json").write_text(json.dumps(art), encoding="utf-8")
            with self.assertRaises(RoleRunnerError):
                verify_m2b_for_language(m2b)

    def test_changed_execution_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, m2b, _ = build_run_tree(Path(tmp))
            evidence_path = m2b / "execution-evidence.json"
            evidence = json.loads(evidence_path.read_text())
            evidence["runtime"]["version"] = "0.0.0"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            with self.assertRaises(RoleRunnerError):
                verify_m2b_for_language(m2b)

    def test_content_report_for_other_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, m2b, _ = build_run_tree(Path(tmp))
            report_path = m2b / "judge-report-with-execution.json"
            report = json.loads(report_path.read_text())
            report["artifact_sha256"] = "0" * 64
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaises(RoleRunnerError):
                verify_m2b_for_language(m2b)

    def test_language_session_must_be_new(self):
        old = {"a", "b", "c"}
        self.assertTrue(fresh_session("d", old))
        self.assertFalse(fresh_session("b", old))
        self.assertFalse(fresh_session("", old))

    def test_gate_a_requires_both_judges(self):
        self.assertEqual(gate_a_state(content_pass=True, language_pass=True),
                         (True, "PENDING_HUMAN_APPROVAL"))
        self.assertEqual(gate_a_state(content_pass=True, language_pass=False),
                         (False, "NOT_REACHED"))
        self.assertEqual(gate_a_state(content_pass=False, language_pass=True),
                         (False, "NOT_REACHED"))


if __name__ == "__main__":
    unittest.main()
