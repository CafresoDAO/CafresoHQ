#!/usr/bin/env python3
"""An upstream failure arrived as a finished turn with nothing in it.

Every LLM stream in this app opens with a 200 and then fails LATER, in-band,
if it fails at all — that is what SSE is for. Both non-Google readers dropped
those frames on the floor.

  streamAnthropic.  The Messages API ends a broken stream with

      event: error
      data: {"type":"error","error":{"type":"overloaded_error",
             "message":"Overloaded"}}

  and this reader's chain is `content_block_delta` / `message_start` /
  `message_delta`. `error` matched none of them, JSON.parse succeeded, the
  whole `try` fell through, and the frame was gone. On an overload BEFORE the
  first text delta — the common case, since that is when the model is picked
  up — the turn produced zero tokens and threw nothing.

  streamOpenAICompat (LM Studio, Ollama, Hermes, and anything OpenAI-shaped
  behind them).  Same hole, three wire spellings:

      {"error":{"message":"upstream connect error","type":"server_error"}}   OpenAI, vLLM
      {"error":{"message":"Failed to load model","code":"model_not_found"}}  LM Studio
      {"error":"model requires more system memory than is available"}        Ollama

  The reader asks for `j.choices[0].delta` and `j.usage` only. No `choices`,
  no match, dropped.

And parseSSE cannot rescue either one: its own guard fires when a stream sends
NO data at all, and an error frame IS data. So `sawData` was true, parseSSE
returned normally, the caller's await resolved, and the office recorded a
completed turn — an empty bubble on a total failure, a sentence that stops
mid-thought on a partial one, and in both cases no cause anywhere on screen.
This is the shape the CLI drivers were already fixed for (`readCliDelta`'s
`delta.type === 'error'`, `streamAgentContract`'s `⚠ ${label}`); the two
readers a boss's own API key goes through were the ones still missing it.

What must be true now: an error frame with no text before it FAILS the turn
and names the cause; an error frame after some text keeps the text and marks
where it stopped; a clean stream is untouched.

Run: python3 scripts/test_a_stream_that_dies_after_the_200_is_not_an_answer.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / 'claude-client.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, header):
    """`header` plus its balanced `{ … }` body, verbatim from the file."""
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d, k = 0, j
    while k < len(src):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                break
        k += 1
    return src[i:k + 1]


def run_js(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-2000:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


HARNESS = r'''
/* Stand-ins for the module scope the two readers close over. Nothing here
   is under test; the two functions below are lifted verbatim. */
const _settings = { anthropicKey: 'sk-test', anthropicModel: 'claude-x',
                    maxTokens: 256, lmstudioUrl: 'http://127.0.0.1:1234/v1' };
function normalizeMessages(m) { return m; }
function headTimeoutMs() { return 1000; }
function fetchStreamHead() { return Promise.resolve(globalThis.__RES()); }

function sseResponse(text) {
  const bytes = new TextEncoder().encode(text);
  let sent = false;
  return {
    ok: true, status: 200,
    headers: { get: (k) => (k.toLowerCase() === 'content-type'
                            ? 'text/event-stream' : null) },
    body: { getReader: () => ({
      read: async () => (sent ? { done: true }
                              : (sent = true, { done: false, value: bytes })),
    }) },
  };
}

async function drive(fn, wire) {
  globalThis.__RES = () => sseResponse(wire);
  const tokens = [];
  const usage = [];
  let threw = null;
  try {
    await fn({
      system: 's', messages: [{ role: 'user', content: 'hi' }],
      model: 'm', maxTokens: 64,
      onToken: (t) => tokens.push(t),
      onUsage: (u) => usage.push(u),
    });
  } catch (e) { threw = String((e && e.message) || e); }
  const text = tokens.join('');
  return { text, threw, usage, warned: text.indexOf('⚠') >= 0 };
}
'''

# ── the wires, as the four backends actually spell them ──────────────────
ANTHROPIC_START = (
    'event: message_start\n'
    'data: {"type":"message_start","message":{"usage":{"input_tokens":11}}}\n\n')
ANTHROPIC_TEXT = (
    'event: content_block_delta\n'
    'data: {"type":"content_block_delta","delta":{"type":"text_delta",'
    '"text":"The answer is "}}\n\n')
ANTHROPIC_ERR = (
    'event: error\n'
    'data: {"type":"error","error":{"type":"overloaded_error",'
    '"message":"Overloaded"}}\n\n')
ANTHROPIC_OK_END = (
    'event: content_block_delta\n'
    'data: {"type":"content_block_delta","delta":{"type":"text_delta",'
    '"text":"42."}}\n\n'
    'event: message_delta\n'
    'data: {"type":"message_delta","usage":{"output_tokens":7}}\n\n'
    'event: message_stop\ndata: {"type":"message_stop"}\n\n')

OAI_TEXT = ('data: {"choices":[{"delta":{"content":"Here is the plan: "}}]}\n\n')
OAI_ERR = ('data: {"error":{"message":"upstream connect error or '
           'disconnect/reset before headers","type":"server_error"}}\n\n')
OLLAMA_ERR = ('data: {"error":"model requires more system memory (5.6 GiB) '
              'than is available (4.1 GiB)"}\n\n')
OAI_OK = ('data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
          'data: {"choices":[{"delta":{"content":" there"}}]}\n\n'
          'data: {"usage":{"prompt_tokens":9,"completion_tokens":3,'
          '"total_tokens":12}}\n\n'
          'data: [DONE]\n\n')
OAI_REASONING_ONLY = (
    'data: {"choices":[{"delta":{"reasoning_content":"Let me think..."}}]}\n\n'
    'data: [DONE]\n\n')


def main():
    print('a stream that dies after the 200 is not an answer')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = CLIENT.read_text(encoding='utf-8')
    ANTHROPIC_SIG = ('async function streamAnthropic({ system, messages, model, '
                     'temperature, maxTokens, onToken, onUsage, signal }) {')
    COMPAT_SIG = ('async function streamOpenAICompat({ base, label, system, '
                  'messages, model, temperature, maxTokens, onToken, onReasoning, '
                  'onUsage, signal, defaultModel, apiKey, requireKey, extraHeaders, '
                  'noStreamOptions, local }) {')
    for sig in (ANTHROPIC_SIG, COMPAT_SIG):
        if sig not in src:
            raise SystemExit('signature moved; re-anchor the lift:\n  ' + sig)
    # Nothing but parseSSE is pulled in alongside them: the error read is
    # INLINE in both readers on purpose (#258's rule), because a lift like
    # this one runs them in a bare scope where a module-level callee would be
    # a ReferenceError — swallowed by the same `catch (_e) {}` under test.
    scope = '\n'.join([
        brace_lift(src, 'async function parseSSE(res, onLine) {'),
        brace_lift(src, ANTHROPIC_SIG),
        brace_lift(src, COMPAT_SIG),
        HARNESS,
    ])

    def case(fn, wire):
        return run_js(scope + '\nconsole.log(JSON.stringify(await drive(%s, %s)));'
                      % (fn, json.dumps(wire)))

    def compat(wire):
        return case("(o) => streamOpenAICompat({ ...o, base: 'http://x/v1', "
                    "label: 'LM Studio', defaultModel: 'local' })", wire)

    # ── 1. Anthropic, overloaded before it said anything ─────────────────
    dead = case('streamAnthropic', ANTHROPIC_START + ANTHROPIC_ERR)
    check('an Anthropic stream that only ever errored fails the turn',
          dead['threw'] is not None,
          f'{dead} — it resolved. The caller awaits this and files the turn '
          'as done; an overload became an empty finished reply.')
    check('...and the failure says what the API said',
          dead['threw'] and 'Overloaded' in dead['threw'], dead['threw'])
    check('...and names the provider that failed',
          dead['threw'] and 'Anthropic' in dead['threw'], dead['threw'])
    check('...and does not pass the error off as the reply text',
          dead['text'] == '',
          f'{dead["text"]!r} — an error is not an answer')

    # ── 2. Anthropic, cut off mid-sentence ───────────────────────────────
    part = case('streamAnthropic', ANTHROPIC_START + ANTHROPIC_TEXT + ANTHROPIC_ERR)
    check('a cut-off Anthropic reply keeps the words that did arrive',
          'The answer is ' in part['text'], part)
    check('...and says on screen that it stops there', part['warned'],
          f'{part} — "The answer is " with nothing after it and no mark is a '
          'sentence the boss will read as finished')
    check('...and does not also throw, which would discard the text',
          part['threw'] is None, part['threw'])

    # ── 3. Anthropic, a clean stream is untouched ────────────────────────
    good = case('streamAnthropic', ANTHROPIC_START + ANTHROPIC_TEXT + ANTHROPIC_OK_END)
    check('a healthy Anthropic stream still just works',
          good['threw'] is None and good['text'] == 'The answer is 42.', good)
    check('...with no warning bolted onto a good reply', not good['warned'], good)
    check('...and usage reported exactly once', len(good['usage']) == 1
          and good['usage'][0]['input'] == 11 and good['usage'][0]['output'] == 7,
          good['usage'])

    # ── 4. OpenAI-compatible, the same three shapes ──────────────────────
    oai_dead = compat(OAI_ERR)
    check('an OpenAI-shaped error frame fails the turn',
          oai_dead['threw'] is not None,
          f'{oai_dead} — no `choices` key, so the reader skipped it entirely')
    check('...and carries the upstream message',
          oai_dead['threw'] and 'upstream connect error' in oai_dead['threw'],
          oai_dead['threw'])
    check('...and names the backend, not "something went wrong"',
          oai_dead['threw'] and 'LM Studio' in oai_dead['threw'],
          oai_dead['threw'])

    oll = compat(OLLAMA_ERR)
    check('Ollama’s bare-string error is read too', oll['threw'] is not None, oll)
    check('...and keeps the reason a boss can act on',
          oll['threw'] and 'system memory' in oll['threw'], oll['threw'])

    oai_part = compat(OAI_TEXT + OAI_ERR)
    check('a truncated OpenAI-shaped reply keeps its text',
          'Here is the plan: ' in oai_part['text'], oai_part)
    check('...and is marked as stopping short', oai_part['warned'], oai_part)
    check('...without throwing away what arrived',
          oai_part['threw'] is None, oai_part['threw'])

    # ── 5. the regressions this must not cause ───────────────────────────
    oai_good = compat(OAI_OK)
    check('a healthy OpenAI-compatible stream is unchanged',
          oai_good['threw'] is None and oai_good['text'] == 'Hello there',
          oai_good)
    check('...and its usage still lands', len(oai_good['usage']) == 1
          and oai_good['usage'][0]['total'] == 12, oai_good['usage'])
    check('...and [DONE] is not mistaken for a failure',
          not oai_good['warned'], oai_good)

    think = compat(OAI_REASONING_ONLY)
    check('the all-monologue-no-answer line still fires',
          think['threw'] is None and 'ran out of room' in think['text'],
          f'{think} — the error check sits in front of it and must not '
          'swallow the case it was written for')

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
