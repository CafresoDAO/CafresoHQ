#!/usr/bin/env python3
"""The record says "retryable — Re-send it" and no door in the product can.

Measured 2026-08-15 on office 9261. The STOP ALL work files a waiting
note's record 'cancelled' with failureCause kind 'stopped-all',
retryable true, actionNeeded "Re-send it if the question still needs an
answer." The Inbox modal renders exactly that sentence on the row — and
the row had zero buttons (driven live: rowButtons == []). The palette's
"Retry the most recent failed message" counts state === 'failed' only,
so a cancelled record is invisible to it (and even for failures it
retries the newest, not the one the boss is looking at); the modal's
only lever, ✓ CLEAR THIS, renders on NON-terminal rows; and a stopped
run logs action 'progress', so the attention tab never gets a Retry row
for it. The office named a door it didn't have — the same class as the
publish path that said "impossible" and named no door.

The fix makes the label pressable and keeps one implementation:
resendMessage(m) in app.jsx owns the one-live-child guard (an impatient
second click must not file a second dispatch), the recipient-gone
toast, the confirm door and the fresh dispatch chained via
parentMessageId; the palette's onRetryFailed delegates to it; the Inbox
row gets ↻ RE-SEND gated EXACTLY as the label is — terminal state,
failureCause present, retryable true.

Run: python3 scripts/test_a_retryable_record_has_a_door.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

# The signature gained an options bag when the attention tab's retry was
# folded in (#103): the door is conditional, everything else is shared.
DECL = 'const resendMessage = async (m, { confirm = true } = {}) => {'
GUARD = 'const already = all.find(x => x.parentId === m.id &&'
# #103 made the door conditional (a named row that carries its own button
# skips it) — but it is still ONE door, in this function, opt-out only.
# Shape, not spelling. This was the literal `if (confirm && !(await
# window.hqConfirm(` — the door exactly as written the day it was added —
# so the first correct WIDENING of the condition failed it (2026-08-16: a
# record trimmed before filing forces the door open even for the row
# button, whose skip is earned by "you are looking at what you are
# re-sending" and which a trim makes false). The claim is "there is one
# door here and the confirm opt is part of what opens it"; the rest of the
# boolean is the caller's business, and a check that owns it stops the
# next honest clause from being added.
CONFIRM = re.compile(r'if \((.+?)&& !\(await window\.hqConfirm\(')
CHAIN = 'parentMessageId: m.id,'
PROP = 'onResend={resendMessage}'
SIG = 'onResend = null'
GATE = 'onResend && TERMINAL_STATES.has(m.state) && m.failureCause && m.failureCause.retryable'
BUTTON = '↻ RE-SEND'
CLEAR_GATE = '!TERMINAL_STATES.has(m.state)'
# Shape, not spelling — the same lesson as the confirm door above, and the
# fourth time in this run of tickets that a sibling suite pinned today's
# wording instead of the claim. This was the literal `new Set(['completed',
# 'cancelled', 'failed'])`, the set exactly as written the day it was added,
# so deriving it from the one table that decides terminality (2026-08-16,
# #119 — the chip list turned out to be a state behind and this set was the
# other hand-written copy) read as the set going missing.
#
# What this suite actually needs is that the two gates below consult a set
# that really does hold 'cancelled': a stopped-all cancellation carrying a
# retryable cause is the row that went doorless in the first place. So the
# declaration is LIFTED and evaluated against the real MSG_STATES table
# rather than restated here. Where the answer comes from is #119's business.
TERM_DECL = re.compile(r'^const TERMINAL_STATES = new Set\((?:.|\n)*?\);', re.M)
MSG_STATES_HEAD = 'const MSG_STATES = {'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'\{/\*.*?\*/\}', '', src, flags=re.S)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('a retryable record has a door')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    collab = (ROOT / 'modals' / 'collab.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)
    cbare = strip_comments(collab)

    # ── one implementation, both surfaces ───────────────────────────────
    check('resendMessage exists once', bare.count(DECL) == 1,
          f'{bare.count(DECL)} sites')
    # Was two — the attention tab kept its own dispatch until #103 folded it
    # in. One retry, one dispatch site: that is the whole point of the shared
    # function, and a second site reappearing is how the guard drifts again.
    check('exactly one dispatch site chains a retry (resendMessage)',
          bare.count(CHAIN) == 1,
          f'{bare.count(CHAIN)} — the palette and the attention tab both kept private copies once')
    rf_at = bare.find('onRetryFailed={async () => {')
    rf_end = bare.find('}}', rf_at)
    rf = bare[rf_at:rf_end] if rf_at != -1 and rf_end > rf_at else ''
    check("the palette's retry delegates", 'resendMessage(failed[0])' in rf)
    check('…and keeps no private door or dispatch',
          'dispatchToAgent(' not in rf and 'hqConfirm' not in rf,
          'a second spelling of the confirm/dispatch is how the copies drift')

    rm_at = bare.find(DECL)
    rm_end = bare.find('`Retrying → ${agent.name}…`', rm_at)
    rm = bare[rm_at:rm_end] if rm_at != -1 and rm_end > rm_at else ''
    check('resend guards against a second live child', GUARD in rm,
          'the impatient second click must not file a second dispatch')
    check("…skipping only children that DIDN'T go through",
          "x.state !== 'failed' && x.state !== 'cancelled'" in rm)
    door = CONFIRM.search(rm)
    check('resend keeps the confirm door',
          bool(door) and 'confirm' in door.group(1),
          door.group(1) if door else 'no gated hqConfirm in resendMessage')
    check('resend chains the fresh record to the old one', CHAIN in rm)
    check("resend maps the sender: boss → null, peer → their agent",
          "(m.fromAgentId !== 'boss')" in rm)
    check('the Inbox is handed the door', bare.count(PROP) == 1,
          f'{bare.count(PROP)} prop sites')

    # ── the row's button, gated exactly as its label ────────────────────
    check('InboxModal declares the prop', SIG in cbare)
    termdecl = TERM_DECL.search(cbare)
    check('the terminal-state set is declared once', bool(termdecl)
          and cbare.count('const TERMINAL_STATES') == 1,
          'the gates below have nothing to consult')
    check('the button gate matches the label', cbare.count(GATE) == 1,
          f'{cbare.count(GATE)} gates')
    check('the button exists once', cbare.count(BUTTON) == 1,
          f'{cbare.count(BUTTON)} buttons')
    gate_at = cbare.find(GATE)
    btn_at = cbare.find(BUTTON)
    cause_at = cbare.find('m.failureCause.retryable ? ')
    clear_at = cbare.find(CLEAR_GATE)
    check('cause box → re-send door → clear-this, in that order',
          -1 < cause_at < gate_at < btn_at < clear_at,
          (cause_at, gate_at, btn_at, clear_at))
    btn_block = cbare[gate_at:clear_at] if -1 < gate_at < clear_at else ''
    check('the click stays on the row (stopPropagation) and calls the door',
          'e.stopPropagation();' in btn_block and 'onResend(m);' in btn_block)
    check('CLEAR THIS still renders only on non-terminal rows',
          cbare.count(CLEAR_GATE) == 1)

    # ── drive the lifted pieces ─────────────────────────────────────────
    rm_close = bare.find('};', rm_end)
    rm_full = bare[rm_at:rm_close + 2] if -1 < rm_end < rm_close else ''
    check('resendMessage lifts', rm_full.startswith(DECL) and rm_full.endswith('};'))
    check('the gate lifts', gate_at != -1)

    # The set the gate consults, taken from the source rather than restated
    # — a stub here would keep passing after the shipped set lost a state.
    windows = (ROOT / 'app' / 'windows.jsx').read_text(encoding='utf-8')
    states_src = re.search(r'^const MSG_STATES = \{.*?^\};', windows,
                           re.M | re.S)
    check('the state table lifts', bool(states_src))

    js = ('const RESEND_SRC = ' + json.dumps(rm_full) + ';\n'
          'const GATE_SRC = ' + json.dumps(GATE) + ';\n'
          'const STATES_SRC = ' + json.dumps(states_src.group(0) if states_src else '') + ';\n'
          'const TERM_SRC = ' + json.dumps(termdecl.group(0) if termdecl else '') + ';\n'
          + r'''
async function drive(scenario) {
  const calls = { warns: [], errors: [], oks: [], confirms: [], dispatches: [] };
  const kip = { id: 'a_k', name: 'Kip' };
  const vera = { id: 'a_v', name: 'Vera' };
  const agents = scenario === 'recipientGone' ? [kip] : [kip, vera];
  const children = {
    liveChild: [{ parentId: 'msg_1', state: 'in_progress' }],
    doneChild: [{ parentId: 'msg_1', state: 'completed' }],
    failedChild: [{ parentId: 'msg_1', state: 'failed' }],
  }[scenario] || [];
  const messagesRef = { current: children };
  const window = {
    cafresohqToast: { warn: (s) => calls.warns.push(s), error: (s) => calls.errors.push(s),
                      success: (s) => calls.oks.push(s) },
    hqConfirm: async (msg) => { calls.confirms.push(msg); return scenario !== 'declined'; },
  };
  const dispatchToAgent = (agent, body, opts) => calls.dispatches.push({ to: agent.name, body, opts });
  const m = { id: 'msg_1', toAgentId: 'a_v', toAgentName: 'Vera', body: 'the ask',
              fromAgentId: scenario === 'peerOrigin' ? 'a_k' : 'boss', fromAgentName: 'You' };
  const fn = new Function('messagesRef', 'agents', 'window', 'dispatchToAgent',
    'return (async () => { ' + RESEND_SRC + ' await resendMessage(arguments[4]); })();');
  await fn(messagesRef, agents, window, dispatchToAgent, m);
  return calls;
}

const gateFn = new Function('onResend', 'TERMINAL_STATES', 'm', 'return !!(' + GATE_SRC + ');');
const TERM = new Function(STATES_SRC + '\n' + TERM_SRC
                          + '\n return TERMINAL_STATES;')();
const door = () => {};
const R = {
  liveChild: await drive('liveChild'),
  doneChild: await drive('doneChild'),
  failedChild: await drive('failedChild'),
  recipientGone: await drive('recipientGone'),
  declined: await drive('declined'),
  bossOrigin: await drive('bossOrigin'),
  peerOrigin: await drive('peerOrigin'),
  termStates: [...TERM],
  gate: {
    stoppedAll: gateFn(door, TERM, { state: 'cancelled', failureCause: { retryable: true } }),
    noDoor: gateFn(null, TERM, { state: 'cancelled', failureCause: { retryable: true } }),
    notRetryable: gateFn(door, TERM, { state: 'cancelled', failureCause: { retryable: false } }),
    inFlight: gateFn(door, TERM, { state: 'awaiting_reply', failureCause: { retryable: true } }),
    failedRetryable: gateFn(door, TERM, { state: 'failed', failureCause: { retryable: true } }),
    cleanCompleted: gateFn(door, TERM, { state: 'completed', failureCause: null }),
  },
};
console.log(JSON.stringify(R));
''')
    p = subprocess.run(['node', '--input-type=module', '-e',
                        '(async () => {' + js
                        + '})().catch(e => { console.error(e); process.exit(1); });'],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted pieces run', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a live retry blocks a second one, with a why',
          r['liveChild']['dispatches'] == [] and r['liveChild']['confirms'] == []
          and any('give it a moment' in w for w in r['liveChild']['warns']),
          r['liveChild'])
    check('a retry that went through blocks another, with a why',
          r['doneChild']['dispatches'] == []
          and any('went through' in w for w in r['doneChild']['warns']),
          r['doneChild'])
    check('a retry that FAILED does not block trying again',
          len(r['failedChild']['dispatches']) == 1, r['failedChild'])
    check('a dismissed recipient gets a toast, not a dispatch',
          r['recipientGone']['dispatches'] == [] and r['recipientGone']['confirms'] == []
          and any('no longer hired' in e for e in r['recipientGone']['errors']),
          r['recipientGone'])
    check('declining the door sends nothing',
          r['declined']['confirms'] != [] and r['declined']['dispatches'] == [],
          r['declined'])
    boss = r['bossOrigin']['dispatches']
    check('a boss-origin resend chains the record, dmFrom null',
          len(boss) == 1 and boss[0]['opts']['parentMessageId'] == 'msg_1'
          and boss[0]['opts']['dmFrom'] is None and boss[0]['to'] == 'Vera',
          boss)
    peer = r['peerOrigin']['dispatches']
    check("a peer-origin resend rides as that peer's DM",
          len(peer) == 1 and peer[0]['opts']['dmFrom']
          and peer[0]['opts']['dmFrom']['name'] == 'Kip',
          peer)
    # The content claim, not the spelling: whatever the set is derived
    # from, a cancellation has to be in it or the gate below cannot open.
    check("the shipped set counts a cancellation as finished",
          set(r['termStates']) >= {'completed', 'failed', 'cancelled'},
          r['termStates'])
    check('the gate opens for a stopped-all cancellation',
          r['gate']['stoppedAll'] is True, r['gate'])
    check('…and for a retryable failure', r['gate']['failedRetryable'] is True)
    check('…and stays shut without the prop, on not-retryable, in flight, and on clean rows',
          r['gate']['noDoor'] is False and r['gate']['notRetryable'] is False
          and r['gate']['inFlight'] is False and r['gate']['cleanCompleted'] is False,
          r['gate'])

    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
