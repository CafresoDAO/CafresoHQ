#!/usr/bin/env python3
"""A Project Terminal `claude` turn that DIED must not read as a finished one.

pty_server.py's /terminal/stream runs three CLIs through one function, and
each arm ends with a tail that decides the turn's outcome. gemini and codex
have always spelled it the same way:

    if rc and rc not in (0, None):  sse_delta('… exited …', 'error')
    elif not text_emitted:          sse_delta('… returned no content …', 'error')

The claude arm carried an extra clause nobody else had:

    if proc.returncode and proc.returncode != 0 and not (in_tokens or out_tokens):

claude's `--output-format stream-json` puts `usage` on the FIRST assistant
message, so in_tokens is non-zero for any turn that produced anything at all.
The suppressor was therefore armed for essentially every real turn: a session
that streamed half a paragraph and then died — OOM, a kill, a PreToolUse hook
refusal, a dropped upstream socket, `error_max_turns` — exited non-zero and
emitted NO error marker. `delta.type === 'error'` is the only signal the
terminal UI has to tell a failed turn from a delivered reply, so the truncated
text landed as the answer.

That is the same suppressor drivers/claude_code.py was corrected for — its own
comment names the old test, `returncode and not emitted and not (in_tok or
out_tok)` — but the family rule was only ever enforced over drivers/*.py, so
this second copy of the same parser, on the surface the boss actually types
into, kept it. The same fix also teaches this copy to read the `result`
frame's `is_error` / `subtype`, which is where the CLI states its own verdict.

This test drives the REAL pty_server._terminal_stream() with a fake `claude`
binary on disk that emits real stream-json and exits with a chosen code, and
asserts on the SSE frames the function actually writes.

Run: python3 scripts/test_a_crashed_terminal_turn_is_not_a_finished_reply.py
"""
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pty_server  # noqa: E402

failures = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        failures.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


# ── A fake `claude` CLI ─────────────────────────────────────────────────────
# Prints the stream-json lines handed to it via CLAUDE_FAKE_LINES (one JSON
# object per line, '|' separated), writes CLAUDE_FAKE_STDERR to stderr, then
# exits with CLAUDE_FAKE_RC. Real argv, real stdin, real process exit.
FAKE_CLI = r'''#!/usr/bin/env python3
import os, sys
try: sys.stdin.read()
except Exception: pass
for ln in (os.environ.get('CLAUDE_FAKE_LINES') or '').split('|'):
    if ln.strip():
        sys.stdout.write(ln + '\n')
sys.stdout.flush()
err = os.environ.get('CLAUDE_FAKE_STDERR') or ''
if err:
    sys.stderr.write(err)
    sys.stderr.flush()
sys.exit(int(os.environ.get('CLAUDE_FAKE_RC') or '0'))
'''


class FakeWFile:
    def __init__(self):
        self.buf = bytearray()

    def write(self, b):
        self.buf.extend(b)

    def flush(self):
        pass


