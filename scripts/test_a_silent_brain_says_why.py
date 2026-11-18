#!/usr/bin/env python3
"""When the brain fails, the office says why instead of guessing "busy".

Seen live 2026-11-18 on a hosted office: the shared Gemma had been reloaded
from the LM Studio window with its default 8,192-token context. Hermes sends
13-16K tokens before the boss has said a word, and a CEO turn was about 45K,
so every model call was refused with exceed_context_size_error. Hermes's
chat-completions stream drops that error: it still closes the stream with
finish_reason "stop" and no text. The CEO then answered every message with
"the brain running this office may be offline or busy", which was wrong and
gave the boss nothing to act on.

The reason was sitting in HERMES_HOME/logs/errors.log the whole time. This
suite pins:
  1. the classifier turns each real log line into one plain sentence;
  2. auxiliary-client noise ("payment / credit error" on fallbacks) is not
     blamed for the main reply;
  3. only failures inside the reply's own time window count;
  4. with no log line, LM Studio's own state is read (no model / tiny context
     / not reachable), and a server that is not LM Studio yields no guess;
  5. a real serve.py answers GET /hermes/why-silent from a fake HERMES_HOME;
  6. the CEO and coworker "nothing came back" lines ask before guessing, and
     the client never asks about Hermes for a brain that is not Hermes.

Run: python3 scripts/test_a_silent_brain_says_why.py
"""
import datetime as dt
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import drivers.hermes as h  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (f'  — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(name)


# Lines copied from the live errors.log (container cafresohq-77af…, 2026-11-18).
CTX_LINE = ('2026-11-18 16:08:45,954 WARNING [api-34e35105471f7121] agent.conversation_loop: '
            'API call failed (attempt 1/3) error_type=APIError thread=asyncio_1:139018687735488 '
            'provider=lmstudio base_url=http://10.0.0.100:1234/v1 model=local-model '
            'summary=Engine protocol predict request returned 400: {"error":{"code":400,'
            '"message":"request (13839 tokens) exceeds the available context size (8192 tokens), try inc')
CTX_DONE = ('2026-11-18 16:08:46,032 ERROR [api-34e35105471f7121] agent.conversation_loop: '
            'Context length exceeded: 3,624 tokens. Cannot compress further.')
NO_MODEL = ('2026-11-18 16:02:07,971 ERROR [api-e047283a9dd38ca4] agent.conversation_loop: '
            "Non-retryable client error: Error code: 400 - {'error': {'message': \"No models loaded. "
            "Please load a model in the developer page or use the 'lms load' command.\", "
            "'type': 'invalid_request_error', 'param': 'model', 'code': None}}")
TIMEOUT = ('2026-11-09 03:38:53,522 ERROR [api-e047283a9dd38ca4] agent.conversation_loop: '
           'API call failed after 3 retries. Request timed out. | provider=lmstudio '
           'model=local-model msgs=35 tokens=~39,220')
AUX_NOISE = ('2026-11-18 16:09:47,293 WARNING [api-e047283a9dd38ca4] agent.auxiliary_client: '
             'Auxiliary: marking nous unhealthy for 60s (payment / credit error). HTTP 402')


def sentence_ok(s):
    return bool(s) and s[0].isupper() and s.endswith('.') and '_' not in s and '\n' not in s


print('1. each real failure becomes one sentence')
s = h.classify_brain_error(CTX_LINE.split('agent.conversation_loop: ', 1)[1])
check('context refusal names both sizes', '8,192' in s and '13,839' in s, s)
check('context refusal says what to do', 'larger context length' in s, s)
check('context sentence is plain', sentence_ok(s), s)
s = h.classify_brain_error(NO_MODEL)
check('"No models loaded" → no model loaded', s == h.SILENCE_NO_MODEL, s)
check('timeout → took too long', h.classify_brain_error(TIMEOUT) == h.SILENCE_TIMEOUT)
check('a 401 → key refused', h.classify_brain_error('Error code: 401 - invalid_api_key') == h.SILENCE_KEY)
check('a 402 → out of credit', h.classify_brain_error('HTTP 402: Insufficient credits') == h.SILENCE_CREDIT)
check('connection error → unreachable',
      h.classify_brain_error('APIConnectionError: Connection error.') == h.SILENCE_UNREACHABLE)
check('an unknown failure → no guess', h.classify_brain_error('something odd happened') == '')
for name in ('SILENCE_CONTEXT_SMALL', 'SILENCE_NO_MODEL', 'SILENCE_TIMEOUT', 'SILENCE_UNREACHABLE',
             'SILENCE_KEY', 'SILENCE_CREDIT'):
    txt = getattr(h, name).format(ctx='8,192')
    check(f'{name} is one plain sentence pair', sentence_ok(txt), txt)


def home_with(lines):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, 'logs'))
    with open(os.path.join(d, 'logs', 'errors.log'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return d


NOW = dt.datetime(2026, 11, 18, 16, 9, 0)
print('2. the log is read newest-first, main loop only')
home = home_with([NO_MODEL, CTX_LINE, CTX_DONE, AUX_NOISE])
s = h.recent_brain_error(home, 120, now=NOW)
check('the newest classifiable line wins (context, not the older no-model)', '8,192' in s, s)
check('auxiliary credit noise is not blamed',
      h.recent_brain_error(home_with([AUX_NOISE]), 120, now=NOW) == '')

print('3. only the reply\'s own window counts')
check('a failure from before the reply is ignored',
      h.recent_brain_error(home, 5, now=NOW + dt.timedelta(minutes=10)) == '')
check('a failure logged after the moment asked about is not blamed',
      h.recent_brain_error(home, 10, now=dt.datetime(2026, 11, 18, 16, 2, 10)) == h.SILENCE_NO_MODEL)
check('a missing log is not an error', h.recent_brain_error('/nonexistent', 60, now=NOW) == '')


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(payload=None, exc=None):
    def _open(url, timeout=0):
        _open.url = url
        if exc:
            raise exc
        return FakeResp(json.dumps(payload).encode())
    return _open


print('4. with no log line, the model server is asked')
llm = {'id': 'gemma', 'type': 'llm', 'state': 'loaded', 'loaded_context_length': 8192}
emb = {'id': 'nomic', 'type': 'embeddings', 'state': 'not-loaded'}
op = opener_for({'data': [llm, emb]})
s = h.model_server_state('http://10.0.0.100:1234/v1', opener=op)
check('LM Studio is asked at /api/v0/models', op.url == 'http://10.0.0.100:1234/api/v0/models', op.url)
check('an 8K load is called too small', '8,192' in s and 'too little' in s, s)
big = dict(llm, loaded_context_length=131072)
check('a 131K load is fine', h.model_server_state('http://x:1/v1', opener=opener_for({'data': [big]})) == '')
idle = dict(llm, state='not-loaded')
check('nothing loaded → no model loaded',
      h.model_server_state('http://x:1/v1', opener=opener_for({'data': [idle, emb]})) == h.SILENCE_NO_MODEL)
check('no answer at all → unreachable',
      h.model_server_state('http://x:1/v1', opener=opener_for(exc=urllib.error.URLError('timed out')))
      == h.SILENCE_UNREACHABLE)
check('a server that is not LM Studio → no guess',
      h.model_server_state('http://x:1/v1', opener=opener_for(
          exc=urllib.error.HTTPError('u', 404, 'nf', {}, None))) == '')
check('the log beats the probe',
      '13,839' in h.silence_reason(home, 120, base_url='http://x:1/v1',
                                   opener=opener_for({'data': [big]}), now=NOW))

print('5. a real serve.py answers /hermes/why-silent')
port = 19000 + os.getpid() % 1000
with tempfile.TemporaryDirectory() as tmp:
    hh = os.path.join(tmp, 'hermes')
    os.makedirs(os.path.join(hh, 'logs'))
    stamp = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(os.path.join(hh, 'logs', 'errors.log'), 'w') as f:
        f.write(CTX_LINE.replace('2026-11-18 16:08:45', stamp) + '\n')
    with open(os.path.join(hh, 'config.yaml'), 'w') as f:
        f.write('model:\n  default: local-model\n  provider: openrouter\n')
    env = dict(os.environ, PORT=str(port), CAFRESOHQ_BIND='127.0.0.1', CAFRESOHQ_FLEET_MODE='local',
               CAFRESOHQ_HQ_STATE_DIR=tmp, CAFRESOHQ_VAULT=tmp, HERMES_HOME=hh)
    proc = subprocess.Popen([sys.executable, 'serve.py'], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    got = None
    try:
        for _ in range(80):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/hermes/why-silent?within=30',
                                            timeout=3) as r:
                    got = json.load(r)
                break
            except Exception:
                time.sleep(0.25)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
check('the endpoint answers', isinstance(got, dict), str(got))
check('it reports the context refusal from the log',
      bool(got) and '8,192' in got.get('reason', ''), str(got))

print('6. the office asks before it guesses')
rt = (ROOT / 'hq-runtime.jsx').read_text(encoding='utf-8')
cl = (ROOT / 'claude-client.jsx').read_text(encoding='utf-8')
ceo = rt[rt.index('async function ceoStream('):rt.index('async function agentStream(')]
cw = rt[rt.index('async function agentStream('):]
for label, body, generic in (
        ('CEO', ceo, 'the brain running this office may be offline or busy'),
        ('coworker', cw, 'your office may be offline, or their brain may be busy')):
    i = body.index(generic)
    before = body[max(0, i - 900):i]
    check(f'the {label} line asks hermesWhySilent first', 'hermesWhySilent(' in before)
    check(f'the {label} keeps the generic line as the fallback', generic in body)
    check(f'the {label} times its own hop', 'const hopStarted = Date.now();' in body)
fn = cl[cl.index('async function hermesWhySilent('):]
fn = fn[:fn.index('\n}\n')]
check('the client only asks when the brain is Hermes', "!== 'hermes'" in fn)
check('the client does not ask when the shared brain is reached directly', 'sharedBrainDirect()' in fn)
check('the client sends the window it waited', '/hermes/why-silent?within=' in fn)
check('hermesWhySilent is exported on CafresoHQClient',
      'hermesWhySilent' in cl[cl.index('const CafresoHQClient = {'):])

print()
if FAILS:
    print(f'{len(FAILS)} FAILED')
    sys.exit(1)
print('all ok')
