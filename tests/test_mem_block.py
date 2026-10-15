"""Memory-block regression tests; real sysbench smoke tests when installed."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "abs.sh").read_text()
HELPER = SOURCE.split("resolve_mem_block() {", 1)[1].split("\nresolve_mem_block\n", 1)[0]
HELPER = "resolve_mem_block() {" + HELPER


class MemoryBlockTests(unittest.TestCase):
    def resolve(self, block="auto", ram=2015232, threads=2):
        env = os.environ.copy()
        env.update(MEM_BLOCK=block, RAM_KIB=str(ram), T=str(threads))
        return subprocess.run(
            ["bash", "-c", 'set -euo pipefail\ndie() { echo "$2" >&2; exit 2; }\n'
             + HELPER + '\nresolve_mem_block\nprintf "%s" "$MEM_BLOCK"'],
            env=env, capture_output=True, text=True,
        )

    def test_auto_rounds_down_and_preserves_bounds(self):
        for mib, expected in [(0, 32), (31, 32), (32, 32), (48, 32),
                              (64, 64), (96, 64), (127, 64), (128, 128),
                              (192, 128), (246, 128), (255, 128),
                              (256, 256), (512, 256)]:
            for threads in (1, 2, 8):
                with self.subTest(mib=mib, threads=threads):
                    proc = self.resolve(ram=mib * 1024 * threads * 4, threads=threads)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertEqual(proc.stdout, f"{expected}M")

    def test_valid_overrides_are_preserved(self):
        for block in ("64M", "128M", "256M", "1G", "1024K", "1048576", "64m"):
            with self.subTest(block=block):
                proc = self.resolve(block)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout, block)

    def test_invalid_overrides_fail_clearly(self):
        for block in ("246M", "48M", "96M", "0", "-64M", "nope", "1.5G",
                      "064M", "64MiB", "999999999999999999999999M", "1+1"):
            with self.subTest(block=block):
                proc = self.resolve(block)
                self.assertEqual(proc.returncode, 2)
                self.assertIn("Invalid MEM_BLOCK", proc.stderr)

    @unittest.skipUnless(shutil.which("sysbench"), "sysbench not installed")
    def test_real_sysbench_accepts_resolved_auto_block(self):
        proc = self.resolve()
        self.assertEqual(proc.stdout, "128M")
        for operation in ("read", "write"):
            result = subprocess.run(
                ["sysbench", "memory", "--threads=2", "--memory-scope=local",
                 f"--memory-block-size={proc.stdout}", "--memory-total-size=256M",
                 f"--memory-oper={operation}", "--time=1", "run"],
                text=True, capture_output=True, timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("MiB/sec", result.stdout)


if __name__ == "__main__":
    unittest.main()
