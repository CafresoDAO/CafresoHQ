#!/usr/bin/env python3
"""The office held two answers to "where is LM Studio", and said both.

Measured on the machine where they differ. LM Studio runs at
10.0.0.100:1234, not on the box serving the office.

    NEW HIRE → BRAIN picker:  eleven LM Studio models, listed by name.
    Front desk, same run:     no LM Studio card at all.

Neither surface was wrong about what it had asked. They had asked
different things. `serve.py`'s browser proxy was pinned to a literal:

    ROUTES = { '/lmstudio/': ('10.0.0.100', 1234), … }

— a private LAN address committed to a shipped file, pointing at one
machine on one network — while `LMStudioDriver.base_url()` reads
CAFRESOHQ_LMSTUDIO_URL / LMSTUDIO_BASE_URL and otherwise falls back to
http://localhost:1234/v1. The front desk only shows the card when THAT
probe comes back reachable. So the office could name the boss's twelve
local models on one screen and report not having found LM Studio on the
next, and a boss whose LM Studio is anywhere but localhost sees a front
desk offering only a subscription, a broken CLI and a stopped service.

One resolver now, read by both, defaulting to localhost — which is what
the driver already assumed and what the `/ollama/` line beside it had
right all along. `PORT` directly above ROUTES is the precedent: the thing
a self-hoster must change lives in the environment.

The second half is the consequence of the first. "Already running on this
machine" was the front desk's line for a local daemon, and it was true by
construction while localhost was the only address anything probed. Making
a remote backend detectable for the first time made that sentence
reachable and false, so the card now names the host it actually found.
Fixing the plumbing and leaving the copy would have traded a missing card
for a lying one.

Run: python3 scripts/test_the_office_agrees_where_the_brain_lives.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVE = ROOT / 'serve.py'
DRIVERS = ROOT / 'drivers' / 'local_http.py'
HIRE = ROOT / 'modals' / 'hire.jsx'
ENVEX = ROOT / '.env.example'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def py_block(src, header):
    """One def and its body — stopping at the next SIBLING def, not at the
    next top-level line. Stopping only at column 0 swallowed the whole rest
    of the class, which dragged `api_key`'s LMSTUDIO_API_KEY into the set
    of variables base_url supposedly reads and failed a correct source."""
    i = src.index(header)
    indent = len(header) - len(header.lstrip())
    lines = src[i:].split('\n')
    out = [lines[0]]
    for ln in lines[1:]:
        if not ln.strip():
            out.append(ln)
            continue
        col = len(ln) - len(ln.lstrip())
        if col <= indent:
            break
        out.append(ln)
    return '\n'.join(out)


def main():
    print('the office agrees where the brain lives')
    serve = SERVE.read_text(encoding='utf-8')
    drivers = DRIVERS.read_text(encoding='utf-8')
    hire = HIRE.read_text(encoding='utf-8')

    routes = re.search(r'ROUTES = \{(.*?)\n\}', serve, re.S)
    check('the proxy table is still there', bool(routes), serve[:0] or 'serve.py')
    if not routes:
        print()
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    table = routes.group(1)

    # ── 1. no address is written into the source ─────────────────────────
    # A bare IP or a non-loopback hostname in the table is the defect: it
    # ships one person's network to everyone who installs this.
    literals = re.findall(r"\(\s*'([^']+)'\s*,\s*(\d+)\s*\)", table)
    check('no backend host is hardcoded in the proxy table',
          not literals,
          f'{literals} — a private address committed to a shipped file is '
          'somebody else machine for every other install')
    check('...both routes resolve through one helper',
          len(re.findall(r'_local_route\(', table)) == 2,
          table.strip())

    # ── 2. the proxy asks the same env vars the driver does ──────────────
    # Derived, not hardcoded: add an env var to a driver and this tells you
    # the proxy cannot see it, which is exactly how the two drifted apart.
    def route_args(prefix):
        """The env names and default the TABLE passes for one prefix.

        Read from the table rather than restated here, so the behavioural
        arm below exercises the office's own arguments. Restating them made
        two fire arms pass while the table was wrong: mutating what the
        proxy asks for changed nothing the resolver test could see."""
        m = re.search(re.escape("'%s'" % prefix)
                      + r":\s*_local_route\(\(([^)]*)\),\s*'([^']+)'\)", table, re.S)
        if not m:
            return None, None
        return tuple(re.findall(r"'([A-Z_]+)'", m.group(1))), m.group(2)

    for cls, prefix in (('LMStudioDriver', '/lmstudio/'), ('OllamaDriver', '/ollama/')):
        i = drivers.index('class %s(' % cls)
        body = py_block(drivers[i:], '    def base_url(self):')
        want = set(re.findall(r"os\.environ\.get\('([A-Z_]+)'", body))
        names, dflt_used = route_args(prefix)
        have = set(names or ())
        check('%s asks what %s asks' % (prefix, cls), want and want <= have,
              f'driver reads {sorted(want)}, proxy reads {sorted(have)} — '
              'an env var only one side honours is how these drifted apart')
        dflt = re.search(r"or '(http[^']+)'\)", body)
        check('...and shares its default',
              bool(dflt) and dflt.group(1) == dflt_used,
              f'driver default {dflt.group(1) if dflt else "?"} vs proxy '
              f'default {dflt_used}')

    # ── 3. run the resolver ──────────────────────────────────────────────
    ns = {}
    exec('import os, urllib.parse\n' + py_block(serve, 'def _local_route('), ns)
    lr = ns['_local_route']
    import os as _os
    # The table's OWN arguments, not a restatement of them.
    LM_NAMES, LM_DEFAULT = route_args('/lmstudio/')
    LM_NAMES = LM_NAMES or ()
    LM_DEFAULT = LM_DEFAULT or ''
    cases = [
        ('nothing set', {}, ('localhost', 1234)),
        ('the office-scoped var', {'CAFRESOHQ_LMSTUDIO_URL': 'http://10.0.0.100:1234/v1'},
         ('10.0.0.100', 1234)),
        # LM Studio's own documented variable, honoured second so a machine
        # already configured for it does not have to be reconfigured.
        ('the vendor var', {'LMSTUDIO_BASE_URL': 'http://box.lan:4321/v1'}, ('box.lan', 4321)),
        # A host:port with no scheme is what people actually type.
        ('a bare host:port', {'CAFRESOHQ_LMSTUDIO_URL': '10.0.0.7:9999'}, ('10.0.0.7', 9999)),
        ('https with no port', {'CAFRESOHQ_LMSTUDIO_URL': 'https://brain.example'},
         ('brain.example', 443)),
    ]
    for label, env, want in cases:
        old = {k: _os.environ.get(k) for k in ('CAFRESOHQ_LMSTUDIO_URL', 'LMSTUDIO_BASE_URL')}
        for k in old:
            _os.environ.pop(k, None)
        _os.environ.update(env)
        try:
            got = lr(LM_NAMES, LM_DEFAULT)
        finally:
            for k, v in old.items():
                _os.environ.pop(k, None)
                if v is not None:
                    _os.environ[k] = v
        check('resolves %s' % label, got == want, f'{got} != {want}')

    # ── 4. the card stops claiming the wrong machine ─────────────────────
    check('the front desk knows what loopback looks like',
          re.search(r'const LOOPBACK = /', hire),
          'without this the card says "on this machine" about a host that '
          'is demonstrably not this machine')
    check('...and reads the address detection actually probed',
          re.search(r'hostOf\(det\.detail\)', hire),
          'guessing from the driver id would put us back to two answers')

    check('the env var a self-hoster needs is written down',
          'CAFRESOHQ_LMSTUDIO_URL' in ENVEX.read_text(encoding='utf-8'),
          'a setting nobody can discover is the same as no setting')

    if not shutil.which('node'):
        print('  SKIP  node not on PATH for the behavioural arm')
        return 1 if FAILS else 0

    # Each lift is a NAMED check, not a bare .group(0). Deleting the found
    # ternary -- the exact defect this half exists for -- made the third
    # search return None, and the file died with an AttributeError: no FAILED
    # line, no diagnosis, the fire arm reading as "not pinned". A test that
    # crashes is not a test that reports.
    lifts = [
        ('the loopback pattern is still there to be run',
         re.search(r'const LOOPBACK = /.*?/i;', hire)),
        ('the host reader is still there to be run',
         re.search(r'const hostOf = \(u\) => \{.*?\};', hire, re.S)),
        ('the card still chooses its line from the host',
         re.search(r'^\s*const host = localDaemon \? hostOf\(det\.detail\) : \'\';\n'
                   r'\s*const found = .*?: def\.found;', hire, re.S | re.M)),
    ]
    for label, m in lifts:
        check(label, bool(m), 'nothing in modals/hire.jsx to lift')
    if not all(m for _l, m in lifts):
        print()
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    scope = '\n'.join(m.group(0) for _l, m in lifts)
    lm = 'Already running on this machine — cheap and tireless.'
    cases_js = {
        'local': ('true', json.dumps('http://localhost:1234/v1')),
        'loopback_ip': ('true', json.dumps('http://127.0.0.1:11434/v1')),
        'remote': ('true', json.dumps('http://10.0.0.100:1234/v1')),
        # A CLI card is not a local daemon and must keep its own line.
        'not_a_daemon': ('false', json.dumps('/usr/local/bin/claude')),
        # detect() reports '' for a backend it never resolved.
        'undetected': ('true', json.dumps('')),
    }
    js = 'const def = { found: %s };\nconst R = {};\n' % json.dumps(lm) + '\n'.join(
        '{ const localDaemon = %s; const det = { detail: %s };\n%s\n  R[%s] = found; }'
        % (v[0], v[1], scope, json.dumps(k)) for k, v in cases_js.items()
    ) + '\nconsole.log(JSON.stringify(R));'
    p = subprocess.run(['node', '--input-type=module', '-e', js], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-1200:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    r = json.loads(p.stdout.strip().split('\n')[-1])

    check('a backend on this machine still says so', r['local'] == lm, r['local'])
    check('...including the numeric loopback', r['loopback_ip'] == lm, r['loopback_ip'])
    check('a backend across the network names the host',
          '10.0.0.100' in r['remote'] and 'this machine' not in r['remote'],
          r['remote'])
    check('a CLI card is left alone', r['not_a_daemon'] == lm, r['not_a_daemon'])
    check('an unresolved backend is not accused of being remote',
          r['undetected'] == lm,
          'no detail means no idea where it is — the same do-not-guess rule '
          'as every other absence in this app')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
