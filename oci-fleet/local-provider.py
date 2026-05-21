"""
LocalProvider — manages WSL+ttyd terminal sessions on the Hyper-V host.

Each session starts a ttyd.exe process that wraps a WSL command, exposing
it as a web terminal on a dynamically-allocated port.  The port is then
reverse-proxied through Caddy as /stream/<session_id>/ so the SvelteKit
shell can embed it in an iframe.
"""
import subprocess
import threading
import logging
import time

logger = logging.getLogger(__name__)


class LocalProvider:
    def __init__(self, config=None):
        self.config = config or {}
        self.base_port = int(self.config.get('base_port', 7680))
        self.wsl_distro = self.config.get('wsl_distro', 'Ubuntu')
        self.ttyd_path = self.config.get('ttyd_path', 'C:\\CafresoAI\\ttyd.exe')
        self._sessions = {}   # session_id -> {port, process, template_id, command}
        self._lock = threading.Lock()
        self._used_ports = set()

    # ── Port allocation ───────────────────────────────────────────────────────

    def _alloc_port(self) -> int:
        with self._lock:
            port = self.base_port
            while port in self._used_ports:
                port += 1
            self._used_ports.add(port)
            return port

    def _free_port(self, port: int):
        with self._lock:
            self._used_ports.discard(port)

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def launch(self, session_id: str, template: dict) -> int:
        """Start a ttyd process wrapping a WSL command.

        Returns the localhost port that ttyd is listening on.
        Raises RuntimeError if ttyd.exe cannot be started.
        """
        command = template.get('wsl_command', 'bash')
        distro  = template.get('wsl_distro', self.wsl_distro)
        title   = template.get('name', 'Terminal')
        port    = self._alloc_port()

        args = [
            self.ttyd_path,
            '-p', str(port),
            '-W',                          # writable (allow user input)
            '--title-format', f'CafresoAI – {title}',
            'wsl', '-d', distro, '--', 'bash', '-lc', command,
        ]

        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            self._free_port(port)
            raise RuntimeError(f'Failed to start ttyd: {e}') from e

        with self._lock:
            self._sessions[session_id] = {
                'port':        port,
                'process':     proc,
                'template_id': template.get('id', ''),
                'command':     command,
                'distro':      distro,
            }

        logger.info('[local] launched %s → ttyd :%d (%s)', session_id, port, command)
        return port

    def stop(self, session_id: str) -> bool:
        """Terminate the ttyd process for session_id.  Returns True if found."""
        with self._lock:
            s = self._sessions.pop(session_id, None)
        if not s:
            return False

        try:
            s['process'].terminate()
            s['process'].wait(timeout=5)
        except Exception:
            try:
                s['process'].kill()
            except Exception:
                pass

        self._free_port(s['port'])
        logger.info('[local] stopped %s', session_id)
        return True

    def is_alive(self, session_id: str) -> bool:
        """Return True if the session's ttyd process is still running."""
        with self._lock:
            s = self._sessions.get(session_id)
        return s is not None and s['process'].poll() is None

    def get_port(self, session_id: str) -> int | None:
        """Return the ttyd port for session_id, or None if unknown."""
        with self._lock:
            s = self._sessions.get(session_id)
        return s['port'] if s else None

    def list_sessions(self) -> list[str]:
        """Return list of active session IDs managed by this provider."""
        with self._lock:
            return list(self._sessions.keys())
