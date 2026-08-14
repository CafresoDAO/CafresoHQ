#!/usr/bin/env python3
"""The office certified a job whose deliverable was its own error notes.

Measured on a fresh office, second run of a task brief. The card sat green
in DONE, and the entire stored result was:

    no helper was ever brought in — that needs the task on its own lines
    and a closing tag. Ask them to try again, or hand the job to a
    coworker yourself.
    no file reached the cabinet — that one needs a closing tag to be
    written, so the Vault does not have it. Ask them to file it again.

Both sentences are the OFFICE's. It printed them itself, from its own
guards, and then marked the job complete. Nothing else was stored, because
nothing else existed: the reply cleaned down to empty.

What makes it a defect rather than an oversight is that the same boolean
was already being read correctly two lines away. `if (cleanBuf.trim())`
gates the filing and gates the journal entry — the office declines to put
an empty run in the cabinet and declines to write it into the coworker's
history, then marks the card DONE. Three decisions off one fact, two
honest.

So `produced` is now read by all six surfaces that assert an outcome:

  the board       done  →  doing + blockedReason
  the card's why  (none) →  the honesty notes, which already carry a
                            way forward and were being shown on a DONE card
  the feed row    finished "…" — but not all of it landed  →  came back
                            from "…" with nothing
  the XP ledger   done  →  snag, so the office does not learn that a
                            coworker who produced nothing is reliable
  the desk badge  ✓ done →  stuck
  the desk's line the task TITLE  →  "came back with nothing"

That last one is its own small lie and worth naming: `recent` fell back to
`task.title`, so a coworker who wrote nothing had the boss's own brief
quoted on their desk as if it were their work.

Run: python3 scripts/test_done_means_something_was_done.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'
XP = ROOT / 'app' / 'experience.jsx'
OFFICE = ROOT / 'ui' / 'office.jsx'
FAILS = []


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


def run_js(src):
    p = subprocess.run(['node', '--input-type=module', '-e', src],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('done means something was done')
    app = APP.read_text(encoding='utf-8')
    floor = FLOOR.read_text(encoding='utf-8')

    # The run block, so a stray `produced` elsewhere in a 5000-line file
    # cannot make any of these pass.
    i = app.index('const cleanBuf = HQ.cleanHarmony(HQ.visibleReply(stripToolEcho(buf, '
                  'toolVisits.map(v => v.echo)), agent && agent.name));')
    block = app[i:app.index('if (cleanBuf.trim()) appendJournal(', i)]

    check('the run decides once whether anything was produced',
          re.search(r'const produced = !!cleanBuf\.trim\(\);', block),
          'the filing and the journal already read this exact expression; '
          'a second, differently-worded test is how the three drift apart')

    # ── the six surfaces ─────────────────────────────────────────────────
    check('the board does not certify an empty run',
          re.search(r"applyStatus\(t, produced \? 'done' : 'doing'\)", block),
          "this is the green DONE the boss reads first")
    check('...and the card says why it is not done',
          re.search(r'blockedReason: emptyReason', block)
          and re.search(r'blockedAt: Date\.now\(\)', block),
          'a card parked in doing with no reason is worse than the false '
          'DONE it replaces — at least DONE said something')
    check('...with a fallback for when no guard fired at all',
          re.search(r"const emptyReason = honestyText\.trim\(\)\s*\|\|", block),
          'a model can return whitespace, or nothing but scaffolding the '
          'cleaner removes, and no honesty note fires on either')
    check('the feed row says nothing landed',
          re.search(r'doneLine\(task\.title, honesty\.length, !produced\)', block),
          '"finished — but not all of it landed" reads as a mostly-good '
          'turn; none of it landed')
    check('the experience ledger books a snag',
          re.search(r"outcome: produced \? 'done' : 'snag'", block),
          'paying out a completion teaches the office that a coworker who '
          'produced nothing is reliable, which is the ledger inverted')
    check('the desk badge shows stuck',
          re.search(r"mood: produced \? 'done' : 'stuck'", block),
          'MOOD_ICON renders \'\' for an unknown mood, so an invented word '
          'here is a blank badge — the one state that looks like no state')
    check("...and the desk stops quoting the boss's own brief back",
          re.search(r"recent: produced \? cleanBuf\.slice\(0, 140\) : ", block)
          and 'cleanBuf.slice(0, 140) || task.title' not in block,
          'the fallback to task.title put the brief on the coworker\'s desk '
          'as though it were the work they had just finished')
    check('the announcement does not say completed',
          re.search(r"produced \? 'DONE' : 'SNAG'", block),
          'the spoken line is a surface too, and it was the sixth copy of '
          'the same false claim')

    # ── the vocabulary these reuse has to actually contain the words ─────
    check("'stuck' is a mood the floor can draw",
          re.search(r"MOOD_ICON = \{[^}]*stuck:", OFFICE.read_text(encoding='utf-8')),
          'reusing the established word is the whole point of picking it')
    check("'snag' is an outcome the ledger accepts",
          re.search(r"outcome !== 'done' && outcome !== 'snag'",
                    XP.read_text(encoding='utf-8')),
          'xpRecord drops anything else on the floor silently, so an '
          'invented outcome would book no entry at all')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arms')
        return 1 if FAILS else 0

    # ── the feed's third state ───────────────────────────────────────────
    js = (brace_lift(floor, 'function doneLine(subject, missed, empty) {')
          + '\nconst R = {};\n'
          "R.clean = doneLine('Save a note', 0);\n"
          "R.missed = doneLine('Save a note', 2);\n"
          "R.empty = doneLine('Save a note', 2, true);\n"
          "R.emptyNoGuard = doneLine('Save a note', 0, true);\n"
          "R.emptyNoSubject = doneLine('', 0, true);\n"
          'console.log(JSON.stringify(R));')
    r = run_js(js)

    check('a run that produced nothing does not say finished',
          'finished' not in r['empty'] and 'nothing' in r['empty'],
          f"{r['empty']} — the word the boss scans for is \"finished\"")
    check('...and says so whether or not a guard fired',
          r['emptyNoGuard'] == r['empty'],
          f"{r['emptyNoGuard']} vs {r['empty']} — an empty run with no note "
          'is the quieter failure, not the smaller one')
    check('...and still works with no subject',
          r['emptyNoSubject'] and 'nothing' in r['emptyNoSubject']
          and '""' not in r['emptyNoSubject'],
          f"{r['emptyNoSubject']} — an empty pair of quotes is the shape "
          'the two older branches were careful to avoid')
    check('a real finish is untouched', r['clean'] == 'finished "Save a note" ✓',
          f"{r['clean']} — the common path must not change")
    check('...and so is a partial one',
          r['missed'] == 'finished "Save a note" — but not all of it landed',
          f"{r['missed']} — partial and empty are different claims and the "
          'feed now has a word for each')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
