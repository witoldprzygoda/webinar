"""Inspect the deterministic M3b v2 visual fact catalog without calling an LLM."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flows.m3b_scene_plan import build_evidence_packet, verify_m3a_selection  # noqa: E402
from runners.visual_fact_catalog import build_visual_fact_catalog, verify_visual_fact_catalog  # noqa: E402


PRESENTATION_POLICY = "core_examples_only_enrichment_checks_verification_only"


def preflight(m3a_run_dir: Path) -> dict:
    verified = verify_m3a_selection(m3a_run_dir.expanduser().resolve())
    approved = verified["approved"]
    evidence = build_evidence_packet(approved)
    catalog = build_visual_fact_catalog(approved["artifact_sha256"], evidence)
    verify_visual_fact_catalog(
        catalog,
        artifact_sha256=approved["artifact_sha256"],
        evidence=evidence,
    )
    if catalog.get("presentation_policy") != PRESENTATION_POLICY:
        raise ValueError("Unexpected visual fact presentation policy.")
    forbidden = [
        row.get("fact_id", "")
        for row in catalog.get("facts", [])
        if isinstance(row, dict)
        and (
            row.get("provenance") == "enrichment_check"
            or str(row.get("fact_id", "")).startswith("fact:enrichment:")
        )
    ]
    if forbidden:
        raise ValueError("Visual fact catalog exposes enrichment verification harnesses: " + ", ".join(forbidden))
    return {
        "stage": "M3b-fact-catalog-preflight",
        "status": "PASS",
        "llm_called": False,
        "artifact_sha256": approved["artifact_sha256"],
        "m3a_selection_sha256": verified["selection_sha256"],
        "selected_variant_id": verified["selection"]["selected_variant_id"],
        "visual_fact_catalog_sha256": catalog["visual_fact_catalog_sha256"],
        "presentation_policy": catalog["presentation_policy"],
        "enrichment_verification_facts_exposed": False,
        "fact_count": len(catalog["facts"]),
        "facts": [
            {
                "fact_id": row["fact_id"],
                "content": row["content"],
                "allowed_element_kinds": row["allowed_element_kinds"],
                "provenance": row["provenance"],
                "source_ref": row["source_ref"],
                "fragment_ids": row["fragment_ids"],
                "derivation": row["derivation"],
            }
            for row in catalog["facts"]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m3a_run_dir", help="Completed M3a run with human selection receipt")
    args = parser.parse_args()
    try:
        result = preflight(Path(args.m3a_run_dir))
    except Exception as exc:
        print(json.dumps({"stage": "M3b-fact-catalog-preflight", "status": "ERROR", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
