#!/usr/bin/env python3
"""The 📥 on a roster card is titled "Show what this coworker has been doing".
It opened the Coworker Inbox on whichever tab the panel was last left on —
in practice "Needs attention", the default.

Measured live on a real office (Llama, 14 events, 3 completed): clicking it
produced a panel whose header read **14 EVENTS**, whose Done tab read **· 3**,
and whose only sentence read **"Nothing needs you right now. 🎉"** over an
empty list. Three numbers on screen and the one the boss actually reads said
their coworker had done nothing. Same defect class as the roster card's
"Model" tooltip and the task board's "Nothing waiting": a surface answers a
question it was not asked, and the answer is false about the thing the boss
came to look at.

Fix, one file (views/core.jsx):
  - AgentInbox takes a `focusRequest` nonce. The roster card's 📥 bumps it;
    the PANEL decides which tab that click should land on, because the panel
    is the only place that knows what each tab would contain.
  - `attentionGroups` is hoisted out of `filtered` so the focus effect and
    the list read ONE rule. Deliberately not `attentionCount`, which counts
    only UNREAD items — an already-opened failure still sits in the list, and
    routing from the badge would have sent the boss past a visible row.
  - The attention tab's empty state stops dead-ending: when there IS activity
    one tab over, it offers the door instead of leaving the boss to find it.

Run: python3 scripts/test_the_inbox_button_answers_its_own_question.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
ATTENTION = ROOT / 'app' / 'attention.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift(src, name):
    """One indented `const <name> = ...;` from inside a component body.

    Braces, parens AND brackets are all counted: these bodies carry arrow
    functions, object literals and a `React.useMemo(fn, [deps])` whose deps
    array would close a brace-only scan early.
    """
    m = re.search(r'^[ \t]*const %s = ' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no `const %s = ` in views/core.jsx' % name)
    depth = 0
    for j in range(m.start(), len(src)):
        c = src[j]
        if c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[m.start():j + 1]
    raise SystemExit('unterminated `const %s`' % name)


def component(src, name):
    """One top-level component's body, located by NAME.

    Everything below lifts from inside AgentInbox, not from the file: three
    other components in views/core.jsx declare a `filtered`, and the first
    cut of this test happily lifted TasksView's and asserted things about the
    wrong rule.
    """
    m = re.search(r'^function %s\(' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no top-level `function %s(` in views/core.jsx' % name)
    j = src.find('\nfunction ', m.end())
    return src[m.start():] if j == -1 else src[m.start():j]


def lift_focus_effect(src):
    """The focus effect, located by the guard it opens with rather than by
    its whole text — a locator has to survive the edits the code it locates
    is expected to receive."""
    m = re.search(r'^[ \t]*React\.useEffect\(\(\) => \{\s*\n'
                  r'[ \t]*if \(!focusRequest\) return;', src, re.M)
    if not m:
        raise SystemExit('no focusRequest effect in views/core.jsx')
    end = src.find('}, [focusRequest]);', m.start())
    if end == -1:
        raise SystemExit('focusRequest effect is not keyed on [focusRequest]')
    return src[m.start():end + len('}, [focusRequest]);')]


# Every case is (label, selected agent, activity, approvals, expected tab).
# `agents` is the roster below; an entry for anyone NOT on it is a ghost and
# onRoster drops it, which the attention rule depends on.
AGENTS = [{'id': 'a1', 'name': 'Llama'}, {'id': 'a2', 'name': 'Codex'}]

CASES = [
    ('never worked — nothing to show, so show the empty log, not a 🎉',
     'a2', [], [], 'all'),
    ('the measured case: 14 routine events, none of them need the boss',
     'a1', [{'agentId': 'a1', 'priority': 'routine', 'text': 'filed x'}] * 14,
     [], 'all'),
    ('one failure of theirs — that is what the boss came for',
     'a1', [{'agentId': 'a1', 'priority': 'attention', 'text': 'failed x'},
            {'agentId': 'a1', 'priority': 'routine', 'text': 'filed x'}],
     [], 'attention'),
    ('a failure they have already READ still routes to attention — it is '
     'still in the list, and the badge (unread-only) would have missed it',
     'a1', [{'agentId': 'a1', 'priority': 'attention', 'unread': False,
             'text': 'failed x'}], [], 'attention'),
    ('somebody ELSE is stuck — not this coworker, so not this tab',
     'a1', [{'agentId': 'a2', 'priority': 'attention', 'text': 'failed y'},
            {'agentId': 'a1', 'priority': 'routine', 'text': 'filed x'}],
     [], 'all'),
    ('a pending approval of theirs counts even with no attention activity',
     'a1', [{'agentId': 'a1', 'priority': 'routine', 'text': 'filed x'}],
     [{'id': 'p1', 'agentId': 'a1'}], 'attention'),
    ('an approval waiting on someone else does not hijack their tab',
     'a1', [{'agentId': 'a1', 'priority': 'routine', 'text': 'filed x'}],
     [{'id': 'p1', 'agentId': 'a2'}], 'all'),
    ('a ghost employee\'s failure is nobody\'s problem any more',
     'a9', [{'agentId': 'a9', 'priority': 'attention', 'text': 'failed z'}],
     [], 'all'),
]


def main():
    print("The roster card's 📥 opens the tab that answers its own tooltip")

    core = CORE.read_text(encoding='utf-8')
    inbox = component(core, 'AgentInbox')
    attention_src = ATTENTION.read_text(encoding='utf-8')
    # app/attention.jsx is import-free by design (see its header) and runs
    # verbatim under node once its ES export line is dropped.
    attention_src = re.sub(r'^export \{[^}]*\};\s*$', '', attention_src, flags=re.M)

    # --- §1: the real rule, driven ------------------------------------
    harness = '\n'.join([
        attention_src,
        'const React = { useMemo: (fn) => fn() , useEffect: (fn) => fn() };',
        'const OUT = [];',
        'for (const c of CASES) {',
        '  const [label, selectedAgentId, activity, approvals] = c;',
        '  const agents = AGENTS;',
        '  const focusRequest = 1;',
        '  let tab = "attention";',
        '  const setTab = (t) => { tab = t; };',
        '  ' + lift(inbox, 'pendingApprovals'),
        '  ' + lift(inbox, 'scopedActivity'),
        '  ' + lift(inbox, 'attentionGroups'),
        '  ' + lift_focus_effect(inbox),
        '  OUT.push([label, tab, scopedActivity.length]);',
        '}',
        'console.log(JSON.stringify(OUT));',
    ])
    harness = ('const AGENTS = %s;\nconst CASES = %s;\n' % (
        json.dumps(AGENTS),
        json.dumps([[c[0], c[1], c[2], c[3]] for c in CASES]))) + harness

    proc = subprocess.run(['node', '--input-type=module', '-e', harness],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr.strip()[:2000])
        raise SystemExit('the lifted rule did not run under node')
    got = json.loads(proc.stdout.strip().splitlines()[-1])

    for (label, _sel, _act, _ap, want), (glabel, tab, _n) in zip(CASES, got):
        check(label, tab == want, 'landed on %r, expected %r' % (tab, want))

    # --- §2: the click and the wiring ---------------------------------
    check('the roster card\'s 📥 bumps the focus nonce',
          re.search(r'className="px-btn ghost team-inbox-btn"', core) is not None
          and 'setInboxFocus(n => n + 1)' in core,
          'views/core.jsx: the 📥 button no longer requests a focus')
    check('TeamView passes the nonce down to the panel',
          'focusRequest={inboxFocus}' in core,
          'views/core.jsx: focusRequest not threaded into AgentInbox')
    check('AgentInbox accepts focusRequest with a default',
          'focusRequest = 0' in core.splitlines()[
              next(i for i, l in enumerate(core.splitlines())
                   if l.startswith('function AgentInbox('))],
          'views/core.jsx: AgentInbox signature')

    # --- §3: ONE rule, two readers ------------------------------------
    # The whole point of hoisting attentionGroups. If `filtered` goes back to
    # deriving the attention list itself, the tab the button picks and the
    # list it lands on can disagree — which is the bug, wearing a new hat.
    filtered = lift(inbox, 'filtered')
    check('the attention LIST reads the same attentionGroups the focus '
          'effect asks about — not a second copy of the rule',
          "if (tab === 'attention') return attentionGroups;" in filtered
          and 'groupAttention(' not in filtered,
          filtered)
    check('...and declares it as a dependency',
          'attentionGroups' in filtered.split('}, [')[-1], filtered)

    # --- §4: the empty state stops dead-ending ------------------------
    check('the attention empty state offers the door to the activity that '
          'exists, and only when there is some',
          "tab === 'attention' && scopedActivity.length > 0" in core
          and 'oc-inbox-see-all' in core
          and "onClick={() => setTab('all')}" in core,
          'views/core.jsx: the see-all route is gone')
    check('it counts the events it is offering, not a hardcoded word',
          '{scopedActivity.length} thing' in core,
          'views/core.jsx: see-all label no longer reports the real count')

    # --- §5: the premise -----------------------------------------------
    # If the button ever stops claiming this, the fix above is answering a
    # question nobody asked any more.
    check('the 📥 still promises "what this coworker has been doing"',
          'title="Show what this coworker has been doing"' in core,
          'views/core.jsx: the tooltip this whole fix serves changed')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
