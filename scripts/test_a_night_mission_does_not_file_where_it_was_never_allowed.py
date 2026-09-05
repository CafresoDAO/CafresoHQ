#!/usr/bin/env python3
"""A coworker filed into the Library all night without ever being allowed in.

The daytime office has gated this for a long time. hq-runtime.jsx's
`toolsForAgent` puts VAULT_APPEND and VAULT_NEW into a coworker's prompt only
inside `if (claimed.has('vault'))` — no grant, no writing tools. The night
shift asked nobody. `run_tool` accepted VAULT_APPEND/VAULT_NEW from any
scheduled mission, so what the boss ticked on the Roster decided what a
coworker could reach by day and decided nothing at all after dark.

Measured on this machine's own roster before the fix — three hired coworkers,
`files, shell` / `web` / `web, files, code`, not one of them granted 'vault',
every one of them able to write to the Library on a night mission.

WHAT THIS PINS

1. The policy, four-valued at the edges: granted writes, not-granted does
   not, granted-nothing does not, and NOT KNOWN does not either. That last
   one is the interesting one. Everywhere else in this codebase "we did not
   look" must never render as "they have nothing" — but that rule governs
   DESCRIBING a coworker to the boss, and this is an authorization decision,
   where the same unknown has to be spent the other way. The unknown that
   matters in practice is an agentId matching nobody on the roster, i.e. a
   coworker who was fired after the schedule was made, and a fired coworker's
   mission filing into the Library is precisely the leak being closed.

2. THE ACCOUNTING, which is the trap in this file. `run_iteration` reads
   `vault_write_status(result) is None` as A NOTE THAT LANDED. So a refusal
   phrased as anything but a vault_write_status failure would be counted as a
   successful write, and the morning report would name a note the Library
   never saw. That is the fabrication half this file's comments exist to
   prevent, and it would have been introduced BY the fix. The gate therefore
   answers in the shape the accounting already reads.

3. That the refusal names the right door. 502/503 is the wiring and
   everything else was the vault answering; a permissions decision is
   neither, and sending the boss to inspect a note path over a Roster
   checkbox is the wrong door twice over.

4. That a granted coworker is not collateral: they still get all the way to
   the wire.

Run: python3 scripts/test_a_night_mission_does_not_file_where_it_was_never_allowed.py
"""
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import night_runner as nr  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


class FakeCtx(object):
    """Enough NightContext to drive run_tool. base_url points at a port
    nothing is on, so any attempt to actually reach the wire is visible as a
    connection failure rather than silently succeeding somewhere."""

    def __init__(self, agent_tools):
        self.agent_tools = agent_tools
        self.base_url = 'http://127.0.0.1:1'
        self.api_key = ''
        self.brave_key = ''
        self.hermes_home = ''
        self.ssl_ctx = None

    def current_agent_tools(self):
        # Real NightContext.current_agent_tools() re-asks a live lookup when
        # #370 wired one; this fake carries no lookup and no agentId, so it
        # falls back to the same plain snapshot NightContext falls back to
        # when it wasn't given one either — see NightContext's own default.
        return self.agent_tools


