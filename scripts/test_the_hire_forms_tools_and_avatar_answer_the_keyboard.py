#!/usr/bin/env python3
"""The job-postings BOARD got a keyboard fix (`cardActivate`,
test_the_hire_board_can_be_worked_without_a_mouse.py). The FORM behind
"+ NEW" — where a boss actually configures the hire — did not.

Measured live on a fresh office (127.0.0.1:8905): open Hire -> + NEW,
click the CREATIVITY slider to focus it, press Tab once. Before this fix
focus jumped straight to the PRIVILEGES checkbox — the entire ALLOWED
TOOLS row (Web Search / Library / Image Gen) and the whole AVATAR row (5
sprites) were bare `<div onClick>`s with no role and tabIndex -1 by
default, invisible to the accessibility tree (`read_page` showed three
`generic` nodes for the tools and NOTHING at all under the AVATAR label)
and outside the tab order. A keyboard-only boss filling out this form
could hire someone but could not choose a single tool or an avatar.
Mouse clicks worked the whole time — `onClick` was never missing, only
`tabIndex`/`role`/`onKeyDown` were.

The fix reuses `cardActivate`, the board's own helper, rather than a
second hand-rolled Enter/Space handler — `role`/`aria-checked` are
overridden after the spread since these are toggle/select controls, not
the board's plain buttons. Reuse means a regression in `cardActivate`
breaks both surfaces the same way, so this test re-executes the real
helper (not a copy of it) in addition to checking the two new call
sites wire it in.

Two parts:
  1. `cardActivate` itself, lifted by name and run under Node — proves
     the board's fix still behaves, since this file's two new sites
     depend on it working.
  2. Source checks on the ALLOWED TOOLS and AVATAR blocks: each spreads
     cardActivate (not a bare onClick), carries the right ARIA role,
     and — the check this bug specifically needs — `aria-checked` reads
     the *same* expression as the div's own `on`/`selected` class, so
     the accessible state and the visible state cannot drift apart.

Run: python3 scripts/test_the_hire_forms_tools_and_avatar_answer_the_keyboard.py
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
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  -- ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Blank out /* */ bodies, quote-aware, preserving newlines/positions."""
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
        out.append(ch); i += 1
    return ''.join(out)


def section(src, start_label, end_label):
    """The block of source between two `<label>TEXT</label>` markers,
    exclusive of the end marker itself — how a form-row's fields are
    isolated without depending on brace/line counting."""
    s = src.find(f'<label>{start_label}</label>')
    e = src.find(f'<label>{end_label}</label>', s)
    assert s != -1, f'{start_label!r} label not found'
    assert e != -1, f'{end_label!r} label not found after {start_label!r}'
    return src[s:e]


def main():
    print('the hire form: tools and avatar answer the keyboard')
    raw = open(HIRE, encoding='utf-8').read()
    src = strip_comments(raw)

    # ---- 1. cardActivate itself still behaves, under real Node --------
    print('1. cardActivate (shared helper) behaves under Node')
    m = re.search(r'const cardActivate = \(fn\) => \(\{.*?\n\}\);', raw, re.S)
    check('cardActivate found in modals/hire.jsx', m is not None)
    if not m:
        print('%d check(s) failed' % (len(FAILS) or 1))
        return 1
    helper = m.group(0)

    harness = helper + """
const results = {};
let fired = 0;
const props = cardActivate(() => { fired += 1; });
results.roleIsButton = props.role === 'button';
results.tabIndexZero = props.tabIndex === 0;
fired = 0; props.onClick(); results.clickFires = fired === 1;
const ev = (key) => {
  const node = {};
  let prevented = false;
  return { key, target: node, currentTarget: node,
           preventDefault() { prevented = true; },
           get prevented() { return prevented; } };
};
fired = 0; const e1 = ev('Enter'); props.onKeyDown(e1);
results.enterFires = fired === 1;
results.enterPrevents = e1.prevented;
fired = 0; props.onKeyDown(ev(' '));  results.spaceFires = fired === 1;
fired = 0; props.onKeyDown(ev('a'));  results.otherKeyIgnored = fired === 0;
console.log(JSON.stringify(results));
"""
    tmp = tempfile.mkdtemp(prefix='hireform-')
    try:
        path = os.path.join(tmp, 'h.mjs')
        with open(path, 'w') as fh:
            fh.write(harness)
        proc = subprocess.run([shutil.which('node') or 'node', path],
                               capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            check('node harness ran', False, proc.stderr.strip()[:400])
            r = {}
        else:
            r = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if r:
        check("role='button'", r.get('roleIsButton'))
        check('tabIndex=0 (reachable by Tab)', r.get('tabIndexZero'))
        check('onClick calls the handler', r.get('clickFires'))
        check('Enter activates and preventDefaults', r.get('enterFires') and r.get('enterPrevents'))
        check('Space activates', r.get('spaceFires'))
        check('an ordinary key does not activate', r.get('otherKeyIgnored'))

    # ---- 2. ALLOWED TOOLS wiring ---------------------------------------
    print('2. ALLOWED TOOLS ticks are keyboard-reachable toggles')
    tools_block = section(src, 'ALLOWED TOOLS', 'AVATAR')
    check('the tool grid maps visibleToolsCatalog()',
          'visibleToolsCatalog().map(' in tools_block)
    check('each tick spreads cardActivate(...)',
          '{...cardActivate(()=>toggleTool(t.id))}' in tools_block)
    check('no bare onClick= alongside it (mouse and keyboard from one place)',
          'onClick=' not in tools_block)
    check('role="checkbox" (a tick is a toggle, not a plain button)',
          'role="checkbox"' in tools_block)
    check('aria-checked reads the SAME test as the visible "on" class',
          'aria-checked={tools.includes(t.id)}' in tools_block
          and 'className={`tool-chk ${tools.includes(t.id)?\'on\':\'\'}`}' in tools_block,
          'a screen reader and the pixel-art tick must agree on checked state')

    # ---- 3. AVATAR wiring -----------------------------------------------
    print('3. AVATAR slots are keyboard-reachable, single-select')
    avatar_block = section(src, 'AVATAR', 'PRIVILEGES')
    check('the avatar grid maps HQ.AGENT_COLORS',
          'HQ.AGENT_COLORS.map(' in avatar_block)
    check('each slot spreads cardActivate(...)',
          '{...cardActivate(()=>setAvatar(c))}' in avatar_block)
    check('no bare onClick= alongside it',
          'onClick=' not in avatar_block)
    check('role="radio" (choosing one avatar excludes the others)',
          'role="radio"' in avatar_block)
    check('aria-checked reads the SAME test as the visible "selected" class',
          'aria-checked={avatar===c}' in avatar_block
          and 'className={`slot ${avatar===c?\'selected\':\'\'}`}' in avatar_block,
          'a screen reader and the gold border must agree on which avatar is picked')

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
