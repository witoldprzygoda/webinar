# M2b: execution evidence before content re-review

M2a intentionally omitted execution evidence. Its independent judge therefore
returned BLOCKED with E1/E2 NOT_VERIFIED while passing the remaining content
criteria. M2b closes exactly that evidence gap without changing the authored
artifact.

## Contract

1. Load an already completed M2a run and verify the hashes of `artifact.json`
   and `source-pack.json` against its summary.
2. Run a fixed console-example manifest under exact CPython 3.14.7.
3. Use Python's stdlib `code.InteractiveConsole` in one persistent namespace so
   expression display, assignment silence and the special interactive `_`
   behavior are exercised in-session.
4. Record runtime implementation/version/executable, every input, actual stdout
   and stderr, expected stdout, per-example comparison and evidence hashes.
5. If any execution differs, stop before the judge (`EXECUTION_MISMATCH`).
6. If execution matches, launch one NEW independent judge session and provide
   the same immutable artifact plus the new execution evidence. The previous
   judge report/verdict is deliberately not included.

The executor is deterministic Python code, not an LLM, uses no network, audio or
rendering. M2b still does not reach human Gate A because the separate language
judge and the complete M2 review chain are not implemented yet.

## Runtime

The manifest is pinned to CPython 3.14.7, released 2026-08-05. Discovery tries:

- `WEBINAR_PYTHON_314` when explicitly set to an interpreter path;
- Windows `py -3.14`;
- `python3.14`;
- `python` as a final candidate, accepted only when it is exact CPython 3.14.7.

A different or missing runtime returns `BLOCKED_RUNTIME`; the executor never
silently substitutes Python 3.13 or another 3.14 patch release.

## Run on Windows / Git Bash

Use the clean webinar Codex profile already established for M1:

```bash
export CODEX_HOME="$(cygpath -w "$HOME/.codex-webinar")"
export PREFECT_API_URL="http://127.0.0.1:4200/api"

./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_m2b_executor.py' -v
./.venv/Scripts/python.exe flows/m2b_verify.py runs/m2a-content/<M2A_RUN_ID>
```

For the first real run, use the M2a directory that produced the reviewed
artifact. Expected success is `status: COMPLETED`, `artifact_unchanged: true`,
`runtime_actual: 3.14.7`, `all_examples_passed: true`, and a fresh judge session.
The judge verdict is not forced to PASS.
