#!/usr/bin/env python3
"""Reopening the onboarding tour must start it at step 1 (ui/onboarding.jsx).

Bug: <OnboardingTour> keeps the current step in component state (`idx`), and
app.jsx mounts it permanently with open={tourOpen} — the component is never
unmounted, so `idx` survives every close. Nothing put the deck back to the
first card when it reopened:

  - Finish, then replay. app.jsx wires the `cafresohq:replayTour` event (the
    command palette's "Take the tour") straight to setTourOpen(true). After
    finishing, idx is steps.length - 1, so the replayed tour opened on the
    LAST card — "Step 10 of 10", a lone Finish button — and ended in one
    click.
  - Leave mid-tour and come back. The "Your AI brain" step's "bring your own
    brain →" button dispatches `cafresohq:openSettings`, and that handler
    calls setTourOpen(false). Reopening resumed wherever the boss had left.

Worse across widths: the two step decks are different lengths (desktop 10,
mobile 9). A tour finished on a laptop and replayed at phone width indexed
steps[9] === undefined, so `step` was undefined and the component rendered
NOTHING — while tourOpen stayed true, which also gates <GettingStarted> off.
The boss asked for the tour and got a blank office minus the checklist.

Fix: one effect keyed on `open` — `if (open) setIdx(0)`.

This drives the REAL OnboardingTour: ui/onboarding.jsx bundled with the
project's own esbuild, its client import stubbed (app/floor.jsx goes in
real — it is import-free), hooks driven by a small React
stand-in. A re-implementation of the step counter would happily agree with
itself while the shipped component kept resuming.

Run: python3 scripts/test_replaying_the_tour_starts_it_over.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'ui' / 'onboarding.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'
APP = ROOT / 'app.jsx'
ESBUILD = ROOT / 'node_modules' / '.bin' / 'esbuild'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


STUB_CLIENT = (
    'export const CafresoHQClient = {\n'
    '  getSettings: () => ({}),\n'
    '  hermesSetOpenRouterKey: async () => ({ ok: true, serverStored: false }),\n'
    '};\n'
)

PROBE = r'''
/* A React stand-in just big enough to run one function component: ordered
   hook slots, effects flushed after each render, and a render loop that
   settles when nothing else sets state. */
const st = { hooks: [], idx: 0, effects: [], dirty: false };
const same = (a, b) => !!a && !!b && a.length === b.length
  && a.every((x, i) => Object.is(x, b[i]));
const React = {
  Fragment: 'FRAGMENT',
  createElement: (type, props, ...kids) =>
    ({ type, props: Object.assign({}, props, kids.length ? { children: kids } : {}) }),
  useState(init) {
    const i = st.idx++;
    if (!(i in st.hooks)) st.hooks[i] = { v: typeof init === 'function' ? init() : init };
    const h = st.hooks[i];
    return [h.v, (nv) => {
      const n = typeof nv === 'function' ? nv(h.v) : nv;
      if (!Object.is(n, h.v)) { h.v = n; st.dirty = true; }
    }];
  },
  useRef(init) {
    const i = st.idx++;
    if (!(i in st.hooks)) st.hooks[i] = { current: init };
    return st.hooks[i];
  },
  useMemo(fn, deps) {
    const i = st.idx++;
    const h = st.hooks[i];
    if (!h || !same(h.deps, deps)) st.hooks[i] = { v: fn(), deps };
    return st.hooks[i].v;
  },
  useEffect(fn, deps) {
    const i = st.idx++;
    const h = st.hooks[i];
    if (!h || !same(h.deps, deps)) { st.hooks[i] = { deps }; st.effects.push(fn); }
  },
  useLayoutEffect(fn, deps) { return React.useEffect(fn, deps); },
  createContext: (d) => ({ _d: d, Provider: 'P', Consumer: 'C' }),
  useContext: (c) => c._d,
};
globalThis.React = React;
globalThis.window = {
  innerWidth: 1440, innerHeight: 900,
  addEventListener: () => {}, removeEventListener: () => {},
  dispatchEvent: () => {},
};
globalThis.fetch = () => Promise.reject(new Error('no network in the probe'));

const { OnboardingTour } = await import('./ui/onboarding.jsx');

let tree = null;
function render(props) {
  let guard = 0;
  do {
    st.dirty = false;
    st.idx = 0;
    st.effects = [];
    tree = OnboardingTour(props);
    const fx = st.effects;
    st.effects = [];
    fx.forEach((f) => { const c = f(); if (typeof c === 'function') { /* kept mounted */ } });
  } while (st.dirty && ++guard < 40);
  return tree;
}
function walk(node, hit) {
  if (!node || typeof node !== 'object') return null;
  if (Array.isArray(node)) {
    for (const c of node) { const r = walk(c, hit); if (r) return r; }
    return null;
  }
  if (hit(node)) return node;
  return node.props ? walk(node.props.children, hit) : null;
}
const flat = (n) => Array.isArray(n) ? n.map(flat).join('')
  : (n && typeof n === 'object' ? flat(n.props && n.props.children) : (n == null || n === false ? '' : String(n)));

/* "Step 3 of 10" — the line the boss actually reads. */
function stepLine() {
  if (tree === null) return null;
  const n = walk(tree, (x) => x.props && x.props.className === 'oc-tour-step');
  return n ? flat(n.props.children) : null;
}
function title() {
  if (tree === null) return null;
  const n = walk(tree, (x) => x.props && x.props.className === 'oc-tour-title');
  return n ? flat(n.props.children) : null;
}
function primaryLabel() {
  if (tree === null) return null;
  let found = null;
  walk(tree, (x) => {
    if (x.props && x.props.className === 'px-btn primary') { found = x; return true; }
    return false;
  });
  return found ? flat(found.props.children) : null;
}
function clickPrimary() {
  let found = null;
  walk(tree, (x) => {
    if (x.props && x.props.className === 'px-btn primary') { found = x; return true; }
    return false;
  });
  if (!found) throw new Error('no primary button rendered');
  found.props.onClick();
}

const mk = (n, tag) => Array.from({ length: n }, (_, i) =>
  ({ id: tag + i, title: tag + ' step ' + (i + 1), body: 'body' }));
const DESKTOP = mk(10, 'desktop');
const MOBILE = mk(9, 'mobile');

const events = [];
const base = {
  steps: DESKTOP,
  onClose: () => events.push('close'),
  onComplete: () => events.push('complete'),
};
const out = {};

// closed: renders nothing
render(Object.assign({}, base, { open: false }));
out.closedRenders = tree;

// first run: opens on card 1
render(Object.assign({}, base, { open: true }));
out.firstOpen = stepLine();
out.firstTitle = title();

// walk all the way to the end and hit Finish
for (let i = 0; i < DESKTOP.length - 1; i++) { clickPrimary(); render(Object.assign({}, base, { open: true })); }
out.lastCard = stepLine();
out.lastButton = primaryLabel();
clickPrimary();
out.finishEvents = events.slice();

// the host closes the tour (onClose -> setTourOpen(false))
render(Object.assign({}, base, { open: false }));

// ── the replay: command palette fires cafresohq:replayTour ──
render(Object.assign({}, base, { open: true }));
out.replayLine = stepLine();
out.replayTitle = title();
out.replayButton = primaryLabel();

// ── leaving mid-tour ("bring your own brain →" closes the tour) ──
clickPrimary(); render(Object.assign({}, base, { open: true }));
clickPrimary(); render(Object.assign({}, base, { open: true }));
out.walkedTo = stepLine();
render(Object.assign({}, base, { open: false }));
render(Object.assign({}, base, { open: true }));
out.afterSettingsDetour = stepLine();

// ── the width switch: finish on desktop (10), replay on a phone (9) ──
render(Object.assign({}, base, { open: false }));
render(Object.assign({}, base, { open: true }));
for (let i = 0; i < DESKTOP.length - 1; i++) { clickPrimary(); render(Object.assign({}, base, { open: true })); }
clickPrimary();
render(Object.assign({}, base, { open: false }));
globalThis.window.innerWidth = 375;
render(Object.assign({}, base, { open: true, steps: MOBILE }));
out.narrowReplayRendered = tree !== null;
out.narrowReplayLine = stepLine();

console.log(JSON.stringify(out));
'''


def run_probe():
    """Bundle the real component and drive it. The temp dir lives INSIDE the
    repo so node and esbuild resolve against the project's own tree."""
    tmp = ROOT / '.tour-replay-probe-tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / 'ui').mkdir(parents=True)
    (tmp / 'app').mkdir(parents=True)
    try:
        (tmp / 'claude-client.jsx').write_text(STUB_CLIENT, encoding='utf-8')
        # app/floor.jsx goes in REAL, not stubbed: it is import-free pure
        # string helpers (that is a stated property of the file, and what
        # lets scripts/test_floor.py run it verbatim), so there is nothing
        # to fake and a stub would only be a second copy to keep in step.
        # #330 gave the key step a second import; before that the harness
        # only had claude-client.jsx to stand in for.
        (tmp / 'app' / 'floor.jsx').write_text(
            FLOOR.read_text(encoding='utf-8'), encoding='utf-8')
        (tmp / 'ui' / 'onboarding.jsx').write_text(
            SRC.read_text(encoding='utf-8'), encoding='utf-8')
        (tmp / 'probe.mjs').write_text(PROBE, encoding='utf-8')
        b = subprocess.run(
            [str(ESBUILD), '--bundle', str(tmp / 'probe.mjs'), '--format=esm',
             '--platform=node', '--loader:.jsx=jsx', '--jsx-factory=React.createElement',
             '--jsx-fragment=React.Fragment',
             '--outfile=' + str(tmp / 'out.mjs'), '--log-level=error'],
            cwd=ROOT, capture_output=True, text=True, timeout=180)
        if b.returncode != 0:
            return None, 'esbuild: ' + b.stderr.strip()[:400]
        p = subprocess.run([shutil.which('node') or 'node', str(tmp / 'out.mjs')],
                           cwd=ROOT, capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            return None, 'node: ' + (p.stderr.strip()[:400] or 'no stderr')
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print('replaying the tour starts it over')
    if not ESBUILD.exists() or not shutil.which('node'):
        print('  SKIP  node/esbuild not available — cannot run the real tour')
        return 0

    print('0. the premise: the host never unmounts the tour, and replays it in place')
    app = APP.read_text(encoding='utf-8')
    check('app.jsx mounts <OnboardingTour open={tourOpen}> unconditionally',
          re.search(r'<OnboardingTour\s*\n\s*open=\{tourOpen\}', app) is not None)
    check('the palette replay just flips the flag back on',
          "const onReplay = () => setTourOpen(true);" in app)
    check('the key step\'s Settings link closes the tour mid-run',
          re.search(r'const onOpen = \(e\) => \{ setTourOpen\(false\);', app) is not None)

    r, err = run_probe()
    if r is None:
        print('  FAIL  could not run OnboardingTour: ' + str(err))
        return 1

    print('1. the fixture behaves like the tour on screen')
    check('closed, it renders nothing', r['closedRenders'] is None)
    check('a first run opens on card 1', r['firstOpen'] == 'Step 1 of 10',
          repr(r['firstOpen']))
    check('card 1 is the first step in the deck',
          r['firstTitle'] == 'desktop step 1', repr(r['firstTitle']))
    check('walking to the end lands on the last card',
          r['lastCard'] == 'Step 10 of 10', repr(r['lastCard']))
    check('the last card offers Finish', r['lastButton'] == 'Finish',
          repr(r['lastButton']))
    check('Finish completes and closes',
          r['finishEvents'] == ['complete', 'close'], repr(r['finishEvents']))

    print('2. "Take the tour" after finishing it gives the whole tour again')
    check('the replay opens on card 1, not the last one',
          r['replayLine'] == 'Step 1 of 10',
          repr(r['replayLine']) + ' — the replayed tour opened on the final '
          'card with a lone Finish button, so asking for the tour again ended '
          'it in one click.')
    check('the replay shows the first step\'s content',
          r['replayTitle'] == 'desktop step 1', repr(r['replayTitle']))
    check('the replay offers Next, not Finish', r['replayButton'] == 'Next →',
          repr(r['replayButton']))

    print('3. a mid-tour detour into Settings does not resume half-way')
    check('the boss had walked to card 3', r['walkedTo'] == 'Step 3 of 10',
          repr(r['walkedTo']))
    check('reopening restarts at card 1',
          r['afterSettingsDetour'] == 'Step 1 of 10',
          repr(r['afterSettingsDetour']))

    print('4. finished on a laptop, replayed on a phone (10-step deck -> 9)')
    check('the tour actually renders', r['narrowReplayRendered'] is True,
          'steps[9] was undefined on the 9-step mobile deck, so the component '
          'returned null while tourOpen stayed true — a blank office, and '
          '<GettingStarted> is gated off by that same flag.')
    check('and it renders card 1 of the mobile deck',
          r['narrowReplayLine'] == 'Step 1 of 9', repr(r['narrowReplayLine']))

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'tour replay: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
