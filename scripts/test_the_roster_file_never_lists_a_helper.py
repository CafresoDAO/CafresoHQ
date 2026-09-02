#!/usr/bin/env python3
"""The roster on disk keeps a helper the office already dismissed.

Measured 2026-08-15 on office 9261, canned brain. During a transient
helper's 30-second grace window, the roster file the office keeps on
disk (memory/agents.json — and hq-agents.md, the human-readable roster
serve.py renders from every PUT of it) listed the helper as a member of
staff:

    ## Sub-fact-3j9 — Transient: fact checker

complete with `"transient": true` — a field persistableAgents can never
emit, proof the write path never ran the filter. Close the office
mid-grace and the dead timer takes the goodbye with it: 66+ seconds
after the dismissal was due, with no page running, both records still
listed the helper — and nothing left alive would ever take them off.
On reopen the record healed only by ACCIDENT: a no-op-tolerant CLI-sync
effect happens to call setAgents at +2.5s, and the setter flushes.

Root cause: useFileStored is documented "Like useStored", and useStored
applies its transform at WRITE time — but useFileStored's persist()
sent the raw value to localStorage and to the file PUT, running the
transform only on the read paths. persistableAgents — written as a
write filter, comment and all — never once ran at persist time.

The fix is an opt-in `persistTransform` (blanket transform-on-write
would be WRONG: tasksOnLoad is a load-scrub that would stamp "the run
stopped when the page reloaded" onto a run that is alive), wired for
the agents call site, plus a deterministic heal at adoption: if the
file holds what the write filter would never put there, write it back.

Run: python3 scripts/test_the_roster_file_never_lists_a_helper.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def main():
    print('the roster file never lists a helper')
    storage = (ROOT / 'app' / 'storage.jsx').read_text(encoding='utf-8')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    bare = strip_comments(storage)
    app_bare = strip_comments(app)

    # ── the write filter exists and both sinks drink from it ────────────
    check('persist computes the filtered value once',
          'const out = persistTransform ? persistTransform(v) : v;' in bare)
    check('localStorage receives the filtered value',
          'localStorage.setItem(lsKey, JSON.stringify(out))' in bare,
          'raw v to localStorage means the mirror lies even when the file '
          'does not')
    check('the file PUT receives the filtered value',
          'body: JSON.stringify(out),' in bare,
          'raw v to the PUT is the measured defect — Sub-fact-3j9 on the '
          'roster record')
    check('persist re-binds when the filter changes',
          re.search(r'\[lsKey, fileScope, fileName, sensitive, '
                    r'persistTransform\]\)', bare) is not None)

    # ── adoption heals a poisoned file deterministically ────────────────
    heal = re.search(
        r'if \(persistTransform\) \{\s*try \{\s*'
        r'if \(JSON\.stringify\(persistTransform\(merged\)\) !== '
        r'JSON\.stringify\(data\)\) persist\(merged\);', bare)
    check('adoption writes back when the file holds what the filter '
          'would never write', heal is not None,
          'without this, a record poisoned by a session that died '
          'mid-grace stays poisoned until an unrelated write happens by')

    # ── the agents call site opts in; the load-scrubs stay out ──────────
    check('the agents roster passes the write filter',
          re.search(r"useFileStored\(k\('agents'\),\s*'memory',\s*'agents',"
                    r"\s*seedAgents,\s*persistableAgents,\s*\{\s*"
                    r'persistTransform:\s*persistableAgents\s*\}\)', app_bare)
          is not None)
    for scrub in ('tasksOnLoad', 'missionsOnLoad'):
        check(f'{scrub} never runs at write time',
              re.search(r'persistTransform:\s*' + scrub, app_bare) is None,
              'a load-scrub at write time stamps "the run stopped when the '
              'page reloaded" onto a run that is alive')

    # ── behavior: persist body lifted and driven over both sinks ────────
    body = None
    open_marker = 'const persist = React.useCallback((v) => {'
    close_marker = "}, [lsKey, fileScope, fileName, sensitive, persistTransform]);"
    o, c = bare.find(open_marker), bare.find(close_marker)
    if o != -1 and c != -1 and o < c:
        body = bare[o + len(open_marker):c]
    check('the persist body lifts', body is not None)
    if body is None or not shutil.which('node'):
        if not shutil.which('node'):
            print('  SKIP  node not on PATH — behavior checks need it')
        print()
        if FAILS:
            print(f'roster-file: {len(FAILS)} FAILED')
            return 1
        print('roster-file: source checks passed')
        return 0

    js = (
        'const lsKey = "k:agents", fileScope = "memory", fileName = "agents";\n'
        'const sensitive = false;\n'
        'const hydratedRef = { current: true };\n'
        'const writeRef = { current: null };\n'
        'const window = { _API_BASE: "" };\n'
        'const sinks = { ls: null, put: null };\n'
        'const localStorage = { setItem: (k, v) => { sinks.ls = v; } };\n'
        'const clearTimeout = () => {};\n'
        'const setTimeout = (fn) => { fn(); return 1; };\n'
        'const fetch = (url, opts) => { sinks.put = opts.body; return Promise.resolve({ ok: true, status: 200 }); };\n'
        'const console = { warn: () => {} };\n'
        # persistableAgents lifted straight from the storage module.
        'PERSISTABLE\n'
        'let persistTransform = persistableAgents;\n'
        'const persist = (v) => {' + body + '};\n'
        + '''
const floor = [
  { id: 'a_kip', name: 'Kip', status: 'busy', mood: 'focus', task: 'digging', tools: ['web'] },
  { id: 'sub_1', name: 'Sub-test-abc', status: 'idle', mood: 'idle',
    task: 'standing by', transient: true, systemPrompt: 'one-shot helper' },
];
persist(floor);
const withFilter = { ls: JSON.parse(sinks.ls), put: JSON.parse(sinks.put) };
sinks.ls = sinks.put = null;
persistTransform = null;
persist(floor);
const without = { ls: JSON.parse(sinks.ls), put: JSON.parse(sinks.put) };
const idem = JSON.stringify(persistableAgents(persistableAgents(floor)))
  === JSON.stringify(persistableAgents(floor));
console.log = undefined;
process.stdout.write(JSON.stringify({ withFilter, without, idem }));
''')
    m = re.search(r'const persistableAgents = \(xs\) => xs\s*'
                  r'\.filter[\s\S]*?\}\);', bare)
    if not m:
        check('persistableAgents lifts', False)
        print('FAIL')
        return 1
    js = js.replace('PERSISTABLE', m.group(0))

    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('lifted persist runs', False, p.stderr.strip()[:300])
        print('FAIL')
        return 1
    r = json.loads(p.stdout.strip().split('\n')[-1])

    for sink in ('ls', 'put'):
        rec = r['withFilter'][sink]
        check(f'a transient helper never reaches the record ({sink})',
              [a['id'] for a in rec] == ['a_kip']
              and not any(a.get('transient') for a in rec),
              rec)
    rec = r['withFilter']['put']
    check('live status fields are reset on the record',
          rec[0]['status'] == 'idle' and rec[0]['task'] == 'standing by',
          rec[0])
    check('without the option, persist writes raw (opt-in, not blanket)',
          any(a.get('transient') for a in r['without']['put']),
          'the load-scrub callers rely on persist NOT transforming')
    check('the write filter is idempotent (heal compare is stable)',
          r['idem'] is True)

    print()
    if FAILS:
        print(f'roster-file: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('roster-file: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
