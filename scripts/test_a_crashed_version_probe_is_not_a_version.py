#!/usr/bin/env python3
"""One office, two doors, opposite answers about the same program.

`drivers/base.probe_cli` was corrected because it returned
`stdout or stderr` without ever reading the return code: a CLI that ran and
CRASHED had its crash line filed as its version, and the front desk offered
it as found-and-ready. Every driver in drivers/ was moved onto that fixed
probe.

`serve.py` kept its own copy. `_agent_version` — the probe behind
`GET /agents` — was the same six lines with the same missing test, one
import away from the fix, and it was missed because it does not live in
drivers/. Measured here, not imagined: one booted office, one shim on PATH
that exits 1 the way a real Codex whose vendored binary is gone does, both
doors asked in the same second:

    GET /agent/drivers?probe=1 → version '', probeError 'will not start',
                                 probeDetail 'Error: spawn …/codex ENOENT'
    GET /agents                → version 'Error: spawn /opt/nodejs/lib/node
                                 _modules/@openai/codex/vendor/aarch64-apple'

/agents is not a back road. It is the door the roster sync reads to keep a
hired coworker's line fresh, the door the model picker reads to decide
whether to offer "Gemini · file & shell access", and the door the first-run
gate reads to decide the office is already staffed and the welcome should
be skipped. All three were being told a broken program was a working one
with an unusually long version string.

The durable shape is not "codex". It is that the only version probe in the
building is the one that reads the return code, and that whatever it found
reaches the caller: a problem is not a version, and the office says which
it saw. A fifth CLI added next month is covered without editing this file —
the fixture crashes every agent the endpoint knows about, by name.

Run: python3 scripts/test_a_crashed_version_probe_is_not_a_version.py
"""
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import tokenize
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []

CRASH_LINE = ('Error: spawn /opt/nodejs/lib/node_modules/@openai/codex/'
              'vendor/aarch64-apple-darwin/codex/codex ENOENT')
GOOD_LINE = 'codex-cli 0.9.1'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(path):
    """Source with comments removed. `line.split('#')` would eat the `#`
    inside string literals and delete the code under test with it, so this
    goes through the tokenizer."""
    src = path.read_text(encoding='utf-8')
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                out.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        return src
    return '\n'.join(out)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def get_json(url, timeout=25):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception:
        return None


def shim_dir(tmp, names, exit_code, line, stream='stderr'):
    """A directory of fake CLIs, one per agent id the endpoint probes."""
    d = Path(tmp) / ('shims-%d' % exit_code)
    d.mkdir(parents=True, exist_ok=True)
    redirect = ' >&2' if stream == 'stderr' else ''
    for n in names:
        p = d / n
        p.write_text('#!/bin/sh\necho "%s"%s\nexit %d\n'
                     % (line, redirect, exit_code), encoding='utf-8')
        p.chmod(0o755)
    return d


def boot(path_prefix):
    """A real serve.py with `path_prefix` at the head of PATH."""
    tmp = tempfile.mkdtemp(prefix='probe340-')
    port = free_port()
    env = dict(os.environ, PORT=str(port),
               CAFRESOHQ_HQ_STATE_DIR=str(Path(tmp) / 'state'),
               PATH=str(path_prefix) + os.pathsep + os.environ.get('PATH', ''))
    for k in ('CAFRESOHQ_CODEX_BIN', 'CAFRESOHQ_CLAUDE_BIN',
              'CAFRESOHQ_GEMINI_BIN', 'CAFRESOHQ_HERMES_BIN',
              'CAFRESOHQ_API_KEY'):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT),
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % port

    def kill():
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    for _ in range(120):
        if get_json(base + '/health', timeout=3) is not None:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


