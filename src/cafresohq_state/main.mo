// ──────────────────────────────────────────────────────────────────────────
// CafresoHQ — on-chain per-user state canister  (Phase 2)
//
// Makes the OCI container STATELESS: the durable source of truth for a user's
// HQ app state (conversations/tasks/settings) and their vetKeys-encrypted vault
// ciphertext lives here, keyed by Internet Identity principal, so a container
// can be stopped / recreated losslessly.
//
// AUTH MODEL (see docs/PHASE2_STATE_CANISTER.md §3):
//   The browser — which holds the II delegation — is the primary caller. Every key
//   derives from `msg.caller`; NO method takes a principal argument, so no caller
//   can address another user's rows. The OCI container holds no credential here.
//   Sprint-2 exception: the PAYROLL timer below makes OUTBOUND calls to ICRC-2
//   ledgers (icrc2_transfer_from) — but only under an allowance the user signed
//   (icrc2_approve, spender = this canister), which is the hard spending ceiling.
//
// Storage uses mo:base/OrderedMap held in `stable` vars. NOTE: this scaffold
// keeps data on the heap; before scaling past a few GB of aggregate vault,
// migrate the vault chunk store to mo:stable-structures (stable memory) per the
// design doc §5. `system func postupgrade` exists ONLY to re-arm the payroll
// timer — timers never survive an upgrade.
// ──────────────────────────────────────────────────────────────────────────

