#!/usr/bin/env python3
"""scanWorkerPayouts zeroed a worker's CURRENT accrual instead of subtracting
the SNAPSHOTTED payout amount — silently losing pay earned mid-sweep.

`src/cafresohq_state/main.mo`'s `scanWorkerPayouts` builds `due` as a
synchronous snapshot of every eligible worker's `accruedE8s` at scan start
(T0) — no `await` in that loop, so it's atomic. The second loop that
actually pays each `(p, amount)` DOES `await executeWorkerPayout(...)` on
every iteration — a real inter-canister ledger call, so meaningful
wall-clock time passes between processing worker #1 and worker #2. During
that await, `fulfill` (a separate update call) can run for a worker still
queued in `due` and add newly-earned pay to their `accruedE8s`.

The buggy code:

    patchWorker(p, func(x) { { x with accruedE8s = 0; updatedAt = now() } });

unconditionally reset `accruedE8s` to 0 when the loop finally reached that
worker — wiping out BOTH the stale snapshotted amount (which does get paid
via `amount`) AND whatever accrued after the snapshot (which does not —
it's neither paid nor left in the balance). A worker who earned 105,000
e8s but whose payout was snapshotted at 100,000 e8s before their last job
completed gets paid 100,000 and has their balance zeroed to 0 — the
5,000 e8s of real, already-earned pay simply vanishes, with no log entry
and no error surfaced anywhere.

This is the exact failure mode `restoreAccrual` (a few lines above, used
on every definitive-reject ledger error) already gets right:

    func restoreAccrual(p : Principal, amount : Nat) {
      patchWorker(p, func(x) { { x with accruedE8s = x.accruedE8s + amount } });
    };

— re-reading the CURRENT `x.accruedE8s` and adjusting by `amount`, never
overwriting it outright. `scanWorkerPayouts` was the one place in this
file that still blindly reset a running counter instead of re-reading and
adjusting it, on the same accrual field this same file's own sibling
function proves the correct pattern for.

Fix: subtract the snapshotted `amount` from the CURRENT `x.accruedE8s`
(Nat-safe: floor at 0, since a worker's own `fulfill` is the only thing
that can raise `accruedE8s` in this window, so it can only ever be >=
`amount` — but a floor costs nothing and turns a would-be trap into a
merely-stale sweep instead of a canister trap).

Run: python3 scripts/test_worker_payout_sweep_does_not_wipe_mid_sweep_accrual.py
(the moc compile check is skipped if dfx/moc aren't on PATH — the source-
shape and arithmetic-simulation checks still run everywhere)
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN_MO = ROOT / 'src' / 'cafresohq_state' / 'main.mo'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("the worker-payout sweep does not wipe accrual earned mid-sweep")
    src = MAIN_MO.read_text(encoding='utf-8')

    fn = src[src.index('func scanWorkerPayouts()'):]
    fn = fn[:fn.index('\n  // ── Search-network admin')]

    check('the old unconditional reset is gone from scanWorkerPayouts — '
          'the actual regression: `accruedE8s = 0` wiped out any pay '
          'earned between the snapshot and this worker\'s turn in the loop',
          not re.search(r'accruedE8s\s*=\s*0\s*;\s*updatedAt', fn), fn)

    check('the fix re-reads the CURRENT accrual and subtracts only the '
          'snapshotted `amount`, floored at 0',
          bool(re.search(
              r"accruedE8s\s*=\s*if\s*\(x\.accruedE8s\s*>=\s*amount\)\s*"
              r"\{\s*x\.accruedE8s\s*-\s*amount\s*\}\s*else\s*\{\s*0\s*\}",
              fn)))

    check("restoreAccrual — the sibling function this fix mirrors — still "
          "uses its own re-read-and-add pattern unchanged (a regression "
          "guard: this fix should not have touched that function at all)",
          re.search(
              r'func restoreAccrual\(p : Principal, amount : Nat\) \{\s*\n'
              r'\s*patchWorker\(p, func\(x\) \{ \{ x with '
              r'accruedE8s = x\.accruedE8s \+ amount \} \}\);',
              src) is not None)

    check("the snapshot loop (`due.add`) still has no `await` between "
          "reading accruedE8s and the payout loop — if that ever changed, "
          "the whole bug analysis (and this fix's rationale) would need "
          "re-deriving",
          not re.search(
              r'for \(\(p, w\) in pOps\.entries\(workers\)\) \{[^}]*?'
              r'await', fn))

    # ── Arithmetic simulation of the fixed formula ───────────────────────
    # Mirrors the exact reported scenario: a worker snapshotted at 100_000,
    # who earns another 5_000 via `fulfill` before their turn in the payout
    # loop, must retain that 5_000 — not lose it to an unconditional reset.
    def fixed_formula(current_accrued, amount):
        return current_accrued - amount if current_accrued >= amount else 0

    def buggy_formula(current_accrued, amount):
        return 0

    snapshot_amount = 100_000
    accrued_at_payout_time = 105_000   # fulfill() added 5_000 mid-sweep
    check('fixed formula: a worker who earned MORE after the snapshot keeps '
          'the difference (5,000 e8s), not 0',
          fixed_formula(accrued_at_payout_time, snapshot_amount) == 5_000,
          fixed_formula(accrued_at_payout_time, snapshot_amount))
    check('...whereas the buggy formula (documented here, not run in prod) '
          'would have wiped it to 0 — confirms this is a real behavior '
          'change, not a no-op refactor',
          buggy_formula(accrued_at_payout_time, snapshot_amount) == 0)

    check('a worker with no fulfillment between snapshot and payout still '
          'nets exactly 0 (unchanged behavior for the common case)',
          fixed_formula(100_000, 100_000) == 0)

    check('the Nat-safe floor holds even in a hypothetical corrective '
          'scenario where current accrual is somehow below the snapshot '
          '(should never happen in practice, but must not trap)',
          fixed_formula(40_000, 100_000) == 0)

    # ── Genuine compile: moc must accept the fixed function ──────────────
    has_dfx = bool(shutil.which('dfx'))
    check('dfx is on PATH (needed to genuinely compile main.mo with moc)',
          has_dfx, 'skipping the compile check')
    if has_dfx:
        pinned = (ROOT / '.dfx-version')
        env = dict(os.environ)
        if pinned.exists():
            env['DFX_VERSION'] = pinned.read_text(encoding='utf-8').strip()
        r = subprocess.run(
            ['dfx', 'build', 'cafresohq_state', '--check'],
            cwd=ROOT, capture_output=True, text=True, timeout=180, env=env)
        out = (r.stdout or '') + (r.stderr or '')
        check('moc compiles main.mo with the fix applied, no errors '
              '(warnings — e.g. the expected "operator may trap" on the '
              'Nat-safe floor — are fine, this only fails on a real error)',
              r.returncode == 0 and 'error' not in out.lower(),
              out[-1500:])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
