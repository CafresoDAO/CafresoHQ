"""Signing a coworker into the subscription you already pay for, from the coworker itself.

2026-11-21: Anthony signed his hosted office's Claude into his Claude subscription by approving
on claude.ai and pasting one code back, and asked for exactly that flow for everyone with a
subscription. Two things stood in the way:

1. The only places the sign-in lived were the hire shelf (which hides a coworker once hired)
   and Settings -> Connections (hidden in managed offices). Hire Claude before finishing the
   sign-in and there was nowhere left to paste the code. The sign-in now sits on the coworker's
   own config, under its Brain picker: install it, sign in, or "signed in".
2. The CLI and its sign-in lived in the container layer (npm into /usr, creds in /root), so a
   fleet rebuild wiped them. The image now keeps both on the /data volume, and the office's
   sign-in detection looks where the CLI writes.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
failures = 0


def check(label, ok, why=''):
    global failures
    print(('  ok    ' if ok else '  FAIL  ') + label + ('' if ok else f'  ({why})'))
    if not ok:
        failures += 1


# ── 1. detection follows the CLI's own config dirs ───────────────────────────
print('sign-in detection')
from drivers.claude_code import ClaudeCodeDriver  # noqa: E402
from drivers import codex as codex_mod  # noqa: E402

with tempfile.TemporaryDirectory() as t:
    home, cfg = pathlib.Path(t, 'home'), pathlib.Path(t, 'data', 'claude')
    home.mkdir(); cfg.mkdir(parents=True)
    old = dict(os.environ)
    try:
        os.environ['HOME'] = str(home)
        os.environ.pop('ANTHROPIC_API_KEY', None)
        os.environ['CLAUDE_CONFIG_DIR'] = str(cfg)
        check('no credential anywhere -> not signed in', ClaudeCodeDriver.detect_auth()[0] is False)
        (cfg / '.credentials.json').write_text('{}')
        check('a credential in CLAUDE_CONFIG_DIR counts', ClaudeCodeDriver.detect_auth() == (True, 'oauth'))
        (cfg / '.credentials.json').unlink()
        (cfg / '.claude.json').write_text('{"oauthAccount": {}}')
        check('...and so does its .claude.json there', ClaudeCodeDriver.detect_auth()[0] is True)
        (cfg / '.claude.json').unlink()
        (home / '.claude.json').write_text('{"oauthAccount": {}}')
        check("with CLAUDE_CONFIG_DIR set, a stray ~/.claude.json doesn't count", ClaudeCodeDriver.detect_auth()[0] is False)
        os.environ.pop('CLAUDE_CONFIG_DIR')
        check('without it, ~/.claude.json still counts as before', ClaudeCodeDriver.detect_auth()[0] is True)
    finally:
        os.environ.clear(); os.environ.update(old)

codex_src = (ROOT / 'drivers' / 'codex.py').read_text(encoding='utf-8')
check('codex detection honours CODEX_HOME', "os.environ.get('CODEX_HOME'" in codex_src)

# ── 2. the image keeps sign-ins and installs on the /data volume ─────────────
print('entrypoint')
ep = (ROOT / 'docker' / 'entrypoint.sh').read_text(encoding='utf-8')
m = re.search(r'AGENT_HOME=/data/hq-state/agent-home\n.*?\nfi\n', ep, re.S)
check('the persistence block exists', m is not None)
if m:
    with tempfile.TemporaryDirectory() as t:
        block = m.group(0).replace('/data', f'{t}/data').replace('/root', f'{t}/root')
        os.makedirs(f'{t}/data/hq-state'); os.makedirs(f'{t}/root/.claude')
        pathlib.Path(t, 'root/.claude/.credentials.json').write_text('{"signed":"in"}')
        pathlib.Path(t, 'root/.claude.json').write_text('{"oauthAccount":{}}')
        out = subprocess.run(['bash', '-c', 'set -e\nunset CLAUDE_CONFIG_DIR CODEX_HOME npm_config_prefix\n' + block +
                              'echo "$CLAUDE_CONFIG_DIR|$CODEX_HOME|$npm_config_prefix|$PATH"'],
                             capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
        cfgd, codexd, prefix, path = out.split('|')
        ah = f'{t}/data/hq-state/agent-home'
        check('CLAUDE_CONFIG_DIR is on the volume', cfgd == f'{ah}/claude', cfgd)
        check('CODEX_HOME is on the volume', codexd == f'{ah}/codex', codexd)
        check('npm installs go to the volume and are on PATH', prefix == f'{ah}/npm-global' and path.startswith(f'{ah}/npm-global/bin:'), prefix)
        check('an existing sign-in is moved onto the volume',
              pathlib.Path(ah, 'claude/.credentials.json').read_text() == '{"signed":"in"}'
              and pathlib.Path(ah, 'claude/.claude.json').is_file())
check('it only runs when /data/hq-state is writable', '[ -d /data/hq-state ] && [ -w /data/hq-state ]' in ep)
check('it comes before the npm defaults, so they keep the volume prefix',
      ep.index('AGENT_HOME=/data/hq-state/agent-home') < ep.index('export npm_config_prefix="${npm_config_prefix:-/usr/local}"'))

# ── 3. the sign-in sits on the coworker, under its Brain ─────────────────────
print('coworker settings')
st = (ROOT / 'modals' / 'settings.jsx').read_text(encoding='utf-8')
fn = re.search(r'const SUBSCRIPTION_DRIVER = .*?\n.*?export function subscriptionDriverFor\(model\) \{.*?\n\}', st, re.S)
check('subscriptionDriverFor exists', fn is not None)
if fn:
    js = 'const CafresoHQClient = { parseModelId: (id) => { const m = /^([a-z-]+):(.*)$/.exec(id || ""); return m ? { provider: m[1], model: m[2] } : { provider: null, model: id }; } };\n' + \
         fn.group(0).replace('export function', 'function') + \
         '\nconsole.log(JSON.stringify(["claudecode:opus","cafresohq:sonnet","codex:gpt-4.1","anthropic:claude-opus-5-5","hermes:hermes-agent",""].map(subscriptionDriverFor)));'
    got = json.loads(subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True).stdout)
    check('Claude Code brains -> the claude-code sign-in', got[:2] == ['claude-code', 'claude-code'], got)
    check('Codex -> the codex sign-in', got[2] == 'codex', got)
    check('API-key and shared brains need no sign-in here', got[3:] == [None, None, None], got)
picker = st.index('<ModelPicker value={sel.model} onChange={v=>update({model:v})}/>')
check('it renders right under the coworker\'s Brain picker',
      0 < st.index('<CoworkerBrainAccess model={sel.model} />', picker) - picker < 120)
body = st[st.index('function CoworkerBrainAccess'):st.index('function ConnectionsPanel')]
check('not installed -> the install control', '!det.installed && (\n        <AgentInstall' in body)
check('installed, not signed in -> the sign-in control (with the paste box)', 'det.installed && !det.authenticated && (\n        <AgentSignin' in body)
check('signed in -> says so', 'signed in with ${SUBSCRIPTION_NAME[id]}' in body)
check('it is not gated on managed === false like Connections', 'managed' not in body)

print('\nall checks passed' if not failures else f'\n{failures} check(s) failed')
sys.exit(1 if failures else 0)
