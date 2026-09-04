#!/usr/bin/env python3
"""The concept map ate whole sections of notes that use `---` rules.

cooccur.jsx (window.CafresoCooccur, the builder behind the graph view's
"🧠 Concepts" source) strips markdown scaffolding before it counts a
single token. Its first stripper was meant to drop YAML frontmatter:

    .replace(/^---[\\s\\S]*?---/m, ' ')          // YAML frontmatter

The `m` flag is the bug. With `m`, `^` matches at EVERY line start, not
just the start of the text — so in a note that has no frontmatter at
all, the first two `---` HORIZONTAL RULES are read as a frontmatter
block and everything between them is deleted before tokenizing.

Concrete repro (the case this test pins): a note that opens with a
solar plan, rules off into the section that is actually about the
alpaca herd, and rules off again. Every alpaca concept — alpaca, herd,
shearing, fiber, pricing — was silently absent from the concept map,
while the analytics panel went on reporting the note as one of the
"Co-occurrence over N notes" it had read. Nothing failed, nothing was
flagged; the map just quietly did not know about a third of the note.

kg_builder.py already gets this right on the Python side:

    _FRONTMATTER_RE = _re.compile(r'\\A---\\s*\\n(.*?\\n)---\\s*\\n', _re.DOTALL)

`\\A` is start-of-text and both fences must be whole lines. The fix
gives cooccur.jsx the same shape: no `m` flag, and both `---` fences
must be complete lines.

Run: python3 scripts/test_concept_map_keeps_text_between_horizontal_rules.py
(the live-execution checks skip if `node` isn't on PATH — the
source-shape check still runs everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COOCCUR = ROOT / 'cooccur.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


src = COOCCUR.read_text(encoding='utf-8')

# ---- source shape -------------------------------------------------------
# The frontmatter stripper must not be multiline-anchored.
strippers = re.findall(r'\.replace\(/\^---[^\n]*?/([a-z]*),', src)
check('cooccur.jsx has a frontmatter stripper', bool(strippers), strippers)
check('frontmatter stripper is not `m`-anchored (^ = start of text)',
      all('m' not in flags for flags in strippers),
      'flags found: %r' % (strippers,))

# ---- live behaviour -----------------------------------------------------
node = shutil.which('node')
if not node:
    print('  skip  live checks (node not on PATH)')
else:
    NOTE = '\n'.join([
        '# Solar plan',
        '',
        'Inverters and batteries for the finca.',
        '',
        '---',
        '',
        'The alpaca herd needs shearing before the rains.',
        'Alpaca fiber pricing rises.',
        '',
        '---',
        '',
        'Closing notes about inverters.',
        '',
    ])
    FRONTMATTER_NOTE = '\n'.join([
        '---',
        'title: Solar plan',
        'tags: [energy]',
        '---',
        '',
        'Inverters and batteries for the finca.',
        '',
    ])

    driver = r'''
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const w = {};
new Function('window', src)(w);
const C = w.CafresoCooccur;
const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = {};
for (const [name, text] of Object.entries(cases)) {
  out[name] = {
    lemmas: C.tokenize(text).map((t) => t.lemma),
    nodes: C.build([{ id: 'n.md', title: 'n', text }], { minCount: 1 }).nodes.map((n) => n.id),
  };
}
process.stdout.write(JSON.stringify(out));
'''
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / 'drv.js').write_text(driver, encoding='utf-8')
        (td / 'cases.json').write_text(
            json.dumps({'rules': NOTE, 'frontmatter': FRONTMATTER_NOTE}), encoding='utf-8')
        proc = subprocess.run(
            [node, str(td / 'drv.js'), str(COOCCUR), str(td / 'cases.json')],
            capture_output=True, text=True)
    if proc.returncode != 0:
        check('node driver ran', False, proc.stderr.strip()[:400])
    else:
        got = json.loads(proc.stdout)
        rules = got['rules']

        # The section between the two horizontal rules must survive.
        for term in ('alpaca', 'herd', 'shearing', 'fiber', 'pricing'):
            check('concept "%s" (between two --- rules) survives tokenizing' % term,
                  term in rules['lemmas'], rules['lemmas'])
        check('"alpaca" is a node in the built concept map',
              'alpaca' in rules['nodes'], rules['nodes'])

        # Sections on either side of the rules were never at risk; keep them pinned.
        for term in ('inverter', 'battery', 'finca'):
            check('concept "%s" (before the rules) still present' % term,
                  term in rules['lemmas'], rules['lemmas'])

        # Real frontmatter must STILL be stripped — the fix must not
        # trade one silent loss for a stream full of YAML keys.
        fm = got['frontmatter']['lemmas']
        for key in ('title', 'tag', 'tags', 'energy'):
            check('frontmatter key/value "%s" is still stripped' % key,
                  key not in fm, fm)
        check('body after frontmatter still tokenized',
              'inverter' in fm and 'finca' in fm, fm)

print()
if FAILS:
    print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('PASS — the concept map reads the whole note, rules and all')
