#!/usr/bin/env python3
"""■ STOP ALL claimed to pause every running night shift. It never did.

Three surfaces make the claim:

    title="Stop everyone mid-job and pause every running night shift"   (app.jsx, the button)
    label: 'Stop everyone + every night shift'                          (app/commands.jsx, palette)
    `...paused ${running} running mission${...}.`                       (app.jsx, onStopAll's own confirm/ticker)

`onStopAll`'s `running` count was `missions.filter(m => m.status ===
'running').length` — and `missions` is app.jsx's OWN state, which (per the
comment on `nightShiftBoard` a few lines above `onStopAll`, written for a
different ticket — the office floor's bulletin board) only ever holds
in-browser Research missions. Server-side Night Shift runs
(night_runner.py, "close the laptop, work continues") live in
`nightShiftBoard`, polled from `/missions/scheduled` + `/missions/runs`
specifically so surfaces above the Missions modal could see them —
`onStopAll` was never updated to look.

Two more copies of the identical gate compounded it: the button's own
visibility condition and the command palette's `anyBusy` both checked only
`agents` + `missions`, so if a night shift was the ONLY thing running
anywhere, the button that claims to stop it didn't even render.

**The fix.** `onStopAll` now folds `nightShiftBoard.length` into `running`
(confirm dialog, ticker text, and the "Nothing to stop" gate), and — the
part that actually stops anything — issues `DELETE
/missions/scheduled/<id>` for each board entry, the same call the Missions
modal's own ✕ CANCEL makes (serve.py's `_missions_delete`, which flags
`_night_abort` and `run_mission` picks up within 5s). The button's render
gate and the command palette's `anyBusy` both gained the same
`nightShiftBoard.length > 0` check so the control shows up when a night
shift is the only thing running.

Run: python3 scripts/test_stop_all_stops_the_night_shift_too.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
COMMANDS = (ROOT / 'app/commands.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_arrow_fn(src, marker):
    """Lift `const NAME = async () => { ... };` by brace-depth from the
    `{` right after `marker`, the same shape brace_lift covers for
    `function NAME(` — arrow-const declarations need their own opener
    since there's no `(` immediately preceding the body brace to confuse
    paren-depth tracking with."""
    i = src.index(marker)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('no closing brace found for ' + marker)


def main():
    print('STOP ALL: the night shift is included, not just claimed to be')

    stop_all_src = extract_arrow_fn(APP, 'const onStopAll = async () => {')

    # ── 1. the source ──────────────────────────────────────────────────
    check('onStopAll counts nightShiftBoard, not just the local missions state',
          'nightShiftBoard.length' in stop_all_src, stop_all_src[:200])
    check('...and actually asks serve.py to stop each one',
          re.search(r"fetch\([^)]*`/missions/scheduled/\$\{[^}]+\}`[^)]*method:\s*'DELETE'",
                     stop_all_src) is not None,
          'a count without a DELETE call would just make the CONFIRM '
          'dialog lie a second, different way — the same shape as the bug')
    check('...clears the board optimistically rather than waiting out the poll',
          'setNightShiftBoard([])' in stop_all_src, stop_all_src)
    check('...and the ticker/confirm text actually mentions night shifts '
          'when there are any (not just a bigger number with no explanation)',
          'nightRunning' in stop_all_src
          and stop_all_src.count('night shift') >= 2,
          stop_all_src)

    check('the STOP ALL button renders when a night shift is the only '
          'thing running',
          re.search(r"missions\.some\(m => m\.status === 'running'\)\s*\|\|\s*"
                     r"nightShiftBoard\.length > 0\)\s*&&\s*\(\s*\n\s*<Btn",
                     APP) is not None,
          'this is the second copy of the same gate — fixing onStopAll '
          'alone leaves the button invisible on a night-shift-only office')
    check('the command palette\'s anyBusy sees it too',
          re.search(r"anyBusy=\{[^}]*nightShiftBoard\.length > 0\}", APP) is not None,
          'a third copy of the identical gate, feeding app/commands.jsx')
    check('...and the palette command itself still reads that prop',
          "when: anyBusy" in COMMANDS, COMMANDS[:0])

    # ── 2. the mechanism, run for real: node, the actual extracted body ──
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the mechanism check needs it')
    else:
        # onStopAll closes over a lot of component state; stub every free
        # variable it touches and drive it as a real async function, the
        # same lifted-closure approach scripts/test_a_stop_stops_the_outbox_too.py
        # already uses for this exact handler's sibling, abortAllAgentRuns.
        js = r'''
async function run(scenario) {
  const deletedIds = [];
  const chat = [];
  let missionsState = scenario.missions || [];
  let nightBoard = scenario.nightShiftBoard || [];
  let confirmed = null;
  let saidNothing = false;

  const agentAbortersRef = { current: new Map(scenario.inflight ? scenario.inflight.map(id => [id, {}]) : []) };
  const abortAllAgentRuns = () => { agentAbortersRef.current.clear(); };
  const setAgents = () => {};
  const missions = missionsState;
  const setMissions = (fn) => { missionsState = fn(missionsState); };
  const nightShiftBoard = nightBoard;
  const setNightShiftBoard = (v) => { nightBoard = v; };
  const setChat = (fn) => { chat.push(...fn(chat).slice(chat.length)); };
  const HQ = { uid: (p) => p + '_x' };
  const say = (msg) => { saidNothing = msg === 'Nothing to stop'; };
  const CafresoHQClient = { backendBase: () => 'http://x' };
  global.fetch = (url, opts) => {
    if (opts && opts.method === 'DELETE') deletedIds.push(url);
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
  };
  global.window = { hqConfirm: async () => { confirmed = true; return true; } };
'''
        # extract_arrow_fn's slice runs `const onStopAll = async () => { ... }`
        # up to (and including) the body's own closing brace — no trailing
        # `;`. Swapping the `const NAME =` prefix for `await (` turns the
        # same brace-balanced text into an awaited, immediately-invoked
        # function expression; `)();` supplies the invocation this prefix
        # swap doesn't, closing the `await (` paren rather than reopening
        # a brace the extraction already closed.
        js += stop_all_src.replace('const onStopAll = async () => {', 'await (async () => {', 1)
        js += r'''
)();
  return { deletedIds, chat: chat.map(c => c.text), missionsState, nightBoard, confirmed, saidNothing };
}

(async () => {
  const out = {};
  out.stopsBoth = await run({
    inflight: ['a1'],
    missions: [{ id: 'm1', status: 'running' }],
    nightShiftBoard: [{ id: 'n1', status: 'running', topic: 't1' }, { id: 'n2', status: 'running', topic: 't2' }],
  });
  out.nightOnly = await run({
    inflight: [],
    missions: [],
    nightShiftBoard: [{ id: 'n1', status: 'running', topic: 't1' }],
  });
  out.nothingRunning = await run({ inflight: [], missions: [], nightShiftBoard: [] });
  console.log(JSON.stringify(out));
})();
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            check('the mechanism harness runs', False, p.stderr.strip()[:600])
        else:
            out = json.loads(p.stdout.strip().split('\n')[-1])

            both = out['stopsBoth']
            check('a mixed stop (1 local + 2 night shifts) DELETEs both night shifts',
                  sorted(both['deletedIds']) == ['http://x/missions/scheduled/n1',
                                                  'http://x/missions/scheduled/n2'],
                  both['deletedIds'])
            check('...clears the night-shift board locally',
                  both['nightBoard'] == [], both['nightBoard'])
            check('...pauses the local mission too (unrelated to this ticket, '
                  'but must still work)',
                  both['missionsState'][0]['status'] == 'paused', both['missionsState'])
            check('...and the ticker names the true combined count',
                  any('paused 3 missions' in n or 'paused 3 mission' in n for n in both['chat']),
                  both['chat'])
            check('...mentioning night shifts specifically, not just a bigger '
                  'number the boss has to take on faith',
                  any('night shift' in n for n in both['chat']), both['chat'])

            night_only = out['nightOnly']
            check('a night-shift-only office (nothing local busy) still stops '
                  'through this handler — the earlier bug would have hit the '
                  '"Nothing to stop" early-return here, since inflight=0 and '
                  'the old `running` counted only local missions',
                  night_only['deletedIds'] == ['http://x/missions/scheduled/n1']
                  and not night_only['saidNothing'],
                  night_only)

            nothing = out['nothingRunning']
            check('truly nothing running still says so and confirms nobody',
                  nothing['saidNothing'] and nothing['confirmed'] is None
                  and nothing['deletedIds'] == [],
                  nothing)

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
