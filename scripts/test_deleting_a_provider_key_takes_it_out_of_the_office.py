#!/usr/bin/env python3
"""Deleting a Hermes provider key said it was gone; the office kept it.

Settings → Connections → "Hermes brain (runs in your office)" renders the
active backend's key in a password field whose `defaultValue` is the saved
key, so selecting it and deleting it is the obvious — and only — way to take
a key back out of an office. Blurring the empty field lands on `saveKey` in
modals/providers.jsx, which asked `hermesSetProvider` to save an empty key
and then printed, in green, with a tick:

    ✓ OpenRouter key cleared

Nothing was cleared anywhere but this browser. `hermesSetProvider` opened
with

    if (!trimmed && !local) return { ok: true, serverStored: false, detail: 'cleared' };

after having already wiped the browser's own copy — so the removal never
left the tab. Measured against a REAL serve.py on a scratch HOME (this
file's own live-office half, before the fix):

    POST /hermes/provider {"provider":"openrouter","key":"sk-or-v1-…"}
      → 200, ~/.hermes/.env: OPENROUTER_API_KEY=sk-or-v1-…
    POST /hermes/provider {"provider":"openrouter","key":""}
      → 400 {"error": "invalid OpenRouter key"}
    GET  /hermes/provider
      → {"configured": true}      ← still there, still answering

Even had the client sent it, the office refused it: `_hermes_set_provider`
ran the empty string through the provider's key regex and turned it down as
malformed. There was no way, from anywhere in the app, to take a key out of
an office once it was in.

Three things follow, and all three are worse than the missing feature:

  · the key stays in the container's ~/.hermes/.env at 0600 and the running
    gateway goes on authenticating with it. A boss removing a key BECAUSE it
    leaked is told, in the affirmative, that it is gone;
  · the browser copy is the one that really is gone, so
    `hermesEnsureProvider` — the "keys vanish on recreate" repair — has
    nothing left to re-push, and the Connections field now renders empty
    beside an office still running on that key. The screen and the office
    disagree, and the screen is the one the boss believes;
  · `GET /hermes/provider` still answers `configured: true`, so nothing else
    in the office ever notices either.

Fix: an empty key for a cloud backend is a REMOVAL and it travels.
`clear_provider_key` in drivers/hermes.py drops the provider's line from
~/.hermes/.env, drops it from this process's env, and restarts the gateway
so the running one stops holding it; `_hermes_set_provider` routes an empty
cloud key there instead of through the key regex; the client stops
short-circuiting and drops the browser copy only once the office confirms —
so a failed removal leaves the key that still needs re-pushing where it is.
And `saveKey` says which of the two happened.

This suite drives both halves for real:
  · a REAL serve.py on a scratch HOME, with a stub `hermes` first on PATH so
    the restart is observed and no real gateway is touched, exercising set →
    clear → read-back on disk;
  · the REAL `hermesSetProvider` (claude-client.jsx) and the REAL `saveKey`
    (modals/providers.jsx) lifted under node against a scripted office.

Every key in this file is a fake of the right SHAPE — the host's regex gate
is part of what is under test, so the values have to pass it, and none of
them is real.

Run: python3 scripts/test_deleting_a_provider_key_takes_it_out_of_the_office.py
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / 'claude-client.jsx'
PROVIDERS = ROOT / 'modals' / 'providers.jsx'

# Fakes of the right shape. `sk-or-…` / `gsk_…` are the prefixes the host's
# regex demands; the bodies are nonsense on purpose.
FAKE_OR = 'sk-or-v1-test-not-a-real-key-000000'
FAKE_GROQ = 'gsk_testnotarealkey0000000000'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── lifting real source ─────────────────────────────────────────────────
def _balance(src, i):
    depth = 0
    j = i
    while j < len(src):
        c = src[j]
        if c in '{([':
            depth += 1
        elif c in '})]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[i:j + 1]
        j += 1
    return None


def extract_const(src, name):
    m = re.search(r'\bconst\s+' + re.escape(name) + r'\s*=\s*', src)
    if not m:
        return None
    val = _balance(src, m.end())
    return None if val is None else ('const %s = %s' % (name, val))


def brace_lift(src, header):
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces after ' + header)


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
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:                       # noqa: BLE001
        return 0, str(e)


def boot(home):
    """A real serve.py on a scratch HOME, with a stub `hermes` first on PATH.

    The stub matters twice. `gateway_restart` is the ONE call site that
    replaces the running gateway, and this test asserts a removal reaches it
    — but a developer box with a real `hermes` on PATH would have its own
    gateway restarted by a test run, which is not a thing a test may do. The
    stub records the call and exits."""
    binp = home / 'bin'
    binp.mkdir(parents=True, exist_ok=True)
    stub = binp / 'hermes'
    stub.write_text('#!/bin/sh\necho "$@" >> "%s/hermes-calls.log"\nexit 0\n'
                    % home, encoding='utf-8')
    stub.chmod(0o755)
    port = free_port()
    env = dict(os.environ, PORT=str(port), HOME=str(home),
               HERMES_HOME=str(home / '.hermes'),
               CAFRESOHQ_HQ_STATE_DIR=str(home / 'state'),
               CAFRESOHQ_VAULT=str(home / 'vault'),
               CAFRESOHQ_ALLOWED_DIRS=str(home / 'work'),
               PATH=str(binp) + ':/usr/bin:/bin')
    for k in ('OPENROUTER_API_KEY', 'GOOGLE_API_KEY', 'GROQ_API_KEY',
              'CAFRESOHQ_VAULT_BACKEND', 'CAFRESOHQ_OBSIDIAN_URL',
              'CAFRESOHQ_OBSIDIAN_KEY'):
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


def live_office():
    home = Path(tempfile.mkdtemp(prefix='hq-key-removal-'))
    base, kill = boot(home)
    if not base:
        check('a real serve.py came up on a scratch HOME', False)
        return
    try:
        envf = home / '.hermes' / '.env'
        set_status, set_body = post(base + '/hermes/provider',
                                    {'provider': 'openrouter', 'key': FAKE_OR,
                                     'model': ''})
        check('a key can be put into the office (baseline)',
              set_status == 200, '%s %s' % (set_status, set_body))
        check('and it lands in ~/.hermes/.env',
              envf.is_file() and 'OPENROUTER_API_KEY=' + FAKE_OR in envf.read_text(),
              'env file did not carry the key')

        calls = home / 'hermes-calls.log'
        time.sleep(0.7)   # the restart is a Popen; let the stub finish writing
        restarts_before = (calls.read_text().count('gateway restart')
                           if calls.is_file() else 0)

        clr_status, clr_body = post(base + '/hermes/provider',
                                    {'provider': 'openrouter', 'key': '',
                                     'model': ''})
        check('emptying the key is accepted as a removal, not refused as a bad key',
              clr_status == 200,
              '%s %s — an empty field is the only remove control this screen has'
              % (clr_status, clr_body))
        try:
            clr = json.loads(clr_body)
        except Exception:                        # noqa: BLE001
            clr = {}
        check('the office says it removed the key',
              clr.get('cleared') is True, clr_body)

        env_txt = envf.read_text(encoding='utf-8') if envf.is_file() else ''
        check('the key is no longer in ~/.hermes/.env',
              FAKE_OR not in env_txt,
              'the office still holds the key the boss was told was gone')
        check('no empty OPENROUTER_API_KEY line is left behind either',
              not re.search(r'(?m)^OPENROUTER_API_KEY\s*=', env_txt), env_txt)

        time.sleep(0.7)   # the restart is a Popen; let the stub finish writing
        restarts_after = (calls.read_text().count('gateway restart')
                          if calls.is_file() else 0)
        check('the running gateway is restarted so it stops holding the key',
              restarts_after > restarts_before,
              'a key removed from disk is still live in the process that read it')

        st, body = get(base + '/hermes/provider')
        check('and the office now reports itself as having no key',
              st == 200 and json.loads(body).get('configured') is False,
              body)

        # ── pins: what must keep working alongside the removal ───────────
        bad_status, bad_body = post(base + '/hermes/provider',
                                    {'provider': 'openrouter', 'key': 'nonsense',
                                     'model': ''})
        check('a malformed key is still refused (removal is not a hole)',
              bad_status == 400, '%s %s' % (bad_status, bad_body))

        loc_status, loc_body = post(base + '/hermes/provider',
                                    {'provider': 'lmstudio', 'key': '',
                                     'base_url': 'http://localhost:1234/v1'})
        check('a local backend still configures with no key at all',
              loc_status == 200 and json.loads(loc_body).get('cleared') is not True,
              '%s %s — local backends have no key; an empty one is not a removal'
              % (loc_status, loc_body))

        g2_status, g2_body = post(base + '/hermes/provider',
                                  {'provider': 'groq', 'key': FAKE_GROQ})
        check('a second provider can still be set after a removal',
              g2_status == 200, '%s %s' % (g2_status, g2_body))
        gclr_status, _gb = post(base + '/hermes/provider',
                                {'provider': 'groq', 'key': ''})
        env_txt = envf.read_text(encoding='utf-8') if envf.is_file() else ''
        check('removing one provider\'s key removes that provider\'s key',
              gclr_status == 200 and FAKE_GROQ not in env_txt, env_txt)
    finally:
        kill()


# ── the real client + the real saveKey, under node ──────────────────────
HARNESS = r"""
'use strict';
%(hbackends)s

