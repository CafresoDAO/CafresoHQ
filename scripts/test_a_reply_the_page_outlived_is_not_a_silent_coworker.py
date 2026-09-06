#!/usr/bin/env python3
"""The office came back with a coworker's name over an empty bubble.

Second session, the way a tester actually has one: hire someone, give them
work, ask them something long — then the box reboots, or serve.py is bounced,
or the tab is reloaded while the answer is still coming. Open the office again
and read the thread.

`persistableChat` dropped `streaming` on the way to storage. Dropping the FLAG
is right — a spinner restored on load belongs to a run that died with the last
page and would blink forever — but the fact it carried is the only thing that
tells a finished reply from one the page outlived, and the write path threw it
away. Worse, `useStored`'s 300ms save debounce is re-armed by every token
frame, so nothing of the answer is ever written while it streams: what is on
disk is still the placeholder the dispatcher seeded, `text: ''`.

Measured 2026-09-05 against a real `python3 serve.py` and a real local brain:
asked a hired coworker for a long list, killed the server mid-answer, restarted
it, reloaded. The transcript came back as

    KIP · DEEP RESEARCH
    <div class="msg-body"></div>

The coworker's name over a blank bubble. No error, no note, nothing anywhere
saying the answer was cut off — a run the restart killed, rendered as a
colleague who answered with silence. Tasks (`tasksOnLoad`), missions
(`missionsOnLoad`) and the roster (`persistableAgents`) all learned this on
their own surfaces; the chat, the surface the boss actually reads, did not.

The fix is the same two-sided shape those use. `persistableChat` TRANSLATES
`streaming` into a durable `interrupted` marker instead of dropping it, and
`chatOnLoad` — a READ scrub, wired through useStored's new `onLoad`, never its
write filter — spends that marker on the way in and says what happened.

Run: python3 scripts/test_a_reply_the_page_outlived_is_not_a_silent_coworker.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORAGE = ROOT / 'app' / 'storage.jsx'
APP = ROOT / 'app.jsx'
# The two sentences moved to app/floor.jsx in #349 — they are office voice,
# and living beside the visit templates is what keeps them out of the model's
# context (chatToMessages sends a message's `text` as that speaker's own
# `assistant` turn). What the bubble says is unchanged; it is now said from
# one place, so the strip and the screen cannot drift apart.
FLOOR = ROOT / 'app' / 'floor.jsx'
FAILS = []

EMPTY = ('_(nothing came back — this reply stopped when the page reloaded. '
         'Ask again when you want it.)_')
CUT = ('_(cut off here — this reply stopped when the page reloaded. '
       'Ask again if you need the rest.)_')


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('a reply the page outlived is not a silent coworker')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = STORAGE.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')

    # The REAL statements run here — lifted, not re-typed. capChatFair comes
    # along because persistableChat is built on it.
    cap = re.search(r'const capChatFair = \(xs, max, floor = 15\) => \{[\s\S]*?\n\};', src)
    persist = re.search(r'const persistableChat = \(xs\) =>[\s\S]*?;\n', src)
    scrub = re.search(r'const chatOnLoad = \(xs\) =>[\s\S]*?\n\}\);', src)
    floor_src = FLOOR.read_text(encoding='utf-8')
    notes = re.findall(r'const CHAT_(?:CUT|GONE)_NOTE = [\s\S]*?;\n', floor_src)
    check('the chat write filter is still one statement', bool(cap and persist),
          'app/storage.jsx')
    check('the chat load-scrub exists', bool(scrub),
          'app/storage.jsx: chatOnLoad is the read side of the marker')
    check('the two sentences it says are declared once, in app/floor.jsx',
          len(notes) == 2,
          'app/floor.jsx: CHAT_CUT_NOTE / CHAT_GONE_NOTE — office voice, so '
          'the office-voice strip can find them (#349)')
    if not (cap and persist and scrub and len(notes) == 2):
        print()
        print('a silent coworker: FAILED — could not lift the shipped source')
        return 1

    R = run("""
