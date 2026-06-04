#!/usr/bin/env python3
"""
verifier.py — Caddy forward_auth backend for per-container access control.

Runs on the gateway VM (localhost:9090). Caddy calls it before proxying any
/u/<slug>/* request (except /health). It reads the `hq_session` cookie, verifies
the HMAC token (minted on-chain by the cafresoai_keys canister), and confirms the
token's principal owns the requested slug. On success → 200 + X-Hq-Principal
(copied onto the upstream request for defense-in-depth). Otherwise → 401, and the
request never reaches the container.

Caddy config (per user, rendered by fleet-manager.py / fleet-api.py):

    forward_auth localhost:9090 {
        uri /verify?slug=<slug>
        copy_headers X-Hq-Principal
    }

Run:
    HQ_SESSION_SECRET=<hex> python3 oci-fleet/verifier.py
    → http://127.0.0.1:9090   (bind localhost only; never expose publicly)

The secret is the SAME hex set on the canister via setHqSessionSecret().
"""
import http.cookies
import http.server
import logging
import os
import urllib.parse

import hq_token

PORT = int(os.environ.get('HQ_VERIFIER_PORT', '9090'))
BIND = os.environ.get('HQ_VERIFIER_BIND', '127.0.0.1')

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] verifier: %(message)s')
log = logging.getLogger('verifier')


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'CafresoAI-Verifier/1.0'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):  # quieter access log
        pass

    def _deny(self, reason: str, code: int = 401):
        body = b'unauthorized'
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _allow(self, principal: str):
        self.send_response(200)
        self.send_header('Content-Length', '0')
        # Copied onto the upstream request by Caddy's `copy_headers`.
        self.send_header('X-Hq-Principal', principal)
        self.end_headers()

    def _cookie_token(self) -> str:
        raw = self.headers.get('Cookie', '')
        if not raw:
            return ''
        try:
            jar = http.cookies.SimpleCookie()
            jar.load(raw)
            morsel = jar.get(hq_token.COOKIE_NAME)
            return morsel.value if morsel else ''
        except Exception:
            return ''

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)

        if u.path == '/health':
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            try:
                self.wfile.write(b'ok')
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        if u.path != '/verify':
            return self._deny('not found', code=404)

        secret = hq_token.secret_bytes()
        if not secret:
            # Fail closed — never allow when the secret isn't configured.
            log.warning('HQ_SESSION_SECRET not set — denying all requests')
            return self._deny('verifier not configured')

        params = urllib.parse.parse_qs(u.query)
        slug = (params.get('slug') or [''])[0].strip()
        if not slug:
            return self._deny('missing slug')

        token = self._cookie_token()
        if not token:
            return self._deny('no session cookie')

        claims = hq_token.verify_for_slug(token, slug, secret)
        if not claims:
            return self._deny('invalid/expired token or slug mismatch')

        return self._allow(claims['principal'])

    # forward_auth uses the original method; treat any verb the same.
    do_POST = do_GET
    do_HEAD = do_GET
    do_PUT = do_GET
    do_DELETE = do_GET
    do_PATCH = do_GET
    do_OPTIONS = do_GET


def main():
    addr = (BIND, PORT)
    print('-' * 60, flush=True)
    print(f'  CafresoAI Verifier — http://{addr[0]}:{addr[1]}', flush=True)
    print(f'  Secret: {"configured" if hq_token.secret_bytes() else "MISSING (denies all)"}',
          flush=True)
    print('-' * 60, flush=True)
    srv = http.server.ThreadingHTTPServer(addr, Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == '__main__':
    main()