const _API_BASE = '';
const HERMES_PROVIDER_KEY_FIELD = { openrouter: 'openrouterKey',
                                    gemini: 'geminiKey', groq: 'groqKey' };
const HERMES_LOCAL_PROVIDERS = ['lmstudio', 'ollama'];

let settings = {};
let fetches = [];
let REPLY = { status: 200, body: '{"ok":true,"cleared":true,"restarted":true}' };
let THROW = false;

const setSettings = (p) => { Object.assign(settings, p); };
globalThis.fetch = async (url, init) => {
  fetches.push({ url, body: init && init.body ? JSON.parse(init.body) : null });
  if (THROW) throw new Error('network down');
  return {
    ok: REPLY.status >= 200 && REPLY.status < 300,
    status: REPLY.status,
    json: async () => JSON.parse(REPLY.body),
    text: async () => REPLY.body,
  };
};

%(setprovider)s

/* the component context saveKey closes over */
let probeResult = null, keyBusy = false;
const s = new Proxy({}, { get: (_t, k) => settings[k] });
const update = (p) => { Object.assign(settings, p); };
const setProbeResult = (v) => { probeResult = v; };
const setKeyBusy = (v) => { keyBusy = v; };
const C = { hermesSetProvider };

%(savekey)s

function reset(initial, reply) {
  settings = Object.assign({}, initial);
  fetches = []; probeResult = null; keyBusy = false; THROW = false;
  REPLY = reply || { status: 200, body: '{"ok":true,"cleared":true,"restarted":true}' };
}

