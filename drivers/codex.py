"""Codex driver — OpenAI's `codex exec --json` CLI behind the driver contract.

Second driver extracted from serve.py (DRIVER_CONTRACT.md §5 step 2). Codex is
tools-always-on by design: `exec` runs in a workspace-write sandbox rooted at
the task cwd, so hosts must only pass cwd/addDirs they have already validated.
Auth comes from ~/.codex/auth.json or OPENAI_API_KEY — never from us.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading

from .base import (Driver, DriverError, TaskHandle, ev_done, ev_error,
                   ev_status, ev_token, ev_tool_call, ev_tool_result,
                   probe_cli_version)

_GIT_BASH_DIRS = (r'C:\Program Files\Git\usr\bin',
                  r'C:\Program Files\Git\bin',
                  r'C:\Program Files\Git\mingw64\bin')


def _content_text(value):
    """Codex message content arrives as str, block-list, or nested dict —
    flatten whatever shape shows up into plain text."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for block in value:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get('text') or block.get('content')
                             or block.get('output_text') or '')
        return ''.join(parts)
    if isinstance(value, dict):
        return (value.get('text') or value.get('content')
                or value.get('message') or _content_text(value.get('content_parts')))
    return ''


def _summarize_stderr(s):
    """Codex sometimes dumps an entire upstream HTTP body into stderr. Trim to
    the actual error summary so the chat surface doesn't get blasted with HTML."""
    if not s:
        return ''
    m = re.search(r'failed to refresh available models:[^\n]+', s)
    refresh_hint = ''
    if m:
        refresh_hint = ('\n\nNote: the model-list refresh failed. Check that '
                        'OPENAI_API_KEY is set and the selected model is valid.')
    _BENIGN = ('Reading prompt from stdin', 'codex_models_manager',
               'failed to refresh available models')
    cleaned = []
    for line in s.splitlines():
        if line.startswith((' ', '"', '}', '{')):
            continue
        if '<!DOCTYPE' in line or '<html' in line:
            continue
        if any(p in line for p in _BENIGN):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)[:600].rstrip() + refresh_hint


