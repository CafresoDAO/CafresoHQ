// A tiny canister the factory test installs, upgrades and rolls back. Version 1.
actor {
  stable var n : Nat = 0;
  public func inc() : async Nat { n += 1; n };
  public query func get() : async Nat { n };
  public query func version() : async Text { "v1" };
};
