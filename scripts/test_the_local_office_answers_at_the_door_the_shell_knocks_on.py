#!/usr/bin/env python3
"""The local office answers at the door the shell knocks on (docs/LOCAL_HQ.md).

scripts/local_hq.sh keeps a founder's own office up on their machine as a
per-user LaunchAgent, so the shell at ai.cafreso.com finds it on localhost.
Pinned here, with a fake launchctl/lsof on PATH so nothing on the real
machine is touched:
  * `plist` prints a LaunchAgent that runs serve.py from THIS repo as the
    working directory, on the requested port, at login, kept alive, logging
    to a file — the shape launchd needs and the shape `uninstall` removes;
  * `install` refuses a port another program already holds (Docker's
    forward, on the machine this was written on) and names the way round;
  * the health probe asks 127.0.0.1, never `localhost` (which resolves to
    ::1 first, where a Docker forward answers nothing), and only accepts
    serve.py's own body;
  * `status` on a dead port says "down" and exits 1; `uninstall` removes the
    plist and says the state is untouched; an unknown command is a usage
    error; the script parses and its header is the help text;
  * serve.py's default port is the shell's first probe port and its CORS
    allowlist names the shell's origin.

Run: python3 scripts/test_the_local_office_answers_at_the_door_the_shell_knocks_on.py
"""
import os
import plistlib
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'local_hq.sh'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + ((' — ' + str(detail)[:300]) if not cond else ''))
    if not cond:
        FAILS.append(name)


FAKE_LAUNCHCTL = '#!/usr/bin/env bash\necho "$@" >> "$FAKE_LOG"\nexit 0\n'
FAKE_LSOF_BUSY = '#!/usr/bin/env bash\necho "COMMAND PID USER"\necho "com.docke 1 u 1u IPv6 0x0 0t0 TCP *:8787 (LISTEN)"\n'
FAKE_LSOF_FREE = '#!/usr/bin/env bash\nexit 0\n'


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def run(args, env_extra=None, lsof=FAKE_LSOF_FREE):
    with tempfile.TemporaryDirectory() as d:
        binp = Path(d) / 'bin'
        binp.mkdir()
        (binp / 'launchctl').write_text(FAKE_LAUNCHCTL)
        (binp / 'lsof').write_text(lsof)
        for f in ('launchctl', 'lsof'):
            (binp / f).chmod(0o755)
        log = Path(d) / 'calls.log'
        agents = Path(d) / 'agents'
        env = dict(os.environ, PATH=f'{binp}:{os.environ.get("PATH", "")}', FAKE_LOG=str(log),
                   LAUNCH_AGENTS_DIR=str(agents), CAFRESOHQ_LOG_DIR=d, CAFRESOHQ_HQ_STATE_DIR=str(Path(d) / 'state'))
        env.update(env_extra or {})
        r = subprocess.run(['bash', str(SCRIPT), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        calls = log.read_text().splitlines() if log.exists() else []
        plists = list(agents.glob('*.plist')) if agents.exists() else []
        return r.returncode, r.stdout + r.stderr, calls, plists


def main():
    print('the local office answers at the door the shell knocks on')
    src = SCRIPT.read_text(encoding='utf-8')
    check('the script parses', subprocess.run(['bash', '-n', str(SCRIPT)], capture_output=True).returncode == 0)
    code, out, calls, _ = run(['--help'])
    check('--help prints the header and touches nothing', code == 0 and 'your own office on this machine' in out and calls == [])
    code, out, calls, _ = run(['dance'])
    check('an unknown command is a usage error', code == 2 and 'unknown command' in out and calls == [])

    code, out, calls, _ = run(['plist'], {'PORT': '8790'})
    check('`plist` prints the LaunchAgent without installing anything', code == 0 and calls == [], out[-200:])
    try:
        pl = plistlib.loads(out.encode('utf-8'))
    except Exception as e:      # noqa: BLE001
        pl = {}
        check('the plist is well-formed XML', False, e)
    check('it runs serve.py from this repo, as the working directory',
          pl.get('ProgramArguments', [''])[-1] == str(ROOT / 'serve.py') and pl.get('WorkingDirectory') == str(ROOT), pl.get('ProgramArguments'))
    env = pl.get('EnvironmentVariables', {})
    check('it carries the requested port and a PATH with node on it (the drivers need it)',
          env.get('PORT') == '8790' and '/bin' in env.get('PATH', '') and env.get('HOME') == os.environ.get('HOME'), env)
    check('it starts at login, is kept alive, and logs to a file',
          pl.get('RunAtLoad') is True and pl.get('KeepAlive') is True and pl.get('StandardOutPath', '').endswith('cafreso-hq.log'), pl)
    check('its label is the one uninstall removes', pl.get('Label') == 'com.cafreso.hq' and 'launchctl bootout "$DOMAIN/$LABEL"' in src)

    code, out, calls, plists = run(['install'], {'PORT': '8787'}, lsof=FAKE_LSOF_BUSY)
    check('install refuses a port another program holds, names Docker, and points at another port',
          code == 1 and 'already taken' in out and 'Docker' in out and 'PORT=8789' in out and not any(c.startswith('bootstrap') for c in calls) and plists == [], out[-300:])

    probe = re.search(r'health\(\) \{[\s\S]*?\n\}', src).group(0)
    check('the health probe asks 127.0.0.1, never localhost', '127.0.0.1:$PORT/health' in probe and 'localhost' not in probe)
    check("the probe accepts only serve.py's own body", '\"status\": \"ok\"' in probe)

    dead = free_port()
    code, out, calls, _ = run(['status'], {'PORT': str(dead)})
    check('status on a dead port says down and exits 1', code == 1 and out.startswith('down') and 'not installed' in out, out[:200])

    with tempfile.TemporaryDirectory() as d:
        agents = Path(d) / 'agents'
        agents.mkdir()
        (agents / 'com.cafreso.hq.plist').write_text('<plist/>')
        binp = Path(d) / 'bin'
        binp.mkdir()
        (binp / 'launchctl').write_text(FAKE_LAUNCHCTL)
        (binp / 'launchctl').chmod(0o755)
        env = dict(os.environ, PATH=f'{binp}:{os.environ.get("PATH", "")}', FAKE_LOG=str(Path(d) / 'l.log'), LAUNCH_AGENTS_DIR=str(agents))
        r = subprocess.run(['bash', str(SCRIPT), 'uninstall'], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        check('uninstall boots the agent out, removes the plist, leaves the state',
              r.returncode == 0 and not (agents / 'com.cafreso.hq.plist').exists() and 'untouched' in r.stdout
              and 'bootout' in (Path(d) / 'l.log').read_text(), r.stdout + r.stderr)

    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    check("serve.py's default port is the shell's first probe port (8787)", "os.environ.get('PORT', '8787')" in serve)
    check("serve.py's CORS allowlist names the shell's origin", "'https://ai.cafreso.com'" in serve)
    doc = (ROOT / 'docs' / 'LOCAL_HQ.md').read_text(encoding='utf-8')
    check('the runbook says how to connect and what Safari needs', 'custom port' in doc and 'mkcert' in doc and 'Local network access' in doc)

    print()
    if FAILS:
        print(f'local office: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('local office: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
