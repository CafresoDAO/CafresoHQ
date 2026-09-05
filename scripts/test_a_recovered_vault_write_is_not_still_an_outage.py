#!/usr/bin/env python3
"""A vault write that failed, then succeeded, is still reported as down.

night_runner.py's run_iteration keeps a single `refused` flag: any hop's
vault write that comes back non-200 sets it, and nothing ever clears it.
The error chain checks `if refused is not None:` first, ahead of every
other signal, so a night with two [VAULT_NEW] hops — the first hitting a
502, the second landing clean — still reports the WHOLE iteration as
"vault is not reachable — check Connections", even though `writes` holds
a real note that made it in.

This is the mirror image of the bug scripts/test_a_refused_note_is_not_a_lie.py
fixed (a failed write being blamed on the coworker instead of the vault).
That fix never considered a write recovering later in the SAME iteration —
its drive() harness only ever passes one `vault_status` for every PUT in
a run, so a fail-then-succeed sequence was never exercised.

Why this is a beta blocker and not a cosmetic mislabel: run_mission counts
any iteration with a truthy `error` toward error_streak, and three in a
row trip ERROR_STREAK_AUTO_PAUSE, aborting the rest of the scheduled
night. A vault with occasional transient hiccups (a flaky self-hosted
Obsidian REST server, a bucket with brief network blips) that keeps
recovering within each iteration will have every iteration falsely
flagged as an outage — even while genuinely saving notes — and after
three such iterations the whole night's remaining work is silently cut
short. The morning report then tells the boss to "check Connections" for
a problem that already resolved, while the same run's `writes` list
proves notes were actually saved: a direct contradiction the boss has no
way to act on.

Fix: a write that lands clears `refused` back to None, so the flag
reflects the vault's answer to the LAST attempt in the iteration, not
"did it ever say no this iteration".

Run: python3 scripts/test_a_recovered_vault_write_is_not_still_an_outage.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import night_runner as nr          # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


class FakeCtx(object):
    brave_key = ''
    # Granted on purpose: this file exercises write ACCOUNTING
    # (what lands, what's reported), not the #360 permission gate —
    # a fake that failed may_write_to_vault would fail every test
    # here for a reason none of them are about.
    agent_tools = ['vault']


def drive(replies, vault_statuses):
    """Like test_a_refused_note_is_not_a_lie.py's drive(), but takes a LIST
    of vault statuses, one per successive PUT /vault/note — so a run can
    fail its first write and succeed on a later one within one iteration."""
    calls = []

    def fake_self_call(ctx, method, path, body=None, headers=None, timeout=90):
        calls.append((method, path))
        if path.startswith('/vault/list'):
            return 200, b'{"files": []}'
        if method == 'PUT' and path.startswith('/vault/note'):
            n = sum(1 for c in calls if c[0] == 'PUT') - 1
            status = vault_statuses[min(n, len(vault_statuses) - 1)]
            if status == 200:
                return 200, b'{"path": "x", "mode": "write"}'
            return status, b'{"error": "obsidian: connection refused"}'
        return 200, b'{}'

    def fake_llm(ctx, messages, max_tokens=None):
        return replies[min(sum(1 for c in calls if c[0] == 'PUT'),
                           len(replies) - 1)], 0

    real_llm, real_call = nr.llm_call, nr._self_call
    nr.llm_call, nr._self_call = fake_llm, fake_self_call
    try:
        return nr.run_iteration(
            FakeCtx(), {'vaultFolder': 'Research/night', 'topic': 't'}, 0, 3)
    finally:
        nr.llm_call, nr._self_call = real_llm, real_call


NOTE_A = ('[VAULT_NEW: Research/night/lead-time.md]\n'
          '# Lead time\n\nbody\n[/VAULT_NEW]')
NOTE_B = ('[VAULT_NEW: Research/night/lead-time-2.md]\n'
          '# Lead time 2\n\nbody\n[/VAULT_NEW]')
DONE = 'Wrote it. Next: carriers.'


def main():
    print('a recovered vault write is not still an outage')
    src = read('night_runner.py')

    # ── 1. the fix itself: a landed write clears the flag ────────────────
    body = src[src.index('def run_iteration('):]
    body = body[:body.index('\ndef ')]
    m = re.search(
        r"if status is None:\n"
        r"((?:.*\n)*?)"
        r"                else:\n\s*refused = status",
        body)
    check('found the write-outcome branch in run_iteration', m is not None)
    if m:
        check('a successful write resets `refused` back to None — otherwise '
              'an earlier failure in the same iteration keeps blaming a '
              'vault that already recovered',
              re.search(r'refused\s*=\s*None', m.group(1)) is not None,
              m.group(1))

    # ── 2. drive the real bookkeeping: fail, then succeed ────────────────
    recovered = drive([NOTE_A, NOTE_B, DONE], vault_statuses=[502, 200])
    check('the note that actually landed is counted',
          len(recovered['writes']) == 1
          and recovered['writes'][0]['path'] == 'Research/night/lead-time-2.md',
          recovered['writes'])
    check('a write that recovered later in the SAME iteration is not still '
          'reported as a vault outage — this is the actual regression: '
          'the first hop\'s 502 used to stick for the rest of the iteration',
          recovered['error'] is None,
          [recovered['error'], '— a real note is sitting in `writes` while '
           'the office claims the vault is unreachable'])

    # ── 3. still refuses an iteration that never recovers ────────────────
    never = drive([NOTE_A, DONE], vault_statuses=[502])
    check('an iteration with no successful write is still reported as '
          'refused (the fix must not swallow a real outage)',
          never['error'] == nr.vault_refused_sentence(502), never['error'])
    check('...and nothing lands in writes', never['writes'] == [])

    # ── 4. and the reverse order still works: succeed, then fail ─────────
    thenfail = drive([NOTE_A, NOTE_B, DONE], vault_statuses=[200, 502])
    check('a write that succeeds and is THEN followed by a refusal in the '
          'same iteration still reports the refusal — `refused` tracks the '
          'last attempt, not "ever succeeded"',
          thenfail['error'] == nr.vault_refused_sentence(502), thenfail['error'])
    check('...and the earlier successful note is still counted',
          len(thenfail['writes']) == 1
          and thenfail['writes'][0]['path'] == 'Research/night/lead-time.md',
          thenfail['writes'])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
