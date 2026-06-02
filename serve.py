#!/usr/bin/env python3
import sys as _sys
if hasattr(_sys.stdout, 'reconfigure'):
    _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    _sys.stderr.reconfigure(encoding='utf-8', errors='replace')
"""Serve Openclaw HQ static files and proxy local LM Studio / Ollama / Brave / Vault.

Same-origin proxy avoids browser CORS. SSE streams pass through unbuffered.
Brave proxy:  /brave/search?q=...   forwards to api.search.brave.com with the
caller's X-Brave-Key header rewritten to X-Subscription-Token.
Vault proxy:  /vault/*              read/write Markdown notes under a configured
root directory. Root set via OPENCLAW_VAULT env or POST /vault/configure.
"""
import base64
import hashlib
import http.client
import http.server
import json
import os
import pathlib
import re
import secrets
import select
import socket
import shlex
import shutil
import socketserver
import ssl
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

PORT = 8787
ROUTES = {
    '/lmstudio/': ('10.0.0.100', 1234),
    '/ollama/':   ('localhost', 11434),
}

# Hermes Agent (Nous Research) — the per-container `hermes gateway` exposes an
# OpenAI-compatible API server (enable via ~/.hermes/.env:
# API_SERVER_ENABLED=true, API_SERVER_KEY=…). We proxy /hermes/* → that server,
# injecting the Bearer key server-side so it never reaches the browser, and
# metering the OpenAI `usage` object for per-principal billing. Not in ROUTES
# because it needs the dedicated _hermes_proxy (auth injection + usage tap).
HERMES_HOST = os.environ.get('HERMES_API_HOST', '127.0.0.1')
HERMES_PORT = int(os.environ.get('HERMES_API_PORT', '8642') or '8642')

# ── Idle tracking (powers fleet reap-idle → stop idle containers, free A1 pool) ─
# Single-slot list so the request handler can mutate it without `global`.
# /idle, /health, and /idle's own polls do NOT count as activity.
_LAST_ACTIVITY = [time.time()]
_IDLE_EXEMPT_PREFIXES = ('/idle', '/health')

def _touch_activity(path):
    if not any(path == p or path.startswith(p) for p in _IDLE_EXEMPT_PREFIXES):
        _LAST_ACTIVITY[0] = time.time()

HOP_HEADERS = {'host', 'connection', 'keep-alive', 'proxy-authenticate',
               'proxy-authorization', 'te', 'trailers', 'transfer-encoding',
               'upgrade', 'content-length'}
# Claude Code (Pro/Max subscription) — invoked as a subprocess so the user's
# already-authenticated CLI does the auth. Path is overridable; if blank we
# look up `claude` in PATH at request time.
_claudecode_bin = os.environ.get('OPENCLAW_CLAUDE_BIN', '').strip()

# Codex CLI — alternative elevated agent backend. Uses `codex exec --json`
# with the same allowed-dirs sandbox. Auth is read from ~/.codex/config.toml
# automatically; no API key is passed by serve.py.
# Override binary path with OPENCLAW_CODEX_BIN env var.
_codex_bin = os.environ.get('OPENCLAW_CODEX_BIN', '').strip()

# /openclaw/stream — elevated agent endpoint with computer access. Same
# `claude` CLI as /claudecode/stream but tools are ENABLED and constrained
# by a server-side allowlist (paths and tool names). Both lists are env-
# only — the client can't widen them by sending a bigger spec. If either
# allowlist is empty the endpoint refuses requests, so the unconfigured
# default is safe.
#
#   OPENCLAW_ALLOWED_DIRS: os.pathsep-separated absolute paths claude can
#                          read/write. Empty → endpoint disabled.
#   OPENCLAW_ALLOWED_TOOLS: comma-separated tool names Claude Code accepts
#                          (Read, Write, Edit, Glob, Grep, Bash, ...).
#                          Default is read-only ("Read,Glob,Grep") so the
#                          first-time experience can't mutate the disk
#                          without an explicit opt-in.
_ALLOWED_DIRS_EXPLICIT = 'OPENCLAW_ALLOWED_DIRS' in os.environ
_openclaw_allowed_dirs = [d.strip() for d in
                          os.environ.get('OPENCLAW_ALLOWED_DIRS',
                              os.path.expanduser('~') + os.pathsep +
                              os.path.join(os.path.expanduser('~'), 'Documents')
                          ).split(os.pathsep)
                          if d.strip()]
_openclaw_allowed_tools = [t.strip() for t in
                           os.environ.get('OPENCLAW_ALLOWED_TOOLS',
                               # Default expanded set — gives elevated agents
                               # a real workshop instead of read-only browsing.
                               # Bash + Edit + Write enable code edits; Glob +
                               # Grep cover discovery; WebFetch + WebSearch
                               # cover external research; the ROOT TodoWrite
                               # / Notebook* tools are deliberately excluded
                               # because they're meta-tools that confuse the
                               # sub-agent's own task list.
                               'Read,Glob,Grep,Bash,Edit,Write,WebFetch,WebSearch'
                           ).split(',')
                           if t.strip()]

# ── Runtime environment detection ────────────────────────────────────────────
# 'container' → OCI/Docker container (no display; terminal spawn disabled)
# 'local'     → developer machine (all features enabled)
def _detect_runtime():
    if sys.platform == 'win32':
        return 'local'
    # Linux/macOS: check standard container markers
    if os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv'):
        return 'container'
    try:
        with open('/proc/1/cgroup', 'r') as _f:
            _cg = _f.read()
        if any(kw in _cg for kw in ('docker', 'kubepods', 'lxc', 'containerd')):
            return 'container'
    except Exception:
        pass
    # Our OCI fleet env vars are definitive
    if os.environ.get('OCI_TENANCY_ID') or os.environ.get('FLEET_REGISTRY'):
        return 'container'
    return 'local'

_RUNTIME_ENV = _detect_runtime()

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

# HQ state persistence
_hq_state_dir   = pathlib.Path(os.environ.get('OPENCLAW_HQ_STATE_DIR',
                    os.path.join(os.path.dirname(__file__), 'hq-state')))
_hq_memory_dir  = pathlib.Path(os.environ.get('OPENCLAW_MEMORY_DIR',
                    os.path.join(os.path.dirname(__file__), 'hq-state', 'memory')))


# ---- External approvals (Claude Code PreToolUse hook bridge) ---------------
# When the local `claude` CLI is wired to call our approval hook, each tool
# invocation it wants to make blocks on a long-poll against this server. We
# park the request here, surface it in the HQ UI's ApprovalTray, and signal
# the waiting hook process when the boss clicks APPROVE / REJECT.
#
# Single-process, thread-safe. Entries auto-expire so a closed terminal
# doesn't leak forever in the tray.
_approvals_lock = threading.Lock()
_approvals_pending = {}   # id -> dict (see _new_approval)
_APPROVAL_TTL_SEC = 30 * 60

def _new_approval(payload: dict) -> dict:
    aid = 'ce_' + uuid.uuid4().hex[:10]
    entry = {
        'id': aid,
        'ts': time.time(),
        'tool': str(payload.get('tool') or '')[:80],
        'input': payload.get('input') or {},
        'cwd': str(payload.get('cwd') or '')[:400],
        'agent': str(payload.get('agent') or 'claude-code')[:60],
        'sessionId': str(payload.get('sessionId') or '')[:80],
        'summary': str(payload.get('summary') or '')[:400],
        'decision': None,           # 'allow' | 'deny' | None
        'reason': '',
        'event': threading.Event(),
    }
    with _approvals_lock:
        _approvals_pending[aid] = entry
    return entry

def _gc_approvals():
    """Drop entries older than TTL with no decision — terminal probably went away."""
    now = time.time()
    with _approvals_lock:
        stale = [k for k, e in _approvals_pending.items()
                 if e['decision'] is None and now - e['ts'] > _APPROVAL_TTL_SEC]
        for k in stale:
            e = _approvals_pending.pop(k, None)
            if e:
                e['decision'] = 'deny'
                e['reason'] = 'expired (no human present)'
                e['event'].set()


# Vault config: env vars at startup, can be re-set at runtime via POST /vault/configure.
# By default Openclaw owns a plain Markdown vault under hq-state, so Obsidian is
# optional instead of required for notes to work.
_default_vault_root = _hq_state_dir / 'vault'
_vault_root     = os.environ.get('OPENCLAW_VAULT', str(_default_vault_root)).strip()
_vault_backend  = os.environ.get('OPENCLAW_VAULT_BACKEND', 'fs').strip() or 'fs'
_vault_rest_url = os.environ.get('OPENCLAW_OBSIDIAN_URL', 'https://127.0.0.1:27124').strip()
_vault_rest_key = os.environ.get('OPENCLAW_OBSIDIAN_KEY', '').strip()

# ── OCI Object Storage vault config (OPENCLAW_VAULT_BACKEND=oci) ─────────────
# Used by OCI Fleet containers.  serve.py never reads ~/.oci/config on its own;
# the Container Instance's instance-principal auth or a mounted config file
# provides credentials.  All three vars must be set for OCI vault to work.
_oci_vault_namespace = os.environ.get('OCI_VAULT_NAMESPACE', '').strip()
_oci_vault_bucket    = os.environ.get('OCI_VAULT_BUCKET', 'openclaw-fleet-vault').strip()
# Prefix isolates this user's objects: e.g. "2vxsx-principal-hash/"
_oci_vault_prefix    = os.environ.get('OCI_VAULT_PREFIX', '').strip()
_oci_client_lock     = threading.Lock()
_oci_client_obj: object = None   # lazy singleton — oci.object_storage.ObjectStorageClient

def _oci_object_client():
    """Lazy-load OCI Object Storage client. Thread-safe. Raises RuntimeError on failure."""
    global _oci_client_obj
    if _oci_client_obj is None:
        with _oci_client_lock:
            if _oci_client_obj is None:
                try:
                    import oci as _oci_sdk  # pip install oci

                    # ── 1. Env-var credentials (preferred inside Container Instances) ──
                    # Fleet-manager passes these at provision time so we don't rely on
                    # instance-principal IMDS, which can hang if IAM policies aren't ready.
                    _ev_tenancy     = os.environ.get('OCI_TENANCY_OCID', '').strip()
                    _ev_user        = os.environ.get('OCI_USER_OCID', '').strip()
                    _ev_fingerprint = os.environ.get('OCI_FINGERPRINT', '').strip()
                    _ev_region      = os.environ.get('OCI_REGION', 'us-ashburn-1').strip()
                    _ev_key_b64     = os.environ.get('OCI_KEY_B64', '').strip()
                    if all([_ev_tenancy, _ev_user, _ev_fingerprint, _ev_key_b64]):
                        import base64 as _b64
                        _cfg = {
                            'tenancy':     _ev_tenancy,
                            'user':        _ev_user,
                            'fingerprint': _ev_fingerprint,
                            'region':      _ev_region,
                            'key_content': _b64.b64decode(_ev_key_b64).decode(),
                        }
                        _oci_sdk.config.validate_config(_cfg)
                        _oci_client_obj = _oci_sdk.object_storage.ObjectStorageClient(_cfg)
                        return _oci_client_obj

                    # ── 2. Config file (~/.oci/config) ───────────────────────────────
                    try:
                        _cfg = _oci_sdk.config.from_file()
                        _oci_client_obj = _oci_sdk.object_storage.ObjectStorageClient(_cfg)
                        return _oci_client_obj
                    except Exception:
                        pass

                    # ── 3. Instance principal (OCI Compute; may be slow to init) ────
                    _cfg = {}
                    signer = _oci_sdk.auth.signers.InstancePrincipalsSecurityTokenSigner()
                    _oci_client_obj = _oci_sdk.object_storage.ObjectStorageClient(
                        config=_cfg, signer=signer)
                except ImportError:
                    raise RuntimeError(
                        'OCI SDK not installed — run: pip install oci  '
                        '(or pip install -r oci-fleet/requirements-serve.txt)')
    return _oci_client_obj

def _oci_obj_key(rel: str) -> str:
    """Build the full OCI Object key for a vault-relative path."""
    prefix = (_oci_vault_prefix.rstrip('/') + '/') if _oci_vault_prefix else ''
    return prefix + rel.lstrip('/')

# Fleet identity (set by fleet-manager when provisioning the container)
_fleet_mode      = os.environ.get('OPENCLAW_FLEET_MODE', 'local').strip()
_fleet_user_principal = os.environ.get('USER_PRINCIPAL', '').strip()

# Uptime tracking for /health
_server_start_time = time.time()

if not os.environ.get('OPENCLAW_VAULT'):
    try:
        pathlib.Path(_vault_root).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _clean_vault_root(raw) -> str:
    """Normalize common pasted path forms before validating a local vault."""
    root = str(raw or '').strip()
    while len(root) >= 2 and root[0] == root[-1] and root[0] in ('"', "'"):
        root = root[1:-1].strip()
    if root.lower().startswith('file:'):
        parsed = urllib.parse.urlparse(root)
        if parsed.scheme == 'file':
            path = urllib.parse.unquote(parsed.path or '')
            if parsed.netloc:
                path = f'//{parsed.netloc}{path}'
            if os.name == 'nt' and re.match(r'^/[A-Za-z]:[\\/]', path):
                path = path[1:]
            root = path
    root = os.path.expandvars(os.path.expanduser(root))
    if '%' in root:
        root = urllib.parse.unquote(root)
    return root.strip()


def _obsidian_config_dirs() -> list:
    """Return likely Obsidian desktop config directories for this platform."""
    out = []
    appdata = os.environ.get('APPDATA')
    if appdata:
        out.append(pathlib.Path(appdata) / 'obsidian')
    home = pathlib.Path.home()
    if sys.platform == 'darwin':
        out.append(home / 'Library' / 'Application Support' / 'obsidian')
    else:
        xdg = os.environ.get('XDG_CONFIG_HOME')
        out.append((pathlib.Path(xdg) if xdg else home / '.config') / 'obsidian')
    return out


def _discover_obsidian_vaults() -> list:
    """Read Obsidian's desktop config and return known local vault paths."""
    seen = set()
    vaults = []
    for cfg_dir in _obsidian_config_dirs():
        cfg = cfg_dir / 'obsidian.json'
        if not cfg.is_file():
            continue
        try:
            data = json.loads(cfg.read_text(encoding='utf-8'))
        except Exception:
            continue
        raw_vaults = data.get('vaults') or {}
        if not isinstance(raw_vaults, dict):
            continue
        for vault_id, info in raw_vaults.items():
            if not isinstance(info, dict):
                continue
            raw_path = str(info.get('path') or '').strip()
            if not raw_path:
                continue
            key = os.path.normcase(os.path.abspath(raw_path))
            if key in seen:
                continue
            seen.add(key)
            p = pathlib.Path(raw_path)
            vaults.append({
                'id': str(vault_id),
                'path': raw_path,
                'name': p.name or raw_path,
                'open': bool(info.get('open')),
                'ts': int(info.get('ts') or 0),
                'exists': p.is_dir(),
                'source': str(cfg),
            })
    vaults.sort(key=lambda v: (not v['open'], not v['exists'], -v['ts'], v['name'].lower()))
    return vaults


def _vault_resolve(rel: str) -> pathlib.Path:
    """Resolve `rel` (e.g. "Daily/2026-04-25.md") under the vault directory with
    traversal protection. Raises ValueError if escape is attempted or unset."""
    if not _vault_root:
        raise ValueError('vault directory not configured')
    root = pathlib.Path(_vault_root).resolve()
    if not root.is_dir():
        raise ValueError(f'vault directory does not exist: {root}')
    rel = rel.lstrip('/').replace('\\', '/')
    if not rel.endswith('.md'):
        rel += '.md'
    candidate = (root / rel).resolve()
    # Reject anything outside the vault directory.
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ValueError('path escapes vault directory')
    return candidate


