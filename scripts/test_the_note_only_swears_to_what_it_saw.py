#!/usr/bin/env python3
"""The cabinet note swore to more than its witness saw.

Measured 2026-08-15 on office 9261, task "briefing status", canned brain.
The coworker's whole reply was a prose promise — "Saved the briefing to
Drafts/briefing.md for you." — with an empty visit log, so the note fired,
and it was right to. But it said:

    `Drafts/briefing.md` is named above, but nothing was written to the
    cabinet on this run, so that file is not there.

and the DONE card carrying that sentence had an artifact row reading
Deliveries/briefing-status.md — a file the office wrote to the cabinet on
that very run. The note's witness is the SPEAKER'S visit log, nothing more.
It cannot see the office's own delivery filing (fileDelivery runs after the
notes are computed), and it cannot see what earlier runs left in the
cabinet, so both extra clauses were guesses wearing a verdict's clothes:
"nothing was written to the cabinet" — falsified by the office moments
later; "that file is not there" — falsified by any earlier run that filed
it. (The coworker writing OTHER files cannot falsify it: any cabinet write
by the speaker already silences the guard entirely, pinned in #50's suite.)

The fix narrows the sentence to the witness: they never wrote it to the
cabinet on this run — ask them to file it if you need it. What the office
did file is the artifact row's story, told by the surface that owns it.

Run: python3 scripts/test_the_note_only_swears_to_what_it_saw.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []

sys.path.insert(0, str(ROOT / 'scripts'))
from test_artifacts import pure_source  # noqa: E402


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


def main():
    print('the note only swears to what it saw')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    runtime = RUNTIME.read_text(encoding='utf-8')
    fn = brace_lift(runtime, 'function unfiledPath(')

    # ── the wording itself, pinned at the source ────────────────────────
    check('the note claims only the speaker\'s own log',
          'never wrote it' in fn and 'never wrote them' in fn,
          'hq-runtime.jsx unfiledPath: the witness is the visit log; the '
          'sentence must be about the writer, not the cabinet')
    check('the blanket clause is gone',
          'nothing was written' not in fn,
          '"nothing was written to the cabinet on this run" was falsified '
          'by the office\'s own fileDelivery — measured on the briefing '
          'status card, artifact row two lines below the note')
    check('the absence verdict is gone',
          'not there' not in fn,
          '"so that file is not there" asserts cabinet state the guard '
          'never reads — an earlier run may have filed exactly that path')
    check('the note still offers the way forward (§7)',
          'ask them to file' in fn,
          'knowing the promise was not kept is only half an answer')

    # ── behavior through the real lifted composition ────────────────────
    js = pure_source() + '\n' + fn + '\n'
    CASES = {
        # The measured card: prose promise, empty visit log.
        'measured': ('Saved the briefing to Drafts/briefing.md for you.', []),
        # #82 kept: a path this run opened is a file that is there.
        'opened':   ('Summarised Research/vendors.md as asked.',
                     [{'name': 'VAULT_READ', 'arg': 'Research/vendors.md'}]),
        # #50 kept: the speaker filing ANYTHING silences the guard — which
        # is why "the run wrote other files" can never falsify this note.
        'filed':    ('Saved to Drafts/briefing.md.',
                     [{'name': 'VAULT_NEW', 'arg': 'Notes/log.md'}]),
        # Verb agreement in the plural — a note that reads as machine
        # output gets ignored like machine output.
        'two':      ('Filed to Research/a.md and also Reports/b.md.', []),
        # Unknowable stays silent.
        'no_log':   ('Saved to Drafts/briefing.md.', None),
    }
    js += 'const R = {};\n' + '\n'.join(
        'R[%s] = unfiledPath(%s, %s);' % (json.dumps(k), json.dumps(t), json.dumps(v))
        for k, (t, v) in CASES.items()) + '\nconsole.log(JSON.stringify(R));'
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted composition runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('the measured promise still draws the note',
          r['measured'] is not None
          and '`Drafts/briefing.md` is named above' in r['measured'],
          f"{r['measured']!r} — narrowing the wording must not lose the "
          'caveat; the promise was genuinely not kept')
    check('...which swears to the writer, not the cabinet',
          r['measured'] is not None
          and 'they never wrote it to the cabinet on this run' in r['measured']
          and 'nothing was written' not in r['measured']
          and 'not there' not in r['measured'],
          f"{r['measured']!r}")
    check('...and points at the person who can fix it',
          r['measured'] is not None
          and 'ask them to file it if you need it' in r['measured'],
          f"{r['measured']!r}")
    check('a file this run opened draws nothing (#82 kept)',
          r['opened'] is None, f"{r['opened']!r}")
    check('a speaker who filed anything is not accused (#50 kept)',
          r['filed'] is None, f"{r['filed']!r}")
    check('two promises agree with their verbs',
          r['two'] is not None
          and 'are named above, but they never wrote them' in r['two']
          and 'file those if you need them' in r['two'],
          f"{r['two']!r}")
    check('an uncounted visit log accuses nobody',
          r['no_log'] is None, f"{r['no_log']!r}")

    # ── the sheet's cousin is out of scope, and must stay self-correcting ─
    art = (ROOT / 'app' / 'artifacts.jsx').read_text(encoding='utf-8')
    check('the delivery sheet still corrects its own blanket clause',
          'this sheet is the only file it produced' in art,
          'app/artifacts.jsx buildDelivery: the sheet may say "nothing was '
          'written" only because its next clause names the sheet itself — '
          'if that clause ever goes, the sheet inherits this ticket')

    print()
    if FAILS:
        print(f'note-witness: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('note-witness: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
