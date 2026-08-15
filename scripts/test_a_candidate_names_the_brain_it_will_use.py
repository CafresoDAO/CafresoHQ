#!/usr/bin/env python3
"""Seven candidates advertise a brain the office just failed to find.

Reproduced 2026-08-15 on a live office (port 9259) started with
CAFRESOHQ_CLAUDE_BIN=/nonexistent/claude — a machine with no Claude on it,
which is the ordinary case for a stranger opening this app:

    GET /cafresohq/status   -> {"configured": false, "binary": ""}
    GET /agent/drivers?probe=1 -> claude-code installed:false
                                  lmstudio  version:'reachable'
                                  ollama    version:'reachable'
                                  hermes    installed:true, not reachable

On ONE screen, the front desk correctly DROPPED the Claude card — detection
did its job — and one row below it all seven candidate templates read

    POWERED BY CLAUDE

with a SEED SWARM +7 tile offering to hire every one of them at once. The
office was disagreeing with itself on the same screen about a fact it had
already measured, and the half a first-run boss is most likely to click was
the half that was wrong.

Root cause: `poweredBy(agent)` in app/cast.jsx is a pure function of the
model string, and every OPENSWARM_ROSTER template pins `cafresohq:sonnet`.
Detection played no part. The chip was not reporting a brain, it was
reporting a hardcoded template field — and then SEED SWARM hired seven
coworkers onto it, so the wrong chip became seven silently broken desks.

The fix resolves the brain from the SAME detection the front desk is drawn
from, free-and-local first, and lets `null` be a real answer that the card
and the SEED SWARM tile each render as one.

Two things this file is careful about, both learned the hard way here:

  * readiness must be STRICTER than "has a desk card". Hermes gets a card
    reading NOT RUNNING and Codex one reading WON'T START. Both are worth
    showing. Neither can take a job, so neither may be silently chosen as
    the brain seven specialists are hired onto.
  * `undefined` (probing) is not `null` (nothing found). A deep probe takes
    a few seconds, and a shelf that flashes "no brain yet" at every boss
    during those seconds is the same false statement with a short life.

Also covers the adjacent surface, per the ef8c4b0 lesson — a sentence
repaired for the surface someone was looking at is still broken on the one
they weren't. The Getting Started checklist renders step hints under
`!s.done` and nowhere else, so its "Gemma 4 by Cafreso is included" was on
screen in exactly the state that makes it false.

Run: python3 scripts/test_a_candidate_names_the_brain_it_will_use.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAST = (ROOT / 'app' / 'cast.jsx').read_text(encoding='utf-8')
HIRE = (ROOT / 'modals' / 'hire.jsx').read_text(encoding='utf-8')
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FEEDBACK = (ROOT / 'ui' / 'feedback.jsx').read_text(encoding='utf-8')
ONBOARD = (ROOT / 'ui' / 'onboarding.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose.

    Every phrase this file hunts for — 'Settings → Connections', the
    candidate ids, 'no brain yet' — is written out at length in the comments
    that justify the fix, in the same commit. A check that matches its own
    explanation is a check that will pass after the code is deleted.
    """
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """A function body bounded by braces, not by a character count.

    Fourth suite in this repo to need this. Windows written as `{0,N}?` do
    not report "not found" when the code outgrows them — they report a
    confident false statement about whatever they did reach. Two green
    suites were quietly lying this way as recently as 90d98e3.

    The body opener is the first `{` at paren depth ZERO, so a destructured
    parameter (`fn(a, { b = [] } = {})`) can't be mistaken for the body.
    """
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
    print('a candidate names the brain it will actually use')
    cast = strip_comments(CAST)
    hire = strip_comments(HIRE)
    rt = strip_comments(RUNTIME)

    # ── 1. the shelf's brain comes from detection at all ────────────────
    # The one statement the whole ticket turns on, read as a statement. A
    # bare `const shelfBrain =` was not enough: fire-tested, `= undefined`
    # sailed through it — a shelf pinned to "still probing" forever keeps
    # every template's hardcoded model and looks exactly like the defect.
    shelf = re.search(r'^\s*const shelfBrain = (.+);$', hire, re.M)
    check('the hire shelf resolves a brain from the driver probe',
          shelf and 'candidateBrain(readyIds)' in shelf.group(1),
          [shelf.group(1) if shelf else None,
           '— the whole ticket: the chip used to be a pure function of a '
           'hardcoded template field, so no probe result could change it'])
    # ...and the null survives the trip. Moving the fallback out of
    # candidateBrain and onto this line would restore the defect with every
    # node check above still green.
    check('...and nothing found stays nothing found at the call site',
          shelf and not re.search(r"\|\|\s*'[a-z-]+:", shelf.group(1)),
          [shelf.group(1) if shelf else None,
           '— a `|| \'claudecode:sonnet\'` here is the same lie one line '
           'further out than the function this file exercises'])
    check('...computed from the driver list the front desk also reads',
          re.search(r'readyIds\s*=\s*\(driverList \|\| \[\]\)', hire),
          'one readiness computation, or the two rows on one screen '
          'disagree again — this time about which brain')
    check('...and the templates are remapped onto it before they render',
          re.search(r'\.map\(t =>[^\n]*shelfBrain', hire),
          'remapping at hire time instead would leave the card advertising '
          'one brain and the hired coworker running another')
    check('the SEED SWARM tile hires onto that same brain',
          re.search(r'spawnOpenswarmRoster\(currentAgents,\s*onHire,\s*shelfBrain\)', hire),
          'seven cards saying one thing and seven desks doing another')
    check('...and spawnOpenswarmRoster actually accepts it',
          re.search(r'function spawnOpenswarmRoster\(existingAgents, addAgent, model\)', rt),
          'an argument the callee ignores is the inert-control defect '
          'again, one layer down')
    check('...and applies it over the template',
          re.search(r'\.\.\.\(model \? \{ model \} : \{\}\)', rt), rt[:0])

    # ── 2. every candidate model is a model the desk agrees exists ──────
    # The table is a second copy of a fact FRONT_DESK already holds. Copies
    # drift; this is the check that notices.
    desk = dict(re.findall(r"'([a-z-]+)':\s*\{[^}]*?model:\s*'([^']+)'", hire, re.S))
    cands = re.findall(r"\{ id: '([a-z-]+)',\s*model: '([^']+)' \}", cast)
    check('the candidate table was found', len(cands) >= 8, cands)
    drift = [(i, m) for i, m in cands if i in desk and desk[i] != m]
    check('...and every entry names the same model as its front-desk card',
          not drift, drift)

    # ── 3. ordering, nulls and probing, run for real ────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the resolution checks need it')
    else:
        js = re.search(r'^const CANDIDATE_BRAINS = \[[\s\S]*?^\];$', CAST, re.M).group(0) + '\n'
        js += brace_lift(CAST, 'function candidateBrain(') + '\n'
        # candidateReady lives inside the component, so it is lifted with
        # the FRONT_DESK table it closes over rather than reimplemented —
        # a reimplementation here would test this file, not the app.
        js += re.search(r'^const FRONT_DESK = \{[\s\S]*?^\};$', HIRE, re.M).group(0) + '\n'
        js += 'const ' + brace_lift(HIRE, 'candidateReady = (d) =>').rstrip() + ';\n'
        js += r'''
const ready = (list) => list.filter(candidateReady).map(d => d.id);
const D = (id, detect) => ({ id, detect });
const R = {
  // nothing found is a real answer, not a reason to fall back to Claude
  nothing:   candidateBrain([]),
  nullish:   candidateBrain(null),
  // free and local outranks a paid subscription that is also present
  localFirst: candidateBrain(['claude-code', 'ollama']),
  lmOverOllama: candidateBrain(['ollama', 'lmstudio']),
  // ...and a paid subscription outranks metered cloud
  subOverCloud: candidateBrain(['groq', 'codex']),
  onlyPaid:  candidateBrain(['claude-code']),
  // the office as measured on port 9259: no Claude, two local daemons up
  measured:  candidateBrain(ready([
    D('claude-code', { installed: false }),
    D('codex',       { installed: true, probeError: 'exit 1' }),
    D('lmstudio',    { installed: true, version: 'reachable' }),
    D('ollama',      { installed: true, version: 'reachable' }),
    D('hermes',      { installed: true, version: '' }),
  ])),
  // a card is not a brain: Hermes NOT RUNNING, Codex WON'T START, local
  // daemon "installed" from a default URL nobody answered
  hermesDown: ready([D('hermes', { installed: true, version: '' })]),
  codexBroken: ready([D('codex', { installed: true, probeError: 'exit 1' })]),
  daemonUnreachable: ready([D('lmstudio', { installed: true, version: '' })]),
  cloudNoAuth: ready([D('groq', { installed: true, authenticated: false })]),
  cloudAuthed: ready([D('groq', { installed: true, authenticated: true })]),
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the resolution harness runs', False, p.stderr.strip()[:400])
        else:
            R = json.loads(p.stdout)
            check('an office with nothing ready gets no brain, not a default',
                  R['nothing'] is None and R['nullish'] is None, R)
            check('a free local brain outranks a paid subscription',
                  R['localFirst'] == 'ollama:llama3.1', R['localFirst'])
            check('...and LM Studio outranks Ollama, deterministically',
                  R['lmOverOllama'] == 'lmstudio:local-model', R['lmOverOllama'])
            check('a flat-rate subscription outranks metered cloud',
                  R['subOverCloud'] == 'codex:gpt-4.1', R['subOverCloud'])
            check('a paid subscription is still used when it is all there is',
                  R['onlyPaid'] == 'claudecode:sonnet', R['onlyPaid'])
            check('the reproduced office resolves to its local brain',
                  R['measured'] == 'lmstudio:local-model',
                  [R['measured'], '— port 9259: Claude absent, LM Studio and '
                   'Ollama both reachable. This is the exact screen that '
                   'said POWERED BY CLAUDE seven times.'])
            check('a Hermes that is not running is never chosen',
                  R['hermesDown'] == [],
                  'it gets a desk card reading NOT RUNNING, which is worth '
                  'showing and is not the same as being able to work')
            check("...nor a Codex that won't start", R['codexBroken'] == [], R['codexBroken'])
            check('...nor a local daemon nobody answered',
                  R['daemonUnreachable'] == [],
                  "detect.installed is true from the default URL alone")
            check('a cloud account needs a real sign-in',
                  R['cloudNoAuth'] == [] and R['cloudAuthed'] == ['groq'],
                  [R['cloudNoAuth'], R['cloudAuthed']])

    # ── 4. probing is not "nothing found" ───────────────────────────────
    check('a still-probing shelf leaves the template alone',
          re.search(r'shelfBrain === undefined \? t :', hire),
          'undefined and null are different answers — treating the probe '
          'window as "nothing found" flashes a false line at every boss '
          'for the seconds a deep probe takes')
    check('...and probing is exactly the null driver list',
          re.search(r'const probing = driverList === null', hire), hire[:0])

    # ── 5. the card renders "no brain" as a door, not as a vendor ───────
    cast_line = brace_lift(HIRE, 'function CastLine(')
    check('the card falls through to a no-brain line',
          re.search(r"'no brain yet[^']*'", cast_line),
          'null has to look like null on screen, or the fix only moved the '
          'lie from "Claude" to a blank chip')
    check('...that names somewhere to go',
          re.search(r"no brain yet[^']*Settings → Connections", cast_line),
          '§7: every failure is one honest sentence PLUS a way forward')
    check('...and a resolved brain is still named on the card',
          'brainName(t)' in cast_line,
          'the boss has to be able to see which brain they are hiring onto')

    # ── 6. SEED SWARM refuses rather than hiring seven dead desks ───────
    seed = HIRE[HIRE.index('hire-tile'):]
    seed = seed[:seed.index('SEED')]
    check('the seed tile checks for a brain before promising anything',
          re.search(r'if \(!probing && !shelfBrain\)', seed),
          'the confirm used to cheerfully offer to hire seven specialists '
          'onto a brain that does not exist')
    check('...and says where to get one',
          'Settings → Connections' in seed, seed[-300:])
    check('...naming the free options',
          re.search(r'LM Studio, Ollama', seed),
          'a first-run boss reading "add a brain" should not conclude they '
          'have to buy one')

    # ── 7. the dialog option is not itself an inert control ─────────────
    # Fixing an inert checkbox by passing an unsupported dialog option would
    # be this exact ticket, one file over.
    check('hqConfirm actually honours hideCancel',
          re.search(r'!req\.opts\.hideCancel', FEEDBACK),
          'the guard passes hideCancel:true; DialogHost rendered Cancel '
          'unconditionally, so the option would have been decoration')
    check('...and the cancel button is what it gates',
          re.search(r'!req\.opts\.hideCancel && \(\s*<button className="px-btn secondary"', FEEDBACK),
          FEEDBACK[:0])

    # ── 8. the adjacent surface: the checklist's brain step ─────────────
    onboard = strip_comments(ONBOARD)
    step = re.search(r"\{ k: 'key',[^\n]*\}", onboard)
    check('the Getting Started brain step was found', step, 'ui/onboarding.jsx')
    if step:
        line = step.group(0)
        check('...and no longer announces an included brain',
              'Gemma' not in line and 'included' not in line,
              [line, '— hints render under !s.done, so this sentence was on '
               'screen only for offices that had no brain'])
        check('...while still pointing at the button that exists everywhere',
              "cta: 'Brain settings'" in line, line)
    check('...and the hint names no tab that only half the readers have',
          not re.search(r"hint: '[^']*Connections", onboard),
          'CONNECTIONS is filtered out of the nav on managed — naming it '
          'here is the §5 problem, not the fix for it')

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
