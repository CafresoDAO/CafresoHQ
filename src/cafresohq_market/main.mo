/// cafresohq_market — the hiring hall: hire a coworker from the network,
/// pay them from escrow, and read their résumé before you do.
///
/// North Star §6 Phase C ("Hire from the network") and DRIVER_CONTRACT §6.
/// This is the labor market, not a FLOPs market: what is listed here is a
/// coworker with a name, a job description and a résumé — jobs completed,
/// re-hire rate, disputes — not a GPU.
///
/// Three principals meet on every job:
///
///   the BOSS      — an Internet Identity principal, calling from the shell
///                   at ai.cafreso.com. Posts a job, funds its escrow with an
///                   ICRC-2 allowance, accepts or rejects the delivery.
///   the OPERATOR  — an II principal who lists a coworker they run. Gets paid.
///   the WORKER    — the listed coworker's OWN key, generated inside its
///                   container (ic_agent.py) and linked here by the operator.
///                   It can claim, report progress on, deliver or fail jobs
///                   for its listing — and nothing else. It never touches the
///                   operator's wallet, vault or state. One call unlinks it.
///
/// Why a separate canister from cafresohq_state: escrow is money at rest, and
/// the state canister has already once run its cycles to zero and been wiped
/// (2026-08-05). Held funds get their own cycle balance and their own blast
/// radius. It also lets the state canister's working tree stay untouched.
///
/// Discipline carried over from cafresohq_state (read that file's header):
///   * every row is keyed by msg.caller; no boss/operator method takes a
///     principal argument that names another user's rows;
///   * plan admin is claim-or-match: a controller claims it once, then only
///     that principal may rule on disputes;
///   * SCHEMA EVOLUTION — a stored record can only be read back when the old
///     type is a subtype of the new one, so a field can be REMOVED from Job,
///     Listing or Payout but never ADDED. Variants may grow alternatives.
///     Anything new goes in a side table keyed by id (see `progress`,
///     `resumes`, `payouts`, `fundAttempt`);
///   * exactly-once ledger moves: state changes BEFORE the await, the ledger
///     dedups replays by memo + created_at_time, and only a KNOWN failure
///     restores the balance for retry — an unknown trap never does.
///
/// Money path (ICRC-1 / ICRC-2):
///   fund     boss --(icrc2_transfer_from, price + fee)--> canister/jobSub(id)
///   release  canister/jobSub(id) --(icrc1_transfer, price, fee)--> operator
///   refund   canister/jobSub(id) --(icrc1_transfer, price, fee)--> boss
/// The boss pays the escrow deposit's fee on the way in and the release's fee
/// rides in the deposit, so the worker receives exactly `price`. A refund
/// returns `price` (the boss has spent the two ledger fees).
///
/// Lifecycle:
///   posted → funded → claimed → delivered → accepted (paid)
///                 ↘ cancelled (refund)      ↘ disputed → ruled (paid / refunded / split)
///   a claim past its deadline goes back to funded (attempts + 1, a snag on
///   the résumé); the third snag fails the job and refunds the boss; a
///   delivery the boss ignores for AUTO_ACCEPT is accepted on their behalf;
///   a funded job nobody claims for UNCLAIMED_TTL is cancelled and refunded.
///
/// Privacy: the brief and the deliverable body are visible only to the boss,
/// the operator whose listing holds the claim, and that listing's worker.
/// `jobStatus` is the one public read (status, timestamps, a one-line
/// summary) so a container can poll a job it posted without a credential.
/// The vault is structurally unreachable from here: nothing in this canister
/// can address it.
import Array "mo:base/Array";
import Blob "mo:base/Blob";
import Buffer "mo:base/Buffer";
import Error "mo:base/Error";
import ExperimentalCycles "mo:base/ExperimentalCycles";
import Nat "mo:base/Nat";
import Nat64 "mo:base/Nat64";
import Nat8 "mo:base/Nat8";
import OrderedMap "mo:base/OrderedMap";
import Principal "mo:base/Principal";
import Text "mo:base/Text";
import Time "mo:base/Time";
import Timer "mo:base/Timer";

