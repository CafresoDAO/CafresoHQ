#!/usr/bin/env python3
"""
hq_token.py — verify HQ session tokens minted by the cafresoai_keys canister.

Shared by fleet-api.py (POST /fleet/session cookie setter) and verifier.py
(Caddy forward_auth). Pure Python stdlib — no deps.

Token format (minted on-chain by mintHqSession()):
    v1.<principalText>.<expSeconds>.<hmacHex>
where hmacHex = HMAC-SHA256(secret, "v1.<principalText>.<expSeconds>").

The `secret` is the raw bytes of the hex string set on the canister via
setHqSessionSecret(); mirror the SAME hex into the gateway env HQ_SESSION_SECRET.
The slug routed by Caddy is sha256(principalText)[:16] — the verifier confirms
the token's principal hashes to the requested slug, so a valid token for user A
can never open user B's container.
"""
import hashlib
import hmac
import os
import time

COOKIE_NAME = 'hq_session'


def slug_for(principal: str) -> str:
    """URL slug Caddy routes for a principal — must match fleet-manager's
    _principal_slug() exactly (sha256 of the principal text, first 16 hex)."""
    return hashlib.sha256(principal.encode()).hexdigest()[:16]


def secret_bytes() -> bytes:
    """Raw HMAC key from the HQ_SESSION_SECRET env (hex). b'' if unset/invalid."""
    hexs = os.environ.get('HQ_SESSION_SECRET', '').strip()
    if not hexs:
        return b''
    try:
        return bytes.fromhex(hexs)
    except ValueError:
        return b''


def verify(token: str, secret: bytes, now: int = None):
    """Return {'principal', 'exp'} if the token is well-formed, unexpired, and
    its HMAC matches `secret`; otherwise None. Constant-time tag compare."""
    if not token or not secret:
        return None
    parts = token.split('.')
    if len(parts) != 4:
        return None
    ver, principal, exp_s, tag_hex = parts
    if ver != 'v1' or not principal or not exp_s.isdigit():
        return None
    exp = int(exp_s)
    if now is None:
        now = int(time.time())
    if exp < now:
        return None
    signed = f'{ver}.{principal}.{exp_s}'.encode('utf-8')
    expected = hmac.new(secret, signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, tag_hex.lower()):
        return None
    return {'principal': principal, 'exp': exp}


def verify_for_slug(token: str, slug: str, secret: bytes, now: int = None):
    """verify() + confirm the token's principal owns `slug`. Returns the claims
    dict on success, else None."""
    claims = verify(token, secret, now=now)
    if not claims:
        return None
    if not slug or slug_for(claims['principal']) != slug:
        return None
    return claims
