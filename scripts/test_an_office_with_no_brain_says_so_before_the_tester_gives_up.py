#!/usr/bin/env python3
"""A first message to an office with no brain took 46 seconds to say nothing.

`## 396.` got the office booting for a stranger and then classified the next
thing it hit as a product decision: no brain ships with the office, so until
the tester installs hermes / LM Studio / Ollama or brings a key, every message
fails. Which brain to bundle IS a product decision. How long the failure takes
and what it says are not.

Measured on a genuine cold start — `git archive HEAD | tar -x`, a temp `HOME`
with no `~/.hermes`, a `PATH` with no `hermes` on it, the gateway port pointed
at a dead port — driving `fetchStreamHead` lifted out of claude-client.jsx the
way the browser calls it:

    ms: 46467   status: 502
    {"error": "hermes: [Errno 61] Connection refused",
     "hint": "the agent gateway is restarting or down — retry in ~15s"}

Forty-six seconds, not the fifteen `docs/BETA_READINESS.md` names, because the
fifteen is only one of three: `_hermes_proxy` retries the upstream connect ten
times at 1.5s, and 502 is a retryable status to `fetchStreamHead`, which tries
the whole thing three times with a backoff between. Three fifteens.

And what lands after them is a raw JSON object with a Unix errno in it, whose
only advice — retry in ~15s — is false on this machine specifically: nothing
is going to start. The one true thing about the tester's situation, that they
have no brain and there is a room where they can pick one, is the one thing
nobody says.

Every browser-side first message shares this path. The boss chat and the
coworker chat (hq-runtime.jsx), the terminal (views/terminal.jsx) and the
mission runner (agent_runner.jsx) all funnel through `CafresoHQClient.stream()`
→ `streamHermes` → `streamOpenAICompat`, and the default provider of a
brand-new office is 'hermes'. One fix, four surfaces.

The fix (`#399`):
  · drivers/hermes.py grows `gateway_can_appear()` — is the CLI on this
    machine, or has a gateway ever answered this process? The retry budget
    exists for the window after `gateway_restart()` replaces the running
    singleton, and that window can only exist if a gateway does. The fleet
    container pip-installs `hermes-agent`, so its console script resolves and
    its budget is untouched.
  · `_hermes_proxy` asks that before it waits, and answers **501** — the one
    5xx the RFC defines as a stable property of the server rather than a
    passing mood — carrying `message` (the honest sentence) and `hint` (the
    room).
  · `_retryableStatus` reads 501 as final, so the browser stops multiplying it.
  · `streamOpenAICompat` relays a body's written prose as the error instead of
    printing the JSON around it.

This suite:
  · structural — the predicate is consulted BEFORE the retry loop, the latch is
    set where the gateway answers, 501 is non-retryable client-side, and both
    advisory strings name a room `modals/settings.jsx` actually mounts;
  · behavioural, and general rather than pinned: it boots a real serve.py from
    a real cold tree with no hermes reachable, drives the browser's own
    `streamOpenAICompat` against it over the wire, and asserts a PROPERTY of
    the answer — under two seconds, and a sentence a person can act on that
    names neither a status code nor a JSON brace;
  · and the one way this fix could do harm: the same cold tree with a `hermes`
    on PATH must STILL sit out the restart window and still answer the
    retryable 502, because a gateway that is merely restarting is not absent.

Run: python3 scripts/test_an_office_with_no_brain_says_so_before_the_tester_gives_up.py
"""
import ast
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVE = ROOT / 'serve.py'
DRIVER = ROOT / 'drivers' / 'hermes.py'
CLIENT = ROOT / 'claude-client.jsx'
PATIENCE = ROOT / 'app' / 'patience.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'

# The whole point of the fix: an answer the tester gets before they wonder
# whether they broke something. Generous by ~80x over what was measured (24ms)
# so a loaded CI box cannot make this flaky, and still 20x under the single
# retry it replaced.
FAST_MS = 2000
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def _balanced(src, start, open_c, close_c):
    """Index just past the `open_c`…`close_c` pair beginning at `start`."""
    depth = 0
    for k in range(start, len(src)):
        if src[k] == open_c:
            depth += 1
        elif src[k] == close_c:
            depth -= 1
            if depth == 0:
                return k + 1
    raise AssertionError(f'unbalanced {open_c} at {start}')


