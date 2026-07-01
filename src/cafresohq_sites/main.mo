// ──────────────────────────────────────────────────────────────────────────
// CafresoHQ — public sites asset canister  (Publish-to-Canister)
//
// ONE HQ-owned, DAO-funded canister that hosts every user's published sites —
// so publishing is HQ infrastructure (like the frontend canister), not a
// per-user canister anyone has to provision or fund.
//
// ISOLATION: writes are keyed by `msg.caller` (the browser's II principal), so
// a user can only write their OWN namespace — same model as cafresohq_state.
// This sidesteps the standard asset canister's canister-wide (non-path-scoped)
// commit permission, which makes shared multi-tenant hosting unsafe there.
//
// SERVING: http_request serves any namespace PUBLICLY at
//   https://<this-canister>.icp0.io/<principalText>/<project>/<path>
// For the MVP it upgrades GETs to an update call (http_request_update) so we
// don't need IC asset certification yet; certified query serving is a perf
// follow-up. Bodies must fit the ~2 MiB response limit (no streaming yet).
// ──────────────────────────────────────────────────────────────────────────

import Principal "mo:base/Principal";
import Text "mo:base/Text";
import Blob "mo:base/Blob";
import Nat "mo:base/Nat";
import Nat16 "mo:base/Nat16";
import Int "mo:base/Int";
import Iter "mo:base/Iter";
import Buffer "mo:base/Buffer";
import Time "mo:base/Time";
import Error "mo:base/Error";
import Char "mo:base/Char";
import Cycles "mo:base/ExperimentalCycles";
import OrderedMap "mo:base/OrderedMap";

