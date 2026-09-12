#!/usr/bin/env python3
"""A coworker card may not promise the vault until the vault has answered.

Every capability a card names is conditional — `toolsForAgent` applies a
second test to each claim before it becomes a tool — and app/cast.jsx keeps
those conditions in CAN_DO_NEEDS so the card and the grant say one thing.
'vault' was the exception: no entry, so `grantedTools` and `canDoPhrase`
handed it over on the claim alone.

Measured live on office 9261, 2026-08-16. Kip, tools ['web','vault'], on a
canned brain. Settings → Connections → MARKDOWN VAULT switched to OBSIDIAN
REST with Obsidian closed — one click, the product's own button — and
/vault/status went to `configured: false`. What left his system prompt:

    VAULT_SEARCH  VAULT_READ  VAULT_APPEND
    EXPORT_PPTX   EXPORT_DOCX  EXPORT_PDF
    MEMORY_LIST   MEMORY_READ  MEMORY_WRITE  MEMORY_APPEND

What his card said, before and after, identically: a solid `vault` chip
under "Can use", tooltip "Can read your notes", inside a row whose tooltip
reads "What this coworker is allowed to reach". The row next to it had it
right — `files · off`, dimmed — because 'files' had a condition and 'vault'
did not.

The third surface is the starter brief: `canFileToVault` read the same
claim, so a starter card went on assigning "Save it to Research/<slug>.md"
to a coworker with no tool that can write it.

Guards:
  · every id a card can name has a condition, and it is the condition the
    runtime actually applies
  · the vault fact is read where the grant is, and is SYNCHRONOUS — the
    card renders before a round trip could finish
  · never-asked is not the same as not-there, in both directions
  · the office asks at start-up, and asks again when the answer is dropped
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_the_front_desk_sells_what_exists import (  # noqa: E402
    brace_lift, strip_comments)

CAST = ROOT / 'app' / 'cast.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
APP = ROOT / 'app.jsx'
STARTER = ROOT / 'modals' / 'starter.jsx'

FAILS = []

# id -> (the expression toolsForAgent gates it on, the fact CAN_DO_NEEDS names)
#
# The generalising half. This defect was not "somebody forgot the vault" —
# it was that nothing anywhere asserted the two tables line up, so a claim
# could carry a gate in one file and no condition in the other and every
# suite stayed green. Adding a capability now means adding a row here, and
# a row here cannot be satisfied by a card that promises unconditionally.
GATES = {
    'web':    ("TOOL_REGISTRY.search.requires()",           'canSearch'),
    'vault':  ("await TOOL_REGISTRY.vault_search.requires()", 'vaultOn'),
    'img':    ("s.imageProvider",                            'canMakeImages'),
    'wallet': ("icpWalletEnabled()",                         'moneyOn'),
    'files':  ("agent.elevated",                             'elevated'),
    'code':   ("agent.elevated",                             'elevated'),
}


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('the card waits for the vault to answer')
    cast = CAST.read_text(encoding='utf-8')
    runtime = RUNTIME.read_text(encoding='utf-8')
    app = APP.read_text(encoding='utf-8')
    starter = STARTER.read_text(encoding='utf-8')

    bare = strip_comments(cast)
    can_do = brace_lift(bare, 'const CAN_DO = {')
    needs = brace_lift(bare, 'const CAN_DO_NEEDS = {')
    unlock = brace_lift(bare, 'const CAN_DO_UNLOCK = {')
    grant = brace_lift(runtime, 'async function toolsForAgent(agent, { peers = [], askDepth = 0 } = {}) {')
    facts = brace_lift(runtime, 'function capabilityFacts(subject) {')

    # ── 1. the two tables line up, id by id ──────────────────────────────
    spoken = set(re.findall(r'^\s{2}(\w+):', can_do, re.M))
    unpinned = sorted(spoken - set(GATES))
    check('every capability a card can name is pinned to a gate here',
          not unpinned,
          f'{unpinned} — a new CAN_DO entry has to declare which test '
          'toolsForAgent puts it through, or this suite cannot tell a '
          'promise from a guess')
    for tid in sorted(spoken & set(GATES)):
        expr, fact = GATES[tid]
        check(f"'{tid}' is gated on {expr} in the runtime", expr in grant,
              'the card is describing a condition the grant no longer applies')
        check(f"...and the card's condition for '{tid}' is '{fact}'",
              re.search(r"^\s{2}%s:\s*'%s'" % (tid, re.escape(fact)), needs, re.M) is not None,
              f'CAN_DO_NEEDS.{tid} does not name {fact}; the claim alone '
              'would put it on the card as reach the coworker has')

    # ── 2. the vault fact, read beside the grant ─────────────────────────
    check('the vault condition has a route out, like the other four',
          re.search(r"^\s{2}vault:\s*'[^']+'", unlock, re.M) is not None,
          'a dimmed chip with no unlock line is §7 with the way forward cut')
    check('capabilityFacts reads the vault synchronously',
          'vaultReadySync()' in facts,
          'isVaultReady is a round trip and a card renders now; the card '
          'cannot await it, so it reads the last answer')
    # The whole point. `f.vaultOn = vaultReadySync()` would write `undefined`
    # onto the object, which hasOwnProperty reports as ESTABLISHED — and a
    # card would print "off" for a vault it has never once asked about.
    check('...and leaves the key absent when there has never been an answer',
          re.search(r'vaultOn\s*!==\s*undefined', facts) is not None
          and re.search(r'f\.vaultOn\s*=\s*vaultReadySync\(\)', facts) is None,
          'absent and false are different facts; `established` in cast.jsx '
          'reads presence, not truthiness')
    sync = brace_lift(runtime, 'function vaultReadySync() {')
    check('the reader can tell never-asked from answered-no',
          '_vaultConfiguredCache.at ?' in sync and 'undefined' in sync,
          sync)

    # ── 3. the answer is recorded on BOTH branches ───────────────────────
    probe = brace_lift(runtime, 'async function isVaultReady() {')
    check('a successful probe is recorded through the notifier',
          probe.count('_noteVaultReady(') == 2,
          f'{probe.count("_noteVaultReady(")} of 2 — the catch branch counts: '
          'an office that cannot be reached grants no vault tools either, and '
          'a card that never hears about it goes on promising them')
    check('...and the notifier only wakes watchers when something moved',
          re.search(r'if \(changed\)', brace_lift(runtime, 'function _noteVaultReady(ok, now) {')) is not None)
    clear = brace_lift(runtime, 'function clearVaultReadyCache() {')
    check('dropping the answer tells the watchers it was dropped',
          'undefined' in clear and '_vaultWatchers' in clear,
          'Settings → Connections clears this after a backend swap; without '
          'the nudge every card sits on the unknown branch until the next '
          'dispatch happens to probe')

    # ── 4. somebody actually asks ────────────────────────────────────────
    check('the office probes the vault at start-up',
          'HQ.isVaultReady()' in app,
          'nothing else calls it until a coworker is dispatched, so the card '
          'would spend the whole first session saying nothing')
    check('...and subscribes, so the answer arriving repaints the cards',
          'HQ.onVaultReadyChange(' in app)
    check('...and asks again when the answer is dropped',
          re.search(r'ok === undefined\s*\)\s*ask\(\)', app) is not None,
          'clearVaultReadyCache reports undefined; something has to re-arm')

    # ── 5. the third surface: the brief a starter card writes ────────────
    can_file = brace_lift(starter, 'function canFileToVault(agent) {')
    check('the starter brief checks the vault, not just the checkbox',
          'vaultReadySync()' in can_file,
          '"Save it to Research/<slug>.md" handed to a coworker with no '
          'VAULT_NEW is a snag the office wrote itself')
    check('...and treats an unanswered vault as no',
          '=== true' in can_file,
          'a truthy test would let `undefined` through and put the path back '
          'in the brief on every fresh load')

    # ── 6. drive the fact plumbing ───────────────────────────────────────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
    else:
        lifted = '\n'.join([
            'let _vaultConfiguredCache = { at: 0, ok: false };',
            # #400 — the probe now reads this epoch before it suspends and
            # re-checks it before writing, so a clearVaultReadyCache() landing
            # mid-probe is not undone by the old vault's answer arriving after
            # it. Declared here beside the cache it guards, the way the file
            # declares it; nothing in this harness clears mid-probe, so it only
            # has to exist. The mid-probe clear itself is
            # test_the_card_got_picked_up_while_you_were_deciding.py's job.
            'let _vaultCacheEpoch = 0;',
            'const _vaultWatchers = new Set();',
            brace_lift(runtime, 'function _noteVaultReady(ok, now) {'),
            brace_lift(runtime, 'async function isVaultReady() {'),
            brace_lift(runtime, 'function clearVaultReadyCache() {'),
            brace_lift(runtime, 'function vaultReadySync() {'),
            brace_lift(runtime, 'function onVaultReadyChange(fn) {'),
        ])
        # Clock and transport both under the harness's thumb: the 5s window
        # and the throwing-probe branch are the two behaviours a live office
        # cannot be asked to demonstrate on cue.
        #
        # The clock starts at 1000 on purpose — smaller than the window. A
        # freshness test written as `now - at < 5000` reads a never-asked
        # cache (`at: 0`) as fresh and hands back its placeholder `false`,
        # which a real browser clock hides and this one does not.
        harness = '''
let NOW = 1000;
Date.now = () => NOW;
let status = { configured: true, exists: true };
let calls = 0;
let boom = false;
const CafresoHQClient = {
  vaultStatus: async () => { calls++; if (boom) throw new Error('offline'); return status; },
};
const seen = [];
const R = {};
// JSON.stringify DROPS keys whose value is `undefined`, and the whole
// subject here is the difference between undefined and false — so the
// shrug crosses the wire as a word rather than as a missing key.
const enc = v => v === undefined ? 'never-asked' : v;
R.beforeAnyProbe = vaultReadySync() === undefined;
const off = onVaultReadyChange(v => seen.push(enc(v)));
onVaultReadyChange(() => { throw new Error('a watcher blew up'); });

R.first = await isVaultReady();
R.afterFirst = enc(vaultReadySync());
R.callsAfterFirst = calls;
// Inside the window: no second round trip, and no second wake-up.
NOW += 1000;
await isVaultReady();
R.callsWhileFresh = calls;
// The boss closes Obsidian. Past the window, the answer moves.
NOW += 9000;
status = { configured: false, exists: false };
R.second = await isVaultReady();
R.afterSecond = enc(vaultReadySync());
// Unchanged answers must not spam the watchers.
NOW += 9000;
await isVaultReady();
// The office itself goes away: unknown to us, but the coworker gets nothing
// either way, so it is recorded rather than left blank.
NOW += 9000;
boom = true;
status = { configured: true, exists: true };
R.third = await isVaultReady();
R.afterThird = enc(vaultReadySync());
// A backend swap in Settings drops the answer entirely.
clearVaultReadyCache();
R.afterClear = vaultReadySync() === undefined;
R.seen = seen;
off();
NOW += 9000;
boom = false;
await isVaultReady();
R.seenAfterOff = seen.length;
console.log(JSON.stringify(R));
'''
        p = subprocess.run(['node', '--input-type=module', '-e', lifted + harness],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            print(p.stdout)
            print(p.stderr[-1500:], file=sys.stderr)
            raise SystemExit('node harness failed on source lifted from the app')
        out = json.loads(p.stdout.strip().split('\n')[-1])

        check('a card asking before anyone has probed gets a shrug',
              out['beforeAnyProbe'] is True)
        check('the first probe answers and is remembered',
              out['first'] is True and out['afterFirst'] is True,
              f"{out['first']} / {out['afterFirst']}")
        check('...over the wire, because never-asked is not fresh',
              out['callsAfterFirst'] == 1,
              f"{out['callsAfterFirst']} calls — the window was measured "
              'against `at: 0` and the placeholder was served as an answer')
        check('a second look inside the window does not re-ask',
              out['callsWhileFresh'] == 1, str(out['callsWhileFresh']))
        check('a vault that stops answering is noticed',
              out['second'] is False and out['afterSecond'] is False,
              f"{out['second']} / {out['afterSecond']}")
        check('an unreachable office is recorded, not left unknown',
              out['third'] is False and out['afterThird'] is False,
              f"{out['third']} / {out['afterThird']} — leaving it unknown "
              'would drop the chip instead of dimming it, and the coworker '
              'gets no vault tools in either case')
        check('a backend swap puts it back to never-asked',
              out['afterClear'] is True)
        # true, false, undefined — and nothing between: the repeat probes at
        # each state must not fire. A watcher that wakes on every poll would
        # repaint the roster four times a minute for no reason.
        check('watchers hear each move once, and only moves',
              out['seen'] == [True, False, 'never-asked'], str(out['seen']))
        check('...and a watcher that throws does not break the probe',
              out['afterThird'] is False,
              'the second subscriber raises on every notification')
        check('unsubscribing stops the notifications',
              out['seenAfterOff'] == 3, str(out['seenAfterOff']))

    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed')
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
