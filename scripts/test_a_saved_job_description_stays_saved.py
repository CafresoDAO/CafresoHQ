#!/usr/bin/env python3
"""The job description reverted to the old text one render after saving it.

Team -> click a coworker -> PERFORMANCE REVIEW -> "Job description". Type a
new brief, click away. A toast says "<name>'s job description updated". The
textarea then repaints with the PREVIOUS job description, as if the edit had
been thrown away.

The save is real; the panel is the liar. `InspectPanel` is handed a FROZEN
snapshot of the coworker — app.jsx holds the inspected agent in its own
`const [inspect, setInspect] = useStateA(null)` and never re-looks it up
from the roster, while `onUpdateAgent` rebuilds the roster immutably
(`const next = { ...a, ...patch }`). So the object the panel is holding
still carries the OLD systemPrompt for as long as the panel is open.

The draft was thrown away on commit and the display fell straight back to
that stale prop:

    const jdValue = jd !== null ? jd : (agent.systemPrompt || '');
    const saveJd = () => {
      ...
      onUpdate(agent.id, { systemPrompt: jd });
      setJd(null);                       // -> jdValue falls back to the OLD text

There is a second, worse half. The dirty check used the same stale value, so
after re-typing the very text that had just been saved the panel would call
onUpdate and toast AGAIN — and, in the other direction, a boss who restored
the coworker's ORIGINAL wording could not save it back: `jd ===
agent.systemPrompt` was true against a prompt that was no longer on file, so
the blur was swallowed and the edit silently lost.

The fix remembers what it committed, in a ref keyed by agent.id (so a save
on one coworker can never surface on the next one the panel is pointed at),
and reads both the display fallback and the dirty check off that.

This drives the REAL InspectPanel — ui/panels.jsx bundled with the project's
own esbuild, its imports stubbed, hooks driven by a small React stand-in —
because a re-implementation of the draft logic would happily agree with
itself while the shipped panel kept reverting.

Run: python3 scripts/test_a_saved_job_description_stays_saved.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANELS = ROOT / 'ui' / 'panels.jsx'
APP = ROOT / 'app.jsx'
ESBUILD = ROOT / 'node_modules' / '.bin' / 'esbuild'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── stubs for everything panels.jsx imports; none of it is under test ──────
STUBS = {
    'sprites.jsx':
        'export const SPRITES = { cafresohq: null };\n'
        'export const Sprite = () => null;\n',
    'ui/primitives.jsx':
        'export const Ico = () => null;\n',
    'app/experience.jsx':
        'export const XP_HOT_STREAK = 3;\n'
        'export const xpStats = () => ({ jobs: 0, snags: 0, streak: 0 });\n'
        'export const xpAffinityText = () => "";\n',
    'app/cast.jsx':
        'export const brainName = () => "Llama";\n'
        'export const CAN_USE_TIP = "";\n'
        'export const CAN_USE_OFF_TIP = "";\n'
        'export const EFFORT_TIP = "";\n'
        'export const OFFICE_EFFORT_TIP = "";\n'
        'export const grantedTools = () => ({ granted: [], locked: [] });\n'
        'export const poweredBy = () => "";\n'
        'export const specialtyTag = () => "";\n'
        'export const statBars = () => ({ speed: 1, depth: 1, code: 1, cost: 1 });\n'
        'export const payrollLabel = () => ({ text: "", title: "" });\n',
    'hq-runtime.jsx':
        'export const HQ = { capabilityFacts: () => ({}) };\n',
    'app/artifacts.jsx':
        'export const officeDate = () => "";\n',
}

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

const toasts = [];
globalThis.window = { cafresohqToast: { success: (t) => toasts.push(t), info: () => {}, error: () => {} } };
globalThis.fetch = () => Promise.reject(new Error('no network in the probe'));

const { InspectPanel } = await import('./ui/panels.jsx');

let tree = null;
function render(props) {
  let guard = 0;
  do {
    st.dirty = false;
    st.idx = 0;
    st.effects = [];
    tree = InspectPanel(props);
    const fx = st.effects;
    st.effects = [];
    fx.forEach((f) => f());
  } while (st.dirty && ++guard < 25);
  return tree;
}
function findTextarea(node) {
  if (!node || typeof node !== 'object') return null;
  if (Array.isArray(node)) {
    for (const c of node) { const r = findTextarea(c); if (r) return r; }
    return null;
  }
  if (node.type === 'textarea') return node;
  return node.props ? findTextarea(node.props.children) : null;
}
const ta = () => {
  const t = findTextarea(tree);
  if (!t) throw new Error('no textarea rendered');
  return t;
};

const updates = [];
/* The frozen snapshot, exactly as app.jsx hands it over: one object,
   captured when the card was clicked, never re-looked-up while open. */
const ORIGINAL = 'Answer in one line.';
const EDITED = 'Answer in three lines, and cite your sources.';
const frozen = {
  id: 'a1', name: 'Vera', role: 'Analyst', mood: 'idle', color: null,
  tokens: 0, tools: [], systemPrompt: ORIGINAL, journal: [], recent: '',
};
const props = {
  agent: frozen, activity: [], experience: [],
  onClose: () => {}, onDismiss: () => {},
  onUpdate: (id, patch) => updates.push({ id, patch }),
};

const out = {};
render(props);
out.opensWithTheJobOnFile = ta().props.value;

// type a new brief, then click away — the panel is re-rendered with the SAME
// frozen object, because nothing upstream replaced it.
ta().props.onChange({ target: { value: EDITED } });
render(props);
out.showsWhatWasTyped = ta().props.value;

ta().props.onBlur();
render(props);
out.saved = updates.map((u) => [u.id, u.patch.systemPrompt]);
out.afterSaving = ta().props.value;
out.toasts = toasts.length;

// blur again with nothing typed: must not re-save or re-toast.
ta().props.onBlur();
render(props);
out.savesAfterIdleBlur = updates.length;
out.toastsAfterIdleBlur = toasts.length;

// restore the coworker's ORIGINAL wording — the stale prop still says that IS
// what is on file, so the naive dirty check swallows this edit entirely.
ta().props.onChange({ target: { value: ORIGINAL } });
render(props);
ta().props.onBlur();
render(props);
out.restoreCount = updates.length;
out.restoreSaved = updates.length ? updates[updates.length - 1].patch.systemPrompt : null;
out.afterRestore = ta().props.value;

// point the panel at a different coworker: nothing of the first one leaks.
const other = Object.assign({}, frozen, { id: 'a2', name: 'Kip', systemPrompt: 'Ship it.' });
render(Object.assign({}, props, { agent: other }));
out.nextCoworker = ta().props.value;

console.log(JSON.stringify(out));
'''


def run_probe():
    """Bundle the real panel and drive it. The temp dir lives INSIDE the repo
    so node and esbuild resolve against the project's own tree."""
    tmp = ROOT / '.jobdesc-probe-tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / 'ui').mkdir(parents=True)
    (tmp / 'app').mkdir(parents=True)
    try:
        for rel, body in STUBS.items():
            (tmp / rel).write_text(body, encoding='utf-8')
        (tmp / 'ui' / 'panels.jsx').write_text(
            PANELS.read_text(encoding='utf-8'), encoding='utf-8')
        (tmp / 'probe.mjs').write_text(PROBE, encoding='utf-8')
        b = subprocess.run(
            [str(ESBUILD), '--bundle', str(tmp / 'probe.mjs'), '--format=esm',
             '--platform=node', '--outfile=' + str(tmp / 'out.mjs'),
             '--log-level=error'],
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


ORIGINAL = 'Answer in one line.'
EDITED = 'Answer in three lines, and cite your sources.'


def main():
    print('a saved job description stays saved')
    if not ESBUILD.exists() or not shutil.which('node'):
        print('  SKIP  node/esbuild not available — cannot run the real panel')
        return 0

    print('0. the premise: the panel cannot see its own save')
    app = APP.read_text(encoding='utf-8')
    # If this ever stops being true the panel would get a fresh prop and the
    # revert could not happen — but the fix below stays correct either way.
    check('app.jsx keeps the inspected coworker in its own state',
          re.search(r'const \[inspect, setInspect\] = useStateA\(null\)', app)
          is not None)
    check('onUpdateAgent rebuilds the coworker immutably, so a held snapshot goes stale',
          re.search(r'const onUpdateAgent = \(id, patch\) => setAgents\(prev => prev\.map',
                    app) is not None
          and 'const next = { ...a, ...patch };' in app)

    r, err = run_probe()
    if r is None:
        print('  FAIL  could not run InspectPanel: ' + str(err))
        return 1

    print('1. the fixture is the panel that was on screen')
    check('it opens on the job description that is on file',
          r['opensWithTheJobOnFile'] == ORIGINAL, repr(r['opensWithTheJobOnFile']))
    check('typing shows what was typed',
          r['showsWhatWasTyped'] == EDITED, repr(r['showsWhatWasTyped']))

    print('2. clicking away saves it — and it stays on screen')
    check('the new brief is handed to onUpdate',
          r['saved'] == [['a1', EDITED]], repr(r['saved']))
    check('the boss is told it was saved', r['toasts'] == 1, repr(r['toasts']))
    check('the textarea still shows the new brief after saving',
          r['afterSaving'] == EDITED,
          repr(r['afterSaving']) + ' — the panel repainted the PREVIOUS job '
          'description one render after the toast said it had been updated. '
          'Nothing was lost on disk; the boss was shown their edit vanishing.')

    print('3. a blur that changed nothing changes nothing')
    check('no second save', r['savesAfterIdleBlur'] == 1, repr(r['savesAfterIdleBlur']))
    check('no second toast', r['toastsAfterIdleBlur'] == 1, repr(r['toastsAfterIdleBlur']))

    print('4. putting the original wording back is a real edit')
    check('restoring the coworker\'s original brief actually saves',
          r['restoreCount'] == 2 and r['restoreSaved'] == ORIGINAL,
          '%d save(s), last=%r' % (r['restoreCount'], r['restoreSaved'])
          + ' — measured against the stale prop this '
          'read as "no change" and the blur was swallowed, so the boss could '
          'not undo their own edit from this panel at all')
    check('...and the panel shows the restored wording',
          r['afterRestore'] == ORIGINAL, repr(r['afterRestore']))

    print('5. nothing leaks to the next coworker')
    check('pointing the panel at another coworker shows THEIR job description',
          r['nextCoworker'] == 'Ship it.', repr(r['nextCoworker']))

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
