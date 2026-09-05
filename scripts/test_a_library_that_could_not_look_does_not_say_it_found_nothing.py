#!/usr/bin/env python3
"""Two doors answered 200 with an empty answer over a failure they swallowed.

`## 401` swept the server for this shape and left both DIAGNOSED BUT UNFIXED,
so the first job here was to drive them rather than trust the diagnosis. Both
reproduce; one of the two symptoms `## 401` listed does not.

Measured on a real serve.py on its own port, pointed at a stand-in Obsidian
Local REST API, with every provider key stripped from the child's environment
(the only keys and URLs anywhere in this file are obvious fakes):

    wrong API key (Obsidian answers 401)      -> HTTP 200 {"hits": []}
    Local REST plugin disabled (404)          -> HTTP 200 {"hits": []}
    Obsidian errors (500)                     -> HTTP 200 {"hits": []}
    200 with a body that will not parse       -> HTTP 200 {"hits": []}
    genuinely no matches (200 [])             -> HTTP 200 {"hits": []}
    Obsidian not running (refused connection) -> HTTP 502 obsidian: [Errno 61]…

Five identical answers for five different situations, one of which is the
truth. `_rest_search` answered `return []` to every non-200 and to any body
that would not parse, and `/vault/search` fed that list straight into
`_send_json(200, {'hits': …})`. (`## 401` also named "Obsidian not running"
as a symptom — the last line above says otherwise: `_obsidian_request` raises
for a refused connection and the door's own `except` already answered 502.
That is why this file drives the door instead of reading it.)

Three consumers read that lie and all three were already written to handle a
refusal correctly — they had simply never been shown one:

  · the Library pane          — `vaultSearch` throws on !r.ok, and `search()`
                                toasts "Search failed — <cause>"
  · the daytime VAULT_SEARCH  — same client function; on hits.length === 0 it
                                tells the coworker "No matches in the Library."
  · THE NIGHT SHIFT           — night_runner checks `s != 200` and says "Vault
                                search failed (%d)". That check exists because
                                of `test_a_search_that_failed_is_not_a_search_
                                that_found_nothing.py`, whose whole subject is
                                this lie one door further out: the coworker's
                                standing instruction is "Don't re-write notes
                                that already exist", a shut-out vault reported
                                no such note, and it duly wrote the note again,
                                night after night, with the run recording
                                errors: 0. The status that entry taught the
                                night shift to read is one `_rest_search` never
                                let turn non-200.

And the second door, same shape:

    GET /hermes/model, no config.yaml at all      -> 200 model=''
    GET /hermes/model, config.yaml UNREADABLE     -> 200 model=''
    GET /hermes/model, config.yaml not utf-8      -> 200 model=''
    GET /hermes/model, no model.default set       -> 200 model=''

The first and last are honest — a machine with no hermes on it, and a config
that genuinely sets nothing. The middle two are the office saying "no model is
set" about a file it never managed to open.

The fixes follow the office's own precedent for each door rather than
inventing a channel:

  · `_rest_search` RAISES, and the door's existing `except` turns that into
    the 502 `{"error": "obsidian: …"}` its two neighbours already answer with
    and its three consumers already read. The sentence is the office's §7
    shape — what went wrong, then what to do — and is deliberately DIGIT-FREE:
    the browser runs it through app/floor.jsx's officeCause on the way to the
    toast, and that table owns bare numbers (a sentence carrying "404" comes
    out as "the office couldn't find that — it may have been moved or
    renamed": wrong subject, wrong advice). Round 3 measures that by running
    the real classifier over the real sentences.

  · `/hermes/model` keeps its 200 and its presets and carries a
    `modelProblem` sentence ALONGSIDE the answer, the way /vault/status
    carries `restDetail` and `unanswered`. Not a 5xx: the client's
    `hermesGetModel` discards the whole body on any !r.ok, so a non-2xx would
    empty the preset list and take away the boss's only way to SET a model.
    The sentence names the file and does NOT say "pick one below anyway" —
    `write_model` opens the same file first and fails the same way.

Round 1 is structural and general where it can be. Round 2 is the invariant on
a real server: **a search the office could not PERFORM must not answer 2xx,
and a search that genuinely found nothing must**. Round 3 runs the browser's
own classifier over every sentence this door can emit and requires each to
come back unchanged — the general form of the digit trap above.

Run: python3 scripts/test_a_library_that_could_not_look_does_not_say_it_found_nothing.py
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = '') -> None:
    print(('  ok    ' if cond else '  FAIL  ') + name
          + ((f'  — {detail}') if not cond and detail else ''))
    if not cond:
        FAILS.append(name)


# ── Round 1: structural ────────────────────────────────────────────────────
def _fn(tree, name):
    return next((n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == name), None)


def _returns_empty_default(fn) -> list:
    """Lines where `fn` returns an empty literal ('' / [] / {} / None / 0 /
    False). The shape this whole entry is about."""
    out = []
    for r in ast.walk(fn):
        if not isinstance(r, ast.Return) or r.value is None:
            continue
        v = r.value
        if isinstance(v, ast.Constant) and (v.value in ('', 0, False, None)):
            out.append(r.lineno)
        elif isinstance(v, (ast.List, ast.Dict, ast.Tuple, ast.Set)):
            if not (getattr(v, 'elts', None) or getattr(v, 'keys', None)):
                out.append(r.lineno)
    return out


def structural_checks() -> None:
    print('round 1 — neither helper answers an empty default over a failure')
    serve_src = open(os.path.join(ROOT, 'serve.py'), encoding='utf-8').read()
    serve = ast.parse(serve_src)
    herm_src = open(os.path.join(ROOT, 'drivers', 'hermes.py'), encoding='utf-8').read()
    herm = ast.parse(herm_src)

    rs = _fn(serve, '_rest_search')
    check('_rest_search is still defined', rs is not None)
    if rs is not None:
        empties = _returns_empty_default(rs)
        check('_rest_search never returns an empty list over a refusal — it '
              'raises, so the door\'s own 502 arm answers',
              not empties, f'empty returns at lines {empties}')
        raises = [n for n in ast.walk(rs) if isinstance(n, ast.Raise)]
        check('…and it raises on BOTH the bad-status and the bad-body path',
              len(raises) >= 2, f'{len(raises)} raise(s)')

    ref = _fn(serve, '_obsidian_search_refusal')
    check('_obsidian_search_refusal exists (the sentence lives beside the '
          'door that speaks it)', ref is not None)

    rm = _fn(herm, 'read_model')
    rmp = _fn(herm, 'read_model_problem')
    rct = _fn(herm, '_read_config_text')
    check('read_model_problem exists', rmp is not None)
    check('_read_config_text exists — ONE reader, so the answer and the '
          'problem can never disagree about the same file', rct is not None)
    if rm is not None:
        check('read_model no longer swallows the read itself (no try/except '
              'of its own)',
              not [n for n in ast.walk(rm) if isinstance(n, ast.Try)])
    if rct is not None:
        handlers = [h for h in ast.walk(rct) if isinstance(h, ast.ExceptHandler)]
        names = []
        for h in handlers:
            t = h.type
            for nm in (t.elts if isinstance(t, ast.Tuple) else [t]):
                if isinstance(nm, ast.Name):
                    names.append(nm.id)
        check('a MISSING config.yaml is not reported as a problem — a machine '
              'with no hermes on it is not a failure, and "check the '
              'permissions" is false advice about a file that does not exist',
              'FileNotFoundError' in names, str(names))
        check('…and an unreadable one is: PermissionError and '
              'UnicodeDecodeError are named separately',
              'PermissionError' in names and 'UnicodeDecodeError' in names,
              str(names))
        check('no bare `except Exception` left in the reader — that is the '
              'catch-all this entry removed',
              'Exception' not in names, str(names))

    check('GET /hermes/model carries the sentence beside the answer',
          "'modelProblem': _drivers.hermes.read_model_problem()" in serve_src)
    check('…and still answers 200 with the presets intact (a non-2xx would '
          'make the client discard the whole body, presets included)',
          "_send_json(200, {'model': _drivers.hermes.read_model()," in serve_src)

    prov = open(os.path.join(ROOT, 'modals', 'providers.jsx'), encoding='utf-8').read()
    check('the Connections panel READS modelProblem', 'modelProblem' in prov)
    check('…and renders it — a field nothing draws is the same swallow one '
          'floor up', prov.count('hModelProblem') >= 4,
          f'{prov.count("hModelProblem")} mentions')


# ── plumbing ───────────────────────────────────────────────────────────────
def free_port() -> int:
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http_request(url, method='GET', body=None, headers=None):
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# A stand-in Obsidian Local REST API. MODE decides what it answers, so one
# server covers every way the real plugin can refuse.
MODE = ['ok-empty']


class _Obsidian(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        m = MODE[0]
        if m == 'ok-empty':
            body, status = b'[]', 200
        elif m == 'ok-hit':
            body, status = (json.dumps(
                [{'filename': 'Notes/quarterly.md', 'score': 3,
                  'matches': [{'context': 'the quarterly plan'}]}]
            ).encode('utf-8'), 200)
        elif m == 'garbage-200':
            body, status = b'<html>not json</html>', 200
        elif m == 'object-200':
            body, status = b'{"error":"something"}', 200
        else:
            body, status = b'{"message":"refused"}', int(m)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_PUT = do_GET


# Every way the plugin can answer without answering. Not five hand-picked
# statuses: an invariant over the whole class, so a status nobody thought of
# is covered by the same rule.
REFUSING_MODES = ['400', '401', '403', '404', '405', '429', '500', '502',
                  '503', 'garbage-200', 'object-200']

SENTENCES: list[str] = []


# ── Round 2: the invariant, on a real server ───────────────────────────────
def door_checks() -> None:
    print('round 2 — a real serve.py: a search that could not run must not '
          'answer 2xx')
    obs = HTTPServer(('127.0.0.1', 0), _Obsidian)
    threading.Thread(target=obs.serve_forever, daemon=True).start()
    port = free_port()
    vault = tempfile.mkdtemp(prefix='cafresohq-cantlook-vault-')
    state = tempfile.mkdtemp(prefix='cafresohq-cantlook-state-')
    hhome = tempfile.mkdtemp(prefix='cafresohq-cantlook-hermes-')
    stub_bin = tempfile.mkdtemp(prefix='cafresohq-cantlook-bin-')
    proc = None
    try:
        env = dict(os.environ)
        env.update({
            'CAFRESOHQ_API_KEY': 'regression-test-key',
            'CAFRESOHQ_HQ_STATE_DIR': state,
            'CAFRESOHQ_VAULT': vault,
            'CAFRESOHQ_VAULT_BACKEND': 'rest',
            'CAFRESOHQ_OBSIDIAN_URL': 'http://127.0.0.1:%d' % obs.server_address[1],
            'CAFRESOHQ_OBSIDIAN_KEY': 'obviously-fake-test-key',
            # Scoped away from the real ~/.hermes so this file can make the
            # config unreadable without touching the boss's own office. The
            # empty PATH is deliberate too: nothing here may find a real
            # `hermes` binary to restart.
            'HERMES_HOME': hhome,
            'PATH': stub_bin,
            'PORT': str(port),
            'GAP_CRON': '0', 'NEWS_CRON': '0', 'TOPICS_CRON': '0',
        })
        for k in ('OPENAI_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY',
                  'FAL_KEY', 'ANTHROPIC_API_KEY'):
            env.pop(k, None)
        proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        H = {'X-API-Key': 'regression-test-key',
             'Content-Type': 'application/json'}
        for _ in range(200):
            try:
                http_request(base + '/health')
                break
            except Exception:
                if proc.poll() is not None:
                    check('serve.py stayed up through startup', False,
                          'exited early')
                    return
                time.sleep(0.1)
        else:
            check('serve.py became ready', False, 'timed out')
            return

        # --- the search door -------------------------------------------------
        for mode in REFUSING_MODES:
            MODE[0] = mode
            st, raw = http_request(base + '/vault/search?q=quarterly', headers=H)
            body = json.loads(raw or b'{}')
            print(f'    obsidian {mode:12s} -> HTTP {st} '
                  f'{raw[:120].decode("utf-8", "replace")}')
            check(f'obsidian {mode}: the office does NOT answer 2xx over a '
                  f'search it could not perform', not (200 <= st < 300),
                  f'HTTP {st} {raw[:120].decode("utf-8", "replace")}')
            check(f'obsidian {mode}: …and says why, in a sentence',
                  bool(body.get('error')), raw[:120].decode('utf-8', 'replace'))
            sentence = str(body.get('error', ''))
            if sentence.startswith('obsidian: '):
                SENTENCES.append(sentence)
            check(f'obsidian {mode}: the sentence is the office\'s voice, not '
                  'a raw dump — no status code, no errno, no stack',
                  not any(c.isdigit() for c in sentence)
                  and '\n' not in sentence and len(sentence) <= 90,
                  repr(sentence))

        # The other side, and the whole point of the distinction.
        MODE[0] = 'ok-empty'
        st, raw = http_request(base + '/vault/search?q=quarterly', headers=H)
        print(f'    obsidian {"ok-empty":12s} -> HTTP {st} '
              f'{raw[:120].decode("utf-8", "replace")}')
        check('a search that genuinely found nothing is STILL a 200 with an '
              'empty hit list — "nothing there" and "could not look" are now '
              'different answers, which is the entire fix',
              st == 200 and json.loads(raw).get('hits') == [],
              f'HTTP {st} {raw[:120].decode("utf-8", "replace")}')

        MODE[0] = 'ok-hit'
        st, raw = http_request(base + '/vault/search?q=quarterly', headers=H)
        hits = json.loads(raw or b'{}').get('hits', [])
        print(f'    obsidian {"ok-hit":12s} -> HTTP {st} '
              f'{raw[:120].decode("utf-8", "replace")}')
        check('a search that found something still works, unchanged',
              st == 200 and len(hits) == 1
              and hits[0]['path'] == 'Notes/quarterly.md'
              and hits[0]['snippet'] == 'the quarterly plan',
              f'HTTP {st} {hits}')

        check('the run actually exercised refusals (an invariant nothing '
              'exercises passes trivially)',
              len(SENTENCES) >= len(REFUSING_MODES), f'{len(SENTENCES)}')
        check('the refusals are not one sentence repeated — the office says '
              'which KIND of refusal it was', len(set(SENTENCES)) >= 3,
              str(sorted(set(SENTENCES))))

        # --- the model door --------------------------------------------------
        cfg = os.path.join(hhome, 'config.yaml')

        def model_probe():
            st, raw = http_request(base + '/hermes/model', headers=H)
            d = json.loads(raw or b'{}')
            return st, d.get('model', ''), d.get('modelProblem', ''), d

        st, model, problem, d = model_probe()
        print(f'    hermes  {"no config.yaml":16s} -> HTTP {st} '
              f'model={model!r} problem={problem!r}')
        check('no config.yaml at all: silence, not a warning — a machine with '
              'no hermes on it has no model, and that IS the answer',
              st == 200 and model == '' and problem == '', f'{problem!r}')

        with open(cfg, 'w', encoding='utf-8') as f:
            f.write('model:\n  default: a-model-that-is-set\n')
        st, model, problem, d = model_probe()
        print(f'    hermes  {"a real config":16s} -> HTTP {st} '
              f'model={model!r} problem={problem!r}')
        check('a readable config still reports its model, and says nothing '
              'is wrong', st == 200 and model == 'a-model-that-is-set'
              and problem == '', f'{model!r} / {problem!r}')

        with open(cfg, 'w', encoding='utf-8') as f:
            f.write('provider: somewhere\n')
        st, model, problem, d = model_probe()
        print(f'    hermes  {"no model.default":16s} -> HTTP {st} '
              f'model={model!r} problem={problem!r}')
        check('a config that genuinely sets no model: still silence — this is '
              '"nothing there", the same as an empty hit list',
              st == 200 and model == '' and problem == '', f'{problem!r}')

        unreadable = []
        with open(cfg, 'w', encoding='utf-8') as f:
            f.write('model:\n  default: a-model-that-is-set\n')
        os.chmod(cfg, 0o000)
        st, model, problem, d = model_probe()
        print(f'    hermes  {"unreadable":16s} -> HTTP {st} '
              f'model={model!r} problem={problem[:80]!r}')
        unreadable.append(('unreadable (mode 000)', st, model, problem, d))
        os.chmod(cfg, 0o644)

        with open(cfg, 'wb') as f:
            f.write(b'model:\n  default: \xff\xfe not utf-8\n')
        st, model, problem, d = model_probe()
        print(f'    hermes  {"not utf-8":16s} -> HTTP {st} '
              f'model={model!r} problem={problem[:80]!r}')
        unreadable.append(('not utf-8', st, model, problem, d))

        for label, st, model, problem, d in unreadable:
            check(f'{label}: the office says it could not READ the file, '
                  'instead of reporting "no model set" over a file that sets '
                  'one', bool(problem), f'HTTP {st} model={model!r}')
            check(f'{label}: …still a 200 carrying the presets, so the boss '
                  'can still SET a model',
                  st == 200 and len(d.get('presets') or []) >= 1,
                  f'HTTP {st} presets={len(d.get("presets") or [])}')
            check(f'{label}: …and the sentence names the file it means',
                  cfg in problem, problem[:160])
            check(f'{label}: …and offers a way forward that is not "pick one '
                  'below" — write_model opens the same file first and fails '
                  'the same way', 'reopen this panel' in problem,
                  problem[:160])
            check(f'{label}: …with no errno, no traceback, no Python noise',
                  'Traceback' not in problem and 'Errno' not in problem
                  and '\n' not in problem, problem[:160])
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        obs.shutdown()
        subprocess.run(['chmod', '-R', 'u+rwX', hhome], check=False)
        subprocess.run(['rm', '-rf', vault, state, hhome, stub_bin], check=False)
        # The one thing that must never have happened: drivers/hermes.py's
        # gateway_restart() is a bare PATH lookup for `hermes`. This file
        # pins PATH to an empty directory so it cannot find the real binary.
        out = subprocess.run(['ps', 'ax'], capture_output=True, text=True).stdout
        check('no `hermes gateway restart` was launched by this test',
              'hermes gateway restart' not in out)


# ── Round 3: the sentence survives the browser's own classifier ────────────
def classifier_checks() -> None:
    """views/vault.jsx toasts `Search failed — ${officeCause(e.message)}`, so
    the sentence the server picked is not the sentence the boss reads unless
    officeCause declines to claim it. Run the REAL classifier, from the real
    file, over the REAL strings — the general form of the digit trap: any
    future refusal sentence that trips a rule in OFFICE_CAUSES fails here."""
    print('round 3 — the browser\'s classifier leaves the office\'s own '
          'sentence alone')
    floor = os.path.join(ROOT, 'app', 'floor.jsx')
    if not os.path.isfile(floor):
        check('app/floor.jsx exists', False)
        return
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return
    if not SENTENCES:
        check('round 2 collected sentences to classify', False)
        return
    text = open(floor, encoding='utf-8').read()
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    # The client throws `j.error`, which is the whole `obsidian: …` string.
    cases = ('console.log(JSON.stringify(%s.map(s => [s, officeCause(s), '
             'obsidianCause(s)])));' % json.dumps(SENTENCES))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr[-800:], file=sys.stderr)
        check('the floor.jsx classifier harness ran', False)
        return
    rows = json.loads(proc.stdout.strip().split('\n')[-1])
    seen = set()
    for raw, office, obsid in rows:
        stripped = raw.split('obsidian: ', 1)[-1]
        if stripped in seen:
            continue
        seen.add(stripped)
        print(f'    {stripped[:64]:66s} -> {office[:66]}')
        # Unchanged is the whole assertion. officeCause only rewrites a string
        # when one of its patterns claims it, and every one of those rewrites
        # would be a sentence about a DIFFERENT subject (the office, a missing
        # file, a permission) than the one the server actually meant.
        check('officeCause leaves the office\'s own sentence alone for '
              f'{stripped[:44]!r}', office == raw, repr(office))
        check('…and does not truncate it (cleanCause caps at 90 chars '
              'INCLUDING the "obsidian: " prefix)', not office.endswith('…'),
              repr(office))
        check('…and so does obsidianCause, the classifier the vault view uses '
              f'for Obsidian failures, for {stripped[:36]!r}',
              obsid == raw, repr(obsid))


def main() -> int:
    structural_checks()
    door_checks()
    classifier_checks()
    print()
    if FAILS:
        print(f'{len(FAILS)} check(s) FAILED:')
        for f in FAILS:
            print('  · ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
