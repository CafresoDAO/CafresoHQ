#!/usr/bin/env python3
"""The job-postings board is the first screen a new boss sees, and hiring is the
one thing it exists to do. Every tile on it used to be a bare <div onClick>:
reachable with a mouse, invisible to the keyboard.

Measured on a fresh office before the fix -- the only focusable elements in the
entire dialog were "NEW HIRE ->" and "CLOSE X". All eight candidate cards, the
"+ NEW" tile and the SEED SWARM tile were plain divs with no tabindex and no
role, so a keyboard-only boss could not hire any of the coworkers the front desk
had just found for them. That is the onboarding path dead-ending.

Two halves, because a source check alone would not catch a helper that is wired
in everywhere but does not work:

  1. Behaviour: the cardActivate helper is extracted and RUN under Node. Enter
     and Space must fire, other keys must not, and an event whose target is a
     nested child must not (the template tile holds a real nested delete button
     whose Enter keypress bubbles -- without that guard, deleting a saved role
     would also load it into the form).
  2. Wiring: no interactive tile on the board may carry a bare onClick. Comments
     are stripped first -- the fix's own comment contains the literal string
     "<div onClick>", which is exactly the shape being searched for.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIRE = os.path.join(ROOT, 'modals', 'hire.jsx')
failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(' -- ' + detail) if detail else ''}")
        failures.append(label)


def strip_comments(src):
    """Blank out /* */ and // comment BODIES, preserving newlines so line
    numbers stay accurate. Quote-aware, so string literals survive intact."""
    out, i, n = [], 0, len(src)
    quote = None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(src[i + 1]); i += 2; continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in '"\'`':
            quote = ch; out.append(ch); i += 1; continue
        if ch == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            j = n if j == -1 else j + 2
            out.append(''.join(c if c == '\n' else ' ' for c in src[i:j]))
            i = j
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            j = n if j == -1 else j
            out.append(' ' * (j - i))
            i = j
            continue
        out.append(ch); i += 1
    return ''.join(out)


def main():
    src = open(HIRE).read()

    # ---- 1. the helper actually behaves ------------------------------------
    print("1. cardActivate behaves under Node")
    m = re.search(r'const cardActivate = \(fn\) => \(\{.*?\n\}\);', src, re.S)
    if not m:
        print("  FAIL cardActivate helper not found in modals/hire.jsx")
        return 1
    helper = m.group(0)
    check("helper found in modals/hire.jsx", True)

    harness = helper + """
const results = {};
let fired = 0;
const props = cardActivate(() => { fired += 1; });

results.roleIsButton = props.role === 'button';
results.tabIndexZero = props.tabIndex === 0;

// onClick must call the SAME fn -- mouse and keyboard must not drift apart.
fired = 0; props.onClick(); results.clickFires = fired === 1;

const ev = (key, sameTarget) => {
  const node = {};
  let prevented = false;
  return {
    key,
    target: sameTarget ? node : { nested: true },
    currentTarget: node,
    preventDefault() { prevented = true; },
    get prevented() { return prevented; },
  };
};

fired = 0; const e1 = ev('Enter', true);  props.onKeyDown(e1);
results.enterFires = fired === 1;
results.enterPrevents = e1.prevented;

fired = 0; props.onKeyDown(ev(' ', true));   results.spaceFires = fired === 1;
fired = 0; props.onKeyDown(ev('a', true));   results.otherKeyIgnored = fired === 0;
fired = 0; props.onKeyDown(ev('Tab', true)); results.tabIgnored = fired === 0;

// The nested-delete-button guard.
fired = 0; props.onKeyDown(ev('Enter', false));
results.nestedTargetIgnored = fired === 0;

console.log(JSON.stringify(results));
"""
    tmp = tempfile.mkdtemp(prefix='hireboard-')
    try:
        path = os.path.join(tmp, 'h.mjs')
        with open(path, 'w') as fh:
            fh.write(harness)
        proc = subprocess.run([shutil.which('node') or 'node', path],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            print("  FAIL node harness errored: " + proc.stderr.strip()[:400])
            failures.append("node harness")
            r = {}
        else:
            r = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if r:
        check("role='button'", r.get('roleIsButton'))
        check("tabIndex=0 (so it is reachable by Tab)", r.get('tabIndexZero'))
        check("onClick calls the same fn", r.get('clickFires'))
        check("Enter activates", r.get('enterFires'))
        check("Enter calls preventDefault (no page scroll / double-fire)",
              r.get('enterPrevents'))
        check("Space activates", r.get('spaceFires'))
        check("an ordinary letter key does not activate", r.get('otherKeyIgnored'))
        check("Tab does not activate (it must still move focus)", r.get('tabIgnored'))
        check("a keypress from a NESTED control does not activate the tile",
              r.get('nestedTargetIgnored'))

    # ---- 2. every tile is wired to it --------------------------------------
    print("2. no interactive tile on the board carries a bare onClick")
    clean = strip_comments(src)

    # Sanity: the comment really does contain the shape we search for, so a test
    # that skipped stripping would pass for the wrong reason. Prove it is gone.
    check("comment stripping removed the decoy '<div onClick>' in the fix's note",
          '<div onClick>' in src and '<div onClick>' not in clean)

    board = re.findall(r'<div[^>]*className="[^"]*(?:post-card|hire-tile|frontdesk-card)[^"]*"[^>]*>',
                       clean, re.S)
    check("found the board tiles to check", len(board) >= 5, f"found {len(board)}")
    for tag in board:
        flat = ' '.join(tag.split())
        cls = (re.search(r'className="([^"]*)"', flat) or [None, '?'])[1]
        check(f"tile [{cls}] uses cardActivate, not a bare onClick",
              'cardActivate' in flat and 'onClick=' not in flat,
              flat[:120])

    # The nested delete control must stay a real <button> -- it is already
    # focusable, and turning it into a div would reopen the same hole.
    check("the saved-role delete control is still a real <button>",
          re.search(r'<button[^>]*className="[^"]*post-remove', clean) is not None)

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures[:6]))
        return 1
    print("PASS: the hire board can be worked without a mouse")
    return 0


if __name__ == '__main__':
    sys.exit(main())
