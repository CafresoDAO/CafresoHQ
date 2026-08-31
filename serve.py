#!/usr/bin/env python3
import sys as _sys
if hasattr(_sys.stdout, 'reconfigure'):
    _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    _sys.stderr.reconfigure(encoding='utf-8', errors='replace')
"""Serve CafresoHQ static files and proxy local LM Studio / Ollama / Brave / Vault.

Same-origin proxy avoids browser CORS. SSE streams pass through unbuffered.
Brave proxy:  /brave/search?q=...   forwards to api.search.brave.com with the
caller's X-Brave-Key header rewritten to X-Subscription-Token.
Vault proxy:  /vault/*              read/write Markdown notes under a configured
root directory. Root set via CAFRESOHQ_VAULT env or POST /vault/configure.
"""
import base64
import hashlib
import http.client
import http.server
import json
import mimetypes
import os
# ── env compat shim: mirror legacy OPENCLAW_* vars to CAFRESOHQ_* ───────────────
# Deployed container/entrypoint still export OPENCLAW_* names; mirror them so the
# renamed CAFRESOHQ_* reads keep working until images are rebuilt. Remove later.
for _k, _v in list(os.environ.items()):
    if _k.startswith('OPENCLAW_'):
        os.environ.setdefault('CAFRESOHQ_' + _k[len('OPENCLAW_'):], _v)
import pathlib
import re
import re as _re  # module-scope alias: three handler sites use `_re.…` and
                  # previously only worked in the container's concatenated
                  # build (DRIVER_CONTRACT §0/§5 — the latent NameError).
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

# Agent runtimes sit behind the driver contract (docs/DRIVER_CONTRACT.md);
# routes here speak only that surface. Backends migrate into drivers/ one at
# a time — claude-code first, Hermes last (§5 of the contract doc).
import drivers as _drivers
from drivers.base import DriverError as _DriverError

# Listen port. Env-configurable (the Dockerfile + entrypoint set PORT) so a
# self-hoster can avoid a clash with another local service; defaults to 8787.
PORT = int(os.environ.get('PORT', '8787') or '8787')

def _local_route(env_names, default):
    """Where a local backend lives — resolved from the SAME place the driver
    asks, so the office cannot hold two answers at once.

    It held two. `/lmstudio/` was pinned to ('10.0.0.100', 1234): a private
    LAN address, committed to a shipped file, pointing at one particular
    machine on one particular network. Meanwhile `LMStudioDriver.base_url()`
    reads CAFRESOHQ_LMSTUDIO_URL / LMSTUDIO_BASE_URL and otherwise defaults
    to http://localhost:1234/v1, and the front desk only shows the LM Studio
    card when THAT probe comes back reachable.

    Measured on the machine where the two disagree: the NEW HIRE BRAIN
    picker listed eleven LM Studio models (browser → this proxy →
    10.0.0.100) on the same run that the front desk offered no LM Studio
    card at all (server → driver → localhost). The office could name the
    boss's local models on one screen and say it had not found LM Studio on
    the next. Neither surface was lying; they were reading different files.

    So one resolver, both consumers, and the default is localhost — which is
    what the driver already assumed and what the `/ollama/` line beside it
    had right all along. `PORT` directly above is the precedent: the thing a
    self-hoster has to change belongs in the environment, not in the source.

    The default strings are written identically to the driver's so a future
    reader diffing the two sees them match; only host and port are used
    here, the path is the caller's.
    """
    raw = ''
    for name in env_names:
        raw = os.environ.get(name, '').strip()
        if raw:
            break
    parts = urllib.parse.urlsplit(raw or default if '://' in (raw or default)
                                  else 'http://' + (raw or default))
    return (parts.hostname or 'localhost',
            parts.port or (443 if parts.scheme == 'https' else 80))


ROUTES = {
    '/lmstudio/': _local_route(('CAFRESOHQ_LMSTUDIO_URL', 'LMSTUDIO_BASE_URL'),
                               'http://localhost:1234/v1'),
    '/ollama/':   _local_route(('CAFRESOHQ_OLLAMA_URL',),
                               'http://localhost:11434/v1'),
}

# Hermes Agent (Nous Research) — we proxy /hermes/* → the gateway's
# OpenAI-compatible API server, injecting the Bearer key server-side and
# metering the OpenAI `usage` object for per-principal billing. Not in ROUTES
# because it needs the dedicated _hermes_proxy (auth injection + usage tap).
# Gateway host/port, key handling, and ALL config.yaml/.env plumbing live in
# drivers/hermes.py (DRIVER_CONTRACT §5: Hermes is one driver among peers).

# ── Idle tracking (powers fleet reap-idle → stop idle containers, free A1 pool) ─
# Single-slot list so the request handler can mutate it without `global`.
# /idle, /health, and /idle's own polls do NOT count as activity.
_LAST_ACTIVITY = [time.time()]
# /market is exempt too: the ambient ticker polls every 60s and must never be
# what keeps an idle fleet container awake/billed.
_IDLE_EXEMPT_PREFIXES = ('/idle', '/health', '/market')

def _touch_activity(path):
    if not any(path == p or path.startswith(p) for p in _IDLE_EXEMPT_PREFIXES):
        _LAST_ACTIVITY[0] = time.time()

HOP_HEADERS = {'host', 'connection', 'keep-alive', 'proxy-authenticate',
               'proxy-authorization', 'te', 'trailers', 'transfer-encoding',
               'upgrade', 'content-length'}
# Claude Code (Pro/Max subscription) — invoked as a subprocess so the user's
# already-authenticated CLI does the auth. Binary resolution + the
# CAFRESOHQ_CLAUDE_BIN override now live in drivers/claude_code.py.

# Codex CLI — alternative elevated agent backend (`codex exec --json`, same
# allowed-dirs sandbox). Binary resolution + the CAFRESOHQ_CODEX_BIN override
# now live in drivers/codex.py; auth stays in ~/.codex — never touched here.

# Hermes CLI (Nous Research) — binary resolution + the CAFRESOHQ_HERMES_BIN
# override live in drivers/hermes.py. Hermes is unix-only (gateway/pty_bridge
# import termios/pty/fcntl); on native Windows run the stack in WSL.

# Gemini CLI (Google) — npm `@google/gemini-cli`, native on every platform.
# Binary resolution + the CAFRESOHQ_GEMINI_BIN override now live in
# drivers/gemini_cli.py; auth stays in ~/.gemini — never touched here.

# Extra browser origins allowed to open the terminal WebSocket and fetch the PTY
# nonce. Needed when the HQ UI is served cross-origin from an ICP asset canister
# (the frontend/backend split). Comma-separated, e.g.
#   CAFRESOHQ_ALLOWED_WS_ORIGINS=https://<canister>.icp0.io,https://ai.cafreso.com
_extra_app_origins = {o.strip() for o in
                      os.environ.get('CAFRESOHQ_ALLOWED_WS_ORIGINS', '').split(',')
                      if o.strip()}

# Hostnames a client-supplied Host header may name and still be treated as
# same-origin (see _app_origins). Loopback literals only: a DNS-rebinding attack
# always arrives carrying the attacker's own hostname, never one of these.
_LOOPBACK_HOSTS = {'localhost', '127.0.0.1', '::1', '[::1]', '0.0.0.0'}

# API contract version between the (canister-served) UI and this backend. Bump
# only on a BREAKING change to an endpoint the UI depends on; the UI reads it
# from /health and degrades gracefully rather than hard-failing across a
# version-skewed deploy (UI on a canister, API in a slower-to-update container).
API_VERSION = 1

# ── Client path translation (Windows path → WSL mount) ───────────────────────
# The HQ UI may run on Windows and store project paths in Windows form
# (C:\Users\me\proj). The supported Windows deployment runs the whole serve.py
# stack inside WSL, where those live under /mnt/<drive>. Translate any
# client-supplied path so the unix host can resolve it. No-op on native Windows
# (serve.py there already speaks Windows paths) and for paths that are already
# unix-style. Accepts both back- and forward-slash Windows paths.
_WINPATH_RE = re.compile(r'^([A-Za-z]):[\\/](.*)$')
_WINDRIVE_RE = re.compile(r'^([A-Za-z]):[\\/]?$')

def _client_path(p):
    if not p or sys.platform == 'win32':
        return p
    m = _WINPATH_RE.match(p)
    if m:
        return f'/mnt/{m.group(1).lower()}/' + m.group(2).replace('\\', '/')
    m2 = _WINDRIVE_RE.match(p)
    if m2:
        return f'/mnt/{m2.group(1).lower()}'
    return p

# /cafresohq/stream — elevated agent endpoint with computer access. Same
# `claude` CLI as /claudecode/stream but tools are ENABLED and constrained
# by a server-side allowlist (paths and tool names). Both lists are env-
# only — the client can't widen them by sending a bigger spec. If either
# allowlist is empty the endpoint refuses requests, so the unconfigured
# default is safe.
#
#   CAFRESOHQ_ALLOWED_DIRS: os.pathsep-separated absolute paths claude can
#                          read/write. Empty → endpoint disabled.
#   CAFRESOHQ_ALLOWED_TOOLS: comma-separated tool names Claude Code accepts
#                          (Read, Write, Edit, Glob, Grep, Bash, ...).
#                          Default is read-only ("Read,Glob,Grep") so the
#                          first-time experience can't mutate the disk
#                          without an explicit opt-in.
_ALLOWED_DIRS_EXPLICIT = 'CAFRESOHQ_ALLOWED_DIRS' in os.environ
_cafresohq_allowed_dirs = [d.strip() for d in
                          os.environ.get('CAFRESOHQ_ALLOWED_DIRS',
                              os.path.expanduser('~') + os.pathsep +
                              os.path.join(os.path.expanduser('~'), 'Documents')
                          ).split(os.pathsep)
                          if d.strip()]

# The standalone Terminal tab (views/misc.jsx TerminalView) needs a real cwd
# to hand pty_server.py — it falls back to '/root/Documents', the container
# image's code-agent sandbox dir, when `window._TERMINAL_CWD` is unset. That
# global was never actually injected on any self-hosted (non-container) run,
# so every Terminal tab 400'd with "directory not found: /root/Documents" —
# a path that doesn't exist, and isn't even readable, outside the Dockerfile.
# Mirrors CAFRESOHQ_ALLOWED_DIRS's own local-mode default one directory up.
_cafresohq_terminal_cwd = os.environ.get('CAFRESOHQ_TERMINAL_CWD',
                              os.path.join(os.path.expanduser('~'), 'Documents'))

def _within_allowed_dirs(p):
    """True iff resolved path `p` is inside one of _cafresohq_allowed_dirs.
    Uses Path.relative_to (NOT str.startswith, which lets '/data/proj' authorize
    the sibling '/data/proj-secret'). Enforced in EVERY runtime mode — the fs
    read/browse routes are otherwise an unauthenticated arbitrary-read hole in
    local/BYO deployments. If the allow-list is explicitly emptied, allow (the
    documented opt-out)."""
    if not _cafresohq_allowed_dirs:
        return True
    try:
        rp = pathlib.Path(p).resolve()
    except Exception:
        return False
    for d in _cafresohq_allowed_dirs:
        try:
            rp.relative_to(pathlib.Path(d).resolve())
            return True
        except (ValueError, Exception):
            continue
    return False


def _workspace_path(path, strict=False):
    """`path` as a pathlib.Path, with a RELATIVE path anchored to the
    workspace root rather than to wherever serve.py happens to be running.

    /tools/exec has always read a relative arg that way — its _resolve_arg
    anchors to the request's cwd — but every /fs route resolved against the
    server process cwd, so one string meant two directories. Measured on
    office 9262, 2026-08-15, with site/index.html in the workspace and
    serve.py started from the repo:

      POST /tools/exec  DIR_LIST  arg=site      200  the workspace's site/
      POST /tools/exec  FILE_WRITE site/x.txt   200  written to the workspace
      GET  /fs/collect?path=site                403  outside allowed dirs
      POST /fs/upload?path=site                 403
      GET  /fs/site/<b64 'site/'>/index.html    403

    A coworker wrote site/index.html, listed site/, emitted
    [PUBLISH_SITE: site/], the boss stamped it — and the publish 403'd on a
    folder the office had just made. publishSite calls fsCollect FIRST inside
    the II-shell branch and swallows the throw, so even with the shell
    present a relative path degraded to a preview link that was also 403.

    allowed_dirs[0] is the anchor because this codebase already treats it as
    the workspace root: it is what /fs/browse and /fs/upload fall back to when
    given no path at all. This only ANCHORS — every caller still resolves and
    runs its own whitelist check afterwards, so `../` escapes stay refused.

    Not applied in the local no-whitelist case: there the defaults are ~ and
    ~/Documents, which are not a workspace, and nothing is refused anyway — so
    cwd-relative stays what it has always been for local development.
    """
    p = pathlib.Path(_client_path(path))
    skip = (not strict and not _ALLOWED_DIRS_EXPLICIT
            and _RUNTIME_ENV == 'local')
    # `is_absolute()` is here to be read, not to decide: pathlib already
    # discards the left side when the right is absolute, so Path(ws) /
    # Path('/etc') is '/etc' with or without it. Deleting it changes no
    # output and the fire-test for this fix proved that by deleting it — do
    # not read it as a guard.
    if not p.is_absolute() and not skip and _cafresohq_allowed_dirs:
        p = pathlib.Path(_cafresohq_allowed_dirs[0]) / p
    return p


