#!/usr/bin/env python3
"""The morning report showed the boss two wire-format names and cut the meaning off.

The Gazette's NIGHT SHIFT block renders a run's `lastError` verbatim, sliced
for display. night_runner set that field to:

    said it wrote a note but never called VAULT_NEW/VAULT_APPEND — nothing landed in the vault   (90 chars)

and the Gazette sliced it at 60. The cut lands exactly at the end of the
protocol tokens, so what a boss actually read on their morning report was:

    ⚠ Llama · <topic> · 3 rounds · 0 notes — said it wrote a note but never called VAULT_NEW/VAULT_APPEND

Two faults compounding. §6 bans wire-format names on a human surface, and the
truncation deleted the only clause that says what it MEANS — "nothing landed
in the vault". The boss is left with jargon and no consequence, on the one
screen whose job is telling them what happened overnight.

Two fixes, and both matter:
  · the sentence is office words and short enough to survive a slice;
  · the display cap is raised to 90 to match what the cause classifiers
    themselves cap at. A display cap BELOW the producer's cap is a silent
    editor: snagCause's "that brain isn't signed in yet — add it in
    Settings, or give this to someone else" was being cut to "…or give",
    losing the §7 route out.

Run: python3 scripts/test_gazette_error_copy.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / 'night_runner.py'
FEATURES = ROOT / 'features.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'

FAILS = []

# Wire-format tokens the models and parser depend on — must never be renamed
# in the protocol, and must never be shown to a boss either.
PROTOCOL_TOKENS = ['VAULT_NEW', 'VAULT_APPEND', 'DM_TO', 'SPAWN_SUBAGENT',
                   'BROWSER_FETCH', 'VAULT_SEARCH', 'FILE_READ', 'DIR_LIST']


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('gazette error copy — the morning report is a human surface')
    for f in (RUNNER, FEATURES, FLOOR):
        if not f.is_file():
            print(f'  FAIL  missing {f}')
            return 1
    runner = RUNNER.read_text(encoding='utf-8')
    feats = FEATURES.read_text(encoding='utf-8')
    floor = FLOOR.read_text(encoding='utf-8')

    # ── The sentences that land in the report ───────────────────────────
    # findall, not search: this file checked "the sentence" (the first
    # match) for as long as night_runner had exactly one claim-check
    # literal. The moment a second one landed ABOVE it — the publish-claim
    # branch, 2026-08-15 — the first-match read silently swapped which
    # sentence was under guard and dropped the other, the same
    # single-point rot as every enumerated lift before it. Every literal
    # assigned to `error` is a boss-facing sentence; all of them carry
    # every obligation below.
    sentences = re.findall(r"^\s*error = '([^']+)'", runner, re.M)
    check('night_runner sets boss-facing error sentences', bool(sentences),
          'night_runner.py: expected single-quoted error assignments')
    if not sentences:
        print('\ngazette error copy: FAILED')
        return 1

    leaked = [(t, s) for s in sentences for t in PROTOCOL_TOKENS if t in s]
    check('...with no wire-format token in any of them',
          not leaked,
          f'{leaked!r} — §6 bans these on human surfaces. Rename '
          'the PROSE, never the token itself')

    # ── The display cap must not edit the sentence ──────────────────────
    caps = [int(x) for x in re.findall(r'String\(r\.lastError\)\.slice\(0,\s*(\d+)\)', feats)]
    check('the Gazette slices lastError at a cap it declares',
          len(caps) == 1,
          f'found {caps!r} — expected exactly one lastError slice in features.jsx')
    cap = caps[0] if caps else 0

    cut = [s for s in sentences if len(s) > cap]
    check('every sentence survives that cap intact',
          not cut,
          f'{cut!r} vs a {cap}-char cap — a cut sentence is how the tokens '
          'survived and the meaning did not')
    # A claim-report sentence must state the CONSEQUENCE, not just repeat
    # the claim: "nothing reached the vault", "nothing went live". The
    # word list is the consequence vocabulary, not a sentence enumeration
    # — any honest "said it X, but <nothing happened>" shape lands here.
    dull = [s for s in sentences
            if re.search(r'\bsaid it\b', s, re.I)
            and not re.search(r'nothing|no note|never (?:reached|landed)', s, re.I)]
    check('...and each says what it MEANS, not just what was claimed',
          not dull,
          f'{dull!r} — "said it saved a note" alone is half the story; the '
          'consequence is the half the boss can act on')

    # ── The cap must be >= what the cause classifiers produce ───────────
    m2 = re.search(r'line\.length > (\d+) \? line\.slice\(0, (\d+)\)', floor)
    check('floor.jsx caps its own cause sentences at a known length',
          m2 is not None, 'app/floor.jsx: expected the cleanCause length cap')
    if m2:
        producer_cap = int(m2.group(1))
        check('the Gazette cap is not tighter than the producer cap',
              cap >= producer_cap,
              f'display cap {cap} < producer cap {producer_cap} — every honest '
              'sentence longer than the display cap gets silently edited, and the '
              'part that gets cut is the END, which is where §7 puts the way '
              'forward')

    print()
    if FAILS:
        print(f'gazette error copy: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('gazette error copy: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
