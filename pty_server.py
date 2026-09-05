"""PTY / terminal server — extracted from serve.py.

The persistent-PTY session registry, its reaper, and the five /terminal/*
handlers. The handlers are written as plain functions taking the request
handler as `self` and are bound onto serve.py's Handler class unchanged, so
they keep using its helpers (_send_json, _app_origins, _api_key_ok, the CLI
resolvers) exactly as before. serve.py injects _client_path and _RUNTIME_ENV
after import.
"""
import base64
import fcntl
import hashlib
import json
import re
import os
import pathlib
import secrets
import select
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.parse

# Injected by serve.py right after import (they live in its config prologue).
_client_path = None
_RUNTIME_ENV = 'local'


# Per-process nonce for /terminal/pty WebSocket auth.
# Generated once at startup; never logged.  Frontend fetches it from
# /terminal/nonce before opening the WebSocket.  Any connection that doesn't
# supply it with secrets.compare_digest() equality is rejected with 403.
_PTY_NONCE = secrets.token_hex(32)   # 256-bit random — unguessable

# ── Persistent PTY session registry ────────────────────────────────────────
# Keeps PTY processes alive after the WebSocket drops so mobile clients can
# reconnect and see buffered output from work that ran while they were away.
_PTY_SESSIONS    = {}               # session_id → session-state dict
_PTY_SESSIONS_LK = threading.Lock()
_PTY_SESSION_TTL = 300              # seconds to keep a disconnected PTY alive
_PTY_BUF_CAP     = 524_288          # max bytes buffered per session (512 KB)

def _pty_reaper():
    while True:
        time.sleep(30)
        now = time.time()
        to_kill = []
        with _PTY_SESSIONS_LK:
            for sid, s in list(_PTY_SESSIONS.items()):
                if s['sock'] is None and s.get('expires', 0) < now:
                    to_kill.append((sid, s))
            for sid, _ in to_kill:
                _PTY_SESSIONS.pop(sid, None)
        for _, s in to_kill:
            s['stop'].set()
            for k in ('pty_proc', 'proc'):
                try: s.get(k) and s[k].terminate()
                except Exception: pass

threading.Thread(target=_pty_reaper, daemon=True).start()


def _pty_claim_session(session_id):
    """Find the live session for `session_id`, or register a fresh one and
    claim the right to spawn its PTY. Returns (sess, is_new).

    Both halves happen under ONE hold of _PTY_SESSIONS_LK, and that is the
    whole point. The lookup and the registration used to be two separate
    holds with the session dict built in between, so two connections
    carrying the same session_id — a phone and a desktop both restoring the
    id they persisted, or one client reconnecting the instant the server
    came back — could both read "no session here" and both go on to spawn.
    The second registration overwrote the first, and the first PTY was then
    unreachable by every route that exists to end one: the reaper only walks
    _PTY_SESSIONS, /terminal/kill only pops out of it, and the WS teardown at
    the bottom of _terminal_pty_ws deliberately does NOT terminate a session
    that has an id (it assumes the registry is holding it for a reconnect).
    A whole CLI process, its master fd and its reader thread stayed alive for
    the life of the server, one more per collision.
    """
    with _PTY_SESSIONS_LK:
        sess = _PTY_SESSIONS.get(session_id) if session_id else None
        if sess is not None and not sess['stop'].is_set():
            return sess, False
        sess = {
            'stop':    threading.Event(),
            'sock':    None,
            'sock_lk': threading.Lock(),
            'buf':     bytearray(),
            'buf_lk':  threading.Lock(),
            'expires': None,
        }
        if session_id:
            _PTY_SESSIONS[session_id] = sess
        return sess, True


def _pty_drop_session(session_id, sess):
    """Remove `session_id` from the registry only if it still maps to `sess`.

    The other half of the same hazard: a PTY that exits pops its own id, but
    a bare pop(session_id) evicts whatever is under that key NOW. When a
    client reconnects to an id whose PTY has just died, the claim above
    installs a fresh session under it, and the dying reader thread's pop then
    deleted the live successor — orphaning the new PTY exactly the way the
    duplicate spawn orphaned the old one.
    """
    if not session_id:
        return
    with _PTY_SESSIONS_LK:
        if _PTY_SESSIONS.get(session_id) is sess:
            _PTY_SESSIONS.pop(session_id, None)


# Browser→server control frames that must NEVER be forwarded to the PTY.
def _pty_control_frame(payload):
    """Classify one browser→server WS frame: return the parsed control dict
    for a JSON control message, or None when the frame is keystroke data
    destined for the PTY.

    'resize' has always been a control frame. 'init' now is too, and that is
    the point of this helper: the pre-spawn reader above only waits 2 s for
    the init frame, while the browser (views/terminal.jsx) sends it from
    ws.onopen *after* awaiting up to three CafresoHQClient.getAgentKey()
    vault lookups. When those run long — a cold ICP bridge, a locked vault —
    the frame misses that window and arrives in the ordinary keystroke loop
    instead. Before this, the loop parsed it, saw a type it didn't recognise,
    and wrote the raw payload to the PTY: the user's plaintext
    ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY typed straight into
    the running CLI, echoed on screen and captured in the agent's own
    scrollback and shell history. The keys can't be applied retroactively
    (the child's env was fixed at spawn), so the only safe handling is to
    recognise the frame and drop it.
    """
    try:
        msg = json.loads(payload)
    except (ValueError, TypeError):
        return None
    if isinstance(msg, dict) and msg.get('type') in ('resize', 'init'):
        return msg
    return None


