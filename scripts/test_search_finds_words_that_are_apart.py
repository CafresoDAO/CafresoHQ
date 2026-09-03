#!/usr/bin/env python3
"""A two-word search found nothing in the note it was obviously about.

Live-reproduced against a fresh vault (port 8913, one note): a file
`meeting.md` reading

    # Q3 Planning

    We had a great meeting yesterday about Q3 planning. Everyone attended.

searching "meeting" alone finds it (score 4). Searching "planning" alone
finds it (score 2). Searching "meeting planning" — the two-word query a
boss would actually type — found NOTHING:

    curl 'http://127.0.0.1:8913/vault/search?q=meeting+planning'
    {"hits": [], "total": 0}

`_vault_search_hit` (serve.py, shared by the fs and oci backends) and
`bridgeSearch` (views/vault.jsx, the encrypted-shell arm) both scored the
ENTIRE query as one literal phrase: `ftext.count(fq)` only counts exact,
adjacent occurrences of "meeting planning", and the two words are never
adjacent in the note (it says "...meeting yesterday about Q3 planning...").
Two single-word searches each worked; the two words together, the search
a naive user actually runs, worked for neither backend.

Fix: split the query on whitespace into words and require every word
somewhere — title or body, any order, not necessarily adjacent — the
ordinary implicit-AND a plain-language multi-word search box implies.
A single-word query is a list of one word, so score/snippet are
unchanged for that (by far the most common) case. The snippet anchors on
whichever word's first occurrence is EARLIEST IN THE NOTE, not whichever
word came first in the query, so "meeting planning" and "planning
meeting" come back as the exact same hit — same score, same snippet —
instead of two results that agree on score but disagree about which
sentence to show. `_snippetParts` (the
client-side highlighter) gets the matching update: it used to highlight
only the literal, space-and-all phrase, which would light up NOTHING for
a multi-word AND hit whose words are scattered in the snippet; it now
also highlights each individual word, while STILL preferring the whole
phrase as one continuous span when the two words do happen to sit next
to each other (the longest-match tie-break), so the existing adjacent-
phrase-highlight behavior is unchanged.

This test lifts `_vault_search_hit`/`_fold_accents` out of serve.py by
name (ast, not a line range) and runs them for real under Python, lifts
`bridgeSearch`/`_foldAccents` out of views/vault.jsx by brace-balanced
statement scan and runs them for real under Node with a stub `_bridge`,
and lifts `_snippetParts` the same way.

Run: python3 scripts/test_search_finds_words_that_are_apart.py
(the bridgeSearch/​_snippetParts checks skip if `node` isn't on PATH —
the serve.py checks always run)
"""
import ast
import json
import pathlib
import shutil
import subprocess
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVE = ROOT / 'serve.py'
VAULT_JSX = ROOT / 'views' / 'vault.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift_py(src, name):
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise SystemExit(f'{name} not found')


def brace_lift(src, opener):
    i = src.index(opener)
    j = src.index('{', i)
    depth = 0
    k = j
    while True:
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                break
        k += 1
    return src[i:k + 1]


