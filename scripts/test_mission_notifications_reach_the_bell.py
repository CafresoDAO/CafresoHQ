#!/usr/bin/env python3
"""ui/onboarding.jsx declares a "🔬 Missions" notification filter
(NOTIF_FILTERS: `{ value: 'mission', label: 'Missions' }`, NOTIF_KIND_ICON:
`mission: '🔬'`) but nothing ever produced a `kind: 'mission'` row for the
bell to filter. app.jsx's `mergedNotifications` — the sole data source for
`<NotificationCenter>` — only ever assigned `kind: 'approval'`, `'receipt'`,
`'system'`, or `'agent'`; a mission finishing or hitting a snag left no
trace there at all. The filter chip's own render gate
(`if (f.value !== 'all' && count === 0) return null;`) means "Missions"
could never even appear, not just appear empty — a UI category that was
permanently, structurally dead.

Two earlier tickets in this document are close neighbors and were checked
before writing this fix, to make sure this isn't the same gap twice:

  - "Wire Research Missions into the ticker, Team inbox, and Receipts"
    (missions.jsx) wired a mission's individual TOOL CALLS (web/vault work
    mid-run) into logActivity/recordToolReceipt. It never touched a
    mission's own COMPLETION — the four `ctx.recordXp(...)` call sites
    below are a different event (the mission ending, not a step within
    it) and none of them called logActivity before this fix.
  - "Mission auto-pause (3 errors) never records a snag" and "Night Shift
    runs never reach the XP ledger" wired those same four completion
    events (plus the Night Shift poll's own outcome loop in app.jsx) into
    `recordXp` — the XP ledger — a completely separate feed from the
    activity log the bell reads. Recording XP for an event has never
    implied logging it as activity; nothing about those fixes could have
    populated the bell.

So: real mission completions were computing `outcome: 'done' | 'snag'`
correctly in five places (four in missions.jsx, one in app.jsx's Night
Shift poll) the whole time — recordXp already proves it — but none of
them ever called `logActivity`, the one function that actually feeds the
bell, the ticker, and the Team inbox.

**The fix** adds a `logActivity({..., action: 'mission', ...})` call
beside each of the five existing `recordXp` calls (same guard conditions,
so behavior is identical whenever recordXp already fired), and teaches
`mergedNotifications`'s activity loop to read `action === 'mission'` as
`kind: 'mission'` ahead of the old priority-based fallback (which still
applies unchanged to everything else). `ACT_ICON` (views/core.jsx) and
`INSPECT_ACT_ICON` (ui/panels.jsx) — the twin icon maps a prior ticket
("Stale activity-icon map (ACT_ICON) missing 4 kinds") explicitly noted
must be kept in step — both gained the same `mission: '🔬'` entry so a
mission row reads the same regardless of which panel shows it.

Run: python3 scripts/test_mission_notifications_reach_the_bell.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MISSIONS = ROOT / 'missions.jsx'
APP = ROOT / 'app.jsx'
CORE = ROOT / 'views' / 'core.jsx'
PANELS = ROOT / 'ui' / 'panels.jsx'
ONBOARDING = ROOT / 'ui' / 'onboarding.jsx'
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


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the real files')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print("A mission's own finish/snag now reaches the notification bell")
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    miss = MISSIONS.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    core = CORE.read_text(encoding='utf-8')
    panels = PANELS.read_text(encoding='utf-8')
    onboarding = ONBOARDING.read_text(encoding='utf-8')

    # ── 1. exactly one new call site per existing recordXp site ─────────
    xp_sites = [m.start() for m in re.finditer(r'ctx\.recordXp\(', miss)]
    log_sites = [m.start() for m in re.finditer(r'ctx\.logActivity\(', miss)]
    check('missions.jsx: 4 recordXp sites, unchanged',
          len(xp_sites) == 4, f'found {len(xp_sites)}')
    check('missions.jsx: exactly 4 new logActivity sites, one per recordXp site',
          len(log_sites) == 4,
          f'found {len(log_sites)} — every mission completion path (self-complete, '
          'deadline in the scheduling loop, deadline at fire time, auto-pause snag) '
          'needs its own logActivity call, or the bell only half-populates')

    # ── 2. self-complete path, driven for real ───────────────────────────
    self_complete, _ = extract(
        miss,
        '  if (completed && ctx.recordXp) {',
        '\n  }\n\n  return { ok: true, completed };')
    check('extracted the self-complete completion block',
          "ctx.logActivity" in self_complete, 'missions.jsx shape changed')

    for completed_val, label in [(True, 'completed'), (False, 'not completed')]:
        harness = """