import Principal "mo:base/Principal";
import Text "mo:base/Text";
import Blob "mo:base/Blob";
import Nat "mo:base/Nat";
import Nat8 "mo:base/Nat8";
import Nat32 "mo:base/Nat32";
import Nat16 "mo:base/Nat16";
import Int "mo:base/Int";
import Char "mo:base/Char";
import Iter "mo:base/Iter";
import Buffer "mo:base/Buffer";
import Time "mo:base/Time";
import Error "mo:base/Error";
import Cycles "mo:base/ExperimentalCycles";
import OrderedMap "mo:base/OrderedMap";
import Nat64 "mo:base/Nat64";
import Array "mo:base/Array";
import Timer "mo:base/Timer";
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

  // ── ICP Services + agent wallets ───────────────────────────────────────────
  // Per-agent "HQ wallet" POLICY. The wallet itself is an ICRC subaccount of the
  // user's principal (owner = user, subaccount = deterministic per-agent); this
  // canister never holds keys — it stores the spend policy and does the
  // rolling-window accounting so the cap is tamper-resistant (a user can't lift
  // their own agent's cap by clearing browser storage). Payroll (below) is the
  // one place this canister moves funds itself, and only via a user-signed
  // ICRC-2 allowance that is itself the hard ceiling.
  public type AgentWallet = {
    agentId : Text;
    subaccountHex : Text;   // 64-hex (32-byte) ICRC subaccount for this agent
    token : Text;           // default ledger symbol, e.g. "ICP" / "ckUSDT"
    spendCap : Nat;         // autonomous cap per window, in the token's base units
    windowSecs : Nat;       // rolling-window length (0 = per-transaction cap only)
    windowSpent : Nat;      // spent in the current window (base units)
    windowResetAt : Int;    // ns timestamp the current window started
    paused : Bool;          // per-agent kill switch
    updatedAt : Int;
  };
  // Atomic gate result for an autonomous agent spend.
  public type SpendResult = {
    #ok : { windowSpent : Nat; remaining : Nat };  // within cap, recorded
    #over : { cap : Nat; windowSpent : Nat };       // exceeds cap → route to user approval
    #paused;                                        // agent or global kill switch on
    #noWallet;                                      // no policy for this agent
  };
  // One installed "ICP Service" (wallet, publish, …). configJson is opaque.
  public type ServiceFlag = {
    serviceId : Text; enabled : Bool; configJson : Text; enabledAt : Int; updatedAt : Int;
  };

  // ── Published sites (Publish-to-Canister; hosted here + served publicly) ────
  // Reuses this canister instead of a separate one: same per-caller isolation,
  // already deployed + funded. http_request below reads ONLY siteFiles — never
  // the vault/doc maps — and the vault is client-encrypted ciphertext anyway.
  public type SiteFile = { contentType : Text; body : Blob; updatedAt : Int };
  public type PutFileResult = { #ok : { bytes : Nat }; #err : Text };
  public type SiteSummary = { project : Text; fileCount : Nat; totalBytes : Nat; updatedAt : Int };
  type HeaderField = (Text, Text);
  public type HttpRequest = { method : Text; url : Text; headers : [HeaderField]; body : Blob };
  public type HttpResponse = {
    status_code : Nat16; headers : [HeaderField]; body : Blob;
    streaming_strategy : ?Null; upgrade : ?Bool;
  };

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

  // Per-agent wallet policy + installed-services, both keyed by principal then
  // by a Text id (agentId / serviceId).
  type WalletMap = OrderedMap.Map<Text, AgentWallet>;
  type FlagMap = OrderedMap.Map<Text, ServiceFlag>;
  stable var agentWallets : OrderedMap.Map<Principal, WalletMap> = pOps.empty<WalletMap>();
  stable var serviceFlags : OrderedMap.Map<Principal, FlagMap> = pOps.empty<FlagMap>();
  // Per-user global "pause all agent spending" kill switch.
  stable var allSpendPaused : OrderedMap.Map<Principal, Bool> = pOps.empty<Bool>();

  // Published-site files, per principal. key = "<project>/<relpath>".
  type SiteMap = OrderedMap.Map<Text, SiteFile>;
  stable var siteFiles : OrderedMap.Map<Principal, SiteMap> = pOps.empty<SiteMap>();
  stable var siteUsage : OrderedMap.Map<Principal, Nat> = pOps.empty<Nat>();
  let MAX_SITE_FILE_BYTES : Nat = 2_000_000;             // ~2 MiB per file
  let MAX_SITE_USER_BYTES : Nat = 200 * 1024 * 1024;     // 200 MiB of sites per user

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

  func walletsOf(p : Principal) : WalletMap { switch (pOps.get(agentWallets, p)) { case (?m) m; case null tOps.empty<AgentWallet>() } };
  func flagsOf(p : Principal) : FlagMap { switch (pOps.get(serviceFlags, p)) { case (?m) m; case null tOps.empty<ServiceFlag>() } };
  func isAllPaused(p : Principal) : Bool { switch (pOps.get(allSpendPaused, p)) { case (?b) b; case null false } };

  func sitesOf(p : Principal) : SiteMap { switch (pOps.get(siteFiles, p)) { case (?m) m; case null tOps.empty<SiteFile>() } };
  func siteUsageOf(p : Principal) : Nat { switch (pOps.get(siteUsage, p)) { case (?n) n; case null 0 } };
  func siteSafe(c : Char) : Bool {
    (c >= 'a' and c <= 'z') or (c >= 'A' and c <= 'Z') or (c >= '0' and c <= '9') or c == '-' or c == '_' or c == '.'
  };
  func validProject(p : Text) : Bool {
    if (p.size() == 0 or p.size() > 64) { return false };
    for (c in p.chars()) { if (not siteSafe(c)) { return false } };
    not Text.contains(p, #text "..");
  };
  func normSitePath(path : Text) : ?Text {
    let p = Text.trimStart(path, #char '/');
    if (Text.contains(p, #text "..")) { return null };
    if (p.size() == 0) { ?"index.html" } else { ?p };
  };

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

  // ── Agent wallets (policy + tamper-resistant spend accounting) ─────────────
  /// Create/update an agent's wallet policy. Rolling-window accounting is
  /// preserved across policy edits (changing the cap doesn't refill the window).
  public shared (msg) func putAgentWallet(
    agentId : Text, subaccountHex : Text, token : Text, spendCap : Nat, windowSecs : Nat, paused : Bool,
  ) : async () {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    let ws = walletsOf(caller);
    let (spent, resetAt) = switch (tOps.get(ws, agentId)) {
      case (?w) (w.windowSpent, w.windowResetAt);
      case null (0, now());
    };
    let w : AgentWallet = {
      agentId; subaccountHex; token; spendCap; windowSecs;
      windowSpent = spent; windowResetAt = resetAt; paused; updatedAt = now();
    };
    agentWallets := pOps.put(agentWallets, caller, tOps.put(ws, agentId, w));
  };

  public shared query (msg) func getAgentWallet(agentId : Text) : async ?AgentWallet {
    if (Principal.isAnonymous(msg.caller)) { return null };
    tOps.get(walletsOf(msg.caller), agentId);
  };

  public shared query (msg) func listAgentWallets() : async [AgentWallet] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    let out = Buffer.Buffer<AgentWallet>(8);
    for ((_, w) in tOps.entries(walletsOf(msg.caller))) { out.add(w) };
    Buffer.toArray(out);
  };

  public shared (msg) func deleteAgentWallet(agentId : Text) : async Bool {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    let ws = walletsOf(caller);
    switch (tOps.get(ws, agentId)) {
      case null { false };
      case (?_) { agentWallets := pOps.put(agentWallets, caller, tOps.delete(ws, agentId)); true };
    };
  };

  /// Per-user global "pause all agent spending" kill switch.
  public shared (msg) func setAllSpendPaused(paused : Bool) : async () {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    allSpendPaused := pOps.put(allSpendPaused, caller, paused);
  };

  public shared query (msg) func spendPausedAll() : async Bool {
    if (Principal.isAnonymous(msg.caller)) { return false };
    isAllPaused(msg.caller);
  };

  /// Atomic cap gate. The browser calls this BEFORE signing an autonomous
  /// agent-initiated transfer:
  ///   #ok       → within the rolling cap and recorded; go ahead and sign.
  ///   #over     → exceeds the cap; nothing recorded — route to user approval.
  ///   #paused   → agent or global kill switch is on; block.
  ///   #noWallet → no policy for this agent; block.
  public shared (msg) func recordSpend(agentId : Text, amount : Nat) : async SpendResult {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    if (isAllPaused(caller)) { return #paused };
    let ws = walletsOf(caller);
    switch (tOps.get(ws, agentId)) {
      case null { #noWallet };
      case (?w) {
        if (w.paused) { return #paused };
        // Roll the window if it has fully elapsed.
        let nowSecs = now() / 1_000_000_000;
        let startSecs = w.windowResetAt / 1_000_000_000;
        let rolled = w.windowSecs > 0 and nowSecs >= startSecs + w.windowSecs;
        let spent0 = if (rolled) { 0 } else { w.windowSpent };
        let reset0 = if (rolled) { now() } else { w.windowResetAt };
        let projected = spent0 + amount;
        if (projected > w.spendCap) { return #over({ cap = w.spendCap; windowSpent = spent0 }) };
        let updated : AgentWallet = { w with windowSpent = projected; windowResetAt = reset0; updatedAt = now() };
        agentWallets := pOps.put(agentWallets, caller, tOps.put(ws, agentId, updated));
        bumpSpendTotal(caller, agentId, w.token, amount);
        #ok({ windowSpent = projected; remaining = subSat(w.spendCap, projected) });
      };
    };
  };

  // ── Lifetime spend metering (advisory P&L display; caps stay the gate) ─────
  type TokenTotals = OrderedMap.Map<Text, Nat>;      // token symbol → base units
  type AgentTotals = OrderedMap.Map<Text, TokenTotals>; // agentId → totals
  stable var spendTotals : OrderedMap.Map<Principal, AgentTotals> = pOps.empty<AgentTotals>();

  func bumpSpendTotal(user : Principal, agentId : Text, token : Text, amount : Nat) {
    let agents = switch (pOps.get(spendTotals, user)) { case (?m) m; case null tOps.empty<TokenTotals>() };
    let tokens = switch (tOps.get(agents, agentId)) { case (?m) m; case null tOps.empty<Nat>() };
    let cur = switch (tOps.get(tokens, token)) { case (?n) n; case null 0 };
    spendTotals := pOps.put(spendTotals, user, tOps.put(agents, agentId, tOps.put(tokens, token, cur + amount)));
  };

  /// Lifetime recorded agent spend: [(agentId, [(token, baseUnits)])].
  public shared query (msg) func getSpendTotals() : async [(Text, [(Text, Nat)])] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    switch (pOps.get(spendTotals, msg.caller)) {
      case null { [] };
      case (?agents) {
        let out = Buffer.Buffer<(Text, [(Text, Nat)])>(8);
        for ((aid, tokens) in tOps.entries(agents)) {
          out.add((aid, Iter.toArray(tOps.entries(tokens))));
        };
        Buffer.toArray(out);
      };
    };
  };

  // ── Payroll (canister-timer salaries / auto-refill over ICRC-2) ─────────────
  // The user signs ONE icrc2_approve(spender = THIS canister) on the ledger; the
  // 5-minute timer below then pulls user-main-account → agent subaccount with
  // icrc2_transfer_from. The allowance is the hard budget — this canister can
  // never move more than the user approved, and `setPayrollPaused` is the
  // per-user kill switch. Exactly-once: nextRunAt advances BEFORE the ledger
  // await (reentrancy guard), a `pending` Payout keyed (agentId, scheduledAt) is
  // written first, and created_at_time + memo derive from that key so ledger
  // TX-window dedup makes retries safe. Failure mode is a MISSED payout
  // (stalledSince + banner), never a double-pay.
  public type SalaryMode = { #salary; #refill };
  public type Salary = {
    agentId : Text;
    ledger : Principal;     // ICRC-2 ledger canister
    token : Text;           // display symbol, e.g. "ICP"
    amount : Nat;           // per-period pay / refill top-up (base units)
    fee : Nat;              // ledger fee (base units); auto-corrected on #BadFee
    lowWatermark : Nat;     // #refill: skip while agent balance >= this
    periodSecs : Nat;
    nextRunAt : Int;        // ns
    mode : SalaryMode;
    active : Bool;
    stalledSince : ?Int;    // set on allowance/funds failures until a payout lands
    lastResult : Text;      // "", "paid", "skip:funded", "running", "retrying", "stalled:*", "failed:*"
    updatedAt : Int;
  };
  public type Payout = {
    key : Text;             // agentId # "#" # scheduledAt — dedup key AND ledger memo
    agentId : Text;
    token : Text;
    amount : Nat;
    scheduledAt : Int;      // ns; also the ledger created_at_time (dedup window)
    status : Text;          // "pending" | "paid" | "failed:<reason>"
    blockIndex : ?Nat;
    ts : Int;
  };

  // Minimal ICRC-1/2 ledger surface used by payroll.
  type Icrc1Account = { owner : Principal; subaccount : ?Blob };
  type TransferFromArgs = {
    spender_subaccount : ?Blob;
    from : Icrc1Account;
    to : Icrc1Account;
    amount : Nat;
    fee : ?Nat;
    memo : ?Blob;
    created_at_time : ?Nat64;
  };
  type TransferFromError = {
    #BadFee : { expected_fee : Nat };
    #BadBurn : { min_burn_amount : Nat };
    #InsufficientFunds : { balance : Nat };
    #InsufficientAllowance : { allowance : Nat };
    #TooOld;
    #CreatedInFuture : { ledger_time : Nat64 };
    #Duplicate : { duplicate_of : Nat };
    #TemporarilyUnavailable;
    #GenericError : { error_code : Nat; message : Text };
  };
  type LedgerActor = actor {
    icrc1_balance_of : shared query (Icrc1Account) -> async Nat;
    icrc2_transfer_from : shared (TransferFromArgs) -> async { #Ok : Nat; #Err : TransferFromError };
  };

  type SalaryMap = OrderedMap.Map<Text, Salary>;
  stable var salaries : OrderedMap.Map<Principal, SalaryMap> = pOps.empty<SalaryMap>();
  stable var payoutLog : OrderedMap.Map<Principal, [Payout]> = pOps.empty<[Payout]>();
  stable var payrollPausedMap : OrderedMap.Map<Principal, Bool> = pOps.empty<Bool>();

  let PAYROLL_SCAN_SECS : Nat = 300;
  let MAX_PAYOUTS_KEPT : Nat = 200;
  // Retry `pending` payouts only inside the ledger's 24h TX window (with slack).
  let PENDING_RETRY_MAX_NS : Int = 22 * 3600 * 1_000_000_000;
  // Don't re-attempt a pending created moments ago in this same scan.
  let PENDING_RETRY_MIN_AGE_NS : Int = 60 * 1_000_000_000;

  func secsToNs(s : Nat) : Int { s * 1_000_000_000 };
  func salariesOf(p : Principal) : SalaryMap { switch (pOps.get(salaries, p)) { case (?m) m; case null tOps.empty<Salary>() } };
  func payoutsOf(p : Principal) : [Payout] { switch (pOps.get(payoutLog, p)) { case (?a) a; case null [] } };
  func isPayrollPaused(p : Principal) : Bool { switch (pOps.get(payrollPausedMap, p)) { case (?b) b; case null false } };

  // Every write helper RE-READS the current map — scanPayroll spans awaits, and
  // the functional snapshot-put pattern would otherwise clobber concurrent
  // putSalary / pause edits (adversarial-review amendment).
  func patchSalary(user : Principal, agentId : Text, f : Salary -> Salary) {
    let m = salariesOf(user);
    switch (tOps.get(m, agentId)) {
      case (?s) { salaries := pOps.put(salaries, user, tOps.put(m, agentId, f(s))) };
      case null {};
    };
  };
  func appendPayout(user : Principal, po : Payout) {
    let buf = Buffer.fromArray<Payout>(payoutsOf(user));
    buf.add(po);
    while (buf.size() > MAX_PAYOUTS_KEPT) { ignore buf.remove(0) };
    payoutLog := pOps.put(payoutLog, user, Buffer.toArray(buf));
  };
  func setPayoutStatus(user : Principal, key : Text, status : Text, blockIndex : ?Nat) {
    let out = Array.map<Payout, Payout>(payoutsOf(user), func(po) {
      if (po.key == key) { { po with status; blockIndex; ts = now() } } else { po };
    });
    payoutLog := pOps.put(payoutLog, user, out);
  };
  func hasPayout(user : Principal, key : Text) : Bool {
    switch (Array.find<Payout>(payoutsOf(user), func(po) { po.key == key })) { case (?_) true; case null false };
  };
  // Destination = the agent wallet's 32-byte subaccount (wallet-deleted → stall).
  func agentSubOf(user : Principal, agentId : Text) : ?Blob {
    switch (tOps.get(walletsOf(user), agentId)) {
      case null { null };
      case (?w) {
        switch (hexToBytes(w.subaccountHex)) {
          case (?b) { if (b.size() == 32) { ?Blob.fromArray(b) } else { null } };
          case null { null };
        };
      };
    };
  };

  func stallSalary(user : Principal, agentId : Text, reason : Text) {
    patchSalary(user, agentId, func(x) {
      { x with lastResult = "stalled:" # reason;
        stalledSince = switch (x.stalledSince) { case (?t) ?t; case null ?now() };
        updatedAt = now() };
    });
  };

  /// One ledger attempt for an already-logged payout. Safe to retry with the
  /// SAME key: memo + created_at_time make the ledger dedup replays.
  func executeTransfer(user : Principal, s : Salary, key : Text, scheduledAt : Int, amount : Nat, sub : Blob) : async () {
    let ledger : LedgerActor = actor (Principal.toText(s.ledger));
    let args : TransferFromArgs = {
      spender_subaccount = null;
      from = { owner = user; subaccount = null };
      to = { owner = user; subaccount = ?sub };
      amount = amount;
      fee = ?s.fee;
      memo = ?Text.encodeUtf8(key);
      created_at_time = ?Nat64.fromIntWrap(scheduledAt);
    };
    try {
      let res = await ledger.icrc2_transfer_from(args);
      // All writes below re-read state (patchSalary / setPayoutStatus do).
      switch (res) {
        case (#Ok(block)) {
          setPayoutStatus(user, key, "paid", ?block);
          patchSalary(user, s.agentId, func(x) { { x with lastResult = "paid"; stalledSince = null; updatedAt = now() } });
        };
        case (#Err(#Duplicate(d))) {
          // A prior retry already landed — treat as paid.
          setPayoutStatus(user, key, "paid", ?d.duplicate_of);
          patchSalary(user, s.agentId, func(x) { { x with lastResult = "paid"; stalledSince = null; updatedAt = now() } });
        };
        case (#Err(#BadFee(e))) {
          // Auto-correct the stored fee and LEAVE the payout pending — the next
          // scan retries the same key with the right fee (dedup-safe).
          patchSalary(user, s.agentId, func(x) { { x with fee = e.expected_fee; lastResult = "retrying:fee"; updatedAt = now() } });
        };
        case (#Err(#InsufficientAllowance(_))) {
          setPayoutStatus(user, key, "failed:allowance", null);
          stallSalary(user, s.agentId, "allowance");
        };
        case (#Err(#InsufficientFunds(_))) {
          setPayoutStatus(user, key, "failed:funds", null);
          stallSalary(user, s.agentId, "funds");
        };
        case (#Err(#TooOld)) {
          setPayoutStatus(user, key, "failed:expired", null);
          patchSalary(user, s.agentId, func(x) { { x with lastResult = "failed:expired"; updatedAt = now() } });
        };
        case (#Err(_)) {
          setPayoutStatus(user, key, "failed:ledger", null);
          stallSalary(user, s.agentId, "ledger");
        };
      };
    } catch (_e) {
      // Call trapped — outcome UNKNOWN. Leave the payout `pending`; the next
      // scan retries with the same memo/created_at_time (exactly-once via
      // ledger dedup). Never mark failed here: it may have landed.
      patchSalary(user, s.agentId, func(x) { { x with lastResult = "retrying"; updatedAt = now() } });
    };
  };

  /// Process one due salary. Re-validates everything from current state (the
  /// caller's snapshot may be stale after earlier awaits in the same scan).
  func processDue(user : Principal, agentId : Text) : async () {
    let s0 = switch (tOps.get(salariesOf(user), agentId)) { case (?s) s; case null { return } };
    if (not s0.active or isPayrollPaused(user) or s0.nextRunAt > now()) { return };
    let scheduledAt = s0.nextRunAt;
    let key = agentId # "#" # Int.toText(scheduledAt);
    if (hasPayout(user, key)) {
      // Already handled (e.g. runPayrollNow raced the timer) — just advance.
      patchSalary(user, agentId, func(x) { { x with nextRunAt = now() + secsToNs(x.periodSecs); updatedAt = now() } });
      return;
    };
    let sub = switch (agentSubOf(user, agentId)) {
      case (?b) b;
      case null {
        patchSalary(user, agentId, func(x) { { x with nextRunAt = now() + secsToNs(x.periodSecs); updatedAt = now() } });
        stallSalary(user, agentId, "wallet-missing");
        return;
      };
    };
    var amount = s0.amount;
    if (s0.mode == #refill) {
      let ledger : LedgerActor = actor (Principal.toText(s0.ledger));
      let bal = try { await ledger.icrc1_balance_of({ owner = user; subaccount = ?sub }) } catch (_e) {
        patchSalary(user, agentId, func(x) { { x with lastResult = "retrying:balance"; updatedAt = now() } });
        return;
      };
      // RE-READ after the await — active/paused/amount may have changed mid-flight.
      let s1 = switch (tOps.get(salariesOf(user), agentId)) { case (?s) s; case null { return } };
      if (not s1.active or isPayrollPaused(user) or s1.nextRunAt != scheduledAt) { return };
      if (bal >= s1.lowWatermark) {
        patchSalary(user, agentId, func(x) { { x with nextRunAt = now() + secsToNs(x.periodSecs); lastResult = "skip:funded"; stalledSince = null; updatedAt = now() } });
        return;
      };
      amount := s1.amount;
    };
    // Reentrancy guard + crash-safe intent: advance nextRunAt and log a
    // `pending` payout BEFORE the ledger await. Catch-up policy: at most one
    // period per scan (nextRunAt = now + period, not += period).
    patchSalary(user, agentId, func(x) { { x with nextRunAt = now() + secsToNs(x.periodSecs); lastResult = "running"; updatedAt = now() } });
    appendPayout(user, { key; agentId; token = s0.token; amount; scheduledAt; status = "pending"; blockIndex = null; ts = now() });
    let sNow = switch (tOps.get(salariesOf(user), agentId)) { case (?x) x; case null s0 };
    await executeTransfer(user, sNow, key, scheduledAt, amount, sub);
  };

  func scanPayroll() : async () {
    // Snapshot due pairs; processDue re-validates each against live state.
    let due = Buffer.Buffer<(Principal, Text)>(8);
    for ((user, smap) in pOps.entries(salaries)) {
      if (not isPayrollPaused(user)) {
        for ((aid, s) in tOps.entries(smap)) {
          if (s.active and s.nextRunAt <= now()) { due.add((user, aid)) };
        };
      };
    };
    for ((user, aid) in due.vals()) {
      try { await processDue(user, aid) } catch (_e) {};
    };
    // Retry or expire stale `pending` payouts (left by trapped ledger calls).
    let stale = Buffer.Buffer<(Principal, Payout)>(4);
    for ((user, arr) in pOps.entries(payoutLog)) {
      if (not isPayrollPaused(user)) {
        for (po in arr.vals()) {
          if (po.status == "pending" and now() - po.ts > PENDING_RETRY_MIN_AGE_NS) { stale.add((user, po)) };
        };
      };
    };
    for ((user, po) in stale.vals()) {
      if (now() - po.scheduledAt > PENDING_RETRY_MAX_NS) {
        setPayoutStatus(user, po.key, "failed:expired", null);
      } else {
        switch (tOps.get(salariesOf(user), po.agentId), agentSubOf(user, po.agentId)) {
          case (?s, ?sub) { try { await executeTransfer(user, s, po.key, po.scheduledAt, po.amount, sub) } catch (_e) {} };
          case _ { setPayoutStatus(user, po.key, "failed:orphaned", null) };
        };
      };
    };
  };

  // Idempotent arming: cancel-then-set, TimerId held in a FLEXIBLE var (dies with
  // its timer on upgrade — a stale stable flag could otherwise read armed-true
  // while the timer is dead). postupgrade is the mandatory re-arm point.
  var payrollTimerId : ?Timer.TimerId = null;
  func armPayrollTimer<system>() {
    switch (payrollTimerId) { case (?id) { Timer.cancelTimer(id) }; case null {} };
    payrollTimerId := ?Timer.recurringTimer<system>(#seconds PAYROLL_SCAN_SECS, scanPayroll);
  };
  // Fresh install: arm at init. Upgrades: postupgrade (init does not re-run).
  armPayrollTimer<system>();
  system func postupgrade() { armPayrollTimer<system>() };

  // ── Payroll public API (caller-keyed, like everything else here) ───────────
  public shared (msg) func putSalary(
    agentId : Text, ledgerId : Principal, token : Text, amount : Nat, fee : Nat,
    lowWatermark : Nat, periodSecs : Nat, mode : SalaryMode, active : Bool,
  ) : async () {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    if (amount == 0) { throw Error.reject("amount must be positive") };
    if (periodSecs < 60) { throw Error.reject("period too short (min 60s)") };
    let prev = tOps.get(salariesOf(caller), agentId);
    // Keep the schedule phase across edits unless the period changed.
    let nextRunAt = switch (prev) {
      case (?p) { if (p.periodSecs == periodSecs) { p.nextRunAt } else { now() + secsToNs(periodSecs) } };
      case null { now() + secsToNs(periodSecs) };
    };
    let s : Salary = {
      agentId; ledger = ledgerId; token; amount; fee; lowWatermark; periodSecs;
      nextRunAt; mode; active; stalledSince = null;
      lastResult = switch (prev) { case (?p) p.lastResult; case null "" };
      updatedAt = now();
    };
    salaries := pOps.put(salaries, caller, tOps.put(salariesOf(caller), agentId, s));
    armPayrollTimer<system>();
  };

  public shared query (msg) func listSalaries() : async [Salary] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    Iter.toArray(tOps.vals(salariesOf(msg.caller)));
  };

  public shared (msg) func deleteSalary(agentId : Text) : async Bool {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    let m = salariesOf(caller);
    switch (tOps.get(m, agentId)) {
      case null { false };
      case (?_) { salaries := pOps.put(salaries, caller, tOps.delete(m, agentId)); true };
    };
  };

  /// Per-user payroll kill switch (independent of setAllSpendPaused).
  public shared (msg) func setPayrollPaused(paused : Bool) : async () {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    payrollPausedMap := pOps.put(payrollPausedMap, caller, paused);
    if (not paused) { armPayrollTimer<system>() };
  };

  public shared query (msg) func payrollPaused() : async Bool {
    if (Principal.isAnonymous(msg.caller)) { return false };
    isPayrollPaused(msg.caller);
  };

  public shared query (msg) func listPayouts() : async [Payout] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    payoutsOf(msg.caller);
  };

  /// Manual "pay now" (smoke tests + catch-up). Respects active + pause switches.
  public shared (msg) func runPayrollNow(agentId : Text) : async Text {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    switch (tOps.get(salariesOf(caller), agentId)) {
      case null { "no-salary" };
      case (?s) {
        if (not s.active) { return "inactive" };
        if (isPayrollPaused(caller)) { return "paused" };
        patchSalary(caller, agentId, func(x) { { x with nextRunAt = now(); updatedAt = now() } });
        await processDue(caller, agentId);
        switch (tOps.get(salariesOf(caller), agentId)) { case (?x) x.lastResult; case null "deleted" };
      };
    };
  };

  // ── Installed ICP services ─────────────────────────────────────────────────
  public shared (msg) func putServiceFlag(serviceId : Text, enabled : Bool, configJson : Text) : async () {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    let fs = flagsOf(caller);
    let prevEnabledAt = switch (tOps.get(fs, serviceId)) { case (?f) f.enabledAt; case null 0 };
    let enabledAt = if (enabled and prevEnabledAt == 0) { now() } else { prevEnabledAt };
    let f : ServiceFlag = { serviceId; enabled; configJson; enabledAt; updatedAt = now() };
    serviceFlags := pOps.put(serviceFlags, caller, tOps.put(fs, serviceId, f));
  };

  public shared query (msg) func getServiceFlag(serviceId : Text) : async ?ServiceFlag {
    if (Principal.isAnonymous(msg.caller)) { return null };
    tOps.get(flagsOf(msg.caller), serviceId);
  };

  public shared query (msg) func listServiceFlags() : async [ServiceFlag] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    let out = Buffer.Buffer<ServiceFlag>(8);
    for ((_, f) in tOps.entries(flagsOf(msg.caller))) { out.add(f) };
    Buffer.toArray(out);
  };

  // ── Published sites (write API; per-caller — you write only your namespace) ─
  public shared (msg) func putSiteFile(project : Text, path : Text, contentType : Text, body : Blob) : async PutFileResult {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in with Internet Identity") };
    if (not validProject(project)) { return #err("bad project name") };
    if (body.size() > MAX_SITE_FILE_BYTES) { return #err("file exceeds 2 MiB limit") };
    let rel = switch (normSitePath(path)) { case (?r) r; case null { return #err("bad path") } };
    let key = project # "/" # rel;
    let files = sitesOf(caller);
    let prevSize = switch (tOps.get(files, key)) { case (?f) f.body.size(); case null 0 };
    let newUsed = subSat(siteUsageOf(caller), prevSize) + body.size();
    if (newUsed > MAX_SITE_USER_BYTES) { return #err("site storage quota exceeded") };
    let f : SiteFile = { contentType = contentType; body = body; updatedAt = now() };
    siteFiles := pOps.put(siteFiles, caller, tOps.put(files, key, f));
    siteUsage := pOps.put(siteUsage, caller, newUsed);
    #ok({ bytes = body.size() });
  };

  /// Remove all files under a project (call before re-publishing to drop stale files).
  public shared (msg) func deleteSite(project : Text) : async Nat {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    let files = sitesOf(caller);
    let prefix = project # "/";
    var next = files; var freed : Nat = 0; var removed : Nat = 0;
    for ((k, f) in tOps.entries(files)) {
      if (Text.startsWith(k, #text prefix)) { next := tOps.delete(next, k); freed += f.body.size(); removed += 1 };
    };
    siteFiles := pOps.put(siteFiles, caller, next);
    siteUsage := pOps.put(siteUsage, caller, subSat(siteUsageOf(caller), freed));
    removed;
  };

  public shared query (msg) func listMySites() : async [SiteSummary] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    var agg : OrderedMap.Map<Text, SiteSummary> = tOps.empty<SiteSummary>();
    for ((k, f) in tOps.entries(sitesOf(msg.caller))) {
      let proj = switch (Text.split(k, #char '/').next()) { case (?p) p; case null k };
      let prev = switch (tOps.get(agg, proj)) { case (?s) s; case null { { project = proj; fileCount = 0; totalBytes = 0; updatedAt = 0 } } };
      agg := tOps.put(agg, proj, {
        project = proj; fileCount = prev.fileCount + 1;
        totalBytes = prev.totalBytes + f.body.size(); updatedAt = Int.max(prev.updatedAt, f.updatedAt);
      });
    };
    Iter.toArray(tOps.vals(agg));
  };

  public shared query (msg) func mySiteBytes() : async Nat {
    if (Principal.isAnonymous(msg.caller)) { return 0 };
    siteUsageOf(msg.caller);
  };

  // ── Public serving — GET /<principalText>/<project>/<path...> ───────────────
  // Reads ONLY siteFiles. Everything else in this canister is unreachable here.
  func siteLookup(url : Text) : ?SiteFile {
    var path = url;
    switch (Text.split(path, #char '?').next()) { case (?p) path := p; case null {} };
    path := Text.trimStart(path, #char '/');
    let parts = Iter.toArray(Text.split(path, #char '/'));
    if (parts.size() < 2) { return null };
    let owner = Principal.fromText(parts[0]);
    let buf = Buffer.Buffer<Text>(parts.size());
    var i = 1;
    while (i < parts.size()) { if (parts[i].size() > 0) { buf.add(parts[i]) }; i += 1 };
    if (buf.size() == 0) { return null };
    var key = Text.join("/", buf.vals());
    if (buf.size() == 1) { key := key # "/index.html" };       // /<p>/<project> → index.html
    if (Text.endsWith(key, #text "/")) { key := key # "index.html" };
    tOps.get(sitesOf(owner), key);
  };

  func serveSite(url : Text) : HttpResponse {
    switch (siteLookup(url)) {
      case (?f) {
        {
          status_code = 200;
          headers = [("Content-Type", f.contentType), ("Cache-Control", "public, max-age=60"),
                     ("Access-Control-Allow-Origin", "*")];
          body = f.body; streaming_strategy = null; upgrade = null;
        };
      };
      case null {
        { status_code = 404; headers = [("Content-Type", "text/plain")];
          body = Text.encodeUtf8("Not found"); streaming_strategy = null; upgrade = null };
      };
    };
  };

  // Upgrade GETs to an update call so we don't need asset certification (MVP).
  public query func http_request(_req : HttpRequest) : async HttpResponse {
    { status_code = 200; headers = []; body = ""; streaming_strategy = null; upgrade = ?true };
  };
  public func http_request_update(req : HttpRequest) : async HttpResponse {
    serveSite(req.url);
  };

  // ── Diagnostics ────────────────────────────────────────────────────────────
  public query func cycle_balance() : async Nat { Cycles.balance() };
}
