# ABS scoring model (`abs-local-v1`)

This document records how ABS turns raw measurements into a local score and
verdict, where each constant came from, and the limits of that calibration.
It exists so the score can be audited, compared across script versions, and
re-derived from `result.json`.

## What the score is — and is not

The composite score is a **heuristic for spotting weak VPS plans**, not a
statistically calibrated benchmark. The reference constants and weights were
chosen by judgement so that a typical mid-range modern VPS lands near
component score ~1000 and total ~1200+. They have **not** been fit to a
labelled dataset of "good" and "bad" machines, and ABS publishes no error
analysis for them. Treat the absolute verdicts as informed defaults, and
prefer relative comparisons between machines run under identical settings.

## Formulas

Each component maps its measurements to 0–3000 via
`1000 * sqrt(value / reference)` (geometric mean when two inputs), then the
composite is the weighted sum. `result.json` reports the same numbers.

| Component | Weight | Formula (references in units shown) |
|---|---|---|
| CPU | 40% | `1000 * sqrt((single_eps/400) * (per_thread_eps/400))` — sysbench `cpu`, prime `CPU_PRIME` (default 20000), events/s |
| Memory | 15% | `1000 * sqrt((read/30000 MiB/s) * (write/20000 MiB/s))` — sysbench `memory`, sequential |
| Disk | 30% | `1000 * sqrt((qd1_read/10000 IOPS) * (qd1_write/5000 IOPS))` — fio 4K random, queue depth 1, single job |
| fsync | 15% | `1000 * sqrt(fsync_writes/2000 per s)` — fio 4K `randwrite --fsync=1` |

Component scores clamp at 3000 (`min(3000, ...)`).

## Verdicts

| Total score | Verdict |
|---|---|
| ≥ 1200 | KEEP — practical VPS profile looks acceptable |
| ≥ 800 | MAYBE — usable, but has notable weaknesses |
| < 800 | AVOID — weak practical VPS performance |
| any core test missing | INCOMPLETE — not comparable |

Two overrides applied after the weighted sum, so a strong average cannot
hide a broken machine:

- **Component floor**: weakest component < 500 caps the verdict at MAYBE;
  < 250 forces AVOID.
- **FULL ≠ fast**: FULL only means every core test produced data.

## Where the constants came from

Order-of-magnitude anchors for "a healthy modern VPS", not measurements
from a reference fleet:

- `400 events/s/thread` (sysbench cpu, prime 20000): typical modern dedicated
  vCPU. Shared/burstable vCPUs often land far below.
- `30000/20000 MiB/s` (memory read/write): DRAM-class sequential bandwidth;
  reachable by current server CPUs, far above cache-starved or throttled
  guests. Memory runs with `--memory-scope=local` and a per-thread working
  set (`MEM_BLOCK`, default `RAM/threads/4` clamped to 32–256 MiB) so the
  metric reflects DRAM rather than a shared hot buffer.
- `10000/5000 IOPS` (4K QD1 read/write): mid-range NVMe; SATA and
  network-backed storage are typically well under.
- `2000 writes/s` (fsync): durable-write rate where storage genuinely
  persists data vs. where flushes are absorbed by volatile cache.
- `800/1200` verdict thresholds and the `0.40/0.15/0.30/0.15` weights: chosen
  to weight CPU and 4K QD1 disk (what makes a VPS *feel* slow) above memory
  bandwidth and fsync rate; not empirically optimized.

## Comparability contract

Two scores are comparable only when run with the same: script version or
`score_model`, test mode (`--quick`/`--full`), thread count, `fio` size,
`DIRECT` setting, `CPU_PRIME`, and `MEM_BLOCK`. `result.json` records all of
these under `mode` plus a `provenance` block (script SHA-256,
sysbench/fio/python3 versions, `score_model` id) — check them before
comparing JSON files. Only `DIRECT=1` FULL local results are directly
comparable; network results never enter the score.

## Known limits

- No calibration dataset: the constants are judgement calls. If you re-run
  the same machine the score is stable, but cross-version comparisons need
  matching `score_model`.
- Burstable/shared vCPUs and steal time can depress CPU far below the 400/s
  anchor; that is a *feature* (it is what the user experiences) but means
  scores fluctuate with host load.
- OpenVZ/LXC and some virtualized storage inflate write/fsync numbers
  through host caches — ABS emits a `why` hint for these cases instead of
  silently trusting the numbers.
- The network check is a single-CDN probe (or optional iperf3 regions) and
  is informational only.

## Changing the model

Bump `score_model` in `result.json` whenever a formula, reference constant,
weight, or measured-input definition changes, and note it here. Constants
live inline in the scoring Python inside `abs.sh` (search for `abs_local_score`).
