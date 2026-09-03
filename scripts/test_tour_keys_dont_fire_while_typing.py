#!/usr/bin/env python3
"""The onboarding tour's keyboard shortcuts must not fire while the boss is typing (ui/onboarding.jsx).

Bug: OnboardingTour registers a window-level keydown handler that maps
Enter/ArrowRight to Next and ArrowLeft to Back — with no check of where the
keystroke came from. The tour's "Your AI brain" step embeds
<OnboardingKeyStep>, a real form: its key input saves on Enter and never
stops propagation. So after pasting an OpenRouter key, pressing Enter saved
the key AND advanced the tour in the same keystroke — and the next step's
action() navigates views, so the boss was yanked to the office floor before
the "✓ Key saved" confirmation could render, left unsure whether the save
happened at all. Arrow keys were worse: moving the text cursor inside the
key field flipped tour steps, unmounting the input mid-edit and eating
whatever was typed.

Fix: a plain, lifted-by-name helper `isTypingTarget(t)` (same precedent as
resolveSpotlight in the same file) answers "did this keydown originate in
something the user types into" — INPUT/TEXTAREA/SELECT or contenteditable —
and the onKey handler returns early for those before Next/Back can fire.
Escape is deliberately exempt: closing the tour from inside a field is the
one navigation a typist still means.

This lifts the REAL isTypingTarget out of ui/onboarding.jsx (brace-balanced
extraction) and drives it in Node against stand-in event targets, then
structurally asserts the onKey handler consults it AFTER the Escape close
but BEFORE any next()/back() dispatch.
Run: python3 scripts/test_tour_keys_dont_fire_while_typing.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'ui' / 'onboarding.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_function(src, name):
    """Brace-balanced extraction of `function NAME(...) { ... }` — same
    technique test_workspace_terminal_key.py uses."""
    m = re.search(r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{', src)
    if not m:
        return None
    depth = 0
    j = m.end() - 1  # the opening '{'
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


def main():
    print('OnboardingTour — keystrokes in a form field never drive the tour')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    fn = extract_function(text, 'isTypingTarget')
    check('isTypingTarget extracted from ui/onboarding.jsx', fn is not None)
    if fn is None:
        print('\nFAILED: %s' % FAILS)
        return 1

    # ── Behavioral: run the REAL helper in Node against stand-in targets ──
    harness = fn + r'''
const cases = [
  ['null target',            null,                                false],
  ['tour card div',          { tagName: 'DIV' },                  false],
  ['Next button',            { tagName: 'BUTTON' },               false],
  ['the key input',          { tagName: 'INPUT' },                true ],
  ['lowercased tagName',     { tagName: 'input' },                true ],
  ['a textarea',             { tagName: 'TEXTAREA' },             true ],
  ['a select',               { tagName: 'SELECT' },               true ],
  ['contenteditable region', { tagName: 'DIV', isContentEditable: true }, true],
];
console.log(JSON.stringify(cases.map(([name, t, want]) =>
  ({ name, want, got: isTypingTarget(t) }))));
'''
    r = subprocess.run(['node', '-e', harness], capture_output=True, text=True)
    check('helper runs standalone in node', r.returncode == 0, r.stderr.strip()[:200])
    if r.returncode == 0:
        for row in json.loads(r.stdout):
            check(f"isTypingTarget: {row['name']} -> {row['want']}",
                  row['got'] == row['want'], f"got {row['got']}")

    # ── Structural: the tour's onKey handler actually uses the guard ──
    tour = extract_function(text, 'OnboardingTour')
    check('OnboardingTour extracted', tour is not None)
    if tour is not None:
        m = re.search(r'const onKey = \(e\) => \{(.*?)\n    \};', tour, re.S)
        check('onKey handler found in OnboardingTour', m is not None)
        if m is not None:
            body = m.group(1)
            esc = body.find('Escape')
            guard = body.find('isTypingTarget(e.target)')
            nxt = body.find('next()')
            bck = body.find('back()')
            check('onKey consults isTypingTarget(e.target)', guard != -1)
            check('guard returns early (typed keys never reach Next/Back)',
                  'return' in body[max(guard, 0):nxt if nxt != -1 else None]
                  if guard != -1 else False)
            check('guard sits before next()', guard != -1 and nxt != -1 and guard < nxt)
            check('guard sits before back()', guard != -1 and bck != -1 and guard < bck)
            check('Escape still closes from inside a field (checked before the guard)',
                  esc != -1 and guard != -1 and esc < guard)

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'tour typing guard: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
