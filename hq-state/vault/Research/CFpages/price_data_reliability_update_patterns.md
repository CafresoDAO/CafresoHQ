---
tags: [research, dapp-ux, market-data]
---

# Real-Time Price Data: Reliability & Update Patterns

## The Problem

Dapps live and die by price accuracy. Users make capital decisions on displayed prices, and stale/incorrect prices erode trust instantly. Yet polling price feeds naively creates cascading failure modes: if one endpoint is slow, the whole balance-calculation chain blocks; if you refresh too aggressively, you get rate-limited or hammered by browser resource warnings.

## Current State (Cafreso Wallet)

Their implementation shows a mature approach:

**Multi-source resilience:**
- CoinGecko for major tokens (ICP, UNI)
- GeckoTerminal for niche/sidechain tokens
- Uses `Promise.allSettled()` so a single endpoint outage doesn't cascade

**Smart fallback hierarchy:**
```
live prices (< 1min old) → 
24-hour localStorage cache → 
stale cache (marked & badged in UI) → 
zero-priced defaults (won't crash)
```

**60-second refresh cycle** with **source tracking** (`'live' | 'cache' | 'cache-stale' | 'default'`) so the UI can badge stale data: critical, because users need to know if they're looking at live market or historical data.

**Smart formatting:**
- Penny tokens: `$0.0001` (4 decimals)
- Normal tokens: `$1.50` (2 decimals)
- Prevents UI collapse when displaying highly-fractional token prices

## Best Practices Dapps Overlook

### 1. **Price Volatility Indicators Are More Valuable Than Prices Themselves**

Showing **24h % change, high/low range, or trend** gives users context. A token at $0.50 up 30% today is different from one up 0.2% — the delta signals opportunity or red flag.

*Implementation hint:* Extend the store to fetch `{ price, change24h, high24h, low24h }` from your data provider. CoinGecko's API includes this; GeckoTerminal may require secondary query.

### 2. **Refresh Rate Should Be Adaptive, Not Fixed**

60 seconds is reasonable for a wallet, but dapps with multi-step flows (like a swap) face a dilemma:
- **During user interaction** (e.g., typing amount, reviewing quote): aggressive refresh (every 5-10s) so quote doesn't drift
- **In background** (user reading confirmations): relaxed refresh (30-60s) to save bandwidth
- **On app visibility change** (tab blur → focus): immediate refresh to catch market moves

*Implementation:* `startPrices()` should accept optional interval parameter; listen to `document.visibilitychange` and tighten refresh when focused.

### 3. **Stale Data Warnings Must Be Unambiguous**

Their `source` tracking is great, but UI integration is critical:
- **Badge stale data** (e.g., "⚠️ Last updated 2m ago")
- **Disable/warn actions** if price is > 5min stale (user shouldn't swap on ancient data)
- **Show refresh button** so user can force-update rather than wait
- Consider **visual de-saturation** of prices in stale state

### 4. **Decimal Handling Is a Silent Killer**

Their `rawToWhole()` function handles the conversion from canister integers to display units. Common pitfalls:
- **Different decimals per token** (ICP = 8, UNI = 18, custom tokens = 0-30)
- **Rounding bias** → users see $100.01 but actually have $100.005, leading to "why can't I swap my full balance?"
- **Display vs. calc decimals** → show 2 decimals for display, but use full precision in calculations

*Implementation:* Always keep calc and display decimals separate; use `toFixed()` only for rendering, never for arithmetic.

### 5. **Rate Limiting & Request Batching**

If prices feed 10+ tokens, naive per-token fetches hit rate limits fast. Better:
- **Batch requests** (CoinGecko allows `?ids=token1,token2,token3`)
- **Request deduplication** → if two components ask for the same token price in the same second, merge into one fetch
- **Circuit breaker** → after 3 consecutive 429 errors, back off exponentially

### 6. **Partial Failure Handling**

Their `allSettled` approach is solid, but consider:
- **Partial stale fallback:** If CoinGecko returns nothing but GeckoTerminal has sGLDT, use that (don't fall back to full cache)
- **Error thresholds:** If you haven't had a live update in 1h (not just 24h cache), show stronger warning
- **Logging/monitoring:** Track which endpoints fail most often; rotate primary → secondary if primary consistently slow

## Display Patterns

### Loading State
```
- Initial load: skeleton or "Loading prices..." until first fetch
- During refresh: no visual change unless user explicitly requested ("Refresh" button)
- Failed fetch: show cache with badge, or last-known value with warning
```

### Stale Data Indicators
```
- Fresh (< 1min):    "$1.50" (no badge)
- Aging (1-5min):    "$1.50 (5m old)" or lighter color
- Stale (> 5min):    "$1.50 ⚠️ stale" in warning color, disable swaps
- Unavailable (live failed, no cache): "$0.00 —" or "price unavailable"
```

### Update Feedback
```
- Price jumped 5%+: soft highlight / pulse to draw attention
- User hit "Refresh": show spinner, disable refresh button for 2s
- Endpoint down: show red banner "Price feed offline" with fallback warning
```

## Related

- [[slippage_price_impact_ux]] — how users understand price impact beyond the base price
- [[transaction_confirmation_ux]] — showing price at time of signing vs. execution
- [[error_handling_recovery_patterns]] — handling quote expiry and price-change failures
