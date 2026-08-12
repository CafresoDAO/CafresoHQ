#!/usr/bin/env python3
"""The service worker must never let a dead office look alive.

`sw.js` has never executed — hq.html unregisters service workers on every
load ("re-enable for production"), so the whole PWA is built and switched
off. Which means it was never tested either. Driven for real on a throwaway
office, and the result is the worst thing found in this codebase all day.

The old fetch handler was a DENYLIST: cache every same-origin GET except a
list of known-live prefixes. That defaults to caching, so every endpoint
added after the list was written became cacheable silently — including the
three that answer "is this office alive". Measured with the server
COMPLETELY DEAD:

    GET /health                 → 200 {"status": "ok", …}
    GET /agent/drivers?probe=1  → 200 {"drivers": [ … ]}
    GET /missions/scheduled     → 200 {"schedules": [], …}

The office reporting itself healthy while nothing is running. It defeats the
offline banner, the front desk's "your office isn't answering", and every §7
route out at once — and it reintroduces the Tier-1 health false-positive
BELOW the app, where no care in the UI could detect it.

Now an allowlist: only the static shell is cacheable, so anything new is
uncached unless someone deliberately adds it. Re-driven after the change,
same dead server: all three now fail honestly with "Failed to fetch", while a
page reload still renders the offline shell.

The old fallback had a second fault this closes: a failed API GET was
answered with `caches.match('/hq.html')`, handing the caller an HTML page to
parse as JSON. Non-shell requests are no longer intercepted at all.

Run: python3 scripts/test_sw_never_caches_state.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SW = ROOT / 'sw.js'
HTML = ROOT / 'hq.html'

FAILS = []

# Every path that reports CURRENT state. Caching any of these is the bug.
LIVE_PATHS = [
    '/health', '/agent/drivers?probe=1', '/agents', '/missions/scheduled',
    '/missions/runs', '/approvals/external/list', '/cafresohq/status',
    '/codex/status', '/claudecode/status', '/browser/status', '/hermes/model',
    '/fs/browse?path=/x', '/vault/graph', '/tools/exec', '/idle',
    '/market/quotes', '/agents/install/status', '/hermes/trial-status',
]
# Static shell files, which SHOULD be cacheable or the PWA has no offline mode.
SHELL_PATHS = ['/', '/hq.html', '/styles.css', '/manifest.webmanifest',
               '/assets/icon-192.png', '/bundle/app-abc123.js', '/dist-ui/x.css']


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_js():
    """Run the REAL isShellAsset from sw.js against both path sets."""
    src = SW.read_text(encoding='utf-8')
    # Strip the SW-only listeners; keep the constants and helpers.
    body = re.sub(r'self\.addEventListener\([\s\S]*?\n\}\);\n', '', src)
    harness = body + '''
const R = { live: {}, shell: {} };
for (const p of %s) R.live[p]  = isShellAsset(new URL('http://x' + p));
for (const p of %s) R.shell[p] = isShellAsset(new URL('http://x' + p));
console.log(JSON.stringify(R));
''' % (json.dumps(LIVE_PATHS), json.dumps(SHELL_PATHS))
    proc = subprocess.run(['node', '--input-type=module', '-e', harness],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('service worker — a dead office must not answer "ok"')
    if not SW.is_file() or not HTML.is_file():
        print('  FAIL  missing sw.js / hq.html')
        return 1
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = SW.read_text(encoding='utf-8')
    out = run_js()

    cached_live = [p for p, v in out['live'].items() if v]
    check('no endpoint that reports current state is cacheable',
          not cached_live,
          f'{cached_live!r} — with the server dead these return a cached 200 and the '
          'office claims to be healthy while nothing is running')
    check('/health specifically is never cacheable',
          out['live'].get('/health') is False,
          'this one alone reintroduces the Tier-1 health false-positive, below the '
          'app where the UI cannot see it')

    # The other half: a fix that caches NOTHING would pass everything above
    # and silently delete the offline mode this worker exists for.
    uncached_shell = [p for p, v in out['shell'].items() if not v]
    check('the static shell IS still cacheable',
          not uncached_shell,
          f'{uncached_shell!r} — caching nothing would pass every check above and '
          'quietly remove the only reason to have a service worker')

    # ── Shape: an allowlist, so new endpoints fail safe ─────────────────
    check('the rule is an allowlist, not a denylist',
          'isShellAsset' in src and 'NEVER_CACHE_PREFIXES' not in src,
          'sw.js: a denylist defaults to CACHING, so every endpoint added after it '
          'was written becomes cacheable silently — which is exactly how /health '
          'got in')
    check('non-shell requests are not intercepted at all',
          re.search(r'if \(!navigating && !isShellAsset\(url\)\) return;', src) is not None,
          'sw.js: letting them through means a failed call fails honestly, which the '
          'app already has words for')
    check('a failed API call is never answered with the HTML shell',
          re.search(r'navigating \? caches\.match\(./hq\.html.\) : Response\.error\(\)', src) is not None,
          'sw.js: the old fallback handed callers a web page to JSON.parse')
    check('a page load still falls back to the offline shell',
          "caches.match('/hq.html')" in src and 'navigating' in src,
          'sw.js: without this there is no offline mode')
    check('the cache name was bumped so old caches are dropped',
          re.search(r"CACHE_NAME = 'cafresohq-shell-v([4-9]|\d\d)'", src) is not None,
          'sw.js: a browser holding v3 would keep serving the poisoned entries')

    # ── The registration is still OFF, deliberately ─────────────────────
    html = HTML.read_text(encoding='utf-8')
    check('the worker is still unregistered on load (enabling it is the boss\'s call)',
          'unregister()' in html and not re.search(r'serviceWorker\.register\(', html),
          'hq.html: a service worker is sticky — a bad one survives reloads and needs '
          'manual clearing. Turning this on is a deliberate decision, not a side '
          'effect of fixing the cache rules')

    print()
    if FAILS:
        print(f'service worker: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('service worker: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
