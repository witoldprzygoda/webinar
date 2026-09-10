"""Scoped Windows ACL guard for disposable boundary-test files, not production data."""
from __future__ import annotations

from contextlib import contextmanager
import base64
import json
import os
from pathlib import Path
import stat
from typing import Callable, Iterator

ROLES = ('author', 'judge', 'arbiter')
HELPER = Path(__file__).with_name('fixture_acl.ps1')


def _regular_entry(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Symlinks and reparse points are not allowed in fixture paths.')
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
        raise ValueError('Only regular fixture files and directories are supported.')


def guarded_paths(root: Path, role: str) -> list[Path]:
    """Enumerate all foreign-role objects; deny each object directly, not recursively by inheritance."""
    if role not in ROLES:
        raise ValueError('Unknown fixture role.')
    root = root.absolute()
    _regular_entry(root)
    if not root.name.startswith('webinar-boundary-'):
        raise ValueError('Not a generated boundary-fixture directory.')
    paths: list[Path] = []

    def visit(path: Path) -> None:
        _regular_entry(path)
        paths.append(path)
        if path.is_dir():
            for child in sorted(path.iterdir()):
                visit(child)

    for other in ROLES:
        if other != role:
            visit(root / other)
    return paths


def powershell_launcher() -> list[str]:
    system_root = os.environ.get('SystemRoot') or os.environ.get('SYSTEMROOT')
    if not system_root:
        raise RuntimeError('SystemRoot missing: cannot locate Windows PowerShell.')
    exe = Path(system_root) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    if not exe.is_file() or not HELPER.is_file():
        raise RuntimeError('Windows PowerShell or fixture ACL helper is unavailable.')
    # Execute a fixed helper as ordinary PowerShell commands, with JSON on stdin.
    # No ExecutionPolicy changes, profiles, elevation, interpolation or user code.
    encoded = base64.b64encode(HELPER.read_text(encoding='utf-8').encode('utf-16le')).decode('ascii')
    return [str(exe), '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded]


def _rpc(execute: Callable, request: dict, root: Path) -> dict:
    result = execute(powershell_launcher(), root, 60,
                     input_text=json.dumps(request, ensure_ascii=True))
    try:
        value = json.loads(result.stdout.lstrip('\ufeff'))
    except (ValueError, AttributeError) as error:
        raise RuntimeError('ACL helper returned no valid JSON; the sandbox probe was not accepted.') from error
    if result.returncode or not isinstance(value, dict) or value.get('status') == 'ERROR':
        detail = value.get('error', 'helper failure') if isinstance(value, dict) else 'invalid response'
        raise RuntimeError('Fixture ACL guard failed: ' + str(detail))
    return value


@contextmanager
def fixture_guard(root: Path, role: str, execute: Callable) -> Iterator[None]:
    """Install, then restore DACLs only on foreign synthetic role trees.

    No sandbox/model is launched if installing the guard fails. The helper rolls
    back partial installs; restore failures propagate as ERROR, never as PASS.
    """
    paths = guarded_paths(root, role)
    fixture_id = (root / '.webinar-fixture-id').read_text(encoding='utf-8').strip()
    request = {'root': str(root), 'fixture_id': fixture_id}
    installed = _rpc(execute, {**request, 'action': 'install',
                              'paths': [str(path) for path in paths]}, root)
    snapshot = installed.get('snapshot')
    if installed.get('status') != 'INSTALLED' or not isinstance(snapshot, list) or not snapshot:
        raise RuntimeError('ACL guard install was not confirmed; no sandbox was launched.')
    try:
        # Strictly validate saved paths before accepting this guard installation.
        if any(not isinstance(item, dict) or set(item) != {'path', 'sddl'} or
               not isinstance(item['path'], str) or not isinstance(item['sddl'], str)
               for item in snapshot):
            raise RuntimeError('Malformed ACL snapshot.')
        if sorted(item['path'] for item in snapshot) != sorted(str(path) for path in paths):
            raise RuntimeError('ACL snapshot differs from the requested fixture paths.')
        yield
    finally:
        restored = _rpc(execute, {**request, 'action': 'restore', 'snapshot': snapshot}, root)
        if restored.get('status') != 'RESTORED' or restored.get('restored') != len(paths):
            raise RuntimeError('Restoring fixture ACLs was not confirmed.')
