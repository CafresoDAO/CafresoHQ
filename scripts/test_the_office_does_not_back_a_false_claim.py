#!/usr/bin/env python3
"""A coworker claimed a file she was never allowed to write, and the office
agreed with her.

Reproduced 2026-08-15 on a canned brain (port 9236). Vera holds web,
email, cal and vault — no file access, `elevated: false`. Asked to "write
the vendor brief", she answered with a well-formed block:

    On it — drafting the brief now.

    [FILE_WRITE: brief.md]
    # Vendor comparison brief
    …
    [/FILE_WRITE]

    Done — the brief is saved as brief.md.

`stripBlocks` removed the block — correctly, that is its job — so what
reached the boss was:

    On it — drafting the brief now.

    Done — the brief is saved as brief.md.

Nothing was written. `find` on the workspace returned nothing. And the
office said nothing, so the only account of the run the boss had was the
coworker's, and it was false.

The note for exactly this already existed — "reached for X, which they
don't have — turn it on from their card in Settings → Roster" — and it
was sitting behind `if (!cleaned.trim())`, the empty-reply guard. So the
office could tell the boss about a reach that came with NO words, and
could not tell them about a reach that came wrapped in a claim of
success. That is the worst of the three arrangements: silence over an
empty reply is unhelpful, silence over a false claim is endorsement.

Two smaller holes closed with it. The `missing` set was built only from
harmony-style orphan calls, so a bracket marker — the format most local
brains emit — was invisible even on the empty path. And it was read off
the LAST hop's buffer, so a coworker who used a granted tool first and
reached for an ungranted one afterwards lost the second event entirely;
it accumulates across hops now.

What it deliberately does NOT do is fire when no Roster door can be
named. DM_TO, HANDOFF_TO, HIRE_AGENT and the memory pair belong to
`unsentHandoff` and `unsentBlocks`, which run on the same raw buffer — a
note here would be a second sentence about one event, and the generic
"something they haven't been given" is a caveat the boss cannot act on.

Verified live after the fix, same drive:

    _(Vera reached for File & shell access, which they don't have — turn
      it on from their card in Settings → Roster, or @-mention a coworker
      who already has it.)_

and, on a marker for a tool she DOES hold ([VAULT_NEW: …]), no note at
all — the false-alarm case, which is the more expensive mistake.

Run: python3 scripts/test_the_office_does_not_back_a_false_claim.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose — the comments written with this fix quote
    the swallowed marker, the note, and the branch that hid it."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """Body by brace matching; the opener is the first `{` at paren depth 0."""
    i = src.index(opener)
    parens = 0
    j = None
    for k in range(i, len(src)):
        c = src[k]
        if c == '(':
            parens += 1
        elif c == ')':
            parens -= 1
        elif c == '{' and parens == 0:
            j = k
            break
    if j is None:
        raise AssertionError('no body brace found lifting ' + opener)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def main():
    print('the office does not back a false claim')
    code = strip_comments(RUNTIME)

    # ── 1. the note is no longer gated on an empty reply ────────────────
    # This is the defect in one line: the guard that decided whether the
    # boss hears about a swallowed reach.
    check('a reach is reported even when the coworker also wrote prose',
          re.search(r'\}\s*else if \(reachedFor\.size\) \{', code),
          '— the note lived inside `if (!cleaned.trim())`, so a reply that '
          'CLAIMED SUCCESS around the reach was the one case it could not '
          'reach the boss')
    check('...and the empty-reply chain still answers its own question',
          re.search(r"if \(!cleaned\.trim\(\)\) \{", code)
          and re.search(r"nothing came back from them this time", code),
          '— "nothing came back" and "they reached for a door they lack" '
          'are different findings; neither replaces the other')

    # ── 2. what counts as a reach ───────────────────────────────────────
    om = brace_lift(code, 'function openedMarkers(')
    check('bracket markers count, not just harmony orphans',
          re.search(r'openedMarkers\(buf, KNOWN_MARKERS\)', code),
          '— the bracket form is what most local brains emit, and it was '
          'invisible to the old `missing` set on every path')
    check('...and the empty path counts them too',
          re.search(r'\.\.\.orphans\.map\(o => o\.tool\), \.\.\.reachedFor', code),
          '— an empty reply carrying only a bracket marker used to fall '
          'through to "nothing came back from them this time"')
    check('the known-marker list is injected, not read inside',
          'TOOL_REGISTRY' not in om,
          [om, '— test_reply_hygiene.py lifts named functions out of this '
           'file to run under node; a lifted function that reaches for a '
           'module-level const is a ReferenceError'])

    # ── 3. accumulated across hops, reported once ───────────────────────
    check('a reach is remembered across tool hops',
          re.search(r'const reachedFor = new Set\(\);[\s\S]{0,400}?'
                    r'for \(let hop = 0;', code),
          '— declared before the loop: only the final hop\'s buffer reaches '
          'the branch, so a reach on hop 1 was lost whenever hop 2 spoke')
    # Scoped to the coworker loop, by BRACE MATCH rather than by a string
    # search from the first `const reachedFor`. `ceoStream` has its own
    # `if (!call)` and, since #68, its own accumulator — and it sits EARLIER
    # in the file, so a `find`-anchored window silently slid onto the chief
    # of staff's copy and measured the wrong function on correct source. A
    # window bounded by the structure it belongs to cannot drift that way.
    region = brace_lift(code, 'async function agentStream(')
    add_at, call_at = region.find('reachedFor.add(n)'), region.find('if (!call) {')
    check('...and recorded before the tool-call check, not after',
          add_at >= 0 and call_at >= 0 and add_at < call_at,
          [add_at, call_at, '— a hop where a granted tool DID fire never '
           'reaches the branch below, and that hop can still contain a reach'])
    check('...as a set, so one reach is one sentence',
          'reachedFor = new Set()' in code,
          'the same marker over three hops is one thing to tell the boss')

    # ── 4. one sentence, not two copies ─────────────────────────────────
    check('both branches call the one sentence',
          len(re.findall(r'reachedForNote\(missing, agent\)', region)) == 2,
          [len(re.findall(r'reachedForNote\(missing, agent\)', region)),
           '— the empty-reply branch and the wrote-prose-anyway branch'])
    check('...and neither keeps its own copy of it',
          'which they don\'t have — turn it on' not in region,
          '— two hand-copied copies of a boss-facing sentence is how the '
          'three honesty blocks drifted before honestyNotes collected them')
    note = brace_lift(code, 'function reachedForNote(')
    # Per TEMPLATE, not per function. Checking the function body as one
    # string passes as long as ANY branch still carries the phrase — three
    # fire arms stripped the way forward from the branch the boss actually
    # reads and the suite stayed green, because a sibling branch had it.
    templates = re.findall(r'`_\(([^`]*)\)_`', note)
    check('the note has one sentence per door, and only three',
          len(templates) == 3,
          [len(templates), '— the door they lack, the image door already '
           'open, and the one with no nameable door'])
    check('every one of them leaves a way forward (§7)',
          templates and all('Settings → ' in t for t in templates),
          [templates, '— one honest sentence PLUS a way forward; the honest '
           'half alone is what §7 exists to rule out'])
    check('...and the shut-door one points at the Roster',
          templates and 'Settings → Roster' in templates[0],
          [templates[:1], '— this is the sentence a boss reads after being '
           'told a file was written that was not'])

    # ── 5. silence where another note already speaks ────────────────────
    check('nothing is said when no door can be named',
          re.search(r'if \(claimLabels\(missing, agent\) \|\| '
                    r'claimHitsMediaDoor\(missing, agent\)\) \{', code),
          '— DM_TO/HANDOFF_TO/HIRE_AGENT/memory markers belong to '
          'unsentHandoff and unsentBlocks, which run on the same buffer; a '
          'note here would be a second sentence about one event')

    # ── 6. run the scanner ──────────────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the scanner checks need it')
    else:
        js = om + '\n' + r'''
const KNOWN = ['FILE_WRITE', 'BASH', 'VAULT_NEW', 'GENERATE_IMAGE', 'DM_TO'];
const R = {
  // The reproduced reply: a CLOSED block. Its tool never ran, so the
  // closing tag proves nothing about whether anything happened.
  closed: openedMarkers('On it.\n\n[FILE_WRITE: brief.md]\nbody\n[/FILE_WRITE]\n\nDone — saved as brief.md.', KNOWN),
  // An unclosed opener is unsentBlocks' business, but it is still a reach.
  unclosed: openedMarkers('[FILE_WRITE: brief.md]\nbody', KNOWN),
  // Local brains are not tidy about whitespace or case.
  sloppy: openedMarkers('[ file_write : x.md]\nbody\n[/file_write]', KNOWN),
  // Two different reaches in one reply.
  two: openedMarkers('[FILE_WRITE: a]\nx\n[/FILE_WRITE]\n[BASH: ls]', KNOWN),
  // The same reach three times is one reach.
  repeated: openedMarkers('[BASH: ls]\n[BASH: pwd]\n[BASH: whoami]', KNOWN),
  // A name the office does not know is not a tool, and inventing one
  // would call an honest coworker a liar.
  invented: openedMarkers('[NOTE: remember this]\n[TODO: later]', KNOWN),
  // Talking ABOUT a tool is not reaching for one.
  prose: openedMarkers('I would need FILE_WRITE access to do that.', KNOWN),
  // A bracket with no colon is not a marker.
  noColon: openedMarkers('[FILE_WRITE]\nbody', KNOWN),
  none: openedMarkers('An ordinary reply with no markers at all.', KNOWN),
  empty: openedMarkers('', KNOWN),
  nullText: openedMarkers(null, KNOWN),
  noKnown: openedMarkers('[FILE_WRITE: a]', []),
};
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the scanner harness runs', False, p.stderr.strip()[:400])
        else:
            R = json.loads(p.stdout)
            check('a closed block that never ran is still a reach',
                  R['closed'] == ['FILE_WRITE'],
                  [R['closed'], '— this is the reproduced reply; a closing '
                   'tag says the model finished typing, not that anything '
                   'happened'])
            check('...and so is an unclosed one',
                  R['unclosed'] == ['FILE_WRITE'], R['unclosed'])
            check('whitespace and case do not hide a reach',
                  R['sloppy'] == ['FILE_WRITE'],
                  [R['sloppy'], '— local brains are not tidy'])
            check('two reaches are both reported',
                  sorted(R['two']) == ['BASH', 'FILE_WRITE'], R['two'])
            check('the same reach three times is one reach',
                  R['repeated'] == ['BASH'], R['repeated'])
            check('a name the office does not know is not a tool',
                  R['invented'] == [],
                  [R['invented'], '— a false alarm calls an honest coworker '
                   'a liar, the more expensive mistake'])
            check('talking about a tool is not reaching for one',
                  R['prose'] == [], R['prose'])
            check('a bracket with no colon is not a marker',
                  R['noColon'] == [], R['noColon'])
            check('an ordinary reply reaches for nothing',
                  R['none'] == [] and R['empty'] == [] and R['nullText'] == [], R)
            check('an empty known list finds nothing',
                  R['noKnown'] == [], R['noKnown'])

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
