#!/usr/bin/env python3
"""A pending rAF write must not outlive the "final, cleaned" write it races.

features.jsx has two local per-token rAF-throttle gates that predate — and
don't know about — the fix HQ.throttleTokens (the chat/task path's
equivalent) already needed: StandupModal's `makeReportGate` and MeetingRoom's
`makeRafGate`. Both schedule a `requestAnimationFrame` write of the latest
RAW streamed buffer, gated to at most once per paint. Both then, once
HQ.agentStream's promise resolves, run a synchronous "final, cleaned" write
using `HQ.visibleReply(buf, ...)` — believing (per their own comments) that
this write is authoritative.

It isn't, without one more step. The stream's LAST token still calls the
gate on its way out, which schedules one more pending rAF callback carrying
the stale RAW buffer. requestAnimationFrame fires on the next paint, which
is after the synchronous "final, cleaned" write already ran — so the pending
callback's raw text lands on top, last, and wins.

Watched live: a real end-of-day stand-up with a local Llama coworker
checked in with "TODAY: Saved first note to private memory folder using
[MEMORY_WRITE: decisions/auth.md]…[/MEMORY_WRITE]." — the exact machine
syntax `HQ.visibleReply()` exists to strip, sitting unstripped on a boss-
facing surface. Confirmed the string strips cleanly through stripBlocks's
regex in isolation (this isn't a stripping-logic bug), which leaves the
gate's own late write as the only explanation — and re-reading both gates
side by side with the chat path's `HQ.throttleTokens` (which already has a
`.cancel()` callers use before their own final write) confirmed the
missing half.

Fix: both gates now expose `.cancel()`, and every final-write call site
(success AND error/stop paths, in both StandupModal and MeetingRoom) calls
it immediately before writing. Static checks only — these are closures
inside component functions, not exported pure functions the node harness
used elsewhere in this suite could import.

Run: python3 scripts/test_report_gate_race.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'features.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('report gate race — StandupModal + MeetingRoom')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    src = SRC.read_text(encoding='utf-8')

    # ── StandupModal's makeReportGate ──────────────────────────────────────
    gate = re.search(r'const makeReportGate = \(agentId\) => \{[\s\S]*?\n    \};', src)
    check('makeReportGate exists', bool(gate))
    gate_body = gate.group(0) if gate else ''
    check('makeReportGate exposes .cancel()',
          'fn.cancel = ' in gate_body and 'cancelled' in gate_body,
          "features.jsx: the gate needs a way for the caller to invalidate "
          "a pending rAF write before it fires")
    check('the scheduled rAF callback itself checks the cancelled flag',
          bool(re.search(r'requestAnimationFrame\(\(\) => \{[^}]*if \(cancelled\) return;', gate_body)),
          'features.jsx: cancel() must actually stop the pending write, not '
          'just exist')

    standup_loop = src[src.find('for (const a of participating) {'):]
    standup_loop = standup_loop[:standup_loop.find('\n    setPhase(\'summarizing\')')]
    check("the stand-up's success path cancels the gate before its final write",
          bool(re.search(r'updateReport\.cancel\(\);\s*\n\s*const said = HQ\.visibleReply', standup_loop)),
          "features.jsx: without this, the stream's last token can schedule "
          "a pending rAF write that fires AFTER this cleaned write and "
          "clobbers it with the raw, unstripped buffer — reproduced live, "
          "a real MEMORY_WRITE marker survived onto a boss-facing stand-up "
          "report")
    check("the stand-up's error/stop path also cancels the gate",
          bool(re.search(r'\} catch \(err\) \{\s*\n\s*updateReport\.cancel\(\);', standup_loop)),
          'features.jsx: the same stale-pending-write race can clobber the '
          'error/stopped message too, not just the success path')

    # ── MeetingRoom's makeRafGate ───────────────────────────────────────────
    raf_gate = re.search(r'const makeRafGate = \(id\) => \{[\s\S]*?\n    \};', src)
    check('makeRafGate exists', bool(raf_gate))
    raf_body = raf_gate.group(0) if raf_gate else ''
    check('makeRafGate exposes .cancel()',
          'fn.cancel = ' in raf_body and 'cancelled' in raf_body,
          'features.jsx: same missing half as makeReportGate — see its checks')
    check('...and its scheduled callback checks the flag too',
          bool(re.search(r'requestAnimationFrame\(\(\) => \{[^}]*if \(cancelled\) return;', raf_body)),
          'features.jsx: cancel() must actually stop the pending write')

    meeting_loop = src[src.find('for (const ph of placeholders) {'):]
    meeting_loop = meeting_loop[:meeting_loop.find('\n    let buf = \'\';\n    if (!controller.signal.aborted)')]
    check("the meeting room's success path cancels the gate before its final write",
          bool(re.search(r"update\.cancel\(\);\s*\n\s*updateById\(ph\.id, \{ text: HQ\.visibleReply", meeting_loop)),
          'features.jsx: same race as the stand-up — a meeting turn\'s last '
          'token can schedule a pending write that clobbers the cleaned text')
    check("the meeting room's error/stop path also cancels the gate",
          bool(re.search(r'\} catch \(err\) \{\s*\n\s*update\.cancel\(\);', meeting_loop)),
          'features.jsx: the error/stopped message needs the same protection')

    print()
    if FAILS:
        print(f'report gate race: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('report gate race: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
