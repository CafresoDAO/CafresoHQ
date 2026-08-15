#!/usr/bin/env python3
"""A marker with prose in front of it reached the boss verbatim.

Two doors strip protocol markers out of a reply, and each had half of one
rule. `ORPHAN_TAG_RE` reasoned that prose BEFORE the marker means a coworker
is explaining it, so it anchored to line start. `stripBlocks` reasoned that a
marker which ENDS the line was meant as an instruction, so its passes require
the marker to be preceded by nothing, a bullet, or a label ending in a colon.

Read together the two halves agree: machine syntax unless there is prose on
both sides of it. Read apart, plain prose then a marker then end of line
satisfies neither anchor and walks past both.

Measured live 2026-08-15 against a canned brain, one task, and this is the
sheet the office filed into the boss's cabinet:

    # Which vendor
    *Delivered by Kip · 2026-08-15*
    ---
    I checked the vendor list [VAULT_READ: Research/vendors.md]
    B wins on cost, so B is the one to go with.
    ---
    **Working**
    - Opened Research/vendors.md in the cabinet
    - `Research/vendors.md` is named above, but nothing was written to the
      cabinet on this run — this sheet is the only file it produced.

Three claims about one act. The tool RAN — TOOL_REGISTRY's `re` is
unanchored, so a marker behind prose executes exactly like one at line start
— and the Working footer reports it in English on the line above. Then the
leaked path fed this sheet's `unfiledPath` line, which reads the CLEANED
body, so the office warned the boss that a file it had merely READ was never
written. Only the sheet's copy of that warning is fixed here: the same
sentence in the chat bubble and the stored result comes from `honestyNotes`,
which reads the RAW buffer, and is filed as its own ticket.

Run: python3 scripts/test_a_marker_behind_prose.py
"""
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def hygiene():
    """Reuse test_reply_hygiene's lift, so this measures the same functions
    the older suite does and cannot drift into testing a copy of them."""
    spec = importlib.util.spec_from_file_location(
        'rh', str(ROOT / 'scripts' / 'test_reply_hygiene.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# [label, reply, what the boss must see]
#
# Everything with a marker at end of line is machine syntax and goes. Every
# case where the marker has a sentence after it is a coworker explaining, and
# survives byte for byte — a guard that eats those is a worse defect than the
# leak it replaces.
CASES = [
    # ── the measured defect, and its neighbours across both vocabularies ──
    ('the vendor reply, verbatim',
     'I checked the vendor list [VAULT_READ: Research/vendors.md]\n'
     'B wins on cost, so B is the one to go with.',
     'I checked the vendor list\nB wins on cost, so B is the one to go with.'),
    ('a write marker behind prose',
     'Filed it [VAULT_NEW: Research/x.md]', 'Filed it'),
    ('a read marker behind prose',
     'Opened it [FILE_READ: notes.md]', 'Opened it'),
    ('a status marker behind prose',
     'All finished. [TASK_DONE]', 'All finished.'),
    ('a search behind prose',
     'Looked it up [SEARCH: primary colours]', 'Looked it up'),
    ('a shell call behind prose',
     'Ran the build [BASH: npm run build]', 'Ran the build'),
    ('a listing behind prose',
     'Had a look around [DIR_LIST: /ws]', 'Had a look around'),
    ('a memory read behind prose',
     'Checked my notes [MEMORY_READ: facts/x.md]', 'Checked my notes'),
    # HANDOFF_TO and HIRE_ASSISTANT were in stripBlocks' vocabulary and
    # missing from the orphan one — the drift a second copy of a thirty-name
    # list produces, and the reason the two anchorings now share one string.
    ('a handoff behind prose',
     'I passed it to Mika [HANDOFF_TO: Mika]', 'I passed it to Mika'),
    ('an assistant hire behind prose',
     'Bringing someone in [HIRE_ASSISTANT: researcher]', 'Bringing someone in'),
    # ACK is the one executable marker deliberately absent from the orphan
    # vocabulary — `stripAcks` owns it, because the inbox needs the status out
    # of it before it goes. Measured here rather than assumed: the exemption
    # in the coverage check below is only honest if this passes.
    ('an ack behind prose',
     'Starting now [ACK: in_progress: reading the brief]', 'Starting now'),

    # ── the counter-cases: a sentence after the bracket is prose ──────────
    ('a coworker explaining the marker',
     'Use [DM_TO: Mika] to reach someone.',
     'Use [DM_TO: Mika] to reach someone.'),
    ('...on the read side too',
     'I checked the list [VAULT_READ: Research/vendors.md] and it is current.',
     'I checked the list [VAULT_READ: Research/vendors.md] and it is current.'),

    # ── what already worked and must keep working ─────────────────────────
    ('a marker alone on its line',
     '[VAULT_READ: Research/vendors.md]\nIt is current.', 'It is current.'),
    ('...with the registry doc string echoed back',
     '[VAULT_READ: Research/vendors.md] — checked\nIt is current.',
     'It is current.'),
    ('...behind a label the model invented',
     '**Vault Path:** [VAULT_NEW: Research/x.md]\n\nThe answer.', 'The answer.'),
    ('...behind a bullet',
     '- [MEMORY_WRITE: the boss bakes sourdough]\n\nThe answer.', 'The answer.'),
    ('...after a colon of any length',
     'I saved your notes and the path is here: [VAULT_NEW: Notes/a.md]',
     'I saved your notes and the path is here:'),

    # ── not a marker at all ───────────────────────────────────────────────
    ('a markdown link is left alone',
     'See [the vendor list](vendors.md)', 'See [the vendor list](vendors.md)'),
    ('a plain answer is untouched',
     'Red, yellow and blue.', 'Red, yellow and blue.'),
]


def main():
    print('a marker behind prose')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    m = hygiene()
    js = 'const R={};\n'
    for label, text, _want in CASES:
        js += 'R[%s] = visibleReply(%s, "Nova");\n' % (
            json.dumps(label), json.dumps(text))
    js += 'console.log(JSON.stringify(R));'
    out = m.run_js(js)
    for label, text, want in CASES:
        got = out[label]
        check(label, got == want, 'got %r, wanted %r (from %r)' % (got, want, text))

    # ── the two anchorings must keep sharing one vocabulary ──────────────
    #
    # The defect this suite exists for was two half-rules in two places. The
    # cases above would all still pass if someone re-inlined a second name
    # list and the two copies started to diverge — every case here names a
    # marker that happens to be in both today. So pin the structure: one
    # string, read twice.
    check('the vocabulary is written once',
          len(re.findall(r'const ORPHAN_TAG_NAMES\s*=', SRC)) == 1
          and len(re.findall(r'const ORPHAN_TAG_CORE\s*=', SRC)) == 1,
          'a thirty-name list copied twice is a list that drifts')
    orphan = re.search(r'const ORPHAN_TAG_RE\s*=[\s\S]*?;$', SRC, re.M)
    check('...and both anchorings read it',
          orphan and orphan.group(0).count('ORPHAN_TAG_CORE') == 2,
          orphan and orphan.group(0))

    # Every marker the office can EXECUTE must be strippable behind prose.
    # TOOL_REGISTRY is the authority on what executes; reading it here means a
    # tool added later fails this rather than quietly joining the leak.
    names = set(re.findall(r"^\s*name: '([A-Z_]+)',", SRC, re.M))
    vocab = re.search(r"const ORPHAN_TAG_NAMES\s*=([\s\S]*?);", SRC)
    listed = set(re.findall(r'[A-Z][A-Z_]+', vocab.group(1) if vocab else ''))
    listed |= {'NEEDS_APPROVAL'}   # spelled NEEDS[_ ]APPROVAL in the pattern
    # ACK belongs to stripAcks, which has to read the status out of it before
    # removing it — a second stripper would race the first. Exempt only
    # because 'an ack behind prose' above proves it is actually stripped; an
    # exemption with no measurement behind it is how a vocabulary goes stale.
    listed |= {'ACK'}
    missing = sorted(names - listed)
    check('every executable tool marker is in the vocabulary',
          not missing,
          'TOOL_REGISTRY runs these and the stripper does not know them: '
          + ', '.join(missing))

    # The unclosed-behind-prose shape is NOT covered, on purpose: with no `]`
    # there is nothing to say where the marker stops, and consuming to end of
    # line eats the sentence. Pinned so the omission stays a decision.
    js2 = ('console.log(JSON.stringify({r: visibleReply('
           + json.dumps('I mentioned [VAULT_NEW: to her') + ', "Nova")}));')
    check('an unclosed marker behind prose is deliberately left alone',
          m.run_js(js2)['r'] == 'I mentioned [VAULT_NEW: to her',
          'the bound `broken` draws, and this pass respects it')

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
