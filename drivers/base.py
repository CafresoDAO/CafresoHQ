"""Driver contract — the ONE interface every agent runtime sits behind.

Spec: docs/DRIVER_CONTRACT.md. The app (serve.py routes, the office animation
layer, usage metering, the approval flow) consumes only this surface; each
backend translates its native behavior into it. Adding a backend = writing one
module in this package, registering it in __init__.py, and nothing else.

Stdlib-only on purpose: drivers ship inside the serve.py container image and
must import with zero extra dependencies.
"""
import threading
import uuid


# ── Canonical event schema (DRIVER_CONTRACT.md §1.3) ─────────────────────────
# Events are plain dicts with an 'event' discriminator so they serialize to
# JSONL/SSE without a class layer. Constructors below are the single source of
# truth for payload shapes — drivers must emit through them, never hand-roll
# dicts, so a schema change is one edit.

def ev_status(state):
    # state: 'starting' | 'thinking' | 'working'
    return {'event': 'status', 'state': state}

def ev_token(text):
    return {'event': 'token', 'text': text}

def ev_tool_call(call_id, name, args, needs_approval=False):
    return {'event': 'tool_call', 'id': call_id, 'name': name,
            'args': args, 'needsApproval': bool(needs_approval)}

def ev_tool_result(call_id, ok, summary=''):
    return {'event': 'tool_result', 'id': call_id, 'ok': bool(ok),
            'summary': summary}

def ev_artifact(name, mime='', ref=''):
    return {'event': 'artifact', 'name': name, 'mime': mime, 'ref': ref}

def ev_usage(in_tokens, out_tokens, cost_hint=''):
    return {'event': 'usage', 'inTokens': int(in_tokens or 0),
            'outTokens': int(out_tokens or 0), 'costHint': cost_hint}

def ev_error(message, recoverable=False):
    return {'event': 'error', 'message': str(message)[:600],
            'recoverable': bool(recoverable)}

def ev_done(summary=''):
    return {'event': 'done', 'summary': summary}


class TaskHandle:
    """Opaque per-task handle returned by start_task(). The host holds it only
    to pass back into events()/cancel(); everything on it is driver-private
    except `id`. Cancellation is cooperative: cancel() sets the flag and the
    driver's events() loop is responsible for tearing down promptly."""
    def __init__(self):
        self.id = 'task_' + uuid.uuid4().hex[:12]
        self.cancelled = threading.Event()
        self.proc = None          # subprocess.Popen for kind='cli' drivers
        self.private = {}         # anything else the driver needs to stash


class Driver:
    """Abstract driver. Subclasses set MANIFEST (DRIVER_CONTRACT.md §1.1) and
    implement the five lifecycle calls (§1.2).

    Task dict accepted by start_task() — hosts pass only what applies:
      prompt      str   — ready-to-send prompt, OR
      messages    list  — [{role, content}] chat history the driver flattens
      system      str   — system prompt (host composes policy/guard text)
      model       str   — model id, driver-native ('' = runtime default)
      cwd         str   — working dir, ALREADY validated by the host
      tools       list  — allowed tool names; empty/absent = tools disabled
      addDirs     list  — dirs the agent may touch, ALREADY validated
      agentName   str   — display name, for audit lines
    Path/allowlist validation is the HOST's job (serve.py) — drivers trust
    task fields and never widen them.
    """
    MANIFEST = {}   # subclasses override; shape per DRIVER_CONTRACT.md §1.1

    def detect(self, probe_version=False):
        """{installed, authenticated, auth, version, detail} — file/PATH checks
        only unless probe_version (which may spawn `<bin> --version`)."""
        raise NotImplementedError

    def configure(self, settings):
        """Driver-private settings (e.g. {'binary': path}). Returns detect()."""
        raise NotImplementedError

    def start_task(self, task):
        """Begin a task, return a TaskHandle. Raises DriverError on refusal."""
        raise NotImplementedError

    def events(self, handle):
        """Generator of contract events for the handle. Terminates with either
        ev_done or ev_error; never raises through to the host."""
        raise NotImplementedError

    def cancel(self, handle):
        handle.cancelled.set()
        proc = handle.proc
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass


class DriverError(Exception):
    """Refusal with an HTTP-ish status the host can map onto a response."""
    def __init__(self, message, status=500):
        super().__init__(message)
        self.status = status
