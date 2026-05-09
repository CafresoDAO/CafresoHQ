---
tags: [project-study, minegold-brave, economics, pricing]
---

# Token Economics & Exchange Rate Mechanisms

**Related:** [[security-audit-findings]] · [[api-and-endpoints]] · [[state-management]] · [[key-components]]

## Overview

Minegold.brave implements a **UNI-to-sGLDT bridge** with locked exchange rates at deposit time to protect users from rate volatility during the multi-step verification process. The system also maintains cached market prices for BAT and sGLDT tokens with fallback to default values.

---

## UNI → sGLDT Exchange Rate

### Core Rate Model

```motoko
// src/backend/main.mo:74
var uniExchangeRate : Nat = 238_000_000;
// Default: 2.38 sGLDT per UNI (precision 1e8)
```

**Precision:** All rates use **1e8 (100,000,000) precision**  
**Unit:** sGLDT per UNI

**Conversion Formula:**
```motoko
// src/backend/main.mo:2028-2033
// uniAmount (e8s) * lockedExchangeRate (sGLDT per UNI in 1e8) / 1e8 = sGLDT (e8s)
let sgldtAmount = (uniAmount * effectiveRate) / 100_000_000;
```

**Example:**
- User deposits: `100 UNI` (10,000,000,000 e8s)
- Locked rate: `238,000,000` (2.38 sGLDT/UNI)
- Payout: `(10,000,000,000 * 238,000,000) / 100,000,000 = 23,800,000,000 e8s` → **238 sGLDT**

---

## Rate Locking Mechanism

### Why Lock Rates?

Deposit verification can take seconds to minutes (Etherscan API latency, calldata parsing, admin review). If the global exchange rate changes during this window, users could receive significantly different amounts than they expected.

### How It Works

```motoko
// src/backend/main.mo:1710-1721
let effectiveLockedRate : Nat = switch (rateHint) {
  case (?hint) {
    if (hint == 0 or uniExchangeRate == 0) {
      uniExchangeRate
    } else {
      let upper = uniExchangeRate + (uniExchangeRate / 2);   // +50%
      let lower = uniExchangeRate - (uniExchangeRate / 2);   // -50%
      if (hint > upper or hint < lower) uniExchangeRate else hint
    }
  };
  case null { uniExchangeRate };
};
```

**Security Constraint (Fixed in Audit):**
- Previously: **Any `rateHint > 0` was accepted** → attackers could specify both `uniAmount` and `rateHint` to drain treasury
- Now: `rateHint` must be within **±50% of current global rate**, otherwise falls back to `uniExchangeRate`

**Rate Lock at Deposit:**
```motoko
// src/backend/main.mo:1738-1740
lockedExchangeRate = ?effectiveLockedRate;
```

Once locked, this rate **persists for the entire deposit lifecycle** (pending → confirmed → paid).

**Fallback During Payout:**
```motoko
// src/backend/main.mo:2029-2032
let effectiveRate = switch (liveRequest.lockedExchangeRate) {
  case (?r) r;           // Use locked rate if available
  case null uniExchangeRate;  // Fallback to global rate (edge case for old deposits)
};
```

---

## Admin Rate Management

### Setting the Global UNI Exchange Rate

```motoko
// src/backend/main.mo:3595-3602 (adminSetUniExchangeRate)
public shared ({ caller }) func adminSetUniExchangeRate(rate : Nat) : async () {
  if (not isAdmin(caller)) {
    Runtime.trap("Unauthorized: admin only");
  };
  if (rate == 0) {
    Runtime.trap("Invalid rate: must be greater than 0");
  };
  uniExchangeRate := rate;
};
```

**Access:** Admin only  
**Validation:** `rate > 0`  
**Effect:** Updates `uniExchangeRate` immediately; **does NOT affect deposits with locked rates**

**Use Cases:**
- Market price changes (UNI or sGLDT volatility)
- Treasury management (adjust conversion ratio to maintain liquidity)
- Initial launch rate adjustments

---

## Price Feeds & Caching

### Cached Market Prices

```motoko
// src/backend/main.mo:91-98
var cachedBatPrice : ?{
  price : Nat;
  timestamp : Time.Time;
} = null;
var cachedSGldtPrice : ?{
  price : Nat;
  timestamp : Time.Time;
} = null;
```

### Cache Configuration

```motoko
// src/backend/main.mo:41-43
let PRICE_CACHE_DURATION = 300_000_000_000; // 5 minutes in nanoseconds
let BAT_DEFAULT_PRICE = 300;         // $3.00 (2 decimal precision)
let SGLDT_DEFAULT_PRICE = 180_000;   // $1,800.00 (2 decimal precision)
```

**Cache TTL:** 5 minutes  
**Precision:** BAT uses cents (2 decimals), sGLDT uses cents (2 decimals)

### Price Query Functions

