/// mock_ledger.mo — a stand-in ICRC-1 / ICRC-2 ledger for the replica
/// harness, so the hiring hall's escrow can be exercised end to end on a
/// local replica with no real token. It keeps the parts of the standard the
/// hall's money path depends on, with the real ledger's semantics:
///
///   * a flat fee (icrc1_fee) charged to the sender on every move;
///   * icrc2_transfer_from needs an allowance of at least amount + fee and
///     reduces it by that much — the detail that decides whether a boss's
///     one signed allowance is enough (see the harness test);
///   * dedup by created_at_time within a 24h window → #Duplicate, so the
///     hall's "same created_at_time on retry" discipline is really tested;
///   * #TooOld / #CreatedInFuture, #BadFee, #InsufficientFunds,
///     #InsufficientAllowance, #Expired, #AllowanceChanged.
///
/// `mint` is the faucet: anyone may mint to any account. This canister is
/// for the local harness only and is never deployed anywhere else.
import Array "mo:base/Array";
import Blob "mo:base/Blob";
import HashMap "mo:base/HashMap";
import Int "mo:base/Int";
import Nat "mo:base/Nat";
import Nat64 "mo:base/Nat64";
import Nat8 "mo:base/Nat8";
import Principal "mo:base/Principal";
import Text "mo:base/Text";
import Time "mo:base/Time";

