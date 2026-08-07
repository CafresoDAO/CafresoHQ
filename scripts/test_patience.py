#!/usr/bin/env python3
"""Head-timeout policy (app/patience.jsx) — pure-function suite.

This decides how long the office waits for a brain's first byte. Too short
and a cold local model — the zero-config first hire — fails on its first
job while being perfectly healthy. Too generous for a REMOTE endpoint and a
genuinely dead backend leaves the boss staring at dots.

The host check is the sharp edge: it must not be fooled by a hostname that
merely CONTAINS a private-looking string.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'patience.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    text = SRC.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('patience (head timeouts)')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
const L = (u) => isLocalEndpoint(u);
// ── loopback ────────────────────────────────────────────────────────────
R.localhost = L('http://localhost:11434');
R.loop4     = L('http://127.0.0.1:1234/v1');
R.loop4b    = L('http://127.1.2.3:8080');
R.loop6     = L('http://[::1]:8080/v1');
R.dotLocal  = L('http://studio.local:1234');
// ── RFC1918 ─────────────────────────────────────────────────────────────
R.ten       = L('http://10.0.0.5:11434');
R.oneNineTwo= L('http://192.168.1.50:11434');
R.oneSevenTwoLow  = L('http://172.16.0.5:11434');
R.oneSevenTwoHigh = L('http://172.31.255.254:11434');
R.oneSevenTwoOut  = L('http://172.32.0.1:11434');   // outside 172.16/12
R.oneSevenTwoPub  = L('http://172.15.0.1:11434');   // ditto, below the range
// ── remote ──────────────────────────────────────────────────────────────
R.openrouter = L('https://openrouter.ai/api/v1');
R.anthropic  = L('https://api.anthropic.com');
// ── things that merely LOOK local ───────────────────────────────────────
R.subdomain  = L('https://localhost.evil.com/v1');
R.fragment   = L('https://evil.com/#localhost');
R.pathOnly   = L('https://evil.com/127.0.0.1/v1');
R.userinfo   = L('https://localhost@evil.com/v1');
R.localSuffix= L('https://notlocalhost.com');
// ── non-URLs ────────────────────────────────────────────────────────────
R.relative   = L('/ollama/v1');
R.empty      = L('');
R.nullish    = L(null);
R.garbage    = L('not a url at all');
// ── headTimeoutMs ───────────────────────────────────────────────────────
R.declared   = headTimeoutMs({ local: true, url: 'https://openrouter.ai' });
R.byUrl      = headTimeoutMs({ url: 'http://127.0.0.1:11434' });
R.remote     = headTimeoutMs({ url: 'https://openrouter.ai/api/v1' });
R.relTimeout = headTimeoutMs({ url: '/ollama/v1' });
R.noArgs     = headTimeoutMs();
R.falseLocal = headTimeoutMs({ local: false, url: 'http://127.0.0.1:11434' });
R.truthyOnly = headTimeoutMs({ local: 1, url: 'https://openrouter.ai' });
// ── constants ───────────────────────────────────────────────────────────
R.remoteMs = REMOTE_HEAD_MS; R.localMs = LOCAL_HEAD_MS; R.slowMs = SLOW_HEAD_MS;
console.log(JSON.stringify(R));
''')

    check('localhost is local', out['localhost'] is True)
    check('127.0.0.1 is local', out['loop4'] is True)
    check('the whole 127/8 block is local', out['loop4b'] is True)
    check('IPv6 loopback is local', out['loop6'] is True)
    check('a .local mDNS name is local', out['dotLocal'] is True)

    check('10/8 is local', out['ten'] is True)
    check('192.168/16 is local', out['oneNineTwo'] is True)
    check('172.16 is local', out['oneSevenTwoLow'] is True)
    check('172.31 is local', out['oneSevenTwoHigh'] is True)
    check('172.32 is NOT local', out['oneSevenTwoOut'] is False)
    check('172.15 is NOT local', out['oneSevenTwoPub'] is False)

    check('a hosted provider is remote', out['openrouter'] is False)
    check('the Anthropic API is remote', out['anthropic'] is False)

    check('localhost.evil.com is NOT local', out['subdomain'] is False)
    check('a #localhost fragment is NOT local', out['fragment'] is False)
    check('127.0.0.1 in the PATH is NOT local', out['pathOnly'] is False)
    check('localhost@evil.com userinfo is NOT local', out['userinfo'] is False)
    check('notlocalhost.com is NOT local', out['localSuffix'] is False)

    check('a relative proxy path makes no claim', out['relative'] is False)
    check('an empty url makes no claim', out['empty'] is False)
    check('null makes no claim', out['nullish'] is False)
    check('an unparseable url makes no claim', out['garbage'] is False)

    check('a driver that declares itself local gets the long budget',
          out['declared'] == out['localMs'])
    check('a loopback url gets the long budget without declaring',
          out['byUrl'] == out['localMs'])
    check('a hosted url gets the short budget', out['remote'] == out['remoteMs'])
    check('a relative path falls back to the short budget',
          out['relTimeout'] == out['remoteMs'])
    check('no options at all is the short budget', out['noArgs'] == out['remoteMs'])
    check('local:false still honours a loopback url',
          out['falseLocal'] == out['localMs'], str(out['falseLocal']))
    check('only a strict true counts as a declaration',
          out['truthyOnly'] == out['remoteMs'], str(out['truthyOnly']))

    check('the local budget really is longer', out['localMs'] > out['remoteMs'])
    check('the slow-warning fires well before either gives up',
          out['slowMs'] < out['remoteMs'] < out['localMs'])

    print()
    if FAILS:
        print(f'patience: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('patience: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
