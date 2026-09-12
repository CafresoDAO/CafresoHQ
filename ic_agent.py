"""A stdlib-only Internet Computer client, so a coworker can sign a canister
call from inside its own container.

Why this exists. PHASE2_STATE_CANISTER.md §3 is binding for the office's own
state: the browser holds the Internet Identity delegation and is the only
thing that ever calls `cafresohq_state`; the container is handed no chain
credential at all. That is the right floor for *the boss's* data. The agent
marketplace needs one thing that floor cannot give: a coworker that is hired
from the network has to claim a job, file a result and get paid **while its
owner's browser is closed** — a worker that only works when someone is
watching is not a worker. So marketplace workers get a key of their own,
generated here, whose principal the owner links on-chain to their own II
principal. The key can do exactly what `cafresohq_market` lets a linked
worker principal do (bid, claim, deliver) and nothing else; it never touches
the vault, the state canister or the owner's wallet. The owner can revoke it
with one call.

Why stdlib only. docker/requirements-serve.txt: "serve.py itself uses only
stdlib". The runtime image has no `ic-py`, no `cryptography`, no
`node_modules` (the UI build stage is discarded). Pulling an agent library in
at runtime would put a network install on the path to a coworker's first
paycheck. Everything the IC HTTP interface needs fits in one file: ed25519
(RFC 8032, big-int arithmetic — a signature costs a few milliseconds, which
is fine for a worker that signs a handful of calls per job), CBOR for the
envelope, a Candid encoder/decoder for the types the market canister speaks,
the representation-independent request id, and the hash-tree lookup that
reads an update call's reply out of the replica's certificate.

What is deliberately NOT here. The certificate's BLS signature is not
verified: this client trusts the TLS connection to the boundary node (or to
the local replica). Every decision that moves money is made by the canister
from `msg.caller`, which the IC authenticates regardless of what this client
believes a reply said — so a spoofed reply can mislead a worker's log, never
the escrow. Verifying BLS12-381 in pure Python is the follow-up, and it is
listed in docs/AGENT_MARKETPLACE.md so nobody mistakes its absence for an
oversight.

Public surface:

    Principal            raw bytes ⇄ "aaaaa-aa" text, anonymous, self-auth
    Ed25519Identity      generate / from_seed / load_or_create(path) / sign
    cbor_encode / cbor_decode
    candid_encode(args) / candid_decode(bytes[, types])
    request_id(content)
    Agent(host, identity).query(...) / .update(...) / .read_state(...)

Candid type descriptors are plain Python: 'nat', 'text', 'principal',
('opt', T), ('vec', T), ('record', [(name, T), ...]), ('variant', [...]).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import struct
import time
import urllib.error
import urllib.request
import zlib

__all__ = [
    'Principal', 'Ed25519Identity', 'Agent', 'CanisterReject', 'AgentError',
    'cbor_encode', 'cbor_decode', 'candid_encode', 'candid_decode',
    'request_id', 'leb128', 'sleb128', 'lookup_path', 'field_hash',
]


# ── LEB128 ───────────────────────────────────────────────────────────────────

def leb128(n: int) -> bytes:
    if n < 0:
        raise ValueError('leb128 takes a non-negative int')
    out = bytearray()
    while True:
        b = n & 0x7f
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def sleb128(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7f
        n >>= 7
        done = (n == 0 and not (b & 0x40)) or (n == -1 and (b & 0x40))
        out.append(b if done else b | 0x80)
        if done:
            return bytes(out)


def _read_leb128(buf: bytes, i: int) -> tuple[int, int]:
    n = 0
    shift = 0
    while True:
        if i >= len(buf):
            raise ValueError('truncated leb128')
        b = buf[i]
        i += 1
        n |= (b & 0x7f) << shift
        shift += 7
        if not (b & 0x80):
            return n, i


def _read_sleb128(buf: bytes, i: int) -> tuple[int, int]:
    n = 0
    shift = 0
    while True:
        if i >= len(buf):
            raise ValueError('truncated sleb128')
        b = buf[i]
        i += 1
        n |= (b & 0x7f) << shift
        shift += 7
        if not (b & 0x80):
            if b & 0x40:
                n -= 1 << shift
            return n, i


# ── Principal ────────────────────────────────────────────────────────────────

class Principal:
    """An IC principal: the raw bytes, and the dashed base32 text form."""
    __slots__ = ('raw',)

    def __init__(self, raw: bytes):
        if not isinstance(raw, (bytes, bytearray)) or len(raw) > 29:
            raise ValueError('a principal is at most 29 bytes')
        self.raw = bytes(raw)

    @classmethod
    def anonymous(cls) -> 'Principal':
        return cls(b'\x04')

    @classmethod
    def management(cls) -> 'Principal':
        return cls(b'')

    @classmethod
    def self_authenticating(cls, der_public_key: bytes) -> 'Principal':
        return cls(hashlib.sha224(der_public_key).digest() + b'\x02')

    @classmethod
    def from_text(cls, text: str) -> 'Principal':
        s = str(text).strip().replace('-', '').upper()
        pad = (-len(s)) % 8
        try:
            data = base64.b32decode(s + '=' * pad)
        except Exception as e:                      # noqa: BLE001
            raise ValueError(f'not a principal: {text!r}') from e
        if len(data) < 4:
            raise ValueError(f'not a principal: {text!r}')
        crc, raw = data[:4], data[4:]
        if zlib.crc32(raw).to_bytes(4, 'big') != crc:
            raise ValueError(f'principal checksum mismatch: {text!r}')
        p = cls(raw)
        if p.to_text() != str(text).strip().lower():
            raise ValueError(f'principal is not canonical: {text!r}')
        return p

    def to_text(self) -> str:
        body = zlib.crc32(self.raw).to_bytes(4, 'big') + self.raw
        b32 = base64.b32encode(body).decode('ascii').lower().rstrip('=')
        return '-'.join(b32[i:i + 5] for i in range(0, len(b32), 5))

    def __str__(self) -> str:
        return self.to_text()

    def __repr__(self) -> str:
        return f'Principal({self.to_text()!r})'

    def __eq__(self, other) -> bool:
        return isinstance(other, Principal) and other.raw == self.raw

    def __hash__(self) -> int:
        return hash(self.raw)


def _as_principal(v) -> Principal:
    if isinstance(v, Principal):
        return v
    if isinstance(v, (bytes, bytearray)):
        return Principal(bytes(v))
    return Principal.from_text(str(v))


# ── Ed25519 (RFC 8032), pure Python ─────────────────────────────────────────

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


_D = (-121665 * _inv(121666)) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _recover_x(y: int, sign: int) -> int:
    y2 = y * y % _P
    u = (y2 - 1) % _P
    v = (_D * y2 + 1) % _P
    x2 = u * _inv(v) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _I % _P
    if (x * x - x2) % _P:
        raise ValueError('not a curve point')
    if x == 0 and sign:
        raise ValueError('not a curve point')
    if (x & 1) != sign:
        x = _P - x
    return x


_Gy = 4 * _inv(5) % _P
_Gx = _recover_x(_Gy, 0)
_G = (_Gx, _Gy, 1, _Gx * _Gy % _P)     # extended coordinates (X, Y, Z, T)
_ZERO = (0, 1, 1, 0)


def _pt_add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = 2 * t1 * t2 * _D % _P
    d = 2 * z1 * z2 % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _pt_mul(s: int, p):
    q = _ZERO
    while s:
        if s & 1:
            q = _pt_add(q, p)
        p = _pt_add(p, p)
        s >>= 1
    return q


def _pt_encode(p) -> bytes:
    x, y, z, _t = p
    zi = _inv(z)
    x = x * zi % _P
    y = y * zi % _P
    return (y | ((x & 1) << 255)).to_bytes(32, 'little')


def _pt_decode(b: bytes):
    if len(b) != 32:
        raise ValueError('a point is 32 bytes')
    y = int.from_bytes(b, 'little')
    sign = y >> 255
    y &= (1 << 255) - 1
    if y >= _P:
        raise ValueError('not a curve point')
    x = _recover_x(y, sign)
    return (x, y, 1, x * y % _P)


def _secret_expand(seed: bytes) -> tuple[int, bytes]:
    if len(seed) != 32:
        raise ValueError('an ed25519 seed is 32 bytes')
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], 'little')
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def ed25519_public_key(seed: bytes) -> bytes:
    a, _ = _secret_expand(seed)
    return _pt_encode(_pt_mul(a, _G))


def ed25519_sign(seed: bytes, msg: bytes) -> bytes:
    a, prefix = _secret_expand(seed)
    pub = _pt_encode(_pt_mul(a, _G))
    r = int.from_bytes(hashlib.sha512(prefix + msg).digest(), 'little') % _L
    big_r = _pt_encode(_pt_mul(r, _G))
    k = int.from_bytes(hashlib.sha512(big_r + pub + msg).digest(), 'little') % _L
    s = (r + k * a) % _L
    return big_r + s.to_bytes(32, 'little')


def ed25519_verify(pub: bytes, msg: bytes, sig: bytes) -> bool:
    if len(sig) != 64 or len(pub) != 32:
        return False
    try:
        big_a = _pt_decode(pub)
        big_r = _pt_decode(sig[:32])
    except ValueError:
        return False
    s = int.from_bytes(sig[32:], 'little')
    if s >= _L:
        return False
    k = int.from_bytes(hashlib.sha512(sig[:32] + pub + msg).digest(), 'little') % _L
    lhs = _pt_mul(s, _G)
    rhs = _pt_add(big_r, _pt_mul(k, big_a))
    return _pt_encode(lhs) == _pt_encode(rhs)


# DER prefix for an ed25519 SubjectPublicKeyInfo (RFC 8410): the IC derives a
# self-authenticating principal from the DER form, not the raw 32 bytes.
_ED25519_DER_PREFIX = bytes.fromhex('302a300506032b6570032100')


class Ed25519Identity:
    """A signing identity: 32-byte seed, DER public key, principal, sign()."""
    __slots__ = ('_seed', 'public_key', 'der_public_key', 'principal')

    def __init__(self, seed: bytes):
        self._seed = bytes(seed)
        self.public_key = ed25519_public_key(self._seed)
        self.der_public_key = _ED25519_DER_PREFIX + self.public_key
        self.principal = Principal.self_authenticating(self.der_public_key)

    @classmethod
    def generate(cls) -> 'Ed25519Identity':
        return cls(secrets.token_bytes(32))

    @classmethod
    def from_seed(cls, seed: bytes) -> 'Ed25519Identity':
        return cls(seed)

    @classmethod
    def load_or_create(cls, path) -> 'Ed25519Identity':
        """The worker's key file: JSON {"seed": hex}, mode 0600, created on
        first use. The seed never leaves the container; only the principal
        does (the owner links it on-chain)."""
        path = os.fspath(path)
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            return cls(bytes.fromhex(data['seed']))
        ident = cls.generate()
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump({'seed': ident._seed.hex(), 'principal': ident.principal.to_text()}, fh)
        return ident

    def sign(self, msg: bytes) -> bytes:
        return ed25519_sign(self._seed, msg)

    def verify(self, msg: bytes, sig: bytes) -> bool:
        return ed25519_verify(self.public_key, msg, sig)


# ── CBOR (RFC 8949), the subset the IC uses ─────────────────────────────────

def _cbor_head(major: int, n: int) -> bytes:
    if n < 24:
        return bytes([(major << 5) | n])
    if n < 0x100:
        return bytes([(major << 5) | 24, n])
    if n < 0x10000:
        return bytes([(major << 5) | 25]) + n.to_bytes(2, 'big')
    if n < 0x100000000:
        return bytes([(major << 5) | 26]) + n.to_bytes(4, 'big')
    return bytes([(major << 5) | 27]) + n.to_bytes(8, 'big')


def cbor_encode(v) -> bytes:
    if v is None:
        return b'\xf6'
    if v is True:
        return b'\xf5'
    if v is False:
        return b'\xf4'
    if isinstance(v, int):
        return _cbor_head(0, v) if v >= 0 else _cbor_head(1, -1 - v)
    if isinstance(v, (bytes, bytearray)):
        return _cbor_head(2, len(v)) + bytes(v)
    if isinstance(v, str):
        b = v.encode('utf-8')
        return _cbor_head(3, len(b)) + b
    if isinstance(v, (list, tuple)):
        return _cbor_head(4, len(v)) + b''.join(cbor_encode(x) for x in v)
    if isinstance(v, dict):
        return _cbor_head(5, len(v)) + b''.join(cbor_encode(k) + cbor_encode(x) for k, x in v.items())
    if isinstance(v, Principal):
        return cbor_encode(v.raw)
    if isinstance(v, _Tag):
        return _cbor_head(6, v.tag) + cbor_encode(v.value)
    raise TypeError(f'cbor: cannot encode {type(v).__name__}')


class _Tag:
    __slots__ = ('tag', 'value')

    def __init__(self, tag: int, value):
        self.tag, self.value = tag, value


def cbor_decode(buf: bytes):
    v, i = _cbor_item(bytes(buf), 0)
    if i != len(buf):
        raise ValueError('cbor: trailing bytes')
    return v


def _cbor_len(buf: bytes, i: int, info: int) -> tuple[int, int]:
    if info < 24:
        return info, i
    if info == 24:
        return buf[i], i + 1
    if info == 25:
        return int.from_bytes(buf[i:i + 2], 'big'), i + 2
    if info == 26:
        return int.from_bytes(buf[i:i + 4], 'big'), i + 4
    if info == 27:
        return int.from_bytes(buf[i:i + 8], 'big'), i + 8
    if info == 31:
        # Indefinite length (RFC 8949 §3.2.3): the item runs until a 0xff
        # break. Replicas DO emit these — pocket-ic answers queries with
        # indefinite-length maps and text — so a reader that refuses them
        # cannot read a real reply. Found on the replica harness, #429.
        return -1, i
    raise ValueError(f'cbor: reserved additional info {info}')


def _cbor_indefinite(buf: bytes, i: int, major: int):
    """Read an indefinite-length string/array/map body up to its break."""
    if major in (2, 3):
        chunks = b''
        while True:
            if i >= len(buf):
                raise ValueError('cbor: truncated indefinite string')
            if buf[i] == 0xff:
                break
            cm, ci = buf[i] >> 5, buf[i] & 0x1f
            if cm != major or ci == 31:
                raise ValueError('cbor: an indefinite string may only hold definite chunks of its own type')
            n, j = _cbor_len(buf, i + 1, ci)
            chunks += buf[j:j + n]
            i = j + n
        return (chunks if major == 2 else chunks.decode('utf-8')), i + 1
    if major == 4:
        out = []
        while True:
            if i >= len(buf):
                raise ValueError('cbor: truncated indefinite array')
            if buf[i] == 0xff:
                return out, i + 1
            v, i = _cbor_item(buf, i)
            out.append(v)
    out = {}
    while True:
        if i >= len(buf):
            raise ValueError('cbor: truncated indefinite map')
        if buf[i] == 0xff:
            return out, i + 1
        k, i = _cbor_item(buf, i)
        v, i = _cbor_item(buf, i)
        out[k] = v


def _cbor_item(buf: bytes, i: int):
    if i >= len(buf):
        raise ValueError('cbor: truncated')
    major, info = buf[i] >> 5, buf[i] & 0x1f
    i += 1
    if major in (0, 1, 6) and info == 31:
        raise ValueError(f'cbor: major type {major} has no indefinite form')
    if major == 0:
        return _cbor_len(buf, i, info)
    if major == 1:
        n, i = _cbor_len(buf, i, info)
        return -1 - n, i
    if major in (2, 3, 4, 5):
        n, i = _cbor_len(buf, i, info)
        if n < 0:
            return _cbor_indefinite(buf, i, major)
    if major == 2:
        return buf[i:i + n], i + n
    if major == 3:
        return buf[i:i + n].decode('utf-8'), i + n
    if major == 4:
        out = []
        for _ in range(n):
            v, i = _cbor_item(buf, i)
            out.append(v)
        return out, i
    if major == 5:
        out = {}
        for _ in range(n):
            k, i = _cbor_item(buf, i)
            v, i = _cbor_item(buf, i)
            out[k] = v
        return out, i
    if major == 6:
        _tag, i = _cbor_len(buf, i, info)
        return _cbor_item(buf, i)          # tags (55799 self-describe) are transparent
    if major == 7:
        if info == 20:
            return False, i
        if info == 21:
            return True, i
        if info == 22:
            return None, i
        if info == 27:
            return struct.unpack('>d', buf[i:i + 8])[0], i + 8
        if info == 26:
            return struct.unpack('>f', buf[i:i + 4])[0], i + 4
    raise ValueError(f'cbor: unsupported item {major}/{info}')


# ── Candid ───────────────────────────────────────────────────────────────────

_PRIM = {
    'null': -1, 'bool': -2, 'nat': -3, 'int': -4, 'nat8': -5, 'nat16': -6,
    'nat32': -7, 'nat64': -8, 'int8': -9, 'int16': -10, 'int32': -11,
    'int64': -12, 'float32': -13, 'float64': -14, 'text': -15,
    'reserved': -16, 'empty': -17, 'principal': -24,
}
_PRIM_BY_CODE = {v: k for k, v in _PRIM.items()}
_OPT, _VEC, _RECORD, _VARIANT = -18, -19, -20, -21


def field_hash(name) -> int:
    """Candid's field-name hash (`hash(name) = fold (h*223 + c)`)."""
    if isinstance(name, int):
        return name
    h = 0
    for c in str(name).encode('utf-8'):
        h = (h * 223 + c) & 0xffffffff
    return h


