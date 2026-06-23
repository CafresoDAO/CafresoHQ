// ──────────────────────────────────────────────────────────────────────────
// SHA-256 + HMAC-SHA256 — self-contained, no external packages.
//
// Vendored because this repo has no mops/vessel setup. Used by the keys
// canister to mint HMAC-signed HQ session tokens that the OCI gateway verifier
// (oci-fleet/hq_token.py, Python stdlib hmac/hashlib) re-checks byte-for-byte.
//
// Reference: FIPS 180-4 (SHA-256) and RFC 2104 (HMAC). Operates on [Nat8].
// ──────────────────────────────────────────────────────────────────────────
import Nat8 "mo:base/Nat8";
import Nat32 "mo:base/Nat32";
import Nat64 "mo:base/Nat64";
import Array "mo:base/Array";
import Buffer "mo:base/Buffer";
import Char "mo:base/Char";

module {

  // Round constants (first 32 bits of the fractional parts of the cube roots
  // of the first 64 primes).
  let K : [Nat32] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];

  func bnot(x : Nat32) : Nat32 { x ^ 0xFFFFFFFF };

  func u32be(b0 : Nat8, b1 : Nat8, b2 : Nat8, b3 : Nat8) : Nat32 {
    (Nat32.fromNat(Nat8.toNat(b0)) << 24)
      | (Nat32.fromNat(Nat8.toNat(b1)) << 16)
      | (Nat32.fromNat(Nat8.toNat(b2)) << 8)
      | Nat32.fromNat(Nat8.toNat(b3))
  };

  func byte(x : Nat32, shift : Nat32) : Nat8 {
    Nat8.fromNat(Nat32.toNat((x >> shift) & 0xFF))
  };

  /// SHA-256 over `msg`, returning the 32-byte digest.
  public func hash(msg : [Nat8]) : [Nat8] {
    var h0 : Nat32 = 0x6a09e667;
    var h1 : Nat32 = 0xbb67ae85;
    var h2 : Nat32 = 0x3c6ef372;
    var h3 : Nat32 = 0xa54ff53a;
    var h4 : Nat32 = 0x510e527f;
    var h5 : Nat32 = 0x9b05688c;
    var h6 : Nat32 = 0x1f83d9ab;
    var h7 : Nat32 = 0x5be0cd19;

    // ── Pre-processing: pad to a multiple of 64 bytes ──────────────────────
    let msgLen = msg.size();
    let bitLen : Nat64 = Nat64.fromNat(msgLen) * 8;
    let buf = Buffer.Buffer<Nat8>(msgLen + 72);
    for (b in msg.vals()) { buf.add(b) };
    buf.add(0x80);
    while (buf.size() % 64 != 56) { buf.add(0x00) };
    // 64-bit big-endian message length in bits
    var s : Nat = 64;
    while (s > 0) {
      s -= 8;
      buf.add(Nat8.fromNat(Nat64.toNat((bitLen >> Nat64.fromNat(s)) & 0xFF)));
    };

    let data = Buffer.toArray(buf);
    let numBlocks = data.size() / 64;

    let w = Array.init<Nat32>(64, 0);
    var blk : Nat = 0;
    while (blk < numBlocks) {
      let base = blk * 64;
      var t : Nat = 0;
      while (t < 16) {
        let j = base + t * 4;
        w[t] := u32be(data[j], data[j + 1], data[j + 2], data[j + 3]);
        t += 1;
      };
      while (t < 64) {
        let x15 = w[t - 15];
        let x2 = w[t - 2];
        let sig0 = (x15 <>> 7) ^ (x15 <>> 18) ^ (x15 >> 3);
        let sig1 = (x2 <>> 17) ^ (x2 <>> 19) ^ (x2 >> 10);
        w[t] := w[t - 16] +% sig0 +% w[t - 7] +% sig1;
        t += 1;
      };

      var a = h0;
      var b = h1;
      var c = h2;
      var d = h3;
      var e = h4;
      var f = h5;
      var g = h6;
      var hh = h7;

      t := 0;
      while (t < 64) {
        let bigS1 = (e <>> 6) ^ (e <>> 11) ^ (e <>> 25);
        let ch = (e & f) ^ (bnot(e) & g);
        let temp1 = hh +% bigS1 +% ch +% K[t] +% w[t];
        let bigS0 = (a <>> 2) ^ (a <>> 13) ^ (a <>> 22);
        let maj = (a & b) ^ (a & c) ^ (b & c);
        let temp2 = bigS0 +% maj;
        hh := g;
        g := f;
        f := e;
        e := d +% temp1;
        d := c;
        c := b;
        b := a;
        a := temp1 +% temp2;
        t += 1;
      };

      h0 := h0 +% a;
      h1 := h1 +% b;
      h2 := h2 +% c;
      h3 := h3 +% d;
      h4 := h4 +% e;
      h5 := h5 +% f;
      h6 := h6 +% g;
      h7 := h7 +% hh;
      blk += 1;
    };

    let out = Buffer.Buffer<Nat8>(32);
    for (h in [h0, h1, h2, h3, h4, h5, h6, h7].vals()) {
      out.add(byte(h, 24));
      out.add(byte(h, 16));
      out.add(byte(h, 8));
      out.add(byte(h, 0));
    };
    Buffer.toArray(out)
  };

  /// HMAC-SHA256(key, msg) → 32-byte tag. (RFC 2104, block size 64.)
  public func hmac(key : [Nat8], msg : [Nat8]) : [Nat8] {
    let blockSize : Nat = 64;
    // Keys longer than the block size are first hashed.
    let k0 = if (key.size() > blockSize) { hash(key) } else { key };

    let ipad = Array.init<Nat8>(blockSize, 0x36);
    let opad = Array.init<Nat8>(blockSize, 0x5c);
    var i : Nat = 0;
    while (i < k0.size()) {
      ipad[i] := ipad[i] ^ k0[i];
      opad[i] := opad[i] ^ k0[i];
      i += 1;
    };

    // inner = H(ipad || msg)
    let inner = Buffer.Buffer<Nat8>(blockSize + msg.size());
    for (b in ipad.vals()) { inner.add(b) };
    for (b in msg.vals()) { inner.add(b) };
    let innerHash = hash(Buffer.toArray(inner));

    // outer = H(opad || inner)
    let outer = Buffer.Buffer<Nat8>(blockSize + 32);
    for (b in opad.vals()) { outer.add(b) };
    for (b in innerHash.vals()) { outer.add(b) };
    hash(Buffer.toArray(outer))
  };

  /// Lowercase hex encoding of a byte array.
  public func toHex(bytes : [Nat8]) : Text {
    let hexChars : [Char] = [
      '0', '1', '2', '3', '4', '5', '6', '7',
      '8', '9', 'a', 'b', 'c', 'd', 'e', 'f',
    ];
    var out = "";
    for (b in bytes.vals()) {
      let n = Nat8.toNat(b);
      out := out # Char.toText(hexChars[n / 16]) # Char.toText(hexChars[n % 16]);
    };
    out
  };
}
