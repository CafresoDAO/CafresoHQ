#!/usr/bin/env python3
"""Asked to put a page live, the office said it was impossible and named no door.

Measured on office 9262, 2026-08-15, gpt-oss-20b through LM Studio. Mika
had just built site/index.html — 467 chars, on disk, and the office had
said so. The boss then asked:

    @Mika great — now put that lemonade page live on the internet and give
    me the link.

The reply, in full:

    I can create the local file at site/index.html, but publishing it
    online requires deployment access or a hosting service that isn't
    currently available in this environment.

Nothing in that is a lie, and every word of it is the model's. That is the
problem. PUBLISH_SITE exists, is implemented, and works without the chain
bridge; `toolsForAgent` gates it on `icpPublishEnabled()`, so with the
Publish module off it never reached Mika's tool list, and Mika explained
the absence the only way it could — by guessing. The office knew the real
reason, and the real reason is one toggle the boss can reach in about four
seconds. §7 asks for one honest sentence PLUS a way forward; the boss got
neither, and was left believing their office cannot do a thing it can.

The fix is a detector on the two things the office actually KNOWS: the
boss's own words, and the module flag. Not on whether the coworker's prose
sounds like a refusal — that is a judgement, and a judgement about a
model's tone is not detection. It is decided once per boss turn and
emitted after the boss's own bubble, on every route out of the composer.

Both halves of the first placement were wrong, and both were measured:
decided down at the @mention block, it sat BELOW two routes that return
before it (a populated room, and /brainstorm) so it never fired in a
meeting at all; emitted there, it printed ABOVE every user echo, so on
screen the office answered the turn before. This suite pins both.

Run: python3 scripts/test_the_publish_door_has_a_name.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_RAW = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
CHAT_RAW = (ROOT / 'ui' / 'chat.jsx').read_text(encoding='utf-8')
APP_RAW = (ROOT / 'app.jsx').read_text(encoding='utf-8')
SETTINGS_RAW = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose. The comment written with this fix quotes the
    measured reply, names the door, and describes the placement it
    replaced — every string this suite looks for appears in it."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    i = src.index(opener)
    parens = 0
    j = None
    for k in range(i, len(src)):
        c = src[k]
        if c == '(':
            parens += 1
        elif c == ')':
            parens -= 1
        elif c == '{' and parens == 0:
            j = k
            break
    if j is None:
        raise AssertionError('no body brace found lifting ' + opener)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def const_lift(src, name):
    m = re.search(r'^const ' + name + r' =[\s\S]*?;\s*$', src, re.M)
    if not m:
        raise AssertionError('cannot lift ' + name)
    return m.group(0)


def main():
    print('the publish door has a name')
    runtime = strip_comments(RUNTIME_RAW)
    chat = strip_comments(CHAT_RAW)
    app = strip_comments(APP_RAW)
    settings = strip_comments(SETTINGS_RAW)

    # ── 1. the note is decided ONCE per boss turn, above every route ────
    #
    # Two separate properties, and the first draft got both wrong at the
    # same point in the file. ONCE is #64: attaching it to replies prints
    # it three times on a two-way fan-out. ABOVE EVERY ROUTE is #5eefde5:
    # a mechanism wired to three of four paths is drifting, and `send`
    # has five ways out.
    # `_send`, not `send`: `## 393` put a one-live-turn claim in front of
    # this handler (a doubled Enter used to run the whole turn — and the
    # whole fan-out — twice), so `send` is now a three-line wrapper and the
    # turn with all its routes out lives in `_send`. Everything below is
    # unchanged; only the name of the body being lifted moved.
    send = brace_lift(chat, 'const _send = async () => {')

    check('the office asks about the publish door exactly once per turn',
          send.count('HQ.publishDoorNote(') == 1,
          [send.count('HQ.publishDoorNote('),
           '— once per REPLY is #64: a two-way fan-out prints it three times'])

    # `find`, not `index`. A mutation that deletes the decision outright
    # must be REPORTED by the check below, not raise out of the suite —
    # a fire-test arm that crashes the harness is an arm that proved
    # nothing, and this one did.
    decided = send.find('HQ.publishDoorNote(')
    helper = send.find('const emitDoorNote =')
    first_route = min(
        send.index('if (activeRoom && activeRoom.participants.length)'),
        send.index("text.toLowerCase().startsWith('/brainstorm')"),
    )
    check('it is decided above every route out of the composer',
          0 <= decided < first_route and 0 <= helper < first_route,
          [decided, helper, first_route,
           '— decided inside the @mention block it sits BELOW the room and '
           '/brainstorm routes, which return first; measured: in a meeting '
           'room the note never fired at all'])

    # ── 2. every boss echo is followed by the note, before the dispatch ─
    #
    # The echo sites are found, not listed. A sixth route added later gets
    # checked by construction — which is the whole reason this defect was
    # possible in a file that already had four.
    echoes = [m.start() for m in re.finditer(r"from: 'user'", send)]
    check('every route out of the composer echoes the boss',
          len(echoes) >= 5,
          [len(echoes), '— room, /brainstorm, @mention, handoff, chief of staff'])

    # AFTER the bubble, BEFORE the dispatch. The first version of this
    # check measured from the `from: 'user'` line, which is a few lines
    # INSIDE the object literal being appended — so hoisting the call up
    # between the literal and its own `]);` still read as "after", and the
    # arm that did exactly that came back green. The append has to have
    # closed. `]);` is that close on every route, including the chief of
    # staff's, where the bubble is a named const and the call reads
    # `setChat(prev => [...prev, userMsg]);`.
    unnoted = []
    for pos in echoes:
        rest = send[pos:]
        note = rest.find('emitDoorNote(')
        shut = rest.find(']);')
        disp = rest.find('onDispatchToAgent(')
        if note < 0 or shut < 0 or shut > note or (0 <= disp < note):
            unnoted.append(send[pos:pos + 90].replace('\n', ' '))
    check('the note follows the boss\'s own bubble on every one of them',
          not unnoted,
          [unnoted, '— above the question it answers, the note reads as an '
           'answer to the PREVIOUS reply; that is what was on screen'])

    # ── 3. the same predicate that decides whether the tool is granted ──
    #
    # The note's job is to explain a missing tool. If it ever consults a
    # different flag than the grant does, it explains something that is not
    # what happened — and the boss is sent to a switch that changes nothing.
    check('the grant is gated on icpPublishEnabled()',
          "requires: () => icpPublishEnabled()" in runtime
          and 'if (icpPublishEnabled()) {' in runtime,
          '— publish_site\'s own gate')
    check('...and the note reads that same flag, not one of its own',
          'HQ.icpPublishEnabled && HQ.icpPublishEnabled()' in send,
          '— a second source of truth for "is publishing on" points the '
          'boss at a switch that changes nothing')

    # ── 4. the task path, which has no composer ─────────────────────────
    check('a task run says it too',
          'HQ.publishDoorNote(' in app,
          '— "put the deck live" typed on a task card reaches no composer')

    # ── 5. the door it names is a door that exists ──────────────────────
    #
    # #49 and #68 are both in the ledger and both are this: a note that
    # sends the boss somewhere by its internal name. The setting's id is
    # `icpServices.publish` and the panel is IcpServicesPanel — neither
    # string appears anywhere the boss can read.
    check('the Modules tab is spelled MODULES on screen',
          re.search(r"id: 'icp-services',[^}]*label: 'MODULES'", settings),
          '— the note says "Settings → Modules"')
    check('the row is spelled "Publish to Web" on screen',
          'Publish to Web' in settings,
          '— the note says "Publish to Web"')
    check('the toggle works without the chain bridge',
          'const togglePublish' in settings,
          '— a way forward the boss cannot take is not a way forward')

    # ── 6. what it actually says, and when ──────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the wording checks need it')
    else:
        js = const_lift(runtime, 'ASKS_TO_PUBLISH') + '\n'
        js += brace_lift(runtime, 'function publishDoorNote(') + '\n'
        js += r'''
// The boss asking, in the words they use. The first is the measured turn.
//
// The pattern is a row of alternatives, and EVERY ONE of them needs an ask
// here that no other alternative also matches — otherwise deleting one
// changes nothing and the check that survives is guarding air. The
// measured turn matches two of them at once, so it cannot do that job for
// either; the two bare ones below exist for exactly that reason and for
// no other. (Found by fire-test: dropping `put … live` altogether left
// this suite green.)
const ASKS = [
  'great — now put that lemonade page live on the internet and give me the link.',
  'ship that lemonade page live and send me the link.',   // ship … live
  'publish site/index.html and give me the link.',        // publish
  'deploy the landing page',                              // deploy
  'can this go live today?',                              // go live
  'when does it go live?',
  'put the lemonade page live',                           // put … live, alone
  'make it live on the internet',                         // live on the …, alone
];
// The boss asking for something else. "internet" and "web" are only
// matched behind "live on the", because this is how people ask for a
// SEARCH — and a note about publishing on top of a research question is
// the office answering a question nobody asked.
const NOT_ASKS = [
  'look it up on the internet and summarise it',
  'search the web for lemonade stand pricing',
  'write me a landing page for a lemonade stand',
  "what's in site/index.html?",
  'summarise the live chat transcript',
  'is the shop still live?',
  '',
];
const fired = s => publishDoorNote(s, false) !== null;
console.log(JSON.stringify({
  note:      publishDoorNote(ASKS[0], false),
  missed:    ASKS.filter(s => !fired(s)),
  spurious:  NOT_ASKS.filter(s => fired(s)),
  // With the module ON there is no missing tool, so there is nothing to
  // explain. Every single ask must go quiet.
  whenOn:    ASKS.filter(s => publishDoorNote(s, true) !== null),
  // Callers hand this whatever the composer held.
  nullish:   [publishDoorNote(null, false), publishDoorNote(undefined, false)],
}));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        if p.returncode != 0:
            check('the detector harness runs', False, p.stderr.strip()[:500])
        else:
            R = json.loads(p.stdout)
            note = R['note'] or ''

            check('the measured ask gets a note', bool(note), R['note'])
            check('every way the boss asks to publish gets one',
                  not R['missed'], R['missed'])
            check('asking to read the internet does not',
                  not R['spurious'],
                  [R['spurious'], '— that is how people ask for a SEARCH'])
            check('with the module on the office says nothing',
                  not R['whenOn'],
                  [R['whenOn'], '— nothing is missing, so there is nothing '
                   'to explain'])
            check('an empty composer is not an ask',
                  R['nullish'] == [None, None], R['nullish'])

            check('the note names the switch as the boss sees it',
                  'Publish to Web' in note and 'Settings → Modules' in note,
                  [note, '— #49 and #68 are both a note naming a door by its '
                   'internal name'])
            check('...and never by its internal name',
                  not re.search(r'icp[- ]?services|icpServices|PUBLISH_SITE',
                                note, re.I),
                  note)
            check('it says what is true now, not what is impossible',
                  'switched off' in note and 'yet' in note,
                  [note, '— "publishing is not available in this environment" '
                   'is what the coworker guessed, and it is a dead end'])

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
