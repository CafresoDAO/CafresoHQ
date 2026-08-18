#!/usr/bin/env python3
"""#142 — the Memory panel promises "every job", and the night shift went out cold.

MemoryPanel (views/core.jsx) tells the boss their long-term memory entries
"go out with every job CafresoHQ and the team pick up". The browser keeps
that promise in agentStream, which folds memorySummary() into the system
prompt of every job it dispatches. Night-shift jobs are dispatched
server-side by night_runner.py — a Python port of the mission loop that
copied the iterations but not the memory around them — so every night job
ran with none of it, and the panel's "every" was false from dusk to dawn.

This suite pins:
  · byte parity — night_runner.memory_summary() must produce the exact
    string the browser's memorySummary() produces for the same entries
    (header, rows, newest-MEMORY_PROMPT_CAP slice), by actually running
    the browser function in node on the same data;
  · the cap constants on both sides are the same number;
  · the promise itself — the panel still renders its "every job" claims,
    and agentStream still folds `mem` into the browser system prompt (the
    other half of "every");
  · the night half live — a real serve.py, entries PUT through the real
    /hq/memory/context door, a real run_iteration: the system message
    carries the block exactly once, an empty store adds nothing, and a
    corrupt store file costs the run its memory but never the run.
"""
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNTIME_RAW = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
CORE_RAW = (ROOT / 'views' / 'core.jsx').read_text(encoding='utf-8')
NR_RAW = (ROOT / 'night_runner.py').read_text(encoding='utf-8')

sys.path.insert(0, str(ROOT))
import night_runner as nr  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print('  %s %s%s' % ('✓' if cond else '✗', name,
                         ('' if cond else ' — ' + str(detail)[:300])))
    if not cond:
        FAILS.append(name)


def brace_lift(src, header, start=0):
    """Extract a balanced-brace block starting at `header`."""
    i = src.find(header, start)
    if i < 0:
        raise AssertionError('anchor not found: %r' % header)
    depth = 0
    j = src.find('{', i)
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces after %r' % header)


