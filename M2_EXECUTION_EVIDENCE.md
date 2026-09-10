# M2b: execution evidence before content re-review

M2b verifies the exact examples attached to the authored artifact. The executor
must not use a separately maintained example list as production truth, because
that can diverge from the narration.

## Contract

1. M2a writes `artifact.json` containing both canonical narration and
   `execution_plan`.
2. Every concrete code example discussed in narration is represented in that
   plan and linked back through `fragment_ids`.
3. Steps that share interpreter state are ordered inside the same `session_id`.
   A new session starts a fresh interactive namespace (including a reset of `_`).
4. The plan contains exact input and expected outcome (`success` or a named
   exception), but **not expected stdout**. Actual stdout/stderr is evidence
   produced by the executor, not text supplied by the author.
5. M2b verifies artifact/source/plan hashes and executes the plan under exact
   CPython configured by the lesson (`execution_runtime`; currently 3.14.7).
6. It records runtime identity, session/example/fragment ids, exact input,
   actual stdout/stderr, observed exception and per-step outcome checks.
7. Any execution mismatch stops before the judge (`EXECUTION_MISMATCH`).
8. A NEW independent content judge receives the immutable artifact and the
   resulting evidence. It must still compare actual results with narration and
   check that the plan covers every concrete narrated code example.

The executor is deterministic Python code, not an LLM, and uses no network,
audio or rendering. A passing executor only proves that declared inputs executed
as declared; it does not prove that the narration quoted or interpreted their
results correctly.

The old `config/m2b_console_examples.json` fixed manifest remains only as a
regression fixture for the early M2b prototype. It is not the source of
production execution evidence.

## Runtime

Discovery tries `WEBINAR_PYTHON_314`, Windows `py -3.14`, `python3.14`, then
`python`, accepting only the exact CPython patch release requested by the lesson.
A different or missing runtime returns `BLOCKED_RUNTIME`.

## Run on Windows / Git Bash

```bash
export CODEX_HOME="$(cygpath -w "$HOME/.codex-webinar")"
export PREFECT_API_URL="http://127.0.0.1:4200/api"

./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_m2b_executor.py' -v
./.venv/Scripts/python.exe flows/m2b_verify.py runs/m2a-content/<M2A_RUN_ID>
```

For the combined current M2 chain use `flows/m2_content_gate.py`; it stops with
`REVISION_REQUIRED` rather than calling the language judge when content review
has not passed.
