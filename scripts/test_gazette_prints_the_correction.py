#!/usr/bin/env python3
"""The office wrote the correction, then filed it where the boss could not read it.

`night_runner.run_iteration` catches a specific lie: the model produces the
closing status line the prompt asks for ("Wrote 1.") without ever calling
VAULT_NEW/VAULT_APPEND, so the vault gains nothing. It sets

    lastError = 'said it saved a note, but nothing reached the vault'

and `scripts/test_gazette_error_copy.py` exists entirely to protect the
wording and the display cap of that sentence -- because an earlier version
leaked wire tokens and got truncated mid-clause on the morning report.

On the common path that sentence was never rendered at all.

`run_mission` refreshes `summary` only on a round with no error, so a night
that worked for five rounds and fabricated on the sixth carries BOTH a
summary and a lastError. The Gazette's line read

    r.summary ? summary : r.lastError ? lastError : ''

-- the correction was the ELSE branch of the coworker's own sentence, so it
only ever appeared on a run where no round had ever succeeded. Measured on
a seeded office, two adjacent rows:

    ⚠ Nova · Gold market watch · 6 rounds · 1 notes — Wrote 1. Next iteration
      could explore refinery margins and the LBMA fix.
    ✓ Nova · Shipping rates    · 3 rounds · 1 notes — Wrote 1. Rates steady
      week over week.

One of those runs was caught fabricating and one was fine, and a single ⚠
was the entire difference. The Gazette is the surface that exists BECAUSE
nobody was watching; the two sibling surfaces showing the same runs -- the
Night Shift panel in missions.jsx and the terminal's `night` listing -- have
always printed lastError unconditionally.

The fix puts the office's sentence first and keeps the coworker's, ATTRIBUTED
-- on the fabrication case the summary IS the false claim, and printing it
unlabelled beside the correction just restages the argument.

Landing it also un-buried the abort wording: a boss-stopped night set
lastError to the wire word 'aborted', which §6 bans on a human surface and
which the summary had been hiding.

Run: python3 scripts/test_gazette_prints_the_correction.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / 'features.jsx'
MISSIONS = ROOT / 'missions.jsx'
TERMINAL = ROOT / 'views' / 'terminal.jsx'
RUNNER = ROOT / 'night_runner.py'
FAILS = []

# A night that worked, then fabricated. This is the shape run_mission
# produces, not an invented one -- see the run_mission check below.
BOTH = {
    'agentName': 'Nova',
    'summary': 'Wrote 1. Next iteration could explore refinery margins and the LBMA fix.',
    'lastError': 'said it saved a note, but nothing reached the vault',
}
ERR_ONLY = {'agentName': 'Llama', 'summary': '',
            'lastError': 'said it saved a note, but nothing reached the vault'}
CLEAN = {'agentName': 'Nova', 'summary': 'Wrote 1. Rates steady week over week.',
         'lastError': ''}
BARE = {'agentName': 'Nova', 'summary': '', 'lastError': ''}


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def node_eval(expr, fixtures):
    """Evaluate a JSX expression lifted VERBATIM from features.jsx.

    Source-grepping a ternary tells you the characters are in the right
    order; running it tells you what the boss reads. The expressions here
    are plain JS over one object, so they can be pulled out and called.
    """
    js = ('const F = ' + json.dumps(fixtures) + ';\n'
          'console.log(JSON.stringify(F.map((r) => (' + expr + '))));')
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on an expression from features.jsx')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('the morning paper has to print its own retraction')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    for f in (FEATURES, MISSIONS, TERMINAL, RUNNER):
        if not f.is_file():
            print(f'  FAIL  missing {f}')
            return 1

    feats = FEATURES.read_text(encoding='utf-8')

    # ── 1. the headline clause, run for real ────────────────────────────
    # Deliberately matches EITHER field first. Pinning the order in the regex
    # would make a reordered clause fail as "expression not found", which is a
    # shape complaint — the failure worth reading is the one below, which
    # quotes what the boss would actually see. Anchored on the backtick so the
    # `r.lastError ? '⚠' : '✓'` glyph on the line above is not picked up.
    m = re.search(r"\{(r\.(?:lastError|summary) \? `[\s\S]*?: '')\}", feats)
    check('the Gazette run line has a single status clause', bool(m),
          'features.jsx: expected one `{r.lastError ? `…` : …}` expression in '
          'the NIGHT SHIFT block')
    if not m:
        print('\nthe morning paper: FAILED')
        return 1
    out = node_eval(m.group(1), [BOTH, ERR_ONLY, CLEAN, BARE])
    both, err_only, clean, bare = out

    check('a night that worked then fabricated shows the CORRECTION',
          BOTH['lastError'] in both,
          f'{both!r} — this is the whole defect: run_mission leaves the last '
          "good round's summary in place, so the correction was the else-branch "
          'of a sentence that is almost always present')
    check("...and does not lead with the coworker's claim",
          not both.startswith(' — ' + BOTH['summary'][:20]), both)
    check('a night that only ever failed still shows it',
          ERR_ONLY['lastError'] in err_only, err_only)
    check('a clean night is untouched',
          clean == ' — ' + CLEAN['summary'], clean)
    check('a night with nothing to say says nothing',
          bare == '', bare)

    # ── 2. the coworker's sentence is kept, and attributed ──────────────
    # Dropping it would be the lazy fix and would lose real information on a
    # run where five rounds worked. Printing it unlabelled is what caused
    # this in the first place.
    m2 = re.search(r'\{r\.lastError && r\.summary && \([\s\S]*?\{(`[^`]+`)\}', feats)
    check('the summary survives, in a block gated on BOTH being present',
          bool(m2),
          'features.jsx: expected `{r.lastError && r.summary && (…)}` carrying '
          "the coworker's own sentence")
    if m2:
        attrib = node_eval(m2.group(1), [BOTH])[0]
        check('...and it names who said it',
              attrib.startswith('Nova'), attrib)
        check('...and marks it as a claim, not as fact',
              'said' in attrib and BOTH['summary'][:20] in attrib, attrib)
        check('...and does not use the verb the correction just denied',
              'wrote:' not in attrib.lower(),
              f'{attrib!r} — the line above it is the office saying nothing '
              'was written; "Nova wrote:" beside that is the collision again')

    # ── 3. the cap this block already fought for is still one cap ───────
    # test_gazette_error_copy.py asserts exactly one lastError slice and
    # that the sentence fits it. Restating the count here is cheap and
    # makes the coupling visible from this side too.
    caps = re.findall(r'String\(r\.lastError\)\.slice\(0,\s*(\d+)\)', feats)
    check('there is still exactly one lastError slice, at 90',
          caps == ['90'],
          f'{caps!r} — see scripts/test_gazette_error_copy.py, which pins the '
          'wording against this cap')

    # ── 4. the cross-surface invariant ──────────────────────────────────
    # Three surfaces render night runs. The defect was one of them treating
    # the error as optional. Checked as a property of all three so a new
    # surface, or a regression in an old one, is caught here.
    for label, path in (('the Gazette', FEATURES),
                        ('the Night Shift panel', MISSIONS),
                        ('the terminal listing', TERMINAL)):
        src = path.read_text(encoding='utf-8')
        # An error branch whose alternative is the summary is the bug.
        bad = re.search(r'r\.summary\s*\?[^\n]*\n?[^\n]*?:\s*r\.lastError\s*\?', src)
        check(f'{label} never makes the error an else-branch of the summary',
              not bad,
              f'{path.name}: `r.summary ? … : r.lastError ? …` means the '
              'correction only prints on a run where nothing ever worked')
        check(f'{label} does render lastError at all',
              'lastError' in src, path.name)

    # ── 5. run_mission really does produce both ─────────────────────────
    # The premise of everything above. If summary ever starts being written
    # on error rounds too, the reasoning changes and this should be reread.
    runner = RUNNER.read_text(encoding='utf-8')
    mm = re.search(r"if res\['error'\]:[\s\S]*?else:[\s\S]*?run\['summary'\] = res\['summary'\]",
                   runner)
    check("summary is refreshed only on a round that did NOT error",
          bool(mm),
          'night_runner.py: this is WHY a run carries a stale-good summary '
          'next to a fresh error — the two fields describe different rounds')

    # ── 6. the abort wording the fix un-buried ──────────────────────────
    ab = re.search(r"run\['lastError'\] = '([^']+)'\n\s*break", runner)
    check('a boss-stopped night sets a boss-facing sentence', bool(ab),
          'night_runner.py: expected the abort branch to set lastError')
    sentence = ab.group(1) if ab else ''
    check('...that is not the wire word', sentence != 'aborted', repr(sentence))
    check('...that says what it cost, not just that it stopped',
          re.search(r'did not run|rest of', sentence, re.I) is not None,
          f'{sentence!r} — "stopped" alone leaves the boss to guess whether '
          'the night finished early or never happened')
    check('...and fits the display cap intact',
          len(sentence) <= 90, f'{len(sentence)} chars vs a 90-char cap')

    # Nothing may branch on the old value — it was only ever display text,
    # which is what makes rewording it safe, and is worth pinning.
    # Comments are stripped first: the change that reworded this left a note
    # saying what the old word WAS, and a prose mention is not a comparison.
    def code_only(p):
        src = p.read_text(encoding='utf-8')
        src = re.sub(r'/\*[\s\S]*?\*/', '', src)
        src = re.sub(r'(?m)^\s*//.*$', '', src)
        return re.sub(r'(?m)^\s*#.*$', '', src)

    # Comparisons only, not the assignment — "sets it" and "branches on it"
    # are the two things this check has to tell apart, and a bare occurrence
    # test cannot. A test whose failure message names the wrong sin is worse
    # than no test.
    SENTINEL = re.compile(r"""(?:[=!]==?\s*|\bin\s*[\(\[][^)\]]*|case\s+|includes\(\s*)
                              ["']aborted["']
                           |["']aborted["']\s*[=!]==?""", re.X)
    strays = [p.name for p in (FEATURES, MISSIONS, TERMINAL, RUNNER, ROOT / 'serve.py')
              if SENTINEL.search(code_only(p))]
    check('no surface branches on the abort text', not strays,
          f'{strays!r} — it is display prose, and the moment something '
          'compares against it the wording is no longer free to be honest')

    print()
    if FAILS:
        print(f'the morning paper: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('the morning paper: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
