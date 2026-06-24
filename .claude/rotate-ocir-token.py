#!/usr/bin/env python3
"""
Rotate an OCI auth token for OCIR access.
Uses OCI REST API with request signing (no OCI CLI/SDK needed).
"""
import base64
import hashlib
import http.client
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from email.utils import formatdate

# ── Config ──────────────────────────────────────────────────────────────────

USER_OCID      = "ocid1.user.oc1..aaaaaaaa2szrls3vtki3t3ilwfzakogjwbheyctaolaln6reuxskdtbby4xa"
TENANCY_OCID   = "ocid1.tenancy.oc1..aaaaaaaazx7gtqeqvbdvsbjcwo2r6gqz7sp4iqxfai3vzgvqt7kswvnbggkq"
FINGERPRINT    = "c3:e7:63:0e:03:02:63:6e:ec:47:bf:a8:84:29:c2:22"
REGION         = "us-ashburn-1"
KEY_FILE       = os.environ.get("OCI_KEY_FILE", os.path.expanduser("~/.oci/oci_api_key.pem"))

IDENTITY_HOST  = f"identity.{REGION}.oraclecloud.com"
KEY_ID         = f"{TENANCY_OCID}/{USER_OCID}/{FINGERPRINT}"

# Token description for the new auth token
NEW_TOKEN_DESC = "cafresoai-ocir-push"

# ── OCI Request Signing ──────────────────────────────────────────────────────

def _load_private_key(path):
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
    except ImportError:
        pass
    # Fallback: use subprocess openssl (always available)
    return None

def _sign_rsa_sha256_openssl(key_file, message_bytes):
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tf:
        tf.write(message_bytes)
        tmp_in = tf.name
    tmp_out = tmp_in + ".sig"
    try:
        subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_file, "-out", tmp_out, tmp_in],
            check=True, capture_output=True
        )
        with open(tmp_out, "rb") as f:
            sig = f.read()
    finally:
        os.unlink(tmp_in)
        if os.path.exists(tmp_out):
            os.unlink(tmp_out)
    return base64.b64encode(sig).decode()

def _sign(message: str) -> str:
    msg_bytes = message.encode("utf-8")
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
        with open(KEY_FILE, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
        sig = key.sign(msg_bytes, padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode()
    except ImportError:
        return _sign_rsa_sha256_openssl(KEY_FILE, msg_bytes)

def _sha256_b64(body: bytes) -> str:
    return base64.b64encode(hashlib.sha256(body).digest()).decode()

def _auth_header(method, path, host, headers, signed_header_names):
    signing_parts = []
    for h in signed_header_names:
        if h == "(request-target)":
            signing_parts.append(f"(request-target): {method.lower()} {path}")
        else:
            signing_parts.append(f"{h}: {headers[h]}")
    signing_string = "\n".join(signing_parts)
    signature = _sign(signing_string)
    headers_str = " ".join(signed_header_names)
    return (
        f'Signature version="1",'
        f'headers="{headers_str}",'
        f'keyId="{KEY_ID}",'
        f'algorithm="rsa-sha256",'
        f'signature="{signature}"'
    )

def _request(method, host, path, body=None):
    now = formatdate(usegmt=True)
    body_bytes = body.encode() if isinstance(body, str) else (body or b"")

    base_headers = {
        "host": host,
        "date": now,
        "content-type": "application/json",
    }
    signed_names = ["(request-target)", "date", "host"]

    if method in ("POST", "PUT", "DELETE") and body_bytes:
        sha = _sha256_b64(body_bytes)
        base_headers["x-content-sha256"] = sha
        base_headers["content-length"] = str(len(body_bytes))
        signed_names += ["content-type", "content-length", "x-content-sha256"]
    elif method == "DELETE":
        signed_names += ["content-type"]

    auth = _auth_header(method, path, host, base_headers, signed_names)
    base_headers["Authorization"] = auth

    conn = http.client.HTTPSConnection(host)
    conn.request(method, path, body=body_bytes if body_bytes else None, headers=base_headers)
    resp = conn.getresponse()
    raw = resp.read()
    return resp.status, raw.decode() if raw else ""

# ── Auth Token Operations ────────────────────────────────────────────────────

def list_auth_tokens():
    path = f"/20160918/users/{urllib.parse.quote(USER_OCID, safe='')}/authTokens"
    status, body = _request("GET", IDENTITY_HOST, path)
    if status != 200:
        print(f"ERROR listing tokens: HTTP {status}\n{body}")
        sys.exit(1)
    return json.loads(body)

def delete_auth_token(token_id):
    path = f"/20160918/users/{urllib.parse.quote(USER_OCID, safe='')}/authTokens/{urllib.parse.quote(token_id, safe='')}"
    status, body = _request("DELETE", IDENTITY_HOST, path)
    if status not in (200, 204):
        print(f"ERROR deleting token {token_id}: HTTP {status}\n{body}")
        sys.exit(1)
    print(f"  deleted token {token_id}")

def create_auth_token(description):
    path = f"/20160918/users/{urllib.parse.quote(USER_OCID, safe='')}/authTokens"
    payload = json.dumps({"description": description})
    status, body = _request("POST", IDENTITY_HOST, path, body=payload)
    if status != 200:
        print(f"ERROR creating token: HTTP {status}\n{body}")
        sys.exit(1)
    data = json.loads(body)
    return data["token"], data["id"]

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=== OCI Auth Token Rotation ===")
    print(f"User: {USER_OCID[:30]}...")
    print()

    # 1. List existing tokens
    print("1. Existing auth tokens:")
    tokens = list_auth_tokens()
    for t in tokens:
        print(f"   id={t['id']}  desc={t.get('description','(none)')}  created={t.get('timeCreated','?')}")
    print(f"   Total: {len(tokens)}")
    print()

    # 2. Delete the oldest token if at quota (2)
    if len(tokens) >= 2:
        oldest = sorted(tokens, key=lambda t: t.get("timeCreated", ""))[0]
        print(f"2. At quota. Deleting oldest: {oldest['id']} ({oldest.get('description','(none)')})")
        delete_auth_token(oldest["id"])
    else:
        print(f"2. Under quota ({len(tokens)}/2) — no deletion needed.")
    print()

    # 3. Create new token
    print(f"3. Creating new auth token '{NEW_TOKEN_DESC}'...")
    new_token, new_id = create_auth_token(NEW_TOKEN_DESC)
    print(f"   Created id={new_id}")
    print()

    # 4. Output docker login command
    # OCIR username format: <tenancy-namespace>/<username>
    # The namespace for idwv6126novh is known from prior use
    ocir_host = "iad.ocir.io"
    namespace = "idwv6126novh"
    # OCI username for auth token login = tenancy-namespace/user-email
    # But simpler: use tenancy_namespace/oracleidentitycloudservice/<email> or just namespace/<user>
    # For OCIR token auth the username is: <namespace>/oracleidentitycloudservice/anthony@cafreso.com
    # or for non-federated: <namespace>/<user-ocid-short>
    # The safest is to print both and let docker login figure out which works
    user_for_docker = f"{namespace}/anthony@cafreso.com"

    print("=== Docker Login Command ===")
    print(f"Run this in WSL:")
    print()
    print(f"  echo '{new_token}' | docker login {ocir_host} -u '{user_for_docker}' --password-stdin")
    print()
    print(f"If that fails with 401, try federated user format:")
    print(f"  echo '{new_token}' | docker login {ocir_host} -u '{namespace}/oracleidentitycloudservice/anthony@cafreso.com' --password-stdin")
    print()
    print(f"Token (keep secret): {new_token}")

if __name__ == "__main__":
    main()