def js_fn(src, name):
    """A JS function's whole source, by name. Balances the PARAMETER list
    first — `streamOpenAICompat({ base, label, … })` destructures, so the
    first `{` after the name belongs to the arguments, not the body, and a
    naive brace lift stops at the end of the signature."""
    m = re.search(r'^(?:async\s+)?function\s+%s\s*\(' % re.escape(name), src, re.M)
    if not m:
        raise AssertionError('no such function: ' + name)
    after_args = _balanced(src, m.end() - 1, '(', ')')
    body = src.index('{', after_args)
    return src[m.start():_balanced(src, body, '{', '}')]


def js_const(src, name):
    """`const NAME = …;` including a multi-line array/object initialiser (which
    the first `;` would cut in half) and a trailing line comment (which `;$`
    would miss)."""
    m = re.search(r'^const %s\s*=\s*' % re.escape(name), src, re.M)
    if not m:
        raise AssertionError('no such const: ' + name)
    opener = src[m.end():m.end() + 1]
    end = m.end()
    if opener in '[{':
        end = _balanced(src, m.end(), opener, ']' if opener == '[' else '}')
    return src[m.start():src.index(';', end) + 1]


def soft(fn, *a):
    """A structural lift that returns '' instead of raising when the symbol is
    absent. The checks below say what is missing far better than a traceback
    does — and a traceback here would abort before the live half, which is
    where the evidence for this entry lives."""
    try:
        return fn(*a)
    except Exception:
        return ''


# ── round 1: structure ───────────────────────────────────────────────────────
def structural():
    print('=== the office asks before it waits ===')
    driver = DRIVER.read_text(encoding='utf-8')
    serve = SERVE.read_text(encoding='utf-8')
    client = CLIENT.read_text(encoding='utf-8')

    check('drivers/hermes.py answers "could a gateway appear?"',
          'def gateway_can_appear(' in driver,
          'the retry budget needs a predicate to be worth paying')
    predicate = soft(brace_lift_py, driver, 'gateway_can_appear')
    check('the predicate is satisfied by an installed CLI',
          'resolve(' in predicate,
          'a fleet container has hermes on PATH and must keep its full budget')
    check('the predicate is also satisfied by a gateway that already answered',
          '_gateway_seen_alive' in predicate,
          'a gateway started some other way must not be written off')
    check('something sets that latch', 'def note_gateway_alive(' in driver)

    # The order is the fix. The predicate has to be read BEFORE the loop that
    # spends the fifteen seconds, not after it.
    proxy = soft(brace_lift_py, serve, '_hermes_proxy')
    i_ask = proxy.find('gateway_can_appear')
    i_sleep = proxy.find('time.sleep(1.5)')
    check('_hermes_proxy consults the predicate', i_ask >= 0)
    check('_hermes_proxy still HAS a retry budget for a real gateway',
          i_sleep >= 0, 'the ~10-15s restart window is why it exists')
    check('it asks before it waits', 0 <= i_ask < i_sleep,
          'a check after the loop has already cost the tester the silence')
    check('the fast answer is 501, not another 502',
          re.search(r'_send_json\(501,\s*\{', proxy) is not None,
          'a 502 is retryable and the browser would multiply it by three')
    check('the proxy latches a gateway that answered',
          'note_gateway_alive()' in proxy)

    print()
    print('=== the browser treats a settled answer as settled ===')
    retryable = soft(js_fn, client, '_retryableStatus')
    check('_retryableStatus refuses to retry 501',
          re.search(r'status\s*===\s*501', retryable) is not None
          and 'return false' in retryable,
          'three attempts at a permanent answer is three times the wait')
    check('every other 5xx still retries',
          'status >= 500' in retryable and 'status === 429' in retryable,
          'this fix must not disarm the transient-failure retry')

    compat = soft(js_fn, client, 'streamOpenAICompat')
    # Scoped to the refusal branch. The mid-stream reader further down reads
    # `j.error` on purpose — an SSE error frame IS shaped that way — and this
    # check is only about what a non-2xx BODY is allowed to contribute.
    refusal = ''
    if 'if (!res.ok) {' in compat:
        i = compat.index('if (!res.ok) {')
        refusal = compat[i:_balanced(compat, compat.index('{', i), '{', '}')]
    check('streamOpenAICompat relays a body that carries prose',
          'j.message' in refusal and 'j.hint' in refusal,
          'otherwise the sentence arrives wrapped in the JSON it was meant '
          'to replace')
    check("it does NOT relay the machine's own word for the fault",
          not re.search(r'\bj\.error\b', refusal),
          "`error` is 'no_brain' / 'trial_limit' / an errno — not a sentence")

    print()
    print('=== the advice names a room that exists ===')
    # A general property, the rule test_the_room_the_warning_names.py exists
    # to keep: any room this failure sends a stranger to must be mounted.
    advice = ' '.join(re.findall(r"_NO_BRAIN_(?:MESSAGE|HINT) = \(([^)]*)\)", serve))
    check('serve.py carries a written no-brain sentence AND a way forward',
          '_NO_BRAIN_MESSAGE' in serve and '_NO_BRAIN_HINT' in serve
          and len(advice) > 80, repr(advice[:120]))
    rooms = set(re.findall(r'Settings → ([A-Z][a-z]+)', advice))
    check('the advice names a Settings room', bool(rooms), advice[:200])
    settings_src = SETTINGS.read_text(encoding='utf-8')
    for room in sorted(rooms):
        check(f'Settings → {room} is a tab settings.jsx mounts',
              f"'{room.lower()}'" in settings_src,
              'the boss follows this sentence into an empty corridor')
    # And the panels it promises are in that room, by their own headings.
    for panel in sorted({p.strip() for p in re.findall(r'\b[A-Z][A-Z ]{4,}\b', advice)}):
        check(f'the panel "{panel}" is really in that room',
              f'<h4>{panel}</h4>' in settings_src,
              'named a panel the boss will not find')
    check('the advice never tells this tester to just wait',
          'retry' not in advice.lower(),
          'nothing is going to start on its own — that is the whole finding')