_cafresohq_allowed_tools = [t.strip() for t in
                           os.environ.get('CAFRESOHQ_ALLOWED_TOOLS',
                               # Default set — discovery, reading and editing,
                               # plus external research. The ROOT TodoWrite /
                               # Notebook* tools are deliberately excluded
                               # because they're meta-tools that confuse the
                               # sub-agent's own task list.
                               #
                               # Bash is NOT in the default set: /tools/exec runs
                               # it through a shell, so enabling it by default
                               # makes every unconfigured deployment one request
                               # away from arbitrary command execution. Opt in
                               # explicitly with CAFRESOHQ_ALLOWED_TOOLS when the
                               # deployment is authenticated and trusted.
                               'Read,Glob,Grep,Edit,Write,WebFetch,WebSearch'
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
import exporters
import fs_routes
import pty_server
pty_server._client_path = _client_path
exporters._vault_root = lambda: _vault_root
# Deferred like _vault_root above: _vault_hidden_part is defined further down
# this file, and the lambda resolves it at request time, not import time.
exporters._vault_hidden_part = lambda rel: _vault_hidden_part(rel)
fs_routes._client_path = _client_path
fs_routes._workspace_path = _workspace_path
fs_routes._RUNTIME_ENV = _RUNTIME_ENV
fs_routes._within_allowed_dirs = _within_allowed_dirs
fs_routes._cafresohq_allowed_dirs = _cafresohq_allowed_dirs
fs_routes._ALLOWED_DIRS_EXPLICIT = _ALLOWED_DIRS_EXPLICIT
pty_server._RUNTIME_ENV = _RUNTIME_ENV

# ── Bearer-key auth for local / BYO deployments ──────────────────────────────
# When CAFRESOHQ_API_KEY is set, the dangerous routes (terminal, agents, vault,
# code-agent streams, hq-state) require it via an X-API-Key header or a ?k=
# query param (WebSocket handshakes can't set custom headers). In OCI-fleet mode
# the Caddy gateway + verifier already gate access, so the key stays unset/optional
# there — this is the security floor for Local-native/WSL and any non-loopback
# exposure (the terminal PTY is effectively RCE). Static UI + /health stay open
# so the app shell can bootstrap.
CAFRESOHQ_API_KEY = os.environ.get('CAFRESOHQ_API_KEY', '').strip()
_KEY_PROTECTED_PREFIXES = (
    '/vault', '/hermes', '/terminal', '/cafresohq', '/codex', '/claudecode',
    '/agents', '/hq/', '/hq-state', '/spawn', '/graph/publish', '/approvals',
    '/browser', '/missions',
    # Code-execution + filesystem routes: RCE-/write-equivalent to the routes
    # above and MUST sit behind the same key. /tools/exec runs a shell;
    # /projects,/export,/generate touch the host; the /fs mutation routes
    # write/delete. NOTE: only the /fs *mutation* prefixes are protected — the
    # preview iframe fetches /fs/site/<root>/<asset> read-only via the browser
    # with no key, so blanket-protecting bare '/fs' would break multi-file
    # previews. The allowed-dirs boundary (enforced in every mode below) caps
    # the read routes instead.
    '/tools', '/projects', '/export', '/generate',
    '/fs/upload', '/fs/mkdir', '/fs/rename', '/fs/delete',
)

# Background CLI-install jobs (POST /agents/install returns 202 immediately;
# the UI polls GET /agents/install/status?agent=…). One job per agent id.
_INSTALL_JOBS = {}
_INSTALL_JOBS_LOCK = threading.Lock()

# ── Market quotes (Trading Floor theme ticker) ──────────────────────────────
# GET /market/quotes proxies Yahoo Finance's public chart endpoint: stock
# indices have no CORS-open free API the browser could hit directly, and
# stooq's CSV endpoints now sit behind a JS anti-bot wall. Cached 60s so a
# whole floor of open tabs costs one upstream sweep per minute; on total
# upstream failure the last good payload is served stale instead of erroring.
_MARKET_SYMBOLS = (
    ('NAS100', '^NDX'),
    ('US30',   '^DJI'),
    ('SPX',    '^GSPC'),
    ('GOLD',   'GC=F'),
)
_market_cache = {'ts': 0.0, 'quotes': []}
_market_lock = threading.Lock()
# HQ state persistence
_hq_state_dir   = pathlib.Path(os.environ.get('CAFRESOHQ_HQ_STATE_DIR',
                    os.path.join(os.path.dirname(__file__), 'hq-state')))
_hq_memory_dir  = pathlib.Path(os.environ.get('CAFRESOHQ_MEMORY_DIR',
                    str(_hq_state_dir / 'memory')))  # follows CAFRESOHQ_HQ_STATE_DIR
                                                     # unless explicitly overridden


# ---- Night Shift (Sprint 4 MVP-1) ------------------------------------------
# "Close the laptop, work continues": a 30s scheduler daemon runs missions
# SERVER-side via night_runner.py — a restricted read/search/fetch + vault-write
# tool subset (no WALLET/PUBLISH/BASH/FILE_WRITE; the money/publish seam stays
# in the authenticated browser shell by construction). Files:
#   hq-state/scheduled-missions.json  — the schedules (UI + hqsh manage these)
#   hq-state/mission-runs.json        — ring-capped run log (Gazette lead story)
# One mission runs at a time; shared-activity writes are deferred while a real
# browser session is live (last-writer-wins clobber guard).
_night_lock = threading.Lock()
_night_running = {}          # scheduleId -> True while a run is in flight
_night_abort = set()         # scheduleId -> requested to stop mid-run (see _missions_delete)
_night_base_url = ['']       # set in __main__ once scheme + port are known
_LAST_UI_ACTIVITY = [0.0]    # last request that came from a real browser
MAX_NIGHT_RUNS_KEPT = 100
MAX_NIGHT_SCHEDULES = 20


def _night_path(name):
    return _hq_state_dir / name


def _night_load(name, default):
    try:
        with open(_night_path(name), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def _night_save(name, data):
    _hq_state_dir.mkdir(parents=True, exist_ok=True)
    tmp = _night_path(name + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())   # os.replace is atomic, but only w.r.t. data
    os.replace(tmp, _night_path(name))          # already on disk


# ── Shared "trial brain" metering ──────────────────────────────────────────
# hermes-bootstrap.py writes HERMES_HOME/trial.json when a fresh HQ falls back to
# the operator's shared trial key (so a new user's agents work with no signup).
# That key draws on ONE shared upstream account, so serve.py caps each principal
# to a small number of trial completions/day and clears the trial the moment the
# user brings their own key. A user's OWN key is never metered here.
_TRIAL_DAILY_CAP = max(1, int(os.environ.get('CAFRESOHQ_TRIAL_DAILY_CAP', '25') or '25'))
_trial_usage_lock = threading.Lock()

# ── Operator control plane (network-wide switches, read from the canister) ──
# The planAdmin sets ONE JSON blob on cafresohq_state; every client + container
# reads it from the public /operator/config.json route. serve.py caches it and
# honors: trialBrain.enabled (kill the shared trial network-wide),
# trialBrain.dailyCap (live cap override), gpuNode.enabled (a worker self-pauses
# when the operator takes the node down). Never blocks on the network — a failed
# fetch keeps the last good config (or {}), so a canister blip can't break chat.
_OPERATOR_BASE = os.environ.get(
    'SEARCH_STATE_URL', 'https://ydacz-riaaa-aaaal-qxeja-cai.icp0.io').rstrip('/')
_operator_cfg = {'ts': 0.0, 'data': {}}
_operator_cfg_lock = threading.Lock()


def _operator_config():
    with _operator_cfg_lock:
        if time.time() - _operator_cfg['ts'] < 60:
            return _operator_cfg['data']
    data = None
    try:
        with urllib.request.urlopen(_OPERATOR_BASE + '/operator/config.json', timeout=6) as r:
            parsed = json.loads(r.read().decode('utf-8'))
        if isinstance(parsed, dict):
            data = parsed
    except Exception:
        pass
    with _operator_cfg_lock:
        if data is not None:
            _operator_cfg['data'] = data
        _operator_cfg['ts'] = time.time()
        return _operator_cfg['data']


def _trial_cap():
    """Operator override (trialBrain.dailyCap) wins over the env default."""
    op = _operator_config().get('trialBrain') or {}
    c = op.get('dailyCap')
    if isinstance(c, (int, float)) and c >= 1:
        return int(c)
    return _TRIAL_DAILY_CAP


# ~/.hermes path resolution lives in drivers/hermes.py; trial.json (host-side
# trial-brain policy state) shares that directory.
_hermes_home = _drivers.hermes.home


def _validate_local_base_url(u):
    """(ok, error) for a LOCAL model backend URL the operator typed.

    ALLOWLIST, not blocklist — whatever this accepts, the container will later
    POST to, and /hermes is only key-protected when CAFRESOHQ_API_KEY is set. So
    this is the whole defence, not a layer of it.

    IP-literal/localhost only is deliberate and is what closes DNS rebinding: we
    validate at write time but hermes resolves at call time, so a hostname that
    passes here can point anywhere seconds later. An IP literal has no such gap.
    Operators with a real internal DNS name can set HQ_ALLOW_REMOTE_BACKEND=1
    and accept that risk knowingly.
    """
    import ipaddress
    u = (u or '').strip()
    if not u:
        return False, 'base_url is required'
    if len(u) > 300:
        return False, 'base_url too long'
    try:
        p = urllib.parse.urlsplit(u)
    except Exception:
        return False, 'unparseable base_url'
    if p.scheme not in ('http', 'https'):
        return False, 'base_url must be http or https'
    if p.username or p.password:
        return False, 'base_url must not contain credentials'
    if p.query or p.fragment:
        return False, 'base_url must not contain a query or fragment'
    if '..' in p.path:
        return False, 'base_url path must not contain ".."'
    if not re.fullmatch(r'(/[\w\-.]+)*/?', p.path or ''):
        return False, 'base_url has an unexpected path'
    host = p.hostname
    if not host:
        return False, 'base_url has no host'
    if os.environ.get('HQ_ALLOW_REMOTE_BACKEND', '').strip() == '1':
        return True, ''
    # IP literal (or the resolver-fixed name 'localhost') ONLY — this is the line
    # that actually closes DNS rebinding, and the docstring above promises it. We
    # validate here at WRITE time, but hermes re-resolves the stored base_url at
    # CALL time, so any real DNS name that passes now can point at 169.254.169.254
    # (or an internal service) a second later. An IP literal can't drift;
    # 'localhost' is resolver-pinned to loopback. A genuine internal DNS name
    # needs HQ_ALLOW_REMOTE_BACKEND=1 (above), accepting that risk knowingly.
    # ipaddress.ip_address() is also strict, so it rejects int/octal/hex-encoded
    # hosts (e.g. http://2130706433/) that getaddrinfo would otherwise accept.
    if host != 'localhost':
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return False, ('base_url host must be an IP literal or "localhost" — a DNS '
                           'name can rebind between validation and use (set '
                           'HQ_ALLOW_REMOTE_BACKEND=1 to allow a hostname)')
    try:
        infos = socket.getaddrinfo(host, p.port or (443 if p.scheme == 'https' else 80),
                                   proto=socket.IPPROTO_TCP)
    except Exception:
        return False, 'could not resolve %s' % host
    addrs = {i[4][0] for i in infos}
    if not addrs:
        return False, 'could not resolve %s' % host
    for a in addrs:
        try:
            ip = ipaddress.ip_address(a)
        except ValueError:
            return False, 'unexpected address for %s' % host
        # link-local (169.254/16, fe80::/10) covers the cloud metadata endpoint,
        # which some definitions call "private" — it must never be reachable.
        if ip.is_link_local:
            return False, 'link-local addresses are not allowed'
        if not (ip.is_private or ip.is_loopback):
            return False, ('%s resolves to the public address %s — a local backend must be '
                           'on private or loopback space (set HQ_ALLOW_REMOTE_BACKEND=1 to '
                           'override)' % (host, a))
    return True, ''


def _trial_state():
    """{'active': bool, 'provider': str} — read fresh so a BYOK clear takes effect
    without a restart. The operator can also kill the shared trial network-wide
    (trialBrain.enabled=false) — that override wins over the local marker."""
    try:
        with open(os.path.join(_hermes_home(), 'trial.json'), 'r', encoding='utf-8') as f:
            d = json.load(f)
        active = bool(d.get('active'))
        provider = str(d.get('provider') or '')
    except Exception:
        active, provider = False, ''
    if active:
        op = _operator_config().get('trialBrain') or {}
        if op.get('enabled') is False:
            active = False   # operator kill switch
    return {'active': active, 'provider': provider}


def _trial_deactivate():
    """Called when the user brings their own key — the trial (and its cap) end."""
    try:
        with open(os.path.join(_hermes_home(), 'trial.json'), 'w', encoding='utf-8') as f:
            json.dump({'active': False, 'provider': ''}, f)
    except Exception:
        pass


def _trial_usage(principal):
    """Return (used_today, cap) for a principal without mutating."""
    cap = _trial_cap()
    today = time.strftime('%Y-%m-%d')
    u = _night_load('trial-usage.json', {})
    if u.get('date') != today:
        return 0, cap
    return int((u.get('counts') or {}).get(principal, 0)), cap


def _trial_check_and_bump(principal):
    """Atomically count one trial completion. Returns (allowed, used, cap):
    allowed False (over cap) means DON'T forward — surface the upsell."""
    cap = _trial_cap()
    today = time.strftime('%Y-%m-%d')
    with _trial_usage_lock:
        u = _night_load('trial-usage.json', {})
        if u.get('date') != today:
            u = {'date': today, 'counts': {}}
        counts = u.setdefault('counts', {})
        used = int(counts.get(principal, 0))
        if used >= cap:
            return False, used, cap
        counts[principal] = used + 1
        _night_save('trial-usage.json', u)
        return True, used + 1, cap


def _night_log_run(run):
    """Upsert a run record (called progressively so a crash keeps partial log)."""
    with _night_lock:
        runs = [r for r in _night_load('mission-runs.json', [])
                if r.get('id') != run.get('id')]
        runs.append(run)
        _night_save('mission-runs.json', runs[-MAX_NIGHT_RUNS_KEPT:])


def _night_browser_active():
    return (time.time() - _LAST_UI_ACTIVITY[0]) < 180


def _night_ctx():
    import night_runner as _nr
    return _nr.NightContext(
        _night_base_url[0] or ('http://127.0.0.1:%d' % PORT),
        api_key=CAFRESOHQ_API_KEY)


def _night_post_activity(run):
    """Surface a finished run on the shared activity ticker. Deferred while a
    browser is live — the app's merge-by-id load makes concurrent writes mostly
    safe, but last-writer-wins can still clobber, so we only write when nobody
    is watching. The Gazette ingests mission-runs.json regardless."""
    if _night_browser_active():
        return
    try:
        import night_runner as _nr
        ctx = _night_ctx()
        s, raw = _nr._self_call(ctx, 'GET', '/hq/state/activity')
        cur = json.loads(raw.decode('utf-8', 'replace')) if s == 200 else []
        if not isinstance(cur, list):
            cur = []
        entry = {
            'id': 'act_night_%s' % run.get('id', ''),
            'ts': int(time.time() * 1000),
            'agentId': run.get('agentId', ''), 'agentName': run.get('agentName', ''),
            'action': 'night', 'priority': 'attention', 'unread': True,
            'text': 'night shift: %d note(s) on %s' % (
                len(run.get('writes', [])), (run.get('topic') or '')[:60]),
        }
        _nr._self_call(ctx, 'PUT', '/hq/state/activity',
                       body=json.dumps([entry] + cur[:199]))
    except Exception:
        pass


def _night_run_one(sched):
    sid = sched.get('id', '')
    try:
        import night_runner as _nr
        run = _nr.run_mission(_night_ctx(), sched, on_progress=_night_log_run,
                               should_abort=lambda: sid in _night_abort)
        _night_log_run(run)
        _night_post_activity(run)
    except Exception as e:
        now_ms = int(time.time() * 1000)
        _night_log_run({
            'id': 'run_%d' % now_ms, 'scheduleId': sid,
            'agentId': sched.get('agentId', ''), 'agentName': sched.get('agentName', ''),
            'topic': sched.get('topic', ''), 'vaultFolder': sched.get('vaultFolder', ''),
            'startedAt': now_ms, 'finishedAt': now_ms, 'iterations': 0, 'writes': [],
            'tokensUsed': 0, 'errors': 1, 'lastError': str(e)[:300], 'summary': ''})
    finally:
        _night_running.pop(sid, None)
        _night_abort.discard(sid)


def _night_scan():
    now_ms = int(time.time() * 1000)
    with _night_lock:
        scheds = _night_load('scheduled-missions.json', [])
        changed = False
        for s in scheds:
            if not s.get('enabled'):
                continue
            if int(s.get('nextRunAt', 0) or 0) > now_ms:
                continue
            if _night_running:
                break   # one mission at a time — keeps provider usage sane
            sid = str(s.get('id', ''))
            _night_running[sid] = True
            s['lastRunAt'] = now_ms
            if s.get('recurrence') == 'daily':
                nxt = int(s.get('nextRunAt', now_ms) or now_ms)
                while nxt <= now_ms:
                    nxt += 86_400_000
                s['nextRunAt'] = nxt
            else:
                s['enabled'] = False
            changed = True
            threading.Thread(target=_night_run_one, args=(dict(s),),
                             daemon=True, name='night-%s' % sid).start()
        if changed:
            _night_save('scheduled-missions.json', scheds)


def _night_loop():
    while True:
        time.sleep(30)
        try:
            _night_scan()
        except Exception as e:
            print('[night] scan error:', e)


threading.Thread(target=_night_loop, daemon=True, name='night-shift').start()


# ---- Ai Cafreso Search — network worker (EXTRACTED) -------------------------
# The search-network worker (claim → Brave → LLM → graph → fulfill) and the
# gap/news/topics crons now live in search_worker_service/worker.py, run via
# docker-compose.worker.yml. It was duplicated here in-process; the two copies
# were parity-diffed before this deletion (54/63 functions byte-identical, the
# rest deliberate gateway-removal drift). Operator status moved with it:
# /gap/status and /news/status on this server proxy the worker's status
# listener (WORKER_STATUS_URL, default http://127.0.0.1:8788).
_WORKER_STATUS_URL = os.environ.get(
    'WORKER_STATUS_URL', 'http://127.0.0.1:8788').rstrip('/')


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
# By default CafresoHQ owns a plain Markdown vault under hq-state, so Obsidian is
# optional instead of required for notes to work.
_default_vault_root = _hq_state_dir / 'vault'
_vault_root     = os.environ.get('CAFRESOHQ_VAULT', str(_default_vault_root)).strip()
# Every backend PUT /vault/note can dispatch to. One tuple, because
# /vault/configure used to keep its own shorter copy — it accepted 'fs' and
# 'rest' and answered `bad backend: oci` to the one backend a fleet office
# actually runs on, which made Connections a door a fleet boss could leave
# through but not come back in by.
_VAULT_BACKENDS = ('fs', 'rest', 'oci')
_vault_backend  = os.environ.get('CAFRESOHQ_VAULT_BACKEND', 'fs').strip() or 'fs'
_vault_rest_url = os.environ.get('CAFRESOHQ_OBSIDIAN_URL', 'https://127.0.0.1:27124').strip()
_vault_rest_key = os.environ.get('CAFRESOHQ_OBSIDIAN_KEY', '').strip()

# ── OCI Object Storage vault config (CAFRESOHQ_VAULT_BACKEND=oci) ─────────────
# Used by OCI Fleet containers.  serve.py never reads ~/.oci/config on its own;
# the Container Instance's instance-principal auth or a mounted config file
# provides credentials.  All three vars must be set for OCI vault to work.
_oci_vault_namespace = os.environ.get('OCI_VAULT_NAMESPACE', '').strip()
_oci_vault_bucket    = os.environ.get('OCI_VAULT_BUCKET', 'cafresohq-fleet-vault').strip()
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
                        '(or pip install -r docker/requirements-serve.txt)')
    return _oci_client_obj

def _oci_obj_key(rel: str) -> str:
    """Build the full OCI Object key for a vault-relative path."""
    prefix = (_oci_vault_prefix.rstrip('/') + '/') if _oci_vault_prefix else ''
    return prefix + rel.lstrip('/')

# Fleet identity (set by fleet-manager when provisioning the container)
_fleet_mode      = os.environ.get('CAFRESOHQ_FLEET_MODE', 'local').strip()
_fleet_user_principal = os.environ.get('USER_PRINCIPAL', '').strip()

# Uptime tracking for /health
_server_start_time = time.time()

if not os.environ.get('CAFRESOHQ_VAULT'):
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


# Every extension the Library's editor can actually open. One set, read by
# all three doors that answer "what is in the Library" — /vault/list decides
# `isBinary` from it, /vault/search decides what it can read, /vault/file
# decides what it will hand back raw. They disagreed before: the list globbed
# '*.md', search globbed '*.md' plus '*.html', and a boss who uploaded a page
# got a search hit for a file the list said did not exist.
#
# `.html` is on this list because the Library previews it in a sandboxed
# srcDoc iframe with no allow-same-origin (views/vault.jsx HtmlFramePreview),
# never at the office's own origin. `.svg` is deliberately NOT — it is markup
# that can carry script, and its only reader would be an <img> tag.
_VAULT_TEXT_EXT = frozenset({
    '.md', '.markdown', '.txt', '.html', '.htm', '.csv', '.json',
    '.yml', '.yaml', '.xml', '.log', '.base',
})


def _vault_entry(rel: str, mtime: int, size: int) -> dict:
    """One row of /vault/list, for any backend.

    `isBinary` is the flag the Library view reads to decide whether a file
    goes to the editor or to the download door — the view has handled it
    since the encrypted-bridge vault started sending it, and no server
    backend ever did, because no server backend listed anything but '*.md'.

    The extension stays in the title for everything the editor cannot open:
    "q3-board-deck" and "q3-board-deck.pptx" are different promises, and
    only one of them is a deck.
    """
    name = rel.rsplit('/', 1)[-1]
    ext = pathlib.PurePosixPath(name).suffix.lower()
    return {
        'path': rel,
        'title': name[:-3] if ext == '.md' else name,
        'mtime': mtime,
        'size': size,
        'isBinary': ext not in _VAULT_TEXT_EXT,
    }


def _vault_search_hit(rel: str, text: str, ql: str, query: str):
    """Score one candidate for /vault/search, or None. Shared by every
    backend arm (fs, oci) so the scoring/snippet logic can't drift between
    them the way the fs arm's copy used to sit alone, unreachable for a
    backend that fell through to it by accident instead of by name."""
    stem = pathlib.PurePosixPath(rel).stem
    tl = text.lower()
    title_score = 3 if ql in stem.lower() else 0
    count = tl.count(ql)
    if not (title_score or count):
        return None
    idx = tl.find(ql)
    snippet = ''
    if idx >= 0:
        s = max(0, idx - 60)
        e = min(len(text), idx + len(query) + 60)
        snippet = ('…' if s > 0 else '') + text[s:e].replace('\n', ' ').strip() + ('…' if e < len(text) else '')
    return {'path': rel, 'title': stem, 'score': title_score + count, 'snippet': snippet}


def _oci_vault_search(query: str, ql: str, limit: int) -> dict:
    """/vault/search's OCI arm, factored out so it's callable (and testable)
    without a running server — one list_objects call to enumerate the
    bucket's text-like objects, one get_object per candidate, scored with
    the exact same _vault_search_hit the fs arm uses."""
    cli = _oci_object_client()
    prefix = (_oci_vault_prefix.rstrip('/') + '/') if _oci_vault_prefix else ''
    resp = cli.list_objects(
        _oci_vault_namespace, _oci_vault_bucket,
        prefix=prefix, fields='name', limit=1000)
    hits = []
    for obj in resp.data.objects:
        rel = obj.name[len(prefix):] if prefix else obj.name
        if not rel or rel.endswith('/'):
            continue
        if any(part.startswith('.') for part in rel.split('/')):
            continue
        if pathlib.PurePosixPath(rel).suffix.lower() not in _VAULT_TEXT_EXT:
            continue
        try:
            content = cli.get_object(_oci_vault_namespace, _oci_vault_bucket, obj.name).data.content
        except Exception:
            continue  # listed but unreadable (e.g. raced a delete) — skip, don't fail the whole search
        hit = _vault_search_hit(rel, content.decode('utf-8', 'replace'), ql, query)
        if hit:
            hits.append(hit)
    hits.sort(key=lambda h: h['score'], reverse=True)
    return {'hits': hits[:limit], 'total': len(hits)}


# Types a browser can safely render in place. Everything else — decks,
# documents, archives, and anything unrecognised — is handed back as an
# attachment, so a filed .html or .svg can never execute at the office's
# own origin with the office's own cookies.
_VAULT_INLINE_PREFIXES = ('image/', 'audio/', 'video/')


def _vault_inline_ok(mime: str) -> bool:
    if mime == 'image/svg+xml':
        return False
    return mime == 'application/pdf' or mime.startswith(_VAULT_INLINE_PREFIXES)


def _vault_hidden_part(rel: str):
    """The first path segment that would make this file invisible, or None.

    Every backend's listing skips dotted parts — the fs and oci branches
    filter `part.startswith('.')` outright, and the REST walk skips
    dot-entries at every level — so a WRITE to such a path files a note the
    Library can never show. The office would say "Saved" about a file that
    has just left every list it keeps (#136 was this disappearance at the
    upload door; #137 made that door refuse hidden files out loud for
    exactly this reason). The write doors ask this before touching any
    backend; read, delete and rename-FROM stay open, because a file that is
    ALREADY invisible needs a way back out — rescuing `.lost/plan.md` to
    `plan.md` is the one move that fixes the situation instead of filing
    another copy of it.

    '..' is deliberately not treated as hidden: it is a traversal attempt,
    `_vault_resolve` already refuses it as one, and calling it "hidden"
    would send the boss to rename a file that was never the problem."""
    for part in str(rel or '').replace('\\', '/').split('/'):
        part = part.strip()
        if part in ('', '.', '..'):
            continue
        if part.startswith('.'):
            return part
    return None


def _vault_resolve(rel: str) -> pathlib.Path:
    """Resolve `rel` (e.g. "Daily/2026-04-25.md") under the vault directory with
    traversal protection. Raises ValueError if escape is attempted or unset."""
    if not _vault_root:
        raise ValueError('vault directory not configured')
    root = pathlib.Path(_vault_root).resolve()
    if not root.is_dir():
        raise ValueError(f'vault directory does not exist: {root}')
    rel = rel.lstrip('/').replace('\\', '/')
    # Bare slugs ("Research/topic") are the common case and rely on this
    # default. A path that already carries a REAL extension must keep it —
    # this used to force '.md' onto anything not already ending in '.md',
    # so buildDelivery()'s `Sites/<slug>.html` (app/artifacts.jsx — "html is
    # written raw so it renders when opened") landed on disk as
    # `Sites/<slug>.html.md`. That is the ONE deliverable format the whole
    # north-star front door produces (the "Simple page" starter task, one of
    # exactly three — 08-north-star-real-product.md §3.6): a fresh install,
    # a first task, "a real artifact lands in your vault" — and the artifact
    # that landed could never be opened as a page, by this app or anything
    # else, and the server's own /vault/search (`root.rglob('*.md')`) could
    # never find it either. `.suffix` only sees the FINAL path segment, so a
    # dotted folder name earlier in the path (`v1.2/notes`) is untouched.
    if not pathlib.PurePosixPath(rel).suffix:
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
                      content_type: str = 'application/json',
                      timeout: float = 30):
    """Forward a request to the Obsidian Local REST API plugin. Returns
    (status, headers_list, body_bytes). Raises ValueError if not configured.
    Tolerates self-signed HTTPS certs (the plugin's default).

    `timeout` defaults to the 30s every caller used before it existed. Doors
    where the answer is advisory rather than the work pass something short —
    a reachability probe must never take longer than the thing it advises."""
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
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request(method, upstream_path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.getheaders(), resp.read()
    finally:
        conn.close()


# ---- Can a note land? -------------------------------------------------------
# The office's one answer to that, at module scope because more than one door
# needs it and a second copy is how the first one goes stale. GET /vault/status
# publishes it; the night-shift schedule door reads it to decide whether a
# confirmation is the whole truth.
#
# What a boss set up at 9pm can be down at 1am, so this is never the last word
# — night_runner asks again at the run door, and the write itself owns the
# failures no probe can see. It is the earliest honest word, not the final one.

# One sentence for the save door, and it names the screen the run door names.
# Not the same words as night_runner.vault_refused_sentence: nothing has been
# refused here and the schedule IS saved, so a sentence about a failed write
# would be a different kind of lie. Same door, different moment.
NO_VAULT_AT_SAVE = 'no vault to file into yet — check Connections'


def _vault_readiness(probe_timeout: float = 30):
    """What the office knows right now about whether a note can land.

    `probe_timeout` is for doors where this answer is advisory rather than
    the work: the Obsidian probe is a network call, and a save must not wait
    30s to decorate its own confirmation. `unanswered` reports that the probe
    ran out of time rather than came back negative — a caller adding a
    warning must not add one on the strength of a question nobody answered.
    """
    if _vault_backend == 'fs' and _vault_root:
        try:
            pathlib.Path(_vault_root).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    fs_ok = bool(_vault_root) and pathlib.Path(_vault_root).is_dir()
    rest_ok = False
    rest_detail = ''
    unanswered = False
    if _vault_rest_url and _vault_rest_key:
        try:
            s, _h, _b = _obsidian_request('GET', '/', timeout=probe_timeout)
            rest_ok = (s == 200)
            rest_detail = '' if rest_ok else 'http %d' % s
        except (socket.timeout, TimeoutError) as e:
            # Ran out of time, which is not the same fact as "shut". A
            # refused connection comes back instantly and lands below.
            rest_detail, unanswered = str(e)[:120] or 'timed out', True
        except Exception as e:
            rest_detail = str(e)[:120]
    # Presence, not a probe: naming a bucket is this backend's equivalent of
    # the fs arm's is_dir(), and it is what tells a provisioned fleet
    # container apart from one nobody set up. The honest reasons a named
    # bucket still refuses — no SDK, IAM not ready, wrong prefix — come back
    # from the write itself as a 502 that says so. A real reachability probe
    # here would build the OCI client on a polled endpoint and can hang on
    # IMDS (see _oci_object_client), which is a worse answer than an
    # optimistic one.
    oci_ok = bool(_oci_vault_namespace and _oci_vault_bucket)
    # One row per backend PUT /vault/note can dispatch to. Written as a table
    # because the two-arm boolean this replaces silently answered False for
    # 'oci' — a fleet container's vault worked at the write door and read as
    # "no vault" at every door that asks first: the coworker cards, the tool
    # grant, and (since the night-shift pre-flight) every night shift,
    # cancelled before it started. A missing row is still False, so the suite
    # walks the write handler's arms and requires each one to appear here.
    backend_ready = {'fs': fs_ok, 'rest': rest_ok, 'oci': oci_ok}
    return {
        'configured': backend_ready.get(_vault_backend, False),
        'fsExists': fs_ok,
        'restReachable': rest_ok,
        'restDetail': rest_detail,
        'ociBucket': _oci_vault_bucket if oci_ok else '',
        'unanswered': unanswered,
    }


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
            elif not entry.startswith('.'):
                # Plugin's listing doesn't include mtime/size in the simple list;
                # fetch a stat-like via the file endpoint headers if needed. For
                # speed we just stub them. The graph + browse views still work.
                #
                # Attachments included. An Obsidian vault holds its images and
                # PDFs alongside the notes that embed them, and this walk used
                # to drop every one of them — so a boss on the REST backend saw
                # a Library missing exactly the files Obsidian itself shows.
                out.append(_vault_entry(full, 0, 0))
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
# ---- Knowledge-graph builder (extracted) ------------------------------------
# The vault concept-graph builders live in kg_builder.py now. init() hands it
# the runtime-mutable config as callables (the vault root can be changed from
# the UI's vault settings, so a snapshot would go stale).
import kg_builder
from kg_builder import _build_graph_fs_cached, _build_graph_rest, _build_graph_oci_cached
kg_builder.init(vault_root=lambda: _vault_root,
                state_dir=lambda: _hq_state_dir,
                memory_dir=lambda: _hq_memory_dir,
                obsidian_request=_obsidian_request,
                oci_client=_oci_object_client,
                oci_namespace=lambda: _oci_vault_namespace,
                oci_bucket=lambda: _oci_vault_bucket,
                oci_prefix=lambda: _oci_vault_prefix)



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

    # RFC 6455 WebSocket handshake magic GUID — concatenated with the client's
    # Sec-WebSocket-Key and SHA-1'd to form Sec-WebSocket-Accept. Used by the
    # /terminal/pty upgrade handler.
    _WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

    def end_headers(self):
        # Disable caching for local-dev iteration so HTML/JSX edits land on
        # next reload without browser caching tripping us up.
        self.send_header('Cache-Control', 'no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        # CORS — only ALLOWLISTED app origins (the SvelteKit frontend + canister
        # UI shell, see _app_origins) get credentialed cross-origin access. Any
        # other origin gets a credential-less '*' (a browser cannot send cookies
        # with ACAO:'*'), so a malicious site can't read this container's
        # cookie-authenticated responses cross-origin (the hq_session is
        # SameSite=None, so it WOULD otherwise ride along). Public probes like
        # /health still work for anyone.
        try:
            origin  = self.headers.get('Origin', '') if hasattr(self, 'headers') else ''
            allowed = bool(origin) and origin in self._app_origins()
        except Exception:
            origin, allowed = '', False
        if allowed:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Credentials', 'true')
        else:
            self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers',
                         'Content-Type, Authorization, X-User-Principal, X-API-Key, '
                         'anthropic-version, x-api-key, X-Vault-Format, X-Brave-Key')
        self.send_header('Access-Control-Max-Age', '86400')
        self.send_header('Vary', 'Origin')
        super().end_headers()

    def _route(self):
        for prefix, target in ROUTES.items():
            if self.path.startswith(prefix):
                return prefix, target
        return None, None

    def _api_key_ok(self):
        """Bearer-key gate (see CAFRESOHQ_API_KEY). A request to a protected
        prefix must present the key via the X-API-Key header or a ?k= query param
        (for WebSocket handshakes). Public paths (static UI, /health, /idle) are
        exempt.

        With no key configured the protected prefixes are restricted to LOOPBACK
        callers rather than opened to everyone. These routes are RCE- and
        write-equivalent (/tools/exec runs a shell, /terminal spawns a PTY), so
        an unset key must not mean "anyone on the network may run commands" — the
        common case of binding 0.0.0.0 on a shared or café LAN would otherwise
        hand the host to any peer. Loopback stays open so local development needs
        no configuration."""
        path = self.path.split('?', 1)[0]
        if not path.startswith(_KEY_PROTECTED_PREFIXES):
            return True
        if not CAFRESOHQ_API_KEY:
            try:
                peer = (self.client_address[0] or '').strip()
            except Exception:
                return False
            return peer in ('127.0.0.1', '::1', '::ffff:127.0.0.1')
        supplied = self.headers.get('X-API-Key', '') or ''
        if not supplied and 'websocket' in (
                self.headers.get('Upgrade', '') or '').lower():
            # Only a WebSocket handshake may pass the key in the query string —
            # the browser API can't set headers there. Everywhere else a ?k= is
            # refused, because query strings leak into access logs, proxy logs
            # and the Referer of any resource the page loads.
            try:
                supplied = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query).get('k', [''])[0]
            except Exception:
                supplied = ''
        import hmac as _hmac
        return bool(supplied) and _hmac.compare_digest(str(supplied), CAFRESOHQ_API_KEY)

    def _site_sandbox_ok(self):
        """True when the keyless /fs/site preview may use the relaxed local-mode
        path rules: the caller is on loopback, so no remote party can reach it."""
        try:
            peer = (self.client_address[0] or '').strip()
        except Exception:
            return False
        return peer in ('127.0.0.1', '::1', '::ffff:127.0.0.1')

    def do_GET(self):
        if not self._api_key_ok():
            return self._send_json(401, {'error': 'API key required'})
        # /idle is the signal the fleet's reap-idle uses to stop idle containers
        # (free the A1 pool + pause billing). Report seconds since the last
        # *user-facing* request. Health/idle pings themselves don't count as
        # activity (they'd keep a container "busy" forever).
        if self.path == '/idle':
            import time as _t
            return self._send_json(200, {'idle_seconds': int(_t.time() - _LAST_ACTIVITY[0])})
        _touch_activity(self.path)
        # Track REAL browser traffic separately (the night runner self-calls
        # tag themselves) — _night_post_activity defers shared-file writes
        # while a session is live.
        # Only genuine browser traffic marks a live UI session. /health is
        # excluded: load-balancer probes (docker-compose curls it every 30s)
        # would otherwise keep _night_browser_active() true forever and
        # permanently suppress the night-shift ticker entry.
        if 'X-Night-Runner' not in self.headers and self.path.startswith(('/hq/', '/vault/')):
            _LAST_UI_ACTIVITY[0] = time.time()
        if self.path == '/health':
            return self._health()
        if self.path == '/market/quotes':
            return self._market_quotes()
        if self.path.startswith('/hq/'):
            return self._hq_handler('GET')
        if self.path == '/missions/scheduled':
            return self._missions_scheduled_get()
        if self.path == '/missions/runs':
            return self._missions_runs()
        if self.path in ('/gap/status', '/news/status'):
            return self._cron_status_proxy()
        if self.path.startswith('/brave/'):
            return self._brave_search()
        if self.path == '/hermes/capability':
            return self._hermes_get_capability()
        if self.path == '/hermes/model':
            return self._hermes_get_model()
        if self.path == '/hermes/provider':
            return self._hermes_get_provider()
        if self.path.split('?')[0] == '/hermes/local-models':
            return self._hermes_local_models(
                self.path.split('?', 1)[1] if '?' in self.path else '')
        if self.path == '/hermes/config/export':
            return self._hermes_export_config()
        if self.path == '/hermes/trial-status':
            return self._hermes_trial_status()
        if self.path.startswith('/hermes/'):
            return self._hermes_proxy('GET')
        if self.path.startswith('/vault/'):
            return self._vault('GET')
        if self.path == '/claudecode/status':
            return self._claudecode_status()
        if self.path == '/cafresohq/status':
            return self._cafresohq_status()
        if self.path == '/codex/status':
            return self._codex_status()
        if self.path.startswith('/agents/install/status'):
            return self._agents_install_status()
        if self.path == '/agents':
            return self._agents_status()
        if self.path.split('?')[0] == '/agent/drivers':
            return self._agent_drivers()
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
        if self.path.startswith('/fs/collect'):
            return self._fs_collect()
        if self.path.startswith('/fs/site/'):
            return self._fs_site()
        if self.path.startswith('/fs/stat'):
            return self._fs_stat()
        if self.path.startswith('/fs/file'):
            return self._fs_file()
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
        if self.path.startswith('/bundle/'):
            return self._serve_bundle()
        _p0 = self.path.split('?', 1)[0]
        if _p0 in ('/', '/hq.html', '/index.html'):
            return self._serve_hq_html()
        if _p0 == '/favicon.ico':
            # Browsers request this path unconditionally, whatever <link
            # rel=icon> declares — without a route it 404'd on every boot
            # (log noise + a console error in devtools).
            return self._serve_cwd_file(os.path.join('assets', 'favicon-32.png'), 'image/png')
        if _p0 == '/graph-viewer.html':
            return self._serve_cwd_file('graph-viewer.html', 'text/html; charset=utf-8')
        if _p0 == '/graph-viewer.js':
            return self._serve_dist_file('graph-viewer.js', 'application/javascript; charset=utf-8')
        if _p0.startswith('/graph/snapshot/'):
            return self._graph_snapshot(_p0.rsplit('/', 1)[-1])
        prefix, target = self._route()
        if target:
            return self._proxy('GET', prefix, target)
        # Static fallthrough serves legit UI assets (styles.css, sw.js,
        # manifest, assets/*, dist-ui) from cwd — but SimpleHTTPRequestHandler
        # would otherwise hand out ANYTHING under the repo root, incl. the TLS
        # private key + vault under hq-state/ and the .py source. Gate it.
        if not self._static_path_allowed(_p0):
            return self.send_error(404, 'Not found')
        return super().do_GET()

    # Static assets that legitimately live at the web root; everything else
    # under cwd (state dir, TLS key, vault, source) is off-limits to the
    # SimpleHTTPRequestHandler fallthrough regardless of the API key.
    def _static_path_allowed(self, url_path):
        try:
            rel = urllib.parse.unquote(url_path.split('?', 1)[0]).lstrip('/')
            root = os.path.realpath(os.getcwd())
            resolved = os.path.realpath(os.path.join(root, rel))
            # (a) must stay inside the web root
            if resolved != root and not resolved.startswith(root + os.sep):
                return False
            # (b) never serve Python source
            if resolved.endswith('.py'):
                return False
            # (c) never serve the state dir (tls/, vault/, memory/, *.json)
            state_root = os.path.realpath(str(_hq_state_dir))
            if resolved == state_root or resolved.startswith(state_root + os.sep):
                return False
            return True
        except Exception:
            return False

    # No directory listings — hq-state/ etc. must not be enumerable.
    def list_directory(self, path):
        self.send_error(404, 'Not found')
        return None

    # --- HQ UI build (no in-browser Babel) ------------------------------------
    # STALENESS. hq.html loads dist-ui/, built by scripts/build_ui_bundle.mjs,
    # and this server never rebuilds it. So editing a .jsx and reloading the
    # page exercises the LAST build, silently: the corrected file is served
    # correctly over HTTP with Cache-Control: no-store, and nothing loads it.
    # Measured 2026-08-14 — a fix verified in the browser reported the old
    # behaviour for eight tool calls before anyone thought to check the
    # manifest's mtime.
    #
    # The dependency set is every .jsx, not the thirteen the builder names.
    # Those thirteen (APP_FILES) are barrels; 45 of the 58 .jsx files in the
    # tree are reached only through their imports, which is why the builder's
    # own --watch mode also misses them (fixed there too).
    # The HQ app is built into dist-ui/ by scripts/build_ui_bundle.mjs: vendor
    # globals (React/ReactDOM/xterm) + content-hashed, pre-transformed JSX. hq.html
    # carries an <!--HQ_SCRIPTS--> placeholder; we substitute it from the manifest.
    # (Mirrors scripts/ui_manifest.py — inlined so the packaged/frozen build needs
    # no scripts/ dir alongside the exe.)
    def _hq_manifest_tags(self):
        import json as _json
        with open(os.path.join(os.getcwd(), 'dist-ui', 'manifest.json'), encoding='utf-8') as fh:
            m = _json.load(fh)
        parts = []
        for css in m.get('vendorCss', []):
            parts.append('<link rel="stylesheet" href="%s"/>' % css)
        for js in m.get('vendor', []):
            parts.append('<script src="%s"></script>' % js)
        if m.get('analyticsWorker'):
            parts.append('<script>window.__CAFRESO_BUNDLE__=%s;</script>'
                         % _json.dumps({'analyticsWorker': m['analyticsWorker']}))
        parts.append('<script>window._TERMINAL_CWD=%s;</script>'
                     % _json.dumps(_cafresohq_terminal_cwd))
        if m.get('graphEngine'):
            parts.append('<script src="%s"></script>' % m['graphEngine'])
        for js in m.get('app', []):
            parts.append('<script src="%s"></script>' % js)
        return '\n'.join(parts)

    def _serve_hq_html(self):
        try:
            with open(os.path.join(os.getcwd(), 'hq.html'), encoding='utf-8') as fh:
                html = fh.read()
            html = html.replace('<!--HQ_SCRIPTS-->', self._hq_manifest_tags())
            # A stale bundle is invisible from the browser and looks exactly
            # like a fix that did not work — the corrected .jsx is even
            # served correctly over HTTP, because nothing loads it. Said
            # where the confusion happens rather than only in the log.
            stale = _ui_bundle_stale()
            if stale:
                html = html.replace('</body>',
                    '<script>console.warn(%s);</script>\n</body>'
                    % json.dumps(_ui_stale_sentence(stale)))
        except Exception as e:
            return self.send_error(500, 'HQ UI not built: %s (run `npm run build`)' % e)
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _serve_bundle(self):
        rel = self.path.split('?', 1)[0].lstrip('/')          # 'bundle/app-<hash>.js'
        base = os.path.normpath(os.path.join(os.getcwd(), 'dist-ui'))
        full = os.path.normpath(os.path.join(base, rel))
        if not full.startswith(base) or not os.path.isfile(full):
            return self.send_error(404)
        ctype = ('application/javascript' if full.endswith('.js')
                 else 'text/css' if full.endswith('.css')
                 else 'application/octet-stream')
        with open(full, 'rb') as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    # --- Public shareable graphs (Phase 2) ------------------------------------
    # Publish exports a laid-out snapshot (positions + community + betweenness) and
    # stores it under hq-state/public-graphs/<slug>.json; the static graph-viewer
    # renders it read-only via ?g=/graph/snapshot/<slug>. (Production target is an
    # ICP asset/Motoko canister — same URL contract, swappable storage.)
    def _public_graph_dir(self):
        base = os.environ.get('CAFRESOHQ_HQ_STATE_DIR') or os.path.join(os.getcwd(), 'hq-state')
        d = os.path.join(base, 'public-graphs')
        os.makedirs(d, exist_ok=True)
        return d

    def _serve_cwd_file(self, name, ctype):
        try:
            with open(os.path.join(os.getcwd(), name), 'rb') as fh:
                data = fh.read()
        except Exception:
            return self.send_error(404)
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        try: self.wfile.write(data)
        except Exception: pass

    def _serve_dist_file(self, name, ctype):
        full = os.path.normpath(os.path.join(os.getcwd(), 'dist-ui', name))
        if not os.path.isfile(full):
            return self.send_error(404)
        with open(full, 'rb') as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        try: self.wfile.write(data)
        except Exception: pass

    def _graph_snapshot(self, slug):
        import re as _re
        if not _re.fullmatch(r'[A-Za-z0-9_-]{1,64}', slug or ''):
            return self.send_error(404)
        full = os.path.join(self._public_graph_dir(), slug + '.json')
        if not os.path.isfile(full):
            return self.send_error(404)
        with open(full, 'rb') as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        try: self.wfile.write(data)
        except Exception: pass

    def _graph_publish(self):
        import json as _json, secrets as _secrets
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length else b'{}'
            payload = _json.loads(body.decode('utf-8'))
        except Exception:
            return self._send_json(400, {'error': 'bad payload'})
        if not isinstance(payload, dict) or 'graph' not in payload:
            return self._send_json(400, {'error': 'missing graph'})
        slug = _secrets.token_hex(6)
        try:
            with open(os.path.join(self._public_graph_dir(), slug + '.json'), 'w', encoding='utf-8') as fh:
                _json.dump(payload, fh)
        except Exception as e:
            return self._send_json(500, {'error': str(e)})
        snap_url = '/graph/snapshot/' + slug
        view_url = '/graph-viewer.html?g=' + snap_url + '&background=dark&most_influential=bc&maxnodes=150&show_analytics=1&selected=highlight&demo=1'
        return self._send_json(200, {'slug': slug, 'snapshotUrl': snap_url, 'viewerUrl': view_url})

    def do_POST(self):
        if not self._api_key_ok():
            return self._send_json(401, {'error': 'API key required'})
        _touch_activity(self.path)
        if self.path == '/hermes/capability':
            return self._hermes_set_capability()
        if self.path == '/hermes/model':
            return self._hermes_set_model()
        if self.path == '/hermes/provider':
            return self._hermes_set_provider()
        if self.path == '/hermes/config/import':
            return self._hermes_import_config()
        if self.path == '/hermes/openrouter-key':
            return self._hermes_set_provider('openrouter')  # back-compat alias
        if self.path.startswith('/hermes/'):
            return self._hermes_proxy('POST')
        if self.path.startswith('/vault/'):
            return self._vault('POST')
        if self.path == '/graph/publish':
            return self._graph_publish()
        if self.path == '/agents/install':
            return self._agents_install()
        if self.path == '/claudecode/configure':
            return self._claudecode_configure()
        if self.path == '/codex/configure':
            return self._codex_configure()
        if self.path == '/agent/stream':
            return self._agent_stream()
        if self.path == '/claudecode/stream':
            return self._claudecode_stream()
        if self.path == '/cafresohq/stream':
            return self._cafresohq_stream()
        if self.path == '/codex/stream':
            return self._codex_stream()
        if self.path == '/terminal/stream':
            return self._terminal_stream()
        if self.path == '/projects/clone':
            return self._projects_clone()
        if self.path == '/missions/schedule':
            return self._missions_schedule()
        if self.path == '/tools/exec':
            return self._tool_exec()
        if self.path.startswith('/fs/upload'):
            return self._fs_upload()
        if self.path.startswith('/fs/mkdir'):
            return self._fs_mkdir()
        if self.path.startswith('/fs/rename'):
            return self._fs_rename()
        if self.path.startswith('/fs/delete'):
            return self._fs_delete()
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
        if not self._api_key_ok():
            return self._send_json(401, {'error': 'API key required'})
        if self.path.startswith('/hq/'):
            return self._hq_handler('PUT')
        if self.path.startswith('/vault/'):
            return self._vault('PUT')
        self.send_error(405)

    def do_DELETE(self):
        if not self._api_key_ok():
            return self._send_json(401, {'error': 'API key required'})
        if self.path.startswith('/vault/'):
            return self._vault('DELETE')
        if self.path.startswith('/missions/scheduled/'):
            return self._missions_delete()
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
        return _drivers.get('claude-code').resolve() or None

    def _market_quotes(self):
        """GET /market/quotes — cached index/gold quotes for the office ticker."""
        global _market_cache
        with _market_lock:
            if time.time() - _market_cache['ts'] < 60 and _market_cache['quotes']:
                return self._send_json(200, {'quotes': _market_cache['quotes'], 'ts': _market_cache['ts']})
        quotes = []
        for sym, yq in _MARKET_SYMBOLS:
            try:
                url = ('https://query1.finance.yahoo.com/v8/finance/chart/'
                       + urllib.parse.quote(yq) + '?range=1d&interval=1d')
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=6) as r:
                    meta = json.load(r)['chart']['result'][0]['meta']
                last = float(meta['regularMarketPrice'])
                prev = float(meta.get('chartPreviousClose') or 0)
                quotes.append({'sym': sym, 'last': last,
                               'pct': ((last - prev) / prev * 100.0) if prev > 0 else None})
            except Exception:
                continue   # partial results are fine; total failure serves stale below
        with _market_lock:
            if quotes:
                _market_cache = {'ts': time.time(), 'quotes': quotes}
            return self._send_json(200, {'quotes': _market_cache['quotes'], 'ts': _market_cache['ts']})

    def _health(self):
        """GET /health — lightweight liveness probe for load balancers and companion detection."""
        import platform
        oci_ready = (
            bool(_oci_vault_namespace and _oci_vault_bucket)
            if _vault_backend == 'oci' else None
        )
        # brain: advertises the managed default model when Cafreso provisioned
        # this HQ with a shared endpoint (LMSTUDIO_BASE_URL injected at fleet
        # provision time — see docker/hermes-bootstrap.py branch 0). The UI's
        # probeManagedBrain() reads {model, provider} to suppress the "add a
        # key" nag for zero-config users. null when no managed brain is wired.
        _lm_base = os.environ.get('LMSTUDIO_BASE_URL', '').strip()
        brain = None
        if _lm_base:
            brain = {
                'model': os.environ.get('LMSTUDIO_MODEL', '').strip() or 'local-model',
                'provider': 'cafreso',
            }
        return self._send_json(200, {
            'status':           'ok',
            'version':          '1.0.0',
            # apiVersion: integer contract between the (canister-served) UI and
            # this API. Bump on a BREAKING endpoint change; the UI min-checks it
            # so a freshly-deployed UI degrades gracefully against an older
            # container (and vice-versa) instead of hard-failing. See API_VERSION.
            'apiVersion':       API_VERSION,
            'mode':             _fleet_mode,
            # managed: True when Cafreso provisioned this container (fleet
            # mode set by fleet-manager). The premium UI reads this to show
            # plan/container status; 'local' self-hosts report False.
            'managed':          _fleet_mode not in ('', 'local'),
            'vault_backend':    _vault_backend,
            'uptime_seconds':   int(time.time() - _server_start_time),
            'platform':         platform.system(),
            'user_principal':   _fleet_user_principal,
            'claude_code':      bool(self._claudecode_resolve()),
            'codex':            bool(self._codex_resolve()),
            'hermes':           bool(self._hermes_resolve()),
            'gemini':           bool(self._gemini_resolve()),
            'runtime_env':      _RUNTIME_ENV,
            'auth_required':    bool(CAFRESOHQ_API_KEY),
            'oci_vault_ready':  oci_ready,
            'brain':            brain,
        })

    def _claudecode_status(self):
        drv = _drivers.get('claude-code')
        bin_ = drv.resolve()
        return self._send_json(200, {
            'configured': bool(bin_),
            'binary': bin_ or '',
            'override': drv.binary_override or '',
        })

    def _claudecode_configure(self):
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})
        try:
            _drivers.get('claude-code').configure({'binary': body.get('binary')})
        except _DriverError as e:
            return self._send_json(e.status, {'error': str(e)})
        return self._claudecode_status()

    def _claudecode_stream(self):
        """Stream a chat completion through the claude-code driver (tools
        DISABLED). Legacy route: output keeps the OpenAI-compat SSE delta
        shape claude-client.jsx already parses. New clients should use
        POST /agent/stream and consume contract events directly.
        Body: {messages, system, model, cwd?}
        """
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})
        task = {
            'messages': body.get('messages') or [],
            'system':   (body.get('system') or '').strip(),
            'model':    (body.get('model') or '').strip(),
            'cwd':      self._agent_task_cwd(body),
        }
        return self._agent_stream_legacy('claude-code', task, 'Claude Code')

    # ---- Agent driver surface (docs/DRIVER_CONTRACT.md) -------------------
    def _agent_task_cwd(self, body):
        """Working dir for an agent task: the client-requested cwd when it
        falls inside an allowed dir and exists, else the first allowed dir.
        (Shared by every agent stream route — was duplicated per-route.)"""
        cwd = _cafresohq_allowed_dirs[0] if _cafresohq_allowed_dirs else None
        req_cwd = (body.get('cwd') or '').strip()
        if req_cwd:
            try:
                cwd_p = pathlib.Path(_client_path(req_cwd)).resolve()
                for d in _cafresohq_allowed_dirs:
                    try:
                        cwd_p.relative_to(pathlib.Path(d).resolve())
                        if cwd_p.is_dir():
                            cwd = str(cwd_p)
                        break
                    except ValueError:
                        continue
            except OSError:
                pass
        return cwd

    def _agent_drivers(self):
        """GET /agent/drivers[?probe=1] — every registered driver's manifest +
        live detection, the data the front desk turns into hireable coworkers.

        probe=1 runs the deep detection (CLI --version spawns, local-daemon
        /models liveness) CONCURRENTLY — needed because http drivers report
        installed:true from their hard-coded default base URL alone; only
        detect.version ('reachable') proves a local daemon is actually up.
        Without probe the response is cheap file/PATH checks only."""
        probe = 'probe=1' in (self.path.split('?', 1)[1] if '?' in self.path else '')
        drivers = list(_drivers.DRIVERS.values())
        if probe:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(drivers)) as ex:
                futs = {drv.MANIFEST['id']: ex.submit(drv.detect, True)
                        for drv in drivers}
                detects = {}
                for did, f in futs.items():
                    try:
                        detects[did] = f.result(timeout=10)
                    except Exception:
                        detects[did] = {'installed': False, 'authenticated': False,
                                        'auth': '', 'version': '', 'detail': ''}
        else:
            detects = {drv.MANIFEST['id']: drv.detect(probe_version=False)
                       for drv in drivers}
        out = []
        for drv in drivers:
            d = dict(drv.MANIFEST)
            d['detect'] = detects[d['id']]
            out.append(d)
        return self._send_json(200, {'drivers': out})

    def _agent_stream(self):
        """POST /agent/stream — the contract-native task route.
        Body: {driver?, prompt|messages, system?, model?, cwd?, tools?,
        agentName?}. SSE where each data: frame is ONE contract event
        (schema in drivers/base.py). tools:true binds the task to the
        server-side CAFRESOHQ_ALLOWED_TOOLS/DIRS allowlists — the client
        can request tools but can never name tools or widen dirs."""
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})
        drv = _drivers.get(body.get('driver') or 'claude-code')
        if drv is None:
            return self._send_json(400, {'error': 'unknown driver'})
        task = {
            'prompt':    body.get('prompt') or '',
            'messages':  body.get('messages') or [],
            'system':    (body.get('system') or '').strip(),
            'model':     (body.get('model') or '').strip(),
            'cwd':       self._agent_task_cwd(body),
            'agentName': (body.get('agentName') or '').strip()[:60],
        }
        try:
            max_toks = int(body.get('maxTokens') or 0)
        except (TypeError, ValueError):
            max_toks = 0
        if max_toks > 0:
            task['limits'] = {'maxTokens': min(max_toks, 131072)}
        if body.get('tools'):
            if not (_cafresohq_allowed_dirs and _cafresohq_allowed_tools):
                return self._send_json(503, {'error':
                    'tools requested but CAFRESOHQ_ALLOWED_DIRS/TOOLS not configured'})
            task['tools'] = list(_cafresohq_allowed_tools)
            task['addDirs'] = list(_cafresohq_allowed_dirs)
        try:
            handle = drv.start_task(task)
        except _DriverError as e:
            return self._send_json(e.status, {'error': str(e)})
        self.send_response(200)
        self.send_header('content-type', 'text/event-stream')
        self.send_header('cache-control', 'no-store')
        self.end_headers()
        try:
            for ev in drv.events(handle):
                try:
                    self.wfile.write(b'data: ' + json.dumps(ev).encode('utf-8') + b'\n\n')
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
        finally:
            drv.cancel(handle)   # idempotent; reaps the subprocess

    def _agent_stream_legacy(self, driver_id, task, err_label,
                             render_tools=False, done_sentinel=False):
        """Run a task through a driver but emit the LEGACY OpenAI-compat SSE
        delta shape (/claudecode/stream, /cafresohq/stream, /codex/stream keep
        one client parser). token→delta frame, usage→final usage frame,
        error→⚠ content frame. render_tools inlines tool_call/tool_result as
        text frames (the old /codex/stream behavior); done_sentinel appends
        the data: [DONE] trailer that route's client expects."""
        drv = _drivers.get(driver_id)
        try:
            handle = drv.start_task(task)
        except _DriverError as e:
            return self._send_json(e.status, {'error': str(e)})
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

        try:
            for ev in drv.events(handle):
                et = ev['event']
                if et == 'token':
                    if not write_sse({'choices': [{'index': 0,
                                      'delta': {'content': ev['text']}}]}):
                        break
                elif et == 'usage' and (ev['inTokens'] or ev['outTokens']):
                    write_sse({'choices': [], 'usage': {
                        'prompt_tokens':     ev['inTokens'],
                        'completion_tokens': ev['outTokens'],
                        'total_tokens':      ev['inTokens'] + ev['outTokens']}})
                elif et == 'error':
                    write_sse({'choices': [{'index': 0, 'delta': {
                        'content': f"\n\n\u26a0 {err_label} error: {ev['message']}"}}]})
                elif et == 'tool_call' and render_tools:
                    args = ev['args']
                    if isinstance(args, dict):
                        cmd_str = args.get('cmd') or args.get('command') or json.dumps(args)
                    else:
                        cmd_str = str(args)
                    write_sse({'choices': [{'index': 0, 'delta': {
                        'content': f"\n[{(ev['name'] or 'tool').upper()}: {cmd_str}]\n"}}]})
                elif et == 'tool_result' and render_tools:
                    if ev['summary']:
                        write_sse({'choices': [{'index': 0, 'delta': {
                            'content': f"\n\U0001f4e1 tool(\"{ev['id'][:60] or '...'}\" \u2192\n{ev['summary']}\n"}}]})
                elif et == 'done' and ev.get('summary'):
                    write_sse({'choices': [{'index': 0, 'delta': {
                        'content': f"\n\n_({ev['summary']})_"}}]})
        finally:
            drv.cancel(handle)
            if done_sentinel:
                try:
                    self.wfile.write(b'data: [DONE]\n\n')
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

    # ---- Tool execution proxy (bracket-format tools for any provider) ------
    def _validate_path(self, path, strict=False):
        """Resolve path and verify it falls within CAFRESOHQ_ALLOWED_DIRS.
        In local mode with no explicit CAFRESOHQ_ALLOWED_DIRS env var the check
        is skipped — the user is developing locally and can access their own files.
        In container mode or when the admin explicitly set CAFRESOHQ_ALLOWED_DIRS
        the strict whitelist is enforced.

        strict=True refuses that local-mode skip for callers that are reachable
        WITHOUT the API key (currently /fs/site, which the preview iframe fetches
        keyless). For those the skip would be an unauthenticated arbitrary-read
        hole, so an explicit sandbox is required — see _site_sandbox_ok.
        """
        # Relative → the workspace, not the server's own cwd. One anchor for
        # every door; see _workspace_path for what the two used to mean.
        p = _workspace_path(path, strict=strict).resolve()
        if not strict and not _ALLOWED_DIRS_EXPLICIT and _RUNTIME_ENV == 'local':
            return p  # local default: no restriction, user accesses own files
        for d in _cafresohq_allowed_dirs:
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
        if not _cafresohq_allowed_dirs:
            return self._send_json(503, {'ok': False,
                'error': 'CAFRESOHQ_ALLOWED_DIRS not set — clone disabled'})
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

        target = pathlib.Path(_cafresohq_allowed_dirs[0]) / repo_name
        try:
            target = target.resolve()
            # Must remain inside the allowed dir
            target.relative_to(pathlib.Path(_cafresohq_allowed_dirs[0]).resolve())
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

    # ---- Night Shift endpoints (Sprint 4 MVP-1) -----------------------------
    def _missions_scheduled_get(self):
        return self._send_json(200, {
            'schedules': _night_load('scheduled-missions.json', []),
            'running': list(_night_running.keys()),
            'browserActive': _night_browser_active(),
        })

    def _missions_runs(self):
        return self._send_json(200, {'runs': _night_load('mission-runs.json', [])})

    def _cron_status_proxy(self):
        """GET /gap/status and /news/status — proxy the standalone search
        worker's status listener (search_worker_service/worker.py, default
        :8788). The crons and their ledgers moved there; this stays so the
        operator's `curl localhost:8787/gap/status` habit keeps working."""
        url = _WORKER_STATUS_URL + self.path
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return self._send_json(r.status, json.loads(r.read().decode('utf-8')))
        except Exception as e:
            return self._send_json(502, {
                'error': 'search worker not reachable at %s' % _WORKER_STATUS_URL,
                'detail': str(e)[:200],
                'hint': 'the worker runs standalone now: '
                        'docker compose -f docker-compose.worker.yml up -d',
            })

    def _missions_schedule(self):
        """POST /missions/schedule — create/update one night-shift schedule.
        Bounds: duration ≤ 4h, interval ≥ 60s, ≤ 20 schedules. The runner's
        tool subset (no wallet/publish/shell) is enforced in night_runner.py."""
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
        except Exception:
            return self._send_json(400, {'error': 'bad json'})
        topic = str(req.get('topic', '')).strip()
        agent_id = str(req.get('agentId', '')).strip()
        if not topic or not agent_id:
            return self._send_json(400, {'error': 'topic and agentId are required'})
        try:
            start_at = int(req.get('startAt') or 0)
            duration = int(req.get('durationMs') or 3_600_000)
            interval = int(req.get('intervalMs') or 300_000)
        except Exception:
            return self._send_json(400, {'error': 'bad startAt/durationMs/intervalMs'})
        now_ms = int(time.time() * 1000)
        duration = max(60_000, min(duration, 4 * 3_600_000))
        interval = max(60_000, min(interval, duration))
        sched = {
            'id': str(req.get('id') or '').strip() or ('nsh_%d' % now_ms),
            'type': 'project-study' if req.get('type') == 'project-study' else 'research',
            'topic': topic[:200],
            'agentId': agent_id[:80],
            'agentName': str(req.get('agentName') or '').strip()[:60],
            'vaultFolder': (str(req.get('vaultFolder') or '').strip().strip('/')
                            or 'Research/night')[:120],
            'projectName': str(req.get('projectName') or '')[:80],
            'projectPath': str(req.get('projectPath') or '')[:300],
            'startAt': start_at,
            'recurrence': 'daily' if req.get('recurrence') == 'daily' else 'once',
            'durationMs': duration, 'intervalMs': interval,
            'enabled': req.get('enabled') is not False,
            'lastRunAt': 0,
            'nextRunAt': start_at if start_at > now_ms else now_ms,
            'createdAt': now_ms,
        }
        # Asked before the lock: this is a network probe on the rest backend,
        # and holding _night_lock across it would stall the scan thread that
        # starts tonight's runs. 3s, not the default 30 — the save is the job
        # and this only decorates its confirmation.
        #
        # Advisory on purpose. The schedule is SAVED either way: a vault down
        # now can be up by 1am, and night_runner asks again at the run door,
        # which stays the authoritative one. What is not optional is saying
        # so — every mission this schedules ends in a mandatory vault write,
        # so "Scheduled 🌙" on its own is a promise the office already knows
        # it may not keep, and the boss finds out at 1am.
        v = _vault_readiness(probe_timeout=3)
        warning = '' if (v['configured'] or v['unanswered']) else NO_VAULT_AT_SAVE
        with _night_lock:
            scheds = [s for s in _night_load('scheduled-missions.json', [])
                      if s.get('id') != sched['id']]
            if len(scheds) >= MAX_NIGHT_SCHEDULES:
                return self._send_json(400, {'error': 'too many schedules (max %d)' % MAX_NIGHT_SCHEDULES})
            scheds.append(sched)
            _night_save('scheduled-missions.json', scheds)
        return self._send_json(200, {'ok': True, 'schedule': sched,
                                     'vaultWarning': warning})

    def _missions_delete(self):
        """DELETE /missions/scheduled/<id> — the boss's "✕ CANCEL".

        Used to only drop the schedule row: a mission already in flight
        (`_night_running`) kept executing in its background thread for the
        rest of its duration — up to 4 hours — with no schedule left to show
        it, no board entry, nothing. An orphaned job the boss had just
        clicked "cancel" on, invisible everywhere, still spending tokens.
        Reproduced live: cancelled a running mission, watched
        `_night_running` still hold its id with `schedules: []` right after.
        Now also flags it to stop — `run_mission`'s should_abort check picks
        it up within its next 5s sleep slice (night_runner.py), same as an
        explicit stop already does for browser-side research missions.
        """
        sid = self.path.rstrip('/').rsplit('/', 1)[-1]
        with _night_lock:
            scheds = _night_load('scheduled-missions.json', [])
            kept = [s for s in scheds if s.get('id') != sid]
            _night_save('scheduled-missions.json', kept)
            was_running = sid in _night_running
            if was_running:
                _night_abort.add(sid)
        return self._send_json(200, {'ok': True, 'removed': sid,
                                     'existed': len(kept) != len(scheds),
                                     'stopped': was_running})

    def _tool_exec(self):
        """Execute a bracket-format tool call dispatched by the frontend.
        Body: {tool, arg, body?}
        Requires CAFRESOHQ_ALLOWED_DIRS to be configured (same gate as /cafresohq/stream).
        BASH additionally requires 'Bash' in CAFRESOHQ_ALLOWED_TOOLS.
        """
        if not _cafresohq_allowed_dirs:
            return self._send_json(503, {'ok': False,
                'error': 'CAFRESOHQ_ALLOWED_DIRS not set — tool execution disabled'})
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
        tool_cwd = _cafresohq_allowed_dirs[0] if _cafresohq_allowed_dirs else os.getcwd()
        if req_cwd:
            try:
                cwd_p = pathlib.Path(_client_path(req_cwd)).resolve()
                if cwd_p.is_dir():
                    if not _ALLOWED_DIRS_EXPLICIT and _RUNTIME_ENV == 'local':
                        tool_cwd = str(cwd_p)  # local default: trust any existing dir
                    else:
                        for d in _cafresohq_allowed_dirs:
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

        # Some tools fail WITHOUT raising: a missing file or a path that
        # isn't a directory are ordinary answers to an ordinary question, so
        # they come back 200 with the explanation as the result. The
        # coworker needs that text to recover — but every surface that
        # renders the event was reading "there is a result" as "it worked",
        # and captioning a failed DIR_LIST "📁 Opened ./site" directly above
        # its own "Not a directory: ./site". Watched live 2026-08-13. The
        # flag below is how the office tells the difference; `ok` stays True
        # so the text still reaches the model.
        failed = False

        try:
            if tool == 'FILE_READ':
                p = _resolve_arg(arg)
                if not p.exists():
                    result = f'File not found: {arg}'
                    failed = True
                else:
                    text = p.read_text(encoding='utf-8', errors='replace')
                    if len(text) > 8000:
                        text = text[:8000] + '\n…(truncated to 8000 chars)'
                    result = text

            elif tool == 'DIR_LIST':
                p = _resolve_arg(arg or tool_cwd)
                if not p.is_dir():
                    result = f'Not a directory: {arg}'
                    failed = True
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
                if 'Bash' not in _cafresohq_allowed_tools:
                    return self._send_json(403, {'ok': False,
                        'error': 'Bash not in CAFRESOHQ_ALLOWED_TOOLS — add it to enable shell access'})
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
                    failed = True   # a command that exited non-zero did not "run" successfully

            else:
                return self._send_json(400, {'ok': False, 'error': f'Unknown tool: {tool}'})

            return self._send_json(200, {'ok': True, 'result': result, 'failed': failed})

        except PermissionError as e:
            return self._send_json(403, {'ok': False, 'error': str(e)})
        except subprocess.TimeoutExpired:
            return self._send_json(200, {'ok': False, 'error': 'command timed out (30s)'})
        except Exception as e:
            return self._send_json(500, {'ok': False, 'error': str(e)})

    # ---- CafresoHQ (elevated agent: Claude Code with constrained tools) ---
    def _cafresohq_status(self):
        """Report whether the elevated endpoint is wired up. The client uses
        this to disable the 🛡 toggle when no allowlist is configured."""
        bin_ = self._claudecode_resolve()
        # Validate that every configured dir exists — a typo'd dir is a
        # silent landmine (claude would just refuse the read).
        dirs_ok = []
        dirs_bad = []
        for d in _cafresohq_allowed_dirs:
            (dirs_ok if pathlib.Path(d).is_dir() else dirs_bad).append(d)
        return self._send_json(200, {
            'configured': bool(bin_) and bool(dirs_ok) and bool(_cafresohq_allowed_tools),
            'binary': bin_ or '',
            'allowedDirs': dirs_ok,
            'badDirs': dirs_bad,
            'allowedTools': list(_cafresohq_allowed_tools),
        })

    def _codex_status(self):
        """Report whether the Codex elevated endpoint is wired up."""
        bin_ = self._codex_resolve()
        dirs_ok, dirs_bad = [], []
        for d in _cafresohq_allowed_dirs:
            (dirs_ok if pathlib.Path(d).is_dir() else dirs_bad).append(d)
        return self._send_json(200, {
            'configured': bool(bin_) and bool(dirs_ok),
            'binary': bin_ or '',
            'override': _drivers.get('codex').binary_override or '',
            'allowedDirs': dirs_ok,
            'badDirs': dirs_bad,
            'allowedTools': list(_cafresohq_allowed_tools),
        })

    # ──────────────────────────────────────────────────────────────────────
    # Agents — Hermes ships built-in (default runtime); Claude Code + Codex are
    # optional and installed on-demand so the image stays lean and provisioning
    # is fast. Users add the agents they want from HQ Settings.
    # ──────────────────────────────────────────────────────────────────────
    def _agent_version(self, bin_, *args):
        if not bin_:
            return ''
        try:
            r = subprocess.run([bin_, *args], capture_output=True, text=True, timeout=6)
            out = (r.stdout or r.stderr or '').strip()
            return out.splitlines()[0][:80] if out else ''
        except Exception:
            return ''

    def _agent_auth_detect(self, aid):
        """Best-effort login/credential detection for an agent CLI on THIS host.

        Returns (authenticated: bool, auth: str) where auth is the mechanism
        found: 'oauth' (CLI login), 'api-key' (env var), 'config' (hermes
        config.yaml present), or '' when nothing was found. File checks only —
        no subprocesses, no key material is read or returned. A False here is
        a hint, not a verdict (e.g. macOS keychain-stored claude creds have no
        file to see), so the UI words it as "needs login", never "broken".
        """
        home = pathlib.Path.home()
        try:
            if aid == 'claude-code':
                # Moved into the driver — one detection, front desk and legacy
                # /agents endpoint both read it.
                return _drivers.get('claude-code').detect_auth()
            elif aid == 'codex':
                return _drivers.get('codex').detect_auth()
            elif aid == 'gemini':
                return _drivers.get('gemini').detect_auth()
            elif aid == 'hermes':
                return _drivers.get('hermes').detect_auth()
        except OSError:
            pass
        return False, ''

    def _hermes_gateway_running(self):
        """True when the Hermes gateway is accepting connections on loopback."""
        return _drivers.hermes.gateway_running()

    def _agents_status(self):
        """GET /agents — which agents are available on this serve.py host.
        Version probes (one subprocess per installed CLI) run concurrently so the
        endpoint stays snappy even with several agents installed. Each agent also
        carries best-effort login detection (authenticated/auth) so the UI can
        sync the user's existing local CLIs — and hermes reports whether its
        gateway is actually up (running)."""
        specs = [
            ('hermes',      'Hermes Agent', True,  False, self._hermes_resolve,
             'Nous Research agent — your container’s default runtime.'),
            ('claude-code', 'Claude Code',  False, True,  self._claudecode_resolve,
             'Anthropic’s coding agent CLI (BYO key).'),
            ('codex',       'Codex',        False, True,  self._codex_resolve,
             'OpenAI’s coding agent CLI (BYO key).'),
            ('gemini',      'Gemini',       False, True,  self._gemini_resolve,
             'Google’s Gemini agent CLI (BYO key).'),
        ]
        bins = {aid: resolve() for (aid, _l, _d, _r, resolve, _ds) in specs}
        # Probe versions concurrently (bounded; each call self-limits to ~6s).
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(specs)) as ex:
            futs = {aid: ex.submit(self._agent_version, b, '--version')
                    for aid, b in bins.items() if b}
            versions = {aid: f.result() for aid, f in futs.items()}
        auth = {aid: self._agent_auth_detect(aid) for aid in bins}
        hermes_up = bool(bins.get('hermes')) and self._hermes_gateway_running()
        agents = [
            {'id': aid, 'label': label, 'installed': bool(bins[aid]),
             'default': dflt, 'removable': rem,
             'version': versions.get(aid, ''), 'desc': desc,
             'authenticated': auth[aid][0], 'auth': auth[aid][1],
             **({'running': hermes_up} if aid == 'hermes' else {})}
            for (aid, label, dflt, rem, _resolve, desc) in specs
        ]
        return self._send_json(200, {'agents': agents})

    def _agents_install(self):
        """POST /agents/install { agent: 'claude-code'|'codex'|'gemini'|'hermes' }
        — install an agent CLI onto the serve.py host. Node CLIs go through npm;
        Hermes (a unix-only Python package) goes through pip. Fixed allowlist (no
        arbitrary packages). Synchronous; can take ~30-90s. Returns { ok, agent,
        installed, version }."""
        AGENT_NPM = {
            'claude-code': '@anthropic-ai/claude-code@latest',
            'codex':       '@openai/codex@latest',
            'gemini':      '@google/gemini-cli@latest',
        }
        # Hermes is unix-only (gateway/pty_bridge import termios/pty/fcntl) — it
        # only installs where serve.py runs on a unix host (container or WSL).
        AGENT_PIP = {
            'hermes':      'hermes-agent',
        }
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})
        agent = str(body.get('agent', '')).strip().lower()

        if agent in AGENT_NPM:
            npm = shutil.which('npm')
            if not npm:
                return self._send_json(503, {'error': 'npm not available on this host'})
            cmd = [npm, 'install', '-g', AGENT_NPM[agent]]
        elif agent in AGENT_PIP:
            if sys.platform == 'win32':
                return self._send_json(400, {'error':
                    'hermes is unix-only and cannot install on native Windows — '
                    'run CafresoHQ in WSL (use Start-CafresoHQ) and install there'})
            # Prefer `pip` if present, else `python3 -m pip` (pip often isn't on
            # the WSL PATH). --user keeps it in the invoking user's site dir.
            pip = shutil.which('pip3') or shutil.which('pip')
            base = [pip] if pip else [sys.executable or 'python3', '-m', 'pip']
            cmd = base + ['install', '--user', '--upgrade', AGENT_PIP[agent]]
        else:
            return self._send_json(400, {
                'error': 'agent must be claude-code, codex, gemini, or hermes'})

        # Inherit the environment so npm/pip use the prefix+cache the image set
        # (Dockerfile + entrypoint export npm_config_prefix/cache + HOME); locally
        # this is the user's own npm/pip config. Guard HOME in case it's unset.
        install_env = dict(os.environ)
        install_env.setdefault('HOME', '/root' if sys.platform != 'win32'
                               else install_env.get('USERPROFILE', ''))

        # Run the install in a BACKGROUND thread and 202 immediately — the old
        # synchronous path parked a request thread for up to 600s, starving the
        # whole server while npm ran. The client polls /agents/install/status.
        with _INSTALL_JOBS_LOCK:
            cur = _INSTALL_JOBS.get(agent)
            if cur and cur.get('status') == 'running':
                return self._send_json(202, {'ok': True, 'agent': agent,
                                             'status': 'running',
                                             'note': 'install already in progress'})
            _INSTALL_JOBS[agent] = {'agent': agent, 'status': 'running',
                                    'started': time.time()}

        resolvers = {
            'claude-code': self._claudecode_resolve,
            'codex':       self._codex_resolve,
            'gemini':      self._gemini_resolve,
            'hermes':      self._hermes_resolve,
        }
        resolve = resolvers[agent]
        version_of = self._agent_version

        def _worker():
            result = {'status': 'error', 'error': 'unknown'}
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=600, env=install_env)
                if proc.returncode != 0:
                    full = ((proc.stderr or '') + '\n' + (proc.stdout or '')).strip()
                    # Persist the FULL log — truncating to 600 chars hid the real cause.
                    try:
                        _sd = os.environ.get('CAFRESOHQ_HQ_STATE_DIR', '/data/hq-state')
                        os.makedirs(_sd, exist_ok=True)
                        with open(os.path.join(_sd, 'agent-install-errors.log'), 'a') as _f:
                            _f.write('=== %s :: %s ===\n%s\n\n' % (agent, ' '.join(cmd), full))
                    except Exception:
                        pass
                    low = full.lower()
                    if 'eacces' in low or 'permission denied' in low:
                        hint = ('permission error writing the install prefix/cache — the host '
                                'must pre-create + chmod the npm/pip target dir')
                    elif any(s in low for s in ('enotfound', 'eai_again', 'etimedout',
                             'getaddrinfo', 'could not resolve', 'network', 'timed out')):
                        hint = ('network/DNS — this host cannot reach the package registry; '
                                'open egress to registry.npmjs.org:443 / pypi.org')
                    elif 'enospc' in low or 'no space' in low:
                        hint = 'no disk space left to complete the install'
                    else:
                        hint = full[-600:] or 'install failed'
                    result = {'status': 'error', 'error': hint}
                else:
                    bin_ = resolve()
                    result = {'status': 'done', 'ok': True,
                              'installed': bool(bin_),
                              'version': version_of(bin_, '--version')}
            except subprocess.TimeoutExpired:
                result = {'status': 'error', 'error':
                          'install timed out (>600s) — usually blocked network egress to '
                          'the package registry (open outbound to registry.npmjs.org:443 / pypi.org)'}
            except Exception as e:
                result = {'status': 'error', 'error': str(e)}
            result['agent'] = agent
            result['finished'] = time.time()
            with _INSTALL_JOBS_LOCK:
                _INSTALL_JOBS[agent] = result

        threading.Thread(target=_worker, daemon=True, name=f'install-{agent}').start()
        return self._send_json(202, {'ok': True, 'agent': agent, 'status': 'started',
                                     'note': 'installing in background — poll '
                                             '/agents/install/status?agent=' + agent})

    def _agents_install_status(self):
        """GET /agents/install/status?agent=<id> → the background job's state:
        {status: running|done|error, …}. 404 when no install was started."""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        agent = (qs.get('agent', [''])[0] or '').strip().lower()
        with _INSTALL_JOBS_LOCK:
            job = dict(_INSTALL_JOBS.get(agent) or {})
        if not job:
            return self._send_json(404, {'agent': agent, 'status': 'none'})
        return self._send_json(200, job)

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
    #                               CAFRESOHQ_BROWSER_CDP_URL must be set.
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
                'set CAFRESOHQ_BROWSER_CDP_URL=http://host:port to enable '
                'screenshots and JS-rendered fetch.'
            ),
        })

    def _browser_cdp_probe(self):
        """Find a CDP endpoint. Tries CAFRESOHQ_BROWSER_CDP_URL first,
        then localhost:9222 (Brave/Chrome default). Returns (ok, info)."""
        candidates = []
        env_url = os.environ.get('CAFRESOHQ_BROWSER_CDP_URL', '').strip()
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
                'User-Agent': 'CafresoHQ/1.0 (+browser-shim)',
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
        (or CAFRESOHQ_BROWSER_CDP_URL pointing at one).

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
                    '(or set CAFRESOHQ_BROWSER_CDP_URL to a different host:port).'
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

    def _cafresohq_stream(self):
        """Streaming chat for ELEVATED agents (tools ENABLED, bound to the
        server-side allowlists). Legacy route — same OpenAI-compat SSE shape
        as /claudecode/stream so the client uses one parser; the subprocess +
        parsing now live in the claude-code driver. Differences from the
        plain route:
          - tools enabled (--allowed-tools <server-side allowlist>)
          - working set bound to --add-dir <each allowed dir>
          - refuses if either allowlist is empty (safe default)
        """
        if not _cafresohq_allowed_dirs:
            return self._send_json(503, {
                'error': 'CAFRESOHQ_ALLOWED_DIRS not set — elevated endpoint disabled'
            })
        if not _cafresohq_allowed_tools:
            return self._send_json(503, {
                'error': 'CAFRESOHQ_ALLOWED_TOOLS empty — elevated endpoint disabled'
            })
        # Refuse if any configured dir is missing — easier to fix typos than
        # to debug a silent permission error.
        for d in _cafresohq_allowed_dirs:
            if not pathlib.Path(d).is_dir():
                return self._send_json(503, {
                    'error': f'CAFRESOHQ_ALLOWED_DIRS includes missing dir: {d}'
                })

        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})

        agent = (body.get('agentName') or 'elevated-agent').strip()[:60]
        system = (body.get('system') or '').strip()
        # Guard-rail system note is HOST policy (not a driver detail): the
        # elevated agent must know it runs under HQ's authority and where its
        # boundaries are. Both allowlists come from server-side env, NOT from
        # the request body.
        guard = (
            f'You are {agent}, an elevated HQ agent with computer access. '
            f'You are restricted to these directories: {", ".join(_cafresohq_allowed_dirs)}. '
            'When you intend to perform an action with side effects, first emit '
            '[NEEDS_APPROVAL: <one-line description>] and stop until the boss replies.'
        )
        model = (body.get('model') or '').strip()

        # Audit: log every elevated invocation server-side so there's a
        # tamper-resistant record outside the browser.
        sys.stderr.write(f'[cafresohq] elevated stream: agent={agent} model={model or "(default)"} '
                         f'dirs={_cafresohq_allowed_dirs} tools={_cafresohq_allowed_tools}\n')

        task = {
            'messages':  body.get('messages') or [],
            'system':    guard + ('\n\n' + system if system else ''),
            'model':     model,
            'cwd':       self._agent_task_cwd(body),
            'tools':     list(_cafresohq_allowed_tools),
            'addDirs':   list(_cafresohq_allowed_dirs),
            'agentName': agent,
        }
        return self._agent_stream_legacy('claude-code', task, 'CafresoHQ')

    # ---- Codex CLI elevated agent ----------------------------------------
    def _codex_resolve(self):
        """Find the codex binary. Returns absolute path or ''."""
        return _drivers.get('codex').resolve()

    def _hermes_resolve(self):
        """Find the hermes binary. Returns absolute path or ''."""
        return _drivers.get('hermes').resolve()

    def _gemini_resolve(self):
        """Find the gemini binary (npm @google/gemini-cli). Returns path or ''.
        Moved into the driver — one detection, front desk, /agents/install
        and the legacy PTY /terminal/run path (pty_server.py) all read it."""
        return _drivers.get('gemini').resolve()

    def _codex_configure(self):
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})
        try:
            _drivers.get('codex').configure({'binary': body.get('binary')})
        except _DriverError as e:
            return self._send_json(e.status, {'error': str(e)})
        return self._codex_status()

    def _codex_stream(self):
        """Streaming elevated agent backed by the codex driver (codex exec
        --json, workspace-write sandbox). Legacy route — same SSE output shape
        as /cafresohq/stream (plus inline tool text + the [DONE] trailer this
        route's client expects); the subprocess + event-zoo parsing now live
        in drivers/codex.py. Auth comes from ~/.codex/auth.json or
        OPENAI_API_KEY — serve.py never touches key material.
        """
        if not _cafresohq_allowed_dirs:
            return self._send_json(503, {
                'error': 'CAFRESOHQ_ALLOWED_DIRS not set \u2014 codex endpoint disabled'
            })
        for d in _cafresohq_allowed_dirs:
            if not pathlib.Path(d).is_dir():
                return self._send_json(503, {
                    'error': f'CAFRESOHQ_ALLOWED_DIRS includes missing dir: {d}'
                })

        length = int(self.headers.get('content-length', 0) or 0)
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return self._send_json(400, {'error': 'bad json'})

        agent = (body.get('agentName') or body.get('agent') or 'elevated-agent').strip()[:60]
        system = (body.get('system') or '').strip()
        model = (body.get('model') or '').strip()
        # Guard-rail note is HOST policy, same wording as /cafresohq/stream.
        guard = (
            f'You are {agent}, an elevated HQ agent with computer access. '
            f'You are restricted to these directories: {", ".join(_cafresohq_allowed_dirs)}. '
            'When you intend to perform an action with side effects, first emit '
            '[NEEDS_APPROVAL: <one-line description>] and stop until the boss replies.'
        )

        sys.stderr.write(f'[codex] stream: agent={agent} model={model or "(default)"} '
                         f'dirs={_cafresohq_allowed_dirs}\n')

        cwd = self._agent_task_cwd(body)
        task = {
            'messages':  body.get('messages') or [],
            'system':    guard + ('\n\n' + system if system else ''),
            'model':     model,
            'cwd':       cwd,
            # Extra roots beyond the -C dir (old behavior: dirs[1:]).
            'addDirs':   list(_cafresohq_allowed_dirs[1:]),
            'agentName': agent,
        }
        return self._agent_stream_legacy('codex', task, 'Codex',
                                         render_tools=True, done_sentinel=True)

    # ---- Filesystem browser (extracted to fs_routes.py) ------------------
    # Plain-function bindings — each receives this Handler as `self`.
    _fs_browse  = fs_routes._fs_browse
    _fs_collect = fs_routes._fs_collect
    _fs_file    = fs_routes._fs_file
    _fs_stat    = fs_routes._fs_stat
    _fs_site    = fs_routes._fs_site
    _fs_upload  = fs_routes._fs_upload
    _fs_mutate_ok = fs_routes._fs_mutate_ok
    _fs_json_body = fs_routes._fs_json_body
    _fs_mkdir   = fs_routes._fs_mkdir
    _fs_rename  = fs_routes._fs_rename
    _fs_delete  = fs_routes._fs_delete

    # ---- Project Terminal (extracted to pty_server.py) -------------------
    # Plain-function bindings: each receives this Handler instance as `self`
    # and keeps using its helpers (_send_json, _app_origins, CLI resolvers).
    _terminal_spawn  = pty_server._terminal_spawn
    _terminal_nonce  = pty_server._terminal_nonce
    _terminal_pty_ws = pty_server._terminal_pty_ws
    _terminal_status = pty_server._terminal_status
    _terminal_stream = pty_server._terminal_stream

    def _app_origins(self):
        """Browser origins permitted to open the terminal WebSocket and fetch the
        PTY nonce: the production gateway, localhost dev, plus any canister
        origins configured via CAFRESOHQ_ALLOWED_WS_ORIGINS (cross-origin
        frontend/backend split).

        The Host header is client-supplied and is NOT trusted to name an allowed
        origin. Echoing it back would defeat this allowlist via DNS rebinding: an
        attacker-controlled name resolving to 127.0.0.1 arrives with
        Host: evil.example.com, which would then authorise itself for the PTY
        nonce and the terminal WebSocket — i.e. RCE from a visited web page.
        Host is only honoured when it names a loopback literal (which no rebinding
        attack can forge, since the browser sends the attacker's own hostname) or
        a host explicitly configured via CAFRESOHQ_ALLOWED_WS_ORIGINS."""
        origins = {
            'https://hq.cafreso.com',        # production Caddy gateway
            'https://hq-ui.cafreso.com',     # canister UI shell (cross-origin split)
            'https://ai.cafreso.com',        # SvelteKit frontend
            'http://localhost:8787',         # local dev (same-origin)
            'http://127.0.0.1:8787',         # local dev (alt)
            'http://localhost:5173',         # vite dev server
            'http://localhost:5174',         # vite dev server (alt)
        } | _extra_app_origins
        host = self.headers.get('Host', '').strip()
        if host:
            scheme   = 'https' if isinstance(self.connection, ssl.SSLSocket) else 'http'
            hostname = host.rsplit(':', 1)[0] if not host.startswith('[') \
                       else host.split(']', 1)[0] + ']'
            if hostname.lower() in _LOOPBACK_HOSTS or f'{scheme}://{host}' in origins:
                origins.add(f'{scheme}://{host}')
        return origins


    # ---- Export / generate endpoints (extracted to exporters.py) ---------
    # Plain-function bindings — each receives this Handler as `self`.
    #
    # `_read_json_body` was missing from this list entirely. It is not a
    # route — no serve.py dispatch table sends a request to it directly —
    # it is exporters.py's own shared helper, called via `self._read_json_body()`
    # from all five functions below. Composing a class from free functions by
    # individually naming each one (rather than real inheritance) means a
    # helper the module calls on itself has to be wired on just as explicitly
    # as a route does, and this one never was. Every one of these five tools
    # crashed the request thread with a raw `AttributeError` the instant a
    # coworker actually tried to use it — confirmed live: `curl -X POST
    # .../export/pptx` returned nothing at all (curl error 52, empty reply),
    # and the server log showed the handler dying mid-request. None of the
    # five had ever been exercised before this was found.
    _read_json_body = exporters._read_json_body
    _vault_binary_path = exporters._vault_binary_path
    _export_pptx    = exporters._export_pptx
    _export_docx    = exporters._export_docx
    _export_pdf     = exporters._export_pdf
    _generate_image = exporters._generate_image
    _generate_video = exporters._generate_video

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
                # "nothing saved yet" is a NORMAL state, not an error. A first
                # run has no receipts, pins, workflows, projects or meetings,
                # so a 404 here painted six red lines into the console on every
                # single load — which is exactly how a real error gets missed
                # (it hid these from me until I went looking).
                #
                # The client already treats a missing body as "use the
                # default" (`r.ok ? r.json() : null` then `if (data == null)
                # return` in useFileStored), so 200 + null is byte-for-byte the
                # same behaviour with no false alarm. The server-side
                # consumers — the night runner's activity append and its
                # memory read (#142) — likewise guard against a non-list body.
                return self._send_json(200, None)
            try:
                data = filepath.read_text(encoding='utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
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
                # Write atomically. A bare write_bytes truncates the file first,
                # so a crash, container kill or full disk mid-write leaves
                # invalid JSON on disk; the next GET then fails the client's
                # shape check and the whole collection silently resets to seed
                # data. tmp + fsync + os.replace makes the swap all-or-nothing,
                # matching _night_save above.
                tmp = filepath.with_suffix('.json.tmp')
                with open(tmp, 'wb') as fh:
                    fh.write(body)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, filepath)
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
                '# CafresoHQ Agent Roster',
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
            v = _vault_readiness()
            return self._send_json(200, {
                'configured': v['configured'],
                'backend': _vault_backend,
                'root': _vault_root,
                'defaultRoot': str(_default_vault_root),
                'restUrl': _vault_rest_url,
                'restKey': '••••' if _vault_rest_key else '',
                'fsExists': v['fsExists'],
                'restReachable': v['restReachable'],
                'restDetail': v['restDetail'],
                'ociBucket': v['ociBucket'],
                # Legacy field for older clients.
                'exists': v['configured'],
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
                if bk not in _VAULT_BACKENDS:
                    return self._send_json(400, {'error': f'bad backend: {bk}'})
                # 'oci' is provisioned, not typed: the bucket and namespace
                # arrive as env on a fleet container and there is no field
                # here that could invent them. Accepting it anyway would let
                # a laptop office select a backend it can never write to —
                # so the door only opens for an office that has the config,
                # and says where the config lives when it doesn't. Without
                # this arm a fleet boss who pressed LOCAL DIRECTORY once had
                # no way back short of restarting the container.
                if bk == 'oci' and not (_oci_vault_namespace and _oci_vault_bucket):
                    return self._send_json(400, {'error':
                        'this office has no fleet storage — OCI_VAULT_NAMESPACE '
                        'and OCI_VAULT_BUCKET are set when the office is '
                        'set up, not from this screen'})
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

        # Routes from here require a configured backend. One arm per backend
        # PUT /vault/note can dispatch to — the `else` this replaces asked
        # every non-rest backend for a `_vault_root`, which is the wrong
        # question on oci: a fully provisioned fleet office would have been
        # turned away over a local folder it never writes to. It only ever
        # passed because CAFRESOHQ_VAULT defaults to a path; an office
        # started with it blank was one env var from a 503 on a good bucket.
        if _vault_backend == 'rest':
            if not (_vault_rest_url and _vault_rest_key):
                return self._send_json(503, {'error': 'Obsidian REST not configured (URL + API key)'})
        elif _vault_backend == 'oci':
            if not (_oci_vault_namespace and _oci_vault_bucket):
                return self._send_json(503, {'error':
                    'fleet storage not configured — OCI_VAULT_NAMESPACE and '
                    'OCI_VAULT_BUCKET are set when the office is set up'})
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
                        if not rel or rel.endswith('/'):
                            continue
                        if any(part.startswith('.') for part in rel.split('/')):
                            continue
                        mtime = 0
                        if obj.time_modified:
                            try: mtime = int(obj.time_modified.timestamp() * 1000)
                            except Exception: pass
                        files.append(_vault_entry(rel, mtime, obj.size or 0))
                    files.sort(key=lambda f: f['mtime'], reverse=True)
                    return self._send_json(200, {'files': files[:500]})
                except Exception as e:
                    return self._send_json(502, {'error': f'oci: {e}'})
            root = pathlib.Path(_vault_root).resolve()
            files = []
            # Everything filed, not just '*.md'. The 📤 button on this very
            # screen is titled "Upload files into the Library", takes any file
            # a boss picks, writes it into this folder and reports "Filed N
            # files in the Library" — and then this listing was the room those
            # files were filed into. A deck, a PDF and a chart went in through
            # the front door and the Library showed two folders and nothing
            # else. §3.6 calls this surface the cabinet; a cabinet that hides
            # what you put in it is not one.
            for p in root.rglob('*'):
                if not p.is_file():
                    continue
                try:
                    parts = p.relative_to(root).parts
                except ValueError:
                    continue
                if any(part.startswith('.') for part in parts):
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                files.append(_vault_entry('/'.join(parts),
                                          int(st.st_mtime * 1000), st.st_size))
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
            except UnicodeDecodeError:
                # The editor's door, asked for a deck. It used to answer with
                # `'utf-8' codec can't decode byte 0x80 in position 132`, which
                # the client raises verbatim — a boss who clicked a filed
                # PowerPoint got a Python codec error. Now the Library never
                # asks (isBinary routes it elsewhere), and if something does,
                # the answer says what the file is and where its real door is.
                return self._send_json(415, {
                    'error': 'not a text file — open it from the Library, '
                             'or download it',
                    'download': '/vault/file?path=' + urllib.parse.quote(rel),
                })
            except Exception as e:
                return self._send_json(500, {'error': str(e)})
            self.send_response(200)
            self.send_header('content-type', 'text/markdown; charset=utf-8')
            self.end_headers()
            try: self.wfile.write(text.encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError): pass
            return

        # ---------- Raw file (the door for everything the editor can't open) --
        # A deck, a PDF, a chart. Before this the Library could accept one,
        # confirm it, and then had nowhere at all to send the boss — the
        # closest thing to a door was a notice telling them to go and look on
        # another website. §7: every honest sentence needs a way forward, and
        # "we can't show this here" is only honest with a door beside it.
        if path == '/vault/file' and method == 'GET':
            rel = (qs.get('path', [''])[0] or '').strip()
            if not rel:
                return self._send_json(400, {'error': 'missing path'})
            name = rel.rsplit('/', 1)[-1]
            try:
                if _vault_backend == 'rest':
                    s, _h, data = _obsidian_request(
                        'GET', '/vault/' + urllib.parse.quote(rel),
                        extra_headers={'Accept': 'application/octet-stream'})
                    if s == 404:
                        return self._send_json(404, {'error': 'not found'})
                    if s != 200:
                        return self._send_json(s, {'error': data[:300].decode('utf-8', 'replace')})
                elif _vault_backend == 'oci':
                    cli = _oci_object_client()
                    data = cli.get_object(_oci_vault_namespace, _oci_vault_bucket,
                                          _oci_obj_key(rel)).data.content
                else:
                    try:
                        target = _vault_resolve(rel)
                    except ValueError as e:
                        return self._send_json(400, {'error': str(e)})
                    if not target.is_file():
                        return self._send_json(404, {'error': 'not found'})
                    data = target.read_bytes()
            except Exception as e:
                err = str(e)
                if '404' in err or 'NoSuchKey' in err or 'ObjectNotFound' in err:
                    return self._send_json(404, {'error': 'not found'})
                return self._send_json(502, {'error': f'{_vault_backend}: {e}'})
            mime = mimetypes.guess_type(name)[0] or 'application/octet-stream'
            self.send_response(200)
            self.send_header('content-type', mime)
            self.send_header('content-length', str(len(data)))
            # An .html or .svg a coworker wrote is markup this office did not
            # author, and this route serves it from the office's own origin.
            # Attachment + nosniff + a sandbox policy means the browser saves
            # it instead of running it here; the Library's own page preview
            # (sandboxed srcDoc, no allow-same-origin) is where pages render.
            disp = 'inline' if _vault_inline_ok(mime) else 'attachment'
            self.send_header('content-disposition',
                             '%s; filename="%s"' % (disp, name.replace('"', '')))
            self.send_header('x-content-type-options', 'nosniff')
            self.send_header('content-security-policy', 'sandbox')
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError): pass
            return

        # ---------- Write/Append ----------
        if path == '/vault/note' and method == 'PUT':
            rel = qs.get('path', [''])[0]
            mode = qs.get('mode', ['write'])[0]
            length = int(self.headers.get('content-length', 0) or 0)
            body = self.rfile.read(length).decode('utf-8') if length else ''
            # Before any backend: a dotted path would be filed and then
            # never listed again, on every backend this door has. Refused
            # here so the boss, a coworker's VAULT_* tool and the night
            # shift all hear the same sentence instead of a green "Saved"
            # over a file that just left every list (#140).
            hidden = _vault_hidden_part(rel)
            if hidden:
                return self._send_json(400, {
                    'error': 'hidden files are not accepted — the Library '
                             f'never lists anything under "{hidden}". Drop '
                             'the leading dot to file this where it can be '
                             'seen.'})
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
                except Exception as e:
                    # Same not-found classification GET /vault/note (OCI)
                    # already uses a couple hundred lines up — a `pass` here
                    # used to swallow EVERY exception, not just "already
                    # gone": a dead client (bad/expired creds), a wrong
                    # bucket, a network timeout, a permissions error all hit
                    # this except too, and every one of them still answered
                    # `{"deleted": rel, "backend": "oci"}`. A boss deletes a
                    # note, the Library still has it, and the response they
                    # got said it worked.
                    err = str(e)
                    if not ('404' in err or 'NoSuchKey' in err or 'ObjectNotFound' in err):
                        return self._send_json(502, {'error': f'oci: {e}'})
                    # 404 on delete is fine — already gone, same idempotent
                    # semantics as the local-fs branch below (no-op success
                    # when target.exists() is already false).
                return self._send_json(200, {'deleted': rel, 'backend': 'oci'})
            try:
                target = _vault_resolve(rel)
            except ValueError as e:
                return self._send_json(400, {'error': str(e)})
            if target.exists():
                try: target.unlink()
                except Exception as e: return self._send_json(500, {'error': str(e)})
            return self._send_json(200, {'deleted': rel})

        # ---------- Rename / move ----------
        if path == '/vault/rename' and method == 'POST':
            length = int(self.headers.get('content-length', 0) or 0)
            try:
                req = json.loads(self.rfile.read(length) or b'{}')
            except Exception:
                return self._send_json(400, {'error': 'bad json'})
            src = str(req.get('from', '')).strip()
            dst = str(req.get('to', '')).strip()
            if not src or not dst:
                return self._send_json(400, {'error': 'need from + to'})
            # Destination only. A dotted SOURCE stays movable — that is the
            # rescue path for a file already filed in the dark; refusing it
            # would trap the file there forever. A dotted destination is a
            # visible note about to vanish from every list this room keeps —
            # this door used to answer that with a 200 (#140).
            hidden = _vault_hidden_part(dst)
            if hidden:
                return self._send_json(400, {
                    'error': 'hidden destinations are not accepted — the '
                             f'Library never lists anything under "{hidden}", '
                             'so the note would vanish from every list. Drop '
                             'the leading dot.'})
            if _vault_backend == 'rest':
                # Obsidian REST has no native move: copy then delete.
                try:
                    s, _h, body = _obsidian_request('GET', '/vault/' + urllib.parse.quote(src))
                    if s != 200:
                        return self._send_json(404, {'error': f'source not found ({s})'})
                    s2, _h2, resp = _obsidian_request(
                        'PUT', '/vault/' + urllib.parse.quote(dst),
                        body=body, content_type='text/markdown')
                    if s2 not in (200, 204):
                        return self._send_json(s2, {'error': resp[:300].decode('utf-8', 'replace')})
                    _obsidian_request('DELETE', '/vault/' + urllib.parse.quote(src))
                except Exception as e:
                    return self._send_json(502, {'error': f'obsidian: {e}'})
                return self._send_json(200, {'from': src, 'to': dst, 'backend': 'rest'})
            if _vault_backend == 'oci':
                try:
                    cli = _oci_object_client()
                    data = cli.get_object(_oci_vault_namespace, _oci_vault_bucket,
                                          _oci_obj_key(src)).data.content
                    cli.put_object(_oci_vault_namespace, _oci_vault_bucket,
                                   _oci_obj_key(dst), put_object_body=data)
                    cli.delete_object(_oci_vault_namespace, _oci_vault_bucket, _oci_obj_key(src))
                except Exception as e:
                    return self._send_json(502, {'error': f'oci: {e}'})
                return self._send_json(200, {'from': src, 'to': dst, 'backend': 'oci'})
            try:
                s_path = _vault_resolve(src)
                d_path = _vault_resolve(dst)
            except ValueError as e:
                return self._send_json(400, {'error': str(e)})
            if not s_path.exists():
                return self._send_json(404, {'error': 'source not found'})
            if d_path.exists():
                return self._send_json(409, {'error': 'target already exists'})
            try:
                d_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(str(s_path), str(d_path))
            except Exception as e:
                return self._send_json(500, {'error': str(e)})
            return self._send_json(200, {'from': src, 'to': dst})

        # ---------- Upload (multipart) ----------
        # The browser-side file picker / drag-drop lands here. Filenames are
        # flattened + sanitized; ?dir= picks a target folder inside the vault.
        if path == '/vault/upload' and method == 'POST':
            ctype = self.headers.get('content-type', '')
            if 'multipart/form-data' not in ctype:
                return self._send_json(400, {'error': 'expected multipart/form-data'})
            length = int(self.headers.get('content-length', 0) or 0)
            if length <= 0:
                return self._send_json(400, {'error': 'empty upload'})
            if length > 50 * 1024 * 1024:
                return self._send_json(413, {'error': 'upload too large (50 MB max)'})
            raw = self.rfile.read(length)
            import email.parser as _ep
            msg = _ep.BytesParser().parsebytes(
                b'Content-Type: ' + ctype.encode('latin-1', 'replace') + b'\r\n\r\n' + raw)
            if not msg.is_multipart():
                return self._send_json(400, {'error': 'bad multipart body'})
            folder = qs.get('dir', [''])[0].strip().strip('/')
            saved, errors = [], []
            for part in msg.get_payload():
                raw_name = part.get_filename()
                if raw_name is None:
                    continue                   # a form field, not a picked file
                # Same decision as the Projects door, from the same function —
                # a file the boss picks has to come back either filed or
                # refused out loud, and two doors keeping their own copy of
                # that rule is how one of them came to keep it silently.
                decided = fs_routes.upload_name(raw_name)
                if not decided['name']:
                    errors.append({'path': (folder + '/' if folder else '') + decided['shown'],
                                   'error': decided['refusal']})
                    continue
                fname = decided['name']
                data = part.get_payload(decode=True) or b''
                rel = (folder + '/' if folder else '') + fname
                try:
                    if _vault_backend == 'rest':
                        s, _h, resp = _obsidian_request(
                            'PUT', '/vault/' + urllib.parse.quote(rel),
                            body=data, content_type='application/octet-stream')
                        if s not in (200, 204):
                            raise RuntimeError(resp[:200].decode('utf-8', 'replace'))
                    elif _vault_backend == 'oci':
                        cli = _oci_object_client()
                        cli.put_object(_oci_vault_namespace, _oci_vault_bucket,
                                       _oci_obj_key(rel), put_object_body=data)
                    else:
                        target = _vault_resolve(rel)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                    entry = {'path': rel, 'size': len(data)}
                    if decided['renamedFrom']:
                        entry['renamedFrom'] = decided['renamedFrom']
                    saved.append(entry)
                except Exception as e:
                    errors.append({'path': rel, 'error': str(e)})
            # 200 even when nothing was filed — see _fs_upload's note. The
            # body says what happened to every part; the status line only
            # said whether anything happened to survive, which made a refusal
            # arrive as a thrown error at one count and a quiet field at
            # another.
            return self._send_json(200, {'uploaded': saved, 'count': len(saved),
                                         **({'failed': errors} if errors else {})})

        # ---------- Search ----------
        if path == '/vault/search' and method == 'GET':
            query = qs.get('q', [''])[0].strip()
            limit = int(qs.get('limit', ['10'])[0])
            if not query:
                return self._send_json(400, {'error': 'missing q'})
            ql = query.lower()
            if _vault_backend == 'rest':
                try:
                    return self._send_json(200, {'hits': _rest_search(query, limit)})
                except Exception as e:
                    return self._send_json(502, {'error': f'obsidian: {e}'})
            if _vault_backend == 'oci':
                # Search used to only know 'rest' by name; everything else,
                # 'oci' included, fell through to the fs walk below reading
                # _vault_root — usually empty or unrelated to the bucket on
                # an OCI office, so search silently reported "no results"
                # for notes that were really there. List/read/write/delete
                # all branch three ways; this now does too.
                try:
                    return self._send_json(200, _oci_vault_search(query, ql, limit))
                except Exception as e:
                    return self._send_json(502, {'error': f'oci: {e}'})
            root = pathlib.Path(_vault_root).resolve()
            hits = []
            # .html joined .md here first, because _vault_resolve keeps a real
            # extension instead of forcing '.md' onto it (see that function) —
            # pages filed by the "Simple page" starter task are real files on
            # disk, and a search that only globbed *.md would never find the
            # one deliverable format the front door's third starter card
            # produces. That fix left search reading a WIDER set than the
            # listing beside it, which is its own dishonesty: a query for
            # "vendor" returned `vendor-summary.html`, and the file tree in the
            # same pane said no such file existed. One set now, shared with
            # /vault/list and /vault/file, so the two rooms agree.
            for p in root.rglob('*'):
                if not p.is_file() or p.suffix.lower() not in _VAULT_TEXT_EXT:
                    continue
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
                hit = _vault_search_hit(rel, text, ql, query)
                if hit:
                    hits.append(hit)
            hits.sort(key=lambda h: h['score'], reverse=True)
            return self._send_json(200, {'hits': hits[:limit], 'total': len(hits)})

        # ---------- Graph (nodes + wikilink edges) ----------
        if path == '/vault/graph' and method == 'GET':
            try:
                # Three backends write notes (list/read/write/delete all
                # branch this way); the graph used to only know two — 'rest'
                # or "assume fs" — so an OCI office got the fs builder
                # pointed at _vault_root, usually empty or unrelated to the
                # bucket, and silently saw an empty or wrong graph instead
                # of its actual notes.
                if _vault_backend == 'rest':
                    graph = _build_graph_rest()
                elif _vault_backend == 'oci':
                    graph = _build_graph_oci_cached()
                else:
                    graph = _build_graph_fs_cached()
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
            return self._send_json(404, {'error': 'unknown brave endpoint'})
        key = self.headers.get('X-Brave-Key') or os.environ.get('BRAVE_API_KEY', '')
        if not key:
            return self._send_json(401, {'error': 'no Brave key (set X-Brave-Key header or BRAVE_API_KEY env)'})
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
                'User-Agent': 'CafresoHQ/1.0',
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
            try: self._send_json(502, {'error': f'brave: {e}'})
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
            # HTTPResponse.read1(n) — NOT resp.fp.read1(n). Both return as
            # soon as any data is available (so SSE still streams token by
            # token, which plain read(n) would ruin by blocking for a full n),
            # but only the HTTPResponse method understands the body framing:
            #   · chunked  → de-chunks. Reading the raw fp forwarded the chunk
            #     size lines verbatim ("e0\r\ndata: {…}") even though
            #     Transfer-Encoding was stripped as a hop header, corrupting
            #     every relayed SSE stream.
            #   · either framing → returns b'' at the true end of the body.
            #     The raw fp only ends on socket close, which a keep-alive
            #     upstream (Ollama's Go server, LM Studio) never does — so the
            #     relay blocked for its full 600s timeout while the browser,
            #     given no length of its own, waited forever for an end that
            #     never came. That hang stalled every local-model chat turn.
            reader = resp.read1 if hasattr(resp, 'read1') else None
            while True:
                try:
                    chunk = reader(8192) if reader else resp.fp.read1(8192)
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
                self._send_json(502, {'error': f'upstream: {e}'})
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
    # ── Hermes model / capability / provider — all config surgery lives in
    # drivers/hermes.py; these handlers keep the HTTP shape + host-side
    # validation (key regexes, base_url allowlist, trial policy) only.
    # GET  /hermes/model            → {model, presets}
    # POST /hermes/model {model}    → driver configure (config rewrite + restart)
    def _hermes_get_model(self):
        return self._send_json(200, {'model': _drivers.hermes.read_model(),
                                     'presets': _drivers.hermes.MODEL_PRESETS})

    def _hermes_set_model(self):
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})
        model = str(req.get('model', '')).strip()
        if not model or not _drivers.hermes.valid_model_id(model):
            return self._send_json(400, {'error': 'invalid model id'})
        try:
            d = _drivers.get('hermes').configure({'model': model})
        except _DriverError as e:
            return self._send_json(e.status, {'error': str(e)})
        return self._send_json(200, {'model': model, 'restarted': d['restarted'],
                                     'note': 'gateway reloading; allow ~10s'})

    def _hermes_get_capability(self):
        return self._send_json(200, {'mode': _drivers.hermes.read_capability()})

    def _hermes_set_capability(self):
        """POST {mode: 'lite'|'full'} → rewrite the capability block via the
        driver and restart the gateway so the new system-prompt size takes
        effect."""
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})
        mode = str(req.get('mode', '')).strip().lower()
        if mode not in ('lite', 'full'):
            return self._send_json(400, {'error': "mode must be 'lite' or 'full'"})
        try:
            d = _drivers.get('hermes').configure({'capability': mode})
        except _DriverError as e:
            return self._send_json(e.status, {'error': str(e)})
        return self._send_json(200, {'mode': mode, 'restarted': d['restarted'],
                                     'note': 'gateway reloading; allow ~10s'})

    def _hermes_local_models(self, query):
        """GET /hermes/local-models?base_url=… → {models:[{id, state, loaded}], detail}

        Which models the operator's local backend actually has, and crucially
        WHICH ARE LOADED. Asking a local backend for an unloaded model fails
        every call; showing loaded state in the picker makes that unpickable
        instead of a mystery.

        The browser can't fetch this itself: the /lmstudio/ proxy is hardcoded to
        one host, so it can't serve a URL the operator just typed. Runs the same
        allowlist as the write path — discovery must not become the SSRF hole the
        writer isn't. Always 200: a backend that's merely offline must not block
        the operator from saving a config for it.
        """
        base_url = urllib.parse.parse_qs(query or '').get('base_url', [''])[0].strip()
        ok, err = _validate_local_base_url(base_url)
        if not ok:
            return self._send_json(400, {'error': err})
        root = base_url.rstrip('/')
        # LM Studio's native REST API carries load state; the OpenAI-compatible
        # /models (which Ollama also answers) does not.
        native = re.sub(r'/v\d+$', '', root) + '/api/v0/models'
        for url, has_state in ((native, True), (root + '/models', False)):
            try:
                with urllib.request.urlopen(url, timeout=3) as r:
                    data = json.loads(r.read().decode('utf-8'))
            except Exception:
                continue
            out = []
            for m in (data.get('data') or []):
                mid = m.get('id')
                if not mid:
                    continue
                if has_state:
                    out.append({'id': mid, 'state': m.get('state'),
                                'loaded': m.get('state') == 'loaded',
                                'type': m.get('type')})
                else:
                    out.append({'id': mid, 'state': None, 'loaded': None,
                                'type': m.get('type')})
            if out:
                # Loaded first — those are the ones that answer immediately.
                out.sort(key=lambda x: (x['loaded'] is not True, x['id']))
                return self._send_json(200, {'models': out, 'source': url})
        return self._send_json(200, {'models': [], 'detail': 'no model list at %s' % root})

    def _hermes_get_provider(self):
        """GET /hermes/provider → {provider, model, configured}. The UI reads this
        on load to decide whether to re-push the user's saved key: a container
        recreate wipes the ephemeral ~/.hermes, so the key must be re-applied from
        the browser-side settings copy (that's the 'keys vanish on recreate' fix)."""
        import night_runner as _nr
        cfg = _nr.read_model_config(_drivers.hermes.home())  # scoped to the model: block
        provider = cfg['raw_provider'] or 'openrouter'
        model, base_url = cfg['model'], cfg['base_url']
        logical = {'google-openai': 'gemini'}.get(provider, provider)
        spec = _drivers.hermes.PROVIDERS.get(logical)
        if spec and spec.get('local'):
            # A local backend has no key — having a base_url IS being configured.
            configured = bool(base_url)
        elif spec:
            configured = _drivers.hermes.key_configured(spec['env'])
        else:
            configured = False
        return self._send_json(200, {'provider': logical, 'model': model,
                                     'base_url': base_url, 'configured': configured})

    def _hermes_set_provider(self, force_provider=None):
        """POST /hermes/provider {provider, key, model?} → write the provider's
        key + rewrite config.yaml's model block + restart, all via the hermes
        driver's configure(). Host-side here: request validation (key regex,
        the local-base_url allowlist) and trial policy. Key lives only in the
        container .env (0600), never persisted server-side beyond that file.
        /hermes/openrouter-key routes here with force_provider='openrouter'."""
        length = int(self.headers.get('content-length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})
        provider = (force_provider or str(req.get('provider', 'openrouter'))).strip().lower()
        spec = _drivers.hermes.PROVIDERS.get(provider)
        if not spec:
            return self._send_json(400, {'error': f'unknown provider: {provider}'})
        key = str(req.get('key', '')).strip()
        local = bool(spec.get('local'))
        base_url = str(req.get('base_url', '')).strip() or spec.get('default_url')
        if local:
            # No key to validate — the gate here is the URL, which the container
            # will go on to POST to. See _validate_local_base_url: allowlist.
            ok, err = _validate_local_base_url(base_url)
            if not ok:
                return self._send_json(400, {'error': err})
        elif not re.match(spec['re'], key):
            return self._send_json(400, {'error': f"invalid {spec['label']} key"})
        model = str(req.get('model', '')).strip() or spec['model']

        try:
            d = _drivers.get('hermes').configure({'provider': provider, 'key': key,
                                                  'model': model, 'baseUrl': base_url})
        except _DriverError as e:
            return self._send_json(e.status, {'error': str(e)})

        # The user just brought their OWN key (or their own hardware) — end the
        # shared-trial cap. Their key draws on their own account, so it's never
        # metered here.
        _trial_deactivate()
        return self._send_json(200, {'ok': True, 'provider': provider, 'model': model,
                                     'restarted': d['restarted'],
                                     'note': 'gateway reloading; allow ~10s'})

    def _hermes_trial_status(self):
        """GET /hermes/trial-status → whether this HQ is on the shared trial
        brain and how much of today's per-principal allowance is left. Drives the
        onboarding upsell ('you're on the free shared brain — add your own key
        for unlimited'). Returns active:false once the user brings their own key."""
        st = _trial_state()
        principal = (self.headers.get('X-User-Principal') or '').strip() or 'local'
        used, cap = _trial_usage(principal)
        return self._send_json(200, {
            'active': st.get('active', False),
            'provider': st.get('provider', ''),
            'used': used,
            'cap': cap,
            'remaining': max(0, cap - used),
        })

    # ── Hermes config import/export ──────────────────────────────────────────
    # Lets users carry a Hermes agent setup between HQs (or in from a local
    # ~/.hermes) in one click. config.yaml holds NO secrets — keys live in
    # .env, which is never exported and never accepted on import.
    def _hermes_export_config(self):
        cfg, mode = _drivers.hermes.export_config()
        return self._send_json(200, {
            'version': 1,
            'kind': 'cafresohq-hermes-config',
            'capability': mode,
            'config_yaml': cfg,
            'note': 'keys are NOT included — set them in Settings → Connections',
        })

    def _hermes_import_config(self):
        """POST {config_yaml, capability?} → replace ~/.hermes/config.yaml (via
        the driver, which keeps a .bak rollback) and restart the gateway.
        Refuses key material (keys belong in .env via Settings) and
        obviously-broken payloads."""
        length = int(self.headers.get('content-length', 0) or 0)
        if length > 64 * 1024:
            return self._send_json(413, {'error': 'config too large (64 KB max)'})
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})
        cfg = str(req.get('config_yaml', '') or '')
        if not cfg.strip():
            return self._send_json(400, {'error': 'config_yaml is empty'})
        if 'model:' not in cfg:
            return self._send_json(400, {'error': "doesn't look like a Hermes config (no model: block)"})
        if re.search(r'(?im)^\s*[\w-]*(api[_-]?key|secret|token|password)\s*:\s*\S', cfg):
            return self._send_json(400, {
                'error': 'config contains key material — remove it; API keys are set in Settings → Connections'})
        cap = str(req.get('capability', '')).strip().lower()
        ok, restarted, rollback, err = _drivers.hermes.import_config(cfg, cap)
        if not ok:
            return self._send_json(500, {'error': err})
        return self._send_json(200, {'ok': True, 'restarted': restarted,
                                     'rollback': rollback,
                                     'note': 'gateway reloading; allow ~10s'})

    def _hermes_proxy(self, method):
        """Proxy /hermes/* → the local `hermes gateway` OpenAI-compatible API
        server (drivers.hermes.HERMES_HOST:PORT, default 127.0.0.1:8642).

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

        # Trial-brain cap: when this HQ is running on the shared trial key, meter
        # chat completions per-principal per-day so one user can't drain the
        # shared pool. A user's OWN key clears the trial (below) and is never
        # metered. Body is already consumed, so a 429 here is a clean response.
        if method == 'POST' and upstream_path.startswith('/v1/chat/completions') \
                and _trial_state().get('active'):
            _principal = (self.headers.get('X-User-Principal') or '').strip() or 'local'
            _ok, _used, _cap = _trial_check_and_bump(_principal)
            if not _ok:
                return self._send_json(429, {
                    'error': 'trial_limit', 'used': _used, 'cap': _cap,
                    'message': (f"You've used your {_cap} free messages for today. "
                                "Add your own free key in Settings — it's quick and "
                                "gives you unlimited use."),
                })

        # Also strip browser-context headers. The in-container Hermes gateway's
        # aiohttp server REJECTS any request carrying an Origin it doesn't know
        # with 403 (CORS/CSRF) — and our cross-origin canister UI always sends
        # Origin: https://hq-ui.cafreso.com — so forwarding it broke every Hermes
        # call (chat + /models). The gateway authenticates via the Bearer we
        # inject below, not the browser cookie/origin, so drop all three.
        _drop = HOP_HEADERS | {'host', 'authorization', 'accept-encoding',
                               'origin', 'referer', 'cookie'}
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in _drop}
        headers['Host'] = f'{_drivers.hermes.HERMES_HOST}:{_drivers.hermes.HERMES_PORT}'
        headers['Accept-Encoding'] = 'identity'
        # Force the upstream (aiohttp) to close after responding. We relay the
        # body with a raw read1() loop (so SSE streams straight through) which
        # bypasses http.client's Content-Length framing — on a keep-alive
        # response read1() would block waiting for an EOF the gateway never
        # sends, hanging the request (and, since we drop Content-Length as a
        # hop header, the browser's fetch never resolves either). Connection:
        # close makes the gateway send EOF after the body, so the loop ends.
        headers['Connection'] = 'close'

        env_key = _drivers.hermes.api_server_key()
        if env_key:
            headers['Authorization'] = 'Bearer ' + env_key
        else:
            client_auth = self.headers.get('Authorization') or self.headers.get('authorization')
            if client_auth:
                headers['Authorization'] = client_auth

        principal = (self.headers.get('X-User-Principal') or '').strip() or 'local'
        # The gateway is briefly unavailable right after a restart (key / model /
        # capability change replaces the running singleton). Retry the upstream
        # CONNECT a few times so the user sees a short delay instead of a transient
        # 502 during that ~10-15s window. Safe to retry: nothing is written to the
        # client until getresponse() succeeds, and the request body is buffered in
        # memory. Only connection-level failures (gateway not listening / dropped)
        # are retried — a real HTTP error comes back as a status, not an exception.
        conn = None
        resp = None
        last_err = None
        for _attempt in range(10):
            conn = http.client.HTTPConnection(_drivers.hermes.HERMES_HOST,
                                              _drivers.hermes.HERMES_PORT, timeout=600)
            try:
                conn.request(method, upstream_path, body=body, headers=headers)
                resp = conn.getresponse()
                break
            except (ConnectionRefusedError, ConnectionResetError,
                    http.client.RemoteDisconnected) as e:
                last_err = e
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
                time.sleep(1.5)
            except Exception as e:
                last_err = e
                break
        if resp is None:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
            try:
                self._send_json(502, {'error': f'hermes: {last_err or "gateway unavailable"}',
                                      'hint': 'the agent gateway is restarting or down — retry in ~15s'})
            except Exception:
                pass
            return
        try:
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
                self._send_json(502, {'error': f'hermes: {e}'})
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


def _ui_sources(root=None):
    """Every file the UI bundle is built from.

    Deliberately a walk rather than the builder's APP_FILES list: those
    thirteen are barrels, and 45 of the tree's 58 .jsx files are reached
    only through their imports. A staleness check that trusted the named
    list would have gone on reporting "fresh" for exactly the files most
    likely to be edited.
    """
    root = root or os.getcwd()
    skip = {'node_modules', 'dist-ui', '.git', '__pycache__', '.dfx'}
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith('.')]
        for fn in filenames:
            if fn.endswith('.jsx') or fn in ('graph-engine.js', 'analytics.worker.js'):
                out.append(os.path.join(dirpath, fn))
    return out


def _ui_bundle_stale(root=None):
    """(newest_source_path, age_seconds) if the bundle is behind, else None.

    Missing manifest is NOT reported here — that is a different failure with
    its own message (`_serve_hq_html` 500s and names the build command), and
    conflating "never built" with "out of date" would send someone to the
    wrong remedy.
    """
    root = root or os.getcwd()
    manifest = os.path.join(root, 'dist-ui', 'manifest.json')
    try:
        built = os.path.getmtime(manifest)
    except OSError:
        return None
    newest, newest_at = None, 0.0
    for src in _ui_sources(root):
        try:
            at = os.path.getmtime(src)
        except OSError:
            continue
        if at > newest_at:
            newest, newest_at = src, at
    if newest is None or newest_at <= built:
        return None
    return (os.path.relpath(newest, root), newest_at - built)


def _ui_stale_sentence(stale):
    """§7 shape: what is wrong, in one sentence, plus the way forward."""
    path, age = stale
    mins = int(age // 60)
    when = ('%dh %dm' % (mins // 60, mins % 60)) if mins >= 60 else (
        '%dm' % mins if mins else 'less than a minute')
    return ('This page is running a UI bundle built %s before the newest '
            'change to %s — what you are looking at is the previous build. '
            'Run `node scripts/build_ui_bundle.mjs` and reload.' % (when, path))


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


def _ensure_local_tls(state_dir, lan_ip='', allow_selfsigned=True):
    """Provision a localhost TLS cert+key so a LOCAL run can serve HTTPS.

    A browser-TRUSTED https://localhost is what lets the SvelteKit shell at
    https://ai.cafreso.com embed this app in an <iframe> in every browser
    (Safari has no localhost mixed-content exemption). Returns
    (cert_path, key_path, trusted) or (None, None, False).

    Trust tiers, best first:
      1. mkcert — issues a cert signed by a CA installed in the OS/browser trust
         store, so the embed works with NO warning. Used if `mkcert` is on PATH.
      2. self-signed (openssl, then the `cryptography` lib) — only when
         allow_selfsigned=True (CAFRESOHQ_TLS_AUTO=1). HTTPS works after the user
         manually trusts the cert; NOT used by default because a TLS-only server
         with an untrusted cert is unreachable (worse than plain HTTP).

    Certs are cached under <state_dir>/tls and reused on later starts. A sibling
    `.mkcert` marker records whether the cached pair is browser-trusted.
    """
    try:
        tls_dir = pathlib.Path(state_dir) / 'tls'
        tls_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        sys.stderr.write(f'[tls] cannot create cert dir: {e}\n')
        return None, None, False

    cert = tls_dir / 'localhost.pem'
    key  = tls_dir / 'localhost-key.pem'
    marker = tls_dir / '.mkcert'

    # Reuse a previously generated pair — but never hand a cached SELF-SIGNED
    # pair to a caller that only wants trusted certs (it would flip the server
    # to TLS-only with a cert the browser rejects).
    if cert.is_file() and key.is_file() and cert.stat().st_size and key.stat().st_size:
        if marker.exists() or allow_selfsigned:
            return str(cert), str(key), marker.exists()

    hosts = ['localhost', '127.0.0.1', '::1']
    if lan_ip and lan_ip not in hosts:
        hosts.append(lan_ip)

    # ── Tier 1: mkcert (trusted) ──────────────────────────────────────────────
    mkcert = shutil.which('mkcert')
    if mkcert:
        try:
            # -install is idempotent; it may prompt for admin the very first time
            # (to add the local CA). Non-fatal if it fails — the cert still works
            # for direct use, just not the trusted embed.
            subprocess.run([mkcert, '-install'], capture_output=True, text=True, timeout=60)
            r = subprocess.run(
                [mkcert, '-cert-file', str(cert), '-key-file', str(key), *hosts],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0 and cert.is_file() and key.is_file():
                marker.write_text('mkcert\n', encoding='utf-8')
                sys.stderr.write('[tls] generated a browser-trusted cert via mkcert\n')
                return str(cert), str(key), True
            sys.stderr.write(f'[tls] mkcert failed: {(r.stderr or r.stdout)[:200]}\n')
        except (subprocess.SubprocessError, OSError) as e:
            sys.stderr.write(f'[tls] mkcert error: {e}\n')

    if not allow_selfsigned:
        # Trusted-only mode (the auto default): no mkcert → stay on HTTP rather
        # than degrade to an unreachable self-signed TLS-only server.
        return None, None, False

    # ── Tier 2a: openssl self-signed ──────────────────────────────────────────
    openssl = shutil.which('openssl')
    if openssl:
        try:
            san = 'subjectAltName=' + ','.join(
                (f'IP:{h}' if (h.replace('.', '').isdigit() or ':' in h) else f'DNS:{h}')
                for h in hosts)
            r = subprocess.run(
                [openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                 '-keyout', str(key), '-out', str(cert), '-days', '825',
                 '-subj', '/CN=localhost', '-addext', san],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0 and cert.is_file() and key.is_file():
                sys.stderr.write('[tls] generated a self-signed cert via openssl '
                                 '(browser will warn until trusted)\n')
                return str(cert), str(key), False
            sys.stderr.write(f'[tls] openssl failed: {(r.stderr or r.stdout)[:200]}\n')
        except (subprocess.SubprocessError, OSError) as e:
            sys.stderr.write(f'[tls] openssl error: {e}\n')

    # ── Tier 2b: pure-Python self-signed via cryptography ─────────────────────
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime as _dt, ipaddress as _ip

        k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        san_list = []
        for h in hosts:
            try:
                san_list.append(x509.IPAddress(_ip.ip_address(h)))
            except ValueError:
                san_list.append(x509.DNSName(h))
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
        # epoch-based dates — Date.now()/utcnow are fine here (real wall clock at
        # startup), but use a fixed past start to dodge clock-skew rejections.
        not_before = _dt.datetime(2020, 1, 1)
        not_after  = _dt.datetime(2035, 1, 1)
        cert_obj = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(k.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before).not_valid_after(not_after)
            .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
            .sign(k, hashes.SHA256())
        )
        cert.write_bytes(cert_obj.public_bytes(serialization.Encoding.PEM))
        key.write_bytes(k.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
        sys.stderr.write('[tls] generated a self-signed cert via cryptography '
                         '(browser will warn until trusted)\n')
        return str(cert), str(key), False
    except ImportError:
        pass
    except Exception as e:
        sys.stderr.write(f'[tls] cryptography generation failed: {e}\n')

    sys.stderr.write('[tls] no cert tool available (mkcert/openssl/cryptography) '
                     '— staying on HTTP\n')
    return None, None, False


if __name__ == '__main__':
    # When packaged as a PyInstaller exe, static files live next to the exe.
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Is this a genuine local desktop run (vs. an OCI Fleet container)? Computed
    # here because both the TLS-auto and bind-host decisions below depend on it.
    _is_local_run = _RUNTIME_ENV == 'local' and _fleet_mode not in ('oci-fleet', 'fleet')

    # TLS — explicit cert/key (mkcert or any trusted pair) win. Otherwise, for a
    # local deployment (anything NOT behind the OCI Fleet gateway — native run
    # OR `docker run -e CAFRESOHQ_FLEET_MODE=local`), auto-provision a localhost
    # cert so the app serves HTTPS and embeds in https://ai.cafreso.com.
    #
    # CRITICAL default: auto only upgrades to HTTPS when the cert is
    # BROWSER-TRUSTED (mkcert present). A self-signed cert here would be a
    # regression, not an upgrade — the server becomes TLS-only, plain
    # http://localhost:8787 stops answering, the browser refuses the untrusted
    # cert, and the app turns unreachable (esp. in Docker, where mkcert can't
    # install a CA into the HOST browser). And http://localhost is already a
    # secure context in Chrome/Edge/Firefox, so self-signed buys nothing there.
    # CAFRESOHQ_TLS_AUTO=1 forces HTTPS incl. the self-signed fallback (power
    # users who will trust the cert manually); =0 disables auto entirely.
    _local_deploy = _fleet_mode not in ('oci-fleet', 'fleet')
    _tls_cert = os.environ.get('CAFRESOHQ_TLS_CERT', '').strip()
    _tls_key  = os.environ.get('CAFRESOHQ_TLS_KEY',  '').strip()
    _tls_trusted = bool(_tls_cert and _tls_key)   # operator-supplied → assume managed
    if not (_tls_cert and _tls_key):
        _auto = os.environ.get('CAFRESOHQ_TLS_AUTO', '').strip().lower()
        _tls_forced   = _auto in ('1', 'true', 'yes', 'on')
        _tls_disabled = _auto in ('0', 'false', 'no', 'off')
        if not _tls_disabled and (_tls_forced or _local_deploy):
            _gc, _gk, _trusted = _ensure_local_tls(
                _hq_state_dir, _local_ip() or '', allow_selfsigned=_tls_forced)
            if _gc and (_trusted or _tls_forced):
                _tls_cert, _tls_key, _tls_trusted = _gc, _gk, _trusted
    _tls_on   = bool(_tls_cert and _tls_key and
                     pathlib.Path(_tls_cert).is_file() and
                     pathlib.Path(_tls_key).is_file())
    _scheme   = 'https' if _tls_on else 'http'
    # Night-shift runner self-calls loop back over the live scheme/port.
    _night_base_url[0] = '%s://127.0.0.1:%d' % (_scheme, PORT)

    # Bind host: containers/fleet listen on all interfaces (the gateway reaches
    # them by private IP); genuine LOCAL runs default to loopback so an accidental
    # port map doesn't expose the (RCE-capable) terminal. NOTE: OCI Container
    # Instances detect as runtime_env='local' (none of the docker markers exist),
    # so gate the loopback default on the FLEET MODE too — a fleet/container
    # deploy (CAFRESOHQ_FLEET_MODE=oci-fleet) MUST bind all interfaces or the
    # gateway gets 502. Override with CAFRESOHQ_BIND.
    _bind_host = os.environ.get('CAFRESOHQ_BIND', '').strip()
    if not _bind_host:
        _bind_host = '127.0.0.1' if _is_local_run else ''
    if _is_local_run and _bind_host not in ('127.0.0.1', 'localhost') \
            and not CAFRESOHQ_API_KEY:
        print('  ⚠  bound to a non-loopback interface with NO CAFRESOHQ_API_KEY — '
              'the terminal, agent, vault and /tools routes are refused for '
              'non-loopback callers. Set CAFRESOHQ_API_KEY to use them from the LAN.')
    with ThreadedServer((_bind_host, PORT), Handler) as httpd:
        if _tls_on:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(_tls_cert, _tls_key)
            httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
            print(f'  🔒 TLS enabled  cert={_tls_cert}'
                  + ('  (browser-trusted)' if _tls_trusted else '  (self-signed)'))

        lan = _local_ip()
        print(f'CafresoHQ -> {_scheme}://localhost:{PORT}/hq.html')
        _stale = _ui_bundle_stale()
        if _stale:
            # flush: stdout is BLOCK-buffered whenever it is not a terminal —
            # nohup, a redirect to a log file, Electron capturing the pipe. The
            # request log lines come from BaseHTTPRequestHandler, which writes
            # to stderr, so a log read back that way shows the traffic and not
            # the banner. Measured on port 9252: the warning was correct, in
            # the code, and sitting in an unflushed buffer. A warning that only
            # appears on a tty is not a warning.
            print('  ⚠  ' + _ui_stale_sentence(_stale), flush=True)
        if lan:
            print(f'  📱 Mobile / LAN  -> {_scheme}://{lan}:{PORT}/hq.html')
        if _tls_on and _local_deploy:
            if _tls_trusted:
                print('  ✅ Trusted HTTPS — this HQ can load embedded inside '
                      'https://ai.cafreso.com')
            else:
                print('  ⚠  Self-signed HTTPS. For the seamless embed in '
                      'ai.cafreso.com, install mkcert (https://github.com/FiloSottile/mkcert) '
                      'and restart — or open https://localhost:%d/hq.html once and '
                      'trust the cert.' % PORT)
        elif not _tls_on:
            print('  💡 Set CAFRESOHQ_TLS_CERT + CAFRESOHQ_TLS_KEY (or install mkcert) '
                  'for HTTPS — enables the ai.cafreso.com embed + iOS service worker')
        for prefix, (h, p) in ROUTES.items():
            print(f'  proxy {prefix}* -> {h}:{p}/*')
        if _cafresohq_allowed_dirs:
            print(f'  /cafresohq/stream  ELEVATED · tools={",".join(_cafresohq_allowed_tools)}'
                  f' · dirs={_cafresohq_allowed_dirs}')
        else:
            print('  /cafresohq/stream  DISABLED (set CAFRESOHQ_ALLOWED_DIRS to enable)')
        _codex_found = _drivers.get('codex').resolve()
        if _codex_found and _cafresohq_allowed_dirs:
            print(f'  /codex/stream     CODEX · dirs={_cafresohq_allowed_dirs}')
        else:
            print('  /codex/stream     DISABLED (codex not found or CAFRESOHQ_ALLOWED_DIRS not set)')
        print('  /approvals/external  Claude Code PreToolUse hook bridge')
        httpd.serve_forever()
