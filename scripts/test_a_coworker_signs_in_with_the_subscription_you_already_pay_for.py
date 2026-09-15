#!/usr/bin/env python3
"""A coworker signs in with the subscription you already pay for (#434).

North Star §3.3 (BYOS) promised "we found your Claude subscription — want
them on the team?" and the front desk did find it — but a Claude or Codex
found WITHOUT a sign-in said "Needs a sign-in before their first task" and
left the boss to open a terminal and run the CLI's login themselves. Now
the card does it: serve.py runs the CLI's OWN sign-in (`claude auth login
--claudeai`, `codex login`) in a pseudo-terminal, reports the link it
printed and any code to paste, hands a pasted code back on stdin, and the
front desk polls until the CLI's credential file appears.

Pinned with fake `claude` and `codex` CLIs on PATH and a scratch HOME (the
real ones would open a real browser):
  * POST /agents/login → 202 running; the link the CLI printed shows up on
    status; a "paste the code" prompt flips needsCode; the pasted code
    reaches the CLI; when it writes its credential the status says
    authenticated and GET /agents agrees; a second POST answers done;
  * an unknown agent is 400, an uninstalled one 404, cancel stops a
    waiting sign-in, logout runs the CLI's sign-out; the routes sit under
    the key-protected /agents prefix; no key material is read by serve.py;
  * the front desk, in a headless browser against that scratch server: the
    FOUND card for Claude shows the one button, worded "subscription";
    clicking it shows the link, then the code field; typing the code ends
    with "Signed in — ready to hire." and the button gone; clicking inside
    the sign-in never fires the card's hire.
  * Settings → Connections → ON THIS MACHINE (#435): the Claude row that
    reads "found · needs a sign-in" carries the SAME control (ui/signin.jsx);
    clicking through link and code ends with the row reading "found ·
    signed in" and the control gone. The front desk and Settings mount one
    component, and a hired desk's status no longer points at a terminal.

Run: python3 scripts/test_a_coworker_signs_in_with_the_subscription_you_already_pay_for.py
"""
import importlib.util
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
_SPEC = importlib.util.spec_from_file_location(
    'office_phone_harness',
    ROOT / 'scripts' / 'test_the_office_ticker_and_the_lobby_door_are_measured_on_a_real_phone.py')
H = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(H)
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + ((' — ' + str(detail)[:400]) if not cond else ''))
    if not cond:
        FAILS.append(name)
    return bool(cond)


