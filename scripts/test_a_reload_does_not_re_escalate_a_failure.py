#!/usr/bin/env python3
"""The office kept telling the boss the same coworker was stuck.

app.jsx's escalation watcher (`escalationStateRef`) is DELIBERATELY
in-memory for its cooldown — the comment right above it says so, and that
is the right call for "live alert" semantics. `lastSeenIds`, the Set that
stops a still-`failed` message being re-elected as "new", rode along on the
same in-memory ref, and that part was never supposed to be session-scoped:
its whole job is to recognize a message this effect has already acted on.

Driven live against a real `python3 serve.py` and a real Chrome tab (no
brain signed in, so the CEO's first reply 401s): send one message, watch
the `critical`-rule escalation fire once, reload the page. `messages`
(useFileStored) comes back from disk exactly as it was — same id, same
`state: 'failed'`, same `failureCause` — but `escalationStateRef` comes back
blank, so the fresh `lastSeenIds` has never heard of that id and the fresh
90s-cooldown `lastEscalatedFor` has never heard of that key either. The
still-failed message reads as brand new and escalates again: one persisted
system chat row after the first load, two after the first reload, three
after the second. Nothing in the scenario changes between reloads — no new
failure, no retry — every load past the first is pure duplication.

The fix stamps `escalatedAt` onto the message record itself, in the same
`setMessages` call that already persists `state`/`failureCause`, at the
moment a rule actually fires. `newFails` now excludes any message already
carrying it, so a message escalated once stays escalated across every
future mount — the fresh ref no longer matters, because the durable half of
the question moved off it.

Lifts the real effect body out of app.jsx (the block that opens at
`const escalationStateRef = useRefA({` and closes at the first `}, [
messages]);` after it) and runs it under node three times in a row against
one persisted `messages` array, standing in for three page loads with no
new failure between them — the same shape as the live drive above.

Run: python3 scripts/test_a_reload_does_not_re_escalate_a_failure.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift_watcher(text):
    start_marker = 'const escalationStateRef = useRefA({'
    start = text.index(start_marker)
    end_marker = '}, [messages]);'
    end = text.index(end_marker, start) + len(end_marker)
    return text[start:end]


HARNESS = r'''
function mount(state) {
  const messages = state.messages;
  const agents = [{ id: 'a_local_ollama', name: 'Llama', model: 'ollama:llama3.1' }];
  const HQ = { uid: (p) => p + '_' + (state.nextId++) };
  const snagCause = (s) => String(s || 'unknown');
  const withRouteOut = (text) => text;
  const CafresoHQClient = {};
  const window = { cafresohqToast: { error: () => { state.toasts++; } } };
  const setChat = (updater) => {
    const out = updater(state.chat);
    state.chat = out;
  };
  const setMessages = (updater) => {
    state.messages = updater(state.messages);
  };
  // A fresh escalationStateRef every call — this is the part of the bug
  // that reload actually reproduces: a component remount hands the effect
  // a blank ref no matter what `messages` remembers.
  const useRefA = (init) => ({ current: init });
  const React = { useEffect: (fn) => fn() };

  %s
}

const state = { messages: %s, chat: [], toasts: 0, nextId: 0 };
mount(state);   // first load — the failure is new, this SHOULD escalate
mount(state);   // reload #1 — same failure, nothing new happened
mount(state);   // reload #2 — same failure again

console.log(JSON.stringify({
  systemRows: state.chat.filter(m => m.from === 'system').length,
  toasts: state.toasts,
  escalatedAt: !!(state.messages[0] || {}).escalatedAt,
}));
'''


def run(messages_json):
    text = SRC.read_text(encoding='utf-8')
    watcher = lift_watcher(text)
    js = HARNESS % (watcher, messages_json)
    proc = subprocess.run(['node', '-e', js], cwd=ROOT, capture_output=True,
                           text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('a reload does not re-escalate a failure')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    critical_failure = json.dumps([{
        'id': 'msg_1',
        'toAgentId': 'a_ceo',
        'toAgentName': 'CafresoHQ',
        'state': 'failed',
        'updatedAt': 0,
        'failureCause': {'kind': 'auth', 'message': 'not signed in'},
    }])
    out = run(critical_failure)

    check('exactly one system chat row across three loads of the same '
          'still-failed message', out['systemRows'] == 1, out)
    check('exactly one toast across the same three loads',
          out['toasts'] == 1, out)
    check('the message itself now carries escalatedAt',
          out['escalatedAt'] is True, out)

    # A message that was never escalated (no failureCause at all) must
    # never be stamped or alerted on — the fix must not touch the happy path.
    ok_msg = json.dumps([{
        'id': 'msg_2', 'toAgentId': 'a_ceo', 'toAgentName': 'CafresoHQ',
        'state': 'done', 'updatedAt': 0,
    }])
    out2 = run(ok_msg)
    check('an ordinary done message is never escalated',
          out2['systemRows'] == 0 and out2['toasts'] == 0
          and out2['escalatedAt'] is False, out2)

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