class FakeHandler:
    """The minimum of BaseHTTPRequestHandler that _terminal_stream touches."""

    def __init__(self, body, bin_path):
        raw = json.dumps(body).encode('utf-8')
        self.headers = {'content-length': str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = FakeWFile()
        self._bin = bin_path
        self.json_out = None

    def _claudecode_resolve(self):
        return self._bin

    def _send_json(self, code, obj):
        self.json_out = (code, obj)
        return None

    def send_response(self, code):
        pass

    def send_header(self, k, v):
        pass

    def end_headers(self):
        pass


def run_turn(lines, rc, stderr=''):
    """Drive the real _terminal_stream and return the parsed SSE frames."""
    with tempfile.TemporaryDirectory() as td:
        bin_path = os.path.join(td, 'fake_claude.py')
        with open(bin_path, 'w', encoding='utf-8') as fh:
            fh.write(FAKE_CLI)
        os.chmod(bin_path, 0o755)
        proj = os.path.join(td, 'project')
        os.makedirs(proj)

        prev_env = {k: os.environ.get(k) for k in
                    ('CLAUDE_FAKE_LINES', 'CLAUDE_FAKE_RC', 'CLAUDE_FAKE_STDERR')}
        os.environ['CLAUDE_FAKE_LINES'] = '|'.join(json.dumps(x) for x in lines)
        os.environ['CLAUDE_FAKE_RC'] = str(rc)
        os.environ['CLAUDE_FAKE_STDERR'] = stderr
        prev_path = pty_server._client_path
        pty_server._client_path = lambda p: p
        try:
            # _terminal_stream builds `cmd = [bin_, '--print', …]` and spawns
            # it for real; the shebang + chmod above make the fake executable.
            h = FakeHandler({'cli': 'claude', 'cwd': proj,
                             'messages': [{'role': 'user', 'content': 'hello'}]},
                            bin_path)
            pty_server._terminal_stream(h)
        finally:
            pty_server._client_path = prev_path
            for k, v in prev_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        if h.json_out is not None:
            raise AssertionError('stream refused: %r' % (h.json_out,))
        return parse_sse(bytes(h.wfile.buf).decode('utf-8', 'replace'))


def parse_sse(text):
    out = []
    for chunk in text.split('\n\n'):
        chunk = chunk.strip()
        if not chunk.startswith('data: '):
            continue
        payload = chunk[len('data: '):]
        if payload == '[DONE]':
            continue
        try:
            out.append(json.loads(payload))
        except json.JSONDecodeError:
            pass
    return out


def deltas(frames, type_=None):
    got = []
    for f in frames:
        for c in (f.get('choices') or []):
            d = c.get('delta') or {}
            if type_ is None or d.get('type') == type_:
                got.append(d.get('content') or '')
    return got


ASSISTANT_WITH_USAGE = {
    'type': 'assistant',
    'message': {
        'content': [{'type': 'text', 'text': 'Here is the first half of the ans'}],
        # The whole reason the old guard never fired: usage arrives on the
        # FIRST assistant message, long before the turn can go wrong.
        'usage': {'input_tokens': 1200, 'output_tokens': 9},
    },
}

print('a crashed terminal turn is not a finished reply')

# 1. The measured case: text streamed, usage counted, process died non-zero.
frames = run_turn([ASSISTANT_WITH_USAGE], rc=137, stderr='Killed')
errs = deltas(frames, 'error')
check('a non-zero exit after usage was counted still marks the turn failed',
      bool(errs), 'no delta.type=="error" frame at all: %r' % (deltas(frames),))
check('the failure names the exit code the CLI died with',
      any('137' in e for e in errs), repr(errs))
check('the half-answer is still delivered (the words stand)',
      any('first half' in t for t in deltas(frames, 'text')))

# 2. The CLI's own verdict on the `result` frame.
frames = run_turn([ASSISTANT_WITH_USAGE,
                   {'type': 'result', 'subtype': 'error_max_turns',
                    'is_error': True, 'result': 'ran out of turns',
                    'usage': {'input_tokens': 1200, 'output_tokens': 40}}],
                  rc=0)
errs = deltas(frames, 'error')
check('a turn the CLI itself declared failed is marked failed even on exit 0',
      bool(errs), 'no error delta: %r' % (deltas(frames),))
check('the failure quotes what the CLI said went wrong',
      any('ran out of turns' in e or 'error_max_turns' in e for e in errs),
      repr(errs))

# 3. An in-band error frame is a verdict, not a passing remark.
frames = run_turn([{'type': 'error', 'message': 'upstream connection reset'}],
                  rc=0)
errs = deltas(frames, 'error')
check('an in-band error frame ends the turn as an error',
      any('upstream connection reset' in e for e in errs), repr(errs))

# 4. A CLI that printed nothing at all is not a silent success.
frames = run_turn([], rc=0, stderr='not logged in')
check('a turn with no content at all says so',
      bool(deltas(frames, 'error')), repr(deltas(frames)))

# 5. The guard must not cry wolf: a clean turn stays clean.
frames = run_turn([ASSISTANT_WITH_USAGE,
                   {'type': 'result', 'subtype': 'success', 'is_error': False,
                    'result': 'done',
                    'usage': {'input_tokens': 1200, 'output_tokens': 40}}],
                  rc=0)
check('a successful turn emits no error marker',
      not deltas(frames, 'error'), repr(deltas(frames, 'error')))
check('a successful turn still reports its usage',
      any((f.get('usage') or {}).get('total_tokens') for f in frames),
      repr(frames))

# 6. The rule is the family's, not this arm's alone — the three CLI tails of
#    the one function must agree. Comments stripped first: the prose above
#    quotes the very predicate this checks for.
src = (ROOT / 'pty_server.py').read_text(encoding='utf-8')
code = '\n'.join(re.sub(r'(?<!["\'])#.*$', '', ln) for ln in src.splitlines())
check('no CLI tail excuses a non-zero exit because tokens were counted',
      'not (in_tokens or out_tokens)' not in code,
      'the usage-suppressor is still in pty_server.py')
check('all three CLI arms track whether anything was emitted',
      code.count('text_emitted') >= 6, 'text_emitted appears %d times'
      % code.count('text_emitted'))

print()
if failures:
    print('FAILED %d check(s): %s' % (len(failures), ', '.join(failures)))
    sys.exit(1)
print('all checks passed')
