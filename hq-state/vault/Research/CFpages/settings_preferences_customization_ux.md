---
tags: [research]
---

# Settings, Preferences, and Customization UX

## Core Patterns

**Slippage tolerance preset selection**
- Quick toggle buttons (0.1%, 0.5%, 1%) with custom input fallback
- Visual feedback showing impact on quote (estimated output ranges)
- Persistence across sessions with tooltip explaining impact

**Gas settings customization**
- Standard/Fast/Custom radio buttons with live gas price updates
- Custom: show limit and priority fee sliders with estimated time-to-block
- Display current network-recommended range as reference
- Auto-clear custom settings on network switch

**Default behaviors**
- Toggle for "auto-wrap native token" or similar chain-specific defaults
- Remember last selected token pair (but warn if liquidity changed)
- Optional: "Expert mode" toggle hiding advanced fields from casual users

**Display preferences**
- Chart timeframe memory (1D, 7D, 1M, etc.)
- USD vs native currency display toggle
- Dark/light theme persistence
- Decimal precision for token display (2 vs 8 decimals)

## Common Pitfalls

1. **Lost settings on network switch** – Users set slippage on Ethereum, switch to Polygon, expect same setting; should warn if switching to lower-liquidity chain
2. **Settings scattered** – Gas, slippage, and display prefs in separate modals; consolidate into one settings panel
3. **No feedback on impact** – Changing slippage tolerance with no immediate quote recalc feels broken
4. **Onboarding the settings** – New users don't find advanced settings; consider in-line help or interactive tour

## Improvement Ideas

- **Settings sidebar** instead of modal; always accessible during swap flow
- **Presets for user personas**: "Conservative" (0.1% slippage, standard gas), "Aggressive" (1% slippage, fast gas)
- **Import/export settings** as JSON for multi-device sync
- **Audit log** of settings changes (when slippage was updated, why a swap uses custom gas, etc.)
- **Per-token defaults**: remember that USDC swaps always use fast gas, SHIB always allows 1% slippage

## Related Notes

- [[gas_fee_transparency_ux]] – gas settings deep-dive
- [[slippage_price_impact_ux]] – how slippage impacts quote
- [[wallet_onboarding_patterns]] – where settings discovery begins
