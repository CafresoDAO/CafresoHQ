#!/usr/bin/env python3
"""The sentences that exist to be honest with the boss spoke in machine.

§6 of OFFICE_AS_INTERFACE is a jargon table, binding on all UI copy. The
copy breaking it hardest was the copy written to protect the boss: every
one of `unsentBlocks`' fourteen notes, plus `unsentHandoff` and
`unsentElevation`, diagnosed the failure the same way —

    nothing was saved to their memory — that note needs a closing tag to
    be written, so it is not there however it was described above. Ask
    them to save it again.

A closing tag is not a thing in the boss's world. They cannot supply one,
cannot ask for one, and cannot tell a coworker who forgot one from a
coworker who is simply not very good. And it teaches: the office is built
so the boss never learns there is a marker protocol underneath, and this
was the surface that told them — at the exact moment they were already
being handed bad news.

Two ticks earlier the raw marker printed BESIDE this sentence was removed,
on the reasoning that it showed the machine's name for a failure already
described in words. The words kept the machine's name.

The replacement is not a metaphor. An opener with no closer IS a coworker
who began the write and stopped partway — true, in the office's own
vocabulary, and it tells the boss the one thing that changes what they do
next: the coworker meant to do it, so asking again is worth the trouble.

What must not change is the shape §7 requires. Every note still leads with
the contradiction (the coworker may have just claimed success, and that
claim is what the boss actually read) and still ends with a way forward.
Only the middle clause was ever the problem.

Run: python3 scripts/test_the_honesty_notes_speak_plainly.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
DOCS = ROOT / 'docs' / 'OFFICE_AS_INTERFACE.md'
FAILS = []

# Words a boss cannot act on, cannot ask for, and should never learn from
# an error message. Not a style list — every one of these names a piece of
# the marker protocol or the model plumbing that the office exists to hide.
JARGON = [
    'closing tag', 'opening tag', 'close tag', 'tag',
    'marker', 'delimiter', 'bracket', 'syntax', 'parse', 'parsed',
    'malformed', 'well-formed', 'block form', 'detail lines',
    'on its own line', 'on its own lines',
    'token', 'max_tokens', 'temperature', 'prompt', 'api', 'json',
]


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def jargon_in(text):
    """Which banned words appear, matched on word boundaries.

    Boundaries matter: "it is not there" contains no 'tag', and refusing to
    match inside words is what lets the list keep a term as short as 'tag'
    without flagging every sentence with 'stage' or 'vantage' in it."""
    low = str(text).lower()
    return [w for w in JARGON if re.search(r'\b' + re.escape(w) + r'\b', low)]


def main():
    print('a note written for the boss is written in the boss’s words')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = RUNTIME.read_text(encoding='utf-8')

    # ── every note the guards can produce, run for real ─────────────────
    # Lifted and executed rather than regex-scraped out of the source: the
    # notes are assembled at call time (unsentHandoff interpolates a name),
    # and a scrape would measure the template instead of the sentence.
    js = brace_lift(src, 'function unsentBlocks(') + '\n'
    js += brace_lift(src, 'function unsentElevation(') + '\n'
    js += brace_lift(src, 'function unsentHandoff(') + '\n'
    js += r'''
const KINDS = ['HIRE_AGENT','HIRE_ASSISTANT','SPAWN_SUBAGENT','HANDOFF_TO',
  'MEMORY_WRITE','MEMORY_APPEND','VAULT_NEW','VAULT_APPEND','FILE_WRITE',
  'EXPORT_PPTX','EXPORT_DOCX','EXPORT_PDF','GENERATE_IMAGE','GENERATE_VIDEO'];
const R = { notes: {}, all: [] };
for (const k of KINDS) {
  const note = unsentBlocks('[' + k + ': something]\nbody text');
  R.notes[k] = note;
  if (note) R.all.push(note);
}
R.elevation = unsentElevation('[REQUEST_ELEVATION: shell access', false);
if (R.elevation) R.all.push(R.elevation);
R.handoff = unsentHandoff('[DM_TO: Mika] please take this', 0, 'Nova', ['Mika']);
if (R.handoff) R.all.push(R.handoff);
R.skipped = unsentBlocks('[VAULT_NEW: a.md]\nbody', ['VAULT_NEW']);
R.closed  = unsentBlocks('[VAULT_NEW: a.md]\nbody\n[/VAULT_NEW]');
console.log(JSON.stringify(R));
'''
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from hq-runtime')
    R = json.loads(proc.stdout.strip().split('\n')[-1])
    notes, every = R['notes'], R['all']

    # ── 1. the guards still fire, or nothing below means anything ───────
    missing = [k for k, v in notes.items() if not v]
    check('every write- and request-class marker still has a note',
          not missing, 'silent kinds: ' + ', '.join(missing) + ' — a guard '
          'that cannot fire has established nothing, and rewording is the '
          'easiest way to delete one by accident')
    check('...and the elevation and hand-off guards too',
          bool(R['elevation']) and bool(R['handoff']),
          repr([R['elevation'], R['handoff']]))
    check('a marker that closed properly says nothing', R['closed'] is None,
          repr(R['closed']))
    check('...and neither does one the office filed itself',
          R['skipped'] is None, repr(R['skipped']) + ' — skipKinds exists '
          'because the note calls three honest surfaces liars otherwise')
    check('sixteen notes in all, which is what the guards cover',
          len(every) == 16, str(len(every)))

    # ── 2. none of them speaks machine ──────────────────────────────────
    dirty = {}
    for note in every:
        found = jargon_in(note)
        if found:
            dirty[note[:60]] = found
    check('no note uses a word from the §6 table or the marker protocol',
          not dirty, json.dumps(dirty, indent=1))
    check('...and specifically none of them says "closing tag"',
          not any('closing tag' in n.lower() for n in every),
          'the exact phrase that was on all sixteen')

    # ── 3. the §7 shape survived the rewrite ────────────────────────────
    # A plainer sentence that stopped contradicting the claim, or stopped
    # offering a next step, would pass section 2 and be a worse note.
    NEGATION = re.compile(
        r'\b(nothing|no file|no deck|no document|no pdf|no image|no video|'
        r'no helper|never|not there|unchanged|didn.t)\b', re.I)
    weak = [n[:70] for n in every if not NEGATION.search(n)]
    check('every note still says plainly that it did not happen', not weak,
          json.dumps(weak, indent=1) + ' — the coworker may have just claimed '
          'success in the line above, and that claim is what the boss read')

    FORWARD = re.compile(
        r'\b(ask them|try again|send it again|yourself|grant it|'
        r'hand (?:the job|it) to)\b', re.I)
    stuck = [n[:70] for n in every if not FORWARD.search(n)]
    check('...and still offers a way forward', not stuck,
          json.dumps(stuck, indent=1) + ' — §7 is one honest sentence PLUS a '
          'way forward; the honest half alone is just bad news')

    check('the note that contradicts a claimed save still contradicts it',
          'however it was described above' in (notes['MEMORY_WRITE'] or ''),
          repr(notes['MEMORY_WRITE']) + ' — this clause is aimed at the ACK '
          'the coworker wrote one line earlier, which is the whole reason '
          'write-class notes are worded differently from request-class')

    # ── 3b. and points at a door that exists ────────────────────────────
    # The first draft of the hire notes said "from the Team page", which
    # sounds right and is wrong: hiring is a vacant desk on the office
    # floor. §5 is about exactly this — a way forward aimed at the wrong
    # surface is worse than none, because the boss goes there and finds
    # nothing, and now the office has lied to them twice in one message.
    office = (ROOT / 'ui' / 'office.jsx').read_text(encoding='utf-8')
    hires = [notes['HIRE_AGENT'], notes['HIRE_ASSISTANT']]
    check('the hire notes name the gesture that actually hires',
          all('empty desk' in n for n in hires), repr(hires))
    # Anchored to the vacant-unit element itself, not to "onHire appears
    # somewhere near the word vacant" — the floor calls onHire from three
    # places, so a loose match stays green while the desk itself stops
    # hiring, which is the one regression this check is for.
    vacant = re.search(r'className="px-room vacant"[\s\S]{0,300}?>', office)
    check('...and a vacant desk really is what calls onHire',
          vacant is not None and 'onHire' in vacant.group(0),
          'ui/office.jsx: ' + (vacant.group(0)[:200] if vacant else 'no vacant '
          'unit found') + ' — if the desk stops being the hire affordance, '
          'this sentence becomes a wrong direction and has to be rewritten '
          'with it')

    # ── 4. the shared phrasing, so the sixteen cannot drift apart ───────
    partway = [n for n in every if 'stopped partway' in n]
    check('all sixteen describe the failure the same way',
          len(partway) == 16, f'{len(partway)}/16 — sixteen hand-rolled '
          'phrasings for one condition is how the tool-visit row ended up '
          'described four different ways (§6 pass four)')

    # ── 5. the rule is written down where copy gets reviewed ────────────
    docs = DOCS.read_text(encoding='utf-8')
    check('§6 still exists and still says it binds all UI copy',
          '## 6. Jargon translation table (binding for all UI copy)' in docs,
          'the heading these notes are measured against')

    print()
    if FAILS:
        print(f'plain speech: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('plain speech: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
