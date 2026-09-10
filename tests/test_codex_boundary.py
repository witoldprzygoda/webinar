"""Offline regression tests. Never invoke real Codex, Windows ACLs or paid services."""
import importlib.util
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'boundary', Path(__file__).resolve().parents[1] / 'scripts/check_codex_boundary.py')
boundary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boundary)
from scripts import fixture_guard as guard


class BoundaryTests(unittest.TestCase):
    def test_toml_windows_paths_roundtrip(self):
        value = {'filesystem': {r'C:\Users\wit\Documents\test': 'read'},
                 'network': {'enabled': False}}
        self.assertEqual(tomllib.loads('value=' + boundary.toml(value))['value'], value)

    def test_toml_rejects_unsupported_values(self):
        with self.assertRaises(TypeError):
            boundary.toml(['unexpected'])

    def test_command_uses_host_sandbox_not_windows_subcommand(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = boundary.sandbox_command(['codex.exe'], root, 'judge')
        index = command.index('sandbox')
        self.assertEqual(command[index + 1], '-P')
        self.assertNotIn('windows', command)
        self.assertNotIn('exec', command)
        self.assertIn('--include-managed-config', command)
        self.assertIn(sys.executable, command)
        self.assertIn('--', command)

    def test_profile_has_no_broad_root_read_and_no_network(self):
        root = Path('/synthetic').resolve()
        config = boundary.permission_config(root, 'judge')[boundary.PROFILE]
        self.assertNotIn(':root', config['filesystem'])
        self.assertEqual(config['filesystem'][str(root / 'author')], 'deny')
        self.assertEqual(config['filesystem'][str(root / 'arbiter')], 'deny')
        self.assertEqual(config['filesystem'][str(root / 'judge/out')], 'write')
        self.assertFalse(config['network']['enabled'])

    def test_environment_does_not_forward_keys_or_code_injection(self):
        with patch.dict('os.environ', {'PATH': 'x', 'HOME': 'h', 'CODEX_HOME': 'c',
                                       'OPENAI_API_KEY': 'x', 'NODE_OPTIONS': 'bad',
                                       'PYTHONPATH': 'bad', 'BASH_ENV': 'bad'}, clear=True):
            self.assertEqual(boundary.environment(), {'PATH': 'x', 'HOME': 'h', 'CODEX_HOME': 'c'})

    def test_real_positive_control_without_sandbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boundary.create_fixtures(root)
            original = boundary.content_hashes(root)
            for role in boundary.ROLES:
                checks = boundary.probes(root, role)
                child = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', boundary.PROBE,
                                        json.dumps(checks)], capture_output=True, text=True, timeout=10)
                self.assertEqual(child.returncode, 0, child.stderr)
                actual = boundary.parse_result(child.stdout, checks)
                self.assertTrue(all(row['outcome'] == 'ALLOWED' for row in actual.values()))
                self.assertGreaterEqual(len(actual), 21)
            self.assertEqual(boundary.content_hashes(root), original)

    def test_missing_file_is_error_not_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            checks = {'missing': {'path': str(Path(tmp) / 'absent'), 'operation': 'read'}}
            child = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', boundary.PROBE,
                                    json.dumps(checks)], capture_output=True, text=True, timeout=10)
            self.assertEqual(boundary.parse_result(child.stdout, checks)['missing']['outcome'], 'ERROR')

    def test_no_result_is_not_denial_success(self):
        with self.assertRaises(ValueError):
            boundary.parse_result('access denied while launching', {'x': {}})

    def test_result_keys_must_match(self):
        with self.assertRaises(ValueError):
            boundary.parse_result(boundary.PREFIX + '{}', {'x': {}})

    def test_duplicate_results_rejected(self):
        text = boundary.PREFIX + '{"x":{"outcome":"DENIED"}}'
        with self.assertRaises(ValueError):
            boundary.parse_result(text + '\n' + text, {'x': {}})

    def test_malformed_outcome_rejected(self):
        for outcome in ('PASSED', True, None):
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                boundary.parse_result(boundary.PREFIX + json.dumps({'x': {'outcome': outcome}}), {'x': {}})

    def test_synthetic_denial_result_is_parsed(self):
        text = boundary.PREFIX + '{"x":{"outcome":"DENIED","errno":13}}'
        self.assertEqual(boundary.parse_result(text, {'x': {}})['x']['outcome'], 'DENIED')

    def test_every_role_transition_and_warm_return_is_present(self):
        pairs = set(zip(boundary.ROLE_SEQUENCE, boundary.ROLE_SEQUENCE[1:]))
        self.assertTrue(set(itertools.permutations(boundary.ROLES, 2)).issubset(pairs))
        self.assertTrue(all(boundary.ROLE_SEQUENCE.count(role) >= 2 for role in boundary.ROLES))

    def test_original_prohibitions_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boundary.create_fixtures(root)
            for role in boundary.ROLES:
                checks = boundary.probes(root, role)
                for key in ('rubric_write', 'approval_write', 'evidence_write', 'unlisted_read'):
                    self.assertEqual(checks[key]['expected'], 'DENIED')
                for other in boundary.ROLES:
                    if other != role:
                        for suffix in ('private_read', 'report_write', 'nested_read', 'directory_list'):
                            self.assertEqual(checks[other + '_' + suffix]['expected'], 'DENIED')

    def test_previous_generated_outputs_are_also_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boundary.create_fixtures(root)
            (root / 'author/out/new.txt').write_text('output')
            self.assertEqual(boundary.probes(root, 'judge')['author_generated_read']['expected'], 'DENIED')

    def test_aggregate_does_not_ignore_early_failures(self):
        self.assertEqual(boundary.aggregate([{'status': 'FAIL'}, {'status': 'PASS'}], 2), 'FAIL')
        self.assertEqual(boundary.aggregate([{'status': 'ERROR'}, {'status': 'PASS'}], 2), 'ERROR')
        self.assertEqual(boundary.aggregate([{'status': 'PASS'}], 2), 'ERROR')
        self.assertEqual(boundary.aggregate([{'status': 'PASS'}] * 2, 2), 'PASS')

    def test_sequence_reuses_fixtures_and_tests_every_transition(self):
        visited = []
        def fake(cli, root, role, run_dir, index, *, native_only):
            visited.append((root, role, native_only))
            return {'role': role, 'step': index, 'status': 'PASS'}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            steps = boundary.run_sequence([], root, root, native_only=False, step_fn=fake)
        self.assertEqual([role for _, role, _ in visited], list(boundary.ROLE_SEQUENCE))
        self.assertEqual(len({str(root) for root, _, _ in visited}), 1)
        self.assertEqual(boundary.aggregate(steps, len(boundary.ROLE_SEQUENCE)), 'PASS')

    def test_sequence_stops_on_invalid_setup(self):
        def fake(cli, root, role, run_dir, index, *, native_only):
            return {'role': role, 'step': index, 'status': 'ERROR'}
        result = boundary.run_sequence([], Path('.'), Path('.'), native_only=False, step_fn=fake)
        self.assertEqual(len(result), 1)
        self.assertEqual(boundary.aggregate(result, len(boundary.ROLE_SEQUENCE)), 'ERROR')

    def test_live_step_reports_file_error_as_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boundary.create_fixtures(root)
            calls = []
            def fake(args, cwd, timeout=90, **kwargs):
                checks = json.loads(args[-1])
                native = 'sandbox' in args
                values = {k: {'outcome': v['expected'] if native else 'ALLOWED'} for k, v in checks.items()}
                if native:
                    values['author_private_read'] = {'outcome': 'ERROR'}
                else:
                    (root / 'judge/out/new.txt').write_text('baseline')
                calls.append(native)
                return subprocess.CompletedProcess(args, 0, boundary.PREFIX + json.dumps(values), '')
            with patch.object(boundary, 'execute', side_effect=fake):
                result = boundary.run_step(['codex'], root, 'judge', root, 1, native_only=True)
            self.assertEqual(result['status'], 'ERROR')
            self.assertEqual(calls, [False, True])


