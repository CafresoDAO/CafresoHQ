// ──────────────────────────────────────────────────────────────────────────
// CafresoAI — vetKeys vault key derivation canister
//
// Per-user encryption keys derived via ICP vetKeys (threshold BLS12-381).
// Each user's vault key is keyed on their Internet Identity principal, so:
//   • The same principal always derives the same key (cross-device)
//   • No single subnet node ever sees the plaintext key
//   • Only the holder of the matching transport private key can decrypt
//   • Even Anthony (canister controller) cannot recover a user's key
//
// Two endpoints:
//   • vault_public_key()                       query, free, returns BLS pubkey
//   • vault_encrypted_key(transport_pubkey)    update, ~26B cycles
//
// Cost model: one vault_encrypted_key call per browser session (cached in
// sessionStorage). Daily-active user ≈ $0.03/day, $1/month per user.
// ──────────────────────────────────────────────────────────────────────────

import Principal "mo:base/Principal";
import Text "mo:base/Text";
import Blob "mo:base/Blob";
import Cycles "mo:base/ExperimentalCycles";
import Error "mo:base/Error";
import Time "mo:base/Time";
import Int "mo:base/Int";
import Nat8 "mo:base/Nat8";
import Nat32 "mo:base/Nat32";
import Char "mo:base/Char";
import Buffer "mo:base/Buffer";
import Sha256 "Sha256";