actor CafresoHQMarket {

  // ── Types ─────────────────────────────────────────────────────────────────

  public type JobStatus = {
    #posted;      // written down, escrow not yet funded — nobody can claim it
    #funded;      // escrow held; open to a claim
    #claimed;     // a worker holds the lease
    #delivered;   // the worker filed a result; waiting on the boss
    #accepted;    // the boss stamped it (or AUTO_ACCEPT did) — paid
    #disputed;    // the boss rejected the delivery; the plan admin rules
    #refunded;    // escrow went back to the boss (cancel, fail, or a ruling)
    #cancelled;   // the boss withdrew an unclaimed job
    #failed;      // three snags, or an unclaimable job — refund follows
  };

  public type Job = {
    id : Nat;
    boss : Principal;
    listing : ?Nat;          // direct hire: only this listing may claim; null = open
    title : Text;
    brief : Text;            // the task. Marketplace-ok by construction: the boss posted it.
    kind : Text;             // résumé task type: "brief" | "draft" | "page" | "code" | "research" | …
    tags : [Text];           // capabilities an open job needs; a listing must cover all of them
    ledger : Principal;      // ICRC-1/2 ledger the price is denominated in
    price : Nat;             // base units; what the worker receives
    fee : Nat;               // the ledger's fee at fund time; rides in the deposit
    deadlineSecs : Nat;      // lease length once claimed
    status : JobStatus;
    worker : ?Principal;     // the worker key holding (or that last held) the claim
    workerListing : ?Nat;    // the listing that claimed
    claimedAt : Int;
    attempts : Nat;
    deliveredAt : Int;
    summary : Text;          // the worker's one-line delivery note (public via jobStatus)
    body : Text;             // the deliverable itself (≤ BODY_MAX)
    bodySha256 : Text;       // hex, as the worker computed it
    rating : Nat;            // 0 = unrated, else 1..5
    note : Text;             // boss's reason (reject/cancel) or the admin's ruling
    escrowed : Nat;          // held right now in jobSub(id); 0 once moved out
    createdAt : Int;
    updatedAt : Int;
  };

  public type Listing = {
    id : Nat;
    operator : Principal;
    worker : ?Principal;     // the coworker's own key; null until linked
    name : Text;
    role : Text;
    pitch : Text;            // one line: what they are good at
    brain : Text;            // display name only (brainName-style), never a routing id
    tags : [Text];           // what they take: ["brief","research","code"]
    ledger : Principal;
    price : Nat;             // asking price per job, base units of `ledger`
    payoutSub : ?Blob;       // ICRC subaccount under `operator` to pay into
    active : Bool;
    lastSeen : Int;          // worker heartbeat, ns
    createdAt : Int;
    updatedAt : Int;
  };

  public type ResumeEntry = {
    at : Int;
    jobId : Nat;
    kind : Text;
    outcome : Text;          // "done" | "snag" | "disputed" | "refunded"
    boss : Principal;
    earned : Nat;            // base units of the job's ledger
    ledger : Principal;
    rating : Nat;
  };

  public type ResumeStats = {
    jobsDone : Nat;
    jobsFailed : Nat;
    disputes : Nat;
    bosses : Nat;            // distinct bosses served
    rehires : Nat;           // jobs from a boss who had hired this listing before
    ratingSum : Nat;
    ratingCount : Nat;
    lastActive : Int;
  };

  public type ListingCard = { listing : Listing; resume : ResumeStats; online : Bool };

  public type Payout = {
    key : Text;              // "<jobId>#release" | "<jobId>#refund" | "<jobId>#split-w" … — memo AND dedup key
    jobId : Nat;
    to : Principal;
    toSub : ?Blob;
    amount : Nat;
    scheduledAt : Int;       // ns; also created_at_time
    status : Text;           // "pending" | "paid" | "failed:<reason>"
    blockIndex : ?Nat;
    ts : Int;
  };

  public type JobOffer = {
    id : Nat; title : Text; brief : Text; kind : Text; tags : [Text];
    ledger : Principal; price : Nat; deadlineSecs : Nat; listing : ?Nat; createdAt : Int;
  };

  public type PublicStatus = {
    id : Nat; status : JobStatus; summary : Text; workerListing : ?Nat;
    claimedAt : Int; deliveredAt : Int; updatedAt : Int;
  };

  public type PostJobReq = {
    title : Text; brief : Text; kind : Text; tags : [Text];
    listing : ?Nat; ledger : Principal; price : Nat; deadlineSecs : Nat;
  };

  public type PutListingReq = {
    id : ?Nat; name : Text; role : Text; pitch : Text; brain : Text; tags : [Text];
    ledger : Principal; price : Nat; payoutSub : ?Blob; active : Bool;
  };

  public type Ruling = { #payWorker; #refundBoss; #split : Nat };   // split = worker's share, percent

  public type Result = { #ok : Nat; #err : Text };
  public type MoneyResult = { #ok : { block : Nat }; #duplicate : { block : Nat }; #err : Text };

  // ── ICRC-1 / ICRC-2 ───────────────────────────────────────────────────────

  type Account = { owner : Principal; subaccount : ?Blob };
  type TransferArgs = {
    from_subaccount : ?Blob; to : Account; amount : Nat; fee : ?Nat;
    memo : ?Blob; created_at_time : ?Nat64;
  };
  type TransferError = {
    #BadFee : { expected_fee : Nat }; #BadBurn : { min_burn_amount : Nat };
    #InsufficientFunds : { balance : Nat }; #TooOld;
    #CreatedInFuture : { ledger_time : Nat64 }; #Duplicate : { duplicate_of : Nat };
    #TemporarilyUnavailable; #GenericError : { error_code : Nat; message : Text };
  };
  type TransferFromArgs = {
    spender_subaccount : ?Blob; from : Account; to : Account; amount : Nat;
    fee : ?Nat; memo : ?Blob; created_at_time : ?Nat64;
  };
  type TransferFromError = {
    #BadFee : { expected_fee : Nat }; #BadBurn : { min_burn_amount : Nat };
    #InsufficientFunds : { balance : Nat }; #InsufficientAllowance : { allowance : Nat };
    #TooOld; #CreatedInFuture : { ledger_time : Nat64 };
    #Duplicate : { duplicate_of : Nat }; #TemporarilyUnavailable;
    #GenericError : { error_code : Nat; message : Text };
  };
  type Ledger = actor {
    icrc1_fee : shared query () -> async Nat;
    icrc1_transfer : shared TransferArgs -> async { #Ok : Nat; #Err : TransferError };
    icrc2_transfer_from : shared TransferFromArgs -> async { #Ok : Nat; #Err : TransferFromError };
  };

  // Same allowlist as cafresohq_state's KNOWN_LEDGERS, plus the two chain-key
  // stablecoins a marketplace price is most naturally quoted in. The plan
  // admin can add more without an upgrade (`market_admin_add_ledger`).
  let KNOWN_LEDGERS : [Text] = [
    "ryjl3-tyaaa-aaaaa-aaaba-cai",     // ICP
    "cngnf-gddge-nq2mj-vjyfl-v76et-6c2pt-xg3n3-jzihw-d3iyp-ughtf-3ae",  // ckUSDT
    "xevnm-gaaaa-aaaar-qafnq-cai",     // ckUSDC
    "mxzaz-hqaaa-aaaar-qaada-cai",     // ckBTC
    "ilzky-ayaaa-aaaar-qahha-cai",     // ckUNI
    "i2s4q-syaaa-aaaan-qz4sq-cai",     // sGLDT
    "mwen2-oqaaa-aaaam-adaca-cai",     // $nanas
  ];

  // ── Limits ────────────────────────────────────────────────────────────────

  let TITLE_MAX : Nat = 200;
  let BRIEF_MAX : Nat = 16_384;
  let BODY_MAX : Nat = 65_536;
  let SUMMARY_MAX : Nat = 500;
  let PITCH_MAX : Nat = 500;
  let NOTE_MAX : Nat = 2_000;
  let TAGS_MAX : Nat = 12;
  let TAG_MAX : Nat = 32;
  let JOBS_OPEN_PER_BOSS : Nat = 50;
  let LISTINGS_PER_OPERATOR : Nat = 10;
  let MAX_ATTEMPTS : Nat = 3;
  let DEADLINE_MIN_SECS : Nat = 300;          // 5 minutes
  let DEADLINE_MAX_SECS : Nat = 7 * 86_400;   // a week
  let ONLINE_NS : Int = 600_000_000_000;      // heartbeat within 10 min = at their desk
  let AUTO_ACCEPT_NS : Int = 7 * 86_400_000_000_000;      // a delivery ignored for a week is accepted
  let UNCLAIMED_TTL_NS : Int = 30 * 86_400_000_000_000;   // a funded job nobody takes for a month is refunded
  let POSTED_TTL_NS : Int = 7 * 86_400_000_000_000;       // an unfunded post is forgotten after a week
  let TEND_BATCH : Nat = 4;                   // ledger moves per timer tick, at most

  // ── State ─────────────────────────────────────────────────────────────────

  let natMap = OrderedMap.Make<Nat>(Nat.compare);
  let pMap = OrderedMap.Make<Principal>(Principal.compare);
  let tMap = OrderedMap.Make<Text>(Text.compare);

  stable var jobs : OrderedMap.Map<Nat, Job> = natMap.empty();
  stable var jobSeq : Nat = 0;
  stable var listings : OrderedMap.Map<Nat, Listing> = natMap.empty();
  stable var listingSeq : Nat = 0;
  stable var workerIndex : OrderedMap.Map<Principal, Nat> = pMap.empty();   // worker key → listing id
  stable var resumes : OrderedMap.Map<Nat, [ResumeEntry]> = natMap.empty(); // listing id → entries, append-only
  stable var payouts : OrderedMap.Map<Nat, [Payout]> = natMap.empty();       // job id → moves out of escrow
  stable var progress : OrderedMap.Map<Nat, Text> = natMap.empty();          // job id → worker's latest note
  stable var fundAttempt : OrderedMap.Map<Nat, Nat64> = natMap.empty();      // job id → created_at_time of the deposit
  stable var extraLedgers : OrderedMap.Map<Text, Bool> = tMap.empty();
  stable var planAdmin : ?Principal = null;
  stable var paused : Bool = false;   // admin kill switch: no new posts, funds, claims

  // ── Helpers ───────────────────────────────────────────────────────────────

  func now() : Int = Time.now();
  func nowNat64() : Nat64 = Nat64.fromIntWrap(now());

  func self() : Principal = Principal.fromActor(CafresoHQMarket);


  func isPlanAdminP(c : Principal) : Bool {
    switch (planAdmin) { case (?a) { a == c }; case null { false } };
  };

  /// Claim-or-match. Returns the refusal, or null when the caller is (now) the admin.
  func adminGate(caller : Principal) : ?Text {
    switch (planAdmin) {
      case null {
        if (not Principal.isController(caller)) { return ?"only a controller may claim plan admin" };
        planAdmin := ?caller;
        null
      };
      case (?a) { if (caller != a) { ?"only the plan admin may do that" } else { null } };
    };
  };

  func isKnownLedger(p : Principal) : Bool {
    let t = Principal.toText(p);
    for (k in KNOWN_LEDGERS.vals()) { if (k == t) { return true } };
    switch (tMap.get(extraLedgers, t)) { case (?true) { true }; case _ { false } };
  };

  func ledgerOf(p : Principal) : Ledger = actor (Principal.toText(p)) : Ledger;

  /// The escrow subaccount for a job: "mkt" then zeros then the id, 32 bytes.
  func jobSub(id : Nat) : Blob {
    let bytes = Array.tabulate<Nat8>(32, func (i : Nat) : Nat8 {
      if (i == 0) { 0x6d } else if (i == 1) { 0x6b } else if (i == 2) { 0x74 }
      else if (i >= 24) {
        let shift : Nat = (31 - i) * 8;
        Nat8.fromNat((id / (2 ** shift)) % 256)
      } else { 0 }
    });
    Blob.fromArray(bytes)
  };

  func memoOf(t : Text) : Blob = Text.encodeUtf8(t);

  /// Lower-cased, trimmed tags; null when there are too many or one is malformed.
  func cleanTags(tags : [Text]) : ?[Text] {
    if (tags.size() > TAGS_MAX) { return null };
    let out = Buffer.Buffer<Text>(tags.size());
    for (t in tags.vals()) {
      let s = Text.toLowercase(Text.trim(t, #char ' '));
      if (s.size() == 0 or s.size() > TAG_MAX) { return null };
      out.add(s);
    };
    ?Buffer.toArray(out)
  };

  func covers(have : [Text], need : [Text]) : Bool {
    for (n in need.vals()) {
      var found = false;
      for (h in have.vals()) { if (h == n) { found := true } };
      if (not found) { return false };
    };
    true
  };

  func storeJob(j : Job) { jobs := natMap.put(jobs, j.id, j) };
  func storeListing(l : Listing) { listings := natMap.put(listings, l.id, l) };

  func withUpdated(j : Job) : Job = { j with updatedAt = now() };

  func listingOfWorker(w : Principal) : ?Listing {
    switch (pMap.get(workerIndex, w)) {
      case (?lid) { natMap.get(listings, lid) };
      case null { null };
    };
  };

  func appendResume(lid : Nat, e : ResumeEntry) {
    let prev = switch (natMap.get(resumes, lid)) { case (?xs) { xs }; case null { [] } };
    resumes := natMap.put(resumes, lid, Array.append<ResumeEntry>(prev, [e]));
  };

  func resumeStats(lid : Nat) : ResumeStats {
    let entries = switch (natMap.get(resumes, lid)) { case (?xs) { xs }; case null { [] } };
    var done = 0; var failed = 0; var disputes = 0; var rehires = 0;
    var rsum = 0; var rcount = 0; var last : Int = 0;
    var bosses : OrderedMap.Map<Principal, Bool> = pMap.empty();
    for (e in entries.vals()) {
      if (e.outcome == "done") {
        done += 1;
        if (pMap.contains(bosses, e.boss)) { rehires += 1 };
        bosses := pMap.put(bosses, e.boss, true);
      } else if (e.outcome == "snag") { failed += 1 }
      else if (e.outcome == "disputed" or e.outcome == "refunded") { disputes += 1 };
      if (e.rating > 0) { rsum += e.rating; rcount += 1 };
      if (e.at > last) { last := e.at };
    };
    { jobsDone = done; jobsFailed = failed; disputes; bosses = pMap.size(bosses);
      rehires; ratingSum = rsum; ratingCount = rcount; lastActive = last }
  };

  func recordPayout(p : Payout) {
    let prev = switch (natMap.get(payouts, p.jobId)) { case (?xs) { xs }; case null { [] } };
    payouts := natMap.put(payouts, p.jobId, Array.append<Payout>(prev, [p]));
  };

  func settlePayout(jobId : Nat, key : Text, status : Text, block : ?Nat) {
    let prev = switch (natMap.get(payouts, jobId)) { case (?xs) { xs }; case null { [] } };
    payouts := natMap.put(payouts, jobId, Array.map<Payout, Payout>(prev, func (p : Payout) : Payout {
      if (p.key == key) { { p with status; blockIndex = block; ts = now() } } else { p }
    }));
  };

  func openJobsOf(boss : Principal) : Nat {
    var n = 0;
    for ((_, j) in natMap.entries(jobs)) {
      if (j.boss == boss) {
        switch (j.status) {
          case (#posted or #funded or #claimed or #delivered or #disputed) { n += 1 };
          case _ {};
        };
      };
    };
    n
  };

  func canSee(caller : Principal, j : Job) : Bool {
    if (caller == j.boss) { return true };
    switch (j.worker) { case (?w) { if (w == caller) { return true } }; case null {} };
    switch (j.workerListing) {
      case (?lid) {
        switch (natMap.get(listings, lid)) {
          case (?l) { if (l.operator == caller) { return true } };
          case null {};
        };
      };
      case null {};
    };
    isPlanAdminP(caller)
  };

  /// Move `amount` out of the job's escrow subaccount. State is written before
  /// the await; a known failure restores it, an unknown trap does not.
  func moveOut(j : Job, key : Text, to : Account, amount : Nat, nextStatus : JobStatus, note : Text) : async MoneyResult {
    // Two guards against paying twice. The caller's `j` may be a snapshot
    // taken before an await (the timer walks the map, then awaits a ledger)
    // while the boss accepted in between: re-read, and refuse if the row
    // moved. And a payout key that already went out — or is still in the
    // unknown — is never issued a second time with a fresh created_at_time;
    // that path is `retryPayout`, which reuses the old one so the ledger can
    // say #Duplicate.
    switch (natMap.get(jobs, j.id)) {
      case (?cur) { if (cur.status != j.status or cur.escrowed != j.escrowed) { return #err("the job changed while this was in flight — reload and try again") } };
      case null { return #err("job vanished") };
    };
    for (p in (switch (natMap.get(payouts, j.id)) { case (?xs) { xs }; case null { [] } }).vals()) {
      if (p.key == key and p.status != "paid" and not Text.startsWith(p.status, #text "failed:")) {
        return #err("that payout is already in flight (" # p.status # ")");
      };
      if (p.key == key and p.status == "paid") { return #duplicate({ block = switch (p.blockIndex) { case (?b) { b }; case null { 0 } } }) };
      if (p.key == key and Text.startsWith(p.status, #text "failed:unknown")) {
        return #err("that payout ended in the unknown — use retryPayout, which reuses its created_at_time");
      };
    };
    if (amount + j.fee > j.escrowed) { return #err("escrow short: " # Nat.toText(j.escrowed) # " held") };
    let scheduledAt = now();
    let held = j.escrowed;
    storeJob(withUpdated({ j with escrowed = held - amount - j.fee; status = nextStatus; note }));
    recordPayout({
      key; jobId = j.id; to = to.owner; toSub = to.subaccount; amount;
      scheduledAt; status = "pending"; blockIndex = null; ts = scheduledAt;
    });
    let ledger = ledgerOf(j.ledger);
    let args : TransferArgs = {
      from_subaccount = ?jobSub(j.id); to; amount; fee = ?j.fee;
      memo = ?memoOf("mkt:" # key); created_at_time = ?Nat64.fromIntWrap(scheduledAt);
    };
    try {
      switch (await ledger.icrc1_transfer(args)) {
        case (#Ok(block)) { settlePayout(j.id, key, "paid", ?block); #ok({ block }) };
        case (#Err(#Duplicate({ duplicate_of }))) { settlePayout(j.id, key, "paid", ?duplicate_of); #duplicate({ block = duplicate_of }) };
        case (#Err(e)) {
          let reason = transferErr(e);
          // Known refusal: nothing moved. Put the escrow back so a retry can try again.
          switch (natMap.get(jobs, j.id)) {
            case (?cur) { storeJob(withUpdated({ cur with escrowed = held; status = j.status })) };
            case null {};
          };
          settlePayout(j.id, key, "failed:" # reason, null);
          #err(reason)
        };
      };
    } catch (e) {
      // Unknown outcome (the ledger trapped or the call never returned). The
      // funds may or may not have moved; never restore. The record says so
      // and `retryPayout` can re-issue with the SAME created_at_time, which
      // the ledger dedups.
      settlePayout(j.id, key, "failed:unknown " # Error.message(e), null);
      #err("ledger call failed: " # Error.message(e))
    }
  };

  func transferErr(e : TransferError) : Text {
    switch (e) {
      case (#BadFee({ expected_fee })) { "bad fee, ledger expects " # Nat.toText(expected_fee) };
      case (#BadBurn(_)) { "bad burn" };
      case (#InsufficientFunds({ balance })) { "insufficient funds in escrow (" # Nat.toText(balance) # ")" };
      case (#TooOld) { "too old" };
      case (#CreatedInFuture(_)) { "created in future" };
      case (#Duplicate(_)) { "duplicate" };
      case (#TemporarilyUnavailable) { "ledger temporarily unavailable" };
      case (#GenericError({ message })) { message };
    }
  };

  func transferFromErr(e : TransferFromError) : Text {
    switch (e) {
      case (#BadFee({ expected_fee })) { "bad fee, ledger expects " # Nat.toText(expected_fee) };
      case (#BadBurn(_)) { "bad burn" };
      case (#InsufficientFunds({ balance })) { "insufficient funds (balance " # Nat.toText(balance) # ")" };
      case (#InsufficientAllowance({ allowance })) { "insufficient allowance (" # Nat.toText(allowance) # ") — approve the hiring hall for price + fee first" };
      case (#TooOld) { "too old" };
      case (#CreatedInFuture(_)) { "created in future" };
      case (#Duplicate(_)) { "duplicate" };
      case (#TemporarilyUnavailable) { "ledger temporarily unavailable" };
      case (#GenericError({ message })) { message };
    }
  };

  func refundBoss(j : Job, nextStatus : JobStatus, note : Text) : async MoneyResult {
    if (j.escrowed == 0) {
      storeJob(withUpdated({ j with status = nextStatus; note }));
      return #ok({ block = 0 });
    };
    await moveOut(j, Nat.toText(j.id) # "#refund", { owner = j.boss; subaccount = null }, j.price, nextStatus, note)
  };

  func payWorker(j : Job, note : Text, rating : Nat) : async MoneyResult {
    let lid = switch (j.workerListing) { case (?l) { l }; case null { return #err("no listing on this job") } };
    let l = switch (natMap.get(listings, lid)) { case (?l) { l }; case null { return #err("listing is gone") } };
    let r = await moveOut(j, Nat.toText(j.id) # "#release", { owner = l.operator; subaccount = l.payoutSub }, j.price, #accepted, note);
    switch (r) {
      case (#ok(_) or #duplicate(_)) {
        appendResume(lid, { at = now(); jobId = j.id; kind = j.kind; outcome = "done"; boss = j.boss; earned = j.price; ledger = j.ledger; rating });
      };
      case (#err(_)) {};
    };
    r
  };

  // ── Boss: post, fund, cancel, accept, reject ──────────────────────────────

  public shared (msg) func postJob(req : PostJobReq) : async Result {
    if (Principal.isAnonymous(msg.caller)) { throw Error.reject("sign in") };
    if (paused) { return #err("the hiring hall is paused right now") };
    if (req.title.size() == 0 or req.title.size() > TITLE_MAX) { return #err("title must be 1–" # Nat.toText(TITLE_MAX) # " characters") };
    if (req.brief.size() == 0 or req.brief.size() > BRIEF_MAX) { return #err("brief must be 1–" # Nat.toText(BRIEF_MAX) # " characters") };
    if (req.kind.size() == 0 or req.kind.size() > TAG_MAX) { return #err("kind is required") };
    if (not isKnownLedger(req.ledger)) { return #err("unknown ledger") };
    if (req.price == 0) { return #err("price must be positive") };
    if (req.deadlineSecs < DEADLINE_MIN_SECS or req.deadlineSecs > DEADLINE_MAX_SECS) { return #err("deadline must be between 5 minutes and 7 days") };
    if (openJobsOf(msg.caller) >= JOBS_OPEN_PER_BOSS) { return #err("you already have " # Nat.toText(JOBS_OPEN_PER_BOSS) # " open jobs") };
    let tags = switch (cleanTags(req.tags)) { case (?t) { t }; case null { return #err("tags: at most 12, each 1–32 characters") } };
    switch (req.listing) {
      case (?lid) {
        switch (natMap.get(listings, lid)) {
          case (?l) {
            if (not l.active) { return #err("that coworker is not taking work right now") };
            if (l.ledger != req.ledger) { return #err("that coworker is paid in a different token") };
            if (req.price < l.price) { return #err("below that coworker's asking price (" # Nat.toText(l.price) # ")") };
          };
          case null { return #err("no such listing") };
        };
      };
      case null {};
    };
    jobSeq += 1;
    let t = now();
    storeJob({
      id = jobSeq; boss = msg.caller; listing = req.listing; title = req.title; brief = req.brief;
      kind = Text.toLowercase(req.kind); tags; ledger = req.ledger; price = req.price; fee = 0;
      deadlineSecs = req.deadlineSecs; status = #posted; worker = null; workerListing = null;
      claimedAt = 0; attempts = 0; deliveredAt = 0; summary = ""; body = ""; bodySha256 = "";
      rating = 0; note = ""; escrowed = 0; createdAt = t; updatedAt = t;
    });
    #ok(jobSeq)
  };

  /// Pull price + fee from the boss's account under an ICRC-2 allowance they
  /// signed for THIS canister. Safe to retry: the same job reuses the same
  /// created_at_time, so the ledger answers a replay with #Duplicate.
  public shared (msg) func fundJob(id : Nat) : async MoneyResult {
    if (Principal.isAnonymous(msg.caller)) { throw Error.reject("sign in") };
    if (paused) { return #err("the hiring hall is paused right now") };
    let j = switch (natMap.get(jobs, id)) { case (?j) { j }; case null { return #err("no such job") } };
    if (j.boss != msg.caller) { return #err("not your job") };
    if (j.status != #posted) { return #err("this job is already funded") };
    let ledger = ledgerOf(j.ledger);
    let fee = try { await ledger.icrc1_fee() } catch (e) { return #err("could not read the ledger fee: " # Error.message(e)) };
    let createdAt : Nat64 = switch (natMap.get(fundAttempt, id)) {
      case (?t) { t };
      case null { let t = nowNat64(); fundAttempt := natMap.put(fundAttempt, id, t); t };
    };
    let args : TransferFromArgs = {
      spender_subaccount = null;
      from = { owner = j.boss; subaccount = null };
      to = { owner = self(); subaccount = ?jobSub(id) };
      amount = j.price + fee; fee = null;
      memo = ?memoOf("mkt:" # Nat.toText(id) # "#fund");
      created_at_time = ?createdAt;
    };
    let outcome = try { await ledger.icrc2_transfer_from(args) } catch (e) {
      return #err("ledger call failed: " # Error.message(e))
    };
    // Re-read: the job may have moved while we awaited.
    let cur = switch (natMap.get(jobs, id)) { case (?c) { c }; case null { return #err("job vanished") } };
    switch (outcome) {
      case (#Ok(block)) {
        storeJob(withUpdated({ cur with status = #funded; fee; escrowed = j.price + fee }));
        #ok({ block })
      };
      case (#Err(#Duplicate({ duplicate_of }))) {
        if (cur.status == #posted) { storeJob(withUpdated({ cur with status = #funded; fee; escrowed = j.price + fee })) };
        #duplicate({ block = duplicate_of })
      };
      case (#Err(#TooOld)) {
        // The remembered created_at_time aged out of the ledger's dedup window
        // without a deposit landing; forget it so the next try uses a fresh one.
        fundAttempt := natMap.delete(fundAttempt, id);
        #err("the deposit attempt expired — try funding again")
      };
      case (#Err(e)) { #err(transferFromErr(e)) };
    }
  };

  public shared (msg) func cancelJob(id : Nat, reason : Text) : async MoneyResult {
    if (Principal.isAnonymous(msg.caller)) { throw Error.reject("sign in") };
    let j = switch (natMap.get(jobs, id)) { case (?j) { j }; case null { return #err("no such job") } };
    if (j.boss != msg.caller) { return #err("not your job") };
    if (reason.size() > NOTE_MAX) { return #err("reason too long") };
    switch (j.status) {
      case (#posted) { storeJob(withUpdated({ j with status = #cancelled; note = reason })); #ok({ block = 0 }) };
      case (#funded) { await refundBoss(j, #cancelled, reason) };
      case (#claimed) { #err("a coworker is on this job — wait for the delivery, then accept or reject it") };
      case (#delivered) { #err("this job has been delivered — accept or reject it instead") };
      case (#failed) { #err("this job already failed — its refund goes out on the next sweep") };
      case _ { #err("this job is already closed") };
    }
  };

  public shared (msg) func acceptDelivery(id : Nat, rating : Nat) : async MoneyResult {
    if (Principal.isAnonymous(msg.caller)) { throw Error.reject("sign in") };
    let j = switch (natMap.get(jobs, id)) { case (?j) { j }; case null { return #err("no such job") } };
    if (j.boss != msg.caller) { return #err("not your job") };
    if (j.status != #delivered) { return #err("nothing has been delivered yet") };
    if (rating > 5) { return #err("rating is 0–5") };
    await payWorker({ j with rating }, "accepted by the boss", rating)
  };

  public shared (msg) func rejectDelivery(id : Nat, reason : Text) : async Result {
    if (Principal.isAnonymous(msg.caller)) { throw Error.reject("sign in") };
    let j = switch (natMap.get(jobs, id)) { case (?j) { j }; case null { return #err("no such job") } };
    if (j.boss != msg.caller) { return #err("not your job") };
    if (j.status != #delivered) { return #err("nothing has been delivered yet") };
    if (reason.size() == 0 or reason.size() > NOTE_MAX) { return #err("say why, in up to " # Nat.toText(NOTE_MAX) # " characters") };
    storeJob(withUpdated({ j with status = #disputed; note = reason }));
    switch (j.workerListing) {
      case (?lid) { appendResume(lid, { at = now(); jobId = j.id; kind = j.kind; outcome = "disputed"; boss = j.boss; earned = 0; ledger = j.ledger; rating = 0 }) };
      case null {};
    };
    #ok(id)
  };

  /// Re-issue a payout whose ledger call ended in the unknown. Same key and
  /// created_at_time, so a move that did land is answered with #Duplicate.
  public shared (msg) func retryPayout(id : Nat, key : Text) : async MoneyResult {
    if (Principal.isAnonymous(msg.caller)) { throw Error.reject("sign in") };
    let j = switch (natMap.get(jobs, id)) { case (?j) { j }; case null { return #err("no such job") } };
    if (not canSee(msg.caller, j)) { return #err("not your job") };
    let rows = switch (natMap.get(payouts, id)) { case (?xs) { xs }; case null { [] } };
    var found : ?Payout = null;
    for (p in rows.vals()) { if (p.key == key) { found := ?p } };
    let p = switch (found) { case (?p) { p }; case null { return #err("no such payout") } };
    if (p.status == "paid") { return #err("already paid") };
    let ledger = ledgerOf(j.ledger);
    let args : TransferArgs = {
      from_subaccount = ?jobSub(id); to = { owner = p.to; subaccount = p.toSub }; amount = p.amount; fee = ?j.fee;
      memo = ?memoOf("mkt:" # key); created_at_time = ?Nat64.fromIntWrap(p.scheduledAt);
    };
    let out = try { await ledger.icrc1_transfer(args) } catch (e) { return #err("ledger call failed: " # Error.message(e)) };
    switch (out) {
      case (#Ok(block)) { settlePayout(id, key, "paid", ?block); #ok({ block }) };
      case (#Err(#Duplicate({ duplicate_of }))) { settlePayout(id, key, "paid", ?duplicate_of); #duplicate({ block = duplicate_of }) };
      case (#Err(#TooOld)) {
        // Past the dedup window and never landed: the escrow is still here.
        // Re-schedule with a fresh time.
        let fresh = now();
        let rows2 = Array.map<Payout, Payout>(rows, func (q : Payout) : Payout { if (q.key == key) { { q with scheduledAt = fresh; ts = fresh } } else { q } });
        payouts := natMap.put(payouts, id, rows2);
        let out2 = try { await ledger.icrc1_transfer({ args with created_at_time = ?Nat64.fromIntWrap(fresh) }) } catch (e) { return #err("ledger call failed: " # Error.message(e)) };
        switch (out2) {
          case (#Ok(block)) { settlePayout(id, key, "paid", ?block); #ok({ block }) };
          case (#Err(e)) { let r = transferErr(e); settlePayout(id, key, "failed:" # r, null); #err(r) };
        }
      };
      case (#Err(e)) { let r = transferErr(e); settlePayout(id, key, "failed:" # r, null); #err(r) };
    }
  };

  public shared query (msg) func myJobs() : async [Job] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    let out = Buffer.Buffer<Job>(8);
    for ((_, j) in natMap.entries(jobs)) { if (j.boss == msg.caller) { out.add(j) } };
    Buffer.toArray(out)
  };

  public shared query (msg) func getJob(id : Nat) : async ?Job {
    if (Principal.isAnonymous(msg.caller)) { return null };
    switch (natMap.get(jobs, id)) {
      case (?j) { if (canSee(msg.caller, j)) { ?j } else { null } };
      case null { null };
    }
  };

  public shared query (msg) func jobPayouts(id : Nat) : async [Payout] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    switch (natMap.get(jobs, id)) {
      case (?j) { if (canSee(msg.caller, j)) { switch (natMap.get(payouts, id)) { case (?xs) { xs }; case null { [] } } } else { [] } };
      case null { [] };
    }
  };

  public shared query (msg) func jobProgress(id : Nat) : async ?Text {
    if (Principal.isAnonymous(msg.caller)) { return null };
    switch (natMap.get(jobs, id)) {
      case (?j) { if (canSee(msg.caller, j)) { natMap.get(progress, id) } else { null } };
      case null { null };
    }
  };

  /// The one public read. No brief, no body: status and a one-line summary,
  /// so a container that posted a job through its boss's browser can poll
  /// it without any credential.
  public query func jobStatus(id : Nat) : async ?PublicStatus {
    switch (natMap.get(jobs, id)) {
      case (?j) { ?{ id = j.id; status = j.status; summary = j.summary; workerListing = j.workerListing;
                     claimedAt = j.claimedAt; deliveredAt = j.deliveredAt; updatedAt = j.updatedAt } };
      case null { null };
    }
  };

  // ── Operator: list a coworker, link its key ───────────────────────────────

  public shared (msg) func putListing(req : PutListingReq) : async Result {
    if (Principal.isAnonymous(msg.caller)) { throw Error.reject("sign in") };
    if (req.name.size() == 0 or req.name.size() > 80) { return #err("name must be 1–80 characters") };
    if (req.role.size() > 80 or req.brain.size() > 80) { return #err("role and brain are 80 characters at most") };
    if (req.pitch.size() > PITCH_MAX) { return #err("pitch is " # Nat.toText(PITCH_MAX) # " characters at most") };
    if (not isKnownLedger(req.ledger)) { return #err("unknown ledger") };
    if (req.price == 0) { return #err("asking price must be positive") };
    switch (req.payoutSub) { case (?s) { if (s.size() != 32) { return #err("payout subaccount must be 32 bytes") } }; case null {} };
    let tags = switch (cleanTags(req.tags)) { case (?t) { t }; case null { return #err("tags: at most 12, each 1–32 characters") } };
    let t = now();
    switch (req.id) {
      case (?id) {
        let l = switch (natMap.get(listings, id)) { case (?l) { l }; case null { return #err("no such listing") } };
        if (l.operator != msg.caller) { return #err("not your listing") };
        storeListing({ l with name = req.name; role = req.role; pitch = req.pitch; brain = req.brain; tags;
                     ledger = req.ledger; price = req.price; payoutSub = req.payoutSub; active = req.active; updatedAt = t });
        #ok(id)
      };
      case null {
        var mine = 0;
        for ((_, l) in natMap.entries(listings)) { if (l.operator == msg.caller) { mine += 1 } };
        if (mine >= LISTINGS_PER_OPERATOR) { return #err("you already list " # Nat.toText(LISTINGS_PER_OPERATOR) # " coworkers") };
        listingSeq += 1;
        storeListing({ id = listingSeq; operator = msg.caller; worker = null; name = req.name; role = req.role;
                     pitch = req.pitch; brain = req.brain; tags; ledger = req.ledger; price = req.price;
                     payoutSub = req.payoutSub; active = req.active; lastSeen = 0; createdAt = t; updatedAt = t });
        #ok(listingSeq)
      };
    }
  };

  /// Link the coworker's own key. One key serves one listing; relinking moves it.
  public shared (msg) func linkWorker(id : Nat, worker : Principal) : async Result {
    if (Principal.isAnonymous(msg.caller)) { throw Error.reject("sign in") };
    if (Principal.isAnonymous(worker)) { return #err("that is the anonymous principal") };
    if (worker == msg.caller) { return #err("the worker key must be the coworker's own key, not your identity") };
    let l = switch (natMap.get(listings, id)) { case (?l) { l }; case null { return #err("no such listing") } };
    if (l.operator != msg.caller) { return #err("not your listing") };
    switch (pMap.get(workerIndex, worker)) {
      case (?other) {
        if (other != id) {
          switch (natMap.get(listings, other)) {
            case (?ol) { if (ol.operator != msg.caller) { return #err("that key already works for someone else") };
                         storeListing({ ol with worker = null; updatedAt = now() }) };
            case null {};
          };
        };
      };
      case null {};
    };
    switch (l.worker) { case (?old) { if (old != worker) { workerIndex := pMap.delete(workerIndex, old) } }; case null {} };
    workerIndex := pMap.put(workerIndex, worker, id);
    storeListing({ l with worker = ?worker; updatedAt = now() });
    #ok(id)
  };

  public shared (msg) func unlinkWorker(id : Nat) : async Result {
    if (Principal.isAnonymous(msg.caller)) { throw Error.reject("sign in") };
    let l = switch (natMap.get(listings, id)) { case (?l) { l }; case null { return #err("no such listing") } };
    if (l.operator != msg.caller) { return #err("not your listing") };
    switch (l.worker) { case (?w) { workerIndex := pMap.delete(workerIndex, w) }; case null {} };
    storeListing({ l with worker = null; active = false; updatedAt = now() });
    #ok(id)
  };

  public shared query (msg) func myListings() : async [Listing] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    let out = Buffer.Buffer<Listing>(4);
    for ((_, l) in natMap.entries(listings)) { if (l.operator == msg.caller) { out.add(l) } };
    Buffer.toArray(out)
  };

  /// Jobs on the caller's listings (as operator).
  public shared query (msg) func operatorJobs() : async [Job] {
    if (Principal.isAnonymous(msg.caller)) { return [] };
    let out = Buffer.Buffer<Job>(8);
    for ((_, j) in natMap.entries(jobs)) {
      switch (j.workerListing) {
        case (?lid) { switch (natMap.get(listings, lid)) { case (?l) { if (l.operator == msg.caller) { out.add(j) } }; case null {} } };
        case null {};
      };
    };
    Buffer.toArray(out)
  };

  // ── Public reads ──────────────────────────────────────────────────────────

  public query func browseListings(offset : Nat, limit : Nat) : async [ListingCard] {
    let cap = if (limit == 0 or limit > 100) { 100 } else { limit };
    let out = Buffer.Buffer<ListingCard>(cap);
    var i = 0;
    let t = now();
    for ((_, l) in natMap.entries(listings)) {
      if (l.active and l.worker != null) {
        if (i >= offset and out.size() < cap) {
          out.add({ listing = l; resume = resumeStats(l.id); online = (t - l.lastSeen) < ONLINE_NS });
        };
        i += 1;
      };
    };
    Buffer.toArray(out)
  };

  public query func getListing(id : Nat) : async ?ListingCard {
    switch (natMap.get(listings, id)) {
      case (?l) { ?{ listing = l; resume = resumeStats(id); online = (now() - l.lastSeen) < ONLINE_NS } };
      case null { null };
    }
  };

  public query func getResume(id : Nat) : async [ResumeEntry] {
    switch (natMap.get(resumes, id)) { case (?xs) { xs }; case null { [] } }
  };

  public query func marketStats() : async { listings : Nat; active : Nat; jobs : Nat; open : Nat; paid : Nat; escrowed : Nat } {
    var active = 0; var open = 0; var paid = 0; var held = 0;
    for ((_, l) in natMap.entries(listings)) { if (l.active and l.worker != null) { active += 1 } };
    for ((_, j) in natMap.entries(jobs)) {
      switch (j.status) { case (#funded or #claimed or #delivered) { open += 1 }; case (#accepted) { paid += 1 }; case _ {} };
      held += j.escrowed;
    };
    { listings = natMap.size(listings); active; jobs = natMap.size(jobs); open; paid; escrowed = held }
  };

  public query func planConfigured() : async Bool = async (planAdmin != null);

  public query func cycle_balance() : async Nat = async ExperimentalCycles.balance();

  // ── Worker: poll, claim, progress, deliver, fail ──────────────────────────

  public shared query (msg) func workerPoll() : async [JobOffer] {
    let l = switch (listingOfWorker(msg.caller)) { case (?l) { l }; case null { return [] } };
    if (not l.active) { return [] };
    let out = Buffer.Buffer<JobOffer>(4);
    for ((_, j) in natMap.entries(jobs)) {
      if (j.status == #funded) {
        let mine = switch (j.listing) { case (?lid) { lid == l.id }; case null { covers(l.tags, j.tags) and j.ledger == l.ledger and j.price >= l.price } };
        if (mine) {
          out.add({ id = j.id; title = j.title; brief = j.brief; kind = j.kind; tags = j.tags; ledger = j.ledger;
                    price = j.price; deadlineSecs = j.deadlineSecs; listing = j.listing; createdAt = j.createdAt });
        };
      };
    };
    Buffer.toArray(out)
  };

  public shared (msg) func workerHeartbeat() : async Bool {
    switch (listingOfWorker(msg.caller)) {
      case (?l) { storeListing({ l with lastSeen = now() }); true };
      case null { false };
    }
  };

  public shared (msg) func claimJob(id : Nat) : async Result {
    if (paused) { return #err("the hiring hall is paused right now") };
    let l = switch (listingOfWorker(msg.caller)) { case (?l) { l }; case null { return #err("this key is not linked to a listing") } };
    if (not l.active) { return #err("your listing is not active") };
    let j = switch (natMap.get(jobs, id)) { case (?j) { j }; case null { return #err("no such job") } };
    if (j.status != #funded) { return #err("this job is not open") };
    let allowed = switch (j.listing) { case (?lid) { lid == l.id }; case null { covers(l.tags, j.tags) and j.ledger == l.ledger and j.price >= l.price } };
    if (not allowed) { return #err("this job is not for your listing") };
    let t = now();
    storeJob({ j with status = #claimed; worker = ?msg.caller; workerListing = ?l.id; claimedAt = t; updatedAt = t });
    storeListing({ l with lastSeen = t });
    #ok(id)
  };

  public shared (msg) func progressJob(id : Nat, note : Text) : async Result {
    let j = switch (natMap.get(jobs, id)) { case (?j) { j }; case null { return #err("no such job") } };
    if (j.worker != ?msg.caller or j.status != #claimed) { return #err("not your claim") };
    if (note.size() > SUMMARY_MAX) { return #err("note too long") };
    progress := natMap.put(progress, id, note);
    storeJob(withUpdated(j));
    switch (listingOfWorker(msg.caller)) { case (?l) { storeListing({ l with lastSeen = now() }) }; case null {} };
    #ok(id)
  };

  public shared (msg) func deliverJob(id : Nat, summary : Text, body : Text, bodySha256 : Text) : async Result {
    let j = switch (natMap.get(jobs, id)) { case (?j) { j }; case null { return #err("no such job") } };
    if (j.worker != ?msg.caller or j.status != #claimed) { return #err("not your claim") };
    if (summary.size() == 0 or summary.size() > SUMMARY_MAX) { return #err("summary must be 1–" # Nat.toText(SUMMARY_MAX) # " characters") };
    if (body.size() > BODY_MAX) { return #err("deliverable is over " # Nat.toText(BODY_MAX) # " characters — publish it and deliver the link") };
    if (bodySha256.size() != 64) { return #err("bodySha256 must be 64 hex characters") };
    let t = now();
    storeJob({ j with status = #delivered; summary; body; bodySha256; deliveredAt = t; updatedAt = t });
    switch (listingOfWorker(msg.caller)) { case (?l) { storeListing({ l with lastSeen = t }) }; case null {} };
    #ok(id)
  };

  public shared (msg) func failJob(id : Nat, reason : Text) : async Result {
    let j = switch (natMap.get(jobs, id)) { case (?j) { j }; case null { return #err("no such job") } };
    if (j.worker != ?msg.caller or j.status != #claimed) { return #err("not your claim") };
    if (reason.size() > NOTE_MAX) { return #err("reason too long") };
    releaseClaim(j, reason);
    #ok(id)
  };

  /// A claim that ended without a delivery: back to the board, one attempt
  /// spent, a snag on the résumé. The third snag fails the job (refund on
  /// the next tend).
  func releaseClaim(j : Job, reason : Text) {
    switch (j.workerListing) {
      case (?lid) { appendResume(lid, { at = now(); jobId = j.id; kind = j.kind; outcome = "snag"; boss = j.boss; earned = 0; ledger = j.ledger; rating = 0 }) };
      case null {};
    };
    let attempts = j.attempts + 1;
    let next : JobStatus = if (attempts >= MAX_ATTEMPTS) { #failed } else { #funded };
    storeJob(withUpdated({ j with status = next; worker = null; workerListing = null; claimedAt = 0; attempts; note = reason }));
    progress := natMap.delete(progress, j.id);
  };

  // ── Admin ─────────────────────────────────────────────────────────────────

  public shared (msg) func market_admin_claim() : async Bool {
    switch (adminGate(msg.caller)) { case (?e) { throw Error.reject(e) }; case null {} };
    true
  };

  public shared (msg) func market_admin_pause(p : Bool) : async () {
    switch (adminGate(msg.caller)) { case (?e) { throw Error.reject(e) }; case null {} };
    paused := p;
  };

  public shared (msg) func market_admin_add_ledger(p : Principal) : async () {
    switch (adminGate(msg.caller)) { case (?e) { throw Error.reject(e) }; case null {} };
    extraLedgers := tMap.put(extraLedgers, Principal.toText(p), true);
  };

  /// Rule on a disputed job. `#split(n)` pays the worker n% and refunds the rest.
  public shared (msg) func resolveDispute(id : Nat, ruling : Ruling, note : Text) : async MoneyResult {
    switch (adminGate(msg.caller)) { case (?e) { throw Error.reject(e) }; case null {} };
    let j = switch (natMap.get(jobs, id)) { case (?j) { j }; case null { return #err("no such job") } };
    if (j.status != #disputed) { return #err("this job is not in dispute") };
    if (note.size() > NOTE_MAX) { return #err("note too long") };
    switch (ruling) {
      case (#payWorker) { await payWorker(j, "ruled for the coworker: " # note, 0) };
      case (#refundBoss) {
        switch (j.workerListing) {
          case (?lid) { appendResume(lid, { at = now(); jobId = j.id; kind = j.kind; outcome = "refunded"; boss = j.boss; earned = 0; ledger = j.ledger; rating = 0 }) };
          case null {};
        };
        await refundBoss(j, #refunded, "ruled for the boss: " # note)
      };
      case (#split(pct)) {
        if (pct == 0 or pct >= 100) { return #err("split is 1–99 percent") };
        let lid = switch (j.workerListing) { case (?l) { l }; case null { return #err("no listing on this job") } };
        let l = switch (natMap.get(listings, lid)) { case (?l) { l }; case null { return #err("listing is gone") } };
        // Two moves, two fees: the worker's share is net of one fee, the
        // boss's remainder net of the other. Both ride in what is held.
        let workerAmt = (j.price * pct) / 100;
        let held = j.escrowed;
        if (held < workerAmt + 2 * j.fee) { return #err("escrow short") };
        let r1 = await moveOut(j, Nat.toText(j.id) # "#split-w", { owner = l.operator; subaccount = l.payoutSub }, workerAmt, #disputed, "split ruling: " # note);
        switch (r1) { case (#err(e)) { return #err(e) }; case _ {} };
        let cur = switch (natMap.get(jobs, id)) { case (?c) { c }; case null { return #err("job vanished") } };
        let bossAmt : Nat = if (cur.escrowed > j.fee) { cur.escrowed - j.fee } else { 0 };
        appendResume(lid, { at = now(); jobId = j.id; kind = j.kind; outcome = "done"; boss = j.boss; earned = workerAmt; ledger = j.ledger; rating = 0 });
        if (bossAmt == 0) { storeJob(withUpdated({ cur with status = #accepted })); return r1 };
        await moveOut(cur, Nat.toText(j.id) # "#split-b", { owner = j.boss; subaccount = null }, bossAmt, #accepted, "split ruling: " # note)
      };
    }
  };

  public shared query (msg) func amPlanAdmin() : async Bool = async isPlanAdminP(msg.caller);

  // ── Timer: leases, ghosted deliveries, stale posts ────────────────────────

  func tend() : async () {
    let t = now();
    var moves = 0;
    for ((_, j) in natMap.entries(jobs)) {
      if (moves >= TEND_BATCH) { return };
      switch (j.status) {
        case (#claimed) {
          if (t - j.claimedAt > j.deadlineSecs * 1_000_000_000) {
            releaseClaim(j, "the deadline passed without a delivery");
          };
        };
        case (#delivered) {
          if (t - j.deliveredAt > AUTO_ACCEPT_NS) {
            moves += 1;
            ignore await payWorker(j, "accepted: the boss did not answer within a week", 0);
          };
        };
        case (#failed) {
          if (j.escrowed > 0) { moves += 1; ignore await refundBoss(j, #refunded, j.note) };
        };
        case (#funded) {
          if (t - j.updatedAt > UNCLAIMED_TTL_NS) {
            moves += 1;
            ignore await refundBoss(j, #cancelled, "nobody took this job in a month");
          };
        };
        case (#posted) {
          if (t - j.createdAt > POSTED_TTL_NS) { storeJob(withUpdated({ j with status = #cancelled; note = "never funded" })) };
        };
        case _ {};
      };
    };
  };

  ignore Timer.recurringTimer<system>(#seconds 60, tend);   // MUST be the last declaration
};
