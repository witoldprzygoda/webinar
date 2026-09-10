# M1b: preserve failed positive-control diagnostics

## Observed result

At commit 0ac5149 the operator's 28 offline tests passed on Windows. The live
probe printed `[1/7] author: PASS`, then stopped with `Positive control failed
for judge; no isolation conclusion possible.` The summary incorrectly showed
zero passed steps and no per-step errors.

This live result is NOT an isolation PASS. The preceding native-only probe
also allowed forbidden cross-role reads. That defect remains unverified as
fixed. The current log does not identify which positive-control operation
failed; its cause must not be asserted from an unrecorded errno or pathname.

## Confirmed reporting defects and repair

1. run_step discarded positive-control stdout/stderr and raised one generic
   RuntimeError. It now saves baseline logs and parsed results before deciding
   whether the control passed. Failures include check name, fixture path,
   operation, errno, winerror, exception type and OS error message.
2. main assigned report['steps'] only after run_sequence returned. An exception
   erased all earlier results. A caller-owned progress list now preserves them,
   and expected step exceptions produce an ERROR entry and stop the sequence.
3. progress.json is written after every finished step. It is marked incomplete
   and never represents a final success. summary.json is finalized separately,
   including when an error, interruption or fixture-cleanup failure occurs.
4. Sandbox output is saved before the guard exits, so a subsequent restore
   failure does not discard the command's available diagnostic output.

The native permission profile, fixture ACL implementation, role order and all
access expectations are unchanged. No automatic retry, privilege escalation,
permission repair or switch to an API is introduced. The test still uses only
disposable fixtures and invokes no model or audio service.

## Important interpretation

The positive control runs OUTSIDE the sandbox, as the operator. Every operation
there must return ALLOWED. Its report includes sandbox_expected separately:
a DENIED result is correct inside a sandbox for a forbidden read, but is not
a successful positive control. Failure of the control means ERROR, not proof
of isolation. Missing paths and FileExistsError are not relabelled as DENIED.

Do not remove negative checks or grant broad permissions merely to get PASS.
First use control_failures to identify the actual failing operation.

## Run on Windows from Git Bash

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_boundary_reporting.py' -v
./.venv/Scripts/python.exe scripts/check_codex_boundary.py
```

If the same second-step problem recurs, the summary should show one passed
step, two completed steps, and a step_errors entry for judge containing the
actual control_failures. That is a correct ERROR report, not a fixed boundary.
Send only the final JSON; do not send auth.json or private account files.

## Verification during preparation

14 new reporting-regression tests passed on Linux. They exercise real local
Python file errors, exact control-error reporting, progress retention after
exceptions/interruption, stopping without retries, and atomic JSON writes.
The second-step failure is simulated; its Windows-specific cause is NOT
reproduced or identified by those tests. Python syntax compilation passed.
No live Codex, Windows sandbox, ACL helper, Prefect or paid API was run here.
