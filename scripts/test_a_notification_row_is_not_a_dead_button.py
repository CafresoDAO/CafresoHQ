#!/usr/bin/env python3
"""Every row in the 🔔 bell rendered as a real control and mostly wasn't one.

Reproduced live on the running office (port 9280): opened Notifications,
saw 51 entries — 49 "Coworkers", 2 "System" (two ⚠ night-shift failures).
Clicked a ⚠ row. Nothing happened: no navigation, no panel, no state
change of any kind.

Root cause is in `mergedNotifications` (app.jsx), the useMemo that builds
the bell's list from three sources — approvals, receipts, and the
activity log — before handing it to NotificationCenter
(ui/onboarding.jsx), which renders every row as:

    <div className="oc-notif-row" onClick={() => n.onClick && n.onClick(n)}
         role="button" tabIndex={0} ...>

and `.oc-notif-row:hover` gets a background change in the CSS — every
row, not just approvals, is dressed as something you can act on. Only the
approvals loop ever set `onClick`. Receipts and activity — everything
else, which on a real floor is almost the whole list, and specifically
every ⚠ attention item (a night-shift failure, a stuck task: the exact
thing a boss opens the bell FOR) — pushed a row with no `onClick` at
all. `n.onClick && n.onClick(n)` then silently no-ops. A control that
grants nothing.

The fix gives both of the other two sources a real destination:
receipts open the ReceiptsModal they already have (the bell and the tray
read the same receipt — this is just the second reader), and activity
rows call `openAttention()`, the exact function the "N need you" pill
already uses to open the Team inbox — which owns this same activity feed
with expand + Retry (views/core.jsx). No new destination invented; both
onClicks reuse doors this office already had.

Run: python3 scripts/test_a_notification_row_is_not_a_dead_button.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
ONBOARDING = (ROOT / 'ui/onboarding.jsx').read_text(encoding='utf-8')
CORE = (ROOT / 'views/core.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
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
    print('a notification row is not a dead button')
    code = strip_comments(APP)

    merged = brace_lift(code, 'const mergedNotifications = useMemoA(() => {')

    # ── 1. the render side really is a dead button without onClick ─────
    onb = strip_comments(ONBOARDING)
    check('NotificationCenter only fires a click that the row was given',
          re.search(r"onClick=\{\(\)\s*=>\s*n\.onClick\s*&&\s*n\.onClick\(n\)\}", onb)
          is not None,
          '— if this changed shape, a row with no onClick may no longer '
          'be silently inert, and this whole test is checking the wrong '
          'thing')
    check('...and every row is presented as one (role=button, tabIndex)',
          re.search(r'role="button"', onb) and re.search(r'tabIndex=\{0\}', onb),
          '— confirms the UI dresses every row as actionable, not just '
          'the ones that happen to have a handler')

    # ── 2. all three sources of mergedNotifications set onClick ─────────
    # Split the region into each source's own out.push({...}) block by its
    # leading `kind:` line, so a check against one source cannot pass by
    # matching text that actually belongs to a different one.
    def push_block(kind_literal):
        m = re.search(r"out\.push\(\{[^}]*?kind:\s*" + re.escape(kind_literal), merged)
        if not m:
            raise AssertionError('no out.push block found for kind ' + kind_literal)
        # from the push() opener, lift the matching close paren by brace/paren depth
        start = merged.rindex('out.push(', 0, m.end())
        depth = 0
        for k in range(start, len(merged)):
            c = merged[k]
            if c in '({':
                depth += 1
            elif c in ')}':
                depth -= 1
                if depth == 0:
                    return merged[start:k + 1]
        raise AssertionError('unbalanced push() lifting kind ' + kind_literal)

    approval_block = push_block("'approval'")
    check("approvals still jump to the composer on click (regression guard)",
          "onClick:" in approval_block and "goTo('visual')" in approval_block)

    # Receipts and activity both key `kind:` off a variable/ternary, not a
    # literal, so match by the surrounding comment/field markers instead.
    receipt_block_m = re.search(
        r"for \(const r of receipts\) \{.*?\n\s*\}\n", merged, re.S)
    check('receipts out.push block found', receipt_block_m is not None)
    receipt_block = receipt_block_m.group(0) if receipt_block_m else ''
    check('a receipt row now has an onClick',
          'onClick:' in receipt_block,
          '— this is the exact defect: receipts pushed a row with no '
          'onClick, so NotificationCenter\'s `n.onClick && n.onClick(n)` '
          'was always false for it')
    check('...and it opens the receipts tray this event already feeds',
          re.search(r"onClick:\s*\(\)\s*=>\s*\{[^}]*setReceiptsOpen\(true\)", receipt_block)
          is not None)

    activity_block_m = re.search(
        r"for \(const e of activity\) \{.*?\n\s*\}\n", merged, re.S)
    check('activity out.push block found', activity_block_m is not None)
    activity_block = activity_block_m.group(0) if activity_block_m else ''
    check('an activity row (including every ⚠ attention item) now has an onClick',
          'onClick:' in activity_block,
          '— this is the row that matters most: night-shift failures and '
          'stuck tasks render with the ⚠ icon from this exact loop, and '
          'this was the one a boss would click first')
    check('...and it opens the same door the "N need you" pill already uses',
          re.search(r"onClick:\s*\(\)\s*=>\s*\{[^}]*openAttention\(\)", activity_block)
          is not None,
          '— reusing openAttention means this can only be as broken as '
          'the pill already proven to work, not a second, independent '
          'path that could silently drift from it')

    # ── 3. openAttention genuinely goes somewhere, not another dead end ─
    oa = brace_lift(code, 'const openAttention = useCallbackA(() => {')
    check("openAttention navigates to the team view",
          re.search(r"navTo\('team'\)", oa) is not None)
    check("...and dispatches the event the Team inbox listens for",
          re.search(r"dispatchEvent\(new CustomEvent\('cafresohq:openAgentInbox'\)\)", oa)
          is not None)

    core = strip_comments(CORE)
    check("views/core.jsx actually listens for that event and opens the inbox",
          re.search(
              r"addEventListener\('cafresohq:openAgentInbox',\s*open\)", core)
          is not None
          and re.search(r"const open = \(\) => setShowInbox\(true\)", core) is not None,
          '— closes the loop end to end: bell click -> openAttention -> '
          'dispatch -> Team view actually opens the inbox panel, not just '
          'that app.jsx believes it did')

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
