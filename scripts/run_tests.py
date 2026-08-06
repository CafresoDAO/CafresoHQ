#!/usr/bin/env python3
"""Run every CafresoHQ Python test suite and aggregate the results.

The suites are hand-rolled (`FAILS = []`, `check(name, cond)`, print a summary)
rather than pytest, and several of them print "N FAILED" while still exiting 0.
That is why CI ran one file for so long and reported green: there was nothing
combining the results. This runner is the missing piece — it treats a suite as
failed if it exits non-zero OR prints a failure summary, and it exits non-zero
if any suite failed.

Usage:
    python3 scripts/run_tests.py            # run everything
    python3 scripts/run_tests.py --fast     # skip the slow deadline suites
    python3 scripts/run_tests.py -k worker  # only suites matching a substring
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (path, timeout_seconds, slow?) — the deadline-salvage suites deliberately
# simulate 75s-blocking gateways and 90s stalls, so they need real wall clock.
SUITES: list[tuple[str, int, bool]] = [
    ('scripts/test_security_boundaries.py',          60,  False),
    ('scripts/test_durability_retry.py',             60,  False),
    ('scripts/test_night_grammar.py',                60,  False),
    ('scripts/test_backend_resolve.py',              60,  False),
    ('scripts/test_artifacts.py',                    60,  False),
    ('scripts/test_experience.py',                   60,  False),
    ('scripts/test_brave_ledger.py',                 60,  False),
    ('scripts/test_gap_cron.py',                     60,  False),
    ('scripts/test_deep_research.py',               600,  True),
    ('scripts/test_search_worker.py',               600,  True),
    ('search_worker_service/scripts/test_worker.py', 600, True),
]

# A suite that exits 0 but says so in its summary is still a failure.
FAIL_RE = re.compile(r'\b(\d+)\s+FAILED\b|\b(\d+)\s+failure\(s\)', re.I)


def _summary_failures(output: str) -> int:
    """Largest failure count named in the output, 0 if none."""
    worst = 0
    for m in FAIL_RE.finditer(output):
        for g in m.groups():
            if g and g.isdigit():
                worst = max(worst, int(g))
    return worst


def run(path: str, timeout: int) -> tuple[bool, str, str]:
    full = ROOT / path
    if not full.is_file():
        return False, 'MISSING', ''
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(full)],
            cwd=ROOT, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f'TIMEOUT after {timeout}s', ''
    out = (proc.stdout or '') + (proc.stderr or '')
    secs = time.monotonic() - started
    named = _summary_failures(out)
    if proc.returncode != 0:
        return False, f'exit {proc.returncode} ({secs:.0f}s)', out
    if named:
        # The suite printed failures but exited 0 — the bug this runner exists for.
        return False, f'{named} failed, but exited 0 ({secs:.0f}s)', out
    return True, f'ok ({secs:.0f}s)', out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fast', action='store_true',
                    help='skip the slow deadline-salvage suites')
    ap.add_argument('-k', dest='match', default='',
                    help='only run suites whose path contains this substring')
    args = ap.parse_args()

    selected = [(p, t) for p, t, slow in SUITES
                if not (args.fast and slow) and args.match in p]
    if not selected:
        print('no suites matched')
        return 1

    failures: list[tuple[str, str, str]] = []
    for path, timeout in selected:
        print(f'──→ {path}', flush=True)
        ok, status, out = run(path, timeout)
        print(f'    {"PASS" if ok else "FAIL"}  {status}', flush=True)
        if not ok:
            failures.append((path, status, out))

    print()
    print(f'{len(selected) - len(failures)}/{len(selected)} suites passed')
    for path, status, out in failures:
        print(f'\n{"=" * 70}\nFAILED: {path}  ({status})\n{"=" * 70}')
        print('\n'.join(out.splitlines()[-40:]) if out else '(no output)')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
