#!/usr/bin/env python3
"""Every GET on cafresohq_state used to be upgraded to an update call, so each
public read was a paid message: ~7.7 M cycles on mainnet's 13-node subnet.
That covers a published site page, a receipt, /library/*.json,
/operator/config.json (read by every serve.py and search worker), and a
/search/job poll. It is the most likely source of the canister's unexplained
~6 B/day burn.

GET/HEAD are now answered from the query `http_request`. Clients read the
plain <id>.icp0.io URL, not `.raw`, so a bare uncertified answer would fail
the gateway's response verification. SkipCert certifies "no certification
needed" for every path (response verification v2), and each query answer
carries the matching headers. Checked against dfx 0.24.3's local gateway on
2026-10-24:
  * the routes answer 200/404/403 through the gateway;
  * a tampered expression header gets "500 Response verification failed";
  * 50 GETs cost 0 cycles, while 50 upgraded POSTs cost 0.55 M each.

This suite pins that by reading the source and compiling it with the pinned
dfx where it is on PATH:

  * the query answers only GET/HEAD and upgrades everything else;
  * the query falls back to upgrading when no certificate is available;
  * the query and the update share ONE router, so they cannot drift;
  * the router does nothing on a GET that must persist: worker routes deny
    every non-POST, search submit requires POST, and tendJobs is the only
    write, which a query discards;
  * the skip tree is set as certified data on install AND on upgrade;
  * SkipCert's expression, tree and expr_path follow the spec, recomputed
    here in Python (expr_path cross-checked against the known constant);
  * `dfx build cafresohq_state --check` passes (skipped without dfx).

Run:  python3 scripts/test_a_public_read_of_the_state_canister_costs_no_cycles.py
"""
import base64
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'src' / 'cafresohq_state' / 'main.mo'
SKIP = ROOT / 'src' / 'cafresohq_state' / 'SkipCert.mo'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (('' if cond else '  -- ' + str(detail)[:300])))
    if not cond:
        FAILS.append(name)


def body_of(src, header_regex):
    m = re.search(header_regex, src)
    if not m:
        return ''
    rest = src[m.end():]
    n = re.search(r'\n  (?:public |system |func |stable |let |var |//)', rest)
    return rest[: n.start()] if n else rest


def cbor_head(major, n):
    return bytes([major << 5 | n]) if n < 24 else bytes([major << 5 | 24, n])


def main():
    print('a public read of the state canister costs no cycles')
    src = SRC.read_text()
    skip = SKIP.read_text()

    q = body_of(src, r'\n  public query func http_request\(req : HttpRequest\) : async HttpResponse \{')
    check('the query upgrades anything that is not GET/HEAD',
          'if (req.method != "GET" and req.method != "HEAD") { return upgrade };' in q)
    check('the query upgrades when no certificate is available',
          'switch (CertifiedData.getCertificate()) { case (?c) c; case null { return upgrade } };' in q)
    check('the query answers through the shared router with the skip headers and no upgrade',
          'let res = route(req);' in q and
          '{ res with headers = Array.append(res.headers, SkipCert.headers(cert)); upgrade = null };' in q)
    u = body_of(src, r'\n  public func http_request_update\(req : HttpRequest\) : async HttpResponse \{')
    check('the update answers through the same router', 'let res = route(req);' in u)

    r = body_of(src, r'\n  func route\(req : HttpRequest\) : HttpResponse \{')
    order = [m.start() for m in (re.search(p, r) for p in [
        r'receiptLookup\(req\.url\)', r'operatorLookup\(req\.url\)', r'searchLookup\(req\)',
        r'libraryLookup\(req\.url\)', r'workerRoute\(req\)', r'serveSite\(req\.url\)']) if m]
    check('the router keeps the receipt → operator → search → library → worker → site order',
          len(order) == 6 and order == sorted(order), order)

    w = body_of(src, r'\n  func workerRoute\(req : HttpRequest\) : \?HttpResponse \{')
    check('a GET on /worker/* is denied before anything runs',
          w.find('if (req.method != "POST") { return ?workerDeny() };') != -1 and
          w.find('if (req.method != "POST") { return ?workerDeny() };') < w.find('tendJobs();'))
    s = body_of(src, r'\n  func searchLookup\(req : HttpRequest\) : \?HttpResponse \{')
    check('search submit only runs on POST', 'parts[1] == "submit" and req.method == "POST"' in s)

    up = body_of(src, r'\n  system func postupgrade\(\) \{')
    check('an upgrade sets the skip tree as certified data', 'CertifiedData.set(SkipCert.rootHash());' in up)
    check('a fresh install sets it at the actor tail',
          re.search(r'\n  CertifiedData\.set\(SkipCert\.rootHash\(\)\);[^\n]*\n\}\s*$', src) is not None)

    expr = 'default_certification(ValidationArgs{no_certification:Empty{}})'
    check('the expression is the spec\'s no_certification expression', f'public let EXPR : Text = "{expr}";' in skip)
    check('the header carries version 2, the tree and the expr_path',
          'certificate=:' in skip and ':, tree=:' in skip and ':, expr_path=:' in skip and ':, version=2' in skip)
    for sep in ['ic-hashtree-leaf', 'ic-hashtree-labeled']:
        check(f'hashes use the {sep} domain separator', f'domain("{sep}")' in skip)
    path_cbor = b'\xd9\xd9\xf7' + cbor_head(4, 2) + cbor_head(3, 9) + b'http_expr' + cbor_head(3, 3) + b'<*>'
    check('expr_path ["http_expr","<*>"] encodes to the known constant',
          base64.b64encode(path_cbor).decode() == '2dn3gmlodHRwX2V4cHJjPCo+')
    check('SkipCert encodes expr_path as exactly that array',
          'cat([SELF_DESCRIBE, head(4, 2), cborText("http_expr"), cborText("<*>")])' in skip)
    check('the tree is http_expr / <*> / expr_hash → leaf ""',
          'cborLabeled(bytes("http_expr"), cborLabeled(bytes("<*>"), cborLabeled(exprHash(), cat([head(4, 2), [3], cborBytes([])]))))' in skip
          and 'labeled(bytes("http_expr"), labeled(bytes("<*>"), labeled(exprHash(), leafHash())))' in skip)

    if shutil.which('dfx'):
        env = dict(os.environ, DFX_VERSION=(ROOT / '.dfx-version').read_text().strip() if (ROOT / '.dfx-version').exists() else '0.24.3')
        p = subprocess.run(['dfx', 'build', 'cafresohq_state', '--check'], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=600)
        check('dfx build cafresohq_state --check passes', p.returncode == 0, (p.stderr or p.stdout)[-400:])
    else:
        print('  skip compile check: dfx is not on PATH')

    if FAILS:
        print(f'FAILED: {len(FAILS)}'); return 1
    print('OK'); return 0


if __name__ == '__main__':
    sys.exit(main())