def _norm(t):
    """Normalise a type descriptor: 'blob' → ('vec','nat8'); dict fields → list."""
    if isinstance(t, str):
        if t == 'blob':
            return ('vec', 'nat8')
        if t not in _PRIM:
            raise ValueError(f'candid: unknown type {t!r}')
        return t
    if isinstance(t, tuple) and len(t) == 2:
        kind, inner = t
        if kind in ('opt', 'vec'):
            return (kind, _norm(inner))
        if kind in ('record', 'variant'):
            fields = list(inner.items()) if isinstance(inner, dict) else list(inner)
            out = [(n, _norm(ft) if ft is not None else 'null') for n, ft in fields]
            out.sort(key=lambda f: field_hash(f[0]))
            return (kind, out)
    raise ValueError(f'candid: bad type descriptor {t!r}')


class _TypeTable:
    def __init__(self):
        self.entries: list[bytes] = []
        self.index: dict = {}

    def ref(self, t) -> int:
        """Primitive → negative code; compound → table index (interned)."""
        if isinstance(t, str):
            return _PRIM[t]
        key = repr(t)
        if key in self.index:
            return self.index[key]
        kind, inner = t
        if kind in ('opt', 'vec'):
            code = _OPT if kind == 'opt' else _VEC
            body = sleb128(code) + sleb128(self.ref(inner))
        else:
            code = _RECORD if kind == 'record' else _VARIANT
            body = sleb128(code) + leb128(len(inner))
            for name, ft in inner:
                body += leb128(field_hash(name)) + sleb128(self.ref(ft))
        idx = len(self.entries)
        self.entries.append(body)
        self.index[key] = idx
        return idx

    def encode(self) -> bytes:
        return leb128(len(self.entries)) + b''.join(self.entries)