class GuardTests(unittest.TestCase):
    def make_root(self):
        directory = tempfile.TemporaryDirectory(prefix='webinar-boundary-')
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        boundary.create_fixtures(root)
        return root

    def test_guard_enumerates_foreign_objects_only(self):
        root = self.make_root()
        paths = guard.guarded_paths(root, 'judge')
        self.assertIn(root / 'author', paths)
        self.assertIn(root / 'author/private.txt', paths)
        self.assertIn(root / 'author/nested/private.txt', paths)
        self.assertIn(root / 'arbiter/out/existing.txt', paths)
        self.assertNotIn(root / 'judge', paths)
        self.assertFalse(any(p.is_relative_to(root / 'shared') for p in paths))
        self.assertTrue(all(p.is_relative_to(root) for p in paths))

    def test_guard_rejects_other_roots_and_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                guard.guarded_paths(Path(tmp), 'author')
        with self.assertRaises(ValueError):
            guard.guarded_paths(self.make_root(), 'unknown')

    def test_guard_rejects_symlink_escape(self):
        root = self.make_root()
        with tempfile.TemporaryDirectory() as tmp:
            link = root / 'author/escape'
            try:
                link.symlink_to(tmp, target_is_directory=True)
            except OSError:
                self.skipTest('OS does not allow test symlinks.')
            with self.assertRaises(ValueError):
                guard.guarded_paths(root, 'judge')

    def test_guard_restores_after_failed_sandbox_call(self):
        root = self.make_root()
        snapshots = [{'path': str(p), 'sddl': 'D:synthetic'} for p in guard.guarded_paths(root, 'judge')]
        history = []
        def rpc(execute, request, passed_root):
            history.append(request['action'])
            if request['action'] == 'install':
                return {'status': 'INSTALLED', 'snapshot': snapshots}
            return {'status': 'RESTORED', 'restored': len(snapshots)}
        with patch.object(guard, '_rpc', side_effect=rpc), self.assertRaisesRegex(RuntimeError, 'sandbox failed'):
            with guard.fixture_guard(root, 'judge', lambda: None):
                history.append('sandbox')
                raise RuntimeError('sandbox failed')
        self.assertEqual(history, ['install', 'sandbox', 'restore'])

    def test_guard_install_failure_never_enters_body(self):
        root = self.make_root()
        entered = False
        with patch.object(guard, '_rpc', side_effect=RuntimeError('install failed')), self.assertRaises(RuntimeError):
            with guard.fixture_guard(root, 'judge', lambda: None):
                entered = True
        self.assertFalse(entered)

    def test_guard_restore_failure_is_not_success(self):
        root = self.make_root()
        snapshots = [{'path': str(p), 'sddl': 'D:synthetic'} for p in guard.guarded_paths(root, 'judge')]
        responses = [{'status': 'INSTALLED', 'snapshot': snapshots},
                     {'status': 'RESTORED', 'restored': 0}]
        with patch.object(guard, '_rpc', side_effect=responses), self.assertRaises(RuntimeError):
            with guard.fixture_guard(root, 'judge', lambda: None):
                pass

    def test_guard_rejects_wrong_snapshot(self):
        root = self.make_root()
        responses = [{'status': 'INSTALLED', 'snapshot': [{'path': str(root / 'judge'), 'sddl': 'D:'}]},
                     {'status': 'RESTORED', 'restored': len(guard.guarded_paths(root, 'judge'))}]
        with patch.object(guard, '_rpc', side_effect=responses), self.assertRaises(RuntimeError):
            with guard.fixture_guard(root, 'judge', lambda: None):
                self.fail('Wrong snapshot must not start sandbox.')

    def test_rpc_rejects_helper_error(self):
        fake = lambda *args, **kwargs: subprocess.CompletedProcess([], 1, '{"status":"ERROR","error":"denied"}', '')
        with patch.object(guard, 'powershell_launcher', return_value=['powershell']), self.assertRaises(RuntimeError):
            guard._rpc(fake, {}, Path('.'))

    def test_rpc_uses_stdin_without_shell_interpolation(self):
        seen = []
        def fake(*args, **kwargs):
            seen.append((args, kwargs))
            return subprocess.CompletedProcess([], 0, '{"status":"RESTORED","restored":1}', '')
        with patch.object(guard, 'powershell_launcher', return_value=['powershell', '-File', 'helper.ps1']):
            guard._rpc(fake, {'path': 'A & B'}, Path('.'))
        self.assertEqual(json.loads(seen[0][1]['input_text']), {'path': 'A & B'})
        self.assertNotIn('A & B', seen[0][0][0])


if __name__ == '__main__':
    unittest.main()
