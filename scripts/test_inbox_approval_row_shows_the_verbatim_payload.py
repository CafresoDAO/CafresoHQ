#!/usr/bin/env python3
"""The Coworker Inbox's approval row must show the verbatim payload it stamps
(views/core.jsx AgentInbox).

Bug: AgentInbox renders live approval rows — pinned on top of the "Needs
attention" tab, with working ✓ Approve / ✕ Reject buttons wired to the same
onApprove/onReject the ApprovalTray uses — but the row showed only `ap.title`
and `ap.kind`. `ap.title` is the REQUESTING agent's own summary of what it
wants to do; the consent contract in app/approvals.jsx (and the tray, and the
Receipts modal, and the external-approval bridge that added
`detail: formatToolInput(p.input)` for exactly this reason) all state the
same invariant: the gate exists to catch a claim that doesn't match the
action, so the action must be visible NEXT TO the claim or the boss is being
asked to rubber-stamp a description. From this inbox, `rm -rf /important`
titled "Harmless cleanup" was approvable with the command visible nowhere on
screen — the one surface in the app where the tray's honesty rule silently
didn't apply.

Fix: the inbox approval row now renders `ap.detail` in the same
<pre className="ap-detail"> box the ApprovalTray uses (red left rule for
elevated rows, neutral for the rest — same border-colour rule as the tray).

This lifts the REAL AgentInbox source out of views/core.jsx (brace-balanced
extraction, like test_workspace_terminal_key.py) and checks the structural
invariant directly: the approval-row map body must render ap.detail in an
ap-detail box, guarded so detail-less legacy cards still render, and the
Approve/Reject buttons must still be present (the row stays a live consent
surface — the point is to inform the stamp, not remove it).
Run: python3 scripts/test_inbox_approval_row_shows_the_verbatim_payload.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'core.jsx'

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
    print('AgentInbox — approval row renders the verbatim payload it stamps')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    body = extract_function(text, 'AgentInbox')
    check('AgentInbox extracted from views/core.jsx', body is not None)
    if body is None:
        print('\n1 failure(s)')
        return 1

    # The approval-row region: from the pendingApprovals.map render loop to
    # the empty-state check that follows it. If either anchor vanishes the
    # extraction broke (row moved/renamed) — hard fail, not a skip.
    m_start = body.find('pendingApprovals.map')
    m_end = body.find('filtered.length === 0')
    check('approval-row map region located', m_start != -1 and m_end > m_start,
          f'start={m_start} end={m_end}')
    if not (m_start != -1 and m_end > m_start):
        print('\nFAILED: %s' % FAILS)
        return 1
    row = body[m_start:m_end]

    # 1. The verbatim payload is rendered — ap.detail inside the row.
    check('row reads ap.detail', 'ap.detail' in row)

    # 2. …in the same ap-detail box the ApprovalTray uses, inside a <pre>
    #    (monospace, "this exact text", scrolls instead of pushing the stamp
    #    buttons away — styles.css .ap-detail).
    pre_re = re.compile(r'<pre\s+className="ap-detail"', re.S)
    check('payload box is <pre className="ap-detail">', bool(pre_re.search(row)))

    # 3. Guarded, so pre-fix cards with no detail (and hire proposals that
    #    never set one) still render a row instead of an empty box.
    check('detail render is conditional on ap.detail',
          bool(re.search(r'\{ap\.detail\s*&&', row)))

    # 4. Same border-colour rule as the tray: the red left rule is for
    #    elevated (command-about-to-run) rows only — non-elevated rows get
    #    the neutral border, keyed off ap.elevated.
    check('border colour keyed off ap.elevated like the tray',
          bool(re.search(r'ap\.elevated\s*\?\s*undefined\s*:', row)))

    # 5. The row is still a live consent surface — both stamps intact.
    check('Approve button still wired to onApprove',
          'onApprove(ap.id)' in row.replace(' ', ''))
    check('Reject button still wired to onReject',
          'onReject(ap.id)' in row.replace(' ', ''))

    print()
    print(('FAILED: %s' % FAILS) if FAILS
          else 'inbox approval payload: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