def _enc_value(t, v) -> bytes:
    if isinstance(t, str):
        if t == 'null' or t == 'reserved':
            return b''
        if t == 'bool':
            return b'\x01' if v else b'\x00'
        if t == 'nat':
            return leb128(int(v))
        if t == 'int':
            return sleb128(int(v))
        if t in ('nat8', 'nat16', 'nat32', 'nat64'):
            return int(v).to_bytes(int(t[3:]) // 8, 'little')
        if t in ('int8', 'int16', 'int32', 'int64'):
            return int(v).to_bytes(int(t[3:]) // 8, 'little', signed=True)
        if t == 'float64':
            return struct.pack('<d', float(v))
        if t == 'float32':
            return struct.pack('<f', float(v))
        if t == 'text':
            b = str(v).encode('utf-8')
            return leb128(len(b)) + b
        if t == 'principal':
            raw = _as_principal(v).raw
            return b'\x01' + leb128(len(raw)) + raw
        if t == 'empty':
            raise ValueError('candid: empty has no values')
    kind, inner = t
    if kind == 'opt':
        return b'\x00' if v is None else b'\x01' + _enc_value(inner, v)
    if kind == 'vec':
        if inner == 'nat8' and isinstance(v, (bytes, bytearray)):
            return leb128(len(v)) + bytes(v)
        return leb128(len(v)) + b''.join(_enc_value(inner, x) for x in v)
    if kind == 'record':
        out = b''
        for name, ft in inner:
            if isinstance(v, dict):
                if name in v:
                    fv = v[name]
                elif isinstance(name, int) or ft == 'null':
                    fv = v.get(name)
                else:
                    raise ValueError(f'candid: record is missing field {name!r}')
            else:
                fv = v[name]
            out += _enc_value(ft, fv)
        return out
    if kind == 'variant':
        if isinstance(v, str):
            tag, payload = v, None
        elif isinstance(v, dict) and len(v) == 1:
            (tag, payload), = v.items()
        else:
            raise ValueError(f'candid: a variant value is a tag or {{tag: value}}, got {v!r}')
        for i, (name, ft) in enumerate(inner):
            if name == tag:
                return leb128(i) + _enc_value(ft, payload)
        raise ValueError(f'candid: {tag!r} is not an alternative of the variant')
    raise ValueError(f'candid: cannot encode type {t!r}')


def candid_encode(args) -> bytes:
    """`args` is a list of (type, value). Returns the DIDL-prefixed bytes."""
    table = _TypeTable()
    types = [_norm(t) for t, _ in args]
    refs = [table.ref(t) for t in types]
    body = b''.join(_enc_value(t, v) for t, (_, v) in zip(types, args))
    return b'DIDL' + table.encode() + leb128(len(refs)) + b''.join(sleb128(r) for r in refs) + body


class _Decoder:
    def __init__(self, buf: bytes):
        self.buf = buf
        self.i = 0
        self.table: list = []

    def read_type_table(self):
        n, self.i = _read_leb128(self.buf, self.i)
        for _ in range(n):
            code, self.i = _read_sleb128(self.buf, self.i)
            if code in (_OPT, _VEC):
                inner, self.i = _read_sleb128(self.buf, self.i)
                self.table.append(('opt' if code == _OPT else 'vec', inner))
            elif code in (_RECORD, _VARIANT):
                cnt, self.i = _read_leb128(self.buf, self.i)
                fields = []
                for _ in range(cnt):
                    fid, self.i = _read_leb128(self.buf, self.i)
                    ft, self.i = _read_sleb128(self.buf, self.i)
                    fields.append((fid, ft))
                self.table.append(('record' if code == _RECORD else 'variant', fields))
            elif code == -22:                       # func: skip the reference shape
                raise ValueError('candid: func types are not supported by this client')
            elif code == -23:
                raise ValueError('candid: service types are not supported by this client')
            else:
                raise ValueError(f'candid: unknown type code {code}')

    def resolve(self, ref: int):
        if ref < 0:
            if ref in _PRIM_BY_CODE:
                return _PRIM_BY_CODE[ref]
            raise ValueError(f'candid: unknown primitive {ref}')
        return self.table[ref]

    def value(self, ref: int):
        t = self.resolve(ref)
        buf = self.buf
        if isinstance(t, str):
            if t in ('null', 'reserved'):
                return None
            if t == 'bool':
                v = buf[self.i] != 0
                self.i += 1
                return v
            if t == 'nat':
                v, self.i = _read_leb128(buf, self.i)
                return v
            if t == 'int':
                v, self.i = _read_sleb128(buf, self.i)
                return v
            if t in ('nat8', 'nat16', 'nat32', 'nat64'):
                n = int(t[3:]) // 8
                v = int.from_bytes(buf[self.i:self.i + n], 'little')
                self.i += n
                return v
            if t in ('int8', 'int16', 'int32', 'int64'):
                n = int(t[3:]) // 8
                v = int.from_bytes(buf[self.i:self.i + n], 'little', signed=True)
                self.i += n
                return v
            if t == 'float64':
                v = struct.unpack('<d', buf[self.i:self.i + 8])[0]
                self.i += 8
                return v
            if t == 'float32':
                v = struct.unpack('<f', buf[self.i:self.i + 4])[0]
                self.i += 4
                return v
            if t == 'text':
                n, self.i = _read_leb128(buf, self.i)
                v = buf[self.i:self.i + n].decode('utf-8')
                self.i += n
                return v
            if t == 'principal':
                if buf[self.i] != 1:
                    raise ValueError('candid: opaque principal references are not supported')
                self.i += 1
                n, self.i = _read_leb128(buf, self.i)
                v = Principal(buf[self.i:self.i + n])
                self.i += n
                return v
            if t == 'empty':
                raise ValueError('candid: a value of type empty cannot exist')
        kind, inner = t
        if kind == 'opt':
            flag = buf[self.i]
            self.i += 1
            return self.value(inner) if flag else None
        if kind == 'vec':
            n, self.i = _read_leb128(buf, self.i)
            if self.resolve(inner) == 'nat8':
                v = bytes(buf[self.i:self.i + n])
                self.i += n
                return v
            return [self.value(inner) for _ in range(n)]
        if kind == 'record':
            return {fid: self.value(ft) for fid, ft in inner}
        if kind == 'variant':
            idx, self.i = _read_leb128(buf, self.i)
            fid, ft = inner[idx]
            return {fid: self.value(ft)}
        raise ValueError(f'candid: cannot decode {t!r}')


def _name_fields(v, t):
    """Replace field hashes with names, guided by an expected type descriptor."""
    if isinstance(t, str) or v is None:
        return v
    kind, inner = t
    if kind == 'opt':
        return _name_fields(v, inner)
    if kind == 'vec':
        return v if isinstance(v, bytes) else [_name_fields(x, inner) for x in v]
    if kind == 'record' and isinstance(v, dict):
        by_hash = {field_hash(n): (n, ft) for n, ft in inner}
        return {by_hash[h][0] if h in by_hash else h: _name_fields(x, by_hash[h][1] if h in by_hash else 'reserved')
                for h, x in v.items()}
    if kind == 'variant' and isinstance(v, dict):
        by_hash = {field_hash(n): (n, ft) for n, ft in inner}
        (h, x), = v.items()
        if h in by_hash:
            return {by_hash[h][0]: _name_fields(x, by_hash[h][1])}
        return {h: x}
    return v


def candid_decode(buf: bytes, types=None) -> list:
    """Decode a DIDL message into Python values. Records and variants come
    back keyed by field NAME when `types` (a list of descriptors matching the
    reply's arguments) is given, by field hash otherwise."""
    buf = bytes(buf)
    if buf[:4] != b'DIDL':
        raise ValueError('candid: missing DIDL magic')
    d = _Decoder(buf)
    d.i = 4
    d.read_type_table()
    n, d.i = _read_leb128(buf, d.i)
    refs = []
    for _ in range(n):
        r, d.i = _read_sleb128(buf, d.i)
        refs.append(r)
    values = [d.value(r) for r in refs]
    if types:
        values = [_name_fields(v, _norm(t)) for v, t in zip(values, types)]
    return values


# ── Request id (representation-independent hash) ────────────────────────────

def _sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def _hash_value(v) -> bytes:
    if isinstance(v, Principal):
        return _sha256(v.raw)
    if isinstance(v, (bytes, bytearray)):
        return _sha256(bytes(v))
    if isinstance(v, str):
        return _sha256(v.encode('utf-8'))
    if isinstance(v, int):
        return _sha256(leb128(v))
    if isinstance(v, (list, tuple)):
        return _sha256(b''.join(_hash_value(x) for x in v))
    if isinstance(v, dict):
        return request_id(v)
    raise TypeError(f'request id: cannot hash {type(v).__name__}')


def request_id(content: dict) -> bytes:
    pairs = sorted(_sha256(k.encode('utf-8')) + _hash_value(v)
                   for k, v in content.items() if v is not None)
    return _sha256(b''.join(pairs))


# ── Hash tree lookup (certificate) ──────────────────────────────────────────

def lookup_path(tree, path):
    """Find a leaf in a certificate hash tree. Returns the leaf bytes, or
    None when the path is absent or pruned."""
    if not path:
        return tree[1] if tree and tree[0] == 3 else None
    kind = tree[0] if tree else None
    if kind == 1:
        found = lookup_path(tree[1], path)
        return found if found is not None else lookup_path(tree[2], path)
    if kind == 2:
        label = tree[1]
        return lookup_path(tree[2], path[1:]) if label == path[0] else None
    return None


# ── Agent ────────────────────────────────────────────────────────────────────

class AgentError(RuntimeError):
    pass


class CanisterReject(AgentError):
    def __init__(self, code, message, error_code=None):
        super().__init__(f'canister rejected (code {code}): {message}')
        self.code, self.message, self.error_code = code, message, error_code


_INGRESS_DOMAIN = b'\x0aic-request'


class Agent:
    """Query and update calls against one host, signed by `identity` (or
    anonymous when None). `host` is the boundary node (https://icp-api.io)
    or a local replica (http://127.0.0.1:4943)."""

    def __init__(self, host: str = 'https://icp-api.io', identity: Ed25519Identity | None = None,
                 timeout: float = 30.0, expiry_seconds: int = 240):
        self.host = host.rstrip('/')
        self.identity = identity
        self.timeout = timeout
        self.expiry_seconds = expiry_seconds

    # -- wire helpers --------------------------------------------------------
    @property
    def sender(self) -> Principal:
        return self.identity.principal if self.identity else Principal.anonymous()

    def _expiry_ns(self) -> int:
        return (int(time.time()) + self.expiry_seconds) * 1_000_000_000

    def _envelope(self, content: dict) -> bytes:
        env = {'content': content}
        if self.identity is not None:
            rid = request_id(content)
            env['sender_pubkey'] = self.identity.der_public_key
            env['sender_sig'] = self.identity.sign(_INGRESS_DOMAIN + rid)
        return cbor_encode(_Tag(55799, env))

    def _post(self, path: str, body: bytes) -> tuple[int, bytes]:
        req = urllib.request.Request(
            self.host + path, data=body, method='POST',
            headers={'Content-Type': 'application/cbor', 'Accept': 'application/cbor'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise AgentError(f'{self.host}{path}: {e}') from e

    # -- calls -----------------------------------------------------------------
    def query(self, canister, method: str, arg: bytes = b'DIDL\x00\x00') -> bytes:
        cid = _as_principal(canister)
        content = {
            'request_type': 'query', 'sender': self.sender.raw,
            'ingress_expiry': self._expiry_ns(), 'canister_id': cid.raw,
            'method_name': method, 'arg': bytes(arg),
        }
        status, body = self._post(f'/api/v2/canister/{cid.to_text()}/query', self._envelope(content))
        if status != 200:
            raise AgentError(f'query {method}: HTTP {status}: {body[:300]!r}')
        resp = cbor_decode(body)
        if resp.get('status') == 'replied':
            return bytes(resp['reply']['arg'])
        if resp.get('status') == 'rejected':
            raise CanisterReject(resp.get('reject_code'), resp.get('reject_message'), resp.get('error_code'))
        raise AgentError(f'query {method}: unexpected response {resp!r}')

    def update(self, canister, method: str, arg: bytes = b'DIDL\x00\x00',
               wait: bool = True, poll_interval: float = 1.0, max_wait: float = 120.0) -> bytes | None:
        cid = _as_principal(canister)
        content = {
            'request_type': 'call', 'sender': self.sender.raw,
            'ingress_expiry': self._expiry_ns(), 'canister_id': cid.raw,
            'method_name': method, 'arg': bytes(arg),
        }
        rid = request_id(content)
        status, body = self._post(f'/api/v2/canister/{cid.to_text()}/call', self._envelope(content))
        if status == 200 and body:
            # A replica answering the newer synchronous shape: the certificate
            # rides in the body. Read the reply straight out of it.
            resp = cbor_decode(body)
            if isinstance(resp, dict) and resp.get('status') == 'replied' and 'certificate' in resp:
                return self._reply_from_certificate(bytes(resp['certificate']), rid, method)
            if isinstance(resp, dict) and resp.get('status') == 'non_replicated_rejection':
                raise CanisterReject(resp.get('reject_code'), resp.get('reject_message'), resp.get('error_code'))
        elif status != 202:
            raise AgentError(f'call {method}: HTTP {status}: {body[:300]!r}')
        if not wait:
            return None
        deadline = time.time() + max_wait
        while True:
            cert = self.read_state(cid, [[b'request_status', rid]])
            tree = cert['tree']
            st = lookup_path(tree, [b'request_status', rid, b'status'])
            if st == b'replied':
                return bytes(lookup_path(tree, [b'request_status', rid, b'reply']))
            if st == b'rejected':
                code = lookup_path(tree, [b'request_status', rid, b'reject_code'])
                msg = lookup_path(tree, [b'request_status', rid, b'reject_message'])
                ec = lookup_path(tree, [b'request_status', rid, b'error_code'])
                raise CanisterReject(_read_leb128(code, 0)[0] if code else None,
                                     msg.decode('utf-8', 'replace') if msg else '',
                                     ec.decode('utf-8', 'replace') if ec else None)
            if st == b'done':
                raise AgentError(f'call {method}: the replica dropped the reply before it was read')
            if time.time() > deadline:
                raise AgentError(f'call {method}: no reply after {max_wait:.0f}s (request {rid.hex()})')
            time.sleep(poll_interval)

    def _reply_from_certificate(self, cert_bytes: bytes, rid: bytes, method: str) -> bytes:
        cert = cbor_decode(cert_bytes)
        tree = cert['tree']
        st = lookup_path(tree, [b'request_status', rid, b'status'])
        if st == b'replied':
            return bytes(lookup_path(tree, [b'request_status', rid, b'reply']))
        if st == b'rejected':
            code = lookup_path(tree, [b'request_status', rid, b'reject_code'])
            msg = lookup_path(tree, [b'request_status', rid, b'reject_message'])
            raise CanisterReject(_read_leb128(code, 0)[0] if code else None,
                                 msg.decode('utf-8', 'replace') if msg else '')
        raise AgentError(f'call {method}: certificate carries status {st!r}')

    def read_state(self, canister, paths) -> dict:
        """Returns the decoded certificate {tree, signature, delegation?}.
        NOT signature-verified — see the module docstring."""
        cid = _as_principal(canister)
        content = {
            'request_type': 'read_state', 'sender': self.sender.raw,
            'ingress_expiry': self._expiry_ns(),
            'paths': [[bytes(p) for p in path] for path in paths],
        }
        status, body = self._post(f'/api/v2/canister/{cid.to_text()}/read_state', self._envelope(content))
        if status != 200:
            raise AgentError(f'read_state: HTTP {status}: {body[:300]!r}')
        resp = cbor_decode(body)
        return cbor_decode(bytes(resp['certificate']))

    # -- convenience: typed call ----------------------------------------------
    def call(self, canister, method: str, arg_types=(), args=(), ret_types=None,
             query: bool = False, **kw):
        """Encode `args` with `arg_types`, call, decode with `ret_types`."""
        payload = candid_encode(list(zip(arg_types, args)))
        raw = self.query(canister, method, payload) if query else self.update(canister, method, payload, **kw)
        if raw is None:
            return None
        return candid_decode(raw, ret_types)