async function run() {
  const out = {};

  /* 1. THE BUG. A key is on file; the boss empties the field and blurs. */
  reset({ hermesBackend: 'openrouter', openrouterKey: 'sk-or-v1-onfile' });
  await saveKey('openrouter', '');
  out.cleared = { fetches: fetches.slice(), probe: probeResult,
                  local: settings.openrouterKey, busy: keyBusy };

  /* 2. The office refuses the removal — the browser copy must survive, or
        the key that still needs re-pushing is the one thing thrown away. */
  reset({ hermesBackend: 'openrouter', openrouterKey: 'sk-or-v1-onfile' },
        { status: 500, body: 'boom' });
  await saveKey('openrouter', '');
  out.refused = { fetches: fetches.slice(), probe: probeResult,
                  local: settings.openrouterKey };

  /* 3. The office is not answering at all. */
  reset({ hermesBackend: 'openrouter', openrouterKey: 'sk-or-v1-onfile' });
  THROW = true;
  await saveKey('openrouter', '');
  out.offline = { probe: probeResult, local: settings.openrouterKey };

  /* 4. PIN — saving a real key still behaves exactly as before. */
  reset({ hermesBackend: 'openrouter' },
        { status: 200, body: '{"ok":true,"restarted":true}' });
  await saveKey('openrouter', 'sk-or-v1-brand-new');
  out.saved = { fetches: fetches.slice(), probe: probeResult,
                local: settings.openrouterKey };

  /* 5. PIN — a local backend's empty key is not a removal; it still pushes
        its URL, and never writes a key field. */
  reset({ hermesBackend: 'openrouter' },
        { status: 200, body: '{"ok":true,"restarted":true}' });
  const lr = await hermesSetProvider('lmstudio', '', 'local-model',
                                     'http://localhost:1234/v1');
  out.local = { fetches: fetches.slice(), r: lr, settings: Object.assign({}, settings) };

  return out;
}