# ---- Project Terminal (Claude Code / Codex CLI runner) ---------------
def _terminal_spawn(self):
    """GET /terminal/spawn?cli=claude|codex&cwd=<path>
    Opens the CLI in a new OS terminal window so the user sees the
    full interactive TUI (welcome screen, coloured prompts, etc.).
    Windows: tries Windows Terminal → pwsh → PowerShell → cmd.
    macOS: osascript → Terminal.app.
    Linux: tries x-terminal-emulator → gnome-terminal → kitty → xterm.
    """
    qs = urllib.parse.urlparse(self.path).query
    params = urllib.parse.parse_qs(qs)
    cli  = (params.get('cli')  or ['claude'])[0].strip().lower()
    cwd  = (params.get('cwd')  or ['']      )[0].strip()
    if cli not in ('claude', 'codex', 'hermes', 'gemini'):
        return self._send_json(400, {'error': 'cli must be claude, codex, hermes, or gemini'})
    if not cwd:
        return self._send_json(400, {'error': 'cwd required'})
    cwd_path = pathlib.Path(_client_path(cwd)).resolve()
    if not cwd_path.is_dir():
        return self._send_json(400, {'error': f'directory not found: {cwd}'})
    if cli == 'claude':
        bin_ = self._claudecode_resolve()
    elif cli == 'codex':
        bin_ = self._codex_resolve()
    elif cli == 'gemini':
        bin_ = self._gemini_resolve()
    else:  # hermes
        bin_ = self._hermes_resolve()
    if not bin_:
        return self._send_json(503, {'error': f'{cli} CLI not found'})
    # Hermes' bare binary doesn't open the interactive agent — same reason
    # _terminal_pty_ws appends this subcommand (see its own comment above).
    cli_args = [cli, 'chat'] if cli == 'hermes' else [cli]
    cli_cmd  = ' '.join(cli_args)
    try:
        if sys.platform == 'win32':
            wt  = shutil.which('wt')
            ps  = shutil.which('pwsh') or shutil.which('powershell')
            if wt and ps:
                subprocess.Popen(
                    ['wt', '-d', str(cwd_path), ps, '-NoExit', '-Command', cli_cmd],
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            elif ps:
                subprocess.Popen(
                    [ps, '-NoExit', '-Command',
                     f'Set-Location "{cwd_path}"; {cli_cmd}'],
                    creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                )
            else:
                subprocess.Popen(
                    ['cmd', '/k', f'cd /d "{cwd_path}" && {cli_cmd}'],
                    creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                )
        elif sys.platform == 'darwin':
            # None of the Linux terminal emulators below ship on stock macOS
            # (confirmed: x-terminal-emulator/gnome-terminal/kitty/xterm are
            # all absent), so that loop always fell through to the 503 here —
            # this actually spawns a window. Terminal.app takes the command
            # as a shell string via `do script`, so cwd_path is shell-quoted
            # for that inner shell *and* the whole string is AppleScript-
            # escaped for the outer `do script "..."` literal.
            osa = shutil.which('osascript')
            if not osa:
                return self._send_json(503, {'error': 'no terminal emulator found'})
            shell_cmd = f'cd {shlex.quote(str(cwd_path))} && ' + ' '.join(shlex.quote(a) for a in cli_args)
            as_literal = shell_cmd.replace('\\', '\\\\').replace('"', '\\"')
            applescript = (
                'tell application "Terminal"\n'
                'activate\n'
                f'do script "{as_literal}"\n'
                'end tell'
            )
            subprocess.Popen([osa, '-e', applescript])
        else:
            launched = False
            for term in ['x-terminal-emulator', 'gnome-terminal', 'kitty', 'xterm']:
                if shutil.which(term):
                    subprocess.Popen([term, '-e'] + cli_args, cwd=str(cwd_path))
                    launched = True
                    break
            if not launched:
                return self._send_json(503, {'error': 'no terminal emulator found'})
    except Exception as e:
        return self._send_json(500, {'error': f'spawn failed: {e}'})
    return self._send_json(200, {'ok': True, 'cli': cli, 'cwd': str(cwd_path)})

def _terminal_nonce(self):
    """GET /terminal/nonce → {"nonce": "<hex>"}
    Returns the per-process nonce that /terminal/pty requires as a query param.
    TWO gates, and both are load-bearing:

      * the HOST gate (_rebind_host_gate) — the Host must be something a
        DNS-rebinding attack cannot produce: absent, a loopback literal, a bare
        IP literal, or a hostname in _app_origins();
      * the ORIGIN gate below — a cross-origin Origin not in the allowlist is
        refused, which is what stops an ordinary cross-origin fetch.

    This docstring used to say the Origin gate alone made the route
    "same-origin only", on the reasoning that an absent Origin means a
    same-origin XHR. That reasoning is false under DNS rebinding, and it stated
    the hole as the design. A page at http://evil.example whose name has been
    rebound to 127.0.0.1 is same-origin WITH ITSELF, so the browser sends no
    Origin header at all; the check was skipped and the nonce handed over. The
    page then opened /terminal/pty?cli=claude&cwd=… with it — arbitrary code
    execution on the machine of anyone who visited it. Ledger `## 320.`.

    Both gates are also applied at dispatch in serve.py, for the whole
    /terminal family. The Host gate is repeated here because this function is
    bound onto the handler as a free function: it is one line in a dispatch
    table away from being reachable by some other path, and the nonce is the
    key to a shell.
    """
    if not self._rebind_host_gate():
        return
    _origin = self.headers.get('Origin', '').strip()
    if _origin and _origin not in self._app_origins():
        return self._send_json(403, {'error': f'origin not allowed: {_origin}'})
    return self._send_json(200, {'nonce': _PTY_NONCE})

def _terminal_pty_ws(self):
    """GET /terminal/pty?cli=claude|codex&cwd=<path>&cols=120&rows=30
    Upgrades to WebSocket, spawns a PTY running the CLI, and bridges
    stdin/stdout between the browser (xterm.js) and the process.

    Windows: uses pywinpty (existing behaviour, unchanged).
    Linux/macOS: uses Python stdlib pty + subprocess (no extra packages).

    Browser → server frames: raw keystroke bytes (text or binary frames),
    or a JSON resize message: {"type":"resize","cols":N,"rows":N}.
    Server → browser frames: binary frames containing PTY output bytes.
    """
    _is_win = sys.platform == 'win32'
    if _is_win:
        try:
            import winpty as _winpty
        except ImportError:
            return self._send_json(503, {'error': 'pywinpty not installed — run: pip install pywinpty'})

    qs = urllib.parse.urlparse(self.path).query
    params = urllib.parse.parse_qs(qs)
    cli  = (params.get('cli')  or ['claude'])[0].strip().lower()
    cwd  = (params.get('cwd')  or ['']      )[0].strip()
    cols = max(10, min(500, int((params.get('cols') or ['120'])[0])))
    rows = max(5,  min(200, int((params.get('rows') or ['30'] )[0])))

    if cli not in ('claude', 'codex', 'hermes', 'gemini'):
        return self._send_json(400, {'error': 'cli must be claude, codex, hermes, or gemini'})
    if not cwd:
        return self._send_json(400, {'error': 'cwd required'})
    cwd_path = pathlib.Path(_client_path(cwd)).resolve()
    if not cwd_path.is_dir():
        return self._send_json(400, {'error': f'directory not found: {cwd}'})
    if cli == 'claude':
        bin_ = self._claudecode_resolve()
    elif cli == 'codex':
        bin_ = self._codex_resolve()
    elif cli == 'gemini':
        bin_ = self._gemini_resolve()
    else:  # hermes — the default agent (unix-only; native here or via WSL)
        bin_ = self._hermes_resolve()
    if not bin_:
        return self._send_json(503, {'error': f'{cli} CLI not found'})
    # Hermes opens its interactive agent via the `chat` subcommand; the
    # workspace cwd scopes the agent to that project. Others just exec.
    cli_extra_args = ['chat'] if cli == 'hermes' else []

    # ── Security: Host + Origin + nonce checks ─────────────────────────
    # Host validation — reject a DNS-rebound page. Also applied at dispatch
    # in serve.py for the whole /terminal family; repeated here because this
    # is the route that hands out a shell, and neither of the two checks
    # below stops a rebind on its own: the Origin check is skipped when no
    # Origin is sent (a rebound page sends none, being same-origin with this
    # server), and the nonce is fetchable by that same page from
    # /terminal/nonce. Ledger `## 320.`.
    if not self._rebind_host_gate():
        return
    # Origin validation — reject cross-origin WS initiations.
    # Browsers always send Origin on WebSocket upgrade; non-browser clients
    # may omit it (curl, CLI tools, unit tests) — those are allowed through
    # so local dev tooling isn't broken.
    _origin = self.headers.get('Origin', '').strip()
    if _origin and _origin not in self._app_origins():
        return self.send_error(403, f'WebSocket origin not allowed: {_origin}')

    # Nonce validation — the frontend fetches /terminal/nonce first and
    # appends ?nonce=<value> to the WS URL.  Any connection without the
    # correct nonce is rejected (attacker can't fetch the nonce cross-origin
    # because /terminal/nonce is same-origin-only for browser XHR).
    _provided_nonce = (params.get('nonce') or [''])[0]
    if not _provided_nonce or not secrets.compare_digest(_provided_nonce, _PTY_NONCE):
        return self.send_error(403, 'Missing or invalid nonce — fetch /terminal/nonce first')

    # ── WebSocket handshake ─────────────────────────────────────────────
    ws_key = self.headers.get('Sec-WebSocket-Key', '')
    if not ws_key:
        return self.send_error(400, 'missing Sec-WebSocket-Key')
    accept = base64.b64encode(
        hashlib.sha1((ws_key + self._WS_GUID).encode()).digest()
    ).decode()
    self.wfile.write((
        'HTTP/1.1 101 Switching Protocols\r\n'
        'Upgrade: websocket\r\n'
        'Connection: Upgrade\r\n'
        f'Sec-WebSocket-Accept: {accept}\r\n\r\n'
    ).encode('latin-1'))
    self.wfile.flush()
    self.close_connection = True
    client_sock = self.connection
    client_sock.settimeout(None)

    # ── Build PTY environment ───────────────────────────────────────────
    import copy as _copy
    agent_env = _copy.deepcopy(os.environ)
    for _d in [r'C:\Program Files\Git\usr\bin',
               r'C:\Program Files\Git\bin',
               r'C:\Program Files\Git\mingw64\bin']:
        if os.path.isdir(_d) and _d not in agent_env.get('PATH', ''):
            agent_env['PATH'] = _d + os.pathsep + agent_env.get('PATH', '')

    def _ws_recv_frame(sock):
        """Read one WebSocket frame; return (opcode, payload) or (None,None)."""
        def _read(n):
            buf = b''
            while len(buf) < n:
                chunk = sock.recv(n - len(buf))
                if not chunk:
                    raise ConnectionError('ws closed')
                buf += chunk
            return buf
        try:
            b0, b1 = struct.unpack('!BB', _read(2))
            opcode  = b0 & 0x0F
            masked  = bool(b1 & 0x80)
            length  = b1 & 0x7F
            if length == 126:
                (length,) = struct.unpack('!H', _read(2))
            elif length == 127:
                (length,) = struct.unpack('!Q', _read(8))
            mask = _read(4) if masked else b'\x00\x00\x00\x00'
            payload = bytearray(_read(length))
            if masked:
                for i in range(len(payload)):
                    payload[i] ^= mask[i % 4]
            return opcode, bytes(payload)
        except Exception:
            return None, None

    # ── Optional init frame — inject BYOK keys before spawning ──────────
    # The browser sends {"type":"init","anthropic_key":"...","openai_key":"..."}
    # as the very first WebSocket frame (in ws.onopen) so the shell inherits
    # the user's stored API keys automatically.  If the frame doesn't arrive
    # within 2 s (or the user has no stored keys), we just proceed without it.
    # Server-side env vars always win: BYOK is only injected when the
    # container env is blank (same rule as /terminal/stream).
    pending_frame = None   # replayed into ws_to_pty if it isn't an init frame
    client_sock.settimeout(2.0)
    _init_opcode, _init_payload = _ws_recv_frame(client_sock)
    client_sock.settimeout(None)
    if _init_opcode in (0x1, 0x2) and _init_payload:
        try:
            _init_msg = json.loads(_init_payload)
            if isinstance(_init_msg, dict) and _init_msg.get('type') == 'init':
                _pty_auth = (_init_msg.get('auth_method') or '').strip().lower()
                _ak = (_init_msg.get('anthropic_key') or '').strip()
                _ok = (_init_msg.get('openai_key')    or '').strip()
                _gk = (_init_msg.get('gemini_key')    or '').strip()
                if _pty_auth == 'subscription':
                    # Strip API key so CLI uses its own OAuth login
                    agent_env.pop('ANTHROPIC_API_KEY', None)
                elif _ak and not agent_env.get('ANTHROPIC_API_KEY', '').strip():
                    agent_env['ANTHROPIC_API_KEY'] = _ak
                if _ok and not agent_env.get('OPENAI_API_KEY', '').strip():
                    agent_env['OPENAI_API_KEY'] = _ok
                # Gemini CLI reads GEMINI_API_KEY (and GOOGLE_API_KEY as a
                # fallback) — set both so either lookup path works.
                if _gk and not agent_env.get('GEMINI_API_KEY', '').strip():
                    agent_env['GEMINI_API_KEY'] = _gk
                    agent_env.setdefault('GOOGLE_API_KEY', _gk)
                del _ak, _ok, _gk, _pty_auth  # clear plaintext key strings from Python locals
                del _init_msg, _init_payload  # clear raw frame bytes
            else:
                pending_frame = (_init_opcode, _init_payload)  # not init — replay
                del _init_msg
        except (ValueError, TypeError):
            pending_frame = (_init_opcode, _init_payload)      # not JSON — replay
    elif _init_opcode is not None:
        pending_frame = (_init_opcode, _init_payload)          # non-text — replay

    # ── WebSocket frame helper (server → client, unmasked) ─────────────
    def _ws_send_raw(sock, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        n = len(data)
        if n < 126:
            hdr = struct.pack('!BB', 0x82, n)
        elif n < 65536:
            hdr = struct.pack('!BBH', 0x82, 126, n)
        else:
            hdr = struct.pack('!BBQ', 0x82, 127, n)
        sock.sendall(hdr + data)   # raises OSError on failure; callers handle it

    # ── Session resume or new spawn ─────────────────────────────────────
    session_id = (params.get('session_id') or [''])[0].strip()

    sess, _sess_is_new = _pty_claim_session(session_id)

    if not _sess_is_new:
        # ── Reconnect to existing PTY session ──────────────────────────
        with sess['sock_lk']:
            sess['sock']    = client_sock
            sess['expires'] = None   # cancel reaper countdown

        # This connection's cols/rows (freshly parsed above) may differ
        # from whatever the PTY was originally spawned with — the browser
        # window can easily be a different size by the time a session is
        # resumed. Apply them to the already-running PTY now: the ONLY
        # other place that ever changes an existing PTY's kernel-level
        # window size is the {"type":"resize"} message handler below, and
        # the frontend (terminal.jsx) only sends that message in response
        # to a NEW resize event — never on reconnect/resume itself — so
        # without this, a resumed session would silently keep stale
        # dimensions (wrong wrapping, garbled TUI redraws) until the user
        # happened to resize the browser window again.
        try:
            if _is_win:
                sess['pty_proc'].setwinsize(rows, cols)
            else:
                import termios as _termios4
                fcntl.ioctl(sess['master_fd'], _termios4.TIOCSWINSZ,
                            struct.pack('HHHH', rows, cols, 0, 0))
        except Exception:
            pass

        # Replay buffered output collected while the client was away.
        with sess['buf_lk']:
            replay, sess['buf'] = bytes(sess['buf']), bytearray()
        if replay:
            try:
                _ws_send_raw(client_sock, replay)
            except OSError:
                pass

        sys.stderr.write(f'[pty-ws] reconnected: {session_id[:8]}… {cli} @ {cwd_path}\n')

    else:
        # ── Spawn a fresh PTY ───────────────────────────────────────────
        # The registry slot was already claimed atomically above; this
        # connection owns it, so attaching the socket needs no lock yet
        # (no reader thread exists until the spawn below succeeds).
        with sess['sock_lk']:
            sess['sock'] = client_sock

        if _is_win:
            spawn_argv = ['cmd.exe', '/c', bin_ or cli] + cli_extra_args
            try:
                pty_proc = _winpty.PtyProcess.spawn(
                    spawn_argv, cwd=str(cwd_path), env=agent_env,
                    dimensions=(rows, cols),
                )
            except Exception as exc:
                try: _ws_send_raw(client_sock, f'\r\n\x1b[31mFailed to spawn {cli}: {exc}\x1b[0m\r\n')
                except OSError: pass
                _pty_drop_session(session_id, sess)
                return
            sess['pty_proc'] = pty_proc

            def pty_to_ws():
                while not sess['stop'].is_set():
                    try:
                        data = pty_proc.read(4096)
                    except EOFError:
                        data = None
                    except Exception:
                        data = None if not pty_proc.isalive() else b''
                    if data is None:
                        break
                    if not data:
                        continue
                    raw = data.encode('utf-8') if isinstance(data, str) else data
                    with sess['sock_lk']:
                        sock = sess['sock']
                    if sock:
                        try:
                            _ws_send_raw(sock, raw)
                            continue
                        except OSError:
                            with sess['sock_lk']:
                                if sess['sock'] is sock:
                                    sess['sock']    = None
                                    sess['expires'] = time.time() + _PTY_SESSION_TTL
                    with sess['buf_lk']:
                        sess['buf'] += raw
                        if len(sess['buf']) > _PTY_BUF_CAP:
                            sess['buf'] = sess['buf'][-_PTY_BUF_CAP:]
                # PTY exited — notify client and clean up.
                sess['stop'].set()
                _pty_drop_session(session_id, sess)
                with sess['sock_lk']:
                    sock = sess['sock']
                if sock:
                    try: _ws_send_raw(sock, b'\r\n\x1b[2m[process exited]\x1b[0m\r\n')
                    except OSError: pass
                    try: sock.shutdown(socket.SHUT_RDWR)
                    except OSError: pass
                sys.stderr.write(f'[pty-ws] PTY exited: {session_id[:8] if session_id else "?"} {cli}\n')

        else:
            import pty as _pty, fcntl, struct as _struct2, termios, select as _select
            master_fd, slave_fd = _pty.openpty()
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ,
                        _struct2.pack('HHHH', rows, cols, 0, 0))
            spawn_argv = [bin_ or cli] + cli_extra_args
            try:
                proc = subprocess.Popen(
                    spawn_argv,
                    stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                    close_fds=True, start_new_session=True,
                    cwd=str(cwd_path), env=agent_env,
                )
            except Exception as exc:
                os.close(slave_fd); os.close(master_fd)
                try: _ws_send_raw(client_sock, f'\r\n\x1b[31mFailed to spawn {cli}: {exc}\x1b[0m\r\n')
                except OSError: pass
                _pty_drop_session(session_id, sess)
                return
            os.close(slave_fd)
            sess['proc']      = proc
            sess['master_fd'] = master_fd

            def pty_to_ws():
                while not sess['stop'].is_set():
                    try:
                        r, _, _ = _select.select([master_fd], [], [], 0.05)
                        if r:
                            data = os.read(master_fd, 4096)
                            if not data:
                                break
                        elif proc.poll() is not None:
                            break
                        else:
                            continue
                    except OSError:
                        break
                    with sess['sock_lk']:
                        sock = sess['sock']
                    if sock:
                        try:
                            _ws_send_raw(sock, data)
                            continue
                        except OSError:
                            with sess['sock_lk']:
                                if sess['sock'] is sock:
                                    sess['sock']    = None
                                    sess['expires'] = time.time() + _PTY_SESSION_TTL
                    with sess['buf_lk']:
                        sess['buf'] += data
                        if len(sess['buf']) > _PTY_BUF_CAP:
                            sess['buf'] = sess['buf'][-_PTY_BUF_CAP:]
                sess['stop'].set()
                _pty_drop_session(session_id, sess)
                try: os.close(master_fd)
                except OSError: pass
                with sess['sock_lk']:
                    sock = sess['sock']
                if sock:
                    try: _ws_send_raw(sock, b'\r\n\x1b[2m[process exited]\x1b[0m\r\n')
                    except OSError: pass
                    try: sock.shutdown(socket.SHUT_RDWR)
                    except OSError: pass
                sys.stderr.write(f'[pty-ws] PTY exited: {session_id[:8] if session_id else "?"} {cli}\n')

        t_out = threading.Thread(target=pty_to_ws, daemon=True)
        t_out.start()

    # ── ws_to_pty — shared for both new and reconnected sessions ────────
    # Reads frames from this WS connection and forwards them to the PTY.
    # On disconnect, detaches the socket from the session WITHOUT killing
    # the PTY so the client can reconnect and resume.
    if _is_win:
        def ws_to_pty():
            nonlocal pending_frame
            _pf, pending_frame = pending_frame, None
            _pf_queue = [_pf] if _pf is not None else []
            while not sess['stop'].is_set():
                if _pf_queue:
                    opcode, payload = _pf_queue.pop(0)
                else:
                    opcode, payload = _ws_recv_frame(client_sock)
                if opcode is None or opcode == 0x8:
                    break
                if opcode == 0x9:   # ping → pong
                    try: client_sock.sendall(struct.pack('!BB', 0x8A, len(payload)) + payload)
                    except OSError: break
                    continue
                if opcode in (0x1, 0x2) and payload:
                    msg = _pty_control_frame(payload)
                    if msg is not None:
                        # Control frame — acted on, then swallowed. A late
                        # 'init' carries API keys and must never be typed
                        # into the CLI; see _pty_control_frame.
                        if isinstance(msg, dict) and msg.get('type') == 'resize':
                            try:
                                c = max(10, min(500, int(msg.get('cols', cols))))
                                r = max(5,  min(200, int(msg.get('rows', rows))))
                                sess['pty_proc'].setwinsize(r, c)
                            except (ValueError, TypeError, OSError):
                                pass
                        continue
                    try:
                        sess['pty_proc'].write(payload.decode('utf-8', errors='replace'))
                    except Exception:
                        break
            # WS dropped — detach socket; PTY keeps running.
            with sess['sock_lk']:
                if sess['sock'] is client_sock:
                    sess['sock']    = None
                    sess['expires'] = time.time() + _PTY_SESSION_TTL
    else:
        def ws_to_pty():
            import fcntl as _fcntl2, struct as _struct3, termios as _termios2
            nonlocal pending_frame
            _pf, pending_frame = pending_frame, None
            _pf_queue = [_pf] if _pf is not None else []
            while not sess['stop'].is_set():
                if _pf_queue:
                    opcode, payload = _pf_queue.pop(0)
                else:
                    opcode, payload = _ws_recv_frame(client_sock)
                if opcode is None or opcode == 0x8:
                    break
                if opcode == 0x9:
                    try: client_sock.sendall(_struct3.pack('!BB', 0x8A, len(payload)) + payload)
                    except OSError: break
                    continue
                if opcode in (0x1, 0x2) and payload:
                    msg = _pty_control_frame(payload)
                    if msg is not None:
                        # Control frame — acted on, then swallowed. A late
                        # 'init' carries API keys and must never be typed
                        # into the CLI; see _pty_control_frame.
                        if isinstance(msg, dict) and msg.get('type') == 'resize':
                            try:
                                c = max(10, min(500, int(msg.get('cols', cols))))
                                r = max(5,  min(200, int(msg.get('rows', rows))))
                                _fcntl2.ioctl(sess['master_fd'], _termios2.TIOCSWINSZ,
                                              _struct3.pack('HHHH', r, c, 0, 0))
                            except (ValueError, TypeError, OSError):
                                pass
                        continue
                    try:
                        os.write(sess['master_fd'], payload)
                    except OSError:
                        break
            with sess['sock_lk']:
                if sess['sock'] is client_sock:
                    sess['sock']    = None
                    sess['expires'] = time.time() + _PTY_SESSION_TTL

    t_in = threading.Thread(target=ws_to_pty, daemon=True)
    t_in.start()
    t_in.join()   # block until this WS connection closes
    if not session_id and not sess['stop'].is_set():
        # No session_id → this session was never put in _PTY_SESSIONS, so
        # the reaper can't see it, /terminal/kill can't address it, and no
        # client can ever reconnect to it. The soft-detach above would
        # leave the spawned CLI process running forever — kill it now.
        sess['stop'].set()
        for k in ('pty_proc', 'proc'):
            try: sess.get(k) and sess[k].terminate()
            except Exception: pass
    sys.stderr.write(f'[pty-ws] WS detached: {session_id[:8] if session_id else "?"} {cli} @ {cwd_path}\n')

def _terminal_status(self):
    """Report CLI availability, runtime environment, and spawn capability."""
    claude_bin = self._claudecode_resolve()
    codex_bin  = self._codex_resolve()
    hermes_bin = self._hermes_resolve()
    gemini_bin = self._gemini_resolve()
    # Spawn is only meaningful on local machines that have a display/GUI.
    spawn_ok = (_RUNTIME_ENV == 'local')
    try:
        import winpty as _wp  # noqa: F401
        pty_ok = True          # Windows + pywinpty installed
    except ImportError:
        # Linux / macOS: stdlib pty is always available
        pty_ok = (sys.platform != 'win32')
    return self._send_json(200, {
        'claude':          bool(claude_bin),
        'claudePath':      claude_bin or '',
        'codex':           bool(codex_bin),
        'codexPath':       codex_bin or '',
        'hermes':          bool(hermes_bin),
        'hermesPath':      hermes_bin or '',
        # hermesVia: how a Projects terminal would reach hermes — 'native'
        # when on PATH here; '' when unavailable (e.g. native Windows, where
        # the supported path is running the whole stack in WSL).
        'hermesVia':       ('native' if hermes_bin else ''),
        'gemini':          bool(gemini_bin),
        'geminiPath':      gemini_bin or '',
        'runtime_env':     _RUNTIME_ENV,
        'spawn_supported': spawn_ok,
        'pty_supported':   pty_ok,
    })

def _terminal_kill(self):
    """Terminate a PTY session NOW, for an explicit "End session" click.

    The reaper's 300s grace (_PTY_SESSION_TTL) exists so a dropped
    WebSocket — a network blip, a mobile client backgrounding the tab —
    doesn't kill a long-running CLI session the user still means to come
    back to. But the frontend's tab-close button used that exact same
    soft-detach path (just closing the socket), so a session the user
    explicitly ended kept its PTY/CLI process alive server-side for up
    to 5 minutes with no way for the client to ask for it sooner — the
    UI's own "End session" label promised something the client had no
    way to actually request. This is the one route that lets it ask.
    """
    qs = urllib.parse.urlparse(self.path).query
    params = urllib.parse.parse_qs(qs)
    session_id = (params.get('session_id') or [''])[0].strip()
    if not session_id:
        return self._send_json(400, {'error': 'session_id required'})
    with _PTY_SESSIONS_LK:
        sess = _PTY_SESSIONS.pop(session_id, None)
    if sess is None:
        # Already reaped, never existed, or not a PTY-backed session
        # (e.g. a non-persistent stream tab) — nothing to do, not an error.
        return self._send_json(200, {'ok': True, 'killed': False})
    sess['stop'].set()
    for k in ('pty_proc', 'proc'):
        try: sess.get(k) and sess[k].terminate()
        except Exception: pass
    with sess['sock_lk']:
        sock = sess.get('sock')
    if sock is not None:
        try: sock.close()
        except Exception: pass
    return self._send_json(200, {'ok': True, 'killed': True})

def _terminal_stream(self):
    """Stream an agentic CLI session scoped to a project directory.

    Body: {messages, cli, cwd, model?, projectName?, authMethod?,
           claudeKey?, codexKey?}
      cli        — 'claude' | 'codex'
      cwd        — absolute path to the project directory
      messages   — [{role, content}] conversation history
      model      — optional model override
      authMethod — 'subscription' | 'apikey' (default varies by cli)
                   'subscription' strips any ANTHROPIC_API_KEY from the
                   subprocess env so the Claude CLI uses its own OAuth
                   credentials (Pro/Max plan).
      claudeKey  — BYOK: client's ANTHROPIC_API_KEY (AES-GCM decrypted client-side)
      codexKey   — BYOK: client's OPENAI_API_KEY (AES-GCM decrypted client-side)
    Server env vars always win over BYOK keys so fleet admins can lock
    the backend. A blank server key lets the client key through.
    SSE output uses the same {choices[0].delta.content} shape as
    /claudecode/stream. delta.type ('text'|'tool'|'error') lets the
    terminal UI colour-code different event kinds.
    """
    length = int(self.headers.get('content-length', 0) or 0)
    try:
        body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return self._send_json(400, {'error': 'bad json'})

    cli      = (body.get('cli') or 'claude').lower().strip()
    cwd      = (body.get('cwd') or '').strip()
    messages = body.get('messages') or []
    model    = (body.get('model') or '').strip()
    auth_method = (body.get('authMethod') or '').strip().lower()
    byok_claude = (body.get('claudeKey') or '').strip()
    byok_codex  = (body.get('codexKey') or '').strip()
    byok_gemini = (body.get('geminiKey') or '').strip()
    # Orchestrator session keys — used to tie multi-turn invocations to
    # the same project + CLI session so context (working dir, prior
    # output) can be threaded through. Logged for trace; future use:
    # pass to `claude --resume <session-id>` to recover stored CLI state.
    session_id  = (body.get('sessionId') or '').strip()[:80]
    project_id  = (body.get('projectId') or '').strip()[:80]

    if cli not in ('claude', 'codex', 'gemini'):
        return self._send_json(400, {'error': 'cli must be "claude", "codex", or "gemini"'})
    if not cwd:
        return self._send_json(400, {'error': 'cwd required'})
    cwd_path = pathlib.Path(_client_path(cwd)).resolve()
    if not cwd_path.is_dir():
        return self._send_json(400, {'error': f'directory not found: {cwd}'})

    history_lines = []
    for m in messages:
        role    = (m.get('role') or 'user').upper()
        content = (m.get('content') or '').strip()
        if content:
            history_lines.append(f'{role}: {content}')
    prompt = '\n\n'.join(history_lines)
    if not prompt:
        return self._send_json(400, {'error': 'no prompt'})

    import copy as _copy
    agent_env = _copy.deepcopy(os.environ)
    for _d in [r'C:\Program Files\Git\usr\bin',
               r'C:\Program Files\Git\bin',
               r'C:\Program Files\Git\mingw64\bin']:
        if os.path.isdir(_d) and _d not in agent_env.get('PATH', ''):
            agent_env['PATH'] = _d + os.pathsep + agent_env.get('PATH', '')

    if cli == 'claude':
        bin_ = self._claudecode_resolve()
        if not bin_:
            return self._send_json(503, {'error': 'claude CLI not found — install Claude Code or set CAFRESOHQ_CLAUDE_BIN'})
        if auth_method == 'subscription':
            # Strip any ANTHROPIC_API_KEY so the CLI falls through to its
            # own OAuth / subscription credentials (Pro/Max plan).
            agent_env.pop('ANTHROPIC_API_KEY', None)
        elif byok_claude and not agent_env.get('ANTHROPIC_API_KEY', '').strip():
            agent_env['ANTHROPIC_API_KEY'] = byok_claude
        cmd = [bin_, '--print',
               '--output-format', 'stream-json',
               '--verbose',
               '--allowed-tools', 'Read,Glob,Grep,Bash,Edit,Write,WebFetch,WebSearch',
               '--add-dir', str(cwd_path),
               '--input-format', 'text']
        if model:
            cmd += ['--model', model]
    elif cli == 'gemini':
        bin_ = self._gemini_resolve()
        if not bin_:
            return self._send_json(503, {'error': 'gemini CLI not found — npm i -g @google/gemini-cli or set CAFRESOHQ_GEMINI_BIN'})
        # Auth mirrors the PTY path: 'subscription' = the gemini CLI's own
        # Google login (stored creds), otherwise inject the BYOK key into
        # GEMINI_API_KEY/GOOGLE_API_KEY (both lookups the CLI honours).
        if auth_method == 'subscription':
            agent_env.pop('GEMINI_API_KEY', None)
            agent_env.pop('GOOGLE_API_KEY', None)
        elif byok_gemini and not agent_env.get('GEMINI_API_KEY', '').strip():
            agent_env['GEMINI_API_KEY'] = byok_gemini
            agent_env.setdefault('GOOGLE_API_KEY', byok_gemini)
        # Non-interactive one-shot: `--prompt` runs once and exits, printing
        # the answer to stdout. `--yolo` auto-approves tool calls so the
        # agent can actually read/edit files in the project dir (parity with
        # claude --print's fixed allowed-tools); the project cwd scopes it.
        # The prompt goes in argv (not stdin) — gemini reads --prompt, so we
        # skip the stdin write below for it.
        cmd = [bin_, '--yolo', '--prompt', prompt]
        if model:
            cmd += ['--model', model]
    else:
        bin_ = self._codex_resolve()
        if not bin_:
            return self._send_json(503, {'error': 'codex CLI not found — npm i -g @openai/codex or set CAFRESOHQ_CODEX_BIN'})
        path_key = next((k for k in agent_env.keys() if k.lower() == 'path'),
                        'Path' if sys.platform == 'win32' else 'PATH')
        path_value = agent_env.get(path_key, '')
        path_value = os.pathsep.join(
            p for p in path_value.split(os.pathsep)
            if p and r'\.codex\tmp\arg0' not in p.lower()
        )
        for _k in [k for k in list(agent_env.keys()) if k.lower() == 'path']:
            agent_env.pop(_k, None)
        # Same POSIX case-sensitivity trap as drivers/codex.py: hardcoding
        # 'Path' erased PATH for the codex child on macOS/Linux.
        agent_env[path_key] = path_value
        agent_env.pop('OPENAI_BASE_URL', None)

        if byok_codex and not agent_env.get('OPENAI_API_KEY', '').strip():
            agent_env['OPENAI_API_KEY'] = byok_codex
            cmd = [bin_, 'exec', '--json', '--skip-git-repo-check',
                   '--sandbox', 'workspace-write', '-C', str(cwd_path),
                   '-c', 'model_provider="openai"',
                   '-c', 'approval_policy="untrusted"']
            if model:
                cmd += ['--model', model]
        else:
            # Codex → OpenAI directly (OPENAI_API_KEY); no base_url override.
            wire_model = model or 'gpt-4.1'
            cmd = [bin_, 'exec', '--json', '--skip-git-repo-check',
                   '--sandbox', 'workspace-write', '-C', str(cwd_path),
                   '-c', 'model_provider="openai"',
                   '-c', 'approval_policy="untrusted"']
            cmd += ['--model', wire_model]

    sys.stderr.write(
        f'[terminal] cli={cli} cwd={cwd_path} model={model or "(default)"}'
        f' auth={auth_method or "auto"} session={session_id[:8] or "-"}'
        f' project={project_id[:12] or "-"}'
        f' byok_claude={bool(byok_claude)} byok_codex={bool(byok_codex)}\n'
    )
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, bufsize=1, encoding='utf-8',
            cwd=str(cwd_path),
            env=agent_env,
        )
    except (FileNotFoundError, OSError) as e:
        return self._send_json(500, {'error': f'spawn {cli}: {e}'})

    # claude/codex read the prompt on stdin; gemini gets it in argv (--prompt)
    # so we just close its stdin to signal no interactive input.
    try:
        if cli != 'gemini':
            proc.stdin.write(prompt)
        proc.stdin.close()
    except Exception as e:
        try: proc.kill()
        except Exception: pass
        return self._send_json(500, {'error': f'stdin: {e}'})

    self.send_response(200)
    self.send_header('content-type', 'text/event-stream')
    self.send_header('cache-control', 'no-store')
    self.end_headers()

    def write_sse(obj):
        try:
            self.wfile.write(b'data: ' + json.dumps(obj).encode('utf-8') + b'\n\n')
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return False
        return True

    def sse_delta(content, type_='text'):
        return write_sse({'choices': [{'index': 0, 'delta': {'content': content, 'type': type_}}]})

    stderr_buf = []
    def _drain_err():
        try:
            for line in proc.stderr:
                stderr_buf.append(line)
        except Exception:
            pass
    threading.Thread(target=_drain_err, daemon=True).start()

    in_tokens = out_tokens = 0

    if cli == 'claude':
        # The claude branch is the third of three CLIs streamed by this
        # function, and it was the one that never learned what the other two
        # know: a turn that ends badly has to SAY so. `text_emitted` and the
        # latched `err` below are the gemini/codex arms' own two variables,
        # spelled the same way, so the tail can reach exactly one verdict.
        text_emitted = False
        err = ''
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line: continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = ev.get('type')
                if t == 'assistant':
                    msg = ev.get('message') or {}
                    for block in (msg.get('content') or []):
                        btype = block.get('type')
                        if btype == 'text':
                            text = block.get('text') or ''
                            if text:
                                text_emitted = True
                                ok = sse_delta(text, 'text')
                                if not ok: break
                        elif btype == 'tool_use':
                            name  = block.get('name') or 'tool'
                            inp   = block.get('input') or {}
                            inp_s = json.dumps(inp, ensure_ascii=False)
                            if len(inp_s) > 240: inp_s = inp_s[:240] + '…'
                            text_emitted = True
                            sse_delta(f'\n⚙ {name}: {inp_s}\n', 'tool')
                    u = msg.get('usage')
                    if u:
                        in_tokens  = u.get('input_tokens', in_tokens)
                        out_tokens = u.get('output_tokens', out_tokens)
                elif t == 'result':
                    u = ev.get('usage') or {}
                    in_tokens  = u.get('input_tokens', in_tokens)
                    out_tokens = u.get('output_tokens', out_tokens)
                    # The CLI's own verdict, and the only place it states one:
                    # `subtype` is 'success' on a clean finish and names the
                    # failure otherwise ('error_max_turns',
                    # 'error_during_execution'), with `is_error` saying the
                    # same as a bool. drivers/claude_code.py reads both; this
                    # copy of the same parser read neither, so a turn the CLI
                    # itself declared failed reached the tail below looking
                    # exactly like a finished one.
                    sub = str(ev.get('subtype') or '')
                    if ev.get('is_error') or (sub and sub != 'success'):
                        err = (str(ev.get('result') or '').strip()
                               or sub or 'the CLI reported a failed turn')
                elif t == 'error':
                    # In-band failure frame. Latched rather than printed
                    # inline and then forgotten, so the tail below is the one
                    # place this turn's outcome is decided.
                    err = str(ev.get('message') or ev)
                    break
            if in_tokens or out_tokens:
                write_sse({'choices': [], 'usage': {
                    'prompt_tokens': in_tokens,
                    'completion_tokens': out_tokens,
                    'total_tokens': in_tokens + out_tokens,
                }})
        finally:
            try: proc.wait(timeout=2)
            except Exception:
                try: proc.kill()
                except Exception: pass
            rc = proc.returncode
            stderr_text = ''.join(stderr_buf).strip()
            # `and not (in_tokens or out_tokens)` used to sit on the end of
            # this test, and it is the whole bug: claude's stream-json puts
            # `usage` on the FIRST assistant message, so in_tokens is set for
            # any turn that produced anything at all. A turn that streamed
            # half a paragraph and then died — OOM, a kill, a PreToolUse
            # refusal, a dropped upstream socket — exited non-zero with usage
            # already counted and the marker was suppressed. delta.type
            # 'error' is the ONLY signal the terminal has that a turn failed;
            # without it the truncated text reads as a delivered reply. Same
            # test the gemini and codex arms of this function have always
            # used, and the same one drivers/claude_code.py was corrected to.
            if err:
                sse_delta(f'\n⚠ claude: {err[:600]}\n', 'error')
            elif rc and rc not in (0, None):
                sse_delta(f'\n⚠ claude exited {rc}: '
                          f'{stderr_text[:600] or "(no stderr)"}\n', 'error')
            elif not text_emitted:
                sse_delta(f'\n⚠ claude returned no content — '
                          f'{stderr_text[:300] or "the CLI printed nothing"}\n', 'error')

    elif cli == 'gemini':
        # Gemini CLI (`--prompt … --yolo`) prints its answer as plain text to
        # stdout (it may interleave a little ANSI for spinners). Stream it
        # straight through as 'text', stripping escape sequences so the chat
        # bubble stays clean. No token usage is reported by the CLI.
        _ansi_re = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')
        text_emitted = False
        try:
            while True:
                chunk = proc.stdout.read(256)
                if not chunk:
                    break
                clean = _ansi_re.sub('', chunk)
                if clean:
                    text_emitted = True
                    if not sse_delta(clean, 'text'):
                        break
        finally:
            try: proc.wait(timeout=2)
            except Exception:
                try: proc.kill()
                except Exception: pass
            rc = proc.returncode
            stderr_text = ''.join(stderr_buf).strip()
            if rc and rc not in (0, None):
                sse_delta(f'\n⚠ gemini exited {rc}: {stderr_text[:300] or "(no stderr)"}\n', 'error')
            elif not text_emitted:
                hint = stderr_text[:300] or 'is the gemini CLI logged in? run it once in PTY mode to authenticate'
                sse_delta(f'\n⚠ gemini returned no content — {hint}\n', 'error')
            try: self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError): pass

    else:  # codex
        def _content_text(value):
            if value is None: return ''
            if isinstance(value, str): return value
            if isinstance(value, list):
                return ''.join(
                    (b if isinstance(b, str) else
                     b.get('text') or b.get('content') or b.get('output_text') or '')
                    for b in value
                )
            if isinstance(value, dict):
                return (value.get('text') or value.get('content')
                        or value.get('message') or '')
            return ''

        item_text_seen = {}
        events_seen = 0
        text_emitted = False
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line: continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                events_seen += 1
                t = ev.get('type', '')
                if t in ('agent_message', 'message'):
                    text = _content_text(ev.get('content') or ev.get('message') or '')
                    if text:
                        text_emitted = True
                        sse_delta(text, 'text')
                elif t in ('agent_message_delta', 'message_delta', 'response.output_text.delta'):
                    text = str(ev.get('delta') or ev.get('text') or ev.get('content') or '')
                    if text:
                        text_emitted = True
                        sse_delta(text, 'text')
                elif t in ('item.updated', 'item.completed'):
                    item = ev.get('item') or {}
                    item_type = item.get('type', '')
                    if item_type == 'error':
                        msg = item.get('message') or item.get('text') or json.dumps(item)
                        if not ('disallowed by requirements' in msg
                                or 'falling back to required value' in msg):
                            text_emitted = True
                            sse_delta(f'\n⚠ Codex: {msg}\n', 'error')
                    elif (item.get('role') == 'assistant'
                          or item_type in ('message', 'agent_message')):
                        text = (item.get('text')
                                or _content_text(item.get('content') or item.get('message')))
                        item_id = item.get('id') or ev.get('item_id') or 'assistant'
                        prior = item_text_seen.get(item_id, '')
                        delta = (text[len(prior):]
                                 if text and text.startswith(prior)
                                 else (text if text != prior else ''))
                        item_text_seen[item_id] = text or prior
                        if delta:
                            text_emitted = True
                            sse_delta(delta, 'text')
                elif t in ('turn.completed', 'response.completed'):
                    text = _content_text(
                        ev.get('last_agent_message') or ev.get('message') or '')
                    if text:
                        text_emitted = True
                        sse_delta(text, 'text')
                elif t == 'function_call':
                    fname  = ev.get('name') or ev.get('function') or 'tool'
                    args   = ev.get('arguments') or ev.get('input') or {}
                    cmd_s  = ((args.get('cmd') or args.get('command') or json.dumps(args))
                              if isinstance(args, dict) else str(args))
                    text_emitted = True
                    sse_delta(f'\n⚙ {fname}: {cmd_s}\n', 'tool')
                elif t in ('error', 'turn.failed'):
                    msg = (ev.get('message')
                           or (ev.get('error') or {}).get('message')
                           or str(ev))
                    text_emitted = True
                    sse_delta(f'\n⚠ Codex error: {msg}\n', 'error')
        finally:
            try: proc.wait(timeout=2)
            except Exception:
                try: proc.kill()
                except Exception: pass
            rc = proc.returncode
            stderr_text = ''.join(stderr_buf).strip()
            if rc and rc not in (0, None):
                sse_delta(f'\n⚠ Codex exited {rc}: {stderr_text[:300] or "(no stderr)"}\n', 'error')
            elif not text_emitted:
                sse_delta(f'\n⚠ Codex returned no content (exit {rc})\n', 'error')
            try: self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError): pass

