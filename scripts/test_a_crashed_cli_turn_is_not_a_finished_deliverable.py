#!/usr/bin/env python3
"""The Claude Code driver certified a turn its own CLI had failed.

`#282` ("a reply that stopped mid-sentence was filed as finished work") fixed
this shape in `drivers/local_http.py`: a stream that opens 200 and fails LATER
must not terminate with a success event, because the host reads the LAST event
as the verdict — `base.run_task_text()` marks "stopped early" only when an
error event was seen, and the office's card goes green above half a sentence.
`drivers/codex.py` and `drivers/gemini_cli.py` say the same thing about the
CLI shape of the same failure: a non-zero exit ends the turn as `ev_error`
whether or not text arrived first.

`drivers/claude_code.py` — the flagship driver, the one the boss meets first —
was the odd one out of the four, on both counts:

    if proc.returncode and not emitted and not (in_tok or out_tok):
        yield ev_error(...)
    else:
        yield ev_done()

  * a CLI that streamed half a paragraph and then died (OOM, killed, a hook
    refusal, a dropped upstream socket) had `emitted` True, so the failure
    took the `else` and terminated with ev_done();
  * usage ALONE excused a non-zero exit even with no text at all, because the
    very first assistant message carries `usage`;
  * `{"type":"error"}` was yielded inline and then followed by ev_done()
    anyway — the exact mirror #282 found in local_http's socket-drop handler;
  * and `{"type":"result"}` — the CLI's own verdict, `subtype`
    'error_max_turns' / 'error_during_execution', `is_error` true — was read
    for its token counts and nothing else.

What must be true now: a non-zero exit, an in-band error frame, and a result
the CLI itself marks failed each end the turn as an error; the text that did
arrive is kept; a clean run is untouched, ev_done and all; and the family rule
holds across every driver that ends a stream.

Run: python3 scripts/test_a_crashed_cli_turn_is_not_a_finished_deliverable.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from drivers.base import DriverError, TaskHandle, run_task_text   # noqa: E402
from drivers.claude_code import ClaudeCodeDriver                  # noqa: E402

failures = []


def msg(ev):
    return str((ev or {}).get('message') or '')


def check(label, cond, detail=''):
    if cond:
        print(f'  ok   {label}')
    else:
        print(f'  FAIL {label}{("  -- " + str(detail)) if detail else ""}')
        failures.append(label)


class FakeProc:
    """Stands in for the Popen the driver stashes on the handle: stdout is an
    iterable of stream-json lines, and returncode is what the CLI exited
    with once the pipe closed."""
    def __init__(self, lines, returncode=0):
        self.stdout = iter(l + '\n' for l in lines)
        self.returncode = returncode
        self.killed = False

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True


def drive(lines, returncode=0, stderr=''):
    drv = ClaudeCodeDriver()
    h = TaskHandle()
    h.proc = FakeProc(lines, returncode)
    h.private['stderr'] = [stderr] if stderr else []
    evs = list(drv.events(h))
    return {
        'events': evs,
        'text': ''.join(e['text'] for e in evs if e['event'] == 'token'),
        'terminal': evs[-1] if evs else None,
        'errors': [e for e in evs if e['event'] == 'error'],
        'usage': [e for e in evs if e['event'] == 'usage'],
    }


def assistant(text, in_tok=None, out_tok=None):
    msg = {'content': [{'type': 'text', 'text': text}]}
    if in_tok is not None:
        msg['usage'] = {'input_tokens': in_tok, 'output_tokens': out_tok}
    return json.dumps({'type': 'assistant', 'message': msg})


INIT = json.dumps({'type': 'system', 'subtype': 'init'})
HALF = assistant('Here is the plan: we start by', 812, 9)
RESULT_OK = json.dumps({'type': 'result', 'subtype': 'success',
                        'result': 'done', 'is_error': False,
                        'usage': {'input_tokens': 812, 'output_tokens': 40}})


class ScriptedDriver(ClaudeCodeDriver):
    """run_task_text() drives start_task/events/cancel; only start_task needs
    replacing so the real events() runs against a scripted process."""
    def __init__(self, lines, returncode=0, stderr=''):
        super().__init__()
        self._lines, self._rc, self._stderr = lines, returncode, stderr

    def start_task(self, task):
        h = TaskHandle()
        h.proc = FakeProc(self._lines, self._rc)
        h.private['stderr'] = [self._stderr] if self._stderr else []
        return h


def strip_comments(src):
    """Source with `#` comments and docstrings removed, so this file's own
    explanation of the bug — which quotes the old `not emitted and not
    (in_tok or out_tok)` spelling verbatim, as does the fix's comment in the
    driver — cannot make correct code read as the bug."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in ('"', "'"):
            q = src[i:i + 3] if src[i:i + 3] in ('"""', "'''") else c
            j = i + len(q)
            while j < n:
                if src[j] == '\\':
                    j += 2
                    continue
                if src[j:j + len(q)] == q:
                    j += len(q)
                    break
                j += 1
            out.append(' ' * (j - i))
            i = j
            continue
        if c == '#':
            j = src.find('\n', i)
            j = n if j < 0 else j
            out.append(' ' * (j - i))
            i = j
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def main():
    print('a crashed CLI turn is not a finished deliverable')

    # ── 1. the dangerous case: text, then the process dies ───────────────
    crash = drive([INIT, HALF], returncode=143,
                  stderr='Killed: out of memory\n')
    check('a crashed turn keeps the words that did arrive',
          crash['text'] == 'Here is the plan: we start by', crash['text'])
    check('a non-zero exit AFTER text does NOT end in ev_done',
          crash['terminal'] and crash['terminal']['event'] == 'error',
          f"{crash['terminal']} -- half a sentence certified as a finished turn")
    check('...and the failure names the exit code and the stderr',
          '143' in msg(crash['terminal'])
          and 'out of memory' in msg(crash['terminal']),
          crash['terminal'])
    check('...and is marked recoverable, since the tokens already stand',
          (crash['terminal'] or {}).get('recoverable') is True,
          crash['terminal'])

    # ── 2. usage alone must not excuse a non-zero exit ───────────────────
    usage_only = drive(
        [INIT, json.dumps({'type': 'assistant', 'message': {
            'content': [{'type': 'tool_use', 'id': 't1', 'name': 'Bash',
                         'input': {'command': 'ls'}}],
            'usage': {'input_tokens': 700, 'output_tokens': 3}}})],
        returncode=1, stderr='Error: spawn ENOENT\n')
    check('a non-zero exit with usage but no text is still an error',
          usage_only['terminal']
          and usage_only['terminal']['event'] == 'error',
          usage_only['terminal'])
    check('...and is NOT marked recoverable, since nothing was said',
          (usage_only['terminal'] or {}).get('recoverable') is False,
          usage_only['terminal'])

    # ── 3. the in-band error frame ───────────────────────────────────────
    inband = drive([INIT, HALF,
                    json.dumps({'type': 'error',
                                'message': 'Credit balance is too low'})],
                   returncode=0)
    check('an in-band error frame ends the turn as an error',
          inband['terminal'] and inband['terminal']['event'] == 'error',
          inband['terminal'])
    check('...naming the cause the CLI actually gave',
          'Credit balance is too low' in msg(inband['terminal']),
          inband['terminal'])
    check('...and exactly once — no ev_done follows it',
          [e['event'] for e in inband['events']].count('done') == 0,
          [e['event'] for e in inband['events']])

    # ── 4. the CLI's own verdict on the result frame ─────────────────────
    for sub in ('error_max_turns', 'error_during_execution'):
        res = drive([INIT, HALF,
                     json.dumps({'type': 'result', 'subtype': sub,
                                 'is_error': True,
                                 'result': 'Reached max turns',
                                 'usage': {'input_tokens': 812,
                                           'output_tokens': 9}})],
                    returncode=0)
        check(f'a result the CLI marks {sub} is not a finished turn',
              res['terminal'] and res['terminal']['event'] == 'error',
              res['terminal'])

    # ── 5. a clean run is untouched ──────────────────────────────────────
    good = drive([INIT, assistant('All done.', 812, 40), RESULT_OK],
                 returncode=0)
    check('a clean run still ends in ev_done',
          good['terminal'] and good['terminal']['event'] == 'done',
          good['terminal'])
    check('...with no error event anywhere in it',
          not good['errors'], good['errors'])
    check('...and its usage still reaches the host',
          good['usage'] and good['usage'][-1]['inTokens'] == 812
          and good['usage'][-1]['outTokens'] == 40, good['usage'])
    check('a clean run keeps its text',
          good['text'] == 'All done.', good['text'])

    # ── 6. what the unattended caller actually receives ──────────────────
    text, usage = run_task_text(ScriptedDriver([INIT, HALF], returncode=143,
                                               stderr='Killed\n'),
                                {'prompt': 'plan it'})
    check('run_task_text MARKS a crashed turn instead of returning it clean',
          'stopped early' in text, text)
    check('...and still keeps the half-answer rather than throwing it away',
          text.startswith('Here is the plan: we start by'), text)
    try:
        run_task_text(ScriptedDriver([INIT], returncode=1, stderr='boom\n'),
                      {'prompt': 'plan it'})
        check('a crash with no text at all raises for the night shift',
              False, 'returned normally')
    except DriverError as e:
        check('a crash with no text at all raises for the night shift',
              '1' in str(e), str(e))
    clean_text, _ = run_task_text(
        ScriptedDriver([INIT, assistant('All done.', 812, 40), RESULT_OK]),
        {'prompt': 'plan it'})
    check('a clean run comes back unmarked',
          clean_text == 'All done.', clean_text)

    # ── 7. the family rule, held on the source ───────────────────────────
    src = strip_comments(open(os.path.join(ROOT, 'drivers', 'claude_code.py'),
                              encoding='utf-8').read())
    check('claude_code.py no longer excuses an exit code with usage',
          'not emitted and not (in_tok or out_tok)' not in src)
    check('claude_code.py latches a failure cause like its siblings',
          re.search(r'^\s*err = ', src, re.M) is not None
          and 'if err:' in src)
    for mod in ('claude_code.py', 'codex.py', 'gemini_cli.py',
                'local_http.py'):
        body = strip_comments(open(os.path.join(ROOT, 'drivers', mod),
                                   encoding='utf-8').read())
        dones = len(re.findall(r'yield ev_done\(', body))
        check(f'{mod} reaches ev_done from exactly one branch',
              dones == 1, dones)

    print(f'\n{"FAILED" if failures else "PASSED"}: '
          f'{len(failures)} failing check(s)')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