%s
%s
%s
%s
const R = {};
// The wreck, verbatim: the placeholder a dispatcher seeds, still streaming
// when the page went away. Nothing of the answer ever reached disk.
const live = [{ id:'m1', from:'agent', name:'Kip · Deep Research', text:'',
                streaming:true, thread:'direct', agentId:'a1' }];
R.writtenEmpty = persistableChat(live)[0];
R.loadedEmpty  = chatOnLoad(persistableChat(live))[0];

// Same run, but some of the answer had landed before the page died.
const partial = [{ id:'m2', from:'agent', name:'Kip', text:'1. Anchor pricing.',
                   streaming:true }];
R.loadedPartial = chatOnLoad(persistableChat(partial))[0];

// A reply that really finished: the finalize clears `streaming`, so the
// record it writes carries no marker and the scrub must not touch it.
const done = [{ id:'m3', from:'agent', name:'Kip', text:'The whole answer.',
                streaming:false }];
R.writtenDone = persistableChat(done)[0];
R.loadedDone  = chatOnLoad(persistableChat(done))[0];

// The boss's own lines, and the office's, are never streaming.
R.loadedUser = chatOnLoad(persistableChat(
  [{ id:'m4', from:'user', name:'You', text:'ask' }]))[0];

// The marker is spent once. Re-loading an already-scrubbed store must not
// stack a second note onto the same bubble.
R.twice = chatOnLoad(chatOnLoad(persistableChat(live)))[0];

// `error` is still dropped, same as before.
R.errDropped = persistableChat(
  [{ id:'m5', from:'agent', text:'x', error:true }])[0];

