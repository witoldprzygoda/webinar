"""Validate starter files without external services or installed dependencies."""
from __future__ import annotations
import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    'README.md', 'START.md', 'AGENTS.md', 'CLAUDE.md', 'PRODUCTION_WORKFLOW.md',
    'QUALITY_RUBRIC.md', 'IMPLEMENTATION_PLAN.md', 'config/sources.json',
    'config/production.json', 'requirements.txt', 'flows/smoke.py',
    'prompts/author.md', 'prompts/judge_content.md', 'prompts/judge_language.md',
    'prompts/arbiter.md', 'prompts/scene_designer.md', 'prompts/judge_visual.md',
)

def check_starter(root: Path = ROOT) -> dict:
    hashes = {}
    for name in REQUIRED:
        path = root / name
        if not path.is_file():
            raise ValueError(f'Missing required file: {name}')
        raw = path.read_bytes()
        if not raw.strip() or '\x00' in raw.decode('utf-8'):
            raise ValueError(f'Empty or invalid file: {name}')
        hashes[name] = hashlib.sha256(raw).hexdigest()
    sources = json.loads((root/'config/sources.json').read_text(encoding='utf-8'))
    ids = [s['id'] for s in sources['sources']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate source IDs')
    if not sources['policy']['snapshot_required_before_run']:
        raise ValueError('Snapshots must be required')
    p = json.loads((root/'config/production.json').read_text(encoding='utf-8'))
    if p['llm']['api_fallback'] or p['llm']['automatic_credit_purchase']:
        raise ValueError('Paid LLM fallback is forbidden')
    if p['audio']['enabled']:
        raise ValueError('Audio must remain disabled in this milestone')
    r = p['review']
    for k in ('separate_process_required','separate_session_required',
              'context_access_isolation_required'):
        if not r[k]:
            raise ValueError(f'Required isolation policy: {k}')
    if r['resume_producer_session'] or r['producer_can_approve']:
        raise ValueError('The producer cannot act as the independent judge')
    for folder in ('scripts','flows'):
        for path in (root/folder).glob('*.py'):
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    return {'starter_check':'PASS','scope':'files_configuration_syntax_only',
            'production_implemented':False,'isolation_verified':False,
            'external_services_called':False,'files':hashes}

if __name__ == '__main__':
    try:
        print(json.dumps(check_starter(), indent=2))
    except (OSError, ValueError, KeyError, SyntaxError) as e:
        print(f'STARTER_CHECK_FAILED: {e}', file=sys.stderr)
        raise SystemExit(1)
