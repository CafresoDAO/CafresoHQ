#!/usr/bin/env python3
"""The contract-native path certified a reply that stopped mid-sentence.

#258 fixed this in the browser: every OpenAI-compatible backend opens with a
200 and then fails LATER, in-band, so `streamOpenAICompat` learned to read the
three wire spellings of an error frame

    {"error":{"message":"upstream connect error","type":"server_error"}}
    {"error":{"message":"Failed to load model","code":"model_not_found"}}
    {"error":"model requires more system memory than is available"}

The Python driver behind `POST /agent/stream` — the same LM Studio, Ollama,
OpenRouter, Groq and Gemini backends, and the one night_runner runs unattended
— never learned it. `OpenAICompatDriver.events()` asked each chunk for
`choices` and `usage` and nothing else, so an error frame matched no branch and
fell on the floor:

  BEFORE, a stream that died after two tokens ended with
          token "Here is the plan: " … ev_done()
          i.e. the office recorded a finished turn, and the boss read a
          sentence that stops in the middle as the whole answer.
  BEFORE, a stream that only ever errored ended with
          ev_error('provider returned no content')
          which names neither the backend nor the cause — a boss chasing
          "Failed to load model" was told the model said nothing.

The socket-drop handler had the mirror of the same bug: it yielded ev_error
and then fell straight into `if emitted: yield ev_done()`, terminating a
failed stream with a success event.

And base.run_task_text() — night_runner's entry point — only raised when the
text was EMPTY, so the half-answer came back as a clean return value with no
exception and no mark anywhere on it.

What must be true now: an error frame ends the turn as an error naming the
backend and the cause; the text that did arrive is kept and marked where it
stops; a clean stream is untouched, ev_done and all.

Run: python3 scripts/test_a_half_written_reply_is_not_a_finished_turn.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from drivers.base import DriverError, TaskHandle, run_task_text   # noqa: E402
from drivers.local_http import LMStudioDriver, OllamaDriver       # noqa: E402

failures = []


def check(label, cond, detail=''):
    if cond:
        print(f'  ok   {label}')
    else:
        print(f'  FAIL {label}{("  -- " + str(detail)) if detail else ""}')
        failures.append(label)


class FakeResp:
    """Stands in for the urllib response start_task() stashes: an iterable of
    raw SSE lines, plus close(). Optionally raises mid-iteration to model the
    socket dying under a live stream."""
    def __init__(self, wire, blow_up=None):
        self._lines = [(l + '\n').encode('utf-8') for l in wire.split('\n')]
        self._blow_up = blow_up
        self.closed = False

    def __iter__(self):
        for l in self._lines:
            yield l
        if self._blow_up:
            raise self._blow_up
        return

    def close(self):
        self.closed = True


def drive(driver, wire, blow_up=None):
    h = TaskHandle()
    resp = FakeResp(wire, blow_up)
    h.private['resp'] = resp
    evs = list(driver.events(h))
    return {
        'events': evs,
        'text': ''.join(e['text'] for e in evs if e['event'] == 'token'),
        'terminal': evs[-1] if evs else None,
        'errors': [e for e in evs if e['event'] == 'error'],
        'usage': [e for e in evs if e['event'] == 'usage'],
        'closed': resp.closed,
    }


TEXT = 'data: {"choices":[{"delta":{"content":"Here is the plan: "}}]}\n'
OAI_ERR = ('data: {"error":{"message":"upstream connect error or '
           'disconnect/reset before headers","type":"server_error"}}\n')
LMS_ERR = ('data: {"error":{"message":"Failed to load model",'
           '"code":"model_not_found"}}\n')
OLLAMA_ERR = ('data: {"error":"model requires more system memory (5.6 GiB) '
              'than is available (4.1 GiB)"}\n')
CLEAN = ('data: {"choices":[{"delta":{"content":"Hello"}}]}\n'
         'data: {"choices":[{"delta":{"content":" there"}}]}\n'
         'data: {"usage":{"prompt_tokens":9,"completion_tokens":3}}\n'
         'data: [DONE]\n')


def main():
    print('a half-written reply is not a finished turn')
    lms, oll = LMStudioDriver(), OllamaDriver()

    # ── 1. died after some text: the dangerous case ──────────────────────
    part = drive(lms, TEXT + OAI_ERR)
    check('a truncated reply keeps the words that did arrive',
          part['text'] == 'Here is the plan: ', part['text'])
    check('a stream that died in-band does NOT end in ev_done',
          part['terminal'] and part['terminal']['event'] == 'error',
          f"{part['terminal']} -- a half sentence certified as a finished turn")
    check('...and the failure carries the upstream message',
          part['errors'] and 'upstream connect error' in part['errors'][0]['message'],
          part['errors'])
    check('...and names the backend, not "something went wrong"',
          part['errors'] and 'LM Studio' in part['errors'][0]['message'],
          part['errors'])
    check('...and the response is still closed', part['closed'])

    # ── 2. the other two wire spellings ──────────────────────────────────
    lm = drive(lms, TEXT + LMS_ERR)
    check("LM Studio's own error frame is read",
          lm['terminal'] and lm['terminal']['event'] == 'error'
          and 'Failed to load model' in lm['terminal']['message'], lm['terminal'])
    ol = drive(oll, TEXT + OLLAMA_ERR)
    check("Ollama's bare-string error is read too",
          ol['terminal'] and ol['terminal']['event'] == 'error'
          and 'system memory' in ol['terminal']['message'], ol['terminal'])

    # ── 3. errored before saying anything: name the cause ────────────────
    dead = drive(lms, LMS_ERR)
    check('a stream that only ever errored fails the turn',
          dead['terminal'] and dead['terminal']['event'] == 'error', dead['terminal'])
    check('...and says what the backend said, not "no content"',
          dead['terminal'] and 'Failed to load model' in dead['terminal']['message'],
          dead['terminal'])

    # ── 4. the socket dying under a live stream ──────────────────────────
    drop = drive(lms, TEXT, blow_up=TimeoutError('read timed out'))
    check('a dropped socket does not terminate with a success event',
          drop['terminal'] and drop['terminal']['event'] == 'error',
          f"{[e['event'] for e in drop['events']]} -- ev_error then ev_done "
          'means every consumer keyed on the last event sees a clean finish')
    check('...exactly one error event, not an error chased by a done',
          len(drop['errors']) == 1
          and sum(1 for e in drop['events'] if e['event'] == 'done') == 0,
          [e['event'] for e in drop['events']])

    # ── 5. run_task_text: the unattended caller ──────────────────────────
    class _Canned(LMStudioDriver):
        """The real driver with only start_task stubbed: run_task_text then
        runs the genuine events()/cancel() over a canned wire."""
        def __init__(self, wire):
            super().__init__()
            self._wire = wire

        def start_task(self, task):
            h = TaskHandle()
            h.private['resp'] = FakeResp(self._wire)
            return h

    text, usage = run_task_text(_Canned(TEXT + OAI_ERR), {'prompt': 'x'})
    check('an unattended half-answer is not returned as if it were whole',
          '⚠' in text,
          f'{text!r} -- night_runner files this as the finished deliverable')
    check('...and the words that arrived are still in it',
          'Here is the plan:' in text, text)
    check('...and the mark says why it stopped',
          'upstream connect error' in text, text)

    try:
        run_task_text(_Canned(LMS_ERR), {'prompt': 'x'})
        check('an all-error stream still raises to the caller', False,
              'returned instead of raising')
    except DriverError as e:
        check('an all-error stream still raises to the caller', True)
        check('...naming the cause', 'Failed to load model' in str(e), str(e))

    # ── 6. the regressions this must not cause ───────────────────────────
    good = drive(lms, CLEAN)
    check('a healthy stream is unchanged', good['text'] == 'Hello there', good['text'])
    check('...and still ends in ev_done',
          good['terminal'] and good['terminal']['event'] == 'done', good['terminal'])
    check('...with no error bolted onto a good reply', not good['errors'], good['errors'])
    check('...and its usage still lands',
          len(good['usage']) == 1 and good['usage'][0]['inTokens'] == 9
          and good['usage'][0]['outTokens'] == 3, good['usage'])

    ok_text, ok_usage = run_task_text(_Canned(CLEAN), {'prompt': 'x'})
    check('a healthy run_task_text answer carries no warning marker',
          ok_text == 'Hello there' and ok_usage['inTokens'] == 9,
          (ok_text, ok_usage))

    empty = drive(lms, 'data: [DONE]\n')
    check('a silent provider still reports empty, not success',
          empty['terminal'] and empty['terminal']['event'] == 'error'
          and 'no content' in empty['terminal']['message'], empty['terminal'])

    print()
    if failures:
        print('FAILED (%d): %s' % (len(failures), ', '.join(failures)))
        return 1
    print('all good')
    return 0


raise SystemExit(main())
