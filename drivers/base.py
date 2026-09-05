"""Driver contract — the ONE interface every agent runtime sits behind.

Spec: docs/DRIVER_CONTRACT.md. The app (serve.py routes, the office animation
layer, usage metering, the approval flow) consumes only this surface; each
backend translates its native behavior into it. Adding a backend = writing one
module in this package, registering it in __init__.py, and nothing else.

Stdlib-only on purpose: drivers ship inside the serve.py container image and
must import with zero extra dependencies.
"""
import subprocess
import threading
import uuid


def probe_cli(bin_, timeout=6):
    """(version, problem, detail) from `<bin> --version`.

    Shared by every kind='cli' driver's detect(probe_version=True).

    This used to return `stdout or stderr` without ever looking at the
    return code, so a CLI that ran and CRASHED reported its crash as its
    version. Measured on a real machine: the Codex shim was on PATH but its
    vendored binary was gone, `codex --version` exited 1 printing

        Error: spawn .../vendor/aarch64-apple-darwin/codex/codex ENOENT

    and detect() handed that back as the version. Every surface downstream
    reads detect() as proof the thing is fine, so the front desk offered
    Codex as found-and-ready and told the boss it merely needed a sign-in.
    A failed probe became a wrong diagnosis.

    `problem` is a bare PREDICATE — "will not start", not "it is installed
    but will not start" — because two different surfaces build a sentence
    around it and each already supplies its own subject and contrast. The
    first draft embedded both here and rendered "Codex is on this machine,
    but it is installed but will not start", which is what happens when a
    string tries to be a sentence in a place it cannot see. `detail` is the
    first line the command actually printed, kept for a tooltip so the
    person who can fix it has something to search for; §6 keeps that wire
    text out of the sentence and in the tooltip.
    """
    if not bin_:
        return '', '', ''
    try:
        r = subprocess.run([bin_, '--version'], capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return '', 'did not respond', ''
    except Exception as e:
        return '', 'will not start', str(e)[:120]
    first = ((r.stdout or r.stderr or '').strip().splitlines() or [''])[0][:120]
    if r.returncode != 0:
        return '', 'will not start', first
    return first[:80], '', ''


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
      limits      dict  — {'maxTokens': int} caps drivers honor best-effort
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
    """Refusal with an HTTP-ish status the host can map onto a response.

    upstream / retry_after carry the provider's own HTTP status and
    Retry-After header (when the failure came from an upstream API), so
    unattended callers like night_runner can apply a precise 429/5xx retry
    policy instead of pattern-matching error strings."""
    def __init__(self, message, status=500, upstream=None, retry_after=None):
        super().__init__(message)
        self.status = status
        self.upstream = upstream
        self.retry_after = retry_after


def run_task_text(driver, task):
    """Run a task to completion, non-streaming: returns (text, usage) where
    usage = {'inTokens', 'outTokens'}. For callers that want an answer, not a
    stream (night_runner, future cron/search jobs). Raises DriverError when
    the driver ends in error having produced no text."""
    handle = driver.start_task(task)
    parts, usage, err = [], {'inTokens': 0, 'outTokens': 0}, None
    try:
        for ev in driver.events(handle):
            k = ev['event']
            if k == 'token':
                parts.append(ev['text'])
            elif k == 'usage':
                usage = {'inTokens': ev['inTokens'], 'outTokens': ev['outTokens']}
            elif k == 'error':
                err = ev['message']
    finally:
        driver.cancel(handle)
    text = ''.join(parts)
    if not text and err:
        raise DriverError(err, status=502)
    if err:
        # A stream that failed AFTER some text is the dangerous case: this
        # returned the half-answer with no exception and no mark, so an
        # unattended caller (night_runner) filed a reply that stops
        # mid-sentence as the finished deliverable. Raising would throw the
        # text away, so mark where it stops instead — same shape the browser
        # reader uses for a truncated turn.
        text = text.rstrip() + f'\n\n⚠ stopped early: {err}'
    return text, usage
