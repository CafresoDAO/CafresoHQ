#!/usr/bin/env python3
"""A marketplace coworker has to claim a job and file a result while its
owner's browser is closed — so the container needs to sign a canister call
itself, and the runtime image has nothing but the standard library to do it
with (docker/requirements-serve.txt: "serve.py itself uses only stdlib").

`ic_agent.py` is that client. This suite holds it against published vectors
rather than against itself:

  * ed25519 — RFC 8032 §7.1 tests 1–3 (key derivation and signatures), plus
    the signature must verify and a flipped bit must not.
  * principals — the management canister ("aaaaa-aa"), the anonymous
    principal ("2vxsx-fae"), a self-authenticating principal's shape, the
    checksum catching a corrupted text form.
  * CBOR — RFC 8949 Appendix A examples, and the self-describe tag being
    transparent on decode.
  * Candid — the spec's byte-exact encodings for (), nat, text, bool, opt,
    principal, a record and a variant; field hashes for `ok`/`err`; and
    every descriptor round-tripping through encode → decode with names.
  * request id — the interface spec's worked example (the "hello" call whose
    id is 8781291c…f94b), and order-independence.
  * certificate lookup — a hash tree with forks, labels and a pruned branch.
  * the wire — a stub replica served from a thread answers a query (replied
    and rejected), an update the old way (202 then read_state polling until
    the certificate says replied) and the new way (200 with the certificate
    in the body), and a rejected update. The envelope it receives is checked
    for a signature that verifies under the sender's own public key.

No network, no dfx, no mainnet. Run:
    python3 scripts/test_a_coworker_can_sign_a_canister_call_from_its_own_container.py
"""
import hashlib
import http.server
import json
import os
import stat
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ic_agent as ic  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + ((' — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def hx(b):
    return bytes(b).hex()


# ── 1. ed25519 against RFC 8032 ─────────────────────────────────────────────
def test_ed25519():
    print('ed25519 — RFC 8032 §7.1')
    vectors = [
        ('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60',
         'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
         'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'),
        ('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb',
         '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
         '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00'),
        ('c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7',
         'fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025', 'af82',
         '6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a'),
    ]
    for n, (sk, pk, msg, sig) in enumerate(vectors, 1):
        seed, msg_b = bytes.fromhex(sk), bytes.fromhex(msg)
        check(f'test {n}: public key', hx(ic.ed25519_public_key(seed)) == pk)
        check(f'test {n}: signature', hx(ic.ed25519_sign(seed, msg_b)) == sig)
        check(f'test {n}: verifies', ic.ed25519_verify(bytes.fromhex(pk), msg_b, bytes.fromhex(sig)))
        bad = bytearray(bytes.fromhex(sig))
        bad[3] ^= 0x01
        check(f'test {n}: a flipped bit does not verify', not ic.ed25519_verify(bytes.fromhex(pk), msg_b, bytes(bad)))
    ident = ic.Ed25519Identity.generate()
    check('a fresh identity signs something that verifies', ident.verify(b'hello office', ident.sign(b'hello office')))
    check('DER public key is the RFC 8410 SubjectPublicKeyInfo (44 bytes)',
          len(ident.der_public_key) == 44 and ident.der_public_key[:12] == bytes.fromhex('302a300506032b6570032100'))


# ── 2. principals ───────────────────────────────────────────────────────────
def test_principal():
    print('principals')
    check('management canister is "aaaaa-aa"', ic.Principal.management().to_text() == 'aaaaa-aa')
    check('anonymous is "2vxsx-fae"', ic.Principal.anonymous().to_text() == '2vxsx-fae')
    check('"aaaaa-aa" parses to empty bytes', ic.Principal.from_text('aaaaa-aa').raw == b'')
    check('"2vxsx-fae" parses to 0x04', ic.Principal.from_text('2vxsx-fae').raw == b'\x04')
    # A real canister id in the repo: cafresohq_keys.
    keys = 'vhw7q-lqaaa-aaaab-agthq-cai'
    p = ic.Principal.from_text(keys)
    check('a canister id round-trips through text', p.to_text() == keys)
    check('a canister id is 10 bytes ending in 0x01', len(p.raw) == 10 and p.raw[-1] == 0x01)
    ident = ic.Ed25519Identity.from_seed(bytes(range(32)))
    sa = ident.principal
    check('a self-authenticating principal is sha224(DER) + 0x02',
          sa.raw == hashlib.sha224(ident.der_public_key).digest() + b'\x02' and len(sa.raw) == 29)
    check('it round-trips through text', ic.Principal.from_text(sa.to_text()) == sa)
    check('the same seed always gives the same principal',
          ic.Ed25519Identity.from_seed(bytes(range(32))).principal == sa)
    corrupted = keys[:-1] + ('j' if keys[-1] != 'j' else 'k')
    try:
        ic.Principal.from_text(corrupted)
        check('a corrupted text form is rejected', False, 'accepted')
    except ValueError:
        check('a corrupted text form is rejected', True)


# ── 3. CBOR (RFC 8949 Appendix A) ───────────────────────────────────────────
def test_cbor():
    print('CBOR — RFC 8949 appendix A')
    cases = [
        (0, '00'), (1, '01'), (10, '0a'), (23, '17'), (24, '1818'), (25, '1819'),
        (100, '1864'), (1000, '1903e8'), (1000000, '1a000f4240'),
        (1000000000000, '1b000000e8d4a51000'), (-1, '20'), (-10, '29'), (-100, '3863'),
        (False, 'f4'), (True, 'f5'), (None, 'f6'),
        (b'', '40'), (b'\x01\x02\x03\x04', '4401020304'),
        ('', '60'), ('a', '6161'), ('IETF', '6449455446'), ('ü', '62c3bc'),
        ([], '80'), ([1, 2, 3], '83010203'), ([1, [2, 3], [4, 5]], '8301820203820405'),
        ({}, 'a0'), ({'a': 1, 'b': [2, 3]}, 'a26161016162820203'),
    ]
    for v, expect in cases:
        enc = ic.cbor_encode(v)
        check(f'encode {v!r} → {expect}', hx(enc) == expect, hx(enc))
        check(f'decode {expect} → {v!r}', ic.cbor_decode(bytes.fromhex(expect)) == v)
    check('a 25-element array uses the 1-byte length form',
          hx(ic.cbor_encode(list(range(25)))).startswith('9819'))
    check('self-describe tag 55799 is transparent on decode',
          ic.cbor_decode(bytes.fromhex('d9d9f7' + 'a1616101')) == {'a': 1})
    # Indefinite lengths (RFC 8949 §3.2.3). Replicas DO emit these — the
    # first real-replica run (#429) died on a pocket-ic query reply until
    # the reader learned them. The RFC's own examples, then a reply shape.
    for hexs, want in (('5f42010243030405ff', b'\x01\x02\x03\x04\x05'),
                       ('7f657374726561646d696e67ff', 'streaming'),
                       ('9f018202039f0405ffff', [1, [2, 3], [4, 5]]),
                       ('bf6346756ef563416d7421ff', {'Fun': True, 'Amt': -2}),
                       ('d9d9f7bf667374617475736772657' + '06c696564ff', {'status': 'replied'})):
        check(f'indefinite-length decode {hexs[:12]}… → {want!r}', ic.cbor_decode(bytes.fromhex(hexs)) == want)
    for bad in ('5f7f61ffff', '1f', '5f4101'):
        try:
            ic.cbor_decode(bytes.fromhex(bad))
            check(f'malformed indefinite item {bad} is refused', False, 'decoded')
        except ValueError:
            check(f'malformed indefinite item {bad} is refused', True)
    check('a principal encodes as its raw bytes',
          ic.cbor_encode(ic.Principal.anonymous()) == b'\x41\x04')


# ── 4. Candid ───────────────────────────────────────────────────────────────
def test_candid():
    print('Candid — byte-exact against the spec')
    check('() is DIDL 00 00', hx(ic.candid_encode([])) == '4449444c0000')
    check('(42 : nat)', hx(ic.candid_encode([('nat', 42)])) == '4449444c00017d2a')
    check('(-42 : int)', hx(ic.candid_encode([('int', -42)])) == '4449444c00017c56')
    check('("hi" : text)', hx(ic.candid_encode([('text', 'hi')])) == '4449444c0001710268 69'.replace(' ', ''))
    check('(true : bool)', hx(ic.candid_encode([('bool', True)])) == '4449444c00017e01')
    check('(300 : nat64) little-endian', hx(ic.candid_encode([('nat64', 300)])) == '4449444c0001782c01000000000000')
    check('(principal "aaaaa-aa")', hx(ic.candid_encode([('principal', 'aaaaa-aa')])) == '4449444c0001680100')
    check('(opt 5 : opt nat) → table [opt nat], value 01 05',
          hx(ic.candid_encode([(('opt', 'nat'), 5)])) == '4449444c016e7d01000105')
    check('(null : opt nat) → 00', hx(ic.candid_encode([(('opt', 'nat'), None)])) == '4449444c016e7d010000')
    check('(vec {1;2} : vec nat)', hx(ic.candid_encode([(('vec', 'nat'), [1, 2])])) == '4449444c016d7d0100020102')
    check('(blob "\\01\\02")', hx(ic.candid_encode([('blob', b'\x01\x02')])) == '4449444c016d7b0100020102')
    rec = ('record', [('a', 'nat'), ('b', 'text')])
    check('(record { a = 1 : nat; b = "x" : text }) fields in hash order',
          hx(ic.candid_encode([(rec, {'a': 1, 'b': 'x'})])) == '4449444c016c02617d62710100010178')
    # By hand from the spec's fold: "ok" = 111*223 + 107 = 24860;
    # "err" = (101*223 + 114)*223 + 114 = 5048165.
    check('field_hash("ok") == 24860', ic.field_hash('ok') == 24860)
    check('field_hash("err") == 5048165', ic.field_hash('err') == 5048165)
    res = ('variant', [('ok', 'nat'), ('err', 'text')])
    # ok (24860 → leb 9c c2 01) sorts before err (5048165 → e5 8e b4 02): index 0 is ok.
    check('(variant { ok = 5 })', hx(ic.candid_encode([(res, {'ok': 5})])) == '4449444c016b029cc2017de58eb4027101000005')
    check('(variant { err = "no" })', hx(ic.candid_encode([(res, {'err': 'no'})])) == '4449444c016b029cc2017de58eb40271010001026e6f')

    # round trips, with names restored from the descriptor
    job = ('record', [
        ('id', 'nat64'), ('title', 'text'), ('poster', 'principal'),
        ('budget', 'nat'), ('worker', ('opt', 'principal')),
        ('tags', ('vec', 'text')), ('state', ('variant', [('open', None), ('claimed', 'principal'), ('paid', 'nat')])),
        ('proof', 'blob'),
    ])
    poster = ic.Ed25519Identity.from_seed(b'\x07' * 32).principal
    v = {'id': 7, 'title': 'write a brief', 'poster': poster, 'budget': 10 ** 20,
         'worker': None, 'tags': ['research', 'brief'], 'state': {'claimed': poster}, 'proof': b'\x00\xff'}
    enc = ic.candid_encode([(job, v), ('text', 'ok'), (('opt', 'nat'), 3)])
    dec = ic.candid_decode(enc, [job, 'text', ('opt', 'nat')])
    check('a job record round-trips with field names', dec[0] == v, dec[0])
    check('a large nat survives (10^20)', dec[0]['budget'] == 10 ** 20)
    check('trailing args round-trip', dec[1] == 'ok' and dec[2] == 3)
    dec_nameless = ic.candid_decode(enc)
    check('without descriptors, records are keyed by field hash',
          dec_nameless[0][ic.field_hash('title')] == 'write a brief')
    vecrec = ('vec', ('record', [('n', 'nat'), ('s', 'text')]))
    enc2 = ic.candid_encode([(vecrec, [{'n': 1, 's': 'a'}, {'n': 2, 's': 'b'}])])
    check('a vec of records round-trips', ic.candid_decode(enc2, [vecrec])[0] == [{'n': 1, 's': 'a'}, {'n': 2, 's': 'b'}])
    check('the same compound type is interned once in the table',
          hx(ic.candid_encode([(('opt', 'nat'), 1), (('opt', 'nat'), 2)])).startswith('4449444c016e7d020000'))
    try:
        ic.candid_encode([(res, {'nope': 1})])
        check('an unknown variant tag is refused', False, 'accepted')
    except ValueError:
        check('an unknown variant tag is refused', True)


# ── 5. request id ───────────────────────────────────────────────────────────
def test_request_id():
    print('request id — interface spec worked example')
    content = {
        'request_type': 'call',
        'canister_id': bytes.fromhex('00000000000004d2'),
        'method_name': 'hello',
        'arg': b'DIDL\x00\xfd*',
    }
    rid = ic.request_id(content)
    check('the "hello" call hashes to 8781291c…f94b',
          rid.hex() == '8781291c347db32a9d8c10eb62b710fce5a93be676474c42babc74c51858f94b', rid.hex())
    shuffled = {k: content[k] for k in reversed(list(content))}
    check('field order does not change the id', ic.request_id(shuffled) == rid)
    check('a None field is omitted, not hashed', ic.request_id({**content, 'nonce': None}) == rid)
    check('a Principal hashes as its raw bytes',
          ic.request_id({'sender': ic.Principal.anonymous()}) == ic.request_id({'sender': b'\x04'}))
    check('nested maps hash as request ids',
          ic.request_id({'a': {'b': 1}}) == hashlib.sha256(
              hashlib.sha256(b'a').digest() + ic.request_id({'b': 1})).digest())


# ── 6. certificate lookup ───────────────────────────────────────────────────
def test_lookup():
    print('certificate hash-tree lookup')
    tree = [1, [2, b'a', [1, [2, b'x', [3, b'hello']], [2, b'y', [3, b'world']]]],
               [1, [2, b'b', [3, b'good']], [4, b'\x00' * 32]]]
    check('a/x → hello', ic.lookup_path(tree, [b'a', b'x']) == b'hello')
    check('a/y → world', ic.lookup_path(tree, [b'a', b'y']) == b'world')
    check('b → good', ic.lookup_path(tree, [b'b']) == b'good')
    check('a/z is absent', ic.lookup_path(tree, [b'a', b'z']) is None)
    check('a pruned branch reads as absent', ic.lookup_path(tree, [b'c']) is None)
    check('a label with no leaf underneath is not a leaf', ic.lookup_path(tree, [b'a']) is None)


# ── 7. the wire, against a stub replica ─────────────────────────────────────
class _Stub(http.server.BaseHTTPRequestHandler):
    seen = []
    mode = {'call': 'v2', 'polls_before_reply': 2, 'reject_update': False, 'reject_query': False}
    polls = {'n': 0}
    reply_arg = ic.candid_encode([('text', 'filed')])

    def log_message(self, *a):  # quiet
        pass

    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n)
        env = ic.cbor_decode(body)
        _Stub.seen.append((self.path, env))
        content = env['content']
        if self.path.endswith('/query'):
            if _Stub.mode['reject_query']:
                out = {'status': 'rejected', 'reject_code': 3, 'reject_message': 'no such method', 'error_code': 'IC0302'}
            else:
                out = {'status': 'replied', 'reply': {'arg': ic.candid_encode([('nat', 42)])}}
            return self._send(200, ic.cbor_encode(out))
        if self.path.endswith('/call'):
            rid = ic.request_id(content)
            if _Stub.mode['call'] == 'v3':
                cert = {'tree': self._tree(rid), 'signature': b'\x00' * 48}
                return self._send(200, ic.cbor_encode({'status': 'replied', 'certificate': ic.cbor_encode(cert)}))
            return self._send(202, b'')
        if self.path.endswith('/read_state'):
            rid = content['paths'][0][1]
            _Stub.polls['n'] += 1
            if _Stub.polls['n'] <= _Stub.mode['polls_before_reply']:
                tree = [2, b'request_status', [2, rid, [2, b'status', [3, b'processing']]]]
            else:
                tree = self._tree(rid)
            cert = {'tree': tree, 'signature': b'\x00' * 48}
            return self._send(200, ic.cbor_encode({'certificate': ic.cbor_encode(cert)}))
        self._send(404, b'')

    def _tree(self, rid):
        if _Stub.mode['reject_update']:
            return [2, b'request_status', [2, rid, [1,
                    [2, b'reject_code', [3, ic.leb128(4)]],
                    [1, [2, b'reject_message', [3, b'not your job']],
                        [2, b'status', [3, b'rejected']]]]]]
        return [2, b'request_status', [2, rid, [1,
                [2, b'reply', [3, _Stub.reply_arg]],
                [2, b'status', [3, b'replied']]]]]

    def _send(self, code, body):
        self.send_response(code)
        self.send_header('Content-Type', 'application/cbor')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_wire():
    print('the wire — stub replica')
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Stub)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    host = f'http://127.0.0.1:{srv.server_address[1]}'
    ident = ic.Ed25519Identity.from_seed(b'\x42' * 32)
    canister = 'vhw7q-lqaaa-aaaab-agthq-cai'
    try:
        agent = ic.Agent(host, ident, timeout=5)
        # query
        out = agent.call(canister, 'balance', query=True, ret_types=['nat'])
        check('a query decodes its reply (42)', out == [42], out)
        path, env = _Stub.seen[-1]
        check('the query went to /api/v2/canister/<id>/query', path == f'/api/v2/canister/{canister}/query')
        c = env['content']
        check('the envelope names the sender as the identity principal', c['sender'] == ident.principal.raw)
        check('the envelope carries the DER public key', env['sender_pubkey'] == ident.der_public_key)
        rid = ic.request_id(c)
        check('the signature is over "\\x0Aic-request" ++ request id and verifies',
              ic.ed25519_verify(ident.public_key, b'\x0aic-request' + rid, env['sender_sig']))
        check('ingress expiry is in the future and under 5 minutes',
              0 < c['ingress_expiry'] / 1e9 - __import__('time').time() <= 300)
        # anonymous query carries no signature
        anon = ic.Agent(host, None, timeout=5)
        anon.query(canister, 'balance')
        _, env_a = _Stub.seen[-1]
        check('an anonymous envelope has no sender_sig', 'sender_sig' not in env_a and env_a['content']['sender'] == b'\x04')
        # rejected query
        _Stub.mode['reject_query'] = True
        try:
            agent.query(canister, 'nothing')
            check('a rejected query raises CanisterReject', False, 'no raise')
        except ic.CanisterReject as e:
            check('a rejected query raises CanisterReject', e.code == 3 and 'no such method' in e.message)
        _Stub.mode['reject_query'] = False
        # update, old shape: 202 then poll
        _Stub.polls['n'] = 0
        out = agent.call(canister, 'claim', arg_types=['nat64'], args=[7], ret_types=['text'], poll_interval=0.01)
        check('an update (202 + read_state polling) returns the decoded reply', out == ['filed'], out)
        check('it polled until the certificate said replied', _Stub.polls['n'] == 3, _Stub.polls['n'])
        paths = [p for p, _ in _Stub.seen]
        check('the poll went to read_state with the request id',
              paths[-1].endswith('/read_state') and _Stub.seen[-1][1]['content']['paths'][0][0] == b'request_status')
        call_env = next(e for p, e in reversed(_Stub.seen) if p.endswith('/call'))
        check('the call arg is the Candid-encoded (7 : nat64)',
              call_env['content']['arg'] == ic.candid_encode([('nat64', 7)]) and call_env['content']['method_name'] == 'claim')
        # update, new shape: 200 with certificate
        _Stub.mode['call'] = 'v3'
        _Stub.polls['n'] = 0
        out = agent.call(canister, 'claim', arg_types=['nat64'], args=[8], ret_types=['text'])
        check('an update answered synchronously (200 + certificate) returns the reply without polling',
              out == ['filed'] and _Stub.polls['n'] == 0)
        # rejected update
        _Stub.mode['reject_update'] = True
        try:
            agent.call(canister, 'claim', arg_types=['nat64'], args=[9])
            check('a rejected update raises CanisterReject with the message', False, 'no raise')
        except ic.CanisterReject as e:
            check('a rejected update raises CanisterReject with the message', e.code == 4 and e.message == 'not your job', (e.code, e.message))
        _Stub.mode['reject_update'] = False
        _Stub.mode['call'] = 'v2'
        # wait=False returns immediately
        _Stub.polls['n'] = 0
        out = agent.update(canister, 'claim', wait=False)
        check('wait=False returns None without polling', out is None and _Stub.polls['n'] == 0)
    finally:
        srv.shutdown()
        srv.server_close()


# ── 8. the key file ─────────────────────────────────────────────────────────
def test_keyfile():
    print('the worker key file')
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'keys', 'worker.json')
        a = ic.Ed25519Identity.load_or_create(p)
        b = ic.Ed25519Identity.load_or_create(p)
        check('load_or_create creates the file once and reloads the same principal', a.principal == b.principal)
        mode = stat.S_IMODE(os.stat(p).st_mode)
        check('the key file is 0600', mode == 0o600, oct(mode))
        data = json.loads(Path(p).read_text())
        check('the file records the principal beside the seed', data.get('principal') == a.principal.to_text())


def main():
    for fn in (test_ed25519, test_principal, test_cbor, test_candid, test_request_id, test_lookup, test_wire, test_keyfile):
        fn()
    print()
    if FAILS:
        print(f'ic_agent: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:4]))
        return 1
    print('ic_agent: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
