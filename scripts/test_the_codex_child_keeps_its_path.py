#!/usr/bin/env python3
"""The codex child process must inherit a usable PATH.

drivers/codex.py rebuilds the child's PATH before spawning `codex exec`:
it prepends Git Bash dirs on Windows and drops the self-referential
`\\.codex\\tmp\\arg0` entries codex leaves behind. It found the parent's key
case-insensitively (`path_key`) — correct, since Windows env vars are
case-insensitive — but then wrote the result back to the hardcoded name
`env['Path']` after popping every case variant.

POSIX env vars are case-SENSITIVE. On macOS and Linux that pop-then-write
deleted `PATH` outright and handed codex a child environment whose only
path-ish key was `Path`, which nothing reads. codex itself still launched
(we exec an absolute binary), so the run looked healthy — but every shell
command the agent then ran inside its workspace-write sandbox ("git
status", "npm test", "ls") died with "command not found", and the turn
still ended in DONE. A control that lies about what it did.

Pinned here:
  1. the codex child sees a non-empty PATH under the exact key `PATH`
     on POSIX (the whole bug, checked behaviorally against a stub binary);
  2. the arg0 scrub still happens — the fix must not resurrect the
     self-referential entries;
  3. no stray `Path` key is left behind on POSIX;
  4. pty_server.py's copy of the same block is fixed too (source check) —
     the interactive terminal spawned codex through the identical code.

No network, no real codex binary: a python stub prints its own env.

Run: python3 scripts/test_the_codex_child_keeps_its_path.py
"""
from __future__ import annotations

import json
import os
import pathlib
import stat
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(f'  {"ok  " if cond else "FAIL"}  {label}'
          + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


STUB = '''
import json, os, sys
try:
    sys.stdin.read()
except Exception:
    pass
env = {k: v for k, v in os.environ.items() if k.lower() == 'path'}
print(json.dumps({"type": "agent_message", "content": json.dumps(env)}))
'''


def _stub_codex(tmp: pathlib.Path) -> str:
    p = tmp / 'codex'
    p.write_text('#!' + sys.executable + '\n' + STUB, encoding='utf-8')
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def _child_path_env(marker_dir: str) -> dict:
    """Spawn the stub through the driver and return the child's path keys."""
    from drivers.codex import CodexDriver

    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        drv = CodexDriver()
        drv.binary_override = _stub_codex(tmp)
        handle = drv.start_task({'prompt': 'hi', 'cwd': td})
        text = ''.join(e.get('text', '') for e in drv.events(handle)
                       if e.get('event') == 'token')
    return json.loads(text.strip())


def main() -> int:
    print('the codex child keeps its PATH')

    if sys.platform == 'win32':
        print('  SKIP  POSIX-only (Windows env vars are case-insensitive)')
        return 0

    # A real-looking parent PATH: one usable dir, one arg0 turd to scrub.
    real_dir = os.path.dirname(sys.executable) or '/usr/bin'
    arg0 = r'C:\Users\x\.codex\tmp\arg0'
    saved = os.environ.get('PATH', '')
    os.environ['PATH'] = os.pathsep.join([real_dir, '/usr/bin', arg0])
    try:
        env = _child_path_env(real_dir)
    finally:
        os.environ['PATH'] = saved

    child_path = env.get('PATH', '')
    check('the child env has a PATH key at all', 'PATH' in env,
          f'path-ish keys seen: {sorted(env)}')
    check('that PATH is non-empty', bool(child_path.strip()), repr(child_path))
    check('and it still carries the parent dirs',
          real_dir in child_path.split(os.pathsep), repr(child_path))
    check('the .codex\\tmp\\arg0 scrub survives the fix',
          arg0 not in child_path.split(os.pathsep), repr(child_path))
    check('no stray Windows-cased Path is left on POSIX',
          'Path' not in env, f'path-ish keys seen: {sorted(env)}')

    # The PTY terminal spawns codex through a copy of the same block.
    src = (ROOT / 'pty_server.py').read_text(encoding='utf-8')
    check("pty_server.py no longer hardcodes agent_env['Path']",
          "agent_env['Path'] = path_value" not in src)

    print(f'\n{"FAIL" if FAILS else "PASS"} — {len(FAILS)} failing')
    return 1 if FAILS else 0


raise SystemExit(main())
