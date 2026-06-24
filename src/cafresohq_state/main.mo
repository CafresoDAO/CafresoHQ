// ──────────────────────────────────────────────────────────────────────────
// CafresoHQ — on-chain per-user state canister  (Phase 2)
//
// Makes the OCI container STATELESS: the durable source of truth for a user's
// HQ app state (conversations/tasks/settings) and their vetKeys-encrypted vault
// ciphertext lives here, keyed by Internet Identity principal, so a container
// can be stopped / recreated losslessly.
//
// AUTH MODEL (see docs/PHASE2_STATE_CANISTER.md §3):
//   The browser — which holds the II delegation — is the ONLY caller. Every key
//   derives from `msg.caller`; NO method takes a principal argument, so no caller
//   can address another user's rows. The OCI container holds no credential here.
//
// Storage uses mo:base/OrderedMap held in `stable` vars (enhanced orthogonal
// persistence — no pre/post-upgrade). NOTE: this scaffold keeps data on the heap;
// before scaling past a few GB of aggregate vault, migrate the vault chunk store
// to mo:stable-structures (stable memory) per the design doc §5.
// ──────────────────────────────────────────────────────────────────────────

import Principal "mo:base/Principal";
import Text "mo:base/Text";
import Blob "mo:base/Blob";
import Nat "mo:base/Nat";
import Nat8 "mo:base/Nat8";
import Nat32 "mo:base/Nat32";
import Int "mo:base/Int";
import Char "mo:base/Char";
import Iter "mo:base/Iter";
import Buffer "mo:base/Buffer";
import Time "mo:base/Time";
import Error "mo:base/Error";
import Cycles "mo:base/ExperimentalCycles";
import OrderedMap "mo:base/OrderedMap";
import Sha256 "Sha256";