# ---- Obsidian Local REST API client -----------------------------------------
def _obsidian_request(method: str, upstream_path: str,
                      body: bytes = None, extra_headers: dict = None,
                      content_type: str = 'application/json'):
    """Forward a request to the Obsidian Local REST API plugin. Returns
    (status, headers_list, body_bytes). Raises ValueError if not configured.
    Tolerates self-signed HTTPS certs (the plugin's default)."""
    if not _vault_rest_url:
        raise ValueError('Obsidian REST URL not configured')
    if not _vault_rest_key:
        raise ValueError('Obsidian REST key not configured')
    parsed = urllib.parse.urlparse(_vault_rest_url)
    is_https = parsed.scheme == 'https'
    host = parsed.hostname or '127.0.0.1'
    port = parsed.port or (27124 if is_https else 27123)
    headers = {
        'Authorization': f'Bearer {_vault_rest_key}',
        'Accept': 'application/json',
    }
    if body is not None:
        headers['Content-Type'] = content_type
    if extra_headers:
        headers.update(extra_headers)
    if is_https:
        ctx = ssl._create_unverified_context()  # plugin uses self-signed cert
        conn = http.client.HTTPSConnection(host, port, timeout=30, context=ctx)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=30)
    try:
        conn.request(method, upstream_path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.getheaders(), resp.read()
    finally:
        conn.close()


# ---- Obsidian REST: vault adapter -------------------------------------------
def _rest_list_all() -> list:
    """Walk the vault via the REST API. Returns the same shape as the FS
    listing: [{path, title, mtime, size}, ...]."""
    out = []
    def walk(folder: str):
        s, _, body = _obsidian_request('GET', '/vault/' + urllib.parse.quote(folder))
        if s != 200:
            return
        try:
            data = json.loads(body.decode('utf-8'))
        except Exception:
            return
        for entry in data.get('files', []):
            full = (folder + entry).lstrip('/')
            if entry.endswith('/'):
                # Subfolder; skip Obsidian internals
                if entry.lstrip('/').startswith('.'):
                    continue
                walk(full)
            elif entry.endswith('.md'):
                # Plugin's listing doesn't include mtime/size in the simple list;
                # fetch a stat-like via the file endpoint headers if needed. For
                # speed we just stub them. The graph + browse views still work.
                title = pathlib.PurePosixPath(full).stem
                out.append({'path': full, 'title': title, 'mtime': 0, 'size': 0})
    walk('')
    out.sort(key=lambda f: f['path'])
    return out


def _rest_search(query: str, limit: int = 10) -> list:
    qs = urllib.parse.urlencode({'query': query, 'contextLength': 120})
    s, _, body = _obsidian_request('GET', '/search/simple/?' + qs)
    if s != 200:
        return []
    try:
        data = json.loads(body.decode('utf-8'))
    except Exception:
        return []
    hits = []
    for r in data[:limit]:
        filename = r.get('filename') or r.get('path') or ''
        matches = r.get('matches', [])
        snippet = matches[0].get('context', '') if matches else ''
        hits.append({
            'path': filename,
            'title': pathlib.PurePosixPath(filename).stem,
            'score': r.get('score', len(matches)),
            'snippet': snippet.replace('\n', ' ').strip(),
        })
    return hits


# ---- Graph extraction (works for both backends) -----------------------------
import re as _re
_WIKILINK_RE = _re.compile(r'\[\[([^\]\|]+?)(?:\|[^\]]*)?\]\]')
_TAG_RE = _re.compile(r'(?:^|\s)#([A-Za-z0-9_/\-]+)')


def _graph_node_type(path: str, tags=None) -> str:
    """Lightweight product-facing graph taxonomy. Keep this intentionally small.
    The UI can reason with these without requiring a canonical backend schema yet."""
    p = (path or '').replace('\\', '/').lower()
    tagset = {str(t).lstrip('#').lower() for t in (tags or [])}
    name = pathlib.PurePosixPath(p).stem
    if 'research/' in p or 'research' in tagset:
        return 'research'
    if 'project' in tagset or p.startswith('projects/') or p.startswith('05-projects/') or '/projects/' in p:
        return 'project'
    if 'task' in tagset or 'tasks/' in p or 'todo' in name:
        return 'task'
    if 'agent' in tagset or 'agents/' in p or name.startswith('agent-'):
        return 'agent'
    if 'decision' in tagset or 'decisions/' in p or 'decision' in name:
        return 'decision'
    if 'proposal' in tagset or 'proposal' in name or '/proposals/' in p:
        return 'proposal'
    if 'memory' in tagset or 'memory/' in p or 'memories/' in p:
        return 'memory'
    if 'risk' in tagset or 'risk' in name:
        return 'risk'
    if p.endswith(('.py.md', '.jsx.md', '.js.md', '.ts.md', '.tsx.md')) or 'code' in tagset:
        return 'code_file'
    return 'note'


def _graph_edge_payload(source: str, target: str, edge_type='links_to', status='canonical', confidence=1.0, source_text='') -> dict:
    return {
        'source': source,
        'target': target,
        'type': edge_type,
        'status': status,
        'confidence': confidence,
        'sourcePath': source,
        'sourceText': source_text,
    }


# ──────────────────────────────────────────────────────────────────────────
# Edge-type extraction (knowledge-graph style relationships)
#
# Every wikilink in a markdown file becomes an edge. By default that edge is
# `links_to` (the historical behavior). But we look at the SURROUNDING context
# of each link — section heading, callout type, line prefix, frontmatter key —
# to upgrade generic links into typed knowledge-graph relationships
# (cites, supports, contradicts, child_of, decided, blocked_by, etc).
#
# This makes the graph reason-able instead of just browse-able. Confidence
# stays high (>=0.7) for explicit cues; pure body links remain confidence 1.0
# typed links_to so we don't degrade the existing graph.
# ──────────────────────────────────────────────────────────────────────────

# Section heading → edge type for any links found INSIDE that section.
# Match is case-insensitive on the heading text; trailing punctuation stripped.
_SECTION_EDGE_TYPES = {
    'sources': 'cites',
    'source': 'cites',
    'references': 'cites',
    'reference': 'cites',
    'citations': 'cites',
    'see also': 'related_to',
    'related': 'related_to',
    'related notes': 'related_to',
    'further reading': 'related_to',
    'children': 'parent_of',
    'sub-pages': 'parent_of',
    'parent': 'child_of',
    'parents': 'child_of',
    'implementation': 'implements',
    'implemented by': 'implemented_by',
    'implements': 'implements',
    'risks': 'has_risk',
    'risk': 'has_risk',
    'decisions': 'decided',
    'decided': 'decided',
    'decision': 'decided',
    'evidence': 'supports',
    'supports': 'supports',
    'contradicts': 'contradicts',
    'objections': 'contradicts',
    'counter-evidence': 'contradicts',
    'blocks': 'blocks',
    'blocked by': 'blocked_by',
    'depends on': 'depends_on',
    'dependencies': 'depends_on',
    'supersedes': 'supersedes',
    'superseded by': 'superseded_by',
    'agents': 'created_by',
    'assigned to': 'assigned_to',
    'tasks': 'has_task',
    'proposals': 'has_proposal',
}

# A line that BEGINS with one of these prefixes (case-insensitive) and contains
# a wikilink is treated as a typed edge to that link. e.g. `Parent: [[Foo]]`.
_LINE_PREFIX_EDGE_TYPES = {
    'source': 'cites',
    'sources': 'cites',
    'cite': 'cites',
    'cites': 'cites',
    'reference': 'cites',
    'references': 'cites',
    'parent': 'child_of',
    'parents': 'child_of',
    'child': 'parent_of',
    'children': 'parent_of',
    'see also': 'related_to',
    'related': 'related_to',
    'implements': 'implements',
    'implemented by': 'implemented_by',
    'blocks': 'blocks',
    'blocked by': 'blocked_by',
    'depends on': 'depends_on',
    'depends': 'depends_on',
    'supersedes': 'supersedes',
    'superseded by': 'superseded_by',
    'replaces': 'supersedes',
    'replaced by': 'superseded_by',
    'assigned to': 'assigned_to',
    'assigned': 'assigned_to',
    'owner': 'assigned_to',
    'created by': 'created_by',
    'author': 'created_by',
    'authors': 'created_by',
    'edited by': 'edited_by',
    'reviewer': 'reviewed_by',
    'reviewed by': 'reviewed_by',
    'decision': 'decided',
    'decided': 'decided',
    'decides': 'decided',
    'note': 'notes',
    'tldr': 'notes',
    'summary': 'notes',
    'mention': 'mentions',
    'mentions': 'mentions',
}

# Callout block types (> [!type]) → edge type for links inside the callout.
_CALLOUT_EDGE_TYPES = {
    'supports': 'supports',
    'support': 'supports',
    'evidence': 'supports',
    'contradicts': 'contradicts',
    'contradict': 'contradicts',
    'refutes': 'contradicts',
    'objection': 'contradicts',
    'derived': 'derived_from',
    'derived-from': 'derived_from',
    'derives': 'derived_from',
    'cite': 'cites',
    'cites': 'cites',
    'source': 'cites',
    'note': 'notes',
    'info': 'notes',
    'abstract': 'notes',
    'summary': 'notes',
    'warning': 'has_risk',
    'caution': 'has_risk',
    'danger': 'has_risk',
    'risk': 'has_risk',
    'tip': 'related_to',
    'hint': 'related_to',
    'example': 'exemplifies',
    'decision': 'decided',
    'decided': 'decided',
    'todo': 'has_task',
    'task': 'has_task',
    'question': 'questions',
    'q': 'questions',
}

# Frontmatter key → (edge_type, is_inverse). is_inverse means the edge points
# FROM the linked target back TO this note (e.g. `children: [[X]]` means
# this note is parent_of X, but `parent: [[X]]` means this note is child_of X).
_FRONTMATTER_EDGE_TYPES = {
    'parent': ('child_of', False),
    'parents': ('child_of', False),
    'children': ('parent_of', False),
    'child': ('parent_of', False),
    'source': ('cites', False),
    'sources': ('cites', False),
    'cites': ('cites', False),
    'references': ('cites', False),
    'related': ('related_to', False),
    'see-also': ('related_to', False),
    'see_also': ('related_to', False),
    'supersedes': ('supersedes', False),
    'superseded-by': ('superseded_by', False),
    'replaces': ('supersedes', False),
    'replaced-by': ('superseded_by', False),
    'implements': ('implements', False),
    'implemented-by': ('implemented_by', False),
    'blocks': ('blocks', False),
    'blocked-by': ('blocked_by', False),
    'depends-on': ('depends_on', False),
    'depends': ('depends_on', False),
    'agent': ('created_by', False),
    'author': ('created_by', False),
    'authors': ('created_by', False),
    'created-by': ('created_by', False),
    'assigned-to': ('assigned_to', False),
    'assignedto': ('assigned_to', False),
    'assignee': ('assigned_to', False),
    'owner': ('assigned_to', False),
    'reviewer': ('reviewed_by', False),
    'reviewed-by': ('reviewed_by', False),
}

# Default confidence per type. Explicit frontmatter / line-prefix is 1.0;
# section context is 0.85 (fairly likely); callouts are 0.95 (explicit author
# intent). Generic body links_to stays at 1.0 (the link itself is a fact).
_EDGE_TYPE_CONFIDENCE = {
    'links_to': 1.0,
    'cites': 0.95,
    'related_to': 0.85,
    'child_of': 1.0,
    'parent_of': 1.0,
    'implements': 0.95,
    'implemented_by': 0.95,
    'blocks': 0.95,
    'blocked_by': 0.95,
    'supersedes': 1.0,
    'superseded_by': 1.0,
    'depends_on': 0.95,
    'supports': 0.95,
    'contradicts': 0.95,
    'derived_from': 0.95,
    'has_risk': 0.9,
    'decided': 0.9,
    'created_by': 1.0,
    'assigned_to': 1.0,
    'edited_by': 1.0,
    'reviewed_by': 1.0,
    'notes': 0.7,
    'mentions': 0.85,
    'has_task': 0.9,
    'has_proposal': 0.9,
    'exemplifies': 0.85,
    'questions': 0.85,
    # HQ-state ingestion edge types (tasks/missions/receipts/etc → vault)
    'references': 0.9,   # task/mission body mentions a note
    'produces':   0.95,  # mission wrote a note
    'modified':   0.85,  # receipt records a write to a note
    'targets':    0.85,  # mission scoped to a folder/note
    'runs_as':    1.0,   # mission runs as an agent
    # Message-registry edges
    'sent_to':    1.0,   # agent originated a message-thread
    'received':   1.0,   # agent received a message-thread
    # Org-chart edges
    'reports_to': 1.0,   # assistant agent → senior agent
}


_FRONTMATTER_RE = _re.compile(r'\A---\s*\n(.*?\n)---\s*\n', _re.DOTALL)
_HEADING_RE = _re.compile(r'^(#{1,6})\s+(.+?)\s*$')
_CALLOUT_OPEN_RE = _re.compile(r'^\s*>\s*\[!([A-Za-z][\w\-]*)\]')
# Grabs any line of the form "Word(s):" at the very start, captures the label.
_LINE_PREFIX_RE = _re.compile(r'^\s*(?:[-*]\s+)?\*{0,2}([A-Za-z][\w\s\-]{0,30}?)\*{0,2}\s*:\s*(.*)$')


def _norm_label(s: str) -> str:
    """Lowercase + collapse whitespace + strip trailing punctuation. Used to
    match section headings / line prefixes against the type lookup tables."""
    s = (s or '').strip().lower().rstrip('.:!?')
    return _re.sub(r'\s+', ' ', s)


def _classify_edge(context: dict) -> tuple:
    """Given the context surrounding a wikilink, return (edge_type, confidence,
    source_text). Priority: callout > line prefix > section heading > default.
    `context` keys: callout, prefix, section, line_text."""
    callout = context.get('callout')
    prefix  = context.get('prefix')
    section = context.get('section')
    text    = (context.get('line_text') or '').strip()[:240]
    if callout:
        t = _CALLOUT_EDGE_TYPES.get(callout.lower())
        if t:
            return t, _EDGE_TYPE_CONFIDENCE.get(t, 0.9), text
    if prefix:
        t = _LINE_PREFIX_EDGE_TYPES.get(_norm_label(prefix))
        if t:
            return t, _EDGE_TYPE_CONFIDENCE.get(t, 1.0), text
    if section:
        t = _SECTION_EDGE_TYPES.get(_norm_label(section))
        if t:
            return t, _EDGE_TYPE_CONFIDENCE.get(t, 0.85), text
    return 'links_to', 1.0, text


def _extract_typed_edges(rel: str, text: str, all_paths: dict):
    """Walk `text` line-by-line and yield (target_path, edge_type, confidence,
    source_text) for every resolvable wikilink, classifying each by its
    surrounding context. Also processes YAML frontmatter for typed metadata.

    Yields tuples; the caller dedups by (rel, target, type). We dedup on type
    too so a note can have BOTH a `cites` AND a `related_to` edge to the same
    target if the note links to it from two different contexts — useful for
    showing the strongest relationship while keeping evidence."""
    # ── Frontmatter pass ───────────────────────────────────────────────
    body = text
    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match:
        fm_text = fm_match.group(1)
        body = text[fm_match.end():]
        for fm_line in fm_text.splitlines():
            kv = fm_line.split(':', 1)
            if len(kv) != 2: continue
            key = _norm_label(kv[0]).replace(' ', '-')
            val = kv[1].strip()
            mapping = _FRONTMATTER_EDGE_TYPES.get(key)
            if not mapping: continue
            edge_type, _ = mapping
            conf = _EDGE_TYPE_CONFIDENCE.get(edge_type, 0.9)
            for m in _WIKILINK_RE.finditer(val):
                tgt = _norm_link(m.group(1), all_paths)
                if tgt and tgt != rel:
                    yield (tgt, edge_type, conf, f'{key}: {val}'[:240])

    # ── Body pass: line-by-line, tracking section + callout state ──────
    current_section = None
    callout_type = None
    callout_lines_left = 0  # how many continuation `>` lines still belong to the open callout
    for line in body.splitlines():
        # Heading? Update current_section, no links here.
        h = _HEADING_RE.match(line)
        if h:
            current_section = h.group(2).strip()
            callout_type = None
            callout_lines_left = 0
            continue
        # Callout open?
        co = _CALLOUT_OPEN_RE.match(line)
        if co:
            callout_type = co.group(1)
            callout_lines_left = 12  # generous: callouts up to ~12 lines
        elif callout_type:
            # Callout continues only while line begins with `>`
            if line.lstrip().startswith('>') and callout_lines_left > 0:
                callout_lines_left -= 1
            else:
                callout_type = None
                callout_lines_left = 0
        # Line prefix?  (Only outside callouts; callouts already imply type.)
        prefix = None
        if not callout_type:
            lp = _LINE_PREFIX_RE.match(line)
            if lp:
                cand = lp.group(1)
                if _norm_label(cand) in _LINE_PREFIX_EDGE_TYPES:
                    prefix = cand
        # Now scan wikilinks on this line.
        for m in _WIKILINK_RE.finditer(line):
            tgt = _norm_link(m.group(1), all_paths)
            if not tgt or tgt == rel:
                continue
            ctx = {
                'callout': callout_type,
                'prefix': prefix,
                'section': current_section,
                'line_text': line.strip(),
            }
            etype, conf, text_snip = _classify_edge(ctx)
            yield (tgt, etype, conf, text_snip)

def _norm_link(target: str, all_paths: dict) -> str:
    """Resolve a wikilink target string to a known path key, or '' if unknown.
    Wikilinks can be by stem ("Foo") or path ("dir/Foo"); the .md is implicit."""
    target = target.strip()
    if not target:
        return ''
    # Strip section anchors (#heading) and block refs (^id)
    for sep in ('#', '^'):
        i = target.find(sep)
        if i >= 0: target = target[:i]
    if not target:
        return ''
    candidates = [
        target,
        target + '.md',
        target.rstrip('/') + '.md',
    ]
    # Lowercase fallback for case-insensitive matching
    by_stem = all_paths['by_stem']
    by_path = all_paths['by_path']
    for c in candidates:
        if c in by_path:
            return c
    stem = pathlib.PurePosixPath(target).stem.lower()
    return by_stem.get(stem, '')


def _build_graph_fs() -> dict:
    """Build a graph from raw .md files under the configured vault directory."""
    if not _vault_root:
        raise ValueError('vault not configured')
    root = pathlib.Path(_vault_root).resolve()
    nodes = []
    raw = []
    by_path = {}
    by_stem = {}
    for p in root.rglob('*.md'):
        try:
            rel = str(p.relative_to(root)).replace('\\', '/')
        except ValueError:
            continue
        if any(part.startswith('.') for part in p.relative_to(root).parts):
            continue
        try:
            text = p.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        by_path[rel] = True
        by_stem[p.stem.lower()] = rel
        raw.append((rel, p.stem, text, p.stat().st_mtime if p.exists() else 0, p.stat().st_size if p.exists() else 0))
    all_paths = {'by_path': by_path, 'by_stem': by_stem}
    edges = []
    # Dedupe by (source, target, type) so a note can have multiple edge types
    # to the same target (e.g. cited AND related_to) but never duplicates
    # within a single type. We also track per-pair best-confidence to upgrade
    # repeat plain links_to into typed edges if a typed mention shows up later.
    seen_typed_edge = set()
    for rel, title, text, mtime, size in raw:
        tags = sorted(set(m.group(1) for m in _TAG_RE.finditer(text)))
        out_targets = set()
        # Walk every (target, type, conf, snippet) the extractor finds.
        for tgt, etype, conf, snip in _extract_typed_edges(rel, text, all_paths):
            out_targets.add(tgt)
            key = (rel, tgt, etype)
            if key in seen_typed_edge: continue
            seen_typed_edge.add(key)
            edges.append(_graph_edge_payload(
                rel, tgt, edge_type=etype, confidence=conf, source_text=snip))
        nodes.append({
            'id': rel, 'title': title, 'path': rel,
            'mtime': int(mtime * 1000), 'size': size,
            'tags': tags[:8], 'outlinks': len(out_targets),
            'type': _graph_node_type(rel, tags),
            'source': 'markdownvault',
        })

    # ── HQ-state ingestion: tasks/projects/missions/receipts/agents ────
    # The graph stops being a vault-only viewer and starts representing
    # everything OpenclawHQ knows. New nodes use prefixed IDs (`task:`,
    # `agent:` etc) so they never collide with vault paths. Edges link
    # them to each other AND to vault notes when references resolve.
    hq_nodes, hq_edges = _build_hq_state_graph(all_paths, seen_typed_edge)
    nodes.extend(hq_nodes)
    edges.extend(hq_edges)

    # Compute inlinks for sizing — across BOTH vault and HQ-state nodes.
    indeg = {n['id']: 0 for n in nodes}
    for e in edges:
        if e['target'] in indeg:
            indeg[e['target']] += 1
    for n in nodes:
        n['inlinks'] = indeg[n['id']]
    return {'nodes': nodes, 'edges': edges}


# ──────────────────────────────────────────────────────────────────────────
# HQ-state → graph ingestion
#
# Reads the JSON files in hq-state/ and turns them into typed graph nodes,
# with edges to each other AND to vault notes when references resolve. This
# is what makes GraphView the unified "everything OpenclawHQ knows" view
# rather than just a markdown vault visualizer.
# ──────────────────────────────────────────────────────────────────────────

def _hq_state_path(name: str) -> pathlib.Path:
    """Resolve `hq-state/<name>.json` relative to the configured state dir."""
    return _hq_state_dir / f'{name}.json'


def _load_hq_state(name: str):
    """Safely load `hq-state/<name>.json`. Returns [] / {} on missing/invalid;
    never raises so a missing file doesn't break the whole graph build."""
    p = _hq_state_path(name)
    if not p.exists():
        return None
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f'[graph] could not load {name}.json: {e}\n')
        return None


def _load_hq_memory(name: str):
    """Safely load `<hq-memory>/<name>.json`. Same shape contract as
    _load_hq_state but reads from _hq_memory_dir (where the OpenclawHQ
    frontend persists agents, journals, etc via useFileStored('memory', ...))."""
    p = _hq_memory_dir / f'{name}.json'
    if not p.exists():
        return None
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f'[graph] could not load memory/{name}.json: {e}\n')
        return None


def _load_authoritative_agents() -> dict:
    """Load the canonical agents list from hq-memory/agents.json (where the
    OpenclawHQ frontend persists hired agents). Returns a dict keyed by both
    the agent id (e.g. 'a_nykw53') AND its name (e.g. 'Selvin'), with the
    agent dict as value. This lets the graph builder upgrade synthesised
    agent nodes — which would otherwise show as 'a_nykw53' — to friendly
    names ('Selvin · Code Gremlin') with proper sprite color metadata."""
    raw = _load_hq_memory('agents') or []
    if not isinstance(raw, list):
        return {}
    by_key = {}
    for a in raw:
        if not isinstance(a, dict): continue
        aid = a.get('id') or ''
        name = a.get('name') or ''
        if aid:  by_key[aid.lower()] = a
        if name: by_key[name.lower()] = a
    return by_key


def _slug_agent(s: str) -> str:
    """Normalize an agent name/id into a stable graph node id suffix."""
    return _re.sub(r'[^A-Za-z0-9_]+', '_', (s or 'unknown').strip()).strip('_').lower() or 'unknown'


def _build_hq_state_graph(all_paths: dict, seen_typed_edge: set) -> tuple:
    """Return (nodes, edges) ingested from hq-state/. Safe to call even if
    no JSON files exist — returns ([], []) in that case.

    `all_paths` is the same {by_path, by_stem} the wikilink resolver uses;
    we reuse it so when a task.detail mentions [[NoteName]] we can build a
    proper edge to the actual vault note.

    `seen_typed_edge` is the dedup set from the vault pass; we extend it
    so HQ-state edges don't duplicate vault edges by accident."""
    nodes_out = []
    edges_out = []

    def add_edge(src, tgt, etype, conf, snippet=''):
        key = (src, tgt, etype)
        if key in seen_typed_edge: return
        seen_typed_edge.add(key)
        edges_out.append(_graph_edge_payload(
            src, tgt, edge_type=etype, confidence=conf, source_text=snippet))

    # Authoritative agent registry (hq-memory/agents.json). Lookup by either
    # id or name. When a task/mission/receipt references an agent, we use
    # this to get the friendly name + role + color so the graph node is
    # readable ('Selvin · Code Gremlin') instead of opaque ('a_nykw53').
    auth_agents = _load_authoritative_agents()

    def _resolve_agent_meta(agent_ref: str):
        """Return the canonical agent dict for a given id-or-name reference,
        or None if the registry doesn't know about it. Case-insensitive."""
        if not agent_ref: return None
        return auth_agents.get(str(agent_ref).lower())

    # Track agent identities we've seen — keyed by canonical slug. We unify
    # references so 'Selvin', 'a_nykw53', and 'selvin' all collapse to one
    # node. Slug derives from the canonical id when known, else from the
    # raw reference (so unknown agents still get a node, just unbranded).
    agents_by_slug = {}  # slug → {'id', 'title', 'role', 'color', 'sourceIds', 'roles', 'meta'}

    def note_agent(agent_id_or_name: str, role: str = ''):
        """Register an agent reference; returns the slug node id. If the
        registry knows this agent, all later refs (by id or by name) collapse
        to the same slug — which is critical because tasks reference agents
        by id (a_xxx) but receipts reference them by name (Selvin)."""
        if not agent_id_or_name:
            return None
        meta = _resolve_agent_meta(agent_id_or_name)
        # Canonical slug: from the agent's own id if registry knows them,
        # else from the literal reference. This is what unifies cross-refs.
        canonical = (meta.get('id') if meta else str(agent_id_or_name))
        slug = _slug_agent(canonical)
        rec = agents_by_slug.get(slug)
        if not rec:
            rec = {
                'id': f'agent:{slug}',
                'title': str(agent_id_or_name),
                'role': '',
                'color': None,
                'meta': None,
                'sourceIds': set(),
                'roles': set(),
            }
            agents_by_slug[slug] = rec
        # Apply registry data when available — friendly name wins over a_xxx.
        if meta:
            rec['title'] = meta.get('name') or rec['title']
            rec['role']  = meta.get('role') or rec['role']
            rec['color'] = meta.get('color') or rec['color']
            rec['meta']  = meta
        else:
            # Fallback heuristic: prefer non-`a_xxx` displays when no registry hit.
            new = str(agent_id_or_name)
            if rec['title'].startswith('a_') and not new.startswith('a_'):
                rec['title'] = new
        rec['sourceIds'].add(str(agent_id_or_name))
        if role: rec['roles'].add(role)
        return rec['id']

    def resolve_wikilinks_in(text: str):
        """Yield resolved vault paths for every wikilink in `text`."""
        if not text: return
        for m in _WIKILINK_RE.finditer(text):
            tgt = _norm_link(m.group(1), all_paths)
            if tgt: yield tgt

    def resolve_path_to_note(p: str) -> str:
        """If `p` looks like a path that ends in a markdown filename we know,
        return the resolved vault path. Used to wire receipts whose title is
        e.g. 'FILE_WRITE: graphview_design_doc.md' to the actual note."""
        if not p: return ''
        # Try the literal stem.
        stem = pathlib.PurePosixPath(p.replace('\\', '/')).stem
        return all_paths['by_stem'].get(stem.lower(), '')

    # ── Tasks ──────────────────────────────────────────────────────────
    tasks = _load_hq_state('tasks') or []
    if isinstance(tasks, list):
        for t in tasks:
            if not isinstance(t, dict): continue
            tid = t.get('id') or ''
            if not tid: continue
            node_id = f'task:{tid}'
            title = (t.get('title') or '(untitled task)')[:120]
            detail = t.get('detail') or ''
            status = t.get('status') or ''
            priority = t.get('priority') or ''
            assigned = t.get('assignedTo')
            created = t.get('createdAt') or 0
            tags = [f'status/{status}'] if status else []
            if priority: tags.append(f'priority/{priority}')
            nodes_out.append({
                'id': node_id, 'title': title, 'path': '',
                'mtime': int(created) if created else 0,
                'size': len(detail) + len(title),
                'tags': tags, 'outlinks': 0,
                'type': 'task',
                'source': 'hq-state',
            })
            # Edges
            if assigned:
                aid = note_agent(assigned, 'assignee')
                if aid: add_edge(node_id, aid, 'assigned_to', 1.0,
                                  f'task assigned to {assigned}')
            for ref in resolve_wikilinks_in(title + '\n' + detail):
                add_edge(node_id, ref, 'references', 0.9,
                          f'task body mentions [[{pathlib.PurePosixPath(ref).stem}]]')

    # ── Projects ───────────────────────────────────────────────────────
    projects = _load_hq_state('projects') or []
    if isinstance(projects, list):
        for p in projects:
            if not isinstance(p, dict): continue
            pid = p.get('id') or ''
            if not pid: continue
            node_id = f'project:{pid}'
            name = p.get('name') or '(unnamed project)'
            ptype = p.get('type') or 'local'
            agentIds = p.get('agentIds') or []
            created = p.get('createdAt') or 0
            tags = [f'project-type/{ptype}']
            nodes_out.append({
                'id': node_id, 'title': name, 'path': p.get('path') or '',
                'mtime': int(created) if created else 0,
                'size': 0, 'tags': tags, 'outlinks': 0,
                'type': 'project',
                'source': 'hq-state',
            })
            for aid_raw in agentIds:
                aid = note_agent(aid_raw, 'project-member')
                if aid: add_edge(node_id, aid, 'assigned_to', 1.0,
                                  f'project includes agent {aid_raw}')

    # ── Missions ───────────────────────────────────────────────────────
    missions = _load_hq_state('missions') or []
    if isinstance(missions, list):
        for m in missions:
            if not isinstance(m, dict): continue
            mid = m.get('id') or ''
            if not mid: continue
            node_id = f'mission:{mid}'
            mtype = m.get('type') or 'mission'
            agent = m.get('agentId')
            topic = m.get('topic') or ''
            folder = m.get('vaultFolder') or ''
            started = m.get('startedAt') or 0
            status = m.get('status') or ''
            iters = m.get('iterations') or 0
            written = m.get('notesWritten') or []
            tags = [f'mission-type/{mtype}']
            if status: tags.append(f'status/{status}')
            short_topic = topic.split('.')[0][:80] if topic else ''
            title = f'{mtype.title()}: {short_topic}' if short_topic else f'{mtype.title()} mission'
            nodes_out.append({
                'id': node_id, 'title': title, 'path': '',
                'mtime': int(started) if started else 0,
                'size': len(topic), 'tags': tags, 'outlinks': 0,
                'type': 'mission',
                'source': 'hq-state',
            })
            if agent:
                aid = note_agent(agent, 'mission-runner')
                if aid: add_edge(node_id, aid, 'runs_as', 1.0,
                                  f'mission runs as {agent}')
            # Mission topic mentioning [[wikilinks]] → references
            for ref in resolve_wikilinks_in(topic):
                add_edge(node_id, ref, 'references', 0.9, 'mission topic')
            # `notesWritten` array → produces edges to those vault notes.
            if isinstance(written, list):
                for w in written[:50]:
                    rel = ''
                    if isinstance(w, str):
                        rel = w.replace('\\','/').lstrip('/')
                        if rel and rel not in all_paths['by_path']:
                            # Try stem fallback.
                            rel = resolve_path_to_note(rel)
                    elif isinstance(w, dict):
                        rel = (w.get('path') or '').replace('\\','/').lstrip('/')
                        if rel and rel not in all_paths['by_path']:
                            rel = resolve_path_to_note(rel)
                    if rel:
                        add_edge(node_id, rel, 'produces', 0.95,
                                  f'mission wrote {rel}')
            # If vaultFolder maps to a known folder root, edge to the index/MOC note in it.
            if folder:
                fp = folder.replace('\\','/').strip('/')
                # Look for an index-ish note inside that folder.
                for cand in (f'{fp}/index.md', f'{fp}/README.md', f'{fp}/{pathlib.PurePosixPath(fp).name}.md'):
                    if cand in all_paths['by_path']:
                        add_edge(node_id, cand, 'targets', 0.85, f'mission folder: {fp}')
                        break

    # ── Receipts ───────────────────────────────────────────────────────
    receipts = _load_hq_state('receipts') or []
    if isinstance(receipts, list):
        for r in receipts:
            if not isinstance(r, dict): continue
            rid = r.get('id') or ''
            if not rid: continue
            node_id = f'receipt:{rid}'
            title = (r.get('title') or '(untitled receipt)')[:120]
            kind = r.get('kind') or ''
            decision = r.get('decision') or ''
            decided_at = r.get('decidedAt') or 0
            elevated = r.get('elevated', False)
            by_agent = r.get('by') or ''
            tags = []
            if kind: tags.append(f'receipt-kind/{kind}')
            if decision: tags.append(f'decision/{decision}')
            if elevated: tags.append('elevated')
            # Use type 'decision' for explicit decisions, 'receipt' for tool-execution audit.
            ntype = 'decision' if decision in ('approved', 'rejected') else 'receipt'
            nodes_out.append({
                'id': node_id, 'title': title, 'path': '',
                'mtime': int(decided_at) if decided_at else 0,
                'size': 0, 'tags': tags, 'outlinks': 0,
                'type': ntype,
                'source': 'hq-state',
            })
            if by_agent:
                aid = note_agent(by_agent, 'receipt-actor')
                if aid:
                    etype = 'decided' if ntype == 'decision' else 'created_by'
                    add_edge(node_id, aid, etype, 1.0, f'receipt by {by_agent}')
            # If the receipt title looks like a file action, link to the affected note.
            # e.g. "FILE_WRITE: foo.md" or "EDIT: bar/baz.md".
            m = _re.search(r':\s*(\S+\.md)\b', title)
            if m:
                cand = resolve_path_to_note(m.group(1))
                if cand:
                    affect_type = {
                        'tool-execution': 'modified',
                    }.get(kind, 'references')
                    add_edge(node_id, cand, affect_type, 0.85, title)

    # Add every registry agent up front so even agents who haven't been
    # referenced by any task/mission/receipt still show up in the graph
    # (otherwise newly-hired agents are invisible until they do work).
    # We also seed `reports_to` edges here so the org-chart structure is
    # visible even for assistants who haven't done work yet.
    pending_reports_to = []  # [(assistant_aid_ref, senior_aid_ref)]
    for key, meta in auth_agents.items():
        # Skip duplicate entries — registry indexes by both id and name.
        aid = meta.get('id')
        if not aid: continue
        if key.lower() != aid.lower(): continue
        note_agent(aid)
        # If this agent has a senior (reportsTo set in agents.json), record
        # it for an edge — we resolve both ends to canonical agent slugs
        # AFTER all agents are noted (so the senior exists in the graph
        # regardless of registration order).
        senior_id = meta.get('reportsTo') or meta.get('parentAgentId')
        if senior_id:
            pending_reports_to.append((aid, senior_id, meta.get('name') or aid))
    # Resolve pending reports_to edges now that all agents are noted.
    for assistant_id, senior_id, assistant_name in pending_reports_to:
        a_node = note_agent(assistant_id, 'assistant')
        s_node = note_agent(senior_id, 'senior')
        if a_node and s_node and a_node != s_node:
            add_edge(a_node, s_node, 'reports_to', 1.0,
                     f'{assistant_name} reports to senior')

    # ── Messages: agent-comms registry (Phase 1 of comms refactor) ─────
    # The frontend's MessageRegistry persists every agent↔agent handoff to
    # hq-state/messages.json. Each thread becomes a `message-thread` node
    # in the graph with edges to the participating agents — so the boss can
    # see live conversations as visual structure, not just inbox rows.
    # Per-message nodes would explode the graph on busy days; per-thread
    # gives one node per coherent conversation which is far more readable.
    messages = _load_hq_state('messages') or []
    if isinstance(messages, list) and messages:
        # Group messages into threads (preserving creation order).
        threads = {}
        for m in messages:
            if not isinstance(m, dict): continue
            tid = m.get('threadId') or ''
            if not tid: continue
            threads.setdefault(tid, []).append(m)
        for tid, thread_msgs in threads.items():
            thread_msgs.sort(key=lambda m: m.get('createdAt') or 0)
            head = thread_msgs[0]
            tail = thread_msgs[-1]
            node_id = f'thread:{tid}'
            # Display: "Selvin ↔ Plato (3)" or "boss → Selvin"
            from_n = head.get('fromAgentName') or head.get('fromAgentId') or '?'
            to_n   = head.get('toAgentName')   or head.get('toAgentId')   or '?'
            count = len(thread_msgs)
            title = f'{from_n} → {to_n}'
            if count > 1: title += f' ({count})'
            # Body preview = first message body, truncated.
            body_preview = (head.get('body') or '').split('\n')[0][:90]
            # State: take the latest non-terminal state if any (so an
            # otherwise-completed thread with a new in-progress reply
            # surfaces as in_progress); else take the tail's terminal state.
            terminal_states = {'completed', 'failed', 'cancelled'}
            current_state = tail.get('state') or 'queued'
            for m in reversed(thread_msgs):
                if m.get('state') and m['state'] not in terminal_states:
                    current_state = m['state']; break
            tags = [f'state/{current_state}']
            # Promote priority/taskType to tags for filtering.
            if head.get('priority') and head['priority'] != 'med':
                tags.append(f'priority/{head["priority"]}')
            if head.get('taskType'):
                tags.append(f'task-type/{head["taskType"]}')
            # Aggregate failure cause across thread (any failed msg => tagged).
            had_failure = any(m.get('state') == 'failed' for m in thread_msgs)
            if had_failure: tags.append('had-failure')
            updated = max((m.get('updatedAt') or m.get('createdAt') or 0) for m in thread_msgs)
            nodes_out.append({
                'id': node_id,
                'title': title,
                'path': '',
                'mtime': int(updated) if updated else 0,
                'size': sum(len(m.get('body') or '') for m in thread_msgs),
                'tags': tags,
                'outlinks': 0,
                'type': 'message-thread',
                'source': 'hq-state',
                'messageCount': count,
                'threadState': current_state,
                'preview': body_preview,
            })
            # Edges: thread → each unique participant agent. Use 'sent_to'
            # for the from→thread direction and 'received' for to→thread,
            # so the graph reads as "agent originates / agent receives this
            # conversation". Boss participation collapses into a 'boss'
            # synthetic agent so it's visible in the graph too.
            participants = set()
            for m in thread_msgs:
                fid = m.get('fromAgentId') or ''
                tid_ag = m.get('toAgentId') or ''
                if fid and fid != 'boss': participants.add((fid, m.get('fromAgentName') or fid, 'sender'))
                elif fid == 'boss': participants.add(('boss', 'You (boss)', 'sender'))
                if tid_ag: participants.add((tid_ag, m.get('toAgentName') or tid_ag, 'receiver'))
            for ag_id, ag_name, role in participants:
                aid = note_agent(ag_id, role)
                if aid:
                    etype = 'sent_to' if role == 'sender' else 'received'
                    add_edge(aid, node_id, etype, 1.0,
                             f'{ag_name} {role} on this thread')
            # Edge to the artifact notes the thread produced (vault paths
            # in any message's `artifacts` array).
            for m in thread_msgs:
                for art in (m.get('artifacts') or []):
                    if not isinstance(art, dict): continue
                    p = (art.get('path') or '').replace('\\', '/').lstrip('/')
                    if not p: continue
                    if p in all_paths['by_path']:
                        kind = art.get('kind') or 'produced'
                        etype = 'produces' if kind in ('wrote', 'produced') else 'modified'
                        add_edge(node_id, p, etype, 0.95,
                                 f'thread artifact ({kind})')

    # ── Synthesise agent nodes from everything that referenced them ────
    for slug, rec in agents_by_slug.items():
        meta = rec.get('meta') or {}
        roles = sorted(rec['roles'])
        # Display title: 'Selvin · Code Gremlin' when role is known, else just name.
        display = rec['title']
        if rec.get('role'):
            display = f'{display} · {rec["role"]}'
        # Tags surface role + activity context for filter syntax.
        tags = []
        if rec.get('role'): tags.append(f'role/{_re.sub(r"[^A-Za-z0-9]+", "-", rec["role"]).strip("-").lower()}')
        for r in roles: tags.append(f'activity/{r}')
        if meta.get('elevated'): tags.append('elevated')
        if meta.get('model'): tags.append(f'model/{meta["model"].split(":")[0]}')
        # mtime: agent's lastRun if available, else hiredAt — for time-scrub
        # correctness. Both fields may legitimately be strings like
        # "just hired" or "never" (they're free-form display labels in some
        # OpenclawHQ states), so int() must be defensive — fall back to 0
        # whenever the field isn't a numeric timestamp.
        def _safe_ts(v):
            try: return int(v)
            except (TypeError, ValueError): return 0
        mtime = _safe_ts(meta.get('lastRun')) or _safe_ts(meta.get('hiredAt')) or 0
        node = {
            'id': rec['id'],
            'title': display,
            'path': '',
            'mtime': mtime,
            'size': 0,
            'tags': tags,
            'outlinks': 0,
            'type': 'agent',
            'source': 'hq-state',
        }
        # Attach color/meta hints the frontend can use for sprite rendering
        # without breaking the node schema (extra fields are passed through).
        if rec.get('color'): node['agentColor'] = rec['color']
        if meta.get('id'):   node['agentId']    = meta['id']
        if meta.get('model'): node['agentModel'] = meta['model']
        if meta.get('status'): node['agentStatus'] = meta['status']
        nodes_out.append(node)

    return nodes_out, edges_out


