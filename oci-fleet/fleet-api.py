#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   CafresoAI -- Fleet API                                     ║
║   Bridges the SvelteKit shell to per-user OCI containers     ║
╚══════════════════════════════════════════════════════════════╝

Endpoints
─────────
  GET  /fleet/health                          → liveness
  GET  /fleet/lookup?principal=<p>            → 200 {endpoint,...} or 404
  POST /fleet/provision  { principal }        → 200 existing | 202 {job_id}
  GET  /fleet/job/<id>                        → job status

Auth
────
  All non-/health routes require X-Fleet-Auth header matching FLEET_API_SECRET
  env var (skip auth entirely if FLEET_API_SECRET is unset — DEV ONLY).

Run
───
  $ export FLEET_API_SECRET=somethinglong
  $ python oci-fleet/fleet-api.py
  → http://0.0.0.0:8080

For production, run behind a TLS terminator (OCI Load Balancer, Caddy, etc.)
and pass the secret to the SvelteKit shell via environment.
"""
import http.server
import json
import logging
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid

import hq_token  # shared HQ session-token verify (stdlib HMAC)

# ── Config ───────────────────────────────────────────────────────────────────
FLEET_DIR        = pathlib.Path(__file__).parent
FLEET_FILE       = FLEET_DIR / 'fleet.json'
FLEET_MANAGER    = FLEET_DIR / 'fleet-manager.py'
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
log = logging.getLogger('fleet-api')

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


def _verify_plan_onchain(principal: str, plan: str) -> tuple:
    """Verify the user actually paid for `plan` by checking the on-chain order
    ledger (the IndexCanister GlobalOrder list). Orders are unforgeable —
    GlobalOrder.buyer is set server-side to the caller principal — so this is the
    authoritative gate that prevents a client from self-assigning a paid plan.

    Returns (ok: bool, reason: str). 'free' is always allowed (no payment needed).

    Implementation status: queries the canister via the `dfx`/agent if available;
    otherwise FAILS CLOSED for paid plans unless PLAN_VERIFY_TRUST_AUTH=1 (set
    only when this endpoint is already behind the trusted FLEET_API_SECRET and
    the caller is the shell). Wire the real canister query before public launch.
    """
    if plan == 'free':
        return True, 'free needs no payment'

    # Trust model: the IndexCanister exposes listMyOrders() (authed, returns the
    # CALLER's own unforgeable orders) but NOT listOrdersByBuyer(p) — so a
    # server (anonymous) can't read a specific user's orders directly. The
    # correct verifier is therefore the SHELL, which already holds the user's II
    # identity and calls listMyOrders() to confirm a paid cafresohq-<plan> order
    # before POSTing here. This endpoint trusts that shell IFF the request
    # carries the shared secret (FLEET_API_SECRET) — i.e. it came from our
    # gateway/shell, not an arbitrary client. With auth on, we accept the plan.
    if SHARED_SECRET:
        return True, 'verified by authenticated shell (FLEET_API_SECRET)'

    # No shared secret = dev mode / open API → cannot trust a paid-plan claim.
    # Fail closed. (Set FLEET_API_SECRET in prod; the shell already sends it.)
    return False, ('paid-plan verification requires FLEET_API_SECRET (so only the '
                   'shell, which checked the on-chain order, can set plans). '
                   'Set it in prod.')


def _validate_principal(p: str) -> bool:
    if not p or len(p) > 100:
        return False
    return bool(_PRINCIPAL_RE.match(p))


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
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers',
                         'Content-Type, X-Fleet-Auth')
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
        if not SHARED_SECRET:  # DEV mode
            return True
        return self.headers.get('X-Fleet-Auth') == SHARED_SECRET

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

        return self._send_json(404, {'error': 'not found'})

    def _install_session_cookie(self):
        """POST /fleet/session  { token } → validate the on-chain-minted token
        and set it as an HttpOnly, Secure, SameSite=None cookie scoped to this
        gateway host. The embedded HQ iframe (served from this host) then sends
        the cookie automatically, and Caddy's forward_auth → verifier.py gates
        every /u/<slug>/* request with it. NOT gated by X-Fleet-Auth — the
        browser can't hold that secret; the token itself is the credential."""
        length = int(self.headers.get('Content-Length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})
        token = str(req.get('token', '')).strip()
        secret = hq_token.secret_bytes()
        if not secret:
            return self._send_json(503, {'error': 'sessions not configured'})
        claims = hq_token.verify(token, secret)
        if not claims:
            return self._send_json(401, {'error': 'invalid or expired token'})

        max_age = max(0, int(claims['exp']) - int(time.time()))
        body = json.dumps({'ok': True, 'exp': claims['exp']}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        # Host-only cookie on the gateway; SameSite=None so the cross-site
        # iframe (loaded by ai.cafreso.com) sends it; Secure + HttpOnly.
        self.send_header('Set-Cookie',
                         f'{hq_token.COOKIE_NAME}={token}; Path=/; Max-Age={max_age}; '
                         f'Secure; HttpOnly; SameSite=None')
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _run_set_plan(self, principal, plan):
        """Invoke `fleet-manager set-plan` for a verified (principal, plan)."""
        try:
            proc = subprocess.run(
                [sys.executable, str(FLEET_MANAGER), 'set-plan', principal, plan],
                capture_output=True, text=True, timeout=60,
                env={**os.environ, 'PYTHONUTF8': '1'}, cwd=str(FLEET_DIR.parent))
            if proc.returncode != 0:
                return self._send_json(500, {'error': (proc.stderr or proc.stdout or '')[:300]})
        except Exception as e:
            return self._send_json(500, {'error': str(e)})
        return self._send_json(200, {'ok': True, 'principal': principal, 'plan': plan})

    def _apply_plan(self):
        """POST /fleet/set-plan — apply a plan to the caller's container.

        Two paths:
          • { token }           → plan proof minted ON-CHAIN (mintPlanToken). The
            token IS the credential; principal+plan are taken FROM it, so a client
            can't claim a tier they didn't pay for. No X-Fleet-Auth needed.
          • { principal, plan } → legacy/admin override; requires X-Fleet-Auth
            (FLEET_API_SECRET) since it carries no independent proof.
        """
        length = int(self.headers.get('Content-Length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})

        token = str(req.get('token', '')).strip()
        if token:
            secret = hq_token.secret_bytes()
            if not secret:
                return self._send_json(503, {'error': 'plan tokens not configured'})
            claims = hq_token.verify_plan(token, secret)
            if not claims:
                return self._send_json(401, {'error': 'invalid or expired plan token'})
            principal, plan = claims['principal'], claims['plan']
            if not _validate_principal(principal):
                return self._send_json(400, {'error': 'invalid principal in token'})
            return self._run_set_plan(principal, plan)

        # Legacy/admin path — must carry the shared secret.
        if not self._check_auth():
            return self._send_json(401, {'error': 'unauthorized (token or X-Fleet-Auth required)'})
        principal = (req.get('principal') or '').strip()
        plan = str(req.get('plan', '')).strip().lower()
        if not _validate_principal(principal):
            return self._send_json(400, {'error': 'invalid principal'})
        if plan not in ('free', 'pro', 'always-on'):
            return self._send_json(400, {'error': 'invalid plan'})
        return self._run_set_plan(principal, plan)

    def do_POST(self):
        # Session cookie install is token-gated, not secret-gated (browser call).
        if self.path == '/fleet/session':
            return self._install_session_cookie()
        # Plan application is plan-token-gated (token minted on-chain proves a
        # paid order) — also not secret-gated for the browser path.
        if self.path == '/fleet/set-plan':
            return self._apply_plan()

        # Deprovision is DESTRUCTIVE and self-service: the credential is an
        # on-chain-minted session token (principal comes FROM the token), like
        # /fleet/set-plan. Not gated by X-Fleet-Auth — the browser can't hold
        # that secret. Dispatched before _check_auth like the other token paths.
        if self.path == '/fleet/deprovision':
            return self._handle_deprovision()

        # Provision is self-service like deprovision: an on-chain-minted session
        # token is the credential (principal FROM the token). Dispatched BEFORE
        # _check_auth so dev-mode (no FLEET_API_SECRET) can't wave an anonymous
        # caller through to spin a container for an arbitrary principal.
        if self.path == '/fleet/provision':
            return self._handle_provision()

        if not self._check_auth():
            return self._send_json(401, {'error': 'unauthorized'})
        return self._send_json(404, {'error': 'not found'})

    def _handle_provision(self):
        """POST /fleet/provision — create (or return) a user's container.

        Two credential paths (mirrors /fleet/deprovision):
          • { token }     → self-service. The on-chain-minted session token IS
            the credential; the principal is taken FROM it, so a caller can only
            provision their OWN container. No X-Fleet-Auth needed — browser path.
          • { principal } → admin override; requires X-Fleet-Auth with a real
            FLEET_API_SECRET. REFUSED in dev-mode (no secret) so a bare principal
            can never spin containers on someone else's behalf / rack up cost.

        Returns 200 {status:'existing'} when a live container already exists,
        else 202 {job_id} and provisions asynchronously (~60-90s).
        """
        length = int(self.headers.get('Content-Length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})

        token = str(req.get('token', '')).strip()
        if token:
            secret = hq_token.secret_bytes()
            if not secret:
                return self._send_json(503, {'error': 'sessions not configured'})
            claims = hq_token.verify(token, secret)
            if not claims:
                return self._send_json(401, {'error': 'invalid or expired token'})
            principal = claims['principal']
        else:
            # Admin path — only with a REAL shared secret. In dev-mode
            # _check_auth() would wave everyone through, which must never be
            # enough to provision a container for an arbitrary principal.
            if not SHARED_SECRET or self.headers.get('X-Fleet-Auth') != SHARED_SECRET:
                return self._send_json(401, {'error': 'token required (or admin X-Fleet-Auth)'})
            principal = (req.get('principal') or '').strip()
        if not _validate_principal(principal):
            return self._send_json(400, {'error': 'invalid principal'})

        # Already provisioned? Return the existing endpoint — but only if it's
        # still ALIVE. A stale entry (container deleted/crashed, or its route was
        # never written) would otherwise hand the user a dead endpoint forever and
        # make every Provision click a no-op. Probe /health on the container's
        # private IP first; if it's dead, fall through and re-provision a fresh one.
        full     = _load_fleet_full()
        existing = full.get('users', {}).get(principal)
        if existing and existing.get('ip'):
            _eip   = existing.get('private_ip') or existing.get('ip')
            _eport = existing.get('port', 8787)
            _alive = False
            try:
                import urllib.request
                with urllib.request.urlopen(
                        f'http://{_eip}:{_eport}/health', timeout=5) as _r:
                    _alive = getattr(_r, 'status', _r.getcode()) == 200
            except Exception:
                _alive = False
            if _alive:
                return self._send_json(200, {
                    'status':       'existing',
                    'principal':    principal,
                    'endpoint':     _user_to_endpoint(existing),
                    'gateway_url':  _gateway_url_for_principal(full, principal),
                    'container_id': existing.get('container_instance_id'),
                })
            log.warning(f'existing entry for {principal} is dead '
                        f'({_eip}:{_eport}) — re-provisioning')

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

    def _handle_deprovision(self):
        """POST /fleet/deprovision — permanently delete a user's container.

        Two paths (mirrors /fleet/set-plan):
          • { token }     → self-service. The on-chain-minted session token IS
            the credential; the principal is taken FROM it, so a caller can only
            delete their OWN container. No X-Fleet-Auth needed.
          • { principal } → admin override; requires X-Fleet-Auth with a real
            FLEET_API_SECRET. Explicitly REFUSED in dev-mode (no secret set) —
            a principal alone must never be enough to destroy a container.

        Synchronous (~10-30s): removes the OCI Container Instance, drops it from
        fleet.json, and re-renders the Caddyfile so the `/u/<slug>/*` route is
        removed. The user's vault in Object Storage is DELIBERATELY preserved —
        re-provisioning the same principal recovers it.
        """
        length = int(self.headers.get('Content-Length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            return self._send_json(400, {'error': 'bad json'})

        token = str(req.get('token', '')).strip()
        if token:
            secret = hq_token.secret_bytes()
            if not secret:
                return self._send_json(503, {'error': 'sessions not configured'})
            claims = hq_token.verify(token, secret)
            if not claims:
                return self._send_json(401, {'error': 'invalid or expired token'})
            principal = claims['principal']
        else:
            # Admin path — only with a REAL shared secret. In dev-mode
            # _check_auth() would wave everyone through, which must never be
            # enough to delete someone's container.
            if not SHARED_SECRET or self.headers.get('X-Fleet-Auth') != SHARED_SECRET:
                return self._send_json(401, {'error': 'token required (or admin X-Fleet-Auth)'})
            principal = (req.get('principal') or '').strip()
        if not _validate_principal(principal):
            return self._send_json(400, {'error': 'invalid principal'})

        # Idempotent: nothing on record → treat as already-deleted success so a
        # double-click or a retry doesn't surface a scary error.
        full = _load_fleet_full()
        if not full.get('users', {}).get(principal):
            return self._send_json(200, {
                'status': 'deleted', 'principal': principal,
                'note': 'no container on record (already deleted)',
            })

        log.info(f'deprovision {principal}')
        env = dict(os.environ)
        env.setdefault('PYTHONUTF8', '1')
        try:
            proc = subprocess.run(
                [sys.executable, str(FLEET_MANAGER), 'delete', principal, '--force'],
                capture_output=True, text=True, encoding='utf-8',
                timeout=120, env=env, cwd=str(FLEET_DIR.parent),
            )
        except subprocess.TimeoutExpired:
            return self._send_json(504, {'error': 'delete timed out after 120s'})
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or '').strip()
            log.error(f'deprovision failed for {principal}: {msg[:500]}')
            return self._send_json(502, {'error': msg[:600] or 'delete failed'})

        # Remove the user's gateway route by re-rendering from the now-smaller
        # fleet.json. Non-fatal — the container is already gone either way.
        ok, cmsg = _reload_caddy_with_new_routes()
        if not ok:
            log.warning(f'deprovision caddy reload failed (non-fatal): {cmsg}')
        return self._send_json(200, {
            'status':        'deleted',
            'principal':     principal,
            'caddy_synced':  ok,
            'caddy_message': cmsg,
            'note': 'vault data in Object Storage is preserved — re-provision to recover it',
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
        # Prefer the private (VCN) IP so the public :8787 can be firewalled to
        # the gateway only (Phase B). Public IP is the fallback.
        ip = info.get('private_ip') or ip
        slug = _principal_slug(principal)
        port = info.get('port', 8787)
        block = (
            f'    handle /u/{slug} {{\n'
            f'        redir * /u/{slug}/hq.html\n'
            f'    }}\n'
            f'    handle_path /u/{slug}/* {{\n'
            f'        @approot path /\n'
            f'        rewrite @approot /hq.html\n'
            f'        # /health stays open (liveness). Everything else needs a\n'
            f'        # valid HQ session cookie, checked by verifier.py (:9090).\n'
            f'        @noauth path /health /healthz\n'
            f'        handle @noauth {{\n'
            f'            reverse_proxy {ip}:{port}\n'
            f'        }}\n'
            f'        # CORS preflight (OPTIONS) carries no cookie — let serve.py\n'
            f'        # answer it; the real authed request still needs the cookie.\n'
            f'        @preflight method OPTIONS\n'
            f'        handle @preflight {{\n'
            f'            reverse_proxy {ip}:{port}\n'
            f'        }}\n'
            f'        handle {{\n'
            f'            forward_auth localhost:9090 {{\n'
            f'                uri /verify?slug={slug}\n'
            f'                copy_headers X-Hq-Principal\n'
            f'            }}\n'
            f'            reverse_proxy {ip}:{port}\n'
            f'        }}\n'
            f'    }}'
        )
        user_blocks.append(block)
        # Container routes are HTTPS-only (Secure cookie); not exposed on :80.

    gw           = fleet.get('gateway') or {}
    primary_host = gw.get('public_hostname') or 'hq.cafreso.com'
    gateway_ip   = gw.get('public_ip') or '<unset>'

    return (template
        .replace('__PRIMARY_HOST__',     primary_host)
        .replace('__GATEWAY_IP__',       gateway_ip)
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
        # `sudo cp` + `sudo systemctl reload` need passwordless sudo (NOPASSWD for
        # exactly: /usr/bin/cp <tmp> /etc/caddy/Caddyfile and /usr/bin/systemctl
        # reload caddy). `caddy validate` needs NO root — it only reads the tmp
        # file — so run it directly at the REAL caddy path. On modern Ubuntu the
        # binary is /usr/bin/caddy, NOT /usr/sbin/caddy; the old hardcoded wrong
        # path made `sudo caddy validate` fail and SILENTLY dropped every new
        # user's route (the production "provision isn't working" bug).
        import shutil as _sh
        caddy_bin = (_sh.which('caddy') or next(
            (p for p in ('/usr/bin/caddy', '/usr/local/bin/caddy', '/usr/sbin/caddy')
             if pathlib.Path(p).exists()), None))
        if not caddy_bin:
            return False, ('caddy binary not found (looked in PATH, /usr/bin, '
                           '/usr/local/bin, /usr/sbin) — cannot validate config')
        validate = subprocess.run(
            [caddy_bin, 'validate', '--adapter', 'caddyfile', '--config', str(tmp)],
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


# ── main ────────────────────────────────────────────────────────────────────
def main():
    addr = ('0.0.0.0', PORT)
    print('-' * 60, flush=True)
    print(f'  CafresoAI Fleet API — http://{addr[0]}:{addr[1]}', flush=True)
    print(f'  Auth:    {"shared-secret" if SHARED_SECRET else "DEV MODE (no auth)"}', flush=True)
    print(f'  Fleet:   {FLEET_FILE}', flush=True)
    print(f'  Origins: {", ".join(ALLOWED_ORIGINS) or "(any)"}', flush=True)
    print('-' * 60, flush=True)

    srv = http.server.ThreadingHTTPServer(addr, Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nshutting down…')
        srv.shutdown()


if __name__ == '__main__':
    main()
