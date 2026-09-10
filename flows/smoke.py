"""Local Prefect startup test; no LLM, audio, rendering or agent isolation."""
from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def require_local_server() -> None:
    value = os.environ.get('PREFECT_API_URL', '')
    u = urlparse(value)
    if (u.scheme != 'http' or u.hostname not in {'127.0.0.1','localhost','::1'}
            or u.path.rstrip('/') != '/api' or u.username is not None
            or u.query or u.fragment):
        raise RuntimeError('Set PREFECT_API_URL=http://127.0.0.1:4200/api in this terminal.')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(value.rstrip('/')+'/health', timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f'Prefect health check returned {response.status}')
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError('Local Prefect server is unavailable; start it first.') from e

def main() -> None:
    require_local_server()
    try:
        from prefect import flow, task
    except ImportError as e:
        raise RuntimeError('Install requirements.txt in the project virtual environment.') from e
    from scripts.check_starter import check_starter

    @task(name='check-starter-files', retries=0, persist_result=False)
    def check_files() -> dict:
        return check_starter(ROOT)

    @flow(name='video-production-startup', log_prints=True)
    def startup() -> dict:
        result = check_files()
        print('STARTUP CHECK PASSED. No LLM, audio or render was executed.')
        print('Agent isolation and production workflows are NOT implemented yet.')
        return result

    result = startup()
    print(json.dumps({k:v for k,v in result.items() if k != 'files'}, indent=2))

if __name__ == '__main__':
    try:
        main()
    except RuntimeError as e:
        print(f'STARTUP_FAILED: {e}', file=sys.stderr)
        raise SystemExit(1)