def brace_lift_py(src, funcname):
    """A python function's source, by name, from serve.py."""
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == funcname:
            return ast.get_source_segment(src, n) or ''
    raise AssertionError('no such function: ' + funcname)


# ── round 2: driven ──────────────────────────────────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def cold_tree(tmp):
    """A checkout with everything serve.py imports. Symlinked so it stays
    cheap; dist-ui/ is included when it exists because this test is about the
    message path, not the bundle (`## 396.` owns that one)."""
    for entry in os.listdir(ROOT):
        if entry in {'node_modules', 'hq-state', '.git'}:
            continue
        os.symlink(ROOT / entry, os.path.join(tmp, entry))


def raw(port, method, path, body=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=90)
    try:
        conn.request(method, path, body=body,
                     headers={'content-type': 'application/json'} if body else {})
        r = conn.getresponse()
        return r.status, r.read().decode('utf-8', 'replace')
    except Exception as e:
        return 'DROPPED', f'{type(e).__name__}: {e}'
    finally:
        conn.close()


HARNESS = r'''
/* The browser's own send path, lifted verbatim, pointed at a real serve.py
   with no brain behind it. Everything below the marker is this test's. */
%(lifted)s

const _settings = { maxTokens: 64 };
globalThis.window = { dispatchEvent: () => {}, addEventListener: () => {}, removeEventListener: () => {} };

(async () => {
  const t0 = Date.now();
  let out = '', err = null;
  try {
    await streamOpenAICompat({
      base: '%(base)s',
      label: 'Hermes',
      messages: [{ role: 'user', content: 'hello' }],
      requireKey: false,
      noStreamOptions: true,
      defaultModel: 'hermes-agent',
      onToken: (t) => { out += t; },
    });
  } catch (e) { err = e && e.message ? e.message : String(e); }
  console.log(JSON.stringify({ ms: Date.now() - t0, out, err }));
})();
'''


