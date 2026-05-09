---
tags: [research, dapp-ux]
---

# Slippage & Price Impact UX

When users place a swap or trade order, the execution price may differ from the quoted price due to market movement or trading fees. Poor slippage visibility creates trust issues, failed transactions, and unexpected losses. Best practices focus on transparency before confirmation and proactive guardrails.

## Core Problem

- **Quote staleness**: A 1-minute-old price quote can be significantly different by execution time, especially on volatile assets or low-liquidity pairs
- **Hidden costs**: Users don't realize slippage is a real loss—they see "swap 1 ETH" and expect 1:1 logic, not "1 ETH = 0.98 ETH equivalent out" after fees
- **Multistep surprise**: Slippage compounds with gas fees and approval costs; users mentally math wrongly and feel deceived
- **Expert mode vs. beginner**: Advanced traders want granular control; beginners need defaults they can trust

## UX Patterns in Market Leaders

### **Uniswap (Web)**
- **Quote refresh badge**: Shows age of price quote with countdown to auto-refresh (e.g., "Quote in 10s" with spinner)
- **Slippage tolerance**: Accessible but not prominent—usually hidden until advanced menu opened, defaults to 0.5%
- **Price impact callout**: Shown inline, color-coded red for >5% impact, yellow for >1%, styled as warning
- **Execution preview**: Shows exact input/output breakdown *before* signing, plus expected outcome vs. worst case
- **Post-execution clarity**: Swap summary card shows actual slippage vs. tolerance, helps users learn

### **OpenOcean / 1Inch (Aggregators)**
- **Promo: "Best rate guaranteed"**: Explicitly promises price checking across routes, reduces slippage anxiety
- **Slippage slider visible by default**: 0.1% – 5% range with animated preview of output changing in real-time
- **Route transparency**: Shows which DEXes are being used (e.g., "60% Uniswap v3, 40% Curve"); builds trust in split logic
- **Fallback clarity**: When slippage is tight, shows warning: "May fail if market moves. Increase tolerance to +0.5% for reliability"

### **Curve Finance (Stableswap focus)**
- **Low slippage assumption**: For stable-to-stable swaps, slippage is negligible; minimal mention but not hidden
- **Pool state warning**: Warns if one asset is >90% of liquidity depth; tells user why output is moving or slippage might spike

## Key UX Principles

1. **Educate, don't overwhelm**
   - Show price impact *percentage* and *absolute value* side-by-side: "Price impact: 2.5% (-0.025 ETH)"
   - New users should see "Why is this happening?" explainers, not just numbers
   
2. **Defaults matter**
   - Start with moderate slippage (0.5%–1% for normal swaps, 0.1% for stables)
   - Higher defaults risk failed transactions; too low causes UX friction (manual tweaking)
   
3. **Real-time feedback**
   - As user changes input amount, output and slippage recalculate *instantly*
   - Quote freshness is a first-class UI element (countdown, refresh button, visual timer)
   
4. **Warnings are contextual**
   - High slippage (>5%): "Your output may be significantly less. Review price impact above."
   - Low liquidity: "Limited liquidity for this pair. Slippage may be higher than expected."
   - Stale quote: "Price quote is 30s old. Refresh before confirming."
   
5. **Confirmation ritual**
   - *Always* show a comparison: **Quoted output** vs. **Minimum output** (what you'll receive if slippage hits limit)
   - Example: "You'll receive at least 0.975 ETH (quoted 1.0 ETH, 0.5% slippage)"
   
6. **Post-execution transparency**
   - Show actual slippage in swap receipt/history
   - If slippage was 0.3% but tolerance was 0.5%, highlight: "Better than expected! +0.002 ETH saved"
   - Helps users calibrate future tolerance settings

## Common Pitfalls

- **Hidden slippage tolerance**: Buried in settings; users don't know they can adjust it → frustration when txn fails
- **Jargon-heavy**: "MEV", "execution layer", "price oracle" without context; beginners bounce
- **Ignoring quote age**: Showing a price quote without timestamp; quote could be 2m stale
- **Fake precision**: Showing output to 8 decimals when slippage is ±2% — false confidence
- **No worst-case**: Users expect exact output, not a range; shock when they get 0.97 ETH instead of 1.0

## Implementation Checklist

- [ ] Show slippage tolerance in main swap form (not advanced-only), with smart defaults per asset pair
- [ ] Display price impact as % AND absolute value, color-coded by risk (red >5%, yellow >1%)
- [ ] Include quote freshness indicator with auto-refresh or manual refresh button
- [ ] On confirmation screen: show "Min. output you'll receive if slippage hits limit"
- [ ] Add beginner mode: link to "What is slippage?" and "Why did my swap give me less?"
- [ ] Log actual slippage vs. tolerance in transaction history; celebrate when user beats the estimate
- [ ] Test on low-liquidity pairs; ensure warnings don't break the UI
- [ ] Support both % and manual input for advanced users (0.5% OR enter custom min output)

---

Related: [[transaction_confirmation_ux]], [[error_handling_recovery_patterns]]