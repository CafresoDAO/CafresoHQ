#!/usr/bin/env python3
"""A snag row's Retry sent a stranger's message, twice, with no door.

Measured 2026-08-16 on office 9261. Four of the five writers of a
`failed` attention row carry NO messageId — the runner error, a failed
delegation, a failed task run, and a publish that fell over after
approval. onRetryActivity's fallback picked "the newest failed message
for this agent, or anywhere in the office if the row names no agent"
and dispatched it with neither the one-live-child guard nor the confirm
door.

Driven live: a row reading "HQ — That didn't work — the pty bridge
dropped" re-sent an unrelated coworker's chat message ("trace the
citations fifty-eight") to Vera. Zero confirm prompts. Pressed twice,
it filed TWO completed children of the same parent — real work, ordered
twice, which is precisely what that function's own comment claimed to
prevent.

The fix keeps one dispatch site (resendMessage, from #102) and gives it
an opt-out door:

  - a row that NAMES its run  → resendMessage(m, {confirm: false}).
    The button sits on the row, the row names the work; one press is
    the whole answer. It gains the guard it never had on this path.
  - a row that names a coworker but no run → that coworker's newest
    failure, WITH the door, which quotes the body so the boss sees what
    they are about to send.
  - an office-level row (no coworker, no run) → nothing to re-send, and
    it says so. The office-wide grab is gone.
  - and the button itself no longer renders on a row that names neither
    (views/core.jsx) — same gate==label rule as the Inbox's ↻ RE-SEND.

Run: python3 scripts/test_a_snag_row_retries_its_own_run.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

DECL = 'const onRetryActivity = (entry) => {'
RESEND_DECL = 'const resendMessage = async (m, { confirm = true } = {}) => {'
DOOR = 'if (confirm && !(await window.hqConfirm('
NAMED = 'if (named) return resendMessage(named, { confirm: false });'
FALLBACK = 'return resendMessage(failed[0], { confirm: true });'
OFFICE = "That one is the office's own snag, not a coworker's message"
ROW_GATE = '{(e.messageId || e.agentId) && ('


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
    print('a snag row retries its own run')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    core = (ROOT / 'views' / 'core.jsx').read_text(encoding='utf-8')
    bare = strip_comments(app)
    cbare = strip_comments(core)

    # ── the handler picks a message; it no longer sends one ──────────────
    at = bare.find(DECL)
    end = bare.find('\n  };', at)
    fn = bare[at:end + 5] if at != -1 and end > at else ''
    check('onRetryActivity exists once', bare.count(DECL) == 1, f'{bare.count(DECL)} sites')
    check('it lifts', fn.startswith(DECL) and fn.rstrip().endswith('};'))
    check('it keeps no dispatch of its own',
          'dispatchToAgent(' not in fn,
          'the private copy is how the guard and the door went missing')
    check('…and no private guard either', 'x.parentId === m.id' not in fn,
          'one guard, in resendMessage')
    check('a named row goes straight through', NAMED in fn)
    check('an unnamed row with a coworker pays the door', FALLBACK in fn)
    check('an office-level row is told there is nothing to send', OFFICE in fn)
    check('the office-wide grab is gone',
          'x.state === \'failed\')' not in fn.replace(
              "all.filter(x => x.state === 'failed' && x.toAgentId === agentId)", ''),
          'a row that names no coworker must not reach for another one\'s failure')
    check('the fallback stays scoped to the row\'s coworker',
          "x.state === 'failed' && x.toAgentId === agentId" in fn)

    # ── the shared function still owns guard + door ──────────────────────
    check('resendMessage takes the opt-out door', RESEND_DECL in bare)
    # app.jsx has other confirms (letting someone go, deleting a card); the
    # claim here is narrower: the RETRY path has exactly one, and it is not
    # a second copy living in the handler.
    check('the retry door is conditional, and there is exactly one',
          bare.count(DOOR) == 1 and 'hqConfirm' not in fn,
          f'{bare.count(DOOR)} conditional doors; handler has its own: '
          f'{"hqConfirm" in fn}')

    # ── the button obeys the same rule as its label ──────────────────────
    check('the row gates its Retry on having something to retry',
          cbare.count(ROW_GATE) == 1, f'{cbare.count(ROW_GATE)} gates')
    jumps_at = cbare.find("className=\"oc-act-jumps\" style={{marginTop:6}}")
    what_at = cbare.find('What happened?', jumps_at) if jumps_at != -1 else -1
    gate_at = cbare.find(ROW_GATE)
    check('"What happened?" survives the gate — the detail is not the door',
          -1 < jumps_at < gate_at < what_at,
          (jumps_at, gate_at, what_at))

    # ── drive the lifted handler ─────────────────────────────────────────
    js = ('const FN_SRC = ' + json.dumps(fn) + ';\n' + r'''
async function drive(entry, opts) {
  opts = opts || {};
  const calls = { resends: [], warns: [] };
  const agents = [{ id: 'a_v', name: 'Vera' }, { id: 'a_k', name: 'Kip' }];
  const messagesRef = { current: opts.messages || [] };
  const window = { cafresohqToast: { warn: (s) => calls.warns.push(s) } };
  const resendMessage = async (m, o) => calls.resends.push({ id: m.id, opts: o });
  const fn = new Function('messagesRef', 'agents', 'window', 'resendMessage',
    'return (async () => { ' + FN_SRC + ' return onRetryActivity(arguments[4]); })();');
  await fn(messagesRef, agents, window, resendMessage, entry);
  return calls;
}

const MSGS = [
  { id: 'm_named',  state: 'failed', toAgentId: 'a_v', updatedAt: 10 },
  { id: 'm_older',  state: 'failed', toAgentId: 'a_v', updatedAt: 20 },
  { id: 'm_newest', state: 'failed', toAgentId: 'a_v', updatedAt: 99 },
  { id: 'm_kip',    state: 'failed', toAgentId: 'a_k', updatedAt: 50 },
  { id: 'm_ok',     state: 'completed', toAgentId: 'a_v', updatedAt: 98 },
];
const R = {
  named:      await drive({ messageId: 'm_named', agentId: 'a_v' }, { messages: MSGS }),
  namedGone:  await drive({ messageId: 'm_vanished', agentId: 'a_v' }, { messages: MSGS }),
  unnamed:    await drive({ agentId: 'a_v' }, { messages: MSGS }),
  otherAgent: await drive({ agentId: 'a_k' }, { messages: MSGS }),
  office:     await drive({ text: 'That did not work' }, { messages: MSGS }),
  officeEmpty: await drive({}, { messages: [] }),
  noneForThem: await drive({ agentId: 'a_k' },
    { messages: [{ id: 'm_v', state: 'failed', toAgentId: 'a_v', updatedAt: 5 }] }),
};
console.log(JSON.stringify(R));
''')
    p = subprocess.run(['node', '--input-type=module', '-e',
                        '(async () => {' + js
                        + '})().catch(e => { console.error(e); process.exit(1); });'],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted handler runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    named = r['named']['resends']
    check('a row that names its run retries THAT run, no door',
          len(named) == 1 and named[0]['id'] == 'm_named'
          and named[0]['opts']['confirm'] is False, named)
    gone = r['namedGone']['resends']
    check("a named row whose message has aged out falls back — with the door",
          len(gone) == 1 and gone[0]['id'] == 'm_newest'
          and gone[0]['opts']['confirm'] is True, gone)
    un = r['unnamed']['resends']
    check("an unnamed row takes that coworker's NEWEST failure, with the door",
          len(un) == 1 and un[0]['id'] == 'm_newest'
          and un[0]['opts']['confirm'] is True, un)
    oth = r['otherAgent']['resends']
    check("…and never reaches across to another coworker's failure",
          len(oth) == 1 and oth[0]['id'] == 'm_kip', oth)
    check('an office-level row sends NOTHING and says why',
          r['office']['resends'] == []
          and any('office' in w for w in r['office']['warns']), r['office'])
    check('…even with an empty registry, still no dispatch',
          r['officeEmpty']['resends'] == [], r['officeEmpty'])
    check('a coworker with no failure on record gets a warning, not a stranger\'s note',
          r['noneForThem']['resends'] == []
          and any('No failed message on record' in w for w in r['noneForThem']['warns']),
          r['noneForThem'])

    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