def lifted_source():
    client = CLIENT.read_text(encoding='utf-8')
    patience = PATIENCE.read_text(encoding='utf-8')
    parts = [js_const(patience, n) for n in
             ('PRIVATE_HOST', 'REMOTE_HEAD_MS', 'LOCAL_HEAD_MS', 'SLOW_HEAD_MS')]
    parts += [js_fn(patience, 'isLocalEndpoint'), js_fn(patience, 'headTimeoutMs')]
    parts += [js_const(client, n) for n in
              ('_STREAM_RETRY_MAX', '_STREAM_RETRY_BASE_MS', '_STREAM_RETRY_CAP_MS')]
    parts += [js_fn(client, n) for n in
              ('_retryableStatus', '_retryDelayMs', 'fetchStreamHead',
               'parseSSE', 'streamOpenAICompat')]
    return '\n'.join(parts)


def live():
    print()
    print('=== a cold office, a first message, driven over the wire ===')
    tmp = tempfile.mkdtemp(prefix='hq-nobrain-')
    home = tempfile.mkdtemp(prefix='hq-nobrain-home-')
    state = tempfile.mkdtemp(prefix='hq-nobrain-state-')
    binonly = tempfile.mkdtemp(prefix='hq-nobrain-bin-')
    proc = None
    try:
        cold_tree(tmp)
        port = free_port()
        # The fresh machine, made real three ways: a PATH with no `hermes` on
        # it (so resolve() is empty, exactly as on a tester's laptop), a HOME
        # with no ~/.hermes, and the gateway port pointed at a port nothing is
        # listening on. The empty PATH is also the safety rail — the developer
        # running this has a real gateway, and nothing here may reach it.
        env = {
            'PATH': binonly + ':/usr/bin:/bin:/usr/sbin:/sbin',
            'HOME': home,
            'PORT': str(port),
            'HERMES_HOME': os.path.join(home, '.hermes'),
            'HERMES_API_PORT': str(free_port()),      # nothing is listening there
            'CAFRESOHQ_HQ_STATE_DIR': state,
            'CAFRESOHQ_ALLOWED_DIRS': state,
        }
        check('this test really cannot see a hermes binary',
              shutil.which('hermes', path=env['PATH']) is None)
        proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=tmp, env=env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.STDOUT)
        up = False
        for _ in range(80):
            if raw(port, 'GET', '/health')[0] == 200:
                up = True
                break
            time.sleep(0.25)
        check('the office boots with no brain anywhere on the machine', up)
        if not up:
            return
        st, health = raw(port, 'GET', '/health')
        h = json.loads(health)
        check('and it knows it — /health says hermes:false, brain:null',
              h.get('hermes') is False and h.get('brain') is None, health[:200])

        # The measurement, at the wire. This is the number the entry quotes.
        t0 = time.time()
        st, body = raw(port, 'POST', '/hermes/v1/chat/completions',
                       json.dumps({'model': 'hermes-agent', 'stream': True,
                                   'messages': [{'role': 'user', 'content': 'hello'}]}))
        wire_ms = int((time.time() - t0) * 1000)
        check('the proxy answers a first message quickly', wire_ms < FAST_MS,
              f'{wire_ms}ms — this is the fifteen seconds of silence '
              '`docs/BETA_READINESS.md` calls the largest thing on the '
              'first-run path')
        check('and it answers with a status the browser reads as final',
              st == 501, f'{st}: {str(body)[:160]}')

        # And the same for the client's own liveness probe, which used to pay
        # the full budget just to ask whether there was anything to talk to.
        t0 = time.time()
        st_m, _ = raw(port, 'GET', '/hermes/v1/models')
        probe_ms = int((time.time() - t0) * 1000)
        check('the "is there a brain?" probe is fast too', probe_ms < FAST_MS,
              f'{probe_ms}ms — hermesStatus() gates the whole Agents surface')

        # Now the part the tester actually reads: drive the browser's real
        # send path and look at the sentence it throws.
        node = shutil.which('node')
        if not node:
            check('node is available to drive the browser send path', False,
                  'skipped — install node to run the behavioural half')
            return
        js = HARNESS % {'lifted': lifted_source(),
                        'base': f'http://127.0.0.1:{port}/hermes/v1'}
        jsf = os.path.join(tmp, '_nobrain_harness.mjs')
        with open(jsf, 'w', encoding='utf-8') as f:
            f.write(js)
        r = subprocess.run([node, jsf], capture_output=True, text=True, timeout=180)
        check('the harness ran', r.returncode == 0, r.stderr[-400:])
        if r.returncode != 0:
            return
        res = json.loads(r.stdout.strip().splitlines()[-1])
        said = (res.get('err') or '').strip()
        print(f'    → {res["ms"]}ms: {said}')

        check('the browser gives up in under two seconds', res['ms'] < FAST_MS,
              f'{res["ms"]}ms — measured at 46467ms before #399, because a '
              'retryable 502 made the browser pay the fifteen seconds three '
              'times over')
        check('the message fails rather than silently succeeding', bool(said),
              f'onToken got {res.get("out")!r}')

        # General properties of the sentence, not its wording. Any rewrite that
        # keeps the office honest keeps these; a regression to a status dump
        # or an errno breaks them.
        check('it is a sentence, not a payload',
              '{' not in said and '"' not in said, repr(said))
        check('it names no HTTP status code',
              not re.search(r'\b[45]\d\d\b', said), repr(said))
        check('it names no errno', 'Errno' not in said, repr(said))
        check('it says what is wrong in the office\'s own words',
              'brain' in said.lower(), repr(said))
        check('it names somewhere to go', 'Settings' in said, repr(said))
        check('it does not tell the tester to wait and try again',
              'retry' not in said.lower(), repr(said))
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        for d in (tmp, home, state, binonly):
            shutil.rmtree(d, ignore_errors=True)


