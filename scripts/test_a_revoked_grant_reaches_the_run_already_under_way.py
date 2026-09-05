#!/usr/bin/env python3
"""#360 stopped an ungranted coworker's mission at the door. It never asked
what happens to a mission that was let IN, whose grant the boss takes back
three hours before it finishes.

`## 360.` (docs/OFFICE_AS_INTERFACE.md) made `NightContext.agent_tools`
resolved "per DISPATCH rather than stored on the schedule, so a grant the
boss revoked this afternoon is gone from tonight's run instead of being
honoured from a snapshot." True, and the fix's own test
(test_a_night_mission_does_not_file_where_it_was_never_allowed.py) proves it
at the granularity it was built for: BEFORE a mission starts.

But a mission's own NightContext is a single Python object that a real
serve.py hands to `run_mission`, which then keeps it alive for up to
`min(durationMs, 4h)` — read `night_runner.py`'s own docstring on
`run_mission`. Every VAULT_APPEND/VAULT_NEW hop the mission makes in that
window read `ctx.agent_tools`, a plain list captured once, at the top of
that call chain. "Per dispatch" and "per write" look identical for a
mission that finishes in one interval and are NOT the same fact for a
mission that runs for hours: a boss who unticks "read your Library" on a
coworker mid-run has revoked nothing that run can see until its NEXT
dispatch, tomorrow night. The scheduled 4-hour ceiling on `durationMs` is a
long time to keep writing into a Library the boss just told the office to
shut this coworker out of.

WHAT THIS PINS

1. Before the fix: `serve._night_agent_tools` is a live, un-cached disk
   read (this was already true, and stays true) — but the mission's own
   `ctx.agent_tools`, captured once at dispatch, disagrees with it after a
   revoke, and `run_tool`'s vault branch reads the STALE value.

2. After the fix: `NightContext.current_agent_tools()` re-asks
   `serve._night_agent_tools` on every call when the ctx was built with a
   live lookup (which `serve._night_ctx`/`_night_run_one` now always
   supply), so a write attempted after a revoke sees the revoke — without
   changing a single byte of what a caller with no lookup (existing tests,
   `_night_post_activity`) gets: the old one-shot `agent_tools` value.

3. The granted coworker is still not collateral, and the "we could not
   look this coworker up at all" refusal (agentId matching nobody, #360's
   other unknown) still refuses live, not just at dispatch.

Run: python3 scripts/test_a_revoked_grant_reaches_the_run_already_under_way.py
"""
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def _write_roster(mem_dir, tools):
    (pathlib.Path(mem_dir) / 'agents.json').write_text(json.dumps([
        {'id': 'a_lib', 'name': 'Vera', 'tools': tools},
    ]), encoding='utf-8')


def main():
    td = tempfile.mkdtemp(prefix='revoke370-')
    mem = pathlib.Path(td) / 'memory'
    mem.mkdir(parents=True)
    _write_roster(mem, ['web', 'vault'])

    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = td
    os.environ['CAFRESOHQ_MEMORY_DIR'] = str(mem)
    os.environ.setdefault('PORT', '19998')
    import serve   # noqa: E402  (imports here so it reads the env above)
    import night_runner as nr  # noqa: E402

    print('=== a mission is dispatched while the grant still stands ===')
    ctx = serve._night_ctx(serve._night_agent_tools('a_lib'), agent_id='a_lib')
    check('the dispatch-time snapshot says granted',
          nr.may_write_to_vault(ctx.agent_tools) is True)
    check('current_agent_tools() agrees, at dispatch',
          nr.may_write_to_vault(ctx.current_agent_tools()) is True)

    print('=== the boss unticks "read your Library" for this coworker, '
          'mid-run ===')
    _write_roster(mem, ['web'])  # vault grant withdrawn; run keeps going
    check('the roster itself already shows the revoke, live',
          serve._night_agent_tools('a_lib') == ['web'])
    check('…the STALE dispatch-time snapshot on ctx does not '
          '(it is a plain list, not a re-read)',
          ctx.agent_tools == ['web', 'vault'],
          'if this ever changes, ctx.agent_tools stopped being a snapshot '
          'and the rest of this test needs rethinking, not deleting')

    print('=== a vault write attempted after the revoke, on the SAME ctx '
          'the mission has been holding all along ===')
    # base_url points at a port nothing listens on (same technique as
    # test_a_night_mission_does_not_file_where_it_was_never_allowed.py's
    # FakeCtx): a write that gets PAST the grant check reaches the wire and
    # comes back "vault not reachable" (503); a write the grant check
    # catches never reaches the wire at all (403). The two are
    # distinguishable without needing a real vault backend.
    result = nr.run_tool(ctx, 'VAULT_NEW', 'Research/night/x.md', '# hi')
    status = nr.vault_write_status(result)
    check('the write is refused, not merely delayed',
          status == nr.NIGHT_VAULT_FORBIDDEN,
          'got %r from %r — a stale grant let a write through after the '
          'boss revoked it' % (status, result))
    check('…and the refusal is a 403 (the grant), not a 503 (the wire) — '
          'the whole point is this must be caught BEFORE the wire',
          status != 503, result)
    check('…named correctly: the Roster, not Connections',
          'Roster' in result, result)

    print('=== run_mission\'s own opening door reads live too ===')
    # A fresh ctx, as a fresh dispatch would build — this is the same
    # question #360 already pinned, kept here so a regression in
    # current_agent_tools() itself (not just the wiring) is caught by this
    # file too, independent of the older suite.
    _write_roster(mem, ['web', 'vault'])
    ctx2 = serve._night_ctx(serve._night_agent_tools('a_lib'), agent_id='a_lib')
    _write_roster(mem, [])  # revoked before the first brain call
    sched = {'id': 'nsh_test', 'agentId': 'a_lib', 'agentName': 'Vera',
             'topic': 'anything', 'vaultFolder': 'Research/night',
             'durationMs': 3600000, 'intervalMs': 300000}
    run = nr.run_mission(ctx2, sched)
    check('a mission whose grant vanished before the first call still '
          'turns away at the door', run.get('iterations', 0) == 0)
    check('…naming the Roster', 'Roster' in str(run.get('lastError', '')),
          run.get('lastError'))

    print('=== no collateral: a coworker who is NOT revoked still reaches '
          'the wire ===')
    _write_roster(mem, ['vault'])
    ctx3 = serve._night_ctx(serve._night_agent_tools('a_lib'), agent_id='a_lib')
    ok_result = nr.run_tool(ctx3, 'VAULT_NEW', 'a.md', 'x')
    check('a still-granted coworker is not stopped by this gate',
          nr.vault_write_status(ok_result) != nr.NIGHT_VAULT_FORBIDDEN,
          ok_result)
    check('…they get all the way to the wire',
          nr.vault_write_status(ok_result) == 503, ok_result)

    print('=== a caller with no agentId keeps the old one-shot behaviour '
          '(e.g. _night_post_activity, which never re-asks) ===')
    static_ctx = nr.NightContext('http://127.0.0.1:1', agent_tools=['vault'])
    check('no lookup given → current_agent_tools() is just the snapshot',
          static_ctx.current_agent_tools() == ['vault'])
    check('…and a ctx built via _night_ctx() with no agent_id behaves the '
          'same way',
          serve._night_ctx(['vault']).current_agent_tools() == ['vault'])

    print()
    if FAILS:
        print('FAILED %d check(s): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('a revoked grant reaches the run already under way: '
          'all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
