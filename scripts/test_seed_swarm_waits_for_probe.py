#!/usr/bin/env python3
"""SEED SWARM's "no brain, refuse" guard had a timing hole: probing.

`modals/hire.jsx`'s candidate shelf resolves the brain it will hire seven
specialists onto from the same async front-desk probe the desk cards are
drawn from (`app/cast.jsx`'s `candidateBrain`, reproduced/covered in
scripts/test_a_candidate_names_the_brain_it_will_use.py). Three states, not
two:

    driverList === null        -> probing = true,  shelfBrain = undefined
    driverList = [...], found  -> probing = false, shelfBrain = 'x:y'
    driverList = [...], none   -> probing = false, shelfBrain = null

The SEED SWARM tile's click handler refused to hire when nothing was ready:

    if (!probing && !shelfBrain) { ...warn, no brain yet...; return; }

That condition is FALSE while still probing — `!probing` is false — so it
does not block the hire, it only decides whether to show the WARNING.
`shelfBrain` stays `undefined` for the whole probing window (a few seconds
on every cold open, during which "AT THE FRONT DESK — checking who's
available on this machine…" is on screen and the shelf is already
rendered with `candidates.length > 0`, so the tile is clickable start to
finish). A boss who clicks SEED SWARM in that window skips the check
entirely and falls straight through to:

    HQ.spawnOpenswarmRoster(currentAgents, onHire, shelfBrain)   // shelfBrain === undefined

hq-runtime.jsx's `spawnOpenswarmRoster(existingAgents, addAgent, model)`
treats a falsy `model` as "keep the template's own value" —
`...(model ? { model } : {})` — and every OPENSWARM_ROSTER template pins
`cafresohq:sonnet`. `undefined` and the resolved `null` ("probe finished,
nothing ready") take the exact same falsy branch there; the only thing
standing between either of them and seven coworkers minted onto a
hardcoded Claude model, on a machine that may have no Claude on it at
all, was the caller-side guard — and the guard only covered one of the
two.

This is the same invariant app/cast.jsx's `candidateBrain()` comment
already names: "Returns null when nothing is ready... a card with no
brain is not a card that quietly picks Claude." The card obeyed it. The
hire path, for three seconds on every cold open, did not.

Fixed by giving `probing` its own blocking branch — a distinct "still
checking, try again in a moment" message — ahead of the `!shelfBrain`
check, so no path reaches `spawnOpenswarmRoster` without a resolved
answer, found or not.

Run: python3 scripts/test_seed_swarm_waits_for_probe.py
"""
import json
import re
import subprocess
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIRE = (ROOT / 'modals' / 'hire.jsx').read_text(encoding='utf-8')
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    parens = 0
    j = None
    for k in range(i, len(src)):
        c = src[k]
        if c == '(':
            parens += 1
        elif c == ')':
            parens -= 1
        elif c == '{' and parens == 0:
            j = k
            break
    if j is None:
        raise AssertionError('no body brace found lifting ' + opener)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def main():
    print("SEED SWARM: probing blocks the hire, not just the warning")

    # ── 1. the click handler, isolated ───────────────────────────────────
    # `rfind` because the shelf has two hire-tiles ("+ NEW" then SEED
    # SWARM) and this is the second. A fixed window rather than slicing to
    # the next literal 'SEED' — the fix's own explanatory comment below
    # names "SEED SWARM" by name, which used to be text this test could
    # safely assume appeared nowhere before the visual label itself.
    # The window was 3200, which put `title={probing` at offset 3177 — inside
    # the slice, but with its `?` on the next line falling just outside it, so
    # adding an aria-label to the tile failed a check about code that had not
    # changed. A magic number that a legitimate edit can outgrow reports the
    # wrong thing; widened with room to spare. The end of this JSX element is
    # ~3300 chars in, so this still cannot reach the next component.
    seed = HIRE[HIRE.rfind('hire-tile'):HIRE.rfind('hire-tile') + 4200]

    check('probing has its own blocking branch, checked first',
          re.search(r'if \(probing\)\s*\{', seed),
          'the old guard was `if (!probing && !shelfBrain)` — one '
          'condition doing two jobs, and it only did the second one')

    m = re.search(r'if \(probing\)\s*\{([\s\S]*?)\n\s*\}', seed)
    check('...and that branch returns without hiring anyone',
          m and 'return;' in m.group(1) and 'spawnOpenswarmRoster' not in m.group(1),
          m.group(1) if m else seed[:0])
    check('...with a message distinct from the "no brain" one',
          m and 'no brain' not in m.group(1).lower() and 'checking' in m.group(1).lower(),
          m.group(1) if m else seed[:0])

    check('the no-brain check now stands alone, reached only once resolved',
          re.search(r'if \(!shelfBrain\)\s*\{', seed),
          'if this is still `!probing && !shelfBrain`, the probing branch '
          'above is dead code — both must independently gate the hire')
    check('...and it still names where to add one',
          'Settings → Connections' in seed and 'LM Studio, Ollama' in seed,
          seed[-300:])

    check('the actual hire call still passes the resolved shelfBrain through',
          re.search(r'spawnOpenswarmRoster\(currentAgents,\s*onHire,\s*shelfBrain\)', seed),
          'a fix that stopped forwarding shelfBrain would silently reopen '
          'the sibling ticket (candidates advertise one brain, hire onto '
          'another) that scripts/test_a_candidate_names_the_brain_it_will_use.py covers')

    check('the tile is honest about which state it is in',
          re.search(r'title=\{probing\s*\?', seed),
          '"Hire the whole shelf at once" unconditionally, during the '
          'window where clicking no longer hires anyone, is the same '
          'shape of claim/control mismatch this whole hunt exists to find')

    # ── 2. the mechanism, run for real: what an unresolved model does ────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the mechanism check needs it')
    else:
        roster_m = re.search(r'^const OPENSWARM_ROSTER = \[[\s\S]*?^\];$', RUNTIME, re.M)
        check('OPENSWARM_ROSTER was found in hq-runtime.jsx', roster_m is not None)
        spawn_src = brace_lift(RUNTIME, 'function spawnOpenswarmRoster(')
        js = (roster_m.group(0) + '\n' if roster_m else '') + spawn_src + r'''
function uid(prefix) { return prefix + '_test'; }
const hired = [];
const addAgent = (a) => hired.push(a);
// exactly the call shape `HQ.spawnOpenswarmRoster(currentAgents, onHire, shelfBrain)`
// makes when a boss clicks SEED SWARM before the front-desk probe resolves:
// currentAgents = [] (fresh office), shelfBrain = undefined (still probing).
spawnOpenswarmRoster([], addAgent, undefined);
console.log(JSON.stringify(hired.map(a => a.model)));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the mechanism harness runs', False, p.stderr.strip()[:400])
        else:
            models = json.loads(p.stdout)
            check('spawnOpenswarmRoster was reached and hired the shelf', len(models) >= 5, models)
            check('...every hire landed on the hardcoded template model, '
                  'not "no brain" and not a detected one — an undefined '
                  '`model` argument protects nobody on its own',
                  models and all(m == 'cafresohq:sonnet' for m in models),
                  [models, '— this is exactly what used to happen the '
                   'instant probing let a click reach this call at all; '
                   'the fix has to stop the call, not fix this function, '
                   'because `undefined` is a legitimate model override '
                   'value everywhere else spawnOpenswarmRoster is called '
                   'from (a non-UI caller with no detection to offer)'])

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
