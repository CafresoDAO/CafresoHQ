#!/usr/bin/env python3
"""The first wall a beta tester meets answered with a JSON blob.

The tour's key step (`OnboardingKeyStep` in ui/onboarding.jsx) is the
first thing a new HQ asks anyone to DO. #297 taught it to read
`hermesSetOpenRouterKey`'s reply correctly — a falsy `serverStored` is a
failure, not a green tick — and then printed the reply's `detail` field
verbatim, in brackets, under a fixed lead sentence:

    {saved === 'err' && ('✕ Couldn\\'t save — check the key and try again.'
                        + (saveDetail ? ' (' + saveDetail + ')' : ''))}

`detail` is a DIAGNOSTIC, not prose. `hermesSetProvider` assembles it as
`server ${r.status}: ${t.slice(0, 120)}` — a status code, a colon, and
120 raw bytes of whatever the office's response body was. Driven live
2026-09-05 against a real `serve.py` (POST /hermes/provider with a
malformed key; the host's own regex gate refuses it before any driver
runs), the tour card read:

    ✕ Couldn't save — check the key and try again.
      (server 400: {"error": "invalid OpenRouter key"})

An HTTP status code and a JSON object, on the surface with the least
experienced reader in the app standing in front of it. That is the raw
dump OFFICE_AS_INTERFACE §7 forbids, in the one place §7 costs the most.

The second reading is worse than raw, because it is WRONG. When the
browser cannot reach the office at all, `hermesSetProvider`'s catch
returns `detail: 'offline — saved locally'`, and the same line rendered:

    ✕ Couldn't save — check the key and try again. (offline — saved locally)

Nothing is wrong with the key. Nobody ever looked at it. The sentence
sends the tester away to re-copy a perfectly good key — the misdiagnosis
app/floor.jsx's own commentary calls worse than a vague honest answer —
and then contradicts itself two words later by calling the thing it just
named a failure "saved locally".

The fix is the sibling pattern this codebase keeps paying out on: the
helper already exists, and this path did not use it. app/floor.jsx holds
five cause classifiers, one per SUBJECT (a brain, the office, a repo,
Obsidian, nothing-known-for-certain), each turning a raw failure into one
honest sentence naming the cause and the way forward. A key save is a
sixth subject, so `KEY_CAUSES` / `keyCause` / `keyOpener` join them, and
the tour card renders `'✕ ' + keyOpener(saveDetail) + '.'`:

    ✕ Your office read that key and turned it down as the wrong shape —
      copy it again from openrouter.ai/keys, whole, including the
      sk-or-v1 prefix.

    ✕ Couldn't reach your office to save that key — check it's still
      running, then hit Save again.

`saveDetail` still holds the server's own words; #297's assertion that
they reach the reader still holds through `keyCause`'s fallback, which
repeats the office's authored `error` string (via `serverWords`, then
cleanCause) whenever the classifier cannot place the failure. What it no
longer does is repeat the envelope a machine wrapped it in.

This suite:
  · boots a REAL serve.py on a scratch HOME and POSTs a malformed key, so
    the status and body under test are the ones the office actually
    sends, not a paraphrase;
  · runs the REAL `hermesSetProvider` under node against that live reply
    to build the detail string exactly as the shipped client would;
  · evaluates the REAL render expression lifted out of ui/onboarding.jsx
    with the REAL keyOpener lifted out of app/floor.jsx, and checks the
    rendered line for a status code, JSON shrapnel, a stack, an
    [object Object] and an `undefined`;
  · checks each sentence names a WAY FORWARD, and that the unreachable
    office is no longer blamed on the tester's key;
  · pins the source-level shape so nobody re-appends a raw detail.

Run: python3 scripts/test_a_refused_key_is_told_in_words_not_in_a_status_code.py
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_the_front_desk_sells_what_exists import (  # noqa: E402
    brace_lift, strip_comments)

ONB = ROOT / 'ui' / 'onboarding.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'
CLIENT = ROOT / 'claude-client.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── the live office ─────────────────────────────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def post(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={'content-type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:                       # noqa: BLE001
        return 0, str(e)


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception:                            # noqa: BLE001
        return 0, b''


def boot(home):
    """A real serve.py, pointed at a scratch HOME.

    The path under test (a key the host's own regex refuses) is rejected
    before the hermes driver is reached, so nothing is written anywhere —
    but HOME is redirected regardless, because a test that can rewrite the
    developer's own ~/.hermes/config.yaml is a test nobody should run
    twice."""
    port = free_port()
    env = dict(os.environ, PORT=str(port), HOME=str(home),
               CAFRESOHQ_HQ_STATE_DIR=str(home / 'state'),
               CAFRESOHQ_VAULT=str(home / 'vault'),
               CAFRESOHQ_ALLOWED_DIRS=str(home / 'work'))
    for k in ('OPENROUTER_API_KEY', 'CAFRESOHQ_VAULT_BACKEND',
              'CAFRESOHQ_OBSIDIAN_URL', 'CAFRESOHQ_OBSIDIAN_KEY'):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port

    def kill():
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    for _ in range(80):
        if get(base + '/hermes/trial-status')[0] == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


# ── the real client + the real render, under node ───────────────────────
def run_js(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=90)
    if p.returncode != 0:
        print(p.stderr[-2000:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


def floor_source():
    text = FLOOR.read_text(encoding='utf-8')
    return '\n'.join(ln for ln in text.split('\n')
                     if not ln.startswith('import ') and not ln.startswith('export '))


def render_expr():
    """The 'err' line, lifted verbatim from the tour card.

    Comments stripped first — the fix is explained in a comment right above
    this line that quotes the OLD broken expression, so an un-stripped lift
    would grab the obituary instead of the code."""
    bare = strip_comments(ONB.read_text(encoding='utf-8'))
    m = re.search(r"saved === 'err'\s*&&\s*\(([\s\S]*?)\)\}", bare)
    if not m:
        raise SystemExit("could not find the 'err' branch in ui/onboarding.jsx")
    return m.group(1).strip()


def client_detail(status, body):
    """Build the detail string the SHIPPED client would, from the live reply.

    `hermesSetProvider` is lifted whole out of claude-client.jsx and run
    with fetch answering exactly what the office just answered."""
    fn = brace_lift(CLIENT.read_text(encoding='utf-8'),
                    'async function hermesSetProvider(')
    js = ("const HERMES_PROVIDER_KEY_FIELD = { openrouter: 'openrouterKey' };\n"
          "const HERMES_LOCAL_PROVIDERS = ['lmstudio', 'ollama'];\n"
          "const _API_BASE = '';\n"
          "const setSettings = () => {};\n"
          "const STATUS = %d, BODY = %s;\n"
          "globalThis.fetch = async () => ({\n"
          "  ok: STATUS >= 200 && STATUS < 300, status: STATUS,\n"
          "  json: async () => JSON.parse(BODY), text: async () => BODY });\n"
          % (status, json.dumps(body))
          + fn + '\n'
          + "const r = await hermesSetProvider('openrouter', 'sk-or-nope', '');\n"
            "console.log(JSON.stringify(r));")
    return run_js(js)


def rendered(details):
    expr = render_expr()
    js = (floor_source() + '\n'
          + 'const D = %s;\n' % json.dumps(details)
          + 'const OUT = {};\n'
            'for (const [name, saveDetail] of Object.entries(D)) OUT[name] = (%s);\n'
            'console.log(JSON.stringify(OUT));' % expr)
    return run_js(js)


BAD_SHAPES = [
    ('an HTTP status code', re.compile(r'\b(?:server\s+)?[1-5]\d\d\b')),
    ('JSON shrapnel', re.compile(r'[{}\[\]]|"\w+"\s*:')),
    ('a stack frame', re.compile(r'\bat \S+:\d+|Traceback|Error:')),
    ('an [object Object]', re.compile(r'\[object \w+\]')),
    ('a bare undefined', re.compile(r'\b(?:undefined|null|NaN)\b')),
]

# A sentence is only finished when it says what to do next. These are the
# verbs the office's own KEY_CAUSES sentences offer.
WAY_FORWARD = re.compile(
    r'copy it again|hit Save again|check it is running|check it’s still running|'
    r"check it's still running|pick a different one|will say why", re.I)


def main():
    print('a refused key is told in words, not in a status code')

    # ── 1. source shape: the raw detail is no longer concatenated ────────
    bare = strip_comments(ONB.read_text(encoding='utf-8'))
    check('the tour card no longer pastes the raw detail into the line',
          not re.search(r"saveDetail \? ' \(' \+ saveDetail", bare),
          "that is the whole bug — `detail` is a diagnostic, and it was "
          'being read out to a first-time user in brackets')
    check('...and no longer blames the key whatever the cause',
          "check the key and try again" not in bare,
          'an office that never answered is not a bad key')
    check('the card routes the failure through the floor classifier',
          'keyOpener(saveDetail)' in bare
          and re.search(r"import \{[^}]*keyOpener[^}]*\} from '\.\./app/floor\.jsx'", bare),
          'the helper exists; this path has to use it')
    floor_bare = strip_comments(FLOOR.read_text(encoding='utf-8'))
    for name in ('KEY_CAUSES', 'function keyCause', 'function keyOpener',
                 'function serverWords'):
        check(f'app/floor.jsx defines {name}',
              name in floor_bare,
              'the sixth subject lives beside the other five')
    check('keyCause is exported',
          re.search(r'^export \{[^}]*\bkeyCause\b', FLOOR.read_text(encoding='utf-8'),
                    re.M),
          'onboarding cannot import what floor does not export')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arms')
        return 1 if FAILS else 0

    # ── 2. the office, for real ──────────────────────────────────────────
    live_detail = None
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        (home / 'work').mkdir()
        (home / 'vault').mkdir()
        base, kill = boot(home)
        try:
            if not base:
                check('serve.py answered', False, 'the office never came up')
            else:
                status, body = post(base + '/hermes/provider',
                                    {'provider': 'openrouter', 'key': 'sk-or-oops'})
                check('a malformed key is refused by the real office',
                      status == 400 and 'invalid OpenRouter key' in body,
                      f'{status} {body!r}')
                check('...and the refusal really is a JSON body',
                      body.strip().startswith('{'),
                      f'{body!r} — this is the material the card used to '
                      'print verbatim')
                r = client_detail(status, body)
                live_detail = (r or {}).get('detail', '')
                check('the shipped client turns it into a status-coded diagnostic',
                      live_detail.startswith('server 400:') and '{' in live_detail,
                      f'{live_detail!r} — if this contract changes, the render '
                      'below is being measured against the wrong input')
                check('...and still reports the failure as ok:true + '
                      'serverStored:false',
                      r.get('ok') is True and r.get('serverStored') is False,
                      f'{r!r} — #297 rests on this too')
        finally:
            kill()

    # ── 3. what the tester actually reads ────────────────────────────────
    details = {
        # the live one, exactly as the client built it
        'refused': live_detail or 'server 400: {"error": "invalid OpenRouter key"}',
        # the browser could not reach the office at all
        'offline': 'offline — saved locally',
        # no client on the page at all (the step's own fallback reply)
        'no_client': 'no connection to your office',
        # the office broke while writing the key down
        'broken': ('server 500: {"error": "write .env: [Errno 13] Permission '
                   "denied: '/root/.hermes/.env'\"}"),
        # an office that refused and said nothing whatsoever
        'silent': '',
    }
    out = rendered(details)
    for name, line in sorted(out.items()):
        print(f'    {name}: {line}')
    print()

    for name, line in sorted(out.items()):
        for shape_name, rx in BAD_SHAPES:
            check(f'the {name} line shows no {shape_name}',
                  not rx.search(line), repr(line))
        check(f'the {name} line says what to do next',
              bool(WAY_FORWARD.search(line)),
              repr(line) + ' — §7 wants the cause AND the way forward; a red '
              'line with no next step is a dead end')
        check(f'the {name} line is one sentence a person could read aloud',
              len(line) <= 190 and '\n' not in line, repr(line))

    # ── 4. the wrong diagnosis specifically ──────────────────────────────
    for name in ('offline', 'no_client'):
        check(f'the {name} line does not blame the key',
              'wrong shape' not in out[name] and 'copy it again' not in out[name]
              and 'check the key' not in out[name],
              repr(out[name]) + ' — nobody looked at the key; saying so sends '
              'the tester to re-paste a key that was never the problem')
        check(f'the {name} line names the office as the thing to check',
              'office' in out[name],
              repr(out[name]))
        check(f'the {name} line does not also claim it saved',
              'saved locally' not in out[name],
              repr(out[name]) + ' — the old line called it a failure and a '
              'save in the same breath')
    check('the refused line does name the key, and where to get another',
          'openrouter.ai/keys' in out['refused'] and 'sk-or' in out['refused'],
          repr(out['refused']) + ' — this one really IS the key, and the fix '
          'must not trade a raw blob for a vague shrug')
    check("the office's own words survive an unclassifiable refusal",
          'teapot' in rendered({'odd': 'server 418: {"error": "the office is '
                                       'a teapot"}'})['odd'],
          'the fallback repeats what the office said; it just drops the '
          'envelope the status code came in')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
