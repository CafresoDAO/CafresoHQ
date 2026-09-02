#!/usr/bin/env python3
"""Letting a coworker go left their night shift booked on the machine.

A research mission lives in the tab, so closing it ends the argument. A
night shift does not: it is a row in serve.py's scheduled-missions.json,
run by night_runner.py in its own process. Dismissing someone never
touched it.

Reproduced live on a fresh office: hired Llama, POSTed a daily sweep to
/missions/schedule, pressed LET GO.

  BEFORE: the office read 0 hired and the schedule sat there with
          enabled:true and nextRunAt set for the next night. It would wake
          at 1am, spend an hour and real tokens on their brain, and file
          notes in the vault under the name of someone who does not work
          here -- with the tab shut and nobody watching.
  AFTER:  all of the leaver's schedules are cancelled, anyone else's are
          left alone, and the CEO says what was called off.

The board mirror cannot answer this question: nightShiftBoard is filtered
to schedules RUNNING RIGHT NOW, so it holds none of the ones that matter
most -- the ones booked for tonight. The list has to come from the server.
The DELETE is the one STOP ALL and the modal's own CANCEL already use; it
drops the row AND flags an in-flight run to stop.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(' -- ' + detail) if detail else ''}")
        failures.append(label)


def strip_js_comments(src):
    """Blank comment bodies, keeping newlines so offsets stay usable."""
    out, i, n, q = [], 0, len(src), None
    while i < n:
        c = src[i]
        if q:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(src[i + 1]); i += 2; continue
            if c == q:
                q = None
            i += 1
            continue
        if c in '"\'`':
            q = c; out.append(c); i += 1; continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2); j = n if j == -1 else j + 2
            out.append(''.join(x if x == '\n' else ' ' for x in src[i:j])); i = j; continue
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i); j = n if j == -1 else j
            out.append(' ' * (j - i)); i = j; continue
        out.append(c); i += 1
    return ''.join(out)


def balanced(src, open_at):
    depth = 0
    for k in range(open_at, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return k
    raise AssertionError('unbalanced braces')


APP_RAW = open(os.path.join(ROOT, 'app.jsx')).read()
APP = strip_js_comments(APP_RAW)


def main():
    # The fix is explained in a comment that names the endpoint, the flag and
    # the field the sweeps look for. Measured across the file rather than by
    # one phrase, so rewording a comment can neither fail this nor disarm it.
    check("comment stripping removed every block comment",
          APP_RAW.count('/*') > 100 and APP.count('/*') == 0,
          f"{APP_RAW.count('/*')} raw, {APP.count('/*')} left")
    check("...without moving any line", len(APP) == len(APP_RAW))

    print("1. the cancel runs on the way out, not on the next login")
    try:
        i = APP.index('const onDismiss = async (id) =>')
        dismiss = APP[i:balanced(APP, APP.index('{', i)) + 1]
    except (ValueError, AssertionError) as e:
        print(f"FAILED: could not lift onDismiss ({e})")
        return 1
    check("onDismiss cancels the leaving coworker's night shifts",
          '/missions/scheduled' in dismiss and "method: 'DELETE'" in dismiss,
          '— a night shift is a row on the server, not state in this tab; '
          'closing the office does not stop it')
    # The list has to come from the server. nightShiftBoard only ever holds
    # schedules that are running at this instant, so a fix that filtered it
    # would cancel nothing in the ordinary case and still look right.
    check("...reading the list from the server, not from the board mirror",
          "fetch(base + '/missions/scheduled'" in dismiss,
          '— nightShiftBoard is filtered to RUNNING schedules only')

    print("2. the cancel itself, lifted and run")
    try:
        anchor = APP.index('setNightShiftBoard(prev => prev.filter')
        start = APP.rindex('(async () => {', 0, anchor)
        obrace = APP.index('{', start)
        body = APP[obrace + 1:balanced(APP, obrace)]
    except (ValueError, AssertionError) as e:
        print(f"FAILED: could not lift the cancel ({e})")
        return 1

    harness = """
const HQ = { uid: (p) => p + '1' };
const CafresoHQClient = { backendBase: () => '' };

