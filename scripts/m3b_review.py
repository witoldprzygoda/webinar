"""Render a human-readable review of one completed M3b v2 scene plan.

This is inspection only: no model, render, audio or approval action occurs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flows.m2b_verify import load_json  # noqa: E402
from scripts.record_gate_a_approval import canonical_hash  # noqa: E402


class M3bReviewError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise M3bReviewError(message)


def _self_hash(value: dict, key: str) -> str:
    saved = value.get(key)
    unhashed = {name: item for name, item in value.items() if name != key}
    _require(isinstance(saved, str) and canonical_hash(unhashed) == saved, f"Invalid {key} self-hash.")
    return saved


def verify_m3b(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    summary = load_json(run_dir / "summary.json")
    _require(summary.get("stage") == "M3b", "Input is not an M3b run.")
    _require(summary.get("scene_plan_contract_version") == 2, "M3b run does not use scene-plan contract v2.")
    _require(summary.get("status") == "COMPLETED", "M3b is not completed.")
    _require(summary.get("outcome") == "READY_FOR_PREVIEW_BUILD", "M3b is not ready for preview build.")
    _require(summary.get("deterministic_fact_binding") is True, "M3b did not record deterministic fact binding.")

    plan = load_json(run_dir / "scene-plan.json")
    design = load_json(run_dir / "scene-plan-design.json")
    catalog = load_json(run_dir / "visual-fact-catalog.json")
    catalog_sha = _self_hash(catalog, "visual_fact_catalog_sha256")

    _require(summary.get("scene_plan_sha256") == canonical_hash(plan), "Scene plan changed after M3b completion.")
    _require(summary.get("designer_plan_sha256") == canonical_hash(design), "Designer plan changed after M3b completion.")
    _require(summary.get("visual_fact_catalog_sha256") == catalog_sha, "M3b catalog hash mismatch.")
    _require(plan.get("visual_fact_catalog_sha256") == catalog_sha, "Scene plan refers to another visual fact catalog.")
    _require(design.get("visual_fact_catalog_sha256") == catalog_sha, "Designer output refers to another visual fact catalog.")
    _require(plan.get("artifact_sha256") == summary.get("artifact_sha256"), "Scene plan refers to another Gate A artifact.")
    _require(plan.get("gate_a_approval_sha256") == summary.get("gate_a_approval_sha256"), "Scene plan refers to another Gate A approval.")
    _require(plan.get("m3a_selection_sha256") == summary.get("m3a_selection_sha256"), "Scene plan refers to another M3a selection.")
    _require(plan.get("selected_calibration_variant_id") == summary.get("selected_variant_id"), "Scene plan selected variant mismatch.")
    return {"run_dir": run_dir, "summary": summary, "plan": plan, "design": design, "catalog": catalog}


def build_markdown(verified: dict[str, Any]) -> str:
    summary = verified["summary"]
    plan = verified["plan"]
    lines = [
        "# M3b v2 — pełny plan scen do przeglądu",
        "",
        f"- Artefakt Gate A: `{summary.get('artifact_sha256')}`",
        f"- Gate A approval: `{summary.get('gate_a_approval_sha256')}`",
        f"- M3a selection: `{summary.get('m3a_selection_sha256')}`",
        f"- Visual fact catalog: `{summary.get('visual_fact_catalog_sha256')}`",
        f"- Wybrany wariant kalibracyjny: `{summary.get('selected_variant_id')}`",
        f"- Liczba scen: `{summary.get('scene_count')}`",
        f"- Nowe komponenty: `{summary.get('component_request_count')}`",
        "- Binding kodu/outputu/stanu: **deterministyczny**",
        "- Stan: **READY_FOR_PREVIEW_BUILD**",
        "- Na tym etapie nic nie zostało wyrenderowane ani nagrane.",
        "",
        f"## {plan.get('lesson_title', '')}",
        "",
    ]
    for index, scene in enumerate(plan.get("scenes", []), start=1):
        lines.extend([
            f"## Scena {index}: {scene.get('scene_id')} — {scene.get('title')}",
            "",
            f"- Typ: `{scene.get('scene_type')}`",
            f"- Fragmenty: `{', '.join(scene.get('narration_fragment_ids', []))}`",
            f"- Strategia: `{scene.get('visual_strategy')}`",
            f"- Wariant M3a: `{scene.get('calibration_variant_id') or '—'}`",
            f"- Cel: {scene.get('pedagogical_goal', '')}",
            f"- Nowy komponent: `{'TAK' if scene.get('requires_new_component') else 'NIE'}`",
            "",
            "### Elementy",
            "",
        ])
        for element in scene.get("visible_elements", []):
            source_type = element.get("source_type")
            if source_type == "fact":
                origin = f"fact `{element.get('fact_id')}` → `{element.get('provenance')}:{element.get('source_ref')}`"
            elif source_type == "narration_quote":
                origin = f"narration `{element.get('fragment_id')}`"
            else:
                origin = "visual label"
            lines.append(
                f"- `{element.get('element_id')}` / `{element.get('kind')}` / {origin} — {element.get('content')}"
            )
        lines.extend(["", "### Beaty", ""])
        for beat in scene.get("beats", []):
            reveals = ", ".join(beat.get("reveals", [])) or "—"
            lines.extend([
                f"- `{beat.get('beat_id')}` / `{beat.get('narration_fragment_id')}` / anchor `{beat.get('anchor_text')}`",
                f"  - focus `{beat.get('focus_target_id')}`, reveal `{reveals}`",
                f"  - {beat.get('action')}",
            ])
        lines.extend(["", "### Ryzyka", ""])
        risks = scene.get("risks", [])
        lines.extend([f"- {risk}" for risk in risks] if risks else ["- Brak wskazanych ryzyk."])
        lines.append("")

    lines.extend(["## Zgłoszone nowe komponenty", ""])
    components = plan.get("component_requests", [])
    if components:
        for component in components:
            lines.append(
                f"- `{component.get('component_id')}` — {component.get('purpose')} "
                f"(sceny: {', '.join(component.get('used_in_scene_ids', []))}; "
                f"pochodzenie: `{component.get('origin_variant_id') or 'M3b'}`)"
            )
    else:
        lines.append("- Brak.")
    lines.extend(["", "## Notatka projektanta", "", str(plan.get("design_note", "")), ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m3b_run_dir", help="Completed M3b v2 scene-plan run")
    args = parser.parse_args()
    try:
        verified = verify_m3b(Path(args.m3b_run_dir))
        markdown = build_markdown(verified)
        output = verified["run_dir"] / "m3b-human-review.md"
        output.write_bytes(markdown.encode("utf-8"))
    except Exception as exc:
        print(json.dumps({"m3b_review": "ERROR", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(markdown)
    print("\n---")
    print(json.dumps({
        "m3b_review": "READY",
        "scene_plan_sha256": verified["summary"]["scene_plan_sha256"],
        "visual_fact_catalog_sha256": verified["summary"]["visual_fact_catalog_sha256"],
        "review_file": str(output),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
