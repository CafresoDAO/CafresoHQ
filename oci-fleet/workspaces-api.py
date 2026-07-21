#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   Cafreso -- Workspaces API (the Workspace Portal service)   ║
║   Live desktop streaming: Hyper-V Win11 / WSL / Guacamole    ║
╚══════════════════════════════════════════════════════════════╝

This is the PORTAL service — it runs on the streaming host (today: the
Windows/Hyper-V box behind an HTTPS tunnel), NOT on the OCI gateway. The
gateway keeps running the separate, untouched fleet-api.py. The frontend
targets this service via Settings → "Workspaces API URL"
(stores/workspaces.js `workspacesApiUrl`, falling back to the fleet URL).

Portal endpoints
────────────────
  GET  /workspaces/templates            → catalog (entitled callers only)
  POST /sessions/launch {token, template_id}
  GET  /sessions · /sessions/<id> · /sessions/<id>/metrics
  POST /sessions/<id>/stop · DELETE /sessions/<id>
  GET  /stream/<sid>/* · /guacamole/*   → streaming reverse-proxy
  GET/POST /admin/*                     → fleet admins only

Access control (Cafreso hardening)
──────────────────────────────────
  identity    = on-chain session token (hq_token / HQ_SESSION_SECRET)
  entitlement = state canister /operator/config.json → workspaces.allowedPrincipals
  admin       = X-Fleet-Auth secret AND X-User-Principal ∈ FLEET_ADMIN_PRINCIPALS
  no secret   = refuses to serve unless CAFRESOHQ_DEV=1

Run
───
  $ export FLEET_API_SECRET=… HQ_SESSION_SECRET=… FLEET_ADMIN_PRINCIPALS=…
  $ python oci-fleet/workspaces-api.py     → http://0.0.0.0:8080
Production: behind a TLS tunnel/terminator (the [id] viewer refuses http).
"""
import contextlib
import http.server
import json
import logging
import os
import pathlib
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid

# ── Load .env from streaming/ if present (for TURN_SECRET, etc.) ─────────────
def _load_dotenv():
    """Best-effort .env loader — no external dependencies needed."""
    env_paths = [
        pathlib.Path(__file__).parent / '.env.host',  # host-specific (takes priority)
        pathlib.Path(__file__).parent.parent / 'streaming' / '.env',
        pathlib.Path(__file__).parent / '.env',
    ]
    for env_path in env_paths:
        if env_path.is_file():
            with open(env_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, _, val = line.partition('=')
                        key = key.strip()
                        val = val.strip()
                        # Only set if not already defined (real env vars take precedence)
                        if key and key not in os.environ:
                            os.environ[key] = val
            # continue loading — .env.host overrides others via the key-not-set guard

_load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────
FLEET_DIR        = pathlib.Path(__file__).parent
FLEET_FILE       = FLEET_DIR / 'fleet.json'
FLEET_MANAGER    = FLEET_DIR / 'fleet-manager.py'
WORKSPACES_FILE  = FLEET_DIR / 'workspaces.json'
HYPERV_PROVIDER  = None                          # lazy-init below
LOCAL_PROVIDER   = None                          # lazy-init below
SHARED_SECRET    = os.environ.get('FLEET_API_SECRET', '').strip()
PORT             = int(os.environ.get('FLEET_API_PORT', '8080'))
ALLOWED_ORIGINS  = os.environ.get(
    'FLEET_API_ALLOWED_ORIGINS',
    'http://localhost:5174,http://127.0.0.1:5174,'
    'https://v4tdv-riaaa-aaaab-agtfa-cai.icp0.io,'      # CafresoAI mainnet shell
    'https://6cajv-qqaaa-aaaab-qactq-cai.icp0.io,'      # earlier playground
    'https://ai.cafreso.com,https://cafreso.com'
).split(',')

# Reasonable principal regex — base32 chunks separated by hyphens, length ≤ 100
_PRINCIPAL_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$', re.IGNORECASE)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('workspaces-api')

# ── Access control (Cafreso hardening — not in the original portal) ──────────
# Three layers, all server-side:
#   1. Caller identity: the on-chain session token (minted by the keys
#      canister, verified with hq_token against HQ_SESSION_SECRET) is the only
#      trusted source of a principal. Bare ?principal= is accepted ONLY from
#      an admin-authenticated caller (or dev mode) — never from users.
#   2. Entitlement: the state canister's public /operator/config.json carries
#      { workspaces: { enabled, allowedPrincipals } } — planAdmin-written,
#      cached 60s here, enforced on catalog reads AND launch (the original
#      portal only filtered the catalog).
#   3. Admin: /admin/* requires the shared secret AND an X-User-Principal in
#      FLEET_ADMIN_PRINCIPALS (the original checked only the secret).
FLEET_ADMIN_PRINCIPALS = [p.strip() for p in
                          os.environ.get('FLEET_ADMIN_PRINCIPALS', '').split(',') if p.strip()]
OPERATOR_STATE_URL = os.environ.get(
    'OPERATOR_STATE_URL', 'https://ydacz-riaaa-aaaal-qxeja-cai.icp0.io').rstrip('/')
DEV_MODE = not SHARED_SECRET and os.environ.get('CAFRESOHQ_DEV') == '1'

# Public hostname for hyperv/local sessions, which run entirely ON THIS HOST
# and are never fronted by the OCI gateway. Without this, stream_url fell
# back to fleet.json's gateway.public_hostname (hq.cafreso.com) — a
# DIFFERENT machine that doesn't run this service, silently breaking every
# hyperv/local session's iframe (confirmed live 2026-07-21: launched session
# got stream_url=https://hq.cafreso.com/stream/... instead of this host's
# Tailscale Funnel URL). Set to this host's externally-reachable hostname
# (e.g. the Tailscale Funnel / named tunnel host) in .env.host.
WORKSPACES_PUBLIC_HOSTNAME = os.environ.get('WORKSPACES_PUBLIC_HOSTNAME', '').strip()

try:
    import hq_token as _hq_token
except Exception:            # pragma: no cover — module ships alongside this file
    _hq_token = None

_op_cfg_cache = {'at': 0.0, 'cfg': {}}
_op_cfg_lock = threading.Lock()


def _operator_config() -> dict:
    """The on-chain operator config, cached 60s; keeps last-good on failure.
    Mirrors serve.py's reader — one source of truth for entitlements."""
    with _op_cfg_lock:
        if time.time() - _op_cfg_cache['at'] < 60:
            return _op_cfg_cache['cfg']
    try:
        import urllib.request
        req = urllib.request.Request(OPERATOR_STATE_URL + '/operator/config.json',
                                     headers={'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=8) as r:
            cfg = json.loads(r.read().decode('utf-8'))
        if isinstance(cfg, dict):
            with _op_cfg_lock:
                _op_cfg_cache.update(at=time.time(), cfg=cfg)
    except Exception as e:
        log.warning('operator config fetch failed (keeping last-good): %s', e)
        with _op_cfg_lock:
            _op_cfg_cache['at'] = time.time()   # back off a full period
    return _op_cfg_cache['cfg']


def _workspaces_killed() -> bool:
    ws = _operator_config().get('workspaces') or {}
    return ws.get('enabled') is False


def _workspace_allowed(principal: str) -> bool:
    """Entitlement: on-chain grant list, plus fleet admins always allowed."""
    if not principal:
        return False
    ws = _operator_config().get('workspaces') or {}
    if ws.get('enabled') is False:
        return False
    if principal in FLEET_ADMIN_PRINCIPALS:
        return True
    allowed = ws.get('allowedPrincipals')
    return isinstance(allowed, list) and principal in allowed


def _principal_from_token(token: str) -> str | None:
    """Verify an on-chain session token and return its principal, else None."""
    if not token or _hq_token is None:
        return None
    try:
        secret = _hq_token.secret_bytes()
        claims = _hq_token.verify(token, secret)
        return claims.get('principal') or None
    except Exception:
        return None

# ── In-memory job tracker ────────────────────────────────────────────────────
_jobs      = {}     # job_id -> dict
_jobs_lock = threading.Lock()


def _load_users() -> dict:
    if not FLEET_FILE.exists():
        return {}
    try:
        return json.loads(FLEET_FILE.read_text(encoding='utf-8')).get('users', {})
    except Exception as e:
        log.error(f'fleet.json read error: {e}')
        return {}


def _user_to_endpoint(user: dict) -> str | None:
    if not user:
        return None
    ip = user.get('ip')
    port = user.get('port', 8787)
    if not ip:
        return None
    return f'http://{ip}:{port}'


def _gateway_url_for_principal(fleet: dict, principal: str) -> str | None:
    """Compute the Caddy gateway URL for a principal's container.
       Prefers HTTPS via configured DNS hostname; falls back to raw IP/HTTP
       so the same field works during DNS-not-yet-set development."""
    import hashlib
    gw = fleet.get('gateway') or {}
    slug = hashlib.sha256(principal.encode()).hexdigest()[:16]
    host = gw.get('public_hostname')        # set this once DNS is wired
    if host:
        return f'https://{host}/u/{slug}'
    ip = gw.get('public_ip')
    if ip:
        return f'http://{ip}/u/{slug}'
    return None


def _load_fleet_full() -> dict:
    if not FLEET_FILE.exists():
        return {}
    try:
        return json.loads(FLEET_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _validate_principal(p: str) -> bool:
    if not p or len(p) > 100:
        return False
    return bool(_PRINCIPAL_RE.match(p))


# ── Workspace templates + sessions ──────────────────────────────────────────
def _load_workspaces() -> list:
    """Load built-in templates from workspaces.json."""
    if not WORKSPACES_FILE.exists():
        return []
    try:
        return json.loads(WORKSPACES_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        log.error(f'workspaces.json read error: {e}')
        return []


def _load_custom_templates() -> list:
    """Load user-onboarded custom templates from fleet.json."""
    fleet = _load_fleet_full()
    return fleet.get('custom_templates', [])


def _save_custom_template(template: dict):
    """Add or update a custom template in fleet.json."""
    fleet = _load_fleet_full()
    customs = fleet.get('custom_templates', [])
    # Upsert by id
    idx = next((i for i, t in enumerate(customs) if t['id'] == template['id']), None)
    if idx is not None:
        customs[idx] = template
    else:
        customs.append(template)
    fleet['custom_templates'] = customs
    try:
        FLEET_FILE.write_text(json.dumps(fleet, indent=2, default=str), encoding='utf-8')
    except Exception as e:
        log.error(f'fleet.json write error (custom template): {e}')


def _delete_custom_template(template_id: str) -> bool:
    """Remove a custom template from fleet.json. Returns True if found."""
    fleet = _load_fleet_full()
    customs = fleet.get('custom_templates', [])
    before = len(customs)
    customs = [t for t in customs if t['id'] != template_id]
    if len(customs) == before:
        return False
    fleet['custom_templates'] = customs
    try:
        FLEET_FILE.write_text(json.dumps(fleet, indent=2, default=str), encoding='utf-8')
    except Exception as e:
        log.error(f'fleet.json write error (custom template delete): {e}')
    return True


def _load_all_templates() -> list:
    """Merge built-in + custom templates. Custom are appended after built-in."""
    builtin = _load_workspaces()
    custom  = _load_custom_templates()
    return builtin + custom


def _load_sessions() -> dict:
    """Load sessions map from fleet.json."""
    fleet = _load_fleet_full()
    return fleet.get('sessions', {})


def _save_session(session_id: str, session: dict):
    """Upsert a session into fleet.json sessions map."""
    fleet = _load_fleet_full()
    if 'sessions' not in fleet:
        fleet['sessions'] = {}
    fleet['sessions'][session_id] = session
    try:
        FLEET_FILE.write_text(json.dumps(fleet, indent=2, default=str), encoding='utf-8')
    except Exception as e:
        log.error(f'fleet.json write error: {e}')


def _delete_session_record(session_id: str):
    """Remove a session from fleet.json."""
    fleet = _load_fleet_full()
    sessions = fleet.get('sessions', {})
    if session_id in sessions:
        del sessions[session_id]
        fleet['sessions'] = sessions
        try:
            FLEET_FILE.write_text(json.dumps(fleet, indent=2, default=str), encoding='utf-8')
        except Exception as e:
            log.error(f'fleet.json write error: {e}')


# ── Hyper-V provider (lazy init) ──────────────────────────────────────────────
def _get_hyperv_provider():
    """Lazily initialize the HyperVProvider singleton."""
    global HYPERV_PROVIDER
    if HYPERV_PROVIDER is None:
        try:
            from importlib.util import spec_from_file_location, module_from_spec
            spec = spec_from_file_location(
                "hyperv_provider", FLEET_DIR / "hyperv-provider.py"
            )
            mod = module_from_spec(spec)
            spec.loader.exec_module(mod)
            config = {
                "gold_images_path": os.environ.get(
                    "HYPERV_GOLD_PATH", r"C:\HyperV\GoldImages"
                ),
                "workspace_vm_path": os.environ.get(
                    "HYPERV_WORKSPACE_PATH", r"C:\HyperV\Workspaces"
                ),
                "vswitch_name": os.environ.get("HYPERV_VSWITCH", "Default Switch"),
                "sunshine_timeout": int(os.environ.get("SUNSHINE_TIMEOUT", "120")),
            }
            HYPERV_PROVIDER = mod.HyperVProvider(config)
            log.info("HyperVProvider initialized: gold=%s, workspaces=%s",
                     config["gold_images_path"], config["workspace_vm_path"])
        except Exception as e:
            log.error("Failed to init HyperVProvider: %s", e)
            # Return a dummy so callers don't crash
            HYPERV_PROVIDER = None
    return HYPERV_PROVIDER


def _get_local_provider():
    """Lazily initialize the LocalProvider singleton."""
    global LOCAL_PROVIDER
    if LOCAL_PROVIDER is None:
        try:
            from importlib.util import spec_from_file_location, module_from_spec
            spec = spec_from_file_location(
                "local_provider", FLEET_DIR / "local-provider.py"
            )
            mod = module_from_spec(spec)
            spec.loader.exec_module(mod)
            config = {
                'ttyd_path':  os.environ.get('TTYD_PATH', r'C:\CafresoAI\ttyd.exe'),
                'wsl_distro': os.environ.get('WSL_DISTRO', 'Ubuntu'),
                'base_port':  int(os.environ.get('LOCAL_BASE_PORT', '7680')),
            }
            LOCAL_PROVIDER = mod.LocalProvider(config)
            log.info('LocalProvider initialized: ttyd=%s, distro=%s, base_port=%s',
                     config['ttyd_path'], config['wsl_distro'], config['base_port'])
        except Exception as e:
            log.error('Failed to init LocalProvider: %s', e)
            LOCAL_PROVIDER = None
    return LOCAL_PROVIDER


def _generate_turn_credentials(session_id: str, ttl: int = 86400):
    """Generate HMAC time-limited TURN credentials for a session.
    Returns (username, credential) tuple compatible with coturn's
    use-auth-secret / static-auth-secret scheme.

    username = "expiry_timestamp:session_id"
    credential = HMAC-SHA1(secret, username)
    """
    import hmac
    import hashlib
    import base64

    turn_secret = os.environ.get('TURN_SECRET', '').strip()
    if not turn_secret:
        return '', ''

    expiry = int(time.time()) + ttl
    username = f"{expiry}:{session_id}"
    mac = hmac.new(
        turn_secret.encode(), username.encode(), hashlib.sha1
    ).digest()
    credential = base64.b64encode(mac).decode()
    return username, credential


# ── HTTP handler ─────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'CafresoAI-Fleet-API/1.0'

    def log_message(self, fmt, *args):
        log.info(f'{self.address_string()} - {fmt % args}')

    # ── helpers ─────────────────────────────────────────────────────────────
    def _cors(self):
        origin = self.headers.get('Origin', '')
        allowed = origin if origin in ALLOWED_ORIGINS else (
            ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else '*'
        )
        self.send_header('Access-Control-Allow-Origin', allowed)
        self.send_header('Access-Control-Allow-Credentials', 'true')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        # X-Session-Token carries the on-chain identity (_caller_principal) —
        # omitting it here silently breaks every browser call: the preflight
        # succeeds, but the browser then blocks the real request as a
        # disallowed header, the fetch throws, and the client falls back to
        # the bundled demo catalog with no visible error. Confirmed live 2026-07-21.
        self.send_header('Access-Control-Allow-Headers',
                         'Content-Type, X-Fleet-Auth, X-User-Principal, X-Session-Token')
        self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Max-Age', '86400')

    def _send_json(self, code: int, payload: dict):
        body = json.dumps(payload, default=str).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _check_auth(self) -> bool:
        if not SHARED_SECRET:
            # Original portal silently ran open with no secret. Refuse instead:
            # explicit CAFRESOHQ_DEV=1 is required for an unauthenticated server.
            return DEV_MODE
        return self.headers.get('X-Fleet-Auth') == SHARED_SECRET

    def _caller_principal(self, body: dict | None = None,
                          query_principal: str = '') -> str | None:
        """Trusted caller identity. Order:
        1. on-chain session token — body {'token': ...} or X-Session-Token header
        2. explicit principal (query/body) — ONLY for admin callers or dev mode,
           since a bare principal is spoofable by anyone holding the secret."""
        tok = ''
        if body and isinstance(body.get('token'), str):
            tok = body['token']
        if not tok:
            tok = (self.headers.get('X-Session-Token') or '').strip()
        p = _principal_from_token(tok)
        if p:
            return p
        fallback = (query_principal or (body or {}).get('principal') or
                    self.headers.get('X-User-Principal') or '').strip()
        if fallback and _validate_principal(fallback) and (DEV_MODE or self._is_fleet_admin()):
            return fallback
        return None

    def _is_fleet_admin(self) -> bool:
        """Admin = shared secret AND a principal on the admin list. In the
        original portal the secret alone unlocked /admin/* — now the header
        principal must also match (v1 trusts secret-holders not to spoof it;
        an admin-signed token is the v2 upgrade)."""
        if DEV_MODE:
            return True
        if not SHARED_SECRET or self.headers.get('X-Fleet-Auth') != SHARED_SECRET:
            return False
        principal = (self.headers.get('X-User-Principal') or '').strip()
        return bool(FLEET_ADMIN_PRINCIPALS) and principal in FLEET_ADMIN_PRINCIPALS

    def _portal_gate(self, principal: str | None) -> bool:
        """Shared guard for catalog + launch: kill switch, then entitlement.
        Sends the error response itself; returns True when the caller may
        proceed."""
        if _workspaces_killed():
            self._send_json(503, {'error': 'workspaces_disabled',
                                  'message': 'Workspaces are switched off network-wide.'})
            return False
        if not principal:
            self._send_json(401, {'error': 'session_token_required',
                                  'message': 'Sign in and retry — a principal-bound session token is required.'})
            return False
        if not _workspace_allowed(principal):
            ws = _operator_config().get('workspaces') or {}
            self._send_json(403, {'error': 'not_entitled',
                                  'message': ws.get('message') or 'Workspaces are in private preview.'})
            return False
        return True

    def _stream_proxy(self, host: str, port: int, path: str):
        """Low-level TCP splice proxy.
        Forwards the current HTTP/WebSocket request to (host:port), rewriting
        the path and Host header. Handles both plain HTTP responses and the
        WebSocket 101-upgrade transparently — no WebSocket library needed,
        once headers are forwarded the rest is pure byte forwarding.
        Called from do_GET when the path is /stream/{sid}/...
        """
        try:
            backend = socket.create_connection((host, port), timeout=5)
        except OSError as e:
            log.warning('[stream-proxy] backend %s:%s unreachable: %s', host, port, e)
            return self._send_json(502, {'error': f'backend {host}:{port} unreachable: {e}'})

        # Reconstruct the request line + headers and forward to backend.
        # BaseHTTPRequestHandler has already consumed the request line + headers
        # from self.rfile, so we rebuild them from parsed fields.
        req_lines = [f'{self.command} {path} {self.protocol_version}\r\n']
        for k, v in self.headers.items():
            if k.lower() == 'host':
                req_lines.append(f'Host: {host}:{port}\r\n')
            else:
                req_lines.append(f'{k}: {v}\r\n')
        req_lines.append('\r\n')

        try:
            backend.sendall(''.join(req_lines).encode('latin-1'))
            clen = int(self.headers.get('Content-Length', 0) or 0)
            if clen > 0:
                backend.sendall(self.rfile.read(clen))
        except OSError as e:
            backend.close()
            log.warning('[stream-proxy] backend write error: %s', e)
            return self._send_json(502, {'error': f'backend write error: {e}'})

        # Splice: two threads copy bytes in opposite directions until either
        # side closes. Works identically for HTTP and WebSocket (101 upgrade).
        client = self.connection
        stop   = threading.Event()

        def _copy(src, dst, label):
            try:
                while not stop.is_set():
                    data = src.recv(65536)
                    if not data:
                        break
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                stop.set()
                with contextlib.suppress(OSError):
                    dst.shutdown(socket.SHUT_WR)

        t = threading.Thread(target=_copy, args=(backend, client, 'b->c'), daemon=True)
        t.start()
        _copy(client, backend, 'c->b')   # blocks until client closes
        stop.set()
        t.join(timeout=2)
        with contextlib.suppress(OSError):
            backend.close()
        self.close_connection = True     # tell http.server not to read another req

    # ── routes ──────────────────────────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Content-Length', '0')
        self._cors()
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == '/fleet/health':
            return self._send_json(200, {
                'status':  'ok',
                'service': 'cafresoai-fleet-api',
                'auth':    'configured' if SHARED_SECRET else 'dev-mode',
                'fleet_file': str(FLEET_FILE),
                'fleet_file_exists': FLEET_FILE.exists(),
            })

        # ── Prometheus metrics (no auth required) ──────────────────────
        if u.path == '/metrics':
            body = _render_prometheus_metrics().encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type',
                             'text/plain; version=0.0.4; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        if not self._check_auth():
            return self._send_json(401, {'error': 'unauthorized'})

        if u.path == '/fleet/lookup':
            params    = urllib.parse.parse_qs(u.query)
            principal = (params.get('principal') or [''])[0].strip()
            if not _validate_principal(principal):
                return self._send_json(400, {'error': 'invalid principal'})
            full = _load_fleet_full()
            user = full.get('users', {}).get(principal)
            if not user:
                return self._send_json(404, {
                    'error':     'no container for principal',
                    'principal': principal,
                })
            return self._send_json(200, {
                'principal':    principal,
                'endpoint':     _user_to_endpoint(user),
                'gateway_url':  _gateway_url_for_principal(full, principal),
                'status':       user.get('status'),
                'container_id': user.get('container_instance_id'),
                'created_at':   user.get('created_at'),
                'vault_prefix': user.get('vault_prefix'),
            })

        if u.path.startswith('/fleet/job/'):
            job_id = u.path[len('/fleet/job/'):]
            with _jobs_lock:
                job = _jobs.get(job_id)
            if not job:
                return self._send_json(404, {'error': 'unknown job'})
            return self._send_json(200, dict(job))

        # ── Workspace template catalog (built-in + user-onboarded) ─────
        if u.path == '/workspaces/templates':
            params    = urllib.parse.parse_qs(u.query)
            principal = self._caller_principal(
                query_principal=(params.get('principal') or [''])[0].strip())
            if not self._portal_gate(principal):
                return
            all_tmpls = _load_all_templates()
            # Filter by allowed_principals:
            #   missing / null  → visible to everyone
            #   []              → restricted but nobody whitelisted yet (hidden)
            #   [p1, p2, ...]   → only those principals can see it
            templates = []
            for t in all_tmpls:
                ap = t.get('allowed_principals')
                if ap is None:                    # no restriction
                    templates.append(t)
                elif isinstance(ap, list) and principal and principal in ap:
                    templates.append(t)           # principal is whitelisted
                # else: restricted and caller not in list — omit
            cats = {}
            for t in templates:
                c = t.get('category', 'custom')
                cats[c] = cats.get(c, 0) + 1
            return self._send_json(200, {
                'templates':  templates,
                'categories': cats,
                'total':      len(templates),
            })

        if u.path.startswith('/workspaces/templates/'):
            tid = u.path[len('/workspaces/templates/'):]
            tmpl = next((t for t in _load_all_templates() if t['id'] == tid), None)
            if not tmpl:
                return self._send_json(404, {'error': 'template not found'})
            return self._send_json(200, tmpl)

        # ── Session queries ─────────────────────────────────────────────
        if u.path == '/sessions':
            params    = urllib.parse.parse_qs(u.query)
            principal = self._caller_principal(
                query_principal=(params.get('principal') or [''])[0].strip())
            if not self._portal_gate(principal):
                return
            sessions = _load_sessions()
            # Callers only ever see their OWN sessions; the all-users view
            # lives at /admin/sessions behind the admin gate.
            user_sessions = [
                s for s in sessions.values()
                if s.get('principal') == principal
            ]
            return self._send_json(200, {'sessions': user_sessions})

        # GET /sessions/{id}/metrics — VM resource metrics
        if u.path.startswith('/sessions/') and u.path.endswith('/metrics'):
            sid = u.path[len('/sessions/'):-len('/metrics')]
            sessions = _load_sessions()
            session = sessions.get(sid)
            if not session:
                return self._send_json(404, {'error': 'session not found'})
            metrics = {'session_id': sid, 'status': session.get('status')}
            if session.get('provider') == 'hyperv' and session.get('provider_id'):
                provider = _get_hyperv_provider()
                if provider:
                    vm_status = provider.get_vm_status(session['provider_id'])
                    if vm_status:
                        metrics.update({
                            'cpu_usage':     vm_status.get('cpu_usage', 0),
                            'memory_mb':     vm_status.get('memory_assigned_mb', 0),
                            'memory_demand_mb': vm_status.get('memory_demand_mb', 0),
                            'uptime_seconds': vm_status.get('uptime_seconds', 0),
                            'vm_state':      vm_status.get('state', 'unknown'),
                        })
            return self._send_json(200, metrics)

        if u.path.startswith('/sessions/'):
            sid = u.path[len('/sessions/'):]
            sessions = _load_sessions()
            session = sessions.get(sid)
            if not session:
                return self._send_json(404, {'error': 'session not found'})
            return self._send_json(200, session)

        # ── Admin endpoints ────────────────────────────────────────────
        # Hardened: data endpoints demand the admin PRINCIPAL, not just the
        # shared secret (the original portal's gap). /admin/verify stays open
        # to any authed caller — it merely answers "am I admin?".
        if u.path == '/admin/verify':
            return self._admin_verify()

        if u.path in ('/admin/dashboard', '/admin/sessions', '/admin/infrastructure'):
            if not self._is_fleet_admin():
                return self._send_json(403, {'error': 'admin_principal_required'})
            if u.path == '/admin/dashboard':
                return self._admin_dashboard()
            if u.path == '/admin/sessions':
                return self._admin_sessions()
            return self._admin_infrastructure()

        # ── Guacamole desktop proxy (/guacamole/...) ──────────────────────
        # Plain pass-through to the local Guacamole web app for hyperv
        # workspaces. Auth is supplied via a token already baked into the
        # iframe URL by _hyperv_provision_worker (pre-fetched at session
        # launch using credentials in user-mapping.xml); no header injection
        # needed because the file-auth provider's connections only surface
        # when the token came from that same provider.
        if u.path.startswith('/guacamole/'):
            guac_path = u.path + (('?' + u.query) if u.query else '')
            return self._stream_proxy('127.0.0.1', 8484, guac_path)

        # ── Stream proxy (/stream/{sid}/...) ──────────────────────────────
        # Routes browser traffic to the local streaming backend:
        #   local    → ttyd WebSocket terminal on localhost:{port}
        #   hyperv   → 302 redirect to the per-session Guacamole URL
        if u.path.startswith('/stream/'):
            tail  = u.path[len('/stream/'):]           # 'ses_abc/ws' or 'ses_abc/'
            slash = tail.find('/')
            if slash < 0:
                sid  = tail
                rest = '/'
            else:
                sid  = tail[:slash]
                rest = tail[slash:] or '/'
            if u.query:
                rest = rest + '?' + u.query

            if not sid:
                return self._send_json(400, {'error': 'missing session id in stream path'})

            sessions = _load_sessions()
            session  = sessions.get(sid)
            if not session:
                return self._send_json(404, {'error': 'stream session not found'})
            if session.get('status') not in ('running', 'starting'):
                return self._send_json(410, {
                    'error':  'session not running',
                    'status': session.get('status'),
                })

            provider = session.get('provider')
            if provider == 'local':
                b_port = session.get('port')
                if not b_port:
                    return self._send_json(502, {'error': 'no port recorded in session'})
                log.info('[stream-proxy] local session %s -> localhost:%s%s', sid, b_port, rest)
                return self._stream_proxy('127.0.0.1', b_port, rest)

            elif provider == 'hyperv':
                # Phase 2c compat: if a guacamole_url is stored on the session
                # (legacy sessions launched before Phase 2d), redirect there.
                guac_url   = session.get('guacamole_url', '')
                guac_token = session.get('guacamole_token', '')
                if guac_url:
                    sep = '&' if '?' in guac_url else '?'
                    target_url = f"{guac_url}{sep}token={guac_token}" if guac_token else guac_url
                    body = (
                        f'<!doctype html><meta http-equiv="refresh" content="0;url={target_url}">'
                        f'<p>Connecting to <a href="{target_url}">desktop</a>...</p>'
                    ).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self._cors()
                    self.end_headers()
                    self.wfile.write(body)
                    log.info('[stream-proxy] hyperv %s -> guacamole redirect %s', sid, target_url)
                    return

                # Phase 2d: moonlight-web-stream sidecar proxy.
                # The sidecar container runs on *this host* (ASERVER), so the
                # proxy destination is always 127.0.0.1:{moonlight_port}.
                # Only fall back to the VM's Sunshine HTTP port if no sidecar
                # is running (e.g. during pool-warmup or first-launch race).
                ml_port = session.get('moonlight_port')
                if ml_port:
                    log.info('[stream-proxy] hyperv %s -> moonlight@localhost:%s%s',
                             sid, ml_port, rest)
                    return self._stream_proxy('127.0.0.1', ml_port, rest)

                # Last resort: proxy raw to Sunshine HTTP port on the VM.
                b_host = session.get('ip', '10.0.0.19')
                b_port = session.get('sunshine_http_port', 47990)
                log.info('[stream-proxy] hyperv %s -> sunshine@%s:%s%s', sid, b_host, b_port, rest)
                return self._stream_proxy(b_host, b_port, rest)

            else:
                return self._send_json(501, {
                    'error': f'stream proxy not implemented for provider: {provider}'
                })

        return self._send_json(404, {'error': 'not found'})

    def do_DELETE(self):
        if not self._check_auth():
            return self._send_json(401, {'error': 'unauthorized'})
        u = urllib.parse.urlparse(self.path)

        # DELETE /workspaces/templates/<id> — remove a custom template.
        # Only the template's owner (token-verified) or a fleet admin may.
        if u.path.startswith('/workspaces/templates/'):
            tid = u.path[len('/workspaces/templates/'):]
            if not tid.startswith('custom-'):
                return self._send_json(403, {
                    'error': 'only custom (user-onboarded) templates can be deleted'
                })
            caller = self._caller_principal()
            tmpl = next((t for t in _load_custom_templates() if t.get('id') == tid), None)
            owner = (tmpl or {}).get('owner_principal') or ''
            if not (self._is_fleet_admin() or (caller and caller == owner)):
                return self._send_json(403, {'error': 'not_owner'})
            if _delete_custom_template(tid):
                return self._send_json(200, {
                    'template_id': tid, 'status': 'deleted'
                })
            return self._send_json(404, {'error': 'custom template not found'})

        # DELETE /sessions/<id> — terminate a session + clean up resources.
        # Only the session's owner (token-verified) or a fleet admin may.
        if u.path.startswith('/sessions/'):
            sid = u.path[len('/sessions/'):]
            sessions = _load_sessions()
            session = sessions.get(sid)
            if not session:
                return self._send_json(404, {'error': 'session not found'})
            caller = self._caller_principal()
            if not (self._is_fleet_admin() or
                    (caller and caller == session.get('principal'))):
                return self._send_json(403, {'error': 'not_owner'})
            # Clean up backing resource based on provider
            if session.get('provider') == 'hyperv':
                threading.Thread(
                    target=_hyperv_stop_worker, args=(sid,), daemon=True,
                ).start()
            elif session.get('provider') == 'local':
                lp = _get_local_provider()
                if lp:
                    lp.stop(sid)
            _delete_session_record(sid)
            return self._send_json(200, {
                'session_id': sid,
                'status': 'terminated',
            })
        return self._send_json(404, {'error': 'not found'})

    def do_POST(self):
        if not self._check_auth():
            return self._send_json(401, {'error': 'unauthorized'})

        # ── Session launch ──────────────────────────────────────────────
        if self.path == '/sessions/launch':
            length = int(self.headers.get('Content-Length', 0) or 0)
            try:
                req = json.loads(self.rfile.read(length) or b'{}')
            except Exception:
                return self._send_json(400, {'error': 'bad json'})
            # Identity comes from the on-chain session token; the bare
            # principal field is dev/admin-only (see _caller_principal).
            principal   = self._caller_principal(body=req)
            template_id = (req.get('template_id') or '').strip()
            if not self._portal_gate(principal):
                return
            if not template_id:
                return self._send_json(400, {'error': 'template_id required'})

            # Find template (built-in + user-onboarded)
            templates = _load_all_templates()
            tmpl = next((t for t in templates if t['id'] == template_id), None)
            if not tmpl:
                return self._send_json(404, {'error': 'template not found'})
            if not tmpl.get('enabled', False):
                return self._send_json(400, {'error': 'template is disabled'})
            # Per-template allowlist re-checked at LAUNCH, not just catalog
            # visibility — the original portal's gap.
            ap = tmpl.get('allowed_principals')
            if isinstance(ap, list) and principal not in ap:
                return self._send_json(403, {'error': 'not_entitled_to_template'})

            provider = tmpl.get('provider', 'oci')

            # ── Per-user session limit ─────────────────────────────────
            if provider not in ('canister',):
                allowed, limit_msg = _check_user_session_limit(principal)
                if not allowed:
                    return self._send_json(429, {'error': limit_msg})

            # ── Canister: instant, no provisioning ──────────────────────
            if provider == 'canister':
                sid = 'ses_' + uuid.uuid4().hex[:12]
                import datetime
                session = {
                    'session_id':      sid,
                    'principal':       principal,
                    'template_id':     template_id,
                    'display_name':    tmpl.get('name', template_id),
                    'status':          'running',
                    'provider':        'canister',
                    'provider_id':     tmpl.get('canister_id', ''),
                    'stream_protocol': 'canister',
                    'stream_url':      tmpl.get('canister_url', ''),
                    'persistent':      True,
                    'created_at':      datetime.datetime.utcnow().isoformat() + 'Z',
                }
                _save_session(sid, session)
                return self._send_json(200, session)

            # ── OCI: reuse existing fleet provision flow ────────────────
            if provider == 'oci':
                # Check for existing running session for this principal + template
                sessions = _load_sessions()
                for s in sessions.values():
                    if (s.get('principal') == principal and
                        s.get('template_id') == template_id and
                        s.get('status') in ('running', 'starting')):
                        return self._send_json(200, s)

                # Check if container already exists via fleet
                full     = _load_fleet_full()
                existing = full.get('users', {}).get(principal)
                if existing and existing.get('ip'):
                    sid = 'ses_' + uuid.uuid4().hex[:12]
                    stream_proto = tmpl.get('stream_protocol', 'iframe')
                    ip = existing.get('ip')
                    import datetime

                    # WebRTC OCI containers (Selkies) — stream URL points to
                    # the Selkies signaling endpoint inside the container
                    if stream_proto == 'webrtc':
                        selkies_port = tmpl.get('selkies_port', 8080)
                        gw_url = _gateway_url_for_principal(full, principal)
                        stream_url = f'https://{(full.get("gateway") or {}).get("public_hostname", "hq.cafreso.com")}/stream/{sid}/'
                        # Generate TURN creds for NAT traversal
                        turn_user, turn_cred = _generate_turn_credentials(sid)
                        turn_url = os.environ.get('TURN_URL', '')
                        turn_servers = [{'urls': turn_url, 'username': turn_user, 'credential': turn_cred}] if turn_url else []
                        session = {
                            'session_id':      sid,
                            'principal':       principal,
                            'template_id':     template_id,
                            'display_name':    tmpl.get('name', template_id),
                            'status':          'running',
                            'provider':        'oci',
                            'provider_id':     existing.get('container_instance_id', ''),
                            'ip':              ip,
                            'port':            selkies_port,
                            'stream_protocol': 'webrtc',
                            'stream_url':      stream_url,
                            'selkies_port':    selkies_port,
                            'signaling_mode':  'selkies',
                            'turn_servers':    turn_servers,
                            'region':          full.get('region', ''),
                            'resources':       tmpl.get('resources', {}),
                            'persistent':      tmpl.get('persistent', True),
                            'created_at':      datetime.datetime.utcnow().isoformat() + 'Z',
                        }
                    else:
                        # iframe / other — existing pattern
                        stream_path = tmpl.get('stream_path', '/hq.html')
                        gw_url = _gateway_url_for_principal(full, principal)
                        ep_url = _user_to_endpoint(existing)
                        stream_url = (gw_url or ep_url or '') + stream_path
                        session = {
                            'session_id':      sid,
                            'principal':       principal,
                            'template_id':     template_id,
                            'display_name':    tmpl.get('name', template_id),
                            'status':          'running',
                            'provider':        'oci',
                            'provider_id':     existing.get('container_instance_id', ''),
                            'ip':              ip,
                            'port':            existing.get('port', 8787),
                            'stream_protocol': stream_proto,
                            'stream_url':      stream_url,
                            'region':          full.get('region', ''),
                            'resources':       tmpl.get('resources', {}),
                            'persistent':      tmpl.get('persistent', True),
                            'created_at':      datetime.datetime.utcnow().isoformat() + 'Z',
                        }
                    _save_session(sid, session)
                    return self._send_json(200, session)

                # No container yet — provision via fleet-manager (async)
                sid = 'ses_' + uuid.uuid4().hex[:12]
                import datetime
                session = {
                    'session_id':      sid,
                    'principal':       principal,
                    'template_id':     template_id,
                    'display_name':    tmpl.get('name', template_id),
                    'status':          'starting',
                    'provider':        'oci',
                    'stream_protocol': tmpl.get('stream_protocol', 'iframe'),
                    'resources':       tmpl.get('resources', {}),
                    'persistent':      tmpl.get('persistent', True),
                    'created_at':      datetime.datetime.utcnow().isoformat() + 'Z',
                }
                _save_session(sid, session)
                threading.Thread(
                    target=_session_provision_worker,
                    args=(sid, principal, tmpl),
                    daemon=True
                ).start()
                return self._send_json(202, session)

            # ── Hyper-V: create VM from gold image ─────────────────────
            if provider == 'hyperv':
                # Check for existing running session for this principal + template
                sessions = _load_sessions()
                for s in sessions.values():
                    if (s.get('principal') == principal and
                        s.get('template_id') == template_id and
                        s.get('status') in ('running', 'starting')):
                        return self._send_json(200, s)

                sid = 'ses_' + uuid.uuid4().hex[:12]
                import datetime
                session = {
                    'session_id':      sid,
                    'principal':       principal,
                    'template_id':     template_id,
                    'display_name':    tmpl.get('name', template_id),
                    'status':          'starting',
                    'provider':        'hyperv',
                    'stream_protocol': tmpl.get('stream_protocol', 'webrtc'),
                    'resources':       tmpl.get('resources', {}),
                    'persistent':      tmpl.get('persistent', True),
                    'created_at':      datetime.datetime.utcnow().isoformat() + 'Z',
                }
                _save_session(sid, session)
                threading.Thread(
                    target=_hyperv_provision_worker,
                    args=(sid, principal, tmpl),
                    daemon=True,
                ).start()
                return self._send_json(202, session)

            # ── Local: WSL+ttyd on the Hyper-V host ───────────────────
            if provider == 'local':
                import datetime
                lp = _get_local_provider()
                if lp is None:
                    return self._send_json(503, {
                        'error': 'LocalProvider unavailable (ttyd not found?)'
                    })

                sid = 'ses_' + uuid.uuid4().hex[:12]
                try:
                    port = lp.launch(sid, tmpl)
                except RuntimeError as e:
                    return self._send_json(500, {'error': str(e)})

                # Build stream_url — Caddy will proxy /stream/{sid}/ → localhost:{port}.
                # This session runs on THIS host, not the OCI gateway.
                fleet = _load_fleet_full()
                gw = fleet.get('gateway', {})
                hostname = WORKSPACES_PUBLIC_HOSTNAME or gw.get('public_hostname', 'hq.cafreso.com')
                stream_url = f'https://{hostname}/stream/{sid}/'

                session = {
                    'session_id':      sid,
                    'principal':       principal,
                    'template_id':     template_id,
                    'display_name':    tmpl.get('name', template_id),
                    'status':          'running',
                    'provider':        'local',
                    'provider_id':     '',
                    'ip':              '127.0.0.1',
                    'port':            port,
                    'stream_protocol': 'iframe',
                    'stream_url':      stream_url,
                    'wsl_command':     tmpl.get('wsl_command', 'bash'),
                    'persistent':      tmpl.get('persistent', False),
                    'created_at':      datetime.datetime.utcnow().isoformat() + 'Z',
                }
                _save_session(sid, session)

                # Reload Caddy so the /stream/{sid}/* route is live immediately
                ok, msg = _reload_caddy_with_new_routes()
                if not ok:
                    log.warning('[local] caddy reload non-fatal: %s', msg)

                log.info('[local] session %s → ttyd :%d', sid, port)
                return self._send_json(200, session)

            # ── Custom (user-onboarded VM/endpoint) ────────────────────
            if provider == 'custom':
                sid = 'ses_' + uuid.uuid4().hex[:12]
                import datetime
                host = tmpl.get('custom_host', '')
                port = tmpl.get('custom_port', 47989)
                proto = tmpl.get('stream_protocol', 'webrtc')
                stream_url = f"https://{host}:{port}" if host else ''
                session = {
                    'session_id':      sid,
                    'principal':       principal,
                    'template_id':     template_id,
                    'display_name':    tmpl.get('name', template_id),
                    'status':          'running',
                    'provider':        'custom',
                    'ip':              host,
                    'port':            port,
                    'stream_protocol': proto,
                    'stream_url':      stream_url,
                    'resources':       tmpl.get('resources', {}),
                    'persistent':      True,
                    'created_at':      datetime.datetime.utcnow().isoformat() + 'Z',
                }
                _save_session(sid, session)
                return self._send_json(200, session)

            return self._send_json(400, {'error': f'unknown provider: {provider}'})

        # ── Custom template CRUD (user-onboarded VMs) ──────────────────
        if self.path == '/workspaces/templates':
            length = int(self.headers.get('Content-Length', 0) or 0)
            try:
                req = json.loads(self.rfile.read(length) or b'{}')
            except Exception:
                return self._send_json(400, {'error': 'bad json'})

            principal = self._caller_principal(body=req)
            if not self._portal_gate(principal):
                return
            name       = (req.get('name') or '').strip()
            host       = (req.get('host') or '').strip()
            port       = int(req.get('port', 0) or 0)
            protocol   = (req.get('protocol') or 'webrtc').strip()
            icon       = (req.get('icon') or 'monitor').strip()
            desc       = (req.get('description') or '').strip()

            if not name:
                return self._send_json(400, {'error': 'name required'})
            if not host:
                return self._send_json(400, {'error': 'host (IP or hostname) required'})
            if port < 1 or port > 65535:
                return self._send_json(400, {'error': 'port must be 1-65535'})
            if protocol not in ('webrtc', 'websocket', 'iframe', 'rdp'):
                return self._send_json(400, {
                    'error': 'protocol must be webrtc, websocket, iframe, or rdp'
                })

            # Generate a unique id
            tid = 'custom-' + uuid.uuid4().hex[:8]
            import datetime
            template = {
                'id':               tid,
                'name':             name,
                'description':      desc or f'User-onboarded VM at {host}:{port}',
                'category':         'custom',
                'icon':             icon,
                'provider':         'custom',
                'custom_host':      host,
                'custom_port':      port,
                'stream_protocol':  protocol,
                'resources':        {},
                'persistent':       True,
                'enabled':          True,
                'sort_order':       50,
                'owner_principal':  principal,
                'created_at':       datetime.datetime.utcnow().isoformat() + 'Z',
                'tags':             ['custom'],
            }
            _save_custom_template(template)
            log.info(f'Custom template created: {tid} ({name}) by {principal[:16]}...')
            return self._send_json(201, template)

        # ── Session stop ────────────────────────────────────────────────
        if self.path.startswith('/sessions/') and self.path.endswith('/stop'):
            sid = self.path[len('/sessions/'):-len('/stop')]
            sessions = _load_sessions()
            session = sessions.get(sid)
            if not session:
                return self._send_json(404, {'error': 'session not found'})
            caller = self._caller_principal()
            if not (self._is_fleet_admin() or
                    (caller and caller == session.get('principal'))):
                return self._send_json(403, {'error': 'not_owner'})
            session['status'] = 'stopping'
            _save_session(sid, session)

            # Stop the backing resource based on provider
            provider = session.get('provider', '')
            if provider == 'hyperv':
                threading.Thread(
                    target=_hyperv_stop_worker,
                    args=(sid,),
                    daemon=True,
                ).start()
            elif provider == 'local':
                lp = _get_local_provider()
                if lp:
                    lp.stop(sid)
                session['status'] = 'stopped'
                _save_session(sid, session)
                # Reload Caddy to remove the stream route
                ok, msg = _reload_caddy_with_new_routes()
                if not ok:
                    log.warning('[local-stop] caddy reload non-fatal: %s', msg)
            elif provider == 'canister':
                # Canisters don't need stopping
                session['status'] = 'stopped'
                _save_session(sid, session)
            else:
                # OCI / custom — mark stopped (container cleanup is separate)
                session['status'] = 'stopped'
                _save_session(sid, session)

            return self._send_json(200, {
                'session_id': sid,
                'status': session.get('status', 'stopping'),
            })

        # ── Admin: force-kill a session ────────────────────────────────
        if self.path.startswith('/admin/sessions/') and self.path.endswith('/kill'):
            if not self._is_fleet_admin():
                return self._send_json(403, {'error': 'admin_principal_required'})
            sid = self.path[len('/admin/sessions/'):-len('/kill')]
            sessions = _load_sessions()
            session = sessions.get(sid)
            if not session:
                return self._send_json(404, {'error': 'session not found'})
            # Force-stop the backing resource
            if session.get('provider') == 'hyperv':
                threading.Thread(
                    target=_hyperv_stop_worker, args=(sid,), daemon=True,
                ).start()
            elif session.get('provider') == 'local':
                lp = _get_local_provider()
                if lp:
                    lp.stop(sid)
            session['status'] = 'stopped'
            _save_session(sid, session)
            log.info(f'Admin killed session {sid} ({session.get("display_name")})')
            return self._send_json(200, {
                'session_id': sid,
                'status': 'killed',
            })

        if self.path != '/fleet/provision':
            return self._send_json(404, {'error': 'not found'})

        length = int(self.headers.get('Content-Length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})
        principal = (req.get('principal') or '').strip()
        if not _validate_principal(principal):
            return self._send_json(400, {'error': 'invalid principal'})

        # Already provisioned? Return existing endpoint.
        full     = _load_fleet_full()
        existing = full.get('users', {}).get(principal)
        if existing and existing.get('ip'):
            return self._send_json(200, {
                'status':       'existing',
                'principal':    principal,
                'endpoint':     _user_to_endpoint(existing),
                'gateway_url':  _gateway_url_for_principal(full, principal),
                'container_id': existing.get('container_instance_id'),
            })

        # Spawn a job — provisioning takes ~60-90s end-to-end.
        job_id = uuid.uuid4().hex[:16]
        now    = int(time.time())
        with _jobs_lock:
            _jobs[job_id] = {
                'job_id':     job_id,
                'principal':  principal,
                'status':     'queued',
                'phase':      'queued',
                'started_at': now,
                'updated_at': now,
                'endpoint':   None,
                'error':      None,
            }
        threading.Thread(
            target=_provision_worker,
            args=(job_id, principal),
            daemon=True
        ).start()
        return self._send_json(202, {
            'job_id':    job_id,
            'principal': principal,
            'status':    'queued',
            'poll':      f'/fleet/job/{job_id}',
        })


    # ── Admin handler methods ─────────────────────────────────────────────

    def _admin_dashboard(self):
        """Aggregate metrics across all providers."""
        import datetime as _dt
        sessions = _load_sessions()
        templates = _load_all_templates()
        fleet = _load_fleet_full()

        by_status = {}
        by_provider = {}
        for s in sessions.values():
            st = s.get('status', 'unknown')
            by_status[st] = by_status.get(st, 0) + 1
            pv = s.get('provider', 'unknown')
            by_provider[pv] = by_provider.get(pv, 0) + 1

        return self._send_json(200, {
            'total_sessions':   len(sessions),
            'by_status':        by_status,
            'by_provider':      by_provider,
            'total_templates':  len(templates),
            'enabled_templates': sum(1 for t in templates if t.get('enabled')),
            'total_users':      len(fleet.get('users', {})),
            'timestamp':        _dt.datetime.utcnow().isoformat() + 'Z',
        })

    def _admin_sessions(self):
        """Return all sessions across all users."""
        sessions = _load_sessions()
        session_list = sorted(
            sessions.values(),
            key=lambda s: s.get('created_at', ''),
            reverse=True,
        )
        return self._send_json(200, {'sessions': session_list})

    def _admin_infrastructure(self):
        """Health check for all infrastructure providers."""
        fleet = _load_fleet_full()
        gw = fleet.get('gateway', {})

        # ── Hyper-V ────────────────────────────────────────────────────
        hyperv_info = {'status': 'unknown', 'total_vms': 0, 'running_vms': 0, 'stopped_vms': 0}
        provider = _get_hyperv_provider()
        if provider:
            try:
                vms = provider.list_vms()
                running = sum(1 for v in vms if v.get('state') == 'running')
                stopped = sum(1 for v in vms if v.get('state') in ('stopped', 'off'))
                hyperv_info = {
                    'status':      'healthy',
                    'total_vms':   len(vms),
                    'running_vms': running,
                    'stopped_vms': stopped,
                    'vms':         vms[:20],  # cap at 20 for response size
                }
            except Exception as e:
                hyperv_info = {'status': 'error', 'error': str(e)[:200]}

        # ── OCI Fleet ──────────────────────────────────────────────────
        users = fleet.get('users', {})
        oci_info = {
            'status':           'healthy' if users else 'idle',
            'total_containers': len(users),
            'region':           fleet.get('region', ''),
            'fleet_file_exists': FLEET_FILE.exists(),
        }

        # ── TURN (coturn) ──────────────────────────────────────────────
        turn_secret = os.environ.get('TURN_SECRET', '').strip()
        turn_tls_cert = os.environ.get('TURN_TLS_CERT', '').strip()
        turn_tls_key  = os.environ.get('TURN_TLS_KEY', '').strip()
        tls_available = (
            bool(turn_tls_cert) and bool(turn_tls_key)
            and os.path.isfile(turn_tls_cert)
            and os.path.isfile(turn_tls_key)
        )
        turn_info = {
            'status':           'healthy' if turn_secret else 'not configured',
            'port':             3478,
            'tls_port':         5349,
            'secret_configured': bool(turn_secret),
            'tls':              tls_available,
            'tls_cert':         turn_tls_cert if tls_available else '',
            'turn_url':         os.environ.get('TURN_URL', ''),
        }
        # Quick port check for coturn
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            result = s.connect_ex(('127.0.0.1', 3478))
            s.close()
            if result == 0:
                turn_info['status'] = 'healthy'
                # Also check TLS port
                try:
                    s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s2.settimeout(2)
                    tls_result = s2.connect_ex(('127.0.0.1', 5349))
                    s2.close()
                    turn_info['tls_listening'] = (tls_result == 0)
                except Exception:
                    turn_info['tls_listening'] = False
            elif turn_secret:
                turn_info['status'] = 'port closed'
        except Exception:
            pass

        # ── Caddy gateway ──────────────────────────────────────────────
        user_routes = len([u for u in users.values() if u.get('ip')])
        sessions = _load_sessions()
        stream_routes = len([
            s for s in sessions.values()
            if s.get('status') == 'running' and s.get('stream_protocol') == 'webrtc'
        ])
        caddy_info = {
            'status':        'healthy' if gw.get('public_hostname') else 'unconfigured',
            'hostname':      gw.get('public_hostname', ''),
            'public_ip':     gw.get('public_ip', ''),
            'user_routes':   user_routes,
            'stream_routes': stream_routes,
        }

        # ── VM Pool ─────────────────────────────────────────────────
        pool = _load_vm_pool()
        pool_by_template = {}
        for e in pool:
            tid = e.get('template_id', 'unknown')
            state = e.get('state', 'unknown')
            if tid not in pool_by_template:
                pool_by_template[tid] = {'ready': 0, 'total': 0}
            pool_by_template[tid]['total'] += 1
            if state == 'ready':
                pool_by_template[tid]['ready'] += 1

        pool_info = {
            'total':         len(pool),
            'target_per_template': VM_POOL_SIZE,
            'max_age_hours': VM_POOL_MAX_AGE_HOURS,
            'by_template':   pool_by_template,
            'entries':       pool[:10],  # cap for response size
        }

        return self._send_json(200, {
            'hyperv':  hyperv_info,
            'oci':     oci_info,
            'turn':    turn_info,
            'caddy':   caddy_info,
            'vm_pool': pool_info,
        })

    def _admin_verify(self):
        """Check if the requesting principal is an admin."""
        admin_str = os.environ.get('FLEET_ADMIN_PRINCIPALS', '').strip()
        admin_principals = [p.strip() for p in admin_str.split(',') if p.strip()]
        requesting = self.headers.get('X-User-Principal', '').strip()
        # In dev mode (no secret), everyone is admin
        is_admin = not SHARED_SECRET or requesting in admin_principals
        return self._send_json(200, {
            'is_admin':   is_admin,
            'principal':  requesting[:20] + '...' if len(requesting) > 20 else requesting,
        })


# ── Caddyfile rendering (gateway-local) ─────────────────────────────────────
# Re-renders /etc/caddy/Caddyfile from fleet.json after a successful provision
# so the new user's `/u/<slug>/*` route works immediately. Mirrors the
# rendering logic in fleet-manager.py's `_render_caddyfile()` but skips the
# scp+ssh round-trip since we're already running on the gateway.
import hashlib

CADDYFILE_TEMPLATE = FLEET_DIR / 'caddyfile.template'
CADDYFILE_LIVE     = pathlib.Path('/etc/caddy/Caddyfile')


def _principal_slug(principal: str) -> str:
    return hashlib.sha256(principal.encode()).hexdigest()[:16]


def _render_caddyfile(fleet: dict) -> str:
    """Render the Caddyfile from fleet.json. Same algorithm as
       fleet-manager.py:_render_caddyfile() — keep them in sync."""
    if not CADDYFILE_TEMPLATE.exists():
        raise FileNotFoundError(str(CADDYFILE_TEMPLATE))
    template = CADDYFILE_TEMPLATE.read_text(encoding='utf-8')

    user_blocks      = []
    user_blocks_http = []
    for principal, info in fleet.get('users', {}).items():
        ip = info.get('ip')
        if not ip:
            continue
        slug = _principal_slug(principal)
        port = info.get('port', 8787)
        block = (
            f'    handle_path /u/{slug}/* {{\n'
            f'        reverse_proxy {ip}:{port}\n'
            f'    }}'
        )
        user_blocks.append(block)
        user_blocks_http.append(block)

    # Per-session stream routes — Phase 2 WebRTC sessions get a direct proxy
    # to the streaming backend (Sunshine/moonlight-web-stream or Selkies)
    # bypassing fleet-api for low-latency media.
    # Local (WSL+ttyd) sessions also get a proxy route to localhost:{port}.
    session_blocks = []
    for sid, ses in fleet.get('sessions', {}).items():
        if ses.get('status') != 'running':
            continue

        proto = ses.get('stream_protocol', '')

        if proto == 'webrtc':
            ip = ses.get('ip')
            if not ip:
                continue
            # Sunshine/moonlight-web-stream default port; Selkies uses 8080
            port = ses.get('moonlight_port') or ses.get('selkies_port') or ses.get('port', 47989)
            session_blocks.append(
                f'    handle_path /stream/{sid}/* {{\n'
                f'        reverse_proxy {ip}:{port}\n'
                f'    }}'
            )
        elif ses.get('provider') == 'local':
            # ttyd running on the host — proxy to localhost
            port = ses.get('port')
            if not port:
                continue
            session_blocks.append(
                f'    handle_path /stream/{sid}/* {{\n'
                f'        reverse_proxy localhost:{port}\n'
                f'    }}'
            )

    gw           = fleet.get('gateway') or {}
    primary_host = gw.get('public_hostname') or 'hq.cafreso.com'
    gateway_ip   = gw.get('public_ip') or '<unset>'

    return (template
        .replace('__PRIMARY_HOST__',     primary_host)
        .replace('__GATEWAY_IP__',       gateway_ip)
        .replace('__SESSION_ROUTES__',   '\n\n'.join(session_blocks)   or '    # (no active stream sessions)')
        .replace('__USER_ROUTES__',      '\n\n'.join(user_blocks)      or '    # (no users yet)')
        .replace('__USER_ROUTES_HTTP__', '\n\n'.join(user_blocks_http) or '    # (no users yet)')
    )


def _reload_caddy_with_new_routes() -> tuple[bool, str]:
    """Render Caddyfile from current fleet.json and reload Caddy in-place.
       Requires passwordless sudo for `tee /etc/caddy/Caddyfile` + reload.

       Returns (success, message). Failures are non-fatal — the provision
       is already complete; this just makes the gateway aware of the route.
    """
    try:
        rendered = _render_caddyfile(_load_fleet_full())
    except Exception as e:
        return False, f'render failed: {e}'

    # Write rendered file to a temp path the ubuntu user owns, then sudo-tee
    # it into /etc/caddy/Caddyfile. Avoids `echo "$rendered" | sudo tee`
    # which mangles backticks/$ in Caddyfile blocks.
    tmp = pathlib.Path('/tmp/cafresoai_Caddyfile.new')
    try:
        tmp.write_text(rendered, encoding='utf-8')
    except OSError as e:
        return False, f'tmp write failed: {e}'

    try:
        # `sudo cp` over the live file. Sudoers needs:
        #   ubuntu ALL=(root) NOPASSWD: /usr/bin/cp /tmp/cafresoai_Caddyfile.new /etc/caddy/Caddyfile,\
        #                                /usr/bin/systemctl reload caddy,\
        #                                /usr/sbin/caddy validate --config /etc/caddy/Caddyfile
        validate = subprocess.run(
            ['sudo', '-n', '/usr/sbin/caddy', 'validate',
             '--adapter', 'caddyfile', '--config', str(tmp)],
            capture_output=True, text=True, timeout=10,
        )
        if validate.returncode != 0:
            return False, f'caddy validate failed: {validate.stderr or validate.stdout}'

        cp = subprocess.run(
            ['sudo', '-n', '/usr/bin/cp', str(tmp), str(CADDYFILE_LIVE)],
            capture_output=True, text=True, timeout=10,
        )
        if cp.returncode != 0:
            return False, f'sudo cp failed: {cp.stderr or cp.stdout}'

        reload = subprocess.run(
            ['sudo', '-n', '/usr/bin/systemctl', 'reload', 'caddy'],
            capture_output=True, text=True, timeout=15,
        )
        if reload.returncode != 0:
            return False, f'caddy reload failed: {reload.stderr or reload.stdout}'

        return True, 'caddy reloaded'
    except subprocess.TimeoutExpired as e:
        return False, f'timeout: {e}'
    except Exception as e:
        return False, f'unexpected: {e}'


# ── Provision worker ────────────────────────────────────────────────────────
def _set_job(job_id: str, **fields):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)
            _jobs[job_id]['updated_at'] = int(time.time())


def _provision_worker(job_id: str, principal: str):
    log.info(f'[{job_id}] provisioning {principal}')
    _set_job(job_id, status='provisioning', phase='spawning')

    try:
        # fleet-manager.py creates the OCI Container Instance, polls until ACTIVE,
        # writes the IP to fleet.json, and prints colored progress.
        env = dict(os.environ)
        env.setdefault('PYTHONUTF8', '1')
        proc = subprocess.run(
            [sys.executable, str(FLEET_MANAGER), 'provision', principal],
            capture_output=True, text=True, encoding='utf-8',
            timeout=600, env=env, cwd=str(FLEET_DIR.parent),
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or '').strip()
            log.error(f'[{job_id}] provision failed: {err[:500]}')
            return _set_job(job_id, status='error', phase='failed',
                            error=err[:1000] or 'unknown failure')

        # fleet.json now contains the new user. Read endpoint.
        full = _load_fleet_full()
        user = full.get('users', {}).get(principal)
        endpoint = _user_to_endpoint(user)
        if not endpoint:
            return _set_job(job_id, status='error', phase='no-endpoint',
                            error='provisioned but no endpoint recorded')
        gateway_url = _gateway_url_for_principal(full, principal)
        log.info(f'[{job_id}] ready: {endpoint}  gateway={gateway_url}')

        # Re-render Caddyfile so the new user's /u/<slug>/* route is live
        # immediately. Failure is non-fatal (the container exists and works
        # via raw IP) but the SvelteKit shell expects the gateway URL.
        _set_job(job_id, phase='caddy-sync')
        ok, msg = _reload_caddy_with_new_routes()
        if ok:
            log.info(f'[{job_id}] caddy reloaded for new user route')
        else:
            log.warning(f'[{job_id}] caddy reload failed (non-fatal): {msg}')

        _set_job(job_id, status='ready', phase='ready',
                 endpoint=endpoint,
                 gateway_url=gateway_url,
                 container_id=user.get('container_instance_id'),
                 caddy_synced=ok,
                 caddy_message=msg)
    except subprocess.TimeoutExpired:
        log.error(f'[{job_id}] timed out')
        _set_job(job_id, status='error', phase='timeout',
                 error='provision exceeded 600s')
    except Exception as e:
        log.exception(f'[{job_id}] unexpected error')
        _set_job(job_id, status='error', phase='exception', error=str(e))


# ── Session provision worker ───────────────────────────────────────────────
def _session_provision_worker(session_id: str, principal: str, template: dict):
    """Background worker: provision an OCI container for a workspace session.

    Preferred path: delegate to the remote OCI fleet-api via HTTP when
    OCI_FLEET_API_URL is set (e.g. https://hq.cafreso.com).  This keeps OCI
    credentials on OCI where they belong and avoids running the SDK locally.

    Fallback: run fleet-manager.py as a subprocess (requires local OCI SDK +
    ~/.oci/config — useful for dev / standalone OCI hosts).
    """
    import datetime as _dt
    import urllib.request as _ureq
    import urllib.error   as _uerr
    log.info(f'[session:{session_id}] provisioning OCI container for {principal}')

    def _fail(msg: str):
        s = _load_sessions().get(session_id, {})
        s['status'] = 'error'
        s['error']  = msg[:1000]
        _save_session(session_id, s)

    oci_fleet_url   = os.environ.get('OCI_FLEET_API_URL', '').rstrip('/')
    oci_fleet_token = os.environ.get('OCI_FLEET_AUTH_TOKEN', SHARED_SECRET or '')

    gateway_url = None
    endpoint    = None

    if oci_fleet_url:
        # ── HTTP delegation path ──────────────────────────────────────────
        hdrs = {'Content-Type': 'application/json'}
        if oci_fleet_token:
            hdrs['X-Fleet-Auth'] = oci_fleet_token

        try:
            # 1. POST /fleet/provision
            body = json.dumps({'principal': principal}).encode()
            req  = _ureq.Request(f'{oci_fleet_url}/fleet/provision',
                                 data=body, headers=hdrs, method='POST')
            with _ureq.urlopen(req, timeout=30) as resp:
                pdata = json.loads(resp.read())

            status = pdata.get('status', '')
            if status == 'existing':
                endpoint    = pdata.get('endpoint', '')
                gateway_url = pdata.get('gateway_url', endpoint)
                log.info(f'[session:{session_id}] OCI container already exists → {endpoint}')

            elif status == 'queued':
                job_id = pdata['job_id']
                log.info(f'[session:{session_id}] OCI provision queued: job {job_id}')
                # 2. Poll /fleet/job/<id>
                for _ in range(120):          # 10 min max
                    time.sleep(5)
                    req2 = _ureq.Request(
                        f'{oci_fleet_url}/fleet/job/{job_id}', headers=hdrs)
                    with _ureq.urlopen(req2, timeout=15) as resp2:
                        job = json.loads(resp2.read())
                    js = job.get('status', '')
                    log.info(f'[session:{session_id}] job {job_id}: {js}')
                    if js == 'done':
                        endpoint = job.get('endpoint', '')
                        break
                    elif js in ('failed', 'error'):
                        return _fail(job.get('error') or 'OCI provision job failed')
                else:
                    return _fail('OCI provision timed out (10 min)')

                # 3. Lookup full details for gateway_url
                lurl = (f'{oci_fleet_url}/fleet/lookup'
                        f'?principal={urllib.parse.quote(principal)}')
                req3 = _ureq.Request(lurl, headers=hdrs)
                with _ureq.urlopen(req3, timeout=15) as resp3:
                    ldata = json.loads(resp3.read())
                endpoint    = ldata.get('endpoint', endpoint)
                gateway_url = ldata.get('gateway_url', endpoint)
            else:
                return _fail(f'Unexpected /fleet/provision response: {pdata}')

        except _uerr.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            return _fail(f'OCI fleet-api HTTP {e.code}: {body[:400]}')
        except Exception as e:
            log.exception(f'[session:{session_id}] OCI fleet delegation error')
            return _fail(str(e))

    else:
        # ── Local subprocess fallback ─────────────────────────────────────
        try:
            env = dict(os.environ)
            env.setdefault('PYTHONUTF8', '1')
            proc = subprocess.run(
                [sys.executable, str(FLEET_MANAGER), 'provision', principal],
                capture_output=True, text=True, encoding='utf-8',
                timeout=600, env=env, cwd=str(FLEET_DIR.parent),
            )
            if proc.returncode != 0:
                # Capture both streams — stderr often has urllib3 warnings,
                # stdout has the real OCI error message.
                err_text = '\n'.join(filter(None, [proc.stderr, proc.stdout])).strip()
                log.error(f'[session:{session_id}] provision failed: {err_text[:500]}')
                return _fail(err_text or 'unknown failure')

            full = _load_fleet_full()
            user = full.get('users', {}).get(principal)
            endpoint = _user_to_endpoint(user)
            if not endpoint:
                return _fail('provisioned but no endpoint recorded')
            gateway_url = _gateway_url_for_principal(full, principal)

        except subprocess.TimeoutExpired:
            log.error(f'[session:{session_id}] timed out (600s)')
            return _fail('provision exceeded 600s')
        except Exception as e:
            log.exception(f'[session:{session_id}] unexpected error')
            return _fail(str(e))

    # ── Common completion ─────────────────────────────────────────────────
    stream_path = template.get('stream_path', '/hq.html')
    stream_url  = (gateway_url or endpoint or '') + stream_path

    session = _load_sessions().get(session_id, {})
    session.update({
        'status':        'running',
        'provider_id':   '',
        'stream_url':    stream_url,
        'last_accessed': _dt.datetime.utcnow().isoformat() + 'Z',
    })
    _save_session(session_id, session)
    log.info(f'[session:{session_id}] ready → {stream_url}')

    ok, msg = _reload_caddy_with_new_routes()
    if ok:
        log.info(f'[session:{session_id}] caddy reloaded')
    else:
        log.warning(f'[session:{session_id}] caddy reload non-fatal: {msg}')


def _fetch_guacamole_token(username: str, password: str,
                           url: str = 'http://127.0.0.1:8484/guacamole/api/tokens',
                           timeout: int = 5) -> str:
    """Authenticate to the local Guacamole API and return a session token.
    Returns '' on any failure (we degrade gracefully — user sees login page).
    """
    import urllib.request, urllib.parse
    try:
        data = urllib.parse.urlencode({'username': username, 'password': password}).encode()
        req  = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
            return payload.get('authToken', '')
    except Exception as exc:
        log.warning('guacamole token fetch failed: %s', exc)
        return ''


# ── Hyper-V provision worker ────────────────────────────────────────────────
def _hyperv_provision_worker(session_id: str, principal: str, template: dict):
    """Background worker: create a Hyper-V VM for a workspace session.

    1. Call HyperVProvider.create_vm() (delegates to New-WorkspaceVM.ps1)
    2. If VM starts successfully, launch moonlight-web-stream sidecar
    3. Generate TURN credentials for the session
    4. Update session record with IP, ports, stream_url
    5. Reload Caddy with the new /stream/{session_id}/* route
    """
    import datetime as _dt
    log.info(f'[hyperv:{session_id}] provisioning VM for {principal}')

    def _fail(msg: str):
        s = _load_sessions().get(session_id, {})
        s['status'] = 'error'
        s['error']  = msg[:1000]
        _save_session(session_id, s)

    try:
        provider = _get_hyperv_provider()
        if provider is None:
            return _fail('HyperVProvider failed to initialize')

        # ── Step 1: Try claiming a pre-warmed VM from the pool ─────────
        template_id = template.get('id', '')
        claimed, _ = _claim_from_pool(template_id, session_id)

        if claimed:
            # Pool hit — VM is already running with Sunshine ready
            vm_name = claimed.get('vm_name', '')
            vm_ip   = claimed.get('ip')
            vm_port = claimed.get('port', 47989)
            log.info(f'[hyperv:{session_id}] Pool hit! Claimed {vm_name} @ {vm_ip}:{vm_port}')
        else:
            # Pool miss — create from gold image (slow path)
            log.info(f'[hyperv:{session_id}] Pool miss, creating VM from gold image')
            vm_result = provider.create_vm(template, session_id, principal)
            vm_state = vm_result.get('state', 'error')
            vm_name  = vm_result.get('vm_name', '')
            vm_ip    = vm_result.get('ip')
            vm_port  = vm_result.get('port', 47989)
            vm_error = vm_result.get('error', '')

            if vm_state == 'error':
                log.error(f'[hyperv:{session_id}] VM creation failed: {vm_error}')
                return _fail(f'VM creation failed: {vm_error}')

        if not vm_ip:
            log.error(f'[hyperv:{session_id}] VM started but no IP obtained')
            return _fail('VM started but no IP address obtained')

        log.info(f'[hyperv:{session_id}] VM ready: {vm_name} @ {vm_ip}:{vm_port}')

        # ── Step 2: Start moonlight-web-stream sidecar ─────────────────
        signaling_port = provider._allocate_signaling_port(session_id)

        # Generate TURN credentials for NAT traversal
        turn_user, turn_cred = _generate_turn_credentials(session_id)
        turn_url = os.environ.get('TURN_URL', '')

        ml_ok, ml_container, _ = provider.start_moonlight_sidecar(
            session_id=session_id,
            vm_ip=vm_ip,
            sunshine_port=vm_port,
            signaling_port=signaling_port,
            turn_url=turn_url,
            turn_user=turn_user,
            turn_cred=turn_cred,
        )

        if not ml_ok:
            log.warning(
                f'[hyperv:{session_id}] moonlight sidecar failed to start '
                f'(VM is running — user may still connect directly)'
            )

        # ── Step 3: Build stream URL and update session ────────────────
        # Hyper-V VMs run on THIS host, not the OCI gateway — never use the
        # gateway's hostname here.
        fleet = _load_fleet_full()
        gw = fleet.get('gateway', {})
        hostname = WORKSPACES_PUBLIC_HOSTNAME or gw.get('public_hostname', 'hq.cafreso.com')
        stream_url = f'https://{hostname}/stream/{session_id}/'

        # TURN server info for the client
        turn_servers = []
        if turn_url:
            turn_servers.append({
                'urls': turn_url,
                'username': turn_user,
                'credential': turn_cred,
            })

        # ── Determine stream mode: Guacamole (Phase 2c) or moonlight-web (Phase 2d) ──
        # Phase 2c: template has guacamole_url → pre-fetch a Guacamole auth token
        # and redirect the iframe to Guacamole's RDP viewer.
        # Phase 2d: no guacamole_url → moonlight-web container serves the stream
        # HTML page; the browser loads it via iframe and WebRTC connects directly
        # to Sunshine inside the VM (works on LAN or with TURN for external).
        tmpl_guac_url = (template.get('guacamole_url') or '') if isinstance(template, dict) else ''
        guac_token    = ''
        if tmpl_guac_url:
            # Phase 2c path: Guacamole token pre-fetch
            guac_token = _fetch_guacamole_token(
                os.environ.get('GUAC_USER', 'anthony'),
                os.environ.get('GUAC_PASS', 'unused'))
            if guac_token:
                log.info(f'[hyperv:{session_id}] guacamole token minted ({guac_token[:8]}...)')
            else:
                log.warning(f'[hyperv:{session_id}] guacamole token fetch failed — iframe will show login page')
            final_protocol = 'iframe'
        else:
            # Phase 2d path: moonlight-web iframe
            # stream_protocol='iframe'; the <iframe> loads the moonlight-web HTML
            # from /stream/{sid}/ (proxied by fleet-api to the sidecar container).
            final_protocol = 'iframe'
            log.info(f'[hyperv:{session_id}] moonlight-web sidecar on port {signaling_port}')

        session = _load_sessions().get(session_id, {})
        session.update({
            'status':          'running',
            'provider_id':     vm_name,
            'ip':              vm_ip,
            'port':            vm_port,
            'stream_url':      stream_url,
            'moonlight_port':  signaling_port,
            'moonlight_container': ml_container,
            'turn_servers':    turn_servers,
            'region':          'local',
            'last_accessed':   _dt.datetime.utcnow().isoformat() + 'Z',
            # Guacamole fields — populated only in Phase 2c path.
            'guacamole_url':    tmpl_guac_url,
            'guacamole_token':  guac_token,
            'stream_protocol':  final_protocol,
        })
        _save_session(session_id, session)
        log.info(f'[hyperv:{session_id}] session running → {stream_url}')

        # ── Step 4: Reload Caddy with stream route ─────────────────────
        ok, msg = _reload_caddy_with_new_routes()
        if ok:
            log.info(f'[hyperv:{session_id}] caddy reloaded with stream route')
        else:
            log.warning(f'[hyperv:{session_id}] caddy reload non-fatal: {msg}')

    except Exception as e:
        log.exception(f'[hyperv:{session_id}] unexpected error')
        _fail(str(e))


def _hyperv_stop_worker(session_id: str):
    """Background worker: stop a Hyper-V VM and its moonlight sidecar."""
    log.info(f'[hyperv-stop:{session_id}] stopping session')

    session = _load_sessions().get(session_id, {})
    vm_name = session.get('provider_id', '')
    persistent = session.get('persistent', True)

    try:
        provider = _get_hyperv_provider()

        # Stop the moonlight-web-stream sidecar
        if provider:
            provider.stop_moonlight_sidecar(session_id)

        # Stop (or delete) the VM
        if provider and vm_name:
            if persistent:
                # Persistent VMs: stop but keep the disk for next session
                provider.stop_vm(vm_name)
                log.info(f'[hyperv-stop:{session_id}] VM {vm_name} stopped (persistent)')
            else:
                # Ephemeral VMs: delete everything
                provider.delete_vm(vm_name, remove_disk=True)
                log.info(f'[hyperv-stop:{session_id}] VM {vm_name} deleted (ephemeral)')

        # Update session status
        session['status'] = 'stopped'
        _save_session(session_id, session)

        # Reload Caddy to remove the stream route
        ok, msg = _reload_caddy_with_new_routes()
        if ok:
            log.info(f'[hyperv-stop:{session_id}] caddy reloaded (route removed)')

    except Exception as e:
        log.exception(f'[hyperv-stop:{session_id}] error during stop')
        session['status'] = 'error'
        session['error'] = str(e)[:1000]
        _save_session(session_id, session)


# ── Session idle reaper (background) ──────────────────────────────────────────
# Stops sessions that have been idle (no last_accessed update) for too long.
# Default: 4 hours. Configurable via SESSION_IDLE_TIMEOUT_SEC env var.

SESSION_IDLE_TIMEOUT = int(os.environ.get('SESSION_IDLE_TIMEOUT_SEC', str(4 * 3600)))
SESSION_MAX_PER_USER = int(os.environ.get('SESSION_MAX_PER_USER', '5'))
REAPER_INTERVAL      = int(os.environ.get('REAPER_INTERVAL_SEC', '120'))
HEALTH_POLL_INTERVAL = int(os.environ.get('HEALTH_POLL_INTERVAL_SEC', '30'))
HEALTH_FAIL_THRESHOLD = int(os.environ.get('HEALTH_FAIL_THRESHOLD', '3'))
VM_POOL_SIZE         = int(os.environ.get('VM_POOL_SIZE', '2'))
VM_POOL_REPLENISH_INTERVAL = int(os.environ.get('VM_POOL_REPLENISH_SEC', '60'))
VM_POOL_MAX_AGE_HOURS = int(os.environ.get('VM_POOL_MAX_AGE_HOURS', '12'))


def _idle_reaper_loop():
    """Background loop: reap sessions idle longer than SESSION_IDLE_TIMEOUT."""
    import datetime as _dt
    log.info('Idle reaper started (timeout=%ds, interval=%ds)',
             SESSION_IDLE_TIMEOUT, REAPER_INTERVAL)

    while True:
        try:
            time.sleep(REAPER_INTERVAL)
            sessions = _load_sessions()
            now = time.time()

            for sid, session in list(sessions.items()):
                if session.get('status') not in ('running', 'starting'):
                    continue
                # Canister sessions don't idle out
                if session.get('provider') == 'canister':
                    continue

                # Check last_accessed or created_at
                ts_str = session.get('last_accessed') or session.get('created_at', '')
                if not ts_str:
                    continue

                try:
                    ts = _dt.datetime.fromisoformat(ts_str.rstrip('Z'))
                    age_sec = now - ts.timestamp()
                except (ValueError, OSError):
                    continue

                if age_sec > SESSION_IDLE_TIMEOUT:
                    log.info(
                        '[reaper] Session %s idle for %.0fh, stopping '
                        '(name=%s, provider=%s)',
                        sid, age_sec / 3600,
                        session.get('display_name', '?'),
                        session.get('provider', '?'),
                    )
                    session['status'] = 'stopping'
                    _save_session(sid, session)

                    if session.get('provider') == 'hyperv':
                        threading.Thread(
                            target=_hyperv_stop_worker, args=(sid,), daemon=True,
                        ).start()
                    elif session.get('provider') == 'local':
                        lp = _get_local_provider()
                        if lp:
                            lp.stop(sid)
                        session['status'] = 'stopped'
                        _save_session(sid, session)
                    else:
                        session['status'] = 'stopped'
                        _save_session(sid, session)

        except Exception:
            log.exception('[reaper] Error in idle reaper loop')


def _health_poll_loop():
    """Background loop: poll running sessions for health.
    Mark as 'error' after HEALTH_FAIL_THRESHOLD consecutive failures."""
    log.info('Health poller started (interval=%ds, threshold=%d)',
             HEALTH_POLL_INTERVAL, HEALTH_FAIL_THRESHOLD)

    # Track consecutive failures per session
    fail_counts = {}

    while True:
        try:
            time.sleep(HEALTH_POLL_INTERVAL)
            sessions = _load_sessions()

            for sid, session in list(sessions.items()):
                if session.get('status') != 'running':
                    fail_counts.pop(sid, None)
                    continue

                provider = session.get('provider', '')
                healthy = True

                if provider == 'hyperv':
                    # Check if VM is still running
                    vm_name = session.get('provider_id', '')
                    if vm_name:
                        hp = _get_hyperv_provider()
                        if hp:
                            status = hp.get_vm_status(vm_name)
                            if not status or status.get('state') != 'running':
                                healthy = False

                elif provider == 'oci':
                    # Check if container IP is reachable (simple TCP check)
                    ip = session.get('ip')
                    port = session.get('port', 8787)
                    if ip:
                        import socket
                        try:
                            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            s.settimeout(3)
                            result = s.connect_ex((ip, port))
                            s.close()
                            healthy = (result == 0)
                        except Exception:
                            healthy = False

                elif provider == 'local':
                    # Check if the ttyd process is still alive
                    lp = _get_local_provider()
                    if lp:
                        healthy = lp.is_alive(sid)

                elif provider == 'canister':
                    # Canisters are always "healthy" (externally managed)
                    continue

                if healthy:
                    fail_counts.pop(sid, None)
                else:
                    fail_counts[sid] = fail_counts.get(sid, 0) + 1
                    if fail_counts[sid] >= HEALTH_FAIL_THRESHOLD:
                        log.warning(
                            '[health] Session %s failed %d consecutive checks, '
                            'marking error (name=%s)',
                            sid, fail_counts[sid],
                            session.get('display_name', '?'),
                        )
                        session['status'] = 'error'
                        session['error'] = (
                            f'Health check failed {fail_counts[sid]} times. '
                            f'Provider: {provider}, IP: {session.get("ip", "?")}'
                        )
                        _save_session(sid, session)
                        fail_counts.pop(sid, None)

        except Exception:
            log.exception('[health] Error in health poll loop')


def _check_user_session_limit(principal: str) -> tuple[bool, str]:
    """Check if a user has exceeded their per-user session limit.
    Returns (allowed, message)."""
    sessions = _load_sessions()
    user_active = [
        s for s in sessions.values()
        if s.get('principal') == principal
        and s.get('status') in ('running', 'starting')
        and s.get('provider') != 'canister'  # canisters don't count
    ]
    if len(user_active) >= SESSION_MAX_PER_USER:
        return False, (
            f'Session limit reached ({SESSION_MAX_PER_USER} active). '
            f'Stop an existing session first.'
        )
    return True, ''


# ── VM Pool (pre-warming) ─────────────────────────────────────────────────
# Maintains N ready-to-assign VMs per enabled Hyper-V template so users get
# instant VM launches instead of waiting 2-3 min for gold image cloning.

def _load_vm_pool() -> list:
    """Load the VM pool from fleet.json."""
    fleet = _load_fleet_full()
    return fleet.get('vm_pool', [])


def _save_vm_pool(pool: list):
    """Persist the VM pool to fleet.json."""
    fleet = _load_fleet_full()
    fleet['vm_pool'] = pool
    try:
        FLEET_FILE.write_text(json.dumps(fleet, indent=2, default=str), encoding='utf-8')
    except Exception as e:
        log.error(f'fleet.json write error (vm_pool): {e}')


def _claim_from_pool(template_id: str, session_id: str):
    """Try to claim a pre-warmed VM from the pool.
    Returns (claimed_entry, updated_pool) or (None, pool) if none available."""
    pool = _load_vm_pool()
    for i, entry in enumerate(pool):
        if (entry.get('template_id') == template_id and
                entry.get('state') == 'ready'):
            # Claim this entry
            provider = _get_hyperv_provider()
            if not provider:
                return None, pool

            claimed = provider.claim_pool_vm(entry, session_id)
            if claimed:
                pool.pop(i)
                _save_vm_pool(pool)
                log.info('[pool] Claimed VM %s for session %s (template=%s)',
                         claimed.get('vm_name'), session_id, template_id)
                return claimed, pool

    return None, pool


def _vm_pool_replenisher_loop():
    """Background loop: maintain VM_POOL_SIZE pre-warmed VMs per Hyper-V template.

    On each tick:
      1. Load pool and enabled Hyper-V templates
      2. For each template, count 'ready' pool VMs
      3. If count < VM_POOL_SIZE, create a new pool VM (one at a time to avoid overload)
      4. Clean up stale pool VMs older than VM_POOL_MAX_AGE_HOURS
    """
    log.info('VM pool replenisher started (size=%d/template, interval=%ds, max_age=%dh)',
             VM_POOL_SIZE, VM_POOL_REPLENISH_INTERVAL, VM_POOL_MAX_AGE_HOURS)

    # Initial delay to let the system settle
    time.sleep(30)

    while True:
        try:
            time.sleep(VM_POOL_REPLENISH_INTERVAL)

            provider = _get_hyperv_provider()
            if not provider:
                continue

            # Get enabled Hyper-V templates
            templates = _load_all_templates()
            hyperv_templates = [
                t for t in templates
                if t.get('provider') == 'hyperv'
                and t.get('enabled', False)
                and t.get('vm_template')  # must have a gold image
            ]

            if not hyperv_templates:
                continue

            pool = _load_vm_pool()

            # ── Clean up stale pool VMs ────────────────────────────────
            stale_ready = [e for e in pool if e.get('state') == 'ready']
            if stale_ready:
                cleaned_ids = provider.cleanup_stale_pool_vms(
                    stale_ready, max_age_hours=VM_POOL_MAX_AGE_HOURS
                )
                if cleaned_ids:
                    pool = [e for e in pool if e.get('pool_id') not in cleaned_ids]
                    _save_vm_pool(pool)
                    log.info('[pool] Cleaned %d stale pool VMs', len(cleaned_ids))

            # ── Replenish pool ─────────────────────────────────────────
            # Only create one VM per tick to avoid overloading the host
            created_one = False
            for tmpl in hyperv_templates:
                tid = tmpl['id']
                ready_count = sum(
                    1 for e in pool
                    if e.get('template_id') == tid and e.get('state') == 'ready'
                )

                if ready_count < VM_POOL_SIZE and not created_one:
                    log.info('[pool] Template %s has %d/%d ready, creating pool VM',
                             tid, ready_count, VM_POOL_SIZE)
                    entry = provider.create_pool_vm(tmpl)
                    if entry:
                        pool.append(entry)
                        _save_vm_pool(pool)
                        created_one = True
                        log.info('[pool] Pool VM created: %s (template=%s)',
                                 entry.get('vm_name'), tid)
                    else:
                        log.warning('[pool] Failed to create pool VM for %s', tid)

        except Exception:
            log.exception('[pool] Error in VM pool replenisher')


# ── Prometheus metrics ─────────────────────────────────────────────────────
# Text-based Prometheus exposition format at GET /metrics

def _render_prometheus_metrics() -> str:
    """Render Prometheus metrics in text exposition format."""
    lines = []

    def _metric(name, help_text, mtype, values):
        lines.append(f'# HELP {name} {help_text}')
        lines.append(f'# TYPE {name} {mtype}')
        for labels, val in values:
            if labels:
                label_str = ','.join(f'{k}="{v}"' for k, v in labels.items())
                lines.append(f'{name}{{{label_str}}} {val}')
            else:
                lines.append(f'{name} {val}')

    sessions = _load_sessions()
    templates = _load_all_templates()
    fleet = _load_fleet_full()

    # Session counts by status and provider
    by_status = {}
    by_provider = {}
    for s in sessions.values():
        st = s.get('status', 'unknown')
        by_status[st] = by_status.get(st, 0) + 1
        pv = s.get('provider', 'unknown')
        by_provider[pv] = by_provider.get(pv, 0) + 1

    _metric('cafresoai_sessions_total', 'Total session count', 'gauge',
            [({}, len(sessions))])

    _metric('cafresoai_sessions_by_status', 'Sessions by status', 'gauge',
            [({'status': st}, cnt) for st, cnt in by_status.items()])

    _metric('cafresoai_sessions_by_provider', 'Sessions by provider', 'gauge',
            [({'provider': pv}, cnt) for pv, cnt in by_provider.items()])

    active = sum(1 for s in sessions.values()
                 if s.get('status') in ('running', 'starting'))
    _metric('cafresoai_sessions_active', 'Currently active sessions', 'gauge',
            [({}, active)])

    # Template counts
    enabled = sum(1 for t in templates if t.get('enabled'))
    _metric('cafresoai_templates_total', 'Total workspace templates', 'gauge',
            [({}, len(templates))])
    _metric('cafresoai_templates_enabled', 'Enabled workspace templates', 'gauge',
            [({}, enabled)])

    # VM Pool
    pool = _load_vm_pool()
    pool_ready = {}
    for e in pool:
        if e.get('state') == 'ready':
            tid = e.get('template_id', 'unknown')
            pool_ready[tid] = pool_ready.get(tid, 0) + 1

    _metric('cafresoai_vm_pool_total', 'Total VMs in pre-warm pool', 'gauge',
            [({}, len(pool))])
    _metric('cafresoai_vm_pool_ready', 'Ready VMs in pool by template', 'gauge',
            [({'template': tid}, cnt) for tid, cnt in pool_ready.items()] or [({}, 0)])

    # OCI containers
    users = fleet.get('users', {})
    _metric('cafresoai_oci_containers_total', 'Total OCI containers', 'gauge',
            [({}, len(users))])

    # Unique principals with active sessions
    principals = set(
        s.get('principal', '') for s in sessions.values()
        if s.get('status') in ('running', 'starting')
    )
    _metric('cafresoai_active_users', 'Users with active sessions', 'gauge',
            [({}, len(principals))])

    # Config info
    _metric('cafresoai_config_idle_timeout_seconds',
            'Session idle timeout in seconds', 'gauge',
            [({}, SESSION_IDLE_TIMEOUT)])
    _metric('cafresoai_config_max_sessions_per_user',
            'Max sessions per user', 'gauge',
            [({}, SESSION_MAX_PER_USER)])
    _metric('cafresoai_config_vm_pool_size',
            'Target VM pool size per template', 'gauge',
            [({}, VM_POOL_SIZE)])

    # Server uptime
    _metric('cafresoai_up', 'Fleet API is up', 'gauge', [({}, 1)])

    return '\n'.join(lines) + '\n'


# ── main ────────────────────────────────────────────────────────────────────
def _restore_hyperv_portproxies():
    """
    On startup, refresh Windows portproxy entries for running Hyper-V sessions.

    Scenario: fleet-api restarted after a WSL reboot.  WSL gets a new eth0 IP
    (e.g. 172.30.x.x → 172.31.x.x).  Old portproxy entries in the 8500–8999
    range point to the dead old IP.  We:
      1. Remove ALL portproxy entries in that range (stale or not).
      2. Re-add entries for sessions that are still running and have a live
         moonlight-web container (confirmed via `docker inspect`).

    If docker/WSL isn't present (Linux native deploy or Docker Desktop), this
    function is a no-op — it detects that and exits cleanly.
    """
    try:
        provider = _get_hyperv_provider()
        if provider is None:
            return

        # Check if we're actually running through WSL (if not, no portproxy needed)
        prefix = provider._docker_prefix()
        if not prefix:
            return  # native docker — localhost relay handles it

        # Step 1: clear any stale portproxy entries in the moonlight port range
        import subprocess as _sp
        for port in range(8500, 9000):
            _sp.run(
                ["netsh", "interface", "portproxy", "delete", "v4tov4",
                 "listenaddress=127.0.0.1", f"listenport={port}"],
                capture_output=True, timeout=5,
            )

        # Step 2: re-add entries for running sessions whose container is alive
        wsl_ip = provider._wsl_ip()
        if not wsl_ip:
            log.warning("[startup] Could not get WSL IP — skipping portproxy restore")
            return

        sessions = _load_sessions()
        restored = 0
        for sid, session in sessions.items():
            if session.get('provider') != 'hyperv':
                continue
            if session.get('status') != 'running':
                continue
            ml_port = session.get('moonlight_port')
            if not ml_port:
                continue
            container = session.get('moonlight_container', f"cafresoai-moonlight-{sid[:12]}")

            # Verify container is actually running before adding portproxy
            r = _sp.run(
                prefix + ["docker", "inspect", "--format={{.State.Running}}", container],
                capture_output=True, text=True, timeout=5,
            )
            if r.stdout.strip() != 'true':
                log.info("[startup] moonlight container %s not running — skipping portproxy", container)
                continue

            provider._add_portproxy(ml_port, ml_port, wsl_ip)
            restored += 1

        if restored:
            log.info("[startup] Restored %d moonlight portproxy entries (WSL IP: %s)", restored, wsl_ip)
        else:
            log.debug("[startup] No active moonlight sessions to restore portproxy for")

    except Exception:
        log.exception("[startup] portproxy restore failed (non-fatal)")


def main():
    addr = ('0.0.0.0', PORT)
    print('-' * 60, flush=True)
    print(f'  CafresoAI Fleet API — http://{addr[0]}:{addr[1]}', flush=True)
    print(f'  Auth:    {"shared-secret" if SHARED_SECRET else "DEV MODE (no auth)"}', flush=True)
    print(f'  Fleet:   {FLEET_FILE}', flush=True)
    print(f'  Origins: {", ".join(ALLOWED_ORIGINS) or "(any)"}', flush=True)
    print(f'  Idle:    {SESSION_IDLE_TIMEOUT // 3600}h timeout, '
          f'{SESSION_MAX_PER_USER} max/user', flush=True)
    print(f'  Pool:    {VM_POOL_SIZE}/template, '
          f'{VM_POOL_REPLENISH_INTERVAL}s interval, '
          f'{VM_POOL_MAX_AGE_HOURS}h max age', flush=True)
    print(f'  Metrics: http://0.0.0.0:{PORT}/metrics', flush=True)
    print('-' * 60, flush=True)

    # ── Restore WSL portproxies for any running hyperv sessions ────────────────
    # After a WSL restart the WSL IP changes, leaving stale portproxy entries.
    # On each fleet-api startup, remove all stale entries in the moonlight-web
    # port range (8500-8999) and re-add valid ones for active sessions.
    _restore_hyperv_portproxies()

    # Start background maintenance threads
    threading.Thread(target=_idle_reaper_loop, daemon=True,
                     name='session-reaper').start()
    threading.Thread(target=_health_poll_loop, daemon=True,
                     name='health-poller').start()
    threading.Thread(target=_vm_pool_replenisher_loop, daemon=True,
                     name='vm-pool-replenisher').start()

    srv = http.server.ThreadingHTTPServer(addr, Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nshutting down…')
        srv.shutdown()


if __name__ == '__main__':
    main()