def _build_graph_rest() -> dict:
    """Use Dataview via the REST plugin to extract links + tags in one query."""
    query = (
        'TABLE WITHOUT ID '
        'file.path AS path, file.name AS title, file.size AS size, '
        'file.mtime AS mtime, file.outlinks AS outlinks, file.tags AS tags '
        'FROM "" SORT file.mtime DESC'
    )
    body = json.dumps({'query': query, 'queryType': 'dataview'}).encode('utf-8')
    s, _, raw = _obsidian_request('POST', '/search/', body=body,
                                  content_type='application/json')
    if s != 200:
        # Fall back to FS extraction if Dataview isn't installed.
        if _vault_root:
            return _build_graph_fs()
        raise ValueError(f'dataview query failed (status {s}); install Dataview plugin or set vault directory for FS fallback')
    try:
        data = json.loads(raw.decode('utf-8'))
    except Exception as e:
        raise ValueError(f'invalid graph response: {e}')
    rows = data if isinstance(data, list) else data.get('values', []) or data.get('rows', [])
    by_path = {}
    by_stem = {}
    raw_rows = []
    for r in rows:
        # Dataview returns objects keyed by query column names, or arrays.
        if isinstance(r, dict):
            path = r.get('path') or ''
            title = r.get('title') or pathlib.PurePosixPath(path).stem
            size = r.get('size') or 0
            mtime = r.get('mtime') or 0
            outs = r.get('outlinks') or []
            tags = r.get('tags') or []
        elif isinstance(r, list) and len(r) >= 6:
            path, title, size, mtime, outs, tags = r[:6]
        else:
            continue
        if not path: continue
        by_path[path] = True
        stem = pathlib.PurePosixPath(path).stem.lower()
        by_stem[stem] = path
        raw_rows.append((path, title, size, mtime, outs or [], tags or []))
    all_paths = {'by_path': by_path, 'by_stem': by_stem}
    nodes, edges, seen_edge = [], [], set()
    for path, title, size, mtime, outs, tags in raw_rows:
        out_paths = []
        for o in outs:
            tgt = ''
            if isinstance(o, dict):
                tgt = o.get('path') or o.get('display') or ''
            elif isinstance(o, str):
                tgt = o
            tgt = _norm_link(tgt, all_paths)
            if tgt and tgt != path:
                out_paths.append(tgt)
        clean_tags = []
        for t in tags:
            if isinstance(t, str):
                clean_tags.append(t.lstrip('#'))
        for tgt in out_paths:
            key = (path, tgt)
            if key in seen_edge: continue
            seen_edge.add(key)
            edges.append(_graph_edge_payload(path, tgt))
        # mtime from Dataview is an ISO string or a luxon DateTime serialized object.
        if isinstance(mtime, str):
            try:
                from datetime import datetime
                mtime_ms = int(datetime.fromisoformat(mtime.replace('Z','+00:00')).timestamp() * 1000)
            except Exception:
                mtime_ms = 0
        elif isinstance(mtime, (int, float)):
            mtime_ms = int(mtime)
        else:
            mtime_ms = 0
        nodes.append({
            'id': path, 'title': title or pathlib.PurePosixPath(path).stem, 'path': path,
            'mtime': mtime_ms, 'size': size or 0,
            'tags': clean_tags[:8], 'outlinks': len(out_paths),
            'type': _graph_node_type(path, clean_tags),
            'source': 'markdownvault',
        })
    indeg = {n['id']: 0 for n in nodes}
    for e in edges:
        if e['target'] in indeg:
            indeg[e['target']] += 1
    for n in nodes:
        n['inlinks'] = indeg[n['id']]
    return {'nodes': nodes, 'edges': edges}


# ────────────────────────────────────────────────────────────────────────────
# Minimal Chrome DevTools Protocol WebSocket client.
#
# Just enough to drive a fresh tab through navigate + screenshot using only
# stdlib (`socket` + `struct`). Replaces a full `websockets` dependency for
# what's a single short-lived RPC dance per screenshot.
#
# Spec subset:
#   - Client always masks frames (RFC 6455).
#   - Server frames may be unmasked (and usually are for browsers).
#   - Only TEXT (opcode 0x1) frames are handled — CDP uses JSON text frames.
#   - Single-frame messages only (we never see fragmented CDP messages
#     in practice for the tiny payloads we exchange).
# ────────────────────────────────────────────────────────────────────────────
_CDP_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

