#!/usr/bin/env python3
"""Critical-path regressions: curl|bash stdin mode and memory-backed targets."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "abs.sh"
REAL_DF = shutil.which("df") or "/bin/df"
CLEARED_ENV = (
    "LOGDIR", "ABS_LANG", "DIRECT", "STRICT", "SIZE", "DIR", "PROFILE", "T", "D",
    "INSTALL", "FIO_ENGINE", "JOBS", "NETWORK", "MEM_BLOCK", "FAKE_FS_TYPE",
    "FAKE_DF_PT_FAIL", "FAKE_SYSBENCH_VERSION_FAILS",
)
REQUIRED_JSON_KEYS = (
    "version", "profile", "score", "verdict", "results", "provenance",
    "target_filesystem", "system", "mode", "local_score", "network_score",
)

SYSBENCH = r'''#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then
  [ "${FAKE_SYSBENCH_VERSION_FAILS:-0}" = "1" ] && exit 1
  echo 'sysbench 1.0.20'
  exit 0
fi
case " ${*} " in
  *" memory "*)
    if [[ " ${*} " == *" --memory-oper=read "* ]]; then
      echo '102400.00 MiB transferred (30000.00 MiB/sec)'
    else
      echo '102400.00 MiB transferred (20000.00 MiB/sec)'
    fi ;;
  *) echo 'events per second: 400.00'; echo '95th percentile: 1.00' ;;
esac
'''

FIO = r'''#!/usr/bin/env python3
import json, os, sys
if '--version' in sys.argv:
    print('fio-3.33')
    raise SystemExit
if '--enghelp' in sys.argv:
    print('Available IO engines:\nlibaio\nsync')
    raise SystemExit
trace = os.environ.get('FAKE_FIO_TRACE')
if trace:
    with open(trace, 'a', encoding='utf-8') as f:
        f.write(json.dumps(sys.argv[1:]) + '\n')
args = dict(a.split('=', 1) for a in sys.argv[1:] if '=' in a)
rw = args.get('--rw', 'write')
read_iops = 10000.0 if 'read' in rw else 0.0
write_iops = 2000.0 if '--fsync' in args else (5000.0 if 'write' in rw else 0.0)
if rw == 'randrw':
    read_iops, write_iops = 10000.0, 5000.0
lat = {'clat_ns': {'percentile': {'95.000000': 1000000}}}
job = {
    'read': dict(lat, bw_bytes=read_iops * 4096, iops=read_iops),
    'write': dict(lat, bw_bytes=write_iops * 4096, iops=write_iops),
    'sync': {'lat_ns': {'percentile': {'95.000000': 1000000}}},
}
print(json.dumps({'jobs': [job]}))
'''

DF = r'''#!/usr/bin/env bash
case " $* " in
  *" -PT "*)
    [ "${FAKE_DF_PT_FAIL:-0}" = "1" ] && exit 1
    printf 'Filesystem Type 1024-blocks Used Available Capacity Mounted on\n'
    printf 'fakefs %s 1048576 0 1048576 0%% %s\n' "${FAKE_FS_TYPE:-ext4}" "${!#}"
    exit 0 ;;
esac
exec "REAL_DF_PATH" "$@"
'''.replace("REAL_DF_PATH", REAL_DF)

DD = r'''#!/usr/bin/env bash
if [ -n "${FAKE_DD_TRACE:-}" ]; then printf '%s\n' "$*" >>"$FAKE_DD_TRACE"; fi
exit 1
'''


def write_tools(bin_dir: Path) -> None:
    for name, body in (("sysbench", SYSBENCH), ("fio", FIO), ("df", DF), ("dd", DD)):
        tool = bin_dir / name
        tool.write_text(body, encoding="utf-8")
        tool.chmod(0o755)


class CriticalPathTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bin = self.root / "bin"
        self.data = self.root / "data"
        self.work = self.root / "work"
        for path in (self.bin, self.data, self.work):
            path.mkdir()
        write_tools(self.bin)
        self.fio_trace = self.root / "fio-argv.jsonl"
        self.dd_trace = self.root / "dd-argv.txt"

    def env(self, **overrides: str) -> dict[str, str]:
        env = os.environ.copy()
        for key in CLEARED_ENV:
            env.pop(key, None)
        env.update(
            PATH=f"{self.bin}{os.pathsep}{env['PATH']}",
            DIR=str(self.data),
            LOGDIR=str(self.root / "logs"),
            INSTALL="0",
            MEM_BLOCK="1M",
            FAKE_FS_TYPE="ext4",
            FAKE_FIO_TRACE=str(self.fio_trace),
            FAKE_DD_TRACE=str(self.dd_trace),
        )
        env.update(overrides)
        return env

    def run_abs(self, args: list[str], env: dict[str, str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        # stdin mode mirrors `curl | bash`: bash reads the script from stdin and $0 is "bash".
        argv = ["bash", "-s", "--", *args] if stdin is not None else [str(SCRIPT), *args]
        return subprocess.run(argv, input=stdin, cwd=self.work, env=env, text=True, capture_output=True, timeout=120)

    def load(self, path: Path) -> dict:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in REQUIRED_JSON_KEYS:
            self.assertIn(key, data, f"JSON missing {key}")
        return data

    def test_stdin_mode_finishes_with_na_provenance(self) -> None:
        out = self.root / "stdin.json"
        env = self.env(FAKE_SYSBENCH_VERSION_FAILS="1")
        proc = self.run_abs(
            ["--quick", "-n", "--no-network", "--json-file", str(out)],
            env,
            stdin=SCRIPT.read_text(encoding="utf-8"),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self.load(out)
        self.assertEqual(data["provenance"]["script_sha256"], "n/a")
        self.assertIn("sysbench", data["provenance"]["tool_versions"])
        self.assertTrue(data["results"])
        self.assertTrue((self.root / "logs" / "result.json").is_file())

    def test_file_mode_hashes_script_bytes(self) -> None:
        out = self.root / "file.json"
        proc = self.run_abs(["--quick", "-n", "--no-network", "--json-file", str(out)], self.env())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        digest = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        self.assertEqual(self.load(out)["provenance"]["script_sha256"], digest)

    def test_memory_target_skips_all_disk_writes(self) -> None:
        out = self.root / "memory.json"
        args = ["--quick", "-n", "--no-network"]
        strict = self.run_abs([*args, "--json-file", str(out), "--strict"], self.env(FAKE_FS_TYPE="tmpfs"))
        self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)
        self.assertIn("内存文件系统（tmpfs）", strict.stdout)
        self.assertFalse(self.fio_trace.exists(), "fio ran on a memory-backed target")
        self.assertFalse(self.dd_trace.exists(), "dd ran on a memory-backed target")
        data = self.load(out)
        self.assertEqual(data["target_filesystem"]["class"], "memory")
        self.assertEqual(data["target_filesystem"]["type"], "tmpfs")
        self.assertIn("memory-backed", data["target_filesystem"]["skip_reason"])
        self.assertEqual(data["score"]["status"], "partial")
        self.assertFalse(data["score"]["comparable"])
        self.assertEqual(data["verdict"]["code"], "INCOMPLETE")
        self.assertEqual(sorted(data["score"]["missing_components"]), ["disk", "fsync"])
        rows = {row["metric"]: row["result"] for row in data["results"]}
        self.assertIn("memory-backed", rows["fio disk tests"])
        self.assertNotIn("Disk sequential write", rows)

        lax = self.run_abs([*args, "--lang", "en"], self.env(FAKE_FS_TYPE="tmpfs"))
        self.assertEqual(lax.returncode, 0, lax.stdout + lax.stderr)
        self.assertIn("memory-backed filesystem (tmpfs)", lax.stdout)
        self.assertFalse(self.fio_trace.exists(), "fio ran on a memory-backed target")
        self.assertFalse(self.dd_trace.exists(), "dd ran on a memory-backed target")

    def test_unknown_filesystem_is_not_claimed_as_memory(self) -> None:
        for name in ("stat", "mount"):
            tool = self.bin / name
            tool.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
            tool.chmod(0o755)
        out = self.root / "unknown.json"
        proc = self.run_abs(
            ["--quick", "-n", "--no-network", "--json-file", str(out)],
            self.env(FAKE_DF_PT_FAIL="1"),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self.load(out)
        self.assertEqual(data["target_filesystem"]["class"], "unknown")
        self.assertEqual(data["target_filesystem"]["skip_reason"], "")
        self.assertTrue(self.fio_trace.exists(), "unknown filesystems keep normal disk tests")

    def test_persistent_filesystem_keeps_normal_scoring(self) -> None:
        # Needs roughly 615 MiB free in DIR, the same as the existing end-to-end test.
        out = self.root / "persistent.json"
        proc = self.run_abs(
            ["--quick", "-n", "--no-network", "--json-file", str(out)],
            self.env(FAKE_FS_TYPE="ext4"),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self.load(out)
        self.assertEqual(data["target_filesystem"]["class"], "persistent")
        self.assertEqual(data["score"]["status"], "full")
        self.assertTrue(self.fio_trace.exists())


if __name__ == "__main__":
    unittest.main()
