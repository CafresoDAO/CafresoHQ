#!/usr/bin/env python3
"""A stalled workflow reported itself as running.

Measured 2026-08-16 on office 9280, against a canned brain. Two tasks,
"Alpha probe one three one" and "Beta probe one three one", chained into a
workflow named "Alpha then Beta" with auto-dispatch ON. Step one's coworker
answered every turn with

    Let me look at the alpha figures on file before I answer.

    [VAULT_READ: Research/alpha-figures.md]

and the tool budget ran out. #127 handled that part correctly: the card
parked in `doing`, blockedReason set, feed row `stopped part-way through
"Alpha probe one three one"`, XP `snag`, ▶ START on the card.

Then the pipeline stopped, and nothing in the office said so.

    tasks.json   Beta: status "inbox", assignedTo null, stalledNote ABSENT
    the board    `✕ | Beta probe one three one | Assign… |
                  Local Brain · Generalist | MED | → CHAT | 📋 ROOM`
                 — pixel-identical to a card nobody has got to
    the feed     last word on the whole thing was step one's own snag
    the word "workflow" appeared NOWHERE on the board
    ⛓ Workflows  "ALPHA THEN BETA · 0/2 done · 1 in progress"

The last line is the lie, and it is the only status readout a boss has for
a pipeline: `1 in progress` was step one, parked. #86 ruled that a parked
snag is not work in flight; three surfaces learned it and this counter
never did.

The rest is the silence. `depsReady` was computed — step two depends on
step one, step one is not `done` — and the answer was dropped on the
floor: no dispatch, no approval, no row, no note. The office knew exactly
which step was holding the chain and told nobody, which is #127's lesson
arriving a second time on a different surface.

Run: python3 scripts/test_a_stalled_workflow_says_so.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
FLOOR = (ROOT / 'app' / 'floor.jsx').read_text(encoding='utf-8')
WORKLOG = (ROOT / 'app' / 'worklog.jsx').read_text(encoding='utf-8')
COLLAB = (ROOT / 'modals' / 'collab.jsx').read_text(encoding='utf-8')
PANELS = (ROOT / 'ui' / 'panels.jsx').read_text(encoding='utf-8')
CORE = (ROOT / 'views' / 'core.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Scan code, never prose. Every comment in the fix quotes the wrong
    reading it replaced — including the literal `1 in progress`."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, opener):
    """Body by brace matching; the opener is the first `{` at paren depth 0."""
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


def module_source(path, extra=''):
    """A whole import-free module, minus its import/export lines, for node."""
    text = (ROOT / path).read_text(encoding='utf-8')
    body = '\n'.join(ln for ln in text.split('\n')
                     if not ln.startswith('import ') and not ln.startswith('export '))
    return body + '\n' + extra


def node(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=90)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr[-1500:], file=sys.stderr)
        return None
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('a stalled workflow says so')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = strip_comments(APP)
    chain = brace_lift(app, 'if (task.chainTo) {')

    # ── 1. the answer survives the question ──────────────────────────────
    #
    # `depsReady` was a boolean, and by the time the office wanted to say
    # WHICH step was holding the chain the answer no longer existed. Same
    # shape as #127's `ranOutOfHops`: the fact was computed and discarded in
    # the same expression.
    check('the chain check keeps which steps are holding it, not just whether',
          re.search(r'const blockedBy = \(nextTask\.dependsOn \|\| \[\]\)', chain)
          and 'const depsReady = blockedBy.length === 0;' in chain,
          [chain[:400], '— a boolean cannot be shown to the boss'])
    check('...and a dependency that has been deleted counts as holding it',
          re.search(r'\.filter\(dep => !dep \|\| dep\.status !== .done.\)', chain),
          '— `!dep` is a step someone removed mid-pipeline; the chain is '
          'just as stuck and the successor just as silent')
    check('the hold has an else at all',
          re.search(r'if \(depsReady\) \{[\s\S]*\n {10}\} else \{', chain),
          '— this branch was the whole defect: no dispatch, no approval, '
          'no row, no note')

    # ── 2. the waiting card is the one that says it ──────────────────────
    #
    # The step that stopped already explains itself. The card that looks
    # wrong is the untouched-looking one in the inbox, and `stalledNote` is
    # the field whose entire job is "why is this sitting in the inbox" —
    # rendered by features.jsx, cleared by START.
    hold = chain[chain.index('} else {'):]
    check('the note lands on the WAITING card, not the one that stopped',
          re.search(r'setTasks\(prev => prev\.map\(t => t\.id === nextTask\.id', hold),
          [hold[:400], '— the stopped card already has blockedReason'])
    check('...in stalledNote, the field START clears',
          'stalledNote: holdNote' in hold,
          '— a note about a wait that is over must not outlive the wait')
    check('...and the office says it in the feed as well',
          "action: 'blocked'" in hold and 'taskId: nextTask.id' in hold,
          '— the card is only seen by someone already looking at the board, '
          'and this is the one workflow event that happens to a task nobody '
          'is working on')
    check("the feed's 'blocked' rows have a glyph of their own",
          re.search(r"blocked: '⛓'", PANELS),
          "ui/panels.jsx: INSPECT_ACT_ICON falls back to '✦' for an unknown "
          'action, which is the icon for "something happened"')
    # Two panels render these rows off two copies of the same map. Adding
    # the action to one and not the other was measured on the live board:
    # ⛓ on the coworker's card, ✦ in the inbox, for the same event.
    check('...in both of the feeds that render them',
          re.search(r"blocked: '⛓'", CORE),
          'views/core.jsx: ACT_ICON is the twin of INSPECT_ACT_ICON and the '
          'row is the same row')
    # Both of those panels print the icon in front of the text, so a glyph
    # in the text too came out "⛓ … ⛓". The rows that DO carry a trailing
    # glyph carry a different one, because it says a second thing.
    check('...and the row does not print the glyph twice',
          '⛓' not in hold,
          [re.findall(r'text: `[^`]*`', hold),
           '— the icon is the icon\'s job'])

    # ── 3. the sentence has one author ───────────────────────────────────
    check('the hold sentence is built by the shared floor vocabulary',
          'chainHoldLine(' in hold
          and re.search(r'^import \{[^}]*\bchainHoldLine\b', APP, re.M),
          '— app.jsx must not write a second copy of a sentence app/floor.jsx '
          'owns; that is how three surfaces start giving three accounts')
    check('...and it is told whether the office will start the step itself',
          re.search(r'chainHoldLine\(\s*blockedBy\.map\(dep => dep && dep\.title\), !!task\.autoDispatch\)',
                    hold),
          [hold, '— without auto-dispatch the office asks first, and promising '
           'a boss it runs on its own is how a pipeline sits still while '
           'everyone believes it is moving'])

    # ── 4. the counter stops calling a parked step "in progress" ─────────
    collab = strip_comments(COLLAB)
    check('the workflow row asks whether a step is parked',
          'const parked = known.filter(isParked).length;' in collab
          and "const doing = known.filter(t => t.status === 'doing' && !isParked(t)).length;" in collab,
          [re.findall(r'.*const doing = .*', collab),
           "— `status === 'doing'` was the whole test, and it read a stopped "
           'pipeline as a moving one'])
    check('...reading the one predicate, not a fourth copy of it',
          re.search(r"^import \{ isParked \} from '\.\./app/worklog\.jsx';", COLLAB, re.M),
          'modals/collab.jsx: #86 has been re-derived at three sites already')
    check('...and a parked step is named on the row',
          re.search(r"bits\.push\(`\$\{parked\} stopped — needs you`\)", collab),
          '— folding it into silence leaves `0/2 done` on a pipeline that '
          'will never move again; the stopped step is the one thing the boss '
          'can act on')

    # ── 5. the predicate, run for real ───────────────────────────────────
    R = node(module_source('app/worklog.jsx', r'''
const C = {
  'a card the boss has not started':        { status: 'inbox' },
  'a run actually in flight':               { status: 'doing' },
  'a run in flight with a cleared reason':  { status: 'doing', blockedReason: '' },
  'a step that stopped part-way':           { status: 'doing', blockedReason: 'they did as much as they can in one go and stopped there.' },
  'a coworker who said they are blocked':   { status: 'doing', blockedReason: 'waiting on the API key' },
  'a finished job':                         { status: 'done' },
  'a finished job with a stale reason':     { status: 'done', blockedReason: 'x' },
  'nothing at all':                         null,
};
const out = {};
for (const k of Object.keys(C)) out[k] = isParked(C[k]);
console.log(JSON.stringify(out));
'''))
    if R is None:
        check('the isParked harness runs', False, 'node failed')
    else:
        want = {
            'a card the boss has not started': False,
            'a run actually in flight': False,
            'a run in flight with a cleared reason': False,
            'a step that stopped part-way': True,
            'a coworker who said they are blocked': True,
            'a finished job': False,
            'a finished job with a stale reason': False,
            'nothing at all': False,
        }
        for k, w in want.items():
            check('%s → %s' % (k, 'parked' if w else 'not parked'),
                  R.get(k) is w, 'got %r' % (R.get(k),))

    # ── 5b. and the card renders it whole ────────────────────────────────
    #
    # Found while verifying the fix, on the same screen, both honesty lines
    # cut mid-word at 140 characters:
    #
    #   ✋ …carries nothing over, so a narrower bri
    #   ↩ …Finish it and this starts on
    #
    # §7's way forward is the last clause of both, which is exactly what a
    # hard character cut eats. "Finish it and this starts on" is not a
    # shorter version of the sentence.
    feat = strip_comments((ROOT / 'features.jsx').read_text(encoding='utf-8'))
    check('the card cuts its honesty lines on a word, not a character count',
          'cardNote(t.stalledNote)' in feat and 'cardNote(t.blockedReason)' in feat
          and 'slice(0, 140)' not in feat,
          [re.findall(r'.*slice\(0, 140\).*', feat),
           '— both lines put the boss\'s next move at the end'])
    check('...and hands the whole sentence to the hover',
          feat.count("+ String(t.stalledNote)") == 1
          and feat.count("+ String(t.blockedReason)") == 1,
          '— the cut one is the one that fits, not the one that is true')

    N = node(module_source('app/worklog.jsx', r'''
const LONG = 'waiting on "Alpha probe one three one" — that step has not delivered '
  + 'yet, so this one has nothing to work from. Finish it and the office will ask '
  + 'you before starting this, which makes this sentence longer than any card line '
  + 'the office writes for itself, and therefore the one case the cut has to handle.';
const out = {
  full:           LONG,
  shortUntouched: cardNote('hit a snag'),
  exactlyAtCap:   cardNote('y'.repeat(240)),
  overCap:        cardNote(LONG),
  noSpaces:       cardNote('z'.repeat(400)),
  collapses:      cardNote('  two   words\n  here  '),
  empty:          cardNote(''),
  nullish:        cardNote(null),
  smallCap:       cardNote('one two three four five', 12),
};
console.log(JSON.stringify(out));
'''))
    if N is None:
        check('the cardNote harness runs', False, 'node failed')
    else:
        check('a note that fits is left exactly alone',
              N['shortUntouched'] == 'hit a snag', N['shortUntouched'])
        check('...and so is one right at the cap',
              N['exactlyAtCap'] == 'y' * 240, len(N['exactlyAtCap']))
        body = N['overCap'][:-1]
        check('a long note says it was cut',
              N['overCap'].endswith('…') and not body.endswith(' '),
              N['overCap'][-40:])
        check('...and it is still the office\'s own sentence, from the start',
              N['full'].startswith(body), [body[-40:], N['full'][:len(body)][-40:]])
        check('...ending on a whole word',
              body.split(' ')[-1] in N['full'].split(' '),
              body.split(' ')[-1])
        check('...and no longer than the cap',
              len(N['overCap']) <= 240, len(N['overCap']))
        # A 400-character token has no word boundary to back up to, and
        # losing three-fifths of the line hunting one is worse than the cut.
        check('a note with nothing to break on is still cut, and still says so',
              N['noSpaces'].endswith('…') and len(N['noSpaces']) == 240,
              [N['noSpaces'][:30], len(N['noSpaces'])])
        check('whitespace is collapsed so the line stays a line',
              N['collapses'] == 'two words here', repr(N['collapses']))
        check('nothing in, nothing out', N['empty'] == '' and N['nullish'] == '',
              [N['empty'], N['nullish']])
        check('the cap is a parameter, and honoured',
              len(N['smallCap']) <= 12 and N['smallCap'].endswith('…'),
              N['smallCap'])

    # ── 6. the sentence itself ───────────────────────────────────────────
    S = node(module_source('app/floor.jsx', r'''
const out = {
  auto:     chainHoldLine(['Alpha probe one three one'], true),
  manual:   chainHoldLine(['Alpha probe one three one'], false),
  two:      chainHoldLine(['Draft the brief', 'Check the figures'], true),
  three:    chainHoldLine(['A', 'B', 'C'], false),
  deleted:  chainHoldLine([null], true),
  none:     chainHoldLine([], true),
  longName: chainHoldLine(['x'.repeat(90)], true),
  messy:    chainHoldLine(['  Draft\n  the   brief  '], true),
};
console.log(JSON.stringify(out));
'''))
    if S is None:
        check('the chainHoldLine harness runs', False, 'node failed')
    else:
        check('it names the step being waited on',
              '"Alpha probe one three one"' in S['auto'], S['auto'])
        check('auto-dispatch promises the office will start it',
              'starts on its own' in S['auto']
              and 'ask you' not in S['auto'], S['auto'])
        # The half that was easiest to get wrong, and the reason this
        # splits at all: with step-approve the boss has to stamp it, and
        # "this starts on its own" would leave them waiting on the office
        # while the office waits on them.
        check('step-approve promises the office will ask first',
              'the office will ask you before starting this' in S['manual']
              and 'on its own' not in S['manual'], S['manual'])
        check('two blockers read as two, in one sentence',
              '"Draft the brief" and "Check the figures"' in S['two']
              and 'those steps have' in S['two'], S['two'])
        check('three blockers get their commas',
              '"A", "B" and "C"' in S['three'], S['three'])
        # A deleted dependency has no title to give. It must not become
        # `waiting on ""` — the office saying it is waiting on nothing.
        check('a deleted dependency is still a reason, not an empty quote',
              'an earlier step' in S['deleted'] and '""' not in S['deleted'],
              S['deleted'])
        check('...and so is a step list that is empty',
              'an earlier step' in S['none'] and '""' not in S['none'], S['none'])
        check('a long title is cut, like every other title on a card',
              len(S['longName']) < 220 and 'x' * 41 not in S['longName'],
              S['longName'])
        check('a title with newlines in it stays one line',
              '\n' not in S['messy'] and '"Draft the brief"' in S['messy'],
              S['messy'])
        # §6: the boss's language. No ids, no field names, no "dependsOn".
        for word in ('dependsOn', 'chainTo', 'autoDispatch', 'depsReady', 'null'):
            check('...and says nothing about %s' % word,
                  word not in S['auto'] + S['manual'] + S['deleted'], word)

    # ── 7. the gate, run for real ────────────────────────────────────────
    #
    # The real `if (depsReady) … else …` shape, lifted from app.jsx and
    # driven over the reproduced pipeline. Everything the branch calls is
    # stubbed to a log, so what is measured is which of the three things
    # the office does — dispatch, ask, hold — and on which card.
    # The WHOLE `if (nextTask …)` statement, guard included: "already
    # started by hand" is one of the cases under test, and it is that guard
    # that decides it.
    inner = brace_lift(chain, "if (nextTask && nextTask.status === 'inbox') {")
    H = node(module_source('app/floor.jsx', r'''
const RUN = (tasksNow, task, nextId) => {
  const log = { dispatched: null, asked: null, notes: [], rows: [] };
  const tasksRef = { current: tasksNow };
  const nextTask = tasksNow.find(t => t.id === nextId);
  const agent = { id: 'a1', name: 'Local Brain', color: '#fff' };
  // In scope at the real call site, and the wrong answer to "which card is
  // this row about" — so the harness has to offer it, or swapping
  // `nextTask.id` for it would only ever be caught as a ReferenceError.
  const taskId = task.id;
  const cleanBuf = 'the stall text';
  const HQ = { uid: () => 'wf_x' };
  const triggerChainStep = (t) => { log.dispatched = t.id; };
  const onApprovalRequest = (a) => { log.asked = a.title; };
  const setTasks = (fn) => fn(tasksNow).forEach(t => {
    if (t.stalledNote) log.notes.push([t.id, t.stalledNote]); });
  const logActivity = (r) => log.rows.push([r.action, r.taskId, r.text]);
''' + inner + r'''
  return log;
};
const STOPPED = { id: 't1', title: 'Alpha probe one three one', status: 'doing',
                  blockedReason: 'they stopped there', chainTo: 't2', autoDispatch: true };
const DONE    = Object.assign({}, STOPPED, { status: 'done', blockedReason: '' });
const NEXT    = { id: 't2', title: 'Beta probe one three one', status: 'inbox',
                  dependsOn: ['t1'], autoDispatch: true };
const out = {
  held:      RUN([STOPPED, NEXT], STOPPED, 't2'),
  delivered: RUN([DONE, NEXT], DONE, 't2'),
  manual:    RUN([STOPPED, Object.assign({}, NEXT, { autoDispatch: false })],
                 Object.assign({}, STOPPED, { autoDispatch: false }), 't2'),
  gone:      RUN([STOPPED, Object.assign({}, NEXT, { dependsOn: ['t9'] })], STOPPED, 't2'),
  started:   RUN([STOPPED, Object.assign({}, NEXT, { status: 'doing' })], STOPPED, 't2'),
};
console.log(JSON.stringify(out));
'''))
    if H is None:
        check('the chain-gate harness runs', False, 'node failed')
    else:
        held = H['held']
        check('a step held by a stopped predecessor is not dispatched',
              held['dispatched'] is None and held['asked'] is None, held)
        check('...and it is not left looking untouched',
              len(held['notes']) == 1 and held['notes'][0][0] == 't2'
              and 'Alpha probe one three one' in held['notes'][0][1], held['notes'])
        check('...and the feed carries a row naming the waiting step',
              len(held['rows']) == 1 and held['rows'][0][0] == 'blocked'
              and held['rows'][0][1] == 't2'
              and 'Beta probe one three one' in held['rows'][0][2], held['rows'])
        # The other half of the fix, and the one a careless guard breaks: a
        # pipeline that DOES deliver must still run, silently, as before.
        deliv = H['delivered']
        check('a step whose predecessor delivered still auto-dispatches',
              deliv['dispatched'] == 't2', deliv)
        check('...and says nothing about waiting',
              not deliv['notes'] and not deliv['rows'], deliv)
        check('a held step under step-approve gets the asking sentence',
              H['manual']['notes'] and 'ask you' in H['manual']['notes'][0][1],
              H['manual']['notes'])
        check('a dependency that no longer exists holds the chain and says so',
              H['gone']['dispatched'] is None and len(H['gone']['notes']) == 1
              and 'an earlier step' in H['gone']['notes'][0][1], H['gone'])
        # Somebody already started it by hand: there is nothing to explain,
        # and a note reading "waiting on…" over a running card is a new lie.
        check('a step the boss already started is left alone entirely',
              H['started']['dispatched'] is None and not H['started']['notes']
              and not H['started']['rows'], H['started'])

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