actor CafresoaiKeys {

    // ── Management canister vetKD interface ────────────────────────────────
    // Production interface (verified empirically May 2026 — error msg from
    // mgmt canister explicitly required `context : blob` rather than the
    // older `derivation_path : vec blob`). Names match the current
    // IC interface spec: vetkd_public_key + vetkd_derive_key.
    type VetKDCurve = { #bls12_381_g2 };
    type VetKDKeyId = { curve : VetKDCurve; name : Text };

    type VetKDPublicKeyArgs = {
        canister_id : ?Principal;
        context : Blob;          // domain-separation tag (replaces derivation_path)
        key_id : VetKDKeyId;
    };

    type VetKDPublicKeyReply = {
        public_key : Blob;
    };

    type VetKDDeriveKeyArgs = {
        input : Blob;                  // per-user derivation seed (was derivation_id)
        context : Blob;                // domain-separation tag (was public_key_derivation_path)
        key_id : VetKDKeyId;
        transport_public_key : Blob;   // was encryption_public_key
    };

    type VetKDDeriveKeyReply = {
        encrypted_key : Blob;
    };

    let ic : actor {
        vetkd_public_key : (VetKDPublicKeyArgs) -> async VetKDPublicKeyReply;
        vetkd_derive_key : (VetKDDeriveKeyArgs) -> async VetKDDeriveKeyReply;
    } = actor "aaaaa-aa";

    // ── Configuration ──────────────────────────────────────────────────────
    // Production BLS key on mainnet. For local replica use "dfx_test_key".
    let KEY_NAME : Text = "key_1";

    // Domain-separation tag scoping this key family to the vault subsystem.
    // Future BYOK / messaging features should use distinct contexts so a
    // vault-key compromise can't widen blast radius.
    let VAULT_CONTEXT : Blob = Text.encodeUtf8("cafresoai-vault-v1");

    // vetkd_derive_encrypted_key cost on mainnet (subject to NNS proposals).
    let VETKD_CALL_CYCLES : Nat = 26_153_846_153;

    // ── Public methods ─────────────────────────────────────────────────────

    /// Returns the canister's vetKD public key for the vault derivation path.
    /// Used by clients to verify decrypted master keys. Free + uncached
    /// (cheap to recompute, but clients should cache for the session).
    public func vault_public_key() : async Blob {
        let { public_key } = await ic.vetkd_public_key({
            canister_id = null;
            context = VAULT_CONTEXT;
            key_id = { curve = #bls12_381_g2; name = KEY_NAME };
        });
        public_key
    };

    /// Returns the caller's vault master key, encrypted under their transport
    /// public key. Caller MUST be authenticated (no anonymous principals).
    /// Cycle cost is paid by this canister out of its own balance.
    public shared(msg) func vault_encrypted_key(transport_public_key : Blob) : async Blob {
        let caller = msg.caller;
        if (Principal.isAnonymous(caller)) {
            throw Error.reject("anonymous principals cannot derive vault keys");
        };
        if (transport_public_key.size() == 0) {
            throw Error.reject("transport_public_key is required");
        };
        Cycles.add<system>(VETKD_CALL_CYCLES);
        let { encrypted_key } = await ic.vetkd_derive_key({
            input = Principal.toBlob(caller);
            context = VAULT_CONTEXT;
            key_id = { curve = #bls12_381_g2; name = KEY_NAME };
            transport_public_key = transport_public_key;
        });
        encrypted_key
    };

    // ── HQ container session tokens ──────────────────────────────────────────
    // The OCI gateway (hq.cafreso.com) gates each user's /u/<slug>/* route with a
    // Caddy forward_auth check. The credential is an HMAC-signed token THIS
    // canister mints for the authenticated caller. II ownership is proven
    // natively — the IC verifies the delegation, so msg.caller is unforgeable —
    // and the principal is bound into a token the gateway verifier re-checks with
    // a shared secret (Python stdlib hmac). Token format:
    //   v1.<principalText>.<expSeconds>.<hmacHex>
    // hmac = HMAC-SHA256(secret, "v1.<principalText>.<expSeconds>").

    // Principals allowed to set/rotate the shared secret. The secret itself is
    // NEVER exposed by any query. Two are permitted:
    //   • the HQ ops principal (revenue/admin II) — can rotate from an admin UI
    //   • the canister deploy controller — lets the secret be bootstrapped from
    //     dfx at deploy time, so it never has to transit a browser.
    let HQ_ADMIN : Principal =
      Principal.fromText("rc62u-qypnw-bbkkp-d56wk-tnzaq-vwhi2-cqqay-q56hw-gsqbp-6wegl-jae");
    let HQ_DEPLOYER : Principal =
      Principal.fromText("tzw3r-vl6w2-4gbq6-4kxdl-cqq35-q2kji-t34ph-pqyhj-4enus-dpe53-sqe");

    func isHqAdmin(p : Principal) : Bool {
      p == HQ_ADMIN or p == HQ_DEPLOYER
    };

    // Session lifetime; the shell re-mints before expiry while the II delegation
    // is still valid.
    let HQ_SESSION_TTL_SECONDS : Int = 1800; // 30 minutes

    // Shared HMAC secret, set by the admin and mirrored into the gateway's
    // HQ_SESSION_SECRET env. Empty until configured → minting is disabled.
    stable var hqSecret : Blob = "";

    func hexVal(c : Char) : ?Nat8 {
      let n = Char.toNat32(c);
      if (n >= 48 and n <= 57) { ?Nat8.fromNat(Nat32.toNat(n - 48)) }        // 0-9
      else if (n >= 97 and n <= 102) { ?Nat8.fromNat(Nat32.toNat(n - 87)) }  // a-f
      else if (n >= 65 and n <= 70) { ?Nat8.fromNat(Nat32.toNat(n - 55)) }   // A-F
      else { null };
    };

    func hexToBytes(t : Text) : ?[Nat8] {
      let buf = Buffer.Buffer<Nat8>(t.size() / 2);
      var hi : ?Nat8 = null;
      for (c in t.chars()) {
        switch (hexVal(c)) {
          case (null) { return null };
          case (?nib) {
            switch (hi) {
              case (null) { hi := ?nib };
              case (?h) { buf.add(h * 16 + nib); hi := null };
            };
          };
        };
      };
      switch (hi) { case (null) { ?Buffer.toArray(buf) }; case (?_) { null } };
    };

    /// Admin-only: set/rotate the HMAC secret shared with the gateway verifier.
    /// `secretHex` is lowercase/upper hex (>= 32 chars / 16 bytes recommended).
    public shared (msg) func setHqSessionSecret(secretHex : Text) : async () {
      if (not isHqAdmin(msg.caller)) {
        throw Error.reject("only the HQ admin may set the session secret");
      };
      switch (hexToBytes(secretHex)) {
        case (null) { throw Error.reject("secret must be valid hex") };
        case (?bytes) {
          if (bytes.size() < 16) {
            throw Error.reject("secret too short (>= 16 bytes / 32 hex chars)");
          };
          hqSecret := Blob.fromArray(bytes);
        };
      };
    };

    /// Whether an HQ session secret has been configured (no secret leaked).
    public query func hqSessionConfigured() : async Bool {
      hqSecret.size() > 0
    };

    /// Mint a short-lived HQ session token for the authenticated caller. The
    /// gateway verifier accepts it for the caller's container only.
    public shared (msg) func mintHqSession() : async { token : Text; exp : Int } {
      let caller = msg.caller;
      if (Principal.isAnonymous(caller)) {
        throw Error.reject("sign in with Internet Identity to mint an HQ session");
      };
      if (hqSecret.size() == 0) {
        throw Error.reject("HQ sessions are not configured yet");
      };
      let nowSec : Int = Time.now() / 1_000_000_000;
      let exp : Int = nowSec + HQ_SESSION_TTL_SECONDS;
      let signed : Text = "v1." # Principal.toText(caller) # "." # Int.toText(exp);
      let tag = Sha256.hmac(Blob.toArray(hqSecret), Blob.toArray(Text.encodeUtf8(signed)));
      { token = signed # "." # Sha256.toHex(tag); exp = exp };
    };

    // ── Diagnostics ────────────────────────────────────────────────────────
    public query func cycle_balance() : async Nat {
        Cycles.balance()
    };

    public query func key_config() : async { key_name : Text; context : Blob } {
        { key_name = KEY_NAME; context = VAULT_CONTEXT }
    };
}
