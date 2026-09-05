#!/usr/bin/env python3
"""An empty folder said nothing and a 300-entry cut-off said nothing either.

serve.py's DIR_LIST does not only emit entries. It emits two facts about the
listing itself, in its own words:

    result = '\\n'.join(lines) or '(empty directory)'
    if len(lines) == 300:
        result += '\\n…(truncated at 300 entries)'

The Workspace file tree threw both away on one line — "if (line.startsWith('(')
|| line.startsWith('…')) continue;" — and drew whatever survived.

So a brand-new project's FILES pane was a blank box. Nothing said the folder
was empty, which meant nothing distinguished "there is nothing here" from a
listing that quietly produced no rows; the boss had to guess which.

The truncation was worse, because it was not blank, it was WRONG. A folder
with more than 300 children rendered its first 300 with nothing at the
bottom — no marker, no count, no seam. The boss scrolled to the last row and
believed they had seen the folder. A partial answer wearing the shape of a
complete one is a confident falsehood, not a gap.

This lifts the real parseDirEntries out of views/ide.jsx and runs it under
node against a real empty listing, a real truncated listing and an ordinary
one, then checks that BOTH render paths — the root pane and an expanded
subfolder — go through the same notes.

Run: python3 scripts/test_an_empty_folder_says_so_and_a_truncated_listing_admits_it_is_partial.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDE = (ROOT / 'views' / 'ide.jsx').read_text(encoding='utf-8')
SERVE = (ROOT / 'serve.py').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Drop /* */ and // comments so our own prose can't satisfy a check."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'(?m)^\s*//.*$', '', src)


def lift(src, start, end):
    i = src.find(start)
    if i < 0:
        return None
    j = src.find(end, i)
    if j < 0:
        return None
    return src[i:j + len(end)]


# The listings below are byte-for-byte what serve.py's DIR_LIST builds.
EMPTY = '(empty directory)'
ORDINARY = 'sub/\nnotes.md  (12 B)'
TRUNCATED = '\n'.join(['f%03d.md  (1 B)' % i for i in range(300)]) \
            + '\n…(truncated at 300 entries)'

PROBE = r'''
const LISTINGS = JSON.parse(process.argv[2]);
const out = {};
for (const [name, text] of Object.entries(LISTINGS)) {
  const rows = parseDirEntries(text, '/w/proj');
  out[name] = {
    isArray: Array.isArray(rows),
    names: rows.map(r => r.name),
    empty: rows.empty === true,
    truncated: rows.truncated === true,
  };
}
console.log(JSON.stringify(out));
'''


def run(parse, listings):
    js = parse + '\n' + PROBE
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / 'probe.cjs').write_text(js, encoding='utf-8')
        p = subprocess.run([shutil.which('node') or 'node', str(tmp / 'probe.cjs'),
                            json.dumps(listings)],
                           capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None, 'node: ' + (p.stderr.strip()[:400] or 'no output')
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print('an empty folder says so, and a truncated listing admits it is partial')

    # ── the sentinels this test asserts on are the ones the server emits ──
    check('serve.py still emits the empty-directory sentinel',
          "'(empty directory)'" in SERVE)
    check('serve.py still emits the truncation marker at 300 entries',
          '…(truncated at 300 entries)' in SERVE and 'len(lines) == 300' in SERVE)

    if not shutil.which('node'):
        print('  SKIP  node not available — cannot run the real parser')
        return 1 if FAILS else 0

    parse = lift(IDE, 'function parseDirEntries(text, basePath) {', '\n  return out;\n}')
    check('lifted the real parseDirEntries from views/ide.jsx', parse is not None)
    if parse is None:
        print('\n%d check(s) failed' % len(FAILS))
        return 1

    got, err = run(parse, {'empty': EMPTY, 'ordinary': ORDINARY,
                           'truncated': TRUNCATED})
    check('the parser ran under node', got is not None, err)
    if got is None:
        print('\n%d check(s) failed' % len(FAILS))
        return 1

    # ── an empty folder ───────────────────────────────────────────────────
    e = got['empty']
    check('an empty listing produces no fabricated rows', e['names'] == [], e['names'])
    check('an empty listing is REPORTED as empty, not merely rowless',
          e['empty'] is True,
          'the (empty directory) sentinel was dropped, so a blank pane is all '
          'the boss gets and nothing distinguishes it from a listing that failed')
    check('an empty listing is not mistaken for a truncated one',
          e['truncated'] is False)

    # ── a truncated folder: the serious one ───────────────────────────────
    t = got['truncated']
    check('a truncated listing still yields its 300 rows', len(t['names']) == 300,
          len(t['names']))
    check('the truncation marker is not drawn as a file row',
          not any('truncated' in n for n in t['names']))
    check('a truncated listing ADMITS it is partial',
          t['truncated'] is True,
          'the …(truncated at 300 entries) marker was dropped, so 300 of N '
          'entries were presented as the whole folder — the boss scrolls to '
          'the bottom and believes they have seen everything')
    check('a truncated listing is not also reported as empty', t['empty'] is False)

    # ── the ordinary case is unchanged ────────────────────────────────────
    o = got['ordinary']
    check('an ordinary listing still parses into rows',
          o['names'] == ['sub', 'notes.md'], o['names'])
    check('an ordinary listing claims neither empty nor truncated',
          o['empty'] is False and o['truncated'] is False)
    check('the parser still returns a real Array on every path',
          all(got[k]['isArray'] for k in got),
          'the sub-listing cache tells a listing from a failure with '
          'Array.isArray — the flags must ride ON the array')

    # ── both render paths must actually SAY it ────────────────────────────
    src = strip_comments(IDE)
    check('the sentinels are matched exactly, not by a leading-character guess',
          "line.startsWith('(')" not in src and "line.startsWith('…')" not in src,
          'a prefix test both discards the facts and can eat a real filename')
    notes = re.search(r'const listNotes = \(list, depth\) => \{[\s\S]{0,900}?\n  \};', src)
    check('the tree has one place that renders what a listing says about itself',
          notes is not None)
    if notes:
        body = notes.group(0)
        check('...it says an empty folder is empty',
              re.search(r'list\.length === 0', body) is not None
              and 'empty' in body.lower(), body[:120])
        check('...and it says a truncated listing is incomplete',
              'list.truncated' in body and re.search(r'more|first', body) is not None,
              body[:120])
    check('every listing renders through the notes — root pane and subfolder alike',
          re.search(r'const renderEntries = \(list, depth\) =>[\s\S]{0,200}listNotes\(list, depth\)',
                    src) is not None,
          'if only the root pane got the notes, an expanded subfolder would '
          'still lie about being empty or complete')
    check('the subfolder branch still routes its children through renderEntries',
          re.search(r'Array\.isArray\(kids\) && renderEntries\(kids, depth \+ 1\)', src)
          is not None)
    check('the root pane still routes its entries through renderEntries',
          'renderEntries(entries, 0)' in src)
    check('#303\'s failed-subfolder sentence is untouched',
          re.search(r'kids\s*&&\s*!Array\.isArray\(kids\)[\s\S]{0,400}kids\.error', src)
          is not None)

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
