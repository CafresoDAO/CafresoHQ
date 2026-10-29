/// Response-verification v2 "skip certification" for every path.
///
/// A query `http_request` answer is uncertified, and the HTTP gateway on
/// <id>.icp0.io refuses an uncertified answer unless the canister has
/// certified, for that path, that the response needs NO certification. This
/// module holds the one constant tree that says so for every path:
///
///   http_expr / "<*>" / sha256(EXPR) → leaf ""
///
/// Set `rootHash()` as the canister's certified data (init + postupgrade),
/// then attach `headers(cert)` to each query response; `cert` comes from
/// CertifiedData.getCertificate() inside the query. The whole tree is
/// revealed in the witness, so the gateway can also prove that no more
/// specific path exists. Hashing and encoding follow the IC interface spec's
/// HashTree and the HTTP Gateway Protocol spec.
import Array "mo:base/Array";
import Blob "mo:base/Blob";
import Buffer "mo:base/Buffer";
import Nat8 "mo:base/Nat8";
import Text "mo:base/Text";
import Sha256 "Sha256";

module {
  public let EXPR : Text = "default_certification(ValidationArgs{no_certification:Empty{}})";

  func bytes(t : Text) : [Nat8] { Blob.toArray(Text.encodeUtf8(t)) };
  func cat(parts : [[Nat8]]) : [Nat8] { Array.flatten<Nat8>(parts) };
  func domain(sep : Text) : [Nat8] { let b = bytes(sep); cat([[Nat8.fromNat(b.size())], b]) };

  func exprHash() : [Nat8] { Sha256.hash(bytes(EXPR)) };
  func leafHash() : [Nat8] { Sha256.hash(cat([domain("ic-hashtree-leaf"), []])) };
  func labeled(lbl : [Nat8], sub : [Nat8]) : [Nat8] {
    Sha256.hash(cat([domain("ic-hashtree-labeled"), lbl, sub]));
  };

  /// The certified data to set: the root hash of the constant tree.
  public func rootHash() : Blob {
    Blob.fromArray(labeled(bytes("http_expr"), labeled(bytes("<*>"), labeled(exprHash(), leafHash()))));
  };

  // ── CBOR (only the shapes the witness needs: small arrays, uints, bytes, text) ──
  let SELF_DESCRIBE : [Nat8] = [0xd9, 0xd9, 0xf7];
  func head(major : Nat8, n : Nat) : [Nat8] {
    if (n < 24) { [(major << 5) | Nat8.fromNat(n)] } else { [(major << 5) | 24, Nat8.fromNat(n)] };
  };
  func cborBytes(b : [Nat8]) : [Nat8] { cat([head(2, b.size()), b]) };
  func cborText(t : Text) : [Nat8] { let b = bytes(t); cat([head(3, b.size()), b]) };
  // HashTree: Labeled = [2, label, sub], Leaf = [3, value].
  func cborLabeled(lbl : [Nat8], sub : [Nat8]) : [Nat8] { cat([head(4, 3), [2], cborBytes(lbl), sub]) };

  func treeCbor() : [Nat8] { cat([SELF_DESCRIBE,
    cborLabeled(bytes("http_expr"), cborLabeled(bytes("<*>"), cborLabeled(exprHash(), cat([head(4, 2), [3], cborBytes([])]))))]) };
  func exprPathCbor() : [Nat8] { cat([SELF_DESCRIBE, head(4, 2), cborText("http_expr"), cborText("<*>")]) };

  let B64_ALPHABET : Text = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  public func base64(b : [Nat8]) : Text {
    let B64 = Text.toArray(B64_ALPHABET);
    let out = Buffer.Buffer<Char>(((b.size() + 2) / 3) * 4);
    var i = 0;
    while (i < b.size()) {
      let n = b.size() - i;
      let b0 = Nat8.toNat(b[i]);
      let b1 = if (n > 1) { Nat8.toNat(b[i + 1]) } else { 0 };
      let b2 = if (n > 2) { Nat8.toNat(b[i + 2]) } else { 0 };
      let v = b0 * 65536 + b1 * 256 + b2;
      out.add(B64[v / 262144]);
      out.add(B64[(v / 4096) % 64]);
      out.add(if (n > 1) { B64[(v / 64) % 64] } else { '=' });
      out.add(if (n > 2) { B64[v % 64] } else { '=' });
      i += 3;
    };
    Text.fromIter(out.vals());
  };

  /// The two headers that let the gateway accept an uncertified query answer.
  public func headers(cert : Blob) : [(Text, Text)] {
    [
      ("IC-Certificate", "certificate=:" # base64(Blob.toArray(cert)) # ":, tree=:" # base64(treeCbor()) #
        ":, expr_path=:" # base64(exprPathCbor()) # ":, version=2"),
      ("IC-CertificateExpression", EXPR),
    ];
  };
};
