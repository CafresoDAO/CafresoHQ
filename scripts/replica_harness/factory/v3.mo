// A tiny canister the factory test tries to upgrade to and fails: it traps after the upgrade,
// so the IC refuses it and the factory must say why. Version 3.
actor {
  stable var n : Nat = 0;
  public func inc() : async Nat { n += 1; n };
  public query func get() : async Nat { n };
  public query func version() : async Text { "v3" };
  system func postupgrade() { assert false };
};