actor CafresoHQState {

  // ── Types ────────────────────────────────────────────────────────────────
  public type HqDoc = { body : Blob; sha256 : Blob; version : Nat; updatedAt : Int };
  public type DocSummary = { name : Text; version : Nat; sha256 : Blob; updatedAt : Int };
  public type VaultMeta = {
    totalSize : Nat; chunkCount : Nat; sha256 : Blob; sealed : Bool; version : Nat; updatedAt : Int;
  };
  public type Usage = {
    docBytes : Nat; vaultBytes : Nat; objCount : Nat; quotaBytes : Nat; plan : Text; updatedAt : Int;
  };
  // Optimistic-concurrency result shared by every write.
  public type PutResult = { #ok : { version : Nat }; #conflict : { current : Nat }; #quota : Text };

  // ── Limits / defaults ──────────────────────────────────────────────────────
  let MAX_DOC_BYTES : Nat = 1_900_000;        // < 2 MiB ingress cap (Candid headroom)
  let MAX_CHUNK_BYTES : Nat = 1_900_000;      // vault ciphertext slice cap
  let DEFAULT_VAULT_QUOTA : Nat = 2 * 1024 * 1024 * 1024;  // 2 GiB
  let DOC_QUOTA : Nat = 8 * 1024 * 1024;      // 8 MB of HQ docs/user (generous)
  let PLAN_TTL_SLACK : Int = 0;

  // ── Ordered-map operations (functional, stable-persistable) ───────────────
  let pOps = OrderedMap.Make<Principal>(Principal.compare);
  let tOps = OrderedMap.Make<Text>(Text.compare);

  type DocMap = OrderedMap.Map<Text, HqDoc>;
  type MetaMap = OrderedMap.Map<Text, VaultMeta>;
  type ChunkMap = OrderedMap.Map<Text, Blob>;   // key = objId # "#" # ix

  // ── Stable storage (keyed by principal) ───────────────────────────────────
  stable var hqDocs : OrderedMap.Map<Principal, DocMap> = pOps.empty<DocMap>();
  stable var docSeq : OrderedMap.Map<Principal, Nat> = pOps.empty<Nat>();   // per-user monotonic version
  stable var vaultMetas : OrderedMap.Map<Principal, MetaMap> = pOps.empty<MetaMap>();
  stable var vaultChunks : OrderedMap.Map<Principal, ChunkMap> = pOps.empty<ChunkMap>();
  stable var usageMap : OrderedMap.Map<Principal, Usage> = pOps.empty<Usage>();

  // Plan-quota HMAC secret (mirrors cafresohq_keys; gates QUOTA only, never data).
  stable var planSecret : Blob = "";
  // First caller of setPlanSecret becomes the plan admin (the deployer).
  stable var planAdmin : ?Principal = null;

  // ── Helpers ────────────────────────────────────────────────────────────────
  func now() : Int { Time.now() };

  // Saturating Nat subtraction — usage deltas must never trap on drift.
  func subSat(a : Nat, b : Nat) : Nat { if (a > b) { a - b } else { 0 } };

  func docsOf(p : Principal) : DocMap { switch (pOps.get(hqDocs, p)) { case (?m) m; case null tOps.empty<HqDoc>() } };
  func metasOf(p : Principal) : MetaMap { switch (pOps.get(vaultMetas, p)) { case (?m) m; case null tOps.empty<VaultMeta>() } };
  func chunksOf(p : Principal) : ChunkMap { switch (pOps.get(vaultChunks, p)) { case (?m) m; case null tOps.empty<Blob>() } };
  func seqOf(p : Principal) : Nat { switch (pOps.get(docSeq, p)) { case (?n) n; case null 0 } };

  func usageOf(p : Principal) : Usage {
    switch (pOps.get(usageMap, p)) {
      case (?u) u;
      case null { { docBytes = 0; vaultBytes = 0; objCount = 0; quotaBytes = DEFAULT_VAULT_QUOTA; plan = "free"; updatedAt = 0 } };
    };
  };
  func setUsage(p : Principal, u : Usage) { usageMap := pOps.put(usageMap, p, { u with updatedAt = now() }) };
  func bumpSeq(p : Principal) : Nat { let n = seqOf(p) + 1; docSeq := pOps.put(docSeq, p, n); n };

  func chunkKey(objId : Text, ix : Nat) : Text { objId # "#" # Nat.toText(ix) };

  // ── HQ docs ────────────────────────────────────────────────────────────────
  /// Create/update one HQ doc (e.g. "tasks","projects","messages","memory/x").
  /// expectVersion = 0 for first write; otherwise must match current or you get #conflict.
  public shared (msg) func putHqDoc(name : Text, body : Blob, sha256 : Blob, expectVersion : Nat) : async PutResult {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in with Internet Identity") };
    if (body.size() > MAX_DOC_BYTES) { return #quota("doc exceeds 1.9 MiB limit") };
    let docs = docsOf(caller);
    let prev = tOps.get(docs, name);
    let curVer = switch (prev) { case (?d) d.version; case null 0 };
    if (expectVersion != curVer) { return #conflict({ current = curVer }) };
    // Quota (doc bytes) — replace old size with new.
    let u = usageOf(caller);
    let prevBytes = switch (prev) { case (?d) d.body.size(); case null 0 };
    let newDocBytes : Nat = subSat(u.docBytes, prevBytes) + body.size();
    if (newDocBytes > DOC_QUOTA) { return #quota("HQ docs quota exceeded") };
    let ver = curVer + 1;
    let doc : HqDoc = { body = body; sha256 = sha256; version = ver; updatedAt = now() };
    hqDocs := pOps.put(hqDocs, caller, tOps.put(docs, name, doc));
    setUsage(caller, { u with docBytes = newDocBytes });
    ignore bumpSeq(caller);
    #ok({ version = ver });
  };

  public shared query (msg) func getHqDoc(name : Text) : async ?HqDoc {
    if (Principal.isAnonymous(msg.caller)) { return null };
    tOps.get(docsOf(msg.caller), name);
  };

  public shared query (msg) func listHqDocs() : async [DocSummary] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    let out = Buffer.Buffer<DocSummary>(8);
    for ((name, d) in tOps.entries(docsOf(msg.caller))) {
      out.add({ name = name; version = d.version; sha256 = d.sha256; updatedAt = d.updatedAt });
    };
    Buffer.toArray(out);
  };

  public shared (msg) func deleteHqDoc(name : Text) : async Bool {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    let docs = docsOf(caller);
    switch (tOps.get(docs, name)) {
      case null { false };
      case (?d) {
        hqDocs := pOps.put(hqDocs, caller, tOps.delete(docs, name));
        let u = usageOf(caller);
        setUsage(caller, { u with docBytes = subSat(u.docBytes, d.body.size()) });
        ignore bumpSeq(caller);
        true;
      };
    };
  };

  /// Monotonic per-user version — cheap int the container/browser compare to
  /// decide who is ahead (see design §4-E).
  public shared query (msg) func hqVersion() : async Nat {
    if (Principal.isAnonymous(msg.caller)) { return 0 };
    seqOf(msg.caller);
  };

  // ── Vault (chunked ciphertext; canister never decrypts) ───────────────────
  public shared (msg) func putVaultMeta(objId : Text, totalSize : Nat, chunkCount : Nat, sha256 : Blob, expectVersion : Nat) : async PutResult {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    let metas = metasOf(caller);
    let prev = tOps.get(metas, objId);
    let curVer = switch (prev) { case (?m) m.version; case null 0 };
    if (expectVersion != curVer) { return #conflict({ current = curVer }) };
    let ver = curVer + 1;
    let meta : VaultMeta = {
      totalSize = totalSize; chunkCount = chunkCount; sha256 = sha256;
      sealed = false; version = ver; updatedAt = now();
    };
    vaultMetas := pOps.put(vaultMetas, caller, tOps.put(metas, objId, meta));
    #ok({ version = ver });
  };

  public shared (msg) func putVaultChunk(objId : Text, version : Nat, ix : Nat, data : Blob) : async PutResult {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    if (data.size() > MAX_CHUNK_BYTES) { return #quota("chunk exceeds 1.9 MiB limit") };
    // Must reference the in-progress meta version (defends against stale writers).
    switch (tOps.get(metasOf(caller), objId)) {
      case null { return #conflict({ current = 0 }) };
      case (?m) { if (m.version != version) { return #conflict({ current = m.version }) } };
    };
    let chunks = chunksOf(caller);
    let key = chunkKey(objId, ix);
    let prevBytes = switch (tOps.get(chunks, key)) { case (?b) b.size(); case null 0 };
    let u = usageOf(caller);
    let newVaultBytes : Nat = subSat(u.vaultBytes, prevBytes) + data.size();
    if (newVaultBytes > u.quotaBytes) { return #quota("vault quota exceeded") };
    vaultChunks := pOps.put(vaultChunks, caller, tOps.put(chunks, key, data));
    setUsage(caller, { u with vaultBytes = newVaultBytes });
    #ok({ version = version });
  };

  /// Publish atomically: flip sealed=true once all chunks are stored.
  public shared (msg) func sealVault(objId : Text, version : Nat) : async PutResult {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    let metas = metasOf(caller);
    switch (tOps.get(metas, objId)) {
      case null { #conflict({ current = 0 }) };
      case (?m) {
        if (m.version != version) { return #conflict({ current = m.version }) };
        let sealed : VaultMeta = { m with sealed = true; updatedAt = now() };
        vaultMetas := pOps.put(vaultMetas, caller, tOps.put(metas, objId, sealed));
        let u = usageOf(caller);
        // Count a sealed object once (idempotent on re-seal of an existing object).
        if (not m.sealed) { setUsage(caller, { u with objCount = u.objCount + 1 }) };
        #ok({ version = version });
      };
    };
  };

  public shared query (msg) func getVaultMeta(objId : Text) : async ?VaultMeta {
    if (Principal.isAnonymous(msg.caller)) { return null };
    switch (tOps.get(metasOf(msg.caller), objId)) {
      case (?m) { if (m.sealed) { ?m } else { null } };   // hide half-written objects
      case null { null };
    };
  };

  public shared query (msg) func getVaultChunk(objId : Text, ix : Nat) : async ?Blob {
    if (Principal.isAnonymous(msg.caller)) { return null };
    tOps.get(chunksOf(msg.caller), chunkKey(objId, ix));
  };

  public shared (msg) func deleteVault(objId : Text) : async Bool {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    let metas = metasOf(caller);
    switch (tOps.get(metas, objId)) {
      case null { false };
      case (?m) {
        // Drop all chunks for this object + the meta; reclaim quota.
        var chunks = chunksOf(caller);
        var freed : Nat = 0;
        var i : Nat = 0;
        while (i < m.chunkCount) {
          let key = chunkKey(objId, i);
          switch (tOps.get(chunks, key)) { case (?b) { freed += b.size(); chunks := tOps.delete(chunks, key) }; case null {} };
          i += 1;
        };
        vaultChunks := pOps.put(vaultChunks, caller, chunks);
        vaultMetas := pOps.put(vaultMetas, caller, tOps.delete(metas, objId));
        let u = usageOf(caller);
        let newCount : Nat = if (u.objCount > 0 and m.sealed) { u.objCount - 1 } else { u.objCount };
        setUsage(caller, { u with vaultBytes = subSat(u.vaultBytes, freed); objCount = newCount });
        true;
      };
    };
  };

  public shared query (msg) func myUsage() : async Usage {
    if (Principal.isAnonymous(msg.caller)) { throw Error.reject("sign in") };
    usageOf(msg.caller);
  };

  // ── Plan quota (HMAC-verified plan token; gates quota only) ────────────────
  func hexVal(c : Char) : ?Nat8 {
    let n = Char.toNat32(c);
    if (n >= 48 and n <= 57) { ?Nat8.fromNat(Nat32.toNat(n - 48)) }
    else if (n >= 97 and n <= 102) { ?Nat8.fromNat(Nat32.toNat(n - 87)) }
    else if (n >= 65 and n <= 70) { ?Nat8.fromNat(Nat32.toNat(n - 55)) }
    else { null };
  };
  func hexToBytes(t : Text) : ?[Nat8] {
    let buf = Buffer.Buffer<Nat8>(t.size() / 2);
    var hi : ?Nat8 = null;
    for (c in t.chars()) {
      switch (hexVal(c)) {
        case (null) { return null };
        case (?nib) { switch (hi) { case (null) { hi := ?nib }; case (?h) { buf.add(h * 16 + nib); hi := null } } };
      };
    };
    switch (hi) { case (null) { ?Buffer.toArray(buf) }; case (?_) { null } };
  };

  func quotaForPlan(plan : Text) : Nat {
    if (plan == "always-on") { 50 * 1024 * 1024 * 1024 }      // 50 GiB
    else if (plan == "pro") { 10 * 1024 * 1024 * 1024 }        // 10 GiB
    else { DEFAULT_VAULT_QUOTA };                              // free = 2 GiB
  };

  /// Apply a plan tier from the same HMAC token cafresohq_keys mints
  /// (v1plan.<principal>.<plan>.<exp>.<hmacHex>). Sets quota; never touches data.
  public shared (msg) func setPlan(token : Text) : async Bool {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    if (planSecret.size() == 0) { throw Error.reject("plan verification not configured") };
    let parts = Iter.toArray(Text.split(token, #char '.'));
    if (parts.size() != 5 or parts[0] != "v1plan") { throw Error.reject("malformed plan token") };
    let principalText = parts[1];
    let plan = parts[2];
    let expText = parts[3];
    let providedHmac = parts[4];
    if (principalText != Principal.toText(caller)) { throw Error.reject("plan token not for caller") };
    let signed = "v1plan." # principalText # "." # plan # "." # expText;
    let tag = Sha256.hmac(Blob.toArray(planSecret), Blob.toArray(Text.encodeUtf8(signed)));
    if (Sha256.toHex(tag) != providedHmac) { throw Error.reject("invalid plan token signature") };
    // Expiry check.
    let expOpt = textToInt(expText);
    switch (expOpt) {
      case null { throw Error.reject("bad exp") };
      case (?exp) { if (now() / 1_000_000_000 > exp + PLAN_TTL_SLACK) { throw Error.reject("plan token expired") } };
    };
    let u = usageOf(caller);
    setUsage(caller, { u with plan = plan; quotaBytes = quotaForPlan(plan) });
    true;
  };

  func textToInt(t : Text) : ?Int {
    var acc : Int = 0; var any = false;
    for (c in t.chars()) {
      let n = Char.toNat32(c);
      if (n >= 48 and n <= 57) { acc := acc * 10 + Int.abs(Nat32.toNat(n - 48)); any := true } else { return null };
    };
    if (any) { ?acc } else { null };
  };

  public shared (msg) func setPlanSecret(secretHex : Text) : async () {
    let caller = msg.caller;
    switch (planAdmin) {
      case null { planAdmin := ?caller };   // first caller (deployer) claims admin
      case (?a) { if (caller != a) { throw Error.reject("only the plan admin may set the secret") } };
    };
    switch (hexToBytes(secretHex)) {
      case null { throw Error.reject("secret must be valid hex") };
      case (?bytes) {
        if (bytes.size() < 16) { throw Error.reject("secret too short (>= 16 bytes)") };
        planSecret := Blob.fromArray(bytes);
      };
    };
  };

  public query func planConfigured() : async Bool { planSecret.size() > 0 };

  // ── Diagnostics ────────────────────────────────────────────────────────────
  public query func cycle_balance() : async Nat { Cycles.balance() };
}
