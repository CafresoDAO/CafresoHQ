#!/usr/bin/env python3
"""The front desk sold four capabilities the app does not have.

Measured on a fresh office on 2026-08-13, first screen, nothing configured:

    Vera   VIRTUAL ASSISTANT
           CAN SEARCH THE WEB, SEND EMAIL AND MANAGE YOUR CALENDAR +1 MORE
    Dax    DATA ANALYST
           CAN WORK WITH YOUR FILES, READ YOUR NOTES AND QUERY YOUR DATABASE

There is no EMAIL_SEND, no CALENDAR, no DATABASE and no SLACK tool anywhere
in this app. Not ungated — absent. An earlier audit established exactly that,
wrote it down in `NEVER_WIRED_TOOL_IDS` in modals/settings.jsx, and hid the
four from the hiring and roster checkboxes. It did not reach `CAN_DO` in
app/cast.jsx, which turns the same raw `tools` array into a sentence in the
boss's own words. So the office removed the switch and kept the sales pitch,
on the first screen a new boss sees.

Worse than the checkbox it replaced. An inert checkbox grants nothing
silently; this actively tells the boss a thing that is not true, in the exact
register §6 asks for ("tool call → shown as the action itself"). Being good
copy is what made it dangerous.

The conditional ones were the same fault one step milder. `files` and `code`
grant nothing on their own — `toolsForAgent` gates FILE_READ/FILE_WRITE/BASH
on `agent.elevated` — and `web` only buys `[SEARCH:]` when a Brave key is
set, which is the finding two ticks back. A card that reads the claims array
and ignores every condition is promising on behalf of a runtime it never
consulted.

`canDoPhrase(tools, ctx)` now takes the facts. app/cast.jsx is import-free on
purpose (this suite's sibling runs it verbatim under node), so it cannot look
them up — which is the right shape anyway: the card asserts what it was told.
No ctx means unknowable, and unknowable → do not promise.

Run: python3 scripts/test_the_front_desk_sells_what_exists.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAST = ROOT / 'app' / 'cast.jsx'
HIRE = ROOT / 'modals' / 'hire.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []

PHANTOMS = ('email', 'cal', 'db', 'slack')


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, header):
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces after ' + header)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', src)


def run_js(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-1500:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('a card may only promise what the office can deliver')
    cast = CAST.read_text(encoding='utf-8')
    hire = HIRE.read_text(encoding='utf-8')
    settings = SETTINGS.read_text(encoding='utf-8')
    runtime = RUNTIME.read_text(encoding='utf-8')

    # ── 1. the phantoms are gone from the boss-facing map ────────────────
    can_do = brace_lift(cast, 'const CAN_DO = {')
    for pid in PHANTOMS:
        check(f"'{pid}' has no sentence on any card",
              not re.search(r"^\s*%s:" % pid, can_do, re.M),
              f'{pid} still maps to copy; there is no tool behind it '
              'anywhere in the app')

    # The two lists have to stay in step: anything Settings hides as
    # never-wired must not be something a card is willing to say out loud.
    hidden = set(re.findall(r"'(\w+)'",
                            re.search(r'NEVER_WIRED_TOOL_IDS = new Set\(\[([^\]]*)\]',
                                      settings).group(1)))
    spoken = set(re.findall(r'^\s*(\w+):', can_do, re.M))
    check('nothing Settings calls never-wired is still spoken on a card',
          not (hidden & spoken),
          f'{sorted(hidden & spoken)} — these two lists were written by the '
          'same audit and drifted apart because only one of them was updated')
    check('...and the hidden set is the four this test knows about',
          hidden == set(PHANTOMS),
          f'{sorted(hidden)} — if the set changed, re-derive this test '
          'rather than loosening it')

    # ── 2. every remaining promise maps to a real grant ──────────────────
    # The generalising arm. `toolsForAgent` is the only place a claim becomes
    # a tool; anything a card promises must be reachable there.
    grant = brace_lift(runtime, 'async function toolsForAgent(agent, { peers = [] } = {}) {')
    granted_claims = set(re.findall(r"claimed\.has\('(\w+)'\)", grant))
    needs = brace_lift(cast, 'const CAN_DO_NEEDS = {')
    conditional = set(re.findall(r'^\s*(\w+):', needs, re.M))
    for tid in sorted(spoken):
        reachable = (tid in granted_claims) or (tid in conditional)
        check(f"'{tid}' is a promise the runtime can keep", reachable,
              f"neither toolsForAgent's claimed.has('{tid}') nor an entry in "
              'CAN_DO_NEEDS — so nothing turns this sentence into a tool')

    # ── 3. the conditions the runtime actually applies ───────────────────
    check('files and code hang on elevation, the way toolsForAgent does',
          re.search(r"files:\s*'elevated'", needs)
          and re.search(r"code:\s*'elevated'", needs)
          and 'if (agent.elevated) {' in grant,
          'toolsForAgent grants FILE_* and BASH on agent.elevated, and the '
          'tools claim grants neither on its own')
    check('web hangs on a search key',
          re.search(r"web:\s*'canSearch'", needs)
          and "TOOL_REGISTRY.search.requires()" in grant, needs)
    check('...but still names the fetch a web coworker really gets',
          re.search(r"web:\s*'read a web page you name'",
                    brace_lift(cast, 'const CAN_DO_INSTEAD = {')),
          'BROWSER_FETCH goes to anyone claiming web, key or no key — that '
          'is a real capability and worth naming')

    # ── 4. the caller supplies facts, from the same places ───────────────
    # Lifted from the runtime since 2026-08-16: the reader sat in the hire
    # modal, private to the one surface, while the coworker card and the
    # inspect panel — which describe the same coworker after the hire — read
    # nothing at all and printed the raw claim. It now lives next to
    # `toolsForAgent`, and these checks follow it there rather than relax.
    facts = brace_lift(runtime, 'function capabilityFacts(subject) {')
    check('the card is given facts rather than left to guess',
          re.search(r'canDoPhrase\(t\.tools,\s*capabilityFacts\(t\)\)', hire),
          'canDoPhrase(t.tools) alone means every condition reads as met')
    check('...and by the runtime\'s reader, not a copy of its own',
          'HQ.capabilityFacts(t)' in hire and 'function capabilityFacts' not in hire,
          'two readers of the same four facts is how they drift')
    # Stronger than the old assertion, which only checked that the modal
    # spelled `s.braveEnabled && s.braveKey` the same way the registry does:
    # it now calls requires() itself, so there is one expression, not two
    # that have to be kept matching by hand.
    check('...canSearch read the same way requires() reads it',
          'TOOL_REGISTRY.search.requires()' in facts and 'TOOL_REGISTRY.search.requires()' in grant,
          facts)
    check('...elevated read off the subject itself',
          'subject && subject.elevated' in facts, facts)
    check('...imageProvider, the same setting toolsForAgent checks',
          's.imageProvider' in facts and 's.imageProvider' in grant, facts)
    check('a settings store that is not up yet leaves the flags false',
          facts.count('catch') >= 2,
          'this runs during render on the first screen of a fresh install; '
          'the do-not-promise default has to survive a store that is not '
          'ready, and a thrown error there would take the card with it')

    # ── 5. run it, on the roster the front desk actually ships ───────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the live-roster arm')
    else:
        src = strip_comments(cast)
        scope = (brace_lift(src, 'const CAN_DO = {') + '\n'
                 + brace_lift(src, 'const CAN_DO_NEEDS = {') + '\n'
                 + brace_lift(src, 'const CAN_DO_INSTEAD = {') + '\n'
                 + brace_lift(src, 'function canDoPhrase(tools, ctx) {') + '\n')
        # Verbatim from hq-runtime's INITIAL_AGENTS / the hire shelf.
        roster = [
            {'name': 'Vera', 'tools': ['web', 'email', 'cal', 'db'], 'elevated': False},
            {'name': 'Dax', 'tools': ['files', 'vault', 'db'], 'elevated': True},
            {'name': 'Kip', 'tools': ['web', 'vault'], 'elevated': False},
        ]
        out = run_js(scope + 'const R = %s.map(a => canDoPhrase(a.tools, '
                     '{ elevated: a.elevated }));\n'
                     'console.log(JSON.stringify(R));' % json.dumps(roster))
        vera, dax, kip = out
        for name, phrase in zip(('Vera', 'Dax', 'Kip'), out):
            for word in ('email', 'calendar', 'database', 'Slack'):
                check(f'{name} does not offer to {word.lower()}',
                      word.lower() not in phrase.lower(), phrase)
        check('Vera still has something true to say',
              vera == 'read a web page you name', vera)
        check('Dax keeps the file access she genuinely has',
              'work with your files' in dax, dax)
        check('Kip, not elevated and with no key, is not left blank',
              kip == 'read a web page you name and read your notes', kip)

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
