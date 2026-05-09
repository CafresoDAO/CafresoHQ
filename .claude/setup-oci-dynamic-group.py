#!/usr/bin/env python3
"""
Create OCI Dynamic Group + Policy so Container Instances can access Object Storage
using Instance Principal authentication (no API keys needed in the container).

Matching rule: all Container Instances in the tenancy.
Policy: allow them to manage objects in the vault bucket.
"""
import base64, hashlib, http.client, json, os, subprocess, sys, tempfile, urllib.parse
from email.utils import formatdate

USER_OCID    = "ocid1.user.oc1..aaaaaaaa2szrls3vtki3t3ilwfzakogjwbheyctaolaln6reuxskdtbby4xa"
TENANCY_OCID = "ocid1.tenancy.oc1..aaaaaaaazx7gtqeqvbdvsbjcwo2r6gqz7sp4iqxfai3vzgvqt7kswvnbggkq"
FINGERPRINT  = "c3:e7:63:0e:03:02:63:6e:ec:47:bf:a8:84:29:c2:22"
REGION       = "us-ashburn-1"
KEY_FILE     = "/mnt/c/Users/Anthony/.oci/oci_api_key.pem"
KEY_ID       = f"{TENANCY_OCID}/{USER_OCID}/{FINGERPRINT}"

IDENTITY_HOST = f"identity.{REGION}.oraclecloud.com"

DG_NAME       = "cafresoai-container-instances"
DG_DESC       = "CafresoAI OCI Container Instances (fleet)"
POLICY_NAME   = "cafresoai-container-vault-access"
POLICY_DESC   = "Allow CafresoAI containers to access Object Storage vault bucket"
BUCKET_NAME   = "cafresoai-fleet-vault"

# Dynamic group rule: all Container Instances in our tenancy (root compartment)
DG_RULE = f"All {{resource.type = 'computecontainerinstance', resource.compartment.id = '{TENANCY_OCID}'}}"

POLICY_STATEMENTS = [
    f"Allow dynamic-group {DG_NAME} to manage objects in tenancy where target.bucket.name = '{BUCKET_NAME}'",
    f"Allow dynamic-group {DG_NAME} to read buckets in tenancy where target.bucket.name = '{BUCKET_NAME}'",
]

# ── OCI request signing ──────────────────────────────────────────────────────

def sign(message: str) -> str:
    msg_bytes = message.encode()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tf:
        tf.write(msg_bytes); tmp_in = tf.name
    tmp_out = tmp_in + ".sig"
    subprocess.run(["openssl","dgst","-sha256","-sign",KEY_FILE,"-out",tmp_out,tmp_in],
                   check=True, capture_output=True)
    with open(tmp_out, "rb") as f: sig = f.read()
    os.unlink(tmp_in); os.unlink(tmp_out)
    return base64.b64encode(sig).decode()

def sha256_b64(body: bytes) -> str:
    return base64.b64encode(hashlib.sha256(body).digest()).decode()

def oci_request(method, host, path, body=None):
    now = formatdate(usegmt=True)
    body_bytes = body.encode() if isinstance(body, str) else (body or b"")
    hdrs = {"host": host, "date": now, "content-type": "application/json"}
    signed = ["(request-target)", "date", "host"]
    if method in ("POST", "PUT") and body_bytes:
        hdrs["x-content-sha256"] = sha256_b64(body_bytes)
        hdrs["content-length"] = str(len(body_bytes))
        signed += ["content-type", "content-length", "x-content-sha256"]

    signing_str = "\n".join(
        f"(request-target): {method.lower()} {path}" if h == "(request-target)" else f"{h}: {hdrs[h]}"
        for h in signed
    )
    sig = sign(signing_str)
    hdrs["Authorization"] = (
        f'Signature version="1",headers="{" ".join(signed)}",'
        f'keyId="{KEY_ID}",algorithm="rsa-sha256",signature="{sig}"'
    )
    conn = http.client.HTTPSConnection(host)
    conn.request(method, path, body=body_bytes or None, headers=hdrs)
    resp = conn.getresponse()
    raw = resp.read()
    try:
        data = json.loads(raw)
    except Exception:
        data = raw.decode()
    return resp.status, data

# ── List existing resources ──────────────────────────────────────────────────

def list_dynamic_groups():
    path = f"/20160918/dynamicGroups?compartmentId={urllib.parse.quote(TENANCY_OCID)}&limit=100"
    s, d = oci_request("GET", IDENTITY_HOST, path)
    if s != 200:
        print(f"  ERROR listing dynamic groups: {s} {d}")
        return []
    return d if isinstance(d, list) else []

def list_policies():
    path = f"/20160918/policies?compartmentId={urllib.parse.quote(TENANCY_OCID)}&limit=100"
    s, d = oci_request("GET", IDENTITY_HOST, path)
    if s != 200:
        print(f"  ERROR listing policies: {s} {d}")
        return []
    return d if isinstance(d, list) else []

def create_dynamic_group():
    payload = json.dumps({
        "compartmentId": TENANCY_OCID,
        "name": DG_NAME,
        "description": DG_DESC,
        "matchingRule": DG_RULE,
    })
    s, d = oci_request("POST", IDENTITY_HOST, "/20160918/dynamicGroups", payload)
    return s, d

def create_policy(dg_id):
    payload = json.dumps({
        "compartmentId": TENANCY_OCID,
        "name": POLICY_NAME,
        "description": POLICY_DESC,
        "statements": POLICY_STATEMENTS,
    })
    s, d = oci_request("POST", IDENTITY_HOST, "/20160918/policies", payload)
    return s, d

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=== OCI Dynamic Group + Policy Setup ===")
    print(f"Tenancy: {TENANCY_OCID[:30]}...")
    print()

    # 1. Check / create dynamic group
    print("1. Dynamic Group:")
    existing_dgs = list_dynamic_groups()
    existing = next((g for g in existing_dgs if g.get("name") == DG_NAME), None)
    if existing:
        dg_id = existing["id"]
        print(f"   Already exists: {dg_id}")
        print(f"   Rule: {existing.get('matchingRule')}")
    else:
        print(f"   Creating '{DG_NAME}'...")
        s, d = create_dynamic_group()
        if s in (200, 201):
            dg_id = d["id"]
            print(f"   Created: {dg_id}")
        else:
            print(f"   ERROR {s}: {d}")
            sys.exit(1)
    print()

    # 2. Check / create policy
    print("2. Policy:")
    existing_pols = list_policies()
    existing_pol = next((p for p in existing_pols if p.get("name") == POLICY_NAME), None)
    if existing_pol:
        print(f"   Already exists: {existing_pol['id']}")
        print(f"   Statements: {existing_pol.get('statements')}")
    else:
        print(f"   Creating '{POLICY_NAME}'...")
        s, d = create_policy(dg_id)
        if s in (200, 201):
            print(f"   Created: {d.get('id')}")
            print(f"   Statements:")
            for stmt in d.get("statements", []):
                print(f"     - {stmt}")
        else:
            print(f"   ERROR {s}: {d}")
            sys.exit(1)
    print()

    print("=== Done ===")
    print()
    print("IAM changes take ~1-2 minutes to propagate.")
    print("After that, containers can use Instance Principal auth to access Object Storage.")
    print()
    print("Test by hitting the vault blob endpoint after ~2 min:")
    print("  curl -s https://hq.cafreso.com/u/9faa5b3371bb1fee/vault/blob/test-id")

if __name__ == "__main__":
    main()
