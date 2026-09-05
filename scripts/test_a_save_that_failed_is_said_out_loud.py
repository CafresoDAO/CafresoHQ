#!/usr/bin/env python3
"""Three places where the office did work, the work failed, and nobody
told the boss — the diagnosed-but-unfixed tail of `## 395`'s inventory.

`## 395` swept 118 catch blocks, 26 `.catch()` handlers, 654 setter call
sites and 122 state pairs across the client for work the code performs
that never reaches the boss. It fixed the Library graph's load swallow
and left three EXPOSED items named but unfixed. These are those three.

1. **app/storage.jsx — the adoption mirror.** After `useFileStored`'s
   mount fetch adopts the file, it mirrors the adopted value back into
   localStorage:

       try { localStorage.setItem(lsKey, JSON.stringify(merged)); } catch (_e) {}

   The two OTHER `setItem` failures in this same file — `persist()`'s a
   few lines up and `useStored`'s above it — both dispatch
   `cafresohq:storage-error`, which app.jsx's listener toasts. So the
   right mechanism exists, is already wired, is already used by its
   immediate neighbours, and this one call simply did not use it. A boss
   in a restricted or full-quota browser gets NO indication that nothing
   is persisting; and a session that only reads never reaches `persist()`
   at all, so this was the only chance anything had to say so.

2. **views/terminal.jsx — the `hq night` JSON helper.** It was
   `const j = (p, o) => fetch(base + p, …).then(r => r.json())`, with no
   `res.ok` check anywhere on it. Two ways that lied, both driven below:
   a non-2xx whose body is an HTML error page (serve.py's `send_error`
   emits one, and so does the asset host when `hq night` is run at
   ai.cafreso.com, which the command explicitly allows) threw the
   BROWSER's parse complaint into the transcript instead of the office's;
   and a JSON `{ error: … }` body never threw at all, so `hq night runs`
   read `runs === undefined` and printed "(no night runs yet)" over a
   request the office had refused.

3. **ui/feedback.jsx — `runCmd`.** The ⌘K palette calls `close()`, then
   defers the command and runs it in
   `try { cmd.run && cmd.run(); } catch (e) { console.error(e); }`.
   `## 395` left this on impact, reasoning that every registered command
   is a navigation call or a modal toggle. Enumerated here: it is not.
   `app/commands.jsx` is the only registrar of palette commands
   (`useCommands` is called from exactly one place outside feedback.jsx's
   own docstrings) and TWO of its commands are `run: async` doing real
   work behind a dialog — `ws.del.<id>` and `comms.who-can`. For exactly
   those two the try/catch was INERT: an async function throws by
   returning a rejected promise, which a synchronous catch never sees.
   The boss got not even the console line.

Run: python3 scripts/test_a_save_that_failed_is_said_out_loud.py
(skips the live-execution checks if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORAGE_JSX = ROOT / 'app' / 'storage.jsx'
APP_JSX = ROOT / 'app.jsx'
TERMINAL_JSX = ROOT / 'views' / 'terminal.jsx'
FEEDBACK_JSX = ROOT / 'ui' / 'feedback.jsx'
COMMANDS_JSX = ROOT / 'app' / 'commands.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift(src, pattern, what):
    """Pull the REAL committed body out of the source. Never a
    re-implementation — the rule every harness in this series uses."""
    m = re.search(pattern, src, re.S)
    check('lifted the real ' + what + ' out of the committed source',
          m is not None)
    return m.group(1) if m else ''


def node(js):
    return subprocess.run(['node', '-e', js], capture_output=True, text=True)


def main():
    print('Work that failed silently now says so — storage mirror, hq night, ⌘K')

    storage_src = STORAGE_JSX.read_text(encoding='utf-8')
    app_src = APP_JSX.read_text(encoding='utf-8')
    term_src = TERMINAL_JSX.read_text(encoding='utf-8')
    fb_src = FEEDBACK_JSX.read_text(encoding='utf-8')
    cmd_src = COMMANDS_JSX.read_text(encoding='utf-8')
    has_node = bool(shutil.which('node'))

    # ── 1. the adoption mirror ─────────────────────────────────────────
    print('\n1. app/storage.jsx — the adoption mirror that failed in silence')

    check('the adoption mirror no longer swallows into `catch (_e) {}` — '
          'the regression itself',
          'localStorage.setItem(lsKey, JSON.stringify(merged)); } catch (_e) {}'
          not in storage_src)
    check('there is no `localStorage.setItem` left in this file whose catch '
          'is a bare swallow (the whole point: three siblings, one shape)',
          not re.search(r"localStorage\.setItem\([^\n]*\);\s*\}\s*catch\s*\(_e\)\s*\{\s*\}",
                        storage_src))
    check('every write path in this file that can fail now dispatches '
          'cafresohq:storage-error — useStored\'s setItem, persist\'s '
          'setItem, the debounced file PUT, and (this fix) the adoption '
          'mirror: four, where there were three',
          storage_src.count("new CustomEvent('cafresohq:storage-error'") == 4,
          storage_src.count("new CustomEvent('cafresohq:storage-error'"))
    check("the adoption mirror does NOT tag target:'file' — localStorage is "
          'what failed, and app.jsx has separate wording for a disk write',
          "target: 'file'" not in
          storage_src.split('The adoption mirror')[-1].split('/* The held-write flush')[0])
    check("app.jsx still listens for the event and says something",
          "window.addEventListener('cafresohq:storage-error', handler)" in app_src
          and 'recent changes may not persist' in app_src)

    adopt = lift(storage_src, r"\n      \.then\(data => \{\n(.*?)\n      \}\)\n",
                 "mount-fetch adoption body")
    handler = lift(app_src, r"\n    const handler = \(e\) => \{\n(.*?)\n    \};\n",
                   "app.jsx storage-error handler")

    if has_node and adopt and handler:
        js = """
        const results = {};
        function drive(setItemThrows) {
          const events = [];
          const toasts = [];
          const window = {
            dispatchEvent: (e) => { events.push({ type: e.type, detail: e.detail }); return true; },
          };
          const CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };
          const console = { warn: () => {} };
          const localStorage = {
            setItem: () => {
              if (setItemThrows) {
                const err = new Error('The quota has been exceeded.');
                err.name = 'QuotaExceededError';
                throw err;
              }
            },
          };
          // The collaborators the lifted body closes over, handed in explicitly.
          const hydratedRef = { current: false };
          const dirtyRef = { current: false };
          const valRef = { current: { agents: [] } };
          const seedRef = { current: JSON.stringify({ agents: [] }) };
          const mergeOnDirty = false;
          const persistTransform = null;
          const transform = null;
          const lsKey = 'cafresohq_hq_v1:agents';
          let stateValue = null;
          const setVal = (v) => { stateValue = v; };
          const persist = () => {};
          const data = { agents: [{ id: 'vera' }] };

          const body = (data) => { %ADOPT% };
          body(data);

          // Now feed whatever it dispatched into app.jsx's REAL listener.
          let lastShown = 0;
          const say = (text, kind) => { toasts.push({ text, kind }); };
          const listener = (e) => { %HANDLER% };
          events.forEach(e => listener(e));

          return { adopted: stateValue, events, toasts };
        }
        results.storage_ok = drive(false);
        results.storage_full = drive(true);
        console.log(JSON.stringify(results));
        """.replace('%ADOPT%', adopt).replace('%HANDLER%', handler)
        r = node(js)
        check('the extracted adoption body + app.jsx listener ran under node',
              r.returncode == 0, r.stderr.strip()[-900:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            ok, full = out['storage_ok'], out['storage_full']
            check('a healthy mirror write says nothing at all',
                  ok['events'] == [] and ok['toasts'] == [], ok)
            check('THE BUG: a localStorage that refuses the write now '
                  'dispatches cafresohq:storage-error carrying the key and '
                  'the browser\'s own error',
                  len(full['events']) == 1
                  and full['events'][0]['type'] == 'cafresohq:storage-error'
                  and full['events'][0]['detail'].get('key') == 'cafresohq_hq_v1:agents',
                  full['events'])
            check('and app.jsx\'s REAL listener turns that into a toast the '
                  'boss can read — driven, not assumed',
                  len(full['toasts']) == 1
                  and full['toasts'][0]['kind'] == 'STORAGE'
                  and 'may not persist' in full['toasts'][0]['text'],
                  full['toasts'])
            check('the toast names the quota specifically (the listener reads '
                  'error.name), so the boss knows what to clear',
                  'storage full' in (full['toasts'][0]['text'] if full['toasts'] else ''),
                  full['toasts'])
            check('the adoption itself still happens — reporting the failed '
                  'mirror must not cost the boss the file they came back for',
                  ok['adopted'] == {'agents': [{'id': 'vera'}]}
                  and full['adopted'] == {'agents': [{'id': 'vera'}]},
                  [ok['adopted'], full['adopted']])

    # ── 2. hq night ────────────────────────────────────────────────────
    print("\n2. views/terminal.jsx — `hq night` read a refusal as an empty night")

    check('the JSON helper no longer ends in a bare `.then(r => r.json())` '
          'with no status check — the regression itself',
          "const j = (p, o) => fetch(base + p, { credentials: 'include', "
          "...(o || {}) }).then(r => r.json());" not in term_src)
    check('the helper checks r.ok and throws',
          bool(re.search(r"const j = async \(p, o\) => \{", term_src))
          and 'if (!r.ok) throw new Error' in term_src)
    check('a throw from a subcommand reaches the transcript — hqsh\'s own '
          'surface — via runLine\'s catch',
          "catch (e) { print('err', String((e && e.message) || e)); }" in term_src)

    jbody = lift(term_src, r"\n      const j = async \(p, o\) => \{\n(.*?)\n      \};\n",
                 'hq night JSON helper')

    if has_node and jbody:
        js = """
        async function run() {
          const base = 'http://office';
          async function ask(fetchImpl) {
            const fetch = fetchImpl;
            const j = async (p, o) => { %J% };
            try { return { value: await j('/missions/runs') }; }
            catch (e) { return { error: String(e.message || e) }; }
          }
          const html = '<!DOCTYPE html><html><head><title>Error 500</title></head>'
            + '<body><h1>Internal Server Error</h1></body></html>';
          const results = {};
          // serve.py's send_error() answers HTML; so does the asset host.
          results.html_500 = await ask(async () => ({
            ok: false, status: 500, statusText: 'Internal Server Error',
            text: async () => html }));
          // The asset canister's SPA fallback: 200, and index.html.
          results.html_200 = await ask(async () => ({
            ok: true, status: 200, statusText: 'OK', text: async () => html }));
          // A JSON refusal — the one that used to fall straight through.
          results.json_403 = await ask(async () => ({
            ok: false, status: 403, statusText: 'Forbidden',
            text: async () => JSON.stringify({ error: 'night shifts are off in this office' }) }));
          results.good = await ask(async () => ({
            ok: true, status: 200, statusText: 'OK',
            text: async () => JSON.stringify({ runs: [{ id: 'r1' }] }) }));
          console.log(JSON.stringify(results));
        }
        run();
        """.replace('%J%', jbody)
        r = node(js)
        check('the extracted hq night helper ran under node',
              r.returncode == 0, r.stderr.strip()[-900:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check('a 500 with an HTML body is reported as the office\'s '
                  'status, not as the browser\'s JSON parse complaint '
                  '(pre-fix the transcript read "Unexpected token \'<\'")',
                  out['html_500'].get('error', '').startswith('/missions/runs')
                  and '500' in out['html_500'].get('error', '')
                  and 'JSON' not in out['html_500'].get('error', ''),
                  out['html_500'])
            check('THE OTHER HALF: a 200 that is HTML (the asset host\'s SPA '
                  'fallback, which is what `hq night` hits at ai.cafreso.com) '
                  'is named as a non-JSON answer rather than crashing on it',
                  'not JSON' in out['html_200'].get('error', ''),
                  out['html_200'])
            check('THE BUG: a JSON refusal now reaches the transcript in the '
                  'office\'s own words — pre-fix this returned { error } as a '
                  'success and `hq night runs` printed "(no night runs yet)"',
                  'night shifts are off in this office' in out['json_403'].get('error', ''),
                  out['json_403'])
            check('a healthy response is still returned parsed, unchanged',
                  out['good'].get('value') == {'runs': [{'id': 'r1'}]},
                  out['good'])

    # ── 3. runCmd ──────────────────────────────────────────────────────
    print('\n3. ui/feedback.jsx — the palette closed on a command that died')

    # The denominator: every .jsx outside feedback.jsx itself (which owns the
    # hook's definition and quotes it twice in its own comments) that CALLS
    # useCommands. If a second registrar ever appears, this check fails and
    # the enumeration below has to be redone rather than inherited — which is
    # precisely the mistake `## 395` made here.
    registrars = sorted(
        str(p.relative_to(ROOT)) for p in ROOT.glob('**/*.jsx')
        if 'node_modules' not in p.parts and p != FEEDBACK_JSX
        and re.search(r"^\s*useCommands\(", p.read_text(encoding='utf-8'), re.M))
    check('app/commands.jsx is the ONLY registrar of palette commands, so '
          'the enumeration below is the whole denominator',
          registrars == ['app/commands.jsx'], registrars)
    check("`## 395`'s premise is FALSE: app/commands.jsx registers commands "
          'that are neither a navigation call nor a modal toggle — two are '
          '`run: async` and do real work behind a dialog',
          cmd_src.count('run: async') == 2, cmd_src.count('run: async'))
    check('and those two are the workspace delete and /who-can, both of '
          'which await a dialog before touching real data',
          "id: 'ws.del.' + w.id" in cmd_src and "id: 'comms.who-can'" in cmd_src)
    check('runCmd now handles a returned thenable — a synchronous catch '
          'cannot see an async function\'s rejection, which is why the old '
          'try/catch was inert for exactly those two commands',
          "typeof r.then === 'function'" in fb_src)
    check('and it reports on the surface instead of only the console',
          'window.cafresohqToast' in fb_src and "didn't run" in fb_src)

    runcmd = lift(fb_src, r"\n  const runCmd = React\.useCallback\(\(cmd\) => \{\n(.*?)\n  \}, \[close\]\);\n",
                  'runCmd body')

    if has_node and runcmd:
        js = """
        async function run() {
          const results = {};
          async function fire(cmd) {
            const closed = [];
            const toasts = [];
            const close = () => { closed.push(1); };
            const console = { error: () => {} };
            const window = { cafresohqToast: { error: (t) => { toasts.push(t); } } };
            const body = (cmd) => { %RUNCMD% };
            body(cmd);
            await new Promise(r => setTimeout(r, 60));
            return { closed: closed.length, toasts };
          }
          results.sync_throw = await fire({ id: 'act.hire', label: 'Hire a new coworker',
            run: () => { throw new Error('the front desk is closed'); } });
          results.async_reject = await fire({ id: 'comms.who-can', label: '/who-can',
            run: async () => { throw new Error('capabilityFacts is not a function'); } });
          results.fine = await fire({ id: 'nav.tasks', label: 'Switch view: Tasks', run: () => {} });
          results.no_handler = await fire({ id: 'x', label: 'x' });
          console.log(JSON.stringify(results));
        }
        run();
        """.replace('%RUNCMD%', runcmd)
        r = node(js)
        check('the extracted runCmd ran under node',
              r.returncode == 0, r.stderr.strip()[-900:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check('a synchronously throwing command now names itself to the '
                  'boss instead of only the console',
                  len(out['sync_throw']['toasts']) == 1
                  and 'Hire a new coworker' in out['sync_throw']['toasts'][0]
                  and 'the front desk is closed' in out['sync_throw']['toasts'][0],
                  out['sync_throw'])
            check('THE BUG: an ASYNC command that rejects is now caught at '
                  'all — the old synchronous try/catch never saw it, so this '
                  'was an unhandledrejection and a palette that closed on '
                  'nothing',
                  len(out['async_reject']['toasts']) == 1
                  and '/who-can' in out['async_reject']['toasts'][0]
                  and 'capabilityFacts' in out['async_reject']['toasts'][0],
                  out['async_reject'])
            check('a command that works says nothing, and the palette still '
                  'closes in every case',
                  out['fine']['toasts'] == []
                  and out['no_handler']['toasts'] == []
                  and all(out[k]['closed'] == 1 for k in
                          ('sync_throw', 'async_reject', 'fine', 'no_handler')),
                  out)

    check('node is on PATH (needed to genuinely execute the three extracted '
          'bodies above)', has_node, 'skipped the live-execution checks')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
