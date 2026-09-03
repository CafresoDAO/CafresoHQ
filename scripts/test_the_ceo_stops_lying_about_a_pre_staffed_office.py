#!/usr/bin/env python3
"""The CEO's first line was a lie on any machine with a CLI agent installed.

On a fresh office (empty hq-state/), the onboarding effect in app.jsx has an
800ms timer that decides "genuinely new office" vs "returning user" by
reading the hired-roster ref. If it reads zero, the CEO posts a scripted
welcome message into chat — "it's just me and a floor of empty desks:
nothing here is pre-staged" — and 1.6s later auto-opens the JOB POSTINGS
hire deck for "your first hire".

Reproduced live on a wiped office (127.0.0.1:8901, hq-state/ deleted,
localStorage cleared) that has Hermes, Claude Code and Codex CLIs on PATH —
a normal condition for this app's actual target user, a developer running it
on their own machine. A separate effect auto-detects those CLIs and stages
them into the roster (`hq-state/memory/agents.json` held all three, each
`"hiredAt"`-stamped, moments after boot), but that effect fires on
`setTimeout(sync, 2500)` — it spawns `--version`/auth subprocesses over
`GET /agents` server-side. 2500 > 800, always, on every machine, every load:
the welcome decision cannot help but run first. Verified live: the JOB
POSTINGS dialog auto-opened ("PICK A SAVED ROLE · OR START FROM SCRATCH ·
NEW HIRE →") while `read_page` still showed it, and — a few seconds later,
same session — the Getting Started checklist flipped to "1/6" with "Hire
your first specialist" already checked and "3 HIRED" in the topbar, having
never gone through the deck the CEO had just opened for that exact step. On
a machine where local CLIs are common, this is not a rare race: it is what
happens on every fresh boot.

The fix pulls the decision into `decideFirstRunWelcome()`, a standalone
function the timer now awaits before touching chat or the hire modal: if the
roster is still empty it asks the SAME detector (`GET /agents` via
`window.CafresoHQClient.agentsStatus`) the CLI-sync effect itself uses,
directly, instead of racing a timer against it. Re-verified live: on the
same wiped office with the same CLIs on PATH, the chat panel read "No
messages yet — type below to message CafresoHQ." (the fabricated welcome
never landed), both immediately after boot and after the roster caught up
to "3 HIRED" a few seconds later, and no JOB POSTINGS dialog ever appeared
unprompted.

`decideFirstRunWelcome` is lifted out of app.jsx by name and run under Node
across ten scenarios, including the measured case (roster empty, an
installed-but-unauthenticated CLI — Codex never logged in — still counts,
and the roster-hydrated case never even calls the detector). Static checks
pin the call site: the effect actually awaits the function and gates the
welcome on its result, re-checks the roster ref after the await (state can
hydrate mid-await), still honors cancellation on unmount, and the
"installed" field the fix keys off is the same field name the CLI-sync
effect uses to decide who gets auto-staffed — so the two cannot quietly
diverge.

Run: python3 scripts/test_the_ceo_stops_lying_about_a_pre_staffed_office.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift_function(src, name):
    """`(async )?function <name>(…) { … }` to its matching closing brace,
    located by NAME. The parameter list is scanned with its own paren depth
    first (this function's signature destructures an object — `({ a, b })`
    — so a naive "first `{`" would grab the parameter brace, not the body)
    before brace-balancing the body itself. A rename reports as a missing
    locator, never as a silently empty slice."""
    m = re.search(r'^(?:async\s+)?function %s\(' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no `function %s(` in app.jsx' % name)
    depth, i = 0, m.end() - 1
    while i < len(src):
        if src[i] == '(':
            depth += 1
        elif src[i] == ')':
            depth -= 1
            if depth == 0:
                break
        i += 1
    else:
        raise SystemExit('unterminated parameter list for %s' % name)
    body_start = src.find('{', i)
    if body_start == -1:
        raise SystemExit('no body for %s' % name)
    depth = 0
    for j in range(body_start, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
    raise SystemExit('unbalanced body for %s' % name)


def onboarding_effect(src):
    """The first-run useEffectA block, located by its distinctive opening
    line rather than a line number, sliced to the matching `}, []);` that
    closes it."""
    anchor = "useEffectA(() => {\n    if (tourSeen) return;"
    i = src.find(anchor)
    if i == -1:
        raise SystemExit('no first-run onboarding effect found (tourSeen anchor missing)')
    end = src.find('}, []);', i)
    if end == -1:
        raise SystemExit('onboarding effect never closes with `}, []);`')
    return src[i:end + len('}, []);')]


def cli_sync_installed_filter(src):
    """The CLI-sync effect's own `installed` predicate, so §2 can confirm
    the fix keys off the identical field."""
    m = re.search(r'const installed = detected\.filter\(d =>\n\s*(.+?)\);', src)
    if not m:
        raise SystemExit('CLI-sync installed filter not found in app.jsx')
    return m.group(1)


HARNESS_TEMPLATE = r"""
%(fn)s

