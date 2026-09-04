#!/usr/bin/env python3
"""A running Hermes gateway could never be the shelf's brain.

modals/hire.jsx decides which detected runtimes are allowed to become the
brain seven candidate templates are hired onto:

    const candidateReady = (d) => {
      const det = (d && d.detect) || {};
      if (d.id === 'lmstudio' || d.id === 'ollama') return det.version === 'reachable';
      if (d.id === 'hermes') return det.installed && det.version === 'reachable';
      ...

'reachable' is the LOCAL-DAEMON word. drivers/local_http.py writes it, and
only it, from the /models liveness probe. Hermes has never spoken it —
drivers/hermes.py reports its own liveness as

    d['version'] = 'gateway up' if up else ''
    d['probeError'] = '' if up else 'is not running'

so `det.version === 'reachable'` is false on every machine in the world,
gateway up or down. The arm that exists to admit a live Hermes admitted
nothing.

Hermes sits 7th in CANDIDATE_BRAINS, so anywhere a local daemon answers or
a CLI subscription is signed in the wrong answer is masked by a higher
entry. On a Hermes-only office — the house runtime, the one the managed
brain rides — it is the entire shelf, and that one screen said both things
at once:

    AT THE FRONT DESK — found on this machine, ready to join
      Hermes  [FOUND]   Set up on this machine, with its gateway running.

    Vera   VIRTUAL ASSISTANT   no brain yet — add one in Settings → Connections
    Kip    DEEP RESEARCH       no brain yet — add one in Settings → Connections
    ⚡SEED SWARM → "There is no brain on this machine yet, so these 7 would
                    sit at their desks unable to work."

The office contradicting a fact it had just measured, on the first screen a
new boss sees, and the refusal landing on exactly the boss who WAS ready to
hire.

The fix is one word: compare against the string the driver actually emits.
The readiness bar stays where the sibling suite put it — a Hermes whose
gateway is down still gets its NOT RUNNING desk card and is still never
chosen — because `version` is '' in precisely that case.

Run: python3 scripts/test_the_shelf_speaks_the_hermes_drivers_own_word.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIRE = (ROOT / 'modals' / 'hire.jsx').read_text(encoding='utf-8')
CAST = (ROOT / 'app' / 'cast.jsx').read_text(encoding='utf-8')
HERMES_PY = (ROOT / 'drivers' / 'hermes.py').read_text(encoding='utf-8')
LOCAL_PY = (ROOT / 'drivers' / 'local_http.py').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose — the comment that justifies this fix quotes
    every string the checks below hunt for."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """A function body bounded by braces, not by a character count."""
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
    print("the shelf speaks the Hermes driver's own word")
    hire = strip_comments(HIRE)

    # ── 1. what the two drivers actually emit ───────────────────────────
    # The whole defect is a vocabulary mismatch between a Python driver and
    # a JSX reader, so the driver's side is read from the driver, not
    # assumed. If hermes.py ever starts saying 'reachable', this check is
    # the one that should go red first.
    check("hermes.py reports liveness as 'gateway up'",
          re.search(r"d\['version'\]\s*=\s*'gateway up' if up else ''", HERMES_PY),
          'the string the shelf has to compare against')
    check('...and never as a local daemon would',
          "'reachable'" not in HERMES_PY,
          'the word the shelf was comparing against belongs to another driver')
    check("...and marks a stopped gateway with probeError, not with 'reachable'",
          re.search(r"d\['probeError'\]\s*=\s*'' if up else 'is not running'", HERMES_PY))
    check("'reachable' is the local-daemon word, written by local_http.py",
          re.search(r"'version':\s*'reachable' if reachable else ''", LOCAL_PY))

    # ── 2. the reader, read ─────────────────────────────────────────────
    ready_src = brace_lift(hire, 'candidateReady = (d) =>')
    hermes_arm = re.search(r"if \(d\.id === 'hermes'\) return ([^\n;]+);", ready_src)
    check('the hermes readiness arm lifts', bool(hermes_arm), ready_src)
    if hermes_arm:
        check('...and no longer tests hermes against the daemon word',
              "'reachable'" not in hermes_arm.group(1),
              hermes_arm.group(1).strip()
              + " — drivers/hermes.py cannot produce 'reachable', so this "
                'arm was false on every machine, gateway up or down')

    # ── 3. drive the real function against the real detect payloads ─────
    if not shutil.which('node'):
        print('SKIP node half — node not on PATH')
    else:
        js = re.search(r'^const CANDIDATE_BRAINS = \[[\s\S]*?^\];$', CAST, re.M).group(0) + '\n'
        js += brace_lift(strip_comments(CAST), 'function candidateBrain(') + '\n'
        # FRONT_DESK is what candidateReady closes over (the .cloud arm), so
        # it is lifted rather than reimplemented — a reimplementation would
        # be testing this file instead of the app.
        js += re.search(r'^const FRONT_DESK = \{[\s\S]*?^\};$', hire, re.M).group(0) + '\n'
        js += 'const ' + ready_src.rstrip() + ';\n'
        js += r'''
const ready = (list) => list.filter(candidateReady).map(d => d.id);
const D = (id, detect) => ({ id, detect });

/* Exactly what GET /agent/drivers?probe=1 returns for hermes, both ways
   round, straight off drivers/hermes.py's detect(). */
const HERMES_UP   = D('hermes', { installed: true, authenticated: true,
                                  auth: 'config', detail: '/home/u/.local/bin/hermes',
                                  version: 'gateway up', probeError: '', probeDetail: '' });
const HERMES_DOWN = D('hermes', { installed: true, authenticated: true,
                                  auth: 'config', detail: '/home/u/.local/bin/hermes',
                                  version: '', probeError: 'is not running',
                                  probeDetail: 'nothing is listening on 127.0.0.1:8642' });
const NO_HERMES   = D('hermes', { installed: false, version: '', probeError: '' });

const R = {
  up:   ready([HERMES_UP]),
  down: ready([HERMES_DOWN]),
  absent: ready([NO_HERMES]),
  /* The Hermes-only office: the house runtime running, nothing else on
     the machine. This is the screen that said "gateway running" and "no
     brain yet" at the same time. */
  hermesOnlyBrain: candidateBrain(ready([
    D('claude-code', { installed: false }),
    D('codex',       { installed: false }),
    D('gemini',      { installed: false }),
    HERMES_UP,
    D('lmstudio',    { installed: true, version: '' }),
    D('ollama',      { installed: true, version: '' }),
    D('openrouter',  { installed: true, authenticated: false }),
    D('groq',        { installed: true, authenticated: false }),
    D('gemini-api',  { installed: true, authenticated: false }),
  ])),
  /* Same office with the gateway stopped — still no brain, and that is
     the honest answer, not a regression. */
  hermesDownBrain: candidateBrain(ready([
    D('claude-code', { installed: false }),
    HERMES_DOWN,
    D('lmstudio',    { installed: true, version: '' }),
  ])),
  /* The bar does not move for anyone else: a local daemon nobody answered,
     a Codex that ran and failed, a cloud account with no sign-in. */
  daemonUnreachable: ready([D('lmstudio', { installed: true, version: '' })]),
  daemonUp:          ready([D('lmstudio', { installed: true, version: 'reachable' })]),
  codexBroken:       ready([D('codex', { installed: true, probeError: 'exit 1' })]),
  cloudNoAuth:       ready([D('groq', { installed: true, authenticated: false })]),
  /* Free-and-local still outranks the house runtime when both are up. */
  localOverHermes: candidateBrain(ready([
    HERMES_UP, D('ollama', { installed: true, version: 'reachable' })])),
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '--input-type=module', '-e', js],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            check('the readiness harness runs', False, p.stderr.strip()[:500])
        else:
            R = json.loads(p.stdout.strip().split('\n')[-1])
            check('a Hermes whose gateway the probe found UP is ready to take work',
                  R['up'] == ['hermes'],
                  [R['up'], "detect() said version:'gateway up' — the desk card "
                            'printed it, and the shelf refused to believe it'])
            check('...and a Hermes-only office resolves to the Hermes brain',
                  R['hermesOnlyBrain'] == 'hermes:hermes-agent',
                  [R['hermesOnlyBrain'], 'this is the screen where every candidate '
                   'read "no brain yet" over a card reading "gateway running"'])
            check('a stopped gateway is still never chosen',
                  R['down'] == [] and R['hermesDownBrain'] is None,
                  [R['down'], R['hermesDownBrain'],
                   'NOT RUNNING is worth showing and is not the same as '
                   'being able to work'])
            check('...nor is a Hermes that was never installed',
                  R['absent'] == [], R['absent'])
            check('the bar is unmoved for a daemon nobody answered',
                  R['daemonUnreachable'] == [] and R['daemonUp'] == ['lmstudio'],
                  [R['daemonUnreachable'], R['daemonUp']])
            check("...for a Codex that won't start", R['codexBroken'] == [], R['codexBroken'])
            check('...and for a cloud account with no sign-in',
                  R['cloudNoAuth'] == [], R['cloudNoAuth'])
            check('free-and-local still outranks the house runtime',
                  R['localOverHermes'] == 'ollama:llama3.1', R['localOverHermes'])

    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
