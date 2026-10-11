# ABS — AskClaw VPS Benchmark

[简体中文](README.md)

Run it on a Linux VPS before you rent or renew — it tells you whether the CPU is fast, the memory is adequate, and the disk can actually write. ABS measures all of that, produces a score, and gives one verdict: **KEEP**, **MAYBE**, **AVOID**, or **INCOMPLETE** (some test didn't run, so don't judge by that score).

## Run

```bash
curl -fsSL https://askclaw.top/abs.sh | bash
```

Terminal output defaults to Chinese. A typical run finishes within three minutes after dependencies are installed. ABS may install `sysbench`, `fio`, `python3`, and `curl` via `sudo`.

```bash
# English output
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --lang en

# Do not install missing tools
curl -fsSL https://askclaw.top/abs.sh | bash -s -- -n
```

> `curl | bash` executes downloaded code directly. To inspect the script first:
>
> ```bash
> curl -fsSLo abs.sh https://askclaw.top/abs.sh
> less abs.sh
> bash abs.sh --lang en
> ```

## Reading the result

English mode keeps the stable machine codes:

```text
==================== ABS RESULT ====================
SCORE   : FULL 1568 (local only; network reference 136)
VERDICT : MAYBE - disk component is weak (component score 306); weak durable-write/fsync
LOCAL   : FULL 1568 (local only: cpu,mem,disk,fsync; network excluded)
NETWORK : SANITY 136 (Cloudflare HTTP; reference only, not in score)
====================================================
```

- **FULL** = every core test ran (does not mean fast)
- **PARTIAL - not comparable** = some tests failed; don't compare this score to other machines
- **KEEP / MAYBE / AVOID** = the recommendation, based on the local score plus a weakest-component floor
- **INCOMPLETE** = CPU, memory, disk, or fsync data is missing

## What it measures

- **CPU**: single-thread and all-thread throughput
- **Memory**: sequential read and write
- **Disk**: sequential, 4K random at QD1 (queue depth 1 — close to typical scattered small I/O), and multi-job pressure
- **fsync**: durable 4K writes — what actually reaches persistent storage, not what merely looks written
- **Network**: a short Cloudflare reference check, **never counted in the score**

```text
score = 40% CPU + 15% memory + 30% 4K QD1 disk + 15% fsync
```

There's also a floor rule: any component score below 250 forces `AVOID`; below 500 caps the verdict at `MAYBE`. One bad weak spot drags the whole result.

Formulas, reference constants, applicability limits, and known caveats live in [docs/scoring.md](docs/scoring.md).

## Common commands

```bash
# Quick check, about 60 seconds
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --quick

# Full test, about 5–8 minutes
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --full

# Skip the network check (local score stays valid)
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --no-network

# Write the result to JSON
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --json-file result.json

# Broader network picture: Cloudflare + 3 public iperf3 regions
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --network-full
```

Every option: `bash abs.sh --lang en --help`

## Comparing two VPSes

Two scores are only directly comparable when **all** of these match:

- Same ABS version
- Same profile (`--quick` / default / `--full`)
- Same thread count (`-t`)
- Same fio test size (`-z`)
- Same `DIRECT` setting — `DIRECT=1` (default) bypasses the filesystem cache and measures the real disk; `DIRECT=0` goes through the cache, inflates numbers, and **cannot be compared against DIRECT=1**
- Both runs are `FULL`; if either is `PARTIAL`, don't compare

## Terminal language vs. machine output

- Terminal display defaults to Chinese; use `--lang en` or `ABS_LANG=en` for English
- `results.tsv` metric names and `result.json` fields and values stay in English for scripting
- Switching language never changes the score or the file formats

## If dependency installation fails

ABS prints a short reason, a repair hint when known, and the log path, then keeps going and produces an `INCOMPLETE` result instead of silently dying. On an interactive terminal it attaches `sudo` to `/dev/tty`, so `curl | bash` can still prompt for a password; headless runs use non-interactive sudo and fail fast. ABS does not run system-repair commands such as `dpkg --configure -a` on its own.

## What the network check does

The default is a Cloudflare sanity check only:

- Downloads 10 MB from Cloudflare
- Uploads 5 MB of all-zero data (synthetic, not a real file)
- 45-second timeout per attempt, one automatic retry

For a broader network picture, use `--network-full` or `--network-yabs` to add public iperf3 nodes.

## Safety and file locations

- ABS **never uploads results**
- Logs live in a private random `/tmp/abs.*` directory
- Disk test files go to a separate temporary directory and are removed afterward
- Pre-existing `abs.test*` and `abs-dd.test` files are **not** deleted
- If `fio` is missing, a rough `dd` check runs as a fallback but **is not scored**
- Minimal Alpine images need bash first: `apk add bash`

**When GitHub Raw is unreachable from China**, use the jsDelivr mirror:

```bash
curl --resolve cdn.jsdelivr.net:443:104.16.175.226 \
  -fsSL https://cdn.jsdelivr.net/gh/getaskclaw/abs@main/abs.sh | bash -s -- -n
```

## Glossary

| Term | Plain meaning |
|---|---|
| `fsync` | Forces data to actually hit the disk, not just the memory cache. It's what a database commit or file save really needs |
| `QD1` | Queue depth 1 — one I/O request at a time, matching typical scattered small reads/writes |
| `p95` | 95th-percentile latency — 95% of requests finish faster than this; shows the worst-tail speed |
| `DIRECT` | fio's direct mode: 1 = bypass OS cache and measure real disk; 0 = through the cache (numbers get inflated) |
| `OpenVZ` | A virtualization type; its disk numbers can be cache-inflated, verify with `--full` |

## Development

```bash
python3 -m unittest -v tests/test_abs.py
```

GitHub Actions runs the suite on every push and pull request.

## License

MIT
