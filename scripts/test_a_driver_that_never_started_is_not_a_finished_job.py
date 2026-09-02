#!/usr/bin/env python3
"""The hire board labels Codex WON'T START and then says "You can still hire
them and try". Taking it at its word, on a fresh office:

  BEFORE: the task landed in DONE and the card read
          "✓ Codex finished this · just now"
          directly above
          "⚠ Codex error: exited 127: env: node: No such file or directory".
  AFTER:  the task stays parked in DOING and the floor reads
          "Codex · could not start work on "Research brief: …"".

The office was certifying a job whose CLI never started, and it took two
independent gaps to do it:

  1. serve.py's _agent_stream_legacy flattened the driver's error into a plain
     content frame -- its own docstring recorded this as the design
     ("error→⚠ content frame"). pty_server.py's sse_delta has always sent
     'type': 'error'; the newer driver-based route dropped it.
  2. The three CLI stream clients in claude-client.jsx read `delta.content` and
     dropped `delta.type`, so even a marked frame arrived as ordinary output.
     /terminal/stream already forwarded it; those three did not.

With the marker gone, the error banner IS substance by every measure the app
has, so `hasSubstance(cleanBuf)` said the run delivered.

Checks the whole chain, because fixing either end alone leaves it broken --
which is exactly what happened mid-fix: the client was patched first and the
task still went to DONE, because the frame carried no marker to read.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(' -- ' + detail) if detail else ''}")
        failures.append(label)


def strip_js_comments(src):
    out, i, n, q = [], 0, len(src), None
    while i < n:
        c = src[i]
        if q:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(src[i + 1]); i += 2; continue
            if c == q:
                q = None
            i += 1
            continue
        if c in '"\'`':
            q = c; out.append(c); i += 1; continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2); j = n if j == -1 else j + 2
            out.append(''.join(x if x == '\n' else ' ' for x in src[i:j])); i = j; continue
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i); j = n if j == -1 else j
            out.append(' ' * (j - i)); i = j; continue
        out.append(c); i += 1
    return ''.join(out)


def strip_py_comments(src):
    return "\n".join(re.sub(r'#.*$', '', ln) for ln in src.split("\n"))


def read(rel):
    return open(os.path.join(ROOT, rel)).read()


def main():
    # ---- 1. the wire carries the marker -----------------------------------
    print("1. serve.py marks a driver error as an error on the wire")
    serve = strip_py_comments(read('serve.py'))
    m = re.search(r"elif et == 'error':\s*\n\s*write_sse\((.{0,300}?)\}\)", serve, re.S)
    check("the _agent_stream_legacy error frame was found", m is not None)
    if m:
        frame = ' '.join(m.group(1).split())
        check("it sets 'type': 'error' (not just content)",
              "'type': 'error'" in frame, frame[:150])
        check("it still carries the human-readable banner",
              'content' in frame and 'error:' in frame, frame[:150])

    # ---- 2. the client reads it -------------------------------------------
    print("2. readCliDelta keeps the text AND carries the failure back")
    client = read('claude-client.jsx')
    i = client.find('function readCliDelta(')
    check("readCliDelta exists (one reader for the three CLI clients)", i != -1)
    if i == -1:
        print("FAILED: no reader to test")
        return 1
    # Body brace, not the destructured-parameter brace: the signature is
    # `readCliDelta(j, { onToken, onUsage }, state)`, so the first `{` after the
    # name belongs to the params and depth-counting from it closes immediately.
    j = client.index('{', client.index(')', i))
    depth = 0
    for k in range(j, len(client)):
        if client[k] == '{':
            depth += 1
        elif client[k] == '}':
            depth -= 1
            if depth == 0:
                helper = client[i:k + 1]; break

    harness = helper + """
const frame = (content, type) => ({ choices: [{ index: 0, delta: type ? { content, type } : { content } }] });
const run = (frames) => {
  const seen = []; const state = { driverError: null };
  for (const f of frames) readCliDelta(f, { onToken: t => seen.push(t) }, state);
  return { seen, driverError: state.driverError };
};
const plain = run([frame('hello '), frame('world')]);
const errd  = run([frame('partial '), frame('\\n\\u26a0 Codex error: exited 127', 'error')]);
const two   = run([frame('\\u26a0 first fault', 'error'), frame('\\u26a0 second fault', 'error')]);
console.log(JSON.stringify({
  plainTokens: plain.seen.join(''),
  plainError: plain.driverError,
  errdTokens: errd.seen.join(''),
  errdError: errd.driverError,
  firstWins: two.driverError,
}));
"""
    tmp = tempfile.mkdtemp(prefix='clidelta-')
    r = {}
    try:
        p = os.path.join(tmp, 'c.mjs')
        with open(p, 'w') as fh:
            fh.write(harness)
        proc = subprocess.run([shutil.which('node') or 'node', p],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            print("  FAIL node harness errored: " + proc.stderr.strip()[:300])
            failures.append("node harness")
        else:
            r = json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if r:
        check("ordinary tokens still stream through", r.get('plainTokens') == 'hello world')
        check("...and report no driver error", r.get('plainError') is None)
        check("an error frame's text STILL reaches the screen",
              'exited 127' in (r.get('errdTokens') or ''), repr(r.get('errdTokens')))
        check("...and the partial output before it is not lost",
              (r.get('errdTokens') or '').startswith('partial '))
        check("...and the failure is carried back to the caller",
              'exited 127' in (r.get('errdError') or ''), repr(r.get('errdError')))
        check("the first fault wins (a dying driver repeats itself)",
              r.get('firstWins') == '⚠ first fault', repr(r.get('firstWins')))

    # ---- 3. the run reports it, and the card believes it ------------------
    print("3. the failure outranks 'did it produce text?'")
    app = strip_js_comments(read('app.jsx'))
    m = re.search(r"const shortfall = (.{0,300}?);", app, re.S)
    check("the shortfall decision was found", m is not None)
    if m:
        expr = ' '.join(m.group(1).split())
        check("driverError is consulted", 'driverError' in expr, expr[:150])
        check("...BEFORE hasSubstance -- an error banner IS substance",
              'driverError' in expr
              and expr.index('driverError') < expr.index('hasSubstance'), expr[:150])

    runtime = strip_js_comments(read('hq-runtime.jsx'))
    check("agentStream returns the driver error to its caller",
          re.search(r'return \{\s*driverError:', runtime) is not None)

    floor = strip_js_comments(read('app/floor.jsx'))
    check("shortfallLine has a distinct line for a driver that never started",
          "kind === 'error'" in floor)
    check("...and it does not reuse the 'came back with nothing' wording, "
          "which blames the coworker for the machine",
          re.search(r"kind === 'error'[\s\S]{0,220}?could not start", floor) is not None)

    print()
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures[:6]))
        return 1
    print("PASS: a driver that never started is not a finished job")
    return 0


if __name__ == '__main__':
    sys.exit(main())
