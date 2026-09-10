"""Prefect wrapper for the M1 context-isolation audit. No model request is sent."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_context_isolation import run_audit  # noqa: E402


@task(name="audit-model-visible-context", retries=0, cache_policy=NO_CACHE,
      persist_result=False)
def audit_task() -> dict:
    return run_audit()


@flow(name="video-production-context-isolation", retries=0, persist_result=False)
def context_isolation() -> dict:
    result = audit_task()
    logger = get_run_logger()
    if result["context_isolation_audit"] == "PASS":
        logger.info("CONTEXT ISOLATION AUDIT PASSED. NO MODEL REQUEST WAS SENT.")
    else:
        logger.error("CONTEXT ISOLATION AUDIT: %s", result["context_isolation_audit"])
    return result


if __name__ == "__main__":
    print(json.dumps(context_isolation(), indent=2))
