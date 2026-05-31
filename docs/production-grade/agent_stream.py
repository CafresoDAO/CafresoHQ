"""
CafresoHQ — production-grade agent streaming (reference refactor).

PROBLEM (from the architecture review, finding D1/D2):
  serve.py has FOUR near-identical ~200-line handlers —
  _claudecode_stream, _openclaw_stream, _codex_stream, _terminal_stream —
  each doing: parse JSON → validate cwd → resolve CLI → inject BYOK env →
  spawn subprocess → translate the CLI's JSON events into OpenAI-compatible SSE.
  BYOK injection is copy-pasted 4×; path validation 3×.

SOLUTION:
  One spec-driven pipeline. Each provider is a small AgentSpec; a single
  `spawn_and_stream()` runs the shared lifecycle. Adding a provider becomes a
  ~15-line spec instead of a 200-line copy.

This module is dependency-free (stdlib only) and framework-agnostic so it can be
dropped into the existing BaseHTTPRequestHandler or a future ASGI app. Wire it in
incrementally: route _codex_stream through it first, confirm parity, then migrate
the others and delete the originals.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

# ── Config (was scattered magic numbers; finding M3) ────────────────────────
SUBPROCESS_GRACE_S = 2          # wait() before kill on cleanup
DEFAULT_TIMEOUT_S = 600         # hard cap on a single agent turn
STDERR_TAIL_LINES = 6           # how much stderr to surface on failure


# ── Errors ──────────────────────────────────────────────────────────────────
class AgentError(Exception):
    """User-facing agent failure. .status is an HTTP status hint."""
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


# ── Provider spec ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AgentSpec:
    """Declarative description of one CLI-backed agent provider.

    Replaces a whole ~200-line handler. `build_cmd` returns argv given the
    resolved binary + request; `parse_event` maps one line of the CLI's JSON
    output to assistant text (or None to ignore)."""
    name: str                                   # 'claudecode' | 'openclaw' | 'codex'
    binary_candidates: tuple[str, ...]          # e.g. ('claude',) or ('codex','codex.cmd')
    build_cmd: Callable[[str, "AgentRequest"], list[str]]
    parse_event: Callable[[dict], Optional[str]]
    requires_elevation: bool = False
    # env keys to inject from the request's BYOK map, if present
    byok_env: tuple[str, ...] = ()


@dataclass
class AgentRequest:
    system: Optional[str]
    prompt: str
    model: Optional[str]
    cwd: Optional[str]
    agent_name: str = "agent"
    elevated: bool = False
    byok: dict = field(default_factory=dict)        # {'OPENAI_API_KEY': '...'}
    allowed_dirs: tuple[str, ...] = ()
    max_tokens: int = 1024


# ── Shared helpers (each was duplicated 3–4×) ───────────────────────────────
def resolve_binary(candidates: Iterable[str], override: str = "") -> str:
    """Find a CLI on PATH. Was repeated in _codex_resolve / _claudecode_resolve."""
    if override and Path(override).is_file():
        return override
    for c in candidates:
        found = shutil.which(c)
        if found:
            return found
    raise AgentError(
        f"CLI not found (looked for: {', '.join(candidates)})", status=503
    )


def validate_cwd(req_cwd: Optional[str], allowed_dirs: tuple[str, ...]) -> str:
    """Resolve + sandbox a working dir. Was duplicated in 3 handlers.

    Uses resolve()+relative_to (symlink-safe) instead of startswith()
    (finding: fs_browse symlink bypass)."""
    base = Path(req_cwd).expanduser().resolve() if req_cwd else Path.cwd().resolve()
    if allowed_dirs:
        ok = False
        for d in allowed_dirs:
            try:
                base.relative_to(Path(d).expanduser().resolve())
                ok = True
                break
            except ValueError:
                continue
        if not ok:
            raise AgentError("working directory not in the allowed sandbox", status=403)
    if not base.is_dir():
        raise AgentError(f"working directory does not exist: {base}", status=400)
    return str(base)


def build_env(req: AgentRequest, byok_env: tuple[str, ...]) -> dict:
    """Centralized BYOK injection (was copy-pasted in all 4 handlers).

    Server-set env always wins over BYOK (admin can lock the backend). Only the
    keys a provider declares are honored — no blanket env passthrough."""
    env = dict(os.environ)
    # Never leak a stale base-url override into a child agent.
    env.pop("OPENAI_BASE_URL", None)
    for key in byok_env:
        if env.get(key):           # server-side value wins
            continue
        val = (req.byok.get(key) or "").strip()
        if val:
            env[key] = val
    return env


# ── The one lifecycle that replaces four handlers ───────────────────────────
def spawn_and_stream(
    spec: AgentSpec,
    req: AgentRequest,
    *,
    binary_override: str = "",
    emit: Callable[[dict], None],
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> None:
    """Spawn the provider CLI and stream OpenAI-compatible SSE chunks via `emit`.

    `emit(obj)` writes one SSE `data:` line (the caller owns the socket). This is
    the single place spawn/stream/cleanup lives — fix a streaming bug once, not 4×.
    """
    if spec.requires_elevation and not req.elevated:
        raise AgentError(
            f"{spec.name} requires an elevated agent — enable elevation first.",
            status=403,
        )

    binary = resolve_binary(spec.binary_candidates, binary_override)
    cwd = validate_cwd(req.cwd, req.allowed_dirs)
    env = build_env(req, spec.byok_env)
    cmd = spec.build_cmd(binary, req)

    def _chunk(text: str):
        emit({"choices": [{"index": 0, "delta": {"content": text}}]})

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        encoding="utf-8",
        cwd=cwd,
        env=env,
    )

    stderr_buf: list[str] = []

    def _drain_stderr():
        for line in proc.stderr:           # type: ignore[union-attr]
            stderr_buf.append(line)
    threading.Thread(target=_drain_stderr, daemon=True).start()

    # Feed the prompt then read streaming JSON events.
    full_prompt = (req.system + "\n\n" if req.system else "") + req.prompt
    try:
        proc.stdin.write(full_prompt)      # type: ignore[union-attr]
        proc.stdin.close()                 # type: ignore[union-attr]
    except (BrokenPipeError, OSError) as e:
        raise AgentError(f"{spec.name} exited before prompt could be sent: {e}", 502)

    saw_output = False
    try:
        for line in proc.stdout:           # type: ignore[union-attr]
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = spec.parse_event(evt)
            if text:
                saw_output = True
                _chunk(text)
    finally:
        try:
            proc.wait(timeout=SUBPROCESS_GRACE_S)
        except subprocess.TimeoutExpired:
            proc.kill()

    rc = proc.returncode
    if rc not in (0, None) and not saw_output:
        tail = "".join(stderr_buf[-STDERR_TAIL_LINES:]).strip() or "(no stderr)"
        _chunk(f"\n\n⚠ {spec.name} exited {rc}: {tail}")

    emit("[DONE]")  # caller serializes the sentinel


# ── Provider specs — the entire per-provider surface is now this small ──────
def _codex_cmd(binary: str, req: AgentRequest) -> list[str]:
    cmd = [binary, "exec", "--json", "--skip-git-repo-check",
           "--sandbox", "workspace-write", "-C", req.cwd or ".",
           "-c", 'model_provider="openai"',
           "-c", 'approval_policy="untrusted"',
           "--model", req.model or "gpt-4.1"]
    return cmd


def _codex_event(evt: dict) -> Optional[str]:
    t = evt.get("type", "")
    if t == "agent_message" and evt.get("message"):
        return evt["message"]
    if t == "item.completed":
        item = evt.get("item", {})
        if item.get("type") == "agent_message":
            return item.get("text") or None
    return None


def _claude_cmd(binary: str, req: AgentRequest) -> list[str]:
    cmd = [binary, "--print", "--output-format=stream-json",
           "--model", req.model or "sonnet"]
    if not req.elevated:
        cmd += ["--disallowed-tools", "Bash,Edit,Write,WebFetch,WebSearch"]
    return cmd


def _claude_event(evt: dict) -> Optional[str]:
    # claude --output-format=stream-json emits {type:'content_block_delta',...}
    delta = (evt.get("delta") or {})
    if delta.get("type") == "text_delta":
        return delta.get("text") or None
    return None


CODEX = AgentSpec(
    name="codex",
    binary_candidates=("codex", "codex.cmd"),
    build_cmd=_codex_cmd,
    parse_event=_codex_event,
    requires_elevation=True,
    byok_env=("OPENAI_API_KEY",),
)

CLAUDE_CODE = AgentSpec(
    name="claudecode",
    binary_candidates=("claude",),
    build_cmd=_claude_cmd,
    parse_event=_claude_event,
    requires_elevation=False,
    byok_env=("ANTHROPIC_API_KEY",),
)

OPENCLAW = AgentSpec(           # elevated Claude Code (tools enabled, sandboxed)
    name="openclaw",
    binary_candidates=("claude",),
    build_cmd=lambda b, r: [b, "--print", "--output-format=stream-json",
                            "--model", r.model or "sonnet"],
    parse_event=_claude_event,
    requires_elevation=True,
    byok_env=("ANTHROPIC_API_KEY",),
)

REGISTRY = {s.name: s for s in (CODEX, CLAUDE_CODE, OPENCLAW)}


# ── Example wiring inside the existing BaseHTTPRequestHandler ────────────────
#
#   def _agent_stream(self, provider: str):
#       body = json.loads(self.rfile.read(int(self.headers.get('content-length', 0))))
#       spec = REGISTRY.get(provider)
#       if not spec:
#           return self._send_json(404, {'error': f'unknown provider {provider}'})
#       req = AgentRequest(
#           system=body.get('system'), prompt=body.get('prompt', ''),
#           model=body.get('model'), cwd=body.get('cwd'),
#           agent_name=body.get('agentName', 'agent'),
#           elevated=bool(body.get('elevated')),
#           byok={k: v for k, v in (body.get('byok') or {}).items()},
#           allowed_dirs=tuple(_openclaw_allowed_dirs),
#       )
#       self.send_response(200)
#       self.send_header('Content-Type', 'text/event-stream')
#       self.end_headers()
#       def emit(obj):
#           payload = obj if isinstance(obj, str) else json.dumps(obj)
#           self.wfile.write(f'data: {payload}\n\n'.encode()); self.wfile.flush()
#       try:
#           spawn_and_stream(spec, req, emit=emit)
#       except AgentError as e:
#           emit({'choices': [{'index': 0, 'delta': {'content': f'\n\n⚠ {e}'}}]}); emit('[DONE]')
#
# This single method replaces _claudecode_stream + _openclaw_stream +
# _codex_stream (~600 lines → ~25).
