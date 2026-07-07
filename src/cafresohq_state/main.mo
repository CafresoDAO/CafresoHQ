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
//   Sprint-4 exception: the WAKE timer makes an HMAC-signed HTTPS outcall to the
//   fleet gateway carrying only {principal, schedule ids} — and only when the
//   plan admin has enabled wake config (ships dark: off by default).
//
// Storage uses mo:base/OrderedMap held in `stable` vars. NOTE: this scaffold
// keeps data on the heap; before scaling past a few GB of aggregate vault,
// migrate the vault chunk store to mo:stable-structures (stable memory) per the
// design doc §5. `system func postupgrade` exists ONLY to re-arm the payroll
// and wake timers — timers never survive an upgrade.
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
import Float "mo:base/Float";
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
    // SECURITY: "receipt" is reserved — /<principal>/receipt/<id> is the work-
    // receipt verify URL, intercepted before siteLookup. A user project with
    // that name could otherwise serve attacker HTML at the verify-URL shape.
    // (deleteSite still accepts it, so any legacy project can be cleaned up.)
    if (p == "receipt") { return false };
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
    // objId is embedded raw in chunkKey (objId # "#" # ix); a '#' inside it
    // would collide two objects' chunk namespaces.
    if (Text.contains(objId, #char '#')) { return #quota("objId may not contain '#'") };
    let metas = metasOf(caller);
    let prev = tOps.get(metas, objId);
    let curVer = switch (prev) { case (?m) m.version; case null 0 };
    if (expectVersion != curVer) { return #conflict({ current = curVer }) };
    // Cap chunkCount so a bogus meta can't (a) make deleteVault's loop exceed
    // the instruction limit and trap the object into un-deletability, or (b)
    // claim more chunks than the quota could ever hold. Keep totalSize
    // consistent with the chunk count.
    let u0 = usageOf(caller);
    if (chunkCount > u0.quotaBytes / MAX_CHUNK_BYTES + 1) { return #quota("chunkCount too large") };
    if (totalSize > chunkCount * MAX_CHUNK_BYTES) { return #quota("totalSize exceeds chunk capacity") };
    // Shrinking an existing object (new chunkCount < old) orphans the tail
    // chunks — purge them here so their bytes don't leak from quota forever.
    switch (prev) {
      case (?old) {
        if (old.chunkCount > chunkCount) {
          var chunks = chunksOf(caller);
          var freed : Nat = 0;
          var i : Nat = chunkCount;
          while (i < old.chunkCount) {
            let key = chunkKey(objId, i);
            switch (tOps.get(chunks, key)) { case (?b) { freed += b.size(); chunks := tOps.delete(chunks, key) }; case null {} };
            i += 1;
          };
          vaultChunks := pOps.put(vaultChunks, caller, chunks);
          setUsage(caller, { u0 with vaultBytes = subSat(u0.vaultBytes, freed) });
        };
      };
      case null {};
    };
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
    // Must reference the in-progress meta version (defends against stale
    // writers) AND stay within the declared chunk count — a chunk written at
    // ix >= chunkCount would be orphaned (deleteVault only reclaims [0,count)).
    switch (tOps.get(metasOf(caller), objId)) {
      case null { return #conflict({ current = 0 }) };
      case (?m) {
        if (m.version != version) { return #conflict({ current = m.version }) };
        if (ix >= m.chunkCount) { return #quota("chunk index out of range") };
      };
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
      // Only a canister CONTROLLER may claim admin — otherwise any principal
      // could front-run the deployer's first call between install and setup and
      // permanently seize admin (then mint plan tokens / redirect the wake outcall).
      case null { if (not Principal.isController(caller)) { throw Error.reject("only a controller may claim plan admin") }; planAdmin := ?caller };
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
        // Roll the window if it has fully elapsed. windowSecs == 0 is the
        // documented "per-transaction cap only" mode: it must roll EVERY call
        // (spent0 resets to 0), gating on `amount > spendCap` alone. Previously
        // the `> 0` guard made windowSpent accumulate forever, silently turning
        // a per-tx cap into a lifetime cap that permanently blocked the agent.
        let nowSecs = now() / 1_000_000_000;
        let startSecs = w.windowResetAt / 1_000_000_000;
        let rolled = w.windowSecs == 0 or nowSecs >= startSecs + w.windowSecs;
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

  // Allowlist of the app's supported ICRC ledgers (ICP, ckUNI, sGLDT, $nanas,
  // ckUSDT) — mirrors frontend/src/lib/api/icrc1.js TOKENS. putSalary rejects
  // any other ledger so the payroll timer never awaits an unknown canister.
  let KNOWN_LEDGERS : [Text] = [
    "ryjl3-tyaaa-aaaaa-aaaba-cai",
    "ilzky-ayaaa-aaaar-qahha-cai",
    "i2s4q-syaaa-aaaan-qz4sq-cai",
    "mwen2-oqaaa-aaaam-adaca-cai",
    "cngnf-gddge-nq2mj-vjyfl-v76et-6c2pt-xg3n3-jzihw-d3iyp-ughtf-3ae",
  ];
  func isKnownLedger(p : Principal) : Bool {
    let t = Principal.toText(p);
    for (k in KNOWN_LEDGERS.vals()) { if (k == t) { return true } };
    false;
  };

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

  // Idempotent arming: a NO-OP when already armed. The TimerId is held in a
  // FLEXIBLE var (dies with its timer on upgrade — a stale stable flag could
  // otherwise read armed-true while the timer is dead), so it is non-null iff a
  // live timer exists for this actor instance. postupgrade is the mandatory
  // re-arm point. It must NOT cancel-then-recreate: a recurringTimer first fires
  // a full period AFTER creation, so re-arming from the user-facing putSalary
  // path (called per save) would reset the countdown and, if hit every <period,
  // starve scanPayroll for ALL users (cross-tenant DoS).
  var payrollTimerId : ?Timer.TimerId = null;
  // One tick drives BOTH money loops: user payroll and search-worker payout
  // sweeps (defined in the search-network section below). A second recurring
  // timer would double the idle cycle burn for no scheduling benefit.
  func payrollTick() : async () {
    await scanPayroll();
    await scanWorkerPayouts();
  };
  func armPayrollTimer<system>() {
    switch (payrollTimerId) { case (?_) { return }; case null {} };
    payrollTimerId := ?Timer.recurringTimer<system>(#seconds PAYROLL_SCAN_SECS, payrollTick);
  };
  // Fresh install: armed at init by the call at the BOTTOM of this actor —
  // payrollTick reaches into the search-network payout section defined below,
  // so an eager call here would hit M0016 (use before definition). Upgrades:
  // postupgrade (runs after all definitions; init does not re-run). Re-arms
  // BOTH recurring timers; timers never survive an upgrade.
  system func postupgrade() { armPayrollTimer<system>(); armWakeTimer<system>() };

  // ── Payroll public API (caller-keyed, like everything else here) ───────────
  public shared (msg) func putSalary(
    agentId : Text, ledgerId : Principal, token : Text, amount : Nat, fee : Nat,
    lowWatermark : Nat, periodSecs : Nat, mode : SalaryMode, active : Bool,
  ) : async () {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    if (amount == 0) { throw Error.reject("amount must be positive") };
    if (periodSecs < 60) { throw Error.reject("period too short (min 60s)") };
    // Only the app's known ICRC ledgers may be scheduled. Without this, the
    // shared scanPayroll timer would await an arbitrary user-supplied canister;
    // a malicious never-responding ledger stalls other tenants' payouts in the
    // sequential loop and holds call contexts open across upgrades.
    if (not isKnownLedger(ledgerId)) { throw Error.reject("unsupported ledger") };
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

  // ── Work receipts (Sprint 3: hash-anchored proof of agent work) ────────────
  // The browser hashes a deliverable (crypto.subtle) and anchors {tool, title,
  // argHash, contentSha256} here. Anyone with the verify URL can confirm the
  // hash + timestamp from an incognito window — no login, no JS. Best-effort:
  // anchoring never blocks a tool.
  public type WorkReceipt = {
    id : Nat;
    agentId : Text;
    agentName : Text;
    tool : Text;             // e.g. VAULT_NEW / EXPORT_PDF / PUBLISH_SITE
    title : Text;
    argHash : Text;          // sha256 hex of the tool arg (provenance)
    contentSha256 : Text;    // sha256 hex of the artifact bytes
    ts : Int;
  };
  stable var workReceipts : OrderedMap.Map<Principal, [WorkReceipt]> = pOps.empty<[WorkReceipt]>();
  stable var receiptSeq : OrderedMap.Map<Principal, Nat> = pOps.empty<Nat>();
  let MAX_RECEIPTS_KEPT : Nat = 1000;

  func receiptsOf(p : Principal) : [WorkReceipt] {
    switch (pOps.get(workReceipts, p)) { case (?a) a; case null [] };
  };

  /// Anchor one receipt; returns its per-user monotonic id (the verify URL path).
  public shared (msg) func putWorkReceipt(
    agentId : Text, agentName : Text, tool : Text, title : Text, argHash : Text, contentSha256 : Text,
  ) : async Nat {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    if (title.size() > 300 or agentName.size() > 100 or tool.size() > 40
        or argHash.size() > 80 or contentSha256.size() > 80 or agentId.size() > 100) {
      throw Error.reject("receipt field too long");
    };
    let id = switch (pOps.get(receiptSeq, caller)) { case (?n) n + 1; case null 1 };
    receiptSeq := pOps.put(receiptSeq, caller, id);
    let r : WorkReceipt = { id; agentId; agentName; tool; title; argHash; contentSha256; ts = now() };
    let buf = Buffer.fromArray<WorkReceipt>(receiptsOf(caller));
    buf.add(r);
    while (buf.size() > MAX_RECEIPTS_KEPT) { ignore buf.remove(0) };
    workReceipts := pOps.put(workReceipts, caller, Buffer.toArray(buf));
    id;
  };

  public shared query (msg) func listWorkReceipts() : async [WorkReceipt] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    receiptsOf(msg.caller);
  };

  // Receipt fields are user text going into HTML — escape or the verify page is an XSS.
  func escapeHtml(t : Text) : Text {
    var out = "";
    for (c in t.chars()) {
      out #= switch (c) {
        case ('<') "&lt;"; case ('>') "&gt;"; case ('&') "&amp;";
        case ('\"') "&quot;"; case ('\'') "&#39;";
        case (_) Text.fromChar(c);
      };
    };
    out;
  };

  func receiptPage(ownerText : Text, r : WorkReceipt) : Text {
    let tsSecs = r.ts / 1_000_000_000;
    "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
    # "<title>CafresoHQ work receipt #" # Nat.toText(r.id) # "</title>"
    # "<style>body{background:#14121f;color:#e8e4d8;font-family:monospace;max-width:640px;margin:40px auto;padding:0 16px;line-height:1.7}"
    # "h1{font-size:16px;color:#7ee787;border-bottom:2px solid #3a3652;padding-bottom:8px}"
    # ".f{margin:6px 0}.k{color:#8b86a3;display:inline-block;min-width:130px}.v{word-break:break-all}"
    # "footer{margin-top:24px;color:#8b86a3;font-size:11px;border-top:1px dashed #3a3652;padding-top:8px}</style></head><body>"
    # "<h1>⛓ CAFRESOHQ WORK RECEIPT #" # Nat.toText(r.id) # "</h1>"
    # "<div class=\"f\"><span class=\"k\">agent</span><span class=\"v\">" # escapeHtml(r.agentName) # " (" # escapeHtml(r.agentId) # ")</span></div>"
    # "<div class=\"f\"><span class=\"k\">tool</span><span class=\"v\">" # escapeHtml(r.tool) # "</span></div>"
    # "<div class=\"f\"><span class=\"k\">work</span><span class=\"v\">" # escapeHtml(r.title) # "</span></div>"
    # "<div class=\"f\"><span class=\"k\">artifact sha256</span><span class=\"v\">" # escapeHtml(r.contentSha256) # "</span></div>"
    # "<div class=\"f\"><span class=\"k\">arg sha256</span><span class=\"v\">" # escapeHtml(r.argHash) # "</span></div>"
    # "<div class=\"f\"><span class=\"k\">anchored (unix)</span><span class=\"v\">" # Int.toText(tsSecs) # "</span></div>"
    # "<div class=\"f\"><span class=\"k\">owner principal</span><span class=\"v\">" # escapeHtml(ownerText) # "</span></div>"
    # "<footer>Anchored on the Internet Computer in the CafresoHQ state canister at the moment the work finished. "
    # "To verify: sha256 the artifact you were given and compare it to the hash above.</footer>"
    # "</body></html>";
  };

  /// GET /<principal>/receipt/<id> — MUST run before siteLookup (see validProject).
  // Non-trapping principal-text parser. Principal.fromText TRAPS on malformed
  // input (bad base32 / CRC-32), and http_request_update upgrades EVERY GET, so
  // a bot hitting /wp-admin/... would trap the update call (gateway 5xx + cycle
  // burn) instead of getting a clean 404. We validate first: strip dashes,
  // base32-decode (RFC-4648, lowercase a-z/2-7), then verify the leading 4-byte
  // big-endian CRC-32 over the body before handing safe bytes to fromBlob.
  func b32Val(c : Char) : ?Nat8 {
    let n = Char.toNat32(c);
    if (n >= 97 and n <= 122) { ?Nat8.fromNat(Nat32.toNat(n - 97)) }          // a-z → 0..25
    else if (n >= 50 and n <= 55) { ?Nat8.fromNat(Nat32.toNat(n - 50 + 26)) } // 2-7 → 26..31
    else { null };
  };
  func crc32(bytes : [Nat8]) : Nat32 {
    var crc : Nat32 = 0xFFFFFFFF;
    for (b in bytes.vals()) {
      crc := crc ^ Nat32.fromNat(Nat8.toNat(b));
      var k : Nat = 0;
      while (k < 8) {
        if (crc & 1 == 1) { crc := (crc >> 1) ^ 0xEDB88320 } else { crc := crc >> 1 };
        k += 1;
      };
    };
    crc ^ 0xFFFFFFFF;
  };
  func parsePrincipal(t : Text) : ?Principal {
    // Every real principal text carries a dash; bare no-dash junk is rejected
    // cheaply before the full decode.
    if (not Text.contains(t, #char '-')) { return null };
    var acc : Nat32 = 0;
    var bits : Nat32 = 0;
    let out = Buffer.Buffer<Nat8>(33);
    for (c in t.chars()) {
      if (c != '-') {
        switch (b32Val(c)) {
          case null { return null };
          case (?v) {
            acc := (acc << 5) | Nat32.fromNat(Nat8.toNat(v));
            bits += 5;
            if (bits >= 8) {
              bits -= 8;
              out.add(Nat8.fromNat(Nat32.toNat((acc >> bits) & 0xFF)));
            };
          };
        };
      };
    };
    let decoded = Buffer.toArray(out);
    if (decoded.size() < 4 or decoded.size() > 33) { return null };  // 4-byte CRC + ≤29-byte body
    let body = Array.tabulate<Nat8>(decoded.size() - 4 : Nat, func(i) { decoded[i + 4] });
    let got : Nat32 =
      (Nat32.fromNat(Nat8.toNat(decoded[0])) << 24) |
      (Nat32.fromNat(Nat8.toNat(decoded[1])) << 16) |
      (Nat32.fromNat(Nat8.toNat(decoded[2])) << 8) |
       Nat32.fromNat(Nat8.toNat(decoded[3]));
    if (crc32(body) != got) { return null };
    ?Principal.fromBlob(Blob.fromArray(body));
  };

  func receiptLookup(url : Text) : ?HttpResponse {
    var path = url;
    switch (Text.split(path, #char '?').next()) { case (?p) path := p; case null {} };
    path := Text.trimStart(path, #char '/');
    let parts = Iter.toArray(Text.split(path, #char '/'));
    if (parts.size() < 3 or parts[1] != "receipt") { return null };
    let notFound : HttpResponse = {
      status_code = 404; headers = [("Content-Type", "text/plain")];
      body = Text.encodeUtf8("Receipt not found"); streaming_strategy = null; upgrade = null;
    };
    let owner = switch (parsePrincipal(parts[0])) { case (?p) p; case null { return ?notFound } };
    let id = switch (textToInt(parts[2])) { case (?n) Int.abs(n); case null { return ?notFound } };
    switch (Array.find<WorkReceipt>(receiptsOf(owner), func(r) { r.id == id })) {
      case null { ?notFound };
      case (?r) {
        ?{
          status_code = 200;
          headers = [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "public, max-age=300"),
                     ("X-Content-Type-Options", "nosniff")];
          body = Text.encodeUtf8(receiptPage(parts[0], r)); streaming_strategy = null; upgrade = null;
        };
      };
    };
  };

  // ── Public serving — GET /<principalText>/<project>/<path...> ───────────────
  // Reads ONLY siteFiles. Everything else in this canister is unreachable here.
  func siteLookup(url : Text) : ?SiteFile {
    var path = url;
    switch (Text.split(path, #char '?').next()) { case (?p) path := p; case null {} };
    path := Text.trimStart(path, #char '/');
    let parts = Iter.toArray(Text.split(path, #char '/'));
    if (parts.size() < 2) { return null };
    let owner = switch (parsePrincipal(parts[0])) { case (?p) p; case null { return null } };
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

  // ── Ai Cafreso Search — public library ─────────────────────────────────────
  // Opt-in, append-only public library of answered search queries. Each entry
  // is published EXPLICITLY by its signed-in owner from the search UI — a
  // query is NEVER stored here as a side effect of searching. Reads are public
  // via http_request (/library/*); writes are caller-gated with hard size and
  // per-owner count caps so no principal can flood the heap. The library is a
  // cache by design: the first published answer for a normalized query wins,
  // and library_find lets the search UI answer repeat queries without ever
  // hitting the web. Public JSON never includes the owner principal.
  public type LibrarySource = { title : Text; url : Text };
  // Provenance travels with every entry: when the question was first asked,
  // when it was answered, which model wrote the answer, which search engine
  // found the sources, and (for network-fulfilled entries) which worker.
  // The worker principal IS public — it's the attribution that payouts and
  // reputation hang off — unlike the owner principal, which never is.
  public type LibraryProvenance = {
    model : Text;               // "" when no model wrote an answer
    searchEngine : Text;        // "brave" | "" …
    worker : ?Principal;        // set ONLY by the network fulfill path
    firstSearchedAt : Int;      // job submit time for network entries; = answeredAt otherwise
    answeredAt : Int;
  };
  public type LibraryEntry = {
    id : Text;
    owner : Principal;
    q : Text;
    answer : Text;              // quick-answer summary; may be empty
    sources : [LibrarySource];
    graphJson : Text;           // graph-viewer snapshot, served raw at /library/<id>/graph.json
    ts : Int;
    prov : LibraryProvenance;
  };
  public type LibrarySummary = { id : Text; q : Text; ts : Int; sourceCount : Nat };
  public type LibraryPutResult = { #ok : { id : Text; existing : Bool }; #err : Text };

  stable var libraryEntries : OrderedMap.Map<Text, LibraryEntry> = tOps.empty<LibraryEntry>();
  stable var libraryByQuery : OrderedMap.Map<Text, Text> = tOps.empty<Text>(); // normalized query → id
  stable var libraryCounts : OrderedMap.Map<Principal, Nat> = pOps.empty<Nat>();
  stable var librarySeq : Nat = 0;

  let LIB_MAX_QUERY : Nat = 400;
  let LIB_MAX_ANSWER : Nat = 4_000;
  let LIB_MAX_SOURCES : Nat = 10;
  let LIB_MAX_SOURCE_TEXT : Nat = 600;
  let LIB_MAX_GRAPH : Nat = 200_000;
  let LIB_MAX_PROV_TEXT : Nat = 80;
  let LIB_MAX_PER_OWNER : Nat = 200;
  let LIB_INDEX_LIMIT : Nat = 500;

  // ASCII-lowercase + collapse whitespace: the dedup key. Unicode case folding
  // is deliberately out of scope — a miss just means one extra library entry.
  func libNorm(q : Text) : Text {
    let lowered = Text.map(q, func(c : Char) : Char {
      if (c >= 'A' and c <= 'Z') { Char.fromNat32(Char.toNat32(c) + 32) } else { c };
    });
    Text.join(" ", Iter.filter<Text>(
      Text.split(lowered, #char ' '), func(w : Text) : Bool { w.size() > 0 }));
  };

  // Zero-padded ids keep Text.compare order == insertion order, so the newest
  // entries are always at the end of the ordered map.
  func libId(n : Nat) : Text {
    var s = Nat.toText(n);
    while (s.size() < 10) { s := "0" # s };
    "q" # s;
  };

  // Shared validation for both publish paths (user opt-in + network fulfill).
  func libValidate(q : Text, answer : Text, sources : [LibrarySource], graphJson : Text) : ?Text {
    if (libNorm(q).size() == 0 or q.size() > LIB_MAX_QUERY) { return ?"bad query" };
    if (answer.size() > LIB_MAX_ANSWER) { return ?"answer too long" };
    if (sources.size() > LIB_MAX_SOURCES) { return ?"too many sources" };
    for (s in sources.vals()) {
      if (s.title.size() > LIB_MAX_SOURCE_TEXT or s.url.size() > LIB_MAX_SOURCE_TEXT) {
        return ?"source too long";
      };
    };
    if (graphJson.size() > LIB_MAX_GRAPH) { return ?"graph too large" };
    null;
  };

  func libInsert(owner : Principal, q : Text, answer : Text, sources : [LibrarySource],
                 graphJson : Text, prov : LibraryProvenance) : Text {
    librarySeq += 1;
    let id = libId(librarySeq);
    libraryEntries := tOps.put(libraryEntries, id, {
      id; owner; q; answer; sources; graphJson; ts = now(); prov;
    });
    libraryByQuery := tOps.put(libraryByQuery, libNorm(q), id);
    id;
  };

  public shared (msg) func library_put(
    q : Text, answer : Text, sources : [LibrarySource], graphJson : Text,
    model : Text, searchEngine : Text
  ) : async LibraryPutResult {
    if (Principal.isAnonymous(msg.caller)) { return #err("sign in to publish to the library") };
    if (model.size() > LIB_MAX_PROV_TEXT or searchEngine.size() > LIB_MAX_PROV_TEXT) { return #err("bad provenance") };
    switch (libValidate(q, answer, sources, graphJson)) { case (?e) { return #err(e) }; case null {} };
    switch (tOps.get(libraryByQuery, libNorm(q))) {
      case (?id) { return #ok({ id; existing = true }) };  // cache semantics: first answer wins
      case null {};
    };
    let count = switch (pOps.get(libraryCounts, msg.caller)) { case (?n) n; case null 0 };
    if (count >= LIB_MAX_PER_OWNER) { return #err("per-account library limit reached") };
    let id = libInsert(msg.caller, q, answer, sources, graphJson, {
      model; searchEngine; worker = null; firstSearchedAt = now(); answeredAt = now();
    });
    libraryCounts := pOps.put(libraryCounts, msg.caller, count + 1);
    #ok({ id; existing = false });
  };

  public query func library_find(q : Text) : async ?LibraryEntry {
    switch (tOps.get(libraryByQuery, libNorm(q))) {
      case (?id) tOps.get(libraryEntries, id);
      case null null;
    };
  };

  public query func library_get(id : Text) : async ?LibraryEntry {
    tOps.get(libraryEntries, id);
  };

  public query func library_count() : async Nat { tOps.size(libraryEntries) };

  // Newest-first summaries. offset/limit page through from the newest end.
  public query func library_list(offset : Nat, limit : Nat) : async [LibrarySummary] {
    let all = Buffer.Buffer<LibrarySummary>(tOps.size(libraryEntries));
    for ((_, e) in tOps.entries(libraryEntries)) {
      all.add({ id = e.id; q = e.q; ts = e.ts; sourceCount = e.sources.size() });
    };
    let n = all.size();
    let out = Buffer.Buffer<LibrarySummary>(limit);
    var i = 0;
    while (i < limit and offset + i < n) {
      out.add(all.get(n - 1 - (offset + i) : Nat));
      i += 1;
    };
    Buffer.toArray(out);
  };

  // Owner (or plan admin) can withdraw an entry — the abuse/report path.
  public shared (msg) func library_remove(id : Text) : async Bool {
    switch (tOps.get(libraryEntries, id)) {
      case null false;
      case (?e) {
        let isAdmin = switch (planAdmin) { case (?a) a == msg.caller; case null false };
        if (e.owner != msg.caller and not isAdmin) { return false };
        libraryEntries := tOps.delete(libraryEntries, id);
        libraryByQuery := tOps.delete(libraryByQuery, libNorm(e.q));
        switch (pOps.get(libraryCounts, e.owner)) {
          case (?n) { if (n > 0) { libraryCounts := pOps.put(libraryCounts, e.owner, n - 1 : Nat) } };
          case null {};
        };
        true;
      };
    };
  };

  // ── Library public JSON (http_request) ──────────────────────────────────
  func jsonEsc(t : Text) : Text {
    var out = "";
    for (c in t.chars()) {
      if (c == '\"') { out #= "\\\"" }
      else if (c == '\\') { out #= "\\\\" }
      else if (c == '\n') { out #= "\\n" }
      else if (c == '\r') { out #= "\\r" }
      else if (c == '\t') { out #= "\\t" }
      else if (Char.toNat32(c) < 32) { out #= " " }
      else { out #= Text.fromChar(c) };
    };
    out;
  };

  func libJsonHeaders() : [(Text, Text)] {
    [("Content-Type", "application/json; charset=utf-8"),
     ("Access-Control-Allow-Origin", "*"),
     ("Cache-Control", "public, max-age=60"),
     ("X-Content-Type-Options", "nosniff")];
  };

  func libJsonResponse(body : Text) : HttpResponse {
    { status_code = 200; headers = libJsonHeaders();
      body = Text.encodeUtf8(body); streaming_strategy = null; upgrade = null };
  };

  func libNotFound() : HttpResponse {
    { status_code = 404; headers = [("Content-Type", "text/plain")];
      body = Text.encodeUtf8("Not found"); streaming_strategy = null; upgrade = null };
  };

  func entryJson(e : LibraryEntry) : Text {
    // Owner principal intentionally omitted: publishing is opt-in, but the
    // public surface must not link queries to identities.
    var src = "";
    var first = true;
    for (s in e.sources.vals()) {
      if (not first) { src #= "," };
      first := false;
      src #= "{\"title\":\"" # jsonEsc(s.title) # "\",\"url\":\"" # jsonEsc(s.url) # "\"}";
    };
    let workerJson = switch (e.prov.worker) {
      case (?w) "\"" # Principal.toText(w) # "\"";
      case null "null";
    };
    "{\"id\":\"" # jsonEsc(e.id) # "\",\"query\":\"" # jsonEsc(e.q) #
    "\",\"answer\":\"" # jsonEsc(e.answer) # "\",\"sources\":[" # src #
    "],\"ts\":" # Int.toText(e.ts) #
    ",\"model\":\"" # jsonEsc(e.prov.model) # "\",\"engine\":\"" # jsonEsc(e.prov.searchEngine) #
    "\",\"worker\":" # workerJson #
    ",\"firstSearchedAt\":" # Int.toText(e.prov.firstSearchedAt) #
    ",\"answeredAt\":" # Int.toText(e.prov.answeredAt) #
    ",\"graphUrl\":\"/library/" # jsonEsc(e.id) # "/graph.json\"}";
  };

  // /library/index.json               → newest-first summaries (≤ LIB_INDEX_LIMIT)
  // /library/<id>.json                → full entry (answer + sources + graph URL)
  // /library/<id>/graph.json          → raw graph snapshot for graph-viewer.html?g=…
  // The "library" prefix can never collide with published sites: siteLookup
  // requires parts[0] to parse as a principal, which "library" cannot.
  func libraryLookup(url : Text) : ?HttpResponse {
    var path = url;
    switch (Text.split(path, #char '?').next()) { case (?p) path := p; case null {} };
    path := Text.trimStart(path, #char '/');
    let parts = Iter.toArray(Text.split(path, #char '/'));
    if (parts.size() == 0 or parts[0] != "library") { return null };
    if (parts.size() == 2 and parts[1] == "index.json") {
      var body = "";
      var first = true;
      var emitted = 0;
      // Ordered map iterates oldest→newest (zero-padded ids); collect then
      // emit from the tail for newest-first.
      let all = Buffer.Buffer<LibraryEntry>(tOps.size(libraryEntries));
      for ((_, e) in tOps.entries(libraryEntries)) { all.add(e) };
      var i = all.size();
      while (i > 0 and emitted < LIB_INDEX_LIMIT) {
        i -= 1;
        let e = all.get(i);
        if (not first) { body #= "," };
        first := false;
        body #= "{\"id\":\"" # jsonEsc(e.id) # "\",\"query\":\"" # jsonEsc(e.q) #
                "\",\"ts\":" # Int.toText(e.ts) # ",\"sources\":" # Nat.toText(e.sources.size()) # "}";
        emitted += 1;
      };
      return ?libJsonResponse("{\"count\":" # Nat.toText(tOps.size(libraryEntries)) # ",\"entries\":[" # body # "]}");
    };
    if (parts.size() == 2 and parts[1] == "graph.json") {
      return ?libJsonResponse(mergedLibraryGraph());
    };
    if (parts.size() == 3 and parts[2] == "graph.json") {
      return switch (tOps.get(libraryEntries, parts[1])) {
        case (?e) { if (e.graphJson.size() == 0) { ?libNotFound() } else { ?libJsonResponse(e.graphJson) } };
        case null ?libNotFound();
      };
    };
    if (parts.size() == 2) {
      switch (Text.stripEnd(parts[1], #text ".json")) {
        case (?id) {
          return switch (tOps.get(libraryEntries, id)) {
            case (?e) ?libJsonResponse(entryJson(e));
            case null ?libNotFound();
          };
        };
        case null {};
      };
    };
    ?libNotFound();  // reserve the whole /library/* namespace
  };

  // ── Merged "neural web" graph — GET /library/graph.json ────────────────────
  // ONE snapshot merging the newest ≤300 entries: a gold node per question, a
  // community-colored node per source DOMAIN deduped ACROSS entries — shared
  // domains cross-link questions, so the web literally densifies as the
  // library grows. Positions are baked (the public viewer ships without the
  // FA2 layout): questions sit on a golden-angle spiral; each domain sits at
  // the centroid of its linked questions, pushed outward — organic clustering
  // without a physics engine. Entry node keys are the entry ids so the
  // explore page can deep-link node → drawer.
  let LIB_MERGED_MAX : Nat = 300;
  let GRAPH_PALETTE : [Text] = ["#7DC9B0", "#C9B8E0", "#E8A9A9", "#F0C987",
                                "#9BC0E8", "#B8E09A", "#E0A47C", "#D89BE0"];
  func textHash(t : Text) : Nat {
    var h : Nat32 = 0;
    for (c in t.chars()) { h := h *% 31 +% Char.toNat32(c) };
    Nat32.toNat(h);
  };
  func urlDomain(url : Text) : Text {
    var rest = url;
    let ix = Text.split(url, #text "://");
    switch (ix.next()) { case (?_) {}; case null {} };
    switch (ix.next()) { case (?r) rest := r; case null {} };
    var host = switch (Text.split(rest, #char '/').next()) { case (?h) h; case null rest };
    host := switch (Text.split(host, #char '?').next()) { case (?h) h; case null host };
    switch (Text.stripStart(host, #text "www.")) { case (?h) h; case null host };
  };
  func f2(x : Float) : Text { Float.format(#fix 2, x) };

  func mergedLibraryGraph() : Text {
    // Newest LIB_MERGED_MAX entries (map iterates oldest-first).
    let allE = Buffer.Buffer<LibraryEntry>(tOps.size(libraryEntries));
    for ((_, e) in tOps.entries(libraryEntries)) { allE.add(e) };
    let total = allE.size();
    let takeN = if (total > LIB_MERGED_MAX) { LIB_MERGED_MAX } else { total };
    var nodes = "";
    var edges = "";
    var firstN = true;
    var firstE = true;
    // domain → (sumX, sumY, degree)
    var domAgg : OrderedMap.Map<Text, (Float, Float, Nat)> = tOps.empty<(Float, Float, Nat)>();
    var i = 0;
    while (i < takeN) {
      let e = allE.get(total - 1 - i : Nat);          // newest first ⇒ center of the spiral
      let fi = Float.fromInt(i);
      let ang = fi * 2.399963;                         // golden angle
      let r = 4.0 * Float.sqrt(fi + 1.0);
      let x = Float.cos(ang) * r;
      let y = Float.sin(ang) * r;
      let size = 6 + (if (e.sources.size() > 8) { 8 } else { e.sources.size() });
      if (not firstN) { nodes #= "," };
      firstN := false;
      nodes #= "{\"key\":\"" # jsonEsc(e.id) # "\",\"attributes\":{\"label\":\"" # jsonEsc(textTake(e.q, 70)) #
               "\",\"size\":" # Nat.toText(size) # ",\"x\":" # f2(x) # ",\"y\":" # f2(y) #
               ",\"color\":\"#F5D25D\",\"entryId\":\"" # jsonEsc(e.id) # "\"}}";
      // One edge per UNIQUE domain per entry — two sources on the same host
      // would otherwise emit duplicate edge keys, which graphology rejects.
      var entryDoms : OrderedMap.Map<Text, Bool> = tOps.empty<Bool>();
      for (s in e.sources.vals()) {
        let d = urlDomain(s.url);
        if (d.size() > 0 and tOps.get(entryDoms, d) == null) {
          entryDoms := tOps.put(entryDoms, d, true);
          let (sx, sy, n) = switch (tOps.get(domAgg, d)) { case (?a) a; case null (0.0, 0.0, 0) };
          domAgg := tOps.put(domAgg, d, (sx + x, sy + y, n + 1));
          if (not firstE) { edges #= "," };
          firstE := false;
          edges #= "{\"key\":\"e" # jsonEsc(e.id) # "_" # jsonEsc(d) #
                   "\",\"source\":\"" # jsonEsc(e.id) # "\",\"target\":\"d:" # jsonEsc(d) # "\",\"attributes\":{}}";
        };
      };
      i += 1;
    };
    for ((d, (sx, sy, n)) in tOps.entries(domAgg)) {
      let fn = Float.fromInt(n);
      // Centroid of linked questions, pushed 45% outward (+tiny hash jitter so
      // single-link domains around the same question don't stack).
      let jit = Float.fromInt(textHash(d) % 100) / 100.0 - 0.5;
      let x = (sx / fn) * 1.45 + jit;
      let y = (sy / fn) * 1.45 - jit;
      let size = 4 + (if (n > 12) { 12 } else { n });
      let color = GRAPH_PALETTE[textHash(d) % GRAPH_PALETTE.size()];
      if (not firstN) { nodes #= "," };
      firstN := false;
      nodes #= "{\"key\":\"d:" # jsonEsc(d) # "\",\"attributes\":{\"label\":\"" # jsonEsc(d) #
               "\",\"size\":" # Nat.toText(size) # ",\"x\":" # f2(x) # ",\"y\":" # f2(y) #
               ",\"color\":\"" # color # "\"}}";
    };
    "{\"graph\":{\"options\":{\"type\":\"mixed\",\"multi\":false,\"allowSelfLoops\":true}," #
    "\"attributes\":{},\"nodes\":[" # nodes # "],\"edges\":[" # edges # "]}," #
    "\"title\":\"The Cafreso Library\",\"ts\":" # Int.toText(now() / 1_000_000) # "}";
  };

  // ── Search network — job queue + worker registry + HMAC HTTP protocol ──────
  // The decentralized half of Ai Cafreso Search: anonymous visitors queue
  // queries over plain HTTP; community-run containers (admin-approved, each
  // bringing its own Brave key + local model) claim and fulfill them, earning
  // per-job payouts swept by the payroll timer under a planAdmin-signed
  // allowance. Python workers can't sign candid calls, so the worker protocol
  // is HMAC-SHA256 over plain HTTPS POSTs — the wake-outcall trust model in
  // reverse. Worker REQUEST bodies are line-oriented and percent-encoded
  // (Motoko has no JSON parser); responses are JSON like everything else.

  func pctDecode(t : Text) : ?Text {
    let bytes = Buffer.Buffer<Nat8>(t.size());
    let chars = Iter.toArray(t.chars());
    var i = 0;
    func hexVal(c : Char) : ?Nat32 {
      if (c >= '0' and c <= '9') { ?(Char.toNat32(c) - 48) }
      else if (c >= 'a' and c <= 'f') { ?(Char.toNat32(c) - 87) }
      else if (c >= 'A' and c <= 'F') { ?(Char.toNat32(c) - 55) }
      else { null };
    };
    while (i < chars.size()) {
      let c = chars[i];
      if (c == '%') {
        if (i + 2 >= chars.size()) { return null };
        switch (hexVal(chars[i + 1]), hexVal(chars[i + 2])) {
          case (?h, ?l) { bytes.add(Nat8.fromNat(Nat32.toNat(h * 16 + l))); i += 3 };
          case _ { return null };
        };
      } else if (c == '+') { bytes.add(32); i += 1 }              // query-string space
      else if (Char.toNat32(c) < 128) { bytes.add(Nat8.fromNat(Nat32.toNat(Char.toNat32(c)))); i += 1 }
      else {
        // Non-ASCII literal chars: encode back to UTF-8 bytes.
        for (b in Text.encodeUtf8(Text.fromChar(c)).vals()) { bytes.add(b) };
        i += 1;
      };
    };
    Text.decodeUtf8(Blob.fromArray(Buffer.toArray(bytes)));
  };

  func natFromText(t : Text) : ?Nat {
    var n : Nat = 0;
    var seen = false;
    for (c in t.chars()) {
      if (c < '0' or c > '9') { return null };
      n := n * 10 + (Nat32.toNat(Char.toNat32(c)) - 48);
      seen := true;
    };
    if (seen) { ?n } else { null };
  };

  // ── Worker registry ─────────────────────────────────────────────────────
  public type Worker = {
    principal : Principal;
    name : Text;
    status : Text;              // "pending" | "approved" | "suspended"
    payoutOwner : Principal;
    payoutSubHex : Text;        // "" = default subaccount
    registeredAt : Int;
    approvedAt : Int;
    lastSeen : Int;
    lastAuthMs : Int;           // replay guard: signed ts must strictly increase
    jobsDone : Nat;
    jobsFailed : Nat;
    accruedE8s : Nat;           // earned but not yet swept
    earnedE8s : Nat;            // lifetime paid out
    updatedAt : Int;
  };
  stable var workers : OrderedMap.Map<Principal, Worker> = pOps.empty<Worker>();
  // Secrets live in a separate map with NO query/getter — the only reads are
  // HMAC verification below. The browser generates the secret (the canister
  // must hold plaintext to verify HMACs, and this avoids a raw_rand round trip).
  stable var workerSecrets : OrderedMap.Map<Principal, Blob> = pOps.empty<Blob>();
  let MAX_WORKERS : Nat = 500;
  let WORKER_ACTIVE_WINDOW_NS : Int = 600_000_000_000;   // heartbeat within 10 min = active

  public shared (msg) func worker_register(name : Text, secretHex : Text, payoutSubHex : Text) : async Text {
    if (Principal.isAnonymous(msg.caller)) { throw Error.reject("sign in to register a worker") };
    if (name.size() == 0 or name.size() > 64) { throw Error.reject("name must be 1-64 chars") };
    let secret = switch (hexToBytes(secretHex)) {
      case (?b) { if (b.size() != 32) { throw Error.reject("secret must be 32 bytes hex") }; Blob.fromArray(b) };
      case null { throw Error.reject("secret must be hex") };
    };
    if (payoutSubHex != "") {
      switch (hexToBytes(payoutSubHex)) {
        case (?b) { if (b.size() != 32) { throw Error.reject("payout subaccount must be 32 bytes hex") } };
        case null { throw Error.reject("payout subaccount must be hex") };
      };
    };
    let existing = pOps.get(workers, msg.caller);
    if (existing == null and pOps.size(workers) >= MAX_WORKERS) { throw Error.reject("worker registry full") };
    // Re-register rotates the secret WITHOUT resetting an approved status —
    // rotating a credential must not cost a re-approval round.
    let w : Worker = switch (existing) {
      case (?prev) { { prev with name; payoutSubHex; updatedAt = now() } };
      case null {
        { principal = msg.caller; name; status = "pending"; payoutOwner = msg.caller;
          payoutSubHex; registeredAt = now(); approvedAt = 0; lastSeen = 0; lastAuthMs = 0;
          jobsDone = 0; jobsFailed = 0; accruedE8s = 0; earnedE8s = 0; updatedAt = now() };
      };
    };
    workers := pOps.put(workers, msg.caller, w);
    workerSecrets := pOps.put(workerSecrets, msg.caller, secret);
    w.status;
  };

  public shared query (msg) func worker_my_status() : async ?Worker {
    pOps.get(workers, msg.caller);
  };

  func isPlanAdminP(c : Principal) : Bool {
    switch (planAdmin) { case (?a) a == c; case null false };
  };

  public shared query (msg) func amPlanAdmin() : async Bool { isPlanAdminP(msg.caller) };

  public shared (msg) func worker_admin_set_status(p : Principal, status : Text) : async () {
    if (not isPlanAdminP(msg.caller)) { throw Error.reject("plan admin only") };
    if (status != "approved" and status != "suspended" and status != "pending") {
      throw Error.reject("bad status");
    };
    switch (pOps.get(workers, p)) {
      case null { throw Error.reject("no such worker") };
      case (?w) {
        let approvedAt = if (status == "approved" and w.approvedAt == 0) { now() } else { w.approvedAt };
        workers := pOps.put(workers, p, { w with status; approvedAt; updatedAt = now() });
      };
    };
  };

  public shared query (msg) func worker_admin_list() : async [Worker] {
    if (not isPlanAdminP(msg.caller)) { return [] };
    Iter.toArray(pOps.vals(workers));
  };

  func patchWorker(p : Principal, f : Worker -> Worker) {
    switch (pOps.get(workers, p)) {
      case (?w) { workers := pOps.put(workers, p, f(w)) };
      case null {};
    };
  };

  func activeWorkerCount() : Nat {
    var n = 0;
    for ((_, w) in pOps.entries(workers)) {
      if (w.status == "approved" and now() - w.lastSeen <= WORKER_ACTIVE_WINDOW_NS) { n += 1 };
    };
    n;
  };

  // ── Job queue ───────────────────────────────────────────────────────────
  public type SearchJob = {
    id : Text;                  // "j" + zero-padded seq (map order == age)
    q : Text;
    norm : Text;
    status : Text;              // "pending" | "claimed" | "done" | "failed" | "expired"
    submittedAt : Int;
    claimedBy : ?Principal;
    claimedAt : Int;
    attempts : Nat;
    libraryId : ?Text;
    error : Text;
  };
  stable var searchJobs : OrderedMap.Map<Text, SearchJob> = tOps.empty<SearchJob>();
  stable var jobsByNorm : OrderedMap.Map<Text, Text> = tOps.empty<Text>();   // LIVE jobs only
  stable var jobSeq : Nat = 0;
  stable var jobsAnsweredToday : Nat = 0;
  stable var jobDayStamp : Int = 0;
  stable var searchDailyBudget : Nat = 500;

  let MAX_PENDING_JOBS : Nat = 25;
  let JOB_PENDING_TTL_NS : Int = 900_000_000_000;     // 15 min unclaimed → expired
  let CLAIM_LEASE_NS : Int = 240_000_000_000;         // 4 min claimed → back to pending
  let MAX_JOB_ATTEMPTS : Nat = 3;
  let MAX_JOBS_KEPT : Nat = 500;
  // DAY_NS reused from the Night Shift wake section below (same 24h constant).

  func jobId(n : Nat) : Text {
    var s = Nat.toText(n);
    while (s.size() < 10) { s := "0" # s };
    "j" # s;
  };

  func bumpJobDay() {
    let day = now() / DAY_NS;
    if (day != jobDayStamp) { jobDayStamp := day; jobsAnsweredToday := 0 };
  };

  func putJob(j : SearchJob) { searchJobs := tOps.put(searchJobs, j.id, j) };

  // Lazy queue maintenance — no extra timer. Expire stale pendings, reclaim
  // broken leases, prune terminal history past the cap.
  func tendJobs() {
    bumpJobDay();
    let expired = Buffer.Buffer<SearchJob>(4);
    for ((_, j) in tOps.entries(searchJobs)) {
      if (j.status == "pending" and now() - j.submittedAt > JOB_PENDING_TTL_NS) { expired.add(j) }
      else if (j.status == "claimed" and now() - j.claimedAt > CLAIM_LEASE_NS) { expired.add(j) };
    };
    for (j in expired.vals()) {
      if (j.status == "pending") {
        putJob({ j with status = "expired" });
        jobsByNorm := tOps.delete(jobsByNorm, j.norm);
      } else {
        // Broken lease: give it back (or fail out at max attempts).
        if (j.attempts + 1 >= MAX_JOB_ATTEMPTS) {
          putJob({ j with status = "failed"; error = "workers timed out"; attempts = j.attempts + 1 });
          jobsByNorm := tOps.delete(jobsByNorm, j.norm);
        } else {
          putJob({ j with status = "pending"; claimedBy = null; attempts = j.attempts + 1 });
        };
      };
    };
    // Prune oldest TERMINAL jobs beyond the history cap (map iterates oldest-first).
    if (tOps.size(searchJobs) > MAX_JOBS_KEPT) {
      var excess : Nat = tOps.size(searchJobs) - MAX_JOBS_KEPT;
      let victims = Buffer.Buffer<Text>(excess);
      label prune for ((id, j) in tOps.entries(searchJobs)) {
        if (excess == 0) { break prune };
        if (j.status != "pending" and j.status != "claimed") { victims.add(id); excess -= 1 };
      };
      for (id in victims.vals()) { searchJobs := tOps.delete(searchJobs, id) };
    };
  };

  func livePendingCount() : Nat {
    var n = 0;
    for ((_, j) in tOps.entries(searchJobs)) { if (j.status == "pending") { n += 1 } };
    n;
  };

  public type SubmitOutcome = { #hit : Text; #queued : Text; #rejected : Text };
  func submitSearch(qRaw : Text) : SubmitOutcome {
    tendJobs();
    let q = qRaw;
    let norm = libNorm(q);
    if (norm.size() == 0 or q.size() > LIB_MAX_QUERY) { return #rejected("bad-query") };
    switch (tOps.get(libraryByQuery, norm)) { case (?id) { return #hit(id) }; case null {} };
    switch (tOps.get(jobsByNorm, norm)) { case (?jid) { return #queued(jid) }; case null {} };
    if (jobsAnsweredToday >= searchDailyBudget) { return #rejected("budget") };
    if (livePendingCount() >= MAX_PENDING_JOBS) { return #rejected("busy") };
    if (activeWorkerCount() == 0) { return #rejected("dark") };
    jobSeq += 1;
    let id = jobId(jobSeq);
    putJob({ id; q; norm; status = "pending"; submittedAt = now(); claimedBy = null;
             claimedAt = 0; attempts = 0; libraryId = null; error = "" });
    jobsByNorm := tOps.put(jobsByNorm, norm, id);
    #queued(id);
  };

  // ── Worker HMAC verification ────────────────────────────────────────────
  // Envelope (UTF-8 body, \n-separated): v1 / principal / ts-ms / nonce / op / …
  // Signature: hex(HMAC-SHA256(secret, raw body bytes)) in x-worker-signature.
  // Replay: the signed ts must STRICTLY exceed the worker's last accepted ts —
  // O(1) and airtight because a worker's loop serializes its calls.
  let WORKER_MAX_BODY : Nat = 262_144;
  let WORKER_MAX_SKEW_MS : Int = 300_000;

  func headerValue(req : HttpRequest, name : Text) : ?Text {
    for ((k, v) in req.headers.vals()) {
      if (libNorm(k) == name) { return ?v };
    };
    null;
  };

  func verifyWorker(req : HttpRequest) : ?(Principal, [Text]) {
    if (req.body.size() > WORKER_MAX_BODY) { return null };
    let bodyText = switch (Text.decodeUtf8(req.body)) { case (?t) t; case null { return null } };
    let lines = Iter.toArray(Text.split(bodyText, #char '\n'));
    if (lines.size() < 5 or lines[0] != "v1") { return null };
    let p = switch (parsePrincipal(lines[1])) { case (?x) x; case null { return null } };
    let w = switch (pOps.get(workers, p)) { case (?x) x; case null { return null } };
    let secret = switch (pOps.get(workerSecrets, p)) { case (?s) s; case null { return null } };
    let tsMs = switch (natFromText(lines[2])) { case (?n) n; case null { return null } };
    let nowMs = now() / 1_000_000;
    let tsInt : Int = tsMs;
    if (tsInt > nowMs + WORKER_MAX_SKEW_MS or tsInt < nowMs - WORKER_MAX_SKEW_MS) { return null };
    if (tsInt <= w.lastAuthMs) { return null };                    // replay
    let sig = switch (headerValue(req, "x-worker-signature")) { case (?s) libNorm(s); case null { return null } };
    let want = Sha256.toHex(Sha256.hmac(Blob.toArray(secret), Blob.toArray(req.body)));
    if (sig != want) { return null };
    // Op gate: heartbeat allowed while pending (lets operators see "connected"
    // before approval); everything else needs approved.
    if (lines[4] != "heartbeat" and w.status != "approved") { return null };
    if (w.status == "suspended") { return null };
    patchWorker(p, func(x) { { x with lastAuthMs = tsInt; lastSeen = now(); updatedAt = now() } });
    ?(p, lines);
  };

  func libJsonNoStore(body : Text) : HttpResponse {
    { status_code = 200;
      headers = [("Content-Type", "application/json; charset=utf-8"),
                 ("Access-Control-Allow-Origin", "*"),
                 ("Cache-Control", "no-store"),
                 ("X-Content-Type-Options", "nosniff")];
      body = Text.encodeUtf8(body); streaming_strategy = null; upgrade = null };
  };

  func workerDeny() : HttpResponse {
    { status_code = 403; headers = [("Content-Type", "application/json")];
      body = Text.encodeUtf8("{\"error\":\"unauthorized\"}"); streaming_strategy = null; upgrade = null };
  };

  // POST /worker/heartbeat | claim | fulfill | fail
  func workerRoute(req : HttpRequest) : ?HttpResponse {
    var path = req.url;
    switch (Text.split(path, #char '?').next()) { case (?p) path := p; case null {} };
    path := Text.trimStart(path, #char '/');
    let parts = Iter.toArray(Text.split(path, #char '/'));
    if (parts.size() == 0 or parts[0] != "worker") { return null };
    if (req.method != "POST") { return ?workerDeny() };
    let (p, lines) = switch (verifyWorker(req)) { case (?x) x; case null { return ?workerDeny() } };
    let op = lines[4];
    if (parts.size() != 2 or parts[1] != op) { return ?workerDeny() };  // path and envelope must agree
    tendJobs();

    if (op == "heartbeat") {
      let st = switch (pOps.get(workers, p)) { case (?w) w.status; case null "unknown" };
      return ?libJsonNoStore("{\"ok\":true,\"status\":\"" # st # "\"}");
    };

    if (op == "claim") {
      // Oldest pending job wins.
      label find for ((_, j) in tOps.entries(searchJobs)) {
        if (j.status == "pending") {
          putJob({ j with status = "claimed"; claimedBy = ?p; claimedAt = now() });
          return ?libJsonNoStore("{\"job\":{\"id\":\"" # jsonEsc(j.id) # "\",\"q\":\"" # jsonEsc(j.q) # "\"}}");
        };
      };
      return ?libJsonNoStore("{\"job\":null}");
    };

    if (op == "fail") {
      if (lines.size() < 7) { return ?workerDeny() };
      let jid = lines[5];
      let reason = switch (pctDecode(lines[6])) { case (?t) t; case null "" };
      switch (tOps.get(searchJobs, jid)) {
        case (?j) {
          if (j.status == "claimed" and j.claimedBy == ?p) {
            if (j.attempts + 1 >= MAX_JOB_ATTEMPTS) {
              putJob({ j with status = "failed"; claimedBy = null;
                       error = textTake(reason, 200); attempts = j.attempts + 1 });
              jobsByNorm := tOps.delete(jobsByNorm, j.norm);
            } else {
              putJob({ j with status = "pending"; claimedBy = null;
                       error = textTake(reason, 200); attempts = j.attempts + 1 });
            };
            patchWorker(p, func(x) { { x with jobsFailed = x.jobsFailed + 1 } });
          };
        };
        case null {};
      };
      return ?libJsonNoStore("{\"ok\":true}");
    };

    if (op == "fulfill") {
      // Lines: 5 jobId · 6 model · 7 engine · 8 answer · 9 N · 10..10+N-1 "title url" · last graphJson
      if (lines.size() < 11) { return ?workerDeny() };
      let jid = lines[5];
      let j = switch (tOps.get(searchJobs, jid)) { case (?x) x; case null { return ?workerDeny() } };
      if (j.status != "claimed" or j.claimedBy != ?p) {
        return ?libJsonNoStore("{\"ok\":false,\"error\":\"not-your-claim\"}");
      };
      let model = switch (pctDecode(lines[6])) { case (?t) textTake(t, LIB_MAX_PROV_TEXT); case null "" };
      let engine = switch (pctDecode(lines[7])) { case (?t) textTake(t, LIB_MAX_PROV_TEXT); case null "" };
      let answer = switch (pctDecode(lines[8])) { case (?t) t; case null { return ?workerDeny() } };
      let nSrc = switch (natFromText(lines[9])) { case (?n) n; case null { return ?workerDeny() } };
      if (nSrc > LIB_MAX_SOURCES or lines.size() < 11 + nSrc) { return ?workerDeny() };
      let srcs = Buffer.Buffer<LibrarySource>(nSrc);
      var i = 0;
      while (i < nSrc) {
        let sl = Iter.toArray(Text.split(lines[10 + i], #char ' '));
        if (sl.size() != 2) { return ?workerDeny() };
        switch (pctDecode(sl[0]), pctDecode(sl[1])) {
          case (?title, ?url) { srcs.add({ title; url }) };
          case _ { return ?workerDeny() };
        };
        i += 1;
      };
      let graphJson = switch (pctDecode(lines[10 + nSrc])) { case (?t) t; case null { return ?workerDeny() } };
      let sources = Buffer.toArray(srcs);
      switch (libValidate(j.q, answer, sources, graphJson)) {
        case (?e) { return ?libJsonNoStore("{\"ok\":false,\"error\":\"" # jsonEsc(e) # "\"}") };
        case null {};
      };
      // Race with a user publish: mark done pointing at the existing entry, no payout.
      switch (tOps.get(libraryByQuery, j.norm)) {
        case (?existingId) {
          putJob({ j with status = "done"; libraryId = ?existingId });
          jobsByNorm := tOps.delete(jobsByNorm, j.norm);
          return ?libJsonNoStore("{\"ok\":true,\"libraryId\":\"" # jsonEsc(existingId) # "\",\"existing\":true}");
        };
        case null {};
      };
      // Network entries bypass LIB_MAX_PER_OWNER (a 200-lifetime-job cap would
      // brick every productive worker); the daily budget + approval gate flood.
      let libId2 = libInsert(p, j.q, answer, sources, graphJson, {
        model; searchEngine = engine; worker = ?p;
        firstSearchedAt = j.submittedAt; answeredAt = now();
      });
      putJob({ j with status = "done"; libraryId = ?libId2 });
      jobsByNorm := tOps.delete(jobsByNorm, j.norm);
      bumpJobDay();
      jobsAnsweredToday += 1;
      patchWorker(p, func(x) { { x with jobsDone = x.jobsDone + 1;
                                 accruedE8s = x.accruedE8s + searchPayRateE8s } });
      return ?libJsonNoStore("{\"ok\":true,\"libraryId\":\"" # jsonEsc(libId2) # "\",\"existing\":false}");
    };

    ?workerDeny();
  };

  func textTake(t : Text, n : Nat) : Text {
    if (t.size() <= n) { return t };
    var out = "";
    var i = 0;
    label take for (c in t.chars()) {
      if (i >= n) { break take };
      out #= Text.fromChar(c);
      i += 1;
    };
    out;
  };

  // ── Public search routes (anonymous, plain fetch) ───────────────────────
  // GET  /library/find.json?q=…    exact normalized-query lookup
  // POST /search/submit            body = pct-encoded query (text/plain)
  // GET  /search/job/<id>.json     poll a queued job
  // GET  /search/health.json       network liveness for honest UI states
  func searchLookup(req : HttpRequest) : ?HttpResponse {
    var path = req.url;
    var queryStr = "";
    let qIx = Text.split(req.url, #char '?');
    switch (qIx.next()) { case (?pth) path := pth; case null {} };
    switch (qIx.next()) { case (?qs) queryStr := qs; case null {} };
    path := Text.trimStart(path, #char '/');
    let parts = Iter.toArray(Text.split(path, #char '/'));
    if (parts.size() == 0) { return null };

    if (parts[0] == "library" and parts.size() == 2 and parts[1] == "find.json") {
      // find ?q=<pct>
      for (kv in Text.split(queryStr, #char '&')) {
        let pair = Iter.toArray(Text.split(kv, #char '='));
        if (pair.size() == 2 and pair[0] == "q") {
          switch (pctDecode(pair[1])) {
            case (?q) {
              switch (tOps.get(libraryByQuery, libNorm(q))) {
                case (?id) {
                  switch (tOps.get(libraryEntries, id)) {
                    case (?e) { return ?libJsonResponse(entryJson(e)) };
                    case null {};
                  };
                };
                case null {};
              };
            };
            case null {};
          };
        };
      };
      return ?libNotFound();
    };

    if (parts[0] != "search") { return null };
    tendJobs();

    if (parts.size() == 2 and parts[1] == "submit" and req.method == "POST") {
      if (req.body.size() > 2_048) { return ?libNotFound() };
      let raw = switch (Text.decodeUtf8(req.body)) { case (?t) t; case null { return ?libNotFound() } };
      let q = switch (pctDecode(raw)) { case (?t) t; case null raw };
      switch (submitSearch(q)) {
        case (#hit(id)) {
          let e = switch (tOps.get(libraryEntries, id)) { case (?x) ?entryJson(x); case null null };
          return ?libJsonNoStore("{\"status\":\"hit\",\"entry\":" #
            (switch (e) { case (?j) j; case null "null" }) # "}");
        };
        case (#queued(jid)) { return ?libJsonNoStore("{\"status\":\"queued\",\"jobId\":\"" # jsonEsc(jid) # "\"}") };
        case (#rejected(r)) { return ?libJsonNoStore("{\"status\":\"rejected\",\"reason\":\"" # jsonEsc(r) # "\"}") };
      };
    };

    if (parts.size() == 3 and parts[1] == "job") {
      switch (Text.stripEnd(parts[2], #text ".json")) {
        case (?jid) {
          switch (tOps.get(searchJobs, jid)) {
            case (?j) {
              let entry = switch (j.libraryId) {
                case (?lid) {
                  switch (tOps.get(libraryEntries, lid)) { case (?e) entryJson(e); case null "null" };
                };
                case null "null";
              };
              return ?libJsonNoStore("{\"status\":\"" # jsonEsc(j.status) #
                "\",\"libraryId\":" # (switch (j.libraryId) { case (?l) "\"" # jsonEsc(l) # "\""; case null "null" }) #
                ",\"entry\":" # entry # "}");
            };
            case null { return ?libNotFound() };
          };
        };
        case null {};
      };
      return ?libNotFound();
    };

    if (parts.size() == 2 and parts[1] == "health.json") {
      return ?libJsonNoStore("{\"workers\":" # Nat.toText(pOps.size(workers)) #
        ",\"activeWorkers\":" # Nat.toText(activeWorkerCount()) #
        ",\"pending\":" # Nat.toText(livePendingCount()) #
        ",\"answeredToday\":" # Nat.toText(jobsAnsweredToday) #
        ",\"budget\":" # Nat.toText(searchDailyBudget) #
        ",\"entries\":" # Nat.toText(tOps.size(libraryEntries)) #
        ",\"payoutsEnabled\":" # (if (searchPayRateE8s > 0) "true" else "false") # "}");
    };

    ?libNotFound();  // reserve /search/*
  };

  // ── Worker auto-pay — accrue per job, sweep on the payroll timer ───────────
  // "Auto-pay per job" with honest economics: a literal transfer per job pays
  // the ledger fee (10_000 e8s on ICP) per job, which can exceed a micro-rate.
  // So fulfill ACCRUES the per-job rate and the sweep pays each worker once
  // their accrual crosses max(minPayout, 2×fee). Funds come from the plan
  // admin's account under a SEPARATE icrc2_approve (spender = this canister) —
  // the allowance is the hard budget, exactly like user payroll, and fully
  // independent of it. Exactly-once discipline copied from executeTransfer:
  // zero the accrual + log a pending payout BEFORE the ledger await; memo +
  // created_at_time make ledger-side dedup kill replays.
  stable var searchPayLedger : ?Principal = null;
  stable var searchPayRateE8s : Nat = 0;              // 0 = accrual off
  stable var searchPayMinE8s : Nat = 100_000;
  stable var searchPayFee : Nat = 10_000;             // auto-corrected on #BadFee
  stable var searchTreasury : ?Principal = null;      // the admin who configured pay
  public type WorkerPayout = {
    key : Text; worker : Principal; amount : Nat;
    scheduledAt : Int; status : Text; blockIndex : ?Nat; ts : Int;
  };
  stable var workerPayouts : [WorkerPayout] = [];
  let MAX_WORKER_PAYOUTS_KEPT : Nat = 500;

  func appendWorkerPayout(po : WorkerPayout) {
    let buf = Buffer.fromArray<WorkerPayout>(workerPayouts);
    buf.add(po);
    while (buf.size() > MAX_WORKER_PAYOUTS_KEPT) { ignore buf.remove(0) };
    workerPayouts := Buffer.toArray(buf);
  };
  func setWorkerPayoutStatus(key : Text, status : Text, blockIndex : ?Nat) {
    workerPayouts := Array.map<WorkerPayout, WorkerPayout>(workerPayouts, func(po) {
      if (po.key == key) { { po with status; blockIndex; ts = now() } } else { po };
    });
  };
  func restoreAccrual(p : Principal, amount : Nat) {
    patchWorker(p, func(x) { { x with accruedE8s = x.accruedE8s + amount } });
  };
  func workerPayoutSub(w : Worker) : ?Blob {
    if (w.payoutSubHex == "") { return null };
    switch (hexToBytes(w.payoutSubHex)) {
      case (?b) { if (b.size() == 32) { ?Blob.fromArray(b) } else { null } };
      case null null;
    };
  };

  func executeWorkerPayout(po : WorkerPayout) : async () {
    let ledgerP = switch (searchPayLedger) { case (?l) l; case null { return } };
    let treasury = switch (searchTreasury) { case (?t) t; case null { return } };
    let w = switch (pOps.get(workers, po.worker)) { case (?x) x; case null {
      setWorkerPayoutStatus(po.key, "failed:orphaned", null); return } };
    let ledger : LedgerActor = actor (Principal.toText(ledgerP));
    let args : TransferFromArgs = {
      spender_subaccount = null;
      from = { owner = treasury; subaccount = null };
      to = { owner = w.payoutOwner; subaccount = workerPayoutSub(w) };
      amount = po.amount;
      fee = ?searchPayFee;
      memo = ?Text.encodeUtf8(po.key);
      created_at_time = ?Nat64.fromIntWrap(po.scheduledAt);
    };
    try {
      switch (await ledger.icrc2_transfer_from(args)) {
        case (#Ok(block)) {
          setWorkerPayoutStatus(po.key, "paid", ?block);
          patchWorker(po.worker, func(x) { { x with earnedE8s = x.earnedE8s + po.amount; updatedAt = now() } });
        };
        case (#Err(#Duplicate(d))) {
          setWorkerPayoutStatus(po.key, "paid", ?d.duplicate_of);
          patchWorker(po.worker, func(x) { { x with earnedE8s = x.earnedE8s + po.amount; updatedAt = now() } });
        };
        case (#Err(#BadFee(e))) {
          searchPayFee := e.expected_fee;   // retry same key next sweep with the right fee
        };
        case (#Err(#InsufficientAllowance(_))) {
          setWorkerPayoutStatus(po.key, "failed:allowance", null);
          restoreAccrual(po.worker, po.amount);   // definitive reject → funds never moved
        };
        case (#Err(#InsufficientFunds(_))) {
          setWorkerPayoutStatus(po.key, "failed:funds", null);
          restoreAccrual(po.worker, po.amount);
        };
        case (#Err(#TooOld)) {
          setWorkerPayoutStatus(po.key, "failed:expired", null);
          restoreAccrual(po.worker, po.amount);
        };
        case (#Err(_)) {
          setWorkerPayoutStatus(po.key, "failed:ledger", null);
          restoreAccrual(po.worker, po.amount);
        };
      };
    } catch (_e) {
      // Trapped — outcome UNKNOWN. Leave pending; next sweep retries the same
      // memo/created_at_time (ledger dedup = exactly-once). Never restore here.
    };
  };

  func scanWorkerPayouts() : async () {
    if (searchPayLedger == null or searchTreasury == null or searchPayRateE8s == 0) { return };
    let threshold = if (searchPayMinE8s > searchPayFee * 2) { searchPayMinE8s } else { searchPayFee * 2 };
    // New sweeps: accrual crossed the threshold.
    let due = Buffer.Buffer<(Principal, Nat)>(4);
    for ((p, w) in pOps.entries(workers)) {
      if (w.status == "approved" and w.accruedE8s >= threshold) { due.add((p, w.accruedE8s)) };
    };
    for ((p, amount) in due.vals()) {
      let scheduledAt = now();
      let key = "wp#" # Principal.toText(p) # "#" # Int.toText(scheduledAt);
      // Crash-safe intent BEFORE the await: zero the accrual, log pending.
      patchWorker(p, func(x) { { x with accruedE8s = 0; updatedAt = now() } });
      appendWorkerPayout({ key; worker = p; amount; scheduledAt; status = "pending"; blockIndex = null; ts = now() });
      await executeWorkerPayout({ key; worker = p; amount; scheduledAt; status = "pending"; blockIndex = null; ts = now() });
    };
    // Retry or expire stale pendings left by trapped ledger calls.
    for (po in workerPayouts.vals()) {
      if (po.status == "pending" and now() - po.ts > PENDING_RETRY_MIN_AGE_NS) {
        if (now() - po.scheduledAt > PENDING_RETRY_MAX_NS) {
          setWorkerPayoutStatus(po.key, "failed:expired", null);
        } else {
          await executeWorkerPayout(po);
        };
      };
    };
  };

  // ── Search-network admin ───────────────────────────────────────────────────
  public shared (msg) func search_admin_set_pay(
    ledgerId : Principal, ratePerJobE8s : Nat, minPayoutE8s : Nat
  ) : async () {
    // planAdmin claim-or-match — same gate as setWakeConfig: first caller must
    // be a controller; afterwards only the established admin.
    switch (planAdmin) {
      case (?a) { if (a != msg.caller) { throw Error.reject("plan admin only") } };
      case null {
        if (not Principal.isController(msg.caller)) { throw Error.reject("only a controller may claim plan admin") };
        planAdmin := ?msg.caller;
      };
    };
    if (not isKnownLedger(ledgerId)) { throw Error.reject("unsupported ledger") };
    searchPayLedger := ?ledgerId;
    searchPayRateE8s := ratePerJobE8s;
    searchPayMinE8s := minPayoutE8s;
    searchTreasury := ?msg.caller;
  };

  public shared (msg) func search_admin_set_budget(perDay : Nat) : async () {
    if (not isPlanAdminP(msg.caller)) { throw Error.reject("plan admin only") };
    searchDailyBudget := perDay;
  };

  public query func search_pay_status() : async {
    rateE8s : Nat; minE8s : Nat; ledgerSet : Bool; treasurySet : Bool; budgetPerDay : Nat;
  } {
    { rateE8s = searchPayRateE8s; minE8s = searchPayMinE8s;
      ledgerSet = searchPayLedger != null; treasurySet = searchTreasury != null;
      budgetPerDay = searchDailyBudget };
  };

  public shared query (msg) func worker_payout_log() : async [WorkerPayout] {
    if (isPlanAdminP(msg.caller)) { return workerPayouts };
    Array.filter<WorkerPayout>(workerPayouts, func(po) { po.worker == msg.caller });
  };

  // Upgrade GETs to an update call so we don't need asset certification (MVP).
  public query func http_request(_req : HttpRequest) : async HttpResponse {
    { status_code = 200; headers = []; body = ""; streaming_strategy = null; upgrade = ?true };
  };
  public func http_request_update(req : HttpRequest) : async HttpResponse {
    // Receipt verify pages take precedence over sites — SECURITY: a site
    // project can never shadow the /receipt/ URL shape (name reserved too).
    // Then search (find/submit/job/health) → library → worker (HMAC POSTs) →
    // sites. All reserved prefixes fail parsePrincipal, so no site collision.
    switch (receiptLookup(req.url)) {
      case (?res) res;
      case null {
        switch (searchLookup(req)) {
          case (?res) res;
          case null {
            switch (libraryLookup(req.url)) {
              case (?res) res;
              case null {
                switch (workerRoute(req)) {
                  case (?res) res;
                  case null serveSite(req.url);
                };
              };
            };
          };
        };
      };
    };
  };

  // ── Night Shift chain wake (Sprint 4 MVP-2 — ships DARK, flag off) ─────────
  // The browser MIRRORS its serve.py night-shift schedules here so a canister
  // timer can wake a STOPPED fleet container in time for its mission: scan due
  // mirrors → one HTTPS outcall POST <wakeGatewayUrl> per user with body
  // {"user","ids","ts"} and X-Wake-Signature = hex(hmac-sha256(secret, body)).
  // The container's serve.py stays the source of truth for WHAT runs — a wake
  // only means "boot the container" (fleet-api verifies the HMAC and dedups).
  // The outcall carries nothing but the caller's principal + schedule ids.
  // Entirely inert until the plan admin sets a gateway URL + secret AND flips
  // enabled — the fleet-api half is blocked on gateway access, so this ships
  // dark by design.

  public type MissionSchedule = {
    id : Text;              // serve.py schedule id (nsh_*)
    agentId : Text;
    topic : Text;
    recurrence : Text;      // "once" | "daily"
    durationSecs : Nat;
    intervalSecs : Nat;
    enabled : Bool;
    nextRunAt : Int;        // ns epoch — the shell converts serve.py ms
    lastWakeAt : Int;       // ns; 0 = never woken
    lastWakeResult : Text;  // "" | "sent" | "skipped:stale" | "error:…"
    updatedAt : Int;
  };

  type MissionMap = OrderedMap.Map<Text, MissionSchedule>;
  stable var missionSchedules : OrderedMap.Map<Principal, MissionMap> = pOps.empty<MissionMap>();
  // Wake config — planAdmin-gated; all-empty defaults = feature disabled.
  stable var wakeEnabled : Bool = false;
  stable var wakeGatewayUrl : Text = "";
  stable var wakeSecret : Blob = "";

  let WAKE_SCAN_SECS : Nat = 120;
  let MAX_MISSION_SCHEDULES : Nat = 20;                // mirrors serve.py cap
  let WAKE_STALE_NS : Int = 6 * 3600 * 1_000_000_000;  // roll, don't wake, past this
  let DAY_NS : Int = 24 * 3600 * 1_000_000_000;
  let WAKE_OUTCALL_CYCLES : Nat = 300_000_000;         // unspent cycles refund

  func missionsOf(p : Principal) : MissionMap {
    switch (pOps.get(missionSchedules, p)) { case (?m) m; case null tOps.empty<MissionSchedule>() };
  };
  // Same re-read discipline as patchSalary — scanWake spans awaits.
  func patchMission(user : Principal, id : Text, f : MissionSchedule -> MissionSchedule) {
    let m = missionsOf(user);
    switch (tOps.get(m, id)) {
      case (?s) { missionSchedules := pOps.put(missionSchedules, user, tOps.put(m, id, f(s))) };
      case null {};
    };
  };
  // Roll a fired/stale mirror forward so it can't re-trigger every scan:
  // once → disabled (serve.py does the same); daily → +24h steps past now.
  func rollMission(s : MissionSchedule) : MissionSchedule {
    if (s.recurrence == "daily") {
      var t = s.nextRunAt;
      while (t <= now()) { t += DAY_NS };
      { s with nextRunAt = t; updatedAt = now() };
    } else {
      { s with enabled = false; updatedAt = now() };
    };
  };

  // HTTPS outcall plumbing (IC management canister).
  type OutcallHeader = { name : Text; value : Text };
  type OutcallResponse = { status : Nat; headers : [OutcallHeader]; body : Blob };
  type OutcallTransformArgs = { response : OutcallResponse; context : Blob };
  type OutcallArgs = {
    url : Text;
    max_response_bytes : ?Nat64;
    headers : [OutcallHeader];
    body : ?Blob;
    method : { #get; #post; #head };
    transform : ?{ function : shared query OutcallTransformArgs -> async OutcallResponse; context : Blob };
  };
  let mgmt : actor { http_request : OutcallArgs -> async OutcallResponse } = actor ("aaaaa-aa");

  // Strip headers/body so replicas reach consensus on the status code alone.
  public query func wakeTransform(args : OutcallTransformArgs) : async OutcallResponse {
    { status = args.response.status; headers = []; body = Blob.fromArray([]) };
  };

  func sendWake(user : Principal, ids : [Text]) : async Nat {
    // ids are validated [A-Za-z0-9_-] at put time, so raw embedding is JSON-safe.
    var idsJson = "";
    for (id in ids.vals()) { idsJson := idsJson # (if (idsJson == "") "" else ",") # "\"" # id # "\"" };
    let body = "{\"user\":\"" # Principal.toText(user) # "\",\"ids\":[" # idsJson # "],\"ts\":" # Int.toText(now()) # "}";
    let bodyBlob = Text.encodeUtf8(body);
    let sig = Sha256.toHex(Sha256.hmac(Blob.toArray(wakeSecret), Blob.toArray(bodyBlob)));
    Cycles.add<system>(WAKE_OUTCALL_CYCLES);
    let res = await mgmt.http_request({
      url = wakeGatewayUrl;
      max_response_bytes = ?1024;
      headers = [
        { name = "Content-Type"; value = "application/json" },
        { name = "X-Wake-Signature"; value = sig },
      ];
      body = ?bodyBlob;
      method = #post;
      transform = ?{ function = wakeTransform; context = Blob.fromArray([]) };
    });
    res.status;
  };

  func scanWake() : async () {
    if (not wakeEnabled or wakeGatewayUrl == "" or wakeSecret.size() == 0) { return };
    // Snapshot due ids per user; every write below re-reads live state.
    let due = Buffer.Buffer<(Principal, [Text])>(4);
    for ((user, m) in pOps.entries(missionSchedules)) {
      let fresh = Buffer.Buffer<Text>(2);
      for ((id, s) in tOps.entries(m)) {
        if (s.enabled and s.nextRunAt <= now()) {
          if (now() - s.nextRunAt > WAKE_STALE_NS) {
            // Ancient mirror (wake was off, or the user gone for days): roll silently.
            patchMission(user, id, func(x) { { rollMission(x) with lastWakeResult = "skipped:stale" } });
          } else { fresh.add(id) };
        };
      };
      if (fresh.size() > 0) { due.add((user, Buffer.toArray(fresh))) };
    };
    for ((user, ids) in due.vals()) {
      // Advance mirrors BEFORE the outcall (payroll's reentrancy discipline):
      // worst case on failure is a MISSED wake, never a wake storm.
      for (id in ids.vals()) {
        patchMission(user, id, func(x) { { rollMission(x) with lastWakeAt = now() } });
      };
      try {
        let status = await sendWake(user, ids);
        let tag = if (status >= 200 and status < 300) { "sent" } else { "error:http" # Nat.toText(status) };
        for (id in ids.vals()) { patchMission(user, id, func(x) { { x with lastWakeResult = tag } }) };
      } catch (_e) {
        for (id in ids.vals()) { patchMission(user, id, func(x) { { x with lastWakeResult = "error:outcall" } }) };
      };
    };
  };

  // Idempotent arming (no-op when already armed), same shape as the payroll
  // timer; re-armed in postupgrade. Must NOT cancel-then-recreate — the
  // user-facing putMissionSchedule path would otherwise let any caller reset
  // the 120s countdown and starve scanWake for all users.
  var wakeTimerId : ?Timer.TimerId = null;
  func armWakeTimer<system>() {
    switch (wakeTimerId) { case (?_) { return }; case null {} };
    wakeTimerId := ?Timer.recurringTimer<system>(#seconds WAKE_SCAN_SECS, scanWake);
  };
  armWakeTimer<system>();

  func validMissionId(id : Text) : Bool {
    if (id.size() == 0 or id.size() > 64) { return false };
    for (c in id.chars()) {
      let ok = (c >= 'a' and c <= 'z') or (c >= 'A' and c <= 'Z')
        or (c >= '0' and c <= '9') or c == '_' or c == '-';
      if (not ok) { return false };
    };
    true;
  };

  // ── Night Shift mirror public API (caller-keyed) ────────────────────────────
  public shared (msg) func putMissionSchedule(
    id : Text, agentId : Text, topic : Text, recurrence : Text,
    durationSecs : Nat, intervalSecs : Nat, enabled : Bool, nextRunAt : Int,
  ) : async () {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    if (not validMissionId(id)) { throw Error.reject("bad schedule id") };
    if (agentId.size() == 0 or agentId.size() > 64) { throw Error.reject("bad agentId") };
    if (topic.size() == 0 or topic.size() > 500) { throw Error.reject("bad topic") };
    if (recurrence != "once" and recurrence != "daily") { throw Error.reject("recurrence must be once|daily") };
    if (durationSecs < 60 or durationSecs > 4 * 3600) { throw Error.reject("bad duration") };
    if (intervalSecs < 60 or intervalSecs > durationSecs) { throw Error.reject("bad interval") };
    if (nextRunAt < 0) { throw Error.reject("bad nextRunAt") };
    let m = missionsOf(caller);
    let prev = tOps.get(m, id);
    switch (prev) {
      case null { if (tOps.size(m) >= MAX_MISSION_SCHEDULES) { throw Error.reject("too many schedules (max 20)") } };
      case (?_) {};
    };
    let s : MissionSchedule = {
      id; agentId; topic; recurrence; durationSecs; intervalSecs; enabled; nextRunAt;
      lastWakeAt = switch (prev) { case (?p) p.lastWakeAt; case null 0 };
      lastWakeResult = switch (prev) { case (?p) p.lastWakeResult; case null "" };
      updatedAt = now();
    };
    missionSchedules := pOps.put(missionSchedules, caller, tOps.put(m, id, s));
    armWakeTimer<system>();
  };

  public shared query (msg) func listMissionSchedules() : async [MissionSchedule] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    Iter.toArray(tOps.vals(missionsOf(msg.caller)));
  };

  public shared (msg) func deleteMissionSchedule(id : Text) : async Bool {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    let m = missionsOf(caller);
    switch (tOps.get(m, id)) {
      case null { false };
      case (?_) { missionSchedules := pOps.put(missionSchedules, caller, tOps.delete(m, id)); true };
    };
  };

  /// Admin-only wake switch (claim-or-match on the same planAdmin identity).
  /// secretHex = "" keeps the existing secret. URL must be https to enable.
  public shared (msg) func setWakeConfig(enabled : Bool, gatewayUrl : Text, secretHex : Text) : async () {
    let caller = msg.caller;
    switch (planAdmin) {
      // Controller-only claim (see setPlanSecret) — this is the other path that
      // could otherwise seize admin and point the wake outcall at an attacker.
      case null { if (not Principal.isController(caller)) { throw Error.reject("only a controller may claim plan admin") }; planAdmin := ?caller };
      case (?a) { if (caller != a) { throw Error.reject("only the plan admin may set wake config") } };
    };
    if (secretHex != "") {
      switch (hexToBytes(secretHex)) {
        case null { throw Error.reject("secret must be valid hex") };
        case (?bytes) {
          if (bytes.size() < 16) { throw Error.reject("secret too short (>= 16 bytes)") };
          wakeSecret := Blob.fromArray(bytes);
        };
      };
    };
    if (enabled) {
      if (not Text.startsWith(gatewayUrl, #text "https://")) { throw Error.reject("gateway url must be https") };
      if (wakeSecret.size() == 0) { throw Error.reject("set a secret before enabling") };
    };
    wakeGatewayUrl := gatewayUrl;
    wakeEnabled := enabled;
    if (enabled) { armWakeTimer<system>() };
  };

  /// Public visibility for `hq night chain` — config presence only, no secrets.
  public query func wakeStatus() : async { enabled : Bool; urlSet : Bool; secretSet : Bool } {
    { enabled = wakeEnabled; urlSet = wakeGatewayUrl != ""; secretSet = wakeSecret.size() > 0 };
  };

  // ── Diagnostics ────────────────────────────────────────────────────────────
  public query func cycle_balance() : async Nat { Cycles.balance() };

  // Fresh-install timer arm — MUST be the last declaration: payrollTick
  // transitively references the search-network payout section above.
  armPayrollTimer<system>();
}
