"""Claude Code driver — the local `claude` CLI behind the driver contract.

First driver extracted from serve.py (DRIVER_CONTRACT.md §5 step 1) because its
native stream-json output is closest to the canonical event schema, so the
translation layer here is the thinnest. The user's already-authenticated CLI
does the auth; serve.py never touches key material.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading

from .base import (Driver, DriverError, TaskHandle, ev_done, ev_error,
                   ev_status, ev_token, ev_tool_call, ev_tool_result, ev_usage)

# Tool names the CLI accepts for --disallowed-tools when a task runs with
# tools off. --allowed-tools '' (empty string) is rejected by the CLI; a
# disallow list is the correct idiom for "chat only".
_ALL_TOOLS = ('Bash,Edit,Write,MultiEdit,NotebookEdit,WebFetch,WebSearch,'
              'TodoWrite,Task')

# Git Bash locations prepended to PATH on Windows so the CLI's Bash tool can
# find bash.exe (without this it exits 255, "cannot find the path specified").
_GIT_BASH_DIRS = (r'C:\Program Files\Git\usr\bin',
                  r'C:\Program Files\Git\bin',
                  r'C:\Program Files\Git\mingw64\bin')


class ClaudeCodeDriver(Driver):
    MANIFEST = {
        'id': 'claude-code',
        'displayName': 'Claude',
        'sprite': 'coworker-claude',
        'kind': 'cli',
        'authMode': 'oauth-cli',
        'models': [],   # runtime-managed; --model passes through when set
        'capabilities': {'streaming': True, 'tools': True,
                         'artifacts': True, 'workspaces': True},
        'costHint': 'subscription',
    }

    def __init__(self):
        self.binary_override = os.environ.get('CAFRESOHQ_CLAUDE_BIN', '').strip()

    # ── lifecycle ────────────────────────────────────────────────────────────
    def resolve(self):
        """Absolute path to the claude binary, or ''."""
        if self.binary_override and pathlib.Path(self.binary_override).is_file():
            return self.binary_override
        # shutil.which respects PATH and Windows .cmd/.exe extensions.
        return shutil.which(self.binary_override or 'claude') or ''

    @staticmethod
    def detect_auth():
        """(authenticated, mechanism) via file/env checks only — no key
        material is read or returned. False is a hint, not a verdict (macOS
        keychain-stored creds have no file to see)."""
        home = pathlib.Path.home()
        try:
            if (home / '.claude' / '.credentials.json').is_file():
                return True, 'oauth'
            cfg = home / '.claude.json'
            if cfg.is_file():
                try:
                    if '"oauthAccount"' in cfg.read_text(encoding='utf-8',
                                                         errors='ignore'):
                        return True, 'oauth'
                except OSError:
                    pass
            if os.environ.get('ANTHROPIC_API_KEY', '').strip():
                return True, 'api-key'
        except OSError:
            pass
        return False, ''

    def detect(self, probe_version=False):
        bin_ = self.resolve()
        authed, mech = self.detect_auth()
        version = ''
        if bin_ and probe_version:
            try:
                r = subprocess.run([bin_, '--version'], capture_output=True,
                                   text=True, timeout=6)
                out = (r.stdout or r.stderr or '').strip()
                version = out.splitlines()[0][:80] if out else ''
            except Exception:
                pass
        return {'installed': bool(bin_), 'authenticated': authed,
                'auth': mech, 'version': version, 'detail': bin_}

    def configure(self, settings):
        path = str((settings or {}).get('binary') or '').strip()
        if path and not pathlib.Path(path).is_file():
            raise DriverError(f'not a file: {path}', status=400)
        self.binary_override = path
        return self.detect()

    def start_task(self, task):
        bin_ = self.resolve()
        if not bin_:
            raise DriverError('claude CLI not found — install Claude Code or '
                              'set CAFRESOHQ_CLAUDE_BIN', status=503)

        prompt = (task.get('prompt') or '').strip()
        if not prompt:
            # Flatten chat history for non-interactive --print mode: roles get
            # prefixed so the model sees the conversation shape.
            lines = []
            for m in (task.get('messages') or []):
                role = (m.get('role') or 'user').upper()
                content = (m.get('content') or '').strip()
                if content:
                    lines.append(f'{role}: {content}')
            prompt = '\n\n'.join(lines)
        if not prompt:
            raise DriverError('no prompt', status=400)

        tools = [t for t in (task.get('tools') or []) if t]
        cmd = [bin_, '--print',
               '--output-format', 'stream-json',
               '--verbose',
               '--input-format', 'text']
        if tools:
            cmd += ['--allowed-tools', ','.join(tools)]
            for d in (task.get('addDirs') or []):
                cmd += ['--add-dir', d]
        else:
            cmd += ['--disallowed-tools', _ALL_TOOLS]
        model = (task.get('model') or '').strip()
        if model:
            cmd += ['--model', model]
        system = (task.get('system') or '').strip()
        if system:
            cmd += ['--append-system-prompt', system]

        env = dict(os.environ)
        for d in reversed(_GIT_BASH_DIRS):
            if os.path.isdir(d) and d not in env.get('PATH', ''):
                env['PATH'] = d + os.pathsep + env.get('PATH', '')

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, bufsize=1, encoding='utf-8',
                cwd=(task.get('cwd') or None),
                env=env,
            )
        except (FileNotFoundError, OSError) as e:
            raise DriverError(f'spawn: {e}', status=500)

        handle = TaskHandle()
        handle.proc = proc
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception as e:
            self.cancel(handle)
            raise DriverError(f'stdin: {e}', status=500)

        # Drain stderr in a thread so the pipe doesn't fill up and stall the
        # CLI; kept on the handle to surface on a silent non-zero exit.
        stderr_buf = []
        def _drain():
            try:
                for line in proc.stderr:
                    stderr_buf.append(line)
            except Exception:
                pass
        threading.Thread(target=_drain, daemon=True).start()
        handle.private['stderr'] = stderr_buf
        return handle

    def events(self, handle):
        proc = handle.proc
        yield ev_status('starting')
        in_tok = out_tok = 0
        emitted = False
        try:
            for line in proc.stdout:
                if handle.cancelled.is_set():
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # stream-json wraps Anthropic message events:
                #   {"type":"system","subtype":"init", ...}
                #   {"type":"assistant","message":{"content":[...],"usage":{...}}}
                #   {"type":"user","message":{"content":[{"type":"tool_result",...}]}}
                #   {"type":"result","result":"…","usage":{...}}
                t = ev.get('type')
                if t == 'assistant':
                    msg = ev.get('message') or {}
                    for block in (msg.get('content') or []):
                        bt = block.get('type')
                        if bt == 'text' and block.get('text'):
                            emitted = True
                            yield ev_token(block['text'])
                        elif bt == 'tool_use':
                            # The CLI's own PreToolUse hook handles approvals
                            # (serve.py /approvals bridge), so these stream as
                            # informational — they drive the office animation.
                            yield ev_tool_call(block.get('id') or '',
                                               block.get('name') or '',
                                               block.get('input') or {})
                    u = msg.get('usage')
                    if u:
                        in_tok = u.get('input_tokens', in_tok)
                        out_tok = u.get('output_tokens', out_tok)
                elif t == 'user':
                    msg = ev.get('message') or {}
                    for block in (msg.get('content') or []):
                        if block.get('type') == 'tool_result':
                            content = block.get('content')
                            if isinstance(content, list):
                                content = ' '.join(
                                    c.get('text', '') for c in content
                                    if isinstance(c, dict))
                            yield ev_tool_result(
                                block.get('tool_use_id') or '',
                                not block.get('is_error'),
                                str(content or '')[:200])
                elif t == 'result':
                    u = ev.get('usage') or {}
                    in_tok = u.get('input_tokens', in_tok)
                    out_tok = u.get('output_tokens', out_tok)
                elif t == 'error':
                    yield ev_error(ev.get('message') or ev, recoverable=True)
        finally:
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if in_tok or out_tok:
            yield ev_usage(in_tok, out_tok, self.MANIFEST['costHint'])
        # Non-zero exit with nothing streamed: surface stderr as the error.
        if proc.returncode and not emitted and not (in_tok or out_tok):
            err = ''.join(handle.private.get('stderr') or [])[:600]
            yield ev_error(err or f'exit {proc.returncode}')
        else:
            yield ev_done()
