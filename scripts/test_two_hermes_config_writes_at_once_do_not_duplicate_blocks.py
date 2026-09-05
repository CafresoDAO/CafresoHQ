#!/usr/bin/env python3
"""A coworker picks a model while another flips lite/full at the same
moment; five of sixty rounds left config.yaml holding TWO toolsets/agent/
tools blocks glued together instead of one.

`/hermes/model`, `/hermes/capability`, `/hermes/provider` and
`/hermes/config/import` are four separate HTTP endpoints that all read
~/.hermes/config.yaml, derive a new full-file body from it in Python, and
used to write that body back with a bare

    with open(config_path(), 'w', encoding='utf-8') as f:
        f.write(new_cfg)

open(path, 'w') truncates the file the instant it opens — not at close —
and serve.py is a ThreadingMixIn server, so any two of those four doors
landing on config.yaml at the same moment (an ordinary Settings-page
double-click, or the Library's own model switch racing a night-shift
capability flip) can have one door's `open(path, 'r')` land in the middle
of another door's truncate-then-write and read a partial file.
`write_capability`'s own logic

    idx = cfg.find('\\ntoolsets:')
    new_cfg = (cfg[:idx + 1] if idx >= 0 else cfg.rstrip() + '\\n') + block

falls into the "no toolsets: line" branch when it catches config.yaml
mid-truncation, and APPENDS a second toolsets/agent/tools block instead of
replacing the one that (a moment later, fully written) is actually there.

Measured against a real running server: 200 rounds of one `/hermes/model`
POST racing one `/hermes/capability` POST onto one config.yaml, BEFORE the
fix — a duplicated toolsets:/agent:/tools: block turned up repeatedly (the
lead investigation saw it in 5 of an earlier 60-round run); AFTER the fix,
0 of 200.

Fix: a new `_atomic_write(path, text)` helper in drivers/hermes.py — write
to a `tempfile.mkstemp` tmp file unique to this call, in the same
directory, fsync it, then `os.replace()` into place — the identical tmp +
fsync + os.replace shape `_vault_write_local` (serve.py) already carries
for `PUT /vault/note?mode=write`, and `_hq_handler`'s `PUT /hq/state/
<name>` before that. `write_model`, `write_capability`, `write_provider`,
`clear_provider_key` and `import_config` all go through it now for every
file they touch (config.yaml, its .bak, capability_mode, .env). Any
reader now always sees either the whole old file or one writer's whole
new one — never a file caught mid-truncation — which removes the
mechanism that produced the duplicate block. (Two racing writers still
last-writer-wins against EACH OTHER's semantic change, same as
`/vault/note`'s accepted whole-body-replace semantics — this fix closes
the corruption, not the ordinary "last save wins" outcome.)

Guards:
  · N rounds of a model-switch racing a capability-flip on one config.yaml:
    toolsets:/agent:/tools: each appear exactly once, every round
  · config.yaml keeps a `model:` block and is never left empty/truncated
  · the four write paths route through _atomic_write (mkstemp + os.replace),
    not a bare open(path, 'w')
  · a plain single /hermes/model set and a plain single /hermes/capability
    set still work and read back correctly

Run: python3 scripts/test_two_hermes_config_writes_at_once_do_not_duplicate_blocks.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()


def post_json(url, obj):
    body = json.dumps(obj).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}


BASE_CONFIG = """model:
  default: openai/gpt-oss-120b:free
  provider: openrouter
  base_url: https://openrouter.ai/api/v1
approvals:
  mode: manual
toolsets:
  - hermes-cli
agent:
  environment_probe: false
  task_completion_guidance: false
tools:
  tool_search:
    enabled: true
    threshold_pct: 0
