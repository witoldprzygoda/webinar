from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from flows.m3a_scene_variants import (
    target_packet,
    validate_variants,
    verify_gate_a_approval,
)
from runners.codex_role import RoleRunnerError
from scripts.record_gate_a_approval import canonical_hash


class M3aSceneVariantTests(unittest.TestCase):
    def variant(self, variant_id: str, strategy: str = "sequential_run") -> dict:
        return {
            "variant_id": variant_id,
            "title": "Variant",
            "concept": "Concept",
            "pedagogical_rationale": "Reason",
            "visual_strategy": strategy,
            "requires_new_component": False,
            "new_component_request": "",
            "visible_elements": [
                {
                    "element_id": "repl",
                    "kind": "code",
                    "source": "approved_artifact",
                    "content": "price + _",
                },
                {
                    "element_id": "state",
                    "kind": "state",
                    "source": "visual_label",
                    "content": "_ = last displayed result",
                },
            ],
            "beats": [
                {
                    "beat_id": "b1",
                    "narration_fragment_ids": ["frag-07"],
                    "action": "Reveal the next REPL step and move focus to the stored last result.",
                    "focus_target_id": "state",
                    "reveals": ["repl", "state"],
                }
            ],
            "risks": [],
        }

    def output(self) -> dict:
        return {
            "target_fragment_ids": ["frag-07"],
            "variants": [
                self.variant("v1", "sequential_run"),
                self.variant("v2", "state_model"),
                self.variant("v3", "split_view"),
            ],
        }

    def test_valid_variants_are_accepted(self):
        validate_variants(self.output(), target_fragment_ids=["frag-07"], variant_count=3)

    def test_variants_must_use_at_least_two_visual_strategies(self):
        output = self.output()
        for row in output["variants"]:
            row["visual_strategy"] = "sequential_run"
        with self.assertRaises(RoleRunnerError):
            validate_variants(output, target_fragment_ids=["frag-07"], variant_count=3)

    def test_focus_target_must_exist(self):
        output = self.output()
        output["variants"][0]["beats"][0]["focus_target_id"] = "missing"
        with self.assertRaises(RoleRunnerError):
            validate_variants(output, target_fragment_ids=["frag-07"], variant_count=3)

    def test_new_component_request_contract(self):
        output = self.output()
        output["variants"][0]["requires_new_component"] = True
        with self.assertRaises(RoleRunnerError):
            validate_variants(output, target_fragment_ids=["frag-07"], variant_count=3)

    def test_target_packet_uses_only_linked_narration_and_evidence(self):
        verified = {
            "artifact": {
                "narration": [
                    {"fragment_id": "frag-06", "text": "before"},
                    {"fragment_id": "frag-07", "text": "target"},
                ]
            },
            "core_evidence": {
                "results": [
                    {"example_id": "a", "fragment_ids": ["frag-06"]},
                    {"example_id": "b", "fragment_ids": ["frag-07"]},
                ]
            },
            "enrichment_evidence": {"results": []},
        }
        packet = target_packet(verified, ["frag-07"])
        self.assertEqual(packet["narration"], [{"fragment_id": "frag-07", "text": "target"}])
        self.assertEqual([row["example_id"] for row in packet["execution_evidence"]], ["b"])

    def test_m3_requires_self_hashed_gate_a_approval_for_exact_artifact(self):
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            payload = {
                "schema_version": 1,
                "gate": "A",
                "decision": "APPROVE",
                "artifact_sha256": "a" * 64,
                "base_artifact_sha256": "b" * 64,
                "approved_by": "Witold Przygoda",
                "approved_at_utc": "2026-09-10T22:42:00+00:00",
                "review_sha256": "c" * 64,
                "source_m2f_run": str(root),
                "rubric_version": "0.2",
                "portfolio_rubric_version": "0.2",
                "selected_candidate_ids": ["e1"],
                "llm_called": False,
                "audio_called": False,
                "render_called": False,
            }
            payload["approval_sha256"] = canonical_hash(payload)
            (root / "gate-a-approval.json").write_text(json.dumps(payload), encoding="utf-8")
            with patch(
                "flows.m3a_scene_variants.verify_enriched_chain",
                return_value={
                    "run_dir": root,
                    "artifact_sha256": "a" * 64,
                    "summary": {},
                    "artifact": {},
                    "core_evidence": {"results": []},
                    "enrichment_evidence": {"results": []},
                },
            ):
                verified = verify_gate_a_approval(root)
            self.assertEqual(verified["approval_sha256"], payload["approval_sha256"])

    def test_m3_rejects_approval_for_another_artifact(self):
        with TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            payload = {
                "gate": "A",
                "decision": "APPROVE",
                "artifact_sha256": "c" * 64,
                "source_m2f_run": str(root),
            }
            payload["approval_sha256"] = canonical_hash(payload)
            (root / "gate-a-approval.json").write_text(json.dumps(payload), encoding="utf-8")
            with patch(
                "flows.m3a_scene_variants.verify_enriched_chain",
                return_value={
                    "run_dir": root,
                    "artifact_sha256": "a" * 64,
                    "summary": {},
                    "artifact": {},
                    "core_evidence": {"results": []},
                    "enrichment_evidence": {"results": []},
                },
            ):
                with self.assertRaises(RoleRunnerError):
                    verify_gate_a_approval(root)


if __name__ == "__main__":
    unittest.main()
