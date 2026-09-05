#!/usr/bin/env python3
"""Two starter tasks must never be handed the same filename.

modals/starter.jsx turns the ONE thing a starter card asks for — the subject —
into a vault-relative path, and puts that path inside the brief the coworker
receives: "Save the finished brief to Research/<slug>.md". The coworker writes
it with VAULT_NEW, whose own doc line in hq-runtime.jsx reads "create a new
note (overwrites if exists)".

So the slug is load-bearing: if two different subjects slug to the same
string, the second deliverable silently destroys the first, and the reply
reports the same green path both times.

The slug's character class was `[^a-z0-9]`. That is not "unsafe characters",
it is "not the Latin alphabet" — every letter of every other script was
replaced with a dash, the trim then ate the dashes, and the empty result fell
through to the `|| 'note'` fallback. Measured on the old code:

    filePath('Drafts', '顧客への提案メール', 'md')  ->  Drafts/note.md
    filePath('Drafts', '新製品の価格戦略',   'md')  ->  Drafts/note.md
    filePath('Research', 'Стратегия ценообразования', 'md') -> Research/note.md

A Japanese, Russian, Greek, Hebrew or Arabic office got exactly ONE starter
deliverable per folder that survived; every one after it overwrote its
predecessor, with nothing on screen saying so.

Guards, in order of what a boss would notice:
  · distinct subjects in the same script produce distinct paths
  · the subject actually survives into the filename, rather than being
    replaced by a constant
  · the fallback is still there for a subject with no letters or digits
    at all, and is still the only thing that can produce a collision
  · the old class's REAL job — no `/`, no `.`, no leading dot — is still
    done, so a subject can never walk out of the vault or file itself
    somewhere the Library refuses to list (serve.py's hidden-path check)
  · the length cap counts code points, so an astral character is never
    cut in half into a lone surrogate, and the cap cannot leave a
    trailing dash
  · the brief still names the path it promises
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_the_front_desk_sells_what_exists import brace_lift  # noqa: E402

STARTER = ROOT / 'modals' / 'starter.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# (folder, subject) pairs that a real boss types. Every one of these is a
# DIFFERENT deliverable, so every one of them needs a different file.
SUBJECTS = [
    ('Drafts',   '顧客への提案メール'),
    ('Drafts',   '新製品の価格戦略'),
    ('Research', 'Стратегия ценообразования'),
    ('Research', 'Τιμολόγηση προϊόντων'),
    ('Research', 'استراتيجية التسعير'),
    ('Research', 'תמחור מוצרים'),
    ('Research', 'café pricing für Kunden'),
    ('Research', 'how small teams price a new product'),
    ('Sites',    '개 산책 사업 홈페이지'),
]


def main():
    print('two briefs in japanese are not the same file')
    starter = STARTER.read_text(encoding='utf-8')

    lifted = brace_lift(starter, 'function filePath(folder, subject, ext) {')

    # ── the brief still promises the path this function builds ───────────
    check('the brief hands the coworker the path filePath built',
          "filePath('Research'" in starter and "filePath('Drafts'" in starter
          and "filePath('Sites'" in starter,
          'if the cards stop using filePath this suite is guarding nothing')
    check('the slug is not restricted to the Latin alphabet',
          '[^a-z0-9]' not in lifted,
          'a-z0-9 deletes every other script wholesale, and what is left is '
          'the same constant for all of them')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        print()
        return 1 if FAILS else 0

    harness = lifted + '''
const R = {};
const cases = ''' + json.dumps(SUBJECTS) + ''';
R.paths = cases.map(([f, s]) => filePath(f, s, 'md'));
R.empty = filePath('Research', '!!! ??? ---', 'md');
R.emoji = filePath('Research', '\\u{1F600}\\u{1F600}', 'md');
R.traversal = filePath('Research', '../../etc/passwd', 'md');
R.dotted = filePath('Research', '.hidden thing', 'md');
R.long = filePath('Research', 'how small teams price a brand new product '
                  + 'line for the second half of the year', 'md');
// One astral code point repeated past the cap: a UTF-16 slice would cut the
// last pair in half and leave a lone surrogate in the filename.
R.astral = filePath('Research', '\\u{20BB7}'.repeat(60), 'md');
R.astralLone = /[\\uD800-\\uDBFF](?![\\uDC00-\\uDFFF])|(?:^|[^\\uD800-\\uDBFF])[\\uDC00-\\uDFFF]/
  .test(R.astral);
console.log(JSON.stringify(R));
'''
    p = subprocess.run(['node', '--input-type=module', '-e', harness],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr[-1500:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    out = json.loads(p.stdout.strip().split('\n')[-1])

    paths = out['paths']
    dupes = sorted({p_ for p_ in paths if paths.count(p_) > 1})
    check('nine different subjects produce nine different files',
          not dupes,
          f'{dupes} — VAULT_NEW overwrites, so the second task to land on a '
          'shared path deletes the first deliverable with a green reply')

    # The generalising half: "different" is not enough — a counter bolted on
    # the end would satisfy the check above while still throwing the subject
    # away. The filename has to CARRY the thing the boss typed.
    for (folder, subject), got in zip(SUBJECTS, paths):
        head = ''.join(ch for ch in subject.lower() if ch.isalnum())[:6]
        check(f'{subject[:14]!r} survives into its own filename',
              head and head[:4] in got.replace('-', ''),
              f'{got} — the subject was replaced rather than slugged')

    check('a subject with no letters or digits still gets the fallback',
          out['empty'] == 'Research/note.md', out['empty'])
    check('...and so does one that is only emoji',
          out['emoji'] == 'Research/note.md', out['emoji'])

    # What the old class was ACTUALLY protecting, still protected.
    check('a subject cannot walk out of the vault',
          '/' not in out['traversal'][len('Research/'):]
          and '..' not in out['traversal'],
          out['traversal'])
    check('a subject cannot file itself where the Library will not list it',
          not out['dotted'][len('Research/'):].startswith('.'),
          f"{out['dotted']} — serve.py refuses hidden paths outright (#140)")

    slug_long = out['long'][len('Research/'):-len('.md')]
    check('the cap holds', len(slug_long) <= 48, out['long'])
    check('...and never leaves a dangling dash',
          not slug_long.endswith('-') and not slug_long.startswith('-'),
          out['long'])
    check('...and never cuts an astral character in half',
          out['astralLone'] is False,
          f"{out['astral']} — a lone surrogate is not a filename")

    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed')
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