const completed = %s;
const agent = { id: 'a1', name: 'Nova', color: '#7fd' };
const mission = { id: 'nm_1', topic: 'audit the ledger for stray tokens' };
let recorded = null, logged = null;
const ctx = { recordXp: (e) => { recorded = e; }, logActivity: (e) => { logged = e; } };
(function () { %s })();
console.log(JSON.stringify({ recorded, logged }));
""" % (json.dumps(completed_val), self_complete)
        R = run(harness)
        if completed_val:
            check('self-complete: logActivity fires with the mission tagged for the bell',
                  R['logged'] is not None
                  and R['logged'].get('action') == 'mission'
                  and R['logged'].get('agentId') == 'a1'
                  and 'audit the ledger' in R['logged'].get('text', ''),
                  R.get('logged'))
        else:
            check('self-complete: logActivity does NOT fire when the mission did not '
                  'actually complete (guard matches the pre-existing recordXp guard)',
                  R['logged'] is None, R.get('logged'))

    # ── 3. auto-pause snag path, driven for real ──────────────────────────
    autopause, _ = extract(miss, '      if ((m.errors || 0) >= 3) {', '\n        continue;\n      }')
    check('extracted the auto-pause block', 'ctx.logActivity' in autopause,
          'missions.jsx shape changed')
    harness = """
const m = { id: 'nm_2', agentId: 'a1', topic: 'watch the OCI gateway', errors: 3 };
let recorded = null, logged = null, paused = null, stoodDown = null;
const ctx = { recordXp: (e) => { recorded = e; }, logActivity: (e) => { logged = e; } };
const setMissions = (fn) => { paused = fn([m])[0]; };
const standDown = (id) => { stoodDown = id; };
const ctxWithSetters = { agentsRef: { current: [{ id: 'a1', name: 'Nova', color: '#7fd' }] } };
for (const _once of [0]) { %s }
console.log(JSON.stringify({ recorded, logged, paused, stoodDown }));
""" % autopause
    R = run(harness)
    check('auto-pause: logActivity fires, tagged mission + attention priority',
          R['logged'] is not None
          and R['logged'].get('action') == 'mission'
          and R['logged'].get('priority') == 'attention'
          and 'snag' in R['logged'].get('text', ''),
          R.get('logged'))
    check('...against the right mission and agent',
          R['logged'] and R['logged'].get('agentId') == 'a1', R.get('logged'))
    check('auto-pause: unchanged behavior (still pauses + stands down + records XP)',
          R['paused'] and R['paused'].get('status') == 'paused'
          and R['stoodDown'] == 'a1'
          and R['recorded'] and R['recorded'].get('outcome') == 'snag',
          {'paused': R.get('paused'), 'stoodDown': R.get('stoodDown'), 'recorded': R.get('recorded')})

    # ── 4. the two sibling deadline sites carry the same guard shape ─────
    sched_deadline, _ = extract(miss, 'const deadline = m.startedAt + m.durationMs;', '\n        continue;\n      }')
    check('scheduling-loop deadline site: logActivity guarded the same as recordXp '
          '(iterations > 0)',
          'if (m.iterations > 0 && ctx.logActivity)' in sched_deadline, sched_deadline)
    fire_deadline, _ = extract(
        miss,
        'if (Date.now() >= (latest.startedAt + latest.durationMs)) {',
        '\n            return;\n          }')
    check('fire-time deadline site: logActivity guarded the same as recordXp '
          '(iterations > 0)',
          'if (latest.iterations > 0 && ctx.logActivity)' in fire_deadline, fire_deadline)

    # ── 5. app.jsx's Night Shift poll — the fifth completion site ────────
    ns_loop, _ = extract(app, 'for (const r of (rj.runs || [])) {', '\n        }')
    check('extracted the Night Shift poll outcome loop', 'action: \'mission\'' in ns_loop,
          'app.jsx shape changed')
    for run_fixture, expect in [
        ({'id': 'r1', 'agentId': 'a1', 'topic': 'nightly sweep', 'finishedAt': 999,
          'errors': 0, 'iterations': 5}, 'done'),
        ({'id': 'r2', 'agentId': 'a1', 'topic': 'nightly sweep 2', 'finishedAt': 999,
          'errors': 2, 'iterations': 5}, 'snag'),
    ]:
        harness = """
