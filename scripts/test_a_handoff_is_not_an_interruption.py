#!/usr/bin/env python3
"""#129 — a chain step refused for a conversation that never happened.

Reproduced live on office 9280, 2026-08-16. Workflow ALPHA THEN BETA, two
steps, auto-dispatch on, both steps owned by the same coworker. Alpha was
pointed at a canned reply that delivers:

    DONE · 2   Alpha probe one three one · ✓ finished
               "The alpha figure is 34. It is the mean of the three
                quarterly readings on file (31, 34, 37)…"
    INBOX · 1  Beta probe one three one
               ↩ Local Brain was mid-conversation when this step came up —
                 start it when they're free
    the feed   progress | tk_lanwg |
               couldn't pick up "Beta probe one three one" — mid-conversation

There was no conversation. `agentAbortersRef` holds one entry per coworker
and the guard asked only whether one EXISTED; the chain dispatches from the
tail of the finishing step's `try` and that step's `endAgentRun` sits in the
`finally` below it, so the step that had just delivered was still in the
registry when it handed over. Alpha's card was `done` by then, so
`displacedTask` found nothing and the run fell through to the branch whose
sentence names a chat.

The discriminating measurement: started by hand a minute later, the same
card on the same desk ran first time and delivered. The only thing that
changed was who dispatched it.

So the question the guard asks is now about IDENTITY, not presence: is the
registered run the one handing this over, or somebody else's? The suite
pins that, and pins that the two guards it feeds still fire for every case
they were built for — a real chat mid-flight, a real card mid-run, and the
boss driving rather than automation.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
RUNTIME = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


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


def node(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=90)
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr[-1500:], file=sys.stderr)
        return None
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('a hand-off is not an interruption')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    drop = brace_lift(APP, 'const onTaskDropOnAgent = async (taskId, agent, taskFresh, opts = {}) => ')

    # ── 1. the question the desk asks ────────────────────────────────────
    #
    # Presence of a registry entry was the whole test, and a pipeline's own
    # last breath is a registry entry.
    check('the desk asks WHICH run is on it, not whether one is',
          re.search(r'const priorRun = agentAbortersRef\.current\.get\(agent\.id\);', drop)
          and re.search(r'const handingOver = !!\(opts\.fromRun && priorRun === opts\.fromRun\);', drop)
          and re.search(r'const running = !!priorRun && !handingOver;', drop),
          [drop[:200],
           '— identity, because the finishing step is in the registry when '
           'it dispatches the next one'])
    check('...and neither guard reads the registry behind its back',
          'agentAbortersRef.current.has(agent.id)' not in drop,
          [re.findall(r'.*agentAbortersRef\.current\.has\(agent\.id\).*', drop),
           '— a second lookup is a second answer'])
    check('the displaced-card guard is fed the same answer',
          re.search(r'HQ\.displacedTask\(tasks, agent\.id, taskId, running\)', drop),
          '— a hand-off does not displace the card it is handing over from')
    check('the mid-conversation guard is fed the same answer',
          re.search(r'const chatCut = !displaced && running;', drop),
          '— this is the branch that wrote the sentence about a chat that '
          'never happened')

    # ── 2. the run is handed over, not guessed at ────────────────────────
    check("the chain hands over its own run",
          re.search(r'triggerChainStep\(nextTask, cleanBuf, agent, controller\)', APP),
          '— `controller` is this run\'s registry entry; without it the desk '
          'has nothing to compare against')
    check('...and triggerChainStep carries it through',
          re.search(r'const triggerChainStep = React\.useCallback\(\(nextTask, priorResult, fromAgent, fromRun\)', APP)
          and re.search(r'onTaskDropOnAgent\(nextTask\.id, agent, null, \{ auto: true, priorResult, fromRun \}\)', APP),
          [re.findall(r'onTaskDropOnAgent\(nextTask[^;]*;', APP),
           '— dropped in the middle and the desk is back to guessing'])
    # The approval path fires from the boss's stamp, long after the run that
    # asked has left the registry. Passing a controller there would be a
    # claim about a run that no longer exists.
    check('the approval path hands over nothing, and that is right',
          re.search(r"triggerChainStep\(nextTask, ap\.priorResult \|\| '', fromAgent \|\| null\);", APP),
          '— by the time the boss stamps a step, the asking run is gone from '
          'the registry, so there is nothing to be mistaken for it')

    # ── 3. the guards, driven ────────────────────────────────────────────
    #
    # The real prelude, lifted out of app.jsx: everything from the desk
    # question down to the end of the mid-conversation branch. Reaching the
    # end means the card would have started.
    start = drop.index('const priorRun = agentAbortersRef.current.get(agent.id);')
    tail = drop[start:]
    prelude = tail[:tail.index('if (chatCut) {')] + brace_lift(tail, 'if (chatCut) {')
    displaced_fn = brace_lift(RUNTIME, 'function displacedTask(tasks, agentId, taskId, running)')

    harness = displaced_fn + '''

const RUN_A = { name: 'runA' };   /* the finishing step's controller */
const RUN_CHAT = { name: 'runChat' };

async function drive(scene) {
  const notes = [], rows = [], asked = [];
  const agent = { id: 'ag1', name: 'Local Brain', color: '#fff' };
  const task = { id: scene.taskId, title: scene.title };
  const taskId = scene.taskId;
  const tasks = scene.tasks;
  const opts = scene.opts;
  const HQ = { displacedTask };
  const agentAbortersRef = { current: new Map(scene.registry || []) };
  /* #390 added startingTaskIdsRef (a Set claimed synchronously at the top of
     onTaskDropOnAgent) and its releaseStartClaim() helper, called on every
     path that doesn't end in a real dispatch. The prelude lifted below starts
     after the claim, so the harness only needs the release to exist; a no-op
     keeps this a test of the hand-off guards. */
  const releaseStartClaim = () => {};
  const setTasks = (fn) => {
    const out = fn(tasks);
    for (const t of out) {
      const before = tasks.find(x => x.id === t.id);
      if (before && before.stalledNote !== t.stalledNote && t.stalledNote) {
        notes.push([t.id, t.stalledNote]);
      }
    }
  };
  const logActivity = (e) => rows.push([e.action, e.taskId, e.text]);
  const window = { hqConfirm: async (msg) => { asked.push(msg); return scene.answer !== false; } };
  const outcome = await (async () => {
''' + prelude + '''
    return 'started';
  })();
  return { outcome: outcome || 'parked', notes, rows, asked };
}

const AG = 'ag1';
const BETA = { id: 't2', title: 'Beta probe one three one', status: 'inbox' };
const ALPHA_DONE = { id: 't1', title: 'Alpha probe one three one', status: 'done', assignedTo: AG };
const OTHER_DOING = { id: 't3', title: 'Summarise the vendor notes', status: 'doing', assignedTo: AG };
const OTHER_PARKED = { id: 't4', title: 'Chase the invoice', status: 'doing', assignedTo: AG,
                       blockedReason: 'needs a password' };

const out = {};

/* The measured case: the pipeline hands over while its own run is still
   the registered one. */
out.handoff = await drive({
  taskId: 't2', title: BETA.title, tasks: [ALPHA_DONE, BETA],
  registry: [[AG, RUN_A]], opts: { auto: true, priorResult: 'the alpha figure is 34', fromRun: RUN_A },
});

/* Same hand-off, but the boss opened a chat with that coworker while the
   card ran — beginAgentRun evicted the card's controller, so the entry is
   not the one being handed over. The guard must still fire. */
out.chatDuringRun = await drive({
  taskId: 't2', title: BETA.title, tasks: [ALPHA_DONE, BETA],
  registry: [[AG, RUN_CHAT]], opts: { auto: true, fromRun: RUN_A },
});

/* The original #90 case, untouched: the boss starts a card by hand on a
   desk that is mid-conversation. */
out.bossOverChat = await drive({
  taskId: 't2', title: BETA.title, tasks: [BETA],
  registry: [[AG, RUN_CHAT]], opts: {}, answer: true,
});
out.bossOverChatDeclined = await drive({
  taskId: 't2', title: BETA.title, tasks: [BETA],
  registry: [[AG, RUN_CHAT]], opts: {}, answer: false,
});

/* A chain step landing on a desk genuinely running another CARD. */
out.chainOverCard = await drive({
  taskId: 't2', title: BETA.title, tasks: [OTHER_DOING, BETA],
  registry: [[AG, RUN_CHAT]], opts: { auto: true },
});

/* A hand-off onto a desk whose other card is parked, not running: nothing
   to displace, nothing to cut into. */
out.handoffPastParked = await drive({
  taskId: 't2', title: BETA.title, tasks: [ALPHA_DONE, OTHER_PARKED, BETA],
  registry: [[AG, RUN_A]], opts: { auto: true, fromRun: RUN_A },
});

/* A hand-off onto a desk that still shows another card in `doing`. One
   coworker, one run — so if the registry holds only the run handing over,
   that other card is not running either, whatever its column says. */
out.handoffPastDoing = await drive({
  taskId: 't2', title: BETA.title, tasks: [ALPHA_DONE, OTHER_DOING, BETA],
  registry: [[AG, RUN_A]], opts: { auto: true, fromRun: RUN_A },
});

/* An idle desk, either driver. */
out.idleChain = await drive({
  taskId: 't2', title: BETA.title, tasks: [ALPHA_DONE, BETA],
  registry: [], opts: { auto: true, fromRun: RUN_A },
});
out.idleBoss = await drive({
  taskId: 't2', title: BETA.title, tasks: [BETA], registry: [], opts: {},
});

/* A stale controller nobody registered must not unlock the desk. */
out.staleHandoff = await drive({
  taskId: 't2', title: BETA.title, tasks: [ALPHA_DONE, BETA],
  registry: [[AG, RUN_CHAT]], opts: { auto: true, fromRun: { name: 'ghost' } },
});

console.log(JSON.stringify(out));
'''

    N = node(harness)
    if N is None:
        check('the desk-guard harness runs', False, 'node failed')
    else:
        h = N['handoff']
        check('the pipeline\'s own hand-off starts the next step',
              h['outcome'] == 'started', [h['outcome'], h['notes'], h['rows']])
        check('...and says nothing about it, because nothing happened',
              h['notes'] == [] and h['rows'] == [] and h['asked'] == [], h)

        c = N['chatDuringRun']
        check('a chat opened during the run still stops the hand-off',
              c['outcome'] == 'parked', c)
        check('...on the waiting card, in the field that explains an inbox card',
              [n[0] for n in c['notes']] == ['t2']
              and 'mid-conversation' in c['notes'][0][1], c['notes'])
        check('...and in the feed',
              [r[0] for r in c['rows']] == ['progress']
              and 'mid-conversation' in c['rows'][0][2], c['rows'])
        # A stale controller is not a key to the desk.
        s = N['staleHandoff']
        check('a controller nobody registered is not a hand-off',
              s['outcome'] == 'parked' and 'mid-conversation' in s['notes'][0][1], s)

        b = N['bossOverChat']
        check('the boss starting a card over a live chat is still asked first',
              b['outcome'] == 'started' and len(b['asked']) == 1
              and 'mid-conversation in chat' in b['asked'][0], b)
        check('...and a no leaves the card where it was',
              N['bossOverChatDeclined']['outcome'] == 'parked'
              and N['bossOverChatDeclined']['notes'] == [],
              N['bossOverChatDeclined'])

        cc = N['chainOverCard']
        check('a chain step onto someone mid-CARD still parks, naming the card',
              cc['outcome'] == 'parked'
              and 'still on "Summarise the vendor notes"' in cc['notes'][0][1],
              cc)
        check('...and never asks, because the boss did not start this',
              cc['asked'] == [], cc['asked'])

        check('a parked card on the same desk is not a run to work around',
              N['handoffPastParked']['outcome'] == 'started', N['handoffPastParked'])
        # One coworker, one run: if the registry holds only the run handing
        # over, the other card in `doing` is not running either.
        check('...nor is a card in DOING with no run behind it',
              N['handoffPastDoing']['outcome'] == 'started', N['handoffPastDoing'])
        check('an idle desk takes the chain step',
              N['idleChain']['outcome'] == 'started', N['idleChain'])
        check('...and the boss\'s own start, unasked',
              N['idleBoss']['outcome'] == 'started'
              and N['idleBoss']['asked'] == [], N['idleBoss'])

    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) failed')
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
