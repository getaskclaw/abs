"""Safety regressions: process isolation and aggregate memory budgets."""
import os
import importlib.util
import signal
import time
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / 'abs.sh').read_text()


def helper(start, end):
    return start + SOURCE.split(start, 1)[1].split(end, 1)[0]


class ResourceSafetyTests(unittest.TestCase):
    def test_timeout_stops_descendants(self):
        timeout = helper('abs_timeout() ', '\nrun_log() {')
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / 'survived'
            script = timeout + '''
if run_timed 1 bash -c '(trap "" TERM; sleep 3; echo survived > "$1") & wait' bash "$1"; then
  exit 1
fi
sleep 4
'''
            p = subprocess.run(['bash', '-c', script, 'bash', str(marker)],
                               capture_output=True, text=True, timeout=15)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertFalse(marker.exists(), 'descendant survived timeout')

    def test_timeout_does_not_kill_calling_shell(self):
        timeout = helper('abs_timeout() ', '\nrun_log() {')
        p = subprocess.run(['bash', '-c', timeout + '\nif run_timed 1 sleep 10; then exit 1; fi\necho alive\n'],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('alive', p.stdout)

    def test_success_and_error_status(self):
        timeout = helper('abs_timeout() ', '\nrun_log() {')
        p = subprocess.run(['bash', '-c', timeout + '\nrun_timed 2 true; echo success=$?; if run_timed 2 bash -c "exit 7"; then :; else echo error=$?; fi'],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('success=0', p.stdout)
        self.assertIn('error=7', p.stdout)

    def test_timeout_cannot_be_reported_as_success(self):
        timeout = helper('abs_timeout() ', '\nrun_log() {')
        p = subprocess.run(['bash', '-c', timeout + '\nif run_timed 1 bash -c \'trap "exit 0" TERM; sleep 5\'; then echo BAD_SUCCESS; else echo timeout=$?; fi'],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn('BAD_SUCCESS', p.stdout)
        self.assertIn('timeout=124', p.stdout)

    def test_top_level_term_stops_workload(self):
        script_path = Path(__file__).resolve().parents[1] / 'abs.sh'
        spec = importlib.util.spec_from_file_location('fixtures', script_path.parent / 'tests/test_abs.py')
        assert spec is not None and spec.loader is not None
        fixtures = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixtures)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            fixtures.write_fake_tools(bin_dir)
            (bin_dir / 'sysbench').write_text('''#!/usr/bin/env bash
if [ "${1:-}" = --version ]; then echo 'sysbench 1.0.20'; exit; fi
(trap '' TERM; touch "$READY"; sleep 4; touch "$MARKER") & wait
''')
            env = os.environ.copy()
            env.update(PATH=str(bin_dir)+':'+env['PATH'], DIR=str(root/'disk'),
                       LOGDIR=str(root/'logs'), INSTALL='0', NETWORK='0', T='2',
                       READY=str(root/'ready'), MARKER=str(root/'marker'))
            with (root/'output').open('w') as out:
                proc = subprocess.Popen(['bash', str(script_path), '-n', '--no-network'],
                                        env=env, stdout=out, stderr=out, start_new_session=True)
                try:
                    deadline = time.monotonic() + 10
                    while not (root/'ready').exists() and proc.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertTrue((root/'ready').exists())
                    proc.send_signal(signal.SIGTERM)
                    self.assertEqual(proc.wait(timeout=8), 143)
                    time.sleep(4)
                    self.assertFalse((root/'marker').exists())
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()

    def test_cgroup_v1_v2_and_ancestor_limits(self):
        limit = helper('memory_limit_kib() {', '\nMEM_RAM_KIB=')
        for version in (1, 2):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                mount = root / 'mount'
                child = mount / 'child'
                child.mkdir(parents=True)
                name = 'memory.max' if version == 2 else 'memory.limit_in_bytes'
                (mount / name).write_text(str(256 * 1024**2))
                (child / name).write_text('max' if version == 2 else str(2**63 - 4096))
                groups = root / 'cgroup'
                groups.write_text('0::/child\n' if version == 2 else '5:memory:/child\n')
                mounts = root / 'mountinfo'
                fs = 'cgroup2 cgroup rw' if version == 2 else 'cgroup cgroup rw,memory'
                mounts.write_text(f'1 0 0:1 / {mount} rw - {fs}\n')
                p = subprocess.run(['bash', '-c', limit + '\nmemory_limit_kib "$1" "$2"',
                                    'bash', str(groups), str(mounts)], text=True, capture_output=True, timeout=5)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(p.stdout.strip(), '262144')
                usage_name = 'memory.current' if version == 2 else 'memory.usage_in_bytes'
                (mount / usage_name).write_text(str(240 * 1024**2))
                p = subprocess.run(['bash', '-c', limit + '\nmemory_limit_kib "$1" "$2"',
                                    'bash', str(groups), str(mounts)], text=True, capture_output=True, timeout=5)
                self.assertEqual(p.stdout.strip(), '32768')
                (mount / name).write_text('0')
                p = subprocess.run(['bash', '-c', limit + '\nmemory_limit_kib "$1" "$2"',
                                    'bash', str(groups), str(mounts)], text=True, capture_output=True, timeout=5)
                self.assertEqual(p.stdout.strip(), '0')

    def test_memory_auto_never_exceeds_budget(self):
        resolve = helper('resolve_mem_block() {', '\nresolve_mem_block\n')
        for ram_mib, threads in ((1024, 64), (256, 8), (2048, 2), (0, 2)):
            with self.subTest(ram_mib=ram_mib, threads=threads):
                env = os.environ.copy()
                env.update(MEM_BLOCK='auto', RAM_KIB=str(ram_mib * 1024), T=str(threads))
                p = subprocess.run(['bash', '-c', 'die() { exit 2; };\n' + resolve + '\nresolve_mem_block\nprintf "%s" "$MEM_BLOCK"'],
                                   env=env, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                if p.stdout:
                    self.assertLessEqual(int(p.stdout[:-1]) * threads, ram_mib // 4)


if __name__ == '__main__':
    unittest.main()
