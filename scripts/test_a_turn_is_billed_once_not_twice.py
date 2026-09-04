#!/usr/bin/env python3
"""A streamed turn's token usage must be reported exactly once (claude-client.jsx).

Bug: the stream() contract is that onUsage fires ONCE per stream with the
turn's totals — that is what streamOpenAICompat, readCliDelta and
streamAgentContract all do, and it is what the accumulating consumer relies
on: app.jsx's `onCeoUsage = (u) => setCeoTokens(t => t + (u.total || 0))`
ADDS every report it receives. Two providers broke the contract:

  - streamAnthropic fired onUsage at the `message_stop` SSE event AND again
    after parseSSE returned, with identical totals — every Anthropic CEO
    turn was billed at exactly double.
  - streamGoogle fired onUsage on EVERY streamed chunk carrying
    `usageMetadata` (Gemini stamps chunks with CUMULATIVE counts) and once
    more at the end — a turn's recorded spend grew with the chunk count.

Fix: both providers record usage as it streams and report it once, after
the stream ends.

This lifts the REAL streamAnthropic and streamGoogle out of
claude-client.jsx (brace-balanced extraction, like the app/*.jsx node
suites), stubs fetchStreamHead/parseSSE to replay a recorded event
sequence, and counts onUsage calls the way onCeoUsage counts tokens.
Run: python3 scripts/test_a_turn_is_billed_once_not_twice.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'claude-client.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_function(src, name):
    """Brace-balanced extraction of `async function NAME(...) { ... }`."""
    m = re.search(r'(?:async\s+)?function\s+' + re.escape(name) + r'\s*\(', src)
    if not m:
        return None
    # Skip the parameter list first — these functions destructure an options
    # object in their params, so the first '{' after the name is NOT the body.
    pdepth = 1
    k = m.end()
    while k < len(src) and pdepth:
        if src[k] == '(':
            pdepth += 1
        elif src[k] == ')':
            pdepth -= 1
        k += 1
    i = src.find('{', k)
    if i < 0:
        return None
    depth = 0
    j = i
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


HARNESS = r"""
'use strict';
%(anthropic)s
%(google)s

/* ── stubs for the module context the lifted functions close over ────── */
const _settings = {
  anthropicKey: 'k', anthropicModel: 'claude-test', maxTokens: 64,
  googleKey: 'k', googleModel: 'gemini-test',
};
function normalizeMessages(msgs) { return msgs; }
let EVENTS = [];
async function fetchStreamHead(_url, _init) { return { ok: true }; }
async function parseSSE(_res, onLine) {
  for (const [ev, data] of EVENTS) onLine(ev, data);
}

/* ── the accumulating consumer, verbatim in spirit from app.jsx:
      onCeoUsage = (u) => setCeoTokens(t => t + (u.total || 0)) ───────── */
async function run() {
  const out = {};

  // Anthropic: usual event order — message_start carries input tokens,
  // message_delta the running output count, message_stop closes the turn.
  EVENTS = [
    ['message_start', JSON.stringify({ message: { usage: { input_tokens: 10 } } })],
    ['content_block_delta', JSON.stringify({ delta: { type: 'text_delta', text: 'hi' } })],
    ['message_delta', JSON.stringify({ usage: { output_tokens: 5 } })],
    ['message_stop', JSON.stringify({})],
  ];
  let aCalls = 0, aBilled = 0, aLast = null;
  await streamAnthropic({
    messages: [{ role: 'user', content: 'q' }],
    onToken: () => {},
    onUsage: (u) => { aCalls++; aBilled += (u.total || 0); aLast = u; },
  });
  out.anthropic = { calls: aCalls, billed: aBilled, last: aLast };

  // Google: Gemini stamps streamed chunks with CUMULATIVE usageMetadata.
  EVENTS = [
    ['message', JSON.stringify({ candidates: [{ content: { parts: [{ text: 'a' }] } }],
                                 usageMetadata: { promptTokenCount: 10, candidatesTokenCount: 2 } })],
    ['message', JSON.stringify({ candidates: [{ content: { parts: [{ text: 'b' }] } }],
                                 usageMetadata: { promptTokenCount: 10, candidatesTokenCount: 5 } })],
    ['message', JSON.stringify({ candidates: [{ content: { parts: [{ text: 'c' }] } }],
                                 usageMetadata: { promptTokenCount: 10, candidatesTokenCount: 9 } })],
  ];
  let gCalls = 0, gBilled = 0, gLast = null;
  await streamGoogle({
    messages: [{ role: 'user', content: 'q' }],
    onToken: () => {},
    onUsage: (u) => { gCalls++; gBilled += (u.total || 0); gLast = u; },
  });
  out.google = { calls: gCalls, billed: gBilled, last: gLast };

  console.log(JSON.stringify(out));
}
run().catch((e) => { console.error(e && e.stack || e); process.exit(2); });
"""


def main():
    print('claude-client — a streamed turn is billed once, not per report')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    fa = extract_function(text, 'streamAnthropic')
    fg = extract_function(text, 'streamGoogle')
    check('streamAnthropic extracted from claude-client.jsx', fa is not None)
    check('streamGoogle extracted from claude-client.jsx', fg is not None)
    if not (fa and fg):
        print('\nFAILED: %s' % FAILS)
        return 1

    js = HARNESS % {'anthropic': fa, 'google': fg}
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          capture_output=True, text=True, cwd=str(ROOT))
    check('harness ran', proc.returncode == 0, (proc.stderr or '')[:400])
    if proc.returncode != 0:
        print('\nFAILED: %s' % FAILS)
        return 1
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    a = out['anthropic']
    check('anthropic: onUsage fired exactly once', a['calls'] == 1,
          f"fired {a['calls']} times")
    check('anthropic: accumulating meter billed the real total (15)',
          a['billed'] == 15, f"billed {a['billed']}")
    check('anthropic: final report carries the turn totals',
          a['last'] == {'input': 10, 'output': 5, 'total': 15}, str(a['last']))

    g = out['google']
    check('google: onUsage fired exactly once', g['calls'] == 1,
          f"fired {g['calls']} times")
    check('google: accumulating meter billed the real total (19)',
          g['billed'] == 19, f"billed {g['billed']}")
    check('google: final report carries the cumulative last chunk',
          g['last'] == {'input': 10, 'output': 9, 'total': 19}, str(g['last']))

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'billed once: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
