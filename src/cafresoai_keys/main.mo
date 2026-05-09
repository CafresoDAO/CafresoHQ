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

    // ── Diagnostics ────────────────────────────────────────────────────────
    public query func cycle_balance() : async Nat {
        Cycles.balance()
    };

    public query func key_config() : async { key_name : Text; context : Blob } {
        { key_name = KEY_NAME; context = VAULT_CONTEXT }
    };
}
