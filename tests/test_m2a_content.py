"""Offline tests for M2a contracts. No Codex or network calls."""
from __future__ import annotations

import json
import unittest

from flows.m2a_content import (
    CONTENT_CRITERIA,
    RUBRIC_VERSION,
    author_schema,
    audience_for,
    canonical_hash,
    judge_schema,
    validate_judge_report,
)
from runners.codex_role import RoleRunnerError, parse_json_events
from runners.source_pack import SourcePackError, extract_section, raw_url, validate_spec


class SourcePackTests(unittest.TestCase):
    def spec(self):
        return {
            "id": "x", "role": "material", "repository": "owner/repo",
            "commit": "a" * 40, "path": "docs/a.md",
            "section_start": "START", "section_end": "END"
        }

    def test_raw_url_requires_pinned_commit(self):
        spec = self.spec()
        self.assertEqual(raw_url(spec), "https://raw.githubusercontent.com/owner/repo/" + "a" * 40 + "/docs/a.md")
        spec["commit"] = "main"
        with self.assertRaises(SourcePackError):
            validate_spec(spec)

    def test_path_escape_rejected(self):
        spec = self.spec()
        spec["path"] = "../secret"
        with self.assertRaises(SourcePackError):
            validate_spec(spec)

    def test_section_extract_is_exact_and_excludes_next_section(self):
        value = extract_section("head\nSTART\ninside\nEND\nafter\n", "START", "END")
        self.assertEqual(value, "START\ninside\n")

    def test_missing_marker_is_error(self):
        with self.assertRaises(SourcePackError):
            extract_section("text", "START", "END")


class RoleProtocolTests(unittest.TestCase):
    def events(self, output=None):
        if output is None:
            output = {"ok": True}
        rows = [
            {"type": "thread.started", "thread_id": "fresh"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(output)}},
            {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
        ]
        return "\n".join(json.dumps(row) for row in rows)

    def test_generic_json_output_and_session(self):
        session, output, usage = parse_json_events(self.events())
        self.assertEqual(session, "fresh")
        self.assertTrue(output["ok"])
        self.assertEqual(usage["output_tokens"], 1)

    def test_tool_activity_rejected(self):
        text = self.events() + "\n" + json.dumps({"type": "item.started", "item": {"type": "command_execution"}})
        with self.assertRaises(RoleRunnerError) as caught:
            parse_json_events(text)
        self.assertEqual(caught.exception.status, "UNEXPECTED_TOOL_ACTIVITY")

    def test_multiple_sessions_rejected(self):
        with self.assertRaises(RoleRunnerError):
            parse_json_events(self.events() + '\n{"type":"thread.started","thread_id":"other"}')


class ArtifactContractTests(unittest.TestCase):
    def test_hash_is_order_independent_for_objects(self):
        self.assertEqual(canonical_hash({"a": 1, "b": 2}), canonical_hash({"b": 2, "a": 1}))

    def test_author_schema_has_semantic_fragments_and_claims(self):
        schema = author_schema()
        self.assertIn("narration", schema["properties"])
        self.assertIn("claims", schema["properties"])
        fragment = schema["properties"]["narration"]["items"]
        self.assertIn("fragment_id", fragment["properties"])

    def test_judge_schema_binds_artifact_hash_and_current_rubric(self):
        schema = judge_schema("abc")
        self.assertEqual(schema["properties"]["artifact_sha256"]["enum"], ["abc"])
        self.assertEqual(schema["properties"]["rubric_version"]["enum"], ["0.2"])
        self.assertEqual(RUBRIC_VERSION, "0.2")

    def test_judge_requires_each_criterion_once(self):
        report = {"criteria": [{"criterion_id": value} for value in CONTENT_CRITERIA]}
        validate_judge_report(report)
        report["criteria"][-1] = {"criterion_id": CONTENT_CRITERIA[0]}
        with self.assertRaises(RoleRunnerError):
            validate_judge_report(report)

    def test_content_scope_includes_audience_calibration(self):
        self.assertEqual(
            set(CONTENT_CRITERIA),
            {"F1", "F2", "E1", "E2", "L1", "L2", "L3", "L4", "D1", "P1"},
        )

    def test_lesson_resolves_explicit_technical_profile(self):
        profile = audience_for({"audience_profile": "technical_competent"})
        self.assertEqual(profile["profile_id"], "technical_competent")
        flattened = json.dumps(profile, ensure_ascii=False)
        self.assertIn("kompetencjami informatycznymi", flattened)
        self.assertIn("nie z roku studiów", flattened)
        self.assertIn("infantyliz", flattened)
        self.assertIn("oczywist", flattened)

    def test_missing_audience_profile_blocks_input(self):
        with self.assertRaises(RoleRunnerError) as caught:
            audience_for({})
        self.assertEqual(caught.exception.status, "BLOCKED_INPUT")


if __name__ == "__main__":
    unittest.main()
