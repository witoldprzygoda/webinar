"""M1b synthetic Windows boundary probe. No LLM, lesson or audio is run.

The native-only profile failed the operator's test on codex-cli 0.153.4.
The default adds a scoped, direct ACL guard on disposable foreign-role objects.
This does NOT modify the production runner or establish full isolation.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fixture_guard import fixture_guard  # noqa: E402

ROLES = ('author', 'judge', 'arbiter')
ROLE_SEQUENCE = ('author', 'judge', 'arbiter', 'author', 'arbiter', 'judge', 'author')
PREFIX = 'WEBINAR_BOUNDARY_RESULT='
PROFILE = 'webinar_boundary_probe'

# Fixed, trusted diagnostic code. It never prints the contents of a file.
PROBE = r'''
import errno,json,os,pathlib,sys
checks=json.loads(sys.argv[1])
results={}
for name, item in checks.items():
    path=pathlib.Path(item["path"])
    try:
        if item["operation"] == "read":
            with path.open("rb") as handle:
                handle.read()
        elif item["operation"] == "list":
            list(path.iterdir())
        elif item["operation"] == "open_write":
            fd=os.open(str(path), os.O_WRONLY)
            os.close(fd)
        elif item["operation"] == "create":
            with path.open("x", encoding="utf-8") as handle:
                handle.write("SYNTHETIC_OUTPUT\n")
        else:
            raise ValueError("unknown probe operation")
        result={"outcome":"ALLOWED"}
    except OSError as error:
        denied=isinstance(error, PermissionError) or error.errno in (errno.EACCES,errno.EPERM)
        result={"outcome":"DENIED" if denied else "ERROR",
                "errno":error.errno,"winerror":getattr(error,"winerror",None),
                "exception":type(error).__name__,"message":str(error)}
    results[name]=result
print("WEBINAR_BOUNDARY_RESULT="+json.dumps(results), flush=True)
'''


class BoundaryStepError(RuntimeError):
    """A failed phase with machine-readable evidence, not an isolation verdict."""
    def __init__(self, message: str, *, stage: str, details: dict | None = None):
        super().__init__(message)
        self.stage = stage
        self.details = details or {}


def toml(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, dict):
        return '{' + ', '.join(toml(k) + '=' + toml(v) for k, v in value.items()) + '}'
    raise TypeError(f'Unsupported TOML value: {type(value).__name__}')


def find_cli() -> list[str]:
    native = shutil.which('codex.exe')
    if native:
        return [native]
    shim = shutil.which('codex.cmd') or shutil.which('codex')
    if not shim:
        raise RuntimeError('Codex is not in PATH.')
    entry = Path(shim).resolve().parent / 'node_modules/@openai/codex/bin/codex.js'
    node = shutil.which('node.exe') or shutil.which('node')
    if not entry.is_file() or not node:
        raise RuntimeError('Cannot resolve the npm Codex executable. No shell fallback was used.')
    return [node, str(entry)]


def environment() -> dict[str, str]:
    allowed = {
        'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE',
        'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMDATA', 'APPDATA', 'LOCALAPPDATA',
        'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH', 'HOME', 'USERNAME', 'USER',
        'TEMP', 'TMP', 'TMPDIR', 'CODEX_HOME', 'LANG', 'TERM',
    }
    return {k: v for k, v in os.environ.items() if k.upper() in allowed}


def execute(args: list[str], cwd: Path, timeout: int = 90, *,
            input_text: str | None = None) -> subprocess.CompletedProcess:
    with subprocess.Popen(args, cwd=cwd, env=environment(),
                          stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          encoding='utf-8', errors='replace', shell=False) as process:
        try:
            out, err = process.communicate(input_text, timeout=timeout)
        except BaseException:
            if os.name == 'nt' and process.poll() is None:
                try:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=10, check=False)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            raise
        return subprocess.CompletedProcess(args, process.returncode, out, err)


def create_fixtures(root: Path) -> None:
    (root / '.webinar-fixture-id').write_text(uuid.uuid4().hex, encoding='utf-8')
    (root / 'shared').mkdir()
    for name, content in (('evidence.txt', 'SYNTHETIC_EVIDENCE'),
                          ('rubric.txt', 'SYNTHETIC_RUBRIC'),
                          ('approval.txt', 'NOT_APPROVED')):
        (root / 'shared' / name).write_text(content + '\n', encoding='utf-8')
    (root / 'unlisted').mkdir()
    (root / 'unlisted/note.txt').write_text('SYNTHETIC_UNLISTED\n', encoding='utf-8')
    for role in ROLES:
        (root / role / 'out').mkdir(parents=True)
        (root / role / 'nested').mkdir()
        (root / role / 'private.txt').write_text('SYNTHETIC_PRIVATE\n', encoding='utf-8')
        (root / role / 'nested/private.txt').write_text('SYNTHETIC_NESTED\n', encoding='utf-8')
        (root / role / 'out/existing.txt').write_text('SYNTHETIC_REPORT\n', encoding='utf-8')


def probes(root: Path, role: str) -> dict:
    if role not in ROLES:
        raise ValueError('Unknown fixture role.')

    def item(path: Path, operation: str, expected: str) -> dict:
        return {'path': str(path), 'operation': operation, 'expected': expected}

    checks = {
        'evidence_read': item(root / 'shared/evidence.txt', 'read', 'ALLOWED'),
        'rubric_read': item(root / 'shared/rubric.txt', 'read', 'ALLOWED'),
        'own_private_read': item(root / role / 'private.txt', 'read', 'ALLOWED'),
        'own_nested_read': item(root / role / 'nested/private.txt', 'read', 'ALLOWED'),
        'own_output_create': item(root / role / 'out/new.txt', 'create', 'ALLOWED'),
        'rubric_write': item(root / 'shared/rubric.txt', 'open_write', 'DENIED'),
        'approval_write': item(root / 'shared/approval.txt', 'open_write', 'DENIED'),
        'evidence_write': item(root / 'shared/evidence.txt', 'open_write', 'DENIED'),
        'unlisted_read': item(root / 'unlisted/note.txt', 'read', 'DENIED'),
    }
    for other in ROLES:
        if other != role:
            checks[other + '_private_read'] = item(root / other / 'private.txt', 'read', 'DENIED')
            checks[other + '_nested_read'] = item(root / other / 'nested/private.txt', 'read', 'DENIED')
            checks[other + '_directory_list'] = item(root / other, 'list', 'DENIED')
            checks[other + '_nested_list'] = item(root / other / 'nested', 'list', 'DENIED')
            checks[other + '_report_read'] = item(root / other / 'out/existing.txt', 'read', 'DENIED')
            checks[other + '_report_write'] = item(root / other / 'out/existing.txt', 'open_write', 'DENIED')
            generated = root / other / 'out/new.txt'
            if generated.exists():
                checks[other + '_generated_read'] = item(generated, 'read', 'DENIED')
    return checks


def permission_config(root: Path, role: str) -> dict:
    # Original native permission profile is kept unchanged, not weakened.
    fs = {':minimal': 'read', str(Path(sys.base_prefix).resolve()): 'read',
          str(Path(sys.prefix).resolve()): 'read', str(root / 'shared'): 'read',
          str(root / role): 'read', str(root / role / 'out'): 'write'}
    for other in ROLES:
        if other != role:
            fs[str(root / other)] = 'deny'
    return {PROFILE: {'filesystem': fs, 'network': {'enabled': False}}}


def sandbox_command(cli: list[str], root: Path, role: str, checks: dict | None = None) -> list[str]:
    if checks is None:
        checks = probes(root, role)
    return [*cli, '-c', 'permissions=' + toml(permission_config(root, role)),
            '-c', 'approval_policy="never"', 'sandbox', '-P', PROFILE,
            '--include-managed-config', '-C', str(root / role), '--',
            sys.executable, '-I', '-S', '-B', '-c', PROBE,
            json.dumps(checks, ensure_ascii=True)]


def parse_result(output: str, expected: dict) -> dict:
    lines = [line[len(PREFIX):] for line in output.splitlines() if line.startswith(PREFIX)]
    if len(lines) != 1:
        raise ValueError('Probe did not return exactly one result; missing output is NOT denial.')
    result = json.loads(lines[0])
    if not isinstance(result, dict) or set(result) != set(expected):
        raise ValueError('Probe result does not match the requested checks.')
    for name, value in result.items():
        if not isinstance(value, dict) or value.get('outcome') not in ('ALLOWED', 'DENIED', 'ERROR'):
            raise ValueError('Invalid probe result: ' + name)
    return result


def aggregate(steps: list[dict], expected_steps: int) -> str:
    if len(steps) != expected_steps or any(step['status'] == 'ERROR' for step in steps):
        return 'ERROR'
    return 'PASS' if all(step['status'] == 'PASS' for step in steps) else 'FAIL'


def content_hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*.txt') if path.name != 'new.txt'}


def check_positive_control(baseline: subprocess.CompletedProcess, checks: dict,
                           role: str, run_dir: Path, prefix: str) -> dict:
    """Save evidence before parsing; outside the sandbox every check expects ALLOWED."""
    log_names = {stream: prefix + '-baseline-' + stream + '.log'
                 for stream in ('stdout', 'stderr')}
    for stream, name in log_names.items():
        (run_dir / name).write_text(getattr(baseline, stream), encoding='utf-8')
    details = {'baseline_exit_code': baseline.returncode, 'baseline_logs': log_names}
    try:
        before = parse_result(baseline.stdout, checks)
    except ValueError as error:
        raise BoundaryStepError('Invalid positive-control response: ' + str(error),
                                stage='positive_control', details=details) from error
    failures = [
        {'check': name, 'path': checks[name]['path'],
         'operation': checks[name]['operation'], **value,
         'expected': 'ALLOWED', 'sandbox_expected': checks[name]['expected']}
        for name, value in before.items() if value['outcome'] != 'ALLOWED'
    ]
    details['control_failures'] = failures
    (run_dir / (prefix + '-baseline.json')).write_text(
        json.dumps({'role': role, 'checks': checks, 'result': before,
                    'exit_code': baseline.returncode}, indent=2, ensure_ascii=True) + '\n',
        encoding='utf-8')
    if baseline.returncode or failures:
        raise BoundaryStepError('Positive control failed for ' + role +
                                '; sandbox was not started for this step.',
                                stage='positive_control', details=details)
    return before


def run_step(cli: list[str], root: Path, role: str, run_dir: Path,
             index: int, *, native_only: bool) -> dict:
    prefix = f'{index:02d}-{role}'
    # Only our synthetic output may be removed to repeat its exclusive-create check.
    (root / role / 'out/new.txt').unlink(missing_ok=True)
    checks = probes(root, role)
    baseline = execute([sys.executable, '-I', '-S', '-B', '-c', PROBE,
                        json.dumps(checks)], root / role, 20)
    check_positive_control(baseline, checks, role, run_dir, prefix)
    (root / role / 'out/new.txt').unlink()
    original = content_hashes(root)
    guard = nullcontext() if native_only else fixture_guard(root, role, execute)
    with guard:
        result = execute(sandbox_command(cli, root, role, checks), root / role)
        # Save even when guard restoration subsequently fails.
        (run_dir / (prefix + '-stdout.log')).write_text(result.stdout, encoding='utf-8')
        (run_dir / (prefix + '-stderr.log')).write_text(result.stderr, encoding='utf-8')
    if result.returncode:
        return {'step': index, 'role': role, 'status': 'ERROR', 'exit_code': result.returncode,
                'stage': 'sandbox_process', 'message': result.stderr[-2000:]}
    actual = parse_result(result.stdout, checks)
    rows = {name: {**value, 'expected': checks[name]['expected'],
                    'pass': value['outcome'] == checks[name]['expected']}
            for name, value in actual.items()}
    integrity_ok = content_hashes(root) == original
    error = any(row['outcome'] == 'ERROR' for row in rows.values())
    status = 'ERROR' if error else ('PASS' if integrity_ok and all(row['pass'] for row in rows.values()) else 'FAIL')
    return {'step': index, 'role': role, 'status': status, 'checks': rows,
            'fixture_contents_unchanged': integrity_ok}


def run_sequence(cli: list[str], root: Path, run_dir: Path, *, native_only: bool,
                 step_fn=None, steps: list[dict] | None = None, checkpoint=None) -> list[dict]:
    if step_fn is None:
        step_fn = run_step
    if steps is None:
        steps = []
    elif steps:
        raise ValueError('A new probe needs an empty progress list; resuming is not supported.')
    for index, role in enumerate(ROLE_SEQUENCE, start=1):
        try:
            step = step_fn(cli, root, role, run_dir, index, native_only=native_only)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            step = {'step': index, 'role': role, 'status': 'ERROR',
                    'stage': getattr(error, 'stage', 'step_execution'),
                    'exception': type(error).__name__, 'message': str(error)}
            if isinstance(error, BoundaryStepError):
                step.update(error.details)
        steps.append(step)
        if checkpoint is not None:
            checkpoint(steps)
        print(f"[{index}/{len(ROLE_SEQUENCE)}] {role}: {step['status']}", flush=True)
        if step['status'] == 'ERROR':
            break
    return steps


def save_report(path: Path, report: dict) -> None:
    """Replace one local JSON snapshot, without publishing a partial document."""
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    temporary.replace(path)


def concise_report(report: dict) -> dict:
    concise = {key: value for key, value in report.items() if key != 'steps'}
    steps = report['steps']
    concise['steps_passed'] = sum(step['status'] == 'PASS' for step in steps)
    concise['steps_completed'] = len(steps)
    concise['steps_expected'] = len(ROLE_SEQUENCE)
    concise['failures'] = [
        {'step': step['step'], 'role': step['role'], 'check': name,
         'outcome': row['outcome'], 'expected': row['expected']}
        for step in steps for name, row in step.get('checks', {}).items() if not row['pass']]
    concise['step_errors'] = [{key: value for key, value in step.items() if key != 'checks'}
                              for step in steps if step['status'] == 'ERROR']
    return concise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-only', action='store_true',
                        help='Reproduce the original native-only profile without the extra ACL guard.')
    args = parser.parse_args()
    if os.name != 'nt':
        print('This live probe targets native Windows. Use unit tests on other systems.')
        return 2
    run_dir = ROOT / 'runs/boundary-probe' / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    report = {'filesystem_probe': 'ERROR', 'steps': [],
              'guard_mode': 'native_only' if args.native_only else 'native_plus_fixture_acl',
              'sequence': list(ROLE_SEQUENCE), 'llm_called': False,
              'instruction_isolation_verified': False, 'isolation_verified': False,
              'production_ready': False, 'network_isolation_tested': False}

    def checkpoint(steps: list[dict]) -> None:
        # ERROR until the ENTIRE sequence and fixture cleanup have completed.
        # A killed/interrupted run must never leave a successful final verdict.
        save_report(run_dir / 'progress.json', {**report, 'steps': steps,
                                               'filesystem_probe': 'ERROR', 'incomplete': True})

    try:
        cli = find_cli()
        with tempfile.TemporaryDirectory(prefix='webinar-boundary-') as tmp:
            root = Path(tmp).resolve()
            version = execute([*cli, '--version'], root, 30)
            if version.returncode:
                raise RuntimeError('Cannot obtain Codex version.')
            report['cli_version'] = version.stdout.strip()
            if report['cli_version'] != 'codex-cli 0.153.4':
                raise RuntimeError('Probe pinned to CLI 0.153.4; no unsupported flags were tried.')
            create_fixtures(root)
            run_sequence(cli, root, run_dir, native_only=args.native_only,
                         steps=report['steps'], checkpoint=checkpoint)
        report['filesystem_probe'] = aggregate(report['steps'], len(ROLE_SEQUENCE))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        report['filesystem_probe'] = 'ERROR'
        report['error'] = str(error)
    except KeyboardInterrupt:
        report['filesystem_probe'] = 'ERROR'
        report['error'] = 'Interrupted by operator; the probe is incomplete.'
    finally:
        path = run_dir / 'summary.json'
        save_report(path, report)
        print(json.dumps(concise_report(report), indent=2, ensure_ascii=True))
        print('Report: ' + str(path))
    return 0 if report['filesystem_probe'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
