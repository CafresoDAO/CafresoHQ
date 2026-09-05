#!/usr/bin/env python3
"""A night shift with nowhere to file should say so at the door.

Every mission type `build_prompt` writes for ends with a mandatory vault
write; the notes ARE the deliverable. The office already knows whether one
can land — /vault/status probes an Obsidian REST backend for real and stats
an fs one — and `run_mission` never asked.

Measured 2026-08-16 on office 9261, vault pointed at a closed Obsidian REST,
canned brain on 9236. /vault/status said `configured: false` BEFORE the
mission started. What the boss got anyway:

    t+  0s  iterations=1 writes=0 errors=1  'vault is not reachable — …'
    t+ 60s  iterations=2 writes=0 errors=2  'vault is not reachable — …'
    final:  iterations=3, writes=[], errors=3

Two minutes and three brain calls — real money on any paid brain — to learn
what one GET would have said before the first one. The sibling fix (a
refused write is recorded, not blamed on the coworker) is what stops this at
three instead of running till dawn; it does not stop it from starting.

Guards:
  · the question is asked before the first brain call, not after the third
  · a refusal is a finished record with the door named, not an exception
  · one wording for "no vault", whether it was missing at the door or died
    at 1am — the same sentence run_iteration uses
  · an unanswerable probe lets the night run: this is an optimisation over
    a path that is already honest, and must never be the thing that cancels
    a night the office could have run

Run: python3 scripts/test_the_night_asks_before_it_starts.py
"""
import json
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
    return re.sub(r'^\s*#.*$', '', src, flags=re.M)


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


NOTE = ('[VAULT_NEW: Research/night/a.md]\n# A\n\nbody\n[/VAULT_NEW]')


def drive_mission(vault_body, vault_http=200, duration=1000):
    """run_mission with the office and the brain stubbed. Returns
    (run, endpoints hit, number of brain calls)."""
    seen, brain = [], []

    def fake_self_call(ctx, method, path, body=None, headers=None, timeout=90):
        seen.append((method, path.split('?')[0]))
        if path.startswith('/vault/status'):
            return vault_http, json.dumps(vault_body).encode('utf-8')
        if path.startswith('/vault/list'):
            return 200, b'{"files": []}'
        if method == 'PUT' and path.startswith('/vault/note'):
            return 200, b'{"path": "a"}'
        return 200, b'{}'

    def fake_llm(ctx, messages, max_tokens=None):
        brain.append(1)
        return (NOTE if len(brain) == 1 else 'Wrote 1 note. Next: carriers.'), 7

    real_llm, real_call = nr.llm_call, nr._self_call
    nr.llm_call, nr._self_call = fake_llm, fake_self_call
    try:
        run = nr.run_mission(FakeCtx(), {
            'id': 's1', 'agentName': 'Kip', 'topic': 't',
            'vaultFolder': 'Research/night',
            'durationMs': duration, 'intervalMs': 60000})
    finally:
        nr.llm_call, nr._self_call = real_llm, real_call
    return run, seen, len(brain)