class CodexDriver(Driver):
    MANIFEST = {
        'id': 'codex',
        'displayName': 'Codex',
        'sprite': 'coworker-codex',
        'kind': 'cli',
        'authMode': 'oauth-cli',
        'models': [],   # runtime-managed; default wire model below
        'capabilities': {'streaming': True, 'tools': True,
                         'artifacts': True, 'workspaces': True},
        'costHint': 'subscription',
    }
    DEFAULT_MODEL = 'gpt-4.1'

    def __init__(self):
        self.binary_override = os.environ.get('CAFRESOHQ_CODEX_BIN', '').strip()

    def resolve(self):
        """Absolute path to the codex binary, or ''. On Windows prefer
        codex.cmd — the extensionless npm wrapper is a shell script Windows
        can't exec (OSError 193 used to kill the HTTP connection)."""
        if self.binary_override and pathlib.Path(self.binary_override).is_file():
            return self.binary_override
        if sys.platform == 'win32':
            return (shutil.which('codex.cmd')
                    or shutil.which(self.binary_override or 'codex')
                    or shutil.which('codex') or '')
        return (shutil.which(self.binary_override or 'codex')
                or shutil.which('codex.cmd') or '')

    @staticmethod
    def detect_auth():
        try:
            if (pathlib.Path.home() / '.codex' / 'auth.json').is_file():
                return True, 'oauth'
            if os.environ.get('OPENAI_API_KEY', '').strip():
                return True, 'api-key'
        except OSError:
            pass
        return False, ''

    def detect(self, probe_version=False):
        bin_ = self.resolve()
        authed, mech = self.detect_auth()
        version = probe_cli_version(bin_) if (bin_ and probe_version) else ''
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
            raise DriverError('codex CLI not found — install via '
                              'npm i -g @openai/codex or set CAFRESOHQ_CODEX_BIN',
                              status=503)
        cwd = (task.get('cwd') or '').strip()
        if not cwd:
            raise DriverError('codex requires a working directory', status=503)

        prompt = (task.get('prompt') or '').strip()
        if not prompt:
            lines = []
            for m in (task.get('messages') or []):
                role = (m.get('role') or 'user').upper()
                content = (m.get('content') or '').strip()
                if content:
                    lines.append(f'{role}: {content}')
            prompt = '\n\n'.join(lines)
        if not prompt:
            raise DriverError('no prompt', status=400)
        # codex exec has no --append-system-prompt; the system text rides in
        # front of the prompt.
        system = (task.get('system') or '').strip()
        if system:
            prompt = system + '\n\n' + prompt

        cmd = [bin_, 'exec',
               '--json',
               '--skip-git-repo-check',
               '--sandbox', 'workspace-write',
               '-C', cwd]
        # addDirs are passed verbatim — the host sends the extra dirs beyond
        # the cwd's own root (matching the old /codex/stream behavior).
        for d in (task.get('addDirs') or []):
            cmd += ['--add-dir', d]
        # Codex talks directly to OpenAI (default provider); OCI cloud
        # requirements only allow approval_policy "untrusted" — anything else
        # is rejected and used to surface as "Codex returned no content".
        cmd += ['-c', 'model_provider="openai"']
        cmd += ['--model', (task.get('model') or '').strip() or self.DEFAULT_MODEL]
        cmd += ['-c', 'approval_policy="untrusted"']

        # Env fixups: Git Bash on PATH for Windows shell tools, drop the
        # \.codex\tmp\arg0 self-referential PATH entries codex leaves behind,
        # normalize the PATH key casing, and clear OPENAI_BASE_URL (codex uses
        # OpenAI directly; a leftover override breaks it).
        env = dict(os.environ)
        path_key = next((k for k in env if k.lower() == 'path'), 'Path')
        path_value = env.get(path_key, '')
        for d in _GIT_BASH_DIRS:
            if os.path.isdir(d) and d not in path_value:
                path_value = d + os.pathsep + path_value
        path_value = os.pathsep.join(
            p for p in path_value.split(os.pathsep)
            if p and r'\.codex\tmp\arg0' not in p.lower())
        for k in [k for k in list(env) if k.lower() == 'path']:
            env.pop(k, None)
        env['Path'] = path_value
        env.pop('OPENAI_BASE_URL', None)

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, bufsize=1, encoding='utf-8',
                cwd=cwd,
                env=env,
            )
        except (FileNotFoundError, OSError) as e:
            raise DriverError(f'spawn codex: {e}', status=500)

        handle = TaskHandle()
        handle.proc = proc
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception as e:
            # Codex died before the prompt could be sent — surface the real
            # failure (bad profile, bad config, …) instead of a broken pipe.
            stderr_text = ''
            try:
                stderr_text = proc.stderr.read()[:1500]
            except Exception:
                pass
            self.cancel(handle)
            raise DriverError(
                f'codex exited before prompt could be sent: {e}'
                + (f' — {stderr_text}' if stderr_text else ''), status=500)

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
        # item.updated/item.completed re-send the full text of an item; track
        # what we already emitted per item id and forward only the delta.
        item_text_seen = {}
        events_seen = 0
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
                events_seen += 1
                t = ev.get('type', '')

                if t in ('agent_message', 'message'):
                    text = _content_text(ev.get('content') or ev.get('message') or '')
                    if text:
                        emitted = True
                        yield ev_token(text)

                elif t in ('agent_message_delta', 'message_delta',
                           'response.output_text.delta'):
                    text = ev.get('delta') or ev.get('text') or ev.get('content') or ''
                    if text:
                        emitted = True
                        yield ev_token(str(text))

                elif t in ('item.updated', 'item.completed'):
                    item = ev.get('item') or {}
                    item_type = item.get('type', '')
                    if item_type == 'error':
                        msg = item.get('message') or item.get('text') or json.dumps(item)
                        # The cloud-requirements approval_policy downgrade
                        # notice always fires for `codex exec` and the run
                        # still completes — pure noise, don't surface it.
                        if not ('disallowed by requirements' in msg
                                or 'falling back to required value' in msg):
                            emitted = True
                            yield ev_error(msg, recoverable=True)
                    elif (item.get('role') == 'assistant'
                          or item_type in ('message', 'agent_message')):
                        text = (item.get('text')
                                or _content_text(item.get('content') or item.get('message')))
                        item_id = item.get('id') or ev.get('item_id') or 'assistant'
                        prior = item_text_seen.get(item_id, '')
                        if text and text.startswith(prior):
                            delta = text[len(prior):]
                        elif text and text != prior:
                            delta = text
                        else:
                            delta = ''
                        item_text_seen[item_id] = text or prior
                        if delta:
                            emitted = True
                            yield ev_token(delta)

                elif t in ('turn.completed', 'response.completed'):
                    text = _content_text(ev.get('last_agent_message')
                                         or ev.get('message') or '')
                    if text:
                        emitted = True
                        yield ev_token(text)

                elif t == 'function_call':
                    emitted = True
                    yield ev_tool_call(str(ev.get('call_id') or ''),
                                       ev.get('name') or ev.get('function') or 'tool',
                                       ev.get('arguments') or ev.get('input') or {})

                elif t == 'function_call_output':
                    output = ev.get('output') or ''
                    if output:
                        emitted = True
                        yield ev_tool_result(str(ev.get('call_id') or ''),
                                             True, str(output)[:2000])

                elif t in ('error', 'turn.failed'):
                    msg = (ev.get('message')
                           or (ev.get('error') or {}).get('message') or str(ev))
                    emitted = True
                    yield ev_error(msg, recoverable=True)
        finally:
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        stderr_text = (''.join(handle.private.get('stderr') or [])).strip()
        rc = proc.returncode
        # Three endings that all used to look like a silent successful run:
        # non-zero exit, zero exit with no events, zero exit + stderr noise.
        if rc and rc not in (0, None):
            yield ev_error(f'exited {rc}: '
                           + (_summarize_stderr(stderr_text) or f'exit {rc}'))
        elif not emitted:
            hint = (_summarize_stderr(stderr_text)
                    or '(no stdout, no stderr — likely the OS blocked the nested codex spawn)')
            yield ev_error(f'returned no content (events seen: {events_seen}, '
                           f'exit: {rc}). {hint}')
        else:
            summary = _summarize_stderr(stderr_text) if stderr_text else ''
            yield ev_done(f'codex stderr: {summary[:300]}' if summary else '')
