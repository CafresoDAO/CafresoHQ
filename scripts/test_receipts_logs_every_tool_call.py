#!/usr/bin/env python3
"""The elevated-access banner promised a "full tool audit log." The code
disagreed with its own comment.

`ui/panels.jsx`'s InspectPanel, shown only when `agent.elevated`:

    🛡 FILE & SHELL ACCESS — backed by a CafresoHQ / Codex session with
    computer access. Every tool call is logged to Receipts.

`recordToolReceipt` in app.jsx — the only function that ever writes a
Receipts row for a tool call, called from all three tool-dispatch paths
in the file — used to open with:

    if (ev.failed) return;

before the elevated-agent branch a few lines below it ever ran, even
though THAT branch's own comment said:

    /* Elevated agents get a full tool audit log. ... */

So a failed shell command, a failed file write, any tool call that
errored — by an elevated coworker, mid ordinary chat, a DM handoff, or a
task — produced zero Receipts row. Not a red row, not a "failed" stamp:
nothing. The only place the failure surfaced was the coworker's own chat
bubble as a transient ⚠ card, which isn't Receipts and isn't searchable,
filterable, or persisted the way the audit trail is. A boss who trusted
the banner and later filtered Receipts by TOOL-EXECUTION to see what an
elevated coworker actually did on the machine would see every command
that worked and nothing about the ones that didn't.

This wasn't a copy bug like the DM-elevation ticket — the code's own
"full tool audit log" comment was already making the same claim the
banner made, one function scope apart, and the code beneath it broke the
promise both were making.

**The fix** narrows the failure exclusion to what it was actually
protecting — the DELIVERABLE side of a receipt (the corkboard pin, the
deliverable verb in the title, the on-chain anchor), where "Wrote
index.html" for a write that never landed really would be untrue. An
elevated agent's failed tool call now still gets a `tool-execution`
receipt, `decision: 'failed'`, titled `TOOL_NAME: arg — failed`. Every
other combination (non-elevated + failed, non-elevated + non-deliverable
success, elevated + success, any agent + successful deliverable) is
unchanged.

Run: python3 scripts/test_receipts_logs_every_tool_call.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
PANELS = (ROOT / 'ui/panels.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_arrow_fn(src, marker):
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
    print('Receipts: does "every tool call" really mean every tool call?')

    # ── 1. the banner's claim is still there — this ticket fixes the code
    #        to match it, not the other way around ────────────────────────
    check("the elevated-access banner still promises a full tool audit log "
          "(this ticket makes the code true to it, not the copy false to "
          "it)",
          'Every tool call is logged to Receipts' in PANELS, PANELS[:0])

    # ── 2. the fixed guard no longer excludes elevated + failed ─────────
    fn_src = extract_arrow_fn(APP, 'const recordToolReceipt = (agent, ev) => {')
    check("recordToolReceipt no longer has an unconditional `if (ev.failed) "
          "return;` ahead of the elevated-agent branch",
          not re.search(r'if \(ev\.failed\) return;', fn_src), fn_src[:200])
    check('the guard that remains is conditioned on elevation for the '
          'failed case specifically',
          'ev.failed ? !agent.elevated' in fn_src, fn_src[:300])
    check("a failed tool-execution row is titled with an honest ' — failed' "
          "suffix, not a bare deliverable verb",
          "' — failed'" in fn_src or '" — failed"' in fn_src, '')
    check("a failed receipt is stamped decision: 'failed', not 'executed'",
          "decision: ev.failed ? 'failed' : 'executed'" in fn_src, fn_src[:0])

    # ── 3. mechanism, run for real: every combination that matters ──────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the mechanism check needs it')
    else:
        js = r'''
function drive(agent, ev) {
  const receipts = [];
  const pins = [];
  const anchors = [];
  const HQ = { uid: (p) => p + '_x' };
  const onPin = (p) => pins.push(p);
  const anchorWorkReceipt = (a, e, id, title) => anchors.push({ id, title });
  const deliverableVerb = (name) => (
    name === 'VAULT_APPEND' ? 'Appended'
      : name === 'PUBLISH_SITE' ? 'Asked to publish'
      : String(name).indexOf('EXPORT_') === 0 ? 'Exported'
      : String(name).indexOf('GENERATE_') === 0 ? 'Generated'
      : 'Wrote'
  );
  const setReceipts = (fn) => { receipts.push(...fn([])); };
''' + '  ' + fn_src + r'''
  recordToolReceipt(agent, ev);
  return { receipts, pins, anchors };
}
const elevated = { name: 'Selvin', elevated: true };
const grunt = { name: 'Nova', elevated: false };
console.log(JSON.stringify({
  elevatedFailedShell: drive(elevated, { phase: 'done', name: 'BASH', arg: 'rm bad/path', failed: true }),
  gruntFailedShell: drive(grunt, { phase: 'done', name: 'BASH', arg: 'rm bad/path', failed: true }),
  elevatedFailedDeliverable: drive(elevated, { phase: 'done', name: 'VAULT_NEW', arg: 'notes.md', failed: true }),
  elevatedSuccessShell: drive(elevated, { phase: 'done', name: 'BASH', arg: 'ls', failed: false }),
  gruntSuccessDeliverable: drive(grunt, { phase: 'done', name: 'EXPORT_PDF', arg: 'out.pdf', failed: false }),
}));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            check('the mechanism harness runs', False, p.stderr.strip()[:600])
        else:
            out = json.loads(p.stdout)

            ef = out['elevatedFailedShell']
            check('an elevated coworker\'s FAILED, non-deliverable tool call '
                  'now gets exactly one Receipts row (used to get none)',
                  len(ef['receipts']) == 1, ef)
            if ef['receipts']:
                r = ef['receipts'][0]
                check('...kind tool-execution, decision failed, title says so',
                      r['kind'] == 'tool-execution' and r['decision'] == 'failed'
                      and 'failed' in r['title'].lower(), r)
            check('...and nothing was pinned to the corkboard or anchored '
                  'on-chain for a call that never produced anything real',
                  ef['pins'] == [] and ef['anchors'] == [], ef)

            gf = out['gruntFailedShell']
            check('a NON-elevated coworker\'s failed tool call still gets no '
                  'receipt at all — unchanged from before this fix',
                  gf['receipts'] == [], gf)

            efd = out['elevatedFailedDeliverable']
            check('an elevated coworker\'s FAILED deliverable-shaped call '
                  '(e.g. a VAULT_NEW that errored) is logged as a failed '
                  'tool-execution row, NOT as a deliverable — "Wrote '
                  'notes.md" would be untrue for a write that never landed',
                  len(efd['receipts']) == 1
                  and efd['receipts'][0]['kind'] == 'tool-execution'
                  and efd['receipts'][0]['decision'] == 'failed'
                  and efd['pins'] == [] and efd['anchors'] == [],
                  efd)

            es = out['elevatedSuccessShell']
            check('an elevated coworker\'s SUCCESSFUL tool call is unchanged: '
                  'one executed tool-execution row, no " — failed" suffix',
                  len(es['receipts']) == 1
                  and es['receipts'][0]['decision'] == 'executed'
                  and 'failed' not in es['receipts'][0]['title'].lower(),
                  es)

            gs = out['gruntSuccessDeliverable']
            check('a non-elevated coworker\'s successful deliverable is '
                  'unchanged: one executed deliverable row, pinned',
                  len(gs['receipts']) == 1
                  and gs['receipts'][0]['kind'] == 'deliverable'
                  and gs['receipts'][0]['decision'] == 'executed'
                  and len(gs['pins']) == 1,
                  gs)

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
