#!/usr/bin/env python3
"""`## 371.` (docs/OFFICE_AS_INTERFACE.md) made a mid-mission revoke reach a
Night Shift VAULT_APPEND/VAULT_NEW attempt already under way, not just the
next dispatch. It fixed exactly the two branches it named — the write
branch of `run_tool` — and left VAULT_SEARCH/VAULT_READ, two doors over,
completely unguarded.

`may_write_to_vault`'s own docstring asks "Was this coworker granted the
Library?" — not "...to write to it" — and the Roster checkbox its refusal
sentence points at is literally worded 'tick "read your Library"'. The
daytime office already treats this as one door: `hq-runtime.jsx`'s
`toolsForAgent` puts VAULT_SEARCH, VAULT_READ, VAULT_APPEND and VAULT_NEW in
a coworker's prompt together, all four behind the same `claimed.has
('vault')`. The night shift, before this fix, only re-checked two of them.

WHAT THIS PINS

1. Before the fix: a mission dispatched while a coworker holds the Library
   grant, whose grant is revoked mid-run, still reaches the wire on
   VAULT_SEARCH and VAULT_READ every hop for the rest of its (up to 4-hour)
   run — only a VAULT_APPEND/VAULT_NEW attempted after the same revoke was
   ever refused. A boss who unticks "read your Library" believes the whole
   door just shut; half of it stayed open all night.

2. After the fix: VAULT_SEARCH and VAULT_READ read `ctx.current_agent_tools
   ()` — the same live re-ask `## 371.` wired into the write branch — and
   refuse with the same 403/Roster shape the write branch already answers
   with, before ever reaching the wire.

3. No collateral: a still-granted coworker reaches the wire on both reads
   exactly as before — this test's fake port produces the pre-existing
   generic "Tool VAULT_SEARCH/VAULT_READ failed: <connection error>" shape
   (neither read branch has VAULT_APPEND/VAULT_NEW's own URLError→503
   mapping), distinguishing "reached the wire" from "refused at the door"
   (403) the same way
   `test_a_revoked_grant_reaches_the_run_already_under_way.py` does for the
   write branch.

Run: python3 scripts/test_a_revoked_grant_could_still_read_the_library.py
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
    td = tempfile.mkdtemp(prefix='revoke376-')
    mem = pathlib.Path(td) / 'memory'
    mem.mkdir(parents=True)
    _write_roster(mem, ['web', 'vault'])

    os.environ['CAFRESOHQ_HQ_STATE_DIR'] = td
    os.environ['CAFRESOHQ_MEMORY_DIR'] = str(mem)
    os.environ.setdefault('PORT', '19997')
    import serve   # noqa: E402  (imports here so it reads the env above)
    import night_runner as nr  # noqa: E402

    print('=== a mission is dispatched while the grant still stands ===')
    ctx = serve._night_ctx(serve._night_agent_tools('a_lib'), agent_id='a_lib')
    check('the dispatch-time snapshot says granted',
          nr.may_write_to_vault(ctx.agent_tools) is True)

    print('=== the boss unticks "read your Library" mid-run — the mission '
          'keeps holding the same ctx it started with ===')
    _write_roster(mem, ['web'])  # vault grant withdrawn; run keeps going
    check('the roster itself already shows the revoke, live',
          serve._night_agent_tools('a_lib') == ['web'])

    print('=== VAULT_SEARCH after the revoke, on the SAME ctx ===')
    # base_url points at a port nothing listens on: a call that gets PAST
    # the grant check reaches the wire and comes back a bare connection
    # failure (no such "Vault search/read failed (403)" shape) — a call the
    # grant check catches never reaches the wire and says so at 403.
    search_result = nr.run_tool(ctx, 'VAULT_SEARCH', 'pricing', '')
    check('the search is refused, not merely delayed',
          'Vault search failed (403)' in search_result,
          'got %r — a stale grant let a search through after the boss '
          'revoked it' % (search_result,))
    check('…named correctly: the Roster',
          'Roster' in search_result, search_result)

    print('=== VAULT_READ after the same revoke ===')
    read_result = nr.run_tool(ctx, 'VAULT_READ', 'Research/night/x.md', '')
    check('the read is refused, not merely delayed',
          'Vault read failed (403)' in read_result,
          'got %r — a stale grant let a read through after the boss '
          'revoked it' % (read_result,))
    check('…named correctly: the Roster',
          'Roster' in read_result, read_result)

    print('=== no collateral: a coworker who is NOT revoked still reaches '
          'the wire on both doors ===')
    # Neither branch has VAULT_APPEND/VAULT_NEW's own URLError→503 mapping
    # (see the comment on that branch), so a still-granted call that gets
    # past this gate and hits a port nothing listens on surfaces as the
    # generic "Tool <name> failed: <connection error>" — the pre-existing
    # (and unrelated) shape for an unreachable self-call, not this gate's
    # 403. That is exactly the distinction being tested: past the door,
    # not refused at it.
    _write_roster(mem, ['vault'])
    ctx2 = serve._night_ctx(serve._night_agent_tools('a_lib'), agent_id='a_lib')
    ok_search = nr.run_tool(ctx2, 'VAULT_SEARCH', 'pricing', '')
    ok_read = nr.run_tool(ctx2, 'VAULT_READ', 'a.md', '')
    check('a still-granted coworker is not stopped by this gate (search)',
          'Vault search failed (403)' not in ok_search, ok_search)
    check('…they get all the way to the wire (search)',
          'Tool VAULT_SEARCH failed' in ok_search, ok_search)
    check('a still-granted coworker is not stopped by this gate (read)',
          'Vault read failed (403)' not in ok_read, ok_read)
    check('…they get all the way to the wire (read)',
          'Tool VAULT_READ failed' in ok_read, ok_read)

    print()
    if FAILS:
        print('FAILED %d check(s): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('a revoked grant could still read the library: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
