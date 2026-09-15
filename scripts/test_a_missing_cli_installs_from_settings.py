#!/usr/bin/env python3
"""A missing CLI installs from where the office says it is missing (#436).

Settings → Connections → ON THIS MACHINE read "not found on this machine"
(Gemini) or "installed, but it will not start" (a Codex whose shim lost its
binary) and offered nothing — while serve.py has had an allow-listed
installer (`POST /agents/install`, npm for the three Node CLIs) reachable
from no button at all. Now the row carries one: Install / Reinstall, the
exact command the office will run said out loud, and Copy command for a
terminal of your own. When the install lands the panel re-probes and the
row's own sentence flips.

Pinned with a fake `npm` on PATH (it "installs" by writing a fake CLI into
the scratch bin) and a scratch HOME:
  * the routes: not found → 202 → the job settles done with installed:true
    → the probe finds it; a broken Codex reinstalls to a working one; the
    fake npm was asked for exactly the packages the row names;
  * the two command tables — ui/install.jsx (display) and serve.py's
    AGENT_NPM (what runs) — name the same packages;
  * Settings, in a headless browser: the Gemini row shows "Install Gemini
    CLI", the Codex row "Reinstall Codex"; clicking Install ends with the
    row reading found; the row says which command it runs.

Run: python3 scripts/test_a_missing_cli_installs_from_settings.py
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    'signin_suite', ROOT / 'scripts' / 'test_a_coworker_signs_in_with_the_subscription_you_already_pay_for.py')
S = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(S)
H = S.H
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + ((' — ' + str(detail)[:400]) if not cond else ''))
    if not cond:
        FAILS.append(name)
    return bool(cond)


# "Installs" by writing a runnable fake CLI into the scratch bin, which is
# first on the scratch server's PATH — the same place a real global install
# would have to land for the driver's shutil.which to find it.
FAKE_NPM = r'''#!/usr/bin/env bash
echo "$@" >> "$FAKE_NPM_LOG"
if [ "$1 $2" = "install -g" ]; then
  case "$3" in
    @google/gemini-cli@*)
      printf '#!/usr/bin/env bash\necho "0.9.0"; exit 0\n' > "$FAKE_BIN/gemini"; chmod +x "$FAKE_BIN/gemini" ;;
    @openai/codex@*)
      printf '#!/usr/bin/env bash\nif [ "$1 $2" = "login status" ]; then echo "Not logged in"; exit 1; fi\necho "codex-cli 0.1.0"; exit 0\n' > "$FAKE_BIN/codex"; chmod +x "$FAKE_BIN/codex" ;;
    @anthropic-ai/claude-code@*)
      printf '#!/usr/bin/env bash\nif [ "$1 $2" = "auth status" ]; then echo "{\"loggedIn\": false}"; exit 0; fi\necho "1.0.0 (Claude Code)"; exit 0\n' > "$FAKE_BIN/claude"; chmod +x "$FAKE_BIN/claude" ;;
  esac
  echo "added 1 package"; exit 0
fi
exit 0
'''
# A Codex whose vendored binary is gone: present on PATH, crashes on --version.
BROKEN_CODEX = '#!/usr/bin/env bash\necho "Error: spawn ENOENT" >&2; exit 1\n'


def boot(tmp):
    home = os.path.join(tmp, 'home')
    binp = os.path.join(tmp, 'bin')
    os.makedirs(home, exist_ok=True)
    os.makedirs(binp, exist_ok=True)
    Path(binp, 'npm').write_text(FAKE_NPM)
    os.chmod(Path(binp, 'npm'), 0o755)
    Path(binp, 'codex').write_text(BROKEN_CODEX)
    os.chmod(Path(binp, 'codex'), 0o755)
    port = S.free_port()
    env = dict(os.environ, PORT=str(port), HOME=home, PATH=binp + ':/usr/bin:/bin',
               FAKE_BIN=binp, FAKE_NPM_LOG=os.path.join(tmp, 'npm.log'),
               CAFRESOHQ_HQ_STATE_DIR=os.path.join(tmp, 'state'), GAP_CRON='0', NEWS_CRON='0', TOPICS_CRON='0')
    for k in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'CAFRESOHQ_API_KEY',
              'CLAUDE_CODE_BIN', 'CODEX_BIN', 'GEMINI_BIN'):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    for _ in range(80):
        try:
            with urllib.request.urlopen(base + '/health', timeout=2) as r:
                if r.status == 200:
                    return base, proc, home, binp, env['FAKE_NPM_LOG']
        except Exception:      # noqa: BLE001
            pass
        time.sleep(0.25)
    proc.terminate()
    return None, proc, home, binp, env['FAKE_NPM_LOG']


def drivers(base):
    r = S.req(base, 'GET', '/agent/drivers?probe=1')[1]
    return {d['id']: d.get('detect') or {} for d in r.get('drivers', [])}


def wait_job(base, agent, seconds=30):
    st = {}
    for _ in range(int(seconds * 4)):
        st = S.req(base, 'GET', f'/agents/install/status?agent={agent}')[1]
        if st.get('status') in ('done', 'error'):
            return st
        time.sleep(0.25)
    return st


def tables_agree():
    print('the command the row names is the command the office runs')
    ui = (ROOT / 'ui' / 'install.jsx').read_text(encoding='utf-8')
    srv = (ROOT / 'serve.py').read_text(encoding='utf-8')
    shown = dict(re.findall(r"'([a-z-]+)':\s*'npm install -g (\S+)'", ui))
    block = srv[srv.index('AGENT_NPM = {'):srv.index('AGENT_PIP = {')]
    runs = dict(re.findall(r"'([a-z-]+)':\s*'(\S+)'", block))
    check('ui/install.jsx names a command for each Node CLI', set(shown) == {'claude-code', 'codex', 'gemini'}, shown)
    check("...and each is the package serve.py's allowlist installs", all(runs.get(k) == v for k, v in shown.items()), (shown, runs))
    settings = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
    i = settings.find("['claude-code'")
    rows = settings[i:settings.find('cb-panel', i)] if i >= 0 else ''
    check('Settings mounts the install control on a row that is not live and not a daemon',
          '<AgentInstall' in rows and '!live && !isDaemon' in rows and 'broken={broken}' in rows)
    check('a broken CLI is offered a reinstall, an absent one an install',
          "const verb = broken ? 'Reinstall' : 'Install'" in ui)
    check('the row says out loud which command runs on this machine',
          'Runs <code>{INSTALL_CMD[id]}</code> on this machine' in ui)
    check('a copy is offered for a terminal of your own', 'navigator.clipboard.writeText(INSTALL_CMD[id])' in ui)


def server_half():
    print('serve.py — install from not found, reinstall from broken')
    tmp = tempfile.mkdtemp(prefix='hq-install-')
    base, proc, home, binp, log = boot(tmp)
    if not check('serve.py boots with a fake npm on PATH and a scratch HOME', base is not None):
        return
    try:
        d = drivers(base)
        check('before: Gemini is not found, Codex is present but will not start',
              not d.get('gemini', {}).get('installed') and d.get('codex', {}).get('installed') and bool(d.get('codex', {}).get('probeError')), d.get('codex'))
        code, r = S.req(base, 'POST', '/agents/install', {'agent': 'gemini'})
        check('POST /agents/install starts the install in the background (202)', code == 202 and r.get('ok'), (code, r))
        st = wait_job(base, 'gemini')
        check('the job settles done, with the thing it wrote found and runnable',
              st.get('status') == 'done' and st.get('installed') is True and not st.get('probeError') and st.get('version'), st)
        d = drivers(base)
        check('after: the probe finds Gemini on this machine', d.get('gemini', {}).get('installed') is True and not d['gemini'].get('probeError'), d.get('gemini'))
        code, r = S.req(base, 'POST', '/agents/install', {'agent': 'codex'})
        st = wait_job(base, 'codex')
        d = drivers(base)
        check('a reinstall repairs the Codex that would not start',
              code == 202 and st.get('status') == 'done' and d.get('codex', {}).get('installed') and not d['codex'].get('probeError'), (st, d.get('codex')))
        asked = Path(log).read_text() if Path(log).exists() else ''
        check('the fake npm was asked for exactly the packages the rows name',
              'install -g @google/gemini-cli@latest' in asked and 'install -g @openai/codex@latest' in asked, asked)
        check('an agent off the allowlist is refused', S.req(base, 'POST', '/agents/install', {'agent': 'ollama'})[0] == 400)
    finally:
        proc.terminate()


def browser_half():
    print('Settings → Connections — the install button, in a real browser')
    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        check('the HQ UI is built', False, 'run `npm run build`')
        return
    if H.find_chrome() is None:
        print('  SKIPPED — no headless browser on this machine.')
        return
    tmp = tempfile.mkdtemp(prefix='hq-install-ui-')
    base, server, home, binp, log = boot(tmp)
    if not check('serve.py boots for the browser half', base is not None):
        return
    proc, ws = S.open_office(base)
    try:
        if ws is None:
            return
        H.evaluate(ws, "(() => { window.dispatchEvent(new CustomEvent('cafresohq:openSettings', { detail: { tab: 'connections' } })); return 1; })()")
        gem = '.cb-panel .agent-install[data-install="gemini"][data-where="settings"]'
        cdx = '.cb-panel .agent-install[data-install="codex"][data-where="settings"]'
        ok = H.wait_for(ws, f"!!document.querySelector('{gem} button')", 30, "the Gemini row's install button")
        check('the Gemini row under ON THIS MACHINE carries an install button', ok)
        sub = H.evaluate(ws, f"(() => {{ const c = document.querySelector('{gem}'); return c ? c.closest('.row-knob').querySelector('.sub').textContent : ''; }})()")
        check('its sentence still says not found', 'not found on this machine' in sub, sub)
        label = H.evaluate(ws, f"(() => {{ const b = document.querySelector('{gem} button'); return b ? b.textContent.trim() : ''; }})()")
        check('worded Install Gemini CLI', label == 'Install Gemini CLI', label)
        line = H.evaluate(ws, f"(() => {{ const c = document.querySelector('{gem}'); return c ? c.textContent : ''; }})()")
        check('it says which command runs on this machine', 'npm install -g @google/gemini-cli@latest' in line and 'Copy command' in line, line)
        clabel = H.evaluate(ws, f"(() => {{ const b = document.querySelector('{cdx} button'); return b ? b.textContent.trim() : ''; }})()")
        check('the broken Codex row offers a reinstall', clabel == 'Reinstall Codex', clabel)
        H.evaluate(ws, f"(() => {{ document.querySelector('{gem} button').click(); return 1; }})()")
        ok = H.wait_for(ws, f"/Installing Gemini CLI/.test((document.querySelector('{gem}') || {{}}).textContent || '')", 10, 'the installing line')
        check('clicking it says installing', ok)
        ok = H.wait_for(ws, "(() => { const r = [...document.querySelectorAll('.cb-panel .row-knob')].find(x => /Gemini CLI/.test(x.textContent)); return !!r && /found · /.test(r.querySelector('.sub').textContent); })()", 40, 'the row to read found')
        check('the install ends with the row reading found', ok)
        gone = H.evaluate(ws, f"!document.querySelector('{gem}')")
        check('the install control is gone once the CLI is found', gone)
        check('the fake CLI landed where the office looks', Path(binp, 'gemini').is_file())
    finally:
        try:
            if ws:
                ws.close()
        except Exception:      # noqa: BLE001
            pass
        proc.kill()
        server.terminate()


def main():
    print('a missing CLI installs from where the office says it is missing')
    tables_agree()
    server_half()
    browser_half()
    FAILS.extend(S.FAILS)
    print()
    if FAILS:
        print(f'install: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('install: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
