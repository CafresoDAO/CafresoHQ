#!/usr/bin/env python3
"""A screenshot that was never taken was credited as a trip that arrived.

`BROWSER_SCREENSHOT` drives a Chromium over CDP. A browser that is not
running with --remote-debugging-port=9222 is the ORDINARY state of this
tool, and serve.py answers that politely: HTTP 200, `{"error": ..., "hint":
...}`. Nothing throws. The tool composed the office's own sentence for it —
"Couldn't take that screenshot — …" — and returned it as its RESULT.

hq-runtime.jsx's tool loop only learns that a tool failed two ways: the call
throws, or the tool says so out of band on `meta.failed`. This one did
neither, so the `done` event went out with `failed: false` and every reader
of the visit record treated the trip as one that arrived:

  - `visitTense` (app/floor.jsx) returns 'past', so the visit header and the
    activity row read "Captured <url>" over the tool's own "Couldn't take
    that screenshot" in the same element — the exact shape the sibling fix
    on BROWSER_FETCH one block up names ("Opened ./site" directly above
    "Not a directory: ./site");
  - `workingNotes` writes that past tense into the FILED delivery sheet,
    the record that outlives the session;
  - `buildDelivery`'s `consulted` test — `(visits||[]).some(v => v && v.name
    && !v.failed)` — counts it as a source this run genuinely opened, and
    that test is what decides whether a reply full of citations gets the
    "nothing was opened or searched while it was written — treat those as
    recalled" caveat. One failed screenshot was enough to suppress it.

BROWSER_FETCH, eleven lines above it in the same registry, was taught
`meta.failed` for exactly this and its sibling was not.

Fix (#410): the `j.error` branch sets `meta.failed = true`, and the run
signature destructures `meta` so it can.

Round 1 drives the REAL lifted `run` bodies of both browser tools under node
against a stub `/browser/*` shim, with the same `{ signal, meta }` context
object the tool loop builds, and reads `meta.failed` back.

Round 2 feeds the resulting visit into the REAL readers — `visitTense`,
`workingNotes` and `buildDelivery` out of app/floor.jsx + app/artifacts.jsx
— and asserts the delivery sheet says the page was NOT captured and that a
citing reply still earns its caveat.

Round 3 is the part meant to outlive this ticket: it walks every `run` body
in hq-runtime.jsx (registry AND the per-agent rebindings in toolsForAgent)
and requires that any body composing an office-voice failure sentence
("Couldn't …" / "That didn't work") also reaches `meta.failed`. A twelfth
tool that answers politely with a refusal fails this check instead of
quietly re-opening the bug.

Run: python3 scripts/test_a_screenshot_that_never_happened_is_not_a_visit.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'
ARTIFACTS = ROOT / 'app' / 'artifacts.jsx'

RUNTIME_RAW = RUNTIME.read_text(encoding='utf-8')

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = '') -> None:
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond and detail else ''))
    if not cond:
        FAILS.append(name)


def strip_module_lines(path: Path) -> str:
    return '\n'.join(ln for ln in path.read_text(encoding='utf-8').split('\n')
                     if not ln.startswith('import ') and not ln.startswith('export '))


def brace_body(src: str, start: int) -> str:
    """The `{ … }` body beginning at or after `start`. '' if unbalanced."""
    j = src.find('{', start)
    if j < 0:
        return ''
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[j:k + 1]
    return ''


def lift_tool_run(name: str) -> str:
    """The real `run:` arrow of one registry tool, as a standalone async fn.

    Returns '' when the tool or its brace body can't be found, so a rename
    reports one clean FAIL rather than raising out of the whole run.
    """
    m = re.search(r"^\s{4}name: '" + re.escape(name) + r"',$", RUNTIME_RAW, re.M)
    if not m:
        return ''
    r = RUNTIME_RAW.find('run: async ', m.end())
    if r < 0:
        return ''
    arrow = RUNTIME_RAW.find('=>', r)
    if arrow < 0:
        return ''
    sig = RUNTIME_RAW[r + len('run: '):arrow].strip()
    body = brace_body(RUNTIME_RAW, arrow)
    if not body:
        return ''
    return f'const run_{name} = {sig} => {body};'


HARNESS = r'''
__FLOOR__
__ARTIFACTS__
__TOOLS__

const R = {};

/* The shim serve.py actually is when no Chromium is listening: HTTP 200,
   a polite {error, hint}, nothing thrown. */
const SHOT_REFUSAL = { error: 'no Chromium on the debugging port',
                       hint: 'launch Brave with --remote-debugging-port=9222' };
let NEXT = SHOT_REFUSAL;
globalThis.fetch = async () => ({ ok: true, json: async () => NEXT });

/* The context object hq-runtime's tool loop builds, verbatim:
     const meta = {};
     result = await call.tool.run(call.arg, { signal, cwd, meta }, call.body); */
async function drive(fn, arg) {
  const meta = {};
  let result, threw = null;
  try { result = await fn(arg, { signal: undefined, cwd: undefined, meta }); }
  catch (e) { threw = String(e && e.message || e); }
  return { result, threw, failed: !!meta.failed };
}

NEXT = SHOT_REFUSAL;
R.shotRefused = await drive(run_BROWSER_SCREENSHOT, 'https://example.com');
NEXT = { url: 'https://example.com', width: 1200, height: 800, png: 'data:image/png;base64,AAA' };
R.shotOk = await drive(run_BROWSER_SCREENSHOT, 'https://example.com');
/* The sibling that already had it — the control. */
NEXT = { error: 'that host does not resolve' };
R.fetchRefused = await drive(run_BROWSER_FETCH, 'https://nope.example');

/* ── the readers ─────────────────────────────────────────────────────── */
const visitOf = (d) => ({ name: 'BROWSER_SCREENSHOT', arg: 'https://example.com',
                          echo: '', failed: d.failed, outcome: '' });

R.tenseRefused = visitTense(visitOf(R.shotRefused));
R.tenseOk      = visitTense(visitOf(R.shotOk));
R.notesRefused = workingNotes([visitOf(R.shotRefused)]);
R.notesOk      = workingNotes([visitOf(R.shotOk)]);

/* A reply that cites the page it could not capture. `consulted` inside
   buildDelivery is the reader under test. */
const CITING = 'The pricing page at https://example.com lists three tiers, and '
  + 'the middle one is the volume break most teams land on. That is the one to quote.';
const task = { id: 't1', title: 'Check their pricing' };
const agent = { name: 'Kip' };
R.sheetRefused = buildDelivery(task, agent, CITING, [visitOf(R.shotRefused)]);
R.sheetOk      = buildDelivery(task, agent, CITING, [visitOf(R.shotOk)]);

console.log(JSON.stringify(R));
'''


def run_js() -> dict | None:
    floor = strip_module_lines(FLOOR)
    arts = strip_module_lines(ARTIFACTS)
    # cabinetIsEncrypted / fileDelivery reach for browser-only globals.
    for fn in ('function cabinetIsEncrypted', 'async function fileDelivery'):
        i = arts.find(fn)
        if i < 0:
            continue
        body = brace_body(arts, i)
        if body:
            arts = arts[:i] + arts[arts.find(body, i) + len(body):]

    tools = []
    for name in ('BROWSER_SCREENSHOT', 'BROWSER_FETCH'):
        lifted = lift_tool_run(name)
        check(f'{name} run lifted out of hq-runtime.jsx', bool(lifted))
        tools.append(lifted)
    if not all(tools):
        return None

    script = (HARNESS.replace('__FLOOR__', floor)
                     .replace('__ARTIFACTS__', arts)
                     .replace('__TOOLS__', '\n'.join(tools)))
    p = subprocess.run(['node', '--input-type=module', '-e', script],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        check('the node harness ran', False, (p.stderr or p.stdout)[-500:])
        return None
    check('the node harness ran', True)
    try:
        return json.loads(p.stdout.strip().split('\n')[-1])
    except Exception as e:
        check('the harness printed a result', False, f'{e}: {p.stdout[-300:]}')
        return None


def behaviour_checks(out: dict) -> None:
    print('round 1 — the real run bodies, driven with the loop\'s own meta object')
    shot, ok, fet = out['shotRefused'], out['shotOk'], out['fetchRefused']
    print('    refused screenshot -> ' + json.dumps(shot))
    print('    ok screenshot      -> failed=' + str(ok['failed']))

    # Non-vacuous: the refusal really is the polite, non-throwing shape.
    check('the refusal does not throw and answers in the office voice',
          shot['threw'] is None and "Couldn't take that screenshot" in (shot['result'] or ''),
          json.dumps(shot))
    check('a refused BROWSER_SCREENSHOT sets meta.failed', shot['failed'] is True)
    check('a SUCCESSFUL screenshot leaves meta.failed clear', ok['failed'] is False)
    check('the sibling BROWSER_FETCH still sets it (control)', fet['failed'] is True)

    print('round 2 — what each reader of that visit concludes')
    print('    visitTense: refused=' + str(out['tenseRefused'])
          + '  ok=' + str(out['tenseOk']))
    print('    workingNotes(refused): ' + json.dumps(out['notesRefused']))
    check('visitTense reads a refused screenshot as a failure, not the past',
          out['tenseRefused'] == 'fail', out['tenseRefused'])
    check('visitTense still reads a real one as the past',
          out['tenseOk'] == 'past', out['tenseOk'])
    # The floor's VISIT_WORDS give both browser tools the same verb, so the
    # sheet's line for a refused screenshot is "Couldn't read <url>" and for
    # a real one "Read <url>". What matters is which of the two it writes.
    check('the filed sheet does not say the page was visited',
          bool(out['notesRefused'])
          and all(ln.startswith("- Couldn't") for ln in out['notesRefused']),
          json.dumps(out['notesRefused']))
    check('a real capture IS still written in the past tense (non-vacuous)',
          bool(out['notesOk'])
          and all(not ln.startswith("- Couldn't") for ln in out['notesOk']),
          json.dumps(out['notesOk']))

    refused_sheet = (out.get('sheetRefused') or {}).get('content') or ''
    ok_sheet = (out.get('sheetOk') or {}).get('content') or ''
    check('a citing reply whose only trip was refused earns the recalled caveat',
          'recalled' in refused_sheet,
          refused_sheet[-400:])
    check('the same reply after a REAL capture does not (non-vacuous)',
          'recalled' not in ok_sheet, ok_sheet[-400:])


# ── Round 3: the general sweep ─────────────────────────────────────────────
FAIL_SENTENCE = re.compile(r"Couldn't |That didn't work")


def sweep_checks() -> None:
    print("round 3 — every run body that composes a refusal must say so on meta")
    src = re.sub(r'/\*[\s\S]*?\*/', '', RUNTIME_RAW)
    src = re.sub(r'^\s*//.*$', '', src, flags=re.M)
    bodies = []
    for m in re.finditer(r'run: async ', src):
        arrow = src.find('=>', m.start())
        if arrow < 0:
            continue
        body = brace_body(src, arrow)
        if not body:
            # A one-expression arrow (FILE_READ etc.) — nothing to sweep.
            continue
        bodies.append((m.start(), body))
    check('run bodies were found to sweep', len(bodies) >= 10, str(len(bodies)))
    offenders = []
    for pos, body in bodies:
        if FAIL_SENTENCE.search(body) and 'meta.failed' not in body:
            offenders.append('line ' + str(src[:pos].count('\n') + 1))
    check('no tool answers with a refusal it never reports on meta.failed',
          not offenders, ', '.join(offenders))


def main() -> int:
    print('a refused BROWSER_SCREENSHOT is not a trip that arrived')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    out = run_js()
    if out is not None:
        behaviour_checks(out)
    sweep_checks()
    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed: ' + ', '.join(FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
