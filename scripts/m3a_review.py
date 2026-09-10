"""Render a human-readable comparison of one completed M3a scene-variant run.

No model, render or approval action is performed. The report verifies the scene
variant artifact hash recorded by M3a and prints the approved narration target,
execution evidence and each conceptual visual alternative.
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


class M3aReviewError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise M3aReviewError(message)


def verify_m3a(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    summary = load_json(run_dir / "summary.json")
    _require(summary.get("stage") == "M3a", "Input is not an M3a run.")
    _require(summary.get("status") == "COMPLETED", "M3a is not completed.")
    _require(
        summary.get("outcome") == "WAITING_HUMAN_VARIANT_SELECTION",
        "M3a is not waiting for human variant selection.",
    )
    variants = load_json(run_dir / "scene-variants.json")
    _require(
        summary.get("scene_variants_sha256") == canonical_hash(variants),
        "Scene variants changed after M3a completion.",
    )
    _require(
        variants.get("artifact_sha256") == summary.get("artifact_sha256"),
        "Scene variants refer to another Gate A artifact.",
    )
    _require(
        variants.get("gate_a_approval_sha256") == summary.get("gate_a_approval_sha256"),
        "Scene variants refer to another Gate A approval.",
    )
    source_m2f = summary.get("source_m2f_run")
    _require(isinstance(source_m2f, str) and source_m2f, "M3a does not identify its M2f source.")
    m2f_dir = Path(source_m2f).expanduser().resolve()
    artifact = load_json(m2f_dir / "artifact.json")
    target_ids = summary.get("target_fragment_ids", [])
    target_rows = [
        row for row in artifact.get("narration", [])
        if row.get("fragment_id") in set(target_ids)
    ]
    _require(
        [row.get("fragment_id") for row in target_rows] == target_ids,
        "Approved target narration no longer matches M3a target fragments.",
    )
    core_evidence = load_json(m2f_dir / "core-execution-evidence.json")
    enrichment_evidence = load_json(m2f_dir / "enrichment-execution-evidence.json")
    evidence_rows = [
        row for row in [
            *core_evidence.get("results", []),
            *enrichment_evidence.get("results", []),
        ]
        if set(row.get("fragment_ids", [])).intersection(target_ids)
    ]
    return {
        "run_dir": run_dir,
        "summary": summary,
        "variants": variants,
        "target_rows": target_rows,
        "evidence_rows": evidence_rows,
    }


def build_markdown(verified: dict[str, Any]) -> str:
    summary = verified["summary"]
    variants = verified["variants"]
    lines = [
        "# M3a — wybór wariantu realizacji wizualnej",
        "",
        f"- Artefakt Gate A: `{summary.get('artifact_sha256')}`",
        f"- Gate A approval: `{summary.get('gate_a_approval_sha256')}`",
        f"- Fragment testowy: `{', '.join(summary.get('target_fragment_ids', []))}`",
        f"- Projektant session: `{summary.get('scene_designer_session_id')}`",
        "- Stan: **WAITING_HUMAN_VARIANT_SELECTION**",
        "- Żaden wariant nie jest jeszcze wybrany ani wyrenderowany.",
        "",
        "## Zatwierdzona narracja fragmentu",
        "",
    ]
    for row in verified["target_rows"]:
        lines.extend([
            f"**{row.get('fragment_id')}**",
            "",
            str(row.get("text", "")),
            "",
        ])
    lines.extend(["## Dostępne rzeczywiste wyniki wykonania", ""])
    for row in verified["evidence_rows"]:
        stdout = str(row.get("actual_stdout", "")).strip().replace("\n", " ")
        lines.append(
            f"- `{row.get('example_id') or row.get('check_id')}`: `{row.get('input') or row.get('code')}`"
            f" -> stdout `{stdout}`"
        )
    lines.extend(["", f"## Oś projektu", "", str(variants.get("design_axis", "")), ""])

    for index, variant in enumerate(variants.get("variants", []), start=1):
        lines.extend([
            f"## Wariant {index}: {variant.get('variant_id')} — {variant.get('title')}",
            "",
            f"**Strategia:** `{variant.get('visual_strategy')}`",
            "",
            str(variant.get("concept", "")),
            "",
            f"**Dlaczego dydaktycznie:** {variant.get('pedagogical_rationale', '')}",
            "",
            f"**Nowy komponent:** {'TAK' if variant.get('requires_new_component') else 'NIE'}",
        ])
        if variant.get("requires_new_component"):
            lines.append(f"- {variant.get('new_component_request')}")
        lines.extend(["", "### Elementy widoczne", ""])
        for element in variant.get("visible_elements", []):
            lines.append(
                f"- `{element.get('element_id')}` / `{element.get('kind')}` / `{element.get('source')}` — {element.get('content')}"
            )
        lines.extend(["", "### Przebieg semantyczny", ""])
        for beat in variant.get("beats", []):
            reveal = ", ".join(beat.get("reveals", [])) or "—"
            lines.append(
                f"- `{beat.get('beat_id')}` → focus `{beat.get('focus_target_id')}`, reveal `{reveal}`: {beat.get('action')}"
            )
        lines.extend(["", "### Ryzyka", ""])
        risks = variant.get("risks", [])
        if risks:
            lines.extend([f"- {risk}" for risk in risks])
        else:
            lines.append("- Brak wskazanych ryzyk.")
        lines.append("")

    lines.extend([
        "## Porównanie projektanta",
        "",
        str(variants.get("comparison_note", "")),
        "",
        "## Decyzja człowieka",
        "",
        "**NIEZAREJESTROWANA.**",
        "",
        "Wybierz jeden `variant_id`. Dopiero ten wybór może być podstawą pełnego scene-plan całej lekcji.",
        "",
    ])
    return "\n".join(lines)


def make_review(run_dir: Path) -> tuple[Path, str]:
    verified = verify_m3a(run_dir)
    markdown = build_markdown(verified)
    output = verified["run_dir"] / "m3a-human-review.md"
    output.write_text(markdown, encoding="utf-8")
    return output, markdown


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("m3a_run_dir", help="Completed M3a scene-variant run")
    args = parser.parse_args()
    try:
        output, markdown = make_review(Path(args.m3a_run_dir))
    except (M3aReviewError, Exception) as exc:
        # Keep CLI output compact; underlying flow files remain available for diagnosis.
        print(json.dumps({"m3a_review": "ERROR", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(markdown)
    print("\n---")
    print(json.dumps({
        "m3a_review": "READY_FOR_HUMAN_SELECTION",
        "review_file": str(output),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