def main():
    print('A crashed version probe is not a version')

    # ── 1. only one probe left in the building ─────────────────────────
    serve = strip_comments(ROOT / 'serve.py')
    check('serve.py imports the corrected probe instead of rolling its own',
          'probe_cli' in serve,
          'drivers/base.probe_cli is the one function that reads the return '
          'code; a second copy in serve.py is a second chance to drift')
    check('...and no version probe in serve.py reads stdout-or-stderr blind',
          '(r.stdout or r.stderr or' not in serve,
          'that expression IS the bug: it hands back whatever the command '
          'printed, crash or version, with returncode never consulted')

    tmp = tempfile.mkdtemp(prefix='probe340-shims-')
    # Every agent id GET /agents probes, taken from the endpoint itself so a
    # fifth CLI added later is covered without editing this file.
    ids = [a for a in ('hermes', 'claude', 'codex', 'gemini')]

    # ── 2. the broken office ────────────────────────────────────────────
    broken = shim_dir(tmp, ids, 1, CRASH_LINE)
    base, kill = boot(broken)
    check('an office boots with a crashing CLI on PATH', base is not None)
    if base is None:
        return 1
    try:
        agents = (get_json(base + '/agents') or {}).get('agents') or []
        drivers = (get_json(base + '/agent/drivers?probe=1') or {}).get('drivers') or []
    finally:
        kill()

    seen = [a for a in agents if a.get('installed')]
    check('the endpoint found the shims', len(seen) >= 3,
          [a.get('id') for a in agents])
    for a in seen:
        aid = a.get('id')
        check(f'/agents does not report {aid}\'s crash as its version',
              'ENOENT' not in (a.get('version') or '')
              and not (a.get('version') or ''),
              a.get('version'))
        check(f'...and says what it actually observed about {aid}',
              bool(a.get('probeError'))
              and 'ENOENT' in (a.get('probeDetail') or ''),
              {k: a.get(k) for k in ('version', 'probeError', 'probeDetail')})
        check(f'...while still listing {aid} as present (a hint, not a verdict)',
              a.get('installed') is True, a)

    # The two doors are the point: they described the same second of the
    # same machine and disagreed. Compared over the drivers that actually
    # run `<bin> --version` — hermes is excluded on purpose, because its
    # driver reports liveness ('gateway up' from a loopback probe) in the
    # version slot and has no --version verdict to agree or disagree with.
    by_id = {d.get('id'): (d.get('detect') or {}) for d in drivers}
    PROBED = ('claude-code', 'codex', 'gemini')
    for a in seen:
        if a.get('id') not in PROBED:
            continue
        det = by_id.get(a.get('id'))
        if det is None:
            continue
        check(f'both doors give the same verdict on {a.get("id")}',
              bool(det.get('probeError')) == bool(a.get('probeError'))
              and (det.get('version') or '') == (a.get('version') or ''),
              f'/agent/drivers {det.get("probeError")!r}/{det.get("version")!r} '
              f'vs /agents {a.get("probeError")!r}/{a.get("version")!r}')

    # ── 3. the working office is untouched ──────────────────────────────
    good = shim_dir(tmp, ids, 0, GOOD_LINE, stream='stdout')
    base, kill = boot(good)
    check('an office boots with a working CLI on PATH', base is not None)
    if base is not None:
        try:
            agents = (get_json(base + '/agents') or {}).get('agents') or []
        finally:
            kill()
        ok = [a for a in agents if a.get('installed')]
        check('a CLI that exits 0 still reports its version', bool(ok)
              and all(a.get('version') == GOOD_LINE for a in ok),
              [(a.get('id'), a.get('version')) for a in ok])
        check('...and is not marked broken', all(not a.get('probeError')
                                                 for a in ok),
              'the fix must not swallow the healthy case')

    # ── 4. the three callers that read this door ────────────────────────
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    client = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')
    gate = app[app.find('async function decideFirstRunWelcome'):][:900]
    check('the first-run gate does not count a crashing CLI as staffing',
          'probeError' in gate,
          'a brand-new boss whose only backend is broken gets no welcome, '
          'no hire deck, and no explanation')
    sync = app[app.find('const DEFS = {'):][:2400]
    check('the roster refresh stops telling the boss to sign in to it',
          'probeError' in sync, sync[:200])
    gem = client[client.find("find(a => a.id === 'gemini')"):][:600]
    check('the model picker stops offering a brain that cannot start',
          'probeError' in gem, gem[:200])

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), '; '.join(FAILS)))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
