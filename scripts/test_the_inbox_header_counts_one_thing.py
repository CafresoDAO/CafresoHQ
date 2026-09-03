#!/usr/bin/env python3
"""The INBOX subtitle was two answers to two different questions, joined by
a middle dot and closed with a word that only belonged to one of them:

    `${visibleThreads.length} thread…  ·  ${all.length} message…` + ' total'

`visibleThreads` respects the state chip and the agent dropdown. `all` has
never respected either. Measured live on an office holding exactly one
message — the boss's "hello there" to the CEO, state `failed` — with the
panel on its default ACTIVE filter:

    0 THREADS · 1 MESSAGE TOTAL
    No messages match this filter.

Zero threads holding one message is not a state anything can be in. The chip
row directly underneath was right the whole time (ACTIVE 0 · FAILED 1 ·
ALL 1), which is what makes the header the odd one out.

The remedy already existed one level down, on each thread row: when a filter
is on, say how many messages in HERE matched ("3 here"). This is that
sentence for the whole panel.

Not a grep for the new copy. The subtitle expression, the thread grouping,
both filter predicates and the state table are all LIFTED from the shipped
sources and executed under Node — `MSG_STATES` from app/windows.jsx, because
that table is the authority on what "active" excludes and a hand-written
copy of it here would be the third one this file's own comments complain
about.

Run: python3 scripts/test_the_inbox_header_counts_one_thing.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLAB = ROOT / 'modals' / 'collab.jsx'
WINDOWS = ROOT / 'app' / 'windows.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def component(src, name):
    """One top-level function body, located by NAME — never by its parameter
    list, the locator that turned an added prop into a test CRASH once
    already (see test_calendar_task_row_opens_the_right_card)."""
    m = re.search(r'^function %s\(' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no top-level `function %s(` in modals/collab.jsx'
                         % name)
    j = src.find('\nfunction ', m.end())
    return src[m.start():] if j == -1 else src[m.start():j]


def balanced(src, start, opener='({[', closer=')}]'):
    """From `start`, return the slice ending at the depth-0 `;`. Parens,
    braces and brackets are all counted — these bodies hold object literals,
    arrow functions and array spreads."""
    depth = 0
    for j in range(start, len(src)):
        c = src[j]
        if c in opener:
            depth += 1
        elif c in closer:
            depth -= 1
        elif c == ';' and depth == 0:
            return src[start:j + 1]
    raise SystemExit('unterminated statement at offset %d' % start)


def lift(src, name, where):
    m = re.search(r'^[ \t]*(?:const|let) %s = ' % re.escape(name), src, re.M)
    if not m:
        raise SystemExit('no `const %s = ` in %s' % (name, where))
    return balanced(src, m.start())


def region(src, first, last, where):
    """A contiguous run of real statements, from the line declaring `first`
    through the end of the statement declaring `last`. Used for the thread
    grouping, which is a Map plus two loops and so cannot be lifted as one
    `const` — copying it here instead would make this file a second
    implementation of the thing it is supposed to be checking."""
    a = re.search(r'^[ \t]*(?:const|let) %s\b' % re.escape(first), src, re.M)
    b = re.search(r'^[ \t]*(?:const|let) %s = ' % re.escape(last), src, re.M)
    if not a or not b or b.start() < a.start():
        raise SystemExit('cannot bound %s…%s in %s' % (first, last, where))
    return src[a.start():b.start() + len(balanced(src, b.start()))]


def jsx_attr(src, name, where):
    """The expression inside `name={…}`, brace-balanced."""
    m = re.search(r'\b%s=\{' % re.escape(name), src)
    if not m:
        raise SystemExit('no `%s={` in %s' % (name, where))
    depth, j = 0, m.end() - 1
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.end():j]
        j += 1
    raise SystemExit('unterminated `%s={`' % name)


# One record maker. `updatedAt` matters only for thread ordering.
def msg(mid, thread, state, frm='You', to='CafresoHQ', **kw):
    d = dict(id=mid, threadId=thread, state=state, fromAgentName=frm,
             toAgentName=to, fromAgentId='boss', toAgentId='ceo',
             body='hi', createdAt=1, updatedAt=1)
    d.update(kw)
    return d


# (label, records, filterState, filterAgent, expected subtitle)
CASES = [
    ('the measured case: one failed message, panel on its default ACTIVE '
     'filter',
     [msg('m1', 't1', 'failed')], 'active', 'all',
     '0 threads · 0 of 1 message'),

    ('the same office with the chip the empty state points at',
     [msg('m1', 't1', 'failed')], 'failed', 'all',
     '1 thread · 1 of 1 message'),

    ('no filter at all — the sentence the old code got right, unchanged',
     [msg('m1', 't1', 'failed')], 'all', 'all',
     '1 thread · 1 message total'),

    ('the agent dropdown narrows it just as much as the chips do',
     [msg('m1', 't1', 'failed')], 'all', 'CafresoHQ',
     '1 thread · 1 of 1 message'),

    ('...and a coworker with nothing addressed to them',
     [msg('m1', 't1', 'failed')], 'all', 'Nova',
     '0 threads · 0 of 1 message'),

    ('a thread is listed when ANY message matches, but the count is of '
     'MESSAGES — so the two numbers can honestly disagree',
     [msg('m1', 't1', 'completed'), msg('m2', 't1', 'failed'),
      msg('m3', 't2', 'completed')], 'failed', 'all',
     '1 thread · 1 of 3 messages'),

    # The case that separates "how many threads" from "how many messages".
    # Everywhere else in this list the two happen to be equal, so a header
    # that counted THREADS and called them messages read correctly — caught
    # by fire-testing exactly that substitution, which passed the first
    # draft of this file clean. Two matches inside ONE thread is the only
    # shape that tells them apart.
    ('two matches inside one thread — the header says messages, not the '
     'threads holding them',
     [msg('m1', 't1', 'failed'), msg('m2', 't1', 'failed'),
      msg('m3', 't2', 'completed')], 'failed', 'all',
     '1 thread · 2 of 3 messages'),

    ('several threads, several matches',
     [msg('m1', 't1', 'queued'), msg('m2', 't2', 'queued'),
      msg('m3', 't3', 'completed')], 'active', 'all',
     '2 threads · 2 of 3 messages'),

    ('an empty registry says so without inventing a filter',
     [], 'all', 'all', '0 threads · 0 messages total'),

    ('the roll clause survives, unfiltered',
     [msg('m1', 't1', 'completed', droppedBefore=5)], 'all', 'all',
     '1 thread · 1 message kept · 5 older dropped'),

    ('...and filtered, where "kept" attaches to the whole-registry number '
     'the "of" clause already names',
     [msg('m1', 't1', 'completed', droppedBefore=5),
      msg('m2', 't2', 'failed')], 'failed', 'all',
     '1 thread · 1 of 2 messages kept · 5 older dropped'),
]


def main():
    print('The inbox header counts one thing')

    collab = COLLAB.read_text(encoding='utf-8')
    windows = WINDOWS.read_text(encoding='utf-8')
    inbox = component(collab, 'InboxModal')

    # --- §1: the real subtitle, driven ---------------------------------
    parts = [
        lift(windows, 'MSG_STATES', 'app/windows.jsx'),
        'const states = MSG_STATES;',
        region(inbox, 'byThread', 'visibleThreads', 'InboxModal'),
        lift(inbox, 'droppedRecords', 'InboxModal'),
        lift(inbox, 'matchingMessages', 'InboxModal'),
        lift(inbox, 'isFiltered', 'InboxModal'),
        lift(inbox, 'plural', 'InboxModal'),
        'return (' + jsx_attr(inbox, 'subtitle', 'InboxModal') + ');',
    ]
    harness = '\n'.join([
        'const OUT = [];',
        'for (const c of CASES) {',
        '  const [label, all, filterState, filterAgent] = c;',
        '  OUT.push([label, (() => {',
        '\n'.join('    ' + p for p in parts),
        '  })()]);',
        '}',
        'console.log(JSON.stringify(OUT));',
    ])
    harness = 'const CASES = %s;\n' % json.dumps(
        [[c[0], c[1], c[2], c[3]] for c in CASES]) + harness

    proc = subprocess.run(['node', '--input-type=module', '-e', harness],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr.strip()[:2000])
        raise SystemExit('the lifted subtitle did not run under node')
    got = json.loads(proc.stdout.strip().splitlines()[-1])

    for case, (_label, subtitle) in zip(CASES, got):
        check(case[0], subtitle == case[4],
              'header reads %r, expected %r' % (subtitle, case[4]))

    # --- §2: the rule, stated once -------------------------------------
    # Whatever the copy becomes, the two halves have to be answers to the
    # same question. A header claiming threads it is not showing messages
    # for is the defect; a header claiming messages it is not showing
    # threads for is the same defect mirrored.
    bad = [(c[0], s) for c, (_l, s) in zip(CASES, got)
           if re.match(r'^0 threads · [1-9]', s)]
    check('no reading of this header ever says "0 threads" beside a '
          'message count it is actually showing', not bad, bad)

    # And "total" is a claim about the whole registry. It may only appear
    # when the panel really is showing the whole registry.
    liars = [(c[0], s) for c, (_l, s) in zip(CASES, got)
             if 'total' in s and (c[2] != 'all' or c[3] != 'all')]
    check('the word "total" never appears while a filter is narrowing the '
          'view', not liars, liars)

    # --- §3: the premise ------------------------------------------------
    check('the empty state still sends the reader to the filter — which is '
          'the sentence the header has to agree with',
          'Try widening the state filter' in inbox,
          'modals/collab.jsx: the empty-state copy has changed')
    check('the per-thread "N here" badge this borrows its wording from is '
          'still there',
          re.search(r'\{hits\}\s*here', inbox) is not None,
          'modals/collab.jsx: the thread-row match count is gone — this '
          'header is now the only place that says what the filter let '
          'through')
    check('the state table is still read from app/windows.jsx rather than '
          'copied into the modal',
          "import { MSG_STATES } from '../app/windows.jsx';" in collab,
          'modals/collab.jsx: MSG_STATES is no longer imported')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
