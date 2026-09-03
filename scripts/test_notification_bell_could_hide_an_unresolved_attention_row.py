#!/usr/bin/env python3
"""The bell could report "all caught up" while an unresolved attention row
still sat in the Team-nav badge / office "N need you" pill.

app/attention.jsx's `attentionCount` — the single source for that pill — has
always counted an attention-priority activity entry as needing the boss for
as long as its own `unread` flag stays true, and nothing but resolving it in
the Team inbox (views/core.jsx's AgentInbox, via `onMarkRead`) ever flips
that flag. `markNotifsSeen` (app.jsx) was written to match: it deliberately
SKIPS attention entries when it clears `activity`'s unread flag, precisely so
the pill doesn't go quiet just because the boss glanced at the bell — see
test_notification_click_marks_read.py, which pins that skip on the write
side.

`mergedNotifications` — the bell's OWN data source — never got the matching
carve-out on the READ side. Its per-row `unread` was one formula for every
activity-derived row regardless of priority:

    unread: e.unread && (e.ts || 0) > notifSeenAt

`notifSeenAt` is bumped by `markNotifsSeen`, and after the "click marks read"
fix that callback now fires from closing the panel, "Mark all read", AND
every receipt/activity row's own onClick — so any of those, on ANY row,
retroactively flips every attention row already in the feed to computed
"read" in the bell the moment its own ts falls behind the new watermark.
`e.unread` itself is untouched (attentionCount still sees it, correctly, as
unresolved) — only the bell's own badge count and each row's `is-unread`
styling go quiet. Worse: since `notifSeenAt` only ever increases, once it
passes that row's `ts` the bell can never show it unread again on its own —
the boss would have to already know to go resolve it in Team, which is
exactly the nudge the quiet bell just took away.

Net effect, reproduced below: log one attention-priority activity entry,
open-then-close the bell (or click any other row) so `markNotifsSeen` fires
— the bell's own notification for that entry now reads unread:false while
`attentionCountOf` (app/attention.jsx, the pill's actual source) still
counts it. Two surfaces fed by the same `activity` array disagree about
whether the same thing still needs the boss.

Fix: `mergedNotifications`'s activity loop now special-cases attention rows
to mirror `e.unread` directly, ignoring `notifSeenAt` — the same rule
`markNotifsSeen` already enforces on the flag itself, now honored on the
read side too. Routine/mission rows are untouched (this test pins that).

Regression test lifts the real `mergedNotifications` activity loop (same
extraction markers scripts/test_mission_notifications_reach_the_bell.py
already uses on this exact loop) and the real app/attention.jsx, runs both
under Node, and checks they agree.

Run: python3 scripts/test_notification_bell_could_hide_an_unresolved_attention_row.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
ATTENTION = ROOT / 'app' / 'attention.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract(text, start_marker, end_marker, from_idx=0):
    i = text.index(start_marker, from_idx)
    j = text.index(end_marker, i + len(start_marker))
    return text[i:j + len(end_marker)], j + len(end_marker)


def run_js(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the real files')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print("An unresolved attention row stays flagged in the bell, not just the pill")
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = APP.read_text(encoding='utf-8')
    attention_src = ATTENTION.read_text(encoding='utf-8')
    attention_src = '\n'.join(
        ln for ln in attention_src.split('\n')
        if not ln.startswith('import ') and not ln.startswith('export '))

    # Same extraction markers as test_mission_notifications_reach_the_bell.py —
    # this is the one place both tests reach into, so keep them aligned rather
    # than inventing a second way to find the same loop.
    merged_raw, _ = extract(app, 'for (const e of activity) {', '\n    }\n    return out.sort')
    merged = merged_raw[:merged_raw.rindex('\n    return out.sort')]
    check("extracted mergedNotifications's activity loop",
          "e.priority === 'attention' ? e.unread" in merged,
          'app.jsx shape changed — attention rows no longer special-cased on the read side')

    # A stale (long-past) notifSeenAt watermark, and one entry of each shape,
    # all logged before that watermark — the exact state after ANY row's
    # onClick (or Mark all read, or closing the panel) has called
    # markNotifsSeen() at least once since these were logged.
    cases = [
        # Unresolved attention row (e.unread still true — nobody has acted on
        # it in the Team inbox). This is the regression: it must stay unread
        # in the bell no matter how stale notifSeenAt is.
        {'id': 'attn-open', 'agentId': 'a1', 'agentName': 'Nova', 'action': 'failed',
         'priority': 'attention', 'unread': True, 'ts': 1000},
        # An attention row the boss ALREADY resolved via the Team inbox
        # (onMarkRead flipped e.unread to false). Must read as read — the
        # fix must not just hardcode attention rows to always show unread.
        {'id': 'attn-resolved', 'agentId': 'a1', 'agentName': 'Nova', 'action': 'failed',
         'priority': 'attention', 'unread': False, 'ts': 1000},
        # An ordinary routine row from the same window — unaffected by this
        # fix, still gated on notifSeenAt exactly as before.
        {'id': 'routine', 'agentId': 'a1', 'agentName': 'Nova', 'action': 'done',
         'priority': 'routine', 'unread': True, 'ts': 1000},
    ]
    harness = """
const activity = %s;
const notifClearedAt = 0, notifSeenAt = 5000;  // stale watermark, well past ts:1000
const setNotifOpen = () => {}, openAttention = () => {}, setReceiptsOpen = () => {}, markNotifsSeen = () => {};
const out = [];
%s
console.log(JSON.stringify(out.map(o => ({ id: o.id, unread: o.unread }))));
""" % (json.dumps(cases), merged)
    R = run_js(harness)
    got = {row['id']: row['unread'] for row in R}

    check('an unresolved attention row (e.unread still true) stays unread in '
          "the bell even though notifSeenAt is well past its ts — this is the "
          'regression: it used to flip to read the moment ANY row\'s click (or '
          "Mark all read, or closing the panel) bumped notifSeenAt",
          got.get('attn-open') is True, got)
    check('an attention row already resolved via the Team inbox (e.unread '
          'false) still reads as read in the bell — the fix mirrors e.unread, '
          "it doesn't just force every attention row unread",
          got.get('attn-resolved') is False, got)
    check('an ordinary routine row is unaffected — still gated on notifSeenAt '
          'exactly as before the fix',
          got.get('routine') is False, got)

    # Cross-check against the pill's actual source: with the fix, the bell's
    # unreadCount and the pill's attentionCount agree that 'attn-open' still
    # needs the boss. Runs the real app/attention.jsx, not a re-derivation.
    harness2 = """
%s
const activity = %s;
const bellUnreadIds = %s;
const pillCount = attentionCount(activity, []);
const bellCountsItUnread = bellUnreadIds.includes('attn-open');
console.log(JSON.stringify({ pillCount, bellCountsItUnread }));
""" % (attention_src, json.dumps([c for c in cases if c['unread']]),
       json.dumps([c['id'] for c in cases if c['unread'] and c['priority'] == 'attention']))
    R2 = run_js(harness2)
    check("the pill (app/attention.jsx's attentionCount) and the bell now agree "
          "'attn-open' still needs the boss — before the fix the bell alone had "
          'already stopped counting it',
          R2['pillCount'] == 1 and R2['bellCountsItUnread'] is True, R2)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