async function cancel(schedules, leavingIds, opts) {
  opts = opts || {};
  const leaving = new Set(leavingIds);
  const deleted = [];
  let board = [{ id: 'x', agentId: 'a1' }, { id: 'y', agentId: 'a2' }];
  let boardTouched = false;
  let said = [];
  const setNightShiftBoard = (fn) => { boardTouched = true; board = fn(board); };
  const setChat = (fn) => { said = said.concat(fn([])); };
  const fetch = async (url, o) => {
    const u = String(url);
    if (u.endsWith('/missions/scheduled')) {
      if (opts.listThrows) throw new Error('offline');
      return { json: async () => (opts.badBody ? {} : { schedules }) };
    }
    deleted.push(u.split('/').pop());
    if (opts.deleteThrows) return Promise.reject(new Error('nope'));
    return { json: async () => ({ ok: true }) };
  };
  await (async () => {%s})();
  return { deleted, board, boardTouched, said: said.map(m => m.text) };
}

const S = (id, agentId) => ({ id, agentId, agentName: 'Llama', topic: 't' });
const three = await cancel([S('n1','a1'), S('n2','a1'), S('n3','a1'), S('n4','a2')], ['a1']);
const one   = await cancel([S('n1','a1'), S('n4','a2')], ['a1']);
const none  = await cancel([S('n4','a2')], ['a1']);
const cascade = await cancel([S('n1','a1'), S('n2','a9'), S('n4','a2')], ['a1','a9']);
const offline = await cancel([S('n1','a1')], ['a1'], { listThrows: true });
const badBody = await cancel([S('n1','a1')], ['a1'], { badBody: true });
const dfail = await cancel([S('n1','a1')], ['a1'], { deleteThrows: true });

console.log(JSON.stringify({
  threeDeleted: three.deleted, threeSaid: three.said[0] || null,
  threeBoard: three.board.map(b => b.id).join(','),
  oneDeleted: one.deleted, oneSaid: one.said[0] || null,
  noneDeleted: none.deleted, noneSaid: none.said.length, noneBoard: none.boardTouched,
  cascadeDeleted: cascade.deleted.sort(),
  offlineSaid: offline.said.length, offlineDeleted: offline.deleted.length,
  badBodySaid: badBody.said.length,
  dfailSaid: dfail.said.length,
}));
""" % body

    tmp = tempfile.mkdtemp(prefix='nightshift-')
    r = {}
    try:
        p = os.path.join(tmp, 'c.mjs')
        with open(p, 'w') as fh:
            fh.write(harness)
        proc = subprocess.run([shutil.which('node') or 'node', p],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            print("  FAIL node harness errored: " + proc.stderr.strip()[:400])
            failures.append("node harness")
        else:
            r = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if r:
        check("every schedule the leaver owned is cancelled",
              r.get('threeDeleted') == ['n1', 'n2', 'n3'], repr(r.get('threeDeleted')))
        check("...and nobody else's is touched",
              'n4' not in (r.get('threeDeleted') or []), repr(r.get('threeDeleted')))
        check("a cascade dismissal cancels for everyone leaving",
              r.get('cascadeDeleted') == ['n1', 'n2'], repr(r.get('cascadeDeleted')))
        # The floor polls every 15s. Without the optimistic clear it keeps a
        # dismissed coworker at work on screen for up to that long.
        check("the floor stops showing them at once, not at the next poll",
              r.get('threeBoard') == 'y', repr(r.get('threeBoard')))
        check("the boss is told, with the plural agreeing",
              '3 night shifts were' in (r.get('threeSaid') or '')
              and 'they were' in (r.get('threeSaid') or ''), repr(r.get('threeSaid')))
        check("...and the singular reads as English too",
              'night shift was' in (r.get('oneSaid') or '')
              and 'it was' in (r.get('oneSaid') or ''), repr(r.get('oneSaid')))
        check("nothing is cancelled or said when they had none",
              r.get('noneDeleted') == [] and r.get('noneSaid') == 0
              and r.get('noneBoard') is False)
        # This runs while the boss is dismissing someone. A throw here would
        # escape into onDismiss and strand the rest of the cascade.
        check("an unreachable server does not break the dismissal",
              r.get('offlineSaid') == 0 and r.get('offlineDeleted') == 0)
        check("a malformed listing does not break it either",
              r.get('badBodySaid') == 0)
        check("one refused DELETE does not take the announcement down with it",
              r.get('dfailSaid') == 1)

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures[:6]))
        return 1
    print("PASS: a night shift does not outlive the office that booked it")
    return 0


if __name__ == '__main__':
    sys.exit(main())