def budget_survives():
    """The other half of the fix, and the only way it could do harm: an office
    that HAS a gateway must still get the full retry budget. The window after
    `gateway_restart()` replaces the running singleton is real, and a transient
    502 mid-conversation is worse than a wait. Same cold tree, same dead port,
    one difference — a `hermes` on PATH."""
    print()
    print('=== an office that HAS a gateway still waits for it ===')
    tmp = tempfile.mkdtemp(prefix='hq-hasbrain-')
    home = tempfile.mkdtemp(prefix='hq-hasbrain-home-')
    state = tempfile.mkdtemp(prefix='hq-hasbrain-state-')
    binonly = tempfile.mkdtemp(prefix='hq-hasbrain-bin-')
    proc = None
    try:
        cold_tree(tmp)
        # A stub, never invoked on this path — `resolve()` only ever asks
        # whether the name is on PATH. Deliberately inert rather than the real
        # binary: nothing in this suite may start or restart a live gateway.
        stub = os.path.join(binonly, 'hermes')
        with open(stub, 'w') as f:
            f.write('#!/bin/sh\nexit 0\n')
        os.chmod(stub, 0o755)
        port = free_port()
        env = {
            'PATH': binonly + ':/usr/bin:/bin:/usr/sbin:/sbin',
            'HOME': home,
            'PORT': str(port),
            'HERMES_HOME': os.path.join(home, '.hermes'),
            'HERMES_API_PORT': str(free_port()),      # still nothing listening
            'CAFRESOHQ_HQ_STATE_DIR': state,
            'CAFRESOHQ_ALLOWED_DIRS': state,
        }
        proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=tmp, env=env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.STDOUT)
        up = False
        for _ in range(80):
            if raw(port, 'GET', '/health')[0] == 200:
                up = True
                break
            time.sleep(0.25)
        check('the office boots with a hermes on PATH', up)
        if not up:
            return
        t0 = time.time()
        st, _ = raw(port, 'POST', '/hermes/v1/chat/completions',
                    json.dumps({'model': 'hermes-agent', 'stream': True,
                                'messages': [{'role': 'user', 'content': 'hello'}]}))
        ms = int((time.time() - t0) * 1000)
        check('it still sits out the restart window', ms > FAST_MS,
              f'{ms}ms — a gateway that is merely restarting was written off '
              'as absent, which turns a recoverable blip into a failed turn')
        check('and still answers the retryable 502 it always did', st == 502, st)
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        for d in (tmp, home, state, binonly):
            shutil.rmtree(d, ignore_errors=True)


def main():
    print('no brain: the office says so before the tester gives up')
    structural()
    live()
    budget_survives()
    print()
    if FAILS:
        print(f'no brain: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('no brain: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
