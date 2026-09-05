#!/usr/bin/env python3
"""A brand-new office was offered two live buttons to schedule overnight work.

The Missions modal (missions.jsx) is reachable from the topbar ROOMS menu and
the command palette on the very first page load, before anybody is hired. With
`agents === []` it rendered, top to bottom:

    COWORKER   [                    ▾]      <- agents.map() over nothing
    ...
    24 rounds × ~3 brain calls each   [▶ START RESEARCH]   (disabled, no reason)
    🌙 NIGHT SHIFT
    COWORKER   [                    ▾]
    writes under this name — all night shifts share one brain
    [🌙 SCHEDULE]  [▶ RUN NOW]                              (both ENABLED)

Three separate lies in one modal:

  1. An empty `<select>` paints as a box with a dropdown arrow and nothing in
     it — a boss cannot tell "nobody works here yet" from "the picker failed
     to load".
  2. The research half COSTED a run it had already decided it could not make
     ("24 rounds × ~3 brain calls each") beside a START button disabled for a
     reason it never gave.
  3. The night-shift half left 🌙 SCHEDULE and ▶ RUN NOW fully live. Clicking
     either reached `schedule()`, which answered `topic + agent required` —
     developer shorthand, naming a field ("agent") that appears nowhere on
     this screen, and implying the TOPIC was the problem for a boss who had
     just typed one.

The fix is `noCrewNote(agents)` in missions.jsx: one sentence saying what is
missing and where to go, used by both COWORKER rows, the research footer hint,
the night-shift refusal, and the disabled state of both night-shift buttons.

This test (a) EXECUTES the real `noCrewNote` from missions.jsx under node
against an empty roster and a populated one, and (b) checks the comment-free
source so the empty roster can no longer reach a live scheduling button or the
old machine-shorthand refusal.

Run: python3 scripts/test_a_mission_form_with_nobody_hired_says_so.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MISSIONS = ROOT / 'missions.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Prose ABOUT the old bug is not the old bug. Judge the code only."""
    out = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    out = re.sub(r'(^|\s)//[^\n]*', r'\1', out)
    return out


def main():
    print('a mission form with nobody hired says so')
    if not MISSIONS.is_file():
        check('missions.jsx exists', False, str(MISSIONS))
        return 1
    src = MISSIONS.read_text(encoding='utf-8')
    code = strip_comments(src)

    # ── 1. The real function, run under node ─────────────────────────────
    m = re.search(r'\nfunction noCrewNote\(agents\) \{.*?\n\}\n', src, flags=re.S)
    check('missions.jsx defines noCrewNote(agents)', bool(m))
    if not m:
        return 1

    node = shutil.which('node')
    if not node:
        check('node is available to run the real function', False, 'node not on PATH')
        return 1

    harness = m.group(0) + """
const out = {
  empty:      noCrewNote([]),
  undef:      noCrewNote(undefined),
  notAnArray: noCrewNote(null),
  hired:      noCrewNote([{ id: 'a1', name: 'Kip' }]),
};
console.log(JSON.stringify(out));
"""
    res = subprocess.run([node, '-e', harness], capture_output=True, text=True)
    if res.returncode != 0:
        check('noCrewNote runs under node', False, res.stderr.strip()[:400])
        return 1
    got = json.loads(res.stdout.strip().splitlines()[-1])

    empty = got['empty']
    check('an empty roster gets a sentence, not silence', bool(empty.strip()), repr(empty))
    check('it says nobody is hired yet',
          'coworker' in empty.lower() and ('no ' in empty.lower()[:4] or 'not' in empty.lower()),
          repr(empty))
    check('it names the way forward — hiring, in the Office',
          'hire' in empty.lower() and 'office' in empty.lower(), repr(empty))
    check('it speaks office English, never "agent"',
          'agent' not in empty.lower(), repr(empty))
    check('a missing roster is treated as an empty one, not a crash',
          got['undef'] == empty and got['notAnArray'] == empty,
          (got['undef'], got['notAnArray']))
    check('a hired roster gets nothing — the forms stay out of the way',
          got['hired'] == '', repr(got['hired']))

    # ── 2. Both COWORKER pickers stop painting an empty <select> ─────────
    selects = re.findall(r'<select value=\{agentId\}', code)
    check('both COWORKER pickers still exist', len(selects) == 2, len(selects))
    check('each COWORKER picker is behind the no-crew note',
          len(re.findall(r'noCrewNote\(agents\)\s*\r?\n?\s*\?', code)) >= 2,
          code.count('noCrewNote(agents)'))

    # ── 3. The night-shift buttons cannot be clicked into a refusal ──────
    sched = re.search(r'🌙 SCHEDULE', code)
    runnow = re.search(r'▶ RUN NOW', code)
    check('the night shift still offers SCHEDULE and RUN NOW', bool(sched and runnow))
    if sched and runnow:
        # The <button> element each label closes — walk back to its opening tag.
        for label, at in (('🌙 SCHEDULE', sched.start()), ('▶ RUN NOW', runnow.start())):
            open_at = code.rfind('<button', 0, at)
            tag = code[open_at:at]
            check(f'{label} is disabled while nobody is hired',
                  'disabled={!!noCrewNote(agents)}' in tag,
                  tag.strip()[:160])

    # ── 4. The old machine-shorthand refusal is gone ─────────────────────
    check("no 'topic + agent required' shorthand survives",
          'topic + agent required' not in code)

    # ── 5. The research footer leads with the blocker, not a cost ────────
    footer = re.search(r'rounds × ~3 brain calls each', code)
    check('the research footer still costs a real run', bool(footer))
    if footer:
        block_start = code.rfind('<div className="hint"', 0, footer.start())
        check('…but the no-crew note comes first in that same line',
              'noCrewNote(agents)' in code[block_start:footer.start()],
              code[block_start:footer.start()].strip()[:200])

    print()
    if FAILS:
        print(f'FAILED ({len(FAILS)}): ' + '; '.join(FAILS))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    sys.exit(main())
