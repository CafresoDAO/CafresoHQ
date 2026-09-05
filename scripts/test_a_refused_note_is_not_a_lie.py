#!/usr/bin/env python3
"""The vault turned the note away, and the office called the coworker a liar.

The night shift's whole deliverable is notes. `run_tool` already knew when
one failed to land — it returns "Vault write failed (502): …" — and
`run_iteration` threw that away, keeping only the fact that the write
ledger stayed empty. Two things followed, both measured 2026-08-16 on
office 9261 with the vault pointed at a closed Obsidian REST and a canned
brain on 9236 doing exactly as instructed:

  The coworker emitted a real [VAULT_NEW: Research/night/…], the vault
  answered 502, and the run recorded

      writes: [], error: 'said it saved a note, nothing reached the vault'

  which is the office blaming a coworker for the office's own shut door.
  Nothing in that reply was untrue: they were ordered to file, they filed.

  The same run with a status line that made no claim recorded

      writes: [], error: None

  a clean night with an empty vault. And because only an error breaks the
  streak, a vault that is down at 1am is not noticed until the duration
  runs out — every iteration paying for a deliverable that is discarded on
  arrival.

The fix reads the status back out and puts it FIRST in the error chain: it
is the only branch there resting on an observed HTTP status rather than on
reading the reply's prose, and the two claim checks below it describe its
consequences rather than its cause.

Two sentences, because there are two doors. 502/503 is the vault itself
(Obsidian shut, bucket unreachable, nothing configured) and the boss fixes
that in Connections. Anything else came back from a vault that answered,
so the path is the suspect — sending the boss to Connections for a
rejected filename would be the wrong door twice over.

Run: python3 scripts/test_a_refused_note_is_not_a_lie.py
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


def strip_py_comments(src):
    """Every scan below runs on code. The prose in this file's own fix
    explains the defect at length and would satisfy half these checks on
    its own."""
    return re.sub(r'^\s*#.*$', '', src, flags=re.M)


# ── the run_iteration harness ────────────────────────────────────────────
# Stubs the two seams that leave the process — the brain and serve.py — and
# runs the real bookkeeping. `vault_status` is what the office's own PUT
# /vault/note would answer.
class FakeCtx(object):
    brave_key = ''
    # Granted on purpose: this file exercises write ACCOUNTING
    # (what lands, what's reported), not the #360 permission gate —
    # a fake that failed may_write_to_vault would fail every test
    # here for a reason none of them are about.
    agent_tools = ['vault']

    def current_agent_tools(self):
        # Real NightContext.current_agent_tools() re-asks a live lookup
        # when #370 wired one; this fake carries no lookup and no agentId,
        # so it falls back to the same plain snapshot NightContext falls
        # back to when it wasn't given one either.
        return self.agent_tools


def drive(replies, vault_status=200):
    calls = []

    def fake_self_call(ctx, method, path, body=None, headers=None, timeout=90):
        calls.append((method, path))
        if path.startswith('/vault/list'):
            return 200, b'{"files": []}'
        if method == 'PUT' and path.startswith('/vault/note'):
            if vault_status == 200:
                return 200, b'{"path": "x", "mode": "write"}'
            return vault_status, b'{"error": "obsidian: connection refused"}'
        return 200, b'{}'

    # `calls` doubles as the hop counter: reply[0] until a write has been
    # attempted, reply[1] after — the same order the real hop loop produces.
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


NOTE = ('[VAULT_NEW: Research/night/lead-time.md]\n'
        '# Lead time\n\nbody\n[/VAULT_NEW]')
CLAIM = 'Wrote 412 chars to Research/night/lead-time.md. Next: carriers.'
QUIET = 'Next iteration could explore whether the clean lanes share a carrier.'


def main():
    print('a refused note is not a lie')
    src = strip_py_comments(read('night_runner.py'))

    # ── 1. one writer, one reader ────────────────────────────────────────
    # The failure string is written for the model to read and taken apart
    # for the boss. A second hand-rolled startswith() somewhere else is how
    # the two drift until a refused write counts as a note again.
    hand = [l.strip() for l in src.splitlines()
            if re.search(r"""["']Vault write failed""", l)
            and not l.startswith('_VAULT_FAIL_PREFIX =')]
    check('the failure message has a single spelling',
          not hand,
          f'{hand} — build it from _VAULT_FAIL_PREFIX and read it back with '
          'vault_write_status; the literal appearing twice is the drift')
    check('the write ledger asks the reader, not the string',
          re.search(r'status = vault_write_status\(result\)', src) is not None
          and re.search(r'if status is None:\s*\n\s*writes\.append', src) is not None,
          'a refused write must not land in `writes`')

    # ── 2. the observed fact outranks the inferred one ───────────────────
    body = src[src.index('def run_iteration('):]
    body = body[:body.index('\ndef ')]
    order = [m.group(1) for m in re.finditer(
        r'\n    (?:el)?if (refused is not None|reached|_CLAIMS_A_PUBLISH_RE'
        r'|not writes and _CLAIMS_A_WRITE_RE)', body)]
    check('the error chain was found', len(order) == 4, order)
    check('the refused write is the first thing the night reports',
          order and order[0] == 'refused is not None',
          [order, '— every branch after it is describing the same night; '
           'this is the only one holding a status code'])

    # ── 3. the two sentences ─────────────────────────────────────────────
    unreachable = nr.vault_refused_sentence(502)
    rejected = nr.vault_refused_sentence(400)
    check('an unreachable vault names the screen that fixes it',
          'Connections' in unreachable, unreachable)
    check('a vault that answered and said no does not',
          'Connections' not in rejected and 'path' in rejected, rejected)
    check('...and 503 is the same door as 502',
          nr.vault_refused_sentence(503) == unreachable,
          [nr.vault_refused_sentence(503), unreachable,
           '— "no backend configured" and "backend not answering" are one '
           'screen to the boss'])
    check('...and an unknown status falls to the safer of the two',
          nr.vault_refused_sentence(None) == rejected
          and nr.vault_refused_sentence(500) == rejected,
          'naming Connections for a failure that is not about Connections '
          'is the wrong door, and the wrong door is this ledger\'s §5')
    for label, s in (('unreachable', unreachable), ('rejected', rejected)):
        check(f'the {label} sentence fits the narrowest surface',
              len(s) <= nr.NIGHT_ERROR_MAX,
              f'{len(s)} > {nr.NIGHT_ERROR_MAX}: "{s}" — the CLI report '
              'slices, and a truncated door is no door')
        check(f'...says what happened AND what to do ({label})',
              '—' in s, [s, '§7'])
        check(f'...in office words ({label})',
              not re.search(r'[A-Z]{2,}|_|\b\d{3}\b', s),
              [s, '§6: no VAULT_NEW, no 502'])

    # ── 4. reading the status back ───────────────────────────────────────
    f = nr.vault_write_status
    check('a refused write gives up its status',
          f('Vault write failed (502): obsidian: connection refused') == 502)
    check('...and a successful one has none',
          f('Wrote 284 chars → Research/night/a.md') is None)
    check('...nor does an empty result', f('') is None and f(None) is None)
    check('the phrase only counts at the front',
          f('Earlier: Vault write failed (502) — but this one worked') is None,
          'run_tool writes it as the whole message; a mention inside a '
          'model-visible string is not a second failure')

    # ── 5. drive the real bookkeeping ────────────────────────────────────
    loud = drive([NOTE, CLAIM], vault_status=502)
    check('the reproduced night stops blaming the coworker',
          loud['error'] == unreachable,
          [loud['error'], '— they were ordered to file, and they filed'])
    check('...and the note is still not counted', loud['writes'] == [],
          'a refused write is not a note')

    quiet = drive([NOTE, QUIET], vault_status=502)
    check('a coworker who claimed nothing is not left in silence',
          quiet['error'] == unreachable,
          [quiet['error'], '— this was the clean night with an empty vault; '
           'errors: 0 is also what keeps the streak from ever pausing a run '
           'whose vault will refuse every iteration until dawn'])

    reach = drive([NOTE, 'Done.\n[PUBLISH_SITE: /tmp/site]'], vault_status=502)
    check('a shut vault outranks a reach the night cannot serve',
          reach['error'] == unreachable,
          [reach['error'], '— both are true; only one explains why the '
           'morning has no note'])

    bad = drive([NOTE, CLAIM], vault_status=400)
    check('a rejected path gets the other door', bad['error'] == rejected,
          bad['error'])

    ok = drive([NOTE, CLAIM], vault_status=200)
    check('a night that worked is unchanged', ok['error'] is None, ok['error'])
    check('...and its note is counted once',
          [w['path'] for w in ok['writes']] == ['Research/night/lead-time.md'],
          ok['writes'])

    # The check this fix must not have swallowed: no write ATTEMPTED at all,
    # and a status line claiming one. That is the real fabrication, and it
    # is still the coworker's.
    lie = drive([CLAIM], vault_status=200)
    check('a claim with no tool call behind it is still called out',
          lie['error'] and 'said it saved a note' in lie['error'],
          [lie['error'], '— the vault was never asked; nothing to blame it '
           'for'])

    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed')
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