R.nulls  = chatOnLoad([null, { id:'m6', text:'ok' }]);
R.notArr = chatOnLoad('not an array');
console.log(JSON.stringify(R));
""" % (''.join(notes), cap.group(0), persist.group(0), scrub.group(0)))

    check('a live spinner is never written to storage',
          'streaming' not in R['writtenEmpty'],
          f"{R['writtenEmpty']!r} — a spinner restored on load belongs to a "
          'run that died with the last page; it would blink forever')
    check('...but the fact it carried is',
          R['writtenEmpty'].get('interrupted') is True,
          f"{R['writtenEmpty']!r} — without this the record is an ordinary "
          'finished message and the next load cannot tell the difference')
    check('an answer that never started says so, instead of nothing',
          R['loadedEmpty'].get('text') == EMPTY,
          f"{R['loadedEmpty'].get('text')!r} — the measured wreck is a blank "
          "<div class=\"msg-body\"></div> under the coworker's name")
    check('...and the marker is spent on the way in',
          'interrupted' not in R['loadedEmpty'],
          f"{R['loadedEmpty']!r} — a marker left on the record would be "
          're-persisted and re-narrated on every future load')
    check('a half-answer keeps what landed and admits the rest is missing',
          R['loadedPartial'].get('text') == '1. Anchor pricing.\n\n' + CUT,
          f"{R['loadedPartial'].get('text')!r} — nothing the coworker actually "
          'said may be thrown away, and nothing may be invented for what they '
          'did not')
    check('a reply that finished is left completely alone',
          R['writtenDone'].get('interrupted') is None
          and R['loadedDone'].get('text') == 'The whole answer.',
          f"{R['writtenDone']!r} / {R['loadedDone']!r} — the finalize that "
          'ends every real reply clears `streaming`, so the last write of a '
          'healthy run carries no marker')
    check('the boss\'s own lines are never rewritten',
          R['loadedUser'].get('text') == 'ask',
          f"{R['loadedUser']!r}")
    check('a second load does not stack a second note',
          R['twice'].get('text') == EMPTY,
          f"{R['twice'].get('text')!r} — the scrub has to be idempotent; the "
          'office reads this store on every boot')
    check('the error flag is still dropped, as before',
          'error' not in R['errDropped'] and R['errDropped'].get('text') == 'x',
          f"{R['errDropped']!r}")
    check('a null entry does not crash the load',
          R['nulls'][0] is None and R['nulls'][1].get('text') == 'ok',
          f"{R['nulls']!r}")
    check('a corrupt store loads as an empty thread',
          R['notArr'] == [],
          f"{R['notArr']!r}")

    # ── the wiring, pinned ──────────────────────────────────────────────
    # #413 moved the chat from useStored to useFileStored — there is an
    # hq-state/chat.json now — and the two hooks spell this the other way
    # round: useStored takes the WRITE filter third and the READ scrub
    # fourth, useFileStored takes the read transform FIFTH and the write
    # filter in options. The invariant is unchanged and is what this pins:
    # the scrub is on the read side, the filter on the write side, and they
    # are never the same argument. Written to accept EITHER hook so a future
    # move back does not need an edit here — what it refuses is the swap.
    chat_call = re.search(r"use(?:File)?Stored\(k\('chat'\)[^;]*?\);", app, re.S)
    call = chat_call.group(0) if chat_call else ''
    on_read = re.search(r"HQ\.INITIAL_CHAT,\s*chatOnLoad\b", call) is not None
    on_read_merged = 'mergeChat(' in call            # the union runs chatOnLoad itself
    on_write = 'persistTransform: persistableChat' in call
    on_write_positional = re.search(
        r"useStored\(k\('chat'\),\s*HQ\.INITIAL_CHAT,\s*persistableChat,\s*chatOnLoad\)", app) is not None
    check('the scrub is wired to the chat as a READ hook, not a write filter',
          bool(call) and ((on_read and on_write_positional is False and on_write)
                          or (on_read_merged and on_write)
                          or on_write_positional),
          f'app.jsx: {call[:200]!r} — the read scrub and the write filter must '
          'be different arguments. Under useStored the scrub is the 4th and '
          'the filter the 3rd; under useFileStored the read transform is the '
          '5th and the filter goes in options as persistTransform. Swapping '
          'them stamps "this reply stopped when the page reloaded" onto a run '
          'that is still going')
    check('...and whatever runs on the read side actually applies the scrub',
          bool(call) and (on_read or on_write_positional
                          or (on_read_merged
                              and 'chatOnLoad(fetched)' in STORAGE.read_text(encoding='utf-8'))),
          'app.jsx / app/storage.jsx: #413 routes the read side through '
          'mergeChat, which must call chatOnLoad on the FETCHED half — a '
          'union that skips it means a fresh browser shows a coworker name '
          'over a blank bubble with nothing saying the answer was severed')
    check('useStored applies onLoad only where the page READS storage',
          STORAGE.read_text(encoding='utf-8').count('onLoad ? onLoad(parsed) : parsed') == 1,
          'app/storage.jsx: exactly one call site, in the mount initialiser. '
          'The cross-tab absorber must stay off this path — a record another '
          'tab is writing right now belongs to a live run')
    # One writer each, and after #349 that writer is app/floor.jsx: the strip
    # that keeps these out of the model's context matches them literally, so a
    # second copy anywhere is a sentence that reaches the brain.
    floor_code = re.sub(r'/\*[\s\S]*?\*/', '', floor_src)
    check('the two endings have exactly one writer each',
          floor_code.count(EMPTY.split('—')[0]) == 1
          and floor_code.count(CUT.split('—')[0]) == 1,
          'app/floor.jsx: these sentences are only ever true of a reply the '
          'page outlived, so chatOnLoad is the only thing allowed to say them')
    check('...and app/storage.jsx does not keep a second copy',
          src.count(EMPTY.split('—')[0]) == 0 and src.count(CUT.split('—')[0]) == 0,
          'app/storage.jsx must import them; a copy here is one the office-voice '
          'strip would not recognise, and it would ship to the brain (#349)')

    print()
    if FAILS:
        print(f'a silent coworker: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('a silent coworker: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