FAKE_CLAUDE = r'''#!/usr/bin/env bash
case "$1 $2" in
  "auth login")
    echo "Opening browser to sign in…"
    echo "If your browser did not open, visit: https://claude.ai/oauth/authorize?state=abc"
    echo "Paste the code here if prompted:"
    read -r code
    [ "$code" = "OK-CODE" ] || { echo "That code is not right"; exit 1; }
    # a beat between the code and the credential: a status poll in here caches
    # "not signed in", and the verdict after exit must not be that poll (#434)
    sleep 1
    mkdir -p "$HOME/.claude"; echo '{"claudeAiOauth":{}}' > "$HOME/.claude/.credentials.json"; rm -f "$HOME/.claude/.stale"
    echo "Signed in."; exit 0 ;;
  "auth logout") rm -f "$HOME/.claude/.credentials.json"; echo "Logged out"; exit 0 ;;
  "auth status")
    # the CLI's own verdict: a stale marker means the file is there but the session is gone
    if [ -f "$HOME/.claude/.credentials.json" ] && [ ! -f "$HOME/.claude/.stale" ]; then echo '{"loggedIn": true}'; else echo '{"loggedIn": false}'; fi; exit 0 ;;
esac
echo "1.0.0 (Claude Code)"; exit 0
'''
FAKE_CODEX = r'''#!/usr/bin/env bash
case "$1" in
  login)
    echo "Go to https://auth.openai.com/device and enter the code ABCD-EFGH"
    sleep 1
    mkdir -p "$HOME/.codex"; echo '{"tokens":{}}' > "$HOME/.codex/auth.json"
    echo "Successfully logged in"; exit 0 ;;
  logout) rm -f "$HOME/.codex/auth.json"; exit 0 ;;
esac
if [ "$1 $2" = "login status" ]; then [ -f "$HOME/.codex/auth.json" ] && { echo "Logged in using ChatGPT"; exit 0; } || { echo "Not logged in"; exit 1; }; fi
echo "codex-cli 0.1.0"; exit 0
'''


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def boot(tmp, with_codex=True):
    home = os.path.join(tmp, 'home')
    binp = os.path.join(tmp, 'bin')
    os.makedirs(home, exist_ok=True)
    os.makedirs(binp, exist_ok=True)
    Path(binp, 'claude').write_text(FAKE_CLAUDE)
    os.chmod(Path(binp, 'claude'), 0o755)
    if with_codex:
        Path(binp, 'codex').write_text(FAKE_CODEX)
        os.chmod(Path(binp, 'codex'), 0o755)
    port = free_port()
    # Only the fakes and the system dirs: the real CLIs (a real `claude` on
    # this Mac, a broken Codex shim) must never be what the scratch server finds.
    env = dict(os.environ, PORT=str(port), HOME=home, PATH=binp + ':/usr/bin:/bin',
               CAFRESOHQ_HQ_STATE_DIR=os.path.join(tmp, 'state'), GAP_CRON='0', NEWS_CRON='0', TOPICS_CRON='0')
    for k in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'CAFRESOHQ_API_KEY', 'CLAUDE_CODE_BIN', 'CODEX_BIN'):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    for _ in range(80):
        try:
            with urllib.request.urlopen(base + '/health', timeout=2) as r:
                if r.status == 200:
                    return base, proc, home
        except Exception:      # noqa: BLE001
            pass
        time.sleep(0.25)
    proc.terminate()
    return None, proc, home


