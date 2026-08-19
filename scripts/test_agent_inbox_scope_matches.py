#!/usr/bin/env python3
"""AgentInbox's badges counted the whole office even while its own row list
was scoped to one coworker.

`views/core.jsx`'s AgentInbox has a per-agent filter: click a coworker's
chip and `filtered` (the list actually rendered) narrows to their events —
`if (selectedAgentId) xs = xs.filter(e => e.agentId === selectedAgentId)`.
Three other numbers on the same panel never got the same filter:

  - the header's "N events" count read raw `activity.length`
  - `attentionCount` (the "Needs attention · N" tab label) was computed
    from raw `activity`, while the `pendingApprovals` it was combined with
    WAS already scoped by `selectedAgentId` — two arguments to the same
    call disagreeing about whose inbox this is
  - `doneCount` (the "Done · N" tab label) read raw `activity.filter(...)`

Click Selvin's chip and the row list shows 2 events; the three badges
above it kept reporting the whole office's counts. A boss reads "Needs
attention · 6" over a filtered list of 2 with no way to tell which number
is lying — same shape of bug as the office pill/nav-badge ghost-count fix
app/attention.jsx already documents, just on the panel that fix never
touched.

Fixed with one `scopedActivity` memo — `activity` filtered by
`selectedAgentId`, computed once — that the header, `attentionCount`,
`doneCount`, AND `filtered` all read from, so the four numbers on this
panel cannot drift apart from each other again. The per-agent chip counts
(`counts`, building each chip's OWN badge) stay unscoped on purpose — that
map necessarily spans every agent regardless of which chip is selected.

Run: python3 scripts/test_agent_inbox_scope_matches.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = (ROOT / 'views' / 'core.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('AgentInbox: header/attention/done counts scoped like the row list')

    check('found AgentInbox in views/core.jsx',
          'function AgentInbox(' in CORE)

    check('a single scopedActivity memo filters activity by selectedAgentId',
          re.search(r"scopedActivity\s*=\s*React\.useMemo\(\s*\(\)\s*=>\s*"
                     r"selectedAgentId\s*\?\s*activity\.filter\(e\s*=>\s*e\.agentId\s*===\s*selectedAgentId\)\s*:\s*activity",
                     CORE) is not None)

    check('attentionCount is computed from scopedActivity, not raw '
          'activity — it was disagreeing with pendingApprovals (already '
          'scoped) about whose inbox this is',
          'attentionCountOf(scopedActivity, pendingApprovals, agents)' in CORE)

    check("doneCount ('Done · N' tab label) is computed from "
          'scopedActivity',
          re.search(r"doneCount\s*=\s*React\.useMemo\(\s*\(\)\s*=>\s*scopedActivity\.filter\(e\s*=>\s*e\.action\s*===\s*'done'\)\.length",
                     CORE) is not None)

    check('the header event count reads scopedActivity.length, not '
          'activity.length',
          '{scopedActivity.length} event' in CORE)

    check('the header no longer reads the unscoped activity.length',
          '{activity.length} event' not in CORE)

    check("filtered (the actual rendered row list) starts from "
          'scopedActivity — the source this fix unified everything else '
          'against',
          re.search(r"filtered\s*=\s*React\.useMemo\(\(\)\s*=>\s*\{\s*let xs = scopedActivity;",
                     CORE) is not None)

    check('filtered no longer re-derives its own separate selectedAgentId '
          'filter (that logic now lives once, in scopedActivity)',
          'if (selectedAgentId) xs = xs.filter(e => e.agentId === selectedAgentId);' not in CORE)

    check('the per-chip counts map still spans the WHOLE office (every '
          "chip needs its own agent's total, regardless of which chip is "
          'currently selected) — this fix must not have scoped it too',
          re.search(r"counts\s*=\s*React\.useMemo\(\(\)\s*=>\s*\{\s*const c = new Map\(\);\s*for \(const e of activity\)",
                     CORE) is not None)

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
