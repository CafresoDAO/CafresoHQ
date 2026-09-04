#!/usr/bin/env python3
"""A vault write that never got an answer was counted as a landed note.

The refused-write fix taught run_iteration to read the HTTP status back out
of run_tool's "Vault write failed (NNN): …" message — but that shape is only
produced when the vault ANSWERED. A PUT that never gets an answer at all
(serve.py restarting under the runner, a socket timeout, connection refused
at 3am) raises URLError out of _self_call — which only converts HTTPError —
and run_tool's generic "tools never kill an iteration" handler turns it into
'Tool VAULT_NEW failed: <urlopen error …>'. vault_write_status finds no
status in that shape and returns None, and None is the SUCCESS branch:

    writes: [{'name': 'VAULT_NEW', 'path': 'Research/night/x.md', …}]
    error : None

A morning report asserting a note the vault never saw — the exact fabricated
success the write ledger exists to prevent, minted by the office's own
bookkeeping. Worse, the phantom success also ran `refused = None`, so a
GENUINE 502 refusal on an earlier hop of the same iteration was cleared by a
later write that also failed.

The fix answers in the one spelling the reader already takes apart:
run_tool's vault-write branch guards its own self-call and returns
_VAULT_FAIL_PREFIX with 503 — already the "vault is not reachable — check
Connections" door (vault_can_take_a_note sends the same word for the same
fact), so the boss reads one sentence whether the vault refused or never
picked up.

Run: python3 scripts/test_a_write_the_vault_never_heard_is_not_a_note.py
"""
import os
import re
import sys
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import night_runner as nr          # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── the run_iteration harness ────────────────────────────────────────────
# Stubs the two seams that leave the process — the brain and serve.py.
# `put_behavior` is what the office's PUT /vault/note does per attempt:
# an int answers with that status, an exception class never answers at all.
class FakeCtx(object):
    brave_key = ''


def drive(replies, put_behavior):
    puts = []

    def fake_self_call(ctx, method, path, body=None, headers=None, timeout=90):
        if path.startswith('/vault/list'):
            return 200, b'{"files": []}'
        if method == 'PUT' and path.startswith('/vault/note'):
            b = put_behavior[min(len(puts), len(put_behavior) - 1)]
            puts.append(1)
            if isinstance(b, int):
                if b == 200:
                    return 200, b'{"path": "x", "mode": "write"}'
                return b, b'{"error": "obsidian: connection refused"}'
            raise b
        return 200, b'{}'

    def fake_llm(ctx, messages, max_tokens=None):
        return replies[min(len(puts), len(replies) - 1)], 0

    real_llm, real_call = nr.llm_call, nr._self_call
    nr.llm_call, nr._self_call = fake_llm, fake_self_call
    try:
        return nr.run_iteration(
            FakeCtx(), {'vaultFolder': 'Research/night', 'topic': 't'}, 0, 3)
    finally:
        nr.llm_call, nr._self_call = real_llm, real_call


NOTE = ('[VAULT_NEW: Research/night/lead-time.md]\n'
        '# Lead time\n\nbody\n[/VAULT_NEW]')
NOTE2 = ('[VAULT_NEW: Research/night/carriers.md]\n'
         '# Carriers\n\nbody\n[/VAULT_NEW]')
CLAIM = 'Wrote 412 chars to Research/night/lead-time.md. Next: carriers.'
QUIET = 'Next iteration could explore whether the clean lanes share a carrier.'

DEAD = urllib.error.URLError(OSError(61, 'Connection refused'))
UNREACHABLE = nr.vault_refused_sentence(503)


def main():
    print('a write the vault never heard is not a note')

    # ── 1. the reproduced night ──────────────────────────────────────────
    # serve.py gone mid-run: the PUT raises, the status line still claims.
    # Before the fix: writes [path], error None — a minted clean night.
    r = drive([NOTE, CLAIM], [DEAD])
    check('a write nobody answered is not in the ledger',
          r['writes'] == [],
          [r['writes'], '— the vault never saw this note'])
    check('...and the night says which door is shut',
          r['error'] == UNREACHABLE,
          [r['error'], '— same sentence as a vault that answered 503; one '
           'fact, one wording, one door'])

    # ── 2. a quiet coworker gets the same honesty ────────────────────────
    q = drive([NOTE, QUIET], [DEAD])
    check('no claim needed — the shut door is reported anyway',
          q['writes'] == [] and q['error'] == UNREACHABLE,
          [q['writes'], q['error']])

    # ── 3. the phantom success must not clear a real refusal ────────────
    # Hop 1: the vault ANSWERS 502. Hop 2: it never answers at all. Before
    # the fix the second attempt read as success and ran `refused = None`,
    # erasing the observed 502 — and its phantom write gated off the claim
    # check too.
    two = drive([NOTE, NOTE2, CLAIM], [502, DEAD])
    check('a dead PUT does not erase an answered refusal',
          two['writes'] == [] and two['error'] == nr.vault_refused_sentence(502),
          [two['writes'], two['error']])

    # ── 4. timeouts walk the same path ───────────────────────────────────
    t = drive([NOTE, CLAIM], [OSError('timed out')])
    check('a socket timeout is a failed write, not a note',
          t['writes'] == [] and t['error'] == UNREACHABLE,
          [t['writes'], t['error']])

    # ── 5. the sentence still fits the narrowest surface ─────────────────
    check('the door fits the CLI report',
          len(UNREACHABLE) <= nr.NIGHT_ERROR_MAX,
          '%d > %d: "%s"' % (len(UNREACHABLE), nr.NIGHT_ERROR_MAX, UNREACHABLE))

    # ── 6. a vault that answers is untouched ─────────────────────────────
    ok = drive([NOTE, CLAIM], [200])
    check('a healthy night is unchanged',
          ok['error'] is None
          and [w['path'] for w in ok['writes']] == ['Research/night/lead-time.md'],
          [ok['error'], ok['writes']])
    refused = drive([NOTE, CLAIM], [502])
    check('...and an answered refusal still reads its own status',
          refused['writes'] == []
          and refused['error'] == nr.vault_refused_sentence(502),
          [refused['writes'], refused['error']])

    # ── 7. non-write tools keep their guard ──────────────────────────────
    # "tools never kill an iteration" stays true for the rest of the subset:
    # a raising read comes back as a string result, not a raise.
    real_call = nr._self_call

    def dead_call(ctx, method, path, body=None, headers=None, timeout=90):
        raise DEAD
    nr._self_call = dead_call
    try:
        out = nr.run_tool(FakeCtx(), 'VAULT_READ', 'Research/night/x.md', None)
    finally:
        nr._self_call = real_call
    check('a raising read still returns a string',
          isinstance(out, str) and 'VAULT_READ' in out, repr(out))
    check('...and is not mistaken for a refused write',
          nr.vault_write_status(out) is None, out)

    print()
    if FAILS:
        print('FAILED: %d check(s): %s' % (len(FAILS), ', '.join(FAILS)))
        sys.exit(1)
    print('all checks passed')


if __name__ == '__main__':
    main()
