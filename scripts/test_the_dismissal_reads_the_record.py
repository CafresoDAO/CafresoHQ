#!/usr/bin/env python3
"""A failed helper was dismissed as "task complete".

Measured 2026-08-15 on office 9261, canned brain. Vera brought in a
transient helper (Sub-fact-wpv) whose one dispatch died on the wire with
an HTTP 500. The office was honest everywhere it looked first: the
helper's bubble said the brain's service was having trouble, the boss got
a snag notice on the direct thread, and the registry filed the spawn
message 'failed' ("unknown: Inspect error and retry"). Thirty seconds
later, in the same team room, the dismissal timer posted

    🍂 Sub-fact-wpv (transient) dismissed — task complete.

— unconditionally, over a dispatch whose errors are swallowed by
`catch (_e) {}`. The office contradicted its own record half a minute
after writing it (#67 family: backing a claim it knew was false).

The fix makes the goodbye READ the outcome instead of asserting one: at
timer fire the handler looks up the spawn's registry record
(MessageRegistry.getMessage(spawnMsgId) — the dispatch is awaited, so the
run has settled long before the timer) and words the line to match:
completed keeps "task complete.", failed says the task hit a snag,
cancelled says the run was stopped early, blocked says so, and a missing
or unsettled record claims nothing beyond the one thing the office
actually did ("desk cleared.").

Run: python3 scripts/test_the_dismissal_reads_the_record.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('the dismissal reads the record')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)

    # ── the goodbye is written once, and its verdict is interpolated ────
    # Pin the FACT: the dismissal text carries a computed outcome, not a
    # hard-coded claim. Outlawing the old spelling alone would let the
    # defect survive in paraphrase ("— all done."), so the checks are on
    # the shape (interpolation + registry read), then on behavior below.
    n = bare.count('(transient) dismissed')
    check('the dismissal line has one writer', n == 1, f'{n} sites')

    tpl = '(transient) dismissed — ${'
    check('the goodbye interpolates its verdict', bare.count(tpl) == 1,
          'a fixed string here is an assertion; the timer fires long '
          'after the run settled and must look, not remember')

    if bare.count(tpl) == 1:
        at = bare.index(tpl)
        window = bare[max(0, at - 900):at]
        check('the verdict is read from the spawn record at fire time',
              'MessageRegistry.getMessage(spawnMsgId)' in window,
              'the registry already holds the outcome — the dispatch is '
              'awaited, so by timer fire the story is written')
        check('the helper still leaves the floor',
              re.search(r"setAgents\(prev => prev\.filter\(a => a\.id !== "
                        r"transientAgent\.id\)\)", window + bare[at:at + 200])
              is not None,
              'reading the record must not stop the dismissal itself')
        seg = bare[at - 200:at + 120]
        check('the goodbye stays office voice in the team room',
              "from: 'system', name: 'HQ'" in seg
              and "thread: 'team'" in seg, seg[:160])

    # ── behavior: the lifted verdict, driven across every outcome ───────
    m = re.search(
        r"const rec = MessageRegistry\.getMessage\(spawnMsgId\);\s*"
        r"const outcome = (rec && rec\.state.*?: 'desk cleared\.');",
        bare, re.S)
    check('the verdict expression lifts', m is not None,
          'the ternary chain from rec to the desk-cleared fallback')
    if m is None or not shutil.which('node'):
        if shutil.which('node') is None:
            print('  SKIP  node not on PATH — behavior checks need it')
        print()
        if FAILS:
            print(f'dismissal-record: {len(FAILS)} FAILED')
            return 1
        print('dismissal-record: source checks passed')
        return 0

    js = (
        f'const outcomeFor = (rec) => ({m.group(1)});\n'
        + '''
const R = {
  completed: outcomeFor({ state: 'completed' }),
  failed: outcomeFor({ state: 'failed' }),
  cancelled: outcomeFor({ state: 'cancelled' }),
  blocked: outcomeFor({ state: 'blocked' }),
  gone: outcomeFor(null),
  unsettled: outcomeFor({ state: 'in_progress' }),
};
console.log(JSON.stringify(R));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted verdict runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a completed run is still sent off as task complete',
          r['completed'] == 'task complete.', r['completed'])
    check('a failed run is never dismissed as complete',
          'complete' not in r['failed'] and 'snag' in r['failed'],
          [r['failed'], '— the measured lie: registry said failed, the '
           'goodbye said task complete'])
    check('a stopped run says it was stopped',
          'complete' not in r['cancelled'] and 'stopped' in r['cancelled'],
          r['cancelled'])
    check('a blocked run says it is blocked',
          'complete' not in r['blocked'] and 'blocked' in r['blocked'],
          r['blocked'])
    check('a missing record claims nothing it did not see',
          'complete' not in r['gone'], r['gone'])
    check('an unsettled record claims nothing either',
          'complete' not in r['unsettled'], r['unsettled'])

    print()
    if FAILS:
        print(f'dismissal-record: {len(FAILS)} FAILED — '
              + ', '.join(FAILS[:3]))
        return 1
    print('dismissal-record: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
