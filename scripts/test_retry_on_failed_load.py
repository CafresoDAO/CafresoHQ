#!/usr/bin/env python3
"""Track 6 P1: a failed automatic load must offer a way back, in the right words.

Two separate defects on the Settings → Connections panel — the surface that
answers "what brains do I have?", which is the §3.6 detection promise made
inspectable.

**No way forward.** The driver probe runs once on mount inside a `useEffect`,
with no control behind it. When it failed the panel showed a red line and
stayed empty for the rest of the session. Every other failure in that file
sits behind a button the boss can press again; this one had nothing. That is
Track 6's "error-recovery/retry UI on failed async ops" and §7's second half.

**And the wrong words.** The first fix routed it through `snagCause`, which
produced:

    Couldn't check what's on this machine — couldn't reach that brain —
    it looks offline from here.

Every sentence in `SNAG_CAUSES` names a BRAIN, because the table was written
for coworker dispatch. Nothing on this screen is one: the probe asks the
office's OWN backend which brains exist, and the modules panel talks to the
chain bridge. Routing them through it trades a raw dump for a confident
misdiagnosis, which is worse — it sends the boss to check the wrong thing.

Hence `cleanCause`: snagCause's sanitiser without its diagnosis. Use
snagCause where a brain really is the subject, cleanCause where it is not.

The probe itself needs neither, because it knows more than the text does:
whether the office ANSWERED is the only distinction the boss can act on, and
it is knowable from whether the fetch threw. Two sentences, two different
things to check, no HTTP codes.

Run: python3 scripts/test_retry_on_failed_load.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR = ROOT / 'app' / 'floor.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_js(cases_js):
    text = FLOOR.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('retry on failed load — a dead automatic load needs a door, and honest words')
    if not FLOOR.is_file() or not SETTINGS.is_file():
        print('  FAIL  missing source file(s)')
        return 1
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    s = SETTINGS.read_text(encoding='utf-8')

    # ── cleanCause: sanitises without diagnosing ────────────────────────
    out = run_js(r'''
const R = {};
R.exists      = typeof cleanCause === 'function';
R.offline     = cleanCause('Failed to fetch');
R.snagOffline = snagCause('Failed to fetch');
R.url         = cleanCause('POST https://api.example.com/v1/x failed');
R.jsonish     = cleanCause('{"error":["bad"]}');
R.multiline   = cleanCause('first line\nsecond line\nthird');
R.long        = cleanCause('x'.repeat(400)).length;
R.empty       = cleanCause('');
R.nullish     = cleanCause(null);
console.log(JSON.stringify(R));
''')

    check('cleanCause exists and is exported',
          out['exists'] and 'cleanCause' in FLOOR.read_text(encoding='utf-8').split('export {')[-1],
          'app/floor.jsx: surfaces whose subject is not a brain need the sanitiser '
          'without the diagnosis')
    check('cleanCause does NOT invent a brain diagnosis',
          'brain' not in out['offline'].lower(),
          f"got {out['offline']!r} — this is the whole reason it exists")
    check('...while snagCause still does, for surfaces where a brain IS the subject',
          'brain' in out['snagOffline'].lower(),
          f"got {out['snagOffline']!r} — splitting these must not defang the "
          'classifier that dispatch failures depend on')
    check('cleanCause still strips URLs, JSON shrapnel and extra lines',
          'https://' not in out['url'] and '{' not in out['jsonish']
          and '\n' not in out['multiline'] and out['multiline'] == 'first line',
          f"{out['url']!r} / {out['jsonish']!r} / {out['multiline']!r} — §7 forbids "
          'raw dumps whether or not a cause is named')
    check('...and caps length, and survives empty input',
          out['long'] <= 90 and out['empty'] and out['nullish'],
          f"len={out['long']} empty={out['empty']!r} null={out['nullish']!r}")

    # ── The Settings panel must not borrow brain vocabulary ─────────────
    check('Settings routes its failures through cleanCause, not snagCause',
          'cleanCause' in s and not re.search(r'\bsnagCause\s*\(', s),
          'modals/settings.jsx: the probe asks the office\'s own backend and the '
          'modules panel talks to the chain — neither is a brain')
    check('no raw String(e.message) dumps remain',
          not re.search(r'setErr\(String\(', s),
          'modals/settings.jsx: §7 — no raw error dumps')

    # ── The retry itself ────────────────────────────────────────────────
    check('the probe is hoisted out of the effect so it can be re-run',
          re.search(r'const probeDrivers = useCallbackM\(', s) is not None
          and re.search(r'useEffectM\(\(\) => \{ probeDrivers\(\); \}', s) is not None,
          'modals/settings.jsx: a probe defined inside its own useEffect cannot be '
          'called by a button')
    check('the failure renders a control wired back to the probe',
          re.search(r'onClick=\{probeDrivers\}', s) is not None
          and 'CHECK AGAIN' in s,
          'modals/settings.jsx: the honest sentence needs a door next to it')
    check('...and that control reports its own progress',
          re.search(r'disabled=\{probing\}', s) is not None,
          'modals/settings.jsx: a retry that looks inert on the second press '
          'invites the boss to conclude it is broken too')
    check('the retry clears the previous failure before re-running',
          re.search(r"setProbing\(true\);\s*\n\s*setErr\(''\);", s) is not None,
          'modals/settings.jsx: otherwise a successful retry leaves the old red '
          'line on screen under a working list')

    # ── The two sentences: knowable, distinct, and code-free ────────────
    probe = s[s.find('const probeDrivers'):s.find('useEffectM(() => { probeDrivers')]
    check('the probe distinguishes "no answer" from "answered badly"',
          'answered = true' in probe and 'isn’t answering' in probe
          and 'couldn’t list' in probe,
          'modals/settings.jsx: these send the boss to two different places')
    check('...and neither sentence prints a status code',
          not re.search(r"setErr\([^)]*HTTP", probe),
          'modals/settings.jsx: "HTTP 500" is the raw dump with extra steps')

    print()
    if FAILS:
        print(f'retry on failed load: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('retry on failed load: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
