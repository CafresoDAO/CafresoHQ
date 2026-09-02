#!/usr/bin/env python3
"""The Command Palette's fuzzy-search ranking had a dead branch: a query
matching the START of a word inside a command's label never got its
intended relevance boost over a query that's merely a substring
somewhere in the label.

`CommandPaletteProvider`'s `filtered` memo (ui/feedback.jsx) scored each
candidate with an if/else-if chain, in this order:

    if (lbl.startsWith(q)) score = 100;
    else if (lbl.includes(q)) score = 60;
    else if (sect.includes(q)) score = 30;
    else if (lbl.split(/\\s+/).some(w => w.startsWith(q))) score = 80;

The intent (per the function's own comment, "prefix > substring >
none") is that a query matching the start of a *word* inside the label
(e.g. typing "team" for a command labeled "Change Team Roster") should
score 80 — above a query that only matches mid-word, anywhere in the
label (score 60). But any label where a word starts with `q` also,
necessarily, contains `q` as a substring — so `lbl.includes(q)` is a
strict superset of the word-start condition. Being earlier in the
if/else-if chain, the substring branch always fired first, and the
final `else if` for score 80 was unreachable for every non-empty query.
Effect: a command whose label matches at a word boundary was scored
identically to (and could sort below, or tie arbitrarily with) a
command matching only mid-word, inside a longer unrelated word.

Found by a background hunt agent sweeping previously-unswept areas,
looking specifically for `|| fallback`-style truthy/branch-ordering
bugs similar in spirit to the window-drag-to-edge-zero fix.

Fix: reordered the chain so the word-start check runs BEFORE the plain
substring check, making it reachable and correctly ranked between the
full-label-prefix match (100) and a bare substring match (60).

This test genuinely executes the CURRENT scoring logic (extracted
verbatim from the source, not hand-copied) via Node, so a regression
in the ordering — or a future edit that reintroduces an unreachable
branch — fails here rather than only in a source-pattern check.

Run: python3 scripts/test_command_palette_word_start_outranks_substring.py
(skips the live-execution checks if `node` isn't on PATH — the
extraction/shape checks still run everywhere)
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK = ROOT / 'ui' / 'feedback.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("Command Palette: a word-start match outranks a plain mid-word substring match")

    src = FEEDBACK.read_text(encoding='utf-8')

    m = re.search(
        r"let score = 0;\n"
        r"(?:\s*//[^\n]*\n)*"                       # optional leading comment lines
        r"(\s*if \(lbl\.startsWith\(q\)\) score = 100;\n"
        r"\s*else if .*?score = 30;)",
        src, re.S)
    check('found the score if/else-if chain in the filtered memo', m is not None)
    chain = m.group(1) if m else ''

    check('the word-start branch (score 80) appears BEFORE the plain '
          'substring branch (score 60) — the ordering that actually '
          'makes it reachable, since any word-start match is also a '
          'substring match',
          bool(re.search(r'score = 80.*?score = 60', chain, re.S)))

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'scoring logic below)', has_node,
          'skipping live-execution checks on this platform')

    if has_node and chain:
        js = f"""
        function scoreOf(lbl, sect, q) {{
          lbl = lbl.toLowerCase(); sect = sect.toLowerCase(); q = q.toLowerCase();
          let score = 0;
          {chain}
          return score;
        }}
        const cases = [
          ['Change Team Roster', '', 'team', 80],   // word-start, not label-prefix
          ['Steam Settings',     '', 'team', 60],    // "steam" contains "team" mid-word only
          ['Team Roster',        '', 'team', 100],   // label itself starts with "team"
          ['Foo Bar',       'Team', 'team', 30],     // no label match, section matches
        ];
        let out = [];
        for (const [lbl, sect, q, expected] of cases) {{
          const got = scoreOf(lbl, sect, q);
          out.push(JSON.stringify({{lbl, q, expected, got, ok: got === expected}}));
        }}
        console.log(out.join('\\n'));
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted scoring logic ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        for line in r.stdout.strip().splitlines():
            try:
                import json
                d = json.loads(line)
            except Exception:
                check('parsed a result line from Node', False, line)
                continue
            check(f"scoreOf({d['lbl']!r}, {d['q']!r}) == {d['expected']} "
                  f"(the case that used to fail: a word-start match must "
                  f"score ABOVE a plain substring match, not tie with it)",
                  d['ok'], f"got {d['got']}")

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
