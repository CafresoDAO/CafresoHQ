#!/usr/bin/env python3
"""Every finished task must be filed under the title the boss actually typed.

`#279` found this in modals/starter.jsx: the slug's character class was
`[^a-z0-9]`, which is not "unsafe characters" — it is "not the Latin
alphabet". Japanese, Russian, Greek, Hebrew, Arabic and Korean letters were
all replaced with a dash, the trim then ate the dashes, and the empty string
fell through to the constant fallback.

The twin was left open. app/artifacts.jsx `slugify` is the filer the boss
meets FIRST — it names the sheet for every finished task, not just the three
starter cards — and its own header says it is "kept in step with
modals/starter.jsx". It carried the identical class. Measured on the old
code:

    slugify('顧客への提案メール')          ->  'delivery'
    slugify('新製品の価格戦略')            ->  'delivery'
    slugify('Стратегия ценообразования')  ->  'delivery'

`#278` gave `fileDelivery` a step loop, so the second sheet no longer
destroys the first outright — but what an office that does not type in
English actually got was `Deliveries/delivery.md`, `delivery-2.md`,
`delivery-3.md`, … forever: a cabinet in which nothing can be told apart,
and, past the 20th step, a task whose deliverable is filed nowhere at all
and reported as no artifact. missions.jsx
`topicSlug` is the third site of the same constant, and it names the FOLDER a
whole mission writes into — every non-English mission was aimed at
`Research/untitled`, on top of the last one's notes.

Guards, in the order a boss would notice them:
  · distinct titles produce distinct filenames, in every script
  · the title actually SURVIVES into the filename rather than being replaced
    by a constant (a counter bolted onto 'delivery' would pass the first
    check while still throwing the title away)
  · the fallback is still there for a title with no letters or digits, and
    is the only remaining way to collide
  · what the old class was REALLY protecting still holds: no `/`, no `..`,
    no leading dot (serve.py refuses hidden paths, `#140`)
  · the 56-cap holds, counts code points, and leaves no dangling dash
  · the three sites are actually in step with each other
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_the_front_desk_sells_what_exists import brace_lift, strip_comments  # noqa: E402

ARTIFACTS = ROOT / 'app' / 'artifacts.jsx'
MISSIONS = ROOT / 'missions.jsx'
STARTER = ROOT / 'modals' / 'starter.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# Real task titles. Every one of these is a DIFFERENT deliverable, so every
# one of them needs its own sheet in the cabinet.
TITLES = [
    '顧客への提案メール',
    '新製品の価格戦略',
    'Стратегия ценообразования',
    'Τιμολόγηση προϊόντων',
    'استراتيجية التسعير',
    'תמחור מוצרים',
    '개 산책 사업 홈페이지',
    'café pricing für Kunden',
    'Research brief: how small teams price a new product',
]

TOPICS = ['顧客への提案メール', '新製品の価格戦略', 'Стратегия ценообразования']


def main():
    print('a deliverable in japanese is not filed as delivery.md')
    artifacts = ARTIFACTS.read_text(encoding='utf-8')
    missions = MISSIONS.read_text(encoding='utf-8')
    starter = STARTER.read_text(encoding='utf-8')

    slugify = brace_lift(artifacts, 'function slugify(s) {')
    topic_slug = brace_lift(missions, 'function topicSlug(topic) {')

    # ── structural: the sheet path really is built from this function ────
    check('the filed path is still built from slugify',
          'slugify(task' in artifacts and "'.md'" in artifacts or
          '${slug}' in artifacts,
          'if fileDelivery stops using slugify this suite guards nothing')
    check("artifacts' slug is not restricted to the Latin alphabet",
          '[^a-z0-9]' not in strip_comments(slugify),
          'a-z0-9 deletes every other script wholesale, and what is left is '
          "the same constant 'delivery' for all of them")
    check("missions' folder slug is not restricted to the Latin alphabet",
          '[^a-z0-9]' not in strip_comments(topic_slug),
          "every non-English mission aims at Research/untitled")
    check('and neither is the starter card it is kept in step with (#279)',
          '[^a-z0-9]' not in strip_comments(brace_lift(
              starter, 'function filePath(folder, subject, ext) {')),
          'the twin this entry is the sibling of must stay fixed')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        print()
        return 1 if FAILS else 0

    harness = slugify + '\n' + topic_slug + '''
const R = {};
R.slugs  = ''' + json.dumps(TITLES) + '''.map(t => slugify(t));
R.topics = ''' + json.dumps(TOPICS) + '''.map(t => topicSlug(t));
R.empty     = slugify('!!! ??? ---');
R.emoji     = slugify('\\u{1F600}\\u{1F600}');
R.blank     = slugify('   ');
R.traversal = slugify('../../etc/passwd');
R.dotted    = slugify('.hidden thing');
R.ascii     = slugify('First draft: a two-sentence welcome note!');
R.long      = slugify('Save a note to your memory saying the boss likes '
                      + 'bullet points, then confirm');
// One astral code point repeated well past the cap: a UTF-16 slice would cut
// the last pair in half and leave a lone surrogate in the filename.
R.astral     = slugify('\\u{20BB7}'.repeat(80));
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

    slugs = out['slugs']
    dupes = sorted({s for s in slugs if slugs.count(s) > 1})
    check('nine different task titles produce nine different sheets',
          not dupes,
          f'{dupes} — every one of these is a separate deliverable, and the '
          'cabinet cannot tell them apart')

    for title, got in zip(TITLES, slugs):
        head = ''.join(ch for ch in title.lower() if ch.isalnum())[:6]
        check(f'{title[:14]!r} survives into its own filename',
              head and head[:4] in got.replace('-', ''),
              f'{got} — the title was replaced rather than slugged')

    topics = out['topics']
    check('three missions in other scripts get three folders',
          len(set(topics)) == 3,
          f'{topics} — one folder means the second mission writes its notes '
          "on top of the first mission's")

    # ── the properties the old class got right, still right ──────────────
    check('a title with no letters or digits still gets the fallback',
          out['empty'] == 'delivery', out['empty'])
    check('...and so does one that is only emoji',
          out['emoji'] == 'delivery', out['emoji'])
    check('...and so does an empty one',
          out['blank'] == 'delivery', out['blank'])
    check('a title cannot walk out of the cabinet',
          '/' not in out['traversal'] and '..' not in out['traversal'],
          out['traversal'])
    check('a title cannot file itself where the Library will not list it',
          not out['dotted'].startswith('.'),
          f"{out['dotted']} — serve.py refuses hidden paths outright (#140)")
    check('an ordinary english title is unchanged',
          out['ascii'] == 'first-draft-a-two-sentence-welcome-note',
          out['ascii'])
    check('the 56-cap holds', len(out['long']) <= 56, out['long'])
    check('...and never leaves a dangling dash (#215)',
          not out['long'].endswith('-') and not out['long'].startswith('-'),
          out['long'])
    check('...and never cuts an astral character in half',
          out['astralLone'] is False,
          f"{out['astral']} — a lone surrogate is not a filename")

    # The bundle the browser actually loads must carry the fix too.
    bundle = ROOT / 'dist-ui'
    if bundle.is_dir():
        # The bundler rewrites quotes and whitespace, so match on the shape:
        # the old class anywhere within reach of the 'delivery' fallback.
        stale = [f.name for f in bundle.rglob('*.js')
                 if re.search(r"""\[\^a-z0-9\]\+/g[\s\S]{0,160}?["']delivery["']""",
                              f.read_text(encoding='utf-8', errors='ignore'))]
        check('the built bundle is not still shipping the old class',
              not stale, f'{stale} — run npm run build')

    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed')
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