def run_js(script):
    p = subprocess.run(['node', '--input-type=module', '-e', script],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise AssertionError('node failed: %s' % p.stderr[-800:])
    return json.loads(p.stdout.strip().splitlines()[-1])


# 30 well-formed entries, newest-first, shaped as the browser PUTs them.
ENTRIES = [{'id': 'mem_%02d' % i, 'tag': 'RULE' if i % 3 else 'NOTE',
            'text': 'memory entry %02d — the boss works at Cafreso' % i,
            'date': 'Today'} for i in range(30)]


def main():
    print('#142 — the night shift carries the boss\'s memory')

    # ── The promise, pinned at its source ───────────────────────────────
    print('\n[panel claims + browser half of "every job"]')
    check('panel: capped header still says "every job"',
          'go out with every job CafresoHQ and the team pick up' in CORE_RAW)
    check('panel: uncapped header still says "every job"',
          'carried into every job CafresoHQ and the team pick up' in CORE_RAW)
    check('panel: empty state still promises the CEO and crew',
          'goes out with every job your CEO and crew pick up' in CORE_RAW)
    check('panel cap is the runtime cap, not a second number',
          'const MEM_CAP = HQ.MEMORY_PROMPT_CAP;' in CORE_RAW)
    check('browser: memorySummary consumed by CEO chat AND agentStream',
          RUNTIME_RAW.count('const mem = memorySummary(HQ && HQ._memory);') == 2,
          'expected exactly 2 consumers')
    check('browser: agentStream folds mem into the system prompt',
          'journalNote, mem, reg].filter(Boolean)' in RUNTIME_RAW)

    # ── Cap parity ──────────────────────────────────────────────────────
    m = re.search(r'const MEMORY_PROMPT_CAP = (\d+);', RUNTIME_RAW)
    check('runtime cap constant found', bool(m))
    browser_cap = int(m.group(1)) if m else -1
    check('night cap == browser cap (%d)' % browser_cap,
          nr.MEMORY_PROMPT_CAP == browser_cap,
          'night=%r browser=%r' % (nr.MEMORY_PROMPT_CAP, browser_cap))

    # ── The night fix is wired where the browser wires it ───────────────
    print('\n[night wiring]')
    ri = brace_lift_py(NR_RAW, 'def run_iteration(')
    check('run_iteration fetches memory_summary(ctx)',
          'mem = memory_summary(ctx)' in ri)
    check('run_iteration folds it into the system persona',
          "persona += '\\n\\n' + mem" in ri)

    # ── Byte parity: run the BROWSER function on the same entries ───────
    print('\n[byte parity with the browser]')
    fn = brace_lift(RUNTIME_RAW, 'function memorySummary(memory) {')
    js = ('const MEMORY_PROMPT_CAP = %d;\n%s\nconst entries = %s;\n'
          'console.log(JSON.stringify(memorySummary(entries)));'
          % (browser_cap, fn, json.dumps(ENTRIES)))
    browser_out = run_js(js)

    # ── Live: a real serve.py, the real store door, a real iteration ────
    print('\n[live night run]')
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='night-mem-'))
    (tmp / 'vault').mkdir()
    (tmp / 'hq').mkdir()
    (tmp / 'work').mkdir()
    port = 9386
    base = 'http://127.0.0.1:%d' % port
    env = dict(os.environ)
    for k in list(env):
        if k.startswith('OCI_') or k in ('CAFRESOHQ_VAULT_BACKEND',
                                         'CAFRESOHQ_API_KEY',
                                         'OBSIDIAN_API_KEY', 'OBSIDIAN_API_URL'):
            env.pop(k)
    env.update(PORT=str(port), CAFRESOHQ_VAULT=str(tmp / 'vault'),
               CAFRESOHQ_HQ_STATE_DIR=str(tmp / 'hq'),
               CAFRESOHQ_MEMORY_DIR=str(tmp / 'hq' / 'memory'),
               CAFRESOHQ_ALLOWED_DIRS=str(tmp / 'work'))
    srv = subprocess.Popen([sys.executable, 'serve.py'], cwd=str(ROOT), env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base + '/missions/scheduled', timeout=2)
                break
            except Exception:
                time.sleep(0.25)
        else:
            check('server came up', False, 'never answered')
            return finish()

        ctx = nr.NightContext(base)

        # Nothing saved yet: /hq GET answers 200 + null, summary is empty.
        check('no store file → empty summary (200+null path)',
              nr.memory_summary(ctx) == '')

        def put(entries):
            req = urllib.request.Request(
                base + '/hq/memory/context', data=json.dumps(entries).encode(),
                headers={'Content-Type': 'application/json'}, method='PUT')
            return urllib.request.urlopen(req).status

        check('PUT 30 entries through the real door', put(ENTRIES) == 200)
        night_out = nr.memory_summary(ctx)
        check('night summary == browser summary, byte for byte',
              night_out == browser_out,
              'night=%r… browser=%r…' % (night_out[:90], browser_out[:90]))
        rows = night_out.splitlines()
        check('header + exactly the newest %d rows' % browser_cap,
              len(rows) == browser_cap + 1, 'got %d lines' % len(rows))
        check('row 1 is the NEWEST entry (index 0)',
              rows[1] == '  [NOTE] memory entry 00 — the boss works at Cafreso'
              if len(rows) > 1 else False, rows[1] if len(rows) > 1 else '')
        check('entries past the cap are absent (oldest dropped)',
              all('memory entry %02d' % i not in night_out for i in range(24, 30)))

        # End to end through the real iteration loop, LLM captured.
        captured = []
        real_llm = nr.llm_call
        nr.llm_call = lambda c, msgs: (
            captured.append([dict(x) for x in msgs]) or
            ('Quiet night — nothing new to add tonight.', 0))
        try:
            sched = {'id': 's1', 'type': 'research', 'topic': 'pricing',
                     'vaultFolder': 'Research/night', 'agentName': 'Scout'}
            out = nr.run_iteration(ctx, sched, 0, 4)
            check('iteration completed clean', out.get('error') is None, out)
            sysmsg = captured[0][0] if captured else {}
            usrmsg = captured[0][1] if captured and len(captured[0]) > 1 else {}
            check('system message carries the block exactly once',
                  sysmsg.get('role') == 'system' and
                  str(sysmsg.get('content', '')).count('Long-term memory (notes') == 1,
                  str(sysmsg.get('content', ''))[:120])
            check('a real entry reaches the night prompt',
                  'memory entry 00 — the boss works at Cafreso'
                  in str(sysmsg.get('content', '')))
            check('the block rides the system prompt, not the user prompt',
                  'Long-term memory (notes' not in str(usrmsg.get('content', '')))

            # Empty store: no header, no dangling block.
            check('PUT empty list', put([]) == 200)
            captured.clear()
            out = nr.run_iteration(ctx, sched, 0, 4)
            check('empty memory → persona has no memory block',
                  captured and 'Long-term memory (notes'
                  not in str(captured[0][0].get('content', '')))

            # Corrupt rows: skipped, well-formed neighbours still rendered.
            check('PUT mixed garbage', put(
                [ENTRIES[0], 'a bare string', 42,
                 {'tag': 'X', 'text': '   '}, ENTRIES[1]]) == 200)
            mixed = nr.memory_summary(ctx)
            check('corrupt rows skipped, real rows kept',
                  'memory entry 00' in mixed and 'memory entry 01' in mixed
                  and len(mixed.splitlines()) == 3, mixed)

            # Corrupt FILE: the run loses its memory, never the night.
            (tmp / 'hq' / 'memory' / 'context.json').write_text('{not json',
                                                                encoding='utf-8')
            check('corrupt store file → empty summary, no raise',
                  nr.memory_summary(ctx) == '')
            captured.clear()
            out = nr.run_iteration(ctx, sched, 0, 4)
            check('corrupt store file → the night still runs',
                  out.get('error') is None and bool(captured), out)

            # A non-200 answer is not memory, whatever shape its body is.
            # Every error body serve.py writes today is a dict, which the
            # per-row guard would reject anyway — so the status check only
            # earns its place against a body that IS a list: a proxy's error
            # page, a future error shape, a captive-portal JSON. Point the
            # context at one and the entries must not be read as the boss's
            # memory, because nothing about a 500 says they are theirs.
            stub = _list_bodied_error_server(500)
            try:
                bad = nr.NightContext('http://127.0.0.1:%d' % stub.server_port)
                check('non-200 with a LIST body is not read as memory',
                      nr.memory_summary(bad) == '', nr.memory_summary(bad)[:120])
            finally:
                stub.shutdown()
        finally:
            nr.llm_call = real_llm
    finally:
        srv.send_signal(signal.SIGTERM)
        try:
            srv.wait(timeout=10)
        except Exception:
            srv.kill()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    return finish()


def _list_bodied_error_server(status):
    """A localhost stub that answers every request with `status` and a JSON
    LIST body shaped like memory entries. Returns the running server."""
    import http.server
    import threading

    body = json.dumps([{'id': 'x', 'tag': 'RULE',
                        'text': 'proxy error page, not the boss\'s memory'}]
                      ).encode('utf-8')

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a):
            pass

    srv = http.server.HTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def brace_lift_py(src, header):
    """A python def block: from `header` to the next top-level def."""
    i = src.find(header)
    if i < 0:
        raise AssertionError('anchor not found: %r' % header)
    j = src.find('\ndef ', i + 1)
    return src[i:j if j > 0 else len(src)]


def finish():
    print('\n%s' % ('ALL CHECKS PASSED' if not FAILS
                    else 'FAILED: %d check(s): %s' % (len(FAILS), FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