run().then(o => console.log('__RESULT__' + JSON.stringify(o)))
     .catch(e => console.log('__ERROR__' + (e && e.stack || e)));
"""


def node_half():
    ctext = CLIENT.read_text(encoding='utf-8')
    ptext = PROVIDERS.read_text(encoding='utf-8')
    setprovider = brace_lift(ctext, 'async function hermesSetProvider(')
    hbackends = extract_const(ptext, 'HBACKENDS')
    savekey = extract_const(ptext, 'saveKey')
    check('hermesSetProvider lifted from claude-client.jsx', bool(setprovider))
    check('HBACKENDS lifted from modals/providers.jsx', hbackends is not None)
    check('saveKey lifted from modals/providers.jsx', savekey is not None)
    if not (setprovider and hbackends and savekey):
        return

    js = HARNESS % {'hbackends': hbackends, 'setprovider': setprovider,
                    'savekey': savekey}
    tmp = ROOT / '.key_removal_harness.mjs'
    tmp.write_text(js, encoding='utf-8')
    try:
        p = subprocess.run(['node', str(tmp)], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=90)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    if '__RESULT__' not in p.stdout:
        check('the harness ran the lifted source', False,
              (p.stdout + p.stderr)[-1200:])
        return
    out = json.loads(p.stdout.split('__RESULT__', 1)[1].strip().splitlines()[0])

    cl = out['cleared']
    check('emptying the key field sends the removal to the office',
          len(cl['fetches']) == 1,
          'the removal never left the browser: fetches=%s' % (cl['fetches'],))
    if cl['fetches']:
        check('it asks the office to remove THAT provider\'s key',
              cl['fetches'][0]['body'].get('provider') == 'openrouter'
              and cl['fetches'][0]['body'].get('key') == '',
              str(cl['fetches'][0]))
    check('a confirmed removal is reported as a removal from the OFFICE',
          bool(cl['probe']) and cl['probe'].get('ok') is True
          and 'office' in (cl['probe'].get('detail') or ''),
          str(cl['probe']))
    check('and the browser copy is dropped once the office confirms',
          not cl['local'], 'browser still holds %r' % (cl['local'],))
    check('the busy latch is released', cl['busy'] is False)

    rf = out['refused']
    check('an office that refuses the removal is NOT a green tick',
          bool(rf['probe']) and rf['probe'].get('ok') is False,
          str(rf['probe']))
    check('and the line says the office is still running on that key',
          'still' in (rf['probe'] or {}).get('detail', '').lower(),
          str(rf['probe']))
    check('the browser copy survives a refused removal, so it can be re-pushed',
          rf['local'] == 'sk-or-v1-onfile',
          'the only copy that could repair the office was thrown away first')

    off = out['offline']
    check('an unreachable office is not a green tick either',
          bool(off['probe']) and off['probe'].get('ok') is False,
          str(off['probe']))
    check('and the key is still in the browser after an unreachable office',
          off['local'] == 'sk-or-v1-onfile', str(off))

    sv = out['saved']
    check('PIN: saving a real key still pushes it',
          len(sv['fetches']) == 1
          and sv['fetches'][0]['body'].get('key') == 'sk-or-v1-brand-new',
          str(sv['fetches']))
    check('PIN: saving a real key still says the gateway is reloading',
          bool(sv['probe']) and sv['probe'].get('ok') is True
          and 'reloading' in (sv['probe'].get('detail') or ''), str(sv['probe']))
    check('PIN: and the browser copy is written',
          sv['local'] == 'sk-or-v1-brand-new', str(sv))

    lo = out['local']
    check('PIN: a local backend still pushes its URL on an empty key',
          len(lo['fetches']) == 1
          and lo['fetches'][0]['body'].get('base_url') == 'http://localhost:1234/v1',
          str(lo['fetches']))
    check('PIN: and a local backend is never reported as a key removal',
          lo['r'].get('cleared') is not True, str(lo['r']))


def main():
    print('Connections — removing a provider key removes it from the OFFICE')
    print(' live office:')
    live_office()
    print(' the real client + the real saveKey:')
    node_half()
    print()
    print(('FAILED: %s' % FAILS) if FAILS
          else 'key removal: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
