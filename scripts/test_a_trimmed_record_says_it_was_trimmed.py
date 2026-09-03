#!/usr/bin/env python3
"""A bounded record has to say it is bounded, and keep the part worth keeping.

Reproduced 2026-08-16 on a scratch office (127.0.0.1:9269) seeded with 505
message records, the last of which logged 45 state transitions:

    modal subtitle : "1 thread · 500 messages total"        (505 on disk)
    disclosure     : "history (30 events)"                  (45 logged)
    first row      : "5:30 AM · created · Kip — event 16 of 45"

Three separate claims, all wrong, and the third is the worst of them:
`persistableMessages` kept the LAST thirty events, so a record opens on
whatever transition happened to survive — and because that row still
carries a state name, `created` at event 16 reads exactly like a beginning.
The comment under the function said "All transitions append to history so
we never lose the audit trail."

The trim is not the bug. A rolling cap on a browser-persisted registry is
the right call, and this suite does not ask for it to be removed. What was
wrong is that the office spent the boss's trust on it silently: nothing on
screen distinguished a trimmed record from a complete one, and the number
next to the word "total" was the size of what survived.

Worse than deferred — permanent. The cap is `useFileStored`'s READ
transform, so the truncated copy is what state holds; one click of
✓ CLEAR THIS wrote it back over hq-state/messages.json. Measured: 505 → 500
records and 45 → 30 events on disk, from one button press.

So this suite holds:

  1. the trim keeps the OPENING entry, not just the newest N
  2. it counts what it dropped, and the count accumulates across passes
     (h[0] survives every pass, so an earlier trim is not recountable)
  3. the registry cap carries its count forward on the oldest survivor
  4. every place the office shows one of those counts says what is missing

Checks 1-3 run the real functions, lifted out of app/storage.jsx and
executed in node, because the interesting part is arithmetic across
repeated passes and no amount of reading the source proves that.

§5 (a wrong door is worse than a locked one — a complete-looking trail is
a wrong door onto the office's own memory) and §7 (an honest sentence
still needs a way forward: these events are gone, so the way forward is
knowing which parts of the record can still be relied on).
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORAGE = (ROOT / 'app' / 'storage.jsx').read_text(encoding='utf-8')
COLLAB = (ROOT / 'modals' / 'collab.jsx').read_text(encoding='utf-8')

FAILS = []


def check(label, ok, detail=''):
    if ok:
        print(f'  ok    {label}')
    else:
        FAILS.append(label)
        print(f'  FAIL  {label}' + (f'  — {detail}' if detail else ''))


def strip_jsx_comments(src):
    """Comments carry the finding; they are not what the boss reads.

    Stripped before slicing, not after: this round's markup sits directly
    under a comment that uses every word the checks below look for
    ("dropped", "trimmed", "total"), so a check reading the raw slice would
    be satisfied by the note explaining the fix rather than by the fix.
    """
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'(?m)^\s*//.*$', '', src)
    return src


def section(src, start, end):
    """A slice between two markers, or '' if either is missing."""
    a = src.find(start)
    if a < 0:
        return ''
    b = src.find(end, a)
    return src[a:b] if b > a else ''


def component(src, name):
    """One top-level function body, located by NAME — never by its parameter
    list, the locator that turned an added prop into a test CRASH once
    already (see test_calendar_task_row_opens_the_right_card)."""
    m = re.search(r'^function %s\(' % re.escape(name), src, re.M)
    if not m:
        return ''
    j = src.find('\nfunction ', m.end())
    return src[m.start():] if j == -1 else src[m.start():j]


def jsx_attr(src, name):
    """The expression inside `name={…}`, brace-balanced — or '' if absent.

    Located by the attribute's NAME. The subtitle check below used to pin the
    first characters of the expression itself
    (``subtitle={`${visibleThreads.length}``), and #159 rewrote exactly those
    characters to stop the header mixing a filtered count with an unfiltered
    one. `section` then returned '' and BOTH checks failed — not because the
    trim disclosure had regressed, but because the locator had. That is the
    brittle-literal hazard this suite has been flagging for other files,
    landing here: a locator that pins prose or punctuation reports a rename as
    a regression, and (worse) an empty slice satisfies any check phrased as
    "X not in slice".
    """
    m = re.search(r'\b%s=\{' % re.escape(name), src)
    if not m:
        return ''
    depth, j = 0, m.end() - 1
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.end():j]
        j += 1
    return ''


COLLAB_CODE = strip_jsx_comments(COLLAB)

HARNESS = r"""
const mk = (n, tag) => Array.from({length: n}, (_, i) => ({
  id: 'm_' + (tag || '') + String(i).padStart(4, '0'),
  history: [{ at: 1, state: 'created', by: 'a', note: 'only' }],
}));
const hist = (n, tag) => Array.from({length: n}, (_, i) => ({
  at: i + 1, state: 'working', by: 'a', note: (tag || 'event ') + (i + 1),
}));

const R = {};

// ── pass one: 505 records, the last of them 45 events deep ────────────
const seeded = mk(504).concat([{ id: 'm_long', history: hist(45) }]);
const p1 = persistableMessages(seeded);
R.kept1 = p1.length;
R.oldest1 = p1[0].id;
R.dropped1 = p1[0].droppedBefore || 0;
const L1 = p1.find(m => m.id === 'm_long');
R.hist1 = L1.history.length;
R.histOpens1 = L1.history[0].note;
R.histDropped1 = L1.historyDropped || 0;

// ── pass two: the office keeps running on the already-trimmed copy ────
// Ten more records arrive and the long handoff logs ten more transitions.
// h[0] survived pass one, so what pass one took is no longer countable
// from the history array — the numbers have to have been carried.
const grown = p1.concat(mk(10, 'b'));
const gi = grown.findIndex(m => m.id === 'm_long');
grown[gi] = { ...grown[gi], history: grown[gi].history.concat(hist(10, 'later ')) };
const p2 = persistableMessages(grown);
R.kept2 = p2.length;
R.dropped2 = p2[0].droppedBefore || 0;
const L2 = p2.find(m => m.id === 'm_long');
R.hist2 = L2.history.length;
R.histOpens2 = L2.history[0].note;
R.histDropped2 = L2.historyDropped || 0;

// ── a registry under both caps is left exactly alone ──────────────────
const small = persistableMessages([
  { id: 'a', history: hist(3) },
  { id: 'b', history: hist(30) },
]);
R.smallKept = small.length;
R.smallUnmarked = small[0].droppedBefore === undefined;
R.smallHist = small[1].history.length;
R.smallHistUnmarked = small[1].historyDropped === undefined;
R.notArray = persistableMessages(null).length;

console.log(JSON.stringify(R));
"""


def main():
    print('a trimmed record says it was trimmed')

    # ── 1-3. the real functions, run ─────────────────────────────────────
    # Lifted whole. `persistableMessages` and its helper are pure and
    # import nothing, so what runs below is the shipped code and not a
    # Python restatement of what it is supposed to do.
    lifted = section(STORAGE, 'const MESSAGES_CAP',
                     '\n// Message states form a directed lifecycle.')
    check('the trim functions are liftable out of app/storage.jsx',
          bool(lifted) and 'persistableMessages' in lifted,
          '— the markers moved, or the cap went back to being one inline '
          'slice; every arithmetic check below reads this slice')

    if lifted and 'persistableMessages' in lifted:
        if not shutil.which('node'):
            print('  SKIP  node not on PATH — arithmetic checks not run')
        else:
            p = subprocess.run(['node', '--input-type=module', '-e', lifted + HARNESS],
                               cwd=ROOT, capture_output=True, text=True, timeout=60)
            if p.returncode != 0:
                print(p.stderr[-1500:], file=sys.stderr)
                check('the lifted trim functions run', False,
                      '— node could not execute them; see stderr')
                R = None
            else:
                R = json.loads(p.stdout.strip().split('\n')[-1])

            if R is not None:
                check('the record cap still holds', R['kept1'] == 500,
                      f"— kept {R['kept1']}")
                check('...and the oldest survivor carries what went before it',
                      R['dropped1'] == 5 and R['oldest1'] == 'm_0005',
                      f"— {R['oldest1']} carries {R['dropped1']}; 505 in, 500 kept, "
                      '5 dropped, and the array has nowhere else to put the number')

                check('a long history is still bounded', R['hist1'] == 30,
                      f"— kept {R['hist1']}")
                check('...and it opens where the record opened',
                      R['histOpens1'] == 'event 1',
                      f"— opens on {R['histOpens1']!r}; slice(-30) opened a "
                      "45-event record on 'created · event 16 of 45', which "
                      'reads as a beginning and is not one')
                check('...and says how many events it lost',
                      R['histDropped1'] == 15,
                      f"— reported {R['histDropped1']}, expected 15")

                # The pass-two numbers are the whole point of running this in
                # node. Recomputing instead of accumulating looks right on a
                # single pass and quietly resets the count on every reload.
                check('a second trim adds to the record count rather than replacing it',
                      R['kept2'] == 500 and R['dropped2'] == 15,
                      f"— {R['dropped2']} after dropping 10 more from a registry "
                      'that had already dropped 5; 500 kept + 15 dropped = 515 = '
                      'everything that was ever in it')
                check('...and to the history count',
                      R['hist2'] == 30 and R['histDropped2'] == 25,
                      f"— {R['hist2']} kept + {R['histDropped2']} dropped should be "
                      '55, the 45 seeded plus 10 more')
                check('...while the opening entry stays put',
                      R['histOpens2'] == 'event 1',
                      f"— opens on {R['histOpens2']!r} after two trims")

                check('a registry under both caps is untouched and unmarked',
                      R['smallKept'] == 2 and R['smallUnmarked']
                      and R['smallHist'] == 30 and R['smallHistUnmarked'],
                      '— a marker on a record that lost nothing is its own '
                      'wrong sentence')
                check('a non-array still yields an empty registry',
                      R['notArray'] == 0)

    # ── 4. the counts on screen ──────────────────────────────────────────
    # Bounded to the disclosure. `historyDropped` is read in three places in
    # this file, so a file-wide search answers yes with the summary reverted.
    details = section(COLLAB_CODE, '{m.history && m.history.length > 1 && (', '</details>')
    check('the history disclosure is findable', bool(details),
          '— the three checks below read it')
    check('the disclosure counts what the record HAD, not what survived',
          'm.history.length + m.historyDropped' in details,
          '— "history (30 events)" on a message that logged 45 is the trim '
          'reporting itself as the whole story')
    check('...and the list itself shows where the gap is',
          'm.historyDropped > 0' in details and 'dropped here' in details,
          '— the count is a footnote; the list reads top-down and the second '
          'line is where the missing middle actually is')
    check('...and names what can still be relied on',
          'most recent' in details and 'how it opened' in details,
          '— the events are gone for good, so the way forward is knowing '
          'which parts of the record are whole (§7)')
    check('the old unconditional count is gone',
          'history ({m.history.length} events)' not in COLLAB,
          '— that exact string was on screen over a 45-event record')

    # Scoped to the component, not the file: `subtitle={…}` appears on other
    # modals in here too, and the first brace-form one being the inbox's is a
    # fact about line order, not about the code.
    inbox = component(COLLAB_CODE, 'InboxModal')
    check('the InboxModal component is findable', bool(inbox),
          '— modals/collab.jsx: `function InboxModal(` is gone')
    subtitle = jsx_attr(inbox, 'subtitle')
    check('the inbox subtitle is findable', bool(subtitle),
          '— modals/collab.jsx has no `subtitle={…}` on the INBOX modal, so '
          'every check below it would pass against an empty string')
    # Counted, not merely found. The word has to appear ONCE, in the branch
    # taken when nothing was dropped — an arm that put " total" back into the
    # base string and left the conditional suffix hanging off the end read as
    # "500 messages total kept · 5 older dropped" and passed a check that only
    # asked whether the honest branch was still there.
    check('the subtitle stops saying "total" once records have been dropped',
          'droppedRecords' in subtitle and 'older dropped' in subtitle
          and "' total'" in subtitle and subtitle.count('total') == 1,
          f'— "500 messages total" with 505 on disk; the word doing the '
          f'damage is "total", it belongs only on the nothing-was-dropped '
          f'branch, and it appears {subtitle.count("total")} time(s) here')

    # Bounded to the top of the thread list. The '… N more threads' notice at
    # the bottom of the same list uses much the same words, and a check
    # reading the whole render passes on that one.
    listtop = section(COLLAB_CODE, "flexDirection:'column',gap:10}}>",
                      'visibleThreads.slice(0, 100)')
    check('the thread list says so above the list, not below it',
          'droppedRecords > 0' in listtop and 'rolled out' in listtop,
          '— the dropped records are the OLDEST and the list runs '
          'newest-first, so the top is where the boss stops scrolling and '
          'concludes they have seen everything')

    check('the source no longer promises a complete audit trail',
          'never lose the audit trail' not in STORAGE,
          '— that sentence sat four lines under the slice(-30) disproving it')

    print()
    if FAILS:
        print(f'FAILED {len(FAILS)} check(s):')
        for f in FAILS:
            print('  · ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