const rj = { runs: [%s] };
const experienceRef = { current: [] };
const agentsRef = { current: [{ id: 'a1', name: 'Nova', color: '#7fd' }] };
let recorded = null, logged = null;
const recordXp = (e) => { recorded = e; };
const logActivity = (e) => { logged = e; };
%s
console.log(JSON.stringify({ recorded, logged }));
""" % (json.dumps(run_fixture), ns_loop)
        R = run(harness)
        check(f'Night Shift poll: {expect} run produces a correctly-tagged mission activity row',
              R['logged'] is not None
              and R['logged'].get('action') == 'mission'
              and R['logged'].get('agentId') == 'a1'
              and (R['logged'].get('priority') == 'attention') == (expect == 'snag'),
              R.get('logged'))

    # ── 6. mergedNotifications: action:'mission' wins the kind, unchanged
    #        behavior for everything else ─────────────────────────────────
    merged_raw, _ = extract(app, 'for (const e of activity) {', '\n    }\n    return out.sort')
    merged = merged_raw[:merged_raw.rindex('\n    return out.sort')]
    check("extracted mergedNotifications's activity loop",
          "e.action === 'mission' ? 'mission'" in merged, 'app.jsx shape changed')
    cases = [
        ({'id': '1', 'action': 'mission', 'priority': 'routine', 'text': 'x', 'agentName': 'Nova', 'ts': 100}, 'mission'),
        ({'id': '2', 'action': 'mission', 'priority': 'attention', 'text': 'x', 'agentName': 'Nova', 'ts': 100}, 'mission'),
        ({'id': '3', 'action': 'chat', 'priority': 'attention', 'text': 'x', 'agentName': 'Nova', 'ts': 100}, 'system'),
        ({'id': '4', 'action': 'done', 'priority': 'routine', 'text': 'x', 'agentName': 'Nova', 'ts': 100}, 'agent'),
    ]
    harness = """
const activity = %s;
const notifClearedAt = 0, notifSeenAt = 0;
const setNotifOpen = () => {}, openAttention = () => {};
const out = [];
%s
console.log(JSON.stringify(out.map(o => ({ id: o.id, kind: o.kind }))));
""" % (json.dumps([c[0] for c in cases]), merged)
    R = run(harness)
    got = {row['id']: row['kind'] for row in R}
    check('mergedNotifications kinds match expectations for all 4 cases '
          '(mission wins regardless of priority; non-mission rows unchanged)',
          all(got.get(c[0]['id']) == c[1] for c in cases),
          {'expected': {c[0]['id']: c[1] for c in cases}, 'got': got})

    # ── 7. the two icon maps stayed in sync (explicit lesson from a prior
    #        ticket: "kept in step ... adding to one and not the other") ──
    check("views/core.jsx's ACT_ICON gained the mission icon",
          "mission: '🔬'" in core, 'views/core.jsx ACT_ICON unchanged')
    check("ui/panels.jsx's INSPECT_ACT_ICON gained the same icon",
          "mission: '🔬'" in panels, 'ui/panels.jsx INSPECT_ACT_ICON unchanged')

    # ── 8. the consumer side (already correct) is untouched, not duplicated
    check("ui/onboarding.jsx's NOTIF_FILTERS still declares the Missions chip once",
          len(re.findall(r"\{\s*value:\s*'mission',\s*label:\s*'Missions'\s*\}", onboarding)) == 1, '')
    check("...and NOTIF_KIND_ICON still maps it to 🔬, unchanged by this fix",
          re.search(r"mission:\s*'🔬'", onboarding) is not None, '')

    print()
    if FAILS:
        print(f'mission notifications: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('mission notifications: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