def main():
    print('search finds words that are apart')
    serve_src = SERVE.read_text(encoding='utf-8')
    vault_src = VAULT_JSX.read_text(encoding='utf-8')

    # ── serve.py: _vault_search_hit, real code, real Python ─────────────
    ns = {'pathlib': pathlib, 'unicodedata': unicodedata}
    exec(lift_py(serve_src, '_fold_accents'), ns)
    exec(lift_py(serve_src, '_vault_search_hit'), ns)
    hit = ns['_vault_search_hit']

    NOTE = ('# Q3 Planning\n\n'
            'We had a great meeting yesterday about Q3 planning. Everyone attended.\n')

    r_meeting = hit('meeting.md', NOTE, 'meeting', 'meeting')
    r_planning = hit('meeting.md', NOTE, 'planning', 'planning')
    r_both = hit('meeting.md', NOTE, 'meeting planning', 'meeting planning')
    r_reversed = hit('meeting.md', NOTE, 'planning meeting', 'planning meeting')

    check('single word "meeting" finds the note (sanity — this half never broke)',
          bool(r_meeting) and r_meeting['score'] == 4, r_meeting)
    check('single word "planning" finds the note (sanity — this half never broke)',
          bool(r_planning) and r_planning['score'] == 2, r_planning)
    check('THE BUG: "meeting planning" together finds the note '
          '(measured live before the fix: {"hits": [], "total": 0})',
          bool(r_both), r_both)
    check('the combined score is the sum of each word\'s own score '
          '(4 + 2 = 6) — an AND of two independent word matches, not a '
          'phrase match',
          bool(r_both) and r_both['score'] == 6, r_both)
    check('word order does not matter — "planning meeting" is the identical '
          'hit (same score AND same snippet: the snippet anchors on '
          'whichever word occurs earliest in the NOTE, not in the query, '
          'so the two orderings cannot disagree about which sentence to show)',
          bool(r_reversed) and r_reversed == r_both, (r_reversed, r_both))
    check('the snippet is still centered on real note text (not empty, '
          'not a foldedcopy)',
          bool(r_both) and 'meeting' in r_both['snippet'].lower(), r_both)

    r_and_fail = hit('meeting.md', NOTE, 'meeting zanahoria', 'meeting zanahoria')
    check('AND, not OR: a query with one real word and one absent word '
          'is still a miss — search does not go loose the other direction',
          r_and_fail is None, r_and_fail)

    r_messy_ws = hit('meeting.md', NOTE, '  meeting   planning  ',
                      '  meeting   planning  ')
    check('extra/irregular whitespace between words is still just two words',
          bool(r_messy_ws) and r_messy_ws['score'] == 6, r_messy_ws)

    # Title-only multi-word match (mirrors the existing "search finds what
    # it cannot read" name-only path for decks/PDFs — a query naming two
    # parts of a filename should still AND-match on the title alone).
    r_title_only = hit('Research/q3-deck.pptx', '', 'q3 deck', 'q3 deck')
    check('two words that both live in the TITLE (a name-only artifact, '
          'empty body) still AND-match',
          bool(r_title_only) and r_title_only['score'] == 6, r_title_only)
    r_title_miss = hit('Research/q3-deck.pptx', '', 'q3 vendor', 'q3 vendor')
    check('...but not if only one of the two words is in that title',
          r_title_miss is None, r_title_miss)

    # Single-word behavior must be byte-for-byte the same shape as before
    # (this is what makes the fix backward compatible for the overwhelming
    # common case — see test_search_speaks_both_keyboards.py for the
    # accent-folding checks this must keep passing unmodified).
    check('a single-word query is still exactly "a list of one word" — '
          'same score as calling the old single-phrase scorer would have',
          hit('meeting.md', NOTE, 'zanahoria', 'zanahoria') is None)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed for the bridgeSearch/_snippetParts '
          'live-execution checks below)', has_node, 'skipping those checks')
    if not has_node:
        print()
        if FAILS:
            print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS))
            return 1
        print('all checks passed')
        return 0

    # ── views/vault.jsx: bridgeSearch, real code, real Node ─────────────
    fold_fn = brace_lift(vault_src, 'const _foldAccents = (s) => {') + ';'
    bridge_fn = brace_lift(vault_src, 'const bridgeSearch = async (query) => {') + ';'

    harness = f"""
    {fold_fn}
    const files = [{{ path: 'meeting.md', id: 'note-1', title: 'meeting', isBinary: false }}];
    const NOTE = {json.dumps(NOTE)};
    const _bridge = {{ read: async (id) => (id === 'note-1' ? NOTE : (() => {{ throw new Error('no such file'); }})()) }};
    {bridge_fn}
    (async () => {{
      const both = await bridgeSearch('meeting planning');
      const reversed = await bridgeSearch('planning meeting');
      const meetingOnly = await bridgeSearch('meeting');
      const andFail = await bridgeSearch('meeting zanahoria');
      console.log(JSON.stringify({{ both, reversed, meetingOnly, andFail }}));
    }})();
    """
    r = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=60)
    check('bridgeSearch (the encrypted-shell arm) ran without a Node error',
          r.returncode == 0, r.stderr.strip()[-800:])
    if r.returncode == 0:
        out = json.loads(r.stdout.strip().splitlines()[-1])
        check('bridgeSearch: THE BUG mirrored client-side — "meeting planning" '
              'used to score nothing there too (bridgeSearch has its own, '
              'independent scoring copy — see test_bridge_vault_search_'
              'folds_accents_like_server.py for why it must mirror serve.py)',
              len(out['both']) == 1 and out['both'][0]['path'] == 'meeting.md',
              out['both'])
        check('bridgeSearch: word order does not matter either — identical '
              'hit, including the snippet',
              out['reversed'] == out['both'], out)
        check('bridgeSearch: single-word search is unaffected (still finds it)',
              len(out['meetingOnly']) == 1, out['meetingOnly'])
        check('bridgeSearch: AND semantics, not OR — one absent word is still a miss',
              out['andFail'] == [], out['andFail'])

    # ── views/vault.jsx: _snippetParts, real code, real Node ────────────
    snippet_fn = brace_lift(vault_src, 'const _snippetParts = (snippet, q) => {') + ';'
    harness2 = f"""
    {snippet_fn}
    const scattered = _snippetParts(
      'We had a great meeting yesterday about Q3 planning.', 'meeting planning');
    const adjacent = _snippetParts(
      'Why Remote Startups lose people to remote work', 'remote startups');
    const preferLongest = _snippetParts('Check the abstract for details', 'a ab');
    console.log(JSON.stringify({{ scattered, adjacent, preferLongest }}));
    """
    r2 = subprocess.run(['node', '-e', harness2], capture_output=True, text=True, timeout=60)
    check('_snippetParts ran without a Node error', r2.returncode == 0,
          r2.stderr.strip()[-800:])
    if r2.returncode == 0:
        out2 = json.loads(r2.stdout.strip().splitlines()[-1])
        scattered = out2['scattered']
        check('_snippetParts now highlights EACH scattered word on its own '
              '(both "meeting" and "planning" lit, even though they never '
              'sit next to each other) — the old version would have lit '
              'up nothing at all for this hit',
              any(p['hit'] and p['t'].lower() == 'meeting' for p in scattered)
              and any(p['hit'] and p['t'].lower() == 'planning' for p in scattered),
              scattered)
        check('...and the parts still reassemble the snippet exactly',
              ''.join(p['t'] for p in scattered)
              == 'We had a great meeting yesterday about Q3 planning.',
              scattered)
        adjacent = out2['adjacent']
        check('UNCHANGED: two query words that DO sit next to each other in '
              'the snippet still highlight as ONE continuous span, not two '
              'separate word-highlights split by a bare gap (regression '
              'guard for test_a_search_hit_shows_why_it_matched.py\'s '
              '"Remote Startups" case)',
              any(p['hit'] and p['t'] == 'Remote Startups' for p in adjacent),
              adjacent)

        # Two of the query's OWN word-needles ('a' and 'ab') can start at the
        # same position (the 'a' that opens "abstract" IS also where 'ab'
        # starts) — the longest-match tie-break must pick 'ab' there, not
        # stop at the shorter 'a' just because it was tried first. (Later,
        # separate 'a' hits elsewhere in "abstract"/"details" are correct —
        # only the very first, TIED position is what this checks.)
        prefer_longest = out2['preferLongest']
        first_hit = next((p for p in prefer_longest if p['hit']), None)
        check('when two word-needles tie on position, the LONGER one wins '
              '("ab" over "a" at the start of "abstract") — a shorter word '
              'that is a prefix of a longer one must not steal the highlight',
              first_hit is not None and first_hit['t'] == 'ab', prefer_longest)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