"""


def boot(hermes_home):
    """Boots serve.py against a THROWAWAY ~/.hermes-equivalent (HERMES_HOME).

    write_model/write_capability/write_provider all call
    drivers.hermes.gateway_restart(), which is `subprocess.Popen(['hermes',
    'gateway', 'restart'])` — a bare PATH lookup, not gated on HERMES_HOME.
    If the REAL `hermes` CLI is on this machine's PATH (it is, on a dev
    box that also runs the real assistant), that call launches the actual
    gateway daemon, not a fake one — a real, long-lived side effect this
    test must never cause. PATH here is pared down to the bare OS dirs so
    `shutil.which('hermes')`/PATH search inside the child fails cleanly
    (gateway_restart already catches that and reports restarted=False) —
    this test only needs python3 (invoked by absolute path) and the
    stdlib/serve.py machinery, none of which lives outside those dirs.
    """
    hermes_home.mkdir(parents=True, exist_ok=True)
    (hermes_home / 'config.yaml').write_text(BASE_CONFIG, encoding='utf-8')
    port = free_port()
    env = dict(os.environ, PORT=str(port), HERMES_HOME=str(hermes_home),
               PATH='/usr/bin:/bin:/usr/sbin:/sbin',
               GAP_CRON='0', NEWS_CRON='0', TOPICS_CRON='0')
    env.pop('SEARCH_WORKER', None)
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
        if get(base + '/missions/scheduled')[0] == 200:
            return base, kill
        time.sleep(0.25)
    kill()
    return None, (lambda: None)


ROUNDS = 60     # real-clock timing, not deterministic — matches the run
                # length the lead investigation used to first catch this
NM = 4          # concurrent /hermes/model writers per round
NC = 4          # concurrent /hermes/capability writers per round


# ── the write goes through an atomic swap on this door too ──────────────
def structure_checks():
    print('=== the config.yaml/capability_mode/.env writers claim, not truncate-in-place ===')
    src = (ROOT / 'drivers' / 'hermes.py').read_text(encoding='utf-8')
    check('an atomic-write helper exists',
          'def _atomic_write(' in src)
    helper = src[src.find('def _atomic_write('):]
    helper = helper[:helper.find('\ndef ', 4)]
    check('...and it writes through mkstemp',
          'mkstemp' in helper)
    check('...and swaps in with an atomic replace',
          'os.replace(tmp, path)' in helper)
    for fn in ('write_model', 'write_capability', 'write_provider',
               'clear_provider_key', 'import_config'):
        body = src[src.find('def %s(' % fn):]
        body = body[:body.find('\ndef ', 4)]
        check('%s() routes its writes through _atomic_write' % fn,
              '_atomic_write(' in body)
    check('no bare open(config_path(), \'w\'...) survives anywhere in the file',
          "open(config_path(), 'w'" not in src)


# ── the whole door, under real concurrency ───────────────────────────────
def race_checks(base, hermes_home):
    print()
    print('=== /hermes/model racing /hermes/capability — %d rounds ===' % ROUNDS)
    cfg_path = hermes_home / 'config.yaml'
    bad_rounds = []
    for rnd in range(ROUNDS):
        models = ['racemodel-%d-%d' % (rnd, i) for i in range(NM)]
        modes = ['full' if i % 2 == 0 else 'lite' for i in range(NC)]
        results = [None] * (NM + NC)
        barrier = threading.Barrier(NM + NC)

        def model_worker(i, _m=models):
            barrier.wait()
            results[i] = post_json(base + '/hermes/model', {'model': _m[i]})

        def cap_worker(i, _modes=modes):
            barrier.wait()
            results[NM + i] = post_json(base + '/hermes/capability', {'mode': _modes[i]})

        threads = ([threading.Thread(target=model_worker, args=(i,)) for i in range(NM)] +
                   [threading.Thread(target=cap_worker, args=(i,)) for i in range(NC)])
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        all_200 = all(r and r[0] == 200 for r in results)
        cfg = cfg_path.read_text(encoding='utf-8')
        counts = {k: cfg.count(k) for k in ('toolsets:', 'agent:', 'tools:', 'model:')}
        ok = all_200 and all(v == 1 for v in counts.values()) and len(cfg) > 0
        if not ok:
            bad_rounds.append({'round': rnd, 'all_200': all_200, 'counts': counts,
                                'len': len(cfg)})
    check('every round: config.yaml keeps exactly one toolsets:/agent:/tools:/model: '
          'block (never duplicated, never emptied)', not bad_rounds, bad_rounds)


def sanity_checks(base, hermes_home):
    print()
    print('=== a plain single model set and a plain single capability set still work ===')
    code, resp = post_json(base + '/hermes/model', {'model': 'plain-model-id'})
    check('a normal /hermes/model set still succeeds', code == 200, resp)
    code, resp = get(base + '/hermes/model')
    got = json.loads(resp) if code == 200 else {}
    check('...and reads back the model just set',
          code == 200 and got.get('model') == 'plain-model-id', resp)

    code, resp = post_json(base + '/hermes/capability', {'mode': 'full'})
    check('a normal /hermes/capability set still succeeds', code == 200, resp)
    code, resp = get(base + '/hermes/capability')
    got = json.loads(resp) if code == 200 else {}
    check('...and reads back the mode just set',
          code == 200 and got.get('mode') == 'full', resp)
    cfg = (hermes_home / 'config.yaml').read_text(encoding='utf-8')
    check('...and config.yaml still parses as exactly one block of each',
          cfg.count('toolsets:') == 1 and cfg.count('agent:') == 1
          and cfg.count('tools:') == 1, cfg)


def main():
    print('two hermes config writes at once do not duplicate blocks')
    structure_checks()
    with tempfile.TemporaryDirectory() as td:
        hermes_home = Path(td) / 'hermes_home'
        base, kill = boot(hermes_home)
        if not base:
            check('the office came up', False, 'server did not boot')
        else:
            try:
                race_checks(base, hermes_home)
                sanity_checks(base, hermes_home)
            finally:
                kill()

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
