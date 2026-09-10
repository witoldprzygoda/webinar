# M2d: optional enrichment discovery and selection

M2d runs only after an immutable core artifact has passed M2b content review.
It does not modify the core and does not reach Gate A. Its purpose is to discover
and select optional high-value additions such as pitfalls, practical shortcuts,
cross-language contrasts, semantic edge cases and concise technical curiosities.

## Principle

Enrichment is optional. Zero candidates and zero KEEP decisions are valid.
There is no quota. Weak enrichment is worse than no enrichment.

## Roles

1. `enrichment_scout` receives the core artifact, audience profile and a pinned
   enrichment source pack. It returns 0..N candidates. It does not see author
   history or previous judge reports.
2. `judge_enrichment` is a fresh session. It receives the candidate artifact,
   core, audience, sources and ENRICHMENT_RUBRIC.md, but not scout history or
   reasoning. It decides KEEP/MAYBE/DROP for every candidate.
3. `arbiter` is launched only if at least one MAYBE exists. It receives only the
   ambiguous candidates, their judge reviews, core, audience and sources, then
   resolves each to KEEP or DROP.

All role sessions must be distinct from the earlier author/content-judge sessions
and from each other.

## Candidate contract

Each candidate contains a stable id, kind, proposed insertion location, concise
proposed narration, value rationale, estimated narration seconds, pinned source
support, and a later verification mode (`interactive_python`, `python_cli`, or
`documentation_only`). Candidates do not claim unexecuted outputs.

The first calibration source pack for `python-console-calculator` contains the
canonical lesson section plus pinned CPython 3.14 documentation for `**`, bitwise
operators including `^`, command-line `-c`, and `divmod`.

## Output

`runs/m2d-enrichment/<run-id>/` contains:

- `enrichment-source-pack.json`
- `candidates.json`
- `scout/receipt.json`
- `judge-enrichment-report.json` when candidates exist
- `judge_enrichment/receipt.json` when the judge runs
- `arbiter-report.json` and `arbiter/receipt.json` only when MAYBE exists
- `selection.json`
- `summary.json`

If `selected_count == 0`, the next action is `PROCEED_CORE_UNCHANGED`.
If `selected_count > 0`, the next action is `INTEGRATE_SELECTED`. Integration is
a separate stage: it must create a new artifact hash and then re-run execution,
content review and language review before Gate A.

## Calibration run

Use an already passing M2b core; do not regenerate the author:

```bash
export CODEX_HOME="$(cygpath -w "$HOME/.codex-webinar")"
export PREFECT_API_URL="http://127.0.0.1:4200/api"

./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_m2d_enrichment.py' -v
./.venv/Scripts/python.exe flows/m2d_enrichment.py runs/m2b-execution/<PASSING_M2B_RUN>
```

The calibration objective is to inspect candidate quality and selection behavior,
not to force particular expected curiosities.
