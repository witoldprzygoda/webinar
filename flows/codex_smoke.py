"""M1a: Prefect -> two fresh Codex processes. Not the M1 isolation acceptance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runners.codex_smoke import CodexSmokeRunner, RunnerError  # noqa: E402


@task(name="codex-new-session", retries=0, cache_policy=NO_CACHE,
      persist_result=False)
def run_role(role: str, model: str, reports: str) -> dict:
    runner = CodexSmokeRunner(model=model)
    runner.preflight()
    get_run_logger().info("Starting synthetic %s session (no tools, no audio).", role)
    return runner.run(role, Path(reports) / role)


@flow(name="video-production-codex-smoke", retries=0, persist_result=False)
def codex_smoke(model: str = "gpt-6-astra") -> dict:
    logger = get_run_logger()
    run_dir = ROOT / "runs" / "codex-smoke" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    summary = {"connection_check": "FAIL", "separate_sessions": False,
               "isolation_verified": False, "production_implemented": False,
               "audio_called": False, "reports": str(run_dir)}
    try:
        # Sequential on purpose: one subscription, no burst or redundant retry.
        author = run_role("author", model, str(run_dir))
        judge = run_role("judge", model, str(run_dir))
        if author["session_id"] == judge["session_id"]:
            raise RunnerError("SESSION_REUSED", "Author and judge reused the same session.")
        if author["working_directory"] == judge["working_directory"]:
            raise RunnerError("WORKSPACE_REUSED", "Working directories were reused.")
        summary.update(connection_check="PASS", separate_sessions=True,
                       author_session_id=author["session_id"],
                       judge_session_id=judge["session_id"])
        logger.info("CODEX PROCESS/SESSION CHECK PASSED. ISOLATION NOT VERIFIED.")
        logger.info("Reports: %s", run_dir)
        return summary
    except RunnerError as error:
        summary["status"] = error.status
        logger.error("%s: %s", error.status, error)
        raise
    finally:
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-6-astra")
    args = parser.parse_args()
    result = codex_smoke(args.model)
    print(json.dumps(result, indent=2))