class _CDPWebSocket:
    def __init__(self, ws_url, timeout=20):
        u = urllib.parse.urlparse(ws_url)
        self.host = u.hostname
        self.port = u.port or (443 if u.scheme == 'wss' else 80)
        self.path = u.path + (('?' + u.query) if u.query else '')
        self.use_tls = (u.scheme == 'wss')
        self.timeout = timeout
        self.sock = None
        self._next_id = 1
        self._lock = threading.Lock()

    def connect(self):
        raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
        if self.use_tls:
            ctx = ssl.create_default_context()
            raw = ctx.wrap_socket(raw, server_hostname=self.host)
        self.sock = raw
        # Send the upgrade request.
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f'GET {self.path} HTTP/1.1\r\n'
            f'Host: {self.host}:{self.port}\r\n'
            f'Upgrade: websocket\r\n'
            f'Connection: Upgrade\r\n'
            f'Sec-WebSocket-Key: {key}\r\n'
            f'Sec-WebSocket-Version: 13\r\n\r\n'
        )
        self.sock.sendall(req.encode())
        # Read the handshake response.
        buf = b''
        while b'\r\n\r\n' not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError('CDP handshake closed')
            buf += chunk
            if len(buf) > 8192:
                raise RuntimeError('CDP handshake oversized')
        first_line = buf.split(b'\r\n', 1)[0].decode('latin-1', 'replace')
        if '101' not in first_line:
            raise RuntimeError(f'CDP upgrade rejected: {first_line}')
        # Discard any payload bytes after the handshake (shouldn't happen
        # since we haven't sent any RPC yet).
        return self

    def _send_frame(self, payload_bytes):
        """Send a single TEXT frame, masked (per RFC 6455 client rules)."""
        opcode = 0x1                  # text
        first = 0x80 | opcode          # FIN=1, opcode=text
        length = len(payload_bytes)
        mask_key = os.urandom(4)
        if length < 126:
            header = struct.pack('!BB', first, 0x80 | length)
        elif length < 65536:
            header = struct.pack('!BBH', first, 0x80 | 126, length)
        else:
            header = struct.pack('!BBQ', first, 0x80 | 127, length)
        masked = bytearray(payload_bytes)
        for i in range(length):
            masked[i] ^= mask_key[i % 4]
        with self._lock:
            self.sock.sendall(header + mask_key + bytes(masked))

    def _read_exact(self, n):
        buf = b''
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise RuntimeError('CDP socket closed mid-frame')
            buf += chunk
        return buf

    def _recv_frame(self):
        b1, b2 = struct.unpack('!BB', self._read_exact(2))
        # We only handle single-frame TEXT messages (most CDP responses are).
        opcode = b1 & 0x0F
        masked = (b2 & 0x80) != 0
        length = b2 & 0x7F
        if length == 126:
            (length,) = struct.unpack('!H', self._read_exact(2))
        elif length == 127:
            (length,) = struct.unpack('!Q', self._read_exact(8))
        mask_key = self._read_exact(4) if masked else None
        payload = self._read_exact(length)
        if masked:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        if opcode == 0x8:    # close
            raise RuntimeError('CDP server closed connection')
        if opcode in (0x9, 0xA):  # ping/pong — skip
            return self._recv_frame()
        return payload.decode('utf-8', 'replace')

    def call(self, method, params, timeout=None):
        """Send an RPC and wait for the matching response."""
        rid = self._next_id
        self._next_id += 1
        msg = json.dumps({'id': rid, 'method': method, 'params': params})
        self._send_frame(msg.encode('utf-8'))
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            text = self._recv_frame()
            try: ev = json.loads(text)
            except Exception: continue
            if ev.get('id') == rid:
                if 'error' in ev:
                    raise RuntimeError(f'CDP error in {method}: {ev["error"]}')
                return ev
            # Ignore async events (Page.loadEventFired etc.) until our id arrives
        raise TimeoutError(f'CDP {method} timed out after {timeout or self.timeout}s')

    def wait_for_event(self, method, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            text = self._recv_frame()
            try: ev = json.loads(text)
            except Exception: continue
            if ev.get('method') == method:
                return ev
        raise TimeoutError(f'CDP event {method} did not fire within {timeout}s')

    def close(self):
        try:
            # Send close frame (opcode 0x8) — empty payload, masked.
            mask = os.urandom(4)
            self.sock.sendall(struct.pack('!BB', 0x88, 0x80) + mask)
        except Exception:
            pass
        try: self.sock.close()
        except Exception: pass


class Handler(http.server.SimpleHTTPRequestHandler):
    # HTTP/1.0 + Connection: close gives us read-until-close streaming,
    # which is exactly what SSE needs without fighting chunked encoding.
    protocol_version = 'HTTP/1.0'

    def end_headers(self):
        # Disable caching for local-dev iteration so HTML/JSX edits land on
        # next reload without browser caching tripping us up.
        self.send_header('Cache-Control', 'no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        # CORS — required so the CafresoAI SvelteKit frontend (running on a
        # different origin, e.g. localhost:5174 in dev or an ICP asset canister
        # in prod) can hit /health, /vault/*, /api/* etc. on the OCI container.
        # We echo back the requesting Origin when present (safer than '*' when
        # credentials are involved); fall back to '*' for plain probes.
        origin = self.headers.get('Origin', '*') if hasattr(self, 'headers') else '*'
        self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Access-Control-Allow-Credentials', 'true')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers',
                         'Content-Type, Authorization, X-User-Principal, X-API-Key, '
                         'anthropic-version, x-api-key, X-Vault-Format')
        self.send_header('Access-Control-Max-Age', '86400')
        self.send_header('Vary', 'Origin')
        super().end_headers()

    def _route(self):
        for prefix, target in ROUTES.items():
            if self.path.startswith(prefix):
                return prefix, target
        return None, None

    def do_GET(self):
        # /idle is the signal the fleet's reap-idle uses to stop idle containers
        # (free the A1 pool + pause billing). Report seconds since the last
        # *user-facing* request. Health/idle pings themselves don't count as
        # activity (they'd keep a container "busy" forever).
        if self.path == '/idle':
            import time as _t
            return self._send_json(200, {'idle_seconds': int(_t.time() - _LAST_ACTIVITY[0])})
        _touch_activity(self.path)
        if self.path == '/health':
            return self._health()
        if self.path.startswith('/hq/'):
            return self._hq_handler('GET')
        if self.path.startswith('/brave/'):
            return self._brave_search()
        if self.path == '/hermes/capability':
            return self._hermes_get_capability()
        if self.path == '/hermes/model':
            return self._hermes_get_model()
        if self.path.startswith('/hermes/'):
            return self._hermes_proxy('GET')
        if self.path.startswith('/vault/'):
            return self._vault('GET')
        if self.path == '/claudecode/status':
            return self._claudecode_status()
        if self.path == '/openclaw/status':
            return self._openclaw_status()
        if self.path == '/codex/status':
            return self._codex_status()
        if self.path == '/terminal/status':
            return self._terminal_status()
        if self.path == '/terminal/nonce':
            return self._terminal_nonce()
        if self.path.startswith('/terminal/spawn'):
            return self._terminal_spawn()
        if self.path.startswith('/terminal/pty'):
            return self._terminal_pty_ws()
        if self.path.startswith('/fs/browse'):
            return self._fs_browse()
        if self.path == '/browser/status':
            return self._browser_status()
        if self.path.startswith('/browser/fetch'):
            return self._browser_fetch()
        if self.path.startswith('/browser/screenshot'):
            return self._browser_screenshot()
        if self.path.startswith('/approvals/external/wait'):
            return self._approval_wait()
        if self.path == '/approvals/external/list':
            return self._approval_list()
        prefix, target = self._route()
        if target:
            return self._proxy('GET', prefix, target)
        return super().do_GET()

    def do_POST(self):
        _touch_activity(self.path)
        if self.path == '/hermes/capability':
            return self._hermes_set_capability()
        if self.path == '/hermes/model':
            return self._hermes_set_model()
        if self.path == '/hermes/openrouter-key':
            return self._hermes_set_openrouter_key()
        if self.path.startswith('/hermes/'):
            return self._hermes_proxy('POST')
        if self.path.startswith('/vault/'):
            return self._vault('POST')
        if self.path == '/claudecode/configure':
            return self._claudecode_configure()
        if self.path == '/codex/configure':
            return self._codex_configure()
        if self.path == '/claudecode/stream':
            return self._claudecode_stream()
        if self.path == '/openclaw/stream':
            return self._openclaw_stream()
        if self.path == '/codex/stream':
            return self._codex_stream()
        if self.path == '/terminal/stream':
            return self._terminal_stream()
        if self.path == '/projects/clone':
            return self._projects_clone()
        if self.path == '/tools/exec':
            return self._tool_exec()
        if self.path == '/approvals/external':
            return self._approval_submit()
        if self.path == '/approvals/external/decide':
            return self._approval_decide()
        if self.path == '/export/pptx':
            return self._export_pptx()
        if self.path == '/export/docx':
            return self._export_docx()
        if self.path == '/export/pdf':
            return self._export_pdf()
        if self.path == '/generate/image':
            return self._generate_image()
        if self.path == '/generate/video':
            return self._generate_video()
        prefix, target = self._route()
        if target:
            return self._proxy('POST', prefix, target)
        self.send_error(405)

    def do_PUT(self):
        if self.path.startswith('/hq/'):
            return self._hq_handler('PUT')
        if self.path.startswith('/vault/'):
            return self._vault('PUT')
        self.send_error(405)

    def do_DELETE(self):
        if self.path.startswith('/vault/'):
            return self._vault('DELETE')
        self.send_error(405)

    def do_OPTIONS(self):
        prefix, target = self._route()
        if target:
            return self._proxy('OPTIONS', prefix, target)
        # Default: respond 204 No Content with CORS headers (added by end_headers).
        # This handles preflight requests from the SvelteKit frontend for /health,
        # /vault/*, /api/anthropic/*, etc. without needing per-route OPTIONS.
        self.send_response(204)
        self.send_header('content-length', '0')
        self.end_headers()

    # ---- Claude Code (Pro/Max subscription via local CLI) -----------------
    def _claudecode_resolve(self):
        """Find the claude binary. Returns absolute path or None."""
        if _claudecode_bin and pathlib.Path(_claudecode_bin).is_file():
            return _claudecode_bin
        # shutil.which respects PATH and Windows .cmd/.exe extensions.
        return shutil.which(_claudecode_bin or 'claude')

    def _health(self):
        """GET /health — lightweight liveness probe for load balancers and companion detection."""
        import platform
        oci_ready = (
            bool(_oci_vault_namespace and _oci_vault_bucket)
            if _vault_backend == 'oci' else None
        )
        return self._send_json(200, {
            'status':           'ok',
            'version':          '1.0.0',
            'mode':             _fleet_mode,
            'vault_backend':    _vault_backend,
            'uptime_seconds':   int(time.time() - _server_start_time),
            'platform':         platform.system(),
            'user_principal':   _fleet_user_principal,
            'claude_code':      bool(_claudecode_bin or shutil.which('claude')),
            'codex':            bool(_codex_bin or shutil.which('codex')),
            'oci_vault_ready':  oci_ready,
        })

    def _claudecode_status(self):
        bin_ = self._claudecode_resolve()
        return self._send_json(200, {
            'configured': bool(bin_),
            'binary': bin_ or '',
            'override': _claudecode_bin or '',
        })

    def _claudecode_configure(self):
        global _claudecode_bin
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})
        path = (body.get('binary') or '').strip()
        if path and not pathlib.Path(path).is_file():
            return self._send_json(400, {'error': f'not a file: {path}'})
        _claudecode_bin = path
        return self._claudecode_status()

    def _claudecode_stream(self):
        """Stream a chat completion through the local `claude` CLI.

        Body: {messages, system, model, maxTokens?}
        We compose a single prompt from system + history + last user turn,
        spawn `claude --print --output-format=stream-json --model <m> ...`,
        pipe the prompt to stdin, and parse the line-delimited JSON events
        on stdout. Each text delta is forwarded as an SSE-shaped frame
        (matching what claude-client.jsx expects from the OpenAI-compat
        backends, so we can reuse parseSSE on the client).
        """
        bin_ = self._claudecode_resolve()
        if not bin_:
            return self._send_json(503, {
                'error': 'claude CLI not found — install Claude Code or set OPENCLAW_CLAUDE_BIN'
            })
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})

        messages = body.get('messages') or []
        system   = (body.get('system') or '').strip()
        model    = (body.get('model') or '').strip()

        # Compose a single prompt for non-interactive --print mode.
        # Roles get prefixed so the model sees the conversation shape; we
        # extract the last user turn to be the "current" message.
        history_lines = []
        last_user = ''
        for m in messages:
            role = (m.get('role') or 'user').upper()
            content = (m.get('content') or '').strip()
            if not content: continue
            if role == 'USER': last_user = content
            history_lines.append(f'{role}: {content}')
        prompt = '\n\n'.join(history_lines) if history_lines else last_user
        if not prompt:
            return self._send_json(400, {'error': 'no prompt'})

        # Use disallowed-tools to suppress all tool use in non-elevated mode.
        # --allowed-tools '' (empty string) is rejected by Claude CLI; using
        # --disallowed-tools with a wildcard is the correct idiom.
        cmd = [bin_, '--print',
               '--output-format', 'stream-json',
               '--verbose',
               '--disallowed-tools', 'Bash,Edit,Write,MultiEdit,NotebookEdit,WebFetch,WebSearch,TodoWrite,Task',
               '--input-format', 'text']
        if model:
            cmd += ['--model', model]
        if system:
            cmd += ['--append-system-prompt', system]

        # Use project cwd if provided and valid, otherwise first allowed dir.
        _cc_cwd = _openclaw_allowed_dirs[0] if _openclaw_allowed_dirs else None
        req_cwd = (body.get('cwd') or '').strip()
        if req_cwd:
            try:
                cwd_p = pathlib.Path(req_cwd).resolve()
                for d in _openclaw_allowed_dirs:
                    try:
                        cwd_p.relative_to(pathlib.Path(d).resolve())
                        if cwd_p.is_dir():
                            _cc_cwd = str(cwd_p)
                        break
                    except ValueError:
                        continue
            except OSError:
                pass
        import copy as _copy
        _cc_env = _copy.deepcopy(os.environ)
        for _d in [r'C:\Program Files\Git\usr\bin',
                   r'C:\Program Files\Git\bin',
                   r'C:\Program Files\Git\mingw64\bin']:
            if os.path.isdir(_d) and _d not in _cc_env.get('PATH', ''):
                _cc_env['PATH'] = _d + os.pathsep + _cc_env.get('PATH', '')

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, bufsize=1, encoding='utf-8',
                cwd=_cc_cwd,
                env=_cc_env,
            )
        except FileNotFoundError as e:
            return self._send_json(500, {'error': f'spawn: {e}'})

        # Send the prompt and close stdin so the CLI knows we're done.
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception as e:
            try: proc.kill()
            except Exception: pass
            return self._send_json(500, {'error': f'stdin: {e}'})

        # Stream stdout to the client as SSE-style "data: <json>\n\n" frames
        # in the OpenAI-compatible chat-completion delta shape, so the
        # existing client parser works without changes.
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

        # Drain stderr in a thread so the pipe doesn't fill up and stall.
        stderr_buf = []
        def _drain_err():
            try:
                for line in proc.stderr:
                    stderr_buf.append(line)
            except Exception:
                pass
        threading.Thread(target=_drain_err, daemon=True).start()

        in_tokens = 0
        out_tokens = 0
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line: continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Claude Code's stream-json wraps Anthropic message events.
                # Common shapes:
                #   {"type":"system","subtype":"init", ...}
                #   {"type":"assistant","message":{"content":[{"type":"text","text":"…"}], "usage":{...}}}
                #   {"type":"result","result":"…","usage":{...}}
                t = ev.get('type')
                if t == 'assistant':
                    msg = ev.get('message') or {}
                    for block in (msg.get('content') or []):
                        if block.get('type') == 'text':
                            text = block.get('text') or ''
                            if text:
                                ok = write_sse({
                                    'choices': [{
                                        'index': 0,
                                        'delta': {'content': text},
                                    }],
                                })
                                if not ok: break
                    u = msg.get('usage')
                    if u:
                        in_tokens  = u.get('input_tokens', in_tokens)
                        out_tokens = u.get('output_tokens', out_tokens)
                elif t == 'result':
                    u = ev.get('usage') or {}
                    in_tokens  = u.get('input_tokens',  in_tokens)
                    out_tokens = u.get('output_tokens', out_tokens)
                elif t == 'error':
                    write_sse({'choices': [{'index': 0, 'delta': {
                        'content': f"\n\n⚠ Claude Code error: {ev.get('message') or ev}"}}]})
            # Final usage frame so the client can attribute tokens.
            if in_tokens or out_tokens:
                write_sse({
                    'choices': [],
                    'usage': {
                        'prompt_tokens': in_tokens,
                        'completion_tokens': out_tokens,
                        'total_tokens': in_tokens + out_tokens,
                    },
                })
        finally:
            try: proc.wait(timeout=2)
            except Exception:
                try: proc.kill()
                except Exception: pass
            # If exit was non-zero and we never wrote any text, surface stderr.
            if proc.returncode and proc.returncode != 0 and not (in_tokens or out_tokens):
                err_text = ('\n'.join(stderr_buf))[:600] or f'exit {proc.returncode}'
                write_sse({'choices': [{'index': 0, 'delta': {
                    'content': f"\n\n⚠ Claude Code exited {proc.returncode}: {err_text}"}}]})

    # ---- Tool execution proxy (bracket-format tools for any provider) ------
    def _validate_path(self, path):
        """Resolve path and verify it falls within OPENCLAW_ALLOWED_DIRS.
        In local mode with no explicit OPENCLAW_ALLOWED_DIRS env var the check
        is skipped — the user is developing locally and can access their own files.
        In container mode or when the admin explicitly set OPENCLAW_ALLOWED_DIRS
        the strict whitelist is enforced.
        """
        p = pathlib.Path(path).resolve()
        if not _ALLOWED_DIRS_EXPLICIT and _RUNTIME_ENV == 'local':
            return p  # local default: no restriction, user accesses own files
        for d in _openclaw_allowed_dirs:
            try:
                p.relative_to(pathlib.Path(d).resolve())
                return p
            except ValueError:
                continue
        raise PermissionError(f'Path outside allowed directories: {path!r}')

    def _projects_clone(self):
        """Clone a GitHub repo into the first allowed dir.
        Body: {url, name?, depth?}
          url   — github URL or owner/repo shorthand
          name  — optional override for the local folder name
          depth — 1 (default, shallow) or 0 (full history)
        Returns: {ok, path, name, stderr?}
        """
        if not _openclaw_allowed_dirs:
            return self._send_json(503, {'ok': False,
                'error': 'OPENCLAW_ALLOWED_DIRS not set — clone disabled'})
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'ok': False, 'error': 'bad json'})

        raw_url = (req.get('url') or '').strip()
        if not raw_url:
            return self._send_json(400, {'ok': False, 'error': 'url required'})

        # Normalize: 'owner/repo' → 'https://github.com/owner/repo'
        if not raw_url.startswith(('http://', 'https://', 'git@')):
            if '/' in raw_url and not raw_url.startswith('/'):
                raw_url = 'https://github.com/' + raw_url
            else:
                return self._send_json(400, {'ok': False,
                    'error': 'unrecognized url; use https://github.com/owner/repo or owner/repo'})

        # Strip trailing .git or trailing slash for name derivation
        repo_name = (req.get('name') or '').strip()
        if not repo_name:
            tail = raw_url.rstrip('/').split('/')[-1]
            if tail.endswith('.git'): tail = tail[:-4]
            repo_name = tail
        # Sanitize name: only allow safe chars
        safe = ''.join(c for c in repo_name if c.isalnum() or c in '-_.')
        if not safe:
            return self._send_json(400, {'ok': False, 'error': 'invalid repo name'})
        repo_name = safe

        target = pathlib.Path(_openclaw_allowed_dirs[0]) / repo_name
        try:
            target = target.resolve()
            # Must remain inside the allowed dir
            target.relative_to(pathlib.Path(_openclaw_allowed_dirs[0]).resolve())
        except (ValueError, OSError) as e:
            return self._send_json(400, {'ok': False, 'error': f'invalid target: {e}'})

        if target.exists():
            return self._send_json(409, {'ok': False,
                'error': f'destination already exists: {target}',
                'path': str(target), 'name': repo_name})

        git_bin = shutil.which('git') or shutil.which('git.exe')
        if not git_bin:
            return self._send_json(503, {'ok': False, 'error': 'git not found in PATH'})

        depth = req.get('depth', 1)
        cmd = [git_bin, 'clone']
        if depth and int(depth) > 0:
            cmd += ['--depth', str(int(depth))]
        cmd += [raw_url, str(target)]

        sys.stderr.write(f'[projects] clone {raw_url} → {target}\n')
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return self._send_json(504, {'ok': False, 'error': 'clone timed out (5min)'})
        except Exception as e:
            return self._send_json(500, {'ok': False, 'error': f'spawn git: {e}'})

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or '')[:1000]
            return self._send_json(502, {'ok': False,
                'error': f'git clone failed (exit {proc.returncode})',
                'stderr': err})

        return self._send_json(200, {
            'ok': True,
            'path': str(target),
            'name': repo_name,
            'url': raw_url,
        })

    def _tool_exec(self):
        """Execute a bracket-format tool call dispatched by the frontend.
        Body: {tool, arg, body?}
        Requires OPENCLAW_ALLOWED_DIRS to be configured (same gate as /openclaw/stream).
        BASH additionally requires 'Bash' in OPENCLAW_ALLOWED_TOOLS.
        """
        if not _openclaw_allowed_dirs:
            return self._send_json(503, {'ok': False,
                'error': 'OPENCLAW_ALLOWED_DIRS not set — tool execution disabled'})
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'ok': False, 'error': 'bad json'})

        tool    = (req.get('tool') or '').upper()
        arg     = (req.get('arg') or '').strip()
        content = req.get('body') or ''

        # Optional project cwd — if supplied and valid (within allowed dirs),
        # use it as the base for relative paths and BASH cwd.
        req_cwd = (req.get('cwd') or '').strip()
        tool_cwd = _openclaw_allowed_dirs[0] if _openclaw_allowed_dirs else os.getcwd()
        if req_cwd:
            try:
                cwd_p = pathlib.Path(req_cwd).resolve()
                if cwd_p.is_dir():
                    if not _ALLOWED_DIRS_EXPLICIT and _RUNTIME_ENV == 'local':
                        tool_cwd = str(cwd_p)  # local default: trust any existing dir
                    else:
                        for d in _openclaw_allowed_dirs:
                            try:
                                cwd_p.relative_to(pathlib.Path(d).resolve())
                                tool_cwd = str(cwd_p)
                                break
                            except ValueError:
                                continue
            except OSError:
                pass

        def _resolve_arg(raw):
            """Resolve a path arg — if relative, anchor to tool_cwd."""
            p = pathlib.Path(raw)
            if not p.is_absolute():
                p = pathlib.Path(tool_cwd) / p
            return self._validate_path(str(p))

        try:
            if tool == 'FILE_READ':
                p = _resolve_arg(arg)
                if not p.exists():
                    result = f'File not found: {arg}'
                else:
                    text = p.read_text(encoding='utf-8', errors='replace')
                    if len(text) > 8000:
                        text = text[:8000] + '\n…(truncated to 8000 chars)'
                    result = text

            elif tool == 'DIR_LIST':
                p = _resolve_arg(arg or tool_cwd)
                if not p.is_dir():
                    result = f'Not a directory: {arg}'
                else:
                    entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
                    lines = []
                    for e in entries[:300]:
                        lines.append(e.name + '/' if e.is_dir() else f'{e.name}  ({e.stat().st_size} B)')
                    result = '\n'.join(lines) or '(empty directory)'
                    if len(lines) == 300:
                        result += '\n…(truncated at 300 entries)'

            elif tool == 'FILE_WRITE':
                p = _resolve_arg(arg)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding='utf-8')
                result = f'Wrote {len(content)} chars → {p}'

            elif tool == 'BASH':
                if 'Bash' not in _openclaw_allowed_tools:
                    return self._send_json(403, {'ok': False,
                        'error': 'Bash not in OPENCLAW_ALLOWED_TOOLS — add it to enable shell access'})
                proc = subprocess.run(
                    arg, shell=True, capture_output=True, text=True, timeout=30,
                    cwd=tool_cwd,
                )
                out = proc.stdout
                if proc.stderr:
                    out += '\nSTDERR:\n' + proc.stderr
                if len(out) > 4000:
                    out = out[:4000] + '\n…(truncated)'
                result = (out or '(no output)')
                if proc.returncode != 0:
                    result += f'\n(exit {proc.returncode})'

            else:
                return self._send_json(400, {'ok': False, 'error': f'Unknown tool: {tool}'})

            return self._send_json(200, {'ok': True, 'result': result})

        except PermissionError as e:
            return self._send_json(403, {'ok': False, 'error': str(e)})
        except subprocess.TimeoutExpired:
            return self._send_json(200, {'ok': False, 'error': 'command timed out (30s)'})
        except Exception as e:
            return self._send_json(500, {'ok': False, 'error': str(e)})

    # ---- OpenClaw (elevated agent: Claude Code with constrained tools) ---
    def _openclaw_status(self):
        """Report whether the elevated endpoint is wired up. The client uses
        this to disable the 🛡 toggle when no allowlist is configured."""
        bin_ = self._claudecode_resolve()
        # Validate that every configured dir exists — a typo'd dir is a
        # silent landmine (claude would just refuse the read).
        dirs_ok = []
        dirs_bad = []
        for d in _openclaw_allowed_dirs:
            (dirs_ok if pathlib.Path(d).is_dir() else dirs_bad).append(d)
        return self._send_json(200, {
            'configured': bool(bin_) and bool(dirs_ok) and bool(_openclaw_allowed_tools),
            'binary': bin_ or '',
            'allowedDirs': dirs_ok,
            'badDirs': dirs_bad,
            'allowedTools': list(_openclaw_allowed_tools),
        })

    def _codex_status(self):
        """Report whether the Codex elevated endpoint is wired up."""
        bin_ = self._codex_resolve()
        dirs_ok, dirs_bad = [], []
        for d in _openclaw_allowed_dirs:
            (dirs_ok if pathlib.Path(d).is_dir() else dirs_bad).append(d)
        return self._send_json(200, {
            'configured': bool(bin_) and bool(dirs_ok),
            'binary': bin_ or '',
            'override': _codex_bin or '',
            'allowedDirs': dirs_ok,
            'badDirs': dirs_bad,
            'allowedTools': list(_openclaw_allowed_tools),
        })

    # ──────────────────────────────────────────────────────────────────────
    # Browser shim — gives agents a way to fetch URLs and grab screenshots.
    #
    # /browser/fetch?url=...        Pure-stdlib HTTP GET + readable text
    #                               extraction. Always available; works for
    #                               any agent regardless of whether a
    #                               browser is running. Suitable for "read
    #                               this article" or "scrape this docs page"
    #                               jobs that don't need JS.
    #
    # /browser/screenshot?url=...   Talks to a Chromium-based browser via
    #                               the Chrome DevTools Protocol (CDP). The
    #                               user must have launched Brave/Chrome
    #                               with --remote-debugging-port=9222 OR
    #                               OPENCLAW_BROWSER_CDP_URL must be set.
    #                               Returns base64 PNG inside JSON. If no
    #                               CDP target is reachable we return 503
    #                               with a clear "how to enable" hint
    #                               instead of crashing — the rest of the
    #                               app keeps working.
    #
    # /browser/status               One-shot probe — tells the UI whether
    #                               screenshots are available so we can
    #                               surface the right hint.
    # ──────────────────────────────────────────────────────────────────────
    def _browser_status(self):
        cdp_ok, cdp_info = self._browser_cdp_probe()
        return self._send_json(200, {
            'fetchAvailable': True,            # always works (urllib)
            'screenshotAvailable': cdp_ok,
            'cdp': cdp_info,
            'cdpHint': (
                'Launch Brave/Chrome with --remote-debugging-port=9222, or '
                'set OPENCLAW_BROWSER_CDP_URL=http://host:port to enable '
                'screenshots and JS-rendered fetch.'
            ),
        })

    def _browser_cdp_probe(self):
        """Find a CDP endpoint. Tries OPENCLAW_BROWSER_CDP_URL first,
        then localhost:9222 (Brave/Chrome default). Returns (ok, info)."""
        candidates = []
        env_url = os.environ.get('OPENCLAW_BROWSER_CDP_URL', '').strip()
        if env_url:
            candidates.append(env_url.rstrip('/'))
        candidates.append('http://127.0.0.1:9222')
        for base in candidates:
            try:
                u = urllib.parse.urlparse(base)
                conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=2)
                conn.request('GET', '/json/version')
                resp = conn.getresponse()
                if resp.status == 200:
                    info = json.loads(resp.read().decode('utf-8', 'replace'))
                    conn.close()
                    return True, {'base': base, 'browser': info.get('Browser', '?')}
                conn.close()
            except Exception:
                continue
        return False, {'base': None, 'browser': None}

    def _browser_fetch(self):
        """GET /browser/fetch?url=...&max_chars=N
        Returns { url, status, title, text, length } where text is the
        page's readable content with HTML stripped + whitespace normalised.
        No JS execution — for that, use /browser/screenshot which goes
        through CDP. Hard cap on size (default 50KB) so a giant page
        doesn't blow up the agent's context."""
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        url = (params.get('url') or [''])[0].strip()
        try:
            max_chars = int((params.get('max_chars') or ['50000'])[0])
        except ValueError:
            max_chars = 50000
        max_chars = max(500, min(max_chars, 200000))
        if not url:
            return self._send_json(400, {'error': 'url query parameter required'})
        if not (url.startswith('http://') or url.startswith('https://')):
            return self._send_json(400, {'error': 'url must start with http:// or https://'})
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'OpenclawHQ/1.0 (+browser-shim)',
                'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                status = r.status
                ctype = r.headers.get('Content-Type', '')
                # Read up to 2MB raw before processing
                raw = r.read(2 * 1024 * 1024)
        except urllib.error.HTTPError as e:
            return self._send_json(200, {
                'url': url, 'status': e.code,
                'error': f'HTTP {e.code}: {e.reason}',
                'text': '', 'title': '', 'length': 0,
            })
        except Exception as e:
            return self._send_json(502, {'error': f'fetch failed: {type(e).__name__}: {e}'})
        # Decode (best-effort)
        encoding = 'utf-8'
        if 'charset=' in ctype.lower():
            try: encoding = ctype.split('charset=', 1)[1].split(';')[0].strip() or 'utf-8'
            except Exception: pass
        try: html = raw.decode(encoding, errors='replace')
        except Exception: html = raw.decode('utf-8', errors='replace')
        # Title
        m_title = re.search(r'<title[^>]*>([^<]*)</title>', html, re.IGNORECASE)
        title = (m_title.group(1).strip() if m_title else '')[:200]
        # Strip scripts, styles, noscript, then tags. Cheap but effective.
        cleaned = re.sub(r'<script[\s\S]*?</script>', ' ', html, flags=re.IGNORECASE)
        cleaned = re.sub(r'<style[\s\S]*?</style>', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<noscript[\s\S]*?</noscript>', ' ', cleaned, flags=re.IGNORECASE)
        # Preserve paragraph breaks before stripping tags
        cleaned = re.sub(r'</(p|div|h[1-6]|li|br|tr)>', '\n', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<br\s*/?>', '\n', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
        # Collapse whitespace; keep blank lines
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        cleaned = re.sub(r'\n[ \t]*\n+', '\n\n', cleaned)
        # HTML entity decode
        try:
            import html as _htmlmod
            cleaned = _htmlmod.unescape(cleaned)
        except Exception:
            pass
        cleaned = cleaned.strip()
        truncated = len(cleaned) > max_chars
        if truncated:
            cleaned = cleaned[:max_chars] + f'\n\n[…truncated, {len(cleaned) - max_chars} more chars]'
        return self._send_json(200, {
            'url': url, 'status': status, 'title': title,
            'text': cleaned, 'length': len(cleaned), 'truncated': truncated,
        })

    def _browser_screenshot(self):
        """GET /browser/screenshot?url=...&width=1280&height=800&fullPage=0
        Drives a Chromium-based browser via CDP to navigate + screenshot.
        Returns { url, width, height, png } where png is a data: URL.
        Requires a running browser with --remote-debugging-port=9222
        (or OPENCLAW_BROWSER_CDP_URL pointing at one).

        We use the lightweight HTTP+WS subset of CDP via stdlib only:
          1. GET /json/version  → discover webSocketDebuggerUrl
          2. PUT /json/new       → create a fresh tab (so we don't
                                   stomp on the user's actual browsing)
          3. WS dance: Page.navigate → Page.captureScreenshot
          4. DELETE /json/close/<id> → tidy up
        """
        cdp_ok, cdp_info = self._browser_cdp_probe()
        if not cdp_ok:
            return self._send_json(503, {
                'error': 'No CDP-enabled browser detected.',
                'hint': (
                    'Launch Brave or Chrome with --remote-debugging-port=9222 '
                    '(or set OPENCLAW_BROWSER_CDP_URL to a different host:port).'
                ),
            })
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        url = (params.get('url') or [''])[0].strip()
        width = int((params.get('width') or ['1280'])[0])
        height = int((params.get('height') or ['800'])[0])
        full_page = (params.get('fullPage') or ['0'])[0] in ('1', 'true', 'yes')
        if not url:
            return self._send_json(400, {'error': 'url query parameter required'})
        try:
            png_b64 = self._cdp_screenshot(cdp_info['base'], url, width, height, full_page)
        except Exception as e:
            return self._send_json(502, {'error': f'screenshot failed: {type(e).__name__}: {e}'})
        return self._send_json(200, {
            'url': url, 'width': width, 'height': height,
            'png': 'data:image/png;base64,' + png_b64,
        })

    def _cdp_screenshot(self, base, url, width, height, full_page):
        """Open a fresh tab via CDP, navigate, screenshot, close tab.
        Pure stdlib WebSocket — small enough to do by hand for one
        request/response per CDP method. Cap timeout per step."""
        # 1. Open a new tab.
        u = urllib.parse.urlparse(base)
        conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=10)
        conn.request('PUT', '/json/new?about:blank')
        resp = conn.getresponse()
        if resp.status not in (200, 201):
            raise RuntimeError(f'/json/new returned {resp.status}')
        tab = json.loads(resp.read().decode('utf-8', 'replace'))
        conn.close()
        ws_url = tab['webSocketDebuggerUrl']
        tab_id = tab['id']
        try:
            # 2. WS dance.
            ws = _CDPWebSocket(ws_url, timeout=20)
            ws.connect()
            # Set viewport
            ws.call('Emulation.setDeviceMetricsOverride',
                    {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
            ws.call('Page.enable', {})
            ws.call('Page.navigate', {'url': url})
            # Wait for load (up to 12s) — poll lifecycle events.
            ws.wait_for_event('Page.loadEventFired', timeout=12)
            # Tiny grace period for late-rendering JS.
            time.sleep(0.6)
            cap = ws.call('Page.captureScreenshot',
                          {'format': 'png', 'captureBeyondViewport': bool(full_page)})
            ws.close()
            return cap['result']['data']
        finally:
            # 3. Close tab.
            try:
                conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=5)
                conn.request('GET', f'/json/close/{tab_id}')
                conn.getresponse().read()
                conn.close()
            except Exception:
                pass

    def _openclaw_stream(self):
        """Streaming chat for ELEVATED agents. Same SSE-shaped output as
        /claudecode/stream so the client uses one parser. Differences:
          - tools enabled (--allowed-tools <server-side allowlist>)
          - working set bound to --add-dir <each allowed dir>
          - refuses if either allowlist is empty (safe default)
        """
        bin_ = self._claudecode_resolve()
        if not bin_:
            return self._send_json(503, {
                'error': 'claude CLI not found — install Claude Code or set OPENCLAW_CLAUDE_BIN'
            })
        if not _openclaw_allowed_dirs:
            return self._send_json(503, {
                'error': 'OPENCLAW_ALLOWED_DIRS not set — elevated endpoint disabled'
            })
        if not _openclaw_allowed_tools:
            return self._send_json(503, {
                'error': 'OPENCLAW_ALLOWED_TOOLS empty — elevated endpoint disabled'
            })
        # Refuse if any configured dir is missing — easier to fix typos than
        # to debug a silent permission error.
        for d in _openclaw_allowed_dirs:
            if not pathlib.Path(d).is_dir():
                return self._send_json(503, {
                    'error': f'OPENCLAW_ALLOWED_DIRS includes missing dir: {d}'
                })

        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})

        messages = body.get('messages') or []
        system   = (body.get('system') or '').strip()
        model    = (body.get('model') or '').strip()
        agent    = (body.get('agentName') or 'elevated-agent').strip()[:60]

        history_lines = []
        for m in messages:
            role = (m.get('role') or 'user').upper()
            content = (m.get('content') or '').strip()
            if not content: continue
            history_lines.append(f'{role}: {content}')
        prompt = '\n\n'.join(history_lines)
        if not prompt:
            return self._send_json(400, {'error': 'no prompt'})

        # Compose the Claude Code command. Critical bits:
        #   --allowed-tools <comma-list>  bounds what Claude can DO
        #   --add-dir <abs-path>          bounds where it can READ/WRITE
        # Both come from server-side env, NOT from the request body.
        cmd = [bin_, '--print',
               '--output-format', 'stream-json',
               '--verbose',
               '--allowed-tools', ','.join(_openclaw_allowed_tools),
               '--input-format', 'text']
        for d in _openclaw_allowed_dirs:
            cmd += ['--add-dir', d]
        if model:
            cmd += ['--model', model]
        # Always prepend a guard-rail system note so the elevated agent knows
        # it's running under HQ's authority and what its boundaries are.
        guard = (
            f'You are {agent}, an elevated HQ agent with computer access. '
            f'You are restricted to these directories: {", ".join(_openclaw_allowed_dirs)}. '
            'When you intend to perform an action with side effects, first emit '
            '[NEEDS_APPROVAL: <one-line description>] and stop until the boss replies.'
        )
        full_system = guard + ('\n\n' + system if system else '')
        cmd += ['--append-system-prompt', full_system]

        # Audit: log every elevated invocation server-side so there's a
        # tamper-resistant record outside the browser.
        sys.stderr.write(f'[openclaw] elevated stream: agent={agent} model={model or "(default)"} '
                         f'dirs={_openclaw_allowed_dirs} tools={_openclaw_allowed_tools}\n')

        # Use project cwd if provided and valid, otherwise first allowed dir.
        agent_cwd = _openclaw_allowed_dirs[0] if _openclaw_allowed_dirs else None
        req_cwd = (body.get('cwd') or '').strip()
        if req_cwd:
            try:
                cwd_p = pathlib.Path(req_cwd).resolve()
                for d in _openclaw_allowed_dirs:
                    try:
                        cwd_p.relative_to(pathlib.Path(d).resolve())
                        if cwd_p.is_dir():
                            agent_cwd = str(cwd_p)
                        break
                    except ValueError:
                        continue
            except OSError:
                pass

        # Ensure Git Bash is in PATH so Claude Code's Bash tool can find
        # bash.exe on Windows. Without this, Bash exits 255 with
        # "The system cannot find the path specified."
        import copy as _copy
        agent_env = _copy.deepcopy(os.environ)
        _git_bash_dirs = [
            r'C:\Program Files\Git\usr\bin',
            r'C:\Program Files\Git\bin',
            r'C:\Program Files\Git\mingw64\bin',
        ]
        _path_parts = agent_env.get('PATH', '').split(os.pathsep)
        for _d in reversed(_git_bash_dirs):
            if os.path.isdir(_d) and _d not in _path_parts:
                agent_env['PATH'] = _d + os.pathsep + agent_env.get('PATH', '')

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, bufsize=1, encoding='utf-8',
                cwd=agent_cwd,
                env=agent_env,
            )
        except FileNotFoundError as e:
            return self._send_json(500, {'error': f'spawn: {e}'})

        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception as e:
            try: proc.kill()
            except Exception: pass
            return self._send_json(500, {'error': f'stdin: {e}'})

        # SSE response — same shape /claudecode/stream emits.
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

        stderr_buf = []
        def _drain_err():
            try:
                for line in proc.stderr:
                    stderr_buf.append(line)
            except Exception:
                pass
        threading.Thread(target=_drain_err, daemon=True).start()

        in_tokens = 0
        out_tokens = 0
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
                        if block.get('type') == 'text':
                            text = block.get('text') or ''
                            if text:
                                ok = write_sse({
                                    'choices': [{
                                        'index': 0,
                                        'delta': {'content': text},
                                    }],
                                })
                                if not ok: break
                    u = msg.get('usage')
                    if u:
                        in_tokens  = u.get('input_tokens',  in_tokens)
                        out_tokens = u.get('output_tokens', out_tokens)
                elif t == 'result':
                    u = ev.get('usage') or {}
                    in_tokens  = u.get('input_tokens',  in_tokens)
                    out_tokens = u.get('output_tokens', out_tokens)
                elif t == 'error':
                    write_sse({'choices': [{'index': 0, 'delta': {
                        'content': f"\n\n⚠ OpenClaw error: {ev.get('message') or ev}"}}]})
            if in_tokens or out_tokens:
                write_sse({
                    'choices': [],
                    'usage': {
                        'prompt_tokens': in_tokens,
                        'completion_tokens': out_tokens,
                        'total_tokens': in_tokens + out_tokens,
                    },
                })
        finally:
            try: proc.wait(timeout=2)
            except Exception:
                try: proc.kill()
                except Exception: pass
            if proc.returncode and proc.returncode != 0 and not (in_tokens or out_tokens):
                err_text = ('\n'.join(stderr_buf))[:600] or f'exit {proc.returncode}'
                write_sse({'choices': [{'index': 0, 'delta': {
                    'content': f"\n\n⚠ OpenClaw exited {proc.returncode}: {err_text}"}}]})

    # ---- Codex CLI elevated agent ----------------------------------------
    def _codex_resolve(self):
        if _codex_bin and pathlib.Path(_codex_bin).is_file():
            return _codex_bin
        # On Windows, prefer codex.cmd over the extensionless npm wrapper.
        # The extensionless file is a shell script that Windows can't exec
        # directly — subprocess.Popen on it raises OSError 193 ("not a valid
        # Win32 application"), which used to escape the except FileNotFoundError
        # guard and kill the HTTP connection (→ browser "Failed to fetch").
        if sys.platform == 'win32':
            return (shutil.which('codex.cmd')
                    or shutil.which(_codex_bin or 'codex')
                    or shutil.which('codex')
                    or '')
        return shutil.which(_codex_bin or 'codex') or shutil.which('codex.cmd') or ''

    def _codex_configure(self):
        global _codex_bin
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})
        path = (body.get('binary') or '').strip()
        if path and not pathlib.Path(path).is_file():
            return self._send_json(400, {'error': f'not a file: {path}'})
        _codex_bin = path
        return self._codex_status()

    def _codex_stream(self):
        """Streaming elevated agent backed by Codex CLI (codex exec --json).
        Auth comes from ~/.codex/config.toml — serve.py never touches API keys.
        Same SSE output shape as /openclaw/stream so the UI uses one parser.
        """
        bin_ = self._codex_resolve()
        if not bin_:
            return self._send_json(503, {
                'error': 'codex CLI not found — install via npm i -g @openai/codex or set OPENCLAW_CODEX_BIN'
            })
        if not _openclaw_allowed_dirs:
            return self._send_json(503, {
                'error': 'OPENCLAW_ALLOWED_DIRS not set — codex endpoint disabled'
            })

        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})

        for d in _openclaw_allowed_dirs:
            if not pathlib.Path(d).is_dir():
                return self._send_json(503, {
                    'error': f'OPENCLAW_ALLOWED_DIRS includes missing dir: {d}'
                })

        messages = body.get('messages') or []
        model    = (body.get('model') or '').strip()
        system   = (body.get('system') or '').strip()
        agent    = (body.get('agentName') or body.get('agent') or 'elevated-agent').strip()[:60]

        # Build prompt from message history (same as openclaw handler)
        history_lines = []
        for m in messages:
            role = (m.get('role') or 'user').upper()
            content = (m.get('content') or '').strip()
            if not content: continue
            history_lines.append(f'{role}: {content}')
        prompt = '\n\n'.join(history_lines)
        if not prompt:
            return self._send_json(400, {'error': 'no prompt'})

        # Use project cwd if provided and valid, otherwise first allowed dir.
        primary_dir = _openclaw_allowed_dirs[0]
        req_cwd = (body.get('cwd') or '').strip()
        if req_cwd:
            try:
                cwd_p = pathlib.Path(req_cwd).resolve()
                for d in _openclaw_allowed_dirs:
                    try:
                        cwd_p.relative_to(pathlib.Path(d).resolve())
                        if cwd_p.is_dir():
                            primary_dir = str(cwd_p)
                        break
                    except ValueError:
                        continue
            except OSError:
                pass
        cmd = [bin_, 'exec',
               '--json',
               '--skip-git-repo-check',
               '--sandbox', 'workspace-write',
               '-C', primary_dir]
        for d in _openclaw_allowed_dirs[1:]:
            cmd += ['--add-dir', d]
        # Codex talks directly to OpenAI (default provider). Auth via
        # OPENAI_API_KEY (user-supplied through HQ settings / operator env).
        wire_model = model or 'gpt-4.1'
        cmd += ['-c', 'model_provider="openai"']
        cmd += ['--model', wire_model]
        # OCI cloud requirements (synced into ~/.codex/cloud-requirements-cache.json)
        # restrict approval_policy to "untrusted" — anything else (including
        # "never") is rejected as `Configured value … is disallowed by
        # requirements; falling back to required value UnlessTrusted`. That
        # rejection used to surface as an `item.completed type=error` event
        # and the user saw "Codex returned no content". Use the allowed
        # value so the request actually runs.
        cmd += ['-c', 'approval_policy="untrusted"']

        guard = (
            f'You are {agent}, an elevated HQ agent with computer access. '
            f'You are restricted to these directories: {", ".join(_openclaw_allowed_dirs)}. '
            'When you intend to perform an action with side effects, first emit '
            '[NEEDS_APPROVAL: <one-line description>] and stop until the boss replies.'
        )
        full_prompt = (guard + '\n\n' + (system + '\n\n' if system else '')) + prompt

        sys.stderr.write(f'[codex] stream: agent={agent} model={model or "(default)"} '
                         f'wire_model={wire_model or "(default)"} '
                         f'dirs={_openclaw_allowed_dirs}\n')

        # Inherit env + Git Bash paths so shell tools work on Windows.
        # Codex talks to OpenAI directly via OPENAI_API_KEY (BYOK / operator env).
        import copy as _copy
        agent_env = _copy.deepcopy(os.environ)
        path_key = next((k for k in agent_env.keys() if k.lower() == 'path'), 'Path')
        path_value = agent_env.get(path_key, '')
        for _d in [r'C:\Program Files\Git\usr\bin',
                   r'C:\Program Files\Git\bin',
                   r'C:\Program Files\Git\mingw64\bin']:
            if os.path.isdir(_d) and _d not in path_value:
                path_value = _d + os.pathsep + path_value
        path_value = os.pathsep.join(
            p for p in path_value.split(os.pathsep)
            if p and r'\.codex\tmp\arg0' not in p.lower()
        )
        for _k in [k for k in list(agent_env.keys()) if k.lower() == 'path']:
            agent_env.pop(_k, None)
        agent_env['Path'] = path_value
        # Codex uses OpenAI directly via OPENAI_API_KEY; no base_url override.
        agent_env.pop('OPENAI_BASE_URL', None)

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, bufsize=1, encoding='utf-8',
                cwd=primary_dir,
                env=agent_env,
            )
        except (FileNotFoundError, OSError) as e:
            return self._send_json(500, {'error': f'spawn codex: {e}'})

        try:
            proc.stdin.write(full_prompt)
            proc.stdin.close()
        except Exception as e:
            # Codex died before we could send the prompt — capture stderr so
            # the user sees the real failure (bad profile, bad config, etc.)
            stderr_text = ''
            try:
                stderr_text = proc.stderr.read()[:1500]
            except Exception:
                pass
            try: proc.kill()
            except Exception: pass
            return self._send_json(500, {
                'error': f'codex exited before prompt could be sent: {e}',
                'stderr': stderr_text,
                'cmd': ' '.join(cmd),
            })

        # SSE response
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

        stderr_buf = []
        def _drain_err():
            try:
                for line in proc.stderr:
                    stderr_buf.append(line)
            except Exception:
                pass
        threading.Thread(target=_drain_err, daemon=True).start()

        item_text_seen = {}

        def _content_text(value):
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
                        parts.append(block.get('text') or block.get('content') or block.get('output_text') or '')
                return ''.join(parts)
            if isinstance(value, dict):
                return (
                    value.get('text')
                    or value.get('content')
                    or value.get('message')
                    or _content_text(value.get('content_parts'))
                )
            return ''

        # Codex --json event types we care about:
        #   agent_message / message  → text to show the user
        #   function_call            → show tool invocation inline
        #   function_call_output     → show tool result inline
        #   error                    → surface as warning
        #   turn.failed              → surface as error
        #   thread.started / turn.started / turn.completed → silently ignored
        events_seen = 0
        text_emitted = False
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue

                events_seen += 1
                t = ev.get('type', '')

                # Assistant text output
                if t in ('agent_message', 'message'):
                    content = ev.get('content') or ev.get('message') or ''
                    text = _content_text(content)
                    if text:
                        text_emitted = True
                        write_sse({'choices': [{'index': 0, 'delta': {'content': text}}]})

                elif t in ('agent_message_delta', 'message_delta', 'response.output_text.delta'):
                    text = ev.get('delta') or ev.get('text') or ev.get('content') or ''
                    if text:
                        text_emitted = True
                        write_sse({'choices': [{'index': 0, 'delta': {'content': str(text)}}]})

                elif t in ('item.updated', 'item.completed'):
                    item = ev.get('item') or {}
                    item_type = item.get('type', '')
                    # Codex 0.128 emits `type: "agent_message"` with a flat
                    # `text` field for assistant replies (older versions used
                    # `type: "message"` with `content` blocks). Surface errors
                    # too — those are stream-disconnect / config-rejection
                    # diagnostics the user needs to see.
                    if item_type == 'error':
                        msg = item.get('message') or item.get('text') or json.dumps(item)
                        # Suppress informational warnings that don't block
                        # the run — the cloud-requirements override message
                        # always fires for `codex exec` because the CLI
                        # defaults approval_policy to `Never` and the cloud
                        # gate downgrades it to UnlessTrusted. Codex still
                        # produces an answer in the next item.completed,
                        # so showing the warning to the user is just noise.
                        _is_warning = (
                            'disallowed by requirements' in msg
                            or 'falling back to required value' in msg
                        )
                        if not _is_warning:
                            text_emitted = True
                            write_sse({'choices': [{'index': 0, 'delta': {
                                'content': f'\n\n⚠ Codex item error: {msg}'}}]})
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
                            text_emitted = True
                            write_sse({'choices': [{'index': 0, 'delta': {'content': delta}}]})

                elif t in ('turn.completed', 'response.completed'):
                    text = _content_text(ev.get('last_agent_message') or ev.get('message') or '')
                    if text:
                        text_emitted = True
                        write_sse({'choices': [{'index': 0, 'delta': {'content': text}}]})

                # Tool call — show what Codex is doing
                elif t == 'function_call':
                    name = ev.get('name') or ev.get('function') or 'tool'
                    args = ev.get('arguments') or ev.get('input') or {}
                    if isinstance(args, dict):
                        cmd_str = args.get('cmd') or args.get('command') or json.dumps(args)
                    else:
                        cmd_str = str(args)
                    text_emitted = True
                    write_sse({'choices': [{'index': 0, 'delta': {
                        'content': f'\n[{name.upper()}: {cmd_str}]\n'}}]})

                # Tool result
                elif t == 'function_call_output':
                    output = ev.get('output') or ''
                    if output:
                        text_emitted = True
                        write_sse({'choices': [{'index': 0, 'delta': {
                            'content': f'\n📡 {name if (name := ev.get("name","tool")) else "result"}("{cmd_str[:60] if (cmd_str := str(ev.get("call_id",""))) else "..."}" →\n{output}\n'}}]})

                # Errors
                elif t in ('error', 'turn.failed'):
                    msg = ev.get('message') or (ev.get('error') or {}).get('message') or str(ev)
                    text_emitted = True
                    write_sse({'choices': [{'index': 0, 'delta': {
                        'content': f'\n\n⚠ Codex error: {msg}'}}]})

        finally:
            try: proc.wait(timeout=2)
            except Exception:
                try: proc.kill()
                except Exception: pass

            stderr_text = (''.join(stderr_buf)).strip()
            rc = proc.returncode

            def _summarize_stderr(s):
                """Codex sometimes dumps the entire upstream HTTP body into
                stderr. Trim that to the actual error summary so the chat
                surface doesn't get blasted with HTML."""
                if not s: return ''
                # Known noise: a model-list refresh failure can include a large
                # HTML payload. Show only the reason line.
                m = re.search(r'failed to refresh available models:[^\n]+', s)
                refresh_hint = ''
                if m:
                    refresh_hint = (
                        '\n\nNote: the model-list refresh failed. Check that '
                        'OPENAI_API_KEY is set and the selected model is valid.'
                    )
                # Drop any line that looks like raw HTML / JSON body, or
                # known-benign codex startup chatter ("Reading prompt from
                # stdin...", model-refresh notices that we already handle
                # via the proxy). These are not user-facing errors.
                _BENIGN_PATTERNS = (
                    'Reading prompt from stdin',
                    'codex_models_manager',
                    'failed to refresh available models',
                )
                cleaned = []
                for line in s.splitlines():
                    if line.startswith(' ') or line.startswith('"') or line.startswith('}') or line.startswith('{'):
                        continue
                    if '<!DOCTYPE' in line or '<html' in line:
                        continue
                    if any(p in line for p in _BENIGN_PATTERNS):
                        continue
                    cleaned.append(line)
                summary = '\n'.join(cleaned)[:600].rstrip()
                return summary + refresh_hint

            # Surface failures explicitly. Three cases that all used to look
            # like a silent successful run with only [DONE]:
            #   1. non-zero exit              → exited N: <stderr>
            #   2. zero exit + no events      → no output (config/sandbox issue)
            #   3. zero exit + stderr noise   → completed with warnings
            if rc and rc not in (0, None):
                err_text = _summarize_stderr(stderr_text) or f'exit {rc}'
                write_sse({'choices': [{'index': 0, 'delta': {
                    'content': f'\n\n⚠ Codex exited {rc}: {err_text}'}}]})
            elif not text_emitted:
                hint = _summarize_stderr(stderr_text) or '(no stdout, no stderr — likely the OS blocked the nested codex spawn)'
                write_sse({'choices': [{'index': 0, 'delta': {
                    'content': f'\n\n⚠ Codex returned no content (events seen: {events_seen}, exit: {rc}). {hint}'}}]})
            elif stderr_text:
                summary = _summarize_stderr(stderr_text)
                if summary:
                    write_sse({'choices': [{'index': 0, 'delta': {
                        'content': f'\n\n_(codex stderr: {summary[:300]})_'}}]})

            try: self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError): pass

    # ---- Filesystem browser (used by Projects path picker) ---------------
    def _fs_browse(self):
        """GET /fs/browse?path=<dir>
        Returns a directory listing for the path picker popup.
        In container mode: restricted to OPENCLAW_ALLOWED_DIRS subtrees.
        In local mode: any readable path is allowed.
        Response: {path, parent, entries:[{name, type:'dir'|'file', path}]}
        """
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        req_path = (params.get('path') or [''])[0].strip()

        # Default starting location: first allowed dir → home → cwd
        if not req_path:
            if _openclaw_allowed_dirs:
                req_path = _openclaw_allowed_dirs[0]
            else:
                try:
                    req_path = str(pathlib.Path.home())
                except Exception:
                    req_path = os.getcwd()

        try:
            p = pathlib.Path(req_path).resolve()
        except Exception as e:
            return self._send_json(400, {'error': f'invalid path: {e}'})

        if not p.is_dir():
            return self._send_json(400, {'error': 'not a directory'})

        # Container: only browse within allowed dirs
        if _RUNTIME_ENV == 'container' and _openclaw_allowed_dirs:
            try:
                allowed = any(
                    str(p).startswith(str(pathlib.Path(d).resolve()))
                    for d in _openclaw_allowed_dirs
                )
            except Exception:
                allowed = False
            if not allowed:
                return self._send_json(403, {
                    'error': 'path is outside OPENCLAW_ALLOWED_DIRS',
                    'allowed': _openclaw_allowed_dirs,
                })

        try:
            raw = list(p.iterdir())
        except PermissionError:
            return self._send_json(403, {'error': 'permission denied'})
        except Exception as e:
            return self._send_json(500, {'error': f'listing failed: {e}'})

        # Build entries — guard each is_dir() individually because Windows
        # junction points / reparse points can raise ValueError for some paths.
        entries = []
        for item in raw:
            if item.name.startswith('.'):
                continue
            try:
                is_dir = item.is_dir()
            except Exception:
                continue  # skip inaccessible / broken entries silently
            entries.append({
                'name': item.name,
                'type': 'dir' if is_dir else 'file',
                'path': str(item),
            })
        # Dirs first, then files, both alphabetical
        entries.sort(key=lambda e: (e['type'] != 'dir', e['name'].lower()))

        parent = str(p.parent) if str(p.parent) != str(p) else None
        return self._send_json(200, {
            'path':    str(p),
            'parent':  parent,
            'entries': entries,
        })

    # ---- Project Terminal (Claude Code / Codex CLI runner) ---------------
    def _terminal_spawn(self):
        """GET /terminal/spawn?cli=claude|codex&cwd=<path>
        Opens the CLI in a new OS terminal window so the user sees the
        full interactive TUI (welcome screen, coloured prompts, etc.).
        Windows: tries Windows Terminal → pwsh → PowerShell → cmd.
        Linux/macOS: tries x-terminal-emulator → gnome-terminal → xterm.
        """
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        cli  = (params.get('cli')  or ['claude'])[0].strip().lower()
        cwd  = (params.get('cwd')  or ['']      )[0].strip()
        if cli not in ('claude', 'codex'):
            return self._send_json(400, {'error': 'cli must be claude or codex'})
        if not cwd:
            return self._send_json(400, {'error': 'cwd required'})
        cwd_path = pathlib.Path(cwd).resolve()
        if not cwd_path.is_dir():
            return self._send_json(400, {'error': f'directory not found: {cwd}'})
        bin_ = (self._claudecode_resolve() if cli == 'claude' else self._codex_resolve())
        if not bin_:
            return self._send_json(503, {'error': f'{cli} CLI not found'})
        try:
            if sys.platform == 'win32':
                wt  = shutil.which('wt')
                ps  = shutil.which('pwsh') or shutil.which('powershell')
                if wt and ps:
                    subprocess.Popen(
                        ['wt', '-d', str(cwd_path), ps, '-NoExit', '-Command', cli],
                        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    )
                elif ps:
                    subprocess.Popen(
                        [ps, '-NoExit', '-Command',
                         f'Set-Location "{cwd_path}"; {cli}'],
                        creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                    )
                else:
                    subprocess.Popen(
                        ['cmd', '/k', f'cd /d "{cwd_path}" && {cli}'],
                        creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                    )
            else:
                launched = False
                for term in ['x-terminal-emulator', 'gnome-terminal', 'kitty', 'xterm']:
                    if shutil.which(term):
                        subprocess.Popen([term, '-e', cli], cwd=str(cwd_path))
                        launched = True
                        break
                if not launched:
                    return self._send_json(503, {'error': 'no terminal emulator found'})
        except Exception as e:
            return self._send_json(500, {'error': f'spawn failed: {e}'})
        return self._send_json(200, {'ok': True, 'cli': cli, 'cwd': str(cwd_path)})

    def _terminal_nonce(self):
        """GET /terminal/nonce → {"nonce": "<hex>"}
        Returns the per-process nonce that /terminal/pty requires as a query
        param.  Only the HQ app (same container origin) can fetch this, so it
        acts as a lightweight auth token for the WebSocket endpoint.
        """
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

        if cli not in ('claude', 'codex'):
            return self._send_json(400, {'error': 'cli must be claude or codex'})
        if not cwd:
            return self._send_json(400, {'error': 'cwd required'})
        cwd_path = pathlib.Path(cwd).resolve()
        if not cwd_path.is_dir():
            return self._send_json(400, {'error': f'directory not found: {cwd}'})
        bin_ = (self._claudecode_resolve() if cli == 'claude' else self._codex_resolve())
        if not bin_:
            return self._send_json(503, {'error': f'{cli} CLI not found'})

        # ── Security: Origin + nonce checks ────────────────────────────────
        # Origin validation — reject cross-origin WS initiations.
        # Browsers always send Origin on WebSocket upgrade; non-browser clients
        # may omit it (curl, CLI tools, unit tests) — those are allowed through
        # so local dev tooling isn't broken.
        _origin = self.headers.get('Origin', '').strip()
        _host   = self.headers.get('Host', '').strip()
        _is_tls = isinstance(self.connection, ssl.SSLSocket)
        _scheme = 'https' if _is_tls else 'http'
        _allowed_origins = {
            'https://hq.cafreso.com',        # production Caddy gateway
            'http://localhost:8787',          # local Windows dev
            'http://127.0.0.1:8787',          # local Windows dev (alt)
            f'{_scheme}://{_host}',           # same-origin (any IP the client used)
        }
        if _origin and _origin not in _allowed_origins:
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
                    if _pty_auth == 'subscription':
                        # Strip API key so CLI uses its own OAuth login
                        agent_env.pop('ANTHROPIC_API_KEY', None)
                    elif _ak and not agent_env.get('ANTHROPIC_API_KEY', '').strip():
                        agent_env['ANTHROPIC_API_KEY'] = _ak
                    if _ok and not agent_env.get('OPENAI_API_KEY', '').strip():
                        agent_env['OPENAI_API_KEY'] = _ok
                    del _ak, _ok, _pty_auth  # clear plaintext key strings from Python locals
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

        with _PTY_SESSIONS_LK:
            sess = _PTY_SESSIONS.get(session_id) if session_id else None

        if sess is not None and not sess['stop'].is_set():
            # ── Reconnect to existing PTY session ──────────────────────────
            with sess['sock_lk']:
                sess['sock']    = client_sock
                sess['expires'] = None   # cancel reaper countdown

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
            stop_evt = threading.Event()
            sess = {
                'stop':    stop_evt,
                'sock':    client_sock,
                'sock_lk': threading.Lock(),
                'buf':     bytearray(),
                'buf_lk':  threading.Lock(),
                'expires': None,
            }
            if session_id:
                with _PTY_SESSIONS_LK:
                    _PTY_SESSIONS[session_id] = sess

            if _is_win:
                spawn_argv = ['cmd.exe', '/c', bin_ or cli]
                try:
                    pty_proc = _winpty.PtyProcess.spawn(
                        spawn_argv, cwd=str(cwd_path), env=agent_env,
                        dimensions=(rows, cols),
                    )
                except Exception as exc:
                    try: _ws_send_raw(client_sock, f'\r\n\x1b[31mFailed to spawn {cli}: {exc}\x1b[0m\r\n')
                    except OSError: pass
                    if session_id:
                        with _PTY_SESSIONS_LK: _PTY_SESSIONS.pop(session_id, None)
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
                    if session_id:
                        with _PTY_SESSIONS_LK: _PTY_SESSIONS.pop(session_id, None)
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
                spawn_argv = [bin_ or cli]
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
                    if session_id:
                        with _PTY_SESSIONS_LK: _PTY_SESSIONS.pop(session_id, None)
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
                    if session_id:
                        with _PTY_SESSIONS_LK: _PTY_SESSIONS.pop(session_id, None)
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
                        try:
                            msg = json.loads(payload)
                            if isinstance(msg, dict) and msg.get('type') == 'resize':
                                c = max(10, min(500, int(msg.get('cols', cols))))
                                r = max(5,  min(200, int(msg.get('rows', rows))))
                                sess['pty_proc'].setwinsize(r, c)
                                continue
                        except (ValueError, TypeError):
                            pass
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
                        try:
                            msg = json.loads(payload)
                            if isinstance(msg, dict) and msg.get('type') == 'resize':
                                c = max(10, min(500, int(msg.get('cols', cols))))
                                r = max(5,  min(200, int(msg.get('rows', rows))))
                                _fcntl2.ioctl(sess['master_fd'], _termios2.TIOCSWINSZ,
                                              _struct3.pack('HHHH', r, c, 0, 0))
                                continue
                        except (ValueError, TypeError):
                            pass
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
        sys.stderr.write(f'[pty-ws] WS detached: {session_id[:8] if session_id else "?"} {cli} @ {cwd_path}\n')

    def _terminal_status(self):
        """Report CLI availability, runtime environment, and spawn capability."""
        claude_bin = self._claudecode_resolve()
        codex_bin  = self._codex_resolve()
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
            'runtime_env':     _RUNTIME_ENV,
            'spawn_supported': spawn_ok,
            'pty_supported':   pty_ok,
        })

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
        # Orchestrator session keys — used to tie multi-turn invocations to
        # the same project + CLI session so context (working dir, prior
        # output) can be threaded through. Logged for trace; future use:
        # pass to `claude --resume <session-id>` to recover stored CLI state.
        session_id  = (body.get('sessionId') or '').strip()[:80]
        project_id  = (body.get('projectId') or '').strip()[:80]

        if cli not in ('claude', 'codex'):
            return self._send_json(400, {'error': 'cli must be "claude" or "codex"'})
        if not cwd:
            return self._send_json(400, {'error': 'cwd required'})
        cwd_path = pathlib.Path(cwd).resolve()
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
                return self._send_json(503, {'error': 'claude CLI not found — install Claude Code or set OPENCLAW_CLAUDE_BIN'})
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
        else:
            bin_ = self._codex_resolve()
            if not bin_:
                return self._send_json(503, {'error': 'codex CLI not found — npm i -g @openai/codex or set OPENCLAW_CODEX_BIN'})
            path_key = next((k for k in agent_env.keys() if k.lower() == 'path'), 'Path')
            path_value = agent_env.get(path_key, '')
            path_value = os.pathsep.join(
                p for p in path_value.split(os.pathsep)
                if p and r'\.codex\tmp\arg0' not in p.lower()
            )
            for _k in [k for k in list(agent_env.keys()) if k.lower() == 'path']:
                agent_env.pop(_k, None)
            agent_env['Path'] = path_value
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

        try:
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
                                    ok = sse_delta(text, 'text')
                                    if not ok: break
                            elif btype == 'tool_use':
                                name  = block.get('name') or 'tool'
                                inp   = block.get('input') or {}
                                inp_s = json.dumps(inp, ensure_ascii=False)
                                if len(inp_s) > 240: inp_s = inp_s[:240] + '…'
                                sse_delta(f'\n⚙ {name}: {inp_s}\n', 'tool')
                        u = msg.get('usage')
                        if u:
                            in_tokens  = u.get('input_tokens', in_tokens)
                            out_tokens = u.get('output_tokens', out_tokens)
                    elif t == 'result':
                        u = ev.get('usage') or {}
                        in_tokens  = u.get('input_tokens', in_tokens)
                        out_tokens = u.get('output_tokens', out_tokens)
                    elif t == 'error':
                        sse_delta(f'\n⚠ {ev.get("message") or ev}\n', 'error')
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
                if proc.returncode and proc.returncode != 0 and not (in_tokens or out_tokens):
                    err_text = ''.join(stderr_buf)[:600] or f'exit {proc.returncode}'
                    sse_delta(f'\n⚠ claude exited {proc.returncode}: {err_text}\n', 'error')

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

    # ---- Export endpoints (PowerPoint / Word / PDF) ----------------------
    def _vault_binary_path(self, rel: str, allowed_ext: tuple) -> pathlib.Path:
        """Resolve `rel` under the vault for binary files. Mirrors
        _vault_resolve but allows the caller's extension instead of forcing
        .md. Used by export/generate endpoints to drop files into the vault."""
        if not _vault_root:
            raise ValueError('vault directory not configured')
        root = pathlib.Path(_vault_root).resolve()
        if not root.is_dir():
            raise ValueError(f'vault directory does not exist: {root}')
        rel = (rel or '').lstrip('/').replace('\\', '/').strip()
        if not rel:
            raise ValueError('path required')
        ext = pathlib.Path(rel).suffix.lower()
        if ext not in allowed_ext:
            # If no extension was given, append the first allowed one.
            if not ext:
                rel = rel + allowed_ext[0]
                ext = allowed_ext[0]
            else:
                raise ValueError(f'extension must be one of {allowed_ext}, got {ext}')
        candidate = (root / rel).resolve()
        try: candidate.relative_to(root)
        except ValueError: raise ValueError('path escapes vault directory')
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate

    def _read_json_body(self):
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            return json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return None

    def _export_pptx(self):
        """Render a markdown outline into a real .pptx and save to vault.
        Body: { path, content }. The outline uses `## Slide N: Title` headers
        and bullet lists; each `##` becomes a slide. Requires python-pptx."""
        body = self._read_json_body()
        if body is None: return self._send_json(400, {'error': 'bad json'})
        rel = (body.get('path') or '').strip()
        content = body.get('content') or ''
        if not rel or not content.strip():
            return self._send_json(400, {'error': 'path and content required'})
        try:
            out_path = self._vault_binary_path(rel, ('.pptx',))
        except ValueError as e:
            return self._send_json(400, {'error': str(e)})
        try:
            from pptx import Presentation  # noqa: PLC0415
            from pptx.util import Inches, Pt  # noqa: PLC0415
        except ImportError:
            return self._send_json(503, {'error': 'python-pptx not installed — run: pip install python-pptx'})

        prs = Presentation()
        # Title slide from first H1 if any.
        lines = content.splitlines()
        title_line = next((l for l in lines if l.strip().startswith('# ')), None)
        if title_line:
            layout = prs.slide_layouts[0]
            slide = prs.slides.add_slide(layout)
            slide.shapes.title.text = title_line.lstrip('#').strip()
        # Each ## section becomes a slide.
        cur_title = None
        cur_bullets = []
        def flush():
            if cur_title is None and not cur_bullets: return
            layout = prs.slide_layouts[1]  # Title + Content
            slide = prs.slides.add_slide(layout)
            slide.shapes.title.text = cur_title or 'Slide'
            tf = slide.placeholders[1].text_frame
            tf.clear()
            for i, b in enumerate(cur_bullets):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.text = b
                p.level = 0
        for ln in lines:
            s = ln.rstrip()
            if s.startswith('## '):
                flush()
                cur_title = s[3:].strip()
                # Strip leading "Slide N:" prefix the agents tend to write.
                cur_title = re.sub(r'^Slide\s*\d+\s*[:\-]\s*', '', cur_title, flags=re.IGNORECASE)
                cur_bullets = []
            elif re.match(r'^\s*[-*•]\s+', s):
                cur_bullets.append(re.sub(r'^\s*[-*•]\s+', '', s))
            elif s.strip() and cur_title is not None:
                # Plain paragraph under a slide → also a bullet.
                cur_bullets.append(s.strip())
        flush()

        try:
            prs.save(str(out_path))
        except Exception as e:
            return self._send_json(500, {'error': f'save failed: {e}'})
        rel_out = str(out_path.relative_to(pathlib.Path(_vault_root).resolve())).replace('\\', '/')
        return self._send_json(200, {'path': rel_out, 'slides': len(prs.slides)})

    def _export_docx(self):
        """Render markdown into a real .docx and save to vault. Body: {path, content}.
        Supports headings (# / ## / ###), bullets (- / *), and paragraphs.
        Requires python-docx."""
        body = self._read_json_body()
        if body is None: return self._send_json(400, {'error': 'bad json'})
        rel = (body.get('path') or '').strip()
        content = body.get('content') or ''
        if not rel or not content.strip():
            return self._send_json(400, {'error': 'path and content required'})
        try:
            out_path = self._vault_binary_path(rel, ('.docx',))
        except ValueError as e:
            return self._send_json(400, {'error': str(e)})
        try:
            from docx import Document  # noqa: PLC0415
        except ImportError:
            return self._send_json(503, {'error': 'python-docx not installed — run: pip install python-docx'})

        doc = Document()
        for ln in content.splitlines():
            s = ln.rstrip()
            if not s.strip():
                continue
            if s.startswith('### '):
                doc.add_heading(s[4:].strip(), level=3)
            elif s.startswith('## '):
                doc.add_heading(s[3:].strip(), level=2)
            elif s.startswith('# '):
                doc.add_heading(s[2:].strip(), level=1)
            elif re.match(r'^\s*[-*•]\s+', s):
                doc.add_paragraph(re.sub(r'^\s*[-*•]\s+', '', s), style='List Bullet')
            elif re.match(r'^\s*\d+\.\s+', s):
                doc.add_paragraph(re.sub(r'^\s*\d+\.\s+', '', s), style='List Number')
            else:
                doc.add_paragraph(s.strip())
        try:
            doc.save(str(out_path))
        except Exception as e:
            return self._send_json(500, {'error': f'save failed: {e}'})
        rel_out = str(out_path.relative_to(pathlib.Path(_vault_root).resolve())).replace('\\', '/')
        return self._send_json(200, {'path': rel_out})

    def _export_pdf(self):
        """Render markdown into a .pdf and save to vault. Body: {path, content}.
        Tries weasyprint (best) → reportlab (fallback). Returns 503 if neither."""
        body = self._read_json_body()
        if body is None: return self._send_json(400, {'error': 'bad json'})
        rel = (body.get('path') or '').strip()
        content = body.get('content') or ''
        if not rel or not content.strip():
            return self._send_json(400, {'error': 'path and content required'})
        try:
            out_path = self._vault_binary_path(rel, ('.pdf',))
        except ValueError as e:
            return self._send_json(400, {'error': str(e)})

        # Path A — weasyprint (real CSS, good typography).
        try:
            import markdown as _md  # noqa: PLC0415
            from weasyprint import HTML as _WeasyHTML  # noqa: PLC0415
            html_body = _md.markdown(content, extensions=['tables', 'fenced_code'])
            full_html = f'<html><head><meta charset="utf-8"><style>body{{font-family:Helvetica,Arial,sans-serif;line-height:1.5;padding:48px;}} h1,h2,h3{{color:#222}} code{{background:#f4f4f4;padding:2px 6px;border-radius:3px}} pre{{background:#f4f4f4;padding:12px;border-radius:6px;overflow-x:auto}}</style></head><body>{html_body}</body></html>'
            _WeasyHTML(string=full_html).write_pdf(str(out_path))
            rel_out = str(out_path.relative_to(pathlib.Path(_vault_root).resolve())).replace('\\', '/')
            return self._send_json(200, {'path': rel_out, 'renderer': 'weasyprint'})
        except ImportError:
            pass
        except Exception as e:
            sys.stderr.write(f'[export pdf] weasyprint failed: {e}\n')

        # Path B — reportlab (simpler, no CSS, ships with most Pythons via pip).
        try:
            from reportlab.lib.pagesizes import letter  # noqa: PLC0415
            from reportlab.lib.styles import getSampleStyleSheet  # noqa: PLC0415
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer  # noqa: PLC0415
        except ImportError:
            return self._send_json(503, {'error': 'install either weasyprint+markdown OR reportlab — run: pip install weasyprint markdown  (or)  pip install reportlab'})

        doc = SimpleDocTemplate(str(out_path), pagesize=letter, topMargin=48, bottomMargin=48, leftMargin=48, rightMargin=48)
        styles = getSampleStyleSheet()
        story = []
        for ln in content.splitlines():
            s = ln.rstrip()
            if not s.strip():
                story.append(Spacer(1, 6))
                continue
            if s.startswith('# '):
                story.append(Paragraph(s[2:].strip(), styles['Title']))
            elif s.startswith('## '):
                story.append(Paragraph(s[3:].strip(), styles['Heading2']))
            elif s.startswith('### '):
                story.append(Paragraph(s[4:].strip(), styles['Heading3']))
            elif re.match(r'^\s*[-*•]\s+', s):
                story.append(Paragraph('• ' + re.sub(r'^\s*[-*•]\s+', '', s), styles['BodyText']))
            else:
                story.append(Paragraph(s.strip(), styles['BodyText']))
        try:
            doc.build(story)
        except Exception as e:
            return self._send_json(500, {'error': f'pdf build: {e}'})
        rel_out = str(out_path.relative_to(pathlib.Path(_vault_root).resolve())).replace('\\', '/')
        return self._send_json(200, {'path': rel_out, 'renderer': 'reportlab'})

    # ---- Image / video generation (user-configured provider) -------------
    def _generate_image(self):
        """Generate an image via the user's configured provider, save to vault.
        Body: { path, prompt, provider, model, size?, apiKey? }
        - provider: 'openai' | 'google' | 'fal'
        - apiKey: forwarded from the browser (decrypted client-side); server
          env vars override if set."""
        body = self._read_json_body()
        if body is None: return self._send_json(400, {'error': 'bad json'})
        rel = (body.get('path') or '').strip()
        prompt = (body.get('prompt') or '').strip()
        provider = (body.get('provider') or '').strip().lower()
        model = (body.get('model') or '').strip()
        size = (body.get('size') or '1024x1024').strip()
        if not rel or not prompt or not provider:
            return self._send_json(400, {'error': 'path, prompt, and provider required'})
        try:
            out_path = self._vault_binary_path(rel, ('.png', '.jpg', '.jpeg', '.webp'))
        except ValueError as e:
            return self._send_json(400, {'error': str(e)})

        api_key = body.get('apiKey') or ''
        if provider == 'openai':
            api_key = os.environ.get('OPENAI_API_KEY') or api_key
            if not api_key: return self._send_json(400, {'error': 'OPENAI_API_KEY required'})
            payload = {'model': model or 'dall-e-3', 'prompt': prompt, 'size': size, 'n': 1, 'response_format': 'b64_json'}
            try:
                req = urllib.request.Request('https://api.openai.com/v1/images/generations',
                    data=json.dumps(payload).encode('utf-8'),
                    headers={'authorization': f'Bearer {api_key}', 'content-type': 'application/json'})
                with urllib.request.urlopen(req, timeout=120) as r:
                    j = json.loads(r.read().decode('utf-8'))
                b64 = j.get('data', [{}])[0].get('b64_json', '')
                if not b64: return self._send_json(502, {'error': 'no image returned'})
                out_path.write_bytes(base64.b64decode(b64))
            except urllib.error.HTTPError as e:
                return self._send_json(e.code, {'error': e.read().decode('utf-8', 'replace')[:600]})
            except Exception as e:
                return self._send_json(500, {'error': str(e)})
        elif provider == 'google':
            api_key = os.environ.get('GOOGLE_API_KEY') or api_key
            if not api_key: return self._send_json(400, {'error': 'GOOGLE_API_KEY required'})
            model_id = model or 'gemini-2.5-flash-image-preview'
            # Two flavors of Google image gen:
            #  - Imagen (imagen-3.0-*, imagen-4-*) → :predict endpoint, predictions[].bytesBase64Encoded
            #  - Gemini Flash Image / "nano banana" (gemini-*-image-*) → :generateContent,
            #    candidates[0].content.parts[*].inlineData.data
            # We pick the right endpoint based on the model name so the same
            # GOOGLE_API_KEY works for both — no extra setting required.
            is_gemini = 'gemini' in model_id.lower()
            try:
                if is_gemini:
                    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}'
                    payload = {
                        'contents': [{'parts': [{'text': prompt}]}],
                        'generationConfig': {'responseModalities': ['IMAGE']},
                    }
                    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                        headers={'content-type': 'application/json'})
                    with urllib.request.urlopen(req, timeout=180) as r:
                        j = json.loads(r.read().decode('utf-8'))
                    b64 = ''
                    mime = ''
                    cands = j.get('candidates') or []
                    if cands:
                        for part in (cands[0].get('content', {}).get('parts') or []):
                            inline = part.get('inlineData') or part.get('inline_data') or {}
                            if inline.get('data'):
                                b64 = inline['data']
                                mime = (inline.get('mimeType') or inline.get('mime_type') or '').lower()
                                break
                    if not b64:
                        # Surface text fallback if model returned a refusal instead of image bytes
                        text_out = ''
                        for c in cands:
                            for p in (c.get('content', {}).get('parts') or []):
                                if p.get('text'): text_out += p['text']
                        return self._send_json(502, {'error': f'no image bytes in Gemini response{": " + text_out[:200] if text_out else ""}'})
                    out_path.write_bytes(base64.b64decode(b64))
                else:
                    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model_id}:predict?key={api_key}'
                    payload = {'instances': [{'prompt': prompt}], 'parameters': {'sampleCount': 1}}
                    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                        headers={'content-type': 'application/json'})
                    with urllib.request.urlopen(req, timeout=120) as r:
                        j = json.loads(r.read().decode('utf-8'))
                    preds = j.get('predictions', [])
                    if not preds: return self._send_json(502, {'error': 'no image returned'})
                    b64 = preds[0].get('bytesBase64Encoded') or preds[0].get('image', {}).get('bytesBase64Encoded') or ''
                    if not b64: return self._send_json(502, {'error': 'no image bytes in response'})
                    out_path.write_bytes(base64.b64decode(b64))
            except urllib.error.HTTPError as e:
                return self._send_json(e.code, {'error': e.read().decode('utf-8', 'replace')[:600]})
            except Exception as e:
                return self._send_json(500, {'error': str(e)})
        elif provider == 'fal':
            api_key = os.environ.get('FAL_KEY') or api_key
            if not api_key: return self._send_json(400, {'error': 'FAL_KEY required'})
            model_id = model or 'fal-ai/flux/schnell'
            try:
                req = urllib.request.Request(f'https://fal.run/{model_id}',
                    data=json.dumps({'prompt': prompt}).encode('utf-8'),
                    headers={'authorization': f'Key {api_key}', 'content-type': 'application/json'})
                with urllib.request.urlopen(req, timeout=180) as r:
                    j = json.loads(r.read().decode('utf-8'))
                img_url = ((j.get('images') or [{}])[0]).get('url')
                if not img_url: return self._send_json(502, {'error': 'no image url in fal response'})
                with urllib.request.urlopen(img_url, timeout=60) as img:
                    out_path.write_bytes(img.read())
            except urllib.error.HTTPError as e:
                return self._send_json(e.code, {'error': e.read().decode('utf-8', 'replace')[:600]})
            except Exception as e:
                return self._send_json(500, {'error': str(e)})
        elif provider == 'a1111':
            # Automatic1111 Stable Diffusion WebUI — REST API at /sdapi/v1/txt2img.
            # Run A1111 with --api (or --api --listen for LAN). No API key needed.
            base = (body.get('baseUrl') or 'http://127.0.0.1:7860').rstrip('/')
            try:
                w, h = (int(x) for x in size.split('x')[:2]) if 'x' in size else (1024, 1024)
            except Exception:
                w, h = 1024, 1024
            payload = {
                'prompt': prompt,
                'width': w, 'height': h,
                'steps': int(body.get('steps') or 25),
                'cfg_scale': float(body.get('cfgScale') or 7.5),
                'sampler_name': body.get('sampler') or 'DPM++ 2M Karras',
            }
            if model: payload['override_settings'] = {'sd_model_checkpoint': model}
            try:
                req = urllib.request.Request(f'{base}/sdapi/v1/txt2img',
                    data=json.dumps(payload).encode('utf-8'),
                    headers={'content-type': 'application/json'})
                with urllib.request.urlopen(req, timeout=300) as r:
                    j = json.loads(r.read().decode('utf-8'))
                imgs = j.get('images') or []
                if not imgs: return self._send_json(502, {'error': 'no images in A1111 response'})
                out_path.write_bytes(base64.b64decode(imgs[0]))
            except urllib.error.URLError as e:
                return self._send_json(502, {'error': f'A1111 not reachable at {base} — start it with --api flag: {e}'})
            except Exception as e:
                return self._send_json(500, {'error': f'A1111: {e}'})
        elif provider == 'comfyui':
            # ComfyUI — accepts a `workflow` JSON OR a simple `prompt` that we
            # wrap into a minimal txt2img graph. Polls /history for completion
            # then downloads the image bytes from /view.
            base = (body.get('baseUrl') or 'http://127.0.0.1:8188').rstrip('/')
            workflow = body.get('workflow')
            if not workflow:
                # Default minimal txt2img workflow — assumes a SD1.5/SDXL ckpt is
                # loaded under the name in `model` (or "model.safetensors").
                ckpt = model or 'model.safetensors'
                try:
                    w, h = (int(x) for x in size.split('x')[:2]) if 'x' in size else (1024, 1024)
                except Exception:
                    w, h = 1024, 1024
                workflow = {
                    "3": {"class_type": "KSampler", "inputs": {"seed": secrets.randbits(31),
                          "steps": int(body.get('steps') or 25), "cfg": float(body.get('cfgScale') or 7.5),
                          "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                          "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
                    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
                    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
                    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
                    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": body.get('negative') or '', "clip": ["4", 1]}},
                    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
                    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "cafresohq", "images": ["8", 0]}},
                }
            client_id = uuid.uuid4().hex
            try:
                # Queue the prompt.
                req = urllib.request.Request(f'{base}/prompt',
                    data=json.dumps({'prompt': workflow, 'client_id': client_id}).encode('utf-8'),
                    headers={'content-type': 'application/json'})
                with urllib.request.urlopen(req, timeout=30) as r:
                    j = json.loads(r.read().decode('utf-8'))
                prompt_id = j.get('prompt_id')
                if not prompt_id: return self._send_json(502, {'error': 'no prompt_id in ComfyUI response'})
                # Poll history until done (max ~5 min).
                hist = None
                for _i in range(150):
                    time.sleep(2)
                    try:
                        with urllib.request.urlopen(f'{base}/history/{prompt_id}', timeout=10) as r:
                            h = json.loads(r.read().decode('utf-8'))
                        if h.get(prompt_id):
                            hist = h[prompt_id]
                            break
                    except Exception:
                        continue
                if not hist: return self._send_json(504, {'error': 'ComfyUI: prompt did not complete within 5 minutes'})
                # Find first image output.
                outputs = hist.get('outputs') or {}
                img_meta = None
                for _node_id, node_out in outputs.items():
                    if node_out.get('images'):
                        img_meta = node_out['images'][0]
                        break
                if not img_meta: return self._send_json(502, {'error': 'ComfyUI: no image in outputs'})
                # Download the image bytes.
                qs = urllib.parse.urlencode({k: v for k, v in img_meta.items() if k in ('filename','subfolder','type')})
                with urllib.request.urlopen(f'{base}/view?{qs}', timeout=60) as img:
                    out_path.write_bytes(img.read())
            except urllib.error.URLError as e:
                return self._send_json(502, {'error': f'ComfyUI not reachable at {base}: {e}'})
            except Exception as e:
                return self._send_json(500, {'error': f'ComfyUI: {e}'})
        else:
            return self._send_json(400, {'error': f'unsupported provider: {provider}'})
        rel_out = str(out_path.relative_to(pathlib.Path(_vault_root).resolve())).replace('\\', '/')
        return self._send_json(200, {'path': rel_out, 'provider': provider, 'model': model})

    def _generate_video(self):
        """Generate a video via the user's configured provider, save to vault.
        Body: { path, prompt, provider, model, duration?, apiKey? }
        Most video APIs are long-running — this endpoint kicks off the job,
        polls for completion, then writes the bytes. Times out after 10min."""
        body = self._read_json_body()
        if body is None: return self._send_json(400, {'error': 'bad json'})
        rel = (body.get('path') or '').strip()
        prompt = (body.get('prompt') or '').strip()
        provider = (body.get('provider') or '').strip().lower()
        model = (body.get('model') or '').strip()
        duration = int(body.get('duration') or 5)
        if not rel or not prompt or not provider:
            return self._send_json(400, {'error': 'path, prompt, and provider required'})
        try:
            out_path = self._vault_binary_path(rel, ('.mp4', '.mov', '.webm'))
        except ValueError as e:
            return self._send_json(400, {'error': str(e)})

        api_key = body.get('apiKey') or ''
        if provider == 'fal':
            api_key = os.environ.get('FAL_KEY') or api_key
            if not api_key: return self._send_json(400, {'error': 'FAL_KEY required'})
            model_id = model or 'fal-ai/bytedance/seedance/v1/lite/text-to-video'
            try:
                req = urllib.request.Request(f'https://fal.run/{model_id}',
                    data=json.dumps({'prompt': prompt, 'duration': duration}).encode('utf-8'),
                    headers={'authorization': f'Key {api_key}', 'content-type': 'application/json'})
                with urllib.request.urlopen(req, timeout=600) as r:
                    j = json.loads(r.read().decode('utf-8'))
                video_url = (j.get('video') or {}).get('url') or j.get('url') or ''
                if not video_url: return self._send_json(502, {'error': 'no video url in fal response'})
                with urllib.request.urlopen(video_url, timeout=300) as vid:
                    out_path.write_bytes(vid.read())
            except urllib.error.HTTPError as e:
                return self._send_json(e.code, {'error': e.read().decode('utf-8', 'replace')[:600]})
            except Exception as e:
                return self._send_json(500, {'error': str(e)})
        elif provider == 'openai':
            # Sora API is gated; we provide the call shape but most accounts
            # will get a 403. The error message guides the user.
            api_key = os.environ.get('OPENAI_API_KEY') or api_key
            if not api_key: return self._send_json(400, {'error': 'OPENAI_API_KEY required'})
            return self._send_json(501, {'error': 'OpenAI Sora video generation not yet wired (API still gated). Try provider=fal with a Seedance/Veo model instead.'})
        elif provider == 'google':
            return self._send_json(501, {'error': 'Google Veo direct API not yet wired. Try provider=fal with a Veo model instead.'})
        elif provider == 'comfyui':
            # ComfyUI for video — caller passes a `workflow` JSON describing
            # an AnimateDiff / SVD / Hunyuan / Mochi graph. We don't synthesize
            # a default one because video workflows are model-specific.
            base = (body.get('baseUrl') or 'http://127.0.0.1:8188').rstrip('/')
            workflow = body.get('workflow')
            if not workflow:
                return self._send_json(400, {
                    'error': 'ComfyUI video requires a `workflow` JSON (export from your AnimateDiff/SVD/Mochi/Hunyuan setup). Auto-default not provided because video workflows are model-specific. See docs.'
                })
            client_id = uuid.uuid4().hex
            try:
                req = urllib.request.Request(f'{base}/prompt',
                    data=json.dumps({'prompt': workflow, 'client_id': client_id}).encode('utf-8'),
                    headers={'content-type': 'application/json'})
                with urllib.request.urlopen(req, timeout=30) as r:
                    j = json.loads(r.read().decode('utf-8'))
                prompt_id = j.get('prompt_id')
                if not prompt_id: return self._send_json(502, {'error': 'no prompt_id in ComfyUI response'})
                hist = None
                for _i in range(300):  # video takes longer — up to ~10 min
                    time.sleep(2)
                    try:
                        with urllib.request.urlopen(f'{base}/history/{prompt_id}', timeout=10) as r:
                            h = json.loads(r.read().decode('utf-8'))
                        if h.get(prompt_id):
                            hist = h[prompt_id]
                            break
                    except Exception:
                        continue
                if not hist: return self._send_json(504, {'error': 'ComfyUI: prompt did not complete within 10 minutes'})
                outputs = hist.get('outputs') or {}
                # Look for video output — VHS_VideoCombine, SaveVideo, etc.
                vid_meta = None
                for _node_id, node_out in outputs.items():
                    for key in ('videos', 'gifs', 'images'):  # some nodes call the file 'images' even for mp4
                        if node_out.get(key):
                            vid_meta = node_out[key][0]
                            break
                    if vid_meta: break
                if not vid_meta: return self._send_json(502, {'error': 'ComfyUI: no video in outputs — does your workflow include VHS_VideoCombine or SaveVideo?'})
                qs = urllib.parse.urlencode({k: v for k, v in vid_meta.items() if k in ('filename','subfolder','type')})
                with urllib.request.urlopen(f'{base}/view?{qs}', timeout=300) as vid:
                    out_path.write_bytes(vid.read())
            except urllib.error.URLError as e:
                return self._send_json(502, {'error': f'ComfyUI not reachable at {base}: {e}'})
            except Exception as e:
                return self._send_json(500, {'error': f'ComfyUI: {e}'})
        else:
            return self._send_json(400, {'error': f'unsupported provider: {provider}'})
        rel_out = str(out_path.relative_to(pathlib.Path(_vault_root).resolve())).replace('\\', '/')
        return self._send_json(200, {'path': rel_out, 'provider': provider, 'model': model})

    # ---- External approvals (Claude Code hook bridge) --------------------
    def _approval_submit(self):
        """Hook script POSTs a tool-use request here. Returns {id} immediately
        so the script can long-poll /approvals/external/wait until the human
        decides. Body: {tool, input, cwd, agent, sessionId, summary?}."""
        _gc_approvals()
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})
        entry = _new_approval(body)
        sys.stderr.write(f'[approvals] queued {entry["id"]} tool={entry["tool"]} '
                         f'agent={entry["agent"]} cwd={entry["cwd"]}\n')
        return self._send_json(200, {'id': entry['id']})

    def _approval_wait(self):
        """Hook script long-polls here. Returns when a decision is in, or after
        timeout (script should re-poll). Query: ?id=...&timeout=25."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        aid = qs.get('id', [''])[0]
        try:
            wait_s = max(1, min(55, int(qs.get('timeout', ['25'])[0])))
        except ValueError:
            wait_s = 25
        with _approvals_lock:
            entry = _approvals_pending.get(aid)
        if not entry:
            return self._send_json(404, {'error': 'unknown approval id'})
        # Block this thread until decision or timeout. ThreadingMixIn means
        # other requests keep flowing while we wait.
        decided = entry['event'].wait(timeout=wait_s)
        if not decided:
            return self._send_json(200, {'pending': True, 'id': aid})
        # Decided — pop the entry so we don't leak.
        with _approvals_lock:
            _approvals_pending.pop(aid, None)
        return self._send_json(200, {
            'pending': False,
            'id': aid,
            'decision': entry['decision'] or 'deny',
            'reason': entry['reason'] or '',
        })

    def _approval_list(self):
        """UI polls this for pending external approvals to render in the tray."""
        _gc_approvals()
        with _approvals_lock:
            items = [{
                'id': e['id'], 'ts': e['ts'], 'tool': e['tool'],
                'input': e['input'], 'cwd': e['cwd'], 'agent': e['agent'],
                'sessionId': e['sessionId'], 'summary': e['summary'],
            } for e in _approvals_pending.values() if e['decision'] is None]
        items.sort(key=lambda x: x['ts'])
        return self._send_json(200, {'pending': items})

    def _approval_decide(self):
        """UI POSTs the human decision: {id, decision: 'allow'|'deny', reason?}.
        We flip the entry's decision and signal the waiting hook thread."""
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})
        aid = (body.get('id') or '').strip()
        decision = (body.get('decision') or '').strip().lower()
        if decision not in ('allow', 'deny'):
            return self._send_json(400, {'error': 'decision must be allow|deny'})
        reason = (body.get('reason') or '').strip()[:400]
        with _approvals_lock:
            entry = _approvals_pending.get(aid)
            if not entry:
                return self._send_json(404, {'error': 'unknown approval id'})
            if entry['decision'] is not None:
                return self._send_json(409, {'error': 'already decided'})
            entry['decision'] = decision
            entry['reason'] = reason
        entry['event'].set()
        sys.stderr.write(f'[approvals] decided {aid} -> {decision}\n')
        return self._send_json(200, {'id': aid, 'decision': decision})

    def _hq_handler(self, method):
        """Read/write HQ state and memory files.
        GET  /hq/state/<name>    → read hq-state/<name>.json
        PUT  /hq/state/<name>    → write hq-state/<name>.json
        GET  /hq/memory/<name>   → read memory/<name>.json
        PUT  /hq/memory/<name>   → write memory/<name>.json
        """
        parts = self.path.split('/')  # ['', 'hq', 'state'|'memory', '<name>']
        if len(parts) < 4 or not parts[3]:
            return self._send_json(400, {'error': 'path must be /hq/state/<name> or /hq/memory/<name>'})

        scope, name = parts[2], parts[3]
        # Sanitize name — alphanumeric, hyphens, underscores only
        if not _re.match(r'^[\w\-]+$', name):
            return self._send_json(400, {'error': f'invalid name: {name!r}'})

        if scope == 'state':
            base = _hq_state_dir
        elif scope == 'memory':
            base = _hq_memory_dir
        else:
            return self._send_json(404, {'error': f'unknown scope: {scope}'})

        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return self._send_json(503, {'error': f'cannot create dir: {e}'})

        filepath = base / f'{name}.json'

        if method == 'GET':
            if not filepath.exists():
                return self._send_json(404, {'error': 'not found', 'key': name})
            try:
                data = filepath.read_text(encoding='utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode('utf-8'))
            except Exception as e:
                return self._send_json(500, {'error': str(e)})

        elif method == 'PUT':
            length = int(self.headers.get('content-length', 0) or 0)
            try:
                body = self.rfile.read(length)
                # Validate it's JSON
                json.loads(body.decode('utf-8'))
                filepath.write_bytes(body)
                # For agent roster, also write a human-readable markdown summary
                if scope == 'memory' and name == 'agents':
                    self._write_agents_md(base, json.loads(body.decode('utf-8')))
                return self._send_json(200, {'ok': True, 'path': str(filepath)})
            except json.JSONDecodeError:
                return self._send_json(400, {'error': 'body must be valid JSON'})
            except Exception as e:
                return self._send_json(500, {'error': str(e)})

    def _write_agents_md(self, base, agents):
        """Write a human-readable agent roster markdown file alongside the JSON."""
        try:
            from datetime import datetime, timezone
            lines = [
                '# OpenclawHQ Agent Roster',
                f'_Updated: {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}_',
                '',
            ]
            for a in (agents or []):
                lines.append(f"## {a.get('name', '?')} — {a.get('role', '')}")
                lines.append(f"- Model: {a.get('model', 'default')}")
                tools = a.get('tools') or []
                if tools:
                    lines.append(f"- Tools: {', '.join(tools)}")
                lines.append(f"- Elevated: {'yes' if a.get('elevated') else 'no'}")
                lines.append('')
            (base / 'hq-agents.md').write_text('\n'.join(lines), encoding='utf-8')
        except Exception:
            pass  # markdown summary is best-effort

    def _send_json(self, code, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(code)
        self.send_header('content-type', 'application/json; charset=utf-8')
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass

    def _vault(self, method):
        global _vault_root, _vault_backend, _vault_rest_url, _vault_rest_key
        url = urllib.parse.urlparse(self.path)
        path = url.path
        qs = urllib.parse.parse_qs(url.query)

        # ---------- Status ----------
        if path == '/vault/status' and method == 'GET':
            if _vault_backend == 'fs' and _vault_root:
                try:
                    pathlib.Path(_vault_root).mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
            fs_ok = bool(_vault_root) and pathlib.Path(_vault_root).is_dir()
            rest_ok = False
            rest_detail = ''
            if _vault_rest_url and _vault_rest_key:
                try:
                    s, _h, _b = _obsidian_request('GET', '/')
                    rest_ok = (s == 200)
                    rest_detail = '' if rest_ok else f'http {s}'
                except Exception as e:
                    rest_detail = str(e)[:120]
            configured = (_vault_backend == 'rest' and rest_ok) or (_vault_backend == 'fs' and fs_ok)
            return self._send_json(200, {
                'configured': configured,
                'backend': _vault_backend,
                'root': _vault_root,
                'defaultRoot': str(_default_vault_root),
                'restUrl': _vault_rest_url,
                'restKey': '••••' if _vault_rest_key else '',
                'fsExists': fs_ok,
                'restReachable': rest_ok,
                'restDetail': rest_detail,
                # Legacy field for older clients.
                'exists': configured,
            })

        # ---------- Discover local vaults ----------
        if path == '/vault/discover' and method == 'GET':
            return self._send_json(200, {
                'defaultRoot': str(_default_vault_root),
                'vaults': _discover_obsidian_vaults(),
            })

        # ---------- Opaque-blob vault (zero-knowledge / vetKeys) ----------
        # Stores client-encrypted ciphertext blobs identified by hex IDs.
        # The container has zero visibility into contents — it's an
        # untrusted blob store from the client's perspective. Used by the
        # SvelteKit /vault route with vetKeys-derived AES-GCM encryption.
        #
        #   PUT    /vault/blob/<id>   body=<base64 ciphertext>
        #   GET    /vault/blob/<id>   → base64 ciphertext (text/plain)
        #   DELETE /vault/blob/<id>
        #
        # IDs are accepted if they match [a-f0-9]{16,64} OR the literal
        # 'index' alias. No directory hierarchy — flat blob namespace.
        if path.startswith('/vault/blob/'):
            blob_id = path[len('/vault/blob/'):]
            # Strict ID validation: hex chars only (max 64 = SHA-256 length).
            # Rejects any path traversal, slashes, or shell metacharacters.
            if not re.match(r'^[A-Za-z0-9_-]{1,64}$', blob_id):
                return self._send_json(400, {'error': 'invalid blob id'})

            # OCI backend: blobs live under <user-prefix>/blobs/<id>.bin
            if _vault_backend == 'oci':
                if not (_oci_vault_namespace and _oci_vault_bucket):
                    return self._send_json(503, {'error': 'OCI vault not configured'})
                cli = _oci_object_client()
                key = _oci_obj_key('blobs/' + blob_id + '.bin')
                if method == 'PUT':
                    length = int(self.headers.get('content-length', 0) or 0)
                    if length == 0:
                        return self._send_json(400, {'error': 'empty blob'})
                    if length > 300 * 1024 * 1024:  # 300 MB cap per blob
                        return self._send_json(413, {'error': 'blob too large (max 300 MB)'})
                    body = self.rfile.read(length)
                    try:
                        cli.put_object(_oci_vault_namespace, _oci_vault_bucket, key, body,
                                       content_type='application/octet-stream')
                    except Exception as e:
                        return self._send_json(502, {'error': f'oci put: {e}'})
                    return self._send_json(200, {'id': blob_id, 'size': len(body)})
                if method == 'GET':
                    try:
                        resp = cli.get_object(_oci_vault_namespace, _oci_vault_bucket, key)
                        body = resp.data.content
                    except Exception as e:
                        err = str(e)
                        if '404' in err or 'NoSuchKey' in err or 'ObjectNotFound' in err:
                            return self._send_json(404, {'error': 'not found'})
                        return self._send_json(502, {'error': f'oci get: {e}'})
                    self.send_response(200)
                    self.send_header('content-type', 'application/octet-stream')
                    self.send_header('content-length', str(len(body)))
                    self.end_headers()
                    try: self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError): pass
                    return
                if method == 'DELETE':
                    try:
                        cli.delete_object(_oci_vault_namespace, _oci_vault_bucket, key)
                    except Exception as e:
                        err = str(e)
                        if '404' in err or 'NoSuchKey' in err or 'ObjectNotFound' in err:
                            return self._send_json(404, {'error': 'not found'})
                        return self._send_json(502, {'error': f'oci delete: {e}'})
                    return self._send_json(200, {'id': blob_id, 'deleted': True})
                return self._send_json(405, {'error': 'method not allowed'})

            # FS backend: blobs live under <vault_root>/.blobs/<id>.bin
            if _vault_root:
                root = pathlib.Path(_vault_root).resolve()
                blob_dir = root / '.blobs'
                try: blob_dir.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    return self._send_json(500, {'error': f'cannot create blob dir: {e}'})
                blob_path = blob_dir / (blob_id + '.bin')
                # Defense in depth: confirm the resolved path is still under the dir.
                try:
                    blob_path.resolve().relative_to(blob_dir.resolve())
                except ValueError:
                    return self._send_json(400, {'error': 'invalid blob path'})

                if method == 'PUT':
                    length = int(self.headers.get('content-length', 0) or 0)
                    if length == 0:
                        return self._send_json(400, {'error': 'empty blob'})
                    if length > 25 * 1024 * 1024:
                        return self._send_json(413, {'error': 'blob too large (max 25 MB)'})
                    body = self.rfile.read(length)
                    try:
                        blob_path.write_bytes(body)
                    except OSError as e:
                        return self._send_json(500, {'error': str(e)})
                    return self._send_json(200, {'id': blob_id, 'size': len(body)})
                if method == 'GET':
                    if not blob_path.exists():
                        return self._send_json(404, {'error': 'not found'})
                    try:
                        body = blob_path.read_bytes()
                    except OSError as e:
                        return self._send_json(500, {'error': str(e)})
                    self.send_response(200)
                    self.send_header('content-type', 'application/octet-stream')
                    self.send_header('content-length', str(len(body)))
                    self.end_headers()
                    try: self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError): pass
                    return
                if method == 'DELETE':
                    if not blob_path.exists():
                        return self._send_json(404, {'error': 'not found'})
                    try: blob_path.unlink()
                    except OSError as e:
                        return self._send_json(500, {'error': str(e)})
                    return self._send_json(200, {'id': blob_id, 'deleted': True})
                return self._send_json(405, {'error': 'method not allowed'})

            return self._send_json(503, {'error': 'no vault backend configured'})

        # ---------- Configure ----------
        if path == '/vault/configure' and method == 'POST':
            length = int(self.headers.get('content-length', 0) or 0)
            try:
                body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            except json.JSONDecodeError:
                return self._send_json(400, {'error': 'bad json'})
            # Update only what was sent so partial PATCH-style works.
            if 'root' in body:
                root = _clean_vault_root(body.get('root'))
                if root:
                    try:
                        root = str(pathlib.Path(root).resolve())
                    except OSError as e:
                        return self._send_json(400, {'error': f'invalid directory path: {e}'})
                if root and pathlib.Path(root) == _default_vault_root.resolve():
                    try:
                        pathlib.Path(root).mkdir(parents=True, exist_ok=True)
                    except OSError as e:
                        return self._send_json(500, {'error': f'could not create default vault: {e}'})
                if root and not pathlib.Path(root).is_dir():
                    return self._send_json(400, {'error': f'not a directory: {root}'})
                _vault_root = root
            if 'backend' in body:
                bk = (body.get('backend') or 'fs').strip()
                if bk not in ('fs', 'rest'):
                    return self._send_json(400, {'error': f'bad backend: {bk}'})
                _vault_backend = bk
            if 'restUrl' in body:
                _vault_rest_url = (body.get('restUrl') or '').strip()
            if 'restKey' in body and body['restKey']:  # ignore empty string (preserves existing)
                _vault_rest_key = body['restKey'].strip()
            return self._send_json(200, {
                'backend': _vault_backend,
                'root': _vault_root,
                'defaultRoot': str(_default_vault_root),
                'restUrl': _vault_rest_url,
                'restKey': '••••' if _vault_rest_key else '',
            })

        # Routes from here require a configured backend.
        if _vault_backend == 'rest':
            if not (_vault_rest_url and _vault_rest_key):
                return self._send_json(503, {'error': 'Obsidian REST not configured (URL + API key)'})
        else:
            if not _vault_root:
                return self._send_json(503, {'error': 'vault not configured — POST /vault/configure {"root": "..."}'})

        # ---------- List ----------
        if path == '/vault/list' and method == 'GET':
            if _vault_backend == 'rest':
                try:
                    return self._send_json(200, {'files': _rest_list_all()[:500]})
                except Exception as e:
                    return self._send_json(502, {'error': f'obsidian: {e}'})
            if _vault_backend == 'oci':
                try:
                    cli = _oci_object_client()
                    prefix = (_oci_vault_prefix.rstrip('/') + '/') if _oci_vault_prefix else ''
                    resp = cli.list_objects(
                        _oci_vault_namespace, _oci_vault_bucket,
                        prefix=prefix, fields='name,size,timeModified', limit=1000)
                    files = []
                    for obj in resp.data.objects:
                        rel = obj.name[len(prefix):]  # strip user prefix
                        if not rel.endswith('.md') or rel.startswith('.'):
                            continue
                        mtime = 0
                        if obj.time_modified:
                            try: mtime = int(obj.time_modified.timestamp() * 1000)
                            except Exception: pass
                        files.append({
                            'path': rel,
                            'title': rel.rsplit('/', 1)[-1].removesuffix('.md'),
                            'mtime': mtime,
                            'size': obj.size or 0,
                        })
                    files.sort(key=lambda f: f['mtime'], reverse=True)
                    return self._send_json(200, {'files': files[:500]})
                except Exception as e:
                    return self._send_json(502, {'error': f'oci: {e}'})
            root = pathlib.Path(_vault_root).resolve()
            files = []
            for p in root.rglob('*.md'):
                try:
                    rel = str(p.relative_to(root)).replace('\\', '/')
                except ValueError:
                    continue
                if any(part.startswith('.') for part in p.relative_to(root).parts):
                    continue
                try:
                    st = p.stat()
                    files.append({'path': rel, 'title': p.stem,
                                  'mtime': int(st.st_mtime * 1000), 'size': st.st_size})
                except OSError:
                    continue
            files.sort(key=lambda f: f['mtime'], reverse=True)
            return self._send_json(200, {'files': files[:500]})

        # ---------- Read ----------
        if path == '/vault/note' and method == 'GET':
            rel = qs.get('path', [''])[0]
            if _vault_backend == 'rest':
                try:
                    s, hdrs, body = _obsidian_request(
                        'GET', '/vault/' + urllib.parse.quote(rel),
                        extra_headers={'Accept': 'text/markdown'})
                except Exception as e:
                    return self._send_json(502, {'error': f'obsidian: {e}'})
                if s == 404:
                    return self._send_json(404, {'error': 'not found'})
                if s != 200:
                    return self._send_json(s, {'error': body[:300].decode('utf-8', 'replace')})
                self.send_response(200)
                self.send_header('content-type', 'text/markdown; charset=utf-8')
                self.end_headers()
                try: self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError): pass
                return
            if _vault_backend == 'oci':
                try:
                    cli = _oci_object_client()
                    resp = cli.get_object(_oci_vault_namespace, _oci_vault_bucket, _oci_obj_key(rel))
                    content = resp.data.content
                    self.send_response(200)
                    self.send_header('content-type', 'text/markdown; charset=utf-8')
                    self.end_headers()
                    try: self.wfile.write(content)
                    except (BrokenPipeError, ConnectionResetError): pass
                    return
                except Exception as e:
                    err = str(e)
                    if '404' in err or 'NoSuchKey' in err or 'ObjectNotFound' in err:
                        return self._send_json(404, {'error': 'not found'})
                    return self._send_json(502, {'error': f'oci: {e}'})
            try:
                target = _vault_resolve(rel)
            except ValueError as e:
                return self._send_json(400, {'error': str(e)})
            if not target.exists():
                return self._send_json(404, {'error': 'not found'})
            try:
                text = target.read_text(encoding='utf-8')
            except Exception as e:
                return self._send_json(500, {'error': str(e)})
            self.send_response(200)
            self.send_header('content-type', 'text/markdown; charset=utf-8')
            self.end_headers()
            try: self.wfile.write(text.encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError): pass
            return

        # ---------- Write/Append ----------
        if path == '/vault/note' and method == 'PUT':
            rel = qs.get('path', [''])[0]
            mode = qs.get('mode', ['write'])[0]
            length = int(self.headers.get('content-length', 0) or 0)
            body = self.rfile.read(length).decode('utf-8') if length else ''
            if _vault_backend == 'rest':
                # PUT replaces, POST appends.
                http_method = 'POST' if mode == 'append' else 'PUT'
                try:
                    s, _h, resp = _obsidian_request(
                        http_method, '/vault/' + urllib.parse.quote(rel),
                        body=body.encode('utf-8'), content_type='text/markdown')
                except Exception as e:
                    return self._send_json(502, {'error': f'obsidian: {e}'})
                if s not in (200, 204):
                    return self._send_json(s, {'error': resp[:300].decode('utf-8', 'replace')})
                return self._send_json(200, {'path': rel, 'mode': mode, 'backend': 'rest'})
            if _vault_backend == 'oci':
                try:
                    cli = _oci_object_client()
                    key = _oci_obj_key(rel)
                    content = body
                    if mode == 'append':
                        try:
                            existing = cli.get_object(
                                _oci_vault_namespace, _oci_vault_bucket, key).data.content
                            existing_text = existing.decode('utf-8', 'replace')
                            sep = '' if existing_text.endswith('\n') else '\n'
                            content = existing_text + sep + body
                        except Exception:
                            pass  # file doesn't exist yet — treat as write
                    encoded = content.encode('utf-8') if isinstance(content, str) else content
                    cli.put_object(_oci_vault_namespace, _oci_vault_bucket, key,
                                   put_object_body=encoded)
                    return self._send_json(200, {
                        'path': rel, 'mode': mode,
                        'size': len(encoded), 'backend': 'oci'})
                except Exception as e:
                    return self._send_json(502, {'error': f'oci: {e}'})
            try:
                target = _vault_resolve(rel)
            except ValueError as e:
                return self._send_json(400, {'error': str(e)})
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if mode == 'append' and target.exists():
                    existing = target.read_text(encoding='utf-8')
                    sep = '' if existing.endswith('\n') else '\n'
                    target.write_text(existing + sep + body, encoding='utf-8')
                else:
                    target.write_text(body, encoding='utf-8')
            except Exception as e:
                return self._send_json(500, {'error': str(e)})
            return self._send_json(200, {'path': rel, 'mode': mode, 'size': target.stat().st_size})

        # ---------- Delete ----------
        if path == '/vault/note' and method == 'DELETE':
            rel = qs.get('path', [''])[0]
            if _vault_backend == 'rest':
                try:
                    s, _h, resp = _obsidian_request('DELETE', '/vault/' + urllib.parse.quote(rel))
                except Exception as e:
                    return self._send_json(502, {'error': f'obsidian: {e}'})
                if s not in (200, 204):
                    return self._send_json(s, {'error': resp[:300].decode('utf-8','replace')})
                return self._send_json(200, {'deleted': rel})
            if _vault_backend == 'oci':
                try:
                    cli = _oci_object_client()
                    cli.delete_object(_oci_vault_namespace, _oci_vault_bucket, _oci_obj_key(rel))
                except Exception:
                    pass  # 404 on delete is fine
                return self._send_json(200, {'deleted': rel, 'backend': 'oci'})
            try:
                target = _vault_resolve(rel)
            except ValueError as e:
                return self._send_json(400, {'error': str(e)})
            if target.exists():
                try: target.unlink()
                except Exception as e: return self._send_json(500, {'error': str(e)})
            return self._send_json(200, {'deleted': rel})

        # ---------- Search ----------
        if path == '/vault/search' and method == 'GET':
            query = qs.get('q', [''])[0].strip()
            limit = int(qs.get('limit', ['10'])[0])
            if not query:
                return self._send_json(400, {'error': 'missing q'})
            if _vault_backend == 'rest':
                try:
                    return self._send_json(200, {'hits': _rest_search(query, limit)})
                except Exception as e:
                    return self._send_json(502, {'error': f'obsidian: {e}'})
            root = pathlib.Path(_vault_root).resolve()
            ql = query.lower()
            hits = []
            for p in root.rglob('*.md'):
                try:
                    rel = str(p.relative_to(root)).replace('\\', '/')
                except ValueError:
                    continue
                if any(part.startswith('.') for part in p.relative_to(root).parts):
                    continue
                try:
                    text = p.read_text(encoding='utf-8', errors='replace')
                except OSError:
                    continue
                tl = text.lower()
                title_score = 3 if ql in p.stem.lower() else 0
                count = tl.count(ql)
                if not (title_score or count):
                    continue
                idx = tl.find(ql)
                snippet = ''
                if idx >= 0:
                    s = max(0, idx - 60)
                    e = min(len(text), idx + len(query) + 60)
                    snippet = ('…' if s > 0 else '') + text[s:e].replace('\n', ' ').strip() + ('…' if e < len(text) else '')
                hits.append({'path': rel, 'title': p.stem,
                             'score': title_score + count, 'snippet': snippet})
            hits.sort(key=lambda h: h['score'], reverse=True)
            return self._send_json(200, {'hits': hits[:limit], 'total': len(hits)})

        # ---------- Graph (nodes + wikilink edges) ----------
        if path == '/vault/graph' and method == 'GET':
            try:
                graph = _build_graph_rest() if _vault_backend == 'rest' else _build_graph_fs()
                return self._send_json(200, graph)
            except Exception as e:
                return self._send_json(502, {'error': str(e)})

        # ---------- Open in Obsidian (REST only) ----------
        if path == '/vault/open' and method == 'POST':
            if _vault_backend != 'rest':
                return self._send_json(400, {'error': 'open-in-Obsidian requires REST backend'})
            length = int(self.headers.get('content-length', 0) or 0)
            try:
                body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            except json.JSONDecodeError:
                return self._send_json(400, {'error': 'bad json'})
            rel = (body.get('path') or '').strip()
            if not rel:
                return self._send_json(400, {'error': 'missing path'})
            try:
                s, _h, resp = _obsidian_request('POST', '/open/' + urllib.parse.quote(rel))
            except Exception as e:
                return self._send_json(502, {'error': f'obsidian: {e}'})
            return self._send_json(s if s != 200 else 200,
                                   {'opened': rel} if s == 200 else {'error': resp[:200].decode('utf-8','replace')})

        return self._send_json(404, {'error': f'unknown vault route: {path}'})

    def _brave_search(self):
        """Forward /brave/search?q=... to Brave Web Search.

        Auth: caller sends X-Brave-Key, we send X-Subscription-Token.
        Falls back to BRAVE_API_KEY env var if header is absent.
        """
        if not self.path.startswith('/brave/search'):
            return self.send_error(404)
        key = self.headers.get('X-Brave-Key') or os.environ.get('BRAVE_API_KEY', '')
        if not key:
            return self.send_error(401, 'no Brave key (set X-Brave-Key header or BRAVE_API_KEY env)')
        # Preserve all query params after /brave/search
        _, _, qs = self.path.partition('?')
        upstream_path = '/res/v1/web/search' + ('?' + qs if qs else '')
        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection('api.search.brave.com', 443, timeout=30, context=ctx)
        try:
            conn.request('GET', upstream_path, headers={
                'Accept': 'application/json',
                'Accept-Encoding': 'identity',
                'X-Subscription-Token': key,
                'User-Agent': 'OpenclawHQ/1.0',
            })
            resp = conn.getresponse()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in HOP_HEADERS or k.lower() == 'content-encoding':
                    continue
                self.send_header(k, v)
            self.end_headers()
            while True:
                chunk = resp.read(2048)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
        except Exception as e:
            try: self.send_error(502, f'brave: {e}')
            except Exception: pass
        finally:
            conn.close()

    def _proxy(self, method, prefix, target):
        UPSTREAM_HOST, UPSTREAM_PORT = target
        upstream_path = self.path[len(prefix) - 1:]  # keep leading /
        length = int(self.headers.get('content-length', 0) or 0)
        body = self.rfile.read(length) if length else None

        # Strip Accept-Encoding so the upstream doesn't gzip/compress, which
        # would add buffering and break streaming (SSE, etc.).
        _drop = HOP_HEADERS | {'accept-encoding'}
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in _drop}
        headers['host'] = f'{UPSTREAM_HOST}:{UPSTREAM_PORT}'
        headers['Accept-Encoding'] = 'identity'

        conn = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT,
                                          timeout=600)
        try:
            conn.request(method, upstream_path, body=body, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in HOP_HEADERS or k.lower() == 'content-encoding':
                    continue
                self.send_header(k, v)
            self.send_header('Connection', 'close')
            self.end_headers()
            # Use the underlying raw socket (resp.fp.read / resp.fp.read1)
            # to avoid BufferedReader.read(n) blocking until it accumulates
            # exactly n bytes — which kills SSE streaming.  HTTPResponse.read
            # wraps a BufferedReader; read1 returns as soon as ANY data is
            # available in the buffer (at most n bytes), which is exactly the
            # behaviour we need for real-time proxy streaming.
            raw_fp = resp  # HTTPResponse itself
            while True:
                try:
                    # read1 = "one underlying read, return whatever we got"
                    chunk = raw_fp.fp.read1(8192) if hasattr(raw_fp.fp, 'read1') else raw_fp.read(1024)
                except Exception:
                    break
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
        except Exception as e:
            try:
                self.send_error(502, f'upstream: {e}')
            except Exception:
                pass
        finally:
            conn.close()

    # ── Hermes capability mode (lite ↔ full) ─────────────────────────────────
    # Hermes injects its full toolset into the system prompt (~14-17k tokens),
    # which exceeds free hosted tiers' request-size caps (e.g. Groq free ~5-6k →
    # HTTP 413). 'lite' forces tool_search deferral + trims the preamble so the
    # prompt fits the free tier; 'full' restores the rich prompt for BYOK/paid
    # keys that can afford it. The HQ Settings toggle drives this.
    def _hermes_capability_file(self):
        import os as _os
        home = _os.environ.get('HERMES_HOME', '').strip() or _os.path.expanduser('~/.hermes')
        return _os.path.join(home, 'capability_mode')

    # ── Hermes model quick-switch ─────────────────────────────────────────────
    # GET  /hermes/model            → {model, presets}
    # POST /hermes/model {model}    → rewrite config.yaml model.default + restart
    # Presets are curated OpenRouter free open-weights ids verified to accept
    # Hermes' large prompt. The UI offers these as one-click switches.
    _HERMES_MODEL_PRESETS = [
        {'id': 'openai/gpt-oss-120b:free',                  'label': 'GPT-OSS 120B (default)'},
        {'id': 'nvidia/nemotron-3-super-120b-a12b:free',    'label': 'Nemotron 3 Super 120B'},
        {'id': 'nousresearch/hermes-3-llama-3.1-405b:free', 'label': 'Hermes 3 405B (Nous)'},
        {'id': 'meta-llama/llama-3.3-70b-instruct:free',    'label': 'Llama 3.3 70B'},
        {'id': 'qwen/qwen3-next-80b-a3b-instruct:free',     'label': 'Qwen3-Next 80B'},
    ]

    def _hermes_config_path(self):
        import os as _os
        home = _os.environ.get('HERMES_HOME', '').strip() or _os.path.expanduser('~/.hermes')
        return _os.path.join(home, 'config.yaml')

    def _hermes_get_model(self):
        import re as _re
        model = ''
        try:
            with open(self._hermes_config_path(), 'r', encoding='utf-8') as f:
                m = _re.search(r'^\s*default:\s*(.+)\s*$', f.read(), _re.MULTILINE)
                if m:
                    model = m.group(1).strip()
        except Exception:
            pass
        return self._send_json(200, {'model': model, 'presets': self._HERMES_MODEL_PRESETS})

    def _hermes_set_model(self):
        """POST {model} → rewrite config.yaml model.default + restart gateway.
        Only the model id changes; provider/base_url (OpenRouter) are preserved."""
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})
        model = str(req.get('model', '')).strip()
        # allow presets OR any plausible "vendor/model[:tag]" id
        import re as _re
        valid = any(p['id'] == model for p in self._HERMES_MODEL_PRESETS) or \
            bool(_re.match(r'^[\w.\-]+/[\w.\-:]+$', model))
        if not model or not valid:
            return self._send_json(400, {'error': 'invalid model id'})

        cfg_path = self._hermes_config_path()
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = f.read()
        except Exception as e:
            return self._send_json(500, {'error': f'read config: {e}'})

        new_cfg, n = _re.subn(r'(^\s*default:\s*).+$',
                              lambda m: m.group(1) + model, cfg,
                              count=1, flags=_re.MULTILINE)
        if n == 0:
            return self._send_json(500, {'error': 'no model.default line in config'})
        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                f.write(new_cfg)
        except Exception as e:
            return self._send_json(500, {'error': f'write config: {e}'})

        restarted = False
        try:
            subprocess.Popen(['hermes', 'gateway', 'restart'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            restarted = True
        except Exception as e:
            sys.stderr.write(f'[hermes] model restart failed: {e}\n')
        return self._send_json(200, {'model': model, 'restarted': restarted,
                                     'note': 'gateway reloading; allow ~10s'})

    def _hermes_get_capability(self):
        try:
            with open(self._hermes_capability_file(), 'r', encoding='utf-8') as f:
                mode = (f.read().strip() or 'lite')
        except Exception:
            mode = 'lite'
        return self._send_json(200, {'mode': mode if mode in ('lite', 'full') else 'lite'})

    def _hermes_set_capability(self):
        """POST {mode: 'lite'|'full'} → rewrite config.yaml's capability block and
        restart the hermes gateway so the new system-prompt size takes effect."""
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})
        mode = str(req.get('mode', '')).strip().lower()
        if mode not in ('lite', 'full'):
            return self._send_json(400, {'error': "mode must be 'lite' or 'full'"})

        import os as _os
        home = _os.environ.get('HERMES_HOME', '').strip() or _os.path.expanduser('~/.hermes')
        cfg_path = _os.path.join(home, 'config.yaml')
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = f.read()
        except Exception as e:
            return self._send_json(500, {'error': f'read config: {e}'})

        # Replace the toolsets/agent/tools tail (everything from the first
        # 'toolsets:' line) with the requested capability block. The block layout
        # matches hermes-bootstrap.py:_capability_block so the two stay in sync.
        if mode == 'full':
            block = ('toolsets:\n  - hermes-cli\n'
                     'agent:\n  environment_probe: true\n  task_completion_guidance: true\n'
                     'tools:\n  tool_search:\n    enabled: auto\n')
        else:
            block = ('toolsets:\n  - hermes-cli\n'
                     'agent:\n  environment_probe: false\n  task_completion_guidance: false\n'
                     'tools:\n  tool_search:\n    enabled: true\n    threshold_pct: 0\n')

        idx = cfg.find('\ntoolsets:')
        new_cfg = (cfg[:idx + 1] if idx >= 0 else cfg.rstrip() + '\n') + block
        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                f.write(new_cfg)
            with open(self._hermes_capability_file(), 'w', encoding='utf-8') as f:
                f.write(mode)
        except Exception as e:
            return self._send_json(500, {'error': f'write config: {e}'})

        # Restart the gateway so it reloads config.yaml. Best-effort; the proxy
        # keeps serving until the new gateway binds. `hermes gateway restart`
        # replaces the running singleton.
        restarted = False
        try:
            subprocess.Popen(['hermes', 'gateway', 'restart'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            restarted = True
        except Exception as e:
            sys.stderr.write(f'[hermes] capability restart failed: {e}\n')
        return self._send_json(200, {'mode': mode, 'restarted': restarted,
                                     'note': 'gateway reloading; allow ~10s'})

    def _hermes_set_openrouter_key(self):
        """POST {key} → store the user's OWN OpenRouter key in ~/.hermes/.env
        (OPENROUTER_API_KEY) and restart the gateway so it takes effect.

        This gives each user a UNIQUE free key (created at openrouter.ai/keys),
        overriding any shared operator key injected at provision. The key lives
        only in the user's container .env (0600), never in the browser long-term.
        """
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})
        key = str(req.get('key', '')).strip()
        import re as _re
        if not _re.match(r'^sk-or-[A-Za-z0-9_\-]{8,}$', key):
            return self._send_json(400, {'error': 'invalid OpenRouter key (expected sk-or-…)'})

        import os as _os
        home = _os.environ.get('HERMES_HOME', '').strip() or _os.path.expanduser('~/.hermes')
        env_path = _os.path.join(home, '.env')
        try:
            _os.makedirs(home, exist_ok=True)
            lines = []
            if _os.path.exists(env_path):
                with open(env_path, 'r', encoding='utf-8') as f:
                    lines = [l for l in f.read().splitlines()
                             if not l.startswith('OPENROUTER_API_KEY=')]
            lines.append(f'OPENROUTER_API_KEY={key}')
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
            try:
                _os.chmod(env_path, 0o600)
            except Exception:
                pass
        except Exception as e:
            return self._send_json(500, {'error': f'write .env: {e}'})

        # Also export into THIS process env so an immediate gateway restart
        # (which inherits serve.py's env via the bootstrap) sees it.
        _os.environ['OPENROUTER_API_KEY'] = key
        restarted = False
        try:
            subprocess.Popen(['hermes', 'gateway', 'restart'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            restarted = True
        except Exception as e:
            sys.stderr.write(f'[hermes] openrouter-key restart failed: {e}\n')
        return self._send_json(200, {'ok': True, 'restarted': restarted,
                                     'note': 'gateway reloading; allow ~10s'})

    def _hermes_proxy(self, method):
        """Proxy /hermes/* → the local `hermes gateway` OpenAI-compatible API
        server (HERMES_HOST:HERMES_PORT, default 127.0.0.1:8642).

        /hermes/v1/chat/completions → http://127.0.0.1:8642/v1/chat/completions

        Auth: API_SERVER_KEY env var is injected as 'Authorization: Bearer …'
        server-side and takes priority over any header the browser sends, so
        the key never lives in the browser. Falls back to the client's
        Authorization header if the env var is absent (dev convenience).
        Accept-Encoding is forced to 'identity' so SSE arrives uncompressed
        and streams straight through. A bounded tail of the response is scanned
        for the OpenAI `usage` object and recorded per-principal (metering).
        """
        upstream_path = self.path[len('/hermes'):]  # keep leading /
        if not upstream_path.startswith('/'):
            upstream_path = '/' + upstream_path

        length = int(self.headers.get('content-length', 0) or 0)
        body = self.rfile.read(length) if length else None

        _drop = HOP_HEADERS | {'host', 'authorization', 'accept-encoding'}
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in _drop}
        headers['Host'] = f'{HERMES_HOST}:{HERMES_PORT}'
        headers['Accept-Encoding'] = 'identity'

        env_key = os.environ.get('API_SERVER_KEY', '').strip()
        if env_key:
            headers['Authorization'] = 'Bearer ' + env_key
        else:
            client_auth = self.headers.get('Authorization') or self.headers.get('authorization')
            if client_auth:
                headers['Authorization'] = client_auth

        principal = (self.headers.get('X-User-Principal') or '').strip() or 'local'
        conn = http.client.HTTPConnection(HERMES_HOST, HERMES_PORT, timeout=600)
        try:
            conn.request(method, upstream_path, body=body, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in HOP_HEADERS or k.lower() == 'content-encoding':
                    continue
                self.send_header(k, v)
            self.send_header('Connection', 'close')
            self.end_headers()
            tail = b''  # rolling buffer (last 16KB) for usage extraction
            while True:
                try:
                    chunk = resp.fp.read1(8192) if hasattr(resp.fp, 'read1') else resp.read(1024)
                except Exception:
                    break
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                tail = (tail + chunk)[-16384:]
            self._record_hermes_usage(principal, upstream_path, tail)
        except Exception as e:
            try:
                self.send_error(502, f'hermes: {e}')
            except Exception:
                pass
        finally:
            conn.close()

    # Deterministic, writable usage-log path: prefer an explicit override, then
    # the persistent Hermes data dir (mounted volume in the fleet), then /data,
    # then the home dir. Avoids the HOME-ambiguity that silently broke writes.
    def _hermes_usage_log_path(self):
        override = os.environ.get('HERMES_USAGE_LOG', '').strip()
        if override:
            return override
        for base in (os.environ.get('HERMES_HOME', '').strip(), '/data',
                     os.path.expanduser('~')):
            if base and os.path.isdir(base):
                return os.path.join(base, 'hermes-usage.log')
        return os.path.join(os.path.expanduser('~'), 'hermes-usage.log')

    def _record_hermes_usage(self, principal, path, tail_bytes):
        """Best-effort per-principal token accounting. Scans the response tail
        for the LAST OpenAI `usage` object (covers both non-stream JSON bodies
        and the terminal SSE chunk), then appends a JSONL record to the usage
        log. Never raises — metering must not break the proxy. Phase 5 replaces
        this flat log with the vault-backed quota store."""
        try:
            text = tail_bytes.decode('utf-8', 'replace')
            sys.stderr.write(f'[hermes] _record called tail={len(text)}B path={path}\n')
            usage = None
            # Fast path: non-streaming responses are a single JSON object whose
            # top-level `usage` we can read directly.
            try:
                obj = json.loads(text)
                if isinstance(obj, dict) and isinstance(obj.get('usage'), dict):
                    usage = obj['usage']
            except Exception:
                pass
            # SSE / partial path: find the LAST `"usage"` key and brace-match
            # the object that FOLLOWS it (the usage object's own braces).
            if not isinstance(usage, dict):
                idx = text.rfind('"usage"')
                brace = text.find('{', idx) if idx >= 0 else -1
                # Guard against `"usage": null` (intermediate stream chunks).
                if brace >= 0 and 'null' not in text[idx:brace]:
                    depth = 0
                    for j in range(brace, len(text)):
                        c = text[j]
                        if c == '{':
                            depth += 1
                        elif c == '}':
                            depth -= 1
                            if depth == 0:
                                try:
                                    cand = json.loads(text[brace:j + 1])
                                    if isinstance(cand, dict):
                                        usage = cand
                                except Exception:
                                    usage = None
                                break
            if not isinstance(usage, dict):
                sys.stderr.write('[hermes] _record: no usage object found in tail\n')
                return
            rec = {
                'ts': time.time(),
                'principal': principal,
                'path': path,
                'prompt_tokens': usage.get('prompt_tokens'),
                'completion_tokens': usage.get('completion_tokens'),
                'total_tokens': usage.get('total_tokens'),
            }
            log_path = self._hermes_usage_log_path()
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rec, separators=(',', ':')) + '\n')
            sys.stderr.write(f'[hermes] usage principal={principal} total={rec["total_tokens"]} -> {log_path}\n')
        except Exception as e:
            sys.stderr.write(f'[hermes] _record error: {e!r}\n')

    def log_message(self, fmt, *args):
        sys.stderr.write(f'{self.address_string()} - {fmt % args}\n')


class ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _local_ip():
    """Best-effort LAN IP (not loopback) for sharing with mobile devices."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


if __name__ == '__main__':
    # When packaged as a PyInstaller exe, static files live next to the exe.
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Optional TLS — set OPENCLAW_TLS_CERT and OPENCLAW_TLS_KEY to the paths
    # produced by mkcert (or any trusted cert/key pair).
    # Example: mkcert 192.168.1.x localhost 127.0.0.1
    _tls_cert = os.environ.get('OPENCLAW_TLS_CERT', '').strip()
    _tls_key  = os.environ.get('OPENCLAW_TLS_KEY',  '').strip()
    _tls_on   = bool(_tls_cert and _tls_key and
                     pathlib.Path(_tls_cert).is_file() and
                     pathlib.Path(_tls_key).is_file())
    _scheme   = 'https' if _tls_on else 'http'

    with ThreadedServer(('', PORT), Handler) as httpd:
        if _tls_on:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(_tls_cert, _tls_key)
            httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
            print(f'  🔒 TLS enabled  cert={_tls_cert}')

        lan = _local_ip()
        print(f'Openclaw HQ -> {_scheme}://localhost:{PORT}/hq.html')
        if lan:
            print(f'  📱 Mobile / LAN  -> {_scheme}://{lan}:{PORT}/hq.html')
        if not _tls_on:
            print('  💡 Set OPENCLAW_TLS_CERT + OPENCLAW_TLS_KEY for HTTPS (enables iOS service worker)')
        for prefix, (h, p) in ROUTES.items():
            print(f'  proxy {prefix}* -> {h}:{p}/*')
        if _openclaw_allowed_dirs:
            print(f'  /openclaw/stream  ELEVATED · tools={",".join(_openclaw_allowed_tools)}'
                  f' · dirs={_openclaw_allowed_dirs}')
        else:
            print('  /openclaw/stream  DISABLED (set OPENCLAW_ALLOWED_DIRS to enable)')
        _codex_found = (_codex_bin if _codex_bin and pathlib.Path(_codex_bin).is_file() else '') \
            or shutil.which(_codex_bin or 'codex') or shutil.which('codex.cmd')
        if _codex_found and _openclaw_allowed_dirs:
            print(f'  /codex/stream     CODEX · dirs={_openclaw_allowed_dirs}')
        else:
            print('  /codex/stream     DISABLED (codex not found or OPENCLAW_ALLOWED_DIRS not set)')
        print('  /approvals/external  Claude Code PreToolUse hook bridge')
        httpd.serve_forever()
