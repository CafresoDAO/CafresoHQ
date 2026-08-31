#!/usr/bin/env python3
"""A search hit was a bare title and a fake percentage.

Both search arms (serve.py's accent-folded scorer and the bridge's)
have always sent a match-centered snippet — and the UI dropped it on
the floor, leaving the boss a filename and "300.0": the score is a
plain MATCH COUNT that the old row multiplied by 100 and dressed as
a percent. You could not tell why a result matched, or which of two
same-named notes was the one you wanted.

Now one shared hitRow serves both layouts: title, an honest ×N badge,
and the snippet with every case-insensitive occurrence of the query
lit up. The highlight splits on hitQ — the query the hits were MADE
with — so typing after a search doesn't strip highlights out from
under still-shown results. Accent-folded matches (which the server
finds and the client splitter can't) come back as a plain snippet:
shown, just not lit. Verified live: "remote startups" returned the
brief with ×3 and the phrase marked inside its snippet.

Run: python3 scripts/test_a_search_hit_shows_why_it_matched.py
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


HARNESS = r'''
%s
const out = {
  basic: _snippetParts('Why Remote Startups lose people to remote work', 'remote startups'),
  multi: _snippetParts('ab ab', 'ab'),
  noq: _snippetParts('plain text', ''),
  empty: _snippetParts('', 'x'),
  miss: _snippetParts('cafe note', 'café'),
};
console.log(JSON.stringify(out));
'''


def main():
    print('a search hit shows why it matched')
    vault = (ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')

    fn = brace_lift(vault, 'const _snippetParts = (snippet, q) => {')
    p = subprocess.run(['node', '-e', HARNESS % fn], capture_output=True,
                       text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    out = json.loads(p.stdout.strip().split('\n')[-1])

    b = out['basic']
    check('a hit is found case-insensitively, original casing kept',
          any(s['hit'] and s['t'] == 'Remote Startups' for s in b), b)
    check('the parts reassemble the snippet exactly',
          ''.join(s['t'] for s in b) == 'Why Remote Startups lose people to remote work')
    check('every occurrence is lit, not just the first',
          sum(1 for s in out['multi'] if s['hit']) == 2, out['multi'])
    check('no query means one plain segment',
          out['noq'] == [{'t': 'plain text', 'hit': False}], out['noq'])
    check('no snippet means no segments, not a crash', out['empty'] == [])
    check("an accent-folded match the splitter can't see stays plain",
          out['miss'] == [{'t': 'cafe note', 'hit': False}], out['miss'])

    # ── wiring: one row, both layouts, honest score, snapshot query ──
    check('both layouts render the one shared hit row',
          'hits.map(h => hitRow(h, openByPath))' in vault
          and 'hits.map(h => hitRow(h, mobileOpenByPath))' in vault)
    check('the score is an honest match count, not a fake percent',
          '×{h.score}' in vault and '(h.score*100)' not in vault)
    check('highlights split on the query the hits were made with',
          '_snippetParts(h.snippet, hitQ)' in vault
          and 'setHitQ(q.trim())' in vault)
    check('the snippet itself renders in the row',
          '{h.snippet ? (' in vault)
    check('the server still centers the snippet on the match',
          'o_start - 60' in serve and "'snippet': snippet" in serve)

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