def main():
    # ── 1. the policy ────────────────────────────────────────────────────
    check('a coworker granted the Library may file',
          nr.may_write_to_vault(['web', 'vault']) is True)
    check('a coworker granted other things may not',
          nr.may_write_to_vault(['web', 'files', 'code']) is False,
          'this is the shape every coworker on this machine actually has')
    check('a coworker granted nothing may not',
          nr.may_write_to_vault([]) is False)
    check('a coworker we could not look up may not',
          nr.may_write_to_vault(None) is False,
          'None is "we did not look" — on an authorization question that '
          'must refuse, not allow')

    # ── 2. the refusal is counted as a refusal, not as a note ────────────
    refused = nr.run_tool(FakeCtx(['web', 'files']),
                          'VAULT_NEW', 'Research/night/x.md', '# hi')
    status = nr.vault_write_status(refused)
    check('the refusal parses as a vault write failure',
          status == nr.NIGHT_VAULT_FORBIDDEN,
          'got %r from %r' % (status, refused))
    check('…so run_iteration cannot count it as a landed note',
          status is not None,
          'vault_write_status None means LANDED — a refusal read as None '
          'would put a note in the morning report that the Library never saw')
    check('the refusal says who it is about and what to tick',
          'Library' in refused and 'Roster' in refused, refused)
    check('the same refusal covers VAULT_APPEND',
          nr.vault_write_status(nr.run_tool(
              FakeCtx(['web']), 'VAULT_APPEND', 'a.md', 'x'))
          == nr.NIGHT_VAULT_FORBIDDEN)

    unknown = nr.run_tool(FakeCtx(None), 'VAULT_NEW', 'a.md', 'x')
    check('an unlookupable coworker is refused too, and told so plainly',
          nr.vault_write_status(unknown) == nr.NIGHT_VAULT_FORBIDDEN
          and 'roster' in unknown.lower(), unknown)
    check('…and the two unknowns do not share one sentence',
          unknown != refused,
          'a coworker who was never granted the Library and a coworker '
          'nobody can find have different fixes')

    # ── 3. the right door ────────────────────────────────────────────────
    check('a forbidden write does not send the boss to check the note path',
          nr.vault_refused_sentence(nr.NIGHT_VAULT_FORBIDDEN)
          != nr.vault_refused_sentence(400))
    check('…it names the Roster',
          'Roster' in nr.vault_refused_sentence(nr.NIGHT_VAULT_FORBIDDEN))
    check('the wiring sentence is untouched',
          nr.vault_refused_sentence(502) == 'vault is not reachable — check Connections'
          and nr.vault_refused_sentence(503) == nr.vault_refused_sentence(502))
    check('the vault-answered sentence is untouched',
          nr.vault_refused_sentence(400) == 'vault refused the write — check the note path')

    # ── 4. no collateral: a granted coworker reaches the wire ────────────
    allowed = nr.run_tool(FakeCtx(['vault']), 'VAULT_NEW', 'a.md', 'x')
    check('a granted coworker is not stopped by this gate',
          nr.vault_write_status(allowed) != nr.NIGHT_VAULT_FORBIDDEN,
          allowed)
    check('…they get all the way to the wire',
          nr.vault_write_status(allowed) == 503, allowed)
    check('a non-vault tool is not gated by a vault grant',
          nr.run_tool(FakeCtx([]), 'SEARCH', 'anything', None)
          .startswith('SEARCH is unavailable'),
          'the gate must not leak onto tools it has nothing to do with')

    # ── 5. the mission turns away at the door, before paying for a brain ─
    #
    # Not merely safe but CHEAP: every mission type build_prompt writes ends
    # in a mandatory vault write, so an ungranted coworker cannot finish, and
    # without this the night would spend real tokens producing a refusal each
    # iteration until ERROR_STREAK_AUTO_PAUSE stopped it.
    sched = {'id': 'nsh_test', 'agentId': 'a_gone', 'agentName': 'Gone',
             'topic': 'anything', 'vaultFolder': 'Research/night',
             'durationMs': 3600000, 'intervalMs': 300000}
    run = nr.run_mission(FakeCtx(['web', 'files']), sched)
    check('an ungranted mission ends immediately', bool(run.get('finishedAt')))
    check('…having written nothing', run.get('writes') == [])
    check('…having burned no tokens', run.get('tokensUsed', 0) == 0,
          'the outcome was knowable before the first brain call')
    check('…having run no iterations', run.get('iterations', 0) == 0)
    check('…and says why, in the boss\'s words',
          'Library' in str(run.get('lastError', '')), run.get('lastError'))

    # ── 6. serve.py resolves the RIGHT coworker's grants, off disk ───────
    #
    # Read from disk rather than over _self_call: an authorization check
    # should not be able to fail because the office is busy answering itself.
    with tempfile.TemporaryDirectory() as td:
        mem = pathlib.Path(td) / 'memory'
        mem.mkdir(parents=True)
        (mem / 'agents.json').write_text(json.dumps([
            {'id': 'a_librarian', 'name': 'Vera', 'tools': ['web', 'vault']},
            {'id': 'a_coder', 'name': 'Kip', 'tools': ['files', 'code']},
            {'id': 'a_bare', 'name': 'Dax'},
        ]), encoding='utf-8')
        os.environ['CAFRESOHQ_HQ_STATE_DIR'] = td
        os.environ['CAFRESOHQ_MEMORY_DIR'] = str(mem)
        os.environ.setdefault('PORT', '19997')
        sys.path.insert(0, str(ROOT))
        import serve  # noqa: E402  (imported here: it reads the env above)

        check('the granted coworker resolves to their grant',
              serve._night_agent_tools('a_librarian') == ['web', 'vault'])
        check('the ungranted coworker resolves to theirs',
              serve._night_agent_tools('a_coder') == ['files', 'code'])
        check('a roster entry with no tools key is EMPTY, not unknown',
              serve._night_agent_tools('a_bare') == [],
              'they are on the roster and were granted nothing — a different '
              'fact from "we could not find them"')
        check('a coworker who is not on the roster is UNKNOWN',
              serve._night_agent_tools('a_fired') is None)
        check('an empty agentId is unknown', serve._night_agent_tools('') is None)

        check('end to end: the librarian may file',
              nr.may_write_to_vault(serve._night_agent_tools('a_librarian')) is True)
        check('end to end: the coder may not',
              nr.may_write_to_vault(serve._night_agent_tools('a_coder')) is False)
        check('end to end: the fired coworker may not',
              nr.may_write_to_vault(serve._night_agent_tools('a_fired')) is False)

    print()
    if FAILS:
        print('FAILED %d check(s): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('a night mission does not file where it was never allowed: '
          'all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