actor CafresoHQSites {

  // ── Types ────────────────────────────────────────────────────────────────
  public type SiteFile = { contentType : Text; body : Blob; updatedAt : Int };
  public type PutFileResult = { #ok : { bytes : Nat }; #err : Text };
  public type SiteSummary = { project : Text; fileCount : Nat; totalBytes : Nat; updatedAt : Int };

  type HeaderField = (Text, Text);
  public type HttpRequest = { method : Text; url : Text; headers : [HeaderField]; body : Blob };
  public type HttpResponse = {
    status_code : Nat16; headers : [HeaderField]; body : Blob;
    streaming_strategy : ?Null; upgrade : ?Bool;
  };

  // ── Limits ───────────────────────────────────────────────────────────────
  let MAX_FILE_BYTES : Nat = 2_000_000;              // ~2 MiB per file (ingress cap)
  let MAX_USER_BYTES : Nat = 200 * 1024 * 1024;      // 200 MiB of published sites per user

  // ── Storage (per-principal namespace; key = "<project>/<path>") ───────────
  let pOps = OrderedMap.Make<Principal>(Principal.compare);
  let tOps = OrderedMap.Make<Text>(Text.compare);
  type FileMap = OrderedMap.Map<Text, SiteFile>;
  stable var sites : OrderedMap.Map<Principal, FileMap> = pOps.empty<FileMap>();
  stable var usageBytes : OrderedMap.Map<Principal, Nat> = pOps.empty<Nat>();

  func now() : Int { Time.now() };
  func subSat(a : Nat, b : Nat) : Nat { if (a > b) { a - b } else { 0 } };
  func filesOf(p : Principal) : FileMap { switch (pOps.get(sites, p)) { case (?m) m; case null tOps.empty<SiteFile>() } };
  func usageOf(p : Principal) : Nat { switch (pOps.get(usageBytes, p)) { case (?n) n; case null 0 } };

  // ── Name hygiene ─────────────────────────────────────────────────────────
  func isSafe(c : Char) : Bool {
    (c >= 'a' and c <= 'z') or (c >= 'A' and c <= 'Z') or (c >= '0' and c <= '9')
      or c == '-' or c == '_' or c == '.'
  };
  func validProject(p : Text) : Bool {
    if (p.size() == 0 or p.size() > 64) { return false };
    for (c in p.chars()) { if (not isSafe(c)) { return false } };
    not Text.contains(p, #text "..");
  };
  // Strip leading slashes; reject traversal. Relative path within a project.
  func normalizePath(path : Text) : ?Text {
    var p = path;
    p := Text.trimStart(p, #char '/');
    if (Text.contains(p, #text "..")) { return null };
    if (p.size() == 0) { ?"index.html" } else { ?p };
  };

  // ── Write API (per-caller; only you can write your namespace) ─────────────
  public shared (msg) func putSiteFile(project : Text, path : Text, contentType : Text, body : Blob) : async PutFileResult {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in with Internet Identity") };
    if (not validProject(project)) { return #err("bad project name") };
    if (body.size() > MAX_FILE_BYTES) { return #err("file exceeds 2 MiB limit") };
    let rel = switch (normalizePath(path)) { case (?r) r; case null { return #err("bad path") } };
    let key = project # "/" # rel;
    let files = filesOf(caller);
    let prevSize = switch (tOps.get(files, key)) { case (?f) f.body.size(); case null 0 };
    let newUsed = subSat(usageOf(caller), prevSize) + body.size();
    if (newUsed > MAX_USER_BYTES) { return #err("site storage quota exceeded") };
    let f : SiteFile = { contentType = contentType; body = body; updatedAt = now() };
    sites := pOps.put(sites, caller, tOps.put(files, key, f));
    usageBytes := pOps.put(usageBytes, caller, newUsed);
    #ok({ bytes = body.size() });
  };

  /// Remove all files under a project (call before re-publishing to drop stale files).
  public shared (msg) func deleteSite(project : Text) : async Nat {
    let caller = msg.caller;
    if (Principal.isAnonymous(caller)) { throw Error.reject("sign in") };
    let files = filesOf(caller);
    let prefix = project # "/";
    var next = files;
    var freed : Nat = 0;
    var removed : Nat = 0;
    for ((k, f) in tOps.entries(files)) {
      if (Text.startsWith(k, #text prefix)) { next := tOps.delete(next, k); freed += f.body.size(); removed += 1 };
    };
    sites := pOps.put(sites, caller, next);
    usageBytes := pOps.put(usageBytes, caller, subSat(usageOf(caller), freed));
    removed;
  };

  public shared query (msg) func listMySites() : async [SiteSummary] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    // Aggregate keys by their leading "<project>/" segment.
    let acc = OrderedMap.Make<Text>(Text.compare);
    var agg : OrderedMap.Map<Text, SiteSummary> = acc.empty<SiteSummary>();
    for ((k, f) in tOps.entries(filesOf(msg.caller))) {
      let proj = switch (Text.split(k, #char '/').next()) { case (?p) p; case null k };
      let prev = switch (acc.get(agg, proj)) { case (?s) s; case null { { project = proj; fileCount = 0; totalBytes = 0; updatedAt = 0 } } };
      agg := acc.put(agg, proj, {
        project = proj; fileCount = prev.fileCount + 1;
        totalBytes = prev.totalBytes + f.body.size();
        updatedAt = Int.max(prev.updatedAt, f.updatedAt);
      });
    };
    Iter.toArray(acc.vals(agg));
  };

  public shared query (msg) func myUsageBytes() : async Nat {
    if (Principal.isAnonymous(msg.caller)) { return 0 };
    usageOf(msg.caller);
  };

  // ── Public serving ────────────────────────────────────────────────────────
  // GET /<principalText>/<project>/<path...>  →  the stored file, public.
  func lookup(url : Text) : ?SiteFile {
    // strip query/fragment
    var path = url;
    switch (Text.split(path, #char '?').next()) { case (?p) path := p; case null {} };
    path := Text.trimStart(path, #char '/');
    let parts = Iter.toArray(Text.split(path, #char '/'));
    if (parts.size() < 2) { return null };
    let who = parts[0];
    let owner = switch (Principal.fromText(who)) { case p ?p };
    // remaining = project/<rest...>; rebuild the stored key, defaulting to index.html
    let buf = Buffer.Buffer<Text>(parts.size());
    var i = 1;
    while (i < parts.size()) { if (parts[i].size() > 0) { buf.add(parts[i]) }; i += 1 };
    if (buf.size() == 0) { return null };
    var key = Text.join("/", buf.vals());
    if (buf.size() == 1) { key := key # "/index.html" };        // /<p>/<project> → index.html
    if (Text.endsWith(key, #text "/")) { key := key # "index.html" };
    switch (owner) { case (?o) tOps.get(filesOf(o), key); case null null };
  };

  func serve(url : Text) : HttpResponse {
    switch (lookup(url)) {
      case (?f) {
        {
          status_code = 200;
          headers = [("Content-Type", f.contentType), ("Cache-Control", "public, max-age=60"),
                     ("Access-Control-Allow-Origin", "*")];
          body = f.body; streaming_strategy = null; upgrade = null;
        };
      };
      case null {
        {
          status_code = 404;
          headers = [("Content-Type", "text/plain")];
          body = Text.encodeUtf8("Not found");
          streaming_strategy = null; upgrade = null;
        };
      };
    };
  };

  // Upgrade GETs to an update call so we don't need asset certification (MVP).
  public query func http_request(_req : HttpRequest) : async HttpResponse {
    { status_code = 200; headers = []; body = ""; streaming_strategy = null; upgrade = ?true };
  };
  public func http_request_update(req : HttpRequest) : async HttpResponse {
    serve(req.url);
  };

  // ── Diagnostics ────────────────────────────────────────────────────────────
  public query func cycle_balance() : async Nat { Cycles.balance() };
}
