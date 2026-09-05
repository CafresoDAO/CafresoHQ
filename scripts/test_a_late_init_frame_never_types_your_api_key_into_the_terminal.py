#!/usr/bin/env python3
"""A late `init` frame typed the user's API keys into the running CLI.

views/terminal.jsx sends ONE JSON frame the instant the PTY WebSocket
opens:

    ws.onopen = async () => {
      ak = await oc.getAgentKey('anthropic')...   // three vault lookups
      ws.send(JSON.stringify({ type: 'init', anthropic_key: ak, ... }));
    }

pty_server.py's _terminal_pty_ws reads that frame BEFORE spawning the
PTY, under a hard `client_sock.settimeout(2.0)`, so it can seed
ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY into the child's
env. Two seconds is a guess about how long three awaited
CafresoHQClient.getAgentKey() calls take — a cold ICP bridge or a vault
that has to be unlocked blows straight through it.

When it does, the frame is not lost: it arrives a moment later, in the
ordinary keystroke loop (ws_to_pty). That loop used to json.loads() the
payload, check only for `type == 'resize'`, and — finding something
else — fall through to `os.write(master_fd, payload)`. The frame is the
keystrokes. So the whole JSON blob, plaintext API keys and all, was
typed into the interactive CLI: echoed on screen in the terminal pane,
left in the agent's scrollback, and (for a shell-ish CLI) captured in
history. A secret the office went to the trouble of encrypting in the
vault ends up on screen because a lookup was slow.

Fix: a single `_pty_control_frame()` classifier, shared by both the
Windows and POSIX ws_to_pty loops, recognises 'init' as a control frame
alongside 'resize'. Control frames are acted on and then swallowed —
never forwarded to the PTY. The keys themselves can't be applied
retroactively (the child's env was fixed at spawn), so a late init is
simply dropped.

Found by a background hunt agent sweeping pty_server.py.

Run: python3 scripts/test_a_late_init_frame_never_types_your_api_key_into_the_terminal.py
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PTY_SERVER = ROOT / 'pty_server.py'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def _load():
    spec = importlib.util.spec_from_file_location('_pty_server_under_test',
                                                  PTY_SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    print('A late init frame never types your API key into the terminal')

    src = PTY_SERVER.read_text(encoding='utf-8')
    mod = _load()

    classify = getattr(mod, '_pty_control_frame', None)
    check('pty_server exposes a shared control-frame classifier '
          '(_pty_control_frame)', callable(classify),
          'no such module-level function')
    if not callable(classify):
        print()
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1

    # ── The bug itself ────────────────────────────────────────────────
    SECRET = 'sk-ant-DO-NOT-TYPE-ME-0123456789'
    init = json.dumps({'type': 'init', 'anthropic_key': SECRET,
                       'openai_key': 'sk-openai-secret',
                       'gemini_key': 'AIza-secret'}).encode()
    got = classify(init)
    check('an init frame is recognised as a control frame, so the '
          'keystroke loop swallows it instead of writing it to the PTY',
          isinstance(got, dict) and got.get('type') == 'init',
          f'classifier returned {got!r} — the payload would be os.write()n '
          f'to the PTY, typing {SECRET} into the CLI')

    # A bare init with no keys (the common case — the browser always sends
    # the frame) must be dropped too: otherwise `{"type":"init"}` is typed
    # into the CLI prompt as literal text.
    check('a keyless init frame is dropped as well (the browser sends the '
          'frame unconditionally)',
          isinstance(classify(b'{"type":"init"}'), dict))

    # ── Regressions the fix must not cause ────────────────────────────
    resize = classify(json.dumps({'type': 'resize', 'cols': 90,
                                  'rows': 24}).encode())
    check('resize is still a control frame', isinstance(resize, dict)
          and resize.get('type') == 'resize' and resize.get('cols') == 90)

    check('ordinary keystrokes are NOT control frames (they still reach '
          'the PTY)', classify(b'ls -la\r') is None)
    check('a bare number typed at the prompt is not mistaken for a control '
          'frame (json.loads("42") succeeds and returns an int)',
          classify(b'42') is None)
    check('a JSON object with some other type is not a control frame',
          classify(b'{"type":"hello"}') is None)
    check('a JSON array is not a control frame', classify(b'[1,2,3]') is None)
    check('invalid UTF-8 keystrokes do not raise', classify(b'\xff\xfe') is None)

    # ── Both platform loops must route through it ─────────────────────
    posix = re.search(r"msg = _pty_control_frame\(payload\)\n"
                      r"(?:.*?)os\.write\(sess\['master_fd'\], payload\)",
                      src, re.S)
    check('the POSIX ws_to_pty loop classifies via _pty_control_frame '
          'before its os.write() fallthrough', posix is not None)
    win = re.search(r"msg = _pty_control_frame\(payload\)\n"
                    r"(?:.*?)sess\['pty_proc'\]\.write\(payload\.decode",
                    src, re.S)
    check('the Windows ws_to_pty loop does too (pywinpty path)',
          win is not None)
    check('a recognised control frame always `continue`s — it can never '
          'fall through to the PTY write',
          src.count("if msg is not None:") == 2
          and len(re.findall(r"if msg is not None:.*?\n\s+continue\n", src,
                             re.S)) == 2)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


sys.exit(main())