actor MockLedger {
  public type Account = { owner : Principal; subaccount : ?Blob };
  public type TransferArgs = {
    from_subaccount : ?Blob; to : Account; amount : Nat; fee : ?Nat;
    memo : ?Blob; created_at_time : ?Nat64;
  };
  public type TransferError = {
    #BadFee : { expected_fee : Nat }; #BadBurn : { min_burn_amount : Nat };
    #InsufficientFunds : { balance : Nat }; #TooOld;
    #CreatedInFuture : { ledger_time : Nat64 }; #Duplicate : { duplicate_of : Nat };
    #TemporarilyUnavailable; #GenericError : { error_code : Nat; message : Text };
  };
  public type TransferFromArgs = {
    spender_subaccount : ?Blob; from : Account; to : Account; amount : Nat;
    fee : ?Nat; memo : ?Blob; created_at_time : ?Nat64;
  };
  public type TransferFromError = {
    #BadFee : { expected_fee : Nat }; #BadBurn : { min_burn_amount : Nat };
    #InsufficientFunds : { balance : Nat }; #InsufficientAllowance : { allowance : Nat };
    #TooOld; #CreatedInFuture : { ledger_time : Nat64 };
    #Duplicate : { duplicate_of : Nat }; #TemporarilyUnavailable;
    #GenericError : { error_code : Nat; message : Text };
  };
  public type ApproveArgs = {
    from_subaccount : ?Blob; spender : Account; amount : Nat; expected_allowance : ?Nat;
    expires_at : ?Nat64; fee : ?Nat; memo : ?Blob; created_at_time : ?Nat64;
  };
  public type ApproveError = {
    #BadFee : { expected_fee : Nat }; #InsufficientFunds : { balance : Nat };
    #AllowanceChanged : { current_allowance : Nat }; #Expired : { ledger_time : Nat64 };
    #TooOld; #CreatedInFuture : { ledger_time : Nat64 }; #Duplicate : { duplicate_of : Nat };
    #TemporarilyUnavailable; #GenericError : { error_code : Nat; message : Text };
  };
  public type AllowanceArgs = { account : Account; spender : Account };
  public type Allowance = { allowance : Nat; expires_at : ?Nat64 };

  let FEE : Nat = 10_000;
  let WINDOW_NS : Int = 24 * 3_600 * 1_000_000_000;   // the dedup window, like the ICP ledger
  let DRIFT_NS : Int = 60 * 1_000_000_000;            // permitted clock drift into the future

  let balances = HashMap.HashMap<Text, Nat>(64, Text.equal, Text.hash);
  let allowances = HashMap.HashMap<Text, (Nat, ?Nat64)>(64, Text.equal, Text.hash);
  let seen = HashMap.HashMap<Text, Nat>(64, Text.equal, Text.hash);   // fingerprint → block
  var blocks : Nat = 0;

  func zeros() : Blob = Blob.fromArray(Array.tabulate<Nat8>(32, func _ = 0));
  func key(a : Account) : Text {
    let sub = switch (a.subaccount) { case (?b) { if (b.size() == 0) { zeros() } else { b } }; case null { zeros() } };
    Principal.toText(a.owner) # "/" # debug_show(Blob.toArray(sub))
  };
  func bal(a : Account) : Nat = switch (balances.get(key(a))) { case (?n) { n }; case null { 0 } };
  func setBal(a : Account, n : Nat) { balances.put(key(a), n) };
  func nowNs() : Int = Time.now();

  /// #TooOld / #CreatedInFuture, as the real ledger decides them.
  func timeCheck(t : ?Nat64) : ?{ #TooOld; #CreatedInFuture : { ledger_time : Nat64 } } {
    switch (t) {
      case null { null };
      case (?t) {
        let n = nowNs();
        let ct : Int = Nat64.toNat(t);
        if (ct < n - WINDOW_NS) { return ?#TooOld };
        if (ct > n + DRIFT_NS) { return ?#CreatedInFuture({ ledger_time = Nat64.fromIntWrap(n) }) };
        null
      };
    }
  };
  func fp(kind : Text, from : Account, to : Text, amount : Nat, memo : ?Blob, t : Nat64) : Text {
    kind # "|" # key(from) # "|" # to # "|" # Nat.toText(amount) # "|" # debug_show(memo) # "|" # Nat64.toText(t)
  };
  func dedup(f : Text) : ?Nat = seen.get(f);
  func remember(f : ?Text, block : Nat) { switch (f) { case (?f) { seen.put(f, block) }; case null {} } };
  func nextBlock() : Nat { let b = blocks; blocks += 1; b };

  public shared query func icrc1_fee() : async Nat = async FEE;
  public shared query func icrc1_name() : async Text = async "Mock Token";
  public shared query func icrc1_symbol() : async Text = async "MOCK";
  public shared query func icrc1_decimals() : async Nat8 = async 8;
  public shared query func icrc1_balance_of(a : Account) : async Nat = async bal(a);
  public shared query func icrc2_allowance(a : AllowanceArgs) : async Allowance {
    switch (allowances.get(key(a.account) # "|" # key(a.spender))) {
      case (?(n, exp)) {
        switch (exp) {
          case (?e) { if (Nat64.toNat(e) <= Int.abs(nowNs())) { return { allowance = 0; expires_at = null } } };
          case null {};
        };
        { allowance = n; expires_at = exp }
      };
      case null { { allowance = 0; expires_at = null } };
    }
  };

  /// The faucet. Anyone, any account.
  public shared func mint(to : Account, amount : Nat) : async Nat {
    setBal(to, bal(to) + amount);
    nextBlock()
  };

  public shared (msg) func icrc1_transfer(a : TransferArgs) : async { #Ok : Nat; #Err : TransferError } {
    let from : Account = { owner = msg.caller; subaccount = a.from_subaccount };
    switch (a.fee) { case (?f) { if (f != FEE) { return #Err(#BadFee({ expected_fee = FEE })) } }; case null {} };
    switch (timeCheck(a.created_at_time)) {
      case (?#TooOld) { return #Err(#TooOld) };
      case (?#CreatedInFuture(x)) { return #Err(#CreatedInFuture(x)) };
      case null {};
    };
    let f = switch (a.created_at_time) { case (?t) { ?fp("t", from, key(a.to), a.amount, a.memo, t) }; case null { null } };
    switch (f) { case (?f) { switch (dedup(f)) { case (?b) { return #Err(#Duplicate({ duplicate_of = b })) }; case null {} } }; case null {} };
    let have = bal(from);
    if (have < a.amount + FEE) { return #Err(#InsufficientFunds({ balance = have })) };
    setBal(from, have - a.amount - FEE);
    setBal(a.to, bal(a.to) + a.amount);
    let b = nextBlock();
    remember(f, b);
    #Ok(b)
  };

  public shared (msg) func icrc2_approve(a : ApproveArgs) : async { #Ok : Nat; #Err : ApproveError } {
    let from : Account = { owner = msg.caller; subaccount = a.from_subaccount };
    switch (a.fee) { case (?f) { if (f != FEE) { return #Err(#BadFee({ expected_fee = FEE })) } }; case null {} };
    switch (timeCheck(a.created_at_time)) {
      case (?#TooOld) { return #Err(#TooOld) };
      case (?#CreatedInFuture(x)) { return #Err(#CreatedInFuture(x)) };
      case null {};
    };
    let f = switch (a.created_at_time) { case (?t) { ?fp("a", from, key(a.spender), a.amount, a.memo, t) }; case null { null } };
    switch (f) { case (?f) { switch (dedup(f)) { case (?b) { return #Err(#Duplicate({ duplicate_of = b })) }; case null {} } }; case null {} };
    switch (a.expires_at) {
      case (?e) { if (Nat64.toNat(e) <= Int.abs(nowNs())) { return #Err(#Expired({ ledger_time = Nat64.fromIntWrap(nowNs()) })) } };
      case null {};
    };
    let k = key(from) # "|" # key(a.spender);
    let current = switch (allowances.get(k)) { case (?(n, _)) { n }; case null { 0 } };
    switch (a.expected_allowance) {
      case (?exp) { if (exp != current) { return #Err(#AllowanceChanged({ current_allowance = current })) } };
      case null {};
    };
    let have = bal(from);
    if (have < FEE) { return #Err(#InsufficientFunds({ balance = have })) };
    setBal(from, have - FEE);
    allowances.put(k, (a.amount, a.expires_at));
    let b = nextBlock();
    remember(f, b);
    #Ok(b)
  };

  public shared (msg) func icrc2_transfer_from(a : TransferFromArgs) : async { #Ok : Nat; #Err : TransferFromError } {
    let spender : Account = { owner = msg.caller; subaccount = a.spender_subaccount };
    switch (a.fee) { case (?f) { if (f != FEE) { return #Err(#BadFee({ expected_fee = FEE })) } }; case null {} };
    switch (timeCheck(a.created_at_time)) {
      case (?#TooOld) { return #Err(#TooOld) };
      case (?#CreatedInFuture(x)) { return #Err(#CreatedInFuture(x)) };
      case null {};
    };
    let f = switch (a.created_at_time) { case (?t) { ?fp("tf:" # key(spender), a.from, key(a.to), a.amount, a.memo, t) }; case null { null } };
    switch (f) { case (?f) { switch (dedup(f)) { case (?b) { return #Err(#Duplicate({ duplicate_of = b })) }; case null {} } }; case null {} };
    let k = key(a.from) # "|" # key(spender);
    let (allowance, exp) = switch (allowances.get(k)) { case (?x) { x }; case null { (0, null) } };
    let live = switch (exp) { case (?e) { Nat64.toNat(e) > Int.abs(nowNs()) }; case null { true } };
    let allowed = if (live) { allowance } else { 0 };
    // The standard: the allowance must cover amount + fee, and shrinks by that much.
    if (allowed < a.amount + FEE) { return #Err(#InsufficientAllowance({ allowance = allowed })) };
    let have = bal(a.from);
    if (have < a.amount + FEE) { return #Err(#InsufficientFunds({ balance = have })) };
    setBal(a.from, have - a.amount - FEE);
    setBal(a.to, bal(a.to) + a.amount);
    allowances.put(k, (allowed - a.amount - FEE, exp));
    let b = nextBlock();
    remember(f, b);
    #Ok(b)
  };
}
