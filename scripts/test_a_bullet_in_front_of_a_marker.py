#!/usr/bin/env python3
"""A bullet in front of a marker was enough to publish it.

`stripBlocks` removes machine markers from a coworker's reply before the
boss sees it. Two of its passes are written as

    ^[ \\t]*  (optional short label)  [MARKER: …]

and the word "optional" is a lie, because the group sits directly behind a
`^` anchor. When the group declines to match — the label runs one word past
its 22-char bound, or the line starts with a markdown bullet — the anchor
then demands a `[` where prose is, and the whole match fails. The pass does
not fall back to stripping just the marker. It strips NOTHING.

So a bound written to decide "should the label go too?" was silently
answering "should the boss see machine syntax?", and answering it yes.

Measured end to end against a canned brain, one task, reply exactly:

    Saved. Here is what I did:

    - **Vault Path:** [VAULT_NEW: Notes/sourdough.md]
    - [MEMORY_WRITE: the boss bakes sourdough on weekends]

    Anything else?

Both bullets reached the boss verbatim on three surfaces — the task card's
result, the chat message, and `Deliveries/save-a-note-about-sourdough-to-
the-vault.md` in the filing cabinet. The office was otherwise honest about
it: `unsentBlocks` correctly warned that nothing had been written. It just
warned in prose sitting directly above the raw markers it was describing.

The fix separates the two decisions. The marker is machine syntax and
always goes; how much of its wrapper goes with it is where a bound belongs.
A bullet or a short label goes with it (litter from this function's own
cut); a long colon label stays and only the marker is taken.

Run: python3 scripts/test_a_bullet_in_front_of_a_marker.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'hq-runtime.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    """The whole function starting at `opener`, by balancing braces."""
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


def main():
    print('a bullet is not permission to publish the marker behind it')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = RUNTIME.read_text(encoding='utf-8')

    # ── the harness ─────────────────────────────────────────────────────
    # Lifted from the real file rather than restated, so a rewrite of any
    # of these functions is measured here instead of quietly diverging.
    js = re.search(r'^const PLACEHOLDER_ARG\s*=.*?;$', src, re.M).group(0) + '\n'
    # Every ORPHAN_TAG_* const, in file order so dependencies resolve. A
    # prefix sweep, not a pinned literal shape: this lift used to match
    # `const ORPHAN_TAG_RE =\n  /.../gim;` exactly, and #81 split that literal
    # into a shared vocabulary plus two anchorings, which crashed this suite
    # on a NoneType instead of reporting. Whatever the next split looks like,
    # it keeps the prefix.
    orphan = [c.group(0) for c in
              re.finditer(r'^const ORPHAN_TAG_\w+\s*=[\s\S]*?;$', src, re.M)]
    if not orphan:
        raise SystemExit('could not find any ORPHAN_TAG_* const')
    js += '\n'.join(orphan) + '\n'
    for fn in ('reasoningPatterns', 'stripReasoning', 'maskReasoning', 'extractAcks', 'stripAcks', 'stripOrphanTags', 'stripBlocks',
               'stripSelfLabel', 'extractAllDMs', 'extractApproval',
               'isHandoffPlaceholder', 'placeholderRefusal', 'unsentBlocks',
               'shownBody', 'visibleReply'):
        js += brace_lift(src, 'function ' + fn + '(') + '\n'

    # `blocks` measures stripBlocks ALONE and `seen` measures the whole
    # reply path. Both are needed and they answer different questions:
    # ORPHAN_TAG_RE strips a line-leading closed marker on its own, so a
    # `seen` check cannot tell whether the pass under test did the work,
    # and `visibleReply` has a raw fallback that can hand back everything
    # the cleaner just removed — which is how an earlier fix in this file
    # passed its own tests while changing nothing the boss could see.
    js += r'''
const CASES = {
  measured:    'Saved. Here is what I did:\n\n- **Vault Path:** [VAULT_NEW: Notes/sourdough.md]\n- [MEMORY_WRITE: the boss bakes sourdough on weekends]\n\nAnything else?',
  bulletLabel: '- **Vault Path:** [VAULT_NEW: Notes/a.md]',
  bulletBare:  '- [VAULT_NEW: Notes/a.md]',
  bulletStar:  '* [VAULT_NEW: Notes/a.md]',
  bulletPlus:  '+ [MEMORY_WRITE: likes rye]',
  numbered:    '1. **Vault Path:** [VAULT_NEW: Notes/a.md]',
  numParen:    '2) [DM_TO: Mika]',
  bulletNoBr:  '- **Vault Path:** [VAULT_NEW: Notes/a.md',
  longLabel:   '**Here is the vault path for you:** [VAULT_NEW: Notes/a.md]',
  longNoBr:    '**Here is the vault path for you:** [VAULT_NEW: Notes/a.md',
  plainLong:   'I saved your notes and the path is here: [VAULT_NEW: a.md]',
  shortLabel:  '**Vault Path:** [VAULT_NEW: Notes/a.md]',
  prose:       'Use [DM_TO: Mika] to reach someone.',
  proseMid:    'The marker [DM_TO: Mika] is how you ask.',
  proseBullet: '- I will save it to [VAULT_NEW: a.md] later on.',
  labelProse:  'Path: [VAULT_NEW: a.md] is where I put it.',
  clockTime:   'Meet at 10:30 [DM_TO: Mika]',
  typoAck:     '[ACK: banana: saved the note]',
  justText:    'hm.',
};
const R = { blocks: {}, seen: {} };
for (const k in CASES) {
  R.blocks[k] = stripBlocks(CASES[k]);
  R.seen[k] = visibleReply(CASES[k], 'Local Brain');
}
console.log(JSON.stringify(R));
'''
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from hq-runtime')
    R = json.loads(proc.stdout.strip().split('\n')[-1])
    B, S = R['blocks'], R['seen']

    def clean(k):
        return '[' not in S[k]

    # ── 1. the reply that was measured ──────────────────────────────────
    check('the reply that was actually filed comes back clean',
          clean('measured'),
          repr(S['measured']) + ' — this exact string reached the task card, '
          'the chat and the cabinet sheet')
    check('...and keeps the prose that wrapped it',
          'Saved.' in S['measured'] and 'Anything else?' in S['measured'],
          repr(S['measured']) + ' — the coworker did write those sentences')

    # ── 2. a list marker is part of the wrapper, not the prose ──────────
    check('a bullet with a labelled marker leaves nothing behind',
          B['bulletLabel'] == '', repr(B['bulletLabel']))
    check('...and a bullet with a bare marker too',
          B['bulletBare'] == '', repr(B['bulletBare']))
    check('...for every bullet character markdown allows',
          B['bulletStar'] == '' and B['bulletPlus'] == '',
          repr([B['bulletStar'], B['bulletPlus']]) + ' — a coworker picks '
          'one of these at random and the boss should not be able to tell '
          'which one they picked')
    check('...and for a numbered list, dot or paren',
          B['numbered'] == '' and B['numParen'] == '',
          repr([B['numbered'], B['numParen']]))
    check('...and when the bracket never closed either',
          B['bulletNoBr'] == '', repr(B['bulletNoBr']) + ' — the two known '
          'ways a marker slips through have to compose, or fixing one just '
          'moves the leak')
    check('THE BOSS never sees a bulleted marker',
          clean('bulletLabel') and clean('bulletBare') and clean('numbered'),
          repr([S['bulletLabel'], S['bulletBare'], S['numbered']])
          + ' — stripBlocks getting it right is not the same as the reply '
            'path getting it right')

    # ── 3. an unrecognised wrapper is not permission to publish ─────────
    check('a label past the bound loses the marker, not the match',
          '[' not in B['longLabel'], repr(B['longLabel']) + ' — this is the '
          'defect in one line: the bound decided the label stays, and the '
          'marker rode out on the same decision')
    check('...whether or not its bracket closed',
          '[' not in B['longNoBr'], repr(B['longNoBr']))
    check('...and with no markdown on it at all',
          '[' not in B['plainLong'], repr(B['plainLong']))
    check('...and the sentence the coworker wrote survives, colon and all',
          B['plainLong'] == 'I saved your notes and the path is here:',
          repr(B['plainLong']) + ' — the marker always goes; how much of the '
          'line goes with it is the only part a bound gets to decide, and '
          'the colon is the model’s punctuation, not this function’s litter')
    check('THE BOSS never sees a long-labelled marker',
          clean('longLabel') and clean('longNoBr') and clean('plainLong'),
          repr([S['longLabel'], S['longNoBr'], S['plainLong']]))

    # ── 4. what must not change ─────────────────────────────────────────
    check('a short label still takes the whole line with it',
          B['shortLabel'] == '', repr(B['shortLabel']) + ' — the original '
          'litter rule; widening the passes must not narrow this one')
    check('prose explaining a marker keeps its sentence',
          B['prose'] == 'Use [DM_TO: Mika] to reach someone.',
          repr(B['prose']) + ' — a coworker telling the boss how to ask for '
          'something is not a coworker asking for it')
    check('...including a marker mid-sentence',
          B['proseMid'] == 'The marker [DM_TO: Mika] is how you ask.',
          repr(B['proseMid']))
    check('...and a bulleted line that is really prose',
          B['proseBullet'] == '- I will save it to [VAULT_NEW: a.md] later on.',
          repr(B['proseBullet']) + ' — the bullet is only litter when the '
          'marker was the whole of what it held')
    check('a label with prose after it keeps its whole sentence',
          B['labelProse'] == 'Path: [VAULT_NEW: a.md] is where I put it.',
          repr(B['labelProse']) + ' — end of line is what tells a marker the '
          'model MEANT apart from one it is talking about, and the fourth '
          'pass has to honour that bound as much as the first three do')
    # A STAGE assertion, not the boss-visible outcome. stripBlocks leaves this
    # bracket standing and ORPHAN_TAG_RE removes it downstream (#81 — a marker
    # ending the line is machine syntax whatever sits before it). What this
    # pins is narrower and still worth pinning: the colon heuristic must not
    # fire on a clock time and eat "Meet at 10:30".
    check('a colon that is not a label leaves the line alone',
          B['clockTime'] == 'Meet at 10:30 [DM_TO: Mika]',
          repr(B['clockTime']) + ' — the fourth pass keys off a colon, and '
          'clock times and ratios are full of colons; it must sit flush '
          'against the bracket or it is not a label')
    check('a typo’d ACK still comes through whole',
          S['typoAck'].strip() == '[ACK: banana: saved the note]',
          repr(S['typoAck']) + ' — unrecognised protocol is text, and text '
          'is the boss’s to see')
    check('...and so does ordinary prose', S['justText'] == 'hm.',
          repr(S['justText']))

    # ── 5. the shape of the fix, so a rewrite cannot lose it ────────────
    fn = brace_lift(src, 'function stripBlocks(')
    check('the list-marker prefix is shared by both whole-line passes',
          fn.count('LEAD + LABEL') == 2, 'stripBlocks: the closed-bracket and '
          'unclosed-bracket passes drifted apart once before; sharing the '
          'prefix is what keeps a fix to one from missing the other')
    check('the marker-only pass runs last',
          fn.index('.replace(residue') > fn.index('.replace(broken'),
          'the whole-line passes have to have their chance first, or every '
          'labelled marker leaves a dangling colon instead of going quietly')
    check('...and puts back what it matched around the marker',
          re.search(r"\.replace\(residue,\s*'\$1'\)", fn) is not None,
          'replacing with the empty string would eat the colon label the '
          'pass exists to preserve')

    print()
    if FAILS:
        print(f'the wrapper: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('the wrapper: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