def main():
    print('the night asks before it starts')
    src = strip_py_comments(read('night_runner.py'))
    body = src[src.index('def run_mission('):]
    body = body[:body.index('\ndef ') if '\ndef ' in body else len(body)]

    # ── 1. asked at the door ─────────────────────────────────────────────
    ask = body.find('vault_can_take_a_note(ctx)')
    loop = body.find('while int(time.time() * 1000) < deadline')
    check('the mission asks whether a note can land', ask >= 0,
          'run_mission has no pre-flight; the first brain call IS the probe')
    check('...before the loop that spends the tokens',
          0 <= ask < loop,
          [ask, loop, '— after the loop it is a post-mortem, and the boss '
           'has already paid for three iterations of it'])
    check('the refusal is a finished record, not an exception',
          re.search(r'if not ready:[\s\S]{0,300}?run\[.finishedAt.\][\s\S]{0,120}?'
                    r'\n        return run', body) is not None,
          "_night_run_one turns a raise into lastError: str(e) — a stack "
          'message where the door should be')
    guard = body[body.find('if not ready:'):][:320]
    for field in ("run['errors'] = 1", "run['lastError'] = why"):
        check(f'...that says {field.split("[")[1].split("]")[0]}',
              field in guard, guard)

    # ── 2. one wording for one fact ──────────────────────────────────────
    fn = src[src.index('def vault_can_take_a_note('):]
    fn = fn[:fn.index('\ndef ')]
    check('the door sentence is the one run_iteration already uses',
          'vault_refused_sentence(' in fn,
          'a second literal here is two wordings for one fact — the boss '
          'reads whichever surface they happened to open')
    check('...and it is the unreachable one, not the bad-path one',
          nr.vault_can_take_a_note.__doc__ and
          nr.vault_refused_sentence(503) == 'vault is not reachable — check Connections',
          nr.vault_refused_sentence(503))

    # ── 3. the probe ─────────────────────────────────────────────────────
    def probe(payload, http=200, boom=False):
        def fake(ctx, method, path, body=None, headers=None, timeout=90):
            if boom:
                raise OSError('connection refused')
            return http, json.dumps(payload).encode('utf-8')
        real = nr._self_call
        nr._self_call = fake
        try:
            return nr.vault_can_take_a_note(FakeCtx())
        finally:
            nr._self_call = real

    ready, why = probe({'configured': False, 'backend': 'rest'})
    check('an unconfigured vault stops the night',
          ready is False and why == nr.vault_refused_sentence(503), [ready, why])
    check('a working vault does not',
          probe({'configured': True, 'backend': 'fs'}) == (True, ''),
          probe({'configured': True, 'backend': 'fs'}))
    # Fail OPEN, three ways. The refused-write branch catches a dead vault
    # on iteration one regardless; a probe that cannot answer must not be
    # the thing that cancels a night the office could have run.
    check('a status endpoint that errors lets the night run',
          probe({'configured': False}, http=500)[0] is True)
    check('...so does one that will not answer at all',
          probe({}, boom=True)[0] is True)
    check('...and so does a body that is not what we expected',
          probe(['not', 'a', 'dict'])[0] is True,
          'an office that changed shape is not a vault that is down')

    # ── 4. drive the mission ─────────────────────────────────────────────
    run, seen, brains = drive_mission({'configured': False, 'backend': 'rest'})
    check('the reproduced night never starts',
          run['iterations'] == 0 and run['writes'] == [], run)
    check('...and the brain is never called', brains == 0,
          f'{brains} call(s) — the whole point is the tokens not spent')
    check('...but it is on the record with a door',
          run['errors'] == 1 and run['lastError'] == nr.vault_refused_sentence(503),
          [run['errors'], run['lastError'],
           '— errors: 0 and iterations: 0 is a night nobody can tell from a '
           'night that had nothing to say'])
    check('...and it is a finished run, not one still open',
          run['finishedAt'] >= run['startedAt'] > 0,
          [run['startedAt'], run['finishedAt'],
           '— the board reads finishedAt to stop showing it as in flight'])
    check('the probe asked the office, once',
          [p for _m, p in seen].count('/vault/status') == 1, seen)

    ok, seen_ok, brains_ok = drive_mission({'configured': True, 'backend': 'fs'})
    check('a night with a vault still runs', ok['iterations'] >= 1, ok)
    check('...and still files', len(ok['writes']) >= 1, ok['writes'])
    check('...and is not marked with the door', ok['lastError'] == '', ok)
    check('...and did call the brain', brains_ok >= 1, brains_ok)

    blind, _s, blind_brains = drive_mission({'configured': False}, vault_http=503)
    check('a night the office cannot vouch for is attempted, not cancelled',
          blind['iterations'] >= 1 and blind_brains >= 1,
          [blind, '— run_iteration owns the honest failure; this guard only '
           'saves the trip when the answer is certain'])

    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed')
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