const results = [];
const record = (label, outcome, expected, extra) => {
  results.push([label, outcome, expected, extra === undefined ? null : extra]);
};

// Roster already hydrated: must resolve false WITHOUT ever calling the
// detector. A spy (not a throw — a throw would just be swallowed by the
// function's own try/catch and prove nothing) records whether it was asked.
{
  let called = false;
  const spy = async () => { called = true; return { agents: [] }; };
  const outcome = await decideFirstRunWelcome({ agentsCount: 3, agentsStatus: spy });
  record('hydrated roster (returning user) — resolves false', outcome, false);
  record('...and never even asks the detector', called, false);
}

const CASES = [
  ['no CafresoHQClient on window yet — fails open to genuinely-new',
    0, undefined, true],
  ['detector reachable, nothing installed — genuinely new office',
    0, async () => ({ agents: [] }), true],
  ['detector reports agents, none installed — genuinely new office',
    0, async () => ({ agents: [ { id: 'hermes', installed: false },
                                 { id: 'codex', installed: false } ] }), true],
  ['the measured case: Hermes + Claude Code installed and authed — pre-staffed, no welcome',
    0, async () => ({ agents: [ { id: 'hermes', installed: true, authenticated: true },
                                 { id: 'claude-code', installed: true, authenticated: true } ] }), false],
  ['installed but never logged in (Codex) still counts as staffed',
    0, async () => ({ agents: [ { id: 'codex', installed: true, authenticated: false } ] }), false],
  ["detector throws (backend hiccup) — fails open to genuinely-new",
    0, async () => { throw new Error('network down'); }, true],
  ['malformed response with no agents key — fails open',
    0, async () => ({}), true],
  ['agents: null — fails open, does not crash on .some',
    0, async () => ({ agents: null }), true],
  ['a null entry in the agents array does not crash the scan',
    0, async () => ({ agents: [ null, { id: 'hermes', installed: true } ] }), false],
];
for (const [label, agentsCount, agentsStatus, expected] of CASES) {
  const outcome = await decideFirstRunWelcome({ agentsCount, agentsStatus });
  record(label, outcome, expected);
}

console.log(JSON.stringify(results));
"""


def main():
    print('The CEO stops lying about a pre-staffed office')
    src = APP.read_text(encoding='utf-8')

    fn = lift_function(src, 'decideFirstRunWelcome')
    check('decideFirstRunWelcome is findable', bool(fn.strip()),
          'every check below would run against an empty slice')

    # --- §1: the decision, driven under Node -----------------------------
    harness = HARNESS_TEMPLATE % {'fn': fn}
    proc = subprocess.run(['node', '--input-type=module', '-e', harness],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr.strip()[:2000])
        raise SystemExit('decideFirstRunWelcome did not run under node')
    got = json.loads(proc.stdout.strip().splitlines()[-1])

    for label, outcome, expected, _extra in got:
        check(label, outcome == expected, 'got %r, expected %r' % (outcome, expected))

    # --- §2: the fix's criterion cannot quietly diverge from the CLI-sync
    # effect's own criterion for "who gets auto-staffed" ------------------
    cli_filter = cli_sync_installed_filter(src)
    check('the CLI-sync effect keys auto-staffing off `d.installed`',
          'd.installed' in cli_filter, cli_filter)
    check('decideFirstRunWelcome checks the SAME field, not `.authenticated` '
          'or anything else',
          'd.installed' in fn and 'd.authenticated' not in fn, fn)

    # --- §3: the call site actually awaits and gates on the result -------
    effect = onboarding_effect(src)
    check('the effect calls decideFirstRunWelcome(...)',
          'decideFirstRunWelcome(' in effect, effect[:400])
    check('...and awaits it (not fire-and-forget)',
          re.search(r'await decideFirstRunWelcome\(', effect) is not None, effect[:400])
    check('...passing the live roster count',
          'agentsCount: firstRunAgentsRef.current.length' in effect, effect[:400])
    check('...and the real detector off window.CafresoHQClient, not a stub',
          re.search(r'agentsStatus:\s*oc\s*&&\s*oc\.agentsStatus', effect) is not None,
          effect[:400])
    check('the welcome sequence is gated on the result (a falsy answer must '
          'skip setChat/setHireOpen)',
          re.search(r'if\s*\(cancelled\s*\|\|\s*!isNewOffice', effect) is not None,
          effect[:600])
    check('...and re-checks the roster ref after the await, since it can '
          'hydrate mid-flight',
          re.search(r'!isNewOffice\s*\|\|\s*firstRunAgentsRef\.current\.length > 0',
                    effect) is not None,
          effect[:600])
    check('cancellation on unmount is still respected (no setState after '
          'teardown)',
          re.search(r'let cancelled = false;[\s\S]*cancelled = true', effect) is not None,
          'no cancelled flag set true in the cleanup')
    check('the fabricated welcome copy is still gated behind the decision, '
          'not hoisted above it',
          effect.index('decideFirstRunWelcome(') < effect.index('nothing here is pre-staged'),
          'the welcome text appears before the gate meant to guard it')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
