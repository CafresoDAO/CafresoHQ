#!/usr/bin/env python3
"""Hitting STOP mid-round left every not-yet-reached seat "typing" forever.

Both `StandupModal.start()` and `MeetingRoom.moderate()` seed a placeholder
row per participant UP FRONT, all with `streaming: true`, then process them
one at a time in a `for` loop. When the boss hits STOP mid-round:

  - StandupModal's catch block rewrote the CURRENTLY-streaming agent's row
    to `…(stopped)` and then did a bare `return` — every agent later in
    `participating` never had its loop iteration run, so nothing ever set
    its `streaming` back to false.
  - MeetingRoom's catch block did the same for its own seat, then `break`
    (not `return`) — but nothing after the loop resolved the seats still
    queued behind the one that stopped either.

`phase`/`streaming` (the run-level flag) correctly flips back to idle, so
the footer shows ▶ START / the input re-enables — but the leftover rows
for not-yet-reached coworkers keep rendering the three-dot "typing"
indicator with empty text, exactly as if they were still composing,
even though no request was ever sent to them and nothing is running.
Watched live: hire 3 coworkers, start a stand-up, stop it mid-way through
the second — the third's card bounces "typing" until the boss clicks
START again (which wipes `reports` from scratch) or closes the modal.
A boss reading the floor at that moment gets a false read of who's busy.

Fix: on the userStopped/stopped branch in each loop, resolve every row
still marked `streaming: true` (the ones the loop never reached) to
`streaming: false` with a `…(stopped)` label, the same label the row
that WAS mid-flight already got.

Run: python3 scripts/test_a_stopped_round_leaves_no_stuck_typing_bubble.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / 'features.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_slice(src, start_marker, end_marker):
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    return src[i:j]


def main():
    print('a stopped round leaves no stuck "typing" bubble behind')
    src = FEATURES.read_text(encoding='utf-8')

    # ── 1. StandupModal: the userStopped branch resolves EVERY streaming row ──
    standup = brace_slice(src, 'function StandupModal(', '\nfunction ReceiptTray(')
    m = re.search(r"if \(userStopped\) \{(.*?)\n\s*\}", standup, re.S)
    check('found the userStopped branch in StandupModal.start()', m is not None)
    stopbody = m.group(1) if m else ''
    check('it resolves every row still marked streaming (not just the one '
          'that was mid-flight) — this is the actual fix: without it, every '
          'not-yet-reached coworker keeps bouncing "typing" with no run left '
          'to finish them',
          bool(re.search(r"setReports\(prev => prev\.map\(r => r\.streaming", stopbody)),
          stopbody)
    check('...and it still calls setPhase(\'idle\') / clears abortRef, so the '
          'existing close/restart behavior is untouched',
          "setPhase('idle')" in stopbody and 'abortRef.current = null' in stopbody)

    # ── 2. MeetingRoom: an aborted round resolves every queued seat ──────────
    meeting = src[src.index('function MeetingRoom('):]
    meeting = meeting[:meeting.index('\nfunction ', 200)]
    m2 = re.search(r"if \(stopped\) break;\s*\n\s*\} finally \{.*?\n\s*\}\s*\n\s*\}\s*\n"
                   r"(\s*if \(controller\.signal\.aborted\) \{(.*?)\n\s*\})", meeting, re.S)
    check('found a post-loop aborted-cleanup block in MeetingRoom.moderate()',
          m2 is not None)
    cleanup = m2.group(2) if m2 else ''
    check('it resolves every message still marked streaming (the seats the '
          'for-loop never reached once `break` fired)',
          bool(re.search(r"setMsgs\(m => m\.map\(x => x\.streaming", cleanup)),
          cleanup)

    # ── 3. genuinely execute the extracted map callbacks ─────────────────────
    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted fix)',
          has_node, 'skipping the live-execution check')
    if has_node and m and m2:
        reports_map = re.search(r"setReports\(prev => prev\.map\((.*?)\)\);", stopbody, re.S)
        msgs_map = re.search(r"setMsgs\(m => m\.map\((.*?)\)\);", cleanup, re.S)
        check('extracted the StandupModal row-resolver callback', reports_map is not None)
        check('extracted the MeetingRoom row-resolver callback', msgs_map is not None)
        if reports_map and msgs_map:
            js = f"""
            const reportsMapFn = {reports_map.group(1)};
            const msgsMapFn = {msgs_map.group(1)};

            // Three-coworker stand-up: first finished, second was mid-flight
            // (already resolved by the catch block above this code), third
            // never reached.
            const reports = [
              {{ agentId: 'vera', streaming: false, text: 'Shipped the report.' }},
              {{ agentId: 'kip',  streaming: false, text: 'buf …(stopped)' }},
              {{ agentId: 'dana', streaming: true,  text: '' }},
            ];
            const afterStop = reports.map(reportsMapFn);

            const msgs = [
              {{ id: 'you',  streaming: undefined, text: 'go' }},
              {{ id: 'ph1',  streaming: false, text: 'said their bit' }},
              {{ id: 'ph2',  streaming: false, text: 'buf …(stopped)' }},
              {{ id: 'ph3',  streaming: true,  text: '' }},
              {{ id: 'ceo',  streaming: true,  text: '' }},
            ];
            const afterAbort = msgs.map(msgsMapFn);

            console.log(JSON.stringify({{ afterStop, afterAbort }}));
            """
            r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
            check('the extracted callbacks ran without a Node error',
                  r.returncode == 0, (r.stderr or '').strip()[-800:])
            if r.returncode == 0:
                out = json.loads(r.stdout.strip().splitlines()[-1])
                dana = next(r for r in out['afterStop'] if r['agentId'] == 'dana')
                check("Dana's never-reached row is resolved: streaming is now false",
                      dana['streaming'] is False, dana)
                check("...and her row is honestly labelled stopped, not left blank "
                      "as if she were still composing",
                      '…(stopped)' in dana['text'], dana)
                vera = next(r for r in out['afterStop'] if r['agentId'] == 'vera')
                check("a row that already finished is untouched by the cleanup",
                      vera['text'] == 'Shipped the report.' and vera['streaming'] is False,
                      vera)

                ph3 = next(x for x in out['afterAbort'] if x['id'] == 'ph3')
                ceo = next(x for x in out['afterAbort'] if x['id'] == 'ceo')
                check("MeetingRoom's never-reached seat is resolved: streaming false",
                      ph3['streaming'] is False, ph3)
                check("...labelled stopped, not left mid-typing",
                      '…(stopped)' in ph3['text'], ph3)
                check("the CEO placeholder (queued behind every seat) is resolved too",
                      ceo['streaming'] is False and '…(stopped)' in ceo['text'], ceo)
                you = next(x for x in out['afterAbort'] if x['id'] == 'you')
                check("a plain chat row with no `streaming` field is left alone "
                      "(the cleanup must only touch rows that were mid-round)",
                      you == {'id': 'you', 'streaming': None, 'text': 'go'} or you.get('text') == 'go',
                      you)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