def req(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method, headers={'content-type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def wait_status(base, agent, until, seconds=10):
    st = {}
    for _ in range(int(seconds * 4)):
        st = req(base, 'GET', f'/agents/login/status?agent={agent}')[1]
        if until(st):
            return st
        time.sleep(0.25)
    return st


def server_half():
    print('serve.py — the sign-in routes')
    tmp = tempfile.mkdtemp(prefix='hq-signin-')
    base, proc, home = boot(tmp)
    if not check('serve.py boots with the fake CLIs on PATH and a scratch HOME', base is not None):
        return
    try:
        check('an unknown agent is refused', req(base, 'POST', '/agents/login', {'agent': 'gemini'})[0] == 400)
        code, r = req(base, 'POST', '/agents/login', {'agent': 'claude-code'})
        check("POST /agents/login starts the CLI's own sign-in (202 running)", code == 202 and r.get('status') == 'running', (code, r))
        st = wait_status(base, 'claude-code', lambda s: bool(s.get('url')))
        check('the link the CLI printed is on the status', st.get('url') == 'https://claude.ai/oauth/authorize?state=abc', st)
        st = wait_status(base, 'claude-code', lambda s: s.get('needsCode'))
        check('a "paste the code" prompt flips needsCode', st.get('needsCode') is True and not st.get('authenticated'), st)
        code, r = req(base, 'POST', '/agents/login/input', {'agent': 'claude-code', 'text': 'OK-CODE'})
        check('a pasted code is handed to the CLI', code == 200 and r.get('ok'))
        st = wait_status(base, 'claude-code', lambda s: s.get('status') != 'running')
        check('the CLI wrote its credential and the status says signed in', st.get('status') == 'done' and st.get('authenticated') is True and st.get('auth') == 'oauth', st)
        check('the credential is the CLI\'s own file, in the scratch HOME', Path(home, '.claude', '.credentials.json').is_file())
        code, r = req(base, 'POST', '/agents/login', {'agent': 'claude-code'})
        check('a second sign-in answers done without running anything', code == 200 and r.get('status') == 'done' and r.get('authenticated'))
        agents = req(base, 'GET', '/agents')[1].get('agents', [])
        cc = next((a for a in agents if a['id'] == 'claude-code'), {})
        check('GET /agents now reports Claude as signed in', cc.get('authenticated') is True and cc.get('auth') == 'oauth', cc)

        code, r = req(base, 'POST', '/agents/login', {'agent': 'codex'})
        check('a ChatGPT (Codex) sign-in starts the same way', code == 202)
        st = wait_status(base, 'codex', lambda s: s.get('status') != 'running')
        check('the device link and the code the CLI printed are both on the status',
              st.get('url') == 'https://auth.openai.com/device' and st.get('code') == 'ABCD-EFGH' and st.get('authenticated') is True, st)
        code, r = req(base, 'POST', '/agents/logout', {'agent': 'codex'})
        check("logout runs the CLI's own sign-out and reports the credential gone", code == 200 and r.get('ok') and r.get('authenticated') is False, r)

        # cancel: sign out claude, start again (it waits for a code), cancel it
        req(base, 'POST', '/agents/logout', {'agent': 'claude-code'})
        code, r = req(base, 'POST', '/agents/login', {'agent': 'claude-code'})
        wait_status(base, 'claude-code', lambda s: s.get('needsCode'))
        code, r = req(base, 'POST', '/agents/login/cancel', {'agent': 'claude-code'})
        st = wait_status(base, 'claude-code', lambda s: s.get('status') != 'running')
        check('cancel stops a sign-in that is waiting for a code', code == 200 and st.get('status') == 'error' and st.get('error') == 'cancelled', st)
        check('input with nothing waiting is 404', req(base, 'POST', '/agents/login/input', {'agent': 'claude-code', 'text': 'x'})[0] == 404)

        # ── an expired session: the file is there, the CLI says no (#434) ──
        Path(home, '.claude').mkdir(exist_ok=True)
        Path(home, '.claude', '.credentials.json').write_text('{"claudeAiOauth":{}}')
        Path(home, '.claude', '.stale').write_text('1')
        agents = req(base, 'GET', '/agents')[1].get('agents', [])
        cc = next((a for a in agents if a['id'] == 'claude-code'), {})
        check("a credential file the CLI no longer honours reads 'expired', not signed in",
              cc.get('authenticated') is False and cc.get('auth') == 'expired', cc)
        code, r = req(base, 'POST', '/agents/login', {'agent': 'claude-code'})
        check('a sign-in starts for an expired session instead of answering done', code == 202 and r.get('status') == 'running', (code, r))
        wait_status(base, 'claude-code', lambda st: st.get('needsCode'))
        req(base, 'POST', '/agents/login/input', {'agent': 'claude-code', 'text': 'OK-CODE'})
        st = wait_status(base, 'claude-code', lambda st: st.get('status') != 'running')
        check('…and the fresh sign-in is honoured the moment the CLI says so', st.get('authenticated') is True and st.get('auth') == 'oauth', st)
    finally:
        proc.terminate()
    tmp2 = tempfile.mkdtemp(prefix='hq-signin2-')
    base2, proc2, _ = boot(tmp2, with_codex=False)
    try:
        if base2:
            code, r = req(base2, 'POST', '/agents/login', {'agent': 'codex'})
            check('a CLI that is not on this machine is 404, in words', code == 404 and 'not installed' in r.get('error', ''), r)
    finally:
        proc2.terminate()

    src = (ROOT / 'serve.py').read_text(encoding='utf-8')
    check("the routes sit under the key-protected '/agents' prefix", "'/agents'," in src[src.index('_KEY_PROTECTED_PREFIXES = ('):src.index('_KEY_PROTECTED_PREFIXES = (') + 400])
    login = src[src.index('def _agents_login(self):'):src.index('def _agents_install(self):')]
    check('the sign-in commands are a fixed allowlist, nothing from the request reaches them',
          "'claude-code': (['auth', 'login', '--claudeai']" in src and "'codex':       (['login']" in src and 'body.get' not in login.split('def _agents_login_input')[0].replace("body.get('agent'", ''))
    check('serve.py never reads the credential files, only notices them', '.credentials.json' not in login and 'auth.json' not in login)
    hire = (ROOT / 'modals' / 'hire.jsx').read_text(encoding='utf-8')
    signin_ui = (ROOT / 'ui' / 'signin.jsx').read_text(encoding='utf-8')
    check("the card says an expired sign-in has expired and offers 'Sign in again'",
          "expired: det.auth === 'expired'" in hire and 'has expired — sign in again' in hire
          and "replace('Sign in', 'Sign in again')" in signin_ui and 'expired={c.expired}' in hire)
    drv = (ROOT / 'drivers' / 'claude_code.py').read_text(encoding='utf-8')
    check("the driver asks the CLI's own `auth status --json` and returns 'expired' when it says no",
          "'auth', 'status', '--json'" in drv and "return False, 'expired'" in drv)


def open_office(base):
    """A headless browser on the office at `base`, boot splash and coach
    cleared. Returns (chrome process, ws) — ws is None when the browser
    never announced itself (the caller has already logged a FAIL)."""
    chrome = H.find_chrome()
    profile = tempfile.mkdtemp(prefix='cafresohq-cdp-signin-')
    proc = subprocess.Popen(
        [str(chrome), '--headless=new', '--remote-debugging-port=0', f'--user-data-dir={profile}', '--no-sandbox',
         '--disable-gpu', '--hide-scrollbars', '--mute-audio', '--no-first-run', '--no-default-browser-check',
         '--disable-extensions', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', 'about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    endpoint = None
    deadline = time.time() + 30
    while time.time() < deadline:
        line = proc.stderr.readline().decode('utf-8', 'replace')
        if not line:
            break
        hit = re.search(r'ws://\S+', line)
        if hit:
            endpoint = hit.group(0)
            break
    if not check('the browser announced a DevTools endpoint', bool(endpoint)):
        return proc, None
    host = re.match(r'ws://([^/]+)/', endpoint).group(1)
    with urllib.request.urlopen(f'http://{host}/json/list', timeout=15) as fh:
        targets = json.load(fh)
    page = next(t for t in targets if t['type'] == 'page')
    ws = H.WS(page['webSocketDebuggerUrl'])
    ws.call('Page.enable')
    ws.call('Runtime.enable')
    ws.call('Emulation.setDeviceMetricsOverride', {'width': 1280, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
    ws.call('Page.navigate', {'url': base + '/hq.html'})
    H.wait_for(ws, "!!document.querySelector('button[title^=\"Office\"]')", 45, 'the rail')
    H.wait_for(ws, "!document.getElementById('cafreso-boot')", 20, 'the boot splash to clear')
    for _ in range(8):
        if not H.evaluate(ws, "document.querySelectorAll('.backdrop').length"):
            break
        H.press_escape(ws)
        time.sleep(0.4)
    H.evaluate(ws, "(() => { const x = document.querySelector('.gs-coach button.gs-dismiss'); if (x) x.click(); return !!x; })()")
    return proc, ws


def type_code(ws, sel, code):
    """Set the code field's value the way React sees it, then press Enter."""
    H.evaluate(ws, """(() => { const i = document.querySelector('%s input');
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(i, '%s');
      i.dispatchEvent(new Event('input', { bubbles: true }));
      i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); return 1; })()""" % (sel, code))


def browser_half():
    print('the front desk — in a real browser against the scratch server')
    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        check('the HQ UI is built', False, 'run `npm run build`')
        return
    chrome = H.find_chrome()
    if chrome is None:
        print('  SKIPPED — no headless browser on this machine.')
        return
    tmp = tempfile.mkdtemp(prefix='hq-signin-ui-')
    base, server, home = boot(tmp)
    if not check('serve.py boots for the browser half', base is not None):
        return
    proc, ws = open_office(base)
    try:
        if ws is None:
            return
        H.evaluate(ws, "(() => { const b = document.querySelector('button[title^=\"Office\"]'); b && b.click(); return 1; })()")
        H.wait_for(ws, "!!document.querySelector('.px-room.vacant')", 20, 'a vacant unit on the floor')
        H.evaluate(ws, "(() => { document.querySelector('.px-room.vacant').click(); return 1; })()")
        ok = H.wait_for(ws, "!!document.querySelector('.frontdesk-signin[data-signin=\"claude-code\"] button')", 30, "the front desk's Claude card with its sign-in button")
        check('the FOUND card for Claude shows one sign-in button', ok)
        label = H.evaluate(ws, "(() => { const b = document.querySelector('.frontdesk-signin[data-signin=\"claude-code\"] button'); return b ? b.textContent.trim() : ''; })()")
        check('it is worded as the subscription you pay for', label == 'Sign in with your Claude subscription', label)
        note = H.evaluate(ws, "(() => { const c = document.querySelector('.frontdesk-signin[data-signin=\"claude-code\"]').closest('.frontdesk-card'); return c.querySelector('.frontdesk-note').textContent; })()")
        check('the note still says a sign-in is needed', 'Needs a sign-in' in note, note)
        hires_before = H.evaluate(ws, "document.querySelectorAll('.px-room:not(.vacant):not(.filler)').length")
        H.evaluate(ws, "(() => { document.querySelector('.frontdesk-signin[data-signin=\"claude-code\"] button').click(); return 1; })()")
        ok = H.wait_for(ws, "!!document.querySelector('.frontdesk-signin[data-signin=\"claude-code\"] .frontdesk-signin-link')", 15, 'the link the CLI printed')
        href = H.evaluate(ws, "(() => { const a = document.querySelector('.frontdesk-signin[data-signin=\"claude-code\"] .frontdesk-signin-link'); return a ? a.href : ''; })()")
        check('clicking it shows the link the CLI printed, opening in a new tab', ok and href == 'https://claude.ai/oauth/authorize?state=abc', href)
        ok = H.wait_for(ws, "!!document.querySelector('.frontdesk-signin[data-signin=\"claude-code\"] input')", 15, 'the code field')
        check('when the CLI asks for a code, a field appears', ok)
        type_code(ws, '.frontdesk-signin[data-signin="claude-code"]', 'OK-CODE')
        ok = H.wait_for(ws, "(() => { const c = [...document.querySelectorAll('.frontdesk-card')].find(x => /Claude/.test(x.textContent)); return !!c && /Signed in — ready to hire/.test(c.querySelector('.frontdesk-note').textContent); })()", 20, 'the card to read signed in')
        check('typing the code ends with "Signed in — ready to hire."', ok)
        gone = H.evaluate(ws, "!document.querySelector('.frontdesk-signin[data-signin=\"claude-code\"]')")
        check('the sign-in control is gone once signed in', gone)
        hires_after = H.evaluate(ws, "document.querySelectorAll('.px-room:not(.vacant):not(.filler)').length")
        check("clicking inside the sign-in never fired the card's hire", hires_after == hires_before, (hires_before, hires_after))
        check("the CLI's credential landed in the scratch HOME, written by the CLI", Path(home, '.claude', '.credentials.json').is_file())
    finally:
        try:
            if ws:
                ws.close()
        except Exception:      # noqa: BLE001
            pass
        proc.kill()
        server.terminate()



def settings_half():
    print('Settings → Connections — the same control, in a real browser')
    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        return
    if H.find_chrome() is None:
        print('  SKIPPED — no headless browser on this machine.')
        return
    tmp = tempfile.mkdtemp(prefix='hq-signin-settings-')
    base, server, home = boot(tmp)
    if not check('serve.py boots for the Settings half', base is not None):
        return
    proc, ws = open_office(base)
    try:
        if ws is None:
            return
        H.evaluate(ws, "(() => { window.dispatchEvent(new CustomEvent('cafresohq:openSettings', { detail: { tab: 'connections' } })); return 1; })()")
        row_sel = '.cb-panel .frontdesk-signin[data-signin="claude-code"][data-where="settings"]'
        ok = H.wait_for(ws, f"!!document.querySelector('{row_sel} button')", 30, "the Claude row's sign-in button under Settings → Connections")
        check('the Claude row under ON THIS MACHINE carries the sign-in button', ok)
        sub = H.evaluate(ws, f"(() => {{ const c = document.querySelector('{row_sel}'); return c ? c.closest('.row-knob').querySelector('.sub').textContent : ''; }})()")
        check('its sentence still says a sign-in is needed', 'needs a sign-in' in sub, sub)
        label = H.evaluate(ws, f"(() => {{ const b = document.querySelector('{row_sel} button'); return b ? b.textContent.trim() : ''; }})()")
        check('worded as the subscription you pay for, same as the front desk', label == 'Sign in with your Claude subscription', label)
        H.evaluate(ws, f"(() => {{ document.querySelector('{row_sel} button').click(); return 1; }})()")
        ok = H.wait_for(ws, f"!!document.querySelector('{row_sel} .frontdesk-signin-link')", 15, 'the link the CLI printed')
        check('clicking it shows the link the CLI printed', ok)
        ok = H.wait_for(ws, f"!!document.querySelector('{row_sel} input')", 15, 'the code field')
        check('when the CLI asks for a code, a field appears', ok)
        type_code(ws, row_sel, 'OK-CODE')
        ok = H.wait_for(ws, "(() => { const r = [...document.querySelectorAll('.cb-panel .row-knob')].find(x => /Claude Code/.test(x.textContent)); return !!r && /found · signed in/.test(r.querySelector('.sub').textContent); })()", 25, 'the row to read signed in')
        check('typing the code ends with the row reading "found · signed in"', ok)
        gone = H.evaluate(ws, f"!document.querySelector('{row_sel}')")
        check('the control is gone once signed in', gone)
        chip = H.evaluate(ws, "(() => { const r = [...document.querySelectorAll('.cb-panel .row-knob')].find(x => /Claude Code/.test(x.textContent)); return r ? r.querySelector('.tiny').textContent.trim() : ''; })()")
        check('and the dot says ready', chip == '● ready', chip)
        check("the CLI's credential landed in the scratch HOME, written by the CLI", Path(home, '.claude', '.credentials.json').is_file())
    finally:
        try:
            if ws:
                ws.close()
        except Exception:      # noqa: BLE001
            pass
        proc.kill()
        server.terminate()


def one_control_everywhere():
    """Structural: the two surfaces mount ONE component, and the desk status
    line no longer sends anyone to a terminal for a sign-in the office does."""
    print('one control, wherever the office says a sign-in is needed')
    hire = (ROOT / 'modals' / 'hire.jsx').read_text(encoding='utf-8')
    settings = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    ui = (ROOT / 'ui' / 'signin.jsx').read_text(encoding='utf-8')
    check('ui/signin.jsx exports the hook and the control', 'export function useAgentSignin' in ui and 'export function AgentSignin' in ui)
    check('the front desk mounts it', "from '../ui/signin.jsx'" in hire and '<AgentSignin' in hire and 'where="frontdesk"' in hire)
    check('...and no longer carries its own copy', 'setInterval' not in hire.split('useAgentSignin')[0] and 'startSignin' not in hire)
    check('Settings → Connections mounts it', "from '../ui/signin.jsx'" in settings and '<AgentSignin' in settings and 'where="settings"' in settings)
    rows_i = settings.find("['claude-code'")
    rows = settings[rows_i:settings.find('cb-panel', rows_i)] if rows_i >= 0 else ''
    check('...inside the ON THIS MACHINE rows, only for a live CLI that is not signed in',
          '<AgentSignin' in rows and 'live && !isDaemon && !det.authenticated' in rows)
    check('...and its sentence has the expired case, worded sign in again',
          "det.auth === 'expired' ? 'found · its sign-in here has expired — sign in again'" in rows)
    check('a hired desk no longer sends the boss to a terminal for a sign-in',
          'open a Terminal tab' not in app and 'Settings → Connections' in app)
    check('the labels are the subscription, never the protocol',
          "'Sign in with your Claude subscription'" in ui and "'Sign in with your ChatGPT subscription'" in ui and 'OAuth' not in ui)


def main():
    print('a coworker signs in with the subscription you already pay for')
    one_control_everywhere()
    server_half()
    browser_half()
    settings_half()
    print()
    if FAILS:
        print(f'sign in: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('sign in: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
