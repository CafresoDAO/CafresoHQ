"""Gemini CLI driver — Google's `gemini --yolo --prompt` behind the driver
contract.

The last un-checked item in DRIVER_CONTRACT.md §5 step 2. Gemini CLI was the
one bespoke integration style never folded in: it lived only in
pty_server.py's /terminal/run (still there, unchanged — the PTY terminal is
parked off the newcomer path per north-star §5, so its own spawn stays as
is). This driver gives the contract-native paths (POST /agent/stream,
night_runner) the same access serve.py's other four CLIs already have.

Auth comes from `~/.gemini/oauth_creds.json` (Google account login) or
GEMINI_API_KEY/GOOGLE_API_KEY — never from us. `--yolo` auto-approves tool
calls the same way codex's workspace-write sandbox does, so tools are
effectively always-on; the host must only pass a cwd it has already
validated.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading

from .base import (Driver, DriverError, TaskHandle, ev_done, ev_error,
                   ev_status, ev_token, probe_cli_version)

# Gemini's plain-text stdout carries spinner/color escapes; strip them so a
# chat bubble or a filed note never carries raw ANSI.
_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')


class GeminiCliDriver(Driver):
    MANIFEST = {
        'id': 'gemini',
        'displayName': 'Gemini',
        'sprite': 'coworker-gemini',
        'kind': 'cli',
        'authMode': 'oauth-cli',
        'models': [],   # runtime-managed; default wire model below
        'capabilities': {'streaming': True, 'tools': True,
                         'artifacts': True, 'workspaces': True},
        'costHint': 'subscription',
    }
    DEFAULT_MODEL = 'gemini-2.5-pro'

    def __init__(self):
        self.binary_override = os.environ.get('CAFRESOHQ_GEMINI_BIN', '').strip()

    def resolve(self):
        """Absolute path to the gemini binary, or ''. Same OSError-193
        reasoning as codex: on Windows the extensionless npm wrapper is a
        shell script Windows can't exec, so prefer gemini.cmd."""
        if self.binary_override and pathlib.Path(self.binary_override).is_file():
            return self.binary_override
        if sys.platform == 'win32':
            return (shutil.which('gemini.cmd')
                    or shutil.which(self.binary_override or 'gemini')
                    or shutil.which('gemini') or '')
        return shutil.which(self.binary_override or 'gemini') or shutil.which('gemini.cmd') or ''

    @staticmethod
    def detect_auth():
        try:
            gdir = pathlib.Path.home() / '.gemini'
            if ((gdir / 'oauth_creds.json').is_file()
                    or (gdir / 'google_accounts.json').is_file()):
                return True, 'oauth'
            if (os.environ.get('GEMINI_API_KEY', '').strip()
                    or os.environ.get('GOOGLE_API_KEY', '').strip()):
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
            raise DriverError('gemini CLI not found — install via '
                              'npm i -g @google/gemini-cli or set CAFRESOHQ_GEMINI_BIN',
                              status=503)
        cwd = (task.get('cwd') or '').strip()
        if not cwd:
            raise DriverError('gemini requires a working directory', status=503)

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
        system = (task.get('system') or '').strip()
        if system:
            prompt = system + '\n\n' + prompt

        # The prompt goes in argv, not stdin — gemini reads --prompt and runs
        # once, printing the answer to stdout. --yolo auto-approves tool
        # calls so the agent can actually read/edit files in cwd (parity
        # with codex's workspace-write sandbox); cwd scopes it.
        cmd = [bin_, '--yolo', '--prompt', prompt]
        cmd += ['--model', (task.get('model') or '').strip() or self.DEFAULT_MODEL]

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, bufsize=1, encoding='utf-8',
                cwd=cwd,
                env=dict(os.environ),
            )
        except (FileNotFoundError, OSError) as e:
            raise DriverError(f'spawn gemini: {e}', status=500)

        handle = TaskHandle()
        handle.proc = proc
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
        emitted = False
        try:
            while True:
                if handle.cancelled.is_set():
                    break
                chunk = proc.stdout.read(256)
                if not chunk:
                    break
                clean = _ANSI_RE.sub('', chunk)
                if clean:
                    emitted = True
                    yield ev_token(clean)
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
        if rc and rc not in (0, None):
            yield ev_error(f'exited {rc}: ' + (stderr_text[:300] or f'exit {rc}'))
        elif not emitted:
            hint = (stderr_text[:300]
                    or 'is the gemini CLI logged in? run it once in PTY mode to authenticate')
            yield ev_error(f'gemini returned no content — {hint}')
        else:
            yield ev_done()
