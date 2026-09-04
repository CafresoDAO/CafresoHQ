#!/usr/bin/env python3
"""streamGoogle() dropped every part after the first in a Gemini chunk.

A candidate's `content.parts[]` in Gemini's `streamGenerateContent` response
can carry MORE than one entry in a single SSE chunk — e.g. a code-block part
followed by an explanation part, or (on thinking-capable models like
gemini-2.5-pro / gemini-3.1-pro-preview, which reason by default) a
"thought" part ahead of the real answer part in the same candidate. Before
the fix, `streamGoogle` in `claude-client.jsx` read only
`j.candidates[0].content.parts[0].text` and handed that ALONE to `onToken`
— every part after index 0 was silently dropped from the visible reply.
A chunk shaped like:

    parts: [{ text: 'first ' }, { text: 'second' }]

delivered only "first " to the chat bubble; "second" vanished with no error
and no trace anywhere in the UI. Worse, a `{ thought: true, text: '...' }`
part ahead of the real answer (dynamic-thinking models) meant the FIRST
onToken call showed the model's private reasoning instead of anything the
model actually meant to say.

Fix: concatenate every part that carries `.text` and is not a `thought`
part, and only call onToken with the joined text (skipping the call
entirely when nothing textual is present in that chunk).

This lifts the REAL streamGoogle out of claude-client.jsx (brace-balanced
extraction, matching test_a_turn_is_billed_once_not_twice.py's harness),
stubs fetchStreamHead/parseSSE to replay a recorded multi-part chunk
sequence, and asserts the assembled reply contains every part's text in
order, with thought-only parts excluded.
Run: python3 scripts/test_gemini_multipart_chunk_drops_all_but_first_part.py
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
%(google)s

/* ── stubs for the module context the lifted function closes over ────── */
const _settings = { googleKey: 'k', googleModel: 'gemini-test', maxTokens: 64 };
function normalizeMessages(msgs) { return msgs; }
let EVENTS = [];
async function fetchStreamHead(_url, _init) { return { ok: true }; }
async function parseSSE(_res, onLine) {
  for (const [ev, data] of EVENTS) onLine(ev, data);
}

async function run() {
  const out = {};

  // Chunk 1: two plain-text parts in ONE candidate — a normal, undramatic
  // shape Gemini emits for code-block + explanation responses.
  // Chunk 2: a thought part ahead of the real answer part (dynamic
  // thinking), still bundled in a single chunk.
  EVENTS = [
    ['message', JSON.stringify({ candidates: [{ content: { parts: [
      { text: 'first ' }, { text: 'second' },
    ] } }] })],
    ['message', JSON.stringify({ candidates: [{ content: { parts: [
      { text: 'reasoning about it', thought: true }, { text: ' third' },
    ] } }] })],
  ];

  const tokens = [];
  await streamGoogle({
    messages: [{ role: 'user', content: 'q' }],
    onToken: (t) => tokens.push(t),
    onUsage: () => {},
  });
  out.tokens = tokens;
  out.joined = tokens.join('');

  console.log(JSON.stringify(out));
}
run().catch((e) => { console.error(e && e.stack || e); process.exit(2); });
"""


def main():
    print('claude-client — a Gemini chunk with more than one part is not truncated to parts[0]')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    fg = extract_function(text, 'streamGoogle')
    check('streamGoogle extracted from claude-client.jsx', fg is not None)
    if not fg:
        print('\nFAILED: %s' % FAILS)
        return 1

    js = HARNESS % {'google': fg}
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          capture_output=True, text=True, cwd=str(ROOT))
    check('harness ran', proc.returncode == 0, (proc.stderr or '')[:400])
    if proc.returncode != 0:
        print('\nFAILED: %s' % FAILS)
        return 1
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    joined = out['joined']
    check('first chunk\'s SECOND part ("second") reached onToken',
          'second' in joined, f"joined={joined!r}")
    check('second chunk\'s real answer part (" third") reached onToken',
          ' third' in joined, f"joined={joined!r}")
    check('thought-only text ("reasoning about it") never reached onToken',
          'reasoning about it' not in joined, f"joined={joined!r}")
    check('assembled reply is exactly "first second third"',
          joined == 'first second third', f"joined={joined!r}")

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'multi-part chunks: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
