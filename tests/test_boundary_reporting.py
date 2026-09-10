"""Reporting regressions. No real Codex, sandbox, ACL changes or API calls."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_codex_boundary as boundary


class ReportingTests(unittest.TestCase):
    def checks(self):
        return {'author_generated_read': {'path': 'synthetic/author/out/new.txt',
                'operation': 'read', 'expected': 'DENIED'}}

    def result(self, outcome='ALLOWED', code=0):
        row = {'outcome': outcome}
        if outcome == 'DENIED':
            row.update(errno=13, winerror=5, exception='PermissionError', message='Access denied')
        if outcome == 'ERROR':
            row.update(errno=17, winerror=183, exception='FileExistsError', message='File exists')
        text = boundary.PREFIX + json.dumps({'author_generated_read': row})
        return subprocess.CompletedProcess([], code, text, 'synthetic stderr')

    def test_allowed_positive_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = boundary.check_positive_control(self.result(), self.checks(), 'judge', root, '02-judge')
            self.assertEqual(value['author_generated_read']['outcome'], 'ALLOWED')
            self.assertTrue((root / '02-judge-baseline.json').is_file())

    def test_denied_positive_control_has_exact_operation_and_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(boundary.BoundaryStepError) as caught:
                boundary.check_positive_control(self.result('DENIED'), self.checks(), 'judge', root, '02-judge')
            failure = caught.exception.details['control_failures'][0]
            self.assertEqual(caught.exception.stage, 'positive_control')
            self.assertEqual(failure['check'], 'author_generated_read')
            self.assertEqual(failure['path'], 'synthetic/author/out/new.txt')
            self.assertEqual(failure['operation'], 'read')
            self.assertEqual((failure['errno'], failure['winerror']), (13, 5))
            self.assertEqual((failure['expected'], failure['sandbox_expected']), ('ALLOWED', 'DENIED'))
            self.assertEqual(failure['exception'], 'PermissionError')
            self.assertIn('DENIED', (root / '02-judge-baseline-stdout.log').read_text())

    def test_file_exists_is_not_relabelled_access_denied(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(boundary.BoundaryStepError) as caught:
            boundary.check_positive_control(self.result('ERROR'), self.checks(), 'judge', Path(tmp), '02-judge')
        row = caught.exception.details['control_failures'][0]
        self.assertEqual((row['outcome'], row['exception']), ('ERROR', 'FileExistsError'))

    def test_nonzero_exit_is_error_even_with_allowed_rows(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(boundary.BoundaryStepError) as caught:
            boundary.check_positive_control(self.result(code=1), self.checks(), 'judge', Path(tmp), '02-judge')
        self.assertEqual(caught.exception.details['baseline_exit_code'], 1)
        self.assertEqual(caught.exception.details['control_failures'], [])

    def test_invalid_response_retains_both_raw_logs(self):
        result = subprocess.CompletedProcess([], 1, 'not json', 'launcher error')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(boundary.BoundaryStepError) as caught:
                boundary.check_positive_control(result, self.checks(), 'judge', root, '02-judge')
            self.assertEqual(caught.exception.stage, 'positive_control')
            self.assertEqual((root / '02-judge-baseline-stderr.log').read_text(), 'launcher error')
            self.assertEqual((root / '02-judge-baseline-stdout.log').read_text(), 'not json')

    def test_failed_second_step_preserves_pass_and_stops_sequence(self):
        progress = []
        snapshots = []
        visits = []
        def step(cli, root, role, run_dir, index, *, native_only):
            visits.append(role)
            if role == 'judge':
                raise boundary.BoundaryStepError('Positive control failed', stage='positive_control',
                    details={'control_failures': [{'check': 'author_generated_read', 'outcome': 'DENIED'}]})
            return {'role': role, 'step': index, 'status': 'PASS'}
        with redirect_stdout(io.StringIO()):
            result = boundary.run_sequence([], Path('.'), Path('.'), native_only=False,
                steps=progress, step_fn=step, checkpoint=lambda rows: snapshots.append(json.loads(json.dumps(rows))))
        self.assertIs(result, progress)
        self.assertEqual(visits, ['author', 'judge'])
        self.assertEqual([row['status'] for row in result], ['PASS', 'ERROR'])
        self.assertEqual([len(snapshot) for snapshot in snapshots], [1, 2])
        report = boundary.concise_report({'steps': result, 'filesystem_probe': 'ERROR', 'isolation_verified': False})
        self.assertEqual(report['steps_passed'], 1)
        self.assertEqual(report['steps_completed'], 2)
        self.assertEqual(report['steps_expected'], 7)
        self.assertEqual(report['step_errors'][0]['stage'], 'positive_control')
        self.assertFalse(report['isolation_verified'])
        self.assertEqual(boundary.aggregate(result, 7), 'ERROR')

    def test_unstructured_exception_is_recorded_not_lost(self):
        def step(cli, root, role, run_dir, index, *, native_only):
            if index == 2:
                raise RuntimeError('restore failed')
            return {'role': role, 'step': index, 'status': 'PASS'}
        with redirect_stdout(io.StringIO()):
            rows = boundary.run_sequence([], Path('.'), Path('.'), native_only=True, step_fn=step)
        self.assertEqual([row['status'] for row in rows], ['PASS', 'ERROR'])
        self.assertEqual(rows[-1]['message'], 'restore failed')

    def test_timeout_stops_without_retries(self):
        calls = []
        def step(*args, **kwargs):
            calls.append(True)
            raise subprocess.TimeoutExpired(['synthetic-cli'], 90)
        with redirect_stdout(io.StringIO()):
            rows = boundary.run_sequence([], Path('.'), Path('.'), native_only=True, step_fn=step)
        self.assertEqual(len(calls), 1)
        self.assertEqual(rows[0]['exception'], 'TimeoutExpired')
        self.assertEqual(rows[0]['status'], 'ERROR')

    def test_checkpoint_failure_keeps_in_memory_progress(self):
        progress = []
        def checkpoint(rows):
            raise PermissionError('Cannot write progress')
        def step(cli, root, role, run_dir, index, *, native_only):
            return {'role': role, 'step': index, 'status': 'PASS'}
        with self.assertRaises(PermissionError):
            boundary.run_sequence([], Path('.'), Path('.'), native_only=True, step_fn=step,
                                  steps=progress, checkpoint=checkpoint)
        self.assertEqual(len(progress), 1)
        self.assertEqual(progress[0]['role'], 'author')

    def test_interrupt_preserves_previous_step_in_shared_report(self):
        progress = []
        def step(cli, root, role, run_dir, index, *, native_only):
            if index == 2:
                raise KeyboardInterrupt()
            return {'role': role, 'step': index, 'status': 'PASS'}
        with redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            boundary.run_sequence([], Path('.'), Path('.'), native_only=True, step_fn=step, steps=progress)
        self.assertEqual(len(progress), 1)
        self.assertEqual(boundary.aggregate(progress, 7), 'ERROR')

    def test_existing_progress_cannot_be_used_as_resume(self):
        with self.assertRaises(ValueError):
            boundary.run_sequence([], Path('.'), Path('.'), native_only=True, steps=[{'status': 'PASS'}])

    def test_failed_baseline_never_launches_guard_or_sandbox(self):
        with tempfile.TemporaryDirectory(prefix='webinar-boundary-') as tmp:
            root = Path(tmp)
            boundary.create_fixtures(root)
            def execute(args, cwd, timeout=90, **kwargs):
                checks = json.loads(args[-1])
                rows = {key: {'outcome': 'ALLOWED'} for key in checks}
                rows['own_private_read'] = {'outcome': 'DENIED', 'errno': 13}
                return subprocess.CompletedProcess(args, 0, boundary.PREFIX + json.dumps(rows), '')
            with patch.object(boundary, 'execute', side_effect=execute) as execute_mock, \
                 patch.object(boundary, 'fixture_guard') as guard_mock, \
                 self.assertRaises(boundary.BoundaryStepError):
                boundary.run_step(['codex'], root, 'judge', root, 2, native_only=False)
            self.assertEqual(execute_mock.call_count, 1)
            guard_mock.assert_not_called()

    def test_real_missing_file_error_includes_errno_and_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            checks = {'missing': {'path': str(Path(tmp) / 'missing.txt'), 'operation': 'read', 'expected': 'DENIED'}}
            result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', boundary.PROBE,
                                     json.dumps(checks)], capture_output=True, text=True, timeout=10)
        row = boundary.parse_result(result.stdout, checks)['missing']
        self.assertEqual(row['outcome'], 'ERROR')
        self.assertEqual(row['exception'], 'FileNotFoundError')
        self.assertEqual(row['errno'], 2)
        self.assertIn('missing.txt', row['message'])

    def test_atomic_report_replaces_existing_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'progress.json'
            boundary.save_report(path, {'steps': [{'status': 'PASS'}]})
            boundary.save_report(path, {'steps': [{'status': 'PASS'}, {'status': 'ERROR'}]})
            self.assertEqual(len(json.loads(path.read_text())['steps']), 2)
            self.assertFalse(path.with_suffix('.json.tmp').exists())


if __name__ == '__main__':
    unittest.main()