```motoko
// src/backend/main.mo:3763-3787
public shared ({ caller }) func getBatPrice() : async Nat {
  switch (cachedBatPrice) {
    case (null) { BAT_DEFAULT_PRICE };  // No cached price → fallback
    case (?{ price; timestamp }) {
      if (Time.now() - timestamp > PRICE_CACHE_DURATION) {
        BAT_DEFAULT_PRICE;  // Stale cache → fallback
      } else {
        price;  // Fresh cache → return cached price
      };
    };
  };
};

public shared ({ caller }) func getSGLDTPrice() : async Nat {
  // Same logic as getBatPrice
};
```

**Behavior:**
1. If no cached price exists → return default
2. If cache is **older than 5 minutes** → return default
3. If cache is fresh → return cached value

**Note:** The code does **not include price update logic** — caching infrastructure exists but no external oracle integration is implemented. Prices can only be manually set by admin (not shown in current codebase).

---

## Fee Structure

### Dynamic Fee Queries

The system **dynamically fetches** ledger fees at transaction time to avoid hardcoded fee mismatches:

```motoko
// src/backend/main.mo:2045-2052 (verifyAndPayUNIDeposit)
let fee = try {
  await sgldtLedger.icrc1_fee()
} catch (_feeErr) {
  // Standard ICRC-1 fee for sGLDT; fall back if ledger is unreachable.
  10_000  // 0.0001 sGLDT
};
```

**Fallback:** 10,000 e8s (0.0001 tokens) if ledger query fails

### Fee Payment Model

**sGLDT Transfers (UNI deposit payouts):**
```motoko
// src/backend/main.mo:2076-2083
let transferResult = await sgldtLedger.icrc1_transfer({
  from_subaccount = null;
  to = { owner = liveRequest.submitter; subaccount = null };
  amount = sgldtAmount;  // Fee is DEDUCTED from this amount by ledger
  fee = ?fee;            // Explicit fee passed to ledger
  memo = null;
  created_at_time = null;
});
```

**ckUNI Transfers:**
```motoko
// src/backend/main.mo:872 (bridgeCkUNI)
let fee = await ckUNILedger.icrc1_fee();
// Fee deducted from transfer amount
```

**Admin Transfers:**
Admin can override fee by passing `fee = null`, which tells the ledger to use its **current default fee** at execution time (prevents race conditions from fee changes between fetch and transfer).

---

## Zero-Payout Protection

```motoko
// src/backend/main.mo:2035-2040
if (sgldtAmount == 0) {
  // Revert to #confirmed so admin can retry after fixing exchange rate
  let revertedRequest = { liveRequest with status = #confirmed };
  uniDeposits.add(requestId, revertedRequest);
  return "failed: Calculated payout is zero. Check exchange rate and UNI amount.";
};
```

**Why Zero Payouts Occur:**
1. **Exchange rate = 0** (admin misconfiguration)
2. **Dust deposits** (UNI amount too small after integer division)
3. **Arithmetic underflow** (rate * amount < 1e8)

**Recovery:** Deposit reverts to `#confirmed` state → admin can fix rate and call `triggerSGLDTPayout` to retry.

---

## Transaction Types & Economic Events

```motoko
// src/backend/main.mo:219-224
public type TxType = {
  #Bridge;   // UNI sent on Ethereum side → sGLDT payout
  #Mint;     // ckUNI minted on ICP (not used in current UNI flow)
  #Refine;   // sGLDT released from treasury
  #Transfer; // user-initiated token transfer
};
```

**Economic Flow for UNI Deposits:**
1. User sends UNI to Ethereum helper contract → **#Bridge event created**
2. Canister verifies tx on Etherscan → **Deposit status updated**
3. Canister transfers sGLDT from treasury to user → **Payout completes**
4. Transaction history records: `txType = #Bridge`, `amount = sgldtAmount`, `ethTxHash = txHash`

---

## Security Considerations

### ⚠️ Critical: Rate Hint Validation (C-01 Remediation)

See [[security-audit-findings#C-01]] — Prior to the fix, attackers could:
1. Submit deposit with `uniAmount = 1,000,000 UNI` (fake)
2. Provide `rateHint = 999,999,999` (999x inflated)
3. Payout formula: `1,000,000 * 999,999,999 / 1e8` → drain treasury

**Fix:** `rateHint` is now **clamped to ±50% of global rate**.

### Rate Lock Edge Cases

**Old Deposits Without Locked Rate:**
If a deposit was created before rate-locking was implemented, `lockedExchangeRate = null` → falls back to **current global rate** at payout time.

**Global Rate = 0:**
If admin sets `uniExchangeRate = 0` and a deposit has no locked rate, payout will be **0 sGLDT** and deposit will revert to `#confirmed` for admin to fix.

---

## Key Takeaways

✅ **Exchange rates are locked at deposit submission** to protect users from volatility  
✅ **Rate hints are validated** (±50% of global rate) to prevent treasury drainage  
✅ **Fees are dynamically fetched** from ledgers to avoid hardcoded mismatches  
✅ **Zero-payout deposits are caught** and reverted for admin review  
✅ **Price caching exists** but no oracle integration is implemented  
✅ **Admin can update global rate** without affecting in-flight deposits

**Related Security:** See [[security-audit-findings]] for C-01 (failed tx payouts) and C-02 (address ownership) vulnerabilities.