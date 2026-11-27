/// mock_icp.mo — the ICP ledger and the cycles minting canister in one, for the replica harness
/// (scripts/test_an_owner_pays_the_factory_in_icp.py). It keeps the parts cf_factory's pay-in
/// depends on, with the real semantics:
///
///   * balances live under account identifiers, so an ICRC-1 account and its older account id are
///     the same account, as on the real ledger;
///   * `transfer` (the older call) takes a 64-bit memo and a fee, and answers #TxDuplicate for the
///     same created_at_time;
///   * `notify_top_up` mints only for a transfer to this canister's account for that canister with
///     the "TPUP" memo, deposits real cycles, and gives the same answer when asked again.
///
/// `mint` is a faucet and the `mock_*` methods make it fail on purpose. Local harness only.
import Blob "mo:base/Blob";
import Buffer "mo:base/Buffer";
import Cycles "mo:base/ExperimentalCycles";
import Error "mo:base/Error";
import HashMap "mo:base/HashMap";
import Nat "mo:base/Nat";
import Nat64 "mo:base/Nat64";
import Nat8 "mo:base/Nat8";
import Array "mo:base/Array";
import Principal "mo:base/Principal";
import Text "mo:base/Text";

actor MockIcp {
  public type Account = { owner : Principal; subaccount : ?Blob };
  type Tokens = { e8s : Nat64 };
  type Icrc1Error = {
    #BadFee : { expected_fee : Nat }; #BadBurn : { min_burn_amount : Nat };
    #InsufficientFunds : { balance : Nat }; #InsufficientAllowance : { allowance : Nat };
    #TooOld; #CreatedInFuture : { ledger_time : Nat64 }; #Duplicate : { duplicate_of : Nat };
    #TemporarilyUnavailable; #GenericError : { error_code : Nat; message : Text };
  };
  type Block = { from : Blob; to : Blob; amount : Nat; memo : Nat64 };

  let FEE : Nat = 10_000;
  let TPUP : Nat64 = 0x50555054;
  var rate : Nat = 15_197;                  // xdr_permyriad_per_icp: cycles minted per e8s
  var failNotify : Nat = 0;
  var failNotifyHow : Text = "processing";  // processing | reject | refund
  var failTransfer : Nat = 0;

  let balances = HashMap.HashMap<Blob, Nat>(64, Blob.equal, Blob.hash);
  let allowances = HashMap.HashMap<Text, Nat>(16, Text.equal, Text.hash);
  let seen = HashMap.HashMap<Text, Nat>(16, Text.equal, Text.hash);
  let minted = HashMap.HashMap<Nat, Nat>(16, Nat.equal, func(n : Nat) : Nat32 { Text.hash(Nat.toText(n)) });
  let blocks = Buffer.Buffer<Block>(16);

  let ic : actor { deposit_cycles : shared { canister_id : Principal } -> async () } = actor "aaaaa-aa";

  func aid(a : Account) : Blob { Principal.toLedgerAccount(a.owner, a.subaccount) };
  func bal(a : Blob) : Nat { switch (balances.get(a)) { case (?n) n; case null 0 } };
  func subOf(p : Principal) : Blob {
    let b = Blob.toArray(Principal.toBlob(p));
    Blob.fromArray(Array.tabulate<Nat8>(32, func(i : Nat) : Nat8 {
      if (i == 0) Nat8.fromNat(b.size()) else if (i <= b.size()) b[i - 1] else 0;
    }));
  };
  func move(from : Blob, to : Blob, amount : Nat, memo : Nat64) : Nat {
    balances.put(from, bal(from) - amount - FEE);
    balances.put(to, bal(to) + amount);
    blocks.add({ from; to; amount; memo });
    blocks.size() - 1;
  };

  // ── faucet and failure knobs ─────────────────────────────────────────────
  public func mint(to : Account, amount : Nat) : async Nat { balances.put(aid(to), bal(aid(to)) + amount); bal(aid(to)) };
  public func mock_fail_notify(times : Nat, how : Text) : async () { failNotify := times; failNotifyHow := how };
  public func mock_fail_transfer(times : Nat) : async () { failTransfer := times };
  public func mock_set_rate(r : Nat) : async () { rate := r };
  public query func mock_blocks() : async Nat { blocks.size() };

  // ── the ledger ───────────────────────────────────────────────────────────
  public query func icrc1_fee() : async Nat { FEE };
  public query func icrc1_balance_of(a : Account) : async Nat { bal(aid(a)) };

  public shared ({ caller }) func icrc1_transfer(a : {
    from_subaccount : ?Blob; to : Account; amount : Nat; fee : ?Nat; memo : ?Blob; created_at_time : ?Nat64;
  }) : async { #Ok : Nat; #Err : Icrc1Error } {
    switch (a.fee) { case (?f) { if (f != FEE) return #Err(#BadFee({ expected_fee = FEE })) }; case null {} };
    let from = aid({ owner = caller; subaccount = a.from_subaccount });
    if (bal(from) < a.amount + FEE) return #Err(#InsufficientFunds({ balance = bal(from) }));
    #Ok(move(from, aid(a.to), a.amount, 0));
  };

  public shared ({ caller }) func icrc2_approve(a : {
    from_subaccount : ?Blob; spender : Account; amount : Nat; expected_allowance : ?Nat;
    expires_at : ?Nat64; fee : ?Nat; memo : ?Blob; created_at_time : ?Nat64;
  }) : async { #Ok : Nat; #Err : Icrc1Error } {
    let from = aid({ owner = caller; subaccount = a.from_subaccount });
    if (bal(from) < FEE) return #Err(#InsufficientFunds({ balance = bal(from) }));
    balances.put(from, bal(from) - FEE);
    allowances.put(debug_show (from) # "|" # debug_show (aid(a.spender)), a.amount);
    #Ok(blocks.size());
  };

  public shared ({ caller }) func icrc2_transfer_from(a : {
    spender_subaccount : ?Blob; from : Account; to : Account; amount : Nat; fee : ?Nat; memo : ?Blob; created_at_time : ?Nat64;
  }) : async { #Ok : Nat; #Err : Icrc1Error } {
    let from = aid(a.from);
    let k = debug_show (from) # "|" # debug_show (aid({ owner = caller; subaccount = a.spender_subaccount }));
    let allowed = switch (allowances.get(k)) { case (?n) n; case null 0 };
    if (allowed < a.amount + FEE) return #Err(#InsufficientAllowance({ allowance = allowed }));
    if (bal(from) < a.amount + FEE) return #Err(#InsufficientFunds({ balance = bal(from) }));
    allowances.put(k, allowed - a.amount - FEE);
    #Ok(move(from, aid(a.to), a.amount, 0));
  };

  public shared ({ caller }) func transfer(a : {
    memo : Nat64; amount : Tokens; fee : Tokens; from_subaccount : ?Blob; to : Blob;
    created_at_time : ?{ timestamp_nanos : Nat64 };
  }) : async {
    #Ok : Nat64;
    #Err : {
      #BadFee : { expected_fee : Tokens }; #InsufficientFunds : { balance : Tokens };
      #TxTooOld : { allowed_window_nanos : Nat64 }; #TxCreatedInFuture; #TxDuplicate : { duplicate_of : Nat64 };
    };
  } {
    if (failTransfer > 0) { failTransfer -= 1; throw Error.reject("mock: the ledger is busy") };
    if (Nat64.toNat(a.fee.e8s) != FEE) return #Err(#BadFee({ expected_fee = { e8s = Nat64.fromNat(FEE) } }));
    let from = aid({ owner = caller; subaccount = a.from_subaccount });
    let amount = Nat64.toNat(a.amount.e8s);
    let print = switch (a.created_at_time) {
      case (?t) ?(debug_show (from) # debug_show (a.to) # Nat.toText(amount) # Nat64.toText(a.memo) # Nat64.toText(t.timestamp_nanos));
      case null null;
    };
    switch (print) {
      case (?p) { switch (seen.get(p)) { case (?b) return #Err(#TxDuplicate({ duplicate_of = Nat64.fromNat(b) })); case null {} } };
      case null {};
    };
    if (bal(from) < amount + FEE) return #Err(#InsufficientFunds({ balance = { e8s = Nat64.fromNat(bal(from)) } }));
    let b = move(from, a.to, amount, a.memo);
    switch (print) { case (?p) seen.put(p, b); case null {} };
    #Ok(Nat64.fromNat(b));
  };

  // ── the cycles minting canister ──────────────────────────────────────────
  public query func get_icp_xdr_conversion_rate() : async {
    data : { xdr_permyriad_per_icp : Nat64; timestamp_seconds : Nat64 }; hash_tree : Blob; certificate : Blob;
  } {
    { data = { xdr_permyriad_per_icp = Nat64.fromNat(rate); timestamp_seconds = 0 }; hash_tree = ""; certificate = "" };
  };

  public func notify_top_up(a : { block_index : Nat64; canister_id : Principal }) : async {
    #Ok : Nat;
    #Err : {
      #Refunded : { block_index : ?Nat64; reason : Text }; #InvalidTransaction : Text;
      #Other : { error_message : Text; error_code : Nat64 }; #Processing; #TransactionTooOld : Nat64;
    };
  } {
    let i = Nat64.toNat(a.block_index);
    switch (minted.get(i)) { case (?c) return #Ok(c); case null {} };
    if (i >= blocks.size()) return #Err(#InvalidTransaction("no such block"));
    let b = blocks.get(i);
    let mine = Principal.toLedgerAccount(Principal.fromActor(MockIcp), ?subOf(a.canister_id));
    if (b.to != mine) return #Err(#InvalidTransaction("the transfer is not to the top-up account of that canister"));
    if (b.memo != TPUP) return #Err(#InvalidTransaction("the memo is not a top-up"));
    if (failNotify > 0) {
      failNotify -= 1;
      if (failNotifyHow == "reject") throw Error.reject("mock: the minting canister is busy");
      if (failNotifyHow == "refund") {
        // as the real one does: the ICP goes back to the sender, less a fee
        balances.put(mine, bal(mine) - b.amount);
        balances.put(b.from, bal(b.from) + b.amount - FEE);
        return #Err(#Refunded({ block_index = null; reason = "mock: refunded" }));
      };
      return #Err(#Processing);
    };
    let cycles = b.amount * rate;
    minted.put(i, cycles);
    Cycles.add<system>(cycles);
    await ic.deposit_cycles({ canister_id = a.canister_id });
    #Ok(cycles);
  };
};
