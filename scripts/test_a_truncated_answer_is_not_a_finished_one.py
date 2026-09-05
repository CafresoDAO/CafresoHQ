#!/usr/bin/env python3
"""A severed answer arrived byte-identical to a finished one.

`## 402` left `claude-client.jsx` EXPOSED with 45 empty catches — the largest
concentration in the client, and the funnel every browser sender goes through
(`hq-runtime.jsx:4247`, `hq-runtime.jsx:4527`, `views/terminal.jsx:523`,
`agent_runner.jsx:93` all reach the model through `CafresoHQClient.stream()`).
The worst shape in that file was not a swallowed exception at all. It was a
failure that is not spelled as one anywhere on the wire.

Every provider ends a stream by SAYING WHY it stopped, and no reader looked:

    OpenAI-compatible   choices[0].finish_reason === "length"    (LM Studio,
                        Ollama, Hermes, anything OpenAI-shaped behind them)
    Anthropic           message_delta.delta.stop_reason === "max_tokens"
    Google              candidates[0].finishReason === "MAX_TOKENS"

A truncated stream closes as cleanly as a finished one: 200, data frames,
clean EOF. `parseSSE` saw data, so it raised nothing. No `error` frame, so
`## 397`'s streamError read found nothing. The turn resolved, the office
recorded a completed answer, and the boss read a plan that stops mid-step
with NOTHING on screen to say it was cut. Measured before the fix, on the
real lifted bodies, a complete answer and a truncated one:

    complete   {"text": "Deploy with dfx deploy.", "threw": null, "warned": false}
    TRUNCATED  {"text": "Deploy with dfx deploy.", "threw": null, "warned": false}
    identical=True     ← on all three readers

This is not exotic. `DEFAULTS.maxTokens` is 1024 output tokens and
`agent_runner.jsx:88` pins exactly that, so hitting the ceiling is routine.

Google carries a second spelling of the same shape: `finishReason` is also
how a refusal arrives — `SAFETY`, `RECITATION`, `PROHIBITED_CONTENT` come
back as a clean 200 with an EMPTY candidate and no error frame. Measured:
`{"text": "", "threw": null, "warned": false}` — an empty bubble on a
refusal, `## 395`'s Library-graph shape.

What must be true now: a stream that hit the ceiling with text keeps the text
AND is marked incomplete; one that hit it with nothing FAILS the turn; a real
upstream error still outranks the ceiling (a cause beats a guess); a
monologue-only stream keeps `## 397`'s own line rather than gaining a second;
Google's refusals are heard; and a CLEAN stream is byte-for-byte untouched.

Run: python3 scripts/test_a_truncated_answer_is_not_a_finished_one.py
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
/* Stand-ins for the module scope the three readers close over. Nothing here
   is under test; the three functions are lifted verbatim from the file. */
const _settings = { anthropicKey: 'sk-test', anthropicModel: 'claude-x',
                    googleKey: 'g-test', googleModel: 'gemini-x',
                    maxTokens: 64, lmstudioUrl: 'http://127.0.0.1:1234/v1' };
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
      onReasoning: () => {},
      onUsage: (u) => usage.push(u),
    });
  } catch (e) { threw = String((e && e.message) || e); }
  const text = tokens.join('');
  return { text, threw, usage,
           cut: text.indexOf('cut off at the length limit') >= 0,
           warned: text.indexOf('⚠') >= 0 };
}
'''

BODY = 'Deploy with dfx deploy, then'

# ── OpenAI-compatible: LM Studio / Ollama / Hermes ───────────────────────
OAI_TEXT = ('data: {"choices":[{"delta":{"content":"%s"},"finish_reason":null}]}\n\n' % BODY)
OAI_STOP = ('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            'data: [DONE]\n\n')
OAI_LENGTH = ('data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'
              'data: [DONE]\n\n')
# Some backends stamp finish_reason onto the LAST CONTENT frame rather than a
# trailing empty one; both spellings must land.
OAI_LENGTH_INLINE = ('data: {"choices":[{"delta":{"content":"%s"},'
                     '"finish_reason":"length"}]}\n\n'
                     'data: [DONE]\n\n' % BODY)
OAI_ERR = ('data: {"error":{"message":"upstream connect error","type":"server_error"}}\n\n')
OAI_REASONING_ONLY = (
    'data: {"choices":[{"delta":{"reasoning_content":"Let me think..."},'
    '"finish_reason":null}]}\n\n'
    'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'
    'data: [DONE]\n\n')

# ── Anthropic ────────────────────────────────────────────────────────────
ANT_TEXT = ('event: content_block_delta\n'
            'data: {"type":"content_block_delta","delta":{"type":"text_delta",'
            '"text":"%s"}}\n\n' % BODY)


def ant_end(stop):
    return ('event: message_delta\n'
            'data: {"type":"message_delta","delta":{"stop_reason":"%s"},'
            '"usage":{"output_tokens":64}}\n\n'
            'event: message_stop\ndata: {"type":"message_stop"}\n\n' % stop)


ANT_ERR = ('event: error\ndata: {"type":"error","error":'
           '{"type":"overloaded_error","message":"Overloaded"}}\n\n')

# ── Google ───────────────────────────────────────────────────────────────
def gem(text, reason):
    parts = ('"content":{"parts":[{"text":"%s"}]},' % text) if text else ''
    return ('data: {"candidates":[{%s"finishReason":"%s"}]}\n\n' % (parts, reason))


def main():
    print('a truncated answer is not a finished one')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = CLIENT.read_text(encoding='utf-8')

    # ── structural: the three reads exist, each INLINE in its own reader ──
    ANT_SIG = ('async function streamAnthropic({ system, messages, model, '
               'temperature, maxTokens, onToken, onUsage, signal }) {')
    COMPAT_SIG = ('async function streamOpenAICompat({ base, label, system, '
                  'messages, model, temperature, maxTokens, onToken, onReasoning, '
                  'onUsage, signal, defaultModel, apiKey, requireKey, extraHeaders, '
                  'noStreamOptions, local }) {')
    GOOG_SIG = ('async function streamGoogle({ system, messages, model, '
                'temperature, maxTokens, onToken, onUsage, signal }) {')
    for sig in (ANT_SIG, COMPAT_SIG, GOOG_SIG):
        if sig not in src:
            raise SystemExit('signature moved; re-anchor the lift:\n  ' + sig)

    ant_body = brace_lift(src, ANT_SIG)
    compat_body = brace_lift(src, COMPAT_SIG)
    goog_body = brace_lift(src, GOOG_SIG)

    check("the Anthropic reader reads stop_reason",
          "stop_reason === 'max_tokens'" in ant_body)
    check("the OpenAI-compatible reader reads finish_reason",
          "finish_reason === 'length'" in compat_body)
    check("the Google reader reads finishReason",
          '.finishReason' in goog_body and "finish !== 'STOP'" in goog_body)
    # #258's rule: these tests lift the readers into a bare scope, so a
    # module-level helper would be a ReferenceError swallowed by catch(_e){}.
    check("no shared truncation helper was introduced",
          'function _truncationNote' not in src and 'TRUNCATION_NOTE' not in src)
    # Anthropic's stop_reason rides the SAME frame as usage, and that arm of
    # the else-if chain is keyed on j.usage — so the read must sit outside it.
    ant_chain = ant_body[ant_body.index("if (event === 'content_block_delta'"):]
    check("the Anthropic stop_reason read is outside the else-if chain",
          "stop_reason === 'max_tokens'" not in ant_chain)
    for name, body in (('Anthropic', ant_body), ('OpenAI-compatible', compat_body)):
        i = body.index('streamError')
        check("%s: the ceiling is ranked below a real upstream error" % name,
              body.rindex('truncated') > i)

    scope = '\n'.join([
        brace_lift(src, 'async function parseSSE(res, onLine) {'),
        ant_body, compat_body, goog_body, HARNESS,
    ])

    def case(fn, wire):
        return run_js(scope + '\nconsole.log(JSON.stringify(await drive(%s, %s)));'
                      % (fn, json.dumps(wire)))

    def compat(wire):
        return case("(o) => streamOpenAICompat({ ...o, base: 'http://x/v1', "
                    "label: 'LM Studio', defaultModel: 'local' })", wire)

    # ── 1. OpenAI-compatible: the funnel every browser sender goes through ─
    ok = compat(OAI_TEXT + OAI_STOP)
    cut = compat(OAI_TEXT + OAI_LENGTH)
    print('    clean     ', json.dumps(ok))
    print('    truncated ', json.dumps(cut))
    check("compat: a clean stream is untouched",
          ok['text'] == BODY and ok['threw'] is None and not ok['warned'], ok)
    check("compat: a truncated stream KEEPS the text", cut['text'].startswith(BODY), cut)
    check("compat: a truncated stream is MARKED", cut['cut'] and cut['warned'], cut)
    check("compat: a truncated stream no longer reads as a finished one",
          cut['text'] != ok['text'], (ok, cut))
    check("compat: marking it does not fail the turn", cut['threw'] is None, cut)

    inline = compat(OAI_LENGTH_INLINE)
    check("compat: finish_reason on the last CONTENT frame lands too",
          inline['cut'] and inline['text'].startswith(BODY), inline)

    dead = compat(OAI_LENGTH)          # ceiling hit with nothing said at all
    check("compat: cut off before it said anything FAILS the turn",
          dead['threw'] is not None and 'length limit' in dead['threw'], dead)
    check("compat: that failure names the backend", 'LM Studio' in (dead['threw'] or ''), dead)

    both = compat(OAI_TEXT + OAI_ERR + OAI_LENGTH)
    check("compat: a real upstream error outranks the ceiling",
          'upstream connect error' in both['text'] and not both['cut'], both)

    think = compat(OAI_REASONING_ONLY)
    check("compat: a monologue-only stream keeps #397's own line, not two",
          'ran out of room' in think['text'] and not think['cut']
          and think['threw'] is None, think)

    # ── 2. Anthropic ──────────────────────────────────────────────────────
    a_ok = case('streamAnthropic', ANT_TEXT + ant_end('end_turn'))
    a_cut = case('streamAnthropic', ANT_TEXT + ant_end('max_tokens'))
    print('    clean     ', json.dumps(a_ok))
    print('    truncated ', json.dumps(a_cut))
    check("anthropic: a clean stream is untouched",
          a_ok['text'] == BODY and not a_ok['warned'] and a_ok['threw'] is None, a_ok)
    check("anthropic: a truncated stream keeps the text and is MARKED",
          a_cut['text'].startswith(BODY) and a_cut['cut'], a_cut)
    check("anthropic: usage is still reported once on a truncated turn",
          len(a_cut['usage']) == 1, a_cut)
    a_dead = case('streamAnthropic', ant_end('max_tokens'))
    check("anthropic: cut off before it said anything FAILS the turn",
          a_dead['threw'] is not None and 'length limit' in a_dead['threw'], a_dead)
    a_both = case('streamAnthropic', ANT_TEXT + ANT_ERR + ant_end('max_tokens'))
    check("anthropic: a real upstream error outranks the ceiling",
          'Overloaded' in a_both['text'] and not a_both['cut'], a_both)

    # ── 3. Google: the ceiling AND the refusals ───────────────────────────
    g_ok = case('streamGoogle', gem(BODY, 'STOP'))
    g_cut = case('streamGoogle', gem(BODY, 'MAX_TOKENS'))
    print('    clean     ', json.dumps(g_ok))
    print('    truncated ', json.dumps(g_cut))
    check("google: a clean stream is untouched",
          g_ok['text'] == BODY and not g_ok['warned'] and g_ok['threw'] is None, g_ok)
    check("google: a truncated stream keeps the text and is MARKED",
          g_cut['text'].startswith(BODY) and g_cut['cut'], g_cut)
    g_safe = case('streamGoogle', gem('', 'SAFETY'))
    check("google: an empty safety-blocked candidate FAILS the turn",
          g_safe['threw'] is not None and 'SAFETY' in g_safe['threw'], g_safe)
    check("google: it is no longer an empty bubble",
          g_safe['text'] == '' and g_safe['threw'] is not None, g_safe)
    g_part = case('streamGoogle', gem(BODY, 'RECITATION'))
    check("google: a partial answer stopped early keeps the text and is marked",
          g_part['text'].startswith(BODY) and g_part['warned']
          and 'RECITATION' in g_part['text'], g_part)

    print()
    if FAILS:
        print('%d check(s) FAILED:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
