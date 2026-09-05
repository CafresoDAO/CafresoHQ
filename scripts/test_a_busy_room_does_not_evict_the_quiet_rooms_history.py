#!/usr/bin/env python3
"""One busy room spent every other room's history budget.

The chat is ONE array interleaving every room — direct, team, project:*,
meeting:*, research — and both of its caps were a plain slice over that
shared array:

    app/storage.jsx   const persistableChat = (xs) => xs.slice(-80).map(...)
    app.jsx           if (chat.length > 120) setChat(prev => prev.slice(-100));

A slice has no idea threads exist. The newest N messages win, whichever
room they came from, so the noisiest room spent the whole budget.

Measured 2026-08-30, before the fix, by driving the exact lines above:

    20 direct messages, then a project room streams 90:
      saved file:  80 messages — project:p1: 80, direct: 0
    40 direct messages, then the same 90, through the in-memory ceiling:
      live array: 100 messages — project:p1: 90, direct: 10

The first is a reload opening onto an EMPTY Direct room the boss had been
talking in that same morning. The second is the live transcript thinning
on screen while a meeting runs — history the boss can watch disappear.

The fix is a floor, not a quota. `capChatFair(xs, max, floor)` still
evicts oldest-first — a busy room still pays first, it is the one over
budget — but skips any message whose thread is already down to its last
`floor` entries. A quiet room keeps enough of its tail to still read as a
conversation. The total may exceed `max` by at most (threads x floor),
which is bounded by rooms that actually have history, and the helper
returns the SAME array when nothing needs dropping so the React setter
can bail out on reference equality instead of looping.

Run: python3 scripts/test_a_busy_room_does_not_evict_the_quiet_rooms_history.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORAGE = (ROOT / 'app' / 'storage.jsx').read_text(encoding='utf-8')
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    i = src.index(opener)
    depth = 0
    started = False
    for k in range(i, len(src)):
        if src[k] == '{':
            depth += 1
            started = True
        elif src[k] == '}':
            depth -= 1
            if started and depth == 0:
                # run to the statement's end
                j = src.index(';', k)
                return src[i:j + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def main():
    print('a busy room does not evict the quiet rooms\' history')
    storage = strip_comments(STORAGE)
    app = strip_comments(APP)

    # ── 1. both caps go through the fair helper ─────────────────────────
    check('the fair helper exists once',
          storage.count('const capChatFair = (xs, max, floor = 15) =>') == 1)
    # #345 broke this pin on FORMATTING only: persistableChat's body moved to
    # the next line when it grew a second clause. The claim it makes — the
    # save cap is capChatFair(xs, 80) and nothing else — is unchanged, so the
    # pin is re-spelt to allow the wrap rather than relaxed.
    check('the save cap reads it',
          re.search(r'const persistableChat = \(xs\) =>\s*capChatFair\(xs, 80\)\s*\.map\(',
                    storage) is not None,
          '— the saved file is the one a reload trusts')
    check('the in-memory ceiling reads it',
          'setChat(prev => capChatFair(prev, 100));' in app)
    check('no cap is a bare slice over the shared array any more',
          'xs.slice(-80)' not in storage and 'prev.slice(-100)' not in app,
          '— a slice has no idea threads exist')
    check('the helper is exported and imported',
          'capChatFair,' in storage.split('export {')[1]
          and re.search(r'import \{ capChatFair,', app))

    # ── 2. what the caps actually do, on the measured day ───────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — behavior checks need it')
    else:
        helper = brace_lift(storage, 'const capChatFair = (xs, max, floor = 15) =>')
        persist = brace_lift(storage, 'const persistableChat = (xs) =>')
        js = helper + '\n' + persist + r'''
const mk = (n, thread) => Array.from({ length: n }, (_, i) => ({
  id: thread + ':' + i, from: i % 2 ? 'ceo' : 'user', text: 'msg ' + i,
  ...(thread === 'direct' ? {} : { thread }),
}));
const count = (xs) => {
  const b = {};
  for (const m of xs) { const t = m.thread || 'direct'; b[t] = (b[t] || 0) + 1; }
  return b;
};
const isSubseq = (kept, all) => {
  let i = 0;
  for (const m of all) if (i < kept.length && kept[i].id === m.id) i++;
  return i === kept.length;
};
// The measured morning: direct first, then the project room streams.
const saveDay = [...mk(20, 'direct'), ...mk(90, 'project:p1')];
const saved = persistableChat(saveDay);
const liveDay = [...mk(40, 'direct'), ...mk(90, 'project:p1')];
const live = capChatFair(liveDay, 100);
// A pile of rooms all at the floor: eviction must stop, not empty rooms.
const crowded = [].concat(...['direct', 'team', 'project:a', 'project:b',
  'meeting:x', 'meeting:y', 'research'].map(t => mk(15, t)));
const crowdCap = capChatFair(crowded, 60);
const small = mk(30, 'direct');
const streaming = capChatFair(
  [{ id: 's1', from: 'agent', text: 'hi', streaming: true, error: 'x' }], 80);
console.log(JSON.stringify({
  saved: count(saved), savedLen: saved.length,
  savedOrdered: isSubseq(saved, saveDay),
  live: count(live), liveLen: live.length,
  liveOrdered: isSubseq(live, liveDay),
  crowd: count(crowdCap), crowdLen: crowdCap.length,
  sameRef: capChatFair(small, 100) === small,
  stripped: Object.keys(persistableChat(
    [{ id: 's1', from: 'agent', text: 'hi', streaming: true, error: 'x' }])[0]),
}));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True,
                           timeout=60)
        if p.returncode != 0:
            check('the lifted caps run', False, p.stderr.strip()[:300])
        else:
            r = json.loads(p.stdout.strip().split('\n')[-1])
            check('the saved file keeps the quiet room',
                  r['saved'].get('direct', 0) >= 15,
                  [r['saved'], '— this was 0: a reload opened onto an empty '
                   'Direct room'])
            check('...and the busy room paid the eviction',
                  r['saved'].get('project:p1', 0) < 90
                  and r['savedLen'] <= 80 + 15,
                  r['saved'])
            check('the live transcript keeps the quiet room too',
                  r['live'].get('direct', 0) >= 15,
                  [r['live'], '— this was 10 and falling while the meeting ran'])
            check('eviction never reorders what it keeps',
                  r['savedOrdered'] and r['liveOrdered'])
            check('a floor is a floor — rooms all at it are left alone',
                  all(v == 15 for v in r['crowd'].values())
                  and r['crowdLen'] == 105,
                  [r['crowd'], '— over max, and correct: emptying a room to '
                   'hit a byte budget is the defect this fixes'])
            check('an array under budget comes back as the SAME array',
                  r['sameRef'] is True,
                  '— the React setter bails out on reference equality; a '
                  'fresh copy every pass is a render loop')
            # CHANGED by #345, and deliberately: the old spelling of this
            # check was `== ['from', 'id', 'text']`, which pinned the wreck.
            # It asserted that a message still STREAMING when it was written
            # persists as an ordinary, finished record with nothing left of
            # the fact — and with useStored's save debounce re-armed by every
            # token frame, that record is the untouched placeholder, `text:
            # ''`. Measured: reload mid-answer and the thread comes back as
            # the coworker's name over a blank bubble. The live flags are
            # still never persisted (a restored spinner would blink forever)
            # — what is added is the durable marker chatOnLoad spends on the
            # way in. Both halves of that are asserted here.
            check('the save cap still strips the live streaming/error flags',
                  'streaming' not in r['stripped'] and 'error' not in r['stripped'],
                  r['stripped'])
            check('...and keeps the durable marker in their place',
                  sorted(r['stripped']) == ['from', 'id', 'interrupted', 'text'],
                  r['stripped'])

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
