#!/usr/bin/env python3
"""A missing `]` put broken machine syntax in the boss's filing cabinet.

Measured end to end against a canned brain — an OpenAI-compatible server
that returns one exact string, hired through the front desk like any other
coworker. One task, one reply, byte for byte:

    [VAULT_NEW: Notes/scratch.md

An opener whose BRACKET never closed. Every cleaner in the reply path wants
a `]` before it will act — the closed-block pass, the lone-opener pass, and
ORPHAN_TAG_RE — so this string walked through all three untouched and became
the coworker's deliverable. Then, in order:

  the board       went green, because there WAS content to certify
  the cabinet     gained Deliveries/save-a-note-about-sourdough-to-the-
                  vault.md, whose entire body between the title and the
                  Working footer is the broken marker
  the guard       stayed quiet — filing set `deliveryFiled`, which puts
                  VAULT_NEW into `skipKinds`, so the office suppressed
                  "no file reached the cabinet" on the strength of having
                  filed the very thing the note was about

Four surfaces from one character. The file is the one that lasts: chat
scrolls, the board gets cleared, and a .md sits in the cabinet until someone
opens it in a month and reads machine syntax under their own task title.

Fixed at the root, because all three of the others read what the cleaner
returns. Strip it and the reply is empty, and an empty reply is a case the
office already handles correctly: the card parks in `doing`, and the guard
fires with the sentence and the way forward it has always had.

WHOLE-LINE is the bound, and the bound is the design. The lone-opener pass
above it can afford to be looser because a closed bracket is already evidence
of intent; with no `]` anywhere, text mentioning a marker is likelier to be
prose about one. So the line must open with the marker and reach its end
without closing. `Use [DM_TO: Mika] to reach someone.` keeps both its bracket
and its sentence.

Run: python3 scripts/test_a_marker_that_never_closed_its_bracket.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
FEATURES = ROOT / 'features.jsx'
FAILS = []


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


def run_js(src):
    p = subprocess.run(['node', '--input-type=module', '-e', src],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('a marker that never closed its bracket')
    src = RUNTIME.read_text(encoding='utf-8')

    check('the cleaner the reply path runs is the one that got the pass',
          re.search(r'stripOrphanTags\(stripAcks\(stripBlocks\(stripSelfLabel',
                    src),
          'visibleReply composes these four; a pass added anywhere else in '
          'the file cleans nothing the boss ever sees')

    # ── the sixth surface, found by looking at the fixed board ───────────
    # Everything above put the card in `doing` with a readable reason, and
    # the card then printed `✓ finished` over the top of it — keyed off the
    # presence of a result rather than the status of the task. Same family
    # as the defect being fixed, found only because the fix made the card
    # worth reading.
    feats = FEATURES.read_text(encoding='utf-8')
    check('a result on the card is not a finish',
          re.search(r"const finished = t\.status === 'done';", feats),
          "the header read `✓ finished` on a card wearing ✋ hit a snag "
          'three lines above it')
    check('...and an unfinished one says what it actually is',
          re.search(r"came back with this", feats),
          'the text is still worth showing — it is what came back — so the '
          'label changes rather than the block disappearing')
    check('...and the gate matches the two surfaces beside it',
          feats.count("t.status !== 'done'") >= 2
          and "const finished = t.status === 'done';" in feats,
          "stalledNote and blockedReason both gate on done-ness, not on "
          "`=== 'doing'`, because the reload scrub sends doing cards back "
          'to inbox with these fields intact')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 1 if FAILS else 0

    m = re.search(r'const ORPHAN_TAG_RE =\n(.*?);\n', src, re.S)
    js = re.search(r'^const PLACEHOLDER_ARG\s*=.*?;$', src, re.M).group(0) + '\n'
    js += 'const ORPHAN_TAG_RE =\n' + m.group(1) + ';\n'
    # visibleReply itself, not just the strippers it calls. The first cut of
    # this test pinned stripBlocks alone, went green, and the live office was
    # unchanged — because visibleReply's last line hands the RAW text back
    # when the strip leaves nothing, and that is the line the measured bug
    # actually rode in on. A test that stops at the stripper is a test of the
    # stripper.
    for fn in ('extractAcks', 'stripAcks', 'stripOrphanTags', 'stripBlocks',
               'stripSelfLabel', 'extractAllDMs', 'extractApproval',
               'isHandoffPlaceholder', 'placeholderRefusal', 'unsentBlocks',
               'visibleReply'):
        js += brace_lift(src, 'function ' + fn + '(') + '\n'
    js += r'''
const C = {
  broken:          '[VAULT_NEW: Notes/scratch.md',
  brokenLabel:     '**Vault Path:** [VAULT_NEW: Notes/scratch.md',
  brokenThenProse: '[VAULT_NEW: Notes/scratch.md\nSourdough needs a starter.',
  brokenMemory:    '[MEMORY_WRITE: notes/citrus.md',
  brokenHandoff:   '[DM_TO: Mika',
  closedBracket:   '[VAULT_NEW: Notes/scratch.md]',
  bracketThenProse: '[HIRE_AGENT: a writer] is the way to ask for one.',
  realBlock:       '[VAULT_NEW: a.md]\nbody\n[/VAULT_NEW]',
  explaining:      'Use [DM_TO: Mika] to reach someone.',
  explainOpen:     'Open it with [VAULT_NEW: and close it with the matching tag.',
  midLine:         'I will write it. [VAULT_NEW: notes/a.md',
  prose:           'Blue is a primary colour.',
};
const R = { clean: {}, blocks: {}, seen: {} };
for (const k in C) {
  R.clean[k] = stripOrphanTags(stripBlocks(C[k])).trim();
  R.blocks[k] = stripBlocks(C[k]).trim();
  // What the BOSS gets — the whole function, fallback and all.
  R.seen[k] = visibleReply(C[k], 'Local Brain');
}
R.guard = unsentBlocks('[VAULT_NEW: Notes/scratch.md');
R.guardSkipped = unsentBlocks('[VAULT_NEW: Notes/scratch.md', ['VAULT_NEW']);
// An unrecognised marker is the case the raw fallback was written for, and
// it has to keep working: the office did not understand this, so the text
// is the boss's to see.
// Both of these REACH the new door — cleaned is empty, no ack was
// recognised, no hand-off, no approval — and both must still come back raw.
// A case that returns earlier than the door cannot say anything about it.
R.typoAck = visibleReply('[ACK: banana: saved the note]', 'Local Brain');
R.orphanRead = visibleReply('[VAULT_READ: notes/a.md]', 'Local Brain');
R.unknown = visibleReply('[BANANA_TIME: now', 'Local Brain');
console.log(JSON.stringify(R));
'''
    r = run_js(js)
    c = r['clean']
    b = r['blocks']
    seen = r['seen']

    # ── what the boss is handed ──────────────────────────────────────────
    # These are the checks that matter. The strip-level ones below prove the
    # cleaner works; these prove the office USES it. The first version of
    # this file had only the strip-level ones, passed 15/15, and the live
    # office produced the cabinet file described above without a murmur.
    check('THE BOSS never sees the broken marker', seen['broken'] == '',
          f"{seen['broken']!r} — visibleReply hands the RAW text back when "
          'the strip leaves nothing, so every pass above that line is undone '
          'in exactly the case that needed it most')
    check('...nor when it wore a label', seen['brokenLabel'] == '',
          f"{seen['brokenLabel']!r}")
    check('...nor for a memory write', seen['brokenMemory'] == '',
          f"{seen['brokenMemory']!r}")
    check('a real answer beside a broken marker still reaches them',
          seen['brokenThenProse'] == 'Sourdough needs a starter.',
          f"{seen['brokenThenProse']!r} — the fallback must not be traded "
          'for silence on replies that had something in them')
    check('a typo’d ACK still comes through whole',
          r['typoAck'] == '[ACK: banana: saved the note]',
          f"{r['typoAck']!r} — the documented reason the raw fallback was "
          'written: stripAcks deletes any lowercase state while extractAcks '
          'accepts only the four real ones, so a typo would otherwise erase '
          "a coworker's entire reply. This fix narrows that rule to markers "
          'the office can explain; it must not delete it')
    check('...and so does a lone read marker',
          r['orphanRead'] == '[VAULT_READ: notes/a.md]',
          f"{r['orphanRead']!r} — reaches the same door and is not something "
          '`unsentBlocks` has a sentence for, so the old behaviour stands')
    check('...and a marker the office has never heard of',
          r['unknown'] == '[BANANA_TIME: now',
          f"{r['unknown']!r} — if it was not protocol it was text, and text "
          "is the boss's to see")

    # ── the shape that was measured ──────────────────────────────────────
    check('a bare unclosed-bracket opener leaves nothing behind',
          c['broken'] == '',
          f"{c['broken']!r} — this exact string was filed in the cabinet as "
          "a coworker's finished work")
    check('...and takes its dangling label with it', c['brokenLabel'] == '',
          f"{c['brokenLabel']!r} — a heading for a value the cleaner just "
          'deleted is litter from its own cut, not the model’s prose')
    check('...for a write marker of any kind', c['brokenMemory'] == '',
          f"{c['brokenMemory']!r} — the measured case was VAULT_NEW; the "
          'missing bracket is not specific to it')
    check('...and for a request marker too', c['brokenHandoff'] == '',
          f"{c['brokenHandoff']!r} — a hand-off nobody received reads the "
          'same as a file nobody wrote')

    # ── what must survive ────────────────────────────────────────────────
    check('a real answer after a broken opener survives',
          c['brokenThenProse'] == 'Sourdough needs a starter.',
          f"{c['brokenThenProse']!r} — the whole reason the older rule "
          'strips the tag and not the text after it')
    check('a coworker explaining a marker keeps their sentence',
          c['explaining'] == 'Use [DM_TO: Mika] to reach someone.',
          f"{c['explaining']!r} — eating it here turns an explanation into "
          '"Use  to reach someone."')
    check('...including one explaining an opener with no bracket',
          c['explainOpen'] == 'Open it with [VAULT_NEW: and close it with '
                              'the matching tag.',
          f"{c['explainOpen']!r} — this is the sentence the whole-line bound "
          'exists to protect, and the one a looser rule would eat')
    # Measured against stripBlocks ALONE, on purpose. ORPHAN_TAG_RE, one link
    # further down the chain, tidies a line-leading closed marker away by its
    # own older rule, and would answer this question with its behaviour
    # instead of the new pass's. The question here is what THIS pass does with
    # a bracket that closed, and the only place that is visible is here.
    check('a marker that DID close its bracket keeps the rest of its line',
          b['bracketThenProse'] == '[HIRE_AGENT: a writer] is the way to ask '
                                   'for one.',
          f"{b['bracketThenProse']!r} — the line OPENS with a marker, so the "
          'line anchor does not save this one. What saves it is that the pass '
          'must reach end-of-line without meeting a `]`, and this one meets '
          'one immediately. Drop that requirement and the boss reads "] is '
          'the way to ask for one."')
    check('plain prose is untouched', c['prose'] == 'Blue is a primary colour.',
          c['prose'])

    # ── the two older passes still do their jobs ─────────────────────────
    check('a closed-bracket opener still goes', c['closedBracket'] == '',
          f"{c['closedBracket']!r} — the pass this sits beside")
    check('a well-formed block still goes, payload and all',
          c['realBlock'] == '', f"{c['realBlock']!r}")

    # ── a deliberate miss, recorded rather than smoothed ─────────────────
    check('a mid-line broken opener is left alone, silently',
          c['midLine'] == 'I will write it. [VAULT_NEW: notes/a.md',
          f"{c['midLine']!r} — with no bracket AND no line anchor there is "
          'nothing left to tell a marker from prose about one, so this one '
          'is a known miss; the guard below still fires on it')

    # ── the compensating half: the boss is told ──────────────────────────
    check('the guard still fires on the bracket it never closed',
          r['guard'] and 'no file reached the cabinet' in r['guard'],
          f"{r['guard']!r} — stripping the marker must not also strip the "
          'reason; an empty reply with no explanation is a worse card than '
          'a broken one with a sentence under it')
    check('...and its sentence carries a way forward',
          r['guard'] and 'file it again' in r['guard'],
          f"{r['guard']!r} — §7: every failure is one honest sentence plus "
          'a way forward')
    check('...and the office can still hush it once it files the work itself',
          r['guardSkipped'] is None,
          f"{r['guardSkipped']!r} — skipKinds is what stops the note calling "
          'a real, successful filing a lie')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
